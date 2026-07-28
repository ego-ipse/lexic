"""GBNF_FLAVOUR mirror parity check."""

from __future__ import annotations

import pytest

from lexic.compile import canonical_grammar, parse_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.gbnf import (
    GBNF_ACTIONS,
    GBNF_ESCAPES,
    GBNF_FLAVOUR,
    GBNF_GRAMMAR,
    GBNF_NOISE,
    GBNF_QUANTIFIERS,
    GBNF_REDUCER,
    GBNF_REDUCTIONS,
)
from lexic.ir import (
    MAX_CODEPOINT,
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrFlavour,
    IrItem,
    IrLambda,
    IrLiteral,
    IrMap,
    IrNone,
    IrNot,
    IrQuantifier,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing import derivations
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce.policy import DROP, KEEP_REDUCED
from lexic.parsing.earley.reduce.reducer import Reducer
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.products import earley_reduce
from tests.unit.lexic.conftest import (
    GRAMMAR_AST_TYPES,
    assert_wide_rule_wraps_and_round_trips,
    contains_ir_type,
)


def test_subclass():
    """GBNF_FLAVOUR is an IrFlavour singleton."""
    assert isinstance(GBNF_FLAVOUR, IrFlavour)


def test_metadata():
    """GBNF_FLAVOUR metadata is stable."""
    assert GBNF_FLAVOUR.name == "gbnf"
    assert GBNF_FLAVOUR.extensions == (".gbnf",)


def test_line_comment_token():
    """GBNF_FLAVOUR line comment marker is '#'."""
    assert GBNF_FLAVOUR.line_comment == "#"


def test_encode_newline():
    """Newline encodes to backslash-n."""
    assert GBNF_ESCAPES.encode("\n") == r"\n"


def test_encode_tab():
    """Tab encodes to backslash-t."""
    assert GBNF_ESCAPES.encode("\t") == r"\t"


def test_encode_backslash():
    """Backslash encodes to double backslash."""
    assert GBNF_ESCAPES.encode("\\") == r"\\"


def test_encode_quote():
    """Double quote encodes to escaped quote."""
    assert GBNF_ESCAPES.encode('"') == r"\""


def test_encode_plain_text():
    """Plain text encodes unchanged."""
    assert GBNF_ESCAPES.encode("abc") == "abc"


def test_gbnf_emitter_iremit_default_unreachable():
    """Every IR-AST node type has an explicit action — IrEmit default never fires.

    If any type is missing an action, the emitter would fall through to its
    IrEmit default body and silently emit ``str(n)`` instead of raising.
    This test locks that the default is structurally unreachable for GBNF.
    """
    registered = set(GBNF_FLAVOUR.actions.keys())
    missing = GRAMMAR_AST_TYPES - registered
    assert not missing, f"GBNF_FLAVOUR missing explicit actions for: {missing}"


def test_gbnf_any_char_class_emits_dot():
    """The full-Unicode char class emits ``.`` — the any-char surface (F8)."""
    full = IrCharClass(IrRange(IrChr(0), IrChr(MAX_CODEPOINT)))
    assert GBNF_FLAVOUR.apply(full) == "."
    # A non-full class still renders as brackets.
    assert (
        GBNF_FLAVOUR.apply(IrCharClass(IrRange(IrChr(ord("a")), IrChr(ord("z")))))
        == "[a-z]"
    )


@pytest.mark.parametrize("grammar", ["root ::= .", "root ::= .*", 'root ::= "a" .'])
def test_gbnf_dot_round_trips_through_canonical(grammar: str):
    """``.`` survives parse → canonicalize → emit (ruling §7.2; README `.*`)."""
    ast = canonical_grammar(grammar, GBNF_FLAVOUR)
    emitted = str(GBNF_FLAVOUR.apply(ast))
    assert "." in emitted and "\\x00" not in emitted
    assert canonical_grammar(emitted, GBNF_FLAVOUR) == ast


@pytest.mark.parametrize("grammar", ["root ::= .", "root ::= [^]"])
def test_gbnf_raw_any_char_emits_dot_off_the_non_canonical_seam(grammar: str):
    """A raw ``IrNot(empty class)`` (un-canonicalised ``.``/``[^]``) emits ``.``."""
    emitted = str(GBNF_FLAVOUR.apply(parse_grammar(grammar, GBNF_FLAVOUR)))
    assert emitted == "root ::= .\n"


# ── GBNF_QUANTIFIERS ──────────────────────────────────────────────────


def test_gbnf_quantifiers_maps_four_bounds_to_symbols():
    """GBNF_QUANTIFIERS maps the four canonical quantifier bounds to their symbols."""
    assert GBNF_QUANTIFIERS[IrQuantifier(1, 1)] == ""
    assert GBNF_QUANTIFIERS[IrQuantifier(0, 1)] == "?"
    assert GBNF_QUANTIFIERS[IrQuantifier(0, IrNone)] == "*"
    assert GBNF_QUANTIFIERS[IrQuantifier(1, IrNone)] == "+"


def test_gbnf_quantifiers_counted_forms_render():
    """GBNF spells counted repetition natively: {n} / {n,} / {m,n}."""
    assert GBNF_FLAVOUR.apply(IrQuantifier(4, 4)) == "{4}"
    assert GBNF_FLAVOUR.apply(IrQuantifier(2, 5)) == "{2,5}"
    assert GBNF_FLAVOUR.apply(IrQuantifier(0, 15)) == "{0,15}"
    assert GBNF_FLAVOUR.apply(IrQuantifier(3, IrNone)) == "{3,}"


def test_gbnf_quantifier_hit_question_mark():
    """GBNF_FLAVOUR.apply(IrQuantifier(0, 1)) emits '?'."""
    assert GBNF_FLAVOUR.apply(IrQuantifier(0, 1)) == "?"


# ── Declarative literal emission ──────────────────────────────────────


def test_gbnf_literal_emission_escapes_and_quotes():
    """GBNF_FLAVOUR.apply on a literal escapes special chars and wraps in quotes."""
    result = GBNF_FLAVOUR.apply(IrLiteral('a"b'))
    assert result == '"a\\"b"'


# ── Item parenthesisation ─────────────────────────────────────────────


def test_gbnf_item_alternation_atom_is_parenthesised():
    """An IrItem whose atom is an IrAlternation renders wrapped in parens."""
    item = IrItem(atom=IrAlternation(IrSequence(IrItem(atom=IrLiteral("x")))))
    assert GBNF_FLAVOUR.apply(item) == '("x")'


def test_gbnf_item_ruleref_atom_is_not_parenthesised():
    """An IrItem whose atom is an IrRuleRef renders without wrapping parens."""
    item = IrItem(atom=IrRuleRef("foo"))
    assert GBNF_FLAVOUR.apply(item) == "foo"


# ── IrNot / negated charclass emission ───────────────────────────────


def test_gbnf_not_charclass_renders_negated_bracket():
    """GBNF_FLAVOUR.apply(IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z"))))) renders "[^a-z]"."""
    assert (
        GBNF_FLAVOUR.apply(IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))
        == "[^a-z]"
    )


