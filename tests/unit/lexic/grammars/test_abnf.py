# tests/unit/lexic/grammars/abnf/test_flavour.py
"""ABNF_FLAVOUR — full IrFlavour binding for the minimal-ABNF subset."""

from __future__ import annotations

from pathlib import Path

import pytest
from lark import Lark

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import (
    ABNF_ESCAPES,
    ABNF_FLAVOUR,
    ABNF_GRAMMAR,
    ABNF_PREFIX_QUANTIFIER,
    ABNF_REDUCER,
    ABNF_REDUCTIONS,
    META_GRAMMAR,
)
from lexic.ir.base import IrNone, IrSeq
from lexic.ir.escapes import EscapeCodec
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
)
from lexic.ir.operators import IrNot
from lexic.parsing.meta_parser import MetaGrammarParser
from lexic.parsing_2 import parse, recognize
from lexic.parsing_2.forest import ParseTree
from lexic.parsing_2.normalize import normalize
from lexic.parsing_2.reduce import YIELD, Reducer
from tests.unit.lexic.conftest import GRAMMAR_AST_TYPES


def test_abnf_flavour_is_a_flavour():
    """`ABNF_FLAVOUR` is an `IrFlavour` singleton."""
    assert isinstance(ABNF_FLAVOUR, IrFlavour)


def test_abnf_flavour_metadata():
    """`ABNF_FLAVOUR` has expected metadata"""
    assert ABNF_FLAVOUR.name == "abnf"
    assert ".abnf" in ABNF_FLAVOUR.extensions
    assert ABNF_FLAVOUR.line_comment == ";"


# ── parse_quantifier ─────────────────────────────────────────────────


def test_parse_quantifier_star_means_zero_or_more():
    """`"*"` -> `IrQuantifier(0, IrNone)`"""
    assert ABNF_FLAVOUR.parse_quantifier("*") == IrQuantifier(0, IrNone)


def test_parse_quantifier_n_star_means_n_or_more():
    """`"1*"` -> `IrQuantifier(1, IrNone)`"""
    assert ABNF_FLAVOUR.parse_quantifier("1*") == IrQuantifier(1, IrNone)
    assert ABNF_FLAVOUR.parse_quantifier("3*") == IrQuantifier(3, IrNone)


def test_parse_quantifier_star_n_means_zero_to_n():
    """`"*5"` -> `IrQuantifier(0, 5)`"""
    assert ABNF_FLAVOUR.parse_quantifier("*5") == IrQuantifier(0, 5)


def test_parse_quantifier_n_star_m_means_n_to_m():
    """`"2*5"` -> `IrQuantifier(2, 5)`"""
    assert ABNF_FLAVOUR.parse_quantifier("2*5") == IrQuantifier(2, 5)


def test_parse_quantifier_n_alone_means_exactly_n():
    """`"3"` -> `IrQuantifier(3, 3)"""
    assert ABNF_FLAVOUR.parse_quantifier("3") == IrQuantifier(3, 3)


# ── parse_charclass ──────────────────────────────────────────────────


def test_parse_charclass_single_hex():
    """`%x41` → POSIX 'A'."""
    pattern, negated = ABNF_FLAVOUR.parse_charclass("%x41")
    assert pattern == "A"
    assert negated is False


def test_parse_charclass_hex_range():
    """`%x41-5A` → POSIX 'A-Z'."""
    pattern, negated = ABNF_FLAVOUR.parse_charclass("%x41-5A")
    assert pattern == "A-Z"
    assert negated is False


# ── normalize_literal — case-insensitive expansion ───────────────────


def test_normalize_literal_alpha_expands_to_charclass_group():
    """`"abc"` in ABNF is case-insensitive; expand to ([aA] [bB] [cC])."""
    out = ABNF_FLAVOUR.normalize_literal("abc")
    assert isinstance(out, IrAlternation)
    arm = out[0]
    assert arm[0].atom == IrCharClass(IrChr("a"), IrChr("A"))
    assert arm[1].atom == IrCharClass(IrChr("b"), IrChr("B"))
    assert arm[2].atom == IrCharClass(IrChr("c"), IrChr("C"))


