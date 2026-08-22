"""Envelope containers and noise-run leads — the shapes a plain repetition is not.

Two facts keep a real grammar's start rule out of the ``unit item*`` shape
:mod:`~lexic.parsing.parallel.orchestrate` plans over.

**The core sits in an envelope.** A document is rarely only its repetition:
``rulelist ::= filler* rule rl-cont* c-wsp* c-nl?`` wraps the repeated core in
optional head and tail items. Splitting one means the FIRST piece owns the head
fields, the LAST owns the tail fields, and every middle piece must leave both
empty — the same off-route-empty question the wrapper route already asks,
asked at the two ends of one arm.

**The separator is a run, not a character.** ``rl-cont ::= c-wsp* c-nl filler*
rule`` leads with whitespace, a line ending and any number of comments. A cut
lands on the mark and then extends forward over that run: noise characters
directly, and whole opaque regions — a comment carries whatever it likes and
ends at its own closer — by jumping them.

Where the unit itself can emit the mark, extending is not enough to be exact;
:func:`~lexic.parsing.parallel.stitch.safety.unit_boundary` is what proves the
landing site, and :func:`admits` is the local test it licenses.
"""

from __future__ import annotations

from random import Random
from typing import NamedTuple

from lexic.exceptions import LexicError
from lexic.generate import generate
from lexic.ir import IrAst, IrItem, IrRule, IrRuleRef
from lexic.parsing.caches import memo
from lexic.parsing.parallel.discovery.interiors import Interior, as_skip, skip_delimited
from lexic.parsing.parallel.discovery.shapes import (
    UNIT,
    derives_empty,
    emit_charset,
    unbounded,
)
from lexic.parsing.parallel.stitch.safety import (
    Boundary,
    noise_skips,
    unit_boundary,
)
from lexic.parsing.pda.core.charsets import CharSet


class Envelope(NamedTuple):
    """A container arm read as ``head… unit item* tail…``.

    :ivar container: The rule owning the arm.
    :ivar unit: The repeated unit's rule name.
    :ivar item: The repeated item's rule name.
    :ivar core: Item index of the unit within the arm.
    :ivar head: Item indices before the core, all able to vanish.
    :ivar tail: Item indices after the repetition, all able to vanish.
    """

    container: str
    unit: str
    item: str
    core: int
    head: tuple[int, ...]
    tail: tuple[int, ...]

    @property
    def plain(self) -> bool:
        """Whether this is the bare ``unit item*`` shape, with no envelope."""
        return not self.head and not self.tail


def _unit_ref(item: IrItem) -> str | None:
    """The unit rule an item references, when it is a plain unit reference."""
    atom = item.atom
    if isinstance(atom, IrRuleRef) and item.quantifier == UNIT:
        return str(atom)
    return None


def envelope_of(
    container: IrRule, rules: dict[str, IrRule], item: str
) -> Envelope | None:
    """Read a container's single arm as an envelope around ``item*``.

    Every item outside the core pair must be able to vanish: a head or tail
    that some piece is forced to carry cannot be owned by one end of the split.

    :param container: The rule holding the repetition.
    :param rules: The grammar's rules by name.
    :param item: The repeated item rule the core must repeat.
    :returns: The envelope, or ``None`` when the arm has another shape.
    """
    arms = tuple(container.body)
    if len(arms) != 1:
        return None
    items = tuple(arms[0])
    core = _core_at(items, item)
    if core is None:
        return None
    outside = [at for at in range(len(items)) if at not in (core, core + 1)]
    if any(not derives_empty(items[at], rules, frozenset()) for at in outside):
        return None
    return Envelope(
        str(container.name),
        str(_unit_ref(items[core])),
        item,
        core,
        tuple(at for at in outside if at < core),
        tuple(at for at in outside if at > core),
    )


def _core_at(items: tuple[IrItem, ...], item: str) -> int | None:
    """Where ``unit item*`` stands in the arm, or ``None`` if it does not."""
    for at in range(len(items) - 1):
        repeated = items[at + 1].atom
        names = isinstance(repeated, IrRuleRef) and str(repeated) == item
        if _unit_ref(items[at]) is not None and names and unbounded(items[at + 1]):
            return at
    return None


