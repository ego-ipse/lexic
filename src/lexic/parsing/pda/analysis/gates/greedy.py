"""The split-greedy loop licence — a decision policy settles, not lookahead.

A unit whose item can be EMPTY carves every document many ways: `para ::= line+
blank` with `line ::= [a-z]* nl` reads a blank line either as the paragraph's
tail or as one more empty line inside it. Every carving is the SAME production
over the same span with the same arm, so it is a SPLIT, and a split is never an
ambiguity — `tables/splits.py` gives it one answer, the leftmost chain.

**No k separates that decision, and none has to.** After a terminator, the next
character being a body character is consistent with "that terminator ended an
empty item" and with "that terminator was the tail, and the next unit's body
follows"; both derive the whole document, so `kwindow.loop_gate` declines and is
right to. What decides it is the policy: the leftmost chain gives the FIRST slot
all it can take, the first slot here IS the loop, and therefore the loop runs
greedily and exits exactly where it must — when what remains is the unit's tail
and the enclosing continuation.

**The exchange that proves it.** Take any parse into units and any unit that is
not the last. Its tail is `m` copies of the terminator `t`, and those can be
re-read as `m` items whose body is empty — legal because the body is nullable,
unambiguous because no body can hold `t`. Having given up its tail, that unit
must continue into the next one's items and take ITS tail, so it absorbs it.
Iterating collapses every multi-unit parse, and the leftmost chain selects the
fully-absorbed one. It stops at the final boundary, where re-reading the last
`m` terminators would leave the unit with no tail to end with.

**What the licence does NOT claim.** The gate asserts the policy proof and
nothing else: a failed exit test says "do not exit HERE", never that another
item parses. Ordinary item recognition and the loop's own minimum stay in force.
And every reader below returns ``None`` for "cannot tell", which fails its
condition — a certifier that guesses is worse than none, because it is believed.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from lexic.ir import IrNone
from lexic.ir.grammar.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
)

_DEPTH = 8
"""How far a reader follows a reference before it declines."""


GreedySpec = tuple[str, str, "frozenset[str] | None"]
"""``(tail, close, starters)`` — what the clone compiler wraps as its gate.

