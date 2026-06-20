"""Tests for ir/action.py — action-algebra nodes built on the IrSelf substrate.

Action algebra uses ``.eval(d, n, nc)`` to produce typed values.
``__call__(d, n, nc)`` remains identity-shaped (returns self) via
:class:`~lexic.ir.nodes.IrSelf`.
"""

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action import (
    IrAction,
    IrApply,
    IrArg,
    IrArgs,
    IrAt,
    IrBuild,
    IrChild,
    IrChildren,
    IrCompare,
    IrConcat,
    IrCond,
    IrEmit,
    IrField,
    IrIndex,
    IrIsA,
    IrJoin,
    IrLeaf,
    IrOp,
    IrPass,
    IrPipe,
    IrRaise,
    IrRebuild,
    IrReturn,
    IrThis,
    IrWalk,
    _Return,
)
from lexic.ir.base import (
    IrInt,
    IrLambda,
    IrNamedTuple,
    IrNode,
    IrNone,
    IrSelf,
    IrStr,
    IrTuple,
)
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot
from lexic.ir.walk import IrDispatch, IrEmitter
from lexic.utils.charclass import charclass_pattern

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

    op = IrLambda(body_that_catches_exception)
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
    assert repr(IrField("lo", IrInt)) == "IrField('lo', IrInt)"
    assert repr(IrField("name")) == "IrField('name', IrStr)"


def test_irfield_out_irint_reads_int_without_stringifying():
    """IrField('lo', IrInt) reads an int attribute and wraps it as IrInt."""
    q = IrQuantifier(lo=3, hi=5)
    result = IrField("lo", IrInt).eval(IrNone, q, ())
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
    q = IrQuantifier(lo=0, hi=1)
    cmp = IrCompare(IrField("lo", IrInt), IrOp("=="), IrInt(0))
    assert cmp.eval(IrNone, q, ()) == 1


# ── IrChild ──────────────────────────────────────────────────────────


def test_irchild_reads_dispatched_child_by_name():
    """IrChild dispatches the real child from ``n`` via ``d`` — ``nc`` is ignored.

    ``IrChild("atom")`` looks up "atom" in ``type(n)._child_attrs``, takes
    ``n.children()[0]``, and dispatches it.  A populated ``nc`` must not
    change the result.
    """
    item = IrItem(atom=IrLiteral("x"))
    emitter = IrEmitter()
    result_no_nc = IrChild("atom").eval(emitter, item, IrTuple())
    # Passing a non-empty nc must produce the same value — nc is not read.
    result_with_nc = IrChild("atom").eval(
        emitter, item, (IrStr("ignored_1"), IrStr("ignored_2"))
    )
    assert result_no_nc == "x"
    assert result_no_nc == result_with_nc


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


def test_irchild_raises_on_unknown_name():
    """IrChild raises ValueError when the name is not in _child_attrs."""
    item = IrItem(atom=IrLiteral("x"))
    with pytest.raises(ValueError, match="no such child"):
        IrChild("nonexistent").eval(IrNone, item, IrTuple(IrStr("a"), IrStr("b")))


def test_irchild_is_its_payload_string():
    """IrChild is a value-leaf: the node itself IS the field name string."""
    assert IrChild("atom") == "atom"
    assert isinstance(IrChild("atom"), str)


def test_irchild_repr_is_codegen():
    """IrChild repr renders as codegen-style constructor call."""
    assert repr(IrChild("atom")) == "IrChild('atom')"


# ── IrIndex ───────────────────────────────────────────────────────────


def test_irindex_ignores_nc_dispatches_real_child():
    """IrIndex always reads ``n``'s real children — a populated ``nc`` is ignored.

    The eager-``nc`` branch is gone.  Both ``IrIndex(0)`` and ``IrIndex(1)``
    must produce the same result whether or not a non-empty ``nc`` is supplied.
    """
    item = IrItem(atom=IrLiteral("x"))
    emitter = IrEmitter()
    nc_irrelevant = (IrStr("should_be_ignored_0"), IrStr("should_be_ignored_1"))
    result_0_nc = IrIndex(0).eval(emitter, item, nc_irrelevant)
    result_0_no_nc = IrIndex(0).eval(emitter, item, IrTuple())
    assert result_0_nc == result_0_no_nc
    assert result_0_nc == "x"


