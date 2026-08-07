"""Tests for the lockstep boundary verdict's predicates — admission.py.

The lockstep verdict settles a both-viable boundary by CONVERGENCE instead of
running both sides to end-of-input, which is what takes the parse from
quadratic to near-linear. Its soundness rests entirely on two predicates, so
they are pinned here directly rather than only through a parse:

- :func:`control_signature` — two sides sharing it at the same position have
  the same future. It must EXCLUDE values (or the sides never converge) and it
  must normalise the iteration count (or the side that took an extra iteration
  differs forever).
- :func:`values_agree` — the same question the end-of-input comparison asks,
  asked earlier. A false "agree" would commit what the engine refuses, so the
  adversarial case (identical control state, divergent pending values) is the
  one that matters.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from lexic.compile import compile_text
from lexic.parsing.pda.runtime.admission import (
    control_signature,
    pending_values,
    values_agree,
)
from lexic.parsing.pda.runtime.build import F_ARM, F_COUNT, F_I, F_OUT


class ArmStub(NamedTuple):
    """Minimal arm — the bounds :func:`control_signature`'s count key consults."""

    los: tuple[int, ...]
    his: tuple[int, ...]
    n: int


def frames(
    los: tuple[int, ...], his: tuple[int, ...], i: int, counts: tuple[int, int]
) -> tuple[list[Any], list[Any]]:
    """Two frame stubs over ONE shared arm — the signature keys arm by identity,
    so a fresh arm per frame would separate them for the wrong reason."""
    arm = ArmStub(los, his, len(los))
    made: list[list[Any]] = []
    for count in counts:
        frame: list[Any] = [None] * 9
        frame[F_ARM], frame[F_I], frame[F_COUNT], frame[F_OUT] = arm, i, count, []
        made.append(frame)
    return made[0], made[1]


def test_an_unbounded_loop_past_its_floor_ignores_the_exact_count():
    """The take side took one more iteration — that must not separate them.

    Without this the raw counts differ forever and no two states ever match,
    which is exactly the bug that made the first implementation fall through to
    the slow path on every boundary.
    """
    stop, take = frames((0,), (-1,), 0, (3, 4))
    assert control_signature([stop], 7) == control_signature([take], 7)


def test_a_bounded_loop_keeps_its_count():
    """With a ceiling to run into, the exact count still constrains the future."""
    stop, take = frames((0,), (5,), 0, (3, 4))
    assert control_signature([stop], 7) != control_signature([take], 7)


def test_a_count_below_the_mandatory_floor_is_kept():
    """Below ``lo`` the count decides whether the loop may close at all."""
    stop, take = frames((3,), (-1,), 0, (1, 2))
    assert control_signature([stop], 7) != control_signature([take], 7)


def test_the_signature_ignores_the_values_built_so_far():
    """Values are the thing being MEASURED — folding them in defeats convergence."""
    stop, take = frames((0,), (-1,), 0, (1, 1))
    stop[F_OUT], take[F_OUT] = ["left"], ["right"]
    assert control_signature([stop], 7) == control_signature([take], 7)


def test_different_positions_never_share_a_signature():
    """Convergence is a claim about a shared position as much as a shared state."""
    frame, _other = frames((0,), (-1,), 0, (1, 1))
    assert control_signature([frame], 7) != control_signature([frame], 8)


def test_divergent_pending_values_do_not_agree():
    """The adversarial case: same control state, different values built.

    A false agreement here would commit what the engine refuses — the one
    failure the budget escape cannot protect against.
    """
    stop, take = frames((0,), (-1,), 0, (1, 1))
    stop[F_OUT], take[F_OUT] = ["a"], ["b"]
    assert not values_agree(pending_values([stop]), pending_values([take]))


def test_identical_pending_values_agree():
    """The common case — one production carved two ways to the same value."""
    stop, take = frames((0,), (-1,), 0, (1, 1))
    stop[F_OUT], take[F_OUT] = ["same"], ["same"]
    assert values_agree(pending_values([stop]), pending_values([take]))


def test_a_shape_mismatch_reads_as_disagreement_not_an_error():
    """Unequal shapes are a disagreement; the caller's next move is conservative."""
    assert not values_agree((("a",), ()), (("a", "b"), ()))
    assert not values_agree(("a",), "a")


def test_a_boundary_heavy_parse_still_round_trips():
    """The end-to-end claim: convergence changes the COST, not the answer."""
    compiled = compile_text(
        'root ::= item+\nitem ::= word ws\nword ::= [a-z]+\nws ::= " "*\n'
    )
    text = "alpha beta gamma delta epsilon "
    assert compiled.parse(text).to_text() == text
