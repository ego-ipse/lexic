"""EBNF_FLAVOUR — the production ISO-family EBNF flavour (gbnf.py/abnf.py shape)."""

from __future__ import annotations

import pytest

from lexic.compile import parse_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import flavour_for_extension, get_flavour
from lexic.grammars.ebnf import (
    EBNF_ACTIONS,
    EBNF_ESCAPES,
    EBNF_FLAVOUR,
    EBNF_GRAMMAR,
    EBNF_REDUCTIONS,
)
from lexic.ir import (
    EscapeCodec,
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrFlavour,
    IrItem,
    IrLambda,
    IrLiteral,
    IrNone,
    IrNot,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
    canonicalize,
)
from tests.unit.lexic.conftest import GRAMMAR_AST_TYPES, contains_ir_type, wide_grammar


def first_item(text: str) -> IrItem:
    """Parse ``text`` under EBNF_FLAVOUR and drill into its first rule's
    first arm's first item.

    :param text: A single-rule EBNF grammar string.
    :returns: The parsed :class:`IrItem`.
    """
    ast = parse_grammar(text, EBNF_FLAVOUR)
    rule = list(ast.rules)[0]
    arm = list(rule.body)[0]
    return arm[0]


# ── Registration ────────────────────────────────────────────────────────


def test_get_flavour_ebnf_returns_the_singleton():
    """get_flavour("ebnf") resolves to the EBNF_FLAVOUR singleton."""
    assert get_flavour("ebnf") is EBNF_FLAVOUR


def test_flavour_for_extension_dot_ebnf_returns_the_singleton():
    """flavour_for_extension resolves '.ebnf' files to EBNF_FLAVOUR."""
    assert flavour_for_extension("grammar.ebnf") is EBNF_FLAVOUR


def test_ebnf_flavour_is_an_irflavour():
    """EBNF_FLAVOUR is an IrFlavour singleton."""
    assert isinstance(EBNF_FLAVOUR, IrFlavour)


def test_ebnf_flavour_metadata():
    """EBNF_FLAVOUR carries the expected identity metadata."""
    assert EBNF_FLAVOUR.name == "ebnf"
    assert EBNF_FLAVOUR.extensions == (".ebnf",)
    assert EBNF_FLAVOUR.line_comment == ""


def test_ebnf_escapes_is_an_escape_codec():
    """EBNF_ESCAPES is an EscapeCodec singleton."""
    assert isinstance(EBNF_ESCAPES, EscapeCodec)


# ── Parse half: lexic.compile.parse_grammar with EBNF_FLAVOUR ────────────


def test_parse_rule_shape_name_equals_body_semicolon():
    """`name = body ;` parses to one named rule."""
    ast = parse_grammar('a = "x" ;\n', EBNF_FLAVOUR)
    assert [str(r.name) for r in ast.rules] == ["a"]


def test_parse_comma_is_concatenation():
    """`,` concatenates items within one sequence arm."""
    ast = parse_grammar('a = "x", "y" ;\n', EBNF_FLAVOUR)
    rule = list(ast.rules)[0]
    arm = list(rule.body)[0]
    assert [item.atom for item in arm] == [IrLiteral("x"), IrLiteral("y")]


def test_parse_pipe_is_alternation():
    """`|` separates arms of an alternation."""
    ast = parse_grammar('a = "x" | "y" ;\n', EBNF_FLAVOUR)
    rule = list(ast.rules)[0]
    arms = list(rule.body)
    assert len(arms) == 2
    assert arms[0][0].atom == IrLiteral("x")
    assert arms[1][0].atom == IrLiteral("y")


def test_parse_braces_is_zero_or_more():
    """`{x}` repetition parses to the item quantifier (0, None)."""
    item = first_item('a = { "x" } ;\n')
    assert item.quantifier == IrQuantifier(0, IrNone)


def test_parse_brackets_is_zero_or_one():
    """`[x]` option parses to the item quantifier (0, 1)."""
    item = first_item('a = [ "x" ] ;\n')
    assert item.quantifier == IrQuantifier(0, 1)


def test_parse_postfix_star():
    """Postfix `*` parses to quantifier (0, None)."""
    item = first_item('a = "x"* ;\n')
    assert item.quantifier == IrQuantifier(0, IrNone)


def test_parse_postfix_plus():
    """Postfix `+` parses to quantifier (1, None)."""
    item = first_item('a = "x"+ ;\n')
    assert item.quantifier == IrQuantifier(1, IrNone)


def test_parse_postfix_question_mark():
    """Postfix `?` parses to quantifier (0, 1)."""
    item = first_item('a = "x"? ;\n')
    assert item.quantifier == IrQuantifier(0, 1)


def test_parse_dotdot_range_is_a_single_range_charclass():
    """`".."` between quoted terminals parses to a single-range IrCharClass."""
    item = first_item('a = "a".."z" ;\n')
    assert item.atom == IrCharClass(IrRange(IrChr("a"), IrChr("z")))


