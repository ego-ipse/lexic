"""The two product entries — reduce (text → the reducer's value), model (text → model).

Both take the **authored** grammar and own the whole compilation pipeline
internally: lift + normalise, compile the predictive PDA (and, for the model
product, the run-collapsed Earley tables), all memoised per
**(grammar identity, reducer/fold identity)** — the compiled tables bake the
reducer plan / fold records, so grammar identity alone is a wrong key. Earley
tables pack at the tier the input's size picks
(:func:`~lexic.parsing.earley.tables.tier_for` — the model product keys it, the
reduce completion picks it per parse). Each
parse runs the PDA first and completes on the Earley engine on any
:class:`~lexic.parsing.pda.runtime.runtime.PdaFail`; :class:`PdaFail` never escapes.

The Earley-completion entries — :func:`earley_reduce` (fused reduce over a
normalised grammar) and :func:`earley_model` (``parse_first`` + fold) — are the
per-product completions the product entries call, and the seam tests force to
exercise the Earley route directly. They take an **Earley-normalised** grammar,
the low-level contract the tree/forest readers keep.

A leaf inside ``lexic.parsing``: imports the Earley engine and the PDA compiler/
runtime by public name; ``__init__`` re-exports the two product entries at the
package root, the sole surface ``compile.py`` (and every other consumer) sees.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrSelf, IrStr, IrTuple
from lexic.ir.nodes import IrAst
from lexic.parsing.earley.engine import PARSE_FIRST, PARSE_REDUCED, EarleyParser
from lexic.parsing.earley.forest import ParseTree
from lexic.parsing.earley.kernel import FastTree
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce import Reducer
from lexic.parsing.earley.tables import (
    ORIGIN_BITS,
    ParserTables,
    compile_tables,
    tier_for,
)
from lexic.parsing.earley.tokenscan import TokenKernel
from lexic.parsing.fold import ModelFold, collapsed_fold_tables, lift_optional_nullables
from lexic.parsing.pda.compiler.clones import PdaTables, compile_pda, compile_reduce_pda
from lexic.parsing.pda.runtime.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime.runtime import PdaFail

__all__ = [
    "parse_reduced",
    "parse_model",
    "earley_reduce",
    "earley_model",
    "reset_product_cache",
]


# ── the Earley completions (also the tests' route-forcing seam) ────────────


def earley_reduce(grammar: IrAst, text: str, reducer: Reducer) -> IrSelf:
    """Parse ``text`` and fold it straight to IR in one Earley pass.

    The grammar-text product's Earley completion — ``reducer.apply(parse(...))``
    fused (no intermediate :class:`~lexic.parsing.earley.forest.ParseTree` in the
    common unambiguous case).

    :param grammar: The grammar, Earley-normalised (see :mod:`.earley.normalize`).
    :param text: The input string.
    :param reducer: The flavour's reduction policy.
    :returns: The reduced IR of the single derivation.
    :raises UnsupportedConstructError: If ``text`` does not parse, parses
        ambiguously, or ``reducer`` is not a :class:`Reducer`.
    """
    return PARSE_REDUCED.eval(EarleyParser(), grammar, IrTuple(IrStr(text), reducer))


def earley_model[M](
    grammar: IrAst, text: str, fold: ModelFold[M], tables: ParserTables | None = None
) -> M:
    """Parse ``text`` and fold it to a model through the Earley engine.

    The instance product's Earley completion — ``parse_first`` (deterministic
    under ambiguity, since an all-nullable arm would otherwise make the empty
    match ambiguous) folded through ``fold``.

    :param grammar: The Earley-normalised instance grammar.
    :param text: The input string.
    :param fold: The positional ParseTree → model fold producing ``M``.
    :param tables: Optional pre-built run-collapsed tables for ``grammar``.
    :returns: The model the start rule folds to.
    :raises UnsupportedConstructError: If ``text`` does not parse.
    """
    args = (IrStr(text),) if tables is None else (IrStr(text), tables)
    tree = PARSE_FIRST.eval(EarleyParser(), grammar, IrTuple(*args))
    return fold.apply(tree)


def token_model[M](
    grammar: IrAst,
    text: str,
    fold: ModelFold[M],
    bounds: dict[int, tuple[int, int]],
) -> M:
    """Parse token-segmented ``text`` to a model via the token Earley kernel.

    The instance product for a **token-bearing** grammar: :class:`TokenKernel`
    scans the token ``bounds`` (char position → ``(id, len)``), :class:`FastTree`
    builds the single derivation, and ``fold`` builds the model. Char terminals
    cross token boundaries; token terminals match id-granular. Token grammars
    island the PDA by construction, so this Earley route is the whole parse.

    :param grammar: The codegen grammar (with resolved token terminals).
    :param text: The input string.
    :param fold: The positional ParseTree → model fold producing ``M``.
    :param bounds: char position → ``(token_id, char_len)`` segmentation.
    :returns: The model the start rule folds to.
    :raises UnsupportedConstructError: If ``text`` does not parse.
    """
    tables = _token_tables(grammar, tier_for(len(text)))
    kernel = TokenKernel(tables, text, bounds, record_links=True).run()
    if kernel.accept < 0:
        raise UnsupportedConstructError(
            "parsing: input does not parse the token grammar"
        )
    handle = (kernel.accept << kernel.tables.packing.bits) | len(kernel.text)
    tree = FastTree(kernel).build(handle)
    if not isinstance(tree, ParseTree):
        raise UnsupportedConstructError("parsing: no token derivation")
    return fold.apply(tree)


# ── compiled-product records + per-identity memoisation ────────────────────


@dataclass(frozen=True)
class _ReduceProduct:
    """A grammar-text product compiled once — the reduce PDA + Earley grammar.

    :ivar grammar: The authored grammar (held to pin its identity key).
    :ivar reducer: The reduction policy (held to pin its identity key).
    :ivar pda: The reduce PDA (immediate-PdaFail start ⇒ Earley every parse).
    :ivar earley_grammar: ``normalize(lift_optional_nullables(grammar))`` — the
        same lifted, normalised grammar the PDA compiles over.
    """

    grammar: IrAst
    reducer: Reducer
    pda: PdaTables
    earley_grammar: IrAst


@dataclass(frozen=True)
class _ModelProduct:
    """An instance product compiled once — the model PDA + collapsed tables.

    :ivar grammar: The authored codegen grammar (held to pin its identity key).
    :ivar fold: The positional fold (held to pin its identity key).
    :ivar pda: The model PDA (immediate-PdaFail start ⇒ Earley every parse).
    :ivar instance_grammar: ``normalize(lift_optional_nullables(grammar))`` — the
        completion grammar and island sub-parse shape.
    :ivar tables: The run-collapsed Earley tables for ``instance_grammar``.
    """

    grammar: IrAst
    fold: ModelFold
    pda: PdaTables
    instance_grammar: IrAst
    tables: ParserTables


_REDUCE_CACHE: dict[tuple[int, int], _ReduceProduct] = {}
_MODEL_CACHE: dict[tuple[int, int, int], _ModelProduct] = {}
_TOKEN_TABLES: dict[tuple[int, int], tuple[IrAst, ParserTables]] = {}


def reset_product_cache() -> None:
    """Test seam: drop the per-identity product caches."""
    _REDUCE_CACHE.clear()
    _MODEL_CACHE.clear()
    _TOKEN_TABLES.clear()


def _token_tables(grammar: IrAst, bits: int) -> ParserTables:
    """The token product's Earley tables, memoised per ``(grammar, bits)``.

    The token grammar normalises to a fresh ``IrAst`` per call, so the
    identity-keyed :func:`compile_tables` memo alone would recompile every
    parse — this memo pins the AUTHORED grammar's identity instead.
    """
    key = (id(grammar), bits)
    entry = _TOKEN_TABLES.get(key)
    if entry is not None and entry[0] is grammar:
        return entry[1]
    tables = compile_tables(normalize(lift_optional_nullables(grammar)), bits)
    _TOKEN_TABLES[key] = (grammar, tables)
    return tables


def _reduce_product(grammar: IrAst, reducer: Reducer) -> _ReduceProduct:
    """The compiled reduce product for ``(grammar, reducer)``, memoised by identity.

    :raises UnsupportedConstructError: When ``reducer`` is not a :class:`Reducer`.
    """
    if not isinstance(reducer, Reducer):
        raise UnsupportedConstructError(
            f"parse_reduced: reducer is {type(reducer).__name__!r}, not a Reducer"
        )
    key = (id(grammar), id(reducer))
    cached = _REDUCE_CACHE.get(key)
    if cached is not None and cached.grammar is grammar and cached.reducer is reducer:
        return cached
    lifted = lift_optional_nullables(grammar)
    instance = normalize(lifted)
    product = _ReduceProduct(
        grammar,
        reducer,
        compile_reduce_pda(lifted, instance, reducer),
        instance,
    )
    _REDUCE_CACHE[key] = product
    return product


def _model_product(
    grammar: IrAst, fold: ModelFold, bits: int = ORIGIN_BITS
) -> _ModelProduct:
    """The compiled instance product for ``(grammar, fold, bits)``, memoised.

    Keyed by identity plus the packing tier ``bits`` (the Earley tables pack
    at it). The PDA half is tier-independent but rides the key — a second
    tier for the same pair only ever compiles for a beyond-first-tier input.
    """
    key = (id(grammar), id(fold), bits)
    cached = _MODEL_CACHE.get(key)
    if cached is not None and cached.grammar is grammar and cached.fold is fold:
        return cached
    lifted = lift_optional_nullables(grammar)
    instance = normalize(lifted)
    product = _ModelProduct(
        grammar,
        fold,
        compile_pda(lifted, instance, fold.baked),
        instance,
        collapsed_fold_tables(instance, fold, bits),
    )
    _MODEL_CACHE[key] = product
    return product


# ── the public product entries ─────────────────────────────────────────────


def parse_reduced(grammar: IrAst, text: str, reducer: Reducer) -> IrSelf:
    """Parse ``text`` to its reduction — PDA-first, fused Earley completion.

    The engine's REDUCE product over any authored ``(grammar, reducer)`` pair:
    a flavour self-grammar folding grammar text to an ``IrAst``, or any other
    grammar whose reducer folds its documents to values — a reducer is
    something any grammar can have. Lifting, normalisation and PDA compilation
    are internal, memoised per ``(grammar, reducer)`` identity. Each parse
    runs the reduce PDA first and, on any :class:`PdaFail`, completes on the
    fused Earley reduce over the same lifted, normalised grammar the PDA
    compiled from. Result-shape narrowing (grammar text must fold to an
    ``IrAst``) belongs to the caller's boundary (``compile.parse_grammar``),
    not to the product.

    :param grammar: The authored grammar.
    :param text: The input to parse.
    :param reducer: The grammar's reduction policy.
    :returns: Whatever the reducer's top body builds.
    :raises UnsupportedConstructError: When ``reducer`` is not a
        :class:`Reducer`, or ``text`` does not parse / parses ambiguously on
        the Earley completion.
    """
    product = _reduce_product(grammar, reducer)
    try:
        return cast(IrSelf, parse_pda(product.pda, text, None))
    except PdaFail:
        return cast(IrSelf, earley_reduce(product.earley_grammar, text, reducer))


def parse_model[M](grammar: IrAst, text: str, fold: ModelFold[M]) -> M:
    """Parse instance ``text`` to a model — PDA-first, Earley + fold completion.

    Takes the **authored** codegen grammar; lifting, normalisation, PDA and
    run-collapsed table compilation are internal, memoised per ``(grammar,
    fold)`` identity plus the packing tier the input's size picks
    (:func:`~lexic.parsing.earley.tables.tier_for`). Each parse runs the model
    PDA first and, on any :class:`PdaFail`, completes on ``parse_first`` +
    ``fold``.

    :param grammar: The authored codegen grammar.
    :param text: The instance input to parse.
    :param fold: The positional ParseTree → model fold producing ``M``.
    :returns: The model the start rule folds to.
    :raises UnsupportedConstructError: If ``text`` does not parse.
    """
    product = _model_product(grammar, fold, tier_for(len(text)))
    try:
        return cast(M, parse_pda(product.pda, text, fold))
    except PdaFail:
        return earley_model(product.instance_grammar, text, fold, product.tables)
