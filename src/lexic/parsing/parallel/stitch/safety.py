"""Static safety proofs for a region's separator ownership.

A repeated tail leading with ``,`` does not make every visible comma a tail:
the preceding item may itself accept commas at the same bracket depth. A cut
is sound only when that one competing owner cannot emit the separator. Nested
delimited rules are deliberately opaque to this proof because the structural
scan attributes their punctuation to the nested region, not to the owner.

VISIBLE is the whole question. A unit that hides its own marks inside a
delimited region — a fenced block's newlines, a quoted string's commas — owns
them only in the grammar, never in what the scan reads, so the proof asks the
question over the items a scan actually sees. Which regions those are is
:mod:`~lexic.parsing.parallel.discovery.interiors`' answer, read once here so
the proof and the scan cannot drift apart.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import IrAst, IrItem, IrLiteral, IrRule, IrRuleRef
from lexic.parsing.parallel.discovery.interiors import (
    Interior,
    hides,
    interior_rules,
    interior_shapes,
    interiors,
)
from lexic.parsing.parallel.discovery.regions import pair_rules
from lexic.parsing.parallel.discovery.shapes import UNIT, emits, leads_with, rule_emits
from lexic.parsing.parallel.roles import roles


def _protected(grammar: IrAst, region_scan: bool) -> frozenset[str]:
    """Rules hidden or depth-owned by the scan the caller actually uses."""
    pairs = pair_rules(grammar)
    if region_scan:
        paired = {rule for _close, rule in pairs.values()}
        return frozenset(paired) | interior_rules(grammar)
    tracked = set(roles(grammar).pairs)
    return frozenset(
        rule for opener, (closer, rule) in pairs.items() if (opener, closer) in tracked
    )


_OWNER_PROOFS: dict[tuple[int, str, str, bool], tuple[IrAst, bool]] = {}
"""Per-analysis-view ownership proofs, with a strong identity pin."""


def owner_excludes(
    grammar: IrAst, owner: str, separator: str, *, region_scan: bool = False
) -> bool:
    """Prove that ``owner`` cannot consume ``separator`` at this region depth.

    Failure to prove exclusion is an ordinary sequential decline. The proof is
    intentionally per owner: pooling every rule reachable anywhere would
    reject JSON because a nested object quite properly contains commas.
    """
    key = (id(grammar), owner, separator, region_scan)
    entry = _OWNER_PROOFS.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in grammar.rules}
        target = rules.get(owner)
        protected = _protected(grammar, region_scan)
        excludes = target is not None and (
            owner in protected
            or not rule_emits(target, separator, rules, protected, frozenset({owner}))
        )
        entry = (grammar, excludes)
        _OWNER_PROOFS[key] = entry
    return entry[1]


def _arm_target(items: tuple[IrItem, ...]) -> str:
    """The rule an arm consists of, when it is one plain unit reference."""
    atom = items[0].atom if len(items) == 1 else None
    if isinstance(atom, IrRuleRef) and items[0].quantifier == UNIT:
        return str(atom)
    return ""


def _unit_anchored(rules: dict[str, IrRule], owner: str, region: Interior) -> bool:
    """Whether a unit that begins with ``region``'s delimiter must BE it.

    A scan that only tests for the delimiter where a unit begins reads an
    occurrence anywhere else as ordinary text, so the region needs no sole
    spelling — it needs to open the unit, and to be the only arm that can.
    """
    unit = rules.get(owner)
    if unit is None or region.opens != 0 or region.escape:
        return False
    if region.rule == owner:
        return True
    leading = [
        tuple(arm)
        for arm in unit.body
        if leads_with(tuple(arm), region.delim[0], rules, frozenset({owner}))
    ]
    return len(leading) == 1 and _arm_target(leading[0]) == region.rule


_MARK_REGIONS: dict[tuple[int, str, str], tuple[IrAst, tuple[Interior, ...]]] = {}
"""The regions one owner's mark scan skips, with a strong identity pin."""


def mark_interiors(grammar: IrAst, owner: str, mark: str) -> tuple[Interior, ...]:
    """The opaque regions a scan for ``mark`` inside ``owner`` may skip.

    Only regions that actually HIDE the mark are returned: skipping one that
    cannot contain it buys nothing and costs the walk a test per unit. A
    region qualifies when a left-to-right pairing is exact everywhere
    (:func:`~...interiors.interiors`) or when it can only open where a unit
    does. Depth and anchoring do not compose — a grammar with bracket pairs
    keeps its windowed scan and hides nothing — so pairs decline outright.

    :param grammar: The analysis view.
    :param owner: The repeated unit whose marks are being scanned.
    :param mark: The character cuts key on.
    :returns: The certified regions, definition order; empty is the common
        answer and the cue that the windowed scan applies unchanged.
    """
    key = (id(grammar), owner, mark)
    entry = _MARK_REGIONS.get(key)
    if entry is None:
        entry = (grammar, _derive_mark_interiors(grammar, owner, mark))
        _MARK_REGIONS[key] = entry
    return entry[1]