def test_parse_integer_multiplication_is_exact_repetition():
    """`4 * "a"` parses to IrItem(IrLiteral('a'), IrQuantifier(4, 4))."""
    item = first_item('a = 4 * "a" ;\n')
    assert item.atom == IrLiteral("a")
    assert item.quantifier == IrQuantifier(4, 4)


def test_parse_block_comment_is_noise():
    """`(* ... *)` block comments are structural noise — they reach no rule."""
    ast = parse_grammar('a = "x" ; (* a trailing comment *)\n', EBNF_FLAVOUR)
    assert [str(r.name) for r in ast.rules] == ["a"]


def test_parse_block_comment_between_rules_is_noise():
    """A comment between two rule definitions does not disturb parsing."""
    ast = parse_grammar('a = "x" ; (* c *) b = "y" ;\n', EBNF_FLAVOUR)
    assert [str(r.name) for r in ast.rules] == ["a", "b"]


def test_parse_double_quoted_terminal_with_escapes():
    """A double-quoted terminal decodes its short escapes."""
    item = first_item('a = "\\n\\t" ;\n')
    assert item.atom == IrLiteral("\n\t")


def test_parse_single_quoted_terminal_with_escapes():
    """A single-quoted terminal decodes the same short escapes."""
    item = first_item("a = '\\n' ;\n")
    assert item.atom == IrLiteral("\n")


def test_parse_hex_escape_x_decodes_to_the_character():
    """`\\x41` decodes to the character 'A' (2-hex-digit form)."""
    item = first_item('a = "\\x41" ;\n')
    assert item.atom == IrLiteral("A")


def test_parse_hex_escape_u_decodes_to_the_character():
    """`\\u0041` decodes to the character 'A' (4-hex-digit form)."""
    item = first_item('a = "\\u0041" ;\n')
    assert item.atom == IrLiteral("A")


def test_parse_hex_escape_bigu_decodes_to_the_character():
    """`\\U00000041` decodes to the character 'A' (8-hex-digit form)."""
    item = first_item('a = "\\U00000041" ;\n')
    assert item.atom == IrLiteral("A")


def test_parse_class_context_escapes_in_a_terminal():
    """The class-context escapes (\\- \\^ \\]) the emit side spells parse back."""
    assert first_item('a = "\\-" ;\n').atom == IrLiteral("-")
    assert first_item('a = "\\^" ;\n').atom == IrLiteral("^")
    assert first_item('a = "\\]" ;\n').atom == IrLiteral("]")


# ── Emit half: canonical IR -> EBNF text ──────────────────────────────────


def test_emit_literal_is_double_quoted():
    """A literal emits double-quoted, with escapes."""
    assert EBNF_FLAVOUR.apply(IrLiteral('a"b')) == '"a\\"b"'


def test_emit_single_member_charclass_emits_bare():
    """A one-member char class emits bare — no parens."""
    assert EBNF_FLAVOUR.apply(IrCharClass(IrChr("a"))) == '"a"'


def test_emit_multi_member_charclass_emits_parenthesised_pipe_alternation():
    """A multi-member char class emits as a parenthesised `|` alternation."""
    cls = IrCharClass(IrChr("a"), IrChr("b"), IrChr("c"))
    assert EBNF_FLAVOUR.apply(cls) == '("a" | "b" | "c")'


