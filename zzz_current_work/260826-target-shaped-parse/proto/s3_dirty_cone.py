"""Pin the dirty ancestor cone an alternate-derivation replay must redo.

Today an alternate derivation costs a whole second fold: `another_meaning`
flips one ambiguity point and calls `build` over the entire tree. The cone is
what makes that incremental — flipping a point cannot change the meaning of
anything that does not contain it, so a replay redoes the point and its
ancestors and REUSES every other completed handle's meaning.

Two properties are what make the cone usable, and both are checked here on
real ambiguous grammars rather than argued:

* **Well-formed.** The cone contains the flipped point and the root, and
  never reaches outside the forest under that root.
* **Worth it.** The cone is a strict subset of the reachable handles, so a
  replay really does less work than a whole-tree fold.

Soundness — that nothing outside the cone can change — is structural rather
than measured here: a handle that is not an ancestor of the flipped point does
not contain it, so the flip cannot be in its derivation. The witness reports
what each flip actually changes rather than asserting a change, because a flip
that changes tree shape without changing meaning is the "two derivations, one
meaning" case the engine deliberately does not call an ambiguity.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    MeaningBuilder,
    MeaningRun,
    ambiguity_points,
    dirty_cone,
    remembered,
    replayed,
)
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize


class Shape(NamedTuple):
    """One genuinely ambiguous grammar and an input it derives two ways."""

    name: str
    grammar: str
    text: str


SHAPES = (
    Shape("self-pair", 'root ::= s\ns ::= s s | "a"\n', "aaa"),
    Shape("adjacent-optionals", 'root ::= x y\nx ::= "a"?\ny ::= "a"?\n', "a"),
    Shape("adjacent-repeats", 'root ::= p p\np ::= "a"*\n', "aa"),
    Shape("nested-optionals", 'root ::= q\nq ::= r r\nr ::= "a"?\n', "a"),
    Shape("differing", 'root ::= e\ne ::= e e | "a" | "b"\n', "aba"),
)
"""Shapes the forest genuinely PACKS — a gap two nullable slots carve two ways,
and a self-referential production. Arm choices between separately-named rules
are sibling ROOTS rather than packed families (see `_sibling_roots`), so they
are not what a cone is about.

The last shape is the one whose flip genuinely CHANGES meaning — the case a
replay exists for. The others flip tree shape while every node still means the
same thing, which is the engine's "two derivations, one meaning"."""


def _kernel(shape: Shape) -> Kernel:
    """Run one shape's parse to a finished kernel."""
    ast = normalize(canonical_grammar(shape.grammar, GBNF_FLAVOUR))
    kernel = Kernel(compile_tables(ast, tier_for(len(shape.text))), shape.text, True)
    kernel = kernel.run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError(f"{shape.name}: no parse")
    return kernel


def _reachable_handles(kernel: Kernel, root: int) -> set[int]:
    """Every handle the forest walk reaches from ``root``."""
    bits, mask = kernel.tables.packing.bits, kernel.tables.packing.mask
    codes, links = kernel.tables.codes, kernel.st.links
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
        for pitem, pend, child in bucket:
            stack.append((pitem << bits) | pend)
            if isinstance(child, int) and not isinstance(child, bool):
                stack.append(((child >> bits) << bits) | (child & mask))
    return seen


def _subtree_text(node: object) -> str:
    """All consumed characters under one derivation node, in source order."""
    parts: list[str] = []
    stack: list[object] = [node]
    while stack:
        item = stack.pop()
        if isinstance(item, ParseTree):
            stack.extend(reversed(item.kids))
        else:
            parts.append(str(item))
    return "".join(parts)


def _meanings(tree: ParseTree) -> dict[tuple[str, str], int]:
    """A stand-in per-node meaning: (symbol, consumed text) → how many times.

    Deliberately NOT node identity — the point is to compare what two
    derivations MEAN at each place, and two derivations build two objects for
    the same meaning. Symbol plus consumed text is what a fold would agree on.
    """
    counts: dict[tuple[str, str], int] = {}
    stack: list[ParseTree] = [tree]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        key = (str(node.symbol), _subtree_text(node))
        counts[key] = counts.get(key, 0) + 1
        stack.extend(kid for kid in node.kids if isinstance(kid, ParseTree))
    return counts


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s3 dirty cone: {claim}")


def _exercise(shape: Shape) -> None:
    """The cone contains the flip and the root, and is a strict subset."""
    kernel = _kernel(shape)
    root = accept_handle(kernel)
    points = ambiguity_points(kernel, root)
    _check(f"{shape.name} is not ambiguous after all", bool(points))

    reachable = _reachable_handles(kernel, root)
    flipped = points[0]
    cone = dirty_cone(kernel, root, flipped)

    _check(f"{shape.name}: the cone omits the flipped point", flipped in cone)
    _check(f"{shape.name}: the cone omits the root", root in cone)
    _check(
        f"{shape.name}: the cone reaches outside the forest",
        cone <= reachable,
    )
    _check(
        f"{shape.name}: the cone is everything — a replay would save nothing",
        len(cone) < len(reachable),
    )
    print(
        shape.name,
        f"points={len(points)}",
        f"reachable={len(reachable)}",
        f"cone={len(cone)}",
        f"reused={len(reachable) - len(cone)}",
        sep="\t",
    )


