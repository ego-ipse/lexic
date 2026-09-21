"""What admits the next character — the gates and the selection over them.

Built through the public compile path, as ``test_flatten.py`` is: small
hand-authored GBNF snippets compiled to real tables and inspected.
"""

from __future__ import annotations

from typing import Any

import pytest

from lexic.exceptions import EngineInvariantError
from lexic.parsing.pda.compiler.program.flatten import (
    FlatClone,
)
from lexic.parsing.pda.compiler.program.gating import (
    KWindowSelect,
    NoiseSkipSelect,
    gate_take,
    select_gated,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    GATE_ATTEMPT,
    GATE_GREEDY,
    GATE_KWIN,
    GATE_STOP,
)
from lexic.parsing.pda.core.errors import PdaFail

EOF_GATE = (";", "", None)


TWO_GATE = (";;", "", None)


STARTER_GATE = (";", "", frozenset({"#"}))


LITERAL_GATE = (";", "a", None)


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


def _window(char: str, arm: object) -> tuple[Any, object]:
    """One k-window entry: a single one-position window admitting ``char``."""
    position = (frozenset(char), False)
    return ((position,),), arm


def _gated(wide, default=None) -> FlatClone:
    """A clone carrying only what `select_gated` reads."""
    clone = FlatClone.__new__(FlatClone)
    clone.name = "gated"
    clone.selectors = ()
    clone.wide_selectors = wide
    clone.default = default
    return clone


def test_a_wide_selection_answers_with_its_own_matching_arm() -> None:
    """The ordinary path: the selection picks, `select_gated` does not."""
    hit = object()
    wide = KWindowSelect((_window("a", hit),))

    assert select_gated("ab", 0, _gated(wide)) is hit


def test_a_noise_skip_selection_peeks_past_the_run_it_skips() -> None:
    """The lead char is noise on every arm — the decision is the one after it."""
    hit = object()
    wide = NoiseSkipSelect((frozenset(" "), False), ((frozenset("b"), False, hit),))

    assert select_gated("   b", 0, _gated(wide)) is hit
    assert select_gated("b", 0, _gated(wide)) is hit, "an empty run still peeks"


def test_no_gate_admitting_the_character_is_an_ordinary_refusal() -> None:
    """A wide selection that matches nothing is a parse failure, not a bug.

    `PdaFail` and nothing else: the engine seam catches it and answers the
    document with Earley. Raising the engine's own invariant error here would
    crash every gated alternation that legitimately misses.
    """
    wide = KWindowSelect((_window("z", object()),))

    with pytest.raises(PdaFail):
        select_gated("a", 0, _gated(wide))


def test_a_missed_gate_takes_the_default_arm_when_there_is_one() -> None:
    """The same miss, with somewhere to fall — no refusal at all."""
    escape = object()
    wide = KWindowSelect((_window("z", object()),))

    assert select_gated("a", 0, _gated(wide, default=escape)) is escape


def test_a_clone_with_no_wide_selection_is_an_impossible_state() -> None:
    """The other `None`, one line away, and a different answer.

    Every caller guards on `wide_selectors is not None`. Falling through to
    the default instead would turn a broken guard into a quietly WRONG arm;
    `RuntimeError` because the engine seam catches `PdaFail` and would hide it
    behind an Earley parse that succeeds.
    """
    with pytest.raises(EngineInvariantError, match="no wide selection"):
        select_gated("a", 0, _gated(None, default=object()))
