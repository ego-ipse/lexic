"""Tests for ir/action.py — action-algebra nodes built on the IrSelf substrate.

Action algebra uses ``.eval(d, n, nc)`` to produce typed values.
``__call__(d, n, nc)`` remains identity-shaped (returns self) via
:class:`~lexic.ir.nodes.IrSelf`.
"""

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import (
    IrAction,
    IrChild,
    IrChildren,
    IrCompare,
    IrConcat,
    IrCond,
    IrEmit,
    IrField,
    IrJoin,
    IrLeaf,
    IrOp,
    IrPass,
    IrRaise,
    IrRebuild,
    IrReturn,
    IrThis,
    IrWalk,
    _Return,
)
from lexic.ir.base import (
    IrCallable,
    IrInt,
    IrNamedTuple,
    IrNode,
    IrNone,
    IrSelf,
    IrStr,
    IrTuple,
)
from lexic.ir.nodes import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
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

    op = IrCallable[IrSelf, IrStr](body_that_catches_exception)
    with pytest.raises(_Return) as exc_info:
        op.eval(IrNone, IrNone, ())
    assert exc_info.value.value == 99


# ── IrField ──────────────────────────────────────────────────────────


def test_irfield_reads_string_attribute():
    """IrField returns the attribute value wrapped in IrStr.

    IrRuleRef IS-A str — the node itself is the payload; there is no ``.value``
    field. IrField reads a named attribute of a composite node.  Here we read
    ``name`` from an :class:`~lexic.ir.nodes.IrRule`.
    """
    rule = IrRule("greet", IrAlternation())
    out = IrField("name").eval(IrNone, rule, ())
    assert out == "greet" and isinstance(out, IrStr)


def test_irfield_reads_scalar_and_wraps_to_irstr():
    """IrField reads a named attribute and wraps the result via bound (IrStr)."""
    rule = IrRule("greet", IrAlternation())
    out = IrField("name").eval(IrNone, rule, ())
    assert out == "greet" and isinstance(out, IrStr)


def test_irfield_is_composite_no_children():
    """IrField is an IrNamedTuple record-leaf with no IR-node children."""
    assert isinstance(IrField("x"), IrNamedTuple)
    assert not IrField("x").children()


def test_irfield_reads_charclass_pattern():
    """IrField reads any string attribute of a composite node."""
    rule = IrRule("r", IrAlternation())
    # Confirm the read attribute is a plain str that wraps to IrStr
    assert IrField("name").eval(IrNone, rule, ()) == "r"


def test_irfield_repr_is_valid_codegen():
    """IrField repr renders the class-valued `out` as a bare name (eval round-trips)."""
    assert repr(IrField("min", IrInt)) == "IrField('min', IrInt)"
    assert repr(IrField("name")) == "IrField('name', IrStr)"


def test_irfield_out_irint_reads_int_without_stringifying():
    """IrField('min', IrInt) reads an int attribute and wraps it as IrInt."""
    q = IrQuantifier(min=3, max=5)
    result = IrField("min", IrInt).eval(IrNone, q, ())
    assert result == 3
    assert isinstance(result, IrInt)


# ── IrOp / IrCompare ──────────────────────────────────────────────────


def test_irop_is_a_str_leaf():
    """IrOp is its operator string — a plain IrStr leaf, no enum."""
    assert IrOp(">") == ">"
    assert isinstance(IrOp(">"), IrStr)


def test_irop_eval_applies_operator_to_nc_operands():
    """IrOp.eval applies the mapped builtin to the operands handed in as nc."""
    assert IrOp(">").eval(IrNone, IrNone, (IrInt(2), IrInt(1))) == 1
    assert IrOp("<").eval(IrNone, IrNone, (IrInt(2), IrInt(1))) == 0
    result = IrOp("==").eval(IrNone, IrNone, (IrInt(1), IrInt(1)))
    assert result == 1
    assert isinstance(result, IrInt)


def test_irop_unknown_operator_raises_unsupported():
    """An operator string not in ``_OPS`` misses the map — :exc:`IrKeyError`,
    which IS-A ``UnsupportedConstructError``."""
    with pytest.raises(UnsupportedConstructError):
        IrOp("!=").eval(IrNone, IrNone, (IrInt(1), IrInt(1)))


def test_ircompare_eq_true_returns_irint_one():
    """A satisfied comparison evaluates to IrInt(1)."""
    result = IrCompare(IrInt(1), IrOp("=="), IrInt(1)).eval(IrNone, IrNone, ())
    assert result == 1
    assert isinstance(result, IrInt)


def test_ircompare_eq_false_returns_irint_zero():
    """An unsatisfied comparison evaluates to IrInt(0)."""
    assert IrCompare(IrInt(1), IrOp("=="), IrInt(0)).eval(IrNone, IrNone, ()) == 0


def test_ircompare_lt_and_gt():
    """< and > compare operands and yield IrInt(1)/IrInt(0)."""
    assert IrCompare(IrInt(1), IrOp("<"), IrInt(2)).eval(IrNone, IrNone, ()) == 1
    assert IrCompare(IrInt(2), IrOp(">"), IrInt(1)).eval(IrNone, IrNone, ()) == 1
    assert IrCompare(IrInt(2), IrOp("<"), IrInt(1)).eval(IrNone, IrNone, ()) == 0
    assert IrCompare(IrInt(1), IrOp(">"), IrInt(2)).eval(IrNone, IrNone, ()) == 0


def test_ircompare_reads_field_operand():
    """An IrField operand is evaluated against the dispatched node before compare."""
    q = IrQuantifier(min=0, max=1)
    cmp = IrCompare(IrField("min", IrInt), IrOp("=="), IrInt(0))
    assert cmp.eval(IrNone, q, ()) == 1


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


def test_irchildren_returns_full_new_children_tuple():
    """IrChildren() returns new_children for a node with children.

    IrChildren carries no name argument in the new model (R2).
    """
    seq = IrSequence(IrItem(IrLiteral("a")))
    new_children = IrTuple(IrStr("result_a"))
    result = IrChildren[IrSelf, IrStr]().eval(IrNone, seq, new_children)
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
    """IrConcat is an IrNamedTuple; evaluates parts and concatenates."""
    c = IrConcat(parts=IrTuple(IrLiteral("a"), IrLiteral("b")))
    assert isinstance(c, IrNamedTuple)
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


def test_ircond_evaluates_then_when_test_truthy():
    """IrCond picks then_op when the test node evals truthy."""
    node = IrQuantifier(min=1, max=1)
    op = IrCond[IrStr](
        test=IrField("min", IrInt), then_op=IrLiteral("yes"), else_op=IrLiteral("no")
    )
    assert op.eval(IrNone, node, ()) == "yes"


def test_ircond_evaluates_else_when_test_falsy():
    """IrCond picks else_op when the test node evals falsy."""
    node = IrQuantifier(min=0, max=1)
    op = IrCond[IrStr](
        test=IrField("min", IrInt), then_op=IrLiteral("yes"), else_op=IrLiteral("no")
    )
    assert op.eval(IrNone, node, ()) == "no"


# ── IrThis ───────────────────────────────────────────────────────────


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


def test_irreturn_raises_self_and_is_node_and_exception():
    """IrReturn is an IrNode leaf and a BaseException; eval raises self."""
    r = IrReturn(IrLiteral("v"))
    assert isinstance(r, IrNode) and isinstance(r, BaseException)
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
    with pytest.raises(UnsupportedConstructError):
        IrRaise().eval(IrNone, IrLiteral("x"), ())
