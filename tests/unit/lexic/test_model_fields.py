"""Tests for lexic.model_fields — what a field's own grammar item admits.

These checks reach a model through ``GrammarModel.__new__``, and that end of
them is pinned over real generated classes in ``test_model.py``. This file
targets each check directly, including the shapes a constructed model cannot
easily present: a value of the wrong Python type, a length exactly on a
bound, and a rule body the ``Literal[...]`` reading must decline.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import FieldValidationError
from lexic.ir import (
    IrAlternation,
    IrAtom,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrQuantifier,
    IrRange,
    IrRule,
    IrSelf,
    IrSequence,
    IrStr,
)
from lexic.model_fields import (
    FieldCheck,
    check_charclass,
    check_literal,
    check_token,
    uncovered_char,
    value_str_literals,
)

DIGITS = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
"""``[0-9]`` — one contiguous interval."""

VOWELS = IrCharClass(IrChr("a"), IrChr("e"), IrChr("i"))
"""``[aei]`` — three single points, deliberately not adjacent."""


def _nc(quantifier: IrQuantifier, atom: IrAtom = DIGITS) -> tuple[IrSelf, ...]:
    """The argument channel a field check reads its owning item from."""
    return (IrItem(atom, quantifier),)


def _rule(*arms: IrSequence) -> IrRule:
    """A rule whose body is exactly the given arms."""
    return IrRule("r", IrAlternation(*arms))


def _literal_arm(text: str, quantifier: IrQuantifier = IrQuantifier()) -> IrSequence:
    """A one-item arm holding a single literal."""
    return IrSequence(IrItem(IrLiteral(text), quantifier))


# ── the carrier ──────────────────────────────────────────────────


def test_field_check_reads_its_three_lanes_by_name():
    """The carrier is a record: name, runtime value and fold mode, by name."""
    carrier = FieldCheck("digits", "12", "text")
    assert carrier.field == "digits"
    assert carrier.value == "12"
    assert carrier.mode == "text"


def test_field_check_declares_no_ir_children():
    """None of the three lanes is an IR-node child, so the walk skips them."""
    carrier = FieldCheck("f", "v", "text")
    assert not carrier.children()
    assert len(carrier) == 3, "the record still IS its three-field tuple"


# ── uncovered_char ────────────────────────────────────────────────────────


def test_uncovered_char_returns_none_when_every_char_is_covered():
    """A fully covered string has no first offender."""
    assert uncovered_char(DIGITS, "90210") is None


def test_uncovered_char_returns_none_for_the_empty_string():
    """Vacuously covered — no character is out of class."""
    assert uncovered_char(DIGITS, "") is None


def test_uncovered_char_returns_the_first_offender_not_the_last():
    """Order matters: the answer names where the string first leaves the class."""
    assert uncovered_char(DIGITS, "1a2b") == "a"


def test_uncovered_char_reads_a_multi_point_class_as_a_set():
    """Three disjoint points cover their own members and nothing between."""
    assert uncovered_char(VOWELS, "aei") is None
    assert uncovered_char(VOWELS, "abc") == "b"


def test_uncovered_char_is_code_point_exact_at_an_interval_edge():
    """The bounds are inclusive on both ends, and one past each is not."""
    assert uncovered_char(DIGITS, "09") is None
    assert uncovered_char(DIGITS, "/") == "/"  # 0x2F, one below '0'
    assert uncovered_char(DIGITS, ":") == ":"  # 0x3A, one above '9'


def test_uncovered_char_handles_a_point_above_the_bmp():
    """Membership is by code point, so an astral char is simply out of ``[0-9]``."""
    assert uncovered_char(DIGITS, "1\U0001f600") == "\U0001f600"


# ── check_charclass ───────────────────────────────────────────────────────


def test_check_charclass_accepts_a_covered_value_within_bounds():
    """A passing check answers ``IrNone`` — the algebra's absence value."""
    result = check_charclass(
        FieldCheck("d", "123", "text"), DIGITS, _nc(IrQuantifier(1, 3))
    )
    assert result is IrNone


