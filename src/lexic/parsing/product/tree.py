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
from types import MappingProxyType
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
from lexic.parsing.product.abi.construction import Construction, ProductValue
from lexic.parsing.product.abi.records import CaptureMode
from lexic.parsing.product.routines import CaptureRoutine, RuleRoutine

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
    """One bound product's fresh and memo-seeded ParseTree entry points.

    It completes through :class:`~lexic.parsing.product.routines.RuleRoutine`\\
    s, which are the verified program read back — so the derivation runs the
    ranges the verifier bounded rather than a second reading of the authored
    records beside them.

    The routine map is COPIED and private. It is the container every completion
    reads, so it stays a plain dict for the lookup cost; copying is what makes
    that dict unreachable from any caller, so the read-only view a binding
    publishes cannot be worked around through the executor, and a worker's
    executor owns its own container rather than sharing one owner's refcount.
    """

    __slots__ = ("_routines", "wants_spans")

    def __init__(self, routines: Mapping[str, RuleRoutine[Carry]]) -> None:
        """:param routines: Rule name → its verified completion routine."""
        self._routines = dict(routines)
        self.wants_spans = _wants_spans(self._routines)

    @property
    def routines(self) -> Mapping[str, RuleRoutine[Carry]]:
        """A read-only view of what this executor completes through.

        The container itself stays private because it is the hot reader's, and
        a caller holding it could re-aim the parse after verification. Reading
        WHAT it holds is not that, so the question is answerable without one.
        """
        return MappingProxyType(self._routines)

    def build(self, root: ParseTree) -> Carry:
        """Complete a whole derivation, where producing no value is an error."""
        return complete_product(root, self._routines, wants_spans=self.wants_spans)

    def replay(self, root: ParseTree, results: ResultMemo[Carry]) -> Carry:
        """Complete a derivation while reusing and extending ``results``."""
        return complete_product(
            root, self._routines, results, wants_spans=self.wants_spans
        )

    def splice(self, root: ParseTree) -> CompletionResult[Carry]:
        """Complete ONE occurrence, which may legitimately produce no value.

        The document-root question and the occurrence question have different
        answers, which is why this is not :meth:`build` with a flag. A start
        rule that completes to nothing has failed; a recognition-only
        occurrence — a noise rule reached through an island reference — has
        simply produced nothing for its parent to capture, and the caller
        splices nothing rather than a value. Returning the presence explicitly
        is what keeps that distinct from an occurrence whose value IS ``None``.
        """
        return _complete_tree(root, self._routines, {}, wants_spans=self.wants_spans)

    def splice_replay(
        self, root: ParseTree, results: ResultMemo[Carry]
    ) -> CompletionResult[Carry]:
        """Complete one occurrence while reusing and extending ``results``.

        The seeded half of :meth:`splice`, exactly as :meth:`replay` is the
        seeded half of :meth:`build`. An ambiguity gate needs BOTH: it builds
        a baseline once and then replays only what an alternate changed, so a
        seam with no seeded entry has to rebuild the whole span per
        alternative.
        """
        return _complete_tree(
            root, self._routines, results, wants_spans=self.wants_spans
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
    routines: Mapping[str, RuleRoutine[Carry]],
    results: ResultMemo[Carry] | None = None,
    *,
    wants_spans: bool | None = None,
) -> Carry:
    """Complete one whole ParseTree through the program's verified completions.

    ``results`` is both seeded and filled.  A seeded node is never constructed
    again, which is the value-replay contract used by ambiguity checking.

    :raises UnsupportedConstructError: When the start rule produces no value.
        A document root that completes to nothing has failed; an occurrence
        that may honestly produce nothing goes through
        :meth:`ProductExecutor.splice` instead.
    """
    result = _complete_tree(
        root, routines, {} if results is None else results, wants_spans=wants_spans
    )
    if isinstance(result, EmptyResult):
        raise UnsupportedConstructError(
            f"product: start rule {root.symbol!s} completed without a value"
        )
    return result.value


def _complete_tree[Carry](
    root: ParseTree,
    routines: Mapping[str, RuleRoutine[Carry]],
    results: ResultMemo[Carry],
    *,
    wants_spans: bool | None = None,
) -> CompletionResult[Carry]:
    """Walk one derivation bottom-up and return the root's completion result."""
    folded: set[int] = set(results)
    wants_spans = _wants_spans(routines) if wants_spans is None else wants_spans
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
        _complete_node(node, routines, results, offsets)
    root_result = results.get(id(root), EMPTY_RESULT)
    if isinstance(root_result, EmptyResult):
        return _first_product_under(root, results)
    return root_result