def test_gbnf_charclass_renders_without_negation_mark():
    """Plain IrCharClass renders without a caret — no mark leakage from IrNot."""
    assert GBNF_FLAVOUR.apply(IrCharClass(IrRange(IrChr("a"), IrChr("z")))) == "[a-z]"


def test_gbnf_not_non_charclass_raises_unsupported():
    """IrNot wrapping a non-IrCharClass node raises UnsupportedConstructError.

    The error message names the dispatcher and the rejected node type.
    """
    with pytest.raises(UnsupportedConstructError, match="cannot negate 'IrRuleRef'"):
        GBNF_FLAVOUR.apply(IrNot(IrRuleRef("ws")))


# ── Structured IrCharClass emission ──────────────────────────────────


def test_gbnf_charclass_range_emits_bracket_with_dash():
    """A range-only class emits ``[lo-hi]``."""
    assert GBNF_FLAVOUR.apply(IrCharClass(IrRange(IrChr("0"), IrChr("9")))) == "[0-9]"


def test_gbnf_charclass_run_emits_bracket_with_chars():
    """A run of code points emits ``[chars]``."""
    assert (
        GBNF_FLAVOUR.apply(IrCharClass(IrChr("a"), IrChr("b"), IrChr("c"))) == "[abc]"
    )


