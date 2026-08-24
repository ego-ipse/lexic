"""Role derivation — what a grammar's anchor characters DO at a split point.

The window scan needs three character roles: openers and closers (the
depth count), and separators (the split candidates). The demonstrable
shapes are derived from the grammar, never hardcoded per formulation:

- **Pair** — an arm opening with a unit single-char anchor literal whose
  LAST anchor literal closes over a reference or group interior:
  ``"{" ws members "}" ws`` derives the pair ``{`` → ``}`` (trailing noise
  after the closer is fine; a closer is the last structural mark, not the
  last item).
- **Separator** — the anchor literal every arm of a repeated body leads
  with: a rule referenced with an unbounded quantifier (the hoisted
  ``(sep unit)*`` shape) or an inline unbounded group. The lead resolves
  through unit rule references — ``members-item ::= comma member`` with
  ``comma ::= ","`` derives ``,``.

A mark is a SPELLING, not a character: a blank-line boundary spells two. What
makes one readable is the property one character has — every character of it is
an anchor, so no opaque interior can spell it. Pair roles stay single-char:
depth is counted one character at a time. Marks are offered shortest first, so
a grammar whose boundary is already one character keeps the plan it had.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
)
from lexic.parsing.parallel.discovery.anchors import anchors
from lexic.parsing.parallel.discovery.shapes import (
    MARK_ARITY,
    UNIT,
    exact_text,
    last_charset,
    unbounded,
)
from lexic.parsing.pda.core.charsets import CharSet


class Separator(NamedTuple):
    """One repetition separator, with the rules a split orchestration needs.

    :ivar mark: The separator spelling.
    :ivar container: The rule owning the ``unit item*`` arm (``members``).
    :ivar item: The repeated rule (``members-item``); ``""`` for an inline
        group (un-hoisted authored grammars — not orchestratable as-is).
    :ivar lead: The rule the item's arms lead with (``comma``); ``""`` when
        the lead is a bare literal or the arms disagree.
    """

    mark: str
    container: str
    item: str
    lead: str


class Terminator(NamedTuple):
    """One repetition terminator — a repeated unit's own final character.

    ``root ::= line+`` with ``line ::= text "\\n"`` repeats a unit that ENDS
    with an anchor, so a cut after any occurrence lands between two complete
    units and each chunk is a document in its own right.

    :ivar mark: The terminating spelling.
    :ivar container: The rule owning the repeated item.
    :ivar unit: The repeated rule.
    """

    mark: str
    container: str
    unit: str


class Roles(NamedTuple):
    """One grammar's derived anchor roles.

    :ivar pairs: ``(opener, closer)`` character pairs, definition order.
    :ivar records: The separator records, definition order.
    :ivar terminators: The terminator records, definition order.
    """

    pairs: tuple[tuple[str, str], ...]
    records: tuple[Separator, ...]
    terminators: tuple[Terminator, ...] = ()

    @property
    def separators(self) -> frozenset[str]:
        """The separator spellings — the scan's mark set."""
        return frozenset(record.mark for record in self.records)

    @property
    def marks(self) -> frozenset[str]:
        """Every spelling the scan marks: separators and terminators."""
        return self.separators | {record.mark for record in self.terminators}


def _anchor_char(item: IrItem, anchor_set: frozenset[str]) -> str | None:
    """The item's character when it is a unit-quantified single-char anchor."""
    chars = _anchor_chars(item, anchor_set)
    return next(iter(chars)) if len(chars) == 1 else None


def _anchor_chars(item: IrItem, anchor_set: frozenset[str]) -> frozenset[str]:
    """All finite anchor alternatives one unit-quantified item can emit."""
    atom = item.atom
    if item.quantifier != UNIT:
        return frozenset()
    if isinstance(atom, IrLiteral):
        text = str(atom)
        return frozenset(text) if len(text) == 1 and text in anchor_set else frozenset()
    if not isinstance(atom, IrCharClass):
        return frozenset()
    emits = CharSet.from_charclass(atom)
    return (
        frozenset(emits.chars)
        if not emits.negated and emits.chars and emits.chars <= anchor_set
        else frozenset()
    )


def _anchor_marks(item: IrItem, anchor_set: frozenset[str]) -> frozenset[str]:
    """Every mark SPELLING one unit-quantified item can emit.

    A literal of any width qualifies when every character of it is an anchor:
    that is what a window scan needs to find its occurrences without left
    context, and it is the same property a single character carries.
    """
    found = _anchor_chars(item, anchor_set)
    if found:
        return found
    atom = item.atom
    if item.quantifier != UNIT or not isinstance(atom, IrLiteral):
        return frozenset()
    text = str(atom)
    wide = len(text) > 1 and set(text) <= anchor_set
    return frozenset({text}) if wide else frozenset()


