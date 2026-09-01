"""Property-based round-trip tests: generate → parse → to_text == original.

Integers are used as RNG seeds rather than grammar-aware strategies; hypothesis
shrinking navigates numerically not structurally, but failing seeds are
reproducible and replayable.
"""

from __future__ import annotations

import random
from typing import cast

import hypothesis.strategies as st
from hypothesis import HealthCheck, given, settings

from lexic.compile import compile_from_path
from lexic.generate import generate
from lexic.model import GrammarModel
from lexic.parsing.products import _model_product, earley_model
from tests.paths import GROUND_TRUTH as _GRAMMAR_DIR


def roundtrip(grammar: str, specs: dict, seed: int) -> None:
    """Generate from ``specs`` at ``seed`` and assert a full parse round-trip."""
    rng = random.Random(seed)
    text = generate("root", specs, rng=rng, max_depth=4)
    if not text:
        # A star/optional-rooted rule (e.g. c's root ::= (declaration)*) can
        # roll an empty expansion; skip the trivial empty round-trip rather
        # than parsing "". (The grammars routed through here never do, but the
        # guard keeps the helper honest for any that could.)
        return
    gpath = _GRAMMAR_DIR / f"{grammar}.gbnf"
    inst = compile_from_path(gpath).parse(text)
    assert inst.to_text() == text, (
        f"Round-trip failed [{grammar}] seed={seed}:\n"
        f"  generated: {text!r}\n"
        f"  to_text:   {inst.to_text()!r}"
    )
    # Second parse verifies parse() is deterministic: same input → same dump()
    inst2 = compile_from_path(gpath).parse(inst.to_text())
    assert inst.dump() == inst2.dump()


# parse() recompiles the grammar into model classes on every call (~20ms each);
# suppress_health_check=[HealthCheck.too_slow] acknowledges this known cost.


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_arithmetic_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    """Arithmetic grammar round-trips for random seeds."""
    roundtrip("arithmetic", all_grammar_specs["arithmetic"], seed)


# The public parse() above is PDA-first (see compile.py's
# CompiledGrammar.parse) — a future PDA regression could in principle mask an
# engine-side round-trip break by always falling back before the broken engine
# path is ever exercised. This canary forces the Earley route directly (the
# engine's ``earley_model`` completion over the instance grammar) on one
# grammar, budget-capped well below the public-parse property above, so the
# engine's own round-trip guarantee stays independently proven in CI.
@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow])
def test_arithmetic_roundtrip_engine_forced(seed: int, all_grammar_specs: dict) -> None:
    """Engine-forced canary: arithmetic round-trips through the forced Earley route."""
    rng = random.Random(seed)
    text = generate("root", all_grammar_specs["arithmetic"], rng=rng, max_depth=4)
    if not text:
        return
    cg = compile_from_path(_GRAMMAR_DIR / "arithmetic.gbnf")
    product = _model_product(cg.codegen_grammar, cg.product)
    inst = cast(
        GrammarModel,
        earley_model(product.instance_grammar, text, cg.fold, product.tables),
    )
    assert inst.to_text() == text, (
        f"Engine-forced round-trip failed [arithmetic] seed={seed}:\n"
        f"  generated: {text!r}\n"
        f"  to_text:   {inst.to_text()!r}"
    )


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_list_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    """List grammar round-trips for random seeds."""
    roundtrip("list", all_grammar_specs["list"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_japanese_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    """Japanese grammar round-trips for random seeds."""
    roundtrip("japanese", all_grammar_specs["japanese"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_chess_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    """Chess grammar round-trips for random seeds."""
    roundtrip("chess", all_grammar_specs["chess"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_json_ws_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    """JSON-with-whitespace grammar round-trips for random seeds."""
    roundtrip("json_ws", all_grammar_specs["json_ws"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
def test_json_arr_roundtrip(seed: int, all_grammar_specs: dict) -> None:
    """JSON-array grammar round-trips for random seeds."""
    roundtrip("json_arr", all_grammar_specs["json_arr"], seed)


@given(seed=st.integers(min_value=0, max_value=2**32 - 1))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
def test_c_statement_roundtrip(seed: int, c_statement_grammar: tuple) -> None:
    """C statement surface round-trips for random seeds.

    Generation is driven from "statement", not "root" — see the
    ``c_statement_grammar`` fixture docstring for why "root" gives only thin,
    mostly-empty coverage for this grammar.
    """
    cg, specs = c_statement_grammar
    rng = random.Random(seed)
    text = generate("statement", specs, rng=rng, max_depth=4)
    if not text:
        return
    inst = cg.parse(text)
    assert inst.to_text() == text, (
        f"Round-trip failed [c statement] seed={seed}:\n"
        f"  generated: {text!r}\n"
        f"  to_text:   {inst.to_text()!r}"
    )
    inst2 = cg.parse(inst.to_text())
    assert inst.dump() == inst2.dump()