def _derive_mark_interiors(
    grammar: IrAst, owner: str, mark: str
) -> tuple[Interior, ...]:
    """Certify the mark-hiding regions of one owner, once."""
    if roles(grammar).pairs:
        return ()
    rules = {str(rule.name): rule for rule in grammar.rules}
    certified = interiors(grammar)
    return tuple(
        region
        for region in interior_shapes(grammar)
        if hides(grammar, region, frozenset({mark}))
        and (region in certified or _unit_anchored(rules, owner, region))
    )


class Scope(NamedTuple):
    """What one terminator proof holds fixed while it recurses.

    :ivar rules: The grammar's rules by name.
    :ivar protected: Rules whose punctuation the scan attributes elsewhere.
    :ivar opaque: Rule name → the item index closing the region it hides,
        so the proof reads the arm's tail exactly where the scan resumes.
    """

    rules: dict[str, IrRule]
    protected: frozenset[str]
    opaque: dict[str, int]


def _visible(
    rule: IrRule, items: tuple[IrItem, ...], scope: Scope
) -> tuple[IrItem, ...]:
    """The arm's items a scan reads — everything past a hidden region."""
    closes = scope.opaque.get(str(rule.name))
    return items if closes is None else items[closes + 1 :]


def _ends_once(rule: IrRule, char: str, scope: Scope, path: frozenset[str]) -> bool:
    """Whether every arm emits ``char`` once, as its final visible edge."""
    for arm in rule.body:
        items = _visible(rule, tuple(arm), scope)
        if not items or any(
            emits(item, char, scope.rules, scope.protected, path) for item in items[:-1]
        ):
            return False
        last = items[-1]
        if last.quantifier != UNIT:
            return False
        atom = last.atom
        if isinstance(atom, IrLiteral):
            # A merged tail like "}\n" ends the unit too; the terminator must
            # be its final character and occur nowhere earlier in it, or the
            # scan would mark an offset inside the unit.
            valid = str(atom).endswith(char) and str(atom).count(char) == 1
        elif isinstance(atom, IrRuleRef):
            name = str(atom)
            target = scope.rules.get(name)
            valid = (
                name not in path
                and target is not None
                and _ends_once(target, char, scope, path | {name})
            )
        else:
            valid = False
        if not valid:
            return False
    return True


def _skip_set(regions: tuple[Interior, ...]) -> frozenset[tuple[str, str]]:
    """A region set as a scan reads it: what opens it, and what escapes it."""
    return frozenset((region.delim, region.escape) for region in regions)


def scan_agrees(view: IrAst, scanned: IrAst, owner: str, mark: str) -> bool:
    """Whether the regions ``scanned`` skips are the ones ``view`` proves.

    The proof runs over the structural view while the scan runs over the
    grammar it parses. What the scan DOES is fixed by the delimiter spellings
    alone, so the two answer the same question exactly when they derive the
    same ones — a view that elides a region proves nothing about a scan that
    still skips it, and the reverse leaves marks the proof never saw.
    """
    return _skip_set(mark_interiors(view, owner, mark)) == _skip_set(
        mark_interiors(scanned, owner, mark)
    )


_TERMINATOR_PROOFS: dict[tuple[int, str, str], tuple[IrAst, bool]] = {}
"""Per-analysis-view proof that a unit owns no internal terminator marks."""


def terminates_once(grammar: IrAst, owner: str, terminator: str) -> bool:
    """Prove every VISIBLE ``terminator`` in ``owner`` is its final edge."""
    key = (id(grammar), owner, terminator)
    entry = _TERMINATOR_PROOFS.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in grammar.rules}
        target = rules.get(owner)
        scope = Scope(
            rules,
            _protected(grammar, False),
            {
                region.rule: region.closes
                for region in mark_interiors(grammar, owner, terminator)
            },
        )
        proven = target is not None and _ends_once(
            target, terminator, scope, frozenset({owner})
        )
        entry = (grammar, proven)
        _TERMINATOR_PROOFS[key] = entry
    return entry[1]
