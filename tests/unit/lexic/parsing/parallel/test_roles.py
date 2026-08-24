"""Tests for ``lexic.parsing.parallel.roles`` — derived anchor roles.

The demonstrable shapes: a bracketing arm derives an opener/closer pair
(trailing noise after the closer allowed), and a repeated body's leading
anchor literal derives a separator (resolving through unit rule refs).
Nothing is hardcoded per formulation — every case here goes through the
standard pipeline.
"""

from __future__ import annotations

import lexic.parsing
from lexic.compile import compile_text, parse_grammar
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing import parallel
from lexic.parsing.parallel import Roles, Separator, roles
from lexic.parsing.parallel.roles import Terminator, agreed_tail
from tests.unit.lexic.parsing.parallel.discovery.test_anchors import JSONISH


def test_the_facade_exports_the_parallel_vocabulary():
    """Every name in ``__all__`` resolves on the package."""
    for name in parallel.__all__:
        assert getattr(parallel, name) is not None


def test_the_parsing_root_does_not_reexport_the_parallel_layer():
    """Neither engine consumes these names — they stay off the root."""
    assert "anchors" not in lexic.parsing.__all__
    assert "worker_count" not in lexic.parsing.__all__


def test_jsonish_derives_the_brace_pair_and_comma_separator():
    """``"{" ws member ("," ws member)* "}"`` → pair ``{``/``}``, sep ``,``."""
    got = roles(parse_grammar(JSONISH, GBNF_FLAVOUR))
    assert got.pairs == (("{", "}"),)
    assert got.separators == frozenset(",")


def test_trailing_noise_after_the_closer_is_allowed():
    """The closer is the LAST anchor literal, not the last item."""
    grammar = 'root ::= "(" x ")" ws\nx ::= [a-z]+\nws ::= " "*'
    got = roles(compile_text(grammar).codegen_grammar)
    assert got.pairs == (("(", ")"),)


def test_separator_records_carry_the_orchestration_rules():
    """``tail ::= comma item`` derives the full record: char, container,
    repeated item, and the lead rule the cut text re-parses under."""
    grammar = 'root ::= item tail*\ntail ::= comma item\ncomma ::= ","\nitem ::= [a-z]+'
    got = roles(parse_grammar(grammar, GBNF_FLAVOUR))
    assert got.separators == frozenset(",")
    assert got.records == (Separator(",", "root", "tail", "comma"),)


def test_a_common_terminator_resolves_through_recursive_rule_refs():
    """Every entry arm reaches the same newline through ``ending`` and ``nl``."""
    grammar = (
        "root ::= entry+\n"
        "entry ::= word ending\n"
        'word ::= "a" | "b"\n'
        "ending ::= nl\n"
        'nl ::= "\\n"\n'
    )

    got = roles(parse_grammar(grammar, GBNF_FLAVOUR))
    assert got.terminators == (Terminator("\n", "root", "entry"),)


def test_finite_anchor_class_derives_each_separator_alternative():
    """A compiled ``+ | -`` lead remains two structural separator choices."""
    grammar = (
        "root ::= expr\n"
        "expr ::= number tail*\n"
        "tail ::= addop number\n"
        'addop ::= "+" | "-"\n'
        "number ::= [0-9]+\n"
    )

    got = roles(compile_text(grammar).codegen_grammar)
    assert got.records == (
        Separator("+", "expr", "tail", "addop"),
        Separator("-", "expr", "tail", "addop"),
    )


def test_a_merged_tail_literal_derives_the_terminator_from_its_last_character():
    """``@lexical`` inlining can merge a unit's tail into one literal like
    ``"}\\n"``; the terminator is derivable as its LAST character, since it
    occurs nowhere else in the literal, and again as the wider spelling that
    character closes. Narrowest first — the cascade tries that plan first."""
    grammar = 'root ::= unit+\nunit ::= [a-z]+ "}\\n"\n'
    got = roles(compile_text(grammar).codegen_grammar)
    assert got.terminators == (
        Terminator("\n", "root", "unit"),
        Terminator("}\n", "root", "unit"),
    )


