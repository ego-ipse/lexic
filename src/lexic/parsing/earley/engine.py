"""Earley orchestration — the IR-native façade over the compiled kernel.

The paid loop lives in :mod:`lexic.parsing.earley.kernel.loop.kernel`, running over the
compiled :mod:`~lexic.parsing.earley.kernel.tables`. This module keeps the IR seam: one
:class:`~lexic.ir.base.IrSelf` orchestration node per public capability, each
compiling the grammar (memoised), running one :class:`~lexic.parsing.earley.kernel.loop.kernel
.Kernel`, and reading the result its own way:

- :class:`Recognize` — accept or not; SPPF recording stays off.
- :class:`Parse` — the strict single derivation via the packed-links
  :class:`~lexic.parsing.earley.kernel.loop.kernel.FastTree`, falling back to the trampolined
  enumeration over the decoded chart on ambiguity.
- :class:`ParseForest` / :class:`Enumerate` / :class:`IsAmbiguous` — decode
  the packed SPPF to the IR-native :class:`~lexic.parsing.earley.kernel.forest.chart.Chart` and
  drive the :mod:`~lexic.parsing.earley.kernel.forest.forest` readers.

:class:`EarleyParser` remains the façade dispatcher handed to the readers'
``eval`` seams; the per-item type dispatch it once performed is compiled away
(the kernel discriminates with a table lookup).
"""

from __future__ import annotations

from typing import Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrDispatch, IrInt, IrLeaf, IrSelf, IrSeq, IrTuple
from lexic.parsing.earley.kernel.forest.fasttree import (
    FastTree,
    FirstTree,
    first_tree,
    streamed_first,
)
from lexic.parsing.earley.kernel.forest.forest import (
    BUILD_TREE,
    DERIVATION_STREAM,
    DERIVATIONS,
    ForestCtx,
    ParseTree,
)
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    DEFAULT_CONFIG,
    MeaningBuilder,
    ParseConfig,
    chosen_meaning,
    different_meaning,
)
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_handles,
    accept_item,
    accept_node,
    root_ambiguous,
    to_chart,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.decider import LEFTMOST_LONGEST, Decider
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.lexruns import recognition_tables

_MATCH = IrInt(1)
_NO_MATCH = IrInt(0)
"""Shared truth-value leaves — cached so no ``IrInt`` allocation per answer."""


def _run_kernel(n: IrSelf, nc: Sequence[IrSelf], record_links: bool) -> Kernel:
    """Compile ``n`` (memoised, tier picked by input size), run one kernel.

    :param n: The grammar (an :class:`~lexic.ir.grammar.nodes.IrAst`).
    :param nc: ``(IrStr(text), ...)``.
    :param record_links: Whether the kernel records SPPF provenance.
    :returns: The finished kernel.
    """
    if not isinstance(n, IrAst):
        raise UnsupportedConstructError(
            f"parsing: expected an IrAst grammar, got {type(n).__name__}"
        )
    text = str(nc[0])
    return Kernel(compile_tables(n, tier_for(len(text))), text, record_links).run()


def _require_accept(kernel: Kernel, n: IrSelf) -> None:
    """Raise the no-parse error when ``kernel`` found no accepting item.

    :raises UnsupportedConstructError: If the input does not derive.
    """
    if accept_item(kernel) < 0:
        start = n.start if isinstance(n, IrAst) else "<grammar>"
        raise UnsupportedConstructError(
            f"parsing: input does not derive from {str(start)!r}"
        )


def _single_tree(d: IrSelf, kernel: Kernel) -> ParseTree:
    """The strict single derivation of an accepted kernel parse.

    Fast path: :class:`~lexic.parsing.earley.kernel.loop.kernel.FastTree` over the packed
    links. Slow path (a key packing more than one family, or a many-production
    root): the trampolined :data:`~lexic.parsing.earley.kernel.forest.forest.BUILD_TREE` over
    the decoded chart, which raises on a second derivation.

    :raises UnsupportedConstructError: On ambiguous input or no derivation.
    """
    handle = accept_handle(kernel)
    if not root_ambiguous(kernel):
        tree = FastTree(kernel, None, LEFTMOST_LONGEST).build(handle)
        if isinstance(tree, ParseTree):
            return tree
    built = BUILD_TREE.eval(d, accept_node(kernel), IrTuple(to_chart(kernel)))
    if not isinstance(built, ParseTree):
        raise UnsupportedConstructError("parsing: no derivation")
    return built


