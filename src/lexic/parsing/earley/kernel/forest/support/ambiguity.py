"""Does this span mean more than one thing? — the forest's own answer.

Ambiguity is a property of the FOREST, and the forest already records it: a key
packing more than one family IS an ambiguity point (Scott 2008). So the question
is answered by a walk, not by enumerating derivations and hoping the interesting
one comes early.

What counts as an ambiguity is a question about VALUES, not about derivations. A
grammar routinely derives one text several ways without meaning anything by it —
an inline group carves a digit two ways and folds the same both times, and two
adjacent nullable slots split a gap two ways to the same end. Refusing those
refuses valid input for a difference no consumer can observe.

Shared by every consumer that must answer it — the island sub-parse, the reduce
path and the model completion — so that "two derivations, one meaning" is
decided once and the same way, whichever engine is asking.
"""

from __future__ import annotations

from collections.abc import Callable
from operator import ne
from typing import TYPE_CHECKING, NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.readout import accept_items
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice

if TYPE_CHECKING:  # `kernel` is what hands us a finished parse to read
    from lexic.parsing.earley.kernel.loop.kernel import Kernel

__all__ = [
    "BuiltMeaning",
    "MeaningBuilder",
    "MeaningMemo",
    "MeaningPair",
    "MeaningRun",
    "Resolver",
    "ambiguity_points",
    "chosen_meaning",
    "dirty_cone",
    "different_meaning",
    "remembered",
    "replayed",
    "same_value",
]

type Resolver = Callable[[ParseTree, ParseTree], ParseTree]
"""A caller's deterministic answer to an ambiguity — the opt-out from refusal.

Given the derivation in hand and one that means something else, returns the
derivation to keep. How it chooses is the caller's concern; the engine's only
requirement is that it is deterministic, so both engines given the same pair
answer the same way. ``lambda first, other: first`` is the degenerate
take-the-first resolver.
"""


def ambiguity_points(kernel: Kernel, root: int) -> list[int]:
    """Every key reachable from ``root`` that packs more than one family.

    :param kernel: The finished kernel whose links to walk.
    :param root: The packed accepting handle.
    :returns: The ambiguity points, ascending. Empty means the span derives
        exactly one way — proven, not sampled.
    """
    bits, mask = kernel.tables.packing.bits, kernel.tables.packing.mask
    codes, links = kernel.tables.codes, kernel.st.links
    found: set[int] = set()
    seen: set[int] = set()
    stack = [root]
    while stack:
        handle = stack.pop()
        if handle in seen:
            continue
        seen.add(handle)
        item = handle >> bits
        if (item >> bits) == codes.arm_base[codes.code_arm[item >> bits]]:
            continue
        bucket = links.get(handle)
        if bucket is None:
            continue
        if len(bucket) > 1:
            found.add(handle)
        stack.extend(_reachable(bucket, bits, mask))
    return sorted(found)


def _reachable(bucket: list, bits: int, mask: int) -> list[int]:
    """The handles a packed family bucket leads to — predecessors and kids.

    Every family, not merely the first: a walk down one spine finds only the
    ambiguity points ON that spine.
    """
    out: list[int] = []
    for pitem, pend, child in bucket:
        out.append((pitem << bits) | pend)
        if isinstance(child, int) and not isinstance(child, bool):
            out.append(((child >> bits) << bits) | (child & mask))
    return out


