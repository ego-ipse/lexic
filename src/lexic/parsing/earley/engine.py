"""Earley orchestration — the IR-native façade over the compiled kernel.

The paid loop lives in :mod:`lexic.parsing.earley.kernel`, running over the
compiled :mod:`~lexic.parsing.earley.tables`. This module keeps the IR seam: one
:class:`~lexic.ir.base.IrSelf` orchestration node per public capability, each
compiling the grammar (memoised), running one :class:`~lexic.parsing.earley.kernel
.Kernel`, and reading the result its own way:

- :class:`Recognize` — accept or not; SPPF recording stays off.
- :class:`Parse` — the strict single derivation via the packed-links
  :class:`~lexic.parsing.earley.kernel.FastTree`, falling back to the trampolined
  enumeration over the decoded chart on ambiguity.
- :class:`ParseForest` / :class:`Enumerate` / :class:`IsAmbiguous` — decode
  the packed SPPF to the IR-native :class:`~lexic.parsing.earley.chart.Chart` and
  drive the :mod:`~lexic.parsing.earley.forest` readers.

:class:`EarleyParser` remains the façade dispatcher handed to the readers'
``eval`` seams; the per-item type dispatch it once performed is compiled away
(the kernel discriminates with a table lookup).
"""

from __future__ import annotations

from typing import Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import (
    IrInt,
    IrLeaf,
    IrSelf,
    IrSeq,
    IrTuple,
)
from lexic.ir.nodes import IrAst
from lexic.ir.walk import IrDispatch
from lexic.parsing.earley.forest import (
    BUILD_TREE,
    DERIVATION_STREAM,
    DERIVATIONS,
    ParseTree,
)
from lexic.parsing.earley.kernel import FastTree, Kernel
from lexic.parsing.earley.lexruns import recognition_tables
from lexic.parsing.earley.reduce import FusedReduce, Reducer, collapsed_tables
from lexic.parsing.earley.tables import ORIGIN_BITS, ParserTables, compile_tables

_MATCH = IrInt(1)
_NO_MATCH = IrInt(0)
"""Shared truth-value leaves — cached so no ``IrInt`` allocation per answer."""


def _run_kernel(n: IrSelf, nc: Sequence[IrSelf], record_links: bool) -> Kernel:
    """Compile ``n`` (memoised), run one kernel over ``nc[0]``.

    :param n: The grammar (an :class:`~lexic.ir.nodes.IrAst`).
    :param nc: ``(IrStr(text), ...)``.
    :param record_links: Whether the kernel records SPPF provenance.
    :returns: The finished kernel.
    """
    if not isinstance(n, IrAst):
        raise UnsupportedConstructError(
            f"parsing: expected an IrAst grammar, got {type(n).__name__}"
        )
    return Kernel(compile_tables(n), str(nc[0]), record_links).run()


def _require_accept(kernel: Kernel, n: IrSelf) -> None:
    """Raise the no-parse error when ``kernel`` found no accepting item.

    :raises UnsupportedConstructError: If the input does not derive.
    """
    if kernel.accept < 0:
        start = n.start if isinstance(n, IrAst) else "<grammar>"
        raise UnsupportedConstructError(
            f"parsing: input does not derive from {str(start)!r}"
        )


def _single_tree(d: IrSelf, kernel: Kernel) -> ParseTree:
    """The strict single derivation of an accepted kernel parse.

    Fast path: :class:`~lexic.parsing.earley.kernel.FastTree` over the packed
    links. Slow path (a key packing more than one family): the trampolined
    :data:`~lexic.parsing.earley.forest.BUILD_TREE` over the decoded chart, which
    raises on a second derivation.

    :raises UnsupportedConstructError: On ambiguous input or no derivation.
    """
    handle = (kernel.accept << ORIGIN_BITS) | len(kernel.text)
    tree = FastTree(kernel).build(handle)
    if isinstance(tree, ParseTree):
        return tree
    built = BUILD_TREE.eval(d, kernel.accept_node(), IrTuple(kernel.to_chart()))
    if not isinstance(built, ParseTree):
        raise UnsupportedConstructError("parsing: no derivation")
    return built


