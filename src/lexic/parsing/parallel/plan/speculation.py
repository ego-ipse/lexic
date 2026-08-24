"""When a cut may be PROPOSED — the precondition speculation runs under.

Every other split plan reads its boundaries out of the text: some spelling
occurs only where a unit ends, so finding it finds the cut. A unit that ends
where the NEXT one begins offers no such spelling — a section closes at a
newline and is full of newlines — and its boundaries can only be proposed and
then verified by parsing.

Verification alone proves nothing. Two pieces that parse show the document HAS
a reading as ``unit+``; they do not show it has only one, and accepting a
second reading is exactly what the sequential engine refuses. So the missing
half is a grammar property, decided once and memoised:

- **determinism** — no rule reachable from the container is conflicted, so
  every decision inside a unit is settled by bounded lookahead rather than by
  Earley or by attempt-with-rollback;
- **non-vanishing** — a unit that may spell nothing makes ``unit+`` infinitely
  segmentable;
- **exclusive opening** — nothing a unit may continue with can also begin one,
  which is what forces the segmentation;
- **visible opening** — a unit begins on an anchor, so its candidate positions
  are findable by a window scan with no left context.

The third is the one that carries the weight, and the one a determinism check
cannot supply. ``root ::= unit+`` over ``unit ::= [a-z]+`` has no island, no
conflicted rule and no nullable unit, and ``"abc"`` divides three ways — the
engine answers with the maximal munch and never refuses, so a wrong cut there
would be silently wrong. Its extent is settled at the lexical layer, where no
parser decision point exists for a gate to record.
"""

from __future__ import annotations

from lexic.ir import IrAlternation, IrAst, IrRule, IrRuleRef
from lexic.parsing.caches import memo
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.parallel.discovery.anchors import anchors
from lexic.parsing.parallel.discovery.shapes import (
    arm_empty,
    first_charset,
    item_first,
    over_arms,
    repeats,
)
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.core.charsets import CharSet


def continues(
    rule_map: dict[str, IrRule], name: str, path: frozenset[str] = frozenset()
) -> CharSet:
    """Every character that may follow a COULD-END point of ``name``.

    A could-end point is a position with nothing after it that cannot vanish —
    a position at which the unit may already be complete while the document
    goes on. What may stand there is what the unit continues with, and a
    character in both this set and ``FIRST`` leaves "same unit or next one"
    undecidable.

    Three contributions, and the first two are easy to miss. The arm's own
    remainder continues it. A REPEATED item continues with another copy of
    itself, which is the whole of ``unit ::= [a-z]+`` and would read as an
    empty set without this term. And a sub-rule's own vanishable tail puts
    could-end points below the arm's top level, so references are followed.

    Overapproximating is the only safe direction: a missed continuation reads
    as false disjointness, which reads as false uniqueness. An unresolvable
    name or a cycle therefore answers ``ANY``, and the supporting walks agree —
    ``first_charset`` answers ``ANY`` on a cycle and ``derives_empty`` answers
    ``True``, which makes more positions could-end points, not fewer.
    """
    return over_arms(rule_map, name, path, _arm_continues)


def _arm_continues(rule_map, items, path) -> CharSet:
    """The continuations of one arm's could-end points."""
    found = CharSet.EMPTY
    for at, item in enumerate(items):
        if not arm_empty(items[at + 1 :], rule_map, frozenset()):
            continue
        found = found.union(first_charset(items[at + 1 :], rule_map, path))
        found = found.union(_item_continues(rule_map, item, path))
    return found


def _item_continues(rule_map, item, path) -> CharSet:
    """What one item continues with from a could-end point INSIDE it."""
    found = item_first(item, rule_map, path) if repeats(item) else CharSet.EMPTY
    atom = item.atom
    if isinstance(atom, IrRuleRef):
        return found.union(continues(rule_map, str(atom), path))
    if not isinstance(atom, IrAlternation):
        return found
    for arm in atom:
        found = found.union(_arm_continues(rule_map, tuple(arm), path))
    return found


def opens_with(rule_map: dict[str, IrRule], unit: str) -> CharSet:
    """Every character a unit may begin with — FIRST over all its arms."""
    target = rule_map.get(unit)
    if target is None:
        return CharSet.ANY
    found = CharSet.EMPTY
    for arm in target.body:
        found = found.union(first_charset(tuple(arm), rule_map, frozenset({unit})))
    return found


def _conflicted(grammar: IrAst) -> frozenset[str]:
    """Every rule the PDA analysis could not settle by bounded lookahead.

    Islands and attemptable rules alike: an island hands the decision to
    Earley, where two readings survive, and an attempt settles a second success
    at RUNTIME rather than proving there cannot be one. Neither is a static
    guarantee, so both refuse.
    """
    return frozenset(
        GrammarAnalysis(lift_optional_nullables(grammar)).taxonomy.conflicts
    )


_PRECONDITIONS: dict[tuple[int, str], tuple[IrAst, frozenset[str]]] = memo({}, 0)
"""Per-grammar speculative openings, with a strong identity pin."""


def speculative_openings(grammar: IrAst, unit: str) -> frozenset[str]:
    """The characters a speculative cut may be proposed at, or empty to decline.

    Empty is the ordinary answer and the only honest one for a unit whose
    segmentation is not forced. A non-empty set is a licence: every true
    boundary stands at one of these characters, so no boundary is missed, and
    a proposal that is NOT one fails its piece parse and is retried.

    :param grammar: The codegen grammar the pieces parse under.
    :param unit: The repeated unit a cut lands before.
    :returns: The opening alphabet, or empty when any clause refuses.
    """
    key = (id(grammar), unit)
    entry = _PRECONDITIONS.get(key)
    if entry is None:
        entry = (grammar, _derive_openings(grammar, unit))
        _PRECONDITIONS[key] = entry
    return entry[1]


def _derive_openings(grammar: IrAst, unit: str) -> frozenset[str]:
    """Run the four clauses once for one grammar's repeated unit."""
    rule_map = {str(rule.name): rule for rule in grammar.rules}
    target = rule_map.get(unit)
    if target is None or _conflicted(grammar):
        return frozenset()
    if any(arm_empty(tuple(arm), rule_map, frozenset()) for arm in target.body):
        return frozenset()
    opening = opens_with(rule_map, unit)
    if opening.negated or not opening.chars:
        return frozenset()
    if opening.overlaps(continues(rule_map, unit)):
        return frozenset()
    return (
        frozenset(opening.chars) if opening.chars <= anchors(grammar) else frozenset()
    )
