"""The split-greedy gate at the runtime: where it stops, and where it does not.

`gate_take` answers "does this loop admit another iteration". For
:data:`GATE_GREEDY` that is the negation of one question — is what remains the
unit's tail and its certified continuation — and the three shapes of that
question are the three cases of condition (e): the end of the input, a starter
set that cannot begin an item, and a literal matched in full.

The answers are written out by hand from the predicate's own sentence, not read
off a run, so a predicate that drifted would fail here rather than be described
by the test.
"""

from __future__ import annotations

import pytest

from lexic.parsing.pda.compiler.program.flatten import gate_take
from lexic.parsing.pda.compiler.program.opcodes import (
    GATE_ATTEMPT,
    GATE_GREEDY,
    GATE_KWIN,
    GATE_PAIR,
    GATE_STOP,
)

EOF_GATE = (";", "", None)
"""One terminator of tail, then the end of the input."""

TWO_GATE = (";;", "", None)
"""``m = 2``: the tail is two terminators."""

STARTER_GATE = (";", "", frozenset({"#"}))
"""The continuation begins with ``#``, which cannot begin an item."""

LITERAL_GATE = (";", "a", None)
"""astra's case: the continuation is ``a``, which CAN begin a body."""


@pytest.mark.parametrize(
    ("label", "text", "pos", "takes"),
    [
        ("the tail and nothing else stops it", "a;;", 2, False),
        ("a tail with more after it does not", "a;;a;;", 2, True),
        ("mid-document, on a terminator", "a;;a;;", 5, False),
        ("a body character is not the tail", "a;ab;", 2, True),
        ("past the end takes nothing", "a;;", 3, True),
    ],
)
def test_the_end_of_input_case(label: str, text: str, pos: int, takes: bool) -> None:
    """Exit exactly where the remainder IS the tail — nowhere earlier, nowhere later.

    The last row is the one worth stating: at a position past the tail the
    remainder is empty, which is not the tail, so the gate says "take" — and
    says nothing about whether an item is there. Ordinary recognition decides
    that, which is the whole of what this gate claims.
    """
    assert gate_take(text, pos, GATE_GREEDY, EOF_GATE) is takes, label


@pytest.mark.parametrize(
    ("text", "pos", "takes"),
    [
        ("a;;;", 2, False),  # two terminators remain: the tail
        ("a;;;;", 2, True),  # three remain: one more item fits before the tail
        ("a;;", 2, True),  # only one remains — not this tail
    ],
)
def test_a_two_terminator_tail_reads_both(text: str, pos: int, takes: bool) -> None:
    """``m`` is not a constant: a longer tail moves where the loop may stop."""
    assert gate_take(text, pos, GATE_GREEDY, TWO_GATE) is takes


@pytest.mark.parametrize(
    ("text", "pos", "takes"),
    [
        ("a;;#", 2, False),  # the tail, then the continuation's first character
        ("a;;", 2, False),  # the tail, then the end — also a stop
        ("a;;a;;#", 2, True),  # the tail, then a body character: not the end
        ("a;ab;#", 2, True),  # not even the tail here
    ],
)
def test_the_disjoint_starter_case(text: str, pos: int, takes: bool) -> None:
    """A starter that cannot begin an item LOCATES the continuation.

    It does not parse it: the second row stops at the end of input too, because
    a starter set says where the continuation may begin, never that one must.
    """
    assert gate_take(text, pos, GATE_GREEDY, STARTER_GATE) is takes


@pytest.mark.parametrize(
    ("text", "pos", "takes"),
    [
        ("a;;a", 2, False),  # tail then the literal then the end
        ("a;;a;;a", 2, True),  # the same two characters, and MORE after them
        ("a;;", 2, True),  # the tail, but the continuation is missing
        ("a;;ab", 2, True),  # the literal's character, then more
    ],
)
def test_the_literal_to_end_of_input_case(text: str, pos: int, takes: bool) -> None:
    """astra's counterexample, at the predicate that answers it.

    Rows one and two are the conflict pair: identical next two characters
    (``;a``), opposite answers. A two-character window cannot separate them and
    this gate does not try — it matches the tail AND the literal AND the end of
    the input, which is why the licence charges the literal's length.
    """
    assert gate_take(text, pos, GATE_GREEDY, LITERAL_GATE) is takes


def test_every_gate_kind_still_answers_through_the_one_entry_point() -> None:
    """`gate_take` splits after three kinds; all six must still route.

    The three one- and two-character kinds are answered in `gate_take` itself so
    a hot loop pays nothing to reach them; the wider kinds go on to
    `_wide_gate_take`. A split like that is exactly where a kind can fall
    through a crack and start answering ``False`` for the wrong reason, so this
    drives one input of each kind through the single entry point and checks the
    answer against what that kind's own rule says.

    A smaller `gate_take` is not evidence of no regression — the kinds behind
    the split now cost a call, and only the remote's matrix rows on those paths
    decide that. This test defends correctness, not cost.
    """
    semi = (frozenset({";"}), False)
    table = [
        ("STOP takes a char in its set", GATE_STOP, semi, "a;", 1, True),
        ("STOP refuses one outside it", GATE_STOP, semi, "ab", 1, False),
        ("PAIR takes a listed pair", GATE_PAIR, frozenset({";a"}), "x;a", 1, True),
        ("PAIR refuses an unlisted one", GATE_PAIR, frozenset({";a"}), "x;b", 1, False),
        (
            "ATTEMPT takes a FIRST-only char",
            GATE_ATTEMPT,
            (semi, (frozenset({"#"}), False)),
            "a;",
            1,
            True,
        ),
        (
            "KWIN takes a matching window",
            GATE_KWIN,
            (((frozenset({";"}), False), (frozenset({"a"}), False)),),
            "x;a",
            1,
            True,
        ),
        (
            "KWIN refuses a window it does not hold",
            GATE_KWIN,
            (((frozenset({";"}), False), (frozenset({"a"}), False)),),
            "x;b",
            1,
            False,
        ),
        ("GREEDY stops on the tail", GATE_GREEDY, EOF_GATE, "a;", 1, False),
        ("GREEDY takes anything else", GATE_GREEDY, EOF_GATE, "a;;", 1, True),
    ]
    for label, kind, gate, text, pos, expected in table:
        assert gate_take(text, pos, kind, gate) is expected, label
