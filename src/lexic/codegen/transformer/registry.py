"""BUILDER_BY_ATOM dispatch table."""

from __future__ import annotations

from lexic.codegen.transformer.builders import (
    AbstractAlternationBuilder,
    CharClassFieldBuilder,
    InlineAlternationBuilder,
    InlineRegexBuilder,
    LiteralSkipBuilder,
    QuantifiedLiteralBuilder,
    RuleRefBuilder,
)
from lexic.codegen.transformer.context import FieldBuilder
from lexic.ir import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)

BUILDER_BY_ATOM: dict[type, FieldBuilder] = {
    LiteralAtom: LiteralSkipBuilder(),
    CharClassAtom: CharClassFieldBuilder(),
    QuantifiedLiteralAtom: QuantifiedLiteralBuilder(),
    InlineRegexAtom: InlineRegexBuilder(),
    RuleRefAtom: RuleRefBuilder(),
    InlineAlternationAtom: InlineAlternationBuilder(),
    AlternationAtom: AbstractAlternationBuilder(),
}


def builder_for(atom: Atom) -> FieldBuilder:
    builder = BUILDER_BY_ATOM.get(type(atom))
    if builder is None:
        raise ValueError(f"No builder registered for atom type {type(atom).__name__}")
    return builder
