"""GBNF_FLAVOUR mirror parity check."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.gbnf import (
    GBNF_ESCAPES,
    GBNF_FLAVOUR,
    GBNF_GRAMMAR,
    GBNF_NOISE,
    GBNF_QUANTIFIERS,
    GBNF_REDUCER,
    GBNF_REDUCTIONS,
)
from lexic.ir.base import IrNone
from lexic.ir.flavour import IrFlavour
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot
from lexic.parsing import derivations, parse_reduced
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce import DROP, KEEP_REDUCED, Reducer
from tests.unit.lexic.conftest import GRAMMAR_AST_TYPES


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


def test_decode_newline():
    """Backslash-n decodes to newline."""
    assert GBNF_ESCAPES.decode(r"\n") == "\n"


def test_decode_tab():
    """Backslash-t decodes to tab."""
    assert GBNF_ESCAPES.decode(r"\t") == "\t"


def test_decode_carriage_return():
    """Backslash-r decodes to carriage return."""
    assert GBNF_ESCAPES.decode(r"\r") == "\r"


def test_decode_backslash():
    """Double backslash decodes to single backslash."""
    assert GBNF_ESCAPES.decode(r"\\") == "\\"


def test_decode_quote():
    """Escaped quote decodes to double quote."""
    assert GBNF_ESCAPES.decode(r"\"") == '"'


def test_decode_plain_text():
    """Plain text decodes unchanged."""
    assert GBNF_ESCAPES.decode("abc") == "abc"


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


def test_round_trip():
    """encode(decode(x)) == x for a variety of characters."""
    escapes = GBNF_ESCAPES
    for raw in ["\n", "\t", "\\", '"', "hello", "\x00"]:
        assert escapes.decode(escapes.encode(raw)) == raw


def test_gbnf_emitter_iremit_default_unreachable():
    """Every IR-AST node type has an explicit action — IrEmit default never fires.

    If any type is missing an action, the emitter would fall through to its
    IrEmit default body and silently emit ``str(n)`` instead of raising.
    This test locks that the default is structurally unreachable for GBNF.
    """
    registered = set(GBNF_FLAVOUR.actions.keys())
    missing = GRAMMAR_AST_TYPES - registered
    assert not missing, f"GBNF_FLAVOUR missing explicit actions for: {missing}"


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


def _normalize_grammar(g: IrAst) -> IrAst:
    """Full normalization pipeline: flatten_groups -> desugar_quantifiers."""
    return normalize(g)


def _ruleref_names(seq: IrSequence) -> list[str]:
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
            for ref_name in _ruleref_names(arm):
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
    assert GBNF_REDUCER.reductions is GBNF_REDUCTIONS
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


def _first_item(result: IrAst):
    """The first item of the first rule's first arm, for single-item snippets."""
    rule = list(result.rules)[0]
    arm = list(rule.body)[0]
    return arm[0]


def test_plain_rule_and_ruleref_reduces():
    """'a ::= b' reduces to one rule 'a' with a single-item body ref to 'b'."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= b\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert result.start == "a"
    rule = list(result.rules)[0]
    assert rule.name == "a"
    item = _first_item(result)
    assert item.atom == IrRuleRef("b")


def test_item_default_quantifier_is_one_one():
    """An unquantified item defaults to IrQuantifier(1, 1)."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= b\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert _first_item(result).quantifier == IrQuantifier(1, 1)


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
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, f"a ::= b{suffix}\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert _first_item(result).quantifier == expected


def test_quantifier_noise_separated_from_atom():
    """'atom ?' (noise between atom and quantifier) still reduces to (0, 1)."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= b ?\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert _first_item(result).quantifier == IrQuantifier(0, 1)


def test_literal_newline_escape_decodes():
    """'\\n' inside a literal decodes to an actual newline."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, 'a ::= "\\n"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert _first_item(result).atom == IrLiteral("\n")


def test_literal_plain_char_stays_literal():
    """A plain character in a literal reduces unchanged."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, 'a ::= "A"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert _first_item(result).atom == IrLiteral("A")


def test_literal_unknown_escape_stays_verbatim():
    """An unrecognised escape ('\\q') keeps its backslash — decode() passthrough."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, 'a ::= "\\q"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert _first_item(result).atom == IrLiteral("\\q")


def test_literal_hex_escape_decodes_to_character():
    """'\\x41' inside a literal decodes to 'A' (hex2/4/8 → _HEX_GLYPH)."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, 'a ::= "\\x41"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert _first_item(result).atom == IrLiteral("A")


def test_literal_hex4_escape_decodes_to_character():
    """'\\u0042' (the 4-hex-digit form) inside a literal decodes to 'B'."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, 'a ::= "\\u0042"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert _first_item(result).atom == IrLiteral("B")


def test_literal_hex8_escape_decodes_to_character():
    """'\\U00000042' (the 8-hex-digit form) inside a literal decodes to 'B'."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, 'a ::= "\\U00000042"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert _first_item(result).atom == IrLiteral("B")


def test_charclass_range_reduces():
    """'[a-z]' reduces to a single-range IrCharClass."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= [a-z]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = _first_item(result).atom
    assert atom == IrCharClass(IrRange(IrChr("a"), IrChr("z")))


def test_charclass_run_of_singles_reduces():
    """'[abc]' — a run of single chars reduces to one IrChr code point each."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= [abc]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = _first_item(result).atom
    assert atom == IrCharClass(IrChr("a"), IrChr("b"), IrChr("c"))


def test_charclass_mixed_run_then_range_reduces():
    """'[abc0-9]' — a leading run of code points followed by a range."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= [abc0-9]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = _first_item(result).atom
    assert atom == IrCharClass(
        IrChr("a"), IrChr("b"), IrChr("c"), IrRange(IrChr("0"), IrChr("9"))
    )


