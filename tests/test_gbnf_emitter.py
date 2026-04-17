"""GBNFEmitter reconstructs GBNF text from RuleSpec IR."""

from __future__ import annotations
from pathlib import Path

import pytest
from codegen.parser import parse_gbnf
from codegen.ir_builder import IRBuilder
from codegen.gbnf_emitter import GBNFEmitter

GRAMMAR_DIR = Path(__file__).parent.parent / "resources" / "ground_truth"


def _roundtrip_gbnf(grammar: str) -> tuple[list, list]:
    """Parse grammar, build IR, emit GBNF, re-parse. Return (original_rules, rt_rules)."""
    original_text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    original_rules = parse_gbnf(original_text)
    specs = IRBuilder(original_rules).build()

    emitter = GBNFEmitter(specs)
    emitted_text = emitter.emit()

    rt_rules = parse_gbnf(emitted_text)
    return original_rules, rt_rules


@pytest.mark.parametrize(
    "grammar", ["arithmetic", "list", "json_ws", "chess", "japanese"]
)
def test_emitted_gbnf_is_parseable(grammar: str):
    """Emitted GBNF must parse without errors."""
    original_text = (GRAMMAR_DIR / f"{grammar}.gbnf").read_text()
    original_rules = parse_gbnf(original_text)
    specs = IRBuilder(original_rules).build()

    emitted = GBNFEmitter(specs).emit()
    assert emitted.strip()
    # Must parse without raising
    rt_rules = parse_gbnf(emitted)
    assert len(rt_rules) > 0


@pytest.mark.parametrize("grammar", ["arithmetic", "list", "json_ws"])
def test_emitted_gbnf_has_same_rule_names(grammar: str):
    original_rules, rt_rules = _roundtrip_gbnf(grammar)
    original_names = {r.name for r in original_rules}
    rt_names = {r.name for r in rt_rules}
    # All original rule names must appear in the emitted grammar
    assert original_names <= rt_names, (
        f"Missing rule names after GBNFEmitter: {original_names - rt_names}"
    )


def test_arithmetic_emitted_contains_root():
    original_text = (GRAMMAR_DIR / "arithmetic.gbnf").read_text()
    specs = IRBuilder(parse_gbnf(original_text)).build()
    emitted = GBNFEmitter(specs).emit()
    assert "root" in emitted
    assert "ident" in emitted
    assert "::=" in emitted


def test_emit_rule_single_spec():
    """emit_rule() on one RuleSpec returns a single ::= line."""
    from codegen.ir import CharClassAtom, RuleSpec

    spec = RuleSpec(
        rule_name="ws",
        class_name="Ws",
        parent_class_name="GrammarModel",
        kind="value_str",
        items=[CharClassAtom("[ \\t\\n]", 0, None)],
        field_map={},
    )
    emitter = GBNFEmitter([spec])
    line = emitter.emit_rule(spec)
    assert "ws" in line
    assert "::=" in line