def test_gbnf_charclass_mixed_emits_run_then_range():
    """A mixed run + range class emits ``[runchars lo-hi]``."""
    assert (
        GBNF_FLAVOUR.apply(
            IrCharClass(
                IrChr("a"), IrChr("b"), IrChr("c"), IrRange(IrChr("0"), IrChr("9"))
            )
        )
        == "[abc0-9]"
    )


# ── GBNF_GRAMMAR / GBNF_REDUCTIONS — native IR grammar + reducer ──────────
#
# Unit mirror for the GBNF self-grammar authored directly in gbnf.py (the
# text→IR half, mirroring the ABNF block folded into abnf.py). The
# integration golden gate (tests/integration/test_gbnf_ir_equivalence.py)
# pins the reduced rule fingerprint over the ground-truth grammars — these
# tests target behaviors that gate doesn't reach: individual
# escape/quantifier/charclass forms, noise handling, and ambiguity guards on
# minimal snippets.


def normalize_grammar(g: IrAst) -> IrAst:
    """Full normalization pipeline: flatten_groups -> desugar_quantifiers."""
    return normalize(g)


def ruleref_names(seq: IrSequence) -> list[str]:
    """Every ``IrRuleRef`` name directly referenced by a sequence's items."""
    return [str(item.atom) for item in seq if isinstance(item.atom, IrRuleRef)]


# ── Structure ───────────────────────────────────────────────────────────


def test_gbnf_grammar_is_ir_ast():
    """GBNF_GRAMMAR is an IrAst."""
    assert isinstance(GBNF_GRAMMAR, IrAst)


def test_gbnf_grammar_start_rule_is_grammar():
    """GBNF_GRAMMAR start rule is 'grammar'."""
    assert GBNF_GRAMMAR.start == "grammar"


def test_gbnf_grammar_has_expected_rule_count():
    """GBNF_GRAMMAR has at least 60 rules (a far larger surface than ABNF's
    subset: quantifiers, literal escapes, and charclasses are each broken
    into several structurally-disambiguating sub-rules)."""
    assert len(list(GBNF_GRAMMAR.rules)) >= 60


def test_gbnf_grammar_rule_names_include_core():
    """GBNF_GRAMMAR contains the expected core rule names."""
    names = {r.name for r in GBNF_GRAMMAR.rules}
    for expected in (
        "rule",
        "alternation",
        "arm",
        "empty-seq",
        "sequence",
        "item",
        "literal",
        "charclass",
        "quantifier",
        "n",
        "comment-line",
    ):
        assert expected in names, f"Missing rule: {expected}"


def test_gbnf_grammar_every_ruleref_is_defined():
    """Every IrRuleRef referenced by every rule body names a defined rule."""
    names = {r.name for r in GBNF_GRAMMAR.rules}
    undefined: set[str] = set()
    for rule in GBNF_GRAMMAR.rules:
        for arm in rule.body:
            for ref_name in ruleref_names(arm):
                if ref_name not in names:
                    undefined.add(ref_name)
    assert not undefined, f"Undefined rule refs: {undefined}"


def test_gbnf_grammar_emits_non_empty_string():
    """GBNF_FLAVOUR.apply(GBNF_GRAMMAR) returns a non-empty string."""
    result = str(GBNF_FLAVOUR.apply(GBNF_GRAMMAR))
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_gbnf_grammar_emitted_text_contains_grammar_rule():
    """The emitted GBNF text contains the 'grammar' rule definition."""
    text = str(GBNF_FLAVOUR.apply(GBNF_GRAMMAR))
    assert "grammar ::= " in text


def test_irchr_is_codepoint_int_based():
    """IrChr is codepoint-int-based: the glyph and ordinal forms are equal."""
    assert IrChr("a") == IrChr(97)


# ── Reducer wiring ─────────────────────────────────────────────────────


def test_gbnf_reducer_is_a_reducer():
    """GBNF_REDUCER is a Reducer."""
    assert isinstance(GBNF_REDUCER, Reducer)