def first_meaning(
    n: IrSelf,
    text: str,
    tables: ParserTables | None,
    decide: Decider,
) -> ParseTree:
    """The first derivation of ``text`` — deterministic under ambiguity.

    The tree route's chooser. Whether the span MEANS two things is a question
    about values, so it is asked where the values are built
    (:func:`first_built_meaning`, and :func:`~lexic.parsing.earley.kernel.forest
    .support.ambiguity.chosen_meaning` under it); a tree consumer has nothing to
    compare and takes the deterministic first — of the carvings ``decide``
    keeps, as the value route does.

    :param n: The grammar (an :class:`~lexic.ir.grammar.nodes.IrAst`).
    :param text: The input string.
    :param tables: Optional pre-built (run-collapsed) tables for ``n``.
    :param decide: The split decider whose carving the derivation keeps.
    :returns: The first derivation.
    :raises UnsupportedConstructError: If ``text`` does not parse.
    """
    return _first_derivation(n, text, tables, decide)[1].tree


def _first_derivation(
    n: IrSelf,
    text: str,
    tables: ParserTables | None,
    decide: Decider,
) -> tuple[Kernel, FirstTree]:
    """Run Earley and return its kernel and the first derivation of the input.

    Every accepting production is tried, under ``decide``
    (:func:`~lexic.parsing.earley.kernel.forest.fasttree.first_tree`).
    Run terminals shape the chart, so where pre-built tables decline, the input
    is re-parsed plain and read again before the decoded chart is streamed.
    """
    if not isinstance(n, IrAst):
        raise UnsupportedConstructError(
            f"parsing: expected an IrAst grammar, got {type(n).__name__}"
        )
    kernel = Kernel(
        tables if tables is not None else compile_tables(n, tier_for(len(text))),
        text,
        True,
    ).run()
    _require_accept(kernel, n)
    first = first_tree(kernel, accept_handles(kernel), decide)
    if first is None and tables is not None:
        kernel = Kernel(compile_tables(n, tier_for(len(text))), text, True).run()
        _require_accept(kernel, n)
        first = first_tree(kernel, accept_handles(kernel), decide)
    if first is None:
        first = streamed_first(
            accept_node(kernel), to_chart(kernel), accept_handle(kernel)
        )
    if first is None:
        raise UnsupportedConstructError("parsing: no derivation")
    return kernel, first


def first_built_meaning[Value, NodeValue](
    n: IrSelf,
    text: str,
    builder: MeaningBuilder[Value, NodeValue],
    tables: ParserTables | None = None,
    config: ParseConfig = DEFAULT_CONFIG,
) -> Value:
    """Return the chosen value, constructing each considered meaning once.

    The value-route twin of :func:`first_meaning`: same derivation, same
    question, and the answer is the VALUE rather than the tree that carried
    it. Neither route takes a dispatcher: the chart stream they fall back to
    never consults one.

    :param n: The grammar (an :class:`~lexic.ir.grammar.nodes.IrAst`).
    :param text: The input string.
    :param builder: The interpretation's fresh and seeded entry points.
    :param tables: Optional pre-built (run-collapsed) tables for ``n``.
    :param config: The caller's resolver and split decider.
    :returns: The chosen meaning's value.
    :raises UnsupportedConstructError: If ``text`` does not parse, or means two
        things and no resolver was supplied.
    """
    decide = config.decide
    kernel, first = _first_derivation(n, text, tables, decide)
    return chosen_meaning(
        different_meaning(kernel, first, builder, decide), builder, config
    )


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
        text = str(nc[0])
        tables = recognition_tables(n, tier_for(len(text)))
        kernel = Kernel(tables, text, False).run()
        return _MATCH if accept_item(kernel) >= 0 else _NO_MATCH


