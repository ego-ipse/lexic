"""Tests for the sole model product and its per-identity memoisation."""

from __future__ import annotations

from typing import Any, cast

import pytest

from lexic.compile import Vocabulary, compile_ast, compile_text, reset_cache_for_tests
from lexic.compile.artifact import _reduce_entry, _sub_run
from lexic.compile.reduce.variant import reachable_rules
from lexic.compile.reduction import RunSpec, derive_reduction
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.ebnf import EBNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import (
    DROP,
    YIELD,
    IrAlternation,
    IrAst,
    IrChr,
    IrItem,
    IrLiteral,
    IrMap,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
    IrStr,
    IrTokenizer,
    IrTuple,
    Reducer,
)
from lexic.model import GrammarModel
from lexic.parsing.earley.kernel.tables import atoms as tables_mod
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import (
    _MODEL_CACHE,
    _model_product,
    earley_model,
    parse_model,
    pda_tables,
    reset_product_cache,
)
from tests.reduce_helpers import reduce_text
from tests.unit.lexic.parsing.parsing_helpers import compiled

# ── the Earley completions (route-forcing seam) ────────────────────────────


def test_artifact_reduce_returns_ir_ast():
    """The compiled self-grammar artefact reduces grammar text to IR."""
    text = 'root ::= "x" | "y"\n'
    ast = reduce_text(GBNF_FLAVOUR.grammar, text, GBNF_FLAVOUR.reducer)
    assert isinstance(ast, IrAst)
    assert [r.name for r in ast.rules] == ["root"]


def test_earley_model_returns_model_and_round_trips():
    """earley_model parses instance text over the instance grammar + fold,
    with pre-built run-collapsed tables supplied."""
    cg = compiled()
    product = _model_product(cg.codegen_grammar, cg.fold)
    model = earley_model(product.instance_grammar, "ab", cg.fold, product.tables)
    assert isinstance(model, GrammarModel)
    assert model.to_text() == "ab"


def test_earley_model_compiles_its_own_tables_when_none_supplied():
    """earley_model's tables parameter is optional — omitting it compiles plain
    (non-collapsed) tables internally rather than requiring the caller to."""
    cg = compiled()
    product = _model_product(cg.codegen_grammar, cg.fold)
    model = earley_model(product.instance_grammar, "ab", cg.fold)
    assert isinstance(model, GrammarModel)
    assert model.to_text() == "ab"


# ── the product entries agree with their Earley completions ────────────────


def test_public_and_direct_artifact_reduction_agree():
    """The public grammar reader and direct artefact capability are one path."""
    text = 'root ::= "x" "y" | "z"\n'
    got = reduce_text(GBNF_FLAVOUR.grammar, text, GBNF_FLAVOUR.reducer)
    expected = compile_ast(GBNF_FLAVOUR.grammar).reduce(
        text, GBNF_FLAVOUR.reducer, cores=1
    )
    assert got == expected


def test_parse_model_matches_earley_model_completion():
    """parse_model (PDA-first) and earley_model (the forced completion) agree
    on the same instance-text input."""
    cg = compiled()
    got = parse_model(cg.codegen_grammar, "ab", cg.fold)
    product = _model_product(cg.codegen_grammar, cg.fold)
    expected = earley_model(product.instance_grammar, "ab", cg.fold, product.tables)
    assert isinstance(got, GrammarModel)
    assert isinstance(expected, GrammarModel)
    assert got.semantic_dump() == expected.semantic_dump()
    assert got.to_text() == "ab"


def test_reduce_variant_handles_optional_nullable_rules():
    """The one-path variant preserves an optional nullable self-grammar case."""
    ast = reduce_text(GBNF_FLAVOUR.grammar, 'root ::= ("x" |)?\n', GBNF_FLAVOUR.reducer)
    assert isinstance(ast, IrAst)


# ── per-identity memoisation ────────────────────────────────────────────────


def test_reduce_product_is_the_same_object_for_the_same_identity():
    """The derived variant entry is memoised per artefact and reducer."""
    artifact = compile_ast(GBNF_FLAVOUR.grammar)
    first = _reduce_entry(artifact, GBNF_FLAVOUR.reducer)
    second = _reduce_entry(artifact, GBNF_FLAVOUR.reducer)
    assert first is second


