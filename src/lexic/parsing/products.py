"""The model product entry — text → a compiled grammar's model.

It takes the **authored** grammar and owns the compilation internally: lift +
normalise, predictive PDA, and run-collapsed Earley tables, memoised per
**(grammar identity, fold identity, packing tier)**. Each parse runs the PDA
first and completes on the Earley engine on any
:class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaFail`; :class:`PdaFail` never escapes.

The Earley model completion is the route-forcing seam. ``earley_reduce``
remains temporarily for the 1e differential while the retired fused twin is
deleted in 1g; it is not a product entry.

A leaf inside ``lexic.parsing``: imports the Earley engine and the PDA compiler/
runtime by public name; ``__init__`` re-exports the product entries and the
Earley completions at the package root, the sole surface ``compile.py`` (and
every other consumer) sees.
"""

from __future__ import annotations

from dataclasses import dataclass

from lexic.exceptions import Refusal, UnsupportedConstructError
from lexic.ir import IrAst, IrSelf, IrStr, IrTuple
from lexic.parsing.earley.engine import PARSE_REDUCED, EarleyParser, first_meaning
from lexic.parsing.earley.kernel.forest.ambiguity import (
    AmbiguityPolicy,
    Resolver,
    another_meaning,
)
from lexic.parsing.earley.kernel.forest.fasttree import FastTree, ParseTree
from lexic.parsing.earley.kernel.forest.readout import accept_handle, accept_item
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ORIGIN_BITS, ParserTables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce.reducer import Reducer
from lexic.parsing.earley.tokenscan import TokenKernel
from lexic.parsing.fold import ModelFold, collapsed_fold_tables, lift_optional_nullables
from lexic.parsing.pda.compiler.clones import compile_pda
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import ProbeFork
from lexic.parsing.pda.runtime.kernel.kernel import PdaFail
from lexic.parsing.pda.runtime.kernel.reduce_runtime import pda_model

__all__ = [
    "parse_model",
    "earley_reduce",
    "earley_model",
    "pda_tables",
    "reset_product_cache",
]


# ── the Earley completions (also the tests' route-forcing seam) ────────────


