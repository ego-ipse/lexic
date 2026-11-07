"""A stop-set that escapes into its soft FOLLOW is an attempt loop, not a fail-island.

A semantic rule whose run can over-eat a soft-only follower is not a stop-set: a
clone cut against its hard tail would take the follower's text. Where the decider
grants the attempt licence, the loop takes with rollback and audits that
follower, so the predictive engine answers instead of declining every reference.
"""

from __future__ import annotations

import itertools

import pytest

from tests.parity_helpers import DECLINED, answers

ESCAPING = (
    'root ::= z | z "b" ";" | ";" "ab" y?\nx ::= ";" | [a;] "b"?\n'
    'y ::= [ab] z ";"?\nz ::= "b"? [a;] "ab"* | ";" [a;]+ | [ab]+\n'
)
OVER_EAT = 'root ::= x "ab"?\nx ::= [a-c]*\n'
WORDS = ["".join(w) for n in range(1, 5) for w in itertools.product("ab;", repeat=n)]


@pytest.mark.parametrize("text", ["a", "b", ";", "aa", "ab", "ba"])
def test_an_escaping_stopset_answers_as_earley(text: str) -> None:
    """``z``'s ``[ab]+`` escapes, and the predictive engine answers anyway."""
    predictive, gated = answers(ESCAPING, "escaping-stopset", text)
    assert predictive == gated


def test_no_word_gets_a_model_earley_does_not_build() -> None:
    """Over every word up to four characters, an answer is Earley's or a decline."""
    for text in WORDS:
        predictive, gated = answers(ESCAPING, "escaping-stopset", text)
        assert predictive in (gated, DECLINED), text


@pytest.mark.parametrize("text", ["", "ab", "cab", "abab", "ca", "abc"])
def test_the_over_eaten_follower_is_never_taken_from_the_run(text: str) -> None:
    """``x ::= [a-c]*`` before ``"ab"?``: the soft-only follower is audited."""
    predictive, gated = answers(OVER_EAT, "escaping-over-eat", text)
    assert predictive in (gated, DECLINED)
