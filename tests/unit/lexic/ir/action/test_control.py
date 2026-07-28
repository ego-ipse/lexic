"""Tests for ``lexic.ir.action.control``."""

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLeaf
from lexic.ir.action.access import (
    IrArg,
    IrField,
)
from lexic.ir.action.control import (
    IrCond,
    IrEach,
    IrPass,
    IrPipe,
    IrReturn,
    IrThis,
    _Return,
)
from lexic.ir.grammar.nodes import (
    IrLiteral,
    IrQuantifier,
    IrRuleRef,
)
from lexic.ir.spine.records import IrTuple
from lexic.ir.spine.scalars import IrInt, IrStr
from lexic.ir.spine.spine import IrLambda, IrNode, IrNone


def test_return_inherits_base_exception_not_exception():
    """_Return inherits BaseException but not Exception so action bodies that
    wrap their work in ``except Exception:`` cannot swallow it."""
    assert issubclass(_Return, BaseException)
    assert not issubclass(_Return, Exception)


def test_return_carries_value():
    """_Return carries the value to surface to the dispatcher."""
    sig = _Return(value=42)
    assert sig.value == 42


def test_return_not_swallowed_by_except_exception():
    """_Return survives ``except Exception:`` inside a handler.

    Broad Exception is explicitly ignored by pylint for _Return BaseException.
    """

    def body_that_catches_exception(_d, _n, _nc):
        try:
            raise _Return(99)
        except Exception:  # pylint: disable=broad-exception-caught
            return IrStr("swallowed")

    op = IrLambda(body_that_catches_exception)
    with pytest.raises(_Return) as exc_info:
        op.eval(IrNone, IrNone, ())
    assert exc_info.value.value == 99


def test_ircond_evaluates_then_when_test_truthy():
    """IrCond picks then_op when the test node evals truthy."""
    node = IrQuantifier(lo=1, hi=1)
    op = IrCond[IrStr](
        test=IrField("lo", IrInt), then_op=IrLiteral("yes"), else_op=IrLiteral("no")
    )
    assert op.eval(IrNone, node, ()) == "yes"


def test_ircond_evaluates_else_when_test_falsy():
    """IrCond picks else_op when the test node evals falsy."""
    node = IrQuantifier(lo=0, hi=1)
    op = IrCond[IrStr](
        test=IrField("lo", IrInt), then_op=IrLiteral("yes"), else_op=IrLiteral("no")
    )
    assert op.eval(IrNone, node, ()) == "no"


def test_irthis_eval_returns_dispatched_node():
    """IrThis.eval returns the dispatched node ``n`` unchanged — the
    declarative ``lambda d, n, nc: n`` identity body."""
    n = IrRuleRef("term")
    assert IrThis().eval(IrNone, n, ()) is n


def test_irthis_is_plain_leaf_with_no_children():
    """IrThis is a plain IrLeaf body carrying no IR-node children."""
    assert isinstance(IrThis(), IrLeaf)
    assert not IrThis().children()


def test_irthis_call_is_identity_not_node():
    """IrThis inherits IrSelf.__call__ (returns the body itself); only ``eval``
    surfaces the dispatched node. The two must not be conflated."""
    t = IrThis()
    assert t(IrNone, IrLiteral("x"), ()) is t


def test_irpass_returns_irnone():
    """IrPass.eval returns IrNone without recursing."""
    assert IrPass().eval(IrNone, IrNone, ()) is IrNone


def test_irreturn_raises_self_and_is_node_and_exception():
    """IrReturn is an IrNode leaf and a BaseException; eval raises self."""
    r = IrReturn(IrLiteral("v"))
    assert isinstance(r, IrNode) and isinstance(r, BaseException)
    with pytest.raises(IrReturn):
        r.eval(IrNone, IrNone, ())


def test_irreturn_raises_return_with_value():
    """IrReturn raises _Return carrying self.value when evaluated."""
    r = IrReturn[IrStr](value=IrStr("done"))
    with pytest.raises(_Return) as exc_info:
        r.eval(IrNone, IrNone, ())
    assert exc_info.value.value == "done"


