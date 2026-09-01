"""Product-driven ParseTree completion and its source-position machinery.

This is the tree-engine half of the product ABI.  It executes the same
:class:`Construction` records the predictive compiler bakes, while retaining
the Earley tree route's transparent-node walk and exact span derivation.

Completion presence is explicit.  A completed value may itself be Python
``None``; only :data:`EMPTY_RESULT` means that a recognition-only or empty
pass-through node produced no value.  That distinction is also what lets a
delegated :class:`PayloadLeaf` carry a real ``None`` without disappearing.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrLiteral, IrSpan
from lexic.parsing.caches import memo
from lexic.parsing.earley.kernel.forest.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel.tables.records import (
    ORIGIN_BITS,
    RUN_STR,
    ParserTables,
)
from lexic.parsing.earley.lexruns import collapse_runs, unit_leaves
from lexic.parsing.product.construction import (
    Construction,
    ConstructionTables,
    ProductValue,
)
from lexic.parsing.product.records import (
    CaptureMode,
    PassOp,
    RuleProduct,
    construction_of,
)

__all__ = [
    "Completed",
    "CompletionResult",
    "EMPTY_RESULT",
    "EmptyResult",
    "ProductExecutor",
    "ResultMemo",
    "collapsed_product_tables",
    "complete_product",
    "run_ok",
    "slot_span",
    "subtree_text",
    "tree_offsets",
]


class Completed[Carry](NamedTuple):
    """One present completed value, including a present Python ``None``."""

    value: Carry


class EmptyResult(NamedTuple):
    """A node completed without a value for a parent to capture."""


EMPTY_RESULT = EmptyResult()
"""The sole absence marker in a product tree completion."""

type CompletionResult[Carry] = Completed[Carry] | EmptyResult
type ResultMemo[Carry] = dict[int, CompletionResult[Carry]]


class ProductExecutor[Carry]:
    """One bound product's fresh and memo-seeded ParseTree entry points."""

    __slots__ = ("rules", "tables", "wants_spans")

    def __init__(
        self,
        rules: Mapping[str, RuleProduct[Carry]],
        tables: ConstructionTables[Carry],
    ) -> None:
        """:param rules: Authored rule products; :param tables: their operands."""
        self.rules = rules
        self.tables = tables
        self.wants_spans = _wants_spans(rules)

    def build(self, root: ParseTree) -> Carry:
        """Complete a derivation with a fresh result memo."""
        return complete_product(
            root, self.rules, self.tables, wants_spans=self.wants_spans
        )

    def replay(self, root: ParseTree, results: ResultMemo[Carry]) -> Carry:
        """Complete a derivation while reusing and extending ``results``."""
        return complete_product(
            root,
            self.rules,
            self.tables,
            results,
            wants_spans=self.wants_spans,
        )

type Offsets = tuple[dict[int, int], dict[int, int]]
"""``(start by node id, consumed length by node id)`` for one parse tree."""

_NO_OFFSETS: Offsets = ({}, {})


def subtree_text[Carry](node: ParseTree | IrLiteral | PayloadLeaf[Carry]) -> str:
    """Return all consumed text below ``node`` in source order."""
    parts: list[str] = []
    stack: list[ParseTree | IrLiteral | PayloadLeaf[Carry]] = [node]
    while stack:
        kid = stack.pop()
        if isinstance(kid, ParseTree):
            stack.extend(reversed(kid.kids))
        elif isinstance(kid, PayloadLeaf):
            parts.append(kid.text)
        else:
            parts.append(str(kid))
    return "".join(parts)


def _leaf_len[Carry](kid: IrLiteral | PayloadLeaf[Carry]) -> int:
    """Return the number of characters a leaf consumed."""
    return len(kid.text) if isinstance(kid, PayloadLeaf) else len(str(kid))


def _kid_size[Carry](
    kid: ParseTree | IrLiteral | PayloadLeaf[Carry], sizes: dict[int, int]
) -> int:
    """Return a kid's consumed size, using the completed subtree pre-pass."""
    return sizes[id(kid)] if isinstance(kid, ParseTree) else _leaf_len(kid)


def tree_offsets[Carry](root: ParseTree) -> Offsets:
    """Derive every tree node's source start and consumed size once."""
    starts: dict[int, int] = {}
    sizes: dict[int, int] = {}
    at = 0
    stack: list[tuple[ParseTree | IrLiteral | PayloadLeaf[Carry], bool]] = [
        (root, False)
    ]
    while stack:
        node, closing = stack.pop()
        if isinstance(node, ParseTree):
            if closing:
                sizes.setdefault(id(node), at - starts[id(node)])
            else:
                starts.setdefault(id(node), at)
                stack.append((node, True))
                stack.extend((kid, False) for kid in reversed(node.kids))
        else:
            at += _leaf_len(node)
    return starts, sizes