def test_normalize_literal_all_caps_still_expands():
    """All-caps is still case-expanded."""
    out = ABNF_FLAVOUR.normalize_literal("XY")
    assert isinstance(out, IrAlternation)
    arm = out[0]
    assert arm[0].atom == IrCharClass(IrChr("x"), IrChr("X"))
    assert arm[1].atom == IrCharClass(IrChr("y"), IrChr("Y"))


def test_normalize_literal_non_alpha_stays_literal():
    """Punctuation has no case; keep as IrLiteral."""
    out = ABNF_FLAVOUR.normalize_literal("(){}")
    assert out == IrLiteral("(){}")


def test_normalize_literal_mixed_alphanumeric():
    """Letters case-expanded, digits stay literal — emit as group with mixed leaves."""
    out = ABNF_FLAVOUR.normalize_literal("a1")
    assert isinstance(out, IrAlternation)
    arm = out[0]
    assert arm[0].atom == IrCharClass(IrChr("a"), IrChr("A"))
    assert arm[1].atom == IrLiteral("1")


# ── End-to-end: parse a small ABNF sample ────────────────────────────


def test_parse_simple_abnf_grammar_via_meta_parser():
    """Parse a small ABNF sample via MetaGrammarParser."""
    text = (
        "; @non-semantic WSP\n"
        "root = expr\n"
        "expr = num *(op num)\n"
        "num  = 1*DIGIT\n"
        "DIGIT = %x30-39\n"
        'op   = "+" / "-"\n'
        "WSP  = %x20 / %x09\n"
    )
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse(text)
    rule_names = {r.name for r in ast.rules}
    assert rule_names == {"root", "expr", "num", "DIGIT", "op", "WSP"}


def test_abnf_escapes_is_an_escape_codec():
    """ABNF_ESCAPES is an EscapeCodec singleton."""
    assert isinstance(ABNF_ESCAPES, EscapeCodec)


def test_decode_is_identity():
    """Decode is identity. ABNF literals are already canonical Python strings."""
    assert ABNF_ESCAPES.decode("hello") == "hello"
    assert ABNF_ESCAPES.decode("") == ""
    assert ABNF_ESCAPES.decode("ab\\cd") == "ab\\cd"
    assert ABNF_ESCAPES.decode("\\n") == "\\n"
    assert ABNF_ESCAPES.decode("\\t") == "\\t"


def test_encode_is_identity():
    """Encode is identity. ABNF literals are already canonical Python strings."""
    assert ABNF_ESCAPES.encode("hello") == "hello"
    assert ABNF_ESCAPES.encode("") == ""
    assert ABNF_ESCAPES.encode("ab\\cd") == "ab\\cd"
    assert ABNF_ESCAPES.encode("\n") == "\n"


def test_read_escape_passes_through_unknown():
    """read_escape on an unrecognised sequence returns the raw follow-char."""
    char, new_i = ABNF_ESCAPES.read_escape("\\n", 0)
    assert char == "n"
    assert new_i == 2


def test_meta_grammar_is_a_string():
    """The meta-grammar must be a string."""
    assert isinstance(META_GRAMMAR, str)


def test_meta_grammar_is_nonempty():
    """The meta-grammar must not be empty or whitespace-only."""
    assert len(META_GRAMMAR.strip()) > 0


def test_meta_grammar_uses_canonical_tag_names():
    """The grammar must use ir_rule / ir_alternation / ir_sequence / ir_item /
    ir_literal / ir_charclass / ir_ruleref / ir_group tags."""
    for tag in (
        "ir_rule",
        "ir_alternation",
        "ir_sequence",
        "ir_item",
        "ir_literal",
        "ir_charclass",
        "ir_ruleref",
        "ir_group",
    ):
        assert f"-> {tag}" in META_GRAMMAR, f"missing tag {tag}"


def test_meta_grammar_constructs_a_valid_lark():
    """No syntax errors in the meta-grammar."""
    Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")


def test_meta_grammar_ignores_comments_and_whitespace():
    """The meta-grammar must ignore ABNF semicolon comments and whitespace."""
    parser = Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
    parser.parse('; a comment\nfoo = "x"\n')


def test_meta_grammar_parses_hex_charclass():
    """The meta-grammar must parse %xNN and %xNN-MM hex character classes."""
    parser = Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
    parser.parse("DIGIT = %x30-39\n")
    parser.parse("SP = %x20\n")


