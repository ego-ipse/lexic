"""Public IR surface — import everything from here.

A **lazy façade**, for the reason the package root is one: re-exporting eagerly
made every spine consumer pay the whole spine. ``import lexic.ir.base`` cost 17
modules to reach 1, and a compiled ``ir`` payload — which names 13 symbols
living in exactly 2 of these modules — paid all 17 on every read.

The names resolve on first access instead, and the ``TYPE_CHECKING`` block
declares them statically, so ``from lexic.ir import IrRule`` is still typed as
the class it is. That block re-exports rather than restates, so no signature can
drift from the module that owns it.

CLAUDE.md's *"no TYPE_CHECKING dodges"* is a LAYERING rule — it forbids a
runtime module reaching into the engine behind the type checker's back. This is
a package façade, which has no layer and no arrow to dodge.

REVISIT ON 3.15 — if PEP 810 (explicit lazy imports) lands, this file collapses
back to plain ``lazy from … import …`` lines and ``_HOMES``, ``__getattr__`` and
the drift pin all go away. Wait for a RELEASE, not a beta.
"""

from importlib import import_module
from typing import TYPE_CHECKING

from lexic.ir.base import IrSelf

# `concretize` cannot be lazy: it names BOTH this export and the submodule
# `lexic.ir.concretize`, so the moment anything imports the module the attribute
# exists and `__getattr__` — which Python only calls on a MISS — never runs,
# handing a caller the module instead of the function. Binding it here is the
# same collision the package root has with `generate`, and no import mechanism
# resolves two things wanting one name.
from lexic.ir.concretize import concretize, concretize_atom

if TYPE_CHECKING:
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
        IrEach,
        IrField,
        IrIndex,
        IrIsA,
        IrJoin,
        IrLen,
        IrMerge,
        IrOrd,
        IrPipe,
        IrRadix,
        IrReturn,
        IrUnradix,
    )
    from lexic.ir.base import (
        IrAtom,
        IrChr,
        IrInt,
        IrLeaf,
        IrNamedTuple,
        IrNode,
        IrNone,
        IrNoneType,
        IrScalar,
        IrSeq,
        IrStr,
        IrTuple,
    )
    from lexic.ir.bind import BIND_MODES, IrBind
    from lexic.ir.canonical import canonicalize, fold_name
    from lexic.ir.encoding import IrEncoding, IrTokenizer, IrUnicode
    from lexic.ir.escapes import EscapeCodec
    from lexic.ir.mapping import IR_DEFAULT, IrMap, IrTypeMap
    from lexic.ir.nodes import (
        IrAlphabet,
        IrAlternation,
        IrAst,
        IrBounds,
        IrCharClass,
        IrItem,
        IrLiteral,
        IrQuantifier,
        IrRange,
        IrRule,
        IrRuleRef,
        IrSequence,
    )
    from lexic.ir.operators import IrAnd, IrNot, IrOp, IrOpNode
    from lexic.ir.order import RuleOrder, order_by_refs
    from lexic.ir.walk import IrBottomUp, IrTransformer, IrVisitor

__all__ = [
    "BIND_MODES",
    "IR_DEFAULT",
    "EscapeCodec",
    "IrAction",
    "IrAlphabet",
    "IrAlternation",
    "IrAnd",
    "IrApply",
    "IrArg",
    "IrArgs",
    "IrAst",
    "IrAt",
    "IrAtom",
    "IrBind",
    "IrBottomUp",
    "IrChr",
    "IrBounds",
    "IrBuild",
    "IrCharClass",
    "IrChild",
    "IrChildren",
    "IrCompare",
    "IrConcat",
    "IrCond",
    "IrEach",
    "IrEncoding",
    "IrField",
    "IrIndex",
    "IrInt",
    "IrIsA",
    "IrItem",
    "IrJoin",
    "IrLeaf",
    "IrLen",
    "IrLiteral",
    "IrMap",
    "IrMerge",
    "IrNamedTuple",
    "IrNode",
    "IrNone",
    "IrNoneType",
    "IrNot",
    "IrOp",
    "IrOpNode",
    "IrOrd",
    "IrPipe",
    "IrRadix",
    "IrReturn",
    "IrRule",
    "IrRuleRef",
    "IrScalar",
    "IrSelf",
    "IrSeq",
    "IrSequence",
    "IrStr",
    "IrTokenizer",
    "IrTransformer",
    "IrTuple",
    "IrTypeMap",
    "IrUnicode",
    "IrUnradix",
    "IrVisitor",
    "IrQuantifier",
    "IrRange",
    "RuleOrder",
    "canonicalize",
    "concretize",
    "concretize_atom",
    "fold_name",
    "order_by_refs",
]

