"""Public IR surface — import everything from here."""

from lexic.ir.charclass import parse_charclass_chars
from lexic.ir.derive import (
    classify_kind,
    compute_parents,
    derive_specs,
    has_ruleref,
    hoist_helpers,
)
from lexic.ir.directives import Directives, parse_directives
from lexic.ir.emit import FlavourEmitter
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
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSequence,
    IrStructure,
    IrSuperSet,
    Quantifier,
)
from lexic.ir.spec import RuleSpec
from lexic.ir.topo import topo_sort
from lexic.ir.walk import IrTransformer, IrVisitor

__all__ = [
    "CANONICAL_ESCAPES",
    "Directives",
    "EscapeCodec",
    "FlavourEmitter",
    "HelperRuleRegistry",
    "IrAlternation",
    "IrAst",
    "IrAtom",
    "IrCharClass",
    "IrCollection",
    "IrComposite",
    "IrGroup",
    "IrItem",
    "IrLeaf",
    "IrLiteral",
    "IrNode",
    "IrNone",
    "IrRule",
    "IrRuleRef",
    "IrSelf",
    "IrSequence",
    "IrStructure",
    "IrSuperSet",
    "IrTransformer",
    "IrVisitor",
    "Quantifier",
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