def dirty_cone(kernel: Kernel, root: int, flipped: int) -> frozenset[int]:
    """Every handle whose meaning can change when ``flipped`` chooses again.

    Flipping one ambiguity point cannot change a value that does not contain
    it, so a replay only has to redo ``flipped`` and the handles it is nested
    inside — its ancestor cone up to ``root``. Every other completed handle's
    meaning is exactly what it already was, which is what makes an alternate
    derivation reusable rather than a second whole-document fold.

    Computed by walking the link table forward once to learn who reaches whom,
    then reading that relation backwards from ``flipped``. The forward walk is
    the same reachability :func:`ambiguity_points` uses, so the two agree on
    what "inside" means.

    :param kernel: The finished kernel whose links to walk.
    :param root: The packed accepting handle the meaning is wanted for.
    :param flipped: The ambiguity point choosing a different family.
    :returns: The handles to recompute — always containing ``flipped``, and
        ``root`` whenever ``flipped`` is reachable from it. Empty when
        ``flipped`` is not under ``root`` at all, which is the honest answer
        that nothing about this root changes.
    """
    parents = _parent_edges(kernel, root)
    if flipped not in parents and flipped != root:
        return frozenset()
    cone = {flipped}
    frontier = [flipped]
    while frontier:
        for parent in parents.get(frontier.pop(), ()):
            if parent not in cone:
                cone.add(parent)
                frontier.append(parent)
    return frozenset(cone)


class MeaningBuilder[Value, NodeValue](NamedTuple):
    """Fresh and seeded entry points for one compositional interpretation."""

    build: Callable[[ParseTree], Value]
    replay: Callable[[ParseTree, dict[int, NodeValue]], Value]


class BuiltMeaning[Value](NamedTuple):
    """A derivation paired with the value already built from it."""

    tree: ParseTree
    value: Value


class MeaningPair[Value](NamedTuple):
    """The baseline and, when present, first different built meaning."""

    first: BuiltMeaning[Value]
    witness: BuiltMeaning[Value] | None


class MeaningRun[Value, NodeValue](NamedTuple):
    """One span's interpretation attempt — the parse, the handle, the builder.

    The three that are fixed for every alternate of one span. Built ONCE, and
    only after an arm choice has been found, so a span that derives one way
    allocates nothing for a search it never runs.

    :ivar kernel: The finished kernel.
    :ivar root: The packed accepting handle.
    :ivar builder: The interpretation's fresh and seeded entry points.
    """

    kernel: Kernel
    root: int
    builder: MeaningBuilder[Value, NodeValue]


class MeaningMemo[NodeValue](NamedTuple):
    """What the default derivation meant, kept so an alternate can reuse it.

    Values only. No builder handle, no mutation log, no engine state — an
    alternate derivation is evaluated in its own isolation, and anything
    mutable retained here would leak one derivation's construction into
    another's.

    :ivar nodes: Packed handle → the subtree the default build produced for
        it. Seeding a later build with these makes the unchanged parts the
        SAME objects, which is what keeps :attr:`values` addressable.
    :ivar values: ``id(node)`` → the value that node folded to.
    """

    nodes: dict[int, ParseTree]
    values: dict[int, NodeValue]


def remembered[Value, NodeValue](
    run: MeaningRun[Value, NodeValue], first: ParseTree
) -> tuple[BuiltMeaning[Value], MeaningMemo[NodeValue]]:
    """Build and fold the default derivation, keeping what each handle meant.

    :param run: The span's kernel, handle and interpretation.
    :param first: The derivation already in hand, used on a fast-tree miss.
    :returns: The already-built baseline and its reusable node memo.
    """
    tree = FastTree(run.kernel, {})
    built = tree.build(run.root)
    if not isinstance(built, ParseTree):
        return BuiltMeaning(first, run.builder.build(first)), MeaningMemo({}, {})
    values: dict[int, NodeValue] = {}
    value = run.builder.replay(built, values)
    return BuiltMeaning(first, value), MeaningMemo(dict(tree.memo), values)


def replayed[Value, NodeValue](
    run: MeaningRun[Value, NodeValue],
    point: int,
    family: int,
    memo: MeaningMemo[NodeValue],
) -> BuiltMeaning[Value] | None:
    """One alternate derivation's value, recomputing only the dirty cone.

    The saving is the point: everything outside :func:`dirty_cone` keeps the
    subtree AND the value it already had, so an alternate costs the cone
    rather than the document. Seeding the build's memo is what makes the
    reused subtrees the same objects, so the seeded values still address them.

    The seeded value map is a fresh dict per call, so one alternate cannot
    observe or disturb another's evaluation.

    :param run: The span's kernel, handle and interpretation.
    :param point: The ambiguity point taking a different family.
    :param family: The packed-family index selected at ``point``.
    :param memo: What the default derivation meant.
    :returns: The alternate's value, or ``None`` when it does not build.
    """
    cone = dirty_cone(run.kernel, run.root, point)
    keep = {handle: node for handle, node in memo.nodes.items() if handle not in cone}
    tree = FastTree(run.kernel, {point: family})
    tree.memo.update(keep)
    built = tree.build(run.root)
    if not isinstance(built, ParseTree):
        return None
    seeded = {
        id(node): memo.values[id(node)]
        for node in keep.values()
        if id(node) in memo.values
    }
    return BuiltMeaning(built, run.builder.replay(built, seeded))


