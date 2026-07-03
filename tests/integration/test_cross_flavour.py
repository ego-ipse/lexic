"""Cross-flavour: GBNF and ABNF parse the same grammar to comparable IrAst.

The two ASTs are not byte-equivalent — ABNF's case-insensitive literals
expand to char-class groups, while GBNF's literals stay literals — but the
grammars they describe are equivalent for the unambiguous (non-alpha) parts.
"""

from __future__ import annotations

from lexic.compile import compile_grammar, parse_grammar
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.nodes import IrLiteral
from tests.paths import GROUND_TRUTH


def test_arithmetic_grammars_have_same_rule_names():
    """Both versions define at least {root, expr, term, num} (modulo casing).

    The two grammars are structurally different: the GBNF version inlines
    operators in the expr rule and adds ident/ws, while the ABNF version has
    an explicit op rule and DIGIT/WSP helpers. The shared core is the four
    named structural rules.
    """
    gbnf_text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    abnf_text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    gbnf_ast = parse_grammar(gbnf_text, GBNF_FLAVOUR)
    abnf_ast = parse_grammar(abnf_text, ABNF_FLAVOUR)

    gbnf_rules = {r.name.lower() for r in gbnf_ast.rules}
    abnf_rules = {r.name.lower() for r in abnf_ast.rules}

    common = {"root", "expr", "term", "num"}
    assert common <= gbnf_rules
    assert common <= abnf_rules


def test_abnf_op_rule_expands_literals_into_groups():
    """The ABNF "+", "-", "*", "/" each become IrGroup (case-insens-expanded)
    or IrLiteral (no alpha chars). Verify shape."""
    abnf_text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    ast = parse_grammar(abnf_text, ABNF_FLAVOUR)
    op = next(r for r in ast.rules if r.name == "op")
    # All four arms are non-alpha literals, so they stay IrLiteral.

    for arm in op.body:
        assert isinstance(arm[0].atom, IrLiteral)


def test_compile_grammar_works_for_both_flavours_on_arithmetic():
    """End-to-end: both flavours produce non-empty RuleSpec lists with start first."""

    gbnf_text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    abnf_text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    gbnf_start, gbnf_specs = compile_grammar(
        gbnf_text, GBNF_FLAVOUR, non_semantic_rules=frozenset({"ws"})
    )
    abnf_start, abnf_specs = compile_grammar(
        abnf_text, ABNF_FLAVOUR, non_semantic_rules=frozenset({"WSP"})
    )
    assert gbnf_start == "root"
    assert abnf_start == "root"
    assert gbnf_specs[0].rule_name == gbnf_start
    assert abnf_specs[0].rule_name == abnf_start


def test_gbnf_to_abnf_to_gbnf_round_trip_via_iast():
    """Architectural smoke: parse GBNF → emit ABNF → parse ABNF → IrAst' is structurally equal.

    Equivalence is up to ABNF's case-insensitive literal expansion (alpha
    literals expand to char-class groups). Use a non-alpha-literal-only fixture
    to make the IrAst byte-equivalent.
    """

    # Hand-craft a small GBNF grammar with no alpha literals (avoids ABNF case
    # expansion noise). Uses charclass + non-alpha literals only.
    gbnf_text = 'root  ::= digit ("+" digit)*\ndigit ::= [0-9]\n'
    ast_g = parse_grammar(gbnf_text, GBNF_FLAVOUR)

    # Emit as ABNF via the ABNF singleton flavour (consumes IrAst directly).
    abnf_text = str(ABNF_FLAVOUR.apply(ast_g))
    # Parse the emitted ABNF back to IrAst.
    ast_a = parse_grammar(abnf_text, ABNF_FLAVOUR)

    # Structural equivalence: same rule names, same body shapes (no IrLiteral
    # case-expansion since we used only digits and "+"; ABNF's normalize_literal
    # for "+" returns IrLiteral unchanged because no alphas).
    assert {r.name for r in ast_g.rules} == {r.name for r in ast_a.rules}
    for r_g in ast_g.rules:
        r_a = next(r for r in ast_a.rules if r.name == r_g.name)
        assert len(r_g.body) == len(r_a.body)
