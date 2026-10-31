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

REVISIT ON 3.15 — PEP 810 (explicit lazy imports) is not on 3.14. If it lands,
this file collapses back to plain ``lazy from … import …`` lines, and the group
surfaces, ``_HOMES``, ``__getattr__`` and the drift pins all go away. Wait for a
RELEASE, not a beta.
"""

from importlib import import_module
from typing import TYPE_CHECKING

from lexic.ir import action, grammar, spine, text

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
    from lexic.ir.action.flow.compute import (
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
    from lexic.ir.action.flow.control import (
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
    from lexic.ir.grammar.charclass import MAX_CODEPOINT, IrCharClass, IrRange
    from lexic.ir.grammar.graph import (
        callees,
        components,
        cyclic,
        has_reference,
        reach,
        reachable,
        reaching,
        references,
        refs_in_order,
    )
    from lexic.ir.grammar.nodes import (
        IrAlphabet,
        IrAlternation,
        IrAst,
        IrBounds,
        IrItem,
        IrLiteral,
        IrQuantifier,
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
    from lexic.ir.grammar.transform.alignment import (
        CANDIDATE_CAP,
        IrAlignment,
        IrRename,
        IrRenaming,
        IrRenamings,
        align_names,
    )
    from lexic.ir.grammar.transform.canonical import (
        canonicalize,
        fold_name,
        inline_refs,
    )
    from lexic.ir.grammar.transform.order import (
        RuleOrder,
        order_by_refs,
        rule_closure,
    )
    from lexic.ir.identity import (
        IrCensus,
        IrIdentity,
        census,
        field_children,
        unspellable,
    )
    from lexic.ir.reduction import (
        DEFERRED_FAILURE,
        DROP,
        EXACT_MEANING,
        FIRST_DUPLICATE,
        IMMEDIATE_FAILURE,
        KEEP_RAW,
        KEEP_REDUCED,
        LAST_DUPLICATE,
        REFUSE_DUPLICATE,
        SHARED_MEANING,
        SORT_ABSENCE,
        SORT_COMPLETION,
        SORT_ENTRY,
        SORT_FRACTION,
        SORT_INTEGER,
        SORT_ITEM,
        SORT_MAPPING,
        SORT_SEQUENCE,
        SORT_TEXT,
        SORT_TRUTH,
        YIELD,
        AcceptingState,
        Drop,
        DuplicatePolicy,
        EntryRoute,
        ExtensionRoute,
        FailureOrder,
        KeepRaw,
        KeepReduced,
        KnownRoute,
        MeaningLaw,
        PoisonedState,
        RecoveryState,
        Reducer,
        SchemaCheck,
        SchemaChecks,
        SchemaRoute,
        SchemaRoutes,
        SchemaState,
        SemanticSignature,
        SemanticSort,
        TargetSchema,
        Yield,
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
        Bound,
        Field,
        IrCachingTuple,
        IrNamedTuple,
        IrSeq,
        IrTuple,
        is_plain_tuple,
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
    from lexic.ir.text.codec.encodings import (
        IrEncoding,
        IrUnicode,
        IrUtf,
        Merges,
        Vocab,
    )
    from lexic.ir.text.codec.escapes import (
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
    "Bound",
    "AcceptingState",
    "Borg",
    "CANDIDATE_CAP",
    "DEFERRED_FAILURE",
    "DyadicOp",
    "DROP",
    "Drop",
    "DuplicatePolicy",
    "EXACT_MEANING",
    "EntryRoute",
    "EscapeCodec",
    "ExtensionRoute",
    "FIRST_DUPLICATE",
    "FailureOrder",
    "Field",
    "IMMEDIATE_FAILURE",
    "IR_DEFAULT",
    "IrAction",
    "IrAddress",
    "IrAlignment",
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
    "IrCensus",
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
    "IrIdentity",
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
    "IrRename",
    "IrRenaming",
    "IrRenamings",
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
    "KEEP_RAW",
    "KEEP_REDUCED",
    "KnownRoute",
    "LAST_DUPLICATE",
    "MAX_CODEPOINT",
    "MeaningLaw",
    "Merges",
    "MonadicOp",
    "PoisonedState",
    "REFUSE_DUPLICATE",
    "RecoveryState",
    "RuleOrder",
    "Reducer",
    "SHARED_MEANING",
    "SORT_ABSENCE",
    "SORT_COMPLETION",
    "SORT_ENTRY",
    "SORT_FRACTION",
    "SORT_INTEGER",
    "SORT_ITEM",
    "SORT_MAPPING",
    "SORT_SEQUENCE",
    "SORT_TEXT",
    "SORT_TRUTH",
    "SchemaCheck",
    "SchemaChecks",
    "SchemaRoute",
    "SchemaRoutes",
    "SchemaState",
    "SemanticSignature",
    "SemanticSort",
    "Sheet",
    "Singleton",
    "TargetSchema",
    "UnicodeForm",
    "VariadicOp",
    "Vocab",
    "YIELD",
    "Yield",
    "KeepRaw",
    "KeepReduced",
    "align_names",
    "as_doc",
    "callees",
    "canonicalize",
    "census",
    "components",
    "concretize",
    "concretize_atom",
    "cyclic",
    "field_children",
    "fold_name",
    "has_reference",
    "inline_refs",
    "is_plain_tuple",
    "order_by_refs",
    "reach",
    "reachable",
    "reaching",
    "references",
    "refs_in_order",
    "render",
    "rule_closure",
    "unspellable",
]

_SURFACE: dict[str, str] = {
    "IrEscape": "lexic.ir.flavour",
    "IrEscapePoint": "lexic.ir.flavour",
    "IrFlavour": "lexic.ir.flavour",
    "IrSpellable": "lexic.ir.flavour",
    "IrCensus": "lexic.ir.identity",
    "IrIdentity": "lexic.ir.identity",
    "census": "lexic.ir.identity",
    "field_children": "lexic.ir.identity",
    "unspellable": "lexic.ir.identity",
    "DEFERRED_FAILURE": "lexic.ir.reduction",
    "DROP": "lexic.ir.reduction",
    "EXACT_MEANING": "lexic.ir.reduction",
    "FIRST_DUPLICATE": "lexic.ir.reduction",
    "IMMEDIATE_FAILURE": "lexic.ir.reduction",
    "KEEP_RAW": "lexic.ir.reduction",
    "KEEP_REDUCED": "lexic.ir.reduction",
    "LAST_DUPLICATE": "lexic.ir.reduction",
    "REFUSE_DUPLICATE": "lexic.ir.reduction",
    "SHARED_MEANING": "lexic.ir.reduction",
    "SORT_ABSENCE": "lexic.ir.reduction",
    "SORT_COMPLETION": "lexic.ir.reduction",
    "SORT_ENTRY": "lexic.ir.reduction",
    "SORT_FRACTION": "lexic.ir.reduction",
    "SORT_INTEGER": "lexic.ir.reduction",
    "SORT_ITEM": "lexic.ir.reduction",
    "SORT_MAPPING": "lexic.ir.reduction",
    "SORT_SEQUENCE": "lexic.ir.reduction",
    "SORT_TEXT": "lexic.ir.reduction",
    "SORT_TRUTH": "lexic.ir.reduction",
    "YIELD": "lexic.ir.reduction",
    "AcceptingState": "lexic.ir.reduction",
    "Drop": "lexic.ir.reduction",
    "DuplicatePolicy": "lexic.ir.reduction",
    "EntryRoute": "lexic.ir.reduction",
    "ExtensionRoute": "lexic.ir.reduction",
    "FailureOrder": "lexic.ir.reduction",
    "KeepRaw": "lexic.ir.reduction",
    "KeepReduced": "lexic.ir.reduction",
    "KnownRoute": "lexic.ir.reduction",
    "MeaningLaw": "lexic.ir.reduction",
    "PoisonedState": "lexic.ir.reduction",
    "RecoveryState": "lexic.ir.reduction",
    "Reducer": "lexic.ir.reduction",
    "SchemaCheck": "lexic.ir.reduction",
    "SchemaChecks": "lexic.ir.reduction",
    "SchemaRoute": "lexic.ir.reduction",
    "SchemaRoutes": "lexic.ir.reduction",
    "SchemaState": "lexic.ir.reduction",
    "SemanticSignature": "lexic.ir.reduction",
    "SemanticSort": "lexic.ir.reduction",
    "TargetSchema": "lexic.ir.reduction",
    "Yield": "lexic.ir.reduction",
}
"""The surface of the package's own direct modules, in the groups' shape — the
façade is the marker of that level."""

_HOMES = _SURFACE | spine.SURFACE | action.SURFACE | grammar.SURFACE | text.SURFACE
"""Every LAZY export and the module that defines it — where ``__getattr__`` looks.
Derived, never stated: each group marker says where its own names live, as
plain data the marker costs nothing to hold. ``concretize``/``concretize_atom``
are absent because they are bound eagerly above, for the name-collision reason
stated there.

The surface is stated twice here, once per tool that reads only a literal: the
``TYPE_CHECKING`` block for the type checker, ``__all__`` for ruff and the export
machinery. Neither can be derived on 3.14 — ruff reads no other module's
``__all__``, and the star re-export the type checker would accept is F403. The
drift pins in ``test_init_ir`` hold both to the surfaces, so a name joins the
façade only by joining all three."""


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
