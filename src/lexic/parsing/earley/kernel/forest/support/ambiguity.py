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

from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.readout import accept_items
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice

if TYPE_CHECKING:  # `kernel` is what hands us a finished parse to read
    from lexic.parsing.earley.kernel.loop.kernel import Kernel

__all__ = [
    "AmbiguityPolicy",
    "MeaningMemo",
    "Resolver",
    "ambiguity_points",
    "another_meaning",
    "dirty_cone",
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


class AmbiguityPolicy(NamedTuple):
    """How a span that means two things is settled, and by whom.

    ``build`` is what makes the question answerable at all: whether two
    derivations are a real ambiguity is a question about the VALUES they
    build. ``resolve`` is the caller's explicit opt-out from the default
    refusal.

    :ivar build: Turns a derivation into the value it means.
    :ivar resolve: Settles a span that means two things; ``None`` refuses it.
    """

    build: Callable[[ParseTree], object]
    resolve: Resolver | None = None


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


class MeaningMemo(NamedTuple):
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
    values: dict[int, object]


def remembered(
    kernel: Kernel, root: int, fold: Callable[[ParseTree, dict[int, object]], object]
) -> tuple[object, MeaningMemo] | None:
    """Build and fold the default derivation, keeping what each handle meant.

    :param kernel: The finished kernel.
    :param root: The packed accepting handle.
    :param fold: Folds a tree, recording every node's value in the map it is
        given.
    :returns: ``(value, memo)``, or ``None`` when the fast path misses.
    """
    tree = FastTree(kernel, {})
    built = tree.build(root)
    if not isinstance(built, ParseTree):
        return None
    values: dict[int, object] = {}
    return fold(built, values), MeaningMemo(dict(tree.memo), values)


def replayed(
    kernel: Kernel,
    root: int,
    flipped: int,
    fold: Callable[[ParseTree, dict[int, object]], object],
    memo: MeaningMemo,
) -> object | None:
    """One alternate derivation's value, recomputing only the dirty cone.

    The saving is the point: everything outside :func:`dirty_cone` keeps the
    subtree AND the value it already had, so an alternate costs the cone
    rather than the document. Seeding the build's memo is what makes the
    reused subtrees the same objects, so the seeded values still address them.

    The seeded value map is a fresh dict per call, so one alternate cannot
    observe or disturb another's evaluation.

    :param kernel: The finished kernel.
    :param root: The packed accepting handle.
    :param flipped: The ambiguity point taking a different family.
    :param fold: Folds a tree, seeded with the values it may reuse.
    :param memo: What the default derivation meant.
    :returns: The alternate's value, or ``None`` when it does not build.
    """
    cone = dirty_cone(kernel, root, flipped)
    keep = {handle: node for handle, node in memo.nodes.items() if handle not in cone}
    tree = FastTree(kernel, {flipped: 1})
    tree.memo.update(keep)
    built = tree.build(root)
    if not isinstance(built, ParseTree):
        return None
    seeded = {
        id(node): memo.values[id(node)]
        for node in keep.values()
        if id(node) in memo.values
    }
    return fold(built, seeded)


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


def another_meaning(
    kernel: Kernel,
    handle: int,
    build: Callable[[ParseTree], object],
    first: ParseTree,
) -> ParseTree | None:
    """The first other derivation of ``handle`` that builds a DIFFERENT value.

    Flips one ambiguity point at a time rather than trying every combination: a
    fold is compositional, so if no single alternative changes the value, no
    combination of them does. That is linear in ambiguity points, where
    enumerating derivations is exponential in them. On a cyclic chart (a unit
    cycle's same-span completions) a flipped point is consumed at its first
    visit — see :func:`~lexic.parsing.earley.kernel.tables.splits.leftmost_chain` —
    so the flip names the one-lap unroll and the walk terminates.

    Returns the differing derivation itself rather than a truth value, because
    a caller resolving the ambiguity needs the witness in hand, and "means two
    things" and "nothing built" are different answers a bare predicate would
    conflate.

    :param kernel: The finished kernel.
    :param handle: The packed accepting handle.
    :param build: Turns a derivation into the value it means.
    :param first: The derivation already in hand, to compare the rest against.
    :returns: A derivation whose value differs from ``first``'s, or ``None``
        when every derivation means the same thing — proven, not sampled.
    """
    base = build(first)
    for alternate in _sibling_roots(kernel, handle):
        other = FastTree(kernel, {}).build(alternate)
        if isinstance(other, ParseTree) and not same_value(base, build(other)):
            return other
    bits = kernel.tables.packing.bits
    for key in ambiguity_points(kernel, handle):
        bucket = kernel.st.links[key]
        # A SPLIT has a defined answer — the first slot owns the text — so it is
        # not an ambiguity and must not be refused or fallen back for. Only a
        # choice between different authored ARMS is a question the grammar left
        # open. Generated quantifier-helper arms share one choice identity.
        if not is_arm_choice(bucket, bits, kernel.tables.code_choice):
            continue
        for index in range(1, len(bucket)):
            other = FastTree(kernel, {key: index}).build(handle)
            if isinstance(other, ParseTree) and not same_value(base, build(other)):
                return other
    return None
