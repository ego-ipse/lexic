"""LarkBuilder: converts list[RuleSpec] into a Lark grammar string and Transformer.

Single responsibility: knows Lark syntax. Knows nothing about Python source or GBNF text.
"""
from __future__ import annotations

from typing import get_args, get_origin, get_type_hints

from lark import Token, Transformer, Tree

from .ir import AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec


def _to_lark_name(rule_name: str) -> str:
    """Convert GBNF rule name to a valid Lark rule identifier.

    Lark rules must be all-lowercase; terminals start with uppercase.
    Hyphens are not valid in identifiers, so we replace them with underscores.
    """
    return rule_name.replace("-", "_").lower()


def _bounds_to_quantifier(min_: int, max_: int | None) -> str:
    if min_ == 1 and max_ == 1:
        return ""
    if min_ == 0 and max_ == 1:
        return "?"
    if min_ == 0 and max_ is None:
        return "*"
    if min_ == 1 and max_ is None:
        return "+"
    if max_ is None:
        return f"{{{min_},}}"
    if min_ == max_:
        return f"{{{min_}}}"
    return f"{{{min_},{max_}}}"


def _decode_gbnf_escapes(s: str) -> str:
    """Decode GBNF string escape sequences stored as literal backslash sequences.

    IRBuilder stores \\n as the 2-char sequence '\\n', not an actual newline.
    This function converts them to real characters.
    """
    # Order matters: decode \\ first so \\n isn't decoded as \<newline>.
    # Then decode \" as a literal doublequote (GBNF string escape).
    return (
        s.replace("\\\\", "\x00BACKSLASH\x00")   # protect \\ temporarily
         .replace("\\n", "\n")
         .replace("\\t", "\t")
         .replace("\\r", "\r")
         .replace('\\"', '"')
         .replace("\x00BACKSLASH\x00", "\\")
    )


def _escape_lark_regex(s: str) -> str:
    """Escape a string for use inside a Lark /regex/ terminal.

    Lark's grammar parser uses / as regex delimiter, so / must be escaped.
    """
    return s.replace("/", "\\/")


def _normalize_charclass_pattern(pattern: str) -> str:
    """Convert a CharClassAtom pattern to a valid regex usable in Lark /regex/ syntax.

    IRBuilder may store GBNF group expressions as patterns, e.g. '("+"|"-")' or
    '("true"|"false"|"null")'. These contain GBNF-quoted literals which must be
    unquoted to form valid regex.

    Also handles \\n etc. stored as 2-char escape sequences.
    """
    import re as _re

    # Strip GBNF-style double-quoted literals: replace "text" with text
    # e.g. ("+"|"-") -> (+|-) -> [+\-] (simplified later)
    # e.g. ("true"|"false"|"null") -> (true|false|null)
    # e.g. ("."[0-9]) -> (\.[0-9])
    def _unquote_literal(m: "_re.Match[str]") -> str:
        inner = m.group(1)
        # Escape regex special chars that appear literally in the GBNF quoted string
        inner = _re.escape(inner)
        return inner

    # Only unquote if the pattern contains GBNF-style quoted strings
    if '"' in pattern:
        pattern = _re.sub(r'"([^"]*)"', _unquote_literal, pattern)

    # Decode \\n etc. stored as 2-char sequences into real regex escape sequences
    # In regex context: \n means actual newline, which is what we want
    pattern = pattern.replace("\\\\n", "\\n")
    pattern = pattern.replace("\\\\t", "\\t")
    pattern = pattern.replace("\\\\r", "\\r")

    return pattern


def _atom_to_lark(atom) -> str:
    if isinstance(atom, LiteralAtom):
        # Decode GBNF escape sequences stored as 2-char sequences
        decoded = _decode_gbnf_escapes(atom.value)
        if any(c in decoded for c in "\n\t\r"):
            # Emit as regex so Lark handles control chars correctly.
            # Escape regex special chars that appear in the literal.
            regex = ""
            for ch in decoded:
                if ch == "\n":
                    regex += "\\n"
                elif ch == "\t":
                    regex += "\\t"
                elif ch == "\r":
                    regex += "\\r"
                elif ch in r"\.^$*+?{}[]|()":
                    regex += "\\" + ch
                else:
                    regex += ch
            regex = _escape_lark_regex(regex)
            return f"/{regex}/"
        # Safe to emit as quoted Lark string literal
        escaped = decoded.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(atom, CharClassAtom):
        q = _bounds_to_quantifier(atom.min, atom.max)
        # Normalize: strip GBNF-style quotes, fix escape sequences.
        # Skip normalization for complex regex patterns (from _group_to_regex)
        # that already contain structural regex syntax — normalization would
        # escape their ( ) | [ ] chars and break them.
        p = atom.pattern
        is_complex_regex = (
            p.startswith("(") and "|" in p and not p.startswith("([")
        ) or (
            p.startswith("(") and p.count("(") > 1
        )
        normalized = p if is_complex_regex else _normalize_charclass_pattern(p)
        # Escape / so Lark's grammar parser doesn't treat it as regex terminator
        safe_pattern = _escape_lark_regex(normalized)
        return f"/{safe_pattern}/{q}"
    if isinstance(atom, RuleRefAtom):
        name = _to_lark_name(atom.rule_name)
        if atom.rule_name == "ws":
            return "ws?"
        q = _bounds_to_quantifier(atom.min, atom.max)
        return f"{name}{q}"
    if isinstance(atom, AlternationAtom):
        # Parenthesize so inline alternations inside a sequence don't bleed into
        # Lark's rule-level |-alternation.  e.g. (pawn | nonpawn | castle) /[+#]?/
        return "(" + " | ".join(_to_lark_name(n) for n in atom.arm_rule_names) + ")"
    return '""'