def _wants_spans[Carry](routines: Mapping[str, RuleRoutine[Carry]]) -> bool:
    """Return whether any verified capture requests an extent."""
    return any(
        capture.mode == CaptureMode.EXTENT
        for routine in routines.values()
        for capture in routine.captures
    )


def _complete_node[Carry](
    node: ParseTree,
    routines: Mapping[str, RuleRoutine[Carry]],
    results: ResultMemo[Carry],
    offsets: Offsets,
) -> None:
    """Complete one bound rule; transparent nodes write no memo entry."""
    routine = routines.get(str(node.symbol))
    if routine is None:
        return
    if routine.source >= 0:
        results[id(node)] = _passed_value(node, routine, results)
        return
    construction = routine.construction
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
        _complete_record(node, routine, construction, results, offsets)
    )


def _passed_value[Carry](
    node: ParseTree,
    routine: RuleRoutine[Carry],
    results: ResultMemo[Carry],
) -> CompletionResult[Carry]:
    """Return the explicitly present or empty pass-through result.

    That the source names one single-value capture is the binding's answer
    (:func:`~lexic.parsing.product.verify.verify_program`), so this asks only
    what depends on the DERIVATION: whether the node has that child at all.
    """
    if not node.kids:
        return EMPTY_RESULT
    slot = routine.captures[routine.source].slot
    if slot >= len(node.kids):
        raise UnsupportedConstructError(
            f"product: {node.symbol!s}: pass item {slot} is out of range"
        )
    models = _product_models_at(node.kids[slot], results)
    return Completed(models[0]) if models else EMPTY_RESULT


def _complete_record[Carry](
    node: ParseTree,
    routine: RuleRoutine[Carry],
    construction: Construction[Carry],
    results: ResultMemo[Carry],
    offsets: Offsets,
) -> Carry:
    """Capture one sequence node and invoke its resolved construction."""
    kids = node.kids
    if len(kids) != routine.n_items:
        if kids:
            raise UnsupportedConstructError(
                f"product: {node.symbol!s}: {len(kids)} kids do not match "
                f"{routine.n_items} items (nor the empty arm)"
            )
        return construction.call()
    kwargs: dict[str, ProductValue[Carry]] = {}
    for capture in routine.captures:
        present, value = _captured(node, capture, results, offsets)
        if present:
            kwargs[capture.name] = value
    return construction.call(**kwargs)


def _captured[Carry](
    node: ParseTree,
    capture: CaptureRoutine,
    results: ResultMemo[Carry],
    offsets: Offsets,
) -> tuple[bool, ProductValue[Carry]]:
    """Read one capture, looking through transparent normalisation nodes."""
    kids = node.kids
    item = capture.slot
    if item >= len(kids):
        raise UnsupportedConstructError(
            f"product: {node.symbol!s}: capture item {item} is out of range"
        )
    kid = kids[item]
    mode = capture.mode
    if mode == CaptureMode.TEXT:
        text = subtree_text(kid)
        return (not capture.optional or bool(text), text)
    if mode == CaptureMode.EXTENT:
        return True, slot_span(node, kids, item, offsets)
    models = _product_models_at(kid, results)
    if mode == CaptureMode.MANY:
        return True, models
    if mode == CaptureMode.ONE:
        return (bool(models) or not capture.optional, models[0] if models else None)
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
    tuple[Mapping[str, RuleRoutine], IrAst, ParserTables],
] = memo({}, 0, 1)


def collapsed_product_tables(
    grammar: IrAst,
    routines: Mapping[str, RuleRoutine],
    bits: int = ORIGIN_BITS,
) -> ParserTables:
    """Return product-safe run-collapsed Earley tables, identity memoised."""
    key = (id(routines), id(grammar), bits)
    entry = _COLLAPSED.get(key)
    if entry is not None and entry[0] is routines and entry[1] is grammar:
        return entry[2]
    tables = collapse_runs(
        grammar,
        lambda plain, unit_rid: RUN_STR if run_ok(plain, unit_rid, routines) else None,
        bits,
    )
    _COLLAPSED[key] = (routines, grammar, tables)
    return tables
