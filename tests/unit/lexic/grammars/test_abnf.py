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
    ABNF_PREFIX_QUANTIFIER,
    META_GRAMMAR,
)
from lexic.grammars.flavour import IrFlavour
from lexic.ir.base import IrNone, IrStr
from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
)
from lexic.ir.operators import IrNot
from lexic.parsing.meta_parser import MetaGrammarParser
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
    assert arm[0].atom == IrCharClass(IrStr("aA"))
    assert arm[1].atom == IrCharClass(IrStr("bB"))
    assert arm[2].atom == IrCharClass(IrStr("cC"))


def test_normalize_literal_all_caps_still_expands():
    """All-caps is still case-expanded."""
    out = ABNF_FLAVOUR.normalize_literal("XY")
    assert isinstance(out, IrAlternation)
    arm = out[0]
    assert arm[0].atom == IrCharClass(IrStr("xX"))
    assert arm[1].atom == IrCharClass(IrStr("yY"))


def test_normalize_literal_non_alpha_stays_literal():
    """Punctuation has no case; keep as IrLiteral."""
    out = ABNF_FLAVOUR.normalize_literal("(){}")
    assert out == IrLiteral("(){}")


def test_normalize_literal_mixed_alphanumeric():
    """Letters case-expanded, digits stay literal — emit as group with mixed leaves."""
    out = ABNF_FLAVOUR.normalize_literal("a1")
    assert isinstance(out, IrAlternation)
    arm = out[0]
    assert arm[0].atom == IrCharClass(IrStr("aA"))
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
    cls = IrCharClass(IrRange("A", "Z"))
    assert ABNF_FLAVOUR.apply(cls) == "%x41-5A"


def test_abnf_charclass_run_single_char_emits_single_hex():
    """A single-char run emits one ``%xNN`` atom (no parens)."""
    cls = IrCharClass(IrStr("A"))
    assert ABNF_FLAVOUR.apply(cls) == "%x41"


def test_abnf_charclass_run_multiple_chars_emits_parenthesised_alternation():
    """A multi-char run emits ``(%xNN / %xMM / …)``."""
    cls = IrCharClass(IrStr("abc"))
    assert ABNF_FLAVOUR.apply(cls) == "(%x61 / %x62 / %x63)"


def test_abnf_charclass_mixed_run_and_range():
    """A run followed by a range emits all atoms parenthesised."""
    cls = IrCharClass(IrStr("abc"), IrRange("A", "Z"))
    assert ABNF_FLAVOUR.apply(cls) == "(%x61 / %x62 / %x63 / %x41-5A)"


def test_abnf_irnot_raises_unsupported():
    """ABNF has no native negation — IrNot raises UnsupportedConstructError."""
    with pytest.raises(UnsupportedConstructError):
        ABNF_FLAVOUR.apply(IrNot(IrCharClass(IrRange("a", "z"))))


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