def test_meta_grammar_parses_prefix_quantifiers():
    """The meta-grammar must parse ABNF prefix quantifier forms."""
    parser = Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
    parser.parse('foo = *bar\nbaz = 1*bar\nqux = 2*5bar\nbar = "x"\n')


def test_meta_grammar_parses_alternation_with_slash():
    """ABNF alternation uses `/` not `|`."""
    parser = Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
    parser.parse('foo = "a" / "b" / "c"\n')


def test_abnf_emitter_iremit_default_unreachable():
    """Every IR-AST node type has an explicit action — IrEmit default never fires.

    If any type is missing an action, the emitter would fall through to its
    IrEmit default body and silently emit ``str(n)`` instead of raising.
    This test locks that the default is structurally unreachable for ABNF.
    """
    registered = set(ABNF_FLAVOUR.actions.keys())
    missing = GRAMMAR_AST_TYPES - registered
    assert not missing, f"ABNF_FLAVOUR missing explicit actions for: {missing}"


# ── Structured IrCharClass emission ──────────────────────────────────


def test_abnf_charclass_range_emits_hex_range():
    """A range IrCharClass emits ``%xNN-MM``."""
    cls = IrCharClass(IrRange(IrChr("A"), IrChr("Z")))
    assert ABNF_FLAVOUR.apply(cls) == "%x41-5A"


def test_abnf_charclass_run_single_char_emits_single_hex():
    """A single code point emits one ``%xNN`` atom (no parens)."""
    cls = IrCharClass(IrChr("A"))
    assert ABNF_FLAVOUR.apply(cls) == "%x41"


def test_abnf_charclass_run_multiple_chars_emits_parenthesised_alternation():
    """Multiple code points emit ``(%xNN / %xMM / …)``."""
    cls = IrCharClass(IrChr("a"), IrChr("b"), IrChr("c"))
    assert ABNF_FLAVOUR.apply(cls) == "(%x61 / %x62 / %x63)"


def test_abnf_charclass_mixed_run_and_range():
    """Code points followed by a range emit all atoms parenthesised."""
    cls = IrCharClass(
        IrChr("a"), IrChr("b"), IrChr("c"), IrRange(IrChr("A"), IrChr("Z"))
    )
    assert ABNF_FLAVOUR.apply(cls) == "(%x61 / %x62 / %x63 / %x41-5A)"


