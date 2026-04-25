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

__all__ = [
    "AlternationAtom",
    "Atom",
    "AtomEmitHandler",
    "CharClassAtom",
    "EscapeCodec",
    "FieldHandler",
    "FlavourAdapter",
    "FlavourParser",
    "HelperRuleRegistry",
    "InlineAlternationAtom",
    "InlineRegexAtom",
    "LarkHandler",
    "LiteralAtom",
    "QuantifiedLiteralAtom",
    "RuleClassifier",
    "RuleRefAtom",
    "RuleSpec",
    "SequenceConverter",
    "ToTextHandler",
    "TransformHandler",
]
