"""Tests for compile/foldkit.py — the shared authored-fold vocabulary.

Two tiers live here: the pass-throughs (``ALT``/``ALT_BODY``/``passthrough``)
and the shared idioms (``first_rest``, the ``DECODE_INT`` int decode, the
``absent_tail`` absent-default tail). Every hand-authored grammar+fold pair
(the notation, the module self-grammar) reuses these SAME objects rather than
each defining its own copy.
"""

from __future__ import annotations

from typing import Sequence, cast

import pytest

from lexic.compile.foldkit import (
    ABSENT,
    ALT,
    ALT_BODY,
    DECODE_INT,
    FIRST_REST,
    FOLD_SYMBOLS,
    IrNamed,
    absent_tail,
    first_rest,
    model_fold,
    passthrough,
    seq,
)
from lexic.compile.module import selfgrammar
from lexic.compile.notation import parse as notation
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLambda, IrNone, IrSelf
from lexic.parsing import ModelBody, ModelFold, RuleFold

# ── the pass-throughs ────────────────────────────────────────────────────


def test_alt_is_an_alternation_rule_fold():
    """ALT is a RuleFold whose kind is "alternation" with no bound fields."""
    assert isinstance(ALT, RuleFold)
    assert ALT.kind == "alternation"
    assert ALT.n_items == 0
    assert ALT.fields == ()


def test_alt_ctor_is_unused_and_returns_none():
    """The alternation ctor slot is ignored by the fold; it returns None."""
    assert ALT.ctor() is None


def test_alt_body_is_the_model_body_form_of_alt():
    """ALT_BODY is the IrMap-authoring ModelBody form of ALT (ctor IrNone)."""
    assert isinstance(ALT_BODY, ModelBody)
    assert ALT_BODY.kind == "alternation"
    assert ALT_BODY.ctor is IrNone
    assert ALT_BODY.bake().kind == "alternation"


def test_passthrough_returns_its_argument_unchanged():
    """passthrough is a pure identity function over any value."""
    sentinel = object()
    assert passthrough(sentinel) is sentinel
    assert passthrough("x") == "x"
    assert passthrough(0) == 0
    assert passthrough(None) is None


# ── surface reuse (by identity) ──────────────────────────────────────────


def test_notation_reuses_the_shared_vocabulary_objects():
    """notation.py consumes foldkit's shared vocab BY IDENTITY, not a copy."""
    assert notation.ALT_BODY is ALT_BODY
    assert notation.passthrough is passthrough
    assert notation.first_rest is first_rest
    assert notation.absent_tail is absent_tail
    assert notation.DECODE_INT is DECODE_INT


def test_selfgrammar_reuses_the_shared_vocabulary_objects():
    """selfgrammar.py consumes foldkit's shared vocab BY IDENTITY too."""
    assert selfgrammar.ALT_BODY is ALT_BODY
    assert selfgrammar.passthrough is passthrough
    assert selfgrammar.first_rest is first_rest
    assert selfgrammar.DECODE_INT is DECODE_INT
    assert selfgrammar.FIRST_REST is FIRST_REST


# ── the shared idioms — behavior ─────────────────────────────────────────


def test_first_rest_prepends_head_to_tail():
    """first_rest is the head-plus-tail list collector."""
    assert first_rest("a") == ("a",)
    assert first_rest("a", ["b", "c"]) == ("a", "b", "c")
    assert first_rest("a", ()) == ("a",)


def test_absent_tail_returns_the_present_value_including_ir_none():
    """absent_tail returns the keyword value when present — even IrNone."""
    assert absent_tail(v="x") == "x"
    assert absent_tail(v=IrNone) is IrNone  # IrNone is a legitimate argument
    assert absent_tail() is ABSENT  # an empty call is the omitted tail


# ── IrNamed — the named-callable leaf (the no-exec boundary) ─────────────


def test_ir_named_resolves_and_applies_the_registered_callable():
    """IrNamed(key).eval applies FOLD_SYMBOLS[key] to the argument channel."""
    intch = cast(Sequence[IrSelf], ("42",))
    listch = cast(Sequence[IrSelf], ("a", ["b"]))
    assert DECODE_INT.eval(IrNone, IrNone, intch) == 42
    assert FIRST_REST.eval(IrNone, IrNone, listch) == ("a", "b")


def test_ir_named_repr_is_codegen_by_key():
    """IrNamed reprs by its registry key — manifest-shaped, unlike IrLambda."""
    assert repr(DECODE_INT) == "IrNamed('int')"
    assert repr(FIRST_REST) == "IrNamed('first_rest')"


def test_ir_named_equality_is_structural_over_the_key():
    """Two IrNamed leaves are equal iff their registry keys match."""
    assert IrNamed("int") == DECODE_INT
    assert IrNamed("int") != FIRST_REST
    assert hash(IrNamed("int")) == hash(DECODE_INT)


def test_ir_named_unknown_symbol_refuses():
    """An unregistered key raises at eval — the no-exec boundary."""
    with pytest.raises(UnsupportedConstructError, match="unknown fold symbol"):
        IrNamed("nope").eval(IrNone, IrNone, ())


def test_fold_symbols_is_the_curated_registry():
    """FOLD_SYMBOLS holds only the shared idiom callables."""
    assert FOLD_SYMBOLS["int"] is int
    assert FOLD_SYMBOLS["first_rest"] is first_rest
    assert FOLD_SYMBOLS["passthrough"] is passthrough


# ── the authoring helpers ────────────────────────────────────────────────


def test_seq_wraps_a_plain_callable_in_ir_lambda():
    """seq lifts a plain callable to an IrLambda-bodied sequence ModelBody."""
    body = seq(passthrough, 1, ())
    assert isinstance(body, ModelBody)
    assert body.kind == "sequence"
    assert isinstance(body.ctor, IrLambda)


def test_seq_carries_a_shared_ir_body_as_is():
    """seq carries a shared IR body (DECODE_INT) unchanged — the channel path."""
    body = seq(DECODE_INT, 1, ())
    assert body.ctor is DECODE_INT


def test_model_fold_builds_a_fold_from_a_name_body_table():
    """model_fold assembles the IR body-table into a working ModelFold."""
    fold = model_fold({"r": seq(passthrough, 1, ())})
    assert isinstance(fold, ModelFold)
    assert set(fold.baked) == {"r"}
