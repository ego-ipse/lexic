"""LarkBuilder: converts list[RuleSpec] into a Lark grammar string and Transformer.

Single responsibility: knows Lark syntax. Knows nothing about Python source or GBNF text.
"""

from __future__ import annotations

from lark import Transformer

from lexic.codegen.transformer import build_transformer
from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.grammars.gbnf.escapes import decode_gbnf_escapes
from lexic.utils.names import to_lark_name
from lexic.utils.quantifiers import bounds_to_quantifier


def _escape_lark_regex(s: str) -> str:
    """Escape a string for use inside a Lark /regex/ terminal.

    Lark's grammar parser uses / as regex delimiter, so / must be escaped.
    """
    return s.replace("/", "\\/")


def _atom_to_lark(atom) -> str:
    if isinstance(atom, LiteralAtom):
        # Decode GBNF escape sequences stored as 2-char sequences
        decoded = decode_gbnf_escapes(atom.value)
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
        q = bounds_to_quantifier(atom.min, atom.max)
        safe = _escape_lark_regex(atom.pattern)
        return f"/{safe}/{q}"
    if isinstance(atom, RuleRefAtom):
        name = to_lark_name(atom.rule_name)
        if atom.rule_name == "ws":
            return "ws?"
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{name}{q}"
    if isinstance(atom, AlternationAtom):
        # Parenthesize so inline alternations inside a sequence don't bleed into
        # Lark's rule-level |-alternation.  e.g. (pawn | nonpawn | castle) /[+#]?/
        return "(" + " | ".join(to_lark_name(n) for n in atom.arm_rule_names) + ")"
    if isinstance(atom, QuantifiedLiteralAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        decoded = decode_gbnf_escapes(atom.value)
        escaped = decoded.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"{q}'
    if isinstance(atom, InlineRegexAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        safe = _escape_lark_regex(atom.regex)
        return f"/{safe}/{q}"
    if isinstance(atom, InlineAlternationAtom):
        return "(" + " | ".join(to_lark_name(n) for n in atom.arm_rule_names) + ")"
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

        start = to_lark_name(self._specs[0].rule_name)
        return "\n".join(lines), start

    def _spec_to_lark_rule(self, spec: RuleSpec) -> str:
        lark_name = to_lark_name(spec.rule_name)
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
                arms = " | ".join(to_lark_name(n) for n in alt_atom.arm_rule_names)
                return f"{lark_name} : {arms}"
            return f"{lark_name} :"
        # sequence
        body = " ".join(_atom_to_lark(a) for a in spec.items)
        return f"{lark_name} : {body}" if body.strip() else f"{lark_name} :"

    def build_transformer(self, classes: dict[str, type]) -> Transformer:
        """Build a Lark Transformer that maps rule names to Pydantic constructors."""
        # This is broken.
        return build_transformer(self._specs, classes)
