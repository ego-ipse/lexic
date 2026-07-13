"""The two product entries — grammar-text → IR, instance text → model.

Both take the **authored** grammar and own the whole compilation pipeline
internally: lift + normalise, compile the predictive PDA (and, for the model
product, the run-collapsed Earley tables), all memoised per
**(grammar identity, reducer/fold identity)** — the compiled tables bake the
reducer plan / fold records, so grammar identity alone is a wrong key. Each
parse runs the PDA first and completes on the Earley engine on any
:class:`~lexic.parsing.pda.runtime.PdaFail`; :class:`PdaFail` never escapes.

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

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrSelf, IrStr, IrTuple
from lexic.ir.nodes import IrAst
from lexic.parsing.earley.engine import PARSE_FIRST, PARSE_REDUCED, EarleyParser
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce import Reducer
from lexic.parsing.earley.tables import ParserTables
from lexic.parsing.fold import ModelFold, collapsed_fold_tables, lift_optional_nullables
from lexic.parsing.pda.clones import PdaTables, compile_pda, compile_reduce_pda
from lexic.parsing.pda.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime import PdaFail

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


def earley_model(
    grammar: IrAst, text: str, fold: ModelFold, tables: ParserTables | None = None
) -> object:
    """Parse ``text`` and fold it to a model through the Earley engine.

    The instance product's Earley completion — ``parse_first`` (deterministic
    under ambiguity, since an all-nullable arm would otherwise make the empty
    match ambiguous) folded through ``fold``.

    :param grammar: The Earley-normalised instance grammar.
    :param text: The input string.
    :param fold: The positional ParseTree → model fold.
    :param tables: Optional pre-built run-collapsed tables for ``grammar``.
    :returns: The model the start rule folds to.
    :raises UnsupportedConstructError: If ``text`` does not parse.
    """
    args = (IrStr(text),) if tables is None else (IrStr(text), tables)
    tree = PARSE_FIRST.eval(EarleyParser(), grammar, IrTuple(*args))
    return fold.apply(tree)


# ── compiled-product records + per-identity memoisation ────────────────────


@dataclass(frozen=True)
class _ReduceProduct:
    """A grammar-text product compiled once — the reduce PDA + Earley grammar.

    :ivar grammar: The authored grammar (held to pin its identity key).
    :ivar reducer: The reduction policy (held to pin its identity key).
    :ivar pda: The reduce PDA (immediate-PdaFail start ⇒ Earley every parse).
    :ivar earley_grammar: The (un-lifted) normalised grammar the completion runs.
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
_MODEL_CACHE: dict[tuple[int, int], _ModelProduct] = {}


def reset_product_cache() -> None:
    """Test seam: drop the per-identity product caches."""
    _REDUCE_CACHE.clear()
    _MODEL_CACHE.clear()


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
        normalize(grammar),
    )
    _REDUCE_CACHE[key] = product
    return product


def _model_product(grammar: IrAst, fold: ModelFold) -> _ModelProduct:
    """The compiled instance product for ``(grammar, fold)``, memoised by identity."""
    key = (id(grammar), id(fold))
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
        collapsed_fold_tables(instance, fold),
    )
    _MODEL_CACHE[key] = product
    return product


# ── the public product entries ─────────────────────────────────────────────


def parse_reduced(grammar: IrAst, text: str, reducer: Reducer) -> IrSelf:
    """Parse grammar-text ``text`` to IR — PDA-first, Earley reduce completion.

    Takes the **authored** grammar; lifting, normalisation and PDA compilation
    are internal, memoised per ``(grammar, reducer)`` identity. Each parse runs
    the reduce PDA first and, on any :class:`PdaFail`, completes on the fused
    Earley reduce over the (un-lifted) normalised grammar.

    :param grammar: The authored grammar (e.g. a flavour's self-grammar).
    :param text: The grammar source to parse.
    :param reducer: The flavour's reduction policy.
    :returns: The reduced IR.
    :raises UnsupportedConstructError: When ``reducer`` is not a :class:`Reducer`,
        or ``text`` does not parse / parses ambiguously on the completion.
    """
    product = _reduce_product(grammar, reducer)
    try:
        return _as_ir(parse_pda(product.pda, text, None))
    except PdaFail:
        return earley_reduce(product.earley_grammar, text, reducer)


def parse_model(grammar: IrAst, text: str, fold: ModelFold) -> object:
    """Parse instance ``text`` to a model — PDA-first, Earley + fold completion.

    Takes the **authored** codegen grammar; lifting, normalisation, PDA and
    run-collapsed table compilation are internal, memoised per ``(grammar,
    fold)`` identity. Each parse runs the model PDA first and, on any
    :class:`PdaFail`, completes on ``parse_first`` + ``fold``.

    :param grammar: The authored codegen grammar.
    :param text: The instance input to parse.
    :param fold: The positional ParseTree → model fold.
    :returns: The model the start rule folds to.
    :raises UnsupportedConstructError: If ``text`` does not parse.
    """
    product = _model_product(grammar, fold)
    try:
        return parse_pda(product.pda, text, fold)
    except PdaFail:
        return earley_model(product.instance_grammar, text, fold, product.tables)


def _as_ir(value: object) -> IrSelf:
    """Narrow a reduce PDA result to :class:`IrSelf` (the reduce product's type)."""
    if not isinstance(value, IrSelf):
        raise UnsupportedConstructError(
            f"parse_reduced: PDA produced {type(value).__name__!r}, not IR"
        )
    return value
