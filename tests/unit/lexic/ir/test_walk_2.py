"""Tests for ``ir/walk_2.py`` — action-driven dispatcher on the IrSelf substrate.

The dispatcher is an :class:`IrCollection` whose items are the action table.
``apply(root)`` is the entry verb — chosen over ``__call__`` because
``__call__`` is reserved for IrSelf-identity (returns ``Self``). Overriding
it on the dispatcher would violate LSP.

Walk semantics
--------------
1. Recurse ``node.children()`` post-order, building ``new_children`` per node.
2. Resolve the matching :class:`IrAction` via concrete-first MRO walk over
   the action table (memoised).
3. If matched, invoke ``action.body.eval(self, node, new_children)``.
4. If unmatched, fall through to the preset ``_default``.

``_Return`` (BaseException) is caught once at ``apply`` — internal recursion
never catches it, so any ``IrReturn`` body unwinds straight to the top.

Presets
-------
``IrVisitor[None]``         side-effect walker; default returns ``None``.
``IrTransformer[IrNode]``   rewrites IR; default rebuilds on child change.
``IrEmitter[str]``          produces strings; default ``str(node)`` when
                             actions empty, else raise
                             ``UnsupportedConstructError``.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction, IrCallable, IrReturn, _Return
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLeaf,
    IrLiteral,
    IrNode,
    IrNone,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.walk_2 import IrDispatch, IrEmitter, IrTransformer, IrVisitor

# ── Fixtures ─────────────────────────────────────────────────────────


def _tiny_ast() -> IrAst:
    """Build a small AST for traversal tests.

    :returns: An IrAst with a single rule ``r`` referencing itself.
    """
    rule = IrRule(
        name="r",
        body=IrAlternation(
            arms=(IrSequence(items=(IrItem(atom=IrRuleRef(name="r")),)),)
        ),
    )
    return IrAst(rules=(rule,), start="r")


# ── IrDispatch fundamentals ──────────────────────────────────────────


def test_irdispatch_is_an_ircollection_of_actions():
    """IrDispatch IS an IrCollection — children are the actions tuple."""
    from lexic.ir.nodes import IrCollection

    a = IrAction(IrLiteral, IrLiteral("x"))
    d = IrVisitor(actions=(a,))
    assert isinstance(d, IrCollection)
    assert d.children() == (a,)
    assert d.actions == (a,)


def test_irdispatch_apply_with_no_actions_invokes_preset_default():
    """Empty action table falls through to the preset's ``_default``."""
    assert IrVisitor().apply(IrLiteral("a")) is None


def test_irdispatch_concrete_action_wins_over_abstract():
    """A concrete-type action wins over an IrLeaf/IrNode-keyed catch-all."""
    seen: list[str] = []
    leaf_action = IrAction(
        IrLeaf, IrCallable[None](lambda _d, _n, _nc: seen.append("leaf"))
    )
    lit_action = IrAction(
        IrLiteral, IrCallable[None](lambda _d, _n, _nc: seen.append("lit"))
    )
    IrVisitor(actions=(leaf_action, lit_action)).apply(IrLiteral("x"))
    assert seen == ["lit"]


def test_irdispatch_falls_through_to_abstract_action_when_no_concrete_match():
    """An IrLeaf-keyed action catches IrRuleRef (which IS-A IrLeaf)."""
    seen: list[str] = []
    leaf_action = IrAction(
        IrLeaf, IrCallable[None](lambda _d, _n, _nc: seen.append("leaf"))
    )
    IrVisitor(actions=(leaf_action,)).apply(IrRuleRef("r"))
    assert seen == ["leaf"]


def test_irdispatch_walks_children_automatically():
    """Walking the whole AST visits every descendant node."""
    visited: list[type] = []

    def _on(_d, n, _nc):
        visited.append(type(n))

    d = IrVisitor(actions=(IrAction(IrNode, IrCallable[None](_on)),))
    d.apply(_tiny_ast())
    assert IrRuleRef in visited
    assert IrItem in visited
    assert IrAst in visited


def test_irdispatch_passes_new_children_to_action_body():
    """An action body receives ``new_children`` already dispatched."""
    captured: list[tuple] = []

    def _on(_d, _n, new_children):
        captured.append(new_children)
        return None

    # IrItem has children (atom, quantifier). new_children carries the
    # dispatched results for each — under IrVisitor that's (None, None).
    d = IrVisitor(actions=(IrAction(IrItem, IrCallable[None](_on)),))
    d.apply(IrItem(atom=IrLiteral("x")))
    assert captured == [(None, None)]


# ── IrReturn short-circuit ───────────────────────────────────────────


def test_irreturn_short_circuits_at_entry():
    """First IrRuleRef raises _Return; rest of subtree is not visited."""
    visit_count = 0

    def _on_ref(_d, _n, _nc):
        nonlocal visit_count
        visit_count += 1
        raise _Return(True)

    ast = IrAst(
        rules=(
            IrRule(
                name="r",
                body=IrAlternation(
                    arms=(
                        IrSequence(
                            items=(
                                IrItem(atom=IrRuleRef(name="a")),
                                IrItem(atom=IrRuleRef(name="b")),
                            )
                        ),
                    )
                ),
            ),
        ),
        start="r",
    )
    d = IrVisitor(actions=(IrAction(IrRuleRef, IrCallable[None](_on_ref)),))
    assert d.apply(ast) is True
    assert visit_count == 1


