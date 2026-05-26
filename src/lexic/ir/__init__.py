"""Public IR surface — import everything from here."""

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
)
from lexic.ir.charclass import parse_charclass_chars
from lexic.ir.derive import (
    classify_kind,
    compute_parents,
    derive_specs,
    has_ruleref,
    hoist_helpers,
)
from lexic.ir.directives import Directives, parse_directives
from lexic.ir.emit import render_specs
from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrAtom,
    IrCharClass,
    IrCollection,
    IrComposite,
    IrGroup,
    IrItem,
    IrLeaf,
    IrLiteral,
    IrNode,
    IrNone,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSequence,
    IrStructure,
    IrSuperSet,
)
from lexic.ir.spec import RuleSpec
from lexic.ir.topo import topo_sort
from lexic.ir.walk import IrTransformer, IrVisitor

__all__ = [
    "CANONICAL_ESCAPES",
    "Directives",
    "EscapeCodec",
    "render_specs",
    "HelperRuleRegistry",
    "IrAction",
    "IrAlternation",
    "IrAst",
    "IrAtom",
    "IrCallable",
    "IrCharClass",
    "IrChild",
    "IrChildren",
    "IrCollection",
    "IrComposite",
    "IrConcat",
    "IrCond",
    "IrField",
    "IrGroup",
    "IrItem",
    "IrJoin",
    "IrLeaf",
    "IrLiteral",
    "IrNode",
    "IrNone",
    "IrNot",
    "IrReturn",
    "IrRule",
    "IrRuleRef",
    "IrSelf",
    "IrSequence",
    "IrStructure",
    "IrSuperSet",
    "IrTransformer",
    "IrVisitor",
    "IrQuantifier",
    "RuleSpec",
    "classify_kind",
    "compute_parents",
    "derive_specs",
    "has_ruleref",
    "hoist_helpers",
    "parse_charclass_chars",
    "parse_directives",
    "topo_sort",
]