def test_irindex_negative_resolves_last_real_child():
    """IrIndex(-1) dispatches the last real child of ``n``; ``nc`` is not consulted.

    For an :class:`IrItem`, child index -1 is the quantifier, regardless of any
    ``nc`` content passed by the caller.
    """
    item = IrItem(atom=IrLiteral("x"))
    emitter = IrEmitter()
    nc_irrelevant = (IrStr("ignored_0"), IrStr("ignored_1"))
    result_with_nc = IrIndex(-1).eval(emitter, item, nc_irrelevant)
    result_no_nc = IrIndex(-1).eval(emitter, item, IrTuple())
    # Both must give the quantifier child, not the nc content
    assert result_with_nc == result_no_nc
    assert isinstance(result_with_nc, IrLiteral)  # quantifier rendered by IrEmitter


def test_irindex_is_its_payload_int():
    """IrIndex is a value-leaf: the node itself IS its integer position."""
    assert IrIndex(0) == 0
    assert isinstance(IrIndex(0), int)


def test_irindex_repr_is_codegen():
    """IrIndex repr renders as codegen-style constructor call."""
    assert repr(IrIndex(0)) == "IrIndex(0)"


def test_irindex_out_of_range_raises_index_error():
    """IrIndex with an out-of-range position raises IndexError."""
    item = IrItem(atom=IrLiteral("x"))
    new_children = (IrStr("a"), IrStr("b"))
    with pytest.raises(IndexError):
        IrIndex(5).eval(IrNone, item, new_children)


def test_irindex_lazy_dispatches_child_via_d():
    """IrIndex(0) with empty nc dispatches the child through d (lazy path).

    IrEmitter default (IrEmit) converts IrLiteral('x') to IrLiteral('x').
    """
    item = IrItem(atom=IrLiteral("x"))
    emitter = IrEmitter()
    result = IrIndex(0).eval(emitter, item, IrTuple())
    assert result == IrLiteral("x")
    assert isinstance(result, IrLiteral)


# ── IrChildren ───────────────────────────────────────────────────────


def test_irchildren_dispatches_real_children_ignores_nc():
    """IrChildren dispatches ``n``'s real children via ``d`` — a populated ``nc``
    is never consulted.

    The result must be the same whether ``nc`` is empty or non-empty.
    """
    seq = IrSequence(IrItem(IrLiteral("a")))
    emitter = IrEmitter()
    result_empty_nc = IrChildren[IrSelf, IrTuple]().eval(emitter, seq, IrTuple())
    result_populated_nc = IrChildren[IrSelf, IrTuple]().eval(
        emitter, seq, IrTuple(IrStr("ignored"))
    )
    assert result_empty_nc == result_populated_nc
    # Children come from seq itself: one IrItem child
    assert len(result_empty_nc) == 1


# ── IrAt ─────────────────────────────────────────────────────────────


def test_irat_rebinds_focus_to_raw_child():
    """IrAt(0, body) hands the body the raw child at position 0, undispatched.

    Over ``IrNot(IrCharClass(IrRange('a','z')))``, ``IrAt(0, IrThis())`` must
    surface the raw ``IrCharClass`` — not a dispatched/rendered string.
    """
    nod = IrNot(IrCharClass(IrRange("a", "z")))
    emitter = IrEmitter()
    result = IrAt(0, IrThis()).eval(emitter, nod, IrTuple())
    assert result is nod.children()[0]
    assert isinstance(result, IrCharClass)
    assert charclass_pattern(result) == "a-z"


def test_irat_negative_selector_indexes_from_end():
    """IrAt(-1, IrThis()) selects the last raw child."""
    nod = IrNot(IrCharClass(IrRange("0", "9")))
    emitter = IrEmitter()
    result = IrAt(-1, IrThis()).eval(emitter, nod, IrTuple())
    # IrNot has a single child; -1 addresses the same slot as 0
    assert isinstance(result, IrCharClass)


def test_irat_out_of_range_raises_index_error():
    """IrAt raises IndexError when the selector is out of range."""
    nod = IrNot(IrCharClass(IrRange("a", "z")))
    emitter = IrEmitter()
    with pytest.raises(IndexError):
        IrAt(5, IrThis()).eval(emitter, nod, IrTuple())


def test_irat_body_receives_fresh_empty_nc():
    """IrAt starts the body with a fresh empty nc even when the caller passed args.

    :class:`IrArgs` in the body must return an empty tuple because the context
    shift resets the argument channel.
    """
    nod = IrNot(IrCharClass(IrRange("a", "z")))
    emitter = IrEmitter()
    # IrAt(0, IrArgs()) — body reads nc, which must be empty after the rebind
    result = IrAt(0, IrArgs()).eval(emitter, nod, IrTuple(IrLiteral("^")))
    assert result == IrTuple()