def test_reduce_variant_elides_noise_models_without_changing_source_product():
    """Recognition twins belong only to the reducer-derived variant artefact."""
    artifact = compile_ast(JSON_GRAMMAR)
    entry = _reduce_entry(artifact, JSON_REDUCER)
    elide = derive_reduction(JSON_GRAMMAR, JSON_REDUCER).elide
    assert elide
    roots = frozenset(f"{name}-sk" for name in elide)
    assert roots <= {str(rule.name) for rule in entry.variant.grammar.rules}
    omitted = reachable_rules(entry.variant.codegen_grammar, roots)
    assert omitted
    assert omitted.isdisjoint(entry.variant.fold.config)
    assert elide <= artifact.fold.config.keys()
    assert not any(name.endswith("-sk") for name in artifact.fold.config)


def test_conditional_run_subparse_never_constructs_a_dropped_descendant():
    """Named escape subgrammars apply the same full-subtree elision as main."""
    grammar = IrAst(
        IrSeq(
            IrRule("root", IrAlternation(IrSequence(IrItem(IrRuleRef("element"))))),
            IrRule(
                "element",
                IrAlternation(
                    IrSequence(IrItem(IrRuleRef("keep")), IrItem(IrRuleRef("drop")))
                ),
            ),
            IrRule("keep", IrAlternation(IrSequence(IrItem(IrLiteral("a"))))),
            IrRule(
                "drop",
                IrAlternation(IrSequence(IrItem(IrRuleRef("noise")))),
                False,
            ),
            IrRule("noise", IrAlternation(IrSequence(IrItem(IrLiteral("!"))))),
        ),
        "root",
    )
    reducer = Reducer(
        default=YIELD,
        noise=IrMap(
            *(
                IrTuple(IrRuleRef(name), DROP if name == "drop" else YIELD)
                for name in (
                    "root",
                    "element-run",
                    "element",
                    "keep",
                    "drop",
                    "noise",
                )
            )
        ),
    )
    escape = _sub_run(
        compile_ast(grammar),
        reducer,
        "element-run",
        RunSpec(frozenset({"!"}), "element"),
    )
    variant = cast(Any, escape.parse).func.__self__
    omitted = reachable_rules(variant.codegen_grammar, frozenset({"drop-sk"}))
    assert omitted == {"drop-sk", "noise-sk"}
    assert omitted.isdisjoint(variant.fold.config)
    assert escape.fold.plan.aliases == {
        "drop-sk": "drop",
        "noise-sk": "noise",
    }

    def forbidden(**_kwargs: object) -> object:
        raise AssertionError("a dropped run descendant was constructed")

    original = variant.fold.config["noise"]
    variant.fold.config["noise"] = original._replace(ctor=forbidden, fast=None)
    product = _model_product(variant.codegen_grammar, variant.fold)
    assert earley_model(product.instance_grammar, "a!", variant.fold, product.tables)
    assert pda_model(product.pda, "a!", variant.fold)


def test_model_product_is_the_same_object_for_the_same_identity():
    """Two calls with the identical (grammar, fold) objects return the SAME
    compiled product — no recompilation."""
    cg = compiled()
    first = _model_product(cg.codegen_grammar, cg.fold)
    second = _model_product(cg.codegen_grammar, cg.fold)
    assert first is second


def test_reset_product_cache_forces_reduce_product_recompilation():
    """The compile reset clears the derived reduction-entry cache."""
    artifact = compile_ast(GBNF_FLAVOUR.grammar)
    first = _reduce_entry(artifact, GBNF_FLAVOUR.reducer)
    reset_cache_for_tests()
    second = _reduce_entry(artifact, GBNF_FLAVOUR.reducer)
    assert first is not second
    assert first.reducer is second.reducer


def test_reset_product_cache_forces_model_product_recompilation():
    """reset_product_cache drops the model cache — the next call for the same
    identity recompiles rather than reusing the stale product."""
    cg = compiled()
    first = _model_product(cg.codegen_grammar, cg.fold)
    reset_product_cache()
    second = _model_product(cg.codegen_grammar, cg.fold)
    assert first is not second
    assert first.grammar is second.grammar
    assert first.fold is second.fold