def test_gbnf_reducer_tables_are_gbnf_reductions_and_noise():
    """GBNF_REDUCER's tables are GBNF_REDUCTIONS and GBNF_NOISE."""
    assert GBNF_REDUCER.actions is GBNF_REDUCTIONS
    assert GBNF_REDUCER.noise is GBNF_NOISE


def test_gbnf_flavour_grammar_is_gbnf_grammar():
    """GBNF_FLAVOUR.grammar is the GBNF_GRAMMAR singleton."""
    assert GBNF_FLAVOUR.grammar is GBNF_GRAMMAR


def test_gbnf_flavour_reducer_is_gbnf_reducer():
    """GBNF_FLAVOUR.reducer is the GBNF_REDUCER singleton."""
    assert GBNF_FLAVOUR.reducer is GBNF_REDUCER


def test_gbnf_flavour_reducer_is_a_reducer_instance():
    """GBNF_FLAVOUR.reducer satisfies isinstance(..., Reducer)."""
    assert isinstance(GBNF_FLAVOUR.reducer, Reducer)


def test_gbnf_flavour_grammar_is_an_ir_ast_instance():
    """GBNF_FLAVOUR.grammar satisfies isinstance(..., IrAst)."""
    assert isinstance(GBNF_FLAVOUR.grammar, IrAst)


def test_gbnf_reductions_and_noise_are_ir_maps():
    """GBNF_REDUCTIONS and GBNF_NOISE are IrMaps."""
    assert isinstance(GBNF_REDUCTIONS, IrMap)
    assert isinstance(GBNF_NOISE, IrMap)


def test_gbnf_noise_drops_whitespace_and_tail_comment():
    """GBNF_NOISE drops 'n' (whitespace/comment runs) and 'tail-comment'."""
    assert GBNF_NOISE.resolve(IrRuleRef("n")) is DROP
    assert GBNF_NOISE.resolve(IrRuleRef("tail-comment")) is DROP


def test_gbnf_noise_keeps_everything_else_reduced():
    """Every other rule name resolves to KEEP_REDUCED (the IR_DEFAULT arm)."""
    assert GBNF_NOISE.resolve(IrRuleRef("rule")) is KEEP_REDUCED
    assert GBNF_NOISE.resolve(IrRuleRef("literal")) is KEEP_REDUCED


# ── Reduction behaviors ──────────────────────────────────────────────────


def first_item(result: IrAst):
    """The first item of the first rule's first arm, for single-item snippets."""
    rule = list(result.rules)[0]
    arm = list(rule.body)[0]
    return arm[0]


def test_plain_rule_and_ruleref_reduces():
    """'a ::= b' reduces to one rule 'a' with a single-item body ref to 'b'."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= b\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert result.start == "a"
    rule = list(result.rules)[0]
    assert rule.name == "a"
    item = first_item(result)
    assert item.atom == IrRuleRef("b")


def test_item_default_quantifier_is_one_one():
    """An unquantified item defaults to IrQuantifier(1, 1)."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= b\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert first_item(result).quantifier == IrQuantifier(1, 1)


@pytest.mark.parametrize(
    "suffix, expected",
    [
        ("?", IrQuantifier(0, 1)),
        ("*", IrQuantifier(0, IrNone)),
        ("+", IrQuantifier(1, IrNone)),
        ("{2}", IrQuantifier(2, 2)),
        ("{2,}", IrQuantifier(2, IrNone)),
        ("{2,5}", IrQuantifier(2, 5)),
    ],
    ids=["opt", "star", "plus", "exact", "atleast", "between"],
)
def test_quantifier_forms_reduce(suffix: str, expected: IrQuantifier):
    """Each GBNF quantifier suffix reduces to its IrQuantifier bounds."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, f"a ::= b{suffix}\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert first_item(result).quantifier == expected


def test_quantifier_noise_separated_from_atom():
    """'atom ?' (noise between atom and quantifier) still reduces to (0, 1)."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= b ?\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert first_item(result).quantifier == IrQuantifier(0, 1)


def test_literal_newline_escape_decodes():
    """'\\n' inside a literal decodes to an actual newline."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, 'a ::= "\\n"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert first_item(result).atom == IrLiteral("\n")


def test_literal_plain_char_stays_literal():
    """A plain character in a literal reduces unchanged."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, 'a ::= "A"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert first_item(result).atom == IrLiteral("A")