def test_irat_repr_is_codegen():
    """IrAt repr renders as a valid constructor expression."""
    assert repr(IrAt(0, IrThis())) == "IrAt(0, IrThis())"


# ── IrArgs ───────────────────────────────────────────────────────────


def test_irargs_returns_nc_as_irtuple():
    """IrArgs evaluates to the argument channel wrapped in IrTuple."""
    args_node = IrArgs()
    result = args_node.eval(IrNone, IrNone, (IrLiteral("a"), IrLiteral("b")))
    assert result == IrTuple(IrLiteral("a"), IrLiteral("b"))


def test_irargs_empty_nc_returns_empty_irtuple():
    """IrArgs with no arguments evaluates to an empty IrTuple."""
    result = IrArgs().eval(IrNone, IrNone, ())
    assert result == IrTuple()
    assert len(result) == 0


def test_irargs_composes_with_irjoin():
    """IrJoin(parts=IrArgs()) renders joined arguments; empty nc uses the fallback.

    This is the pattern used by :data:`~lexic.grammars.gbnf.flavour.GBNF_ACTIONS`
    inside the ``IrCharClass`` action.
    """
    join = IrJoin(parts=IrArgs(), separator=IrLiteral(","), empty=IrLiteral("(empty)"))
    result_with_args = join.eval(IrNone, IrNone, (IrLiteral("x"), IrLiteral("y")))
    assert result_with_args == "x,y"
    result_no_args = join.eval(IrNone, IrNone, ())
    assert result_no_args == "(empty)"


def test_irargs_repr_is_codegen():
    """IrArgs repr renders as a valid constructor expression."""
    assert repr(IrArgs()) == "IrArgs()"


# ── IrApply ───────────────────────────────────────────────────────────


def test_irapply_re_dispatches_n_with_evaluated_args():
    """IrApply evaluates its args then re-dispatches ``n`` via ``d`` with them.

    Build a small ``IrTypeMap`` / ``IrDispatch`` whose action for ``IrCharClass``
    reads the handed-over arguments via :class:`IrArgs`.  :class:`IrApply` must
    pass those arguments as the new ``nc`` for the re-dispatch.
    """
    # Action for IrCharClass: just return IrArgs() as the result so we can inspect it
    charclass_action = IrAction(
        IrCharClass,
        IrArgs(),  # body returns IrTuple(*nc) — shows what args arrived
    )
    dispatch = IrDispatch(actions=IrTypeMap(charclass_action))
    n = IrCharClass(IrRange("a", "z"))
    args_tuple = IrTuple(IrLiteral("^"))
    result = IrApply(args_tuple).eval(dispatch, n, IrTuple())
    # The re-dispatch ran IrCharClass's action (IrArgs) with nc=(IrLiteral("^"),)
    assert result == IrTuple(IrLiteral("^"))


def test_irapply_default_args_dispatches_with_empty_channel():
    """IrApply() with default empty args dispatches n with an empty nc."""
    charclass_action = IrAction(IrCharClass, IrArgs())
    dispatch = IrDispatch(actions=IrTypeMap(charclass_action))
    n = IrCharClass(IrRange("0", "9"))
    result = IrApply().eval(dispatch, n, IrTuple())
    assert result == IrTuple()


def test_irapply_repr_is_codegen():
    """IrApply repr renders as a valid constructor expression."""
    assert repr(IrApply(IrTuple(IrLiteral("^")))) == "IrApply(IrTuple(IrLiteral('^')))"


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


# ── IrIsA ─────────────────────────────────────────────────────────────


def test_irisa_atom_is_alternation_evals_to_irint_one():
    """IrIsA evals to IrInt(1) when the named attribute IS-A the target type."""
    alt = IrAlternation(IrSequence(IrItem(atom=IrLiteral("x"))))
    item = IrItem(atom=alt)
    result = IrIsA("atom", IrAlternation).eval(IrNone, item, ())
    assert result == 1
    assert repr(result) == "IrInt(1)"


def test_irisa_atom_not_alternation_evals_to_irint_zero():
    """IrIsA evals to IrInt(0) when the named attribute is NOT the target type."""
    item = IrItem(atom=IrLiteral("y"))
    result = IrIsA("atom", IrAlternation).eval(IrNone, item, ())
    assert result == 0
    assert repr(result) == "IrInt(0)"