def test_charclass_leading_dash_reduces():
    """'[-+*/]' — a leading bare dash is an ordinary unit, not a range marker."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= [-+*/]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = _first_item(result).atom
    assert atom == IrCharClass(IrChr("-"), IrChr("+"), IrChr("*"), IrChr("/"))


def test_charclass_trailing_dash_reduces():
    """'[a-]' — a trailing bare dash is an ordinary unit, not a range marker."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= [a-]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = _first_item(result).atom
    assert atom == IrCharClass(IrChr("a"), IrChr("-"))


def test_charclass_negation_reduces_to_irnot():
    """'[^\"]' reduces to IrNot wrapping the (unnegated) IrCharClass."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, 'a ::= [^"]\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = _first_item(result).atom
    assert atom == IrNot(IrCharClass(IrChr('"')))


def test_charclass_escaped_unit_reduces_to_irchr():
    r"""'[\t]' — the escaped tab reduces to IrChr(9)."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= [\\t]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = _first_item(result).atom
    assert atom == IrCharClass(IrChr(9))


def test_charclass_hex_range_reduces():
    r"""'[\x00-\x1f]' — a hex-escaped range reduces to IrRange over IrChr endpoints."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= [\\x00-\\x1f]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = _first_item(result).atom
    assert atom == IrCharClass(IrRange(IrChr(0), IrChr(0x1F)))


def test_group_reduces_to_bare_alternation_atom():
    """'(b | c)' reduces to a bare IrAlternation atom (no separate group node)."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= (b | c)\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = _first_item(result).atom
    assert isinstance(atom, IrAlternation)
    assert atom == IrAlternation(
        IrSequence(IrItem(IrRuleRef("b"))), IrSequence(IrItem(IrRuleRef("c")))
    )


def test_empty_arm_reduces_to_empty_sequence():
    """'ws ::= | " "' — GBNF allows an empty alternation arm."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, 'ws ::= | " "\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rule = list(result.rules)[0]
    arms = list(rule.body)
    assert len(arms) == 2
    assert arms[0] == IrSequence()
    assert arms[1] == IrSequence(IrItem(IrLiteral(" ")))


def test_fully_empty_body_reduces_to_single_empty_arm():
    """'a ::=' (no body at all) is a single-arm rule with an empty sequence."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::=\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rule = list(result.rules)[0]
    assert rule.body == IrAlternation(IrSequence())


def test_comment_line_between_rules_is_noise():
    """A '# comment' line between two rules is dropped; both rules survive."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= b\n# c\nc ::= d\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rules = list(result.rules)
    assert [r.name for r in rules] == ["a", "c"]
    assert rules[0].body[0][0].atom == IrRuleRef("b")
    assert rules[1].body[0][0].atom == IrRuleRef("d")


def test_trailing_comment_without_newline_at_eof():
    """An unterminated '# comment' at EOF (no trailing '\\n') still parses."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "a ::= b\n# c", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rules = list(result.rules)
    assert len(rules) == 1
    assert rules[0].name == "a"


def test_directive_comment_is_ignored_by_the_grammar():
    """A '# @directive'-shaped line is just an ordinary comment to GBNF_GRAMMAR
    (directives are extracted from raw text before the meta-grammar parser
    runs; the self-grammar itself has no directive awareness)."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, "# @start a\na ::= b\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rules = list(result.rules)
    assert len(rules) == 1
    assert rules[0].name == "a"


def test_multiline_rule_continuation():
    """An alternation's second arm on its own indented line still joins the
    same rule (noise absorbs the line break and leading whitespace)."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    result = parse_reduced(g, 'a ::= "x"\n    | "y"\n', GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rule = list(result.rules)[0]
    arms = list(rule.body)
    assert len(arms) == 2
    assert arms[0][0].atom == IrLiteral("x")
    assert arms[1][0].atom == IrLiteral("y")


# ── Ambiguity guards ──────────────────────────────────────────────────────


def test_two_char_name_is_unambiguous():
    """'a ::= bc' has exactly one derivation: ONE two-char ruleref, not two."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    assert len(derivations(g, "a ::= bc\n")) == 1
    result = parse_reduced(g, "a ::= bc\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    rule = list(result.rules)[0]
    arm = list(rule.body)[0]
    assert len(arm) == 1
    assert arm[0].atom == IrRuleRef("bc")


def test_rule_boundary_is_unambiguous():
    """'a ::= b\\nc ::= d' has exactly one derivation: two separate rules."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    text = "a ::= b\nc ::= d\n"
    assert len(derivations(g, text)) == 1
    result = parse_reduced(g, text, GBNF_REDUCER)
    assert isinstance(result, IrAst)
    assert [r.name for r in result.rules] == ["a", "c"]


def test_charclass_range_vs_dash_is_unambiguous():
    """'a ::= [0-9]' has exactly one derivation: a range, not unit-dash-unit."""
    g = _normalize_grammar(GBNF_GRAMMAR)
    assert len(derivations(g, "a ::= [0-9]\n")) == 1
    result = parse_reduced(g, "a ::= [0-9]\n", GBNF_REDUCER)
    assert isinstance(result, IrAst)
    atom = _first_item(result).atom
    assert atom == IrCharClass(IrRange(IrChr("0"), IrChr("9")))