def the_flip_is_observable_or_not(shape: Shape) -> None:
    """Report what the flip actually changes, and assert only what is provable.

    Deliberately NOT asserting that a flip changes something. For
    `s ::= s s | "a"` over "aaa" the two groupings differ in tree SHAPE while
    every node still means the same thing — which is exactly the "two
    derivations, one meaning" case the engine refuses to call an ambiguity.
    A witness that demanded a change would be pinning the wrong contract.

    What IS asserted: both derivations build, and neither loses nodes the
    other has without the meaning multiset saying so. The cone's soundness —
    that nothing outside it can change — is structural: a handle that is not
    an ancestor of the flipped point does not contain it, so the flip is not
    in its derivation. Confirming that empirically needs a handle→node
    correspondence `FastTree` does not hand back, so this reports rather than
    claims it.
    """
    kernel = _kernel(shape)
    root = accept_handle(kernel)
    flipped = ambiguity_points(kernel, root)[0]

    first = FastTree(kernel, {}).build(root)
    other = FastTree(kernel, {flipped: 1}).build(root)
    if not isinstance(first, ParseTree) or not isinstance(other, ParseTree):
        raise AssertionError(f"{shape.name}: a derivation did not build")

    before, after = _meanings(first), _meanings(other)
    changed = {
        key for key in before | after.keys() if before.get(key) != after.get(key)
    }
    _check(
        f"{shape.name}: the flipped derivation consumed different text",
        _subtree_text(first) == _subtree_text(other) == shape.text,
    )
    verdict = "same meaning (not an ambiguity)" if not changed else "differs"
    print(
        f"{shape.name} flip",
        f"nodes={len(before)}",
        f"changed={len(changed)}",
        verdict,
        sep="\t",
    )


class _CountingFold:
    """A fold that records what each node means and counts what it folded."""

    def __init__(self) -> None:
        self.folded = 0

    def __call__(self, tree: ParseTree, results: dict[int, object]) -> object:
        """Fold every node not already seeded, recording each node's meaning."""
        stack: list[ParseTree] = [tree]
        order: list[ParseTree] = []
        seen: set[int] = set()
        while stack:
            node = stack.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            order.append(node)
            stack.extend(kid for kid in node.kids if isinstance(kid, ParseTree))
        for node in reversed(order):
            if id(node) in results:
                continue  # seeded from an earlier derivation — reuse it
            self.folded += 1
            results[id(node)] = (str(node.symbol), _subtree_text(node))
        return results[id(tree)]

    def build(self, tree: ParseTree) -> object:
        """Fold a tree with a fresh value memo."""
        return self(tree, {})


def the_replay_reuses_and_agrees(shape: Shape) -> None:
    """A replay folds only the cone and agrees with a full refold.

    Two claims, and the second is what makes the first safe: the incremental
    answer must be the SAME answer, or the saving is a bug.
    """
    kernel = _kernel(shape)
    root = accept_handle(kernel)
    flipped = ambiguity_points(kernel, root)[0]

    first_tree = FastTree(kernel, {}).build(root)
    if not isinstance(first_tree, ParseTree):
        raise AssertionError(f"{shape.name}: the default derivation did not build")
    first = _CountingFold()
    remembered_pair = remembered(
        MeaningRun(kernel, root, MeaningBuilder(first.build, first)), first_tree
    )
    _base, memo = remembered_pair

    incremental = _CountingFold()
    reused = replayed(
        MeaningRun(kernel, root, MeaningBuilder(incremental.build, incremental)),
        flipped,
        1,
        memo,
    )

    scratch = _CountingFold()
    fresh = FastTree(kernel, {flipped: 1}).build(root)
    if not isinstance(fresh, ParseTree):
        raise AssertionError(f"{shape.name}: the alternate did not build")
    whole = scratch(fresh, {})

    _check(
        f"{shape.name}: the replay disagreed with a full refold",
        reused is not None and reused.value == whole,
    )
    _check(
        f"{shape.name}: the replay folded as much as a full refold",
        incremental.folded < scratch.folded,
    )
    print(
        f"{shape.name} replay",
        f"default={first.folded}",
        f"refold={scratch.folded}",
        f"replay={incremental.folded}",
        "same answer",
        sep="\t",
    )


def main() -> None:
    """Run every shape; any failure raises."""
    for shape in SHAPES:
        _exercise(shape)
    for shape in SHAPES:
        the_flip_is_observable_or_not(shape)
    for shape in SHAPES:
        the_replay_reuses_and_agrees(shape)
    print("s3 dirty cone\tPASS\tcone contains the flip and root, strictly smaller")


if __name__ == "__main__":
    main()