class Recognize(IrLeaf[IrSelf, IrSelf]):
    """Whether ``text`` derives from the grammar's start rule — a truth value.

    Recognition never reads the forest, so SPPF recording is skipped entirely
    — and the kernel runs over maximally run-collapsed tables
    (:func:`~lexic.parsing.earley.lexruns.recognition_tables`): with no tree or
    forest to shape, every grammar-proved lexical run steps in one scan.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: ``IrInt`` 0/1."""
        if not isinstance(n, IrAst):
            raise UnsupportedConstructError(
                f"parsing: expected an IrAst grammar, got {type(n).__name__}"
            )
        kernel = Kernel(recognition_tables(n), str(nc[0]), False).run()
        return _MATCH if kernel.accept >= 0 else _NO_MATCH


class Parse(IrLeaf[IrSelf, IrSelf]):
    """The strict single derivation of ``text`` as a :class:`ParseTree`.

    Fast path: :class:`~lexic.parsing.earley.kernel.FastTree` over the packed
    links. Slow path (a key packing more than one family): the trampolined
    stream over the decoded chart, which raises on a second derivation.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> ParseTree:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: the derivation.

        :raises UnsupportedConstructError: If ``text`` does not parse, or
            parses ambiguously.
        """
        kernel = _run_kernel(n, nc, True)
        _require_accept(kernel, n)
        return _single_tree(d, kernel)


class ParseFirst(IrLeaf[IrSelf, IrSelf]):
    """The FIRST derivation of ``text`` — deterministic under ambiguity.

    The instance-parsing seam (:mod:`lexic.parsing.fold`): where
    :class:`Parse` raises on a second derivation, this takes the
    enumeration's first — parity with the retired Lark path's
    ``ambiguity="resolve"``. Fast path identical to :class:`Parse`; the
    lazy stream is only driven one item on the slow path.

    ``nc`` may carry pre-built :class:`~lexic.parsing.earley.tables.ParserTables` as a
    second element — the instance path passes run-collapsed tables (built with
    the fold-config licence in :mod:`lexic.parsing.fold`) so lexical runs step
    in one scan and land as a single multi-char leaf. A collapsed run is
    text-preserving, so :class:`~lexic.parsing.fold.ModelFold` reads it
    identically to the per-char expansion. On a fast-path miss (ambiguity), the
    collapsed run terminals cannot shape the enumeration the same way, so the
    fold-back mirrors :class:`ParseReduced`: re-parse over plain tables and take
    the stream's first — behaviour-identical to the uncollapsed path.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> ParseTree:
        """:param n: grammar; :param nc: ``(IrStr(text)[, ParserTables])``.

        :returns: a derivation.
        :raises UnsupportedConstructError: If ``text`` does not parse.
        """
        if not isinstance(n, IrAst):
            raise UnsupportedConstructError(
                f"parsing: expected an IrAst grammar, got {type(n).__name__}"
            )
        collapsed = nc[1] if len(nc) > 1 and isinstance(nc[1], ParserTables) else None
        tables = collapsed if collapsed is not None else compile_tables(n)
        kernel = Kernel(tables, str(nc[0]), True).run()
        _require_accept(kernel, n)
        handle = (kernel.accept << ORIGIN_BITS) | len(kernel.text)
        tree = FastTree(kernel).build(handle)
        if isinstance(tree, ParseTree):
            return tree
        if collapsed is not None:  # run terminals shape the chart — re-parse plain
            kernel = _run_kernel(n, nc, True)
            _require_accept(kernel, n)
        stream = DERIVATION_STREAM.eval(
            d, kernel.accept_node(), IrTuple(kernel.to_chart())
        )
        first = next(iter(stream), None)
        if not isinstance(first, ParseTree):
            raise UnsupportedConstructError("parsing: no derivation")
        return first


class ParseReduced(IrLeaf[IrSelf, IrSelf]):
    """Text → reduced IR in one pass — the product path.

    Runs the kernel over **reducer-collapsed tables** (safe lexical runs
    compiled to maximal-munch terminals — see
    :func:`~lexic.parsing.earley.reduce.collapsed_tables`), then folds the packed
    SPPF straight to IR via :class:`~lexic.parsing.earley.reduce.FusedReduce`,
    skipping the intermediate :class:`ParseTree` entirely. A fused fast-path
    miss (ambiguity, or a noise policy the fold does not compile) falls back
    to a fresh plain-tables parse and the general tree-then-reduce path —
    behaviour-identical, just slower.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """:param n: grammar; :param nc: ``(IrStr(text), Reducer)``.

        :returns: The reduced IR of the single derivation.
        :raises UnsupportedConstructError: If the input does not parse, or
            parses ambiguously.
        """
        if not isinstance(n, IrAst):
            raise UnsupportedConstructError(
                f"parsing: expected an IrAst grammar, got {type(n).__name__}"
            )
        reducer = nc[1]
        if not isinstance(reducer, Reducer):
            raise UnsupportedConstructError(
                f"parsing: expected a Reducer, got {type(reducer).__name__}"
            )
        kernel = Kernel(collapsed_tables(reducer, n), str(nc[0]), True).run()
        _require_accept(kernel, n)
        handle = (kernel.accept << ORIGIN_BITS) | len(kernel.text)
        fused = FusedReduce(kernel, reducer).build(handle)
        if fused is not None:
            return fused
        # The collapsed chart's shapes are reducer-specific — the general
        # tree path needs a plain parse.
        plain = _run_kernel(n, nc, True)
        _require_accept(plain, n)
        return reducer.apply(_single_tree(d, plain))


