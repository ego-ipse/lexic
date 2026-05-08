"""FieldBuilder implementations per atom type.

Each builder is stateless; BuildContext is frozen and passed in. Task 9
fills in the real behaviour.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Union, get_args, get_origin

from lark import Token

from lexic.base import GrammarModel
from lexic.codegen.transformer.context import (
    SKIP_FIELD,
    BuildContext,
    BuildResult,
    FieldResult,
    SkipField,
)


class LiteralSkipBuilder:
    """LiteralAtoms are never fields; this builder is never called."""

    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise AssertionError("LiteralSkipBuilder should never be invoked")


class CharClassFieldBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        if ctx.exhausted():
            return FieldResult(value="", consumed=0)
        c = ctx.peek()
        if not isinstance(c, (Token, str)):
            return FieldResult(value="", consumed=0)
        if atom.max != 1:
            parts = [str(c)]
            i = ctx.cursor + 1
            while i < len(ctx.children) and isinstance(ctx.children[i], (Token, str)):
                parts.append(str(ctx.children[i]))
                i += 1
            return FieldResult(value="".join(parts), consumed=i - ctx.cursor)
        return FieldResult(value=str(c), consumed=1)


class QuantifiedLiteralBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        if ctx.exhausted():
            return FieldResult(value="", consumed=0)
        c = ctx.peek()
        if not isinstance(c, (Token, str)):
            return FieldResult(value="", consumed=0)
        return FieldResult(value=str(c), consumed=1)


class InlineRegexBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        if ctx.exhausted():
            return FieldResult(value="", consumed=0)
        c = ctx.peek()
        if not isinstance(c, (Token, str)):
            return FieldResult(value="", consumed=0)
        return FieldResult(value=str(c), consumed=1)


def _is_plain_type(hint) -> bool:
    """Return True only if hint is a plain class usable with isinstance()."""
    return isinstance(hint, type) and get_origin(hint) is None


def _unwrap_hint(hint):
    """Resolve a possibly-Optional/Union hint to its primary non-None type."""
    if hint is None or hint is str or _is_plain_type(hint):
        return hint
    origin = get_origin(hint)
    if origin is Union:
        non_none = [a for a in get_args(hint) if a is not type(None)]
        return non_none[0] if len(non_none) == 1 else hint
    return hint


class RuleRefBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raw_hint = ctx.hints.get(field_name)
        hint = _unwrap_hint(raw_hint)
        is_ws = atom.rule_name == "ws"

        if ctx.exhausted():
            if is_ws:
                # ws atom + no child → construct empty ws instance.
                # hint is always a concrete Ws subclass here; fall back only if
                # somehow it isn't so we at least return an empty string.
                if _is_plain_type(hint) and hint is not str:
                    return FieldResult(value=hint(value=""), consumed=0)  # type: ignore[call-arg]  # hint is a GrammarModel subclass narrowed by _is_plain_type guard; Pyright sees bare `type`
                return FieldResult(value="", consumed=0)
            # non-ws + no child
            if hint is str or hint is None or not _is_plain_type(hint):
                return FieldResult(value="", consumed=0)
            return SKIP_FIELD

        c = ctx.peek()

        if is_ws:
            # Only consume the child if it is actually a ws-compatible instance.
            # If the ws rule produced no token (empty ws), the next child belongs
            # to a different field — construct an empty instance and don't consume.
            if _is_plain_type(hint) and hint is not str and isinstance(c, hint):
                return FieldResult(value=c, consumed=1)
            if _is_plain_type(hint) and hint is not str:
                return FieldResult(value=hint(value=""), consumed=0)  # type: ignore[call-arg]  # hint is a GrammarModel subclass narrowed by _is_plain_type guard; Pyright sees bare `type`
            return FieldResult(value="", consumed=0)

        # non-ws with child present: only consume if child matches expected type
        if _is_plain_type(hint) and hint is not str:
            if isinstance(c, hint):
                return FieldResult(value=c, consumed=1)
            # Wrong type — don't consume; let caller handle Optional/default
            return SKIP_FIELD
        if isinstance(c, (Token, str)):
            return FieldResult(value=str(c), consumed=1)
        # Fallback: pass through whatever we got
        return FieldResult(value=c, consumed=1)


class InlineAlternationBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        if ctx.exhausted():
            return FieldResult(value="", consumed=0)
        c = ctx.peek()
        # If child is already a GrammarModel (built by a sub-rule), pass through.
        if isinstance(c, GrammarModel):
            return FieldResult(value=c, consumed=1)
        return FieldResult(value=str(c), consumed=1)


class AbstractAlternationBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise AssertionError("AbstractAlternationBuilder handled at orchestrator level")


class OptionalFieldBuilder:
    """Wraps inner builder; returns FieldResult(None, 0) when inner declines."""

    _EMPTY_VALUES: frozenset[object] = frozenset(("", None))

    def __init__(self, inner):
        self._inner = inner

    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        if ctx.exhausted():
            return FieldResult(value=None, consumed=0)
        result = self._inner.build(atom, field_name, ctx)
        if isinstance(result, SkipField):
            return FieldResult(value=None, consumed=0)
        if (
            isinstance(result, FieldResult)
            and result.consumed == 0
            and result.value in self._EMPTY_VALUES
        ):
            return FieldResult(value=None, consumed=0)
        return result


class ListFieldBuilder:
    """Collects a list of inner-builder results until inner stops consuming."""

    def __init__(self, inner, *, inner_type: type):
        self._inner = inner
        self._inner_type = inner_type

    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        collected: list[Any] = []
        cursor = ctx.cursor
        while cursor < len(ctx.children):
            local_ctx = replace(ctx, cursor=cursor)
            c = local_ctx.peek()
            if self._inner_type is str or self._inner_type is type(None):
                if not isinstance(c, (Token, str)):
                    break
            else:
                if isinstance(c, GrammarModel) and isinstance(c, self._inner_type):
                    pass
                elif isinstance(c, (Token, str)):
                    cursor += 1
                    continue
                else:
                    break
            sub = self._inner.build(atom, field_name, local_ctx)
            if isinstance(sub, SkipField) or (
                isinstance(sub, FieldResult) and sub.consumed == 0
            ):
                break
            collected.append(sub.value)
            cursor += sub.consumed
        return FieldResult(value=collected, consumed=cursor - ctx.cursor)