def test_irisa_result_is_truthy_when_one():
    """IrInt(1) result is truthy; IrInt(0) is falsy."""
    alt = IrAlternation(IrSequence(IrItem(atom=IrLiteral("x"))))
    item_alt = IrItem(atom=alt)
    item_lit = IrItem(atom=IrLiteral("z"))
    assert bool(IrIsA("atom", IrAlternation).eval(IrNone, item_alt, ()))
    assert not bool(IrIsA("atom", IrAlternation).eval(IrNone, item_lit, ()))


def test_irisa_repr_renders_class_bare():
    """IrIsA repr is codegen: 'IrIsA('atom', IrAlternation)'."""
    assert repr(IrIsA("atom", IrAlternation)) == "IrIsA('atom', IrAlternation)"


def test_irisa_missing_attribute_raises_attribute_error():
    """IrIsA raises AttributeError when the attribute does not exist on the node."""
    item = IrItem(atom=IrLiteral("x"))
    with pytest.raises(AttributeError):
        IrIsA("nonexistent", IrAlternation).eval(IrNone, item, ())


# ── IrArg ─────────────────────────────────────────────────────────────


def test_irarg_reads_positional_nc_element():
    """IrArg(i) returns nc[i] undispatched — arguments are already resolved."""
    nc = (IrLiteral("a"), IrLiteral("b"), IrLiteral("c"))
    assert IrArg(0).eval(IrNone, IrNone, nc) is nc[0]
    assert IrArg(1).eval(IrNone, IrNone, nc) is nc[1]
    assert IrArg(2).eval(IrNone, IrNone, nc) is nc[2]


def test_irarg_negative_indexes_from_end():
    """IrArg(-1) returns the last element of nc."""
    nc = (IrLiteral("x"), IrLiteral("y"))
    assert IrArg(-1).eval(IrNone, IrNone, nc) is nc[-1]


def test_irarg_ignores_d_and_n():
    """IrArg ignores the dispatcher and the dispatched node — only nc matters."""
    nc = (IrStr("val"),)
    result = IrArg(0).eval(IrNone, IrLiteral("ignored"), nc)
    assert result is nc[0]


def test_irarg_out_of_range_raises_index_error():
    """IrArg raises IndexError for a position beyond nc's length."""
    with pytest.raises(IndexError):
        IrArg(5).eval(IrNone, IrNone, (IrLiteral("a"),))


def test_irarg_is_irint_leaf():
    """IrArg IS-A IrInt — the node itself is its index."""
    assert IrArg(0) == 0
    assert isinstance(IrArg(0), IrInt)


def test_irarg_repr_is_codegen():
    """IrArg repr renders as a valid constructor expression."""
    assert repr(IrArg(0)) == "IrArg(0)"
    assert repr(IrArg(1)) == "IrArg(1)"


# ── IrBuild ───────────────────────────────────────────────────────────


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
    """IrBuild repr renders as a valid constructor expression."""
    assert repr(IrBuild(IrSequence)) == "IrBuild(IrSequence, IrNone)"
    assert (
        repr(IrBuild(IrRuleRef, IrTuple(IrArg(0))))
        == "IrBuild(IrRuleRef, IrTuple(IrArg(0)))"
    )


# ── IrPipe ────────────────────────────────────────────────────────────


def test_irpipe_shifts_focus_to_computed_value():
    """IrPipe(source, body) evaluates body with n rebound to source.eval(...)."""
    # source: IrArg(0) reads nc[0]; body: IrField("name") reads .name off that
    rule = IrRule("myrule", IrAlternation())
    nc = (rule,)
    result = IrPipe(IrArg(0), IrField("name")).eval(IrNone, IrNone, nc)
    assert result == IrStr("myrule")


def test_irpipe_carries_nc_through_to_body():
    """IrPipe forwards nc to the body after rebinding the focus."""
    # body = IrArg(0) reads nc[0] using the shifted context
    nc = (IrLiteral("pass-through"),)
    result = IrPipe(IrThis(), IrArg(0)).eval(IrNone, IrNone, nc)
    assert result is nc[0]


def test_irpipe_source_and_body_are_children():
    """IrPipe._child_attrs contains both source and body."""
    pipe = IrPipe(IrArg(0), IrField("name"))
    children = pipe.children()
    assert IrArg(0) in children
    assert IrField("name") in children


def test_irpipe_repr_is_codegen():
    """IrPipe repr renders as a valid constructor expression."""
    assert (
        repr(IrPipe(IrArg(0), IrField("name")))
        == "IrPipe(IrArg(0), IrField('name', IrStr))"
    )
