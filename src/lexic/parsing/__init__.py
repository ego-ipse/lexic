"""IR-native parsing — Earley over an :class:`~lexic.ir.grammar.nodes.IrAst`, no Lark.

This package is the shape of the Lark replacement. The premise: an ``IrAst``
*is already a grammar*, so it can drive a parser directly. Given a grammar as IR
(e.g. ``json.py``'s ``JSON_GRAMMAR``, or ``grammars/abnf.py``'s ABNF-of-
ABNF) plus input text, the engine produces a parse forest; a reduction table
folds that forest back into an ``IrAst``. The fixpoint — parse the ABNF source of
ABNF with the ABNF grammar and recover the ABNF grammar — is the self-hosting
proof that retires the meta-grammars.

One model engine drives parsing. The instance path runs **PDA-first** — a
predictive table-driven runtime
(:mod:`.pda.runtime`) that builds the model during the walk, falling back to this
Earley engine on any non-deterministic point. See ``README.md``.

Layering mirrors the rest of ``lexic.ir``: every state object and every engine
operation IS-AN :class:`~lexic.ir.base.IrSelf`. The Earley operations live in an
:class:`~lexic.ir.action.mapping.IrTypeMap` dispatched on the symbol after the dot —
the same dispatch substrate the emit flavours use, run the other direction.

Module map:

- :mod:`.earley.kernel.tables` — :class:`ParserTables`, the int-coded compiled
                        grammar, and :func:`compile_tables` (memoised per grammar).
- :mod:`.earley.kernel.loop`  — what FILLS the chart: :class:`Kernel`, the flat
                        Earley loop over the compiled tables
                        (predict/scan/complete), the per-parse index state, and
                        the Leo right-recursion climb.
- :mod:`.earley.kernel.forest` — what the filled chart MEANS: :class:`ParseTree`
                        the reducible derivation, :class:`Chart` / :class:`Links`
                        the decoded SPPF and the ``EarleyItem`` tuple,
                        :class:`FastTree` the unambiguous builder, the ambiguity
                        question, the readout and the walk trampoline.
- :mod:`.earley.engine`   — the per-capability orchestration nodes the API drives.
- :mod:`.fold`        — :class:`~lexic.parsing.fold.ModelFold`, forest →
                        ``GrammarModel`` (the instance product).
- :mod:`.earley.normalize` — desugar IR into classical Earley-shaped rules.
- :mod:`.pda.charsets`    — :class:`~lexic.parsing.pda.core.charsets.CharSet`, the PDA analysis
                        substrate (polarity-aware co-finite char sets).
- :mod:`.pda.analysis`    — :class:`~lexic.parsing.pda.analysis.analysis.GrammarAnalysis`,
                        FIRST/FOLLOW/nullability + the island/stopset/LL(2) taxonomy.
- :mod:`.pda.clones`  — :func:`~lexic.parsing.pda.compiler.clones.compile_pda`, the
                        per-(rule, continuation) clone compiler.
- :mod:`.pda.flatten` — the int-coded PDA runtime program + optimizer passes.
- :mod:`.pda.runtime`  — :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel`, the fused
                        predictive runtime (parse + fold, no ``ParseTree``).

The forest is a full SPPF (Scott 2008): nullable-rule completion (Aycock-Horspool)
and ambiguity are handled — ``parse`` returns the single derivation and raises on
ambiguous input, while ``parse_forest`` / ``derivations`` / ``is_ambiguous`` expose
every reading. Quantifier/group desugaring in :mod:`.earley.normalize` is right-recursive;
the Leo optimisation (in :class:`~lexic.parsing.earley.kernel.loop.kernel.Kernel`)
parses that recursion
in linear time, so ``*``/``+`` over long repeated input is O(n). Large *bounded*
counts (``{lo, hi}``) still unroll to ``hi`` nested rules and recurse ``hi``-deep at
desugar time — the one remaining rough edge.

Public API — one **product** entry (:mod:`.products`) that takes the AUTHORED
grammar and owns the whole PDA-first-→-Earley-completion pipeline internally,
plus the lower-level Earley
toolkit that takes an Earley-normalised grammar (a truth value is an
:class:`~lexic.ir.base.IrInt` ∈ {0, 1}, per the IR's no-``IrBool`` rule):

- :func:`parse_model` — instance text → model (the instance product).
- :func:`recognize` — does ``text`` derive from the start rule.
- :func:`parse` — the strict single derivation as a :class:`.earley.forest.ParseTree`.
- :func:`parse_first` — the FIRST derivation, deterministic under ambiguity
  (the instance completion, see :mod:`.fold`).
- :func:`parse_forest` — the SPPF root :class:`.earley.forest.SppfNode`, or
  :data:`~lexic.ir.base.IrNone` on no parse.
- :func:`derivations` — ALL derivations as an :class:`~lexic.ir.base.IrSeq`.
- :func:`is_ambiguous` — whether the input has more than one derivation.

The tree/forest readers (:func:`recognize` … :func:`is_ambiguous`) each box the
text and drive one :class:`~lexic.ir.base.IrSelf` orchestration node in
:mod:`.earley.engine`. ``PdaFail`` is internal to the products and never
surfaces.

The engine floor is public here too, beside :class:`Kernel`:
:func:`~lexic.parsing.products.earley_model` is the model product's Earley
completion — the route-forcing seam — and the predictive half
surfaces as :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel` (the
fused runtime, subclassable for tracing),
:class:`~lexic.parsing.pda.analysis.analysis.GrammarAnalysis` (the decision
taxonomy the verdict readers consume), and
:func:`~lexic.parsing.products.pda_tables` /
:class:`~lexic.parsing.pda.compiler.tables.PdaTables` (the compiled tables a
kernel runs over, identity-memoised with the parse path).

:mod:`~lexic.parsing.earley.kernel.forest.support.readout`'s decode seam surfaces
here whole — :func:`to_chart`, :func:`decode_item`, the ``accept_*``
readers, :func:`start_completion_ends`, :func:`root_ambiguous`,
:func:`child_node`. It reads a finished :class:`Kernel`'s public fields and
calls no method on it, which is what makes it a seam; exporting it means a
consumer that wants to SEE a parse — a chart-column view, a trace — never
reaches past the package boundary for it.

:func:`~lexic.parsing.pda.analysis.predicates.nullable_names` surfaces here for
the same reason: it is the repo's only nullability fixpoint, and the codegen
passes need it to tell a language-preserving rewrite from a language-widening
one (:func:`~lexic.compile.pipeline.passes.relax_non_semantic`).

:mod:`~lexic.parsing.parallel` is the parallel layer — the split-point
analysis (anchors, roles, the self-locating scan) and the worker-count
policy. Nothing in it is engine API: neither engine consumes it, so its
names stay on the subpackage, not this root; ``CompiledGrammar.anchors()``
is the user surface.
"""