def _parent_edges(kernel: Kernel, root: int) -> dict[int, list[int]]:
    """Reverse reachability under ``root`` — handle → the handles containing it."""
    bits, mask = kernel.tables.packing.bits, kernel.tables.packing.mask
    codes, links = kernel.tables.codes, kernel.st.links
    parents: dict[int, list[int]] = {}
    seen: set[int] = set()
    stack = [root]
    while stack:
        handle = stack.pop()
        if handle in seen:
            continue
        seen.add(handle)
        item = handle >> bits
        if (item >> bits) == codes.arm_base[codes.code_arm[item >> bits]]:
            continue
        bucket = links.get(handle)
        if bucket is None:
            continue
        for reached in _reachable(bucket, bits, mask):
            parents.setdefault(reached, []).append(handle)
            stack.append(reached)
    return parents


def _sibling_roots(kernel: Kernel, handle: int) -> list[int]:
    """The OTHER whole-input completions of the start symbol, if any.

    A many-production root is not an ambiguity point in the link table: the
    sibling productions live in other accepting ITEMS, which a walk down from
    one of them never reaches. `s ::= s s | "a"` over `"aaa"` is exactly that
    shape, and reading only the links calls it unambiguous.
    """
    bits, mask = kernel.tables.packing.bits, kernel.tables.packing.mask
    if (handle & mask) != len(kernel.text):
        return []
    return [
        (item << bits) | len(kernel.text)
        for item in accept_items(kernel)
        if ((item << bits) | len(kernel.text)) != handle
    ]


def same_value(one: object, other: object) -> bool:
    """Do two built values differ in anything a consumer could observe?

    Type-aware and structural, because bare ``==`` answers the wrong question in
    both directions. It calls two values equal when one is ``IrStr("a")`` and the
    other bare ``"a"`` — the IR wraps ``str`` and ``int``, so a leaf and its text
    compare equal while a consumer reading the field sees two different things.
    And it calls them different for a float NaN, which is never equal to itself,
    or for any authored class that never defined ``__eq__``, since two
    derivations always build two objects.

    A type that declined to define equality has declined to answer, and the
    conservative reading of "cannot tell" is no observable difference, hence no
    refusal.
    """
    if type(one) is not type(other):
        return False
    if isinstance(one, (tuple, list)) and isinstance(other, (tuple, list)):
        return len(one) == len(other) and all(map(same_value, one, other))
    if isinstance(one, dict) and isinstance(other, dict):
        return one.keys() == other.keys() and all(
            same_value(one[k], other[k]) for k in one
        )
    if type(one).__eq__ is object.__eq__:
        return True
    # `x != x` is true only of a value that is not equal to itself — NaN.
    # Spelled through `operator` because it is a deliberate self-comparison.
    return bool(one == other) or (ne(one, one) and ne(other, other))


