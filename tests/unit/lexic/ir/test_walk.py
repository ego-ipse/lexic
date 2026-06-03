"""Tests for ``ir/walk.py`` — action-driven dispatcher on the IrSelf substrate.

The dispatcher is an :class:`~lexic.ir.nodes.IrComposite` whose ``actions``
tuple is the action table. ``apply(root)`` is the entry verb — chosen over
``__call__`` because ``__call__`` is reserved for IrSelf-identity (returns
``Self``). Overriding it on the dispatcher would violate LSP.

Walk semantics
--------------
The dispatcher does **not** recurse children automatically. ``apply(root)``
calls ``eval(self, root, ())`` once; the resolved action's body is responsible
for any recursion (typically by calling ``d.eval(d, c, ())`` on each child it
cares about, or by leveraging :class:`~lexic.ir.action.IrRebuild` which
walks then rebuilds).

Action resolution
-----------------
The matching :class:`~lexic.ir.action.IrAction` is resolved via
concrete-first MRO walk over the action table (memoised). When no action
matches, the dispatcher falls through to ``self.default``; when ``default``
is :class:`~lexic.ir.action.IrRaise`, that raises
:exc:`~lexic.exceptions.UnsupportedConstructError`.

Short-circuit
-------------
A body raising :class:`~lexic.ir.action.IrReturn` is caught at ``apply``
— its ``.value`` is returned provided it satisfies the dispatcher's ``Ir_co``
bound; otherwise it re-raises and propagates past the dispatcher (same as
bare :class:`~lexic.ir.action._Return`).

Presets
-------
``IrVisitor``       Side-effect walker. Default action :class:`~lexic.ir.action.IrWalk`
                    recurses into children and returns :data:`~lexic.ir.nodes.IrNone`.
``IrTransformer``   Rewrites IR. Default action
                    :class:`~lexic.ir.action.IrRebuild` walks children via
                    ``d`` and rebuilds the node.
``IrEmitter``       Produces :class:`~lexic.ir.nodes.IrLiteral`. Default
                    action :class:`~lexic.ir.action.IrEmit` wraps ``str(n)``
                    in :class:`~lexic.ir.nodes.IrLiteral`; override with
                    ``default=IrRaise()`` to refuse unmatched types.
"""

from dataclasses import FrozenInstanceError

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import IrAction, IrCallable, IrEmit, IrRaise, IrRebuild, IrReturn
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrComposite,
    IrItem,
    IrLeaf,
    IrLiteral,
    IrNode,
    IrNone,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSequence,
    IrTuple,
)
from lexic.ir.walk import IrDispatch, IrEmitter, IrTransformer, IrVisitor

# ── Fixtures ─────────────────────────────────────────────────────────


def _tiny_ast() -> IrAst:
    """Build a small AST for traversal tests.

    :returns: An IrAst with a single rule ``r`` referencing itself.
    """
    rule = IrRule(
        "r",
        IrAlternation(IrSequence(IrItem(atom=IrRuleRef("r")))),
    )
    return IrAst(rules=IrTuple(rule), start="r")


# ── IrDispatch fundamentals ──────────────────────────────────────────
def test_irdispatch_is_composite():
    """IrDispatch IS-AN IrComposite."""
    a = IrAction(IrLiteral, IrLiteral("x"))
    d = IrVisitor(actions=(a,))
    assert isinstance(d, IrComposite)
    assert d.actions == (a,)
    assert not d.children()


def test_dispatch_resolves_action():
    """IrDispatch resolves the registered action and applies it."""
    d = IrDispatch(actions=(IrAction(IrLiteral, IrEmit()),))
    assert isinstance(d, IrComposite)
    assert d.apply(IrLiteral("x")) == "x"


def test_resolve_cache_excluded_from_equality():
    """_resolve_cache is excluded from __eq__ — two dispatchers with equal
    actions compare equal regardless of cache state."""
    a = IrDispatch(actions=())
    b = IrDispatch(actions=())
    assert a == b


def test_irdispatch_apply_with_no_actions_invokes_preset_default():
    """``IrVisitor``'s preset default :class:`~lexic.ir.action.IrWalk`
    returns :data:`~lexic.ir.nodes.IrNone`."""
    assert IrVisitor().apply(IrLiteral("a")) is IrNone


def test_irdispatch_concrete_action_wins_over_abstract():
    """A concrete-type action wins over an IrLeaf/IrNode-keyed catch-all."""
    seen: list[str] = []
    leaf_action = IrAction(
        IrLeaf, IrCallable(lambda _d, _n, _nc: seen.append("leaf") or IrNone)
    )
    lit_action = IrAction(
        IrLiteral, IrCallable(lambda _d, _n, _nc: seen.append("lit") or IrNone)
    )
    IrVisitor(actions=(leaf_action, lit_action)).apply(IrLiteral("x"))
    assert seen == ["lit"]


