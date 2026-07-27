"""Tests for ``ir/walk.py`` — action-driven dispatcher on the IrSelf substrate.

The dispatcher is an :class:`~lexic.ir.base.IrCachingTuple` whose ``actions``
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
``actions`` is an :class:`~lexic.ir.mapping.IrTypeMap` of
:class:`~lexic.ir.action.IrAction` dyads; the matching body is resolved via
the map's concrete-first MRO lookup. When no action matches, the dispatcher
falls through to ``self.default``; when ``default`` is
:class:`~lexic.ir.action.IrRaise`, that raises
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

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.build import IrAction, IrEmit, IrRaise, IrRebuild
from lexic.ir.control import IrReturn
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.records import IrCachingTuple, IrSeq
from lexic.ir.spine import IrLambda, IrLeaf, IrNode, IrNone, IrSelf
from lexic.ir.walk import IrBottomUp, IrDispatch, IrEmitter, IrTransformer, IrVisitor

# ── Fixtures ─────────────────────────────────────────────────────────


def tiny_ast() -> IrAst:
    """Build a small AST for traversal tests.

    :returns: An IrAst with a single rule ``r`` referencing itself.
    """
    rule = IrRule(
        "r",
        IrAlternation(IrSequence(IrItem(atom=IrRuleRef("r")))),
    )
    return IrAst(rules=IrSeq(rule), start="r")


# ── IrDispatch fundamentals ──────────────────────────────────────────
def test_irdispatch_is_caching_tuple():
    """IrDispatch IS-AN IrCachingTuple; ``actions`` is an ``IrTypeMap``."""
    a = IrAction(IrLiteral, IrLiteral("x"))
    d = IrVisitor(
        actions=IrTypeMap(
            a,
        )
    )
    assert isinstance(d, IrCachingTuple)
    assert d.actions == IrTypeMap(a)
    assert not d.children()


def test_dispatch_resolves_action():
    """IrDispatch resolves the registered action and applies it."""
    d = IrDispatch(
        actions=IrTypeMap(
            IrAction(IrLiteral, IrEmit()),
        )
    )
    assert isinstance(d, IrCachingTuple)
    assert d.apply(IrLiteral("x")) == "x"


def test_dispatchers_with_equal_actions_compare_equal():
    """A dispatcher is an immutable value: equal action tables compare equal."""
    a = IrDispatch(actions=IrTypeMap())
    b = IrDispatch(actions=IrTypeMap())
    assert a == b


def test_irdispatch_apply_with_no_actions_invokes_preset_default():
    """``IrVisitor``'s preset default :class:`~lexic.ir.action.IrWalk`
    returns :data:`~lexic.ir.nodes.IrNone`."""
    assert IrVisitor().apply(IrLiteral("a")) is IrNone


def test_irdispatch_concrete_action_wins_over_abstract():
    """A concrete-type action wins over an IrLeaf/IrNode-keyed catch-all."""
    seen: list[str] = []
    leaf_action = IrAction(
        IrLeaf, IrLambda(lambda _d, _n, _nc: seen.append("leaf") or IrNone)
    )
    lit_action = IrAction(
        IrLiteral, IrLambda(lambda _d, _n, _nc: seen.append("lit") or IrNone)
    )
    IrVisitor(actions=IrTypeMap(leaf_action, lit_action)).apply(IrLiteral("x"))
    assert seen == ["lit"]


def test_irdispatch_falls_through_to_abstract_action_when_no_concrete_match():
    """An IrLeaf-keyed action catches IrRuleRef (which IS-A IrLeaf)."""
    seen: list[str] = []
    leaf_action = IrAction(
        IrLeaf, IrLambda(lambda _d, _n, _nc: seen.append("leaf") or IrNone)
    )
    IrVisitor(
        actions=IrTypeMap(
            leaf_action,
        )
    ).apply(IrRuleRef("r"))
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

    d = IrVisitor(
        actions=IrTypeMap(
            IrAction(IrNode, IrLambda(_on)),
        )
    )
    d.apply(tiny_ast())
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

    d = IrVisitor(
        actions=IrTypeMap(
            IrAction(IrItem, IrLambda(_on)),
        )
    )
    item = IrItem(atom=IrLiteral("x"))
    pre = IrSeq(IrLiteral("PRE"), IrLiteral("Q"))
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
        rules=IrSeq(
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
        actions=IrTypeMap(
            IrAction(IrRuleRef, IrLambda(_on_ref)),
            IrAction(IrNode, IrLambda(_walk)),
        )
    )
    assert d.apply(ast) is IrNone
    assert visit_count == 1


def test_irreturn_value_returned_when_satisfies_bound():
    """``IrReturn`` whose ``.value`` satisfies the dispatcher's bound is
    returned as the dispatched value."""
    d = IrVisitor(
        actions=IrTypeMap(
            IrAction(IrRuleRef, IrReturn[IrSelf](IrNone)),
        )
    )
    assert d.apply(IrRuleRef("x")) is IrNone


# ── Resolve cache (observable) ───────────────────────────────────────


def test_repeated_dispatch_does_not_rebuild_action_table():
    """Cache hit: repeated apply on same root type produces consistent
    behaviour with no observable re-resolution side effects."""
    resolve_calls: list[type] = []

    def _on(_d, n, _nc):
        resolve_calls.append(type(n))
        return IrNone

    d = IrVisitor(
        actions=IrTypeMap(
            IrAction(IrLiteral, IrLambda(_on)),
        )
    )
    d.apply(IrLiteral("a"))
    d.apply(IrLiteral("b"))
    d.apply(IrLiteral("c"))
    assert resolve_calls == [IrLiteral, IrLiteral, IrLiteral]


def test_dispatcher_is_frozen_actions_immutable():
    """Immutable tuple record: the actions accessor is read-only (no setter)."""
    d = IrVisitor()
    with pytest.raises(AttributeError):
        setattr(d, "actions", ())


# ── IrVisitor ────────────────────────────────────────────────────────


def test_irvisitor_empty_actions_returns_irnone():
    """IrVisitor with no user actions walks via IrWalk and returns IrNone."""
    assert IrVisitor().apply(IrLiteral("a")) is IrNone
    assert IrVisitor().apply(tiny_ast()) is IrNone


def test_irvisitor_default_walks_into_children():
    """The default IrWalk body recurses into every child node."""
    visited: list[type] = []

    def _record(_d, n, _nc):
        visited.append(type(n))
        return IrNone

    d = IrVisitor(
        actions=IrTypeMap(
            IrAction(IrLiteral, IrLambda(_record)),
        )
    )
    ast = IrAst(
        rules=IrSeq(
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
        actions=IrTypeMap(
            IrAction(IrLiteral, IrLambda(_swap)),
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

    e = IrEmitter(
        actions=IrTypeMap(
            IrAction(IrLiteral, IrLambda(_raise)),
        )
    )
    with pytest.raises(IrReturn):
        e.apply(IrLiteral("x"))


def test_iremitter_with_strict_default_raises_on_unhandled_type():
    """Overriding ``default=IrRaise()`` opts back into strict refusal."""
    e = IrEmitter(
        actions=IrTypeMap(
            IrAction(IrLiteral, IrLiteral("L")),
        ),
        default=IrRaise(),
    )
    with pytest.raises(UnsupportedConstructError):
        e.apply(IrRuleRef("x"))


def test_iremitter_action_on_irnode_acts_as_per_instance_default():
    """User-supplied IrAction(IrNode, ...) catches everything; preset default never fires."""
    e = IrEmitter(
        actions=IrTypeMap(
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

    d = IrVisitor(
        actions=IrTypeMap(
            IrAction(IrLiteral, IrLambda(_on)),
        )
    )
    d.apply(IrLiteral("a"))
    assert captured == [d]


# ── IrReturn() surfaces the matched node (find-first pattern) ─────────


def test_irvisitor_irreturn_surfaces_matched_node():
    """``IrAction(<type>, IrReturn())`` short-circuits the walk and surfaces the
    matched node itself through ``apply`` — the ``has_ruleref`` find-first
    pattern. ``IrReturn()`` defaults to ``IrThis``, which evaluates to ``n``.
    """
    visitor = IrVisitor(
        actions=IrTypeMap(
            IrAction(IrRuleRef, IrReturn()),
        )
    )
    tree = IrAlternation(IrSequence(IrItem(IrRuleRef("foo"))))
    assert visitor.apply(tree) == IrRuleRef("foo")


def test_irvisitor_irreturn_returns_irnone_when_no_match():
    """With no matching node the walk completes without short-circuiting and
    ``apply`` returns :data:`IrNone` (the IrWalk default result)."""
    visitor = IrVisitor(
        actions=IrTypeMap(
            IrAction(IrRuleRef, IrReturn()),
        )
    )
    tree = IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    assert visitor.apply(tree) is IrNone


# ── IrBottomUp ───────────────────────────────────────────────────────


def deep_alternation(depth: int) -> IrAlternation:
    """``depth`` nested single-arm groups around a lone ``"a"`` literal."""
    node = IrAlternation(IrSequence(IrItem(IrLiteral("a"))))
    for _ in range(depth):
        node = IrAlternation(IrSequence(IrItem(node)))
    return node


def test_irbottomup_empty_actions_is_identity():
    """With no user actions the driver's rebuild IS the transform."""
    seq = IrSequence(IrItem(IrLiteral("a")), IrItem(IrRuleRef("r")))
    assert IrBottomUp().apply(seq) == seq


