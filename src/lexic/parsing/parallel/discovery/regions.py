"""Regions — the bracketed runs of a document that are worth dividing.

A document's parallelism does not live where its grammar's start rule is.
A tokenizer file is a small header beside two enormous tables; a log is one
flat list. What both have in common is BRACKETED RUNS: a delimited region
holding many separated items, at whatever depth it happens to sit.

This module finds those runs by scanning once, and cuts each into pieces
that are documents in their own right — a piece wrapped in its OWN region's
brackets is a well-formed instance of the rule that region belongs to, so it
parses at the cost of its own text and nothing more. That is the difference
that decides whether splitting pays: wrapping a piece in the whole
document's envelope re-parses every sibling table with every piece.

This module owns only region discovery and balanced piece selection. Model
orchestration composes those facts elsewhere; the retired reduction stitch
does not live beside the analysis.
"""

from __future__ import annotations

from bisect import bisect_left
from functools import partial
from typing import NamedTuple

from lexic.ir import IrAlternation, IrAst, IrItem, IrRule, IrRuleRef
from lexic.parsing.parallel.discovery.interiors import (
    Skip,
    hides,
    interiors,
    skip_delimited,
    skip_leads,
)
from lexic.parsing.parallel.discovery.shapes import edge_char, literal_char, unbounded
from lexic.parsing.parallel.policy import MIN_CHUNK


class Region(NamedTuple):
    """One bracketed run of separated items.

    :ivar opener: Offset of the bracket opening it.
    :ivar closer: Offset of the bracket closing it.
    :ivar rule: The rule a piece of it parses under (``object``, ``array``).
    :ivar marks: Offsets of the separators directly inside it.
    """

    opener: int
    closer: int
    rule: str
    marks: tuple[int, ...]

    @property
    def span(self) -> int:
        """How many characters the region covers."""
        return self.closer - self.opener


def pair_rules(grammar: IrAst) -> dict[str, tuple[str, str]]:
    """opener → ``(closer, rule)`` for every derived bracketing rule.

    A piece of a region parses under the rule whose arm spells that pair, so
    the split needs the RULE, not just the characters.
    """
    rule_map = {str(rule.name): rule for rule in grammar.rules}
    out: dict[str, tuple[str, str]] = {}
    for rule in grammar.rules:
        for arm in rule.body:
            items = tuple(arm)
            if len(items) < 3:
                continue
            opener = literal_char(items[0], rule_map)
            closers = [
                char
                for item in items[1:]
                if (char := literal_char(item, rule_map)) is not None
            ]
            if opener is None or not closers or closers[-1] == opener:
                continue
            out.setdefault(opener, (closers[-1], str(rule.name)))
    return out


def _repeated_bodies(
    items: tuple[IrItem, ...], rule_map: dict[str, IrRule]
) -> list[IrAlternation]:
    """Every unbounded body reachable from these items, nesting included.

    A repetition is often written inside another group — RFC json spells its
    member list ``[ member *( value-separator member ) ]`` — so a walk that
    reads only an arm's top-level items finds nothing that repeats.
    """
    out: list[IrAlternation] = []
    for item in items:
        atom = item.atom
        body = None
        if isinstance(atom, IrRuleRef):
            target = rule_map.get(str(atom))
            body = target.body if target is not None else None
        elif isinstance(atom, IrAlternation):
            body = atom
        if body is not None and unbounded(item):
            out.append(body)
        if isinstance(atom, IrAlternation):
            for arm in atom:
                out.extend(_repeated_bodies(tuple(arm), rule_map))
    return out


def separators(grammar: IrAst) -> frozenset[str]:
    """The characters that separate a repetition's items.

    Derived, never named: the single character every arm of a repeated body
    begins with is what stands between one item and the next.
    """
    rule_map = {str(rule.name): rule for rule in grammar.rules}
    spells = partial(literal_char, rule_map=rule_map)
    found: set[str] = set()
    for rule in grammar.rules:
        for arm in rule.body:
            for body in _repeated_bodies(tuple(arm), rule_map):
                char = edge_char(body, 0, spells)
                if char is not None:
                    found.add(char)
    return frozenset(found)


