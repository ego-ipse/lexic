"""Pin value-once-per-node folding over shared forest subtrees.

`proto/shared_forest_refold.py` measured the defect: the fold walk's body ran
2, 2 and 1 times for the SAME two-slot sharing across three shapes, and a
transparent synthetic node repeated because it stores no result — so the count
was a traversal accident, neither per-node nor per-occurrence.

This runs the real `ModelFold` over the real Earley fallback and asserts the
contract instead: each shared node's value is computed exactly once, on every
shape, and the model the fold returns is unchanged.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.compile import canonical_grammar, compile_text
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.earley.engine import AmbiguityPolicy, EarleyParser, first_meaning
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.fold import ModelFold
from lexic.parsing.products import _model_product, earley_model
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.support.readout import accept_handle, accept_item
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize


class Shape(NamedTuple):
    """One grammar whose single derivation shares a subtree object.

    :ivar name: The shape's label.
    :ivar grammar: GBNF source whose derivation is a DAG.
    :ivar text: The input.
    :ivar shared: The rule whose derivation object is reached twice.
    """

    name: str
    grammar: str
    text: str
    shared: str


SHAPES = (
    Shape("duplicate-slot", 'root ::= a "x" a\na ::= "y"?\n', "x", "a"),
    Shape("pending-frame", 'root ::= a b\nb ::= a "z"\na ::= "y"?\n', "z", "a"),
    Shape(
        "sibling-memo",
        'root ::= b c\nb ::= a "u"\nc ::= a "w"\na ::= "y"?\n',
        "uw",
        "a",
    ),
)
"""Three of the plan's four §3 exit shapes, folded through the real product.
The fourth — the transparent synthetic — is exercised by
:func:`transparent_synthetic_folds_once` below, which needs the canonical
route where that node is genuinely shared."""


class _CountingFold[M](ModelFold[M]):
    """A fold that records how often each node's body actually ran."""

    __slots__ = ("counts",)

    def __init__(self, bodies: object) -> None:
        """Wrap an existing fold's authored bodies with a per-node counter."""
        super().__init__(bodies)  # type: ignore[arg-type]
        self.counts: dict[int, int] = {}

    def _fold_node(self, node: ParseTree, results: dict[int, object], offsets: object) -> None:  # type: ignore[override]
        """Count this node's body execution, then fold it normally."""
        self.counts[id(node)] = self.counts.get(id(node), 0) + 1
        super()._fold_node(node, results, offsets)  # type: ignore[arg-type]


def _slot_counts(root: ParseTree) -> dict[int, int]:
    """How many kid slots reference each subtree object, by identity."""
    counts: dict[int, int] = {}
    seen: set[int] = set()
    stack: list[ParseTree] = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                counts[id(kid)] = counts.get(id(kid), 0) + 1
                stack.append(kid)
    return counts


def _nodes_named(root: ParseTree, rule: str) -> set[int]:
    """Every distinct subtree object standing for ``rule``."""
    found: set[int] = set()
    seen: set[int] = set()
    stack: list[ParseTree] = [root]
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if str(node.symbol) == rule:
            found.add(id(node))
        stack.extend(kid for kid in node.kids if isinstance(kid, ParseTree))
    return found


def _exercise(shape: Shape) -> None:
    """Fold one shape through the Earley path and pin the execution counts."""
    compiled = compile_text(shape.grammar)
    counting: _CountingFold[object] = _CountingFold(compiled.fold.bodies)
    product = _model_product(
        compiled.codegen_grammar, counting, tier_for(len(shape.text))
    )
    model = earley_model(product.instance_grammar, shape.text, counting, product.tables)
    reference = compiled.parse(shape.text)
    if model != reference:
        raise AssertionError(f"{shape.name}: the guarded fold changed the model")

    # `earley_model` folds more than once — the ambiguity gate's `build` is
    # the fold itself. Count ONE apply over the same derivation instead.
    tree = _derivation(product, shape, counting)
    counting.counts.clear()
    counting.apply(tree)

    slots = _slot_counts(tree)
    shared = {node for node in _nodes_named(tree, shape.shared) if slots.get(node, 0) > 1}
    if not shared:
        raise AssertionError(f"{shape.name}: {shape.shared!r} is not shared here")
    counts = sorted(counting.counts.get(node, 0) for node in shared)
    if any(count != 1 for count in counts):
        raise AssertionError(
            f"{shape.name}: shared {shape.shared!r} folded {counts} times, not once each"
        )
    print(
        shape.name,
        f"shared={len(shared)}",
        f"slots={max(slots[node] for node in shared)}",
        "folds=1 each",
        sep="\t",
    )


def _derivation(product: object, shape: Shape, fold: ModelFold) -> ParseTree:
    """The derivation the counting fold ran over, rebuilt for inspection."""
    policy = AmbiguityPolicy(fold.apply, None)
    return first_meaning(
        EarleyParser(),
        product.instance_grammar,  # type: ignore[attr-defined]
        shape.text,
        product.tables,  # type: ignore[attr-defined]
        policy,
    )


def transparent_synthetic_folds_once() -> None:
    """The synthetic node that stored no result must not fold twice.

    It needs the canonical route rather than the codegen one: the codegen
    passes hoist the repetition into a rule that is no longer shared, while
    the canonical grammar keeps ``__rep_1`` reached from two slots — which is
    exactly the shape whose missing value-table entry made it repeat.
    """
    source = 'root ::= a "x" a\na ::= "y"?\n'
    ast = normalize(canonical_grammar(source, GBNF_FLAVOUR))
    kernel = Kernel(compile_tables(ast, tier_for(1)), "x", True).run()
    if accept_item(kernel) < 0:
        raise AssertionError("transparent-synthetic: no parse")
    tree = FastTree(kernel).build(accept_handle(kernel))
    if not isinstance(tree, ParseTree):
        raise AssertionError("transparent-synthetic: the fast path missed")

    counting: _CountingFold[object] = _CountingFold(compile_text(source).fold.bodies)
    counting.apply(tree)
    slots = _slot_counts(tree)
    parents = {node for node in _nodes_named(tree, "a") if slots.get(node, 0) > 1}
    if not parents:
        raise AssertionError("transparent-synthetic: its shared parent is not shared")
    synthetic = _nodes_named(tree, "__rep_1")
    if len(synthetic) != 1:
        raise AssertionError(
            f"transparent-synthetic: expected one '__rep_1', saw {len(synthetic)}"
        )
    counts = sorted(counting.counts.get(node, 0) for node in synthetic | parents)
    if any(count != 1 for count in counts):
        raise AssertionError(
            f"transparent-synthetic: '__rep_1'/'a' folded {counts} times, not once each"
        )
    print(
        "transparent-synthetic",
        f"shared_parent_slots={max(slots[node] for node in parents)}",
        "folds=1 each",
        "(it stores no result; the old guard re-expanded it with its parent)",
        sep="\t",
    )


def main() -> None:
    """Run every shape; any repeated fold body raises."""
    for shape in SHAPES:
        _exercise(shape)
    transparent_synthetic_folds_once()
    print(
        "s3 shared forest",
        "PASS",
        "value computed once per shared node on all four shapes",
        sep="\t",
    )


if __name__ == "__main__":
    main()