def _arm_pair(
    items: tuple[IrItem, ...], anchor_set: frozenset[str]
) -> tuple[str, str] | None:
    """The arm's opener/closer pair, when it has the bracketing shape."""
    if len(items) < 3:
        return None
    opener = _anchor_char(items[0], anchor_set)
    if opener is None:
        return None
    closer_at = next(
        (
            j
            for j in range(len(items) - 1, 0, -1)
            if _anchor_char(items[j], anchor_set) is not None
        ),
        0,
    )
    closer = _anchor_char(items[closer_at], anchor_set)
    if closer is None or closer == opener:
        return None
    interior = any(
        isinstance(item.atom, (IrRuleRef, IrAlternation)) for item in items[1:closer_at]
    )
    return (opener, closer) if interior else None


def _lead_info(
    item: IrItem,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    seen: frozenset[str],
) -> tuple[set[str], str] | None:
    """``(anchor marks, lead-rule name)`` for one leading item.

    The name is the OUTERMOST unit rule reference the lead resolves through
    (``comma``), or ``""`` for a bare literal lead.
    """
    chars = _anchor_marks(item, anchor_set)
    if chars:
        return (set(chars), "")
    atom = item.atom
    resolvable = (
        isinstance(atom, IrRuleRef)
        and item.quantifier == UNIT
        and str(atom) in by_name
        and str(atom) not in seen
    )
    if not resolvable:
        return None
    name = str(atom)
    inner = _body_leads(by_name[name].body, by_name, anchor_set, seen | {name})
    return None if inner is None else (inner[0], name)


def _body_leads(
    body: IrAlternation,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    seen: frozenset[str] = frozenset(),
) -> tuple[set[str], str] | None:
    """What EVERY arm of a repeated body leads with, or ``None``.

    A body only separates if all arms lead with anchors; the lead name is
    the arms' common rule, ``""`` when they disagree or are bare literals.
    """
    chars: set[str] = set()
    names: set[str] = set()
    for arm in body:
        items = tuple(arm)
        if not items:
            return None
        found = _lead_info(items[0], by_name, anchor_set, seen)
        if found is None:
            return None
        chars |= found[0]
        names.add(found[1])
    lead = names.pop() if len(names) == 1 else ""
    return (chars, lead)


def roles(grammar: IrAst) -> Roles:
    """Derive the grammar's opener/closer pairs and repetition separators.

    :param grammar: The grammar to analyse (the codegen grammar for a
        compiled artefact — repetition groups are hoisted there, so the
        ``(sep unit)*`` shape appears as an unbounded rule reference).
    :returns: The derived :class:`Roles`; empty roles when nothing matches.
    """
    anchor_set = anchors(grammar)
    by_name: dict[str, IrRule] = {str(rule.name): rule for rule in grammar.rules}
    pairs: list[tuple[str, str]] = []
    records: list[Separator] = []
    for rule in grammar.rules:
        for arm in rule.body:
            items = tuple(arm)
            pair = _arm_pair(items, anchor_set)
            if pair is not None and pair not in pairs:
                pairs.append(pair)
            for item in items:
                _repeated_separators(str(rule.name), item, by_name, anchor_set, records)
    paired = {char for pair in pairs for char in pair}
    kept = tuple(record for record in records if not set(record.mark) & paired)
    ended = tuple(
        record
        for record in _terminators(grammar, by_name, anchor_set)
        if not set(record.mark) & paired
    )
    return Roles(tuple(pairs), kept, ended)


def _terminators(
    grammar: IrAst, by_name: dict[str, IrRule], anchor_set: frozenset[str]
) -> list[Terminator]:
    """Every unbounded reference whose target ends with an agreed anchor mark."""
    out: list[Terminator] = []
    for rule in grammar.rules:
        for arm in rule.body:
            for item in arm:
                target = item.atom
                if not unbounded(item) or not isinstance(target, IrRuleRef):
                    continue
                unit = str(target)
                if unit not in by_name:
                    continue
                for mark in _edge_marks(by_name[unit], by_name, anchor_set):
                    record = Terminator(mark, str(rule.name), unit)
                    if record not in out:
                        out.append(record)
    return out


def _edge_marks(
    unit: IrRule, by_name: dict[str, IrRule], anchor_set: frozenset[str]
) -> tuple[str, ...]:
    """The terminator spellings every arm of ``unit`` agrees on, shortest first.

    The single agreed character is what a repetition has always been cut on. A
    unit whose boundary is wider — a text line's own terminator plus the blank
    line that closes the paragraph — agrees on a spelling instead. Both are
    offered and the cascade tries the narrower one first, so a grammar that
    already splits keeps exactly the plan it had.
    """
    seen = frozenset({str(unit.name)})
    char = _body_edge(unit.body, -1, by_name, anchor_set, seen)
    wide = agreed_tail(unit.body, MARK_ARITY, by_name, seen)
    found = [mark for mark in (char, wide) if mark and set(mark) <= anchor_set]
    return tuple(dict.fromkeys(found))