def different_meaning[Value, NodeValue](
    kernel: Kernel,
    handle: int,
    builder: MeaningBuilder[Value, NodeValue],
    first: ParseTree,
) -> MeaningPair[Value]:
    """Build the baseline once and find the first differently valued derivation.

    Flips one ambiguity point at a time rather than trying every combination: a
    fold is compositional, so if no single alternative changes the value, no
    combination of them does. That is linear in ambiguity points, where
    enumerating derivations is exponential in them. On a cyclic chart (a unit
    cycle's same-span completions) a flipped point is consumed at its first
    visit — see :func:`~lexic.parsing.earley.kernel.tables.splits.leftmost_chain` —
    so the flip names the one-lap unroll and the walk terminates.

    The returned pair retains both values.  A resolver choosing either tree
    therefore does not construct its chosen result again.

    :param kernel: The finished kernel.
    :param handle: The packed accepting handle.
    :param builder: Fresh and memo-seeded product execution.
    :param first: The derivation already in hand, to compare the rest against.
    :returns: The already-built baseline and optional differing witness.
    """
    siblings = _sibling_roots(kernel, handle)
    choices = _arm_choices(kernel, handle)
    if not choices:
        base = BuiltMeaning(first, builder.build(first))
        return MeaningPair(base, _sibling_witness(kernel, siblings, base, builder))
    # Only here, where an alternate can exist at all, does the span's fixed
    # trio become worth naming; a one-derivation parse never reaches it.
    run = MeaningRun(kernel, handle, builder)
    base, memo = remembered(run, first)
    witness = _sibling_witness(kernel, siblings, base, builder)
    if witness is not None:
        return MeaningPair(base, witness)
    return MeaningPair(base, _flipped_witness(run, choices, base, memo))


def _flipped_witness[Value, NodeValue](
    run: MeaningRun[Value, NodeValue],
    choices: list[int],
    base: BuiltMeaning[Value],
    memo: MeaningMemo[NodeValue],
) -> BuiltMeaning[Value] | None:
    """The first single flip that means something other than ``base``.

    Nested and lazy: the alternates are visited one at a time and the walk
    stops at the first difference, so a span whose first alternate settles the
    question never enumerates the rest.
    """
    for point in choices:
        for family in range(1, len(run.kernel.st.links[point])):
            built = replayed(run, point, family, memo)
            if built is not None and not same_value(base.value, built.value):
                return built
    return None


def _arm_choices(kernel: Kernel, handle: int) -> list[int]:
    """The ambiguity points under ``handle`` that are genuine arm choices.

    A SPLIT — one production carved two ways — has a defined answer and is
    never a candidate; only a choice between arms can mean two things.
    """
    bits = kernel.tables.packing.bits
    return [
        key
        for key in ambiguity_points(kernel, handle)
        if is_arm_choice(kernel.st.links[key], bits, kernel.tables.code_choice)
    ]


def _sibling_witness[Value, NodeValue](
    kernel: Kernel,
    siblings: list[int],
    base: BuiltMeaning[Value],
    builder: MeaningBuilder[Value, NodeValue],
) -> BuiltMeaning[Value] | None:
    """The first sibling root that means something other than ``base``."""
    for alternate in siblings:
        other = FastTree(kernel, {}).build(alternate)
        if not isinstance(other, ParseTree):
            continue
        built = BuiltMeaning(other, builder.build(other))
        if not same_value(base.value, built.value):
            return built
    return None


def chosen_meaning[Value, NodeValue](
    pair: MeaningPair[Value],
    builder: MeaningBuilder[Value, NodeValue],
    resolve: Resolver | None,
) -> Value:
    """The value a possibly-ambiguous pair settles to, built at most once.

    Shared by every consumer of :func:`different_meaning` that wants the
    VALUE, so the refusal and the resolver contract cannot differ between the
    routes. A resolver returning either derivation it was offered gets the
    value already built from it; only one returning a third tree pays a build.

    :param pair: What :func:`different_meaning` found for the span.
    :param builder: The same interpretation the pair was built through.
    :param resolve: The caller's resolver, or ``None`` to refuse.
    :returns: The chosen meaning's value.
    :raises UnsupportedConstructError: When the span means two things and no
        resolver was supplied.
    """
    witness = pair.witness
    if witness is None:
        return pair.first.value
    if resolve is None:
        raise UnsupportedConstructError(
            "parsing: ambiguous input — two derivations that mean different "
            "things; supply a resolver to choose between them"
        )
    chosen = resolve(pair.first.tree, witness.tree)
    if chosen is pair.first.tree:
        return pair.first.value
    if chosen is witness.tree:
        return witness.value
    return builder.build(chosen)
