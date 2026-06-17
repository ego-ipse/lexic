"""compile_grammar(text, ABNF_FLAVOUR) — end-to-end via new pipeline."""

from __future__ import annotations

from lexic.compile import compile_grammar
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.ir.nodes import IrAlternation, IrItem
from tests.paths import GROUND_TRUTH


def test_compile_arithmetic_abnf_succeeds():
    """All expected rule names are present and structural kinds are correct."""
    text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    _start, specs = compile_grammar(text, ABNF_FLAVOUR)
    by = {s.rule_name: s for s in specs}
    assert {"root", "expr", "term", "op", "num", "DIGIT", "WSP"} <= set(by)
    assert by["op"].kind == "value_str"
    assert by["expr"].kind == "sequence"
    assert by["DIGIT"].kind == "value_str"


def test_compile_abnf_non_semantic_directive_propagates_to_referencing_rule():
    """@non-semantic WSP propagates into non_semantic_fields on any rule that references it."""
    text = (
        "; @non-semantic WSP\n"
        "root = num WSP\n"
        "num  = 1*DIGIT\n"
        "DIGIT = %x30-39\n"
        "WSP  = %x20 / %x09\n"
    )
    _, specs = compile_grammar(text, ABNF_FLAVOUR)
    by = {s.rule_name: s for s in specs}
    assert "WSP" in by["root"].non_semantic_fields


def test_compile_abnf_case_insensitive_literal_expanded():
    """`root = "Hi"` in ABNF → IrGroup of char classes, not a single literal."""
    text = 'root = "Hi"\n'
    _start, specs = compile_grammar(text, ABNF_FLAVOUR)
    spec = specs[0]
    # The rule classifies as value_str (no rulerefs); the IrItem inside should
    # carry an IrGroup atom (from normalize_literal expansion).
    assert spec.kind == "value_str"
    assert any(_has_group_in(item) for item in spec.items if isinstance(item, IrItem))


def _has_group_in(item: IrItem) -> bool:
    """Is the item's atom an IrGroup?"""
    return isinstance(item.atom, IrAlternation)
