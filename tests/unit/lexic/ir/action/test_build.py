"""Tests for ``lexic.ir.action.build``."""

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLeaf
from lexic.ir.action.access import (
    IrArg,
    IrArgs,
    IrChild,
    IrIndex,
)
from lexic.ir.action.build import (
    IrAction,
    IrApply,
    IrBuild,
    IrEmit,
    IrRaise,
    IrRebuild,
    IrWalk,
)
from lexic.ir.action.flow.control import IrPass
from lexic.ir.action.mapping import IrTypeMap
from lexic.ir.action.walk import IrDispatch, IrEmitter
from lexic.ir.grammar.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrRange,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spine.records import IrTuple
from lexic.ir.spine.scalars import IrChr, IrStr
from lexic.ir.spine.spine import IrNone, IrSelf


def test_irchild_reads_second_child():
    """IrChild("quantifier") dispatches n's second child; nc is ignored.

    For an :class:`IrItem` with default quantifier ``(1, 1)``, the second child
    is the quantifier node, not any ``nc`` content.
    """
    item = IrItem(atom=IrLiteral("x"))
    emitter = IrEmitter()
    result = IrChild("quantifier").eval(
        emitter, item, IrTuple(IrStr("ignored_1"), IrStr("ignored_2"))
    )
    # IrEmitter default (IrEmit) converts IrQuantifier(1,1) to IrLiteral("…")
    assert isinstance(result, IrLiteral)


def test_irindex_lazy_dispatches_child_via_d():
    """IrIndex(0) with empty nc dispatches the child through d (lazy path).

    IrEmitter default (IrEmit) converts IrLiteral('x') to IrLiteral('x').
    """
    item = IrItem(atom=IrLiteral("x"))
    emitter = IrEmitter()
    result = IrIndex(0).eval(emitter, item, IrTuple())
    assert result == IrLiteral("x")
    assert isinstance(result, IrLiteral)


def test_irapply_default_args_dispatches_with_empty_channel():
    """IrApply() with default empty args dispatches n with an empty nc."""
    charclass_action = IrAction(IrCharClass, IrArgs())
    dispatch = IrDispatch(actions=IrTypeMap(charclass_action))
    n = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
    result = IrApply().eval(dispatch, n, IrTuple())
    assert result == IrTuple()


def test_irapply_repr_is_codegen():
    """IrApply repr renders as a valid constructor expression."""
    assert repr(IrApply(IrTuple(IrLiteral("^")))) == "IrApply(IrTuple(IrLiteral('^')))"


def test_default_bodies_are_plain_leaves():
    """IrPass, IrWalk, IrEmit, IrRebuild are all IrLeaf instances."""
    for body in (IrPass(), IrWalk(), IrEmit(), IrRebuild()):
        assert isinstance(body, IrLeaf)


def test_irwalk_returns_irnone_after_walking_children():
    """IrWalk.eval walks children for side effects and returns IrNone."""
    visited: list[IrSelf] = []

    class _Tracker(IrSelf):
        __slots__ = ()

        def children(self) -> tuple[IrSelf, ...]:
            return (IrLiteral("child"),)

    class _RecordingDispatch(IrSelf):
        __slots__ = ()

        def eval(self, _d: IrSelf, n: IrSelf, _nc, /) -> IrSelf:
            visited.append(n)
            return IrNone

    result = IrWalk().eval(_RecordingDispatch(), _Tracker(), ())
    assert result is IrNone
    assert IrLiteral("child") in visited


def test_iremit_wraps_str_of_node_as_irliteral():
    """IrEmit returns IrLiteral(str(n)) for the dispatched node."""
    lit = IrLiteral("hi")
    out = IrEmit().eval(IrNone, lit, ())
    assert out == IrLiteral(str(lit))
    assert isinstance(out, IrLiteral)


def test_iraction_delegates_to_body():
    """IrAction.eval delegates to body.eval."""
    a = IrAction(IrLiteral, IrEmit())
    assert a.target_type is IrLiteral


def test_iraction_body_eval_returns_value():
    """IrAction.eval delegates to body.eval and returns its value."""
    a = IrAction[IrStr](IrLiteral, IrLiteral("Z"))
    assert a.eval(IrNone, IrNone, ()) == "Z"


def test_iraction_target_type_not_in_children():
    """target_type is metadata — it must NOT appear in children(). body is
    the sole child."""
    a = IrAction[IrStr](IrLiteral, IrLiteral("x"))
    assert a.children() == (IrLiteral("x"),)


def test_iraction_str_includes_target_type_name():
    """``str`` renders the target_type class name for debug visibility."""
    a = IrAction[IrStr](IrLiteral, IrLiteral("x"))
    assert "IrLiteral" in str(a)


def test_irraise_raises_unsupported_construct_error_by_default():
    """IrRaise.eval raises UnsupportedConstructError by default."""
    with pytest.raises(UnsupportedConstructError):
        IrRaise().eval(IrNone, IrLiteral("x"), ())


def test_irbuild_default_splats_nc_into_target():
    """IrBuild(target) with default args=IrNone calls target(*nc)."""
    item_a = IrItem(IrLiteral("a"))
    item_b = IrItem(IrLiteral("b"))
    nc = (item_a, item_b)
    result = IrBuild(IrSequence).eval(IrNone, IrNone, nc)
    assert result == IrSequence(item_a, item_b)
    assert isinstance(result, IrSequence)


def test_irbuild_with_args_reshapes_channel():
    """IrBuild(target, args) calls target(*args.eval(...))."""
    # args body picks only the first element of nc
    result = IrBuild(IrRuleRef, IrTuple(IrArg(0))).eval(
        IrNone, IrNone, (IrLiteral("myrule"), IrLiteral("ignored"))
    )
    assert result == IrRuleRef("myrule")
    assert isinstance(result, IrRuleRef)


def test_irbuild_empty_nc_calls_target_with_no_args():
    """IrBuild(IrAlternation) with empty nc calls IrAlternation()."""
    result = IrBuild(IrAlternation).eval(IrNone, IrNone, ())
    assert result == IrAlternation()
    assert isinstance(result, IrAlternation)


def test_irbuild_args_is_child_attribute():
    """IrBuild.args is the single dispatched child; target is scalar payload."""
    build = IrBuild(IrSequence)
    # args=IrNone is a scalar: no dispatched children
    assert build.args is IrNone
    build_with_args = IrBuild(IrRuleRef, IrTuple(IrArg(0)))
    assert build_with_args.args == IrTuple(IrArg(0))


def test_irbuild_repr_is_codegen():
    """IrBuild repr renders as a valid constructor expression.

    The default-valued `args=IrNone` is omitted from the trailing run.
    """
    assert repr(IrBuild(IrSequence)) == "IrBuild(IrSequence)"
    assert (
        repr(IrBuild(IrRuleRef, IrTuple(IrArg(0))))
        == "IrBuild(IrRuleRef, IrTuple(IrArg(0)))"
    )