def test_emit_wide_charclass_wraps_its_own_alternation_fit_group():
    """A char class wide enough to overflow 88 columns wraps at its own `|`
    separators, and reparses to the same canonical class."""
    members = [IrChr(c) for c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    cls = IrCharClass(*members)
    rule = IrRule("wide", IrAlternation(IrSequence(IrItem(cls))))
    ast = IrAst(IrSeq(rule), "wide")
    wrapped = str(EBNF_FLAVOUR.apply(ast))
    assert "\n" in wrapped
    assert all(len(line) <= 88 for line in wrapped.splitlines())
    reparsed = parse_grammar(wrapped, EBNF_FLAVOUR)
    assert canonicalize(reparsed) == canonicalize(ast)


def test_emit_exact_n_quantifier_item_is_prefix_multiplication():
    """An item with a (n, n), n > 1 quantifier emits `n * atom` — prefix."""
    item = IrItem(IrLiteral("a"), IrQuantifier(4, 4))
    assert EBNF_FLAVOUR.apply(item) == '4 * "a"'


@pytest.mark.parametrize(
    ("quantifier", "symbol"),
    [
        (IrQuantifier(1, 1), ""),
        (IrQuantifier(0, 1), "?"),
        (IrQuantifier(0, IrNone), "*"),
        (IrQuantifier(1, IrNone), "+"),
    ],
    ids=["exactly-once", "optional", "zero-or-more", "one-or-more"],
)
def test_emit_postfix_quantifier_symbols(quantifier: IrQuantifier, symbol: str):
    """The four postfix-spellable quantifier bounds emit their EBNF symbol."""
    assert EBNF_FLAVOUR.apply(quantifier) == symbol


def test_emit_irnot_raises_unsupported():
    """EBNF has no native negation — IrNot refuses declaratively."""
    with pytest.raises(UnsupportedConstructError):
        EBNF_FLAVOUR.apply(IrNot(IrCharClass(IrChr("a"))))


def test_emit_token_terminal_refuses_declaratively():
    """Token terminals are a GBNF surface — EBNF refuses an IrAlphabet (F5)."""
    with pytest.raises(UnsupportedConstructError, match="token terminals"):
        EBNF_FLAVOUR.apply(IrAlphabet("tokens", IrLiteral("<think>")))


def test_emit_bounded_counted_quantifier_raises_unsupported():
    """A bounded counted quantifier (m, n) has no ISO EBNF spelling — refuses."""
    with pytest.raises(UnsupportedConstructError):
        EBNF_FLAVOUR.apply(IrQuantifier(2, 5))


def test_emit_open_counted_quantifier_raises_unsupported():
    """An open counted quantifier (n, ∞), n > 1 also has no ISO spelling."""
    with pytest.raises(UnsupportedConstructError):
        EBNF_FLAVOUR.apply(IrQuantifier(3, IrNone))


# ── Round trip: wide rules wrap, width=None is flat ───────────────────────


def test_wide_alternation_wraps_with_trailing_pipe_and_terminator():
    """A too-wide alternation breaks onto trailing-pipe continuations at the
    rule nest indent, the last line carrying EBNF's ``;`` terminator; no
    emitted line exceeds the default width of 88."""
    wrapped = str(EBNF_FLAVOUR.apply(wide_grammar()))
    lines = wrapped.splitlines()
    assert lines[0].rstrip().endswith("|")
    assert [ln for ln in lines if ln.startswith("      alternative")], wrapped
    assert lines[-2].rstrip().endswith(";") or lines[-1].rstrip().endswith(";")
    assert max(len(ln) for ln in lines) <= 88


def test_wide_alternation_wrapped_reparses_canonicalize_equal():
    """Wrapped emission round-trips: parse_grammar + canonicalize recovers
    the same canonical AST as the source (the round-trip licence gate)."""
    ast = wide_grammar()
    wrapped = str(EBNF_FLAVOUR.apply(ast))
    reparsed = parse_grammar(wrapped, EBNF_FLAVOUR)
    assert canonicalize(reparsed) == canonicalize(ast)


def test_wide_alternation_width_none_reproduces_the_flat_single_line():
    """width=None reproduces the pre-wrap flat single-line rule form."""
    ast = wide_grammar()
    flat = str(EBNF_FLAVOUR.apply(ast, width=None))
    root_line = flat.splitlines()[0]
    assert "\n" not in root_line
    expected = (
        "wide-rule = "
        + " | ".join(f"alternative-name-number-{i}" for i in range(6))
        + " ;"
    )
    assert root_line == expected


def test_self_hosting_fixpoint():
    """canonicalize(reduce(parse(EBNF_GRAMMAR, emit(canonical(EBNF_GRAMMAR)))))
    returns the canonical EBNF_GRAMMAR — the self-hosting round trip."""
    canonical = canonicalize(EBNF_GRAMMAR)
    emitted = str(EBNF_FLAVOUR.apply(canonical))
    reparsed = canonicalize(parse_grammar(emitted, EBNF_FLAVOUR))
    assert reparsed == canonical


# ── Structural guard: ebnf.py is data + pure IR algebra ───────────────────


def test_ebnf_actions_cover_every_grammar_ast_type():
    """Every IR-AST node type has an explicit EBNF action — no silent default."""
    registered = set(EBNF_ACTIONS.keys())
    missing = GRAMMAR_AST_TYPES - registered
    assert not missing, f"EBNF_FLAVOUR missing explicit actions for: {missing}"


def test_ebnf_actions_and_reductions_carry_no_irlambda():
    """EBNF_ACTIONS and EBNF_REDUCTIONS contain no IrLambda anywhere — like
    gbnf.py/abnf.py, ebnf.py holds zero procedural escape hatch."""
    assert not contains_ir_type(EBNF_ACTIONS.values(), IrLambda)
    assert not contains_ir_type(EBNF_REDUCTIONS.values(), IrLambda)


def test_ebnf_grammar_start_rule_is_grammar():
    """EBNF_GRAMMAR's start rule is 'grammar'."""
    assert EBNF_GRAMMAR.start == "grammar"


def test_ebnf_grammar_rule_names_include_core():
    """EBNF_GRAMMAR contains the expected core rule names."""
    names = {r.name for r in EBNF_GRAMMAR.rules}
    for expected in (
        "rule",
        "alternation",
        "concat",
        "factor",
        "repetition",
        "option",
        "multiplied",
        "quantified",
        "terminal",
        "comment",
    ):
        assert expected in names, f"Missing rule: {expected}"


def test_ebnf_grammar_every_ruleref_is_defined():
    """Every IrRuleRef referenced by every rule body names a defined rule."""
    names = {r.name for r in EBNF_GRAMMAR.rules}
    undefined: set[str] = set()
    for rule in EBNF_GRAMMAR.rules:
        for arm in rule.body:
            for item in arm:
                if isinstance(item.atom, IrRuleRef) and str(item.atom) not in names:
                    undefined.add(str(item.atom))
    assert not undefined, f"Undefined rule refs: {undefined}"
