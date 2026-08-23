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

from lexic.ir import IrAlternation, IrAst, IrItem, IrLiteral, IrRule, IrRuleRef
from lexic.parsing.caches import memo
from lexic.parsing.parallel.discovery.interiors import (
    Interior,
    hides,
    interior_rules,
    interior_shapes,
    interiors,
)
from lexic.parsing.parallel.discovery.regions import pair_rules
from lexic.parsing.parallel.discovery.shapes import (
    UNIT,
    derives_empty,
    emit_charset,
    emits,
    first_charset,
    leads_with,
    rule_emits,
)
from lexic.parsing.parallel.roles import roles
from lexic.parsing.pda.core.charsets import CharSet


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


_OWNER_PROOFS: dict[tuple[int, str, str, bool], tuple[IrAst, bool]] = memo({}, 0)
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
        if leads_with(tuple(arm), region.opening[0], rules, frozenset({owner}))
    ]
    return len(leading) == 1 and _arm_target(leading[0]) == region.rule


_MARK_REGIONS: dict[tuple[int, str, str], tuple[IrAst, tuple[Interior, ...]]] = memo(
    {}, 0
)
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
    :ivar opaque: ``(rule, arm)`` → the first item index the scan reads again
        after the region that arm hides, so the proof reads exactly what the
        scan does. Keyed per ARM: one rule may delimit two ways.
    """

    rules: dict[str, IrRule]
    protected: frozenset[str]
    opaque: dict[tuple[str, int], int]


def _visible(
    rule: IrRule, at: int, items: tuple[IrItem, ...], scope: Scope
) -> tuple[IrItem, ...]:
    """The arm's items a scan reads — everything past a hidden region."""
    resumes = scope.opaque.get((str(rule.name), at))
    return items if resumes is None else items[resumes:]


def _ends_once(rule: IrRule, char: str, scope: Scope, path: frozenset[str]) -> bool:
    """Whether every arm emits ``char`` once, as its final visible edge."""
    for at, arm in enumerate(rule.body):
        items = _visible(rule, at, tuple(arm), scope)
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


def _skip_set(regions: tuple[Interior, ...]) -> frozenset[tuple[str, str, str]]:
    """A region set as a scan reads it: what opens and closes it, and what
    escapes the closer."""
    return frozenset(
        (region.opening, region.closing, region.escape) for region in regions
    )


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


_TERMINATOR_PROOFS: dict[tuple[int, str, str], tuple[IrAst, bool]] = memo({}, 0)
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
                (region.rule, region.arm): region.resumes
                for region in mark_interiors(grammar, owner, terminator)
            },
        )
        proven = target is not None and _ends_once(
            target, terminator, scope, frozenset({owner})
        )
        entry = (grammar, proven)
        _TERMINATOR_PROOFS[key] = entry
    return entry[1]


class Boundary(NamedTuple):
    """The unit prefix a certified cut must land on.

    A unit whose arm reads ``head noise* literal rest…`` announces itself: the
    head's alphabet, the noise it may carry before the literal, and the literal
    that settles it. A cut is admitted where that pattern stands, and the mark
    is excluded from the noise so the match can never span two units.

    :ivar head: What the mandatory first item can spell.
    :ivar noise: What may stand between head and literal, mark removed.
    :ivar literal: The mandatory literal spelling that ends the prefix.
    :ivar at: Its item index in the unit's arm.
    """

    head: CharSet
    noise: CharSet
    literal: str
    at: int

    @property
    def allowed(self) -> CharSet:
        """Every character the admission match may cross."""
        return self.head.union(self.noise)


def unit_prefix(
    rules: dict[str, IrRule], unit: str, mark: str, skipped: frozenset[str]
) -> Boundary | None:
    """The unit's mandatory announcing prefix, or ``None`` on a shape miss.

    Obligations O2 and O3: one mandatory head item, then only items that can
    vanish, then a mandatory item opening with ONE character that stands
    outside everything before it — otherwise the match could not tell them
    apart. The lead character is what settles the prefix, so a two-armed
    ``defined ::= "=" | "=/"`` announces itself exactly as a bare literal does.

    :param skipped: Rules the noise run jumps whole, so their alphabet — a
        comment's is nearly everything — never widens the noise.
    """
    target = rules.get(unit)
    arms = tuple(target.body) if target is not None else ()
    items = tuple(arms[0]) if len(arms) == 1 else ()
    if len(items) < 2 or derives_empty(items[0], rules, frozenset()):
        return None
    head = emit_charset(items[0], rules, frozenset(), skipped)
    noise = CharSet.EMPTY
    for at in range(1, len(items)):
        if not derives_empty(items[at], rules, frozenset()):
            opens = first_charset((items[at],), rules, frozenset())
            return _prefix_of(head, noise, opens, at, mark)
        noise = noise.union(emit_charset(items[at], rules, frozenset(), skipped))
    return None


def _prefix_of(
    head: CharSet, noise: CharSet, opens: CharSet, at: int, mark: str
) -> Boundary | None:
    """One candidate prefix, once its mandatory closing item is known."""
    if opens.negated or len(opens.chars) != 1:
        return None
    lead = next(iter(opens.chars))
    found = Boundary(head, noise.subtract(CharSet.from_chars(mark)), lead, at)
    if found.allowed.overlaps(opens) or head.has(mark):
        return None
    return found


class Refutation(NamedTuple):
    """What the boundary refutation is trying to break, and what it may not enter.

    :ivar found: The prefix a cut must land on.
    :ivar mark: The character cuts key on.
    :ivar skipped: The certified regions. The scan skips these whole, so a mark
        one of them can spell is never a CANDIDATE mark and cannot begin a
        false match inside it.
    """

    found: Boundary
    mark: str
    skipped: frozenset[str]


