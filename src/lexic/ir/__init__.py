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
from lexic.ir.builder import IRBuilder
from lexic.ir.charclass import parse_charclass_chars
from lexic.ir.classify import classify_rule
from lexic.ir.emit import FlavourEmitter
from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.protocols import (
    AtomEmitHandler,
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
from lexic.ir.topo import topo_sort

__all__ = [
    "AlternationAtom",
    "Atom",
    "AtomEmitHandler",
    "CANONICAL_ESCAPES",
    "CharClassAtom",
    "classify_rule",
    "EscapeCodec",
    "FieldHandler",
    "FlavourAdapter",
    "FlavourEmitter",
    "FlavourParser",
    "HelperRuleRegistry",
    "InlineAlternationAtom",
    "InlineRegexAtom",
    "IRBuilder",
    "LarkHandler",
    "LiteralAtom",
    "parse_charclass_chars",
    "QuantifiedLiteralAtom",
    "RuleClassifier",
    "RuleRefAtom",
    "RuleSpec",
    "SequenceConverter",
    "topo_sort",
    "ToTextHandler",
    "TransformHandler",
]
