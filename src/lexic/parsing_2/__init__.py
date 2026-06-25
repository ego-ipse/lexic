"""IR-native parsing — Earley over an :class:`~lexic.ir.nodes.IrAst`, no Lark.

This package is the shape of the Lark replacement. The premise: an ``IrAst``
*is already a grammar*, so it can drive a parser directly. Given a grammar as IR
(e.g. ``json.py``'s ``JSON_GRAMMAR``, or the forthcoming ``abnf_2.py`` ABNF-of-
ABNF) plus input text, the engine produces a parse forest; a reduction table
folds that forest back into an ``IrAst``. The fixpoint — parse the ABNF source of
ABNF with the ABNF grammar and recover the ABNF grammar — is the self-hosting
proof that retires the meta-grammars.

Layering mirrors the rest of ``lexic.ir``: every state object and every engine
operation IS-AN :class:`~lexic.ir.base.IrSelf`. The Earley operations live in an
:class:`~lexic.ir.mapping.IrTypeMap` dispatched on the symbol after the dot —
the same dispatch substrate the emit flavours use, run the other direction.

Module map:

- :mod:`.item`      — :class:`EarleyItem`, the dotted-arm state record.
- :mod:`.chart`     — :class:`Column` / :class:`Chart`, the Earley sets.
- :mod:`.ops`       — :class:`Predict` / :class:`Scan` / :class:`Complete` bodies
                      and the :data:`EARLEY_OPS` dispatch table.
- :mod:`.engine`    — :class:`EarleyParser`, the driver (Scott/Earley loop), and
                      the per-operation orchestration nodes the API drives.
- :mod:`.forest`    — :class:`ParseTree`, the reducible derivation.
- :mod:`.reduce`    — :class:`Reducer`, forest → ``IrAst`` (the meta-notation seam).
- :mod:`.normalize` — desugar IR into classical Earley-shaped rules.

The forest is a full SPPF (Scott 2008): nullable-rule completion (Aycock-Horspool)
and ambiguity are handled — ``parse`` returns the single derivation and raises on
ambiguous input, while ``parse_forest`` / ``derivations`` / ``is_ambiguous`` expose
every reading. Quantifier/group desugaring in :mod:`.normalize` is right-recursive
(O(n²) on long input — a separate optimisation effort).

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
from lexic.parsing_2.chart import Chart, Column, Link, Links
from lexic.parsing_2.engine import (
    ENUMERATE,
    IS_AMBIGUOUS,
    PARSE,
    PARSE_FOREST,
    RECOGNIZE,
    EarleyParser,
)
from lexic.parsing_2.forest import BUILD_TREE, BuildTree, ParseTree, SppfNode
from lexic.parsing_2.item import EarleyItem
from lexic.parsing_2.ops import EARLEY_OPS, Complete, Predict, Scan
from lexic.parsing_2.reduce import Reducer


def recognize(grammar: IrAst, text: str) -> IrInt:
    """Whether ``text`` derives from ``grammar``'s start rule (``IrInt`` 0/1).

    :param grammar: The grammar, Earley-normalised (see :mod:`.normalize`).
    :param text: The input string.
    :returns: ``IrInt(1)`` if the start rule spans the whole input, else ``IrInt(0)``.
    """
    return RECOGNIZE.eval(EarleyParser(), grammar, IrTuple(IrStr(text)))


def parse(grammar: IrAst, text: str) -> ParseTree:
    """Parse ``text`` into its single derivation tree (strict).

    A single :class:`~lexic.parsing_2.forest.ParseTree` cannot honestly represent
    ambiguity — ambiguous input **raises**. Reach the forest via :func:`parse_forest`
    or :func:`derivations` instead.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: The derivation of ``text`` under the start rule.
    :raises UnsupportedConstructError: If ``text`` does not parse, or parses
        ambiguously.
    """
    return PARSE.eval(EarleyParser(), grammar, IrTuple(IrStr(text)))


def parse_forest(grammar: IrAst, text: str) -> IrSelf:
    """Parse ``text`` into its shared packed parse forest (SPPF).

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: The root :class:`~lexic.parsing_2.forest.SppfNode`, or
        :data:`~lexic.ir.base.IrNone` if ``text`` does not parse.
    """
    return PARSE_FOREST.eval(EarleyParser(), grammar, IrTuple(IrStr(text)))


def derivations(grammar: IrAst, text: str) -> IrSeq:
    """Enumerate ALL derivation trees of ``text`` — nothing silently discarded.

    :param grammar: The grammar, Earley-normalised.
    :param text: The input string.
    :returns: An :class:`~lexic.ir.base.IrSeq` of
        :class:`~lexic.parsing_2.forest.ParseTree` derivations (possibly empty).
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
    "Column",
    "Complete",
    "EARLEY_OPS",
    "EarleyParser",
    "EarleyItem",
    "Link",
    "Links",
    "ParseTree",
    "Predict",
    "Reducer",
    "Scan",
    "SppfNode",
    "derivations",
    "is_ambiguous",
    "parse",
    "parse_forest",
    "recognize",
]
