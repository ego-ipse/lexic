"""Tests for ``lexic.ir.compute``."""

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLeaf, IrOp
from lexic.ir.compute import (
    IrCompare,
    IrConcat,
    IrGlyph,
    IrIsA,
    IrJoin,
    IrMerge,
    IrOrd,
    IrRadix,
    IrUnradix,
)
from lexic.ir.control import IrEach, IrPipe
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrSequence,
)
from lexic.ir.records import IrNamedTuple, IrTuple
from lexic.ir.scalars import IrChr, IrInt, IrStr
from lexic.ir.spine import IrNone


def test_ircompare_eq_true_returns_irint_one():
    """A satisfied comparison evaluates to IrInt(1)."""
    result = IrCompare(IrInt(1), IrOp("=="), IrInt(1)).eval(IrNone, IrNone, ())
    assert result == 1
    assert isinstance(result, IrInt)


def test_ircompare_eq_false_returns_irint_zero():
    """An unsatisfied comparison evaluates to IrInt(0)."""
    assert IrCompare(IrInt(1), IrOp("=="), IrInt(0)).eval(IrNone, IrNone, ()) == 0


def test_ircompare_lt_and_gt():
    """< and > compare operands and yield IrInt(1)/IrInt(0)."""
    assert IrCompare(IrInt(1), IrOp("<"), IrInt(2)).eval(IrNone, IrNone, ()) == 1
    assert IrCompare(IrInt(2), IrOp(">"), IrInt(1)).eval(IrNone, IrNone, ()) == 1
    assert IrCompare(IrInt(2), IrOp("<"), IrInt(1)).eval(IrNone, IrNone, ()) == 0
    assert IrCompare(IrInt(1), IrOp(">"), IrInt(2)).eval(IrNone, IrNone, ()) == 0


def test_irconcat_joins_parts_in_order():
    """IrConcat evaluates parts and concatenates results."""
    op = IrConcat(parts=IrTuple(IrLiteral('"'), IrLiteral("x"), IrLiteral('"')))
    assert op.eval(IrNone, IrNone, ()) == '"x"'


def test_irconcat_empty_parts_returns_empty_string():
    """IrConcat with no parts returns empty string."""
    assert IrConcat().eval(IrNone, IrNone, ()) == ""


def test_concat_joins_parts():
    """IrConcat is an IrNamedTuple; evaluates parts and concatenates."""
    c = IrConcat(parts=IrTuple(IrLiteral("a"), IrLiteral("b")))
    assert isinstance(c, IrNamedTuple)
    out = c.eval(IrNone, IrNone, ())
    assert out == "ab" and isinstance(out, IrStr)


def test_irjoin_joins_items_with_separator():
    """IrJoin evaluates parts and joins results with separator."""
    op = IrJoin(
        parts=IrTuple(IrLiteral("a"), IrLiteral("b"), IrLiteral("c")),
        separator=IrLiteral(" | "),
        empty=IrLiteral(""),
    )
    assert op.eval(IrNone, IrNone, ()) == "a | b | c"


def test_irjoin_returns_empty_value_when_no_items():
    """IrJoin returns empty when parts is empty."""
    op = IrJoin(
        parts=IrTuple(),
        separator=IrLiteral(" | "),
        empty=IrLiteral("<empty>"),
    )
    assert op.eval(IrNone, IrNone, ()) == "<empty>"


def test_action_call_is_identity():
    """Action algebra inherits IrSelf's __call__ → returns self.
    Typed value extraction is .eval(); __call__ is for identity."""
    op = IrConcat(parts=IrTuple(IrLiteral("x")))
    assert op(IrNone, IrNone, ()) is op


def test_irisa_atom_is_alternation_evals_to_irint_one():
    """IrIsA evals to IrInt(1) when the named attribute IS-A the target type."""
    alt = IrAlternation(IrSequence(IrItem(atom=IrLiteral("x"))))
    item = IrItem(atom=alt)
    result = IrIsA("atom", IrAlternation).eval(IrNone, item, ())
    assert result == 1
    assert repr(result) == "IrInt(1)"


def test_irisa_atom_not_alternation_evals_to_irint_zero():
    """IrIsA evals to IrInt(0) when the named attribute is NOT the target type."""
    item = IrItem(atom=IrLiteral("y"))
    result = IrIsA("atom", IrAlternation).eval(IrNone, item, ())
    assert result == 0
    assert repr(result) == "IrInt(0)"


def test_irisa_result_is_truthy_when_one():
    """IrInt(1) result is truthy; IrInt(0) is falsy."""
    alt = IrAlternation(IrSequence(IrItem(atom=IrLiteral("x"))))
    item_alt = IrItem(atom=alt)
    item_lit = IrItem(atom=IrLiteral("z"))
    assert bool(IrIsA("atom", IrAlternation).eval(IrNone, item_alt, ()))
    assert not bool(IrIsA("atom", IrAlternation).eval(IrNone, item_lit, ()))


