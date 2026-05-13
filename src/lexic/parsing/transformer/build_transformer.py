"""build_transformer — IR specs + classes → Lark Transformer."""

from __future__ import annotations

from typing import Callable

from lark import Token, Transformer

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import (
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    Quantifier,
)
from lexic.ir.spec import RuleSpec
from lexic.utils.names import to_lark_name

# Lark quirks that consumers must handle:
#   - Regex terminals matching zero chars are omitted from children entirely.
#   - Unbounded rule-refs produce one child per occurrence (→ list field).
#   - Non-Token children are already-transformed Pydantic model instances.

_Consumer = Callable[[IrItem, list, int], tuple[object, int]]


def _consume_terminal(item: IrItem, ch: list, pos: int) -> tuple[str, int]:
    if item.quantifier == Quantifier(1, 1):
        return (
            (str(ch[pos]), pos + 1)
            if pos < len(ch) and isinstance(ch[pos], Token)
            else ("", pos)
        )
    end = pos
    while end < len(ch) and isinstance(ch[end], Token):
        end += 1
    return "".join(str(c) for c in ch[pos:end]), end


def _consume_rule_ref(item: IrItem, ch: list, pos: int) -> tuple[object, int]:
    q = item.quantifier
    if q.max is None or q.max > 1:
        end = pos
        while end < len(ch) and not isinstance(ch[end], Token):
            end += 1
        return ch[pos:end], end
    return (
        (ch[pos], pos + 1)
        if pos < len(ch) and not isinstance(ch[pos], Token)
        else (None, pos)
    )


def _group_has_ruleref(group: IrGroup) -> bool:
    return any(
        isinstance(sub.atom, IrRuleRef)
        for arm in group.body.arms
        for sub in arm.items
        if isinstance(sub, IrItem)
    )


def _consume_group(item: IrItem, ch: list, pos: int) -> tuple[object, int]:
    q = item.quantifier
    if _group_has_ruleref(item.atom):  # type: ignore[arg-type]
        # Tree-producing group (rule-ref alternation like pawn|nonpawn|castle).
        if q.max is None or q.max > 1:
            end = pos
            while end < len(ch) and not isinstance(ch[end], Token):
                end += 1
            return ch[pos:end], end
        if pos < len(ch) and not isinstance(ch[pos], Token):
            return ch[pos], pos + 1
        return None, pos
    # Terminal-only group: tokens when present, non-Token children belong to later items.
    if pos < len(ch) and isinstance(ch[pos], Token):
        end = pos
        while end < len(ch) and isinstance(ch[end], Token):
            end += 1
        return "".join(str(c) for c in ch[pos:end]), end
    return None if q.min == 0 else "", pos


_CONSUME: dict[type, _Consumer] = {
    IrLiteral: _consume_terminal,
    IrCharClass: _consume_terminal,
    IrRuleRef: _consume_rule_ref,
    IrGroup: _consume_group,
}


# ── kind builders ─────────────────────────────────────────────────────────────


def _build_alternation(_cls: type, _spec: RuleSpec, children: list) -> object:
    non_tokens = [c for c in children if not isinstance(c, Token)]
    return non_tokens[0] if non_tokens else None


def _build_value_str(cls: type, spec: RuleSpec, children: list) -> object:
    # All atoms in value_str rules are generated as regex terminals (see lark_builder.py),
    # so every matched character produces a Token in children — just join them.
    return cls(value="".join(str(c) for c in children))


def _build_sequence(
    cls: type, spec: RuleSpec, children: list, by_rule: dict[str, type]
) -> object:
    inv = {v: k for k, v in spec.field_map.items()}
    pos = 0
    kwargs: dict[str, object] = {}
    for idx, item in enumerate(spec.items):
        if not isinstance(item, IrItem):
            continue
        if isinstance(item.atom, IrLiteral) and item.quantifier == Quantifier(1, 1):
            continue
        val: object
        if isinstance(item.atom, IrRuleRef) and item.quantifier == Quantifier(0, 1):
            # Adjacent optional rule-refs are ambiguous by position alone: ws can match
            # empty, producing a child even when "absent". Check type to disambiguate.
            expected = by_rule.get(item.atom.name)
            if pos < len(children) and not isinstance(children[pos], Token):
                if expected is None or isinstance(children[pos], expected):
                    val, pos = children[pos], pos + 1
                else:
                    val = None
            else:
                val = None
        else:
            consume = _CONSUME.get(type(item.atom))
            if consume is None:
                raise UnsupportedConstructError(
                    f"build_transformer: no consumer for {type(item.atom).__name__!r}"
                )
            val, pos = consume(item, children, pos)
        field = inv.get(idx)
        if field is not None and val is not None:
            kwargs[field] = val
    return cls(**kwargs)


_SIMPLE_HANDLER: dict[str, Callable[[type, RuleSpec, list], object]] = {
    "alternation": _build_alternation,
    "value_str": _build_value_str,
}


def _make_method(cls: type, spec: RuleSpec, by_rule: dict[str, type]) -> Callable:
    if spec.kind == "sequence":

        def method(_, items: list) -> object:
            return _build_sequence(cls, spec, items, by_rule)

        return method
    handler = _SIMPLE_HANDLER.get(spec.kind)
    if handler is None:
        raise UnsupportedConstructError(
            f"build_transformer: unknown kind {spec.kind!r}"
        )

    def method(_, items: list) -> object:
        return handler(cls, spec, items)

    return method


def build_transformer(specs: list[RuleSpec], classes: dict[str, type]) -> Transformer:
    """Build a Lark Transformer that maps rule names to Pydantic constructors."""
    by_rule: dict[str, type] = {
        spec.rule_name: classes[spec.class_name]
        for spec in specs
        if spec.class_name in classes
    }
    methods: dict[str, object] = {}
    for spec in specs:
        cls = classes.get(spec.class_name)
        if cls is not None:
            methods[to_lark_name(spec.rule_name)] = _make_method(cls, spec, by_rule)
    return type("GrammarTransformer", (Transformer,), methods)()
