"""Public IR surface — import everything from here."""

from lexic.ir.atoms import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.protocols import (
    AtomEmitHandler,
    EscapeCodec,
    FieldHandler,
    FlavourAdapter,
    FlavourParser,
    LarkHandler,
    RuleClassifier,
    SequenceConverter,
    ToTextHandler,
    TransformHandler,
)
from lexic.ir.spec import RuleSpec
from lexic.ir.builder import IRBuilder
from lexic.ir.classify import classify_rule
from lexic.ir.topo import topo_sort

__all__ = [
    "AlternationAtom",
    "Atom",
    "AtomEmitHandler",
    "CharClassAtom",
    "classify_rule",
    "EscapeCodec",
    "FieldHandler",
    "FlavourAdapter",
    "FlavourParser",
    "HelperRuleRegistry",
    "InlineAlternationAtom",
    "InlineRegexAtom",
    "IRBuilder",
    "LarkHandler",
    "LiteralAtom",
    "QuantifiedLiteralAtom",
    "RuleClassifier",
    "RuleRefAtom",
    "RuleSpec",
    "SequenceConverter",
    "topo_sort",
    "ToTextHandler",
    "TransformHandler",
]