def test_irisa_repr_renders_class_bare():
    """IrIsA repr is codegen: 'IrIsA('atom', IrAlternation)'."""
    assert repr(IrIsA("atom", IrAlternation)) == "IrIsA('atom', IrAlternation)"


def test_irisa_missing_attribute_raises_attribute_error():
    """IrIsA raises AttributeError when the attribute does not exist on the node."""
    item = IrItem(atom=IrLiteral("x"))
    with pytest.raises(AttributeError):
        IrIsA("nonexistent", IrAlternation).eval(IrNone, item, ())


def test_irunradix_decodes_decimal():
    """IrUnradix(base, out) decodes a digit string (the focus ``n``) to out(value)"""
    assert IrUnradix(10, IrInt).eval(IrNone, IrStr("12"), ()) == IrInt(12)


def test_irunradix_decodes_hex_to_irchr():
    """IrUnradix(16, IrChr) decodes a hex digit string to IrChr."""
    assert IrUnradix(16, IrChr).eval(IrNone, IrStr("41"), ()) == IrChr(0x41)


def test_irunradix_empty_string_raises():
    """IrUnradix(base, out) raises on empty string"""
    with pytest.raises(UnsupportedConstructError):
        IrUnradix(10, IrInt).eval(IrNone, IrStr(""), ())


def test_irunradix_bad_digit_for_base_raises():
    """IrUnradix(base, out) raises on bad digit for base"""
    with pytest.raises(UnsupportedConstructError):
        IrUnradix(2, IrInt).eval(IrNone, IrStr("2"), ())  # '2' is out of base 2


def test_irglyph_is_a_plain_leaf():
    """IrGlyph is a plain IrLeaf body carrying no IR-node children."""
    assert isinstance(IrGlyph(), IrLeaf)
    assert not IrGlyph().children()


def test_irglyph_renders_ascii_codepoint():
    """IrGlyph.eval on the focus IrInt(65) yields the character 'A'."""
    assert IrGlyph().eval(IrNone, IrInt(65), ()) == IrStr("A")


def test_irglyph_renders_control_codepoints():
    """IrGlyph.eval renders tab (9) and newline (10) as their control chars."""
    assert IrGlyph().eval(IrNone, IrInt(9), ()) == IrStr("\t")
    assert IrGlyph().eval(IrNone, IrInt(10), ()) == IrStr("\n")


def test_irglyph_renders_non_ascii_codepoint():
    """IrGlyph.eval renders a non-ASCII code point (U+3042, hiragana 'あ')."""
    assert IrGlyph().eval(IrNone, IrInt(0x3042), ()) == IrStr("あ")


def test_irglyph_non_int_focus_raises():
    """IrGlyph.eval raises UnsupportedConstructError when the focus isn't an int."""
    with pytest.raises(UnsupportedConstructError, match="focus must be an integer"):
        IrGlyph().eval(IrNone, IrStr("A"), ())


def test_irglyph_composes_with_irunradix_via_irpipe():
    """IrPipe(IrUnradix(16, IrInt), IrGlyph()) reads a hex digit-run as one char.

    The glyph step after IrUnradix: digits decode to a neutral code point,
    IrGlyph spells it as text — the pattern gbnf.py's literal-context hex
    escapes use (``_HEX_GLYPH``).
    """
    result = IrPipe(IrUnradix(16, IrInt), IrGlyph()).eval(IrNone, IrStr("41"), ())
    assert result == IrStr("A")


def test_irradix_spells_decimal_focus_in_base():
    """IrRadix(base, width).eval spells the focus integer in ``base``, no
    padding when ``width`` is left at its default (0)."""
    assert IrRadix(16).eval(IrNone, IrInt(65), ()) == IrStr("41")
    assert IrRadix(2).eval(IrNone, IrInt(5), ()) == IrStr("101")


def test_irradix_zero_pads_to_width():
    """IrRadix(base, width) zero-pads the spelled digits to ``width``."""
    assert IrRadix(16, 2).eval(IrNone, IrInt(65), ()) == IrStr("41")
    assert IrRadix(16, 4).eval(IrNone, IrInt(0x41), ()) == IrStr("0041")


def test_irradix_zero_focus_spells_a_single_zero_digit():
    """IrRadix on a zero focus spells "0", padded to width if given."""
    assert IrRadix(16).eval(IrNone, IrInt(0), ()) == IrStr("0")
    assert IrRadix(16, 4).eval(IrNone, IrInt(0), ()) == IrStr("0000")


def test_irradix_uses_uppercase_digits():
    """IrRadix spells base>10 digits uppercase (e.g. hex 'A'-'F')."""
    assert IrRadix(16).eval(IrNone, IrInt(0xABCDEF), ()) == IrStr("ABCDEF")


def test_irradix_non_int_focus_raises():
    """IrRadix.eval raises UnsupportedConstructError when the focus isn't an int."""
    with pytest.raises(UnsupportedConstructError, match="non-negative integer"):
        IrRadix(16).eval(IrNone, IrStr("x"), ())


def test_irradix_negative_focus_raises():
    """IrRadix.eval raises UnsupportedConstructError on a negative integer focus."""
    with pytest.raises(UnsupportedConstructError, match="non-negative integer"):
        IrRadix(16).eval(IrNone, IrInt(-1), ())


