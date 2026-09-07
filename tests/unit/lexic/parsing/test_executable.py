"""Tests for lexic.parsing.executable — the bound model product.

``ModelExecutable`` retains no authored rules — its slots are exactly
``program``/``codes``/``routines``/``executor`` — and every downstream
consumer reads ``routines``, the verified program read back.

Verification is a claim about an object, so the object cannot change after it
is made: the executable refuses every rebinding, and ``codes``/``routines`` are
read-only views over containers no caller holds. ``replica()`` shares the
verified ``program`` and both read-only views by identity — nothing can write
through them — and its executor makes its own private physical copy, which is
the container a worker must not share.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.product import (
    CaptureMode,
    CaptureSpec,
    LoweringOwned,
    PassOp,
    RecordConstructor,
    RecordOp,
    RuleProduct,
)
from lexic.parsing.product.tree import ProductExecutor
from tests.unit.lexic.parsing.product_test_helpers import Pair, two_text_capture_rule

_RULES = {
    "a": RuleProduct(
        captures=(CaptureSpec(int(CaptureMode.ONE), 0),), completion=PassOp(0)
    ),
    "b": RuleProduct(
        captures=(CaptureSpec(int(CaptureMode.ONE), 1),), completion=PassOp(0)
    ),
}


def test_model_binding_holds_no_authored_record_at_all():
    """The slot set IS exactly program/codes/routines/executor — nothing else.

    A test naming a fifth slot (``rules``, ``owned``, ``construction``) would
    fail here, which is the point: those were deleted, not renamed.
    """
    assert set(ModelExecutable.__slots__) == {
        "program",
        "codes",
        "routines",
        "executor",
    }


def test_default_construction_binds_no_rules():
    """A binding built with nothing declares an empty codes/routines pair."""
    binding = ModelExecutable()
    assert binding.codes == {}
    assert binding.routines == {}


def test_codes_and_routines_share_exactly_the_same_key_set():
    """Every rule name in codes has a routine, and vice versa."""
    binding = ModelExecutable(_RULES)
    assert binding.codes.keys() == binding.routines.keys() == _RULES.keys()
    assert binding.codes == {"a": 0, "b": 1}


def test_the_executor_completes_through_its_own_private_routine_copy():
    """The executor's container is EQUAL and private — not the published view.

    The defect this catches: handing the executor the very mapping a caller can
    reach would let the parser be re-aimed after verification, which is what
    the published read-only view exists to prevent.
    """
    binding = ModelExecutable(_RULES)
    assert isinstance(binding.executor, ProductExecutor)
    assert binding.executor.routines == binding.routines
    assert binding.executor.routines is not binding.routines
    assert not isinstance(binding.executor.routines, dict)


def test_a_bound_executable_refuses_every_rebinding():
    """Verification is a claim about the object, so the object cannot change."""
    binding = ModelExecutable(_RULES)
    for name in ("program", "codes", "routines", "executor"):
        with pytest.raises(UnsupportedConstructError):
            setattr(binding, name, {})
        with pytest.raises(UnsupportedConstructError):
            delattr(binding, name)


def test_the_published_projections_cannot_be_written_through():
    """codes and routines are read-only VIEWS; the parser cannot be re-aimed.

    Pinned as the absence of a write path rather than as a caught exception:
    a write attempt is only expressible by first lying about the type, and the
    view is what makes the lie necessary.
    """
    binding = ModelExecutable(_RULES)
    assert isinstance(binding.routines, MappingProxyType)
    assert isinstance(binding.codes, MappingProxyType)
    assert not hasattr(binding.routines, "__setitem__")
    assert not hasattr(binding.codes, "__setitem__")
    assert binding.executor.routines.keys() == {"a", "b"}


def test_an_invalid_pass_is_refused_at_binding_not_at_the_first_parse():
    """A PASS whose source names no capture cannot forward anything.

    It bound successfully before, and `_passed_value` discovered it while
    completing a real parse. The cold gate owns that answer now.
    """
    bad = {"a": RuleProduct(captures=(), completion=PassOp(0))}
    with pytest.raises(UnsupportedConstructError, match="passes capture 0"):
        ModelExecutable(bad)


def test_the_meaning_comparator_is_the_engines_own_same_value_law():
    """Every ambiguity gate compares with same_value — the program declares it."""
    binding = ModelExecutable(_RULES)
    assert binding.program.operands.meanings == (same_value,)


def test_the_default_root_finalizer_is_the_identity():
    """The default root finalizer is the start rule's value, unchanged."""
    binding = ModelExecutable(_RULES)
    finalizer = binding.program.operands.roots[0]
    sentinel = object()
    assert finalizer(sentinel, ()) is sentinel


def test_construction_verifies_and_refuses_a_bad_rule():
    """The constructor lowers AND verifies — a malformed rule cannot reach here."""
    bad = {"a": RuleProduct(captures=(), completion=RecordOp(0))}  # no constructor 0
    with pytest.raises(UnsupportedConstructError):
        ModelExecutable(bad)


def test_a_declared_constructor_resolves_through_the_bound_routine():
    """A real RECORD rule's routine carries the resolved construction."""
    rules = {"root": two_text_capture_rule()}
    owned = LoweringOwned(constructors=(RecordConstructor(cls=Pair, names=("a", "b")),))
    binding = ModelExecutable(rules, owned)
    construction = binding.routines["root"].construction
    assert construction is not None
    assert construction.call is Pair


# ── replica() ──────────────────────────────────────────────────────────


def test_replica_shares_the_verified_program_and_codes_by_identity():
    """Nothing is lowered or verified again — same immutable objects."""
    binding = ModelExecutable(_RULES)
    replica = binding.replica()
    assert replica.program is binding.program
    assert replica.codes is binding.codes


def test_replica_shares_the_read_only_view_because_nothing_can_write_it():
    """The published views are immutable, so a worker needs no copy of them."""
    binding = ModelExecutable(_RULES)
    replica = binding.replica()
    assert replica.routines is binding.routines


def test_replica_gets_its_own_executor_over_its_own_private_container():
    """A replica's executor holds its OWN physical copy — the shared-refcount fix."""
    binding = ModelExecutable(_RULES)
    replica = binding.replica()
    assert replica.executor is not binding.executor
    assert replica.executor.routines == binding.executor.routines
    assert replica.executor.routines is not binding.executor.routines