class LeadRun(NamedTuple):
    """What a cut extends over after its mark, and what reparses it.

    :ivar noise: Characters the run may carry directly.
    :ivar skips: Opaque regions the run jumps whole, longest opening first.
    :ivar target: The grammar the separator span reparses under, rooted at the
        repeated ITEM. The span itself carries only the lead, so a reparse
        appends a grammar-generated witness unit and keeps the lead's fields —
        a rule synthesized for the lead alone would carry no fold binding and
        so no field map to rebuild the item from.
    """

    noise: frozenset[str]
    skips: tuple[Interior, ...]
    target: IrAst


def extend(text: str, at: int, run: LeadRun) -> int:
    """Where the noise run starting at ``at`` ends.

    Characters are consumed directly and regions are jumped whole, so a
    comment costs one search rather than one test per character it holds.

    :param text: The document.
    :param at: First offset after the mark.
    :param run: The derived run vocabulary.
    :returns: The offset the next unit starts at.
    """
    size = len(text)
    while at < size:
        char = text[at]
        if char in run.noise:
            at += 1
            continue
        jumped = _jump(text, at, run.skips)
        if jumped == at:
            return at
        at = jumped
    return at


def _jump(text: str, at: int, skips: tuple[Interior, ...]) -> int:
    """Past an opaque region opening here, or ``at`` when none does."""
    for region in skips:
        if text.startswith(region.opening, at):
            return skip_delimited(text, at, as_skip(region))
    return at


def admits(text: str, at: int, found: Boundary, mark: str) -> bool:
    """Whether a unit announces itself at ``at`` — the admission match.

    ``head+ noise* literal``, with no mark crossed. Reaching the literal over
    head and noise characters alone is what
    :func:`~lexic.parsing.parallel.stitch.safety.unit_boundary` has proven no
    position inside a unit can do, so a match here IS a unit boundary.

    :param text: The document.
    :param at: Where the noise run left off.
    :param found: The proven prefix.
    :param mark: The character cuts key on, which the match may never cross.
    :returns: Whether a cut before ``at`` is admitted.
    """
    size = len(text)
    start = at
    while at < size and found.head.has(text[at]) and text[at] != mark:
        at += 1
    if at == start:
        return False
    while at < size and found.noise.has(text[at]) and text[at] != mark:
        at += 1
    return text.startswith(found.literal, at)


def cut_offsets(text: str, mark: str, run: LeadRun, found: Boundary) -> list[int]:
    """Every certified cut offset in ``text``, in document order.

    One C-level ``str.find`` per mark occurrence — the Python loop runs over
    marks, never over characters — then the local admission match at each.

    Consecutive marks separated only by noise reach the SAME unit start, and
    the earliest of them is the cut: it leaves every inter-unit blank line and
    comment in the separator span, where the lead reparses them. A later one
    would strand that noise at the end of a piece, which is not a document —
    the trailing ``c-wsp* c-nl?`` of an envelope absorbs one line ending, not
    a run of them.

    :param text: The document.
    :param mark: The character cuts key on.
    :param run: The lead's noise-run vocabulary.
    :param found: The proven unit prefix.
    :returns: The canonical cut offsets.
    """
    cuts: list[int] = []
    claimed = -1
    at = text.find(mark)
    while at != -1:
        start = extend(text, at + 1, run)
        if start > claimed and admits(text, start, found, mark):
            cuts.append(at)
            claimed = start
        at = text.find(mark, at + 1)
    return cuts


class EnvelopePlan(NamedTuple):
    """One repetition a split can cut, with everything the cut needs.

    :ivar shape: The container arm read as an envelope.
    :ivar run: The lead's noise-run vocabulary.
    :ivar bound: The proven unit prefix a cut must land on.
    :ivar mark: The character cuts key on.
    """

    shape: Envelope
    run: LeadRun
    bound: Boundary
    mark: str

    def cuts(self, text: str) -> list[int]:
        """The certified cut offsets in ``text``."""
        return cut_offsets(text, self.mark, self.run, self.bound)

    def resumes(self, text: str, at: int) -> int:
        """Where the piece after a cut at ``at`` begins."""
        return extend(text, at + 1, self.run)


def _lead_items(rules: dict[str, IrRule], item: str) -> tuple[IrItem, ...]:
    """The repeated item's items before its unit — its separator lead."""
    arms = tuple(rules[item].body)
    return tuple(arms[0])[:-1] if len(arms) == 1 else ()