from __future__ import annotations

from lexic.ir import IrAst, IrInt, IrSelf, IrSeq, IrStr, IrTuple
from lexic.parsing.earley.engine import (
    ENUMERATE,
    IS_AMBIGUOUS,
    PARSE,
    PARSE_FIRST,
    PARSE_FOREST,
    RECOGNIZE,
    EarleyParser,
)
from lexic.parsing.earley.kernel.forest.chart import Chart, EarleyItem, Link, Links
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import (
    BUILD_TREE,
    BuildTree,
    ParseTree,
    RootNode,
    SppfNode,
)
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
    accept_items,
    accept_node,
    child_node,
    decode_item,
    root_ambiguous,
    start_completion_ends,
    to_chart,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.tokenscan import (
    CharTrieCursor,
    TokenMaskCursor,
    TokenTermCursor,
)
from lexic.parsing.fold import (
    FastCtor,
    FieldFold,
    ModelBody,
    ModelFold,
    RuleFold,
    lift_optional_nullables,
)
from lexic.parsing.parallel.pool import reset_pools
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.predicates import nullable_names
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.products import (
    earley_model,
    ModelBinding,
    parse_model,
    pda_tables,
    token_model,
)
from lexic.parsing.trace import (
    TRACE_CAP,
    TRACE_KINDS,
    Trace,
    TraceEvent,
    WatchedKernel,
    WatchedRun,
    watch,
)


def recognize(grammar: IrAst, text: str) -> IrInt:
    """Whether ``text`` derives from ``grammar``'s start rule (``IrInt`` 0/1).

    :param grammar: The grammar, Earley-normalised (see :mod:`.earley.normalize`).
    :param text: The input string.
    :returns: ``IrInt(1)`` if the start rule spans the whole input, else ``IrInt(0)``.
    """
    return RECOGNIZE.eval(EarleyParser(), grammar, IrTuple(IrStr(text)))