def slot_span[Carry](
    node: ParseTree,
    kids: Sequence[ParseTree | IrLiteral | PayloadLeaf[Carry]],
    item: int,
    offsets: Offsets,
) -> IrSpan:
    """Return the half-open source span of ``kids[item]`` in its parent."""
    starts, sizes = offsets
    at = starts[id(node)]
    for kid in kids[:item]:
        at += _kid_size(kid, sizes)
    return IrSpan(at, at + _kid_size(kids[item], sizes))


def complete_product[Carry](
    root: ParseTree,
    rules: Mapping[str, RuleProduct[Carry]],
    tables: ConstructionTables[Carry],
    results: ResultMemo[Carry] | None = None,
    *,
    wants_spans: bool | None = None,
) -> Carry:
    """Complete one ParseTree through the product's authored operations.

    ``results`` is both seeded and filled.  A seeded node is never constructed
    again, which is the value-replay contract used by ambiguity checking.
    """
    results = {} if results is None else results
    folded: set[int] = set(results)
    wants_spans = _wants_spans(rules) if wants_spans is None else wants_spans
    offsets = tree_offsets(root) if wants_spans else _NO_OFFSETS
    stack: list[tuple[ParseTree, bool]] = [(root, False)]
    while stack:
        node, expanded = stack.pop()
        node_id = id(node)
        if not expanded:
            stack.append((node, True))
            for kid in node.kids:
                if isinstance(kid, ParseTree) and id(kid) not in folded:
                    stack.append((kid, False))
            continue
        if node_id in folded:
            continue
        folded.add(node_id)
        _complete_node(node, rules, tables, results, offsets)
    root_result = results.get(id(root), EMPTY_RESULT)
    if isinstance(root_result, EmptyResult):
        root_result = _first_product_under(root, results)
    if isinstance(root_result, EmptyResult):
        raise UnsupportedConstructError(
            f"product: start rule {root.symbol!s} completed without a value"
        )
    return root_result.value


def _wants_spans[Carry](rules: Mapping[str, RuleProduct[Carry]]) -> bool:
    """Return whether any product capture requests an extent."""
    return any(
        spec.mode == CaptureMode.EXTENT
        for product in rules.values()
        for spec in product.captures
    )


def _complete_node[Carry](
    node: ParseTree,
    rules: Mapping[str, RuleProduct[Carry]],
    tables: ConstructionTables[Carry],
    results: ResultMemo[Carry],
    offsets: Offsets,
) -> None:
    """Complete one authored rule; transparent nodes write no memo entry."""
    product = rules.get(str(node.symbol))
    if product is None:
        return
    if isinstance(product.completion, PassOp):
        results[id(node)] = _passed_value(node, product, product.completion, results)
        return
    construction = construction_of(product, tables)
    if construction is None:
        raise UnsupportedConstructError(
            f"product: rule {node.symbol!s} has no construction"
        )
    if construction.matched:
        results[id(node)] = Completed(
            construction.call(**{construction.matched: subtree_text(node)})
        )
        return
    results[id(node)] = Completed(
        _complete_record(node, product, construction, results, offsets)
    )


def _passed_value[Carry](
    node: ParseTree,
    product: RuleProduct[Carry],
    completion: PassOp,
    results: ResultMemo[Carry],
) -> CompletionResult[Carry]:
    """Return the explicitly present or empty pass-through result."""
    source = completion.source
    if source >= len(product.captures):
        raise UnsupportedConstructError(
            f"product: {node.symbol!s}: pass source {source} has no capture"
        )
    spec = product.captures[source]
    if spec.mode != CaptureMode.ONE:
        raise UnsupportedConstructError(
            f"product: {node.symbol!s}: pass source {source} is not one value"
        )
    if not node.kids:
        return EMPTY_RESULT
    if spec.slot >= len(node.kids):
        raise UnsupportedConstructError(
            f"product: {node.symbol!s}: pass item {spec.slot} is out of range"
        )
    models = _product_models_at(node.kids[spec.slot], results)
    return Completed(models[0]) if models else EMPTY_RESULT


