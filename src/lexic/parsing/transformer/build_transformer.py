"""build_transformer — IR specs + classes → Lark Transformer."""

from __future__ import annotations

from typing import Callable

from lark import Token, Transformer

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import IrItem, IrLiteral, Quantifier
from lexic.ir.spec import NewRuleSpec
from lexic.utils.names import to_lark_name


def _build_alternation(_cls: type, _spec: NewRuleSpec, items: list) -> object:
    children = [i for i in items if i is not None and not isinstance(i, Token)]
    return children[0] if children else None


def _build_value_str(cls: type, spec: NewRuleSpec, items: list) -> object:
    """Re-insert filtered literals; batch all token text to handle /pat/+ repetitions."""
    token = "".join(str(i) for i in items if i is not None)
    parts: list[str] = []
    token_placed = False
    for item in (i for i in spec.items if isinstance(i, IrItem)):
        if isinstance(item.atom, IrLiteral):
            parts.append(item.atom.value)
        elif not token_placed:
            parts.append(token)
            token_placed = True
    if not token_placed:
        parts.append(token)
    return cls(value="".join(parts))


def _build_sequence(cls: type, spec: NewRuleSpec, children: list) -> object:
    """Lark only passes children that appear in the grammar; map positions back
    through field_map using pre-filtered (non-literal) item indices."""
    inv = {v: k for k, v in spec.field_map.items()}
    lark_items = [
        (idx, item)
        for idx, item in enumerate(spec.items)
        if isinstance(item, IrItem)
        and not (
            isinstance(item.atom, IrLiteral) and item.quantifier == Quantifier(1, 1)
        )
    ]
    kwargs = {
        inv[idx]: child for (idx, _), child in zip(lark_items, children) if idx in inv
    }
    return cls(**kwargs)


_KIND_HANDLER: dict[str, Callable[[type, NewRuleSpec, list], object]] = {
    "alternation": _build_alternation,
    "value_str": _build_value_str,
    "sequence": _build_sequence,
}


def _make_method(cls: type, spec: NewRuleSpec) -> Callable:
    handler = _KIND_HANDLER.get(spec.kind)
    if handler is None:
        raise UnsupportedConstructError(
            f"build_transformer: unknown kind {spec.kind!r}"
        )

    def method(_, items):
        return handler(cls, spec, items)

    return method


def build_transformer(
    specs: list[NewRuleSpec], classes: dict[str, type]
) -> Transformer:
    """Build a Lark Transformer that maps rule names to Pydantic constructors."""
    methods: dict[str, object] = {}
    for spec in specs:
        cls = classes.get(spec.class_name)
        if cls is not None:
            methods[to_lark_name(spec.rule_name)] = _make_method(cls, spec)
    return type("GrammarTransformer", (Transformer,), methods)()