def test_irdispatch_falls_through_to_abstract_action_when_no_concrete_match():
    """An IrLeaf-keyed action catches IrRuleRef (which IS-A IrLeaf)."""
    seen: list[str] = []
    leaf_action = IrAction(
        IrLeaf, IrCallable(lambda _d, _n, _nc: seen.append("leaf") or IrNone)
    )
    IrVisitor(actions=(leaf_action,)).apply(IrRuleRef("r"))
    assert seen == ["leaf"]


def test_action_body_can_recurse_explicitly_via_dispatcher():
    """The dispatcher does not auto-walk. A body that wants child recursion
    calls ``d.eval(d, c, ())`` on each child itself."""
    visited: list[type] = []

    def _on(d, n, _nc):
        visited.append(type(n))
        for c in n.children():
            d.eval(d, c, ())
        return IrNone

    d = IrVisitor(actions=(IrAction(IrNode, IrCallable(_on)),))
    d.apply(_tiny_ast())
    assert IrAst in visited
    assert IrRuleRef in visited
    assert IrItem in visited


def test_action_body_receives_pre_dispatched_children_when_caller_supplies_them():
    """``nc`` is empty at entry but populated when an outer body pre-walked.
    Calling ``d.eval(d, n, nc)`` directly hands the body its ``nc``."""
    captured: list[tuple] = []

    def _on(_d, _n, new_children):
        captured.append(tuple(new_children))
        return IrNone

    d = IrVisitor(actions=(IrAction(IrItem, IrCallable(_on)),))
    item = IrItem(atom=IrLiteral("x"))
    pre = IrTuple(IrLiteral("PRE"), IrLiteral("Q"))
    d.eval(d, item, pre)
    assert captured == [(IrLiteral("PRE"), IrLiteral("Q"))]


# ── IrReturn short-circuit ───────────────────────────────────────────


def test_irreturn_short_circuits_subtree_walk():
    """A body that recurses children and raises IrReturn unwinds to ``apply``.
    The remaining siblings are never visited."""
    visit_count = 0

    def _on_ref(_d, _n, _nc):
        nonlocal visit_count
        visit_count += 1
        raise IrReturn[IrSelf](IrNone)

    def _walk(d, n, _nc):
        for c in n.children():
            d.eval(d, c, ())
        return IrNone

    ast = IrAst(
        rules=IrTuple(
            IrRule(
                "r",
                IrAlternation(
                    IrSequence(
                        IrItem(atom=IrRuleRef("a")),
                        IrItem(atom=IrRuleRef("b")),
                    )
                ),
            )
        ),
        start="r",
    )
    d = IrVisitor(
        actions=(
            IrAction(IrRuleRef, IrCallable[IrNode](_on_ref)),
            IrAction(IrNode, IrCallable[IrSelf](_walk)),
        )
    )
    assert d.apply(ast) is IrNone
    assert visit_count == 1


def test_irreturn_value_returned_when_satisfies_bound():
    """``IrReturn`` whose ``.value`` satisfies the dispatcher's bound is
    returned as the dispatched value."""
    d = IrVisitor(actions=(IrAction(IrRuleRef, IrReturn[IrSelf](IrNone)),))
    assert d.apply(IrRuleRef("x")) is IrNone


# ── Resolve cache (observable) ───────────────────────────────────────


def test_repeated_dispatch_does_not_rebuild_action_table():
    """Cache hit: repeated apply on same root type produces consistent
    behaviour with no observable re-resolution side effects."""
    resolve_calls: list[type] = []

    def _on(_d, n, _nc):
        resolve_calls.append(type(n))
        return IrNone

    d = IrVisitor(actions=(IrAction(IrLiteral, IrCallable[IrSelf](_on)),))
    d.apply(IrLiteral("a"))
    d.apply(IrLiteral("b"))
    d.apply(IrLiteral("c"))
    assert resolve_calls == [IrLiteral, IrLiteral, IrLiteral]


def test_dispatcher_is_frozen_actions_immutable():
    """Frozen dataclass: actions field cannot be rebound after construction."""
    d = IrVisitor()
    with pytest.raises(FrozenInstanceError):
        # Frozen-dataclass __setattr__ raises; setattr() goes through it.
        setattr(d, "actions", ())


# ── IrVisitor ────────────────────────────────────────────────────────