def _vocabulary(
    grammar: IrAst,
) -> tuple[dict[str, tuple[str, str]], frozenset[str], dict[str, Skip]]:
    """What the scan watches for: bracket pairs, separators, interiors.

    A region is carried only when it can carry a watched character and its
    lead character carries no role of its own. Skipping a region that hides
    nothing costs a swept delimiter and a search per occurrence for no change
    in the answer, and a lead character with a second role could not be
    handed to the skip unconditionally the way the sweep does.
    """
    pairs = pair_rules(grammar)
    marks = separators(grammar) - set(pairs)
    watched = frozenset(pairs) | {closer for closer, _rule in pairs.values()} | marks
    skips = tuple(
        region
        for region in interiors(grammar)
        if region.opening[0] not in watched and hides(grammar, region, watched)
    )
    return pairs, marks, skip_leads(skips)


def _sweep(text: str, watched: set[str]) -> list[int]:
    """Every offset in ``text`` holding one of ``watched``, in order.

    One C-level ``str.find`` pass per character: a Python loop over every
    character of a 10 MB document is itself a second of the answer.
    """
    offsets: list[int] = []
    for char in watched:
        at = text.find(char)
        while at != -1:
            offsets.append(at)
            at = text.find(char, at + 1)
    offsets.sort()
    return offsets


def find(grammar: IrAst, text: str, min_span: int = 0) -> list[Region]:
    """Every bracketed run in ``text``, with the separators inside it.

    One C-level sweep per watched character, merged by sort, then a stack
    walk over the structural offsets alone — a Python loop over every
    character of a 10 MB document is itself a second of the answer. Opaque
    interiors are skipped whole, their delimiter matched in full so a lead
    character that opens nothing here stays an ordinary character. A separator
    is attributed to the bracket that most recently opened, which is what
    makes the answer depth-agnostic: the caller asks for the BIGGEST runs
    rather than for a chosen level.

    :param grammar: The grammar whose roles and interiors drive the scan.
    :param text: The document.
    :param min_span: Omit smaller regions at close time; callers scheduling
        work use this to avoid retaining runs that cannot clear their floor.
    :returns: The regions, in closing order.
    """
    pairs, marks, skips = _vocabulary(grammar)
    closers = {closer: opener for opener, (closer, _rule) in pairs.items()}
    found: list[Region] = []
    stack: list[tuple[int, str, list[int]]] = []
    skip_to = 0
    for at in _sweep(text, set(pairs) | set(closers) | marks | set(skips)):
        if at < skip_to:
            continue  # inside an opaque interior — never read
        char = text[at]
        if char in skips:
            skip_to = skip_delimited(text, at, skips[char])
        elif char in pairs:
            stack.append((at, char, []))
        elif char in closers and stack and stack[-1][1] == closers[char]:
            opener, open_char, inside = stack.pop()
            if inside and at - opener >= min_span:
                found.append(Region(opener, at, pairs[open_char][1], tuple(inside)))
        elif char in marks and stack:
            stack[-1][2].append(at)
    return found


def nearest_mark(marks: tuple[int, ...], want: float) -> int:
    """The mark closest to ``want`` — cuts aim at positions, not at counts."""
    at = bisect_left(marks, want)
    if at == 0:
        return marks[0]
    if at == len(marks):
        return marks[-1]
    before, after = marks[at - 1], marks[at]
    return before if want - before <= after - want else after


def piece_marks(region: Region, workers: int) -> list[int]:
    """The separator offsets :func:`pieces` removes from ``region``.

    Kept as a named result because the model stitch must rebuild each removed
    separator under the region's own grammar. Re-deriving the marks from the
    piece strings would guess at source extent when the same text repeats.

    :param region: The run being divided.
    :param workers: How many balanced pieces are wanted.
    :returns: Distinct separator offsets, in document order.
    """
    lo, hi = region.opener + 1, region.closer
    target = (hi - lo) / workers
    cuts: list[int] = []
    for k in range(1, workers):
        nearest = nearest_mark(region.marks, lo + k * target)
        if nearest not in cuts:
            cuts.append(nearest)
    return cuts


def pieces(text: str, region: Region, workers: int) -> list[str] | None:
    """``region`` cut into ``workers`` self-contained pieces, or ``None``.

    Each piece carries only its OWN brackets, so it costs its own text —
    the point of cutting regions rather than wrapping the document. Cuts aim
    at equal byte positions and take the nearest separator, because dividing
    the separator COUNT divides the work only when they are evenly spread.

    :param text: The document.
    :param region: The run to cut.
    :param workers: How many pieces are wanted.
    :returns: The pieces, or ``None`` when the run will not divide.
    """
    bounds = _piece_bounds(region, workers)
    return _piece_texts(text, region, bounds) if bounds is not None else None


