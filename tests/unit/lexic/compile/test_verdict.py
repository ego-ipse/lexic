"""Tests for lexic.compile.verdict: an attempt's outcome held as a value."""

from __future__ import annotations

import pytest

import lexic.compile
from lexic.compile import Verdict, compile_text
from lexic.exceptions import (
    FieldValidationError,
    LexicError,
    Refusal,
    UnsupportedConstructError,
)

GRAMMAR = 'root ::= "a" "b"\n'


def refusal_of(text: str) -> LexicError:
    """The error a real parse of ``text`` raises under GRAMMAR."""
    compiled = compile_text(GRAMMAR)
    with pytest.raises(UnsupportedConstructError) as caught:
        compiled.parse(text)
    return caught.value


def test_accept_carries_no_words() -> None:
    """An accepted attempt says nothing — there is nothing to say."""
    verdict = Verdict.accept(0.25)
    assert verdict.accepted
    assert verdict.words == ""
    assert verdict.readout == Refusal()
    assert verdict.seconds == 0.25


def test_refuse_keeps_the_engine_message_verbatim() -> None:
    """The words are the engine's own, not a paraphrase of them."""
    error = refusal_of("ax")
    verdict = Verdict.refuse(error, 0.5)
    assert not verdict.accepted
    assert verdict.words == str(error)
    assert verdict.seconds == 0.5


def test_refuse_keeps_the_parse_readout() -> None:
    """A parse refusal's readout rides along — where it stopped survives."""
    error = refusal_of("ax")
    assert isinstance(error, UnsupportedConstructError)
    assert error.readout is not None
    assert Verdict.refuse(error, 0.0).readout == error.readout


def test_refuse_without_a_readout_carries_the_empty_one() -> None:
    """An error that is not a parse refusal has no position to report."""
    verdict = Verdict.refuse(FieldValidationError("field 'a' is not a model"), 0.0)
    assert verdict.words == "field 'a' is not a model"
    assert verdict.readout == Refusal()
    assert verdict.readout.pos == -1


def test_verdict_is_its_field_tuple() -> None:
    """A spine record: the verdict IS its fields, readable by index."""
    verdict = Verdict.accept(1.0)
    assert tuple(verdict) == (True, "", Refusal(), 1.0)
    assert verdict[0] is verdict.accepted


def test_verdicts_compare_across_attempts() -> None:
    """Two verdicts of one outcome are equal — the point of holding them."""
    error = refusal_of("ax")
    assert Verdict.refuse(error, 0.1) == Verdict.refuse(error, 0.1)
    assert Verdict.refuse(error, 0.1) != Verdict.accept(0.1)


def test_verdicts_sort_by_cost() -> None:
    """Tuple order puts the cheapest last field last — comparable as values."""
    fast, slow = Verdict.accept(0.001), Verdict.accept(0.01)
    assert sorted((slow, fast), key=lambda v: v.seconds) == [fast, slow]


def test_verdict_is_exported_from_the_compile_seam() -> None:
    """The seam family rule: reachable means named in __all__."""
    assert "Verdict" in lexic.compile.__all__
