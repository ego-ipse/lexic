"""Tests for lexic.parsing.pda.runtime.build — the fused model-build tail + frames.

Unit-pins the free functions shed out of the kernel: the frame-slot
layout, the delegate-completion window-edge/fail-soft rule, and the per-field
build dispatch (fast, validated, empty-arm). End-to-end coverage of these
through a real parse lives in ``test_kernel`` and the integration suite; this
module pins their branch logic in isolation with lightweight stubs.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from lexic.exceptions import FieldValidationError, UnsupportedConstructError
from lexic.parsing.fold import RuleFold
from lexic.parsing.pda.compiler.flatten import (
    M_CONST,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_TEXT,
    M_VALUE,
    FlatClone,
)
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.build import (
    F_ARM,
    F_CLONE,
    F_COUNT,
    F_ENDS,
    F_I,
    F_MODE,
    F_OUT,
    F_SINKS,
    F_START,
    INTERN_MISS,
    alt_model,
    build_fast,
    build_sequence,
    build_validated,
    build_vstr,
    finish_delegate,
    leaf_mismatch,
)


def make_frame(slots):
    """A 9-slot frame list with the given ``{F_slot: value}`` set (rest ``None``)."""
    frame = [None] * 9
    for idx, val in slots.items():
        frame[idx] = val
    return frame


def test_frame_layout_is_nine_distinct_slots():
    """The frame-slot constants index a 9-wide list, all distinct."""
    slots = [F_ARM, F_I, F_COUNT, F_OUT, F_MODE, F_CLONE, F_START, F_ENDS, F_SINKS]
    assert sorted(slots) == list(range(9))


# ── finish_delegate ──────────────────────────────────────────────────────────


def test_finish_delegate_returns_end_and_payload_on_a_clean_subrun():
    """A sub-run ending before the window edge files ``(end, payload)``."""
    sub = SimpleNamespace(prefix_run=lambda clone, pos: (3, "model"))
    assert finish_delegate(sub, cast(FlatClone, object()), "abcdef", 0) == (3, "model")


def test_finish_delegate_declines_at_the_window_edge():
    """A sub-run reaching the window edge returns ``None`` (grow the window)."""
    sub = SimpleNamespace(prefix_run=lambda clone, pos: (6, "model"))
    assert finish_delegate(sub, cast(FlatClone, object()), "abcdef", 0) is None


def test_finish_delegate_declines_on_pdafail():
    """A :class:`PdaFail` in the sub-run is caught into a decline."""

    def _boom(clone, pos):
        raise PdaFail("no")

    sub = SimpleNamespace(prefix_run=_boom)
    assert finish_delegate(sub, cast(FlatClone, object()), "abc", 0) is None


def test_finish_delegate_declines_on_a_lexic_error_from_the_fold():
    """A fold refusing the delegate's span (LexicError) declines — the island's
    own Earley machinery then parses the rule (valid-prefix truncation fix)."""

    def _refuse(clone, pos):
        raise UnsupportedConstructError("unknown symbol 'IrQuan'")

    sub = SimpleNamespace(prefix_run=_refuse)
    assert finish_delegate(sub, cast(FlatClone, object()), "abc", 0) is None


# ── alt_model ────────────────────────────────────────────────────────────────


def test_alt_model_returns_the_first_populated_sink():
    """The alternation pass-through returns the first non-empty sink's head."""
    frame = make_frame({F_SINKS: [[], ["m"], []]})
    assert alt_model(frame) == "m"


def test_alt_model_none_when_no_sinks():
    """No sinks (nothing captured) yields ``None``."""
    assert alt_model(make_frame({F_SINKS: None})) is None


# ── leaf_mismatch ────────────────────────────────────────────────────────────


def test_leaf_mismatch_empty_arm_builds_ctor_and_keeps_pos():
    """A zero-item arm builds ``ctor()`` and consumes nothing."""
    clone = cast(
        FlatClone,
        SimpleNamespace(fold=SimpleNamespace(ctor=lambda: "empty", n_items=2)),
    )
    out: list = []
    assert leaf_mismatch(clone, out, 0, 5, {}) == 5
    assert out == ["empty"]


def test_leaf_mismatch_nonempty_raises():
    """A non-empty item-count mismatch is a compile/runtime disagreement."""
    clone = cast(
        FlatClone, SimpleNamespace(fold=SimpleNamespace(ctor=lambda: None, n_items=2))
    )
    with pytest.raises(UnsupportedConstructError):
        leaf_mismatch(clone, [], 3, 0, {})


def test_leaf_mismatch_empty_arm_interns_one_shared_instance():
    """Two empty-arm builds of the same ctor share one instance via the memo."""
    calls = {"n": 0}

    def ctor():
        calls["n"] += 1
        return object()

    clone = cast(FlatClone, SimpleNamespace(fold=SimpleNamespace(ctor=ctor, n_items=2)))
    memo: dict = {}
    out: list = []
    leaf_mismatch(clone, out, 0, 0, memo)
    leaf_mismatch(clone, out, 0, 0, memo)
    assert out[0] is out[1]  # shared
    assert calls["n"] == 1  # ctor called once