def _reaches_literal(
    item: IrItem,
    proof: Refutation,
    rules: dict[str, IrRule],
    path: frozenset[str],
) -> bool:
    """Whether a match confined to ``found.allowed`` can reach a literal here.

    The refutation walk. A construct guards everything inside it when the match
    cannot enter: its opening alphabet stands outside what the match may cross,
    so the very first character refuses. A construct the mark can stand INSIDE
    is not guarded that way — the match would begin within it, past its opener
    — unless the mark is its final edge, as a comment's newline is.
    """
    lead = proof.found.literal[0]
    if not emits(item, lead, rules, frozenset(), path):
        return False
    atom = item.atom
    if isinstance(atom, IrAlternation):
        return any(
            _reaches_literal(inner, proof, rules, path) for arm in atom for inner in arm
        )
    if not isinstance(atom, IrRuleRef):
        return True
    name = str(atom)
    target = rules.get(name)
    if target is None or name in path:
        return True
    if _guards(target, proof, rules, path):
        return False
    return any(
        _reaches_literal(inner, proof, rules, path | {name})
        for arm in target.body
        for inner in arm
    )


def _guards(
    target: IrRule,
    proof: Refutation,
    rules: dict[str, IrRule],
    path: frozenset[str],
) -> bool:
    """Whether entering ``target`` refuses a match confined to the prefix.

    A CERTIFIED region guards outright: the scan skips it whole, so no cut is
    ever proposed inside it and no false match can begin there — which is what
    the ``inside`` test below exists to catch for constructs the scan does read
    into. The opener check still applies to both: skipping is irrelevant if the
    match could walk in over allowed characters.
    """
    opens = first_charset(
        tuple(tuple(target.body)[0]) if len(tuple(target.body)) == 1 else (),
        rules,
        path,
    )
    entered = _body_opens(target, rules, path)
    allowed = proof.found.allowed
    if entered.overlaps(allowed) or opens.overlaps(allowed):
        return False
    if str(target.name) in proof.skipped:
        return True
    inside = rule_emits(target, proof.mark, rules, frozenset(), path)
    return not inside or _ends_once(
        target, proof.mark, Scope(rules, frozenset(), {}), path | {str(target.name)}
    )


def _body_opens(
    target: IrRule, rules: dict[str, IrRule], path: frozenset[str]
) -> CharSet:
    """Every character any arm of a rule can begin with."""
    found = CharSet.EMPTY
    for arm in target.body:
        found = found.union(first_charset(tuple(arm), rules, path))
    return found


_BOUNDARY_PROOFS: dict[tuple[int, str, str], tuple[IrAst, Boundary | None]] = memo(
    {}, 0
)
"""Per-analysis-view boundary proofs, with a strong identity pin."""


def unit_boundary(grammar: IrAst, unit: str, mark: str) -> Boundary | None:
    """The prefix a cut before ``unit`` must land on, or ``None`` to decline.

    Replaces the single-character exclusion for units that legitimately CARRY
    the mark — a rule spanning lines owns newlines the scan still reads. What
    makes a cut exact there is not that the mark is absent, but that the unit
    ANNOUNCES itself: past the mark and its noise run, a unit start spells
    ``head+ noise* literal`` with no mark crossed, and nothing mid-unit can.

    The refutation is what proves it. A false admission would need the unit to
    reach the prefix literal over head/noise text alone; every construct that
    could carry that literal is entered through a character the match may not
    cross, so the match dies at the opener rather than reading what is inside.
    A construct the mark can stand INSIDE is not guarded that way and refuses
    the whole proof, unless the mark is its final edge as a comment's is.

    :param grammar: The analysis view.
    :param unit: The repeated unit a cut lands before.
    :param mark: The character cuts key on.
    :returns: The certified prefix, or ``None`` — an ordinary decline.
    """
    key = (id(grammar), unit, mark)
    entry = _BOUNDARY_PROOFS.get(key)
    if entry is None:
        entry = (grammar, _derive_boundary(grammar, unit, mark))
        _BOUNDARY_PROOFS[key] = entry
    return entry[1]


def _derive_boundary(grammar: IrAst, unit: str, mark: str) -> Boundary | None:
    """Shape the unit's prefix, then try to refute a mid-unit match."""
    rules = {str(rule.name): rule for rule in grammar.rules}
    skipped = frozenset(
        region.rule
        for region in interior_shapes(grammar)
        if region.opening != region.closing
    )
    found = unit_prefix(rules, unit, mark, skipped)
    if found is None:
        return None
    # The refutation walk reads CERTIFIED regions, not merely asymmetric
    # shapes: what makes a construct unenterable mid-match is that the scan
    # skips it whole, which is exactly what certification establishes.
    proof = Refutation(found, mark, frozenset(r.rule for r in interiors(grammar)))
    items = tuple(tuple(rules[unit].body)[0])
    refuted = not any(
        _reaches_literal(item, proof, rules, frozenset({unit}))
        for at, item in enumerate(items)
        if at != found.at
    )
    return found if refuted else None


def noise_skips(grammar: IrAst) -> tuple[Interior, ...]:
    """The regions a lead's noise run jumps whole, in definition order.

    An asymmetric region is exactly what a noise run must cross without
    reading: a comment carries whatever it likes and ends at its own closer.
    """
    return tuple(
        region
        for region in interior_shapes(grammar)
        if region.opening != region.closing
    )
