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
- :mod:`.engine`    — :class:`EarleyParser`, the driver (Scott/Earley loop).
- :mod:`.forest`    — :class:`ParseTree`, the reducible derivation.
- :mod:`.reduce`    — :class:`Reducer`, forest → ``IrAst`` (the meta-notation seam).
- :mod:`.normalize` — desugar IR into classical Earley-shaped rules.

Shape caveats (documented at each site): nullable-rule completion (Aycock-
Horspool) and full SPPF disambiguation are simplified to the unambiguous case;
quantifier/group desugaring in :mod:`.normalize` is partial.
"""

from __future__ import annotations

from lexic.parsing_2.chart import Chart, Column, Link, Links
from lexic.parsing_2.engine import EarleyParser, parse, recognize
from lexic.parsing_2.forest import BUILD_TREE, BuildTree, ParseTree
from lexic.parsing_2.item import EarleyItem
from lexic.parsing_2.ops import EARLEY_OPS, Complete, Predict, Scan
from lexic.parsing_2.reduce import Reducer

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
    "parse",
    "recognize",
]