def test_check_charclass_refuses_a_non_str_value():
    """A char-class field holds text; anything else is a construction error."""
    with pytest.raises(FieldValidationError, match="expected a str"):
        check_charclass(FieldCheck("d", 123, "text"), DIGITS, _nc(IrQuantifier(1, 3)))


def test_check_charclass_refuses_an_out_of_class_character_by_name():
    """The message names the offending character and the class it is not in."""
    with pytest.raises(FieldValidationError, match=r"character 'a' is not in \[0-9\]"):
        check_charclass(FieldCheck("d", "1a", "text"), DIGITS, _nc(IrQuantifier(1, 3)))


def test_check_charclass_refuses_a_value_longer_than_the_quantifier_allows():
    """Length is the item's business, so the bound comes from the argument channel."""
    with pytest.raises(FieldValidationError, match="length 4 out of bounds"):
        check_charclass(
            FieldCheck("d", "1234", "text"), DIGITS, _nc(IrQuantifier(1, 3))
        )


def test_check_charclass_refuses_a_value_shorter_than_the_quantifier_allows():
    """The lower bound is enforced too — an empty value fails ``{1,3}``."""
    with pytest.raises(FieldValidationError, match="length 0 out of bounds"):
        check_charclass(FieldCheck("d", "", "text"), DIGITS, _nc(IrQuantifier(1, 3)))


def test_check_charclass_accepts_the_exact_bounds():
    """Both endpoints are inclusive; one char and three chars both pass ``{1,3}``."""
    for value in ("1", "123"):
        carrier = FieldCheck("d", value, "text")
        assert check_charclass(carrier, DIGITS, _nc(IrQuantifier(1, 3))) is IrNone


def test_check_charclass_accepts_any_length_under_an_open_upper_bound():
    """``+`` is ``{1, IrNone}``, so a long value is in bounds."""
    carrier = FieldCheck("d", "0" * 500, "text")
    assert check_charclass(carrier, DIGITS, _nc(IrQuantifier(1, IrNone))) is IrNone


def test_check_charclass_reports_the_class_before_the_length():
    """A value that is both out of class and too long names the character first."""
    with pytest.raises(FieldValidationError, match="character"):
        check_charclass(
            FieldCheck("d", "abcd", "text"), DIGITS, _nc(IrQuantifier(1, 2))
        )


# ── check_literal and check_token (the R7 holes) ──────────────────────────


def test_check_literal_accepts_anything_because_it_is_an_r7_hole():
    """A bound literal field is typed plain ``str`` and deliberately unchecked."""
    for value in ("anything", 42, None, object()):
        carrier = FieldCheck("lit", value, "text")
        assert check_literal(carrier, IrLiteral("x"), _nc(IrQuantifier())) is IrNone


def test_check_token_accepts_any_str_without_consulting_a_vocabulary():
    """Vocabulary membership needs a tokenizer, which is not per-field intrinsic."""
    carrier = FieldCheck("tok", "not-a-real-token", "text")
    assert check_token(carrier, IrLiteral("x"), _nc(IrQuantifier())) is IrNone


def test_check_token_refuses_a_non_str_value():
    """The one thing a token field can say alone: it holds the token's TEXT."""
    with pytest.raises(FieldValidationError, match="expected a str for token field"):
        check_token(FieldCheck("tok", 7, "text"), IrLiteral("x"), _nc(IrQuantifier()))


def test_check_token_refuses_bytes_which_are_not_text():
    """``bytes`` is sequence-like but is not the field's declared ``str``."""
    with pytest.raises(FieldValidationError, match="got bytes"):
        check_token(
            FieldCheck("tok", b"ab", "text"), IrLiteral("x"), _nc(IrQuantifier())
        )


# ── value_str_literals ────────────────────────────────────────────────────


def test_value_str_literals_returns_the_arm_set_for_a_multi_arm_literal_body():
    """Every arm a single unit literal — the ``Literal[...]`` reading."""
    rule = _rule(_literal_arm("+"), _literal_arm("-"), _literal_arm("*"))
    assert value_str_literals(rule) == frozenset({"+", "-", "*"})