def earley_reduce(grammar: IrAst, text: str, reducer: Reducer) -> IrSelf:
    """Parse ``text`` and fold it straight to IR in one Earley pass.

    The grammar-text product's Earley completion — ``reducer.apply(parse(...))``
    fused (no intermediate :class:`~lexic.parsing.earley.kernel.forest.forest.ParseTree` in the
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
    grammar: IrAst,
    text: str,
    fold: ModelFold[M],
    tables: ParserTables | None = None,
    resolve: Resolver | None = None,
) -> M:
    """Parse ``text`` and fold it to a model through the Earley engine.

    The instance product's Earley completion — :func:`~lexic.parsing.earley
    .engine.first_meaning` folded through ``fold``. The fold is also the gate's
    ``build``: a span whose derivations fold to DIFFERENT models is refused
    unless ``resolve`` settles it, the same question the PDA's island sub-parse
    asks, so the two engines refuse (or resolve) identically instead of each
    quietly taking its own "first".

    :param grammar: The Earley-normalised instance grammar.
    :param text: The input string.
    :param fold: The positional ParseTree → model fold producing ``M``.
    :param tables: Optional pre-built run-collapsed tables for ``grammar``.
    :param resolve: The caller's deterministic answer to an ambiguity;
        ``None`` refuses one.
    :returns: The model the start rule folds to.
    :raises UnsupportedConstructError: If ``text`` does not parse, or parses to
        two different models with no resolver supplied.
    """
    policy = AmbiguityPolicy(fold.apply, resolve)
    tree = first_meaning(EarleyParser(), grammar, text, tables, policy)
    return fold.apply(tree)


def token_model[M](
    grammar: IrAst,
    text: str,
    fold: ModelFold[M],
    bounds: dict[int, tuple[int, int]],
    resolve: Resolver | None = None,
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
    :param resolve: The caller's deterministic resolver, or ``None`` to refuse
        an ambiguous span — the same contract the char route offers.
    :returns: The model the start rule folds to.
    :raises UnsupportedConstructError: If ``text`` does not parse, or means two
        things and no resolver was supplied.
    """
    tables = _token_tables(grammar, tier_for(len(text)))
    kernel = TokenKernel(tables, text, bounds, record_links=True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError(
            "parsing: input does not parse the token grammar"
        )
    handle = accept_handle(kernel)
    # RESOLVING mode, as the char route uses. Bail mode declined on exactly the
    # inputs at issue and reported them as "no token derivation" — so an
    # ambiguous span and a plain SPLIT both died claiming nothing derived.
    tree = FastTree(kernel, {}).build(handle)
    if not isinstance(tree, ParseTree):
        raise UnsupportedConstructError("parsing: no token derivation")
    witness = another_meaning(kernel, handle, fold.apply, tree)
    if witness is None:
        return fold.apply(tree)
    if resolve is None:
        raise UnsupportedConstructError(
            "parsing: ambiguous input — two derivations that mean different "
            "things; supply a resolver to choose between them"
        )
    return fold.apply(resolve(tree, witness))


# ── compiled-product records + per-identity memoisation ────────────────────


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


_MODEL_CACHE: dict[tuple[int, int, int], _ModelProduct] = {}
_TOKEN_TABLES: dict[tuple[int, int], tuple[IrAst, ParserTables]] = {}


def reset_product_cache() -> None:
    """Test seam: drop the per-identity product caches."""
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


def _refused(
    fail: PdaFail, refusal: UnsupportedConstructError
) -> UnsupportedConstructError:
    """``refusal``, carrying the readout the predictive route already had.

    Both engines have now declined, so the input genuinely does not parse (or
    parses two ways) and the caller deserves more than words. The gated engine
    owns the VERDICT — its message is unchanged — but the predictive route is
    the one that knows how far it got and what it wanted there, so its readout
    is what gets attached. ``ProbeFork`` marks the readout ``undecidable``: the
    PDA did not fail there, it bailed, so the refusal is about ambiguity rather
    than about a character the grammar cannot derive.

    A refusal that already carries a readout keeps it — the inner seam was
    closer to the question than this one.
    """
    if refusal.readout is not None:
        return refusal
    return UnsupportedConstructError(
        str(refusal),
        Refusal(
            pos=fail.pos,
            rule=fail.rule,
            expected=fail.expected,
            negated=fail.negated,
            undecidable=isinstance(fail, ProbeFork),
        ),
    )


def parse_model[M](
    grammar: IrAst, text: str, fold: ModelFold[M], resolve: Resolver | None = None
) -> M:
    """Parse instance ``text`` to a model — PDA-first, Earley + fold completion.

    Takes the **authored** codegen grammar; lifting, normalisation, PDA and
    run-collapsed table compilation are internal, memoised per ``(grammar,
    fold)`` identity plus the packing tier the input's size picks
    (:func:`~lexic.parsing.earley.kernel.tables.tier_for`). Each parse runs the model
    PDA first and, on any :class:`PdaFail`, completes on the gated Earley
    first derivation + ``fold``. A span whose derivations mean two different
    models is refused by BOTH routes unless ``resolve`` settles it — the same
    resolver reaches whichever engine ends up choosing.

    :param grammar: The authored codegen grammar.
    :param text: The instance input to parse.
    :param fold: The positional ParseTree → model fold producing ``M``.
    :param resolve: The caller's deterministic answer to an ambiguity;
        ``None`` refuses one.
    :returns: The model the start rule folds to.
    :raises UnsupportedConstructError: If ``text`` does not parse, or parses to
        two different models with no resolver supplied.
    """
    product = _model_product(grammar, fold, tier_for(len(text)))
    try:
        return pda_model(product.pda, text, fold, resolve=resolve)
    except PdaFail as fail:
        try:
            return earley_model(
                product.instance_grammar, text, fold, product.tables, resolve
            )
        except UnsupportedConstructError as refusal:
            raise _refused(fail, refusal) from None


def pda_tables(grammar: IrAst, fold: ModelFold, bits: int = ORIGIN_BITS) -> PdaTables:
    """The instance product's compiled PDA — the artefact's predictive half.

    The public reach onto what :func:`parse_model` drives: identity-memoised
    with the parse path, so the tables a parse compiled are the exact object
    returned (and a first call compiles once and shares forward). This is the
    trace substrate a :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel`
    subclass runs over.

    :param grammar: The authored codegen grammar.
    :param fold: The positional fold the product is keyed with.
    :param bits: The packing tier the memo key rides (the PDA half itself is
        tier-independent).
    :returns: The compiled :class:`~lexic.parsing.pda.compiler.tables.PdaTables`.
    """
    return _model_product(grammar, fold, bits).pda