def test_literal_unknown_escape_stays_verbatim():
    """An unrecognised escape ('\\q') keeps its backslash — decode() passthrough."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, 'a ::= "\\q"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert first_item(result).atom == IrLiteral("\\q")


def test_literal_hex_escape_decodes_to_character():
    """'\\x41' inside a literal decodes to 'A' (hex2/4/8 → _HEX_GLYPH)."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, 'a ::= "\\x41"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert first_item(result).atom == IrLiteral("A")


def test_literal_hex4_escape_decodes_to_character():
    """'\\u0042' (the 4-hex-digit form) inside a literal decodes to 'B'."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, 'a ::= "\\u0042"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert first_item(result).atom == IrLiteral("B")


def test_literal_hex8_escape_decodes_to_character():
    """'\\U00000042' (the 8-hex-digit form) inside a literal decodes to 'B'."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, 'a ::= "\\U00000042"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert first_item(result).atom == IrLiteral("B")


def test_charclass_range_reduces():
    """'[a-z]' reduces to a single-range IrCharClass."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= [a-z]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = first_item(result).atom
    assert atom == IrCharClass(IrRange(IrChr("a"), IrChr("z")))


def test_charclass_run_of_singles_reduces():
    """'[abc]' — a run of single chars reduces to one IrChr code point each."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= [abc]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = first_item(result).atom
    assert atom == IrCharClass(IrChr("a"), IrChr("b"), IrChr("c"))


def test_charclass_mixed_run_then_range_reduces():
    """'[abc0-9]' — a leading run of code points followed by a range."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= [abc0-9]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = first_item(result).atom
    assert atom == IrCharClass(
        IrChr("a"), IrChr("b"), IrChr("c"), IrRange(IrChr("0"), IrChr("9"))
    )


def test_charclass_leading_dash_reduces():
    """'[-+*/]' — a leading bare dash is an ordinary unit, not a range marker."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= [-+*/]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = first_item(result).atom
    assert atom == IrCharClass(IrChr("-"), IrChr("+"), IrChr("*"), IrChr("/"))


def test_charclass_trailing_dash_reduces():
    """'[a-]' — a trailing bare dash is an ordinary unit, not a range marker."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= [a-]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = first_item(result).atom
    assert atom == IrCharClass(IrChr("a"), IrChr("-"))


def test_charclass_negation_reduces_to_irnot():
    """'[^\"]' reduces to IrNot wrapping the (unnegated) IrCharClass."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, 'a ::= [^"]\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = first_item(result).atom
    assert atom == IrNot(IrCharClass(IrChr('"')))


def test_charclass_escaped_unit_reduces_to_irchr():
    r"""'[\t]' — the escaped tab reduces to IrChr(9)."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= [\\t]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = first_item(result).atom
    assert atom == IrCharClass(IrChr(9))


def test_charclass_hex_range_reduces():
    r"""'[\x00-\x1f]' — a hex-escaped range reduces to IrRange over IrChr endpoints."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= [\\x00-\\x1f]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = first_item(result).atom
    assert atom == IrCharClass(IrRange(IrChr(0), IrChr(0x1F)))


def test_group_reduces_to_bare_alternation_atom():
    """'(b | c)' reduces to a bare IrAlternation atom (no separate group node)."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= (b | c)\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = first_item(result).atom
    assert isinstance(atom, IrAlternation)
    assert atom == IrAlternation(
        IrSequence(IrItem(IrRuleRef("b"))), IrSequence(IrItem(IrRuleRef("c")))
    )


def test_empty_arm_reduces_to_empty_sequence():
    """'ws ::= | " "' — GBNF allows an empty alternation arm."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, 'ws ::= | " "\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rule = list(result.rules)[0]
    arms = list(rule.body)
    assert len(arms) == 2
    assert arms[0] == IrSequence()
    assert arms[1] == IrSequence(IrItem(IrLiteral(" ")))


