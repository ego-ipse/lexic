"""Full fixture round-trip: compile → exec generated module → instantiate → to_text() == source.

For each ground-truth fixture, run the entire pipeline end-to-end and assert
the reconstructed text round-trips back to the source. This is the strongest
regression gate during the 25a-e cutover.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.compile import compile_grammar, compile_text
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.parsing.meta_parser import MetaGrammarParser

# parents[0]=tests/integration/, parents[1]=tests/, parents[2]=project root
GROUND_TRUTH = Path(__file__).resolve().parents[2] / "resources" / "ground_truth"

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
    "c.gbnf": frozenset({"root", "declaration", "dataType", "identifier", "ws"}),
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
# compile_grammar reads directives automatically — listed here only for assertion.
_HAS_NON_SEMANTIC_WS = frozenset(
    {"arithmetic.gbnf", "c.gbnf", "json_arr.gbnf", "json_ws.gbnf"}
)

_VALID_KINDS = frozenset({"sequence", "alternation", "value_str"})


@pytest.mark.parametrize("fixture", _ALL_FIXTURES)
def test_compile_grammar_succeeds_on_ground_truth(fixture: str) -> None:
    """compile_grammar returns sane specs for every ground-truth fixture."""
    text = (GROUND_TRUTH / fixture).read_text(encoding="utf-8")
    # Directives (@non-semantic ws) are read from the file automatically.
    start, specs = compile_grammar(text, GbnfFlavour)

    assert start == "root", f"{fixture}: expected start='root', got {start!r}"
    assert len(specs) > 0, f"{fixture}: compile_grammar returned no specs"

    rule_names = {s.rule_name for s in specs}

    # Every explicitly declared rule from the source file must appear.
    expected = _EXPECTED_RULE_NAMES[fixture]
    missing = expected - rule_names
    assert not missing, f"{fixture}: missing expected rules: {missing}"

    # All kind values must be one of the three legal kinds.
    bad_kinds = {s.kind for s in specs} - _VALID_KINDS
    assert not bad_kinds, f"{fixture}: specs contain illegal kind values: {bad_kinds}"

    # Fixtures with @non-semantic ws: at least one spec must record ws in non_semantic_fields.
    if fixture in _HAS_NON_SEMANTIC_WS:
        ws_exposed = [s for s in specs if "ws" in s.non_semantic_fields]
        assert ws_exposed, (
            f"{fixture}: @non-semantic ws declared but no spec has 'ws' in non_semantic_fields"
        )

    # Fixtures without ws should not have any non_semantic_fields entries.
    if fixture not in _HAS_NON_SEMANTIC_WS:
        unexpected_nsf = [s for s in specs if s.non_semantic_fields]
        assert not unexpected_nsf, (
            f"{fixture}: no non-semantic directive but got non_semantic_fields: "
            f"{[(s.rule_name, s.non_semantic_fields) for s in unexpected_nsf]}"
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
def test_meta_grammar_parser_round_trip_idempotent(fixture: str) -> None:
    """Parse → IrAst → parse again of the *original text* yields equal IrAst objects."""
    text = (GROUND_TRUTH / fixture).read_text(encoding="utf-8")
    parser = MetaGrammarParser.for_flavour(GbnfFlavour)
    ast1 = parser.parse(text)
    ast2 = parser.parse(text)
    assert ast1 == ast2, (
        f"{fixture}: two parses of the same text produced different IrAst objects"
    )
    assert ast1.rules, f"{fixture}: IrAst has no rules"
    assert ast1.rules[0].name == "root", (
        f"{fixture}: first rule is {ast1.rules[0].name!r}, expected 'root'"
    )


# Pair each fixture with a sample that must round-trip through the old pipeline.
#
# arithmetic.gbnf  — "x=1\n": ws is non-semantic so stripped; no spaces in sample.
# json_arr.gbnf    — "[\n1\n]": arr literal starts with "[\n"; ws stripped.
# json_ws.gbnf     — '{"a":1}': ws stripped; no spaces.
# list.gbnf        — "- apple\n": item starts with literal "- ".
# chess.gbnf       — "1. e4 e5\n2. d4 d5\n": root needs hardcoded "1. " line then 1+ more.
# japanese.gbnf    — "こんにちは": five hiragana chars, all in [ぁ-ゟ].
# c.gbnf           — XFAIL: old pipeline strips ws from to_text() but the Lark grammar
#                    requires whitespace between dataType and identifier; any non-trivial
#                    C declaration fails the round-trip. Fixed at Task 25a when compile_text
#                    switches to the new pipeline. strict=True so we notice if it heals.
_C_XFAIL = pytest.mark.xfail(
    reason=(
        "Old pipeline strips ws from to_text() but Lark grammar requires whitespace "
        "between dataType and identifier. Fixed when compile_text switches to the new "
        "pipeline at Task 25a."
    ),
    strict=True,
)

_FIXTURES = [
    ("arithmetic.gbnf", "x=1\n"),
    ("json_arr.gbnf", "[\n1\n]"),
    ("json_ws.gbnf", '{"a":1}'),
    ("list.gbnf", "- apple\n"),
    ("chess.gbnf", "1. e4 e5\n2. d4 d5\n"),
    ("japanese.gbnf", "こんにちは"),
    pytest.param("c.gbnf", "int foo(){}", marks=_C_XFAIL),
]


@pytest.mark.parametrize("fixture, sample", _FIXTURES)
def test_full_round_trip(fixture: str, sample: str) -> None:
    """Old pipeline: compile_text → parse(sample) → to_text() == sample."""
    text = (GROUND_TRUTH / fixture).read_text(encoding="utf-8")
    cg = compile_text(text, cache_key=fixture)
    model = cg.parse(sample)
    assert model.to_text() == sample, (
        f"{fixture}: round-trip mismatch.\n"
        f"  source:  {sample!r}\n"
        f"  to_text: {model.to_text()!r}"
    )
