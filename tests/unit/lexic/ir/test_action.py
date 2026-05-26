"""Tests for ir/action.py — action-algebra nodes built on the IrSelf substrate.

Action algebra uses ``.eval(d, n, nc)`` to produce typed values.
``__call__(d, n, nc)`` remains identity-shaped (returns self) via
:class:`IrSelf`.
"""

import pytest

from lexic.ir.action import (
    IrAction,
    IrCallable,
    IrChild,
    IrChildren,
    IrConcat,
    IrCond,
    IrField,
    IrJoin,
    IrReturn,
    _Return,
)
from lexic.ir.nodes import (
    IrCharClass,
    IrItem,
    IrLiteral,
    IrNone,
    IrQuantifier,
    IrRuleRef,
    IrSequence,
    IrStr,
    IrTuple,
)

# ── _Return ──────────────────────────────────────────────────────────


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

    op = IrCallable[IrStr](body_that_catches_exception)
    with pytest.raises(_Return) as exc_info:
        op.eval(IrNone, IrNone, ())
    assert exc_info.value.value == 99


# ── IrField ──────────────────────────────────────────────────────────


def test_irfield_reads_string_attribute():
    """IrField returns the attribute value (assumed to be ``Ir_co``-typed)."""
    node = IrRuleRef("my_rule")
    assert IrField("value").eval(IrNone, node, ()) == "my_rule"


def test_irfield_reads_charclass_pattern():
    """IrField reads any string attribute, not just ``value``."""
    node = IrCharClass("a-z")
    assert IrField("value").eval(IrNone, node, ()) == "a-z"


# ── IrCallable ───────────────────────────────────────────────────────


def test_ircallable_invokes_handler_with_all_args():
    """IrCallable forwards (d, n, nc) to the handler."""
    received: list[tuple] = []

    def handler(d, n, nc):
        received.append((d, n, nc))
        return IrStr("ok")

    result = IrCallable[IrStr](handler).eval(
        IrNone,
        IrNone,
        IrTuple(
            "c",
        ),
    )
    assert result == "ok"
    assert received == [(IrNone, IrNone, ("c",))]


def test_ircallable_str_uses_handler_name():
    """``str(IrCallable)`` reflects the handler's ``__name__`` for debug output."""

    def my_handler(_d, _n, _nc):
        return IrStr()

    assert str(IrCallable[IrStr](my_handler)) == "CALLABLE(<my_handler>)"


def test_ircallable_str_fallback_for_lambda():
    """Lambdas have ``__name__ == '<lambda>'``; ``str`` still renders."""
    assert "<" in str(IrCallable[IrStr](lambda _d, _n, _nc: IrStr()))


# ── IrChild ──────────────────────────────────────────────────────────


def test_irchild_reads_dispatched_child_by_name():
    """IrChild("atom") returns new_children[0] for an IrItem
    (_child_attrs=("atom","quantifier"))."""
    item = IrItem(atom=IrLiteral("x"))
    new_children = (IrStr("dispatched_atom"), IrStr("dispatched_quantifier"))
    result = IrChild[IrStr]("atom").eval(IrNone, item, new_children)
    assert result == "dispatched_atom"


def test_irchild_reads_second_child():
    """IrChild("quantifier") returns new_children[1] for an IrItem."""
    item = IrItem(atom=IrLiteral("x"))
    new_children = IrTuple(IrStr("dispatched_atom"), IrStr("dispatched_quantifier"))
    result = IrChild[IrStr]("quantifier").eval(IrNone, item, new_children)
    assert result == "dispatched_quantifier"


def test_irchild_raises_on_unknown_name():
    """IrChild raises ValueError when the name is not in _child_attrs."""
    item = IrItem(atom=IrLiteral("x"))
    with pytest.raises(ValueError, match="no such child"):
        IrChild[IrStr]("nonexistent").eval(IrNone, item, IrTuple("a", "b"))


# ── IrChildren ───────────────────────────────────────────────────────


