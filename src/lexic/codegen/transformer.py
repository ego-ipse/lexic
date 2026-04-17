"""GrammarTransformer: builds a Lark Transformer from RuleSpec + Pydantic classes.

Extracted from lark_builder.py so it can be tested and evolved independently.
"""

from __future__ import annotations

from typing import get_args, get_origin, get_type_hints

from lark import Token, Transformer, Tree

from lexic.ir import (
    CharClassAtom,
    LiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.utils.escapes import decode_gbnf_escapes
from lexic.codegen.lark_builder import to_lark_name


def _flatten(tree_or_token) -> str:
    if isinstance(tree_or_token, Token):
        return str(tree_or_token)
    if isinstance(tree_or_token, Tree):
        return "".join(_flatten(c) for c in tree_or_token.children)
    return str(tree_or_token) if tree_or_token is not None else ""


def _is_ws_ref(atom) -> bool:
    return isinstance(atom, RuleRefAtom) and atom.rule_name == "ws"


def _is_optional_char(atom) -> bool:
    return isinstance(atom, CharClassAtom) and atom.min == 0


def _literal_is_quoted(lit_value: str) -> bool:
    decoded = decode_gbnf_escapes(lit_value)
    return not any(c in decoded for c in "\n\t\r")


def _build_instance(cls, spec: RuleSpec, items: list):
    """Build a Pydantic instance from Lark tree children using spec.field_map.

    Uses spec.items[item_idx] to determine each atom's nature and provide
    sensible defaults when optional atoms produce no Lark token/tree.
    """
    from lexic.base import GrammarModel

    children = [i for i in items if i is not None]

    # LiteralAtoms containing control chars (\n \t \r) are emitted as Lark
    # /regex/ terminals rather than quoted strings, so they are NOT filtered
    # by keep_all_tokens=False and appear as Token objects in children.
    # Strip them out so field positions are not displaced.
    non_field_regex_values = {
        decode_gbnf_escapes(a.value)
        for a in spec.items
        if isinstance(a, LiteralAtom) and not _literal_is_quoted(a.value)
    }
    if non_field_regex_values:
        children = [
            c
            for c in children
            if not (isinstance(c, Token) and str(c) in non_field_regex_values)
        ]
    ordered = sorted(spec.field_map.items(), key=lambda x: x[1])
    kwargs: dict[str, object] = {}
    child_idx = 0

    try:
        hints = get_type_hints(cls)
    except Exception:
        hints = {k: v for k, v in cls.__annotations__.items()}

    def _atom_for(item_idx: int):
        """Return the spec atom at item_idx, or None if out of range."""
        if 0 <= item_idx < len(spec.items):
            return spec.items[item_idx]
        return None

    for fname, item_idx in ordered:
        hint = hints.get(fname)
        origin = get_origin(hint)
        args = get_args(hint)
        atom = _atom_for(item_idx)

        if origin is list:
            inner = args[0] if args else type(None)
            collected = []
            while child_idx < len(children):
                c = children[child_idx]
                if inner is str or inner is type(None):
                    if isinstance(c, (Token, str)):
                        collected.append(str(c))
                        child_idx += 1
                    else:
                        break
                else:
                    if isinstance(c, GrammarModel) and isinstance(c, inner):
                        collected.append(c)
                        child_idx += 1
                    elif isinstance(c, (Token, str)):
                        # Skip stray literal/regex tokens that sit between model
                        # children (e.g. a '\n' token between two list items).
                        child_idx += 1
                    else:
                        break
            kwargs[fname] = collected

        elif origin is type(None) or (
            hasattr(hint, "__args__") and type(None) in getattr(hint, "__args__", ())
        ):
            inner_types = [a for a in (args or []) if a is not type(None)]
            inner = inner_types[0] if inner_types else str
            if child_idx >= len(children):
                kwargs[fname] = None
            else:
                c = children[child_idx]
                if inner is str and isinstance(c, (Token, str)):
                    kwargs[fname] = str(c)
                    child_idx += 1
                elif inner is not str and isinstance(c, inner):
                    kwargs[fname] = c
                    child_idx += 1
                else:
                    kwargs[fname] = None

        else:
            if hint is None:
                continue
            # Non-optional, non-list field.
            # Check whether we have a compatible child; if not, supply a default.
            if child_idx < len(children):
                c = children[child_idx]
                if hint is str or hint is type(None):
                    if isinstance(c, (Token, str)):
                        # CharClassAtom with max != 1 (e.g. [a-z0-9_]* or [0-9]+)
                        # may produce multiple tokens (one per matched char). Consume
                        # all consecutive string tokens so multi-char matches round-trip.
                        if isinstance(atom, CharClassAtom) and atom.max != 1:
                            parts = [str(c)]
                            child_idx += 1
                            while child_idx < len(children) and isinstance(
                                children[child_idx], (Token, str)
                            ):
                                parts.append(str(children[child_idx]))
                                child_idx += 1
                            kwargs[fname] = "".join(parts)
                        else:
                            kwargs[fname] = str(c)
                            child_idx += 1
                    elif _is_optional_char(atom):
                        # CharClassAtom(min=0) matched nothing — default to ""
                        kwargs[fname] = ""
                    else:
                        kwargs[fname] = str(c)
                        child_idx += 1
                else:
                    # Expect a GrammarModel subclass (e.g. Ws)
                    if isinstance(c, hint):
                        kwargs[fname] = c
                        child_idx += 1
                    elif _is_ws_ref(atom):
                        # ws? produced nothing; provide empty Ws instance
                        kwargs[fname] = hint(value="")
                    elif _is_optional_char(atom):
                        kwargs[fname] = ""
                    else:
                        # Wrong type but nothing better — take the child anyway
                        kwargs[fname] = c
                        child_idx += 1
            else:
                # No children left
                if hint is str or hint is type(None):
                    kwargs[fname] = ""
                elif _is_ws_ref(atom):
                    kwargs[fname] = hint(value="")
                elif _is_optional_char(atom):
                    kwargs[fname] = ""
                # else: leave unset and let Pydantic raise (required field truly missing)

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