def _item_edge(
    item: IrItem,
    at: int,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    seen: frozenset[str],
) -> str | None:
    """One structural edge, resolving unit rule-reference wrappers.

    A longer literal carries an edge too: ``@lexical`` inlining merges a
    unit's tail into spellings like ``"}\\n"``, and the terminator is that
    literal's LAST character. It counts only when it occurs nowhere else in
    the spelling — an interior occurrence would be scanned as a mark inside
    the unit, which is exactly what the safety proof must refuse.
    """
    char = _anchor_char(item, anchor_set)
    if char is not None:
        return char
    atom = item.atom
    if item.quantifier != UNIT:
        return None
    if isinstance(atom, IrLiteral):
        text = str(atom)
        edge = text[at] if text else ""
        good = len(text) > 1 and edge in anchor_set and text.count(edge) == 1
        return edge if good else None
    if not isinstance(atom, IrRuleRef):
        return None
    name = str(atom)
    target = by_name.get(name)
    if target is None or name in seen:
        return None
    return _body_edge(target.body, at, by_name, anchor_set, seen | {name})


def _body_edge(
    body: IrAlternation,
    at: int,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    seen: frozenset[str],
) -> str | None:
    """The common recursively resolved structural edge of every arm."""
    chars: set[str] = set()
    for arm in body:
        items = tuple(arm)
        if not items:
            return None
        char = _item_edge(items[at], at, by_name, anchor_set, seen)
        if char is None:
            return None
        chars.add(char)
    return chars.pop() if len(chars) == 1 else None


def _repeated_separators(
    container: str,
    item: IrItem,
    by_name: dict[str, IrRule],
    anchor_set: frozenset[str],
    records: list[Separator],
) -> None:
    """Collect the separator records an unbounded item contributes."""
    if not unbounded(item):
        return
    atom = item.atom
    if isinstance(atom, IrRuleRef) and str(atom) in by_name:
        repeated, body = str(atom), by_name[str(atom)].body
    elif isinstance(atom, IrAlternation):
        repeated, body = "", atom
    else:
        return
    found = _body_leads(body, by_name, anchor_set)
    if found is None:
        return
    chars, lead = found
    for mark in sorted(chars, key=lambda spelling: (len(spelling), spelling)):
        record = Separator(mark, container, repeated, lead)
        if record not in records:
            records.append(record)


def agreed_tail(
    body: IrAlternation, want: int, rule_map: dict[str, IrRule], path: frozenset[str]
) -> str:
    """The last ``want`` characters EVERY arm of ``body`` ends with, or ``""``.

    The conjunction the terminator derivation runs on, one character wider than
    a single agreed edge: a unit whose arms disagree on their tail has no
    terminator spelling, exactly as it has no terminator character.
    """
    found = {arm_tail(tuple(arm), want, rule_map, path) for arm in body}
    return found.pop() if len(found) == 1 else ""


def arm_tail(
    items: tuple[IrItem, ...],
    want: int,
    rule_map: dict[str, IrRule],
    path: frozenset[str],
) -> str:
    """The last ``want`` characters every derivation of one arm ends with.

    Two productions reach a two-character tail: the arm's final item spells
    both, or it spells the second EXACTLY and everything before it always ends
    with the first. The exactness is what licenses reaching leftward — an item
    of variable width puts its own text between the two characters.
    """
    if not items or want <= 0:
        return ""
    last = items[-1]
    whole = exact_text(last, rule_map, path)
    if len(whole) >= want:
        return whole[-want:]
    if whole:
        head = arm_tail(items[:-1], want - len(whole), rule_map, path)
        return head + whole if head else ""
    return _open_tail(items, want, rule_map, path)


def _open_tail(
    items: tuple[IrItem, ...],
    want: int,
    rule_map: dict[str, IrRule],
    path: frozenset[str],
) -> str:
    """The tail of an arm whose final item has no fixed text of its own.

    A reference is followed into its arms, which must agree. Failing that, only
    the final CHARACTER can be fixed, and only when the item's ending alphabet
    is a single positive character — a wider set ends more than one way. That
    character never licenses reaching further left: an item of unknown width
    puts its own text between whatever precedes it and its final character.
    """
    last = items[-1]
    atom = last.atom
    name = str(atom) if isinstance(atom, IrRuleRef) else ""
    target = rule_map.get(name) if name and name not in path else None
    if target is not None and last.quantifier == UNIT:
        found = agreed_tail(target.body, want, rule_map, path | {name})
        if found:
            return found
    edge = _sole(last_charset(items, rule_map, path))
    return edge if want == 1 else ""


def _sole(found: CharSet) -> str:
    """The one character a set holds, or ``""`` when it holds any other number."""
    if found.negated or len(found.chars) != 1:
        return ""
    return next(iter(found.chars))