def test_irchildren_returns_full_new_children_tuple():
    """IrChildren("items") returns new_children for a node whose
    _items_attr is "items"."""
    seq = IrSequence(
        items=IrTuple(
            IrItem(IrLiteral("a")),
        )
    )
    new_children = IrTuple("result_a")
    result = IrChildren[IrStr]("items").eval(IrNone, seq, new_children)
    assert result == ("result_a",)


def test_irchildren_raises_when_items_attr_mismatches():
    """IrChildren raises ValueError when the name doesn't match _items_attr."""
    seq = IrSequence(items=IrTuple())
    with pytest.raises(ValueError, match="_items_attr"):
        IrChildren[IrStr]("arms").eval(IrNone, seq, ())


# ── IrConcat ─────────────────────────────────────────────────────────


def test_irconcat_joins_parts_in_order():
    """IrConcat evaluates parts and concatenates results."""
    op = IrConcat(
        parts=IrTuple(
            IrLiteral(IrStr('"')), IrLiteral(IrStr("x")), IrLiteral(IrStr('"'))
        )
    )
    assert op.eval(IrNone, IrNone, ()) == '"x"'


def test_irconcat_empty_parts_returns_empty_string():
    """IrConcat with no parts returns empty string."""
    assert IrConcat().eval(IrNone, IrNone, ()) == ""


# ── IrJoin ───────────────────────────────────────────────────────────


def test_irjoin_joins_items_with_separator():
    """IrJoin evaluates parts and joins results with separator.value."""
    op = IrJoin(
        parts=IrTuple(
            IrLiteral(IrStr("a")), IrLiteral(IrStr("b")), IrLiteral(IrStr("c"))
        ),
        separator=IrLiteral(IrStr(" | ")),
        empty=IrLiteral(IrStr("")),
    )
    assert op.eval(IrNone, IrNone, ()) == "a | b | c"


def test_irjoin_returns_empty_value_when_no_items():
    """IrJoin returns empty.value when parts is empty."""
    op = IrJoin(
        parts=IrTuple(),
        separator=IrLiteral(IrStr(" | ")),
        empty=IrLiteral(IrStr("<empty>")),
    )
    assert op.eval(IrNone, IrNone, ()) == "<empty>"


# ── IrCond ───────────────────────────────────────────────────────────


def test_ircond_evaluates_then_when_truthy():
    """IrCond picks then_op when getattr(n, field) is truthy."""
    node = IrQuantifier(min=1, max=1)
    op = IrCond[IrStr](field="min", then_op=IrLiteral("yes"), else_op=IrLiteral("no"))
    assert op.eval(IrNone, node, ()) == "yes"


def test_ircond_evaluates_else_when_falsy():
    """IrCond picks else_op when getattr(n, field) is falsy."""
    node = IrQuantifier(min=0, max=1)
    op = IrCond[IrStr](field="min", then_op=IrLiteral("yes"), else_op=IrLiteral("no"))
    assert op.eval(IrNone, node, ()) == "no"


# ── IrReturn ─────────────────────────────────────────────────────────


def test_irreturn_raises_return_with_value():
    """IrReturn raises _Return carrying self.value when evaluated."""
    r = IrReturn[IrStr](value=IrStr("done"))
    with pytest.raises(_Return) as exc_info:
        r.eval(IrNone, IrNone, ())
    assert exc_info.value.value == "done"


def test_irreturn_never_returns_normally():
    """IrReturn always raises — it never returns a value."""
    r = IrReturn[int](value=42)
    with pytest.raises(_Return):
        r.eval(IrNone, IrNone, ())


# ── IrAction ─────────────────────────────────────────────────────────


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


# ── __call__ identity (substrate sanity) ──────────────────────────────


def test_action_call_is_identity():
    """Action algebra inherits IrSelf's __call__ → returns self.
    Typed value extraction is .eval(); __call__ is for identity."""
    op = IrConcat(parts=IrTuple(IrLiteral(IrStr("x"))))
    assert op(IrNone, IrNone, ()) is op