def test_irbottomup_body_sees_transformed_children():
    """A body runs on a node whose children are already in final form."""

    def _swap(_d, _n, _nc):
        return IrLiteral("Z")

    seen: list[IrItem] = []

    def _record(_d, n, _nc):
        seen.append(n)
        return n

    t = IrBottomUp(
        actions=IrTypeMap(
            IrAction(IrLiteral, IrLambda(_swap)),
            IrAction(IrItem, IrLambda(_record)),
        )
    )
    out = t.apply(IrItem(atom=IrLiteral("a")))
    assert isinstance(out, IrItem)
    assert out.atom == IrLiteral("Z")
    assert seen == [out]  # the recorded item already carried the swapped atom


def test_irbottomup_transformed_children_ride_the_nc_channel():
    """Bodies may read the transformed children off ``nc`` directly."""
    captured: list[tuple[IrSelf, ...]] = []

    def _capture(_d, n, nc):
        captured.append(tuple(nc))
        return n

    t = IrBottomUp(actions=IrTypeMap(IrAction(IrSequence, IrLambda(_capture))))
    t.apply(IrSequence(IrItem(IrLiteral("a"))))
    assert captured == [(IrItem(IrLiteral("a")),)]


def test_irbottomup_deep_tree_does_not_overflow():
    """A 2000-level nesting transforms without RecursionError.

    The recursive :class:`IrTransformer` overflows here at a few hundred
    levels; the explicit-stack driver is depth-independent.
    """
    deep = deep_alternation(2000)
    out = IrBottomUp().apply(deep)
    assert out == deep