def test_abnf_irnot_raises_unsupported():
    """ABNF has no native negation — IrNot raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError):
        ABNF_FLAVOUR.apply(IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z")))))


# ── ABNF quantifier emission matrix ──────────────────────────────────


def _emit_q(q: IrQuantifier) -> str:
    """Evaluate ``ABNF_PREFIX_QUANTIFIER`` for ``q`` and return the string result.

    :param q: The quantifier to evaluate.
    :returns: The emitted ABNF quantifier string.
    """
    return str(ABNF_PREFIX_QUANTIFIER.eval(ABNF_FLAVOUR, q, ()))


@pytest.mark.parametrize(
    "quantifier, expected",
    [
        (IrQuantifier(1, 1), ""),
        (IrQuantifier(0, IrNone), "*"),
        # Regression: N* forms with N != 0 were silently mishandled.
        (IrQuantifier(1, IrNone), "1*"),
        (IrQuantifier(2, IrNone), "2*"),  # the fixed regression — MUST stay pinned
        (IrQuantifier(7, IrNone), "7*"),
        (IrQuantifier(3, 3), "3"),
        (IrQuantifier(0, 5), "*5"),
        (IrQuantifier(2, 5), "2*5"),
        (IrQuantifier(0, 1), "*1"),
        (IrQuantifier(1, 3), "1*3"),
    ],
    ids=[
        "exactly-once",
        "zero-or-more",
        "one-or-more",
        "two-or-more-regression",
        "seven-or-more",
        "exactly-three",
        "zero-to-five",
        "two-to-five",
        "zero-to-one",
        "one-to-three",
    ],
)
def test_abnf_quantifier_emission_matrix(quantifier: IrQuantifier, expected: str):
    """``ABNF_PREFIX_QUANTIFIER.eval`` emits the authoritative ABNF prefix string.

    Each row pins one case; the ``2*`` row guards the regression that was fixed.
    """
    assert _emit_q(quantifier) == expected


# ── Round-trip: parse_quantifier → emit ──────────────────────────────


@pytest.mark.parametrize(
    "text",
    ["*", "*5", "2*", "2*5", "3"],
    ids=["star", "star-N", "N-star", "N-star-M", "exactly-N"],
)
def test_abnf_quantifier_round_trip(text: str):
    """``_emit_q(parse_quantifier(s)) == s`` for canonical ABNF quantifier strings."""
    assert _emit_q(ABNF_FLAVOUR.parse_quantifier(text)) == text


def test_abnf_quantifier_default_emits_empty():
    """``IrQuantifier()`` (the ``(1, 1)`` default) emits the empty string.

    ``parse_quantifier`` does not handle the empty token — the meta-parser
    synthesises ``IrQuantifier()`` directly, so this case is tested by
    constructing the default quantifier directly.
    """
    assert _emit_q(IrQuantifier()) == ""


# ── End-to-end: IrItem with 2* prefix through ABNF_FLAVOUR.apply ─────


def test_abnf_item_with_n_star_quantifier_emits_prefix_form():
    """A full ``IrItem`` with ``2*`` quantifier emits ``"2*<atom>"`` via ``ABNF_FLAVOUR.apply``.

    Covers the ``2*``-style prefix path end-to-end through the action table,
    not just the quantifier map in isolation.
    """
    item = IrItem(atom=IrRuleRef("foo"), quantifier=IrQuantifier(2, IrNone))
    assert str(ABNF_FLAVOUR.apply(item)) == "2*foo"


# ── New constructs ────────────────────────────────────────────────────


def test_parse_charclass_decimal():
    """`%d65` → ``('A', False)`` (radix 10)."""
    pattern, negated = ABNF_FLAVOUR.parse_charclass("%d65")
    assert pattern == "A"
    assert negated is False


def test_parse_charclass_binary():
    """`%b1000001` → ``('A', False)`` (radix 2)."""
    pattern, negated = ABNF_FLAVOUR.parse_charclass("%b1000001")
    assert pattern == "A"
    assert negated is False


def test_numseq_value_sequence_becomes_ir_literal():
    """``%x66.61.6c.73.65`` → :class:`IrLiteral` ``\"false\"`` (case-sensitive)."""
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse("false = %x66.61.6c.73.65\n")
    item = ast.rules[0].body[0][0]
    assert isinstance(item.atom, IrLiteral)
    assert item.atom == IrLiteral("false")


def test_cs_string_becomes_raw_ir_literal():
    """``%s"true"`` → :class:`IrLiteral` ``\"true\"`` with no case expansion."""
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse('foo = %s"true"\n')
    item = ast.rules[0].body[0][0]
    assert isinstance(item.atom, IrLiteral)
    assert item.atom == IrLiteral("true")


def test_ci_string_becomes_case_insensitive_alternation():
    """``%i"abc"`` → case-insensitive expansion (an :class:`IrAlternation`)."""
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse('foo = %i"abc"\n')
    item = ast.rules[0].body[0][0]
    assert isinstance(item.atom, IrAlternation)


def test_optional_bracket_produces_quantifier_0_1():
    """``[ "x" ]`` → an :class:`IrItem` with :class:`IrQuantifier` ``(0, 1)``."""
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse('foo = [ "x" ]\n')
    item = ast.rules[0].body[0][0]
    assert isinstance(item, IrItem)
    assert item.quantifier == IrQuantifier(0, 1)


def test_incremental_alternatives_merge_into_one_rule():
    """``=/`` arms are merged into the earlier same-named rule's alternation."""
    text = 'foo = "a"\nfoo =/ "b"\nfoo =/ "c"\n'
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse(text)
    assert len(ast.rules) == 1
    rule = ast.rules[0]
    assert rule.name == "foo"
    assert len(rule.body) == 3


def test_prose_val_raises_unsupported_construct_error():
    """``<...>`` prose-val raises :class:`UnsupportedConstructError`."""
    with pytest.raises(UnsupportedConstructError):
        MetaGrammarParser(ABNF_FLAVOUR).parse("foo = <any prose text>\n")