def _piece_bounds(region: Region, workers: int) -> list[int] | None:
    """Source bounds for balanced pieces, without copying their text."""
    lo, hi = region.opener + 1, region.closer
    target = (hi - lo) / workers
    cuts = piece_marks(region, workers)
    if not cuts:
        return None
    bounds = [lo, *[cut + 1 for cut in cuts], hi]
    if max(bounds[i + 1] - bounds[i] for i in range(len(bounds) - 1)) > 2 * target:
        return None
    return bounds


def _piece_texts(text: str, region: Region, bounds: list[int]) -> list[str]:
    """Materialize one accepted bounds plan exactly once."""
    open_char, close_char = text[region.opener], text[region.closer]
    return [
        open_char
        + text[bounds[i] : bounds[i + 1] - (1 if i + 2 < len(bounds) else 0)]
        + close_char
        for i in range(len(bounds) - 1)
    ]


def stub(text: str, region: Region, nth: int = 0) -> str:
    """The region's ``nth`` item, used as its distinct shell stand-in.

    Different regions use different item indices so equal first entries do not
    route to the same shell node. The index is clamped; equality plus exact
    items-node class is still checked later, and an unresolved collision makes
    the split decline.

    :param text: The complete document.
    :param region: The run whose one item should remain.
    :param nth: The item index, clamped to the run's final item.
    :returns: The raw item span, without the region's brackets.
    """
    at = min(nth, len(region.marks))
    start = region.opener + 1 if at == 0 else region.marks[at - 1] + 1
    end = region.marks[at] if at < len(region.marks) else region.closer
    return text[start:end]


def shell(text: str, regions: list[Region], keep: list[str]) -> str:
    """Replace each divided interior by its one-item stand-in.

    The owning brackets remain in the shell. Model orchestration replaces only
    the parsed items child, so those bracket fields survive the stitch exactly.

    :param text: The complete document.
    :param regions: Non-overlapping divided runs, in document order.
    :param keep: One replacement interior per region.
    :returns: The small document parsed once to provide the outer model shell.
    """
    out: list[str] = []
    at = 0
    for region, item in zip(regions, keep, strict=True):
        out.append(text[at : region.opener + 1])
        out.append(item)
        at = region.closer
    out.append(text[at:])
    return "".join(out)


def choose(
    text: str, found: list[Region], workers: int
) -> list[tuple[Region, list[str]]]:
    """The biggest runs that actually divide, and their pieces.

    A document's outermost bracket contains every other, so size alone would
    divide the same text twice — and worse, a big run that CANNOT divide
    (a tokenizer file's top level is eight members, two of them enormous)
    would claim the territory and block the runs inside it that can. So a
    region takes its span only if its pieces come out balanced; otherwise it
    steps aside and its children are considered on their own.

    ``workers`` is a ceiling, not an exact demand. Each selected run uses the
    largest count it can feed at least :data:`MIN_CHUNK`, while the shared pool
    still caps aggregate concurrency. This keeps useful four-way work when a
    caller happens to have eight cores.
    """
    candidates: list[tuple[Region, list[str]]] = []
    for region in sorted(found, key=lambda r: -r.span):
        capacity = min(workers, region.span // MIN_CHUNK)
        if capacity < 2:
            continue
        for count in range(capacity, 1, -1):
            bounds = _piece_bounds(region, count)
            # Span capacity is only an upper bound. Sparse outer containers
            # can leave one nearly empty piece and one piece holding the whole
            # nested payload; accepting that blocks the balanced child region
            # and repeats its work in joints and the shell. Every ACTUAL owner
            # must clear the already measured per-worker floor.
            if (
                bounds is not None
                and min(bounds[i + 1] - bounds[i] + 1 for i in range(len(bounds) - 1))
                >= MIN_CHUNK
            ):
                candidates.append((region, _piece_texts(text, region, bounds)))
                break
    # Prefer the ownership plan that fills more runners. Span breaks ties, but
    # cannot let a three-way outer container suppress an eight-way child.
    picked: list[tuple[Region, list[str]]] = []
    for region, parts in sorted(
        candidates, key=lambda entry: (-len(entry[1]), -entry[0].span)
    ):
        if any(
            region.opener < other.closer and other.opener < region.closer
            for other, _parts in picked
        ):
            continue
        picked.append((region, parts))
    return sorted(picked, key=lambda entry: entry[0].opener)