_HOMES = {
    "BIND_MODES": "lexic.ir.bind",
    "EscapeCodec": "lexic.ir.escapes",
    "IR_DEFAULT": "lexic.ir.mapping",
    "IrAction": "lexic.ir.action",
    "IrAlphabet": "lexic.ir.nodes",
    "IrAlternation": "lexic.ir.nodes",
    "IrAnd": "lexic.ir.operators",
    "IrApply": "lexic.ir.action",
    "IrArg": "lexic.ir.action",
    "IrArgs": "lexic.ir.action",
    "IrAst": "lexic.ir.nodes",
    "IrAt": "lexic.ir.action",
    "IrAtom": "lexic.ir.base",
    "IrBind": "lexic.ir.bind",
    "IrBottomUp": "lexic.ir.walk",
    "IrBounds": "lexic.ir.nodes",
    "IrBuild": "lexic.ir.action",
    "IrCharClass": "lexic.ir.nodes",
    "IrChild": "lexic.ir.action",
    "IrChildren": "lexic.ir.action",
    "IrChr": "lexic.ir.base",
    "IrCompare": "lexic.ir.action",
    "IrConcat": "lexic.ir.action",
    "IrCond": "lexic.ir.action",
    "IrEach": "lexic.ir.action",
    "IrEncoding": "lexic.ir.encoding",
    "IrField": "lexic.ir.action",
    "IrIndex": "lexic.ir.action",
    "IrInt": "lexic.ir.base",
    "IrIsA": "lexic.ir.action",
    "IrItem": "lexic.ir.nodes",
    "IrJoin": "lexic.ir.action",
    "IrLeaf": "lexic.ir.base",
    "IrLen": "lexic.ir.action",
    "IrLiteral": "lexic.ir.nodes",
    "IrMap": "lexic.ir.mapping",
    "IrMerge": "lexic.ir.action",
    "IrNamedTuple": "lexic.ir.base",
    "IrNode": "lexic.ir.base",
    "IrNone": "lexic.ir.base",
    "IrNoneType": "lexic.ir.base",
    "IrNot": "lexic.ir.operators",
    "IrOp": "lexic.ir.operators",
    "IrOpNode": "lexic.ir.operators",
    "IrOrd": "lexic.ir.action",
    "IrPipe": "lexic.ir.action",
    "IrQuantifier": "lexic.ir.nodes",
    "IrRadix": "lexic.ir.action",
    "IrRange": "lexic.ir.nodes",
    "IrReturn": "lexic.ir.action",
    "IrRule": "lexic.ir.nodes",
    "IrRuleRef": "lexic.ir.nodes",
    "IrScalar": "lexic.ir.base",
    "IrSelf": "lexic.ir.base",
    "IrSeq": "lexic.ir.base",
    "IrSequence": "lexic.ir.nodes",
    "IrStr": "lexic.ir.base",
    "IrTokenizer": "lexic.ir.encoding",
    "IrTransformer": "lexic.ir.walk",
    "IrTuple": "lexic.ir.base",
    "IrTypeMap": "lexic.ir.mapping",
    "IrUnicode": "lexic.ir.encoding",
    "IrUnradix": "lexic.ir.action",
    "IrVisitor": "lexic.ir.walk",
    "RuleOrder": "lexic.ir.order",
    "canonicalize": "lexic.ir.canonical",
    "fold_name": "lexic.ir.canonical",
    "order_by_refs": "lexic.ir.order",
}
"""Every LAZY export and the module that defines it — where ``__getattr__`` looks.
``concretize``/``concretize_atom`` are absent because they are bound eagerly
above, for the name-collision reason stated there.

The surface is stated three times, once per consumer: the ``TYPE_CHECKING``
block for the type checker, ``__all__`` for the export machinery (and for ruff,
which cannot see a computed one), and this for the runtime lookup. The drift pin
in ``test_init_ir`` holds all three to each other, so a name joins the surface
only by joining all of them."""


def __getattr__(name: str) -> type[IrSelf] | IrSelf:
    """Resolve an export on first access.

    :param name: The attribute being read.
    :returns: The node class, or the singleton value for a bare-name export
        (``IrNone``, ``IR_DEFAULT``) — the two things this surface holds.
    :raises AttributeError: On a name the package does not export.
    """
    home = _HOMES.get(name)
    if home is None:
        raise AttributeError(f"module 'lexic.ir' has no attribute {name!r}")
    return getattr(import_module(home), name)


def __dir__() -> list[str]:
    """The exports, so ``dir()`` and tab-completion still see the surface."""
    return sorted(__all__)
