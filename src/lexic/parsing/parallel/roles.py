"""Role derivation — what a grammar's anchor characters DO at a split point.

The window scan needs three character roles: openers and closers (the
depth count), and separators (the split candidates). The demonstrable
shapes are derived from the grammar, never hardcoded per formulation:

- **Pair** — an arm opening with a unit single-char anchor literal whose
  LAST anchor literal closes over a reference or group interior:
  ``"{" ws members "}" ws`` derives the pair ``{`` → ``}`` (trailing noise
  after the closer is fine; a closer is the last structural mark, not the
  last item). Depth is counted over the WHOLE text, so the pair stands only
  when every site spelling either character is a delimiter of such an arm: a
  ``>`` that is also the tail of ``"=>"`` would close every bracket early.
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

from collections.abc import Callable
from functools import partial
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
from lexic.parsing.caches import memo
from lexic.parsing.parallel.discovery.anchors import anchor_site_counts, anchors
from lexic.parsing.parallel.discovery.shapes import (
    MARK_ARITY,
    RuleTable,
    exact_text,
    last_charset,
    rule_table,
)
from lexic.parsing.pda.core.charsets import CharSet


class Separator(NamedTuple):
    """One repetition separator, with the rules a split orchestration needs.

    Derived from a repetition the grammar STATES. A left recursion carries one
    the grammar does not — the fold turns ``A ::= A β | γ`` into ``γ (β)*`` —
    and :mod:`~lexic.parsing.parallel.plan.folded` reads that chain as its own
    candidate source instead. Which plan a proof licenses is
    :mod:`~lexic.parsing.parallel.stitch.safety`'s question either way, which
    is why neither derivation carries the gate.

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

    :ivar mark: The terminating spellings — the set of ways a unit may end.
        One agreed spelling for a unit whose arms all close alike; the unit's
        whole ending alphabet where they close differently and no occurrence of
        it can stand anywhere but at an end.
    :ivar container: The rule owning the repeated item.
    :ivar unit: The repeated rule.
    """

    mark: frozenset[str]
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
        ended = (
            frozenset().union(*(r.mark for r in self.terminators))
            if self.terminators
            else frozenset()
        )
        return self.separators | ended


def _anchor_char(item: IrItem, anchor_set: frozenset[str]) -> str | None:
    """The item's character when it is a unit-quantified single-char anchor."""
    chars = _anchor_chars(item, anchor_set)
    return next(iter(chars)) if len(chars) == 1 else None


def _anchor_chars(item: IrItem, anchor_set: frozenset[str]) -> frozenset[str]:
    """All finite anchor alternatives one unit-quantified item can emit."""
    atom = item.atom
    if not item.quantifier.once():
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
    literal = item.unit_literal()
    if not isinstance(literal, IrLiteral):
        return frozenset()
    text = str(literal)
    wide = len(text) > 1 and set(text) <= anchor_set
    return frozenset({text}) if wide else frozenset()


class BracketArm(NamedTuple):
    """One arm opening on one character and closing on another.

    :ivar opener: The character item 0 spells.
    :ivar closer: The character the LAST later item with one spells.
    :ivar rule: The rule the arm belongs to.
    :ivar arm: The arm's index in that rule's body.
    :ivar closes: The closer's item index.
    """

    opener: str
    closer: str
    rule: str
    arm: int
    closes: int


def bracket_arms(
    grammar: IrAst, char_of: Callable[[IrItem], str | None], enclosing: bool
) -> list[BracketArm]:
    """Every arm of three items or more that opens and closes on two different
    characters, read through ``char_of``, in definition order.

    The one walk both pair derivations read; each brings its own reader.
    :func:`roles` reads anchors and asks ``enclosing``: DELIMITING, not nesting,
    is its test, and a pair also serves
    :func:`~...stitch.safety.owner_excludes`, which attributes what stands
    between the delimiters to the nested region, so the arm must hold a
    reference or group there. A flat ``"{" inner "}"`` owns its own commas just
    as a nesting one does, so nothing narrower is asked. The region scan reads
    literals and keeps the provenance its stray reading needs.
    """
    out: list[BracketArm] = []
    for rule in grammar.rules:
        for at, arm in enumerate(rule.body):
            items = tuple(arm)
            if len(items) < 3:
                continue
            spelled = [char_of(item) for item in items]
            closes = max((k for k, char in enumerate(spelled) if char and k), default=0)
            opener, closer = spelled[0], spelled[closes]
            if not closes or not opener or closer == opener:
                continue
            if enclosing and not any(
                isinstance(item.atom, (IrRuleRef, IrAlternation))
                for item in items[1:closes]
            ):
                continue
            out.append(BracketArm(opener, str(closer), str(rule.name), at, closes))
    return out


class RepeatedBody(NamedTuple):
    """A body some arm repeats.

    :ivar container: The rule owning the arm.
    :ivar item: The repeated rule; ``""`` for an inline group.
    :ivar body: What repeats.
    """

    container: str
    item: str
    body: IrAlternation


