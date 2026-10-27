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
- **exclusive opening** — nothing that may lengthen a complete unit (its
  EXTEND, the PDA analysis' least fixpoint) can also begin one, which is what
  forces the segmentation;
- **visible opening** — a unit begins on an anchor, so its candidate positions
  are findable by a window scan with no left context.

The third is the one that carries the weight, and the one a determinism check
cannot supply. ``root ::= unit+`` over ``unit ::= [a-z]+`` has no island, no
conflicted rule and no nullable unit, and ``"abc"`` divides three ways — the
engine answers with the maximal munch and never refuses, so a wrong cut there
would be silently wrong. Its extent is settled at the lexical layer, where no
parser decision point exists for a gate to record.

The clauses run cheapest first: vanishing and visibility walk the unit's own
arms, determinism builds the grammar's analysis only for a unit that passes
them, and the exclusive opening asks that analysis for EXTEND last, which it
keeps once for every reader.
"""

from __future__ import annotations

from lexic.ir import IrAst, IrRule
from lexic.parsing.caches import memo
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.parallel.discovery.anchors import anchors
from lexic.parsing.parallel.discovery.shapes import arm_empty, first_charset
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.predicates import rule_extensions
from lexic.parsing.pda.core.charsets import CharSet


def opens_with(rule_map: dict[str, IrRule], unit: str) -> CharSet:
    """Every character a unit may begin with — FIRST over all its arms."""
    target = rule_map.get(unit)
    if target is None:
        return CharSet.ANY
    found = CharSet.EMPTY
    for arm in target.body:
        found = found.union(first_charset(tuple(arm), rule_map, frozenset({unit})))
    return found


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
    """Run the four clauses once for one grammar's repeated unit.

    Determinism refuses islands and attemptable rules alike: an island hands
    the decision to Earley, where two readings survive, and an attempt
    settles a second success at RUNTIME rather than proving there cannot be
    one. Neither is a static guarantee.
    """
    rule_map = {str(rule.name): rule for rule in grammar.rules}
    target = rule_map.get(unit)
    if target is None:
        return frozenset()
    if any(arm_empty(tuple(arm), rule_map, frozenset()) for arm in target.body):
        return frozenset()
    opening = opens_with(rule_map, unit)
    if opening.negated or not opening.chars <= anchors(grammar):
        return frozenset()
    analysis = GrammarAnalysis(lift_optional_nullables(grammar))
    if analysis.taxonomy.conflicts:
        return frozenset()
    # The lift keeps every rule's name, so the unit is always in the map.
    extend = rule_extensions(analysis).found[unit]
    return frozenset() if opening.overlaps(extend) else frozenset(opening.chars)