def parse(grammar: IrAst, text: str) -> ParseTree:
    """Parse ``text`` into its single derivation tree (strict).

    A single :class:`~lexic.parsing.earley.kernel.forest.forest.ParseTree` cannot honestly represent
    ambiguity — ambiguous input **raises**. Reach the forest via :func:`parse_forest`
    or :func:`derivations` instead.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: The derivation of ``text`` under the start rule.
    :raises UnsupportedConstructError: If ``text`` does not parse, or parses
        ambiguously.
    """
    return PARSE.eval(EarleyParser(), grammar, IrTuple(IrStr(text)))


def parse_first(
    grammar: IrAst, text: str, tables: ParserTables | None = None
) -> ParseTree:
    """Parse ``text`` into its FIRST derivation — deterministic under ambiguity.

    The tree-level toolkit entry: a cyclic grammar derives its text through
    unboundedly many derivations, so a deterministic first is what makes such
    grammars answerable at all. Prefer :func:`parse` (strict) wherever a
    single honest derivation is required; the value-level ambiguity gate lives
    in the model product (:func:`parse_model`), where a fold exists to compare
    what derivations MEAN.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :param tables: Optional pre-built (run-collapsed) tables for ``grammar`` —
        the instance path passes fold-licenced collapsed tables (see
        :func:`lexic.parsing.fold.collapsed_fold_tables`) for a faster
        lexical layer; ``None`` compiles the plain tables.
    :returns: One derivation of ``text`` under the start rule.
    :raises UnsupportedConstructError: If ``text`` does not parse.
    """
    args = (IrStr(text),) if tables is None else (IrStr(text), tables)
    return PARSE_FIRST.eval(EarleyParser(), grammar, IrTuple(*args))


def parse_forest(grammar: IrAst, text: str) -> IrSelf:
    """Parse ``text`` into its shared packed parse forest (SPPF).

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: The forest root — a single-production
        :class:`~lexic.parsing.earley.kernel.forest.forest.SppfNode`, a
        :class:`~lexic.parsing.earley.kernel.forest.forest.RootNode` packing the start
        symbol's alternative whole-input productions, or
        :data:`~lexic.ir.base.IrNone` if ``text`` does not parse.
    """
    return PARSE_FOREST.eval(EarleyParser(), grammar, IrTuple(IrStr(text)))


def derivations(grammar: IrAst, text: str) -> IrSeq:
    """Enumerate ALL derivation trees of ``text`` — nothing silently discarded.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: An :class:`~lexic.ir.base.IrSeq` of
        :class:`~lexic.parsing.earley.kernel.forest.forest.ParseTree` derivations (possibly empty).
    """
    return ENUMERATE.eval(EarleyParser(), grammar, IrTuple(IrStr(text)))


def is_ambiguous(grammar: IrAst, text: str) -> IrInt:
    """Whether ``text`` has more than one derivation under ``grammar`` (``IrInt`` 0/1).

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: ``IrInt(1)`` if ``text`` parses more than one way, else ``IrInt(0)``.
    """
    return IS_AMBIGUOUS.eval(EarleyParser(), grammar, IrTuple(IrStr(text)))


__all__ = [
    "BUILD_TREE",
    "BuildTree",
    "Chart",
    "EarleyParser",
    "EarleyItem",
    "FastCtor",
    "FastTree",
    "FieldFold",
    "GrammarAnalysis",
    "Kernel",
    "Link",
    "Links",
    "ModelBody",
    "ModelFold",
    "ParseTree",
    "ParserTables",
    "PdaKernel",
    "PdaTables",
    "Resolver",
    "RootNode",
    "RuleFold",
    "SppfNode",
    "accept_handle",
    "accept_handle",
    "accept_item",
    "accept_items",
    "accept_node",
    "child_node",
    "decode_item",
    "root_ambiguous",
    "start_completion_ends",
    "to_chart",
    "compile_tables",
    "derivations",
    "earley_model",
    "is_ambiguous",
    "reset_pools",
    "lift_optional_nullables",
    "normalize",
    "nullable_names",
    "parse",
    "parse_first",
    "parse_forest",
    "ModelBinding",
    "parse_model",
    "pda_tables",
    "CharTrieCursor",
    "TokenMaskCursor",
    "TokenTermCursor",
    "token_model",
    "recognize",
    "TRACE_CAP",
    "TRACE_KINDS",
    "Trace",
    "TraceEvent",
    "watch",
    "WatchedKernel",
    "WatchedRun",
]
