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
    interior_shapes,
    interiors,
)
from lexic.parsing.parallel.discovery.regions import pair_rules
from lexic.parsing.parallel.discovery.scan import mark_overlap
from lexic.parsing.parallel.discovery.shapes import (
    MARK_ARITY,
    UNIT,
    arm_empty,
    arm_spells,
    derives_empty,
    emit_charset,
    emits,
    exact_text,
    first_charset,
    interior,
    joins,
    last_charset,
    leads_with,
    literal_char,
    literal_text,
    rule_emits,
    rule_spells,
    sole_char,
)
from lexic.parsing.parallel.roles import roles
from lexic.parsing.pda.core.charsets import CharSet


def _protected(grammar: IrAst, region_scan: bool, mark: str) -> frozenset[str]:
    """Rules hidden or depth-owned by the scan the caller actually uses.

    A scan owns only what lies INSIDE a delimited span: a paired rule's arm
    from its opener to its last closer, an interior's region from its opening
    to its closing. What an arm spells outside that span — after the closer
    (``"}" ("," note)*``), around an interior, or in an arm that delimits
    nothing — the scan reads at the depth the rule stands at. So a rule hides
    ``mark`` only when none of its visible parts spells it; otherwise the proof
    reads it like any other rule.
    """
    pairs = pair_rules(grammar)
    tracked = None if region_scan else set(roles(grammar).pairs)
    delimited = {
        (opener, closer, rule)
        for opener, (closer, rule) in pairs.items()
        if tracked is None or (opener, closer) in tracked
    }
    regions = interiors(grammar) if region_scan else ()
    rules = {str(rule.name): rule for rule in grammar.rules}
    candidates = {rule for _opener, _closer, rule in delimited} | {
        region.rule for region in regions
    }
    return frozenset(
        name
        for name in candidates
        if name in rules
        and not _visible_spells(rules[name], delimited, regions, mark, rules)
    )


def _visible_spells(
    rule: IrRule,
    delimited: set[tuple[str, str, str]],
    regions: tuple[Interior, ...],
    mark: str,
    rules: dict[str, IrRule],
) -> bool:
    """Whether any arm of ``rule`` spells ``mark`` where a scan reads it.

    Nothing is hidden inside what is read, so a ``False`` holds whatever the
    scan skips.
    """
    name = str(rule.name)
    own = {(opener, closer) for opener, closer, owner in delimited if owner == name}
    spans = {region.arm: region for region in regions if region.rule == name}
    path = frozenset({name})
    for at, arm in enumerate(rule.body):
        items = tuple(arm)
        for part in _visible_parts(items, own, spans.get(at), rules, len(mark) > 1):
            if arm_spells(part, mark, rules, frozenset(), path):
                return True
    return False


def _visible_parts(
    items: tuple[IrItem, ...],
    own: set[tuple[str, str]],
    region: Interior | None,
    rules: dict[str, IrRule],
    joined: bool,
) -> list[tuple[IrItem, ...]]:
    """The stretches of one arm a scan reads at the rule's own depth.

    Around an interior region, its closing included (it stays scan-visible).
    Otherwise the arm is walked counting depth over the rule's own openers and
    closers on one counter, as the scan counts them, and every item that
    stands at depth 0 is read: an arm may close and reopen
    (``"(" a ")" "," "(" b ")"``), and what stands between is the rule's own.
    A literal is walked character by character, so a merged ``"),("`` shows
    its comma. A literal spelling a delimiter under any other quantifier
    (``")"?``) leaves the depth unknown wherever it stands, and then the whole
    arm is read. Inside a span, a reference's own brackets are a nested
    region's, as the scan reads them; at depth 0 a reference that may emit a
    delimiter leaves the depth unknown too.
    """
    if region is not None:
        return [items[: region.opens], items[region.closes :]]
    delimiters = {char for pair in own for char in pair}
    walk = _DepthWalk({opener for opener, _closer in own}, {c for _o, c in own})
    for item in items:
        atom = item.atom
        if isinstance(atom, IrLiteral) and item.quantifier == UNIT:
            walk.spell(item, str(atom), joined)
            continue
        if isinstance(atom, IrLiteral) and delimiters & set(str(atom)):
            return [items]  # a repeated or optional delimiter: depth unknowable
        char = literal_char(item, rules)
        if char in delimiters:
            walk.spell(item, str(char), True)
            continue
        if walk.depth == 0 and _may_emit(item, delimiters, rules):
            return [items]
        walk.plain(item)
    return walk.done()


