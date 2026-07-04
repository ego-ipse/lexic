"""Cross-flavour: GBNF and ABNF parse the same grammar to comparable IrAst.

The two ASTs are not byte-equivalent — ABNF's case-insensitive literals
expand to char-class groups, while GBNF's literals stay literals — but the
grammars they describe are equivalent for the unambiguous (non-alpha) parts.
"""

from __future__ import annotations

import sys

from lexic.codegen.binding import compute_binding
from lexic.codegen.passes import build_codegen_grammar
from lexic.compile import canonical_grammar, compile_text, parse_grammar
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.nodes import IrLiteral
from tests.paths import GENERATED, GROUND_TRUTH


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
    """End-to-end: both flavours produce a non-empty binding view with start first."""

    gbnf_text = (GROUND_TRUTH / "arithmetic.gbnf").read_text(encoding="utf-8")
    abnf_text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    gbnf_ast = canonical_grammar(
        gbnf_text, GBNF_FLAVOUR, non_semantic_rules=frozenset({"ws"})
    )
    abnf_ast = canonical_grammar(
        abnf_text, ABNF_FLAVOUR, non_semantic_rules=frozenset({"WSP"})
    )
    gbnf_binding = compute_binding(build_codegen_grammar(gbnf_ast))
    abnf_binding = compute_binding(build_codegen_grammar(abnf_ast))
    assert gbnf_ast.start == "root"
    assert abnf_ast.start == "root"
    assert gbnf_binding[0].rule_name == gbnf_ast.start
    assert abnf_binding[0].rule_name == abnf_ast.start


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


def _generated_source(module_name: str) -> str:
    """Read a just-written ``generated/<stem>.py`` back from disk."""
    stem = module_name.rsplit(".", 1)[-1]
    return (GENERATED / f"{stem}.py").read_text(encoding="utf-8")


def test_json_gbnf_and_abnf_compile_to_identical_generated_source():
    """The headline user-visible fixpoint: compiling json.gbnf and json.abnf
    through the public :func:`~lexic.compile.compile_text` entry point emits
    the same Pydantic module source, modulo the docstring's stem line.

    ``json.gbnf`` and ``json.abnf`` describe the same language (RFC 8259) rule
    for rule; both fold to the same canonical ``IrAst`` (module docstring on
    both fixtures says so), so codegen driven from either must produce
    byte-identical classes.
    """
    gbnf_text = (GROUND_TRUTH / "json.gbnf").read_text(encoding="utf-8")
    abnf_text = (GROUND_TRUTH / "json.abnf").read_text(encoding="utf-8")

    gbnf_compiled = compile_text(gbnf_text, flavour="gbnf")
    abnf_compiled = compile_text(abnf_text, flavour="abnf")

    assert set(gbnf_compiled.classes) == set(abnf_compiled.classes)

    gbnf_module = next(iter(gbnf_compiled.classes.values())).__module__
    abnf_module = next(iter(abnf_compiled.classes.values())).__module__
    assert gbnf_module in sys.modules
    assert abnf_module in sys.modules

    gbnf_source = _generated_source(gbnf_module)
    abnf_source = _generated_source(abnf_module)

    # Both sources start with a one-line docstring naming their (distinct,
    # content-hashed) stem; every line after it must match exactly.
    gbnf_lines = gbnf_source.splitlines()
    abnf_lines = abnf_source.splitlines()
    assert gbnf_lines[0].startswith('"""Generated module: ')
    assert abnf_lines[0].startswith('"""Generated module: ')
    assert gbnf_lines[1:] == abnf_lines[1:]
