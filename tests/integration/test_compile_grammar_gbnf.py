"""GBNF integration tests — full pipeline: grammar text → parse → round-trip."""

from __future__ import annotations

from lexic.compile import (
    canonical_grammar,
    compile_from_path,
    compile_text,
    reset_cache_for_tests,
)
from lexic.compile.binding import compute_binding
from lexic.compile.passes import build_codegen_grammar
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.nodes import IrRuleRef
from tests.paths import GROUND_TRUTH


def _binding(text: str, **kwargs):
    """(canonical ast, codegen grammar, {rule_name: RuleBinding}) for a GBNF string."""
    ast = canonical_grammar(text, GBNF_FLAVOUR, **kwargs)
    codegen_grammar = build_codegen_grammar(ast)
    binding = compute_binding(codegen_grammar)
    return ast, codegen_grammar, {b.rule_name: b for b in binding}


def _ws_ref_items(codegen_grammar, rule_name: str):
    """The arm-level ``ws`` ref items of ``rule_name`` in the codegen grammar."""
    rule = next(r for r in codegen_grammar.rules if r.name == rule_name)
    arm = next(a for a in rule.body if a)
    return [it for it in arm if isinstance(it.atom, IrRuleRef) and it.atom == "ws"]


def test_simple_value_str_round_trips():
    """Single value_str rule: compile → parse → to_text identity."""
    text = 'root ::= "x"\n'
    cg = compile_text(text, flavour="gbnf")
    inst = cg.parse("x")
    assert inst.to_text() == "x"


def test_value_str_charclass_with_dash_range_bound_validates():
    """A class where ``-``–``.`` forms a range behind lower members validates.

    Pins the set-difference failure mode: in some regex engines an unescaped
    ``--`` reads as set difference, silently dropping members — Python ``re``
    only warns, so the emitted pattern must escape the dash bound.
    """
    text = "root ::= w\nw ::= [A-Za-z0-9_.!&^-]+\n"
    cg = compile_text(text, flavour="gbnf")
    w_cls = cg.classes["W"]
    for sample in ("unit", "ship", "ORD-7291", "depth-limit", "cli.py", "!&^"):
        assert w_cls(value=sample).to_text() == sample
    inst = cg.parse("mean-0.5")
    assert inst.to_text() == "mean-0.5"


def test_simple_arithmetic_parses_and_round_trips():
    """Multi-rule sequence grammar: binding kinds are correct and parsing works."""
    text = (
        "root  ::= expr\n"
        "expr  ::= term op term\n"
        "term  ::= num\n"
        "op    ::= [-+*/]\n"
        "num   ::= [0-9]+\n"
    )
    _ast, _cg, by = _binding(text)
    assert by["expr"].kind == "sequence"
    assert by["op"].kind == "value_str"
    assert by["num"].kind == "value_str"

    cg = compile_text(text, flavour="gbnf")
    inst = cg.parse("12+34")
    assert inst.to_text() == "12+34"


def test_non_semantic_ws_transparent_to_round_trip():
    """@non-semantic ws: ws refs relax to min=0 and are absent from to_text output."""
    text = '# @non-semantic ws\nroot ::= ws value ws\nvalue ::= "x"\nws ::= [ \\t]*\n'
    _ast, codegen_grammar, by = _binding(text)
    ws_items = _ws_ref_items(codegen_grammar, "root")
    assert ws_items and all(it.quantifier.lo == 0 for it in ws_items)
    assert "ws" in by["root"].fields
    assert by["root"].fields["ws"].semantic is False

    cg = compile_text(text, flavour="gbnf")
    inst = cg.parse("  x  ")
    assert inst.to_text() == "  x  "
    assert "ws" not in inst.semantic_dump()


def test_explicit_non_semantic_overrides_directive():
    """non_semantic_rules=frozenset() overrides @non-semantic — ws stays required."""
    text = '# @non-semantic ws\nroot ::= ws value\nvalue ::= "x"\nws ::= [ \\t]*\n'
    _ast, codegen_grammar, by = _binding(text, non_semantic_rules=frozenset())
    ws_items = _ws_ref_items(codegen_grammar, "root")
    assert ws_items and all(it.quantifier.lo == 1 for it in ws_items)
    assert all(ibind.semantic for ibind in by["root"].fields.values())


def test_alternation_produces_correct_subclass():
    """Alternation rule: concrete arm is the right subclass and parses correctly."""
    text = "root ::= term\nterm ::= num | ident\nnum ::= [0-9]+\nident ::= [a-z]+\n"
    _ast, _cg, by = _binding(text)
    assert by["term"].kind == "alternation"
    assert by["num"].parent_class_names == ("Term",)
    assert by["ident"].parent_class_names == ("Term",)

    cg = compile_text(text, flavour="gbnf")
    num_inst = cg.parse("42")
    assert num_inst.to_text() == "42"
    assert type(getattr(num_inst, "term")).__name__ == "Num"

    ident_inst = cg.parse("abc")
    assert ident_inst.to_text() == "abc"
    assert type(getattr(ident_inst, "term")).__name__ == "Ident"


def test_multi_membership_arm_isinstance_of_all_alternations():
    """A rule that is an arm of two alternations is an instance of both classes.

    ``unquoted`` is a unit-ref arm of both ``value`` and ``cell``; the parsed
    ``Unquoted`` instance must be an instance of ``Value`` AND ``Cell`` (the
    L1 fix — the single-parent map dropped one, so a ``Cell``-typed field
    rejected an ``Unquoted`` at fold-ctor time). A compact inline grammar keeps
    the cross-flavour ground-truth set undisturbed.
    """
    text = (
        "line ::= value cell\n"
        "value ::= unquoted | pipe\n"
        "cell ::= unquoted | num\n"
        'unquoted ::= "u"\n'
        'pipe ::= "|"\n'
        'num ::= "0"\n'
        "# @start line\n"
    )
    cg = compile_text(text, flavour="gbnf")
    inst = cg.parse("uu")
    assert inst.to_text() == "uu"
    value_field = getattr(inst, "value")
    value_cls = cg.classes["Value"]
    cell_cls = cg.classes["Cell"]
    assert isinstance(value_field, value_cls)
    assert isinstance(value_field, cell_cls)
    # The ``unquoted`` arm parsed under ``value`` is nominally both alternations.
    assert type(value_field).__name__ == "Unquoted"


def test_compile_from_path_uses_filename_stem():
    """compile_from_path names the synthesized classes' module by the filename stem."""
    reset_cache_for_tests()
    cg = compile_from_path(GROUND_TRUTH / "list.gbnf")
    assert "Root" in cg.classes
    assert cg.classes["Root"].__module__ == "generated.list"
    assert cg.parse("- apple\n").to_text() == "- apple\n"


def test_compile_from_path_ground_truth_uses_filename_stem():
    """compile_from_path on a ground truth grammar uses the .gbnf stem as module name."""
    reset_cache_for_tests()
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert "Root" in cg.classes
    assert cg.classes["Root"].__module__ == "generated.arithmetic"
    inst = cg.parse("x=1\n")
    assert inst.to_text() == "x=1\n"