def test_json_abnf_ground_truth_parses_32_rules():
    """Parsing ``resources/ground_truth/json.abnf`` yields 32 rules."""
    path = Path(__file__).parents[4] / "resources" / "ground_truth" / "json.abnf"
    ast = MetaGrammarParser(ABNF_FLAVOUR).parse(path.read_text(encoding="utf-8"))
    assert len(ast.rules) == 32


# ── ABNF_GRAMMAR / ABNF_REDUCTIONS — native IR grammar + reducer ──────────
#
# Formerly tests/unit/lexic/grammars/test_abnf_2.py. API changes carried over
# from that file's own header:
#
# - ``EarleyParser().parse(g, t)`` → module-level ``parse(g, t)``.
# - ``Reducer(...).reduce(tree)`` → ``Reducer(...).apply(tree)``.


def _normalize_grammar(g: IrAst) -> IrAst:
    """Full normalization pipeline: flatten_groups -> desugar_quantifiers.

    Multi-char literals stay atomic (no split_literals step).
    """
    return normalize(g)


# ── ABNF_GRAMMAR structure ────────────────────────────────────────────


def test_abnf_grammar_is_ir_ast():
    """ABNF_GRAMMAR is an IrAst."""
    assert isinstance(ABNF_GRAMMAR, IrAst)


def test_abnf_grammar_start_rule_is_rulelist():
    """ABNF_GRAMMAR start rule is 'rulelist'."""
    assert ABNF_GRAMMAR.start == "rulelist"


def test_abnf_grammar_has_expected_rule_count():
    """ABNF_GRAMMAR has at least 20 rules (RFC 5234 §4 subset)."""
    assert len(list(ABNF_GRAMMAR.rules)) >= 20


def test_abnf_grammar_rule_names_include_core():
    """ABNF_GRAMMAR contains expected core rule names."""
    names = {r.name for r in ABNF_GRAMMAR.rules}
    for expected in (
        "rulelist",
        "rule",
        "rulename",
        "alternation",
        "concatenation",
        "repetition",
    ):
        assert expected in names, f"Missing rule: {expected}"


# ── ABNF_GRAMMAR emits as well-formed ABNF ───────────────────────────


def test_abnf_grammar_emits_non_empty_string():
    """ABNF_FLAVOUR.apply(ABNF_GRAMMAR) returns a non-empty string."""
    result = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert isinstance(result, str)
    assert len(result.strip()) > 0


def test_abnf_grammar_emitted_text_contains_rulelist():
    """The emitted ABNF text contains the 'rulelist' rule definition."""
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert "rulelist" in text


def test_abnf_grammar_emitted_text_contains_equals():
    """The emitted ABNF text contains '=' rule assignments."""
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert " = " in text


# ── ABNF_REDUCTIONS structure ─────────────────────────────────────────


def test_abnf_reductions_is_ir_map():
    """ABNF_REDUCTIONS is an IrMap."""
    assert isinstance(ABNF_REDUCTIONS, IrMap)


def test_abnf_reductions_covers_all_structural_rules():
    """ABNF_REDUCTIONS has entries for all structural rules."""
    for rule_name in (
        "rulelist",
        "rule",
        "rulename",
        "alternation",
        "concatenation",
        "repetition",
        "element",
        "group",
        "char-val",
        "num-val",
    ):
        assert ABNF_REDUCTIONS[IrRuleRef(rule_name)] is not None, (
            f"Missing reduction for {rule_name!r}"
        )


def test_abnf_reductions_covers_terminal_rules():
    """Terminal rules resolve through IR_DEFAULT → YIELD (no explicit entry)."""
    for rule_name in ("ALPHA", "DIGIT", "HEXDIG", "CR", "LF", "SP", "HTAB", "DQUOTE"):
        assert ABNF_REDUCTIONS.resolve(IrRuleRef(rule_name)) is YIELD, (
            f"Expected YIELD for {rule_name!r}"
        )


# ── ABNF_REDUCTIONS leaf reductions on simple trees ───────────────────