def test_irreturn_never_returns_normally():
    """IrReturn always raises — it never returns a value."""
    r = IrReturn[IrStr](value=IrStr("x"))
    with pytest.raises(_Return):
        r.eval(IrNone, IrNone, ())


def test_irreturn_defaults_to_dispatched_node():
    """``IrReturn()`` defaults its body to :class:`IrThis`, so evaluating it
    surfaces the dispatched node — the ``has_ruleref`` find-first pattern.

    The re-raised IrReturn carries the *evaluated* node, not the original
    body, so ``exc.value.value is n``.
    """
    n = IrRuleRef("term")
    with pytest.raises(IrReturn) as exc:
        IrReturn().eval(IrNone, n, ())
    assert exc.value.value is n


def test_irreturn_lazy_evaluates_irthis_body_against_context():
    """An explicit ``IrThis()`` body lazily evaluates to the dispatched node."""
    n = IrRuleRef("x")
    with pytest.raises(IrReturn) as exc:
        IrReturn(IrThis()).eval(IrNone, n, ())
    assert exc.value.value is n


def test_irreturn_lazy_evaluates_leaf_body_to_itself():
    """Under lazy_eval, a leaf body evaluates to itself (leaf eval is identity),
    so ``IrReturn(IrLiteral("v"))`` still surfaces ``IrLiteral("v")``."""
    with pytest.raises(IrReturn) as exc:
        IrReturn(IrLiteral("v")).eval(IrNone, IrNone, ())
    assert exc.value.value == IrLiteral("v")


def test_irreturn_non_lazy_carries_static_body_unevaluated():
    """``lazy_eval=False`` raises ``self`` carrying the body object as-is,
    without evaluating it against the dispatch context."""
    body = IrThis()
    r = IrReturn(body, lazy_eval=False)
    with pytest.raises(IrReturn) as exc:
        r.eval(IrNone, IrLiteral("x"), ())
    assert exc.value is r
    assert exc.value.value is body


def test_irreturn_non_irself_value_raises_self_unevaluated():
    """A non-IrSelf payload (e.g. a plain ``bool``) is never evaluated; eval
    raises ``self`` carrying that payload verbatim."""
    r = IrReturn(True)
    with pytest.raises(IrReturn) as exc:
        r.eval(IrNone, IrNone, ())
    assert exc.value is r
    assert exc.value.value is True


def test_irpipe_carries_nc_through_to_body():
    """IrPipe forwards nc to the body after rebinding the focus."""
    # body = IrArg(0) reads nc[0] using the shifted context
    nc = (IrLiteral("pass-through"),)
    result = IrPipe(IrThis(), IrArg(0)).eval(IrNone, IrNone, nc)
    assert result is nc[0]


def test_ireach_maps_body_over_tuple_elements():
    """IrEach(body) evaluates body once per element of a tuple-shaped focus."""
    focus = IrTuple(IrInt(1), IrInt(2), IrInt(3))
    result = IrEach(IrThis()).eval(IrNone, focus, ())
    assert result == IrTuple(IrInt(1), IrInt(2), IrInt(3))
    assert isinstance(result, IrTuple)


def test_ireach_maps_body_over_str_chars():
    """IrEach(body) lifts each character of a str-leaf focus to IrStr, then
    evaluates body against it."""
    result = IrEach(IrThis()).eval(IrNone, IrStr("ab"), ())
    assert result == IrTuple(IrStr("a"), IrStr("b"))


def test_ireach_empty_focus_yields_empty_tuple():
    """IrEach over an empty tuple/str focus yields an empty IrTuple."""
    assert IrEach(IrThis()).eval(IrNone, IrTuple(), ()) == IrTuple()
    assert IrEach(IrThis()).eval(IrNone, IrStr(""), ()) == IrTuple()


def test_ireach_non_iterable_focus_raises():
    """IrEach.eval raises UnsupportedConstructError on a non-iterable focus."""
    with pytest.raises(UnsupportedConstructError, match="no elements"):
        IrEach(IrThis()).eval(IrNone, IrInt(5), ())


def test_ireach_repr_is_codegen():
    """IrEach repr renders as a valid constructor expression."""
    assert repr(IrEach(IrThis())) == "IrEach(IrThis())"
