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
# `lexic.ir.grammar.concretize`, so the moment anything imports the module the attribute
# exists and `__getattr__` — which Python only calls on a MISS — never runs,
# handing a caller the module instead of the function. Binding it here is the
# same collision the package root has with `generate`, and no import mechanism
# resolves two things wanting one name.
from lexic.ir.grammar.concretize import concretize, concretize_atom
from lexic.ir.spine.spine import IrSelf

if TYPE_CHECKING:
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
        IrBuild,
        IrEmit,
        IrRaise,
        IrRebuild,
        IrWalk,
    )
    from lexic.ir.action.compute import (
        IrCompare,
        IrConcat,
        IrGlyph,
        IrIsA,
        IrJoin,
        IrMerge,
        IrOrd,
        IrRadix,
        IrUnradix,
    )
    from lexic.ir.action.control import (
        IrCond,
        IrEach,
        IrPass,
        IrPipe,
        IrReturn,
        IrThis,
    )
    from lexic.ir.action.mapping import (
        IR_DEFAULT,
        IrMap,
        IrMapping,
        IrMultiMap,
        IrTypeMap,
    )
    from lexic.ir.action.walk import (
        IrBottomUp,
        IrDispatch,
        IrEmitter,
        IrTransformer,
        IrVisitor,
    )
    from lexic.ir.flavour import (
        IrEscape,
        IrEscapePoint,
        IrFlavour,
        IrSpellable,
    )
    from lexic.ir.grammar.canonical import (
        canonicalize,
        fold_name,
    )
    from lexic.ir.grammar.nodes import (
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
    from lexic.ir.grammar.operators import (
        DyadicOp,
        IrAnd,
        IrEq,
        IrNot,
        IrOp,
        IrOpNode,
        MonadicOp,
        VariadicOp,
    )
    from lexic.ir.grammar.order import (
        RuleOrder,
        order_by_refs,
        refs_in_order,
        rule_closure,
    )
    from lexic.ir.spine.bind import (
        BIND_MODES,
        IrBind,
    )
    from lexic.ir.spine.meta import (
        Borg,
        IrMeta,
        IrSingleton,
        Singleton,
    )
    from lexic.ir.spine.records import (
        Field,
        IrCachingTuple,
        IrNamedTuple,
        IrSeq,
        IrTuple,
    )
    from lexic.ir.spine.scalars import (
        IrChr,
        IrInt,
        IrScalar,
        IrStr,
    )
    from lexic.ir.spine.spine import (
        IrAtom,
        IrLambda,
        IrLeaf,
        IrNode,
        IrNone,
        IrNoneType,
    )
    from lexic.ir.text.encodings import (
        IrEncoding,
        IrUnicode,
        IrUtf,
        Merges,
        Vocab,
    )
    from lexic.ir.text.escapes import (
        EscapeCodec,
    )
    from lexic.ir.text.layout import (
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
    from lexic.ir.text.pipeline import (
        IrNormalizer,
        IrPretoken,
        IrReplace,
        IrTokenPipeline,
        IrUnicodeForm,
        IrUnknown,
        UnicodeForm,
        WMeta,
        identity_meta,
    )
    from lexic.ir.text.spans import (
        IrAddress,
        IrEmission,
        IrExtent,
        IrExtents,
        IrOrigin,
        IrOrigins,
        IrSpan,
        IrStep,
    )
    from lexic.ir.text.tokenizer import (
        IrLongestMatch,
        IrRankedMerge,
        IrSegmenter,
        IrTokenizer,
    )

__all__ = [
    "Borg",
    "DyadicOp",
    "EscapeCodec",
    "Field",
    "IR_DEFAULT",
    "IrAction",
    "IrAddress",
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
    "IrEmission",
    "IrEmit",
    "IrEmitter",
    "IrEncoding",
    "IrEq",
    "IrEscape",
    "IrEscapePoint",
    "IrExtent",
    "IrExtents",
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
    "IrOrigin",
    "IrOrigins",
    "IrPass",
    "IrPipe",
    "WMeta",
    "identity_meta",
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
    "IrSpan",
    "IrSpellable",
    "IrStep",
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
    "Borg": "lexic.ir.spine.meta",
    "DyadicOp": "lexic.ir.grammar.operators",
    "EscapeCodec": "lexic.ir.text.escapes",
    "Field": "lexic.ir.spine.records",
    "IR_DEFAULT": "lexic.ir.action.mapping",
    "IrAction": "lexic.ir.action.build",
    "IrAddress": "lexic.ir.text.spans",
    "IrAlphabet": "lexic.ir.grammar.nodes",
    "IrAlternation": "lexic.ir.grammar.nodes",
    "IrAnd": "lexic.ir.grammar.operators",
    "IrApply": "lexic.ir.action.build",
    "IrArg": "lexic.ir.action.access",
    "IrArgs": "lexic.ir.action.access",
    "IrAst": "lexic.ir.grammar.nodes",
    "IrAt": "lexic.ir.action.access",
    "IrAtom": "lexic.ir.spine.spine",
    "BIND_MODES": "lexic.ir.spine.bind",
    "IrBind": "lexic.ir.spine.bind",
    "IrBottomUp": "lexic.ir.action.walk",
    "IrBounds": "lexic.ir.grammar.nodes",
    "IrBuild": "lexic.ir.action.build",
    "IrCachingTuple": "lexic.ir.spine.records",
    "IrCat": "lexic.ir.text.layout",
    "IrCharClass": "lexic.ir.grammar.nodes",
    "IrChild": "lexic.ir.action.access",
    "IrChildren": "lexic.ir.action.access",
    "IrChr": "lexic.ir.spine.scalars",
    "IrCompare": "lexic.ir.action.compute",
    "IrConcat": "lexic.ir.action.compute",
    "IrCond": "lexic.ir.action.control",
    "IrDispatch": "lexic.ir.action.walk",
    "IrDoc": "lexic.ir.text.layout",
    "IrDocConcat": "lexic.ir.text.layout",
    "IrDocJoin": "lexic.ir.text.layout",
    "IrEach": "lexic.ir.action.control",
    "IrEmission": "lexic.ir.text.spans",
    "IrEmit": "lexic.ir.action.build",
    "IrEmitter": "lexic.ir.action.walk",
    "IrEncoding": "lexic.ir.text.encodings",
    "IrEq": "lexic.ir.grammar.operators",
    "IrEscape": "lexic.ir.flavour",
    "IrEscapePoint": "lexic.ir.flavour",
    "IrExtent": "lexic.ir.text.spans",
    "IrExtents": "lexic.ir.text.spans",
    "IrField": "lexic.ir.action.access",
    "IrFlavour": "lexic.ir.flavour",
    "IrGlyph": "lexic.ir.action.compute",
    "IrGroup": "lexic.ir.text.layout",
    "IrIndex": "lexic.ir.action.access",
    "IrInt": "lexic.ir.spine.scalars",
    "IrIsA": "lexic.ir.action.compute",
    "IrItem": "lexic.ir.grammar.nodes",
    "IrJoin": "lexic.ir.action.compute",
    "IrLambda": "lexic.ir.spine.spine",
    "IrLeaf": "lexic.ir.spine.spine",
    "IrLen": "lexic.ir.action.access",
    "IrLine": "lexic.ir.text.layout",
    "IrLiteral": "lexic.ir.grammar.nodes",
    "IrLongestMatch": "lexic.ir.text.tokenizer",
    "IrMap": "lexic.ir.action.mapping",
    "IrMapping": "lexic.ir.action.mapping",
    "IrMerge": "lexic.ir.action.compute",
    "IrMeta": "lexic.ir.spine.meta",
    "IrMultiMap": "lexic.ir.action.mapping",
    "IrNamedTuple": "lexic.ir.spine.records",
    "IrNest": "lexic.ir.text.layout",
    "IrNode": "lexic.ir.spine.spine",
    "IrNone": "lexic.ir.spine.spine",
    "IrNoneType": "lexic.ir.spine.spine",
    "IrNormalizer": "lexic.ir.text.pipeline",
    "IrNot": "lexic.ir.grammar.operators",
    "IrOp": "lexic.ir.grammar.operators",
    "IrOpNode": "lexic.ir.grammar.operators",
    "IrOrd": "lexic.ir.action.compute",
    "IrOrigin": "lexic.ir.text.spans",
    "IrOrigins": "lexic.ir.text.spans",
    "IrPass": "lexic.ir.action.control",
    "IrPipe": "lexic.ir.action.control",
    "WMeta": "lexic.ir.text.pipeline",
    "identity_meta": "lexic.ir.text.pipeline",
    "IrPretoken": "lexic.ir.text.pipeline",
    "IrQuantifier": "lexic.ir.grammar.nodes",
    "IrRadix": "lexic.ir.action.compute",
    "IrRaise": "lexic.ir.action.build",
    "IrRange": "lexic.ir.grammar.nodes",
    "IrRankedMerge": "lexic.ir.text.tokenizer",
    "IrRebuild": "lexic.ir.action.build",
    "IrReplace": "lexic.ir.text.pipeline",
    "IrReturn": "lexic.ir.action.control",
    "IrRule": "lexic.ir.grammar.nodes",
    "IrRuleRef": "lexic.ir.grammar.nodes",
    "IrScalar": "lexic.ir.spine.scalars",
    "IrSegmenter": "lexic.ir.text.tokenizer",
    "IrSelf": "lexic.ir.spine.spine",
    "IrSeq": "lexic.ir.spine.records",
    "IrSequence": "lexic.ir.grammar.nodes",
    "IrSingleton": "lexic.ir.spine.meta",
    "IrSpan": "lexic.ir.text.spans",
    "IrSpellable": "lexic.ir.flavour",
    "IrStep": "lexic.ir.text.spans",
    "IrStr": "lexic.ir.spine.scalars",
    "IrText": "lexic.ir.text.layout",
    "IrThis": "lexic.ir.action.control",
    "IrTokenPipeline": "lexic.ir.text.pipeline",
    "IrTokenizer": "lexic.ir.text.tokenizer",
    "IrTransformer": "lexic.ir.action.walk",
    "IrTuple": "lexic.ir.spine.records",
    "IrTypeMap": "lexic.ir.action.mapping",
    "IrUnicode": "lexic.ir.text.encodings",
    "IrUnicodeForm": "lexic.ir.text.pipeline",
    "IrUnknown": "lexic.ir.text.pipeline",
    "IrUnradix": "lexic.ir.action.compute",
    "IrUtf": "lexic.ir.text.encodings",
    "IrVisitor": "lexic.ir.action.walk",
    "IrWalk": "lexic.ir.action.build",
    "MAX_CODEPOINT": "lexic.ir.grammar.nodes",
    "Merges": "lexic.ir.text.encodings",
    "MonadicOp": "lexic.ir.grammar.operators",
    "RuleOrder": "lexic.ir.grammar.order",
    "Sheet": "lexic.ir.text.layout",
    "Singleton": "lexic.ir.spine.meta",
    "UnicodeForm": "lexic.ir.text.pipeline",
    "VariadicOp": "lexic.ir.grammar.operators",
    "Vocab": "lexic.ir.text.encodings",
    "as_doc": "lexic.ir.text.layout",
    "canonicalize": "lexic.ir.grammar.canonical",
    "fold_name": "lexic.ir.grammar.canonical",
    "order_by_refs": "lexic.ir.grammar.order",
    "refs_in_order": "lexic.ir.grammar.order",
    "render": "lexic.ir.text.layout",
    "rule_closure": "lexic.ir.grammar.order",
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