def test_irvisitor_empty_actions_returns_irnone():
    """IrVisitor with no user actions walks via IrWalk and returns IrNone."""
    assert IrVisitor().apply(IrLiteral("a")) is IrNone
    assert IrVisitor().apply(_tiny_ast()) is IrNone


def test_irvisitor_default_walks_into_children():
    """The default IrWalk body recurses into every child node."""
    visited: list[type] = []

    def _record(_d, n, _nc):
        visited.append(type(n))
        return IrNone

    d = IrVisitor(actions=(IrAction(IrLiteral, IrCallable[IrSelf](_record)),))
    ast = IrAst(
        rules=IrTuple(
            IrRule(
                "r",
                IrAlternation(
                    IrSequence(
                        IrItem(atom=IrLiteral("a")),
                        IrItem(atom=IrLiteral("b")),
                    )
                ),
            )
        ),
        start="r",
    )
    d.apply(ast)
    assert visited == [IrLiteral, IrLiteral]


# ── IrTransformer ────────────────────────────────────────────────────


def test_irtransformer_empty_actions_rebuilds_to_equal_tree():
    """IrTransformer with no user actions walks via IrRebuild and
    produces a tree equal to the input."""
    seq = IrSequence(IrItem(atom=IrLiteral("a")))
    assert IrTransformer().apply(seq) == seq


def test_irtransformer_rebuilds_with_replaced_child():
    """A user action returning a different child causes the parent to be
    rebuilt with that child in place."""

    def _swap(_d, _n, _nc):
        return IrLiteral("Z")

    t = IrTransformer(
        actions=(
            IrAction(IrLiteral, IrCallable[IrNode](_swap)),
            IrAction(IrNode, IrRebuild()),
        )
    )
    item = IrItem(atom=IrLiteral("a"))
    new = t.apply(item)
    assert isinstance(new, IrItem)
    assert new.atom == IrLiteral("Z")


# ── IrEmitter ────────────────────────────────────────────────────────


def test_iremitter_empty_actions_emits_str_of_node():
    """Default IrEmit body wraps ``str(n)`` in IrLiteral."""
    out = IrEmitter().apply(IrLiteral("hi"))
    assert out == IrLiteral(str(IrLiteral("hi")))


def test_iremitter_irreturn_with_non_irliteral_value_reraises_past_apply():
    """``IrReturn`` carrying a non-IrLiteral payload doesn't satisfy
    the emitter's bound — it propagates past ``apply``."""

    def _raise(_d, _n, _nc):
        raise IrReturn[IrNode](IrRuleRef("not-a-literal"))

    e = IrEmitter(actions=(IrAction(IrLiteral, IrCallable[IrNode](_raise)),))
    with pytest.raises(IrReturn):
        e.apply(IrLiteral("x"))


def test_iremitter_with_strict_default_raises_on_unhandled_type():
    """Overriding ``default=IrRaise()`` opts back into strict refusal."""
    e = IrEmitter(
        actions=(IrAction(IrLiteral, IrLiteral("L")),),
        default=IrRaise(),
    )
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


# ── Dispatcher passed to action bodies ───────────────────────────────


def test_action_body_receives_dispatcher_as_first_arg():
    """``action.body.eval(self, node, new_children)`` — first arg is the dispatcher."""
    captured: list[IrDispatch] = []

    def _on(d, _n, _nc):
        captured.append(d)
        return IrNone

    d = IrVisitor(actions=(IrAction(IrLiteral, IrCallable[IrSelf](_on)),))
    d.apply(IrLiteral("a"))
    assert captured == [d]


# ── IrReturn() surfaces the matched node (find-first pattern) ─────────


def test_irvisitor_irreturn_surfaces_matched_node():
    """``IrAction(<type>, IrReturn())`` short-circuits the walk and surfaces the
    matched node itself through ``apply`` — the ``has_ruleref`` find-first
    pattern. ``IrReturn()`` defaults to ``IrThis``, which evaluates to ``n``.
    """
    visitor = IrVisitor(actions=(IrAction(IrRuleRef, IrReturn()),))
    tree = IrAlternation(IrSequence(IrItem(IrRuleRef("foo"))))
    assert visitor.apply(tree) == IrRuleRef("foo")


def test_irvisitor_irreturn_returns_irnone_when_no_match():
    """With no matching node the walk completes without short-circuiting and
    ``apply`` returns :data:`IrNone` (the IrWalk default result)."""
    visitor = IrVisitor(actions=(IrAction(IrRuleRef, IrReturn()),))
    tree = IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    assert visitor.apply(tree) is IrNone
