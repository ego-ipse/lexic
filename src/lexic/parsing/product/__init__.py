"""The product ABI — one compiled program both engines execute.

``ModelFold``'s ``value_str``/``sequence``/``alternation`` vocabulary made the
generated model the engine's privileged construction shape. This package is
the generalisation: a :class:`~lexic.parsing.product.records.ProductProgram`
says what each contextual rule captures and how it completes, and building a
generated model becomes one specialisation of that rather than the thing every
other target has to be expressed in terms of.

Four modules, one job each:

``records``
    The immutable authored operations and the flat int-coded tables they lower
    to. Nothing executes.
``state``
    Everything mutable in one parse: occurrence-owned builders, deferred
    verdicts, and constant-size transaction marks.
``verify``
    The cold gate. Every physical table passes it before the paid loop starts.
``expressions``
    The reducer's own algebra in authored form, its own layer because it
    lowers into its own table.
``regular``
    The authoritative regular-language proof — when a possessive recognizer
    may decide a region outright.
``tree``
    Product-driven ParseTree completion, explicit result presence, and exact
    source-span derivation.

This module is the package's one import surface. Nothing outside reaches into
a submodule, so the package can be rearranged without a second import path
appearing. The whole package is a leaf with respect to the rest of lexic: it
imports :mod:`lexic.ir`, :mod:`lexic.exceptions`, and the ``pda`` leaves that
already own character sets and possessive lowering — never ``lexic.compile``,
``lexic.grammars`` or ``lexic.api``.
"""

from __future__ import annotations

from lexic.parsing.product.expressions import (
    ArgExpr,
    ArgsExpr,
    BuildExpr,
    CondExpr,
    ConstantExpr,
    ContributeExpr,
    ExprCode,
    ExprOp,
    ExprProgram,
    JoinExpr,
    LookupExpr,
    PipeExpr,
    RaiseExpr,
    SymbolExpr,
)
from lexic.parsing.product.records import (
    CAPTURE_FOR_BIND,
    AppendSequenceOp,
    BeginMappingOp,
    BeginSequenceOp,
    BoundSymbol,
    CaptureMode,
    CaptureSpec,
    CompletionRange,
    ConstantOp,
    Construction,
    ConstructionTables,
    construction_of,
    DecodeCode,
    DecodeOp,
    Extent,
    FinishMappingOp,
    FinishSequenceOp,
    FlatRuleProduct,
    FragmentProduct,
    InsertMappingOp,
    LoweredRoute,
    MappingFinisher,
    MeaningComparator,
    MeaningOp,
    OpCode,
    OperandTables,
    PassOp,
    ProductOp,
    ProductValue,
    ProductProgram,
    RangeKind,
    RecordConstructor,
    RecordOp,
    RootFinalizer,
    RootOp,
    RouteContinuation,
    RouteOp,
    RouteTable,
    RuleBody,
    RuleCompletion,
    RuleProduct,
    SequenceFinisher,
    SingletonRoute,
    SymbolConstructor,
    TableRoute,
    UniformRoute,
    ValidateOp,
)
from lexic.parsing.product.regular import RegularProof, prove_regular
from lexic.parsing.product.state import (
    MAPPING_INSERT,
    MAPPING_REPLACE,
    SEQUENCE_APPEND,
    MappingHandle,
    ParseState,
    ProductMark,
    SequenceHandle,
)
from lexic.parsing.product.tree import (
    Completed,
    CompletionResult,
    EMPTY_RESULT,
    EmptyResult,
    ProductExecutor,
    ResultMemo,
    collapsed_product_tables,
    complete_product,
    run_ok,
    slot_span,
    subtree_text,
    tree_offsets,
)
from lexic.parsing.product.verify import verify_exact_ints, verify_program

__all__ = [
    # records — authored operations
    "PassOp",
    "ConstantOp",
    "DecodeOp",
    "RouteOp",
    "ValidateOp",
    "BeginSequenceOp",
    "AppendSequenceOp",
    "FinishSequenceOp",
    "BeginMappingOp",
    "InsertMappingOp",
    "FinishMappingOp",
    "RecordOp",
    "RecordConstructor",
    "SymbolConstructor",
    "BoundSymbol",
    "Construction",
    "ConstructionTables",
    "construction_of",
    "MeaningOp",
    "RootOp",
    "RuleCompletion",
    "ProductOp",
    "ProductValue",
    "Completed",
    "CompletionResult",
    "EmptyResult",
    "EMPTY_RESULT",
    "ResultMemo",
    "ProductExecutor",
    "complete_product",
    "collapsed_product_tables",
    "run_ok",
    "subtree_text",
    "tree_offsets",
    "slot_span",
    # records — the reducer-expression layer
    "ExprCode",
    "ExprOp",
    "ExprProgram",
    "RuleBody",
    "ArgExpr",
    "ArgsExpr",
    "ConstantExpr",
    "JoinExpr",
    "BuildExpr",
    "PipeExpr",
    "CondExpr",
    "LookupExpr",
    "RaiseExpr",
    "ContributeExpr",
    "SymbolExpr",
    # records — lowered routes
    "LoweredRoute",
    "UniformRoute",
    "SingletonRoute",
    "TableRoute",
    # records — vocabularies and layout
    "CAPTURE_FOR_BIND",
    "CaptureMode",
    "CaptureSpec",
    "DecodeCode",
    "OpCode",
    "RangeKind",
    "Extent",
    "RuleProduct",
    "FlatRuleProduct",
    "CompletionRange",
    "RouteTable",
    "RouteContinuation",
    "OperandTables",
    "ProductProgram",
    "FragmentProduct",
    "SequenceFinisher",
    "MappingFinisher",
    "MeaningComparator",
    "RootFinalizer",
    # state
    "ParseState",
    "ProductMark",
    "SequenceHandle",
    "MappingHandle",
    "SEQUENCE_APPEND",
    "MAPPING_INSERT",
    "MAPPING_REPLACE",
    # verify
    "verify_program",
    "verify_exact_ints",
    # regular
    "RegularProof",
    "prove_regular",
]