def repeated_bodies(grammar: IrAst, nested: bool) -> list[RepeatedBody]:
    """Every unbounded body an arm repeats, in definition order; with
    ``nested``, the ones inside its groups too.

    The one walk both separator derivations read. A repetition is often written
    inside another group (RFC json spells its member list
    ``[ member *( value-separator member ) ]``), which the region scan reaches.
    :func:`roles` records a separator against the arm's own repetition, so it
    reads the top level only.
    """
    rule_map = rule_table(grammar)
    out: list[RepeatedBody] = []
    for rule in grammar.rules:
        for arm in rule.body:
            _collect(str(rule.name), tuple(arm), rule_map, nested, out)
    return out


def _collect(
    container: str,
    items: tuple[IrItem, ...],
    rule_map: RuleTable,
    nested: bool,
    out: list[RepeatedBody],
) -> None:
    """:func:`repeated_bodies` over one run of items."""
    for item in items:
        atom = item.atom
        target = rule_map.get(str(atom)) if isinstance(atom, IrRuleRef) else None
        if item.quantifier.unbounded() and target is not None:
            out.append(RepeatedBody(container, str(atom), target.body))
        elif item.quantifier.unbounded() and isinstance(atom, IrAlternation):
            out.append(RepeatedBody(container, "", atom))
        if nested and isinstance(atom, IrAlternation):
            for arm in atom:
                _collect(container, tuple(arm), rule_map, nested, out)


def _lead_info(
    item: IrItem,
    by_name: RuleTable,
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
        and item.quantifier.once()
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
    by_name: RuleTable,
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


_ROLES: dict[int, tuple[IrAst, Roles]] = memo({})
"""Derived roles — id(grammar) → (grammar, roles). The strong reference pins
the id, so a recycled id can never alias a live entry."""


def roles(grammar: IrAst) -> Roles:
    """Derive the grammar's opener/closer pairs and repetition separators.

    Memoised per grammar identity: the derivation walks every arm of every
    rule, and the split asks for it once per document rather than once per
    grammar — on a meta grammar that re-walk was several percent of the whole
    split parse.

    :param grammar: The grammar to analyse (the codegen grammar for a
        compiled artefact — repetition groups are hoisted there, so the
        ``(sep unit)*`` shape appears as an unbounded rule reference).
    :returns: The derived :class:`Roles`; empty roles when nothing matches.
    """
    entry = _ROLES.get(id(grammar))
    if entry is None:
        entry = (grammar, _derive_roles(grammar))
        _ROLES[id(grammar)] = entry
    return entry[1]


def _derive_roles(grammar: IrAst) -> Roles:
    """Classify every arm's anchors: separators and terminators in one walk,
    pairs in :func:`_pairs`'s own."""
    anchor_set = anchors(grammar)
    by_name = rule_table(grammar)
    records: list[Separator] = []
    for repeated in repeated_bodies(grammar, nested=False):
        _repeated_separators(repeated, by_name, anchor_set, records)
    pairs = _pairs(grammar, anchor_set)
    paired = {char for pair in pairs for char in pair}
    kept = tuple(record for record in records if not set(record.mark) & paired)
    ended = tuple(
        narrowed
        for record in _terminators(grammar, by_name, anchor_set)
        if (narrowed := _unpaired(record, paired)) is not None
    )
    return Roles(pairs, kept, ended)


def _pairs(grammar: IrAst, anchor_set: frozenset[str]) -> tuple[tuple[str, str], ...]:
    """Every bracketing arm's pair whose characters no other site spells.

    Each such arm contributes one opener and one closer site; a pair stands when
    the arms of STANDING pairs account for every site of both characters
    (:func:`~lexic.parsing.parallel.discovery.anchors.anchor_site_counts`).
    """
    read = partial(_anchor_char, anchor_set=anchor_set)
    arms = [arm[:2] for arm in bracket_arms(grammar, read, enclosing=True)]
    sites = anchor_site_counts(grammar)
    strays = partial(_miscounted, arms, sites)
    return tuple(standing_pairs(list(dict.fromkeys(arms)), strays))


def _miscounted(
    arms: list[tuple[str, str]],
    sites: dict[str, int],
    standing: list[tuple[str, str]],
) -> frozenset[str]:
    """The standing pairs' characters spelled at more sites than their arms."""
    delimiting: dict[str, int] = {}
    for char in (char for pair in arms if pair in standing for char in pair):
        delimiting[char] = delimiting.get(char, 0) + 1
    chars = {char for pair in standing for char in pair}
    return frozenset(char for char in chars if delimiting[char] != sites.get(char, 0))


def standing_pairs(
    pairs: list[tuple[str, str]],
    strays: Callable[[list[tuple[str, str]]], frozenset[str]],
) -> list[tuple[str, str]]:
    """The pairs a scan counting depth on every opener and closer reads exactly.

    A scan counts depth on every occurrence it reads, so a pair stands only
    while each site spelling either of its characters is a delimiter of a
    standing pair's arm; ``strays`` names the characters that fail, given the
    pairs standing. A character that opens one standing pair and closes
    another fails as well: the count moves it by zero where the depth moves
    by one, and the walk can only read it as one of the two. A fallen pair's
    delimiters are stray sites like any other, so the check repeats until no
    pair falls.

    :param pairs: Candidate ``(opener, closer)`` pairs, in definition order.
    :param strays: The characters some read site spells off a standing arm's
        own delimiters, for the pairs standing.
    :returns: The pairs that stand, in their given order.
    """
    while True:
        crossed = {opener for opener, _ in pairs} & {closer for _, closer in pairs}
        stray = strays(pairs) | crossed
        kept = [pair for pair in pairs if not stray & set(pair)]
        if len(kept) == len(pairs):
            return kept
        pairs = kept


def _unpaired(record: Terminator, paired: set[str]) -> Terminator | None:
    """``record`` with every pair-playing spelling removed, or ``None``.

    A character the scan counts depth with cannot also be a mark, and a set of
    endings NARROWS rather than dies when one of them is spent that way: the
    survivors are still endings, and each is still a boundary wherever it
    stands. Losing every one of them is what leaves no terminator at all.
    """
    kept = frozenset(mark for mark in record.mark if not set(mark) & paired)
    return record._replace(mark=kept) if kept else None


def _terminators(
    grammar: IrAst, by_name: RuleTable, anchor_set: frozenset[str]
) -> list[Terminator]:
    """Every unbounded reference whose target ends with an agreed anchor mark."""
    out: list[Terminator] = []
    for rule in grammar.rules:
        for arm in rule.body:
            for item in arm:
                target = item.atom
                if not item.quantifier.unbounded() or not isinstance(target, IrRuleRef):
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
    unit: IrRule, by_name: RuleTable, anchor_set: frozenset[str]
) -> tuple[frozenset[str], ...]:
    """The terminator mark sets ``unit`` offers, narrowest first.

    Three derivations, and a unit may offer any of them. The single agreed
    CHARACTER is what a repetition has always been cut on. The agreed
    SPELLING is wider — a text line's own terminator plus the blank line that
    closes the paragraph. The unit's whole ending ALPHABET is the last resort
    and the only one available to a unit whose arms close differently: a
    record stream ending ``;``, ``>`` and a newline agrees on nothing, yet
    every one of those characters may still be a boundary.

    The cascade tries them in this order, so a grammar that already splits
    keeps exactly the plan it had. Which of them a safety proof licenses is
    :mod:`~lexic.parsing.parallel.stitch.safety`'s question, not this one's.
    """
    seen = frozenset({str(unit.name)})
    char = _body_edge(unit.body, -1, by_name, anchor_set, seen)
    wide = agreed_tail(unit.body, MARK_ARITY, by_name, seen)
    found = [
        frozenset({mark}) for mark in (char, wide) if mark and set(mark) <= anchor_set
    ]
    ending = _ending_alphabet(unit, by_name, anchor_set)
    if ending:
        found.append(ending)
    return tuple(dict.fromkeys(found))


