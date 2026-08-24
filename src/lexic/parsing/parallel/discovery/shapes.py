"""Arm shapes — the questions the split analyses ask a grammar's arms.

:mod:`~lexic.parsing.parallel.discovery.interiors`,
:mod:`~lexic.parsing.parallel.discovery.regions`,
:mod:`~lexic.parsing.parallel.roles` and
:mod:`~lexic.parsing.parallel.stitch.safety` read a grammar for the same
handful of facts: what one item spells, whether it repeats, what every arm of
an alternation carries at one end, and which characters a derivation can emit
— anywhere, first, or last. They live here so that changing what "spells one
character" means reaches all of them at once.

A mark is a SPELLING, and past one character emission stops answering
containment: ``para ::= line+`` over ``line ::= [a-z]* "\\n"`` has no atom
spelling ``"\\n\\n"`` and derives it anyway, because an empty line stands beside
another and the two terminators meet. So the emission family has a spelling
half — :func:`rule_spells` — that refuses ASSEMBLY as well as emission, and
answers "can spell" for everything it cannot decide.
"""

from __future__ import annotations

from collections.abc import Callable

from lexic.ir import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNoneType,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
)
from lexic.parsing.pda.core.charsets import CharSet

UNIT = IrQuantifier()
"""The unit quantifier — exactly one occurrence."""


def unbounded(item: IrItem) -> bool:
    """Whether the item repeats without an upper bound."""
    return isinstance(item.quantifier.hi, IrNoneType)


def repeats(item: IrItem) -> bool:
    """Whether the item may occur more than once, so it stands beside itself."""
    hi = item.quantifier.hi
    return isinstance(hi, IrNoneType) or int(hi) > 1


def _one_char(text: str) -> bool:
    """Whether a spelling is exactly one character."""
    return len(text) == 1


def _any_text(text: str) -> bool:
    """Whether a spelling carries anything at all."""
    return bool(text)


def _spelling(
    item: IrItem, rule_map: dict[str, IrRule], accept: Callable[[str], bool]
) -> str | None:
    """The literal an item spells, through one unit rule reference.

    A grammar may name its punctuation (``begin-object ::= ws "{" ws``), and
    the punctuation may sit among noise, so a rule spells one literal when
    exactly one of its items does.
    """
    if item.quantifier != UNIT:
        return None
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return str(atom) if accept(str(atom)) else None
    if not isinstance(atom, IrRuleRef):
        return None
    target = rule_map.get(str(atom))
    arms = tuple(target.body) if target is not None else ()
    if len(arms) != 1:
        return None
    spelled = [
        text
        for inner in tuple(arms[0])
        if (text := _spelling(inner, rule_map, accept)) is not None
    ]
    return spelled[0] if len(spelled) == 1 else None


def literal_char(item: IrItem, rule_map: dict[str, IrRule]) -> str | None:
    """The single character an item spells, through one unit rule reference."""
    return _spelling(item, rule_map, _one_char)


def literal_text(item: IrItem, rule_map: dict[str, IrRule]) -> str | None:
    """The literal string an item spells, through one unit rule reference.

    A delimiter is not always one character (```` ``` ```` fences a block), so
    the interior analysis reads the whole spelling where the anchor analyses
    read only single-character ones.
    """
    return _spelling(item, rule_map, _any_text)


def item_lead(item: IrItem, rule_map: dict[str, IrRule]) -> str | None:
    """The first character of the literal an item spells, or ``None``.

    A region's opening delimiter is reached at its FIRST character and skipped
    whole, so that character is the only one of its spelling a scan can decide
    at — which is what lets ``"<["`` stop competing with a ``"["`` region.
    """
    spelling = literal_text(item, rule_map)
    return spelling[0] if spelling else None


def edge_char(
    body: IrAlternation, at: int, char_of: Callable[[IrItem], str | None]
) -> str | None:
    """The one character EVERY arm of ``body`` carries at ``at``, else ``None``.

    :param body: The alternation whose arms must agree.
    :param at: The item index within an arm — ``0`` for what an arm leads
        with, ``-1`` for what it ends with.
    :param char_of: What counts as a character there; the callers differ on
        whether that means a literal spelling or a certified anchor.
    :returns: The agreed character, or ``None`` when an arm is empty, spells
        nothing at ``at``, or the arms disagree.
    """
    found: set[str] = set()
    for arm in body:
        items = tuple(arm)
        if not items:
            return None
        char = char_of(items[at])
        if char is None:
            return None
        found.add(char)
    return found.pop() if len(found) == 1 else None