def repetition_of(rules: dict[str, IrRule], container: str) -> Envelope | None:
    """The ``unit item*`` core a container's arm holds, envelope included.

    The repeated item must itself end with the same unit — ``rl-cont ::= c-wsp*
    c-nl filler* rule`` repeats ``rule`` behind a lead — which is what makes
    the separator the lead and the cut a boundary between two units.
    """
    rule = rules.get(container)
    arms = tuple(rule.body) if rule is not None else ()
    items = tuple(arms[0]) if len(arms) == 1 else ()
    for at in range(len(items) - 1):
        repeated = items[at + 1].atom
        if not unbounded(items[at + 1]) or not isinstance(repeated, IrRuleRef):
            continue
        unit = _unit_ref(items[at])
        lead = _lead_items(rules, str(repeated))
        tail_arm = tuple(tuple(rules[str(repeated)].body)[0])
        repeats = bool(lead) and _unit_ref(tail_arm[-1]) == unit
        if unit is not None and repeats and rule is not None:
            return envelope_of(rule, rules, str(repeated))
    return None


def _run_of(
    grammar: IrAst, rules: dict[str, IrRule], shape: Envelope
) -> tuple[LeadRun, CharSet]:
    """The lead's noise vocabulary, and what its mandatory item must spell.

    Regions the run jumps contribute nothing to the noise: a comment's alphabet
    is nearly every character, and letting it widen the noise would leave no
    character able to announce a unit.
    """
    skips = noise_skips(grammar)
    hidden = frozenset(region.rule for region in skips)
    noise = CharSet.EMPTY
    required = CharSet.EMPTY
    for item in _lead_items(rules, shape.item):
        spelled = emit_charset(item, rules, frozenset(), hidden)
        noise = noise.union(spelled)
        if not derives_empty(item, rules, frozenset()):
            required = required.union(spelled)
    chars = frozenset() if noise.negated else frozenset(noise.chars)
    return LeadRun(chars, skips, IrAst(grammar.rules, shape.item)), required


def envelope_plan(grammar: IrAst, container: str) -> EnvelopePlan | None:
    """The certified plan a container's repetition admits, or ``None``.

    The mark is derived, never named: it is a character the lead's MANDATORY
    item must spell, read with the run's own regions hidden — which for a
    comment-bearing lead leaves the line endings and nothing else. Each
    candidate is offered to the boundary proof, and the first that proves wins.

    :param grammar: The codegen grammar.
    :param container: The rule whose arm holds the repetition.
    :returns: The plan, or ``None`` — an ordinary decline.
    """
    rules = {str(rule.name): rule for rule in grammar.rules}
    shape = repetition_of(rules, container)
    if shape is None:
        return None
    run, required = _run_of(grammar, rules, shape)
    if required.negated:
        return None
    for mark in sorted(required.chars):
        bound = unit_boundary(grammar, shape.unit, mark)
        if bound is not None and mark in run.noise:
            return EnvelopePlan(shape, run, bound, mark)
    return None


_WITNESS: dict[tuple[int, str], tuple[IrAst, str | None]] = memo({}, 0)
"""Minimal unit text per grammar identity, so generation runs once."""


def unit_witness(grammar: IrAst, unit: str) -> str | None:
    """The smallest string the repeated unit derives, or ``None``.

    A separator span carries only the lead, and the repeated ITEM rule — the
    one with a fold binding — requires its unit. Parsing the span with this
    appended yields a real item model whose lead fields are the ones to keep;
    the stitch then swaps the witness out for the piece that follows.
    """
    key = (id(grammar), unit)
    entry = _WITNESS.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in grammar.rules}
        entry = (grammar, _smallest(rules, unit))
        _WITNESS[key] = entry
    return entry[1]


_SEEDS = 8
"""Attempts per depth. A witness only has to parse, so the search stops at the
first depth that yields any and takes the shortest of that handful — sweeping
every seed at every depth cost 109 ms on a hundred-rule grammar to pick a
string a few characters shorter."""


def _smallest(rules: dict[str, IrRule], unit: str) -> str | None:
    """The shortest derivation of ``unit`` the first workable depth offers."""
    for depth in range(3):
        found = []
        for seed in range(_SEEDS):
            try:
                found.append(generate(unit, rules, rng=Random(seed), max_depth=depth))
            except LexicError:
                continue
        if found:
            return min(found, key=len)
    return None
