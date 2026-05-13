"""GBNF integration tests — full pipeline: grammar text → parse → round-trip."""

from __future__ import annotations

from lexic.compile import compile_from_path, compile_grammar, compile_text
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.ir.nodes import IrItem, IrRuleRef
from tests.paths import GROUND_TRUTH


def test_simple_value_str_round_trips():
    """Single value_str rule: compile → parse → to_text identity."""
    text = 'root ::= "x"\n'
    cg = compile_text(text, flavour="gbnf")
    inst = cg.parse("x")
    assert inst.to_text() == "x"


def test_simple_arithmetic_parses_and_round_trips():
    """Multi-rule sequence grammar: spec kinds are correct and parsing works."""
    text = (
        "root  ::= expr\n"
        "expr  ::= term op term\n"
        "term  ::= num\n"
        "op    ::= [-+*/]\n"
        "num   ::= [0-9]+\n"
    )
    _, specs = compile_grammar(text, GbnfFlavour)
    by = {s.rule_name: s for s in specs}
    assert by["expr"].kind == "sequence"
    assert by["op"].kind == "value_str"
    assert by["num"].kind == "value_str"

    cg = compile_text(text, flavour="gbnf")
    inst = cg.parse("12+34")
    assert inst.to_text() == "12+34"


def test_non_semantic_ws_transparent_to_round_trip():
    """@non-semantic ws: ws is in IR but absent from to_text output."""
    text = '# @non-semantic ws\nroot ::= ws value ws\nvalue ::= "x"\nws ::= [ \\t]*\n'
    _, specs = compile_grammar(text, GbnfFlavour)
    by = {s.rule_name: s for s in specs}
    root = by["root"]
    ws_item = next(
        i
        for i in root.items
        if isinstance(i, IrItem)
        and isinstance(i.atom, IrRuleRef)
        and i.atom.name == "ws"
    )
    assert ws_item.quantifier.min == 0
    assert "ws" in root.non_semantic_fields

    cg = compile_text(text, flavour="gbnf")
    inst = cg.parse("  x  ")
    assert inst.to_text() == "  x  "
    assert "ws" not in inst.semantic_dump()


def test_explicit_non_semantic_overrides_directive():
    """non_semantic_rules=frozenset() overrides @non-semantic directive — ws stays required."""
    text = '# @non-semantic ws\nroot ::= ws value\nvalue ::= "x"\nws ::= [ \\t]*\n'
    _, specs = compile_grammar(text, GbnfFlavour, non_semantic_rules=frozenset())
    by = {s.rule_name: s for s in specs}
    root = by["root"]
    ws_item = next(
        i
        for i in root.items
        if isinstance(i, IrItem)
        and isinstance(i.atom, IrRuleRef)
        and i.atom.name == "ws"
    )
    assert ws_item.quantifier.min == 1
    assert root.non_semantic_fields == frozenset()


def test_alternation_produces_correct_subclass():
    """Alternation rule: concrete arm is the right subclass and parses correctly."""
    text = "root ::= term\nterm ::= num | ident\nnum ::= [0-9]+\nident ::= [a-z]+\n"
    _, specs = compile_grammar(text, GbnfFlavour)
    by = {s.rule_name: s for s in specs}
    assert by["term"].kind == "alternation"
    assert by["num"].parent_class_name == "Term"
    assert by["ident"].parent_class_name == "Term"

    cg = compile_text(text, flavour="gbnf")
    num_inst = cg.parse("42")
    assert num_inst.to_text() == "42"
    assert type(getattr(num_inst, "term")).__name__ == "Num"
    ident_inst = cg.parse("abc")
    assert ident_inst.to_text() == "abc"
    assert type(getattr(ident_inst, "term")).__name__ == "Ident"


def test_compile_from_path_uses_filename_stem():
    """compile_from_path uses the grammar filename stem as the generated module name."""
    import importlib

    from lexic.compile import reset_cache_for_tests

    reset_cache_for_tests()
    cg = compile_from_path(GROUND_TRUTH / "list.gbnf")
    mod = importlib.import_module("generated.list")
    assert hasattr(mod, "Root")
    assert cg.parse("- apple\n").to_text() == "- apple\n"


def test_compile_from_path_ground_truth_uses_filename_stem():
    """compile_from_path on a ground truth grammar uses the .gbnf stem as module name."""
    import importlib

    from lexic.compile import reset_cache_for_tests

    reset_cache_for_tests()
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    mod = importlib.import_module("generated.arithmetic")
    assert hasattr(mod, "Root")
    inst = cg.parse("x=1\n")
    assert inst.to_text() == "x=1\n"