class Parse(IrLeaf[IrSelf, IrSelf]):
    """The strict single derivation of ``text`` as a :class:`ParseTree`.

    Fast path: :class:`~lexic.parsing.earley.kernel.loop.kernel.FastTree` over the packed
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

    Where :class:`Parse` raises on a second derivation, this takes the
    enumeration's first. Not a convenience: a cyclic grammar
    (``s ::= s | "a"``) derives its text through unboundedly many derivations,
    so "the single derivation" does not exist there and a deterministic first
    is what makes such grammars answerable at all. The VALUE-level ambiguity
    question — does the span mean two things — needs a fold to answer, so it is
    asked on the value route (:func:`first_built_meaning`) rather than here.
    Fast path identical to :class:`Parse`; the lazy stream is only driven one
    item on the slow path.

    ``nc`` may carry pre-built :class:`~lexic.parsing.earley.kernel.tables.ParserTables` as a
    second element — the instance path passes run-collapsed tables (built with
    the rule-keyed licence in :mod:`lexic.parsing.product`) so lexical runs step
    in one scan and land as a single multi-char leaf. A collapsed run is
    text-preserving, so :class:`~lexic.parsing.product.ProductExecutor` reads it
    identically to the per-char expansion. On a fast-path miss (ambiguity), the
    collapsed run terminals cannot shape the enumeration the same way, so the
    fold-back re-parses over plain tables and takes the stream's first —
    behaviour-identical to the uncollapsed path.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> ParseTree:
        """:param n: grammar; :param nc: ``(IrStr(text), ParserTables | IrNone,
            Decider)``.

        :returns: a derivation.
        :raises UnsupportedConstructError: If ``text`` does not parse, or
            ``nc`` carries no decider.
        """
        text, tables, decide = str(nc[0]), nc[1], nc[2]
        if not isinstance(decide, Decider):
            raise UnsupportedConstructError(
                f"parsing: parse_first needs a decider, got {type(decide).__name__}"
            )
        collapsed = tables if isinstance(tables, ParserTables) else None
        return first_meaning(n, text, collapsed, decide)


class ParseForest(IrLeaf[IrSelf, IrSelf]):
    """The shared packed parse forest root — an IR-native ``SppfNode``.

    Returns :data:`~lexic.ir.base.IrNone` when ``text`` does not parse. The
    packed SPPF is decoded so the returned handle's families are readable by
    the :mod:`~lexic.parsing.earley.kernel.forest.forest` machinery.
    """

    def eval(self, _d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: root or IrNone."""
        return accept_node(_run_kernel(n, nc, True))


class Enumerate(IrLeaf[IrSelf, IrSelf]):
    """The cycle-free derivation trees of ``text`` as an :class:`~lexic.ir.base.IrSeq`."""

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSeq:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: the trees."""
        kernel = _run_kernel(n, nc, True)
        if accept_item(kernel) < 0:
            return IrSeq()
        node = accept_node(kernel)
        return DERIVATIONS.eval(d, node, IrTuple(to_chart(kernel)))


class IsAmbiguous(IrLeaf[IrSelf, IrSelf]):
    """Whether ``text`` has more than one derivation — a truth value.

    Short-circuits after the second derivation from the lazy stream; the
    (potentially exponential) full enumeration is never forced. A stream that
    ends with one tree is still ambiguous if it cut a cycle
    (:attr:`~lexic.parsing.earley.kernel.forest.forest.ForestCtx.cut`): the
    pumped derivation through it is a second one.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: ``IrInt`` 0/1."""
        kernel = _run_kernel(n, nc, True)
        if accept_item(kernel) < 0:
            return _NO_MATCH
        node = accept_node(kernel)
        ctx = ForestCtx(to_chart(kernel))
        stream = DERIVATION_STREAM.eval(d, node, IrTuple(ctx))
        seen = 0
        for _tree in stream:
            seen += 1
            if seen > 1:  # a second derivation ⇒ ambiguous; stop driving
                return _MATCH
        return _MATCH if ctx.cut else _NO_MATCH


class EarleyParser(IrDispatch):
    """The façade dispatcher for parsing text against an IR grammar.

    The per-item Earley type dispatch is compiled away — the kernel
    discriminates the symbol after the dot with one table lookup — so the
    table here is empty; the object remains the ``d`` seam the forest and
    reduction readers thread through their ``eval`` calls.
    """


EARLEY_PARSER = EarleyParser()
RECOGNIZE = Recognize()
PARSE = Parse()
PARSE_FIRST = ParseFirst()
PARSE_FOREST = ParseForest()
ENUMERATE = Enumerate()
IS_AMBIGUOUS = IsAmbiguous()
"""Shared orchestration nodes — all stateless, so one instance each."""
