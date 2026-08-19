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

What is left over — the document with each region reduced to one piece — is
the shell, and it is parsed once. Every region's value then replaces the
piece it stood in for.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from functools import partial
from typing import NamedTuple

from lexic.exceptions import LexicError
from lexic.ir import IrAlternation, IrAst, IrItem, IrRule, IrRuleRef, IrSelf
from lexic.parsing.earley.reduce.reducer import Reducer
from lexic.parsing.parallel.interiors import interiors
from lexic.parsing.parallel.policy import AUTO, doc_workers
from lexic.parsing.parallel.pool import ParsePool
from lexic.parsing.parallel.replicas import grammar_replicas
from lexic.parsing.parallel.shapes import edge_char, literal_char, unbounded


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


def _skip_interior(text: str, start: int, escape: str) -> int:
    """Where the interior opened at ``start`` ends (past its closer)."""
    delim = text[start]
    at = start + 1
    while at < len(text):
        char = text[at]
        if escape and char == escape:
            at += 2
            continue
        if char == delim:
            return at + 1
        at += 1
    return len(text)


def _vocabulary(
    grammar: IrAst,
) -> tuple[dict[str, tuple[str, str]], frozenset[str], dict[str, str]]:
    """What the scan watches for: bracket pairs, separators, interiors."""
    pairs = pair_rules(grammar)
    marks = separators(grammar) - set(pairs)
    skips = {region.delim: region.escape for region in interiors(grammar)}
    return pairs, marks, skips


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


def find(grammar: IrAst, text: str) -> list[Region]:
    """Every bracketed run in ``text``, with the separators inside it.

    One C-level sweep per watched character, merged by sort, then a stack
    walk over the structural offsets alone — a Python loop over every
    character of a 10 MB document is itself a second of the answer. Opaque
    interiors are skipped whole. A separator is attributed to the bracket that most
    recently opened, which is what makes the answer depth-agnostic: the
    caller asks for the BIGGEST runs rather than for a chosen level.

    :param grammar: The grammar whose roles and interiors drive the scan.
    :param text: The document.
    :returns: The regions, in closing order.
    """
    pairs, marks, skips = _vocabulary(grammar)
    closers = {closer: opener for opener, (closer, _rule) in pairs.items()}
    offsets = _sweep(text, set(pairs) | set(closers) | marks | set(skips))
    found: list[Region] = []
    stack: list[tuple[int, str, list[int]]] = []
    skip_to = 0
    for at in offsets:
        if at < skip_to:
            continue  # inside an opaque interior — never read
        char = text[at]
        if char in skips:
            skip_to = _skip_interior(text, at, skips[char])
        elif char in pairs:
            stack.append((at, char, []))
        elif char in closers and stack and stack[-1][1] == closers[char]:
            opener, open_char, inside = stack.pop()
            if inside:
                found.append(Region(opener, at, pairs[open_char][1], tuple(inside)))
        elif char in marks and stack:
            stack[-1][2].append(at)
    return found


def _nearest(marks: tuple[int, ...], want: float) -> int:
    """The mark closest to ``want`` — cuts aim at positions, not at counts."""
    return min(marks, key=lambda mark: abs(mark - want))


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
    open_char, close_char = text[region.opener], text[region.closer]
    lo, hi = region.opener + 1, region.closer
    target = (hi - lo) / workers
    cuts: list[int] = []
    for k in range(1, workers):
        nearest = _nearest(region.marks, lo + k * target)
        if nearest not in cuts:
            cuts.append(nearest)
    if not cuts:
        return None
    bounds = [lo, *[cut + 1 for cut in cuts], hi]
    if max(bounds[i + 1] - bounds[i] for i in range(len(bounds) - 1)) > 2 * target:
        return None
    return [
        open_char
        + text[bounds[i] : bounds[i + 1] - (1 if i + 2 < len(bounds) else 0)]
        + close_char
        for i in range(len(bounds) - 1)
    ]


def stub(text: str, region: Region) -> str:
    """The region's FIRST item — the least text that keeps its shape.

    The shell is the one part still parsed whole, so what stands in for a
    divided run should be as small as the run allows: one item, not one
    piece. On a 10 MB tokenizer that is the difference between a 670 KB
    shell and a 2 KB one, and the shell is serial.
    """
    return text[region.opener + 1 : region.marks[0]]


def shell(text: str, regions: list[Region], keep: list[str]) -> str:
    """``text`` with each region's interior replaced by ``keep``'s stand-in.

    :param text: The document.
    :param regions: The divided runs, in document order.
    :param keep: The interior text to leave in place of each.
    :returns: The reduced document.
    """
    out: list[str] = []
    at = 0
    for region, piece in zip(regions, keep, strict=True):
        out.append(text[at : region.opener + 1])
        out.append(piece)
        at = region.closer
    out.append(text[at:])
    return "".join(out)


