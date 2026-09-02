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

from collections.abc import Callable
from typing import Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrDispatch, IrInt, IrLeaf, IrNone, IrSelf, IrSeq, IrTuple
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import (
    BUILD_TREE,
    DERIVATION_STREAM,
    DERIVATIONS,
    ParseTree,
)
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    AmbiguityPolicy,
    MeaningBuilder,
    Resolver,
    another_meaning,
    different_meaning,
)
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
    accept_node,
    root_ambiguous,
    to_chart,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
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
        tree = FastTree(kernel).build(handle)
        if isinstance(tree, ParseTree):
            return tree
    built = BUILD_TREE.eval(d, accept_node(kernel), IrTuple(to_chart(kernel)))
    if not isinstance(built, ParseTree):
        raise UnsupportedConstructError("parsing: no derivation")
    return built


def _one_meaning(kernel: Kernel, build: Callable[[ParseTree], object]) -> ParseTree:
    """The derivation to interpret, refusing only a span with two meanings.

    The strict :func:`_single_tree` refuses on a second DERIVATION, which is the
    rule the island path abandoned: a grammar derives one text several ways
    without meaning anything by it, and two adjacent nullable slots split a gap
    two ways to the same end. Under the counting rule every whitespace-carrying
    EBNF file was refused, because that self-grammar has exactly that shape.

    :raises UnsupportedConstructError: When two derivations build different
        values, or when nothing derives.
    """
    handle = accept_handle(kernel)
    # An empty choices map takes family 0 at every ambiguity point instead of
    # bailing on one, so this builds whenever the links are complete — the
    # enumerating fallback would only reinstate the counting rule.
    tree = FastTree(kernel, {}).build(handle)
    if not isinstance(tree, ParseTree):
        raise UnsupportedConstructError("parsing: no derivation")
    if another_meaning(kernel, handle, build, tree) is not None:
        raise UnsupportedConstructError(
            "parsing: ambiguous input — two derivations that mean different "
            "things; use the forest enumeration entry to choose between them"
        )
    return tree


def first_meaning(
    d: IrSelf,
    n: IrSelf,
    text: str,
    tables: ParserTables | None = None,
    policy: AmbiguityPolicy | None = None,
) -> ParseTree:
    """The first derivation of ``text`` — gated, given a ``policy``, on meaning.

    The model completion's derivation chooser. Without a policy this is the
    plain deterministic first (what :class:`ParseFirst` returns). With one, the
    span is asked whether another derivation builds a DIFFERENT value
    (:func:`~lexic.parsing.earley.kernel.forest.support.ambiguity.another_meaning`):
    a real arm choice is refused by default, and the policy's ``resolve`` is
    the caller's explicit opt-out — a deterministic resolver handed both
    derivations, whose choice is their concern. A function argument rather than
    part of the action's ``nc``, because a fold's callable is not an IR value
    and does not belong on an IR channel.

    :param d: The dispatcher seam the forest readers thread.
    :param n: The grammar (an :class:`~lexic.ir.grammar.nodes.IrAst`).
    :param text: The input string.
    :param tables: Optional pre-built (run-collapsed) tables for ``n``.
    :param policy: The build that makes the meaning question answerable, and
        the resolver that settles it; ``None`` skips the question entirely.
    :returns: The chosen derivation.
    :raises UnsupportedConstructError: If ``text`` does not parse, or means two
        things and no resolver was supplied.
    """
    kernel, handle, first = _first_derivation(d, n, text, tables)
    if policy is None:
        return first
    witness = another_meaning(kernel, handle, policy.build, first)
    if witness is None:
        return first
    if policy.resolve is None:
        raise UnsupportedConstructError(
            "parsing: ambiguous input — two derivations that mean different "
            "things; supply a resolver to choose between them"
        )
    return policy.resolve(first, witness)


def _first_derivation(
    d: IrSelf,
    n: IrSelf,
    text: str,
    tables: ParserTables | None,
) -> tuple[Kernel, int, ParseTree]:
    """Run Earley and return its kernel, accepting handle, and first tree."""
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
    handle = accept_handle(kernel)
    first: IrSelf = IrNone
    if not root_ambiguous(kernel):
        # RESOLVING mode: an empty choices map pins nothing, so the chain
        # policy decides the splits. Bail mode would decline on exactly the
        # ambiguous inputs at issue and fall through to the stream, which
        # takes chart order — the very thing the two engines disagreed on.
        first = FastTree(kernel, {}).build(handle)
    if not isinstance(first, ParseTree):
        if tables is not None:  # run terminals shape the chart — re-parse plain
            kernel = Kernel(compile_tables(n, tier_for(len(text))), text, True).run()
            _require_accept(kernel, n)
            handle = accept_handle(kernel)
        stream = DERIVATION_STREAM.eval(
            d, accept_node(kernel), IrTuple(to_chart(kernel))
        )
        first = next(iter(stream), IrNone)
        if not isinstance(first, ParseTree):
            raise UnsupportedConstructError("parsing: no derivation")
    return kernel, handle, first


def first_built_meaning[Value, NodeValue](
    d: IrSelf,
    n: IrSelf,
    text: str,
    builder: MeaningBuilder[Value, NodeValue],
    tables: ParserTables | None = None,
    resolve: Resolver | None = None,
) -> Value:
    """Return the chosen value, constructing each considered meaning once."""
    kernel, handle, first = _first_derivation(d, n, text, tables)
    pair = different_meaning(kernel, handle, builder, first)
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
    question — does the span mean two things — needs a fold to answer and is
    asked by :func:`first_meaning`, which the model completion drives; this
    action is that function without the gate. Fast path identical to
    :class:`Parse`; the lazy stream is only driven one item on the slow path.

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

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> ParseTree:
        """:param n: grammar; :param nc: ``(IrStr(text)[, ParserTables])``.

        :returns: a derivation.
        :raises UnsupportedConstructError: If ``text`` does not parse.
        """
        text = str(nc[0])
        collapsed = nc[1] if len(nc) > 1 and isinstance(nc[1], ParserTables) else None
        return first_meaning(d, n, text, collapsed)


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
    """ALL derivation trees of ``text`` as an :class:`~lexic.ir.base.IrSeq`."""

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSeq:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: every tree."""
        kernel = _run_kernel(n, nc, True)
        if accept_item(kernel) < 0:
            return IrSeq()
        node = accept_node(kernel)
        return DERIVATIONS.eval(d, node, IrTuple(to_chart(kernel)))


class IsAmbiguous(IrLeaf[IrSelf, IrSelf]):
    """Whether ``text`` has more than one derivation — a truth value.

    Short-circuits after the second derivation from the lazy stream; the
    (potentially exponential) full enumeration is never forced.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """:param n: grammar; :param nc: ``(IrStr(text),)``; :returns: ``IrInt`` 0/1."""
        kernel = _run_kernel(n, nc, True)
        if accept_item(kernel) < 0:
            return _NO_MATCH
        node = accept_node(kernel)
        stream = DERIVATION_STREAM.eval(d, node, IrTuple(to_chart(kernel)))
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
PARSE_FOREST = ParseForest()
ENUMERATE = Enumerate()
IS_AMBIGUOUS = IsAmbiguous()
"""Shared orchestration nodes — all stateless, so one instance each."""