def _complete_record[Carry](
    node: ParseTree,
    product: RuleProduct[Carry],
    construction: Construction[Carry],
    results: ResultMemo[Carry],
    offsets: Offsets,
) -> Carry:
    """Capture one sequence node and invoke its resolved construction."""
    kids = node.kids
    if len(kids) != product.n_items:
        if kids:
            raise UnsupportedConstructError(
                f"product: {node.symbol!s}: {len(kids)} kids do not match "
                f"{product.n_items} items (nor the empty arm)"
            )
        return construction.call()
    if len(product.captures) != len(construction.names):
        raise UnsupportedConstructError(
            f"product: {node.symbol!s}: {len(product.captures)} captures do not "
            f"match {len(construction.names)} construction names"
        )
    kwargs: dict[str, ProductValue[Carry]] = {}
    for at, (spec, name) in enumerate(
        zip(product.captures, construction.names, strict=True)
    ):
        present, value = _captured(
            node,
            spec.slot,
            spec.mode,
            at in construction.optional,
            results,
            offsets,
        )
        if present:
            kwargs[name] = value
    return construction.call(**kwargs)


def _captured[Carry](
    node: ParseTree,
    item: int,
    mode: int,
    optional: bool,
    results: ResultMemo[Carry],
    offsets: Offsets,
) -> tuple[bool, ProductValue[Carry]]:
    """Read one capture, looking through transparent normalisation nodes."""
    kids = node.kids
    if item >= len(kids):
        raise UnsupportedConstructError(
            f"product: {node.symbol!s}: capture item {item} is out of range"
        )
    kid = kids[item]
    if mode == CaptureMode.TEXT:
        text = subtree_text(kid)
        return (not optional or bool(text), text)
    if mode == CaptureMode.EXTENT:
        return True, slot_span(node, kids, item, offsets)
    models = _product_models_at(kid, results)
    if mode == CaptureMode.MANY:
        return True, models
    if mode == CaptureMode.ONE:
        return (bool(models) or not optional, models[0] if models else None)
    raise UnsupportedConstructError(
        f"product: {node.symbol!s}: capture mode {mode} builds no model field"
    )


def _product_models_at[Carry](
    kid: ParseTree | IrLiteral | PayloadLeaf[Carry],
    results: ResultMemo[Carry],
) -> list[Carry]:
    """Return present values at or below one capture slot."""
    result = results.get(id(kid), EMPTY_RESULT)
    if isinstance(result, Completed):
        return [result.value]
    out: list[Carry] = []
    stack: list[ParseTree | IrLiteral | PayloadLeaf[Carry]] = [kid]
    while stack:
        current = stack.pop()
        if isinstance(current, PayloadLeaf):
            out.append(current.payload)
        elif isinstance(current, ParseTree):
            result = results.get(id(current), EMPTY_RESULT)
            if isinstance(result, Completed):
                out.append(result.value)
            else:
                stack.extend(reversed(current.kids))
    return out


def _first_product_under[Carry](
    node: ParseTree, results: ResultMemo[Carry]
) -> CompletionResult[Carry]:
    """Return the first present value below a transparent node."""
    for kid in node.kids:
        models = _product_models_at(kid, results)
        if models:
            return Completed(models[0])
    return EMPTY_RESULT


def run_ok(tables: ParserTables, unit_rid: int, rules: Collection[str]) -> bool:
    """Return whether a lexical run hides no product-bearing rule."""
    if unit_rid < 0:
        return True
    resolved = unit_leaves(tables, unit_rid)
    if resolved is None:
        return False
    leaf_rids, _has_bare = resolved
    names = tables.decode.rule_names
    return not any(names[rid] in rules for rid in leaf_rids)


_COLLAPSED: dict[
    tuple[int, int, int],
    tuple[Mapping[str, RuleProduct], IrAst, ParserTables],
] = memo({}, 0, 1)


def collapsed_product_tables(
    grammar: IrAst,
    rules: Mapping[str, RuleProduct],
    bits: int = ORIGIN_BITS,
) -> ParserTables:
    """Return product-safe run-collapsed Earley tables, identity memoised."""
    key = (id(rules), id(grammar), bits)
    entry = _COLLAPSED.get(key)
    if entry is not None and entry[0] is rules and entry[1] is grammar:
        return entry[2]
    tables = collapse_runs(
        grammar,
        lambda plain, unit_rid: RUN_STR if run_ok(plain, unit_rid, rules) else None,
        bits,
    )
    _COLLAPSED[key] = (rules, grammar, tables)
    return tables
