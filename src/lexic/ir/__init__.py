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

# `concretize` cannot be lazy: it names BOTH this export and the submodule
# `lexic.ir.concretize`, so the moment anything imports the module the attribute
# exists and `__getattr__` — which Python only calls on a MISS — never runs,
# handing a caller the module instead of the function. Binding it here is the
# same collision the package root has with `generate`, and no import mechanism
# resolves two things wanting one name.
from lexic.ir.concretize import concretize, concretize_atom
from lexic.ir.spine import IrSelf

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
        IrEmit,
        IrField,
        IrGlyph,
        IrIndex,
        IrIsA,
        IrJoin,
        IrLen,
        IrMerge,
        IrOrd,
        IrPass,
        IrPipe,
        IrRadix,
        IrRaise,
        IrRebuild,
        IrReturn,
        IrThis,
        IrUnradix,
        IrWalk,
    )
    from lexic.ir.bind import (
        BIND_MODES,
        IrBind,
    )
    from lexic.ir.canonical import (
        canonicalize,
        fold_name,
    )
    from lexic.ir.encoding import (
        IrEncoding,
        IrLongestMatch,
        IrNormalizer,
        IrPretoken,
        IrRankedMerge,
        IrReplace,
        IrSegmenter,
        IrTokenizer,
        IrTokenPipeline,
        IrUnicode,
        IrUnicodeForm,
        IrUnknown,
        IrUtf,
        Merges,
        UnicodeForm,
        Vocab,
    )
    from lexic.ir.escapes import (
        EscapeCodec,
    )
    from lexic.ir.flavour import (
        IrEscape,
        IrEscapePoint,
        IrFlavour,
        IrSpellable,
    )
    from lexic.ir.layout import (
        IrCat,
        IrDoc,
        IrDocConcat,
        IrDocJoin,
        IrGroup,
        IrLine,
        IrNest,
        IrText,
        Sheet,
        as_doc,
        render,
    )
    from lexic.ir.mapping import (
        IR_DEFAULT,
        IrMap,
        IrMapping,
        IrMultiMap,
        IrTypeMap,
    )
    from lexic.ir.meta import (
        Borg,
        IrMeta,
        IrSingleton,
        Singleton,
    )
    from lexic.ir.nodes import (
        MAX_CODEPOINT,
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
    from lexic.ir.operators import (
        DyadicOp,
        IrAnd,
        IrEq,
        IrNot,
        IrOp,
        IrOpNode,
        MonadicOp,
        VariadicOp,
    )
    from lexic.ir.order import (
        RuleOrder,
        order_by_refs,
        refs_in_order,
        rule_closure,
    )
    from lexic.ir.records import (
        Field,
        IrCachingTuple,
        IrNamedTuple,
        IrSeq,
        IrTuple,
    )
    from lexic.ir.scalars import (
        IrChr,
        IrInt,
        IrScalar,
        IrStr,
    )
    from lexic.ir.spine import (
        IrAtom,
        IrLambda,
        IrLeaf,
        IrNode,
        IrNone,
        IrNoneType,
    )
    from lexic.ir.walk import (
        IrBottomUp,
        IrDispatch,
        IrEmitter,
        IrTransformer,
        IrVisitor,
    )

__all__ = [
    "Borg",
    "DyadicOp",
    "EscapeCodec",
    "Field",
    "IR_DEFAULT",
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
    "BIND_MODES",
    "IrBind",
    "IrBottomUp",
    "IrBounds",
    "IrBuild",
    "IrCachingTuple",
    "IrCat",
    "IrCharClass",
    "IrChild",
    "IrChildren",
    "IrChr",
    "IrCompare",
    "IrConcat",
    "IrCond",
    "IrDispatch",
    "IrDoc",
    "IrDocConcat",
    "IrDocJoin",
    "IrEach",
    "IrEmit",
    "IrEmitter",
    "IrEncoding",
    "IrEq",
    "IrEscape",
    "IrEscapePoint",
    "IrField",
    "IrFlavour",
    "IrGlyph",
    "IrGroup",
    "IrIndex",
    "IrInt",
    "IrIsA",
    "IrItem",
    "IrJoin",
    "IrLambda",
    "IrLeaf",
    "IrLen",
    "IrLine",
    "IrLiteral",
    "IrLongestMatch",
    "IrMap",
    "IrMapping",
    "IrMerge",
    "IrMeta",
    "IrMultiMap",
    "IrNamedTuple",
    "IrNest",
    "IrNode",
    "IrNone",
    "IrNoneType",
    "IrNormalizer",
    "IrNot",
    "IrOp",
    "IrOpNode",
    "IrOrd",
    "IrPass",
    "IrPipe",
    "IrPretoken",
    "IrQuantifier",
    "IrRadix",
    "IrRaise",
    "IrRange",
    "IrRankedMerge",
    "IrRebuild",
    "IrReplace",
    "IrReturn",
    "IrRule",
    "IrRuleRef",
    "IrScalar",
    "IrSegmenter",
    "IrSelf",
    "IrSeq",
    "IrSequence",
    "IrSingleton",
    "IrSpellable",
    "IrStr",
    "IrText",
    "IrThis",
    "IrTokenPipeline",
    "IrTokenizer",
    "IrTransformer",
    "IrTuple",
    "IrTypeMap",
    "IrUnicode",
    "IrUnicodeForm",
    "IrUnknown",
    "IrUnradix",
    "IrUtf",
    "IrVisitor",
    "IrWalk",
    "MAX_CODEPOINT",
    "Merges",
    "MonadicOp",
    "RuleOrder",
    "Sheet",
    "Singleton",
    "UnicodeForm",
    "VariadicOp",
    "Vocab",
    "as_doc",
    "canonicalize",
    "concretize",
    "concretize_atom",
    "fold_name",
    "order_by_refs",
    "refs_in_order",
    "render",
    "rule_closure",
]

_HOMES = {
    "Borg": "lexic.ir.meta",
    "DyadicOp": "lexic.ir.operators",
    "EscapeCodec": "lexic.ir.escapes",
    "Field": "lexic.ir.records",
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
    "IrAtom": "lexic.ir.spine",
    "BIND_MODES": "lexic.ir.bind",
    "IrBind": "lexic.ir.bind",
    "IrBottomUp": "lexic.ir.walk",
    "IrBounds": "lexic.ir.nodes",
    "IrBuild": "lexic.ir.action",
    "IrCachingTuple": "lexic.ir.records",
    "IrCat": "lexic.ir.layout",
    "IrCharClass": "lexic.ir.nodes",
    "IrChild": "lexic.ir.action",
    "IrChildren": "lexic.ir.action",
    "IrChr": "lexic.ir.scalars",
    "IrCompare": "lexic.ir.action",
    "IrConcat": "lexic.ir.action",
    "IrCond": "lexic.ir.action",
    "IrDispatch": "lexic.ir.walk",
    "IrDoc": "lexic.ir.layout",
    "IrDocConcat": "lexic.ir.layout",
    "IrDocJoin": "lexic.ir.layout",
    "IrEach": "lexic.ir.action",
    "IrEmit": "lexic.ir.action",
    "IrEmitter": "lexic.ir.walk",
    "IrEncoding": "lexic.ir.encoding",
    "IrEq": "lexic.ir.operators",
    "IrEscape": "lexic.ir.flavour",
    "IrEscapePoint": "lexic.ir.flavour",
    "IrField": "lexic.ir.action",
    "IrFlavour": "lexic.ir.flavour",
    "IrGlyph": "lexic.ir.action",
    "IrGroup": "lexic.ir.layout",
    "IrIndex": "lexic.ir.action",
    "IrInt": "lexic.ir.scalars",
    "IrIsA": "lexic.ir.action",
    "IrItem": "lexic.ir.nodes",
    "IrJoin": "lexic.ir.action",
    "IrLambda": "lexic.ir.spine",
    "IrLeaf": "lexic.ir.spine",
    "IrLen": "lexic.ir.action",
    "IrLine": "lexic.ir.layout",
    "IrLiteral": "lexic.ir.nodes",
    "IrLongestMatch": "lexic.ir.encoding",
    "IrMap": "lexic.ir.mapping",
    "IrMapping": "lexic.ir.mapping",
    "IrMerge": "lexic.ir.action",
    "IrMeta": "lexic.ir.meta",
    "IrMultiMap": "lexic.ir.mapping",
    "IrNamedTuple": "lexic.ir.records",
    "IrNest": "lexic.ir.layout",
    "IrNode": "lexic.ir.spine",
    "IrNone": "lexic.ir.spine",
    "IrNoneType": "lexic.ir.spine",
    "IrNormalizer": "lexic.ir.encoding",
    "IrNot": "lexic.ir.operators",
    "IrOp": "lexic.ir.operators",
    "IrOpNode": "lexic.ir.operators",
    "IrOrd": "lexic.ir.action",
    "IrPass": "lexic.ir.action",
    "IrPipe": "lexic.ir.action",
    "IrPretoken": "lexic.ir.encoding",
    "IrQuantifier": "lexic.ir.nodes",
    "IrRadix": "lexic.ir.action",
    "IrRaise": "lexic.ir.action",
    "IrRange": "lexic.ir.nodes",
    "IrRankedMerge": "lexic.ir.encoding",
    "IrRebuild": "lexic.ir.action",
    "IrReplace": "lexic.ir.encoding",
    "IrReturn": "lexic.ir.action",
    "IrRule": "lexic.ir.nodes",
    "IrRuleRef": "lexic.ir.nodes",
    "IrScalar": "lexic.ir.scalars",
    "IrSegmenter": "lexic.ir.encoding",
    "IrSelf": "lexic.ir.spine",
    "IrSeq": "lexic.ir.records",
    "IrSequence": "lexic.ir.nodes",
    "IrSingleton": "lexic.ir.meta",
    "IrSpellable": "lexic.ir.flavour",
    "IrStr": "lexic.ir.scalars",
    "IrText": "lexic.ir.layout",
    "IrThis": "lexic.ir.action",
    "IrTokenPipeline": "lexic.ir.encoding",
    "IrTokenizer": "lexic.ir.encoding",
    "IrTransformer": "lexic.ir.walk",
    "IrTuple": "lexic.ir.records",
    "IrTypeMap": "lexic.ir.mapping",
    "IrUnicode": "lexic.ir.encoding",
    "IrUnicodeForm": "lexic.ir.encoding",
    "IrUnknown": "lexic.ir.encoding",
    "IrUnradix": "lexic.ir.action",
    "IrUtf": "lexic.ir.encoding",
    "IrVisitor": "lexic.ir.walk",
    "IrWalk": "lexic.ir.action",
    "MAX_CODEPOINT": "lexic.ir.nodes",
    "Merges": "lexic.ir.encoding",
    "MonadicOp": "lexic.ir.operators",
    "RuleOrder": "lexic.ir.order",
    "Sheet": "lexic.ir.layout",
    "Singleton": "lexic.ir.meta",
    "UnicodeForm": "lexic.ir.encoding",
    "VariadicOp": "lexic.ir.operators",
    "Vocab": "lexic.ir.encoding",
    "as_doc": "lexic.ir.layout",
    "canonicalize": "lexic.ir.canonical",
    "fold_name": "lexic.ir.canonical",
    "order_by_refs": "lexic.ir.order",
    "refs_in_order": "lexic.ir.order",
    "render": "lexic.ir.layout",
    "rule_closure": "lexic.ir.order",
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