def test_value_str_literals_declines_the_single_item_shortcut():
    """One arm of one item is typed plain ``str``, not a one-member ``Literal``."""
    assert value_str_literals(_rule(_literal_arm("+"))) is None


def test_value_str_literals_declines_a_quantified_arm():
    """``"a"+`` derives more strings than ``"a"``, so the arm set would lie."""
    rule = _rule(_literal_arm("+"), _literal_arm("-", IrQuantifier(1, IrNone)))
    assert value_str_literals(rule) is None


def test_value_str_literals_declines_a_multi_item_arm():
    """An arm spelling two items is not one literal, whatever the items are."""
    rule = _rule(
        _literal_arm("+"),
        IrSequence(IrItem(IrLiteral("-")), IrItem(IrLiteral("-"))),
    )
    assert value_str_literals(rule) is None


def test_value_str_literals_declines_a_non_literal_atom():
    """A char-class arm is a pattern; its members are not an arm set."""
    rule = _rule(_literal_arm("+"), IrSequence(IrItem(DIGITS)))
    assert value_str_literals(rule) is None


def test_value_str_literals_ignores_an_empty_arm_in_the_set_but_not_in_the_test():
    """An empty arm contributes no spelling, and cannot break the literal reading.

    ``arms`` drops the empty alternate before the set is built, while the
    ``all(...)`` test still runs over the whole body — an empty arm has no
    items, so it satisfies neither ``len(arm) == 1`` nor the shortcut.
    """
    rule = _rule(_literal_arm("+"), _literal_arm("-"), IrSequence())
    assert value_str_literals(rule) is None


def test_value_str_literals_deduplicates_equal_arms():
    """A set is what the check needs; two arms spelling ``+`` are one member."""
    rule = _rule(_literal_arm("+"), _literal_arm("+"), _literal_arm("-"))
    assert value_str_literals(rule) == frozenset({"+", "-"})


REBUILT = "root ::= head tail\nhead ::= [a-z]+\ntail ::= [0-9]+\n"
"""A record of two sub-model fields, for what a rebuild re-checks."""


def test_a_rebuild_checks_a_changed_field_and_refuses_a_bad_one() -> None:
    """A rebuild still answers for what it was handed: a changed field whose
    item refuses its value raises, exactly as hand construction does."""
    model = compile_text(REBUILT).parse("ab12")
    head, tail = model.children()
    with pytest.raises(FieldValidationError, match="expected a sub-model"):
        model.rebuild([IrStr("not a model"), tail])
    assert model.rebuild([head, tail]) == model


def test_a_rebuild_does_not_recheck_a_field_it_keeps() -> None:
    """A field whose value a rebuild keeps by identity is the instance's own,
    answered when it was built, and is not asked again — so a record trusted
    with a value its item would refuse rebuilds cleanly while that field is
    kept, and refuses the moment a rebuild hands it a new one."""
    model = compile_text(REBUILT).parse("ab12")
    build, _defaults, _fields = type(model).fast_construct()
    trusted = build([IrStr("not a model"), model.children()[1]])
    kept, _tail = trusted.children()
    new_tail = compile_text(REBUILT).parse("cd34").children()[1]
    assert trusted.rebuild([kept, new_tail]).children()[1] is new_tail
    with pytest.raises(FieldValidationError, match="expected a sub-model"):
        trusted.rebuild([IrStr("still not a model"), new_tail])


def test_a_rebuild_checks_a_new_run_and_keeps_the_tuple_it_was_handed() -> None:
    """A repetition's run is a field like any other: a rebuild handed a new
    run stores that very tuple, and the record it builds still hashes."""
    model = compile_text('root ::= item+\nitem ::= [a-z]+ "\\n"\n').parse("ab\ncd\n")
    (run,) = model.children()
    assert isinstance(run, tuple)
    swapped = (run[1], run[0])
    rebuilt = model.rebuild([swapped])
    assert rebuilt.children()[0] is swapped
    assert hash(rebuilt) == hash(model.rebuild([(run[1], run[0])]))
    assert rebuilt.to_text() == "cd\nab\n"