# ── build_fast / build_validated per-field dispatch ─────────────────────────


def seq_clone(fields, *, fast, defaults=None, n_items=None, plan=None):
    """A stub ``sequence`` clone with the given int-coded fields + fast ctor.

    ``plan`` is the positional build plan the fused build reads; it defaults to
    one entry per field, in field order, which is what a single-field-per-slot
    class compiles to.
    """
    fold = SimpleNamespace(
        fields=fields,
        n_items=n_items if n_items is not None else len(fields),
        ctor=lambda **kw: ("ctor", kw),
        kind="sequence",
    )
    if plan is None:
        plan = tuple(
            (mode, item, lo, (defaults or {}).get(name))
            for item, mode, name, lo in fields
        )
    return cast(
        FlatClone,
        SimpleNamespace(
            fold=fold,
            fast=fast,
            defaults=defaults or {},
            fields=fields,
            plan=plan,
        ),
    )


def test_build_fast_fills_text_and_model_slots():
    """``M_TEXT`` reads the item span; ``M_MODEL`` reads the sink head."""
    fields = ((0, M_TEXT, "head", 1), (1, M_MODEL, "kid", 1))
    seen = []
    clone = seq_clone(fields, fast=lambda values: seen.extend(values) or "built")
    out = build_fast("abXY", clone, (0, [2, 2], [None, ["submodel"]]))
    assert out == "built"
    assert seen == ["ab", "submodel"]


def test_build_fast_models_slot_defaults_to_an_empty_tuple():
    """``M_MODELS`` with no sink yields ``()`` — coerced in the build, not the ctor."""
    fields = ((0, M_MODELS, "kids", 0),)
    seen = []
    clone = seq_clone(fields, fast=seen.extend)
    build_fast("", clone, (0, [0], None))
    assert seen == [()]


def test_build_fast_models_slot_coerces_the_live_sink_list():
    """The kernel hands a live list; the values carry a tuple (never aliased)."""
    fields = ((0, M_MODELS, "kids", 0),)
    seen = []
    clone = seq_clone(fields, fast=seen.extend)
    sink = ["a", "b"]
    build_fast("", clone, (0, [0], [sink]))
    sink.append("c")
    assert seen == [("a", "b")]


def test_build_fast_gtext_falls_back_to_the_default_on_an_empty_span():
    """An empty ``M_GTEXT`` span with ``lo == 0`` takes the plan's default."""
    fields = ((0, M_GTEXT, "opt", 0),)
    seen = []
    clone = seq_clone(fields, fast=seen.extend, defaults={"opt": "DEF"})
    build_fast("x", clone, (0, [0], None))  # span (0,0) empty, lo 0 -> default
    assert seen == ["DEF"]


def test_build_fast_gtext_keeps_an_empty_span_a_required_field_asked_for():
    """``lo`` non-zero means the empty span IS the value — not a missing field."""
    fields = ((0, M_GTEXT, "req", 1),)
    seen = []
    clone = seq_clone(fields, fast=seen.extend, defaults={"req": "DEF"})
    build_fast("x", clone, (0, [0], None))
    assert seen == [""]


def test_build_fast_model_slot_falls_back_to_the_default_on_an_empty_sink():
    """An optional ``M_MODEL`` whose sink never filled takes the default."""
    fields = ((0, M_MODEL, "kid", 0),)
    seen = []
    clone = seq_clone(fields, fast=seen.extend, defaults={"kid": None})
    build_fast("", clone, (0, [0], None))
    assert seen == [None]


def test_build_fast_const_slot_is_the_plan_default():
    """A class field no bound field supplies is ``M_CONST`` — a plan constant."""
    seen = []
    clone = seq_clone(
        ((0, M_TEXT, "head", 1),),
        fast=seen.extend,
        plan=((M_TEXT, 0, 1, None), (M_CONST, 0, 0, "fixed")),
    )
    build_fast("ab", clone, (0, [2], None))
    assert seen == ["ab", "fixed"]


def test_build_fast_does_not_intern_the_record_path():
    """Records build per occurrence: the key needed a second projection of every
    field and cost more than the tuple construction a hit would save.

    ``value_str`` models and the empty alternate arm still intern — their keys
    are already at hand. Value equality is what the parity gate gets; identity
    sharing is not promised for records.
    """
    fields = ((0, M_TEXT, "head", 1),)
    calls = {"n": 0}

    def fast(values):
        calls["n"] += 1
        return list(values)

    clone = seq_clone(fields, fast=fast)
    a = build_fast("ab", clone, (0, [2], None))
    b = build_fast("ab", clone, (0, [2], None))
    assert a == b
    assert a is not b
    assert calls["n"] == 2