def test_irradix_repr_is_codegen():
    """IrRadix repr renders as a valid constructor expression.

    The default-valued ``width=0`` is omitted from the trailing run.
    """
    assert repr(IrRadix(16, 2)) == "IrRadix(16, 2)"
    assert repr(IrRadix(16)) == "IrRadix(16)"


def test_irradix_inverts_irunradix_round_trip():
    """IrRadix(base, width) ∘ IrUnradix(base, IrInt) round-trips a digit string.

    The emit-side spelling (IrRadix) is the inverse of the reduce-side decode
    (IrUnradix) — decoding then re-spelling a zero-padded hex run returns it.
    """
    decoded = IrUnradix(16, IrInt).eval(IrNone, IrStr("0041"), ())
    respelled = IrRadix(16, 4).eval(IrNone, decoded, ())
    assert respelled == IrStr("0041")


def test_irord_is_a_plain_leaf():
    """IrOrd is a plain IrLeaf body carrying no IR-node children."""
    assert isinstance(IrOrd(), IrLeaf)
    assert not IrOrd().children()


def test_irord_returns_codepoint_of_single_char():
    """IrOrd.eval on a single-character focus yields its code point."""
    assert IrOrd().eval(IrNone, IrStr("A"), ()) == IrInt(65)


def test_irord_multi_char_focus_raises():
    """IrOrd.eval raises UnsupportedConstructError on a multi-character focus."""
    with pytest.raises(UnsupportedConstructError, match="single character"):
        IrOrd().eval(IrNone, IrStr("AB"), ())


def test_irord_empty_focus_raises():
    """IrOrd.eval raises UnsupportedConstructError on an empty focus."""
    with pytest.raises(UnsupportedConstructError, match="single character"):
        IrOrd().eval(IrNone, IrStr(""), ())


def test_irord_repr_is_codegen():
    """IrOrd repr renders as a valid constructor expression."""
    assert repr(IrOrd()) == "IrOrd()"


def test_irord_inverts_irglyph_round_trip():
    """IrOrd ∘ IrGlyph round-trips a character through its code point."""
    codepoint = IrOrd().eval(IrNone, IrStr("あ"), ())
    respelled = IrGlyph().eval(IrNone, codepoint, ())
    assert respelled == IrStr("あ")


def test_ireach_applies_a_computing_body_per_element():
    """IrEach with a non-identity body (IrOrd) transforms each element."""
    result = IrEach(IrOrd()).eval(IrNone, IrStr("AB"), ())
    assert result == IrTuple(IrInt(65), IrInt(66))


def test_irmerge_is_a_plain_leaf():
    """IrMerge is a plain IrLeaf body carrying no IR-node children."""
    assert isinstance(IrMerge(), IrLeaf)
    assert not IrMerge().children()


def test_irmerge_folds_distinct_rules_into_an_ast():
    """IrMerge folds distinctly-named nc rules into one IrAst, start = first name."""
    rule_a = IrRule("a", IrAlternation(IrSequence(IrItem(IrLiteral("x")))))
    rule_b = IrRule("b", IrAlternation(IrSequence(IrItem(IrLiteral("y")))))
    result = IrMerge().eval(IrNone, IrNone, (rule_a, rule_b))
    assert isinstance(result, IrAst)
    assert result.start == "a"
    assert list(result.rules) == [rule_a, rule_b]


def test_irmerge_appends_arms_of_same_named_rules_in_source_order():
    """A rule name seen twice on nc has its later arms appended to the
    earlier rule's alternation, in source order — the ABNF ``=/`` shape."""
    first = IrRule("a", IrAlternation(IrSequence(IrItem(IrLiteral("x")))))
    second = IrRule("a", IrAlternation(IrSequence(IrItem(IrLiteral("y")))))
    result = IrMerge().eval(IrNone, IrNone, (first, second))
    assert isinstance(result, IrAst)
    rules = list(result.rules)
    assert len(rules) == 1
    assert rules[0].name == "a"
    assert list(rules[0].body) == [
        IrSequence(IrItem(IrLiteral("x"))),
        IrSequence(IrItem(IrLiteral("y"))),
    ]


def test_irmerge_empty_nc_yields_empty_ast_with_blank_start():
    """IrMerge with no nc rules yields IrAst(IrSeq(), IrStr(""))."""
    result = IrMerge().eval(IrNone, IrNone, ())
    assert isinstance(result, IrAst)
    assert not list(result.rules)
    assert result.start == ""


def test_irmerge_non_irrule_arg_raises():
    """IrMerge.eval raises UnsupportedConstructError on a non-IrRule nc element."""
    with pytest.raises(UnsupportedConstructError, match="expected IrRule"):
        IrMerge().eval(IrNone, IrNone, (IrLiteral("not-a-rule"),))


def test_irmerge_repr_is_codegen():
    """IrMerge repr renders as a valid constructor expression."""
    assert repr(IrMerge()) == "IrMerge()"