def test_irbottomup_shared_subtree_transforms_once():
    """One object reachable twice is transformed once, spliced everywhere."""
    calls: list[IrSelf] = []

    def _count(_d, n, _nc):
        calls.append(n)
        return n

    t = IrBottomUp(actions=IrTypeMap(IrAction(IrLiteral, IrLambda(_count))))
    shared = IrItem(IrLiteral("s"))
    seq = IrSequence(shared, shared)
    out = t.apply(seq)
    assert out == seq
    assert len(calls) == 1


def test_irbottomup_irreturn_short_circuits():
    """An :class:`IrReturn` body unwinds through the iterative driver too."""
    t = IrBottomUp(actions=IrTypeMap(IrAction(IrRuleRef, IrReturn())))
    tree = IrAlternation(IrSequence(IrItem(IrRuleRef("hit")), IrItem(IrLiteral("x"))))
    assert t.apply(tree) == IrRuleRef("hit")


# ── IrBottomUp._descend seam (opaque-subtree fencing) ───────────────────


def _rewrite_charclass_to(text: str):
    """A body that rewrites any dispatched char class to ``IrLiteral(text)``."""
    return IrLambda(lambda _d, _n, _nc: IrLiteral(text))


def test_bottomup_descend_seam_fences_a_subtree():
    """Overriding ``_descend`` to return () leaves that node's subtree verbatim."""

    class _Fenced(IrBottomUp):
        def _descend(self, node):
            return () if isinstance(node, IrItem) else tuple(node.children())

    driver = _Fenced(
        actions=IrTypeMap(IrAction(IrCharClass, _rewrite_charclass_to("REWRITTEN")))
    )
    # the char class sits UNDER an IrItem, which the driver fences → not rewritten
    tree = IrSequence(IrItem(IrCharClass(IrChr(65))))
    assert driver.apply(tree) == tree


def test_bottomup_default_descend_reaches_every_node():
    """Without an override, ``_descend`` recurses fully (the char class rewrites)."""
    driver = IrBottomUp(
        actions=IrTypeMap(IrAction(IrCharClass, _rewrite_charclass_to("X")))
    )
    tree = IrSequence(IrItem(IrCharClass(IrChr(65))))
    assert driver.apply(tree) == IrSequence(IrItem(IrLiteral("X")))