# ── pda_tables — the public predictive-tables accessor ─────────────────────


def test_pda_tables_returns_pda_tables():
    """pda_tables returns the compiled PdaTables for a (grammar, fold) pair."""
    cg = compiled()
    assert isinstance(pda_tables(cg.codegen_grammar, cg.fold), PdaTables)


def test_pda_tables_is_the_model_products_pda():
    """pda_tables is identity-memoised with the parse path — the same object
    _model_product's .pda field holds."""
    cg = compiled()
    assert (
        pda_tables(cg.codegen_grammar, cg.fold)
        is _model_product(cg.codegen_grammar, cg.fold).pda
    )


def test_pda_tables_is_the_same_object_across_calls():
    """Two calls with the identical (grammar, fold) return the SAME tables —
    no recompilation."""
    cg = compiled()
    first = pda_tables(cg.codegen_grammar, cg.fold)
    second = pda_tables(cg.codegen_grammar, cg.fold)
    assert first is second


def test_reset_product_cache_forces_pda_tables_recompilation():
    """reset_product_cache drops the model cache pda_tables reads too — a
    fresh object comes back for the same identity."""
    cg = compiled()
    first = pda_tables(cg.codegen_grammar, cg.fold)
    reset_product_cache()
    second = pda_tables(cg.codegen_grammar, cg.fold)
    assert first is not second


# ── boundary checks ─────────────────────────────────────────────────────────


def test_parse_reduced_returns_the_reduction_unnarrowed():
    """An artefact reduction may return a value other than ``IrAst``."""
    doc = reduce_text(JSON_GRAMMAR, '{"a": 1}', JSON_REDUCER)
    assert isinstance(doc, IrMap)


def test_flavour_reduction_is_an_ir_ast():
    """A flavour's reduction still narrows to IrAst at the compile boundary —
    the product itself passes it through unnarrowed."""
    ast = reduce_text(GBNF_FLAVOUR.grammar, 'root ::= "x"\n', GBNF_FLAVOUR.reducer)
    assert isinstance(ast, IrAst)


def test_artifact_reduce_raises_on_a_non_reducer():
    """The artefact rejects a non-Reducer before attempting a parse."""
    with pytest.raises(UnsupportedConstructError):
        compile_ast(GBNF_FLAVOUR.grammar).reduce(
            'root ::= "x"\n', cast(Reducer, "not-a-reducer")
        )


# ── packing-tier selection ──────────────────────────────────────────────────


def test_model_product_is_distinct_per_tier():
    """The model cache keys the packing tier — per-tier products coexist and
    each replays from its own key."""
    cg = compiled()
    small = _model_product(cg.codegen_grammar, cg.fold, 8)
    default = _model_product(cg.codegen_grammar, cg.fold)
    assert small is not default
    assert small.tables.packing.bits == 8
    assert _model_product(cg.codegen_grammar, cg.fold, 8) is small


def test_parse_model_picks_the_tier_by_input_size(monkeypatch):
    """parse_model keys its product at tier_for(len(text)) — under a small
    first tier a short input lands on the small-tier cache key."""
    cg = compiled()
    monkeypatch.setattr(tables_mod, "TIERS", (8, 28))
    reset_product_cache()
    model = parse_model(cg.codegen_grammar, "ab", cg.fold)
    assert model.to_text() == "ab"
    assert (id(cg.codegen_grammar), id(cg.fold), 8) in _MODEL_CACHE
    reset_product_cache()


# ── the reduce path decides ambiguity the same way everything else does ──


def test_artifact_reduce_accepts_derivations_that_reduce_to_one_value():
    """Two derivations, one meaning, is not an ambiguity — anywhere.

    The islands path stopped counting derivations and started comparing the
    values they build. The reduce path kept counting, and the cost was the
    whole EBNF fallback: that self-grammar has adjacent nullable `ws` slots, so
    EVERY whitespace-carrying EBNF file derives at least two ways and reduced
    to exactly one value. Earley refused all of them, which left `parse_grammar`
    for EBNF riding entirely on the PDA never escaping.
    """
    got = reduce_text(EBNF_FLAVOUR.grammar, "a = b ;\n", EBNF_FLAVOUR.reducer)
    assert isinstance(got, IrAst)
    assert [str(r.name) for r in got.rules] == ["a"]


