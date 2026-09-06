"""The derived language differential — what a probe set is, and what it decides."""

from __future__ import annotations

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from tools.benchmark.engines.refusals import LEXIC_REFUSALS
from tools.benchmark.measurement.language import (
    BOUNDARY_SUFFIXES,
    _candidates,
    disagreement,
    probes,
)

_SOURCE = 'root ::= word ("," word)*\nword ::= [a-z]+\n'
_CORPUS = "ab,cd"


def _ast():
    """The tiny grammar these tests derive probes from."""
    return compile_text(_SOURCE, cache_key="probe-language").grammar


def _reference(text: str) -> object:
    """A reference verdict for the same language, spelled without lexic."""
    if not text or text.startswith(",") or text.endswith(","):
        raise UnsupportedConstructError(text)
    if not all(part and part.isalpha() and part.islower() for part in text.split(",")):
        raise UnsupportedConstructError(text)
    return text


def test_the_probe_set_is_deterministic_and_deduplicated() -> None:
    """Two derivations of one grammar's probes agree exactly, string for string."""
    first = _candidates(_ast(), _CORPUS)
    second = _candidates(_ast(), _CORPUS)

    assert first == second
    assert len(set(first)) == len(first)
    assert len(first) > 40


def test_the_probes_poke_the_boundaries_of_the_timed_document() -> None:
    """The document with whitespace on either end is in the set, by name.

    This is the family the authored `rejects` never held, and the one an
    end-of-input anchor built outside the emitter's whitespace window accepts.
    """
    built = _candidates(_ast(), _CORPUS)

    for suffix in BOUNDARY_SUFFIXES:
        assert _CORPUS + suffix in built
        assert suffix + _CORPUS in built


def test_a_probe_set_carries_both_verdicts() -> None:
    """A set of only-accepted or only-refused probes could decide one direction."""
    built = probes("probe-language-both", _ast(), _CORPUS, _reference)

    assert any(taken for _text, taken in built)
    assert any(not taken for _text, taken in built)


def test_an_agreeing_seat_is_not_flagged() -> None:
    """The reference compared against itself disagrees with itself nowhere."""
    built = probes("probe-language-same", _ast(), _CORPUS, _reference)

    assert disagreement(_reference, built, LEXIC_REFUSALS) is None


def test_a_seat_accepting_more_than_the_reference_is_flagged() -> None:
    """Trailing whitespace ignored — the pyparsing anchor's exact widening."""
    built = probes("probe-language-wide", _ast(), _CORPUS, _reference)

    def wide(text: str) -> object:
        """The reference, plus every string it accepts after an rstrip."""
        return _reference(text.rstrip())

    why = disagreement(wide, built, LEXIC_REFUSALS)
    assert why is not None
    assert why.startswith("accepts the derived probe")


def test_a_seat_refusing_more_than_the_reference_is_flagged() -> None:
    """The other direction: a translation that describes a smaller language."""
    built = probes("probe-language-narrow", _ast(), _CORPUS, _reference)
    letters = sorted({c for text, taken in built if taken for c in text})
    assert letters, "the probe set derives no accepted sentence to narrow"
    struck = letters[0]

    def narrow(text: str) -> object:
        """The reference, with one letter struck out of the alphabet."""
        if struck in text:
            raise UnsupportedConstructError(text)
        return _reference(text)

    why = disagreement(narrow, built, LEXIC_REFUSALS)
    assert why is not None
    assert why.startswith("refuses the derived probe")
