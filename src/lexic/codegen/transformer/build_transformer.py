"""GrammarTransformer: builds a Lark Transformer from RuleSpec + Pydantic classes.

Extracted from lark_builder.py so it can be tested and evolved independently.
"""

from __future__ import annotations

from lark import Token, Transformer

from lexic.ir import (
    LiteralAtom,
    RuleSpec,
)
from lexic.grammars.gbnf.syntax import decode_gbnf_escapes
from lexic.utils.names import to_lark_name
from dataclasses import replace as dc_replace
from typing import get_args, get_origin, get_type_hints

from lexic.codegen.transformer.context import BuildContext, FieldResult, SkipField
from lexic.codegen.transformer.registry import builder_for
from lexic.codegen.transformer.builders import ListFieldBuilder, OptionalFieldBuilder


def _literal_is_quoted(lit_value: str) -> bool:
    decoded = decode_gbnf_escapes(lit_value)
    return not any(c in decoded for c in "\n\t\r")


def _build_instance(cls, spec: RuleSpec, items: list):

    children = tuple(i for i in items if i is not None)

    non_field_regex_values = {
        decode_gbnf_escapes(a.value)
        for a in spec.items
        if isinstance(a, LiteralAtom) and not _literal_is_quoted(a.value)
    }
    if non_field_regex_values:
        children = tuple(
            c
            for c in children
            if not (isinstance(c, Token) and str(c) in non_field_regex_values)
        )

    try:
        hints = get_type_hints(cls)
    except Exception:
        hints = {k: v for k, v in cls.__annotations__.items()}

    ctx = BuildContext(spec=spec, children=children, hints=hints, cursor=0)
    ordered = sorted(spec.field_map.items(), key=lambda x: x[1])
    kwargs: dict[str, object] = {}

    for fname, item_idx in ordered:
        atom = spec.items[item_idx] if 0 <= item_idx < len(spec.items) else None
        if atom is None:
            continue
        hint = hints.get(fname)
        base = builder_for(atom)
        origin = get_origin(hint)
        args = get_args(hint)
        if origin is list:
            inner = args[0] if args else str
            b = ListFieldBuilder(base, inner_type=inner)
        elif hint is not None and type(None) in (args or ()):
            b = OptionalFieldBuilder(base)
        else:
            b = base
        result = b.build(atom, fname, ctx)
        match result:
            case SkipField():
                continue
            case FieldResult(value=v, consumed=n):
                kwargs[fname] = v
                ctx = dc_replace(ctx, cursor=ctx.cursor + n)

    return cls(**kwargs)


def build_transformer(specs: list[RuleSpec], classes: dict[str, type]) -> Transformer:
    """Build a Lark Transformer that maps rule names to Pydantic constructors."""
    methods: dict[str, object] = {}
    specs_by_lark = {to_lark_name(s.rule_name): s for s in specs}

    # ws: return a Ws instance if the class exists, otherwise return the joined text
    ws_cls = classes.get("Ws")

    def ws_method(self_, items):
        text = "".join(str(i) for i in items if i is not None)
        if ws_cls is not None:
            return ws_cls(value=text)
        return text

    methods["ws"] = ws_method

    for lark_name, spec in specs_by_lark.items():
        if spec.rule_name == "ws":
            continue
        cls = classes.get(spec.class_name)
        if cls is None:
            continue

        if spec.kind == "alternation":

            def make_abstract(cn=spec.class_name):
                def method(self_, items):
                    children = [
                        i for i in items if i is not None and not isinstance(i, Token)
                    ]
                    return children[0] if children else None

                return method

            methods[lark_name] = make_abstract()

        elif spec.kind == "value_str":
            # With keep_all_tokens=False, Lark filters out quoted-literal
            # tokens but keeps regex terminals. LiteralAtoms that contain
            # control chars (\n \t \r) are emitted as /regex/ (kept as tokens);
            # printable-only LiteralAtoms are emitted as "quoted" (filtered).
            # We reconstruct the full text by inserting filtered literal text
            # around the token stream in spec order.

            def make_value(ct=cls, sp=spec):
                def method(self_, items):
                    # Token stream: all non-filtered content (charclass tokens +
                    # regex-literal tokens like \n).
                    token_text = "".join(str(i) for i in items if i is not None)
                    # Reconstruct full text: walk spec, insert filtered literals
                    # at their positions, place token_text at the first
                    # non-filtered-literal position.
                    result: list[str] = []
                    token_placed = False
                    for atom in sp.items:
                        if isinstance(atom, LiteralAtom) and _literal_is_quoted(
                            atom.value
                        ):
                            result.append(decode_gbnf_escapes(atom.value))
                        elif not token_placed:
                            result.append(token_text)
                            token_placed = True
                    if not token_placed:
                        result.append(token_text)
                    return ct(value="".join(result))

                return method

            methods[lark_name] = make_value()

        else:

            def make_seq(ct=cls, sp=spec):
                def method(self_, items):
                    return _build_instance(ct, sp, items)

                return method

            methods[lark_name] = make_seq()

    return type("GrammarTransformer", (Transformer,), methods)()