def test_build_validated_unknown_mode_raises():
    """A field mode outside BIND_MODES is a hard error in the validated build."""
    fold = cast(
        RuleFold, SimpleNamespace(fields=((0, "bogus", "x", 1),), ctor=lambda **kw: kw)
    )
    with pytest.raises(UnsupportedConstructError):
        build_validated(
            "ab", make_frame({F_ENDS: [2], F_SINKS: None, F_START: 0}), fold, {}
        )


def test_build_validated_does_not_cache_a_raising_construction():
    """Interning is pre-construction: a raising ctor never populates the memo,
    so ``FieldValidationError`` (raised by the real validated ctor) is unchanged
    and a later valid build still constructs and caches."""
    state = {"boom": True, "n": 0}

    def ctor(**kwargs):
        state["n"] += 1
        if state["boom"]:
            raise FieldValidationError("bad field")
        return ("ok", kwargs)

    fold = cast(RuleFold, SimpleNamespace(fields=((0, "text", "head", 1),), ctor=ctor))
    frame = make_frame({F_ENDS: [2], F_SINKS: None, F_START: 0})
    memo: dict = {}
    with pytest.raises(FieldValidationError):
        build_validated("ab", frame, fold, memo)
    assert not memo  # nothing cached from the raising build
    state["boom"] = False
    out = build_validated("ab", frame, fold, memo)
    assert out == ("ok", {"head": "ab"})
    # a second identical build now hits the cache (ctor not re-invoked)
    assert build_validated("ab", frame, fold, memo) is out
    assert state["n"] == 2  # one failed + one successful; the hit adds nothing


def test_build_sequence_empty_arm_builds_bare_ctor():
    """A zero-item arm (``arm.n == 0``, ``n_items`` mismatch) builds ``ctor()``."""
    clone = cast(
        FlatClone,
        SimpleNamespace(
            fold=SimpleNamespace(n_items=2, ctor=lambda: ("bare",)),
            fast=None,
            fields=(),
        ),
    )
    frame = make_frame({F_ARM: SimpleNamespace(n=0)})
    assert build_sequence("", frame, clone, {}) == ("bare",)


# ── build_vstr (value_str build + intern) ────────────────────────────────────


def test_build_vstr_interns_by_ctor_and_span():
    """Equal ``(ctor, span)`` hits the memo; a differing span misses."""
    calls = {"n": 0}

    def ctor(value):
        calls["n"] += 1
        return ("vstr", value)

    clone = cast(FlatClone, SimpleNamespace(fold=SimpleNamespace(ctor=ctor), fast=None))
    memo: dict = {}
    a = build_vstr(clone, "true", memo)
    b = build_vstr(clone, "true", memo)
    assert a is b and a == ("vstr", "true")
    assert calls["n"] == 1
    c = build_vstr(clone, "false", memo)
    assert c is not a and calls["n"] == 2


def test_build_vstr_uses_fast_ctor_when_licensed():
    """With a fast licence, ``build_vstr`` builds positionally off the plan."""
    seen = []
    clone = cast(
        FlatClone,
        SimpleNamespace(
            fold=SimpleNamespace(ctor=lambda value: None),
            fast=lambda values: seen.extend(values) or "fast-built",
            plan=((M_VALUE, 0, 0, None),),
        ),
    )
    assert build_vstr(clone, "42", {}) == "fast-built"
    assert seen == ["42"]


def test_build_vstr_fills_a_non_value_field_from_the_plan_default():
    """A ``value_str`` class field beside ``value`` takes its plan constant."""
    seen = []
    clone = cast(
        FlatClone,
        SimpleNamespace(
            fold=SimpleNamespace(ctor=lambda value: None),
            fast=seen.extend,
            plan=((M_VALUE, 0, 0, None), (M_CONST, 0, 0, "DEF")),
        ),
    )
    build_vstr(clone, "42", {})
    assert seen == ["42", "DEF"]


def test_build_vstr_still_interns_by_ctor_and_span():
    """The one memo kept on the build path — its key is already at hand."""
    calls = {"n": 0}

    def fast(values):
        calls["n"] += 1
        return list(values)

    clone = cast(
        FlatClone,
        SimpleNamespace(
            fold=SimpleNamespace(ctor=lambda value: None),
            fast=fast,
            plan=((M_VALUE, 0, 0, None),),
        ),
    )
    memo: dict = {}
    assert build_vstr(clone, "42", memo) is build_vstr(clone, "42", memo)
    assert calls["n"] == 1
    build_vstr(clone, "43", memo)
    assert calls["n"] == 2


def test_intern_miss_sentinel_is_distinct():
    """The miss sentinel equals nothing a build produces (a real ``None`` sink)."""
    assert INTERN_MISS is not None
    memo: dict = {}
    assert memo.get(("k",), INTERN_MISS) is INTERN_MISS
