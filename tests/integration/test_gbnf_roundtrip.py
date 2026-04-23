"""GBNF round-trip tests: grammar → IR → GBNFEmitter → re-parse → same rule names."""

from __future__ import annotations
from pathlib import Path
import pytest
from lexic.grammars.gbnf.parser import parse_gbnf
from lexic.codegen.ir_builder import IRBuilder
from lexic.grammars.gbnf.emitter import GBNFEmitter

GRAMMAR_DIR = Path(__file__).parent.parent.parent / "resources" / "ground_truth"
ALL_GRAMMARS = ["arithmetic", "c", "chess", "japanese", "json_arr", "json_ws", "list"]


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_emitted_gbnf_parses(grammar: str):
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    specs = IRBuilder(parse_gbnf(text)).build()
    emitted = GBNFEmitter(specs).emit()
    assert emitted.strip()
    rt_rules = parse_gbnf(emitted)
    assert len(rt_rules) > 0


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_emitted_gbnf_has_original_rule_names(grammar: str):
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    original_rules = parse_gbnf(text)
    specs = IRBuilder(original_rules).build()
    emitted = GBNFEmitter(specs).emit()
    rt_rules = parse_gbnf(emitted)
    original_names = {r.name for r in original_rules}
    rt_names = {r.name for r in rt_rules}
    assert original_names <= rt_names, f"Missing rules: {original_names - rt_names}"


@pytest.mark.parametrize("grammar", ALL_GRAMMARS)
def test_emitted_gbnf_same_rule_count(grammar: str):
    text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    specs = IRBuilder(parse_gbnf(text)).build()
    emitted = GBNFEmitter(specs).emit()
    rt_specs = IRBuilder(parse_gbnf(emitted)).build()
    assert len(specs) == len(rt_specs), (
        f"Rule count mismatch for {grammar}: original={len(specs)}, roundtrip={len(rt_specs)}"
    )
