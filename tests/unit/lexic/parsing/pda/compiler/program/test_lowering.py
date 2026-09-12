"""The build-tail contract: a composed builder means what the plan means.

The pin the specialisation rests on. Every shape the roster compiles, and
synthetic shapes past the widest template, must build an object equal to what
the plan describes — type included. If a composed builder ever drifts from its
plan, this is what says so.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.pda.compiler.program.lowering import (
    UNROLL_LIMIT,
    _general,
    field_read,
    no_shape_build,
    shape_build,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    M_CONST,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_SPAN,
    M_TEXT,
    M_VALUE,
)
from tests.build_tail_helpers import plan_means


class Shape(tuple):
    """A record of arbitrary width — the build tail does not care which."""

    __slots__ = ()


MODES = (M_MODEL, M_MODELS, M_TEXT, M_GTEXT, M_SPAN, M_CONST)
"""Every mode a composed build serves.

``M_VALUE`` is deliberately absent: it names the rule's own matched extent,
which is not any item's span, and its clone is built by ``vstr_model``. The
refusal is pinned below rather than a reading being invented for it.
"""


def plan_of(modes: tuple[int, ...]) -> tuple[tuple[int, int, int, object], ...]:
    """One plan entry per field, each reading its own item."""
    return tuple((mode, at, 1, None) for at, mode in enumerate(modes))


def capture_state(arity: int):
    """``(text, ends, sinks)`` wide enough for every item of ``arity`` fields."""
    return (
        "abcdefghijklmnop",
        list(range(arity + 2)),
        [[Shape()] for _ in range(arity + 2)],
    )


def expected(modes, text, ends, sinks):
    """The record the plan describes, read by the shared independent reader."""
    return tuple.__new__(Shape, plan_means(plan_of(modes), text, ends, sinks))


@pytest.mark.parametrize("arity", [*range(0, UNROLL_LIMIT + 4), 24])
def test_every_arity_builds_what_its_plan_means(arity: int) -> None:
    """Every unrolled template, the widest-plus-one, and a wide arity (24)
    past every template — the general comprehension builder's only case."""
    modes = tuple(MODES[k % len(MODES)] for k in range(arity))
    text, ends, sinks = capture_state(arity)
    built = shape_build(Shape, plan_of(modes))(text, ends, sinks)
    want = expected(modes, text, ends, sinks)
    assert built == want
    assert type(built) is type(want)


@pytest.mark.parametrize("arity", range(1, UNROLL_LIMIT + 1))
def test_the_unrolled_template_agrees_with_the_general_builder(arity: int) -> None:
    """Forcing the same plan through both builders must yield equal records
    of the same type — the selection in :func:`shape_build` is an
    optimisation, never a second meaning for the same plan."""
    modes = tuple(MODES[k % len(MODES)] for k in range(arity))
    plan = plan_of(modes)
    text, ends, sinks = capture_state(arity)
    reads = tuple(
        field_read(mode, item, lo, default) for mode, item, lo, default in plan
    )
    unrolled = shape_build(Shape, plan)(text, ends, sinks)
    general = _general(Shape, reads)(text, ends, sinks)
    assert unrolled == general
    assert type(unrolled) is type(general)


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_builds_what_it_means(mode: int) -> None:
    """One field, each mode in the vocabulary."""
    text, ends, sinks = capture_state(1)
    built = shape_build(Shape, plan_of((mode,)))(text, ends, sinks)
    assert built == expected((mode,), text, ends, sinks)


def test_a_frame_that_kept_no_sinks_falls_back_to_defaults() -> None:
    """A model field whose frame never descended takes its default."""
    build = shape_build(Shape, ((M_MODEL, 0, 1, None), (M_MODELS, 1, 1, None)))
    assert build("", [0, 0, 0], None) == tuple.__new__(Shape, (None, ()))