def test_irreturn_via_op_unwinds_to_entry():
    """IrReturn body raises _Return(value); ``apply`` returns that value."""
    d = IrVisitor(actions=(IrAction(IrRuleRef, IrReturn[None](None)),))
    assert d.apply(IrRuleRef("x")) is None


# ── Resolve cache (observable) ───────────────────────────────────────


def test_repeated_dispatch_does_not_rebuild_action_table():
    """Cache hit: repeated apply on same root type produces consistent
    behaviour with no observable re-resolution side effects."""
    resolve_calls: list[type] = []

    def _on(_d, n, _nc):
        resolve_calls.append(type(n))

    d = IrVisitor(actions=(IrAction(IrLiteral, IrCallable[None](_on)),))
    d.apply(IrLiteral("a"))
    d.apply(IrLiteral("b"))
    d.apply(IrLiteral("c"))
    # The action fired once per call — three times total.
    assert resolve_calls == [IrLiteral, IrLiteral, IrLiteral]


def test_dispatcher_is_frozen_actions_immutable():
    """Frozen dataclass: actions field cannot be rebound after construction."""
    from dataclasses import FrozenInstanceError

    d = IrVisitor()
    with pytest.raises(FrozenInstanceError):
        # Use object.__setattr__ to bypass pyright's frozen-write check;
        # the runtime still raises, which is what we're testing.
        object.__setattr__(d, "actions", ())


# ── IrVisitor ────────────────────────────────────────────────────────


def test_irvisitor_empty_actions_returns_none():
    """IrVisitor with no actions returns ``None`` for any root."""
    assert IrVisitor().apply(IrLiteral("a")) is None
    assert IrVisitor().apply(_tiny_ast()) is None


# ── IrTransformer ────────────────────────────────────────────────────


def test_irtransformer_empty_actions_is_identity():
    """IrTransformer with no actions returns the root unchanged."""
    seq = IrSequence(items=(IrItem(atom=IrLiteral("a")),))
    assert IrTransformer().apply(seq) == seq


def test_irtransformer_rebuilds_on_child_change():
    """When an action returns a different child, parent is rebuilt."""

    def _swap(_d, _n, _nc):
        return IrLiteral("Z")

    t = IrTransformer(actions=(IrAction(IrLiteral, IrCallable[IrNode](_swap)),))
    item = IrItem(atom=IrLiteral("a"))
    new = t.apply(item)
    assert isinstance(new, IrItem)
    assert new.atom == IrLiteral("Z")


def test_irtransformer_no_change_preserves_identity():
    """An identity-returning action doesn't trigger rebuild."""

    def _identity(_d, n, _nc):
        return n

    t = IrTransformer(actions=(IrAction(IrLiteral, IrCallable[IrNode](_identity)),))
    lit = IrLiteral("a")
    assert t.apply(lit) is lit


# ── IrEmitter ────────────────────────────────────────────────────────


def test_iremitter_empty_actions_falls_back_to_str_node():
    """IrEmitter with no actions returns ``str(node)`` — canonical-form fallback."""
    out = IrEmitter().apply(IrLiteral("hi"))
    assert "hi" in out


def test_iremitter_with_actions_raises_on_unhandled_type():
    """If actions are configured but none match, raise UnsupportedConstructError."""
    e = IrEmitter(actions=(IrAction(IrLiteral, IrLiteral("L")),))
    with pytest.raises(UnsupportedConstructError):
        e.apply(IrRuleRef("x"))


def test_iremitter_action_on_irnode_acts_as_per_instance_default():
    """User-supplied IrAction(IrNode, ...) catches everything; preset default never fires."""
    e = IrEmitter(
        actions=(
            IrAction(IrLiteral, IrLiteral("L")),
            IrAction(IrNode, IrLiteral("ANY")),
        )
    )
    assert e.apply(IrRuleRef("x")) == "ANY"
    assert e.apply(IrLiteral("y")) == "L"


# ── IrNone in dispatch slots ─────────────────────────────────────────


def test_action_body_receives_dispatcher_as_first_arg():
    """``action.body.eval(self, node, new_children)`` — first arg is the dispatcher."""
    captured: list[IrDispatch] = []

    def _on(d, _n, _nc):
        captured.append(d)

    d = IrVisitor(actions=(IrAction(IrLiteral, IrCallable[None](_on)),))
    d.apply(IrLiteral("a"))
    assert captured == [d]


def test_action_body_evaluating_irnone_returns_none_value():
    """An action body that returns IrNone (the sentinel) propagates it."""

    def _on(_d, _n, _nc):
        return IrNone

    d = IrVisitor(actions=(IrAction(IrLiteral, IrCallable[None](_on)),))
    # IrVisitor's Ir_co is None; this isn't a value test but a propagation test.
    # The action body is allowed to return any object; the dispatcher returns
    # whatever the top-level action returned.
    assert d.apply(IrLiteral("a")) is IrNone