``tail`` is ``m`` copies of the terminator; ``close`` is the continuation
matched in full after it, empty where the certified boundary is the end of the
input; ``starters`` are the characters the continuation may BEGIN with, when
those are disjoint from what an item can begin with, and ``None`` when the
continuation is matched by spelling instead.
"""


def greedy_loop_gate(
    rules: Mapping[str, IrRule],
    start: str,
    unit: str,
    items: Sequence[IrItem],
    idx: int,
) -> GreedySpec | None:
    """The licence for item ``idx`` of ``unit``'s arm, or ``None`` to decline.

    Seven conditions, every one read off the grammar:

    a. the item repetition is UNBOUNDED — the absorption has no ceiling;
    b. the terminator is a SINGLE character no body character can be;
    c. the body is nullable and the terminator is nonempty;
    d. the unit's tail is exactly ``m`` copies of the terminator;
    e. the continuation is settled — the certified end of input, a starter set
       disjoint from what an item can begin with, or a fixed literal matched in
       full;
    f. the unit occurs as ``U+ C`` or ``U* C`` with ONE unit permitted, so the
       absorption has somewhere to collapse to;
    g. the body derives ε in exactly ONE way, so the items the exchange
       introduces carry no choice of their own.

    :param rules: The grammar's rule table.
    :param start: The start rule's name.
    :param unit: The enclosing rule's name.
    :param items: That rule's arm.
    :param idx: The looping item's index.
    :returns: The gate, or ``None`` where any condition is unmet or unknown.
    """
    shape = _unit_shape(rules, items, idx)
    if shape is None:
        return None
    body, terminator, tail = shape
    begins = _item_starts(rules, body, terminator)
    return _continuation(rules, start, unit, tail, begins)


def _unit_shape(
    rules: Mapping[str, IrRule], items: Sequence[IrItem], idx: int
) -> tuple[list[IrItem], str, str] | None:
    """Conditions (a)–(d) and (g) — the unit and its item, or ``None``.

    :returns: ``(body items, terminator, tail)``.
    """
    item = items[idx]
    if item.quantifier.hi is not IrNone or idx != 0 or len(items) != 2:
        return None  # (a) unbounded, and the shape is `I+ T` — one loop, one tail
    item_rule = _sole_arm(rules, item.atom)
    if item_rule is None or len(item_rule) < 2:
        return None
    body, term = list(item_rule[:-1]), item_rule[-1]
    terminator = _spelling(rules, term.atom)
    if terminator is None or not _item_is_delimited(rules, body, term, terminator):
        return None
    tail = _spelling(rules, items[1].atom)
    if tail is None or not _exactly_once(items[1]):
        return None
    if not tail or tail != terminator * len(tail):
        return None  # (d)
    return body, terminator, tail


def _exactly_once(item: IrItem) -> bool:
    """Does ``item`` occur exactly once — read off its bounds, not its repr."""
    return int(item.quantifier.lo) == 1 and item.quantifier.hi == 1


def _item_is_delimited(
    rules: Mapping[str, IrRule],
    body: Sequence[IrItem],
    term: IrItem,
    terminator: str,
) -> bool:
    """Conditions (b), (c) and (g) on one item's body and terminator.

    (b) a SINGLE-character terminator no body character can be — a longer one
    could overlap itself or straddle a boundary; (c) the body is nullable;
    (g) it derives ε in exactly one way.
    """
    held = _alphabet_of(rules, body)
    return (
        len(terminator) == 1
        and _exactly_once(term)
        and held is not None
        and terminator not in held
        and not any(int(one.quantifier.lo) for one in body)
        and _uniquely_empty(rules, body) is True
    )


def _continuation(
    rules: Mapping[str, IrRule],
    start: str,
    unit: str,
    tail: str,
    begins: frozenset[str] | None,
) -> GreedySpec | None:
    """Conditions (e) and (f) — what settles the boundary after the unit.

    A continuation's FIRST set is not its occurrence boundary: where the two
    sets meet, only matching the continuation in full against the end of input
    settles it, and its length is charged to the gate's width.
    """
    arm = _sole_arm(rules, IrRuleRef(start))
    if not arm:
        return None
    outer, after = arm[0], list(arm[1:])
    if (
        str(outer.atom) != unit
        or int(outer.quantifier.lo) > 1  # (f): one unit must be permitted
        or outer.quantifier.hi is not IrNone  # (f): a bounded outer cannot absorb
    ):
        return None
    if not after:
        return (tail, "", None)
    starts = _starts_of(rules, after)
    if starts is None or begins is None:
        return None
    if not starts & begins:
        return (tail, "", frozenset(starts))
    close = _spelling_of(rules, after)
    return None if close is None else (tail, close, None)


def _sole_arm(rules: Mapping[str, IrRule], atom: object) -> list[IrItem] | None:
    """The single arm of the rule ``atom`` names, or ``None``.

    An alternation is a choice the licence has nothing to say about, and
    anything that is not a plain reference is not this shape.
    """
    if not isinstance(atom, IrRuleRef):
        return None
    rule = rules.get(str(atom))
    if rule is None or not isinstance(rule.body, IrAlternation) or len(rule.body) != 1:
        return None
    return list(rule.body[0])


def _spelling(rules: Mapping[str, IrRule], atom: object, depth: int = 0) -> str | None:
    """The one fixed string ``atom`` derives, or ``None`` — unknown included."""
    if depth > _DEPTH:
        return None
    if isinstance(atom, IrLiteral):
        return str(atom)
    arm = _sole_arm(rules, atom)
    return None if arm is None else _spelling_of(rules, arm, depth + 1)


def _spelling_of(
    rules: Mapping[str, IrRule], items: Sequence[IrItem], depth: int = 0
) -> str | None:
    """The one fixed string a sequence derives, or ``None``."""
    out: list[str] = []
    for item in items:
        if not _exactly_once(item):
            return None
        text = _spelling(rules, item.atom, depth)
        if text is None:
            return None
        out.append(text)
    return "".join(out)


def _named_rule(rules: Mapping[str, IrRule], atom: object, depth: int) -> IrRule | None:
    """The rule ``atom`` names, or ``None`` — depth exhaustion included."""
    if depth > _DEPTH or not isinstance(atom, IrRuleRef):
        return None
    return rules.get(str(atom))


def _alphabet(
    rules: Mapping[str, IrRule], atom: object, depth: int = 0
) -> set[str] | None:
    """Every character ``atom`` can hold, or ``None`` where that is unknowable.

    ``None``, never the empty set: an empty set claims disjointness from
    everything, and an atom nobody could read has claimed nothing.
    """
    if isinstance(atom, IrCharClass):
        return {chr(point) for point in atom.members()}
    if isinstance(atom, IrLiteral):
        return set(str(atom))
    rule = _named_rule(rules, atom, depth)
    if rule is None:
        return None
    out: set[str] = set()
    for arm in rule.body:
        for item in arm:
            more = _alphabet(rules, item.atom, depth + 1)
            if more is None:
                return None
            out |= more
    return out


def _alphabet_of(
    rules: Mapping[str, IrRule], items: Sequence[IrItem]
) -> set[str] | None:
    """Every character a sequence can hold, or ``None``."""
    out: set[str] = set()
    for item in items:
        more = _alphabet(rules, item.atom)
        if more is None:
            return None
        out |= more
    return out


def _starts_of(rules: Mapping[str, IrRule], items: Sequence[IrItem]) -> set[str] | None:
    """What a sequence can BEGIN with, walking past a nullable leading item."""
    out: set[str] = set()
    for item in items:
        chars = _alphabet(rules, item.atom)
        if chars is None:
            return None
        out |= chars
        if int(item.quantifier.lo) > 0:
            break
    return out


def _item_starts(
    rules: Mapping[str, IrRule], body: Sequence[IrItem], terminator: str
) -> frozenset[str] | None:
    """What ONE item can begin with — the body's starts, and the terminator.

    The terminator belongs in the set because the body is nullable: an item
    whose body is empty begins with its terminator.
    """
    starts = _starts_of(rules, body)
    return None if starts is None else frozenset(starts | {terminator})


def _uniquely_empty(
    rules: Mapping[str, IrRule], items: Sequence[IrItem], depth: int = 0
) -> bool | None:
    """Does this sequence derive ε in exactly ONE way?

    "Nullable" says an ε derivation EXISTS; the exchange needs it to be the
    only one. Taking every quantifier zero times is one, and it is the only one
    when no POSITIVE count can also derive ε — so ``[a-z]*`` qualifies, because
    ``[a-z]`` always consumes a character, and ``w*`` with ``w ::= [a-z]*`` does
    NOT: it derives ε as zero ``w``, as one empty ``w``, as two, with no arm
    choice anywhere. A nullable operand under an optional or a repetition is not
    a proof of uniqueness, and this licence does not guess one.
    """
    if depth > _DEPTH:
        return None
    for item in items:
        if int(item.quantifier.lo) != 0:
            return False
        verdict = _item_uniquely_empty(rules, item, depth)
        if verdict is not True:
            return verdict
    return True


def _item_uniquely_empty(
    rules: Mapping[str, IrRule], item: IrItem, depth: int
) -> bool | None:
    """One zero-lower-bound item's contribution to uniqueness.

    An operand that cannot itself derive ε settles it: zero repetitions is then
    the only way this item contributes nothing, whatever the operand's shape.
    An earlier version went on to ask whether the operand's own BODY derived ε
    uniquely, which is a different question and the wrong one — it answered
    False for a named operand and so licensed ``i ::= [a]* t`` while refusing
    the identical ``i ::= letter* t`` with ``letter ::= [a]``. Spelling a
    character class as a rule is not a change of language.
    """
    empty = _derives_empty(rules, item.atom, depth)
    if empty is None:
        return None  # unknown — never assumed either way
    return not empty  # a nullable operand: zero repeats is not the unique ε


def _derives_empty(
    rules: Mapping[str, IrRule], atom: object, depth: int = 0
) -> bool | None:
    """Can ``atom`` itself derive ε? ``None`` where that is not knowable."""
    if isinstance(atom, IrCharClass):
        return False
    if isinstance(atom, IrLiteral):
        return not str(atom)
    rule = _named_rule(rules, atom, depth)
    if rule is None:
        return None
    verdicts = [_arm_derives_empty(rules, arm, depth) for arm in rule.body]
    if any(one is None for one in verdicts):
        return None
    return any(verdicts)


def _arm_derives_empty(
    rules: Mapping[str, IrRule], arm: Sequence[IrItem], depth: int
) -> bool | None:
    """Can one arm derive ε? ``None`` where an item cannot be read."""
    for item in arm:
        if int(item.quantifier.lo) == 0:
            continue
        inner = _derives_empty(rules, item.atom, depth + 1)
        if inner is not True:
            return inner
    return True