def test_a_repeated_terminator_character_resolves_at_the_wider_spelling():
    """The candidate CHARACTER occurs twice in the merged literal, so which
    occurrence is the boundary is unprovable and no character edge derives.
    The two-character tail ``"b\\n"`` stands only at the end, so it does —
    a wider mark is what settles an ambiguous narrow one."""
    grammar = 'root ::= unit+\nunit ::= [a-z]+ "a\\nb\\n"\n'
    got = roles(compile_text(grammar).codegen_grammar)
    assert got.terminators == (Terminator("b\n", "root", "unit"),)


def test_a_grammar_without_the_shapes_derives_empty_roles():
    """No bracketing arm, no repeated separated body — empty roles, not an
    error: the orchestrator's cue for sequential processing."""
    ast = parse_grammar('root ::= x y\nx ::= "ab"\ny ::= "ba"', GBNF_FLAVOUR)
    assert roles(ast) == Roles((), ())


# ── agreed_tail: the arm-family conjunction, one character wider ──────────


def _tail(source: str, unit: str, want: int = 2) -> str:
    ast = parse_grammar(source, GBNF_FLAVOUR)
    rule_map = {str(rule.name): rule for rule in ast.rules}
    return agreed_tail(rule_map[unit].body, want, rule_map, frozenset({unit}))


def test_an_assembled_tail_reaches_left_past_an_exact_final_item():
    """``para ::= line+ blank`` ends with the blank line's own newline, and
    the character before it is whatever the last line ended with. ``blank``
    always spells exactly one newline, which is what licenses reaching left."""
    source = (
        "root ::= para+\npara ::= line+ blank\n"
        'line ::= [a-z0-9 ]+ nl\nblank ::= nl\nnl ::= "\\n"\n'
    )
    assert _tail(source, "para") == "\n\n"


def test_a_variable_width_final_item_yields_only_its_last_character():
    """``word`` puts its own text between whatever precedes it and its final
    character, so nothing to the left can be reached and the wider tail
    declines — the narrower one still stands."""
    source = 'root ::= unit+\nunit ::= nl word\nword ::= [a-z]+ "!"\nnl ::= "\\n"\n'
    assert _tail(source, "unit", 1) == "!"
    assert _tail(source, "unit") == ""


def test_every_arm_must_agree_on_the_wider_tail():
    """The conjunction: one arm ending differently leaves the family with no
    spelling, exactly as it leaves it with no character."""
    agree = (
        'root ::= unit+\nunit ::= a | b\na ::= [a-z]+ x\nb ::= [0-9]+ x\nx ::= "!\\n"\n'
    )
    differ = agree.replace("b ::= [0-9]+ x", "b ::= [0-9]+ y").replace(
        'x ::= "!\\n"', 'x ::= "!\\n"\ny ::= "?\\n"'
    )
    assert _tail(agree, "unit") == "!\n"
    assert _tail(differ, "unit") == ""


def test_a_cycle_in_the_tail_walk_declines():
    """A self-referential tail never resolves a fixed spelling, and an
    unresolved walk answers nothing rather than guessing."""
    assert _tail('root ::= unit+\nunit ::= "a" unit\n', "unit") == ""


def test_a_wider_terminator_is_offered_behind_the_narrower_one():
    """Order is the whole non-regression argument: the character every
    grammar already derives is offered first, so the cascade reaches the
    spelling only when the narrower plan fails to certify."""
    source = (
        "root ::= para+\npara ::= line+ blank\n"
        'line ::= [a-z0-9 ]+ nl\nblank ::= nl\nnl ::= "\\n"\n'
    )
    got = roles(compile_text(source).codegen_grammar)
    para = [record.mark for record in got.terminators if record.unit == "para"]
    assert para == ["\n", "\n\n"]


def test_a_multi_character_separator_derives_as_one_mark():
    """A blank-line separator spells two characters; both are anchors, so the
    scan can find its occurrences with no left context and it is a mark."""
    source = 'root ::= block (sep block)*\nsep ::= "\\n\\n"\nblock ::= [a-z]+\n'
    got = roles(compile_text(source).codegen_grammar)
    assert [record.mark for record in got.records] == ["\n\n"]