def merge(values: list[IrSelf]) -> IrSelf | None:
    """Concatenate a region's piece values into the one it means.

    Every piece is the same bracketing rule carrying its own items, so the
    region's value is their concatenation.

    :param values: The piece values, in document order.
    :returns: The merged value, or ``None`` when the pieces disagree.
    """
    if not values:
        return None
    first = values[0]
    if any(not isinstance(value, type(first)) for value in values[1:]):
        return None
    items = [item for value in values for item in value.children()]
    try:
        return values[0].rebuild(items)
    except TypeError, ValueError, LexicError:
        return None


def _preorder(
    node: IrSelf, route: tuple[int, ...]
) -> Iterator[tuple[tuple[int, ...], IrSelf]]:
    """Every node at or under ``node``, with the route reaching it.

    Walks the spine's own ``children()``: a reduced document is not a tuple
    (an ``IrMap`` iterates and has a length without subclassing one), so
    asking the node what its children are is both the typed answer and the
    only correct one.
    """
    yield route, node
    for index, part in enumerate(node.children()):
        yield from _preorder(part, (*route, index))


def _past(route: tuple[int, ...], after: tuple[int, ...]) -> bool:
    """Whether ``route`` reaches a node strictly after — and outside — ``after``."""
    return route > after and route[: len(after)] != after


def route_after(
    whole: IrSelf, needle: IrSelf, after: tuple[int, ...] | None
) -> tuple[int, ...] | None:
    """Where ``needle`` sits inside ``whole``, past ``after``; ``None`` = nowhere.

    Value equality alone cannot answer this. Two regions whose stand-ins
    reduce to the same value — two arrays beginning with the same item — have
    the same needle, so the first match claims both, one region's value is
    written twice and the other keeps its stub. Nothing raises; the caller
    just returns the wrong document.

    Position is what tells them apart. :func:`choose` refuses overlapping
    regions, so the runs are disjoint and in document order, and any
    order-preserving reduction lays their stand-ins down in that same order.
    Searching each from strictly past the previous one — and outside it,
    since a later region can never be INSIDE an earlier one — makes the
    assignment unique exactly where equality is not.

    :param whole: The shell's reduced value.
    :param needle: The stand-in value to place.
    :param after: The previous region's route, or ``None`` for the first.
    :returns: The route, or ``None`` when no admissible node matches.
    """
    for route, node in _preorder(whole, ()):
        if after is not None and not _past(route, after):
            continue
        if node is needle or node == needle:
            return route
    return None


def splice[V: IrSelf](whole: V, route: tuple[int, ...], value: IrSelf) -> V | None:
    """``whole`` with the node at ``route`` replaced by ``value``.

    An empty route addresses ``whole`` itself, which this cannot answer: the
    replacement is any ``IrSelf`` and the return is ``whole``'s own type. The
    caller decides what replacing the root means.
    """
    if not route:
        return None
    parts = list(whole.children())
    head = route[0]
    if len(route) > 1:
        inner = splice(parts[head], route[1:], value)
        if inner is None:
            return None
        parts[head] = inner
    else:
        parts[head] = value
    try:
        return whole.rebuild(parts)
    except TypeError, ValueError, LexicError:
        return None


def rooted(grammar: IrAst, rule: str) -> IrAst:
    """``grammar`` re-rooted at ``rule`` — what a piece parses under."""
    return grammar if rule == str(grammar.start) else IrAst(grammar.rules, rule)