def test_rulename_reduction_yields_irruleref():
    """rulename reduction: children joined -> IrRuleRef."""
    reducer = Reducer(reductions=ABNF_REDUCTIONS)
    tree = ParseTree(IrRuleRef("rulename"), IrSeq(IrLiteral("a"), IrLiteral("b")))
    result = reducer.apply(tree)
    assert isinstance(result, IrRuleRef)
    assert str(result) == "ab"


def test_char_val_alpha_reduces_to_case_insensitive_alternation():
    """char-val with letters reduces to a case-insensitive IrAlternation (RFC 7405).

    Ported from the old case-sensitive-literal assertion after the Phase 3
    re-author made char-val case-insensitive, matching ``normalize_literal``.
    """
    g = _normalize_grammar(ABNF_GRAMMAR)
    result = ABNF_REDUCER.apply(parse(g, 'x = "ab"\n'))
    assert isinstance(result, IrAst)
    atom = list(list(result.rules)[0].body)[0][0].atom
    assert isinstance(atom, IrAlternation)
    seq = atom[0]
    assert seq[0].atom == IrCharClass(IrChr("a"), IrChr("A"))
    assert seq[1].atom == IrCharClass(IrChr("b"), IrChr("B"))


def _hexdig(ch: str) -> ParseTree:
    """Wrap a single hex character in a HEXDIG ParseTree (as the real parser produces)."""
    return ParseTree(IrRuleRef("HEXDIG"), IrSeq(IrLiteral(ch)))


def test_num_single_yields_ircharclass_chr():
    """num-single over a hexits subtree yields IrCharClass(IrChr('A'))."""
    hexits = ParseTree(IrRuleRef("hexits"), IrSeq(_hexdig("4"), _hexdig("1")))
    tree = ParseTree(
        IrRuleRef("num-single"),
        IrSeq(IrLiteral("%"), IrLiteral("x"), hexits),
    )
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrCharClass)
    assert result == IrCharClass(IrChr("A"))


def test_num_range_yields_ircharclass_range():
    """num-range over two hexits subtrees yields IrCharClass(IrRange('A','Z'))."""
    lo = ParseTree(IrRuleRef("hexits"), IrSeq(_hexdig("4"), _hexdig("1")))
    hi = ParseTree(IrRuleRef("hexits"), IrSeq(_hexdig("5"), _hexdig("A")))
    tree = ParseTree(
        IrRuleRef("num-range"),
        IrSeq(IrLiteral("%"), IrLiteral("x"), lo, IrLiteral("-"), hi),
    )
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrCharClass)
    assert result == IrCharClass(IrRange(IrChr("A"), IrChr("Z")))


# ── In-subset single-rule parse+reduce ───────────────────────────────


def test_parse_reduce_single_literal_rule():
    """'s = \"+-\"' parses and reduces to IrAst with IrLiteral('+-') item.

    Uses a non-alpha literal: an alpha literal case-expands (RFC 7405), so a
    bare-``IrLiteral`` assertion needs a body with no letters.
    """
    g = _normalize_grammar(ABNF_GRAMMAR)
    tree = parse(g, 's = "+-"\n')
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrAst)
    assert result.start == "s"
    rules = list(result.rules)
    assert rules[0].name == "s"
    arm = list(rules[0].body)[0]
    item = arm[0]
    assert item.atom == IrLiteral("+-")
    assert item.quantifier == IrQuantifier(1, 1)


def test_parse_reduce_alternation_rule():
    """'s = foo / bar' reduces to two-arm IrAlternation of IrRuleRef atoms."""
    g = _normalize_grammar(ABNF_GRAMMAR)
    text = 's = foo / bar\nfoo = "x"\nbar = "y"\n'
    tree = parse(g, text)
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrAst)
    s_rule = list(result.rules)[0]
    assert s_rule.name == "s"
    arms = list(s_rule.body)
    assert len(arms) == 2
    assert arms[0][0].atom == IrRuleRef("foo")
    assert arms[1][0].atom == IrRuleRef("bar")


def test_parse_reduce_charclass_rule():
    """'x = %x41-5A' reduces to IrCharClass(IrRange('A','Z'))."""
    g = _normalize_grammar(ABNF_GRAMMAR)
    text = "x = %x41-5A\n"
    tree = parse(g, text)
    result = ABNF_REDUCER.apply(tree)
    assert isinstance(result, IrAst)
    rules = list(result.rules)
    item = list(rules[0].body)[0][0]
    assert isinstance(item.atom, IrCharClass)
    assert item.atom == IrCharClass(IrRange(IrChr("A"), IrChr("Z")))