class LarkBuilder:
    """Builds a Lark grammar string and Transformer from a list of RuleSpec."""

    def __init__(self, specs: list[RuleSpec]):
        self._specs = specs
        self._by_rule = {s.rule_name: s for s in specs}

    def build_grammar(self) -> tuple[str, str]:
        """Return (lark_grammar_str, start_rule_name)."""
        lines: list[str] = []
        has_ws = "ws" in self._by_rule

        for spec in self._specs:
            if spec.rule_name == "ws":
                continue
            line = self._spec_to_lark_rule(spec)
            lines.append(line)

        if has_ws:
            lines.append(r"ws : /[ \t\n]+/")

        start = _to_lark_name(self._specs[0].rule_name)
        return "\n".join(lines), start

    def _spec_to_lark_rule(self, spec: RuleSpec) -> str:
        lark_name = _to_lark_name(spec.rule_name)
        if spec.kind == "value_str":
            # If every item is a LiteralAtom, they are alternatives (disjunction),
            # not a concatenated sequence. Emit with | separators.
            if spec.items and all(isinstance(a, LiteralAtom) for a in spec.items):
                body = " | ".join(_atom_to_lark(a) for a in spec.items)
            else:
                body = " ".join(_atom_to_lark(a) for a in spec.items) or '""'
            return f"{lark_name} : {body}"
        if spec.kind == "alternation":
            alt_atom = spec.items[0] if spec.items else None
            if alt_atom and isinstance(alt_atom, AlternationAtom):
                arms = " | ".join(_to_lark_name(n) for n in alt_atom.arm_rule_names)
                return f"{lark_name} : {arms}"
            return f"{lark_name} :"
        # sequence
        body = " ".join(_atom_to_lark(a) for a in spec.items)
        return f"{lark_name} : {body}" if body.strip() else f"{lark_name} :"

    def build_transformer(self, classes: dict[str, type]) -> Transformer:
        """Build a Lark Transformer that maps rule names to Pydantic constructors."""
        methods: dict[str, object] = {}
        specs_by_lark = {_to_lark_name(s.rule_name): s for s in self._specs}

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
                        children = [i for i in items if i is not None and not isinstance(i, Token)]
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
                def _literal_is_quoted(lit_value: str) -> bool:
                    decoded = _decode_gbnf_escapes(lit_value)
                    return not any(c in decoded for c in "\n\t\r")

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
                            if isinstance(atom, LiteralAtom) and _literal_is_quoted(atom.value):
                                result.append(_decode_gbnf_escapes(atom.value))
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


def _flatten(tree_or_token) -> str:
    if isinstance(tree_or_token, Token):
        return str(tree_or_token)
    if isinstance(tree_or_token, Tree):
        return "".join(_flatten(c) for c in tree_or_token.children)
    return str(tree_or_token) if tree_or_token is not None else ""


def _build_instance(cls, spec: RuleSpec, items: list):
    """Build a Pydantic instance from Lark tree children using spec.field_map.

    Uses spec.items[item_idx] to determine each atom's nature and provide
    sensible defaults when optional atoms produce no Lark token/tree.
    """
    from base import GrammarModel

    children = [i for i in items if i is not None]
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

    def _is_ws_ref(atom) -> bool:
        return isinstance(atom, RuleRefAtom) and atom.rule_name == "ws"

    def _is_optional_char(atom) -> bool:
        return isinstance(atom, CharClassAtom) and atom.min == 0

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
            # Non-optional, non-list field.
            # Check whether we have a compatible child; if not, supply a default.
            if child_idx < len(children):
                c = children[child_idx]
                if hint is str or hint is type(None):
                    if isinstance(c, (Token, str)):
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
