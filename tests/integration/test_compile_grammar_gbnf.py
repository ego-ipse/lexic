"""compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""

from __future__ import annotations

import pytest

from lexic.compile import compile_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.ir.nodes import IrItem, IrRuleRef


def test_compile_grammar_returns_rulespecs():
    """compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""
    text = 'root ::= "x"\n'
    start, specs = compile_grammar(text, GbnfFlavour)
    assert start == "root"
    assert len(specs) == 1
    assert specs[0].rule_name == "root"
    assert specs[0].kind == "value_str"


def test_compile_grammar_simple_arithmetic():
    """compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""
    text = (
        "root  ::= expr\n"
        "expr  ::= term op term\n"
        "term  ::= num\n"
        "op    ::= [-+*/]\n"
        "num   ::= [0-9]+\n"
    )
    start, specs = compile_grammar(text, GbnfFlavour)
    by = {s.rule_name: s for s in specs}
    assert start == "root"
    assert by["expr"].kind == "sequence"
    assert by["op"].kind == "value_str"
    assert by["num"].kind == "value_str"


def test_compile_grammar_extracts_directive_when_present():
    """compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""
    text = '# @non-semantic ws\nroot ::= ws value\nvalue ::= "x"\nws ::= [ \\t]*\n'
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


def test_compile_grammar_explicit_non_semantic_overrides_directive():
    """compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""
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


def test_compile_grammar_alternation_creates_subclasses():
    """compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""
    text = "root  ::= term\nterm  ::= num | ident\nnum   ::= [0-9]+\nident ::= [a-z]+\n"
    _, specs = compile_grammar(text, GbnfFlavour)
    by = {s.rule_name: s for s in specs}
    assert by["term"].kind == "alternation"
    assert by["num"].parent_class_name == "Term"
    assert by["ident"].parent_class_name == "Term"


def test_compile_grammar_uses_start_directive():
    """compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""
    text = "# @start expr\nroot  ::= expr\nexpr  ::= [0-9]+\n"
    start, _ = compile_grammar(text, GbnfFlavour)
    assert start == "expr"


def test_compile_grammar_falls_back_to_first_rule_when_no_directive():
    """compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""
    text = "root ::= [0-9]+\n"
    start, _ = compile_grammar(text, GbnfFlavour)
    assert start == "root"


def test_compile_grammar_explicit_start_wins_over_directive():
    """compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""
    text = "# @start expr\nroot ::= expr\nexpr ::= [0-9]+\n"
    start, _ = compile_grammar(text, GbnfFlavour, start="root")
    assert start == "root"


def test_compile_grammar_invalid_start_raises():
    """compile_grammar(text, GbnfFlavour) — end-to-end via new pipeline."""
    text = "# @start nonexistent\nroot ::= [0-9]+\n"
    with pytest.raises(UnsupportedConstructError, match="start"):
        compile_grammar(text, GbnfFlavour)
