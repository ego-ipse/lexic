"""Opaque interiors — the spans a structural scan must skip, not read.

A grammar that spells strings as ``string ::= quote char* quote`` puts a
co-finite class inside a delimited region: a comma there is TEXT, not a
separator. Reading it is exactly how a naive splitter mis-cuts, and the
anchor analysis avoids that by de-certifying every character such a class
can emit — which for an RFC-shaped json is every structural character it
has, leaving nothing to split on at all.

The region is derivable, so the scan skips it instead. A rule whose one arm
opens with a literal spelling and closes with the SAME spelling carries one:
the items BETWEEN them are opaque when none of them can emit the delimiter's
lead character, or — for a one-character delimiter — when the body's arms lead
with an escape literal, which is what makes ``\\"`` not a closer. Items after
the closing delimiter stay visible; the region ends where the closer does. So
```` fence ::= tick3 info nl fenceline* tick3 nl ```` hides its interior
newlines and exposes its final one, on the same reading that hides a comma in
a string.

Deriving the shape does not license skipping it. A scan that pairs delimiter
occurrences from the left is exact only when every occurrence of the lead
character IS a delimiter, and :func:`interiors` certifies that by
reachability: no rule reachable without descending into the region may spell
that character. Shapes failing it stay in :func:`interior_shapes`, for the
analyses that anchor an occurrence some other way.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSelf,
)
from lexic.parsing.caches import memo
from lexic.parsing.parallel.discovery.shapes import (
    emits,
    literal_char,
    literal_text,
    unbounded,
)


class Interior(NamedTuple):
    """One delimited opaque region.

    :ivar rule: The rule whose arm carries it.
    :ivar arm: Which arm of that rule — a choice may delimit two ways, as a
        character class does with ``[`` and ``[^``.
    :ivar opening: The spelling that opens it.
    :ivar closing: The spelling that closes it — equal to ``opening`` for a
        quoted region, distinct for a comment (``";"`` … newline). The closing
        characters stay scan-visible: a comment's newline may be the very mark
        a split cuts on.
    :ivar escape: The character that makes the next one literal, or ``""``.
        Only a symmetric region has one; an asymmetric region is opaque
        because its body cannot spell the closer at all.
    :ivar closing: ``""`` for a region with no closing item at all — a trailing
        comment ends where the document does.
    :ivar opens: Item index of the opening delimiter.
    :ivar closes: Item index of the closing delimiter, or of the last item for
        a region that runs to EOF.
    """

    rule: str
    arm: int
    opening: str
    closing: str
    escape: str
    opens: int
    closes: int

    @property
    def spans_arm(self) -> bool:
        """Whether the region begins its arm — nothing visible precedes it."""
        return self.opens == 0

    @property
    def consumes_closer(self) -> bool:
        """Whether the scan skips the closer too, or leaves it to be read.

        A symmetric region must consume it, or a closing quote reads as an
        opening one. An asymmetric closer has no such ambiguity and stays
        visible, which is what keeps a comment's newline cuttable.
        """
        return self.opening == self.closing

    @property
    def resumes(self) -> int:
        """The first item index a scan reads again after the region.

        Only a DISTINCT closing item is left visible. A symmetric closer is
        consumed, and a region with no closer at all runs to the arm's end,
        so both resume past it.
        """
        distinct = bool(self.closing) and self.closing != self.opening
        return self.closes if distinct else self.closes + 1


def _escape_char(body: str, rule_map: dict[str, IrRule], seen: frozenset[str]) -> str:
    """The character an arm of the interior body leads with to escape.

    An arm that is one bare reference is followed: hoisting ``char ::= unescaped
    | "\\\\" escaped`` into a named second arm moves the escape one rule down
    without changing what the body derives.
    """
    rule = rule_map.get(body)
    if rule is None or body in seen:
        return ""
    for arm in rule.body:
        items = tuple(arm)
        if len(items) >= 2 and (lead := literal_char(items[0], rule_map)) is not None:
            return lead
        # Follow the arm's OWN head when it names one: a class item resolves
        # through ``cc-item-nc ::= cc-unit-nc cc-tail`` before reaching the
        # escape, and stopping at the first two-item arm never finds it.
        nested = items[0].atom if items else None
        if isinstance(nested, IrRuleRef):
            found = _escape_char(str(nested), rule_map, seen | {body})
            if found:
                return found
    return ""


def _opacity(
    inner: tuple[IrItem, ...], closing: str, rule_map: dict[str, IrRule]
) -> str | None:
    """What keeps the span before the closer opaque, or ``None``.

    ``""`` says nothing inside can spell the closer's lead character at all;
    an escape character says the body's own arms make an occurrence literal.
    A body with neither is not a region a scan may skip.
    """
    lead = closing[0]
    if not any(emits(item, lead, rule_map, frozenset(), frozenset()) for item in inner):
        return ""
    return (_body_escape(inner, lead, rule_map) or None) if len(closing) == 1 else None


def _body_escape(
    inner: tuple[IrItem, ...], lead: str, rule_map: dict[str, IrRule]
) -> str:
    """The one escape every part of the body that can spell ``lead`` uses.

    A quoted string keeps one body item; a character class has three, and any
    of them may reach the escaped closer. They must agree, or the region has no
    single parity to count and declines.
    """
    found: set[str] = set()
    for item in inner:
        if not emits(item, lead, rule_map, frozenset(), frozenset()):
            continue
        atom = item.atom
        escape = (
            _escape_char(str(atom), rule_map, frozenset())
            if isinstance(atom, IrRuleRef)
            else ""
        )
        if not escape:
            return ""
        found.add(escape)
    return found.pop() if len(found) == 1 else ""


def _closed_at(
    items: tuple[IrItem, ...], opening: str, rule_map: dict[str, IrRule]
) -> tuple[int, str, str] | None:
    """The item that closes the region opened at 0, with how it stays opaque.

    A region closed by its OWN spelling is tried first and may sit anywhere in
    the arm, so a quoted body keeps exactly the reading — and the escape
    derivation — it already had, and a fence keeps its visible tail.

    A DISTINCT closing spelling must be the arm's last item. Any later item
    that merely resolves to some literal is not a closer: ``object ::= "{" ws
    members "}" ws`` would otherwise read ``members`` as spelling the colon its
    first member carries, and open a region from ``{`` to ``:``.
    """
    same = next(
        (
            at
            for at in range(1, len(items))
            if literal_text(items[at], rule_map) == opening
        ),
        None,
    )
    if same is not None:
        escape = _opacity(items[1:same], opening, rule_map)
        if escape is not None:
            return (same, opening, escape)
    last = len(items) - 1
    closing = literal_text(items[last], rule_map)
    if closing is None or closing == opening:
        return None
    escape = _opacity(items[1:last], closing, rule_map)
    return None if escape is None else (last, closing, escape)


def _arm_interior(
    name: str, at: int, items: tuple[IrItem, ...], rule_map: dict[str, IrRule]
) -> Interior | None:
    """The interior one ARM defines, when it has a delimited shape.

    Read per arm rather than per rule: a character class spells ``[`` one way
    and ``[^`` another, and a rule that offers both is still two regions.
    """
    if len(items) < 2:
        return None
    opening = literal_text(items[0], rule_map)
    if opening is None:
        return None
    closed = _closed_at(items, opening, rule_map) if len(items) >= 3 else None
    if closed is not None:
        closes, closing, escape = closed
        return Interior(name, at, opening, closing, escape, 0, closes)
    # No closing item at all. A run behind an opener ends where the document
    # does, which is what a trailing comment IS. The opener must be spelled
    # RIGHT HERE: resolving one through rules would read ``members ::= member
    # members-rest*`` as opening at the colon its first member carries, and
    # skip from there to the end of the document.
    literal = isinstance(items[0].atom, IrLiteral)
    if not literal or len(items) != 2 or not unbounded(items[1]):
        return None
    return Interior(name, at, opening, "", "", 0, 1)


def _interiors_of(rule: IrRule, rule_map: dict[str, IrRule]) -> list[Interior]:
    """Every interior the rule's arms define, in arm order."""
    found = [
        _arm_interior(str(rule.name), at, tuple(arm), rule_map)
        for at, arm in enumerate(rule.body)
    ]
    return [region for region in found if region is not None]


def _refs(atom: IrSelf) -> frozenset[str]:
    """Every rule name an atom references, nested alternations included."""
    if isinstance(atom, IrRuleRef):
        return frozenset({str(atom)})
    if not isinstance(atom, IrAlternation):
        return frozenset()
    found: set[str] = set()
    for arm in atom:
        for item in arm:
            found |= _refs(item.atom)
    return frozenset(found)


def _visible_items(
    rule: IrRule, spans: dict[tuple[str, int], tuple[int, int]]
) -> tuple[IrItem, ...]:
    """The rule's items a scan still reads, its own hidden span removed.

    A region's DELIMITERS are visible — they are where the scan decides — so
    only what stands between them drops out. Hiding a whole rule instead would
    let two regions certify each other on delimiters they cannot tell apart.
    """
    kept: list[IrItem] = []
    for at, arm in enumerate(rule.body):
        items = tuple(arm)
        span = spans.get((str(rule.name), at))
        kept.extend(items if span is None else items[: span[0]] + items[span[1] :])
    return tuple(kept)


def _reachable_visible(
    grammar: IrAst,
    rule_map: dict[str, IrRule],
    spans: dict[tuple[str, int], tuple[int, int]],
    skip: str,
) -> frozenset[str]:
    """Rules reachable from the start through scan-visible items only."""
    seen: set[str] = set()
    pending = [str(grammar.start)]
    while pending:
        name = pending.pop()
        rule = rule_map.get(name)
        if name in seen or name == skip or rule is None:
            continue
        seen.add(name)
        for item in _visible_items(rule, spans):
            pending.extend(_refs(item.atom))
    return frozenset(seen)


def _sole_opener(
    grammar: IrAst,
    rule_map: dict[str, IrRule],
    region: Interior,
    spans: dict[tuple[str, int], tuple[int, int]],
    surviving: tuple[Interior, ...],
) -> bool:
    """Whether only this region opens with its lead character.

    ``spans`` gives the hidden span of every region a scan already skips. What
    stands inside one is not visible, so a spelling there cannot desync the
    pairing — which is what lets a comment and a quoted string certify each
    other. What stands at a region's delimiters IS visible, so a sibling that
    opens with the same character still refuses.

    Hiding every reference turns :func:`~...shapes.rule_emits` into "what does
    this item spell DIRECTLY", so the question is asked once per reachable
    rule rather than once per derivation path.
    """
    opaque = frozenset(rule_map)
    lead = region.opening[0]
    kin = _decided_by(surviving, region)
    return not any(
        emits(item, lead, rule_map, opaque, frozenset())
        for name in _reachable_visible(grammar, rule_map, spans, region.rule)
        if name not in kin
        for item in _visible_items(rule_map[name], spans)
    )


def _decided_by(surviving: tuple[Interior, ...], region: Interior) -> frozenset[str]:
    """Siblings a scan can already tell apart from ``region``.

    Sharing a lead character is not competition when the SPELLINGS differ:
    :func:`skip_table` orders them longest-first, so ``[^`` is tested before
    ``[`` and the reading is decided. Nor is a sibling :func:`_precise`
    subsumes — a trailing comment and a comment line open identically, and
    searching for the newline answers both.

    An identical opening with a different closer is real competition: the scan
    reaches it by that spelling alone and has nothing left to decide with.
    """
    deciding = {found.rule for found in _precise(list(surviving))}
    return frozenset(
        other.rule
        for other in surviving
        if other.opening[0] == region.opening[0]
        and (other.opening != region.opening or other.rule not in deciding)
    )


def _certified(
    grammar: IrAst, rule_map: dict[str, IrRule], shapes: tuple[Interior, ...]
) -> tuple[Interior, ...]:
    """The regions a left-to-right pairing reads exactly, as a fixpoint.

    Certification is mutual: abnf spells a quote inside its comments and a
    semicolon inside its strings, so neither region is sole on its own and
    both are sole beside the other. The fixpoint therefore starts with every
    candidate skipped and DROPS what fails, rather than starting empty and
    growing — a growing set cannot enter a cycle it needs to already be in.

    Soundness is the scan's own induction. Before the first region opener
    there is no region, so that occurrence is genuine; skipping to its closer
    leaves the scan outside every region again. An opener that only ever
    appears inside an already-skipped span is therefore never reached.

    Whether a certified region is one a given scan SHOULD skip is the
    caller's question, not this one's: the region sweep drops any whose
    opening character carries a bracket or separator role of its own.
    """
    surviving = tuple(region for region in shapes if region.spans_arm)
    while True:
        # The OPENING delimiter stays visible: it is where the scan decides
        # which region opens, so a sibling spelling it there must still refuse.
        spans = {
            (region.rule, region.arm): (region.opens + 1, region.resumes)
            for region in surviving
        }
        # A region another already decides for the scan rides along: its span
        # is skipped by that sibling, so it needs no opener proof of its own.
        deciding = {found.rule for found in _precise(list(surviving))}
        kept = tuple(
            region
            for region in surviving
            if region.rule not in deciding
            or _sole_opener(grammar, rule_map, region, spans, surviving)
        )
        if len(kept) == len(surviving):
            return kept
        surviving = kept


_SHAPES: dict[int, tuple[IrAst, tuple[Interior, ...]]] = memo({})
"""Shape memo — id(grammar) → (grammar, shapes). The strong reference pins the
id, so a recycled id can never alias a live entry."""


def interior_shapes(grammar: IrAst) -> tuple[Interior, ...]:
    """Every delimited region the grammar's rule shapes define.

    Certifying WHERE such a region may be recognised is the caller's question:
    :func:`interiors` answers it by reachability, and a plan that knows where
    its units begin can anchor one this analysis alone cannot.

    :param grammar: The grammar to analyse.
    :returns: One :class:`Interior` per delimited shape, definition order.
    """
    entry = _SHAPES.get(id(grammar))
    if entry is None:
        rule_map = {str(rule.name): rule for rule in grammar.rules}
        found = [
            region for rule in grammar.rules for region in _interiors_of(rule, rule_map)
        ]
        entry = (grammar, tuple(found))
        _SHAPES[id(grammar)] = entry
    return entry[1]


_INTERIORS: dict[int, tuple[IrAst, tuple[Interior, ...]]] = memo({})
"""Certified-skippable memo, keyed and pinned like :data:`_SHAPES`."""


def interiors(grammar: IrAst) -> tuple[Interior, ...]:
    """The regions a left-to-right scan may pair anywhere in the document.

    :param grammar: The grammar to analyse.
    :returns: The certified regions, definition order.
    """
    entry = _INTERIORS.get(id(grammar))
    if entry is None:
        rule_map = {str(rule.name): rule for rule in grammar.rules}
        found = _certified(grammar, rule_map, interior_shapes(grammar))
        entry = (grammar, found)
        _INTERIORS[id(grammar)] = entry
    return entry[1]


def interior_rules(grammar: IrAst) -> frozenset[str]:
    """Rules whose spans the structural scanner actually treats as opaque."""
    return frozenset(region.rule for region in interiors(grammar))


def hides(grammar: IrAst, region: Interior, watched: frozenset[str]) -> bool:
    """Whether ``region``'s own span can carry any of ``watched``.

    A region a scan would read the same way skipped or not is pure cost: it
    adds its delimiter to the swept characters and a search to every
    occurrence. Only regions that would otherwise MISLEAD are worth skipping.
    """
    rule_map = {str(rule.name): rule for rule in grammar.rules}
    items = tuple(tuple(rule_map[region.rule].body)[region.arm])
    return any(
        emits(item, char, rule_map, frozenset(), frozenset())
        for item in items[region.opens : region.resumes]
        for char in watched
    )


def skip_table(regions: tuple[Interior, ...]) -> dict[str, tuple[Interior, ...]]:
    """Lead character → the regions it may open, longest opening first.

    One character can lead more than one spelling (```` ` ```` opens both a
    code span and a fence), and the longer spelling is the one a scan must
    test first or it splits the longer opening in half.
    """
    found: dict[str, list[Interior]] = {}
    for region in regions:
        found.setdefault(region.opening[0], []).append(region)
    return {
        lead: tuple(sorted(_precise(entries), key=lambda region: -len(region.opening)))
        for lead, entries in found.items()
    }


def _precise(entries: list[Interior]) -> list[Interior]:
    """Drop regions a same-opening sibling already reads more exactly.

    A trailing comment and a comment line open alike and differ only in ending:
    one at a newline, one at EOF. Searching for the newline answers both, since
    a search that finds none already runs to EOF, so the EOF-only reading adds
    nothing and would swallow a document that has more to read.
    """
    closed = {region.opening for region in entries if region.closing}
    return [
        region for region in entries if region.closing or region.opening not in closed
    ]


type Skip = tuple[str, str, int, str, int]
"""One region as a scan consumes it.

``(closing, escape, resume, guard, width)``. ``resume`` is what the closer's
offset gains: a symmetric region consumes its closer, because leaving it would
read a closing quote as an opening one; an asymmetric region leaves it VISIBLE,
because a comment's newline may be the very mark a split cuts on. ``guard`` is
the opening spelling when it needs matching in full and ``""`` when one
character settles it — checked as a truth test so a single-character opening
pays no ``len``, which measurably was the whole cost of carrying longer ones.
"""


def as_skip(region: Interior) -> Skip:
    """One region in the flat form both scans hand to :func:`skip_delimited`."""
    symmetric = region.opening == region.closing
    return (
        region.closing,
        region.escape,
        len(region.closing) if symmetric else 0,
        region.opening if len(region.opening) > 1 else "",
        len(region.opening),
    )


def skip_leads(regions: tuple[Interior, ...]) -> dict[str, Skip]:
    """Lead character → the one region it opens.

    The region sweep tests this table once per structural character of a
    document, so the answer is a lookup rather than a search — which is what
    :func:`skip_table` is for, where a position is already known. A lead
    character opening two spellings has no single answer and is dropped: the
    sweep reaches it by that character alone and cannot tell them apart.
    """
    table = skip_table(regions)
    return {
        lead: as_skip(entries[0])
        for lead, entries in table.items()
        if len(entries) == 1
    }


def skip_opaque(text: str, at: int, candidates: tuple[Interior, ...]) -> int:
    """Past the region opening at ``at``, or ``at`` when none opens there."""
    for region in candidates:
        if text.startswith(region.opening, at):
            return skip_delimited(text, at, as_skip(region))
    return at


def skip_delimited(text: str, start: int, skip: Skip) -> int:
    """Where the region opened at ``start`` ends.

    Past its closer for a symmetric region, AT its closer for an asymmetric
    one, and ``start`` when a guarded opening does not stand here in full —
    the sweep reaches this on the lead character alone.
    """
    closing, escape, resume, guard, width = skip
    if guard and not text.startswith(guard, start):
        return start
    if closing == escape:
        return len(text)
    at = text.find(closing, start + width)
    while at != -1:
        before = at - 1
        while escape and before > start and text[before] == escape:
            before -= 1
        if not escape or (at - before - 1) % 2 == 0:
            return at + resume
        at = text.find(closing, at + 1)
    return len(text)
