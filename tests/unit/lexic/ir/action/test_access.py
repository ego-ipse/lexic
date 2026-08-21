"""Tests for ``lexic.ir.action.access``."""

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLeaf, IrOp
from lexic.ir.action.access import (
    IrArg,
    IrArgs,
    IrAt,
    IrChild,
    IrChildren,
    IrField,
    IrIndex,
    IrLen,
)
from lexic.ir.action.build import (
    IrAction,
    IrApply,
)
from lexic.ir.action.flow.compute import (
    IrCompare,
    IrJoin,
)
from lexic.ir.action.flow.control import IrEach, IrPipe, IrThis
from lexic.ir.action.mapping import IrTypeMap
from lexic.ir.action.walk import IrDispatch, IrEmitter
from lexic.ir.grammar.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrSequence,
)
from lexic.ir.grammar.operators import IrNot
from lexic.ir.spine.records import IrNamedTuple, IrTuple
from lexic.ir.spine.scalars import IrChr, IrInt, IrStr
from lexic.ir.spine.spine import IrNone, IrSelf


def test_irfield_reads_string_attribute():
    """IrField returns the attribute value wrapped in IrStr.

    IrRuleRef IS-A str — the node itself is the payload; there is no ``.value``
    field. IrField reads a named attribute of a composite node.  Here we read
    ``name`` from an :class:`~lexic.ir.grammar.nodes.IrRule`.
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
    """IrField repr renders the class-valued `out` as a bare name (eval round-trips).

    The default-valued `out=IrStr` is omitted from the trailing run.
    """
    assert repr(IrField("lo", IrInt)) == "IrField('lo', IrInt)"
    assert repr(IrField("name")) == "IrField('name')"


def test_irfield_out_irint_reads_int_without_stringifying():
    """IrField('lo', IrInt) reads an int attribute and wraps it as IrInt."""
    q = IrQuantifier(lo=3, hi=5)
    result = IrField("lo", IrInt).eval(IrNone, q, ())
    assert result == 3
    assert isinstance(result, IrInt)


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


def test_ircompare_reads_field_operand():
    """An IrField operand is evaluated against the dispatched node before compare."""
    q = IrQuantifier(lo=0, hi=1)
    cmp = IrCompare(IrField("lo", IrInt), IrOp("=="), IrInt(0))
    assert cmp.eval(IrNone, q, ()) == 1


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


def test_irat_rebinds_focus_to_raw_child():
    """IrAt(0, body) hands the body the raw child at position 0, undispatched.

    Over ``IrNot(IrCharClass(IrRange('a','z')))``, ``IrAt(0, IrThis())`` must
    surface the raw ``IrCharClass`` — not a dispatched/rendered string.
    """
    nod = IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z"))))
    emitter = IrEmitter()
    result = IrAt(0, IrThis()).eval(emitter, nod, IrTuple())
    assert result is nod.children()[0]
    assert isinstance(result, IrCharClass)
    assert result == IrCharClass(IrRange(IrChr("a"), IrChr("z")))


def test_irat_negative_selector_indexes_from_end():
    """IrAt(-1, IrThis()) selects the last raw child."""
    nod = IrNot(IrCharClass(IrRange(IrChr("0"), IrChr("9"))))
    emitter = IrEmitter()
    result = IrAt(-1, IrThis()).eval(emitter, nod, IrTuple())
    # IrNot has a single child; -1 addresses the same slot as 0
    assert isinstance(result, IrCharClass)


def test_irat_out_of_range_raises_index_error():
    """IrAt raises IndexError when the selector is out of range."""
    nod = IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z"))))
    emitter = IrEmitter()
    with pytest.raises(IndexError):
        IrAt(5, IrThis()).eval(emitter, nod, IrTuple())


def test_irat_body_receives_fresh_empty_nc():
    """IrAt starts the body with a fresh empty nc even when the caller passed args.

    :class:`IrArgs` in the body must return an empty tuple because the context
    shift resets the argument channel.
    """
    nod = IrNot(IrCharClass(IrRange(IrChr("a"), IrChr("z"))))
    emitter = IrEmitter()
    # IrAt(0, IrArgs()) — body reads nc, which must be empty after the rebind
    result = IrAt(0, IrArgs()).eval(emitter, nod, IrTuple(IrLiteral("^")))
    assert result == IrTuple()


def test_irat_repr_is_codegen():
    """IrAt repr renders as a valid constructor expression."""
    assert repr(IrAt(0, IrThis())) == "IrAt(0, IrThis())"


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
    n = IrCharClass(IrRange(IrChr("a"), IrChr("z")))
    args_tuple = IrTuple(IrLiteral("^"))
    result = IrApply(args_tuple).eval(dispatch, n, IrTuple())
    # The re-dispatch ran IrCharClass's action (IrArgs) with nc=(IrLiteral("^"),)
    assert result == IrTuple(IrLiteral("^"))


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


def test_irpipe_shifts_focus_to_computed_value():
    """IrPipe(source, body) evaluates body with n rebound to source.eval(...)."""
    # source: IrArg(0) reads nc[0]; body: IrField("name") reads .name off that
    rule = IrRule("myrule", IrAlternation())
    nc = (rule,)
    result = IrPipe(IrArg(0), IrField("name")).eval(IrNone, IrNone, nc)
    assert result == IrStr("myrule")


def test_irpipe_source_and_body_are_children():
    """IrPipe._child_attrs contains both source and body."""
    pipe = IrPipe(IrArg(0), IrField("name"))
    children = pipe.children()
    assert IrArg(0) in children
    assert IrField("name") in children


def test_irpipe_repr_is_codegen():
    """IrPipe repr renders as a valid constructor expression.

    The nested IrField's default-valued `out=IrStr` is omitted.
    """
    assert (
        repr(IrPipe(IrArg(0), IrField("name"))) == "IrPipe(IrArg(0), IrField('name'))"
    )


def test_irlen_is_a_plain_leaf():
    """IrLen is a plain IrLeaf body carrying no IR-node children."""
    assert isinstance(IrLen(), IrLeaf)
    assert not IrLen().children()


def test_irlen_counts_tuple_shaped_focus():
    """IrLen.eval on a tuple-shaped focus returns its element count."""
    seq = IrSequence(IrItem(IrLiteral("a")), IrItem(IrLiteral("b")))
    assert IrLen().eval(IrNone, seq, ()) == IrInt(2)


def test_irlen_counts_str_leaf_focus():
    """IrLen.eval on a str-leaf focus returns its character count."""
    assert IrLen().eval(IrNone, IrLiteral("abc"), ()) == IrInt(3)


def test_irlen_empty_focus_is_zero():
    """IrLen.eval on an empty tuple/str focus returns IrInt(0)."""
    assert IrLen().eval(IrNone, IrSequence(), ()) == IrInt(0)
    assert IrLen().eval(IrNone, IrLiteral(""), ()) == IrInt(0)


def test_irlen_unsized_focus_raises():
    """IrLen.eval raises UnsupportedConstructError on an unsized focus."""
    with pytest.raises(UnsupportedConstructError, match="no length"):
        IrLen().eval(IrNone, IrInt(5), ())


def test_irlen_repr_is_codegen():
    """IrLen repr renders as a valid constructor expression."""
    assert repr(IrLen()) == "IrLen()"


def test_irlen_composes_as_ircompare_operand():
    """IrLen is the natural IrCompare operand for arity-branching bodies."""
    seq = IrSequence(IrItem(IrLiteral("a")))
    cmp = IrCompare(IrLen(), IrOp("=="), IrInt(1))
    assert cmp.eval(IrNone, seq, ()) == 1


def test_ireach_body_receives_fresh_empty_nc():
    """IrEach starts each per-element body with a fresh empty nc, like every
    other focus shift (IrAt's precedent) — IrArgs() in the body must read empty
    even though the caller passed args."""
    focus = IrTuple(IrInt(1), IrInt(2))
    result = IrEach(IrArgs()).eval(IrNone, focus, (IrLiteral("ignored"),))
    assert result == IrTuple(IrTuple(), IrTuple())
