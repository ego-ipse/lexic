"""Full fixture round-trip: compile → exec generated module → instantiate → to_text() == source.

For each ground-truth fixture, run the entire pipeline end-to-end and assert
the reconstructed text round-trips back to the source. This is the strongest
regression gate during the 25a-e cutover.
"""

from __future__ import annotations

import pytest

from lexic.codegen.binding import compute_binding
from lexic.codegen.passes import build_codegen_grammar
from lexic.compile import canonical_grammar, compile_from_path
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir.nodes import IrAst
from lexic.parsing import parse_reduced
from lexic.parsing.earley.normalize import normalize
from tests.paths import GROUND_TRUTH

# All 7 ground-truth fixtures produce "root" as the start rule.
_ALL_FIXTURES = [
    "arithmetic.gbnf",
    "c.gbnf",
    "chess.gbnf",
    "japanese.gbnf",
    "json_arr.gbnf",
    "json_ws.gbnf",
    "list.gbnf",
]

# Per-fixture: set of rule names that must appear in the compiled output.
# These are the explicitly declared top-level rules from each .gbnf file.
_EXPECTED_RULE_NAMES: dict[str, frozenset[str]] = {
    "arithmetic.gbnf": frozenset({"root", "expr", "term", "ident", "num", "ws"}),
    # canonicalize's rewrite 7 folds rule names to lowercase: dataType->datatype
    "c.gbnf": frozenset({"root", "declaration", "datatype", "identifier", "ws"}),
    "chess.gbnf": frozenset({"root", "move", "nonpawn", "pawn", "castle"}),
    "japanese.gbnf": frozenset(
        {"root", "jp-char", "hiragana", "katakana", "punctuation", "cjk"}
    ),
    "json_arr.gbnf": frozenset(
        {"root", "value", "arr", "object", "array", "string", "number", "ws"}
    ),
    "json_ws.gbnf": frozenset(
        {"root", "value", "object", "array", "string", "number", "ws"}
    ),
    "list.gbnf": frozenset({"root", "item"}),
}

# Fixtures with @non-semantic ws directives in their source files.
# canonical_grammar reads directives automatically — listed here only for assertion.
_HAS_NON_SEMANTIC_WS = frozenset(
    {"arithmetic.gbnf", "c.gbnf", "json_arr.gbnf", "json_ws.gbnf"}
)

_VALID_KINDS = frozenset({"sequence", "alternation", "value_str"})


def _noise_fields(binding) -> list[str]:
    """Field names flagged ``semantic=False`` across the binding view."""
    return [
        name for b in binding for name, ibind in b.fields.items() if not ibind.semantic
    ]


@pytest.mark.parametrize("fixture", _ALL_FIXTURES)
def test_binding_view_succeeds_on_ground_truth(fixture: str) -> None:
    """The binding view is sane for every ground-truth fixture."""
    text = (GROUND_TRUTH / fixture).read_text(encoding="utf-8")
    # Directives (@non-semantic ws) are read from the file automatically.
    ast = canonical_grammar(text, GBNF_FLAVOUR)
    binding = compute_binding(build_codegen_grammar(ast))

    assert ast.start == "root", f"{fixture}: expected start='root', got {ast.start!r}"
    assert binding, f"{fixture}: binding view is empty"

    rule_names = {b.rule_name for b in binding}

    # Every explicitly declared rule from the source file must appear.
    expected = _EXPECTED_RULE_NAMES[fixture]
    missing = expected - rule_names
    assert not missing, f"{fixture}: missing expected rules: {missing}"

    # All kind values must be one of the three legal kinds.
    bad_kinds = {b.kind for b in binding} - _VALID_KINDS
    assert not bad_kinds, f"{fixture}: binding has illegal kind values: {bad_kinds}"

    # Fixtures with @non-semantic ws: at least one bound field is non-semantic.
    if fixture in _HAS_NON_SEMANTIC_WS:
        assert "ws" in _noise_fields(binding), (
            f"{fixture}: @non-semantic ws declared but no field is flagged non-semantic"
        )

    # Fixtures without ws should not flag any field non-semantic.
    if fixture not in _HAS_NON_SEMANTIC_WS:
        assert not _noise_fields(binding), (
            f"{fixture}: no non-semantic directive but got noise fields: "
            f"{_noise_fields(binding)}"
        )


@pytest.mark.parametrize(
    "fixture",
    [
        "arithmetic.gbnf",
        "c.gbnf",
        "chess.gbnf",
        "japanese.gbnf",
        "json_arr.gbnf",
        "json_ws.gbnf",
        "list.gbnf",
    ],
)
def test_grammar_parse_round_trip_idempotent(fixture: str) -> None:
    """Parse → IrAst → parse again of the *original text* yields equal IrAst objects."""
    text = (GROUND_TRUTH / fixture).read_text(encoding="utf-8")
    norm = normalize(GBNF_FLAVOUR.grammar)
    ast1 = parse_reduced(norm, text, GBNF_FLAVOUR.reducer)
    ast2 = parse_reduced(norm, text, GBNF_FLAVOUR.reducer)
    assert isinstance(ast1, IrAst)
    assert ast1 == ast2, (
        f"{fixture}: two parses of the same text produced different IrAst objects"
    )
    assert ast1.rules, f"{fixture}: IrAst has no rules"
    assert ast1.rules[0].name == "root", (
        f"{fixture}: first rule is {ast1.rules[0].name!r}, expected 'root'"
    )


_FIXTURES = [
    ("arithmetic.gbnf", "x=1\n"),
    ("json_arr.gbnf", "[\n1\n]"),
    ("json_ws.gbnf", '{"a":1}'),
    ("list.gbnf", "- apple\n"),
    ("chess.gbnf", "1. e4 e5\n2. d4 d5\n"),
    ("japanese.gbnf", "こんにちは"),
    ("c.gbnf", "int foo(){}"),
]


@pytest.mark.parametrize("fixture, sample", _FIXTURES)
def test_full_round_trip(fixture: str, sample: str) -> None:
    """compile_from_path → parse(sample) → to_text() == sample."""
    cg = compile_from_path(GROUND_TRUTH / fixture)
    model = cg.parse(sample)
    assert model.to_text() == sample, (
        f"{fixture}: round-trip mismatch.\n"
        f"  source:  {sample!r}\n"
        f"  to_text: {model.to_text()!r}"
    )


# The char rule's escape group is a mixed literal/ref group (each escape char
# literal, plus "u" hexdig{4}). Regression guard for the gtext-vs-model defect:
# every escape input must parse and round-trip on both JSON flavours.
_ESCAPE_INPUTS = ['"\\""', '"\\\\"', '"\\n"', '"A"', '"\\/"', '"\\u0041"']


@pytest.mark.parametrize("fixture", ["json.gbnf", "json.abnf"])
@pytest.mark.parametrize("sample", _ESCAPE_INPUTS)
def test_json_escape_round_trip(fixture: str, sample: str) -> None:
    """String escapes parse + round-trip on both JSON flavours."""
    cg = compile_from_path(GROUND_TRUTH / fixture)
    model = cg.parse(sample)
    assert model.to_text() == sample, (
        f"{fixture}: escape round-trip mismatch.\n"
        f"  source:  {sample!r}\n"
        f"  to_text: {model.to_text()!r}"
    )
