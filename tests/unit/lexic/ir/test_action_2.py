"""Tests for ir/action_2.py — action-algebra nodes built on the IrSelf substrate.

Action algebra uses ``.eval(d, n, nc)`` to produce typed values.
``__call__(d, n, nc)`` remains identity-shaped (returns self) via
:class:`~lexic.ir.nodes_2.IrSelf`.
"""

import pytest

from lexic.ir.action_2 import (
    IrAction,
    IrCallable,
    IrChild,
    IrChildren,
    IrConcat,
    IrCond,
    IrEmit,
    IrField,
    IrJoin,
    IrLeaf,
    IrPass,
    IrRaise,
    IrRebuild,
    IrReturn,
    IrWalk,
    _Return,
)
from lexic.ir.nodes_2 import (
    IrComposite,
    IrItem,
    IrLiteral,
    IrNone,
    IrQuantifier,
    IrSelf,
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
    """IrField returns the attribute value wrapped in IrStr.

    IrRuleRef IS-A str — the node itself is the payload; there is no ``.value``
    field. IrField reads a named attribute of a composite node.  Here we read
    ``name`` from an :class:`~lexic.ir.nodes_2.IrRule`.
    """
    from lexic.ir.nodes_2 import IrAlternation, IrRule

    rule = IrRule("greet", IrAlternation())
    out = IrField("name").eval(IrNone, rule, ())
    assert out == "greet" and isinstance(out, IrStr)


def test_irfield_reads_scalar_and_wraps_to_irstr():
    """IrField reads a named attribute and wraps the result via bound (IrStr)."""
    from lexic.ir.nodes_2 import IrAlternation, IrRule

    rule = IrRule("greet", IrAlternation())
    out = IrField("name").eval(IrNone, rule, ())
    assert out == "greet" and isinstance(out, IrStr)


def test_irfield_is_composite_no_children():
    """IrField is an IrComposite record-leaf with no IR-node children."""
    assert isinstance(IrField("x"), IrComposite)
    assert IrField("x").children() == ()


def test_irfield_reads_charclass_pattern():
    """IrField reads any string attribute of a composite node."""
    from lexic.ir.nodes_2 import IrAlternation, IrRule

    rule = IrRule("r", IrAlternation())
    # Confirm the read attribute is a plain str that wraps to IrStr
    assert IrField("name").eval(IrNone, rule, ()) == "r"


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
            IrStr("c"),
        ),
    )
    assert result == "ok"
    assert received == [(IrNone, IrNone, ("c",))]


def test_ircallable_repr_contains_handler_name():
    """``repr(IrCallable)`` contains the handler's ``__name__`` for debug output.

    In the primitive-node model, ``IrCallable`` uses ``IrComposite.__repr__``
    (``repr=False`` dataclass, field rendered as ``handler=<...>``).
    The old ``CALLABLE(<name>)`` str was specific to the original action.py's
    custom ``__str__``; action_2.py uses the generic composite repr instead.
    """

    def my_handler(_d, _n, _nc):
        return IrStr()

    assert "my_handler" in repr(IrCallable[IrStr](my_handler))


def test_ircallable_repr_fallback_for_lambda():
    """Lambdas appear in ``repr(IrCallable)``; rendering never crashes."""
    assert "lambda" in repr(IrCallable[IrStr](lambda _d, _n, _nc: IrStr()))


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
        IrChild[IrStr]("nonexistent").eval(
            IrNone, item, IrTuple(IrStr("a"), IrStr("b"))
        )


# ── IrChildren ───────────────────────────────────────────────────────
# NOTE: test_irchildren_raises_when_items_attr_mismatches REMOVED.
# IrChildren no longer takes a name argument (R2 decision: _items_attr /
# IrCollection removed; IrChildren reads n.children() regardless). The
# old test exercised name-mismatch ValueError on a deleted API.


def test_irchildren_returns_full_new_children_tuple():
    """IrChildren() returns new_children for a node with children.

    IrChildren carries no name argument in the new model (R2).
    """
    seq = IrSequence(IrItem(IrLiteral("a")))
    new_children = IrTuple(IrStr("result_a"))
    result = IrChildren[IrStr]().eval(IrNone, seq, new_children)
    assert result == ("result_a",)


# ── IrConcat ─────────────────────────────────────────────────────────


def test_irconcat_joins_parts_in_order():
    """IrConcat evaluates parts and concatenates results."""
    op = IrConcat(parts=IrTuple(IrLiteral('"'), IrLiteral("x"), IrLiteral('"')))
    assert op.eval(IrNone, IrNone, ()) == '"x"'


def test_irconcat_empty_parts_returns_empty_string():
    """IrConcat with no parts returns empty string."""
    assert IrConcat().eval(IrNone, IrNone, ()) == ""


def test_concat_joins_parts():
    """IrConcat is an IrComposite; evaluates parts and concatenates."""
    c = IrConcat(parts=IrTuple(IrLiteral("a"), IrLiteral("b")))
    assert isinstance(c, IrComposite)
    out = c.eval(IrNone, IrNone, ())
    assert out == "ab" and isinstance(out, IrStr)


# ── IrJoin ───────────────────────────────────────────────────────────


def test_irjoin_joins_items_with_separator():
    """IrJoin evaluates parts and joins results with separator."""
    op = IrJoin(
        parts=IrTuple(IrLiteral("a"), IrLiteral("b"), IrLiteral("c")),
        separator=IrLiteral(" | "),
        empty=IrLiteral(""),
    )
    assert op.eval(IrNone, IrNone, ()) == "a | b | c"


def test_irjoin_returns_empty_value_when_no_items():
    """IrJoin returns empty when parts is empty."""
    op = IrJoin(
        parts=IrTuple(),
        separator=IrLiteral(" | "),
        empty=IrLiteral("<empty>"),
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


# ── Default bodies (Tasks 7 contract tests) ──────────────────────────


def test_default_bodies_are_plain_leaves():
    """IrPass, IrWalk, IrEmit, IrRebuild are all IrLeaf instances."""
    for body in (IrPass(), IrWalk(), IrEmit(), IrRebuild()):
        assert isinstance(body, IrLeaf)


def test_irpass_returns_irnone():
    """IrPass.eval returns IrNone without recursing."""
    assert IrPass().eval(IrNone, IrNone, ()) is IrNone


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


def test_irreturn_raises_self_and_is_composite():
    """IrReturn is an IrComposite and a BaseException; eval raises self."""
    r = IrReturn(IrLiteral("v"))
    assert isinstance(r, IrComposite) and isinstance(r, BaseException)
    with pytest.raises(IrReturn):
        r.eval(IrNone, IrNone, ())


def test_iraction_delegates_to_body():
    """IrAction.eval delegates to body.eval."""
    a = IrAction(IrLiteral, IrEmit())
    assert a.target_type is IrLiteral


# ── IrReturn ─────────────────────────────────────────────────────────


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
    op = IrConcat(parts=IrTuple(IrLiteral("x")))
    assert op(IrNone, IrNone, ()) is op


# ── IrRaise ───────────────────────────────────────────────────────────


def test_irraise_raises_unsupported_construct_error_by_default():
    """IrRaise.eval raises UnsupportedConstructError by default."""
    from lexic.exceptions import UnsupportedConstructError

    with pytest.raises(UnsupportedConstructError):
        IrRaise().eval(IrNone, IrLiteral("x"), ())