def _ending_alphabet(
    unit: IrRule, by_name: RuleTable, anchor_set: frozenset[str]
) -> frozenset[str]:
    """Every character ``unit`` can END with, when they are all anchors.

    An anchor is a character no opaque interior can spell and no maximal-munch
    run contains, which is what lets a window scan find every occurrence with
    no left context. A unit that can end on anything else has an unreadable
    boundary whatever else is true of it, so the set is offered only whole.
    """
    found = CharSet.EMPTY
    for arm in unit.body:
        found = found.union(
            last_charset(tuple(arm), by_name, frozenset({str(unit.name)}))
        )
    if found.negated or not found.chars or not found.chars <= anchor_set:
        return frozenset()
    return frozenset(found.chars)


def _item_edge(
    item: IrItem,
    at: int,
    by_name: RuleTable,
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
    if not item.quantifier.once():
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
    by_name: RuleTable,
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
    repeated: RepeatedBody,
    by_name: RuleTable,
    anchor_set: frozenset[str],
    records: list[Separator],
) -> None:
    """Collect the separator records one repeated body contributes."""
    found = _body_leads(repeated.body, by_name, anchor_set)
    if found is None:
        return
    chars, lead = found
    for mark in sorted(chars, key=lambda spelling: (len(spelling), spelling)):
        record = Separator(mark, repeated.container, repeated.item, lead)
        if record not in records:
            records.append(record)


def agreed_tail(
    body: IrAlternation, want: int, rule_map: RuleTable, path: frozenset[str]
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
    rule_map: RuleTable,
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
    rule_map: RuleTable,
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
    if target is not None and last.quantifier.once():
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
