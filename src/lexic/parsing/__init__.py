"""IR-native parsing — Earley over an :class:`~lexic.ir.nodes.IrAst`, no Lark.

This package is the shape of the Lark replacement. The premise: an ``IrAst``
*is already a grammar*, so it can drive a parser directly. Given a grammar as IR
(e.g. ``json.py``'s ``JSON_GRAMMAR``, or ``grammars/abnf.py``'s ABNF-of-
ABNF) plus input text, the engine produces a parse forest; a reduction table
folds that forest back into an ``IrAst``. The fixpoint — parse the ABNF source of
ABNF with the ABNF grammar and recover the ABNF grammar — is the self-hosting
proof that retires the meta-grammars.

Layering mirrors the rest of ``lexic.ir``: every state object and every engine
operation IS-AN :class:`~lexic.ir.base.IrSelf`. The Earley operations live in an
:class:`~lexic.ir.mapping.IrTypeMap` dispatched on the symbol after the dot —
the same dispatch substrate the emit flavours use, run the other direction.

Module map:

- :mod:`.tables`    — :class:`ParserTables`, the int-coded compiled grammar,
                      and :func:`compile_tables` (memoised, once per grammar).
- :mod:`.kernel`    — :class:`Kernel`, the flat Earley loop over the compiled
                      tables (predict/scan/complete, Leo, packed SPPF), and
                      :class:`FastTree`, the unambiguous tree builder.
- :mod:`.item`      — :class:`EarleyItem`, the decoded dotted-arm record.
- :mod:`.chart`     — :class:`Chart` / :class:`Links`, the decoded SPPF the
                      IR-native forest readers walk.
- :mod:`.engine`    — the per-capability orchestration nodes the API drives.
- :mod:`.forest`    — :class:`ParseTree`, the reducible derivation.
- :mod:`.reduce`    — :class:`Reducer`, forest → ``IrAst`` (the meta-notation seam).
- :mod:`.normalize` — desugar IR into classical Earley-shaped rules.

The forest is a full SPPF (Scott 2008): nullable-rule completion (Aycock-Horspool)
and ambiguity are handled — ``parse`` returns the single derivation and raises on
ambiguous input, while ``parse_forest`` / ``derivations`` / ``is_ambiguous`` expose
every reading. Quantifier/group desugaring in :mod:`.normalize` is right-recursive;
the Leo optimisation (in :class:`~lexic.parsing.kernel.Kernel`) parses that recursion
in linear time, so ``*``/``+`` over long repeated input is O(n). Large *bounded*
counts (``{lo, hi}``) still unroll to ``hi`` nested rules and recurse ``hi``-deep at
desugar time — the one remaining rough edge.

Public API — each is a thin wrapper that boxes the text and drives one
:class:`~lexic.ir.base.IrSelf` orchestration node in :mod:`.engine`; the node owns
all the logic and the wrapper returns its result verbatim (a truth value is an
:class:`~lexic.ir.base.IrInt` ∈ {0, 1}, per the IR's no-``IrBool`` rule):

- :func:`recognize` — does ``text`` derive from the start rule.
- :func:`parse` — the strict single derivation as a :class:`.forest.ParseTree`.
- :func:`parse_forest` — the SPPF root :class:`.forest.SppfNode`, or
  :data:`~lexic.ir.base.IrNone` on no parse.
- :func:`derivations` — ALL derivations as an :class:`~lexic.ir.base.IrSeq`.
- :func:`is_ambiguous` — whether the input has more than one derivation.
"""

from __future__ import annotations

from lexic.ir.base import IrInt, IrSelf, IrSeq, IrStr, IrTuple
from lexic.ir.nodes import IrAst
from lexic.parsing.chart import Chart, EarleyItem, Link, Links
from lexic.parsing.engine import (
    ENUMERATE,
    IS_AMBIGUOUS,
    PARSE,
    PARSE_FIRST,
    PARSE_FOREST,
    PARSE_REDUCED,
    RECOGNIZE,
    EarleyParser,
)
from lexic.parsing.forest import BUILD_TREE, BuildTree, ParseTree, SppfNode
from lexic.parsing.kernel import FastTree, Kernel
from lexic.parsing.reduce import Reducer
from lexic.parsing.tables import ParserTables, compile_tables


def recognize(grammar: IrAst, text: str) -> IrInt:
    """Whether ``text`` derives from ``grammar``'s start rule (``IrInt`` 0/1).

    :param grammar: The grammar, Earley-normalised (see :mod:`.normalize`).
    :param text: The input string.
    :returns: ``IrInt(1)`` if the start rule spans the whole input, else ``IrInt(0)``.
    """
    return RECOGNIZE.eval(EarleyParser(), grammar, IrTuple(IrStr(text)))


def parse(grammar: IrAst, text: str) -> ParseTree:
    """Parse ``text`` into its single derivation tree (strict).

    A single :class:`~lexic.parsing.forest.ParseTree` cannot honestly represent
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

    The instance-parsing entry (:mod:`.models`): parity with the retired Lark
    path's ``ambiguity="resolve"``. Prefer :func:`parse` (strict) wherever a
    single honest derivation is required.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :param tables: Optional pre-built (run-collapsed) tables for ``grammar`` —
        the instance path passes ModelFold-licenced collapsed tables (see
        :func:`lexic.parsing.models.collapsed_instance_tables`) for a faster
        lexical layer; ``None`` compiles the plain tables.
    :returns: One derivation of ``text`` under the start rule.
    :raises UnsupportedConstructError: If ``text`` does not parse.
    """
    args = (IrStr(text),) if tables is None else (IrStr(text), tables)
    return PARSE_FIRST.eval(EarleyParser(), grammar, IrTuple(*args))


def parse_reduced(grammar: IrAst, text: str, reducer: Reducer) -> IrSelf:
    """Parse ``text`` and fold it straight to IR — the one-pass product path.

    Equivalent to ``reducer.apply(parse(grammar, text))`` but fused: the
    packed forest reduces directly, with no intermediate
    :class:`~lexic.parsing.forest.ParseTree` in the common unambiguous case.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :param reducer: The flavour's reduction policy.
    :returns: The reduced IR of the single derivation.
    :raises UnsupportedConstructError: If ``text`` does not parse, or parses
        ambiguously.
    """
    return PARSE_REDUCED.eval(EarleyParser(), grammar, IrTuple(IrStr(text), reducer))


def parse_forest(grammar: IrAst, text: str) -> IrSelf:
    """Parse ``text`` into its shared packed parse forest (SPPF).

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: The root :class:`~lexic.parsing.forest.SppfNode`, or
        :data:`~lexic.ir.base.IrNone` if ``text`` does not parse.
    """
    return PARSE_FOREST.eval(EarleyParser(), grammar, IrTuple(IrStr(text)))


def derivations(grammar: IrAst, text: str) -> IrSeq:
    """Enumerate ALL derivation trees of ``text`` — nothing silently discarded.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: An :class:`~lexic.ir.base.IrSeq` of
        :class:`~lexic.parsing.forest.ParseTree` derivations (possibly empty).
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
    "FastTree",
    "Kernel",
    "Link",
    "Links",
    "ParseTree",
    "ParserTables",
    "Reducer",
    "SppfNode",
    "compile_tables",
    "derivations",
    "is_ambiguous",
    "parse",
    "parse_first",
    "parse_forest",
    "parse_reduced",
    "recognize",
]