def _may_emit(item: IrItem, chars: set[str], rules: dict[str, IrRule]) -> bool:
    """Whether ``item`` may emit any of ``chars`` — unknowns answer yes."""
    emitted = emit_charset(item, rules, frozenset())
    return any(emitted.has(char) for char in chars)


class _DepthWalk:
    """One arm's depth walk: the stretches read at depth 0, as they close."""

    __slots__ = ("openers", "closers", "depth", "stretch", "parts")

    def __init__(self, openers: set[str], closers: set[str]) -> None:
        """Start at the rule's own depth with nothing read."""
        self.openers = openers
        self.closers = closers
        self.depth = 0
        self.stretch: list[IrItem] = []
        self.parts: list[tuple[IrItem, ...]] = []

    def plain(self, item: IrItem) -> None:
        """An item that neither opens nor closes: read when at depth 0."""
        if self.depth == 0:
            self.stretch.append(item)

    def spell(self, item: IrItem, text: str, border: bool) -> None:
        """An item spelling ``text``: move the depth character by character,
        and read the item when any of its own characters stands at depth 0 —
        or when it borders a read stretch and ``border`` asks for its edges."""
        seen = border and self.depth == 0
        for char in text:
            if char in self.openers:
                self.depth += 1
            elif char in self.closers and self.depth > 0:
                self.depth -= 1
            elif self.depth == 0:
                seen = True
        if seen or (border and self.depth == 0):
            self.stretch.append(item)
        if self.depth > 0:
            self.parts.append(tuple(self.stretch))
            self.stretch = []

    def done(self) -> list[tuple[IrItem, ...]]:
        """Every stretch read, the last one closed."""
        return [*self.parts, tuple(self.stretch)]


_OWNER_PROOFS: dict[tuple[int, str, str, bool], tuple[IrAst, bool]] = memo({}, 0)
"""Per-analysis-view ownership proofs, with a strong identity pin."""


