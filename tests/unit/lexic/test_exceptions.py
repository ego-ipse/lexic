"""Tests for lexic.exceptions — the LexicError hierarchy and the Refusal record."""

from __future__ import annotations

import pytest

from lexic.exceptions import (
    FieldValidationError,
    IrKeyError,
    LexicError,
    Refusal,
    UnsupportedConstructError,
)


def test_refusal_defaults_to_an_unknown_stop_with_no_expectation():
    """Every field defaults to its documented neutral value."""
    refusal = Refusal()
    assert refusal.pos == -1
    assert refusal.rule == ""
    assert refusal.expected == ()
    assert refusal.negated is False
    assert refusal.undecidable is False


def test_refusal_is_a_plain_immutable_record():
    """Refusal is a NamedTuple — assigning to a field raises."""
    refusal = Refusal(pos=3, rule="digit", expected=("0", "1"), negated=True)
    assert refusal.pos == 3
    assert refusal.expected == ("0", "1")
    with pytest.raises(AttributeError):
        setattr(refusal, "pos", 4)


def test_unsupported_construct_error_carries_a_message_and_no_readout_by_default():
    """The bare-message constructor leaves readout unset."""
    error = UnsupportedConstructError("bad construct")
    assert str(error) == "bad construct"
    assert error.readout is None


def test_unsupported_construct_error_carries_a_refusal_readout():
    """The readout, when supplied, rides on the error unchanged."""
    readout = Refusal(pos=2, rule="root")
    error = UnsupportedConstructError("parse refused", readout)
    assert error.readout == readout


def test_unsupported_construct_error_is_a_lexic_error():
    """UnsupportedConstructError is part of the LexicError hierarchy."""
    assert issubclass(UnsupportedConstructError, LexicError)


def test_ir_key_error_is_both_unsupported_construct_and_key_error():
    """Doubly typed so both a library catch and ``Mapping`` protocol machinery
    (``dict.get`` etc.) catch it."""
    error = IrKeyError("missing key")
    assert isinstance(error, UnsupportedConstructError)
    assert isinstance(error, KeyError)


def test_field_validation_error_is_a_lexic_error_but_not_unsupported_construct():
    """FieldValidationError is a sibling of UnsupportedConstructError, not a subtype."""
    error = FieldValidationError("bad field")
    assert isinstance(error, LexicError)
    assert not isinstance(error, UnsupportedConstructError)


def test_lexic_error_is_a_plain_exception():
    """LexicError itself is an ordinary Exception subclass."""
    assert issubclass(LexicError, Exception)