class ParseForest(IrLeaf[IrSelf, IrSelf]):
    """The shared packed parse forest root — an IR-native ``SppfNode``.

    Returns :data:`~lexic.ir.base.IrNone` when ``text`` does not parse. The
    packed SPPF is decoded so the returned handle's families are readable by
    the :mod:`~lexic.parsing.earley.forest` machinery.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: root or IrNone."""
        return _run_kernel(n, nc, True).accept_node()


class Enumerate(IrLeaf[IrSelf, IrSelf]):
    """ALL derivation trees of ``text`` as an :class:`~lexic.ir.base.IrSeq`."""

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSeq:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: every tree."""
        kernel = _run_kernel(n, nc, True)
        if kernel.accept < 0:
            return IrSeq()
        node = kernel.accept_node()
        return DERIVATIONS.eval(d, node, IrTuple(kernel.to_chart()))


class IsAmbiguous(IrLeaf[IrSelf, IrSelf]):
    """Whether ``text`` has more than one derivation — a truth value.

    Short-circuits after the second derivation from the lazy stream; the
    (potentially exponential) full enumeration is never forced.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: ``IrInt`` 0/1."""
        kernel = _run_kernel(n, nc, True)
        if kernel.accept < 0:
            return _NO_MATCH
        node = kernel.accept_node()
        stream = DERIVATION_STREAM.eval(d, node, IrTuple(kernel.to_chart()))
        seen = 0
        for _tree in stream:
            seen += 1
            if seen > 1:  # a second derivation ⇒ ambiguous; stop driving
                return _MATCH
        return _NO_MATCH


class EarleyParser(IrDispatch):
    """The façade dispatcher for parsing text against an IR grammar.

    The per-item Earley type dispatch is compiled away — the kernel
    discriminates the symbol after the dot with one table lookup — so the
    table here is empty; the object remains the ``d`` seam the forest and
    reduction readers thread through their ``eval`` calls.
    """


RECOGNIZE = Recognize()
PARSE = Parse()
PARSE_FIRST = ParseFirst()
PARSE_REDUCED = ParseReduced()
PARSE_FOREST = ParseForest()
ENUMERATE = Enumerate()
IS_AMBIGUOUS = IsAmbiguous()
"""Shared orchestration nodes — all stateless, so one instance each."""