def owner_excludes(
    grammar: IrAst, owner: str, separator: str, *, region_scan: bool = False
) -> bool:
    """Prove that ``owner`` cannot SPELL ``separator`` at this region depth.

    Failure to prove exclusion is an ordinary sequential decline. The proof is
    intentionally per owner: pooling every rule reachable anywhere would
    reject JSON because a nested object quite properly contains commas.

    Spelling, not emission: a separator wider than one character can be
    assembled at the join between two adjacent items neither of which emits it,
    so the question is asked of the owner's TEXT rather than of its atoms.

    A caller whose occurrences are not known to be aligned asks this of EVERY
    CHARACTER of its mark, one call each, rather than of the whole spelling.
    Exclusion on a substring implies exclusion on every superstring, so a
    per-character answer is the strongest form available — and it is the one
    that stays inside ``MARK_ARITY``, above which ``rule_spells`` answers "can
    spell" by design. Together with a non-empty item between two marks it
    proves alignment without any border theory: ``" + "`` and ``"aba"`` have
    the same border structure, and what tells them apart is whether an owner
    can emit the character a spurious occurrence would need.
    """
    key = (id(grammar), owner, separator, region_scan)
    entry = _OWNER_PROOFS.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in grammar.rules}
        target = rules.get(owner)
        protected = _protected(grammar, region_scan, separator)
        excludes = target is not None and (
            owner in protected
            or not rule_spells(target, separator, rules, protected, frozenset({owner}))
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


_MARK_REGIONS: dict[
    tuple[int, str, frozenset[str]], tuple[IrAst, tuple[Interior, ...]]
] = memo({}, 0)
"""The regions one owner's mark scan skips, with a strong identity pin."""


def mark_interiors(
    grammar: IrAst, owner: str, marks: frozenset[str]
) -> tuple[Interior, ...]:
    """The opaque regions a scan for ``mark`` inside ``owner`` may skip.

    Only regions that actually HIDE the mark are returned: skipping one that
    cannot contain it buys nothing and costs the walk a test per unit. A
    region qualifies when a left-to-right pairing is exact everywhere
    (:func:`~...interiors.interiors`) or when it can only open where a unit
    does. Depth and anchoring do not compose — a grammar with bracket pairs
    keeps its windowed scan and hides nothing — so pairs decline outright.

    :param grammar: The analysis view.
    :param owner: The repeated unit whose marks are being scanned.
    :param marks: The spellings cuts key on.
    :returns: The certified regions, definition order; empty is the common
        answer and the cue that the windowed scan applies unchanged.
    """
    key = (id(grammar), owner, marks)
    entry = _MARK_REGIONS.get(key)
    if entry is None:
        entry = (grammar, _derive_mark_interiors(grammar, owner, marks))
        _MARK_REGIONS[key] = entry
    return entry[1]


def _derive_mark_interiors(
    grammar: IrAst, owner: str, marks: frozenset[str]
) -> tuple[Interior, ...]:
    """Certify the mark-hiding regions of one owner, once."""
    if roles(grammar).pairs:
        return ()
    rules = {str(rule.name): rule for rule in grammar.rules}
    certified = interiors(grammar)
    return tuple(
        region
        for region in interior_shapes(grammar)
        if hides(grammar, region, marks)
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


def _ends_once(rule: IrRule, mark: str, scope: Scope, path: frozenset[str]) -> bool:
    """Whether every arm spells ``mark`` once, as its final visible edge."""
    for at, arm in enumerate(rule.body):
        items = _visible(rule, at, tuple(arm), scope)
        if not items or items[-1].quantifier != UNIT:
            return False
        if arm_spells(items[:-1], mark, scope.rules, scope.protected, path):
            return False
        if not _final_edge(items, mark, scope, path):
            return False
    return True


def _final_edge(
    items: tuple[IrItem, ...], mark: str, scope: Scope, path: frozenset[str]
) -> bool:
    """Whether the arm's ONE occurrence of ``mark`` is its closing edge.

    Either the final item spells the mark and the join into it adds no second
    overlapping occurrence, or it spells the mark's tail exactly while what
    precedes it always ends with the head — a blank line closing a paragraph.
    """
    head, last = items[:-1], items[-1]
    if _spells_edge(last, mark, scope, path):
        return len(mark) == 1 or not joins(head, (last,), mark, scope.rules, path)
    if len(mark) != MARK_ARITY or exact_text(last, scope.rules, path) != mark[1:]:
        return False
    if not head or arm_empty(head, scope.rules, frozenset()):
        return False
    return sole_char(last_charset(head, scope.rules, path)) == mark[0]


def _spells_edge(last: IrItem, mark: str, scope: Scope, path: frozenset[str]) -> bool:
    """Whether the arm's final item ends with ``mark`` and holds no other."""
    atom = last.atom
    if isinstance(atom, IrLiteral):
        # A merged tail like "}\n" ends the unit too, so the mark must be its
        # final characters and stand nowhere earlier. ``find`` is overlap-exact:
        # the leftmost occurrence being the last one makes it the only one.
        text = str(atom)
        return text.endswith(mark) and text.find(mark) == len(text) - len(mark)
    if not isinstance(atom, IrRuleRef):
        return False
    name = str(atom)
    target = scope.rules.get(name)
    return (
        name not in path
        and target is not None
        and _ends_once(target, mark, scope, path | {name})
    )


def _skip_set(regions: tuple[Interior, ...]) -> frozenset[tuple[str, str, str]]:
    """A region set as a scan reads it: what opens and closes it, and what
    escapes the closer."""
    return frozenset(
        (region.opening, region.closing, region.escape) for region in regions
    )


def scan_agrees(view: IrAst, scanned: IrAst, owner: str, marks: frozenset[str]) -> bool:
    """Whether the regions ``scanned`` skips are the ones ``view`` proves.

    The proof runs over the structural view while the scan runs over the
    grammar it parses. What the scan DOES is fixed by the delimiter spellings
    alone, so the two answer the same question exactly when they derive the
    same ones — a view that elides a region proves nothing about a scan that
    still skips it, and the reverse leaves marks the proof never saw.
    """
    return _skip_set(mark_interiors(view, owner, marks)) == _skip_set(
        mark_interiors(scanned, owner, marks)
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
            _protected(grammar, False, terminator),
            {
                (region.rule, region.arm): region.resumes
                for region in mark_interiors(grammar, owner, frozenset({terminator}))
            },
        )
        proven = (
            target is not None
            and _ends_once(target, terminator, scope, frozenset({owner}))
            # A unit ending with the mark ends with the mark's LAST character,
            # so an extra reading straddling two units needs the mark to be its
            # own border and the next unit to open with it — exactly the
            # undecidable case of the overlap question, asked of an owner this
            # proof has already shown ends with the mark.
            and mark_overlap(grammar, owner, terminator).decided
        )
        entry = (grammar, proven)
        _TERMINATOR_PROOFS[key] = entry
    return entry[1]


_BOUNDARY_SETS: dict[tuple[int, str, frozenset[str]], tuple[IrAst, bool]] = memo({}, 0)
"""Per-analysis-view set-valued boundary proofs, with a strong identity pin."""


def bounds_units(grammar: IrAst, owner: str, marks: frozenset[str]) -> bool:
    """Prove every occurrence of ``marks`` is a boundary of ``owner``.

    The set-valued terminator proof, for a unit whose arms close DIFFERENTLY
    and so agree on no single terminator. One obligation carries it: no
    character of ``marks`` may stand at a non-final position of any derivation
    of the unit. Every occurrence in a document of ``owner+`` then stands at
    some unit's last position, so a cut after it is exact — no candidate
    filter, no verification. Covering every way the unit can end is NOT
    required; missing one costs candidates, never exactness. A vanishing unit
    is refused, its end naming no position.

    :param grammar: The analysis view.
    :param owner: The repeated unit.
    :param marks: The candidate boundary characters.
    :returns: Whether every occurrence bounds a unit; ``False`` declines.
    """
    key = (id(grammar), owner, marks)
    entry = _BOUNDARY_SETS.get(key)
    if entry is None:
        rules = {str(rule.name): rule for rule in grammar.rules}
        target = rules.get(owner)
        single = bool(marks) and all(len(mark) == 1 for mark in marks)
        vanishes = target is None or any(
            arm_empty(tuple(arm), rules, frozenset()) for arm in target.body
        )
        proven = (
            single
            and not vanishes
            and not interior(rules, owner).overlaps(CharSet.from_chars(*marks))
        )
        entry = (grammar, proven)
        _BOUNDARY_SETS[key] = entry
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
    if not inside:
        return True
    if _ends_once(
        target, proof.mark, Scope(rules, frozenset(), {}), path | {str(target.name)}
    ):
        return True
    return leads_once(target, proof, rules, path)


def leads_once(
    target: IrRule,
    proof: Refutation,
    rules: dict[str, IrRule],
    path: frozenset[str],
) -> bool:
    """Whether the mark is a LEADING edge every arm resumes past harmlessly.

    The mirror of :func:`_ends_once`. A construct carrying the mark at its
    front — a continuation separator like ``"\n  | "`` — is entered mid-unit,
    so a cut proposed AT that mark starts its match on whatever the construct
    spells next. If that cannot begin the prefix, the match dies at its first
    character and the mark is not admissible: no false cut, whatever the
    construct reaches later.

    The obligation is CharSet disjointness, per arm, not an example:

    - every arm whose leading edge IS the mark must have
      ``FIRST(what follows the mark in that arm, through nullables)``
      **disjoint from the prefix's head charset**;
    - arms that do not lead with the mark contribute under the ordinary
      reachability rules — this clause says nothing about them;
    - an arm the walk cannot decide answers "reachable", so the plan declines,
      as everywhere else in this proof.

    A construct carrying the mark at a leading edge AND somewhere interior
    gets NO clause: the interior occurrence is a real mid-construct cut
    candidate, and it keeps refusing through the ordinary path.
    """
    head = proof.found.head
    leads = False
    for arm in target.body:
        items = tuple(arm)
        after = _after_lead_mark(items, proof.mark, rules, path)
        if after is None:
            if _arm_carries(items, proof.mark, rules, path):
                return False  # not a leading edge — the ordinary path owns it
            continue
        leads = True
        if after.negated or after.overlaps(head):
            return False
        if _arm_carries(items[1:], proof.mark, rules, path):
            return False  # a second, interior occurrence — no clause
    return leads


def _after_lead_mark(
    items: tuple[IrItem, ...],
    mark: str,
    rules: dict[str, IrRule],
    path: frozenset[str],
) -> CharSet | None:
    """FIRST of what follows a LEADING mark in one arm, or ``None``.

    ``None`` says the arm does not lead with the mark, which is the caller's
    cue to leave it to the ordinary walk. The mark is a CHARACTER, so a
    multi-character literal carries its own continuation: ``"\n  | "`` is
    followed by ``" "`` inside the very same item.

    A leading literal whose TAIL spells the mark again does not lead: that
    second occurrence is interior, the caller's arm-carries check must see
    it, and answering ``None`` here is what routes the arm there.
    """
    if not items:
        return None
    spelling = literal_text(items[0], rules)
    if not spelling or not spelling.startswith(mark) or mark in spelling[1:]:
        return None
    if len(spelling) > 1:
        return CharSet.from_chars(spelling[1])
    return first_charset(items[1:], rules, path)


def _arm_carries(
    items: tuple[IrItem, ...],
    mark: str,
    rules: dict[str, IrRule],
    path: frozenset[str],
) -> bool:
    """Whether any item of the arm can emit ``mark`` at all."""
    return any(emits(item, mark, rules, frozenset(), path) for item in items)


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
    if len(mark) != 1:
        # The announcing-prefix proof is stated over a mark CHARACTER: the
        # noise run subtracts it from a CharSet and the refutation walks
        # per-character alphabets. A spelling owes a second proof this one
        # does not make, so it declines rather than borrowing this one.
        return None
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