def _class_of(atom: IrNot) -> CharSet:
    """The character set a negation atom accepts."""
    inner = atom[0]
    return CharSet.from_not(inner) if isinstance(inner, IrCharClass) else CharSet.ANY


def emits(
    item: IrItem,
    char: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether one item can emit ``char`` somewhere in its derivations.

    :param hidden: Rule names the asking scan never reads. A nested delimited
        region names its own rule there; passing EVERY name asks what an arm
        spells directly, with no reference followed.
    :param path: Rules already on the derivation path, so a cycle terminates.
    """
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return char in str(atom)
    if isinstance(atom, IrCharClass):
        return CharSet.from_charclass(atom).has(char)
    if isinstance(atom, IrNot):
        return _class_of(atom).has(char)
    if isinstance(atom, IrAlternation):
        return any(
            emits(inner, char, rule_map, hidden, path) for arm in atom for inner in arm
        )
    if isinstance(atom, IrRuleRef):
        return _ref_emits(str(atom), char, rule_map, hidden, path)
    return True


def _ref_emits(
    name: str,
    char: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether a referenced rule can emit ``char``; unknown names can."""
    if name in hidden:
        return False
    target = rule_map.get(name)
    if target is None:
        return True
    return name not in path and rule_emits(
        target, char, rule_map, hidden, path | {name}
    )


def rule_emits(
    rule: IrRule,
    char: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether a rule has any flat derivation that emits ``char``."""
    return any(
        emits(item, char, rule_map, hidden, path) for arm in rule.body for item in arm
    )


def leads_with(
    items: tuple[IrItem, ...],
    char: str,
    rule_map: dict[str, IrRule],
    path: frozenset[str],
) -> bool:
    """Whether an arm can derive a string whose FIRST character is ``char``.

    Unknown atoms and cycles answer yes: a caller uses this to prove that only
    ONE arm can open with a character, and an unprovable arm must not certify.
    """
    for item in items:
        if _item_leads(item, char, rule_map, path):
            return True
        if not derives_empty(item, rule_map, frozenset()):
            return False
    return False


def _item_leads(
    item: IrItem, char: str, rule_map: dict[str, IrRule], path: frozenset[str]
) -> bool:
    """Whether one item can derive a string starting with ``char``."""
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return str(atom).startswith(char)
    if isinstance(atom, IrCharClass):
        return CharSet.from_charclass(atom).has(char)
    if isinstance(atom, IrNot):
        return _class_of(atom).has(char)
    if isinstance(atom, IrAlternation):
        return any(leads_with(tuple(arm), char, rule_map, path) for arm in atom)
    if isinstance(atom, IrRuleRef):
        return _ref_leads(str(atom), char, rule_map, path)
    return True


def _ref_leads(
    name: str, char: str, rule_map: dict[str, IrRule], path: frozenset[str]
) -> bool:
    """Whether a referenced rule can open with ``char``; unknown names can."""
    target = rule_map.get(name)
    if target is None or name in path:
        return True
    return any(
        leads_with(tuple(arm), char, rule_map, path | {name}) for arm in target.body
    )


def derives_empty(
    item: IrItem, rule_map: dict[str, IrRule], path: frozenset[str]
) -> bool:
    """Whether an item can derive the empty string."""
    if item.quantifier.lo == 0:
        return True
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return not str(atom)
    if isinstance(atom, IrAlternation):
        return any(arm_empty(tuple(arm), rule_map, path) for arm in atom)
    if not isinstance(atom, IrRuleRef):
        return False
    target = rule_map.get(str(atom))
    if target is None or str(atom) in path:
        return True
    return any(
        arm_empty(tuple(arm), rule_map, path | {str(atom)}) for arm in target.body
    )


def arm_empty(
    items: tuple[IrItem, ...], rule_map: dict[str, IrRule], path: frozenset[str]
) -> bool:
    """Whether every item of one arm can derive the empty string."""
    return all(derives_empty(item, rule_map, path) for item in items)


def interior(
    rule_map: dict[str, IrRule], name: str, path: frozenset[str] = frozenset()
) -> CharSet:
    """Every character a rule can emit at a NON-final position of its text.

    The complement of :func:`last_charset` over one rule: what it may spell
    with something still to come. A mark standing outside this set can only
    ever be a unit's closing edge, which is what turns a set of terminator
    characters into a set of BOUNDARIES.

    Overapproximating is the safe direction — a character wrongly included
    merely declines — so a cycle or an unresolvable name answers ``ANY``.
    """
    return over_arms(rule_map, name, path, _arm_interior)


def over_arms(
    rule_map: dict[str, IrRule],
    name: str,
    path: frozenset[str],
    of_arm: Callable[[dict[str, IrRule], tuple[IrItem, ...], frozenset[str]], CharSet],
) -> CharSet:
    """Union ``of_arm`` over every arm of a rule; ``ANY`` when unresolvable.

    The shared shape of every per-rule alphabet walk here: a name the map does
    not hold, or one already on the path, answers the conservative set rather
    than an empty one, because every caller is proving a DISJOINTNESS and an
    empty answer would prove it vacuously.
    """
    target = rule_map.get(name)
    if target is None or name in path:
        return CharSet.ANY
    found = CharSet.EMPTY
    for arm in target.body:
        found = found.union(of_arm(rule_map, tuple(arm), path | {name}))
    return found


def _arm_interior(
    rule_map: dict[str, IrRule], items: tuple[IrItem, ...], path: frozenset[str]
) -> CharSet:
    """Every character one arm can emit before its own last."""
    found = CharSet.EMPTY
    if not items:
        return found
    for item in items[:-1]:
        found = found.union(emit_charset(item, rule_map, frozenset()))
    return found.union(_item_interior(rule_map, items[-1], path))


def _item_interior(
    rule_map: dict[str, IrRule], item: IrItem, path: frozenset[str]
) -> CharSet:
    """What an arm's FINAL item can emit before its own last character.

    A repeated item stands beside itself, so every character it spells is an
    interior one; a reference is followed; a literal contributes all but its
    last character; a single-character atom contributes nothing.
    """
    if repeats(item):
        return emit_charset(item, rule_map, frozenset())
    atom = item.atom
    if isinstance(atom, IrRuleRef):
        return interior(rule_map, str(atom), path)
    if isinstance(atom, IrAlternation):
        found = CharSet.EMPTY
        for arm in atom:
            items = tuple(arm)
            for inner in items[:-1]:
                found = found.union(emit_charset(inner, rule_map, frozenset()))
            if items:
                found = found.union(_item_interior(rule_map, items[-1], path))
        return found
    if isinstance(atom, IrLiteral):
        text = str(atom)
        return CharSet.from_chars(*text[:-1]) if len(text) > 1 else CharSet.EMPTY
    return CharSet.EMPTY


def sole_char(found: CharSet) -> str:
    """The one character a set holds, or ``""`` for any other count.

    A set of exactly one positive character is the only shape that turns "can
    end with" into "always ends with", which is what a proof reaching leftward
    past a spelling needs.
    """
    if found.negated or len(found.chars) != 1:
        return ""
    return next(iter(found.chars))


def emit_charset(
    item: IrItem,
    rule_map: dict[str, IrRule],
    path: frozenset[str],
    hidden: frozenset[str] = frozenset(),
) -> CharSet:
    """Every character an item's derivations can emit.

    The set form of :func:`emits`, for callers asking about a whole alphabet
    rather than one character. Unknown atoms and cycles answer
    :attr:`~lexic.parsing.pda.core.charsets.CharSet.ANY`, so a caller proving
    a set is DISJOINT from another cannot be misled by one it cannot read.

    :param hidden: Rules a scan skips whole. They contribute nothing: a
        comment's alphabet is nearly every character, but a scan that jumps
        the comment never reads one of them.
    """
    atom = item.atom
    leaf = _leaf_charset(atom)
    if leaf is not None:
        return leaf
    if isinstance(atom, IrAlternation):
        return _arms_charset(atom, rule_map, path, hidden)
    if not isinstance(atom, IrRuleRef):
        return CharSet.ANY
    name = str(atom)
    if name in hidden:
        return CharSet.EMPTY
    target = rule_map.get(name)
    if target is None or name in path:
        return CharSet.ANY
    return _arms_charset(target.body, rule_map, path | {name}, hidden)


def _leaf_charset(atom: IrSelf) -> CharSet | None:
    """What an atom spells on its own, or ``None`` when it must be walked."""
    if isinstance(atom, IrLiteral):
        return CharSet.from_chars(*str(atom))
    if isinstance(atom, IrCharClass):
        return CharSet.from_charclass(atom)
    return _class_of(atom) if isinstance(atom, IrNot) else None


def _arms_charset(
    body: IrAlternation,
    rule_map: dict[str, IrRule],
    path: frozenset[str],
    hidden: frozenset[str],
) -> CharSet:
    """The union of what every item of every arm can emit."""
    found = CharSet.EMPTY
    for arm in body:
        for item in arm:
            found = found.union(emit_charset(item, rule_map, path, hidden))
    return found


def first_charset(
    items: tuple[IrItem, ...], rule_map: dict[str, IrRule], path: frozenset[str]
) -> CharSet:
    """Every character an arm can begin with — FIRST, as a set.

    Scanning stops at the first item that cannot vanish, which is what makes
    this the arm's opening alphabet rather than everything it emits.
    """
    found = CharSet.EMPTY
    for item in items:
        found = found.union(item_first(item, rule_map, path))
        if not derives_empty(item, rule_map, frozenset()):
            break
    return found


def item_first(
    item: IrItem, rule_map: dict[str, IrRule], path: frozenset[str]
) -> CharSet:
    """The characters one item can begin with."""
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return CharSet.from_chars(str(atom)[0]) if str(atom) else CharSet.EMPTY
    if isinstance(atom, IrAlternation):
        return _body_first(atom, rule_map, path)
    if not isinstance(atom, IrRuleRef):
        return emit_charset(item, rule_map, path)
    name = str(atom)
    target = rule_map.get(name)
    if target is None or name in path:
        return CharSet.ANY
    return _body_first(target.body, rule_map, path | {name})


def _body_first(
    body: IrAlternation, rule_map: dict[str, IrRule], path: frozenset[str]
) -> CharSet:
    """The union of what every arm of an alternation can begin with."""
    found = CharSet.EMPTY
    for arm in body:
        found = found.union(first_charset(tuple(arm), rule_map, path))
    return found


def last_charset(
    items: tuple[IrItem, ...], rule_map: dict[str, IrRule], path: frozenset[str]
) -> CharSet:
    """Every character an arm can END with — the exact mirror of FIRST.

    A mark spelled by two adjacent items is read at the join between what one
    can end with and what the next can begin with, so the two sets are one
    analysis walked in opposite directions.
    """
    found = CharSet.EMPTY
    for item in reversed(items):
        found = found.union(item_last(item, rule_map, path))
        if not derives_empty(item, rule_map, frozenset()):
            break
    return found


def item_last(
    item: IrItem, rule_map: dict[str, IrRule], path: frozenset[str]
) -> CharSet:
    """The characters one item can end with."""
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return CharSet.from_chars(str(atom)[-1]) if str(atom) else CharSet.EMPTY
    if isinstance(atom, IrAlternation):
        return _body_last(atom, rule_map, path)
    if not isinstance(atom, IrRuleRef):
        return emit_charset(item, rule_map, path)
    name = str(atom)
    target = rule_map.get(name)
    if target is None or name in path:
        return CharSet.ANY
    return _body_last(target.body, rule_map, path | {name})


def _body_last(
    body: IrAlternation, rule_map: dict[str, IrRule], path: frozenset[str]
) -> CharSet:
    """The union of what every arm of an alternation can end with."""
    found = CharSet.EMPTY
    for arm in body:
        found = found.union(last_charset(tuple(arm), rule_map, path))
    return found


def exact_text(item: IrItem, rule_map: dict[str, IrRule], path: frozenset[str]) -> str:
    """The one fixed string an item ALWAYS derives, or ``""``.

    Stricter than :func:`literal_text`, which reads the one anchor literal an
    item spells among noise. A caller reaching leftward for the character
    BEFORE a spelling needs the item's whole text, not its punctuation.
    """
    if item.quantifier != UNIT:
        return ""
    atom = item.atom
    if isinstance(atom, IrLiteral):
        return str(atom)
    if not isinstance(atom, IrRuleRef):
        return ""
    name = str(atom)
    target = rule_map.get(name)
    arms = tuple(target.body) if target is not None and name not in path else ()
    if len(arms) != 1:
        return ""
    parts = [exact_text(inner, rule_map, path | {name}) for inner in tuple(arms[0])]
    return "".join(parts) if parts and all(parts) else ""


MARK_ARITY = 2
"""The widest mark spelling the junction analysis decides.

A two-character mark has exactly one way to straddle a join, and that split is
a LAST-character / FIRST-character question the ``CharSet`` algebra answers
exactly. A longer mark asks whether derivable text ends with a STRING, which is
not a character-set question; rather than approximate it, a longer mark answers
"can spell" and every proof over it declines.
"""


def rule_spells(
    rule: IrRule,
    mark: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether any derivation of ``rule`` contains ``mark`` as a substring.

    Conservative in one direction only: ``False`` is a proof, ``True`` may be a
    decline. A one-character mark delegates to
    :func:`~...discovery.shapes.rule_emits` verbatim, so every grammar whose
    marks are characters reads exactly as it did.

    :param rule: The symbol whose derivations are in question.
    :param mark: The mark spelling.
    :param rule_map: The grammar's rules by name.
    :param hidden: Rule names the asking scan never reads.
    :param path: Rules already on the derivation path, so a cycle terminates.
    """
    if len(mark) == 1:
        return rule_emits(rule, mark, rule_map, hidden, path)
    if len(mark) > MARK_ARITY:
        return True
    return any(
        arm_spells(tuple(arm), mark, rule_map, hidden, path) for arm in rule.body
    )


def arm_spells(
    items: tuple[IrItem, ...],
    mark: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether one arm's derivations contain ``mark`` — joins included.

    The join clause walks THROUGH vanishing items in both directions: ``LAST``
    reaches left past items that may be empty and ``FIRST`` reaches right past
    them, so two items with only nullables between them are tested as the
    neighbours they can become.
    """
    if len(mark) == 1:
        return any(emits(item, mark, rule_map, hidden, path) for item in items)
    if len(mark) > MARK_ARITY:
        return bool(items)
    if any(item_spells(item, mark, rule_map, hidden, path) for item in items):
        return True
    return any(
        joins(items[: at + 1], items[at + 1 :], mark, rule_map, path)
        for at in range(len(items) - 1)
    )


def joins(
    before: tuple[IrItem, ...],
    after: tuple[IrItem, ...],
    mark: str,
    rule_map: dict[str, IrRule],
    path: frozenset[str],
) -> bool:
    """Whether text ending ``before`` can meet text beginning ``after`` as ``mark``."""
    return last_charset(before, rule_map, path).has(mark[0]) and first_charset(
        after, rule_map, path
    ).has(mark[1])


def item_spells(
    item: IrItem,
    mark: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether one item's derivations contain ``mark`` — repetition included.

    A repeated item stands beside itself, so ``[\\n]+`` spells a two-newline
    mark that its atom cannot. The repetition clause reads the atom's own edges
    rather than the item's, since the quantifier is what makes them adjacent.
    """
    if len(mark) == 1:
        return emits(item, mark, rule_map, hidden, path)
    if len(mark) > MARK_ARITY:
        return True
    if repeats(item) and _self_joins(item, mark, rule_map, path):
        return True
    return _atom_spells(item.atom, mark, rule_map, hidden, path)


def _self_joins(
    item: IrItem, mark: str, rule_map: dict[str, IrRule], path: frozenset[str]
) -> bool:
    """Whether two occurrences of a repeated item spell ``mark`` between them."""
    return item_last(item, rule_map, path).has(mark[0]) and item_first(
        item, rule_map, path
    ).has(mark[1])


def _atom_spells(
    atom: IrSelf,
    mark: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether one atom occurrence's own text can contain ``mark``."""
    if isinstance(atom, IrLiteral):
        return mark in str(atom)
    if isinstance(atom, (IrCharClass, IrNot)):
        return False  # one occurrence spells one character
    if isinstance(atom, IrAlternation):
        return any(arm_spells(tuple(arm), mark, rule_map, hidden, path) for arm in atom)
    if not isinstance(atom, IrRuleRef):
        return True
    return _ref_spells(str(atom), mark, rule_map, hidden, path)


def _ref_spells(
    name: str,
    mark: str,
    rule_map: dict[str, IrRule],
    hidden: frozenset[str],
    path: frozenset[str],
) -> bool:
    """Whether a referenced rule can spell ``mark``; unknown names can."""
    if name in hidden:
        return False
    target = rule_map.get(name)
    if target is None:
        return True
    return name not in path and rule_spells(
        target, mark, rule_map, hidden, path | {name}
    )