def _quant_of(text: str) -> IrQuantifier:
    """Parse a one-rule ABNF snippet and return its single item's quantifier."""
    g = _normalize_grammar(ABNF_GRAMMAR)
    result = ABNF_REDUCER.apply(parse(g, text))
    assert isinstance(result, IrAst)
    return list(list(result.rules)[0].body)[0][0].quantifier


def test_repeat_exact_quantifier():
    """'5"a"' → IrQuantifier(5, 5)."""
    assert _quant_of('x = 5"a"\n') == IrQuantifier(5, 5)


def test_repeat_range_quantifier():
    """'1*5"a"' → IrQuantifier(1, 5)."""
    assert _quant_of('x = 1*5"a"\n') == IrQuantifier(1, 5)


def test_repeat_open_upper_quantifier():
    """'5*"a"' → IrQuantifier(5, IrNone) — empty hi-bound is unbounded."""
    assert _quant_of('x = 5*"a"\n') == IrQuantifier(5, IrNone)


def test_repeat_open_lower_quantifier():
    """'*5"a"' → IrQuantifier(0, 5) — empty lo-bound is zero."""
    assert _quant_of('x = *5"a"\n') == IrQuantifier(0, 5)


def test_repeat_star_quantifier():
    """'*"a"' → IrQuantifier(0, IrNone) — both bounds empty."""
    assert _quant_of('x = *"a"\n') == IrQuantifier(0, IrNone)


def test_repeat_absent_defaults_to_one_one():
    """No repeat prefix → repeat-opt defaults to IrQuantifier(1, 1)."""
    assert _quant_of('x = "a"\n') == IrQuantifier(1, 1)


def test_num_single_parse_reduce():
    """'x = %x41' reduces to IrCharClass(IrChr('A'))."""
    g = _normalize_grammar(ABNF_GRAMMAR)
    result = ABNF_REDUCER.apply(parse(g, "x = %x41\n"))
    assert isinstance(result, IrAst)
    item = list(list(result.rules)[0].body)[0][0]
    assert item.atom == IrCharClass(IrChr("A"))


# ── THE SELF-HOSTING FIXPOINT ─────────────────────────────────────────


def test_self_hosting_recognize():
    """normalize(ABNF_GRAMMAR) recognizes its own emitted text."""
    g = _normalize_grammar(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    assert recognize(g, text)


def test_self_hosting_fixpoint():
    """The headline test: parse(normalize(ABNF_GRAMMAR), emitted_text) reduced
    through ABNF_REDUCER equals ABNF_GRAMMAR."""
    g = _normalize_grammar(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    tree = parse(g, text)
    result = ABNF_REDUCER.apply(tree)
    assert result == ABNF_GRAMMAR


def test_self_hosting_fixpoint_idempotent():
    """Reduce → re-emit → re-parse → re-reduce: result is the same IrAst."""
    g = _normalize_grammar(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))

    # First round
    tree1 = parse(g, text)
    result1 = ABNF_REDUCER.apply(tree1)
    assert isinstance(result1, IrAst)

    # Re-emit and re-parse
    text2 = str(ABNF_FLAVOUR.apply(result1))
    tree2 = parse(g, text2)
    result2 = ABNF_REDUCER.apply(tree2)

    assert result2 == result1
    assert result2 == ABNF_GRAMMAR


def test_self_hosting_crlf_recognized():
    """CRLF line endings in the emitted text are recognized and parse correctly."""
    g = _normalize_grammar(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    text_crlf = text.replace("\n", "\r\n")
    assert recognize(g, text_crlf)


def test_self_hosting_crlf_reduces_to_abnf_grammar():
    """CRLF-terminated emitted text reduces back to ABNF_GRAMMAR."""
    g = _normalize_grammar(ABNF_GRAMMAR)
    text = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
    text_crlf = text.replace("\n", "\r\n")
    tree = parse(g, text_crlf)
    result = ABNF_REDUCER.apply(tree)
    assert result == ABNF_GRAMMAR