MIN_REGION = 64 * 1024
"""A run below this is not worth dividing — the overhead outweighs it."""


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
    """
    picked: list[tuple[Region, list[str]]] = []
    for region in sorted(found, key=lambda r: -r.span):
        if region.span < MIN_REGION:
            break
        if any(
            region.opener < other.closer and other.opener < region.closer
            for other, _parts in picked
        ):
            continue
        parts = pieces(text, region, workers)
        if parts is not None:
            picked.append((region, parts))
    return sorted(picked, key=lambda entry: entry[0].opener)


class Reduction(NamedTuple):
    """The reduce product bound to one grammar, reducer and worker count.

    The four travel together through every phase of a split, so they are one
    record rather than four parameters repeated at each hand-off.

    :ivar reduce: The reduce product, injected by the layer that owns it.
    :ivar grammar: The authored grammar.
    :ivar reducer: The grammar's reduction policy.
    :ivar workers: How many pieces reduce beside each other.
    """

    reduce: Callable[[IrAst, str, Reducer], IrSelf]
    grammar: IrAst
    reducer: Reducer
    workers: int


def _parse_pieces(run: Reduction, flat: list[tuple[str, str]]) -> list[IrSelf]:
    """Every piece, reduced concurrently, each worker on its own replica."""
    views = grammar_replicas(run.grammar, min(run.workers, len(flat)) or 1)
    pool = ParsePool[int, IrSelf](
        lambda k: run.reduce(
            rooted(views[k % len(views)], flat[k][0]), flat[k][1], run.reducer
        ),
        run.workers,
    )
    try:
        return pool.map(range(len(flat)))
    finally:
        pool.close()


class Parts(NamedTuple):
    """What a split reduction holds before it splices.

    :ivar values: Every piece's value, flat, in document order.
    :ivar whole: The shell's value — the document with each run stubbed.
    :ivar stubs: Each region's stand-in, reduced under that region's own rule.
    """

    values: list[IrSelf]
    whole: IrSelf
    stubs: list[IrSelf]


def _reduce_parts(
    run: Reduction, text: str, divided: list[tuple[Region, list[str]]]
) -> Parts | None:
    """The pieces, the shell and the stand-ins; ``None`` = reduce sequentially.

    A refusal here is a verdict on the SPLIT, never on the document: the
    caller reduces the whole text instead, and that parse is what raises.
    """
    flat = [(region.rule, piece) for region, parts in divided for piece in parts]
    regions = [region for region, _parts in divided]
    keep = [stub(text, region) for region in regions]
    try:
        values = _parse_pieces(run, flat)
        whole = run.reduce(run.grammar, shell(text, regions, keep), run.reducer)
        stubs = [
            run.reduce(
                rooted(run.grammar, region.rule),
                text[region.opener] + piece + text[region.closer],
                run.reducer,
            )
            for region, piece in zip(regions, keep, strict=True)
        ]
    except LexicError:
        return None
    return Parts(values, whole, stubs)


def _splice_all(
    divided: list[tuple[Region, list[str]]], parts: Parts, size: int
) -> IrSelf | None:
    """Each region's merged value in the place its stand-in holds.

    :param divided: The chosen runs and their pieces, in document order.
    :param parts: The piece values, the shell's value and the stand-ins.
    :param size: The document's length, which certifies a root route.
    :returns: The document's value, or ``None`` to reduce sequentially.
    """
    whole = parts.whole
    at = 0
    after: tuple[int, ...] | None = None
    placed: list[tuple[Region, tuple[int, ...], IrSelf]] = []
    for index, (region, cuts) in enumerate(divided):
        merged = merge(parts.values[at : at + len(cuts)])
        at += len(cuts)
        if merged is None:
            return None
        # The needle is the STUB's own value, reduced: a container normalises
        # what it holds, so the merged value's first entry is not necessarily
        # the one the shell kept.
        after = route_after(whole, parts.stubs[index], after)
        if after is None:
            return None
        placed.append((region, after, merged))
    for region, route, merged in placed:
        if not route:
            # The stand-in IS the shell's whole value. That is the answer only
            # when the run is the whole document; anywhere else it means the
            # reduction spells an inner value the same way as its container,
            # and which of the two the shell kept is not decidable here.
            if region.opener != 0 or region.closer != size - 1:
                return None
            whole = merged
            continue
        spliced = splice(whole, route, merged)
        if spliced is None:
            return None
        whole = spliced
    return whole


def split_regions(
    reduce: Callable[[IrAst, str, Reducer], IrSelf],
    grammar: IrAst,
    text: str,
    reducer: Reducer,
    cores: int = AUTO,
) -> IrSelf | None:
    """Reduce ``text`` by dividing its bracketed runs; ``None`` = sequential.

    Every large run is cut into pieces that carry their own brackets, so a
    piece parses under the run's own rule at the cost of its own text. What
    remains — the document with each run shrunk to one piece — is parsed
    once, and each run's merged value replaces the piece standing for it.

    :param reduce: The reduce product, injected by the layer that owns it.
    :param grammar: The authored grammar.
    :param text: The document.
    :param reducer: The grammar's reduction policy.
    :param cores: 0 = auto, 1 = sequential, N = that many.
    :returns: The reduced value, or ``None`` to reduce sequentially.
    """
    workers = doc_workers(cores)
    if workers < 2 or len(text) < MIN_REGION:
        return None
    divided = choose(text, find(grammar, text), workers)
    if not divided:
        return None
    parts = _reduce_parts(Reduction(reduce, grammar, reducer, workers), text, divided)
    if parts is None:
        return None
    return _splice_all(divided, parts, len(text))
