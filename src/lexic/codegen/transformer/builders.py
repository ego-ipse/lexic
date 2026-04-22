"""FieldBuilder implementations per atom type.

Each builder is stateless; BuildContext is frozen and passed in. Task 9
fills in the real behaviour.
"""

from __future__ import annotations

from lexic.codegen.transformer.context import (
    BuildContext,
    BuildResult,
)


class LiteralSkipBuilder:
    """LiteralAtoms are never fields; this builder is never called."""

    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise AssertionError("LiteralSkipBuilder should never be invoked")


class CharClassFieldBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise NotImplementedError


class QuantifiedLiteralBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise NotImplementedError


class InlineRegexBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise NotImplementedError


class RuleRefBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise NotImplementedError


class InlineAlternationBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise NotImplementedError


class AbstractAlternationBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise AssertionError("AbstractAlternationBuilder handled at orchestrator level")