def test_fully_empty_body_reduces_to_single_empty_arm():
    """'a ::=' (no body at all) is a single-arm rule with an empty sequence."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::=\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rule = list(result.rules)[0]
    assert rule.body == IrAlternation(IrSequence())


def test_comment_line_between_rules_is_noise():
    """A '# comment' line between two rules is dropped; both rules survive."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= b\n# c\nc ::= d\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rules = list(result.rules)
    assert [r.name for r in rules] == ["a", "c"]
    assert rules[0].body[0][0].atom == IrRuleRef("b")
    assert rules[1].body[0][0].atom == IrRuleRef("d")


def test_trailing_comment_without_newline_at_eof():
    """An unterminated '# comment' at EOF (no trailing '\\n') still parses."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "a ::= b\n# c", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rules = list(result.rules)
    assert len(rules) == 1
    assert rules[0].name == "a"


def test_directive_comment_is_ignored_by_the_grammar():
    """A '# @directive'-shaped line is just an ordinary comment to GBNF_GRAMMAR
    (directives are extracted from raw text before the meta-grammar parser
    runs; the self-grammar itself has no directive awareness)."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, "# @start a\na ::= b\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rules = list(result.rules)
    assert len(rules) == 1
    assert rules[0].name == "a"


def test_multiline_rule_continuation():
    """An alternation's second arm on its own indented line still joins the
    same rule (noise absorbs the line break and leading whitespace)."""
    g = normalize_grammar(GBNF_GRAMMAR)
    result = earley_reduce(g, 'a ::= "x"\n    | "y"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rule = list(result.rules)[0]
    arms = list(rule.body)
    assert len(arms) == 2
    assert arms[0][0].atom == IrLiteral("x")
    assert arms[1][0].atom == IrLiteral("y")


# ── Ambiguity guards ──────────────────────────────────────────────────────


def test_two_char_name_is_unambiguous():
    """'a ::= bc' has exactly one derivation: ONE two-char ruleref, not two."""
    g = normalize_grammar(GBNF_GRAMMAR)
    assert len(derivations(g, "a ::= bc\n")) == 1
    result = earley_reduce(g, "a ::= bc\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rule = list(result.rules)[0]
    arm = list(rule.body)[0]
    assert len(arm) == 1
    assert arm[0].atom == IrRuleRef("bc")


def test_rule_boundary_is_unambiguous():
    """'a ::= b\\nc ::= d' has exactly one derivation: two separate rules."""
    g = normalize_grammar(GBNF_GRAMMAR)
    text = "a ::= b\nc ::= d\n"
    assert len(derivations(g, text)) == 1
    result = earley_reduce(g, text, GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert [r.name for r in result.rules] == ["a", "c"]


def test_charclass_range_vs_dash_is_unambiguous():
    """'a ::= [0-9]' has exactly one derivation: a range, not unit-dash-unit."""
    g = normalize_grammar(GBNF_GRAMMAR)
    assert len(derivations(g, "a ::= [0-9]\n")) == 1
    result = earley_reduce(g, "a ::= [0-9]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = first_item(result).atom
    assert atom == IrCharClass(IrRange(IrChr("0"), IrChr("9")))


# ── Left-factored cc-item reshape: language pins over the shipped PDA path ──


@pytest.mark.parametrize(
    "cls",
    [
        "[a--]",
        "[a-]",
        "[abc-]",
        "[-a]",
        "[]",
        "[^]",
        "[\\x41-\\x5A]",
        "[a-zA-Z0-9-]",
        "[^\\]-]",
        "[-]",
        "[^-]",
        "[^a-z]",
        "[a--b]",
        "[--]",
    ],
)
def test_charclass_corpus_accepts(cls):
    """The reshaped ``cc-item ::= cc-unit cc-tail`` accepts the same class
    surface as before — the FOLLOW-window arm gate keeps a trailing ``-``
    (``[a-]``) an ordinary unit while a real range (``[a-z]``) still parses."""
    result = parse_grammar(f"root ::= {cls}\n", GBNF_FLAVOUR)
    assert isinstance(result, IrAst)


@pytest.mark.parametrize("cls", ["[--a]", "[a-b-c]", "[---]", "[^--a]", "[]-]"])
def test_charclass_corpus_rejects(cls):
    """A ``-`` that is neither leading, trailing, nor a range-hi is rejected —
    the left-factored tail never admits an infix bare dash."""
    with pytest.raises(UnsupportedConstructError):
        parse_grammar(f"root ::= {cls}\n", GBNF_FLAVOUR)


def test_charclass_range_hi_dash_parses_as_range():
    """``[\\--a]`` is ``range('-', 'a')`` — ``-`` is a legal range-hi via the
    preserved ``cc-hi`` (``cc-unit | cc-dash``), so ``[a--b]`` is
    ``range(a, '-')`` then ``b`` (language-preserving, not a reject)."""
    result = parse_grammar("root ::= [a--b]\n", GBNF_FLAVOUR)
    atom = first_item(result).atom
    assert atom == IrCharClass(IrRange(IrChr("a"), IrChr("-")), IrChr("b"))


# ── Structural guard: gbnf.py is data + pure IR algebra, no procedural bodies ──


def test_gbnf_actions_and_reductions_carry_no_irlambda():
    """GBNF_ACTIONS and GBNF_REDUCTIONS contain no :class:`IrLambda` anywhere.

    gbnf.py holds zero ``def`` beyond dataclass/ABC machinery — its emit and
    parse halves are pure IR algebra. A stray :class:`IrLambda` escape hatch
    creeping back into either table would be a regression from that ruling.
    """
    assert not contains_ir_type(GBNF_ACTIONS.values(), IrLambda)
    assert not contains_ir_type(GBNF_REDUCTIONS.values(), IrLambda)


# ── Width-aware structure emission (trailing-pipe wrap) ───────────────────


def test_wide_alternation_wraps_and_round_trips():
    """Wide-rule structure-level doc emission: trailing-pipe wrap at indent
    6 (past 'name ::= '), no over-width line, reparse-canonicalize-equal,
    and width=None reproduces the pre-wrap flat single-line form."""
    flat_text = "wide-rule ::= " + " | ".join(
        f"alternative-name-number-{i}" for i in range(6)
    )
    assert_wide_rule_wraps_and_round_trips(GBNF_FLAVOUR, "|", flat_text)


# ── token terminals (README §Tokens) ────────────────────────────────────


def _tok_atom(text: str):
    """Parse a one-rule token grammar and return its first atom."""
    ast = parse_grammar(f"root ::= {text}", GBNF_FLAVOUR)
    return ast.rules[0].body[0][0].atom


def test_token_text_form_parses_to_alphabet_literal():
    """``<think>`` → an alphabet over the literal key (brackets included)."""
    assert _tok_atom("<think>") == IrAlphabet("tokens", IrLiteral("<think>"))


def test_token_id_form_parses_to_alphabet_charclass():
    """``<[1000]>`` → an alphabet over the id ordinal."""
    assert _tok_atom("<[1000]>") == IrAlphabet("tokens", IrCharClass(IrChr(1000)))


def test_token_negated_text_form():
    """``!<think>`` → negation INSIDE the alphabet (the encoding's complement)."""
    assert _tok_atom("!<think>") == IrAlphabet("tokens", IrNot(IrLiteral("<think>")))


def test_token_negated_id_form():
    """``!<[1001]>`` → negation INSIDE the id-form alphabet."""
    assert _tok_atom("!<[1001]>") == IrAlphabet(
        "tokens", IrNot(IrCharClass(IrChr(1001)))
    )


def test_any_char_parses_to_unicode_complement():
    """``.`` is any Unicode char — an ``IrNot`` of the empty class."""
    assert _tok_atom(".") == IrNot(IrCharClass())


def test_token_grammar_mixes_tokens_and_chars_in_one_rule():
    """The README root: token atoms and a Unicode ``.`` coexist in one sequence."""
    ast = parse_grammar(
        "root ::= <think> body </think> .*\nbody ::= [a-z]", GBNF_FLAVOUR
    )
    root = ast.rules[0].body[0]
    assert root[0].atom == IrAlphabet("tokens", IrLiteral("<think>"))
    assert root[2].atom == IrAlphabet("tokens", IrLiteral("</think>"))
    assert root[3].atom == IrNot(IrCharClass())
    assert root[3].quantifier == IrQuantifier(0, IrNone)


# ── token terminal EMIT (round-trip A) ──────────────────────────────────


def test_emit_text_form_token():
    """A text-form alphabet emits its literal key verbatim."""
    assert GBNF_FLAVOUR.apply(IrAlphabet("tokens", IrLiteral("<think>"))) == "<think>"


def test_emit_id_form_token():
    """An id-form alphabet emits ``<[id]>`` with the decimal id."""
    assert (
        GBNF_FLAVOUR.apply(IrAlphabet("tokens", IrCharClass(IrChr(1000)))) == "<[1000]>"
    )


def test_emit_negated_text_form_token():
    """A negated text-form token (IrNot INSIDE the alphabet) emits the ``!`` prefix."""
    assert (
        GBNF_FLAVOUR.apply(IrAlphabet("tokens", IrNot(IrLiteral("<think>"))))
        == "!<think>"
    )


def test_emit_negated_id_form_token():
    """A negated id-form token (IrNot INSIDE the alphabet) emits ``!<[id]>``."""
    assert (
        GBNF_FLAVOUR.apply(IrAlphabet("tokens", IrNot(IrCharClass(IrChr(1001)))))
        == "!<[1001]>"
    )


def test_token_grammar_round_trips_through_parse_emit_parse():
    """A token grammar is a parse/emit/parse fixpoint (`.` folds to `[^]`)."""
    txt = (
        "root ::= <think> thinking </think> .*\n"
        "thinking ::= !</think>*\n"
        "r2 ::= <[1000]> !<[1001]>*"
    )
    ast = parse_grammar(txt, GBNF_FLAVOUR)
    assert parse_grammar(GBNF_FLAVOUR.apply(ast), GBNF_FLAVOUR) == ast


# ── token id-range terminal `<[lo-hi]>` (README §Tokens) ─────────────────


def test_token_id_range_form_parses_to_alphabet_charclass_range():
    """``<[5-10]>`` → an alphabet over an ``IrRange`` inside the char class."""
    assert _tok_atom("<[5-10]>") == IrAlphabet(
        "tokens", IrCharClass(IrRange(IrChr(5), IrChr(10)))
    )


def test_token_id_single_form_still_parses_to_single_chr():
    """``<[5]>`` — the single-id form still reduces to one ``IrChr`` (regression pin)."""
    assert _tok_atom("<[5]>") == IrAlphabet("tokens", IrCharClass(IrChr(5)))


def test_token_negated_id_range_form():
    """``!<[5-10]>`` → negation INSIDE the alphabet, wrapping the range class."""
    assert _tok_atom("!<[5-10]>") == IrAlphabet(
        "tokens", IrNot(IrCharClass(IrRange(IrChr(5), IrChr(10))))
    )


def test_token_id_range_round_trips_through_parse_emit_parse():
    """``<[5-10]>`` is a parse/emit/parse and grammar-text fixpoint."""
    ast = parse_grammar("root ::= <[5-10]>", GBNF_FLAVOUR)
    emitted = str(GBNF_FLAVOUR.apply(ast))
    assert emitted == "root ::= <[5-10]>\n"
    assert parse_grammar(emitted, GBNF_FLAVOUR) == ast


def test_token_id_range_emits_lo_dash_hi():
    """A hand-built range-alphabet renders ``<[lo-hi]>``."""
    assert (
        GBNF_FLAVOUR.apply(
            IrAlphabet("tokens", IrCharClass(IrRange(IrChr(5), IrChr(10))))
        )
        == "<[5-10]>"
    )


def test_token_id_range_multidigit_round_trips():
    """A multi-digit range (``<[100-4095]>``) round-trips both sides of the dash."""
    ast = parse_grammar("root ::= <[100-4095]>", GBNF_FLAVOUR)
    emitted = str(GBNF_FLAVOUR.apply(ast))
    assert emitted == "root ::= <[100-4095]>\n"
    assert parse_grammar(emitted, GBNF_FLAVOUR) == ast


def test_gbnf_self_grammar_id_range_tail_split_is_island_free():
    """The ``tok-id``/``tok-id-tail`` left-factored split keeps the GBNF
    self-grammar free of islands and fail-islands."""
    analysis = GrammarAnalysis(lift_optional_nullables(GBNF_FLAVOUR.grammar))
    assert sorted(analysis.islands) == []
    assert sorted(analysis.fail_islands) == []