# ── the token route asks the meaning question too ─────────────────────────

_TOKEN_ARM_CHOICE = "root ::= viaone | viatwo\nviaone ::= <a>\nviatwo ::= <a>\n"
"""Two arms over the SAME token. Segmentation is deterministic, so a token-route
ambiguity can only come from the grammar — this is the smallest one."""


def _token_vocabulary() -> Vocabulary:
    """A two-entry vocabulary. A vocab is a parameter, not a fetched artefact."""
    encode = IrMap(
        *(IrTuple(IrStr(t), IrChr(i)) for t, i in {"<a>": 0, "<b>": 1}.items())
    )
    return Vocabulary(IrTokenizer.from_vocab("tokens", encode))


def test_the_token_route_refuses_an_arm_choice_like_the_char_route_does():
    """A token grammar must not silently pick between two meanings.

    `token_model` built with a bail-mode `FastTree` and folded, asking nothing.
    Token grammars island the PDA by construction, so that Earley route is the
    WHOLE parse — there was no second route to catch it. The identical grammar
    shape was refused on the char route and answered `Viaone` here, and a caller
    could not tell a choice had been made for them.
    """
    token_grammar = compile_text(
        _TOKEN_ARM_CHOICE, vocabulary=_token_vocabulary(), cache_key="tok-arm-choice"
    )
    assert token_grammar.tokens.segmented, "this must exercise the token route"
    with pytest.raises(UnsupportedConstructError, match="ambiguous"):
        token_grammar.parse("<a>")


def test_a_resolver_settles_the_token_route_too():
    """The opt-out reaches the token route, so it is not a char-only promise."""
    token_grammar = compile_text(
        _TOKEN_ARM_CHOICE, vocabulary=_token_vocabulary(), cache_key="tok-arm-resolve"
    )
    picked = token_grammar.parse("<a>", resolve=lambda first, _other: first)
    assert picked.to_text() == "<a>"


# ── the refusal readout (both engines declined) ───────────────────────────


def test_a_refused_parse_carries_where_it_stopped_and_what_it_wanted():
    """The public refusal names the position, the rule and the expected chars.

    The readout exists so a caller can DRAW a refusal — a caret, the rule, the
    continuations. Before it, the position lived only in the predictive route's
    prose and never escaped the product seam at all.
    """
    grammar = compile_text('root ::= "abc" digit\ndigit ::= [0-9]\n')
    with pytest.raises(UnsupportedConstructError) as caught:
        grammar.parse("abcX")
    readout = caught.value.readout
    assert readout is not None
    assert readout.pos == 3
    assert readout.rule == "digit"
    assert readout.expected == tuple("0123456789")
    assert readout.negated is False
    assert readout.undecidable is False


def test_a_refusal_keeps_its_message_unchanged():
    """The gated engine owns the verdict — the readout is additive, not a rewrite."""
    grammar = compile_text('root ::= "abc" digit\ndigit ::= [0-9]\n')
    with pytest.raises(UnsupportedConstructError, match="does not derive from 'root'"):
        grammar.parse("abcX")


def test_an_accepted_parse_raises_nothing_to_carry_a_readout():
    """A readout is a property of a refusal, not of every parse."""
    grammar = compile_text('root ::= "abc" digit\ndigit ::= [0-9]\n')
    assert grammar.parse("abc7").to_text() == "abc7"


def test_a_negated_expected_set_keeps_its_polarity():
    """A co-finite expectation is reported as an EXCLUSION, never enumerated."""
    grammar = compile_text('root ::= "<" body ">"\nbody ::= [^<>]+\n')
    with pytest.raises(UnsupportedConstructError) as caught:
        grammar.parse("<>")
    readout = caught.value.readout
    assert readout is not None
    assert readout.negated is True
    assert "<" in readout.expected and ">" in readout.expected