def test_an_unknown_mode_is_refused_with_words() -> None:
    """No silent fallback for a mode outside the build vocabulary."""
    with pytest.raises(UnsupportedConstructError, match="no build operation"):
        field_read(99, 0, 1, None)


def test_the_matched_extent_mode_is_refused_rather_than_read_off_an_item() -> None:
    """M_VALUE means the RULE's extent, and no item carries it.

    Reading item zero's text would agree only where the rule has one item, so
    the mode is refused here and served by ``vstr_model`` instead.
    """
    with pytest.raises(UnsupportedConstructError, match="no build operation"):
        field_read(M_VALUE, 0, 1, None)


def test_a_clone_that_builds_nothing_refuses_to_be_called() -> None:
    """Reaching the empty build is a bake defect, and says so."""
    with pytest.raises(UnsupportedConstructError, match="no positional build"):
        no_shape_build("", (), None)


# ── M_GTEXT: empty is absence only where the item may be absent ───────────


def test_gtext_empty_span_with_lo_zero_is_absence() -> None:
    """An optional group (``lo=0``) that matched empty text takes its default,
    not the empty string — the item never appeared, so its text is absence."""
    read = field_read(M_GTEXT, 0, 0, "the-default")
    assert read("", [0, 0], None) == "the-default"


def test_gtext_empty_span_with_lo_nonzero_is_the_empty_string() -> None:
    """A required group (``lo>=1``) that matched empty text is a real, if
    empty, match — the default must NOT be substituted for it."""
    read = field_read(M_GTEXT, 0, 1, "the-default")
    assert read("", [0, 0], None) == ""


def test_gtext_nonempty_span_ignores_lo_entirely() -> None:
    """Once the span is nonempty, ``lo`` plays no further part."""
    for lo in (0, 1, 3):
        read = field_read(M_GTEXT, 0, lo, "the-default")
        assert read("hi", [0, 2], None) == "hi"


# ── M_MODELS: a live sink list is frozen and copied, not aliased ──────────


def test_models_freezes_a_multi_element_run_in_order() -> None:
    """A field's whole run, in the order the kernel produced it."""
    subs = [Shape((1,)), Shape((2,)), Shape((3,))]
    read = field_read(M_MODELS, 0, 1, None)
    assert read("", [0, 0], [subs]) == (subs[0], subs[1], subs[2])


def test_models_result_does_not_alias_the_live_sink_list() -> None:
    """The kernel keeps mutating its sink list after the build reads it — the
    stored field must be a snapshot, or a later append would corrupt an
    already-built record."""
    subs = [Shape((1,))]
    read = field_read(M_MODELS, 0, 1, None)
    built = read("", [0, 0], [subs])
    subs.append(Shape((2,)))
    assert built == (Shape((1,)),)


def test_models_an_empty_but_present_sink_is_the_empty_tuple() -> None:
    """The item's sink list exists (the frame descended) but produced no
    sub-model — distinct from never descending at all, same empty result."""
    read = field_read(M_MODELS, 0, 1, None)
    assert read("", [0, 0], [[]]) == ()


def test_model_an_empty_but_present_sink_falls_back_to_default() -> None:
    """A single-model field whose sink exists but is empty takes its default,
    the same as a frame that never descended."""
    read = field_read(M_MODEL, 0, 1, "fallback")
    assert read("", [0, 0], [[]]) == "fallback"


def test_a_frame_with_sinks_falls_back_per_field_not_wholesale() -> None:
    """Sibling fields are independent: one item's empty sink must not affect
    another item's populated one in the same frame."""
    build = shape_build(
        Shape, ((M_MODEL, 0, 1, "d0"), (M_MODEL, 1, 1, "d1"), (M_MODELS, 2, 1, None))
    )
    sinks = [[], [Shape(("present",))], []]
    assert build("", [0, 0, 0, 0], sinks) == tuple.__new__(
        Shape, ("d0", Shape(("present",)), ())
    )
