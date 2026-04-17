"""GBNFEmitter: reconstructs GBNF text from list[RuleSpec].

Single responsibility: knows GBNF syntax. Knows nothing about Lark or Python.
Enables the reverse direction: Pydantic model classes → GBNF grammar file.
"""

from __future__ import annotations

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
from lexic.utils.quantifiers import bounds_to_quantifier


def _normalize_charclass_pattern_for_gbnf(pattern: str) -> str:
    """Convert a CharClassAtom pattern to valid GBNF syntax.

    CharClassAtom patterns from IRBuilder may contain regex escape sequences
    that don't parse as GBNF. This attempts to convert them back to GBNF literals.
    """
    # Pattern from IRBuilder._group_to_regex may contain backslash sequences
    # that are meant for Lark regex, not GBNF. These look like \\\\\\\ in the
    # Python string (which displays as \\\\\\ in GBNF).

    # Strategy: look for problematic patterns and try to reconstruct GBNF literals.
    # The pattern |\\\\( is particularly problematic - it represents | followed
    # by a literal backslash and open paren, but GBNF can't parse \\ outside a string.

    # Replace sequence: \\\\\\\\( becomes "\\\\\\\\("  (GBNF literal for \\()
    # But this is complex because we need to match the right context.

    # Simpler approach: wrap problematic parts in quotes
    if "\\\\" in pattern and "|" in pattern:
        # Look for patterns like |\\\\  which are invalid in GBNF
        # and wrap them as literals
        pattern = pattern.replace("|\\\\\\\\(", '|"\\\\\\\\\\\\"(')

    return pattern


def _atom_to_gbnf(atom) -> str:
    """Convert an Atom to GBNF string representation."""
    if isinstance(atom, LiteralAtom):
        # LiteralAtom.value already contains escape sequences from GBNF source.
        # Don't escape again - just wrap in quotes.
        return f'"{atom.value}"'
    if isinstance(atom, CharClassAtom):
        # Normalize pattern to ensure it's valid GBNF
        pattern = _normalize_charclass_pattern_for_gbnf(atom.pattern)
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{pattern}{q}"
    if isinstance(atom, RuleRefAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{atom.rule_name}{q}"
    if isinstance(atom, AlternationAtom):
        return " | ".join(atom.arm_rule_names)
    if isinstance(atom, QuantifiedLiteralAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        return f'"{atom.value}"{q}'
    if isinstance(atom, InlineRegexAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        if q:
            # Wrap in parens so the quantifier applies to the whole group
            body = (
                atom.gbnf
                if (atom.gbnf.startswith("(") and atom.gbnf.endswith(")"))
                else f"({atom.gbnf})"
            )
            return f"{body}{q}"
        return atom.gbnf
    if isinstance(atom, InlineAlternationAtom):
        return "(" + " | ".join(atom.arm_rule_names) + ")"
    return ""


class GBNFEmitter:
    """Emits GBNF grammar text from a list of RuleSpec objects.

    Usage:
        specs = IRBuilder(parse_gbnf(text)).build()
        gbnf_text = GBNFEmitter(specs).emit()
        # gbnf_text can be passed back to parse_gbnf() or saved as a .gbnf file
    """

    def __init__(self, specs: list[RuleSpec]):
        self._specs = specs

    def emit(self) -> str:
        """Emit the full grammar as a GBNF string."""
        lines = []
        for spec in self._specs:
            lines.append(self.emit_rule(spec))
        return "\n".join(lines) + "\n"

    def emit_rule(self, spec: RuleSpec) -> str:
        """Emit a single rule as 'name ::= body'."""
        body = self._emit_body(spec)
        return f"{spec.rule_name} ::= {body}"

    def _emit_body(self, spec: RuleSpec) -> str:
        """Emit the right-hand side of a rule based on its kind."""
        if spec.kind == "value_str":
            parts = [_atom_to_gbnf(a) for a in spec.items]
            return " ".join(parts) if parts else '""'
        if spec.kind == "alternation":
            if spec.items and isinstance(spec.items[0], AlternationAtom):
                return " | ".join(spec.items[0].arm_rule_names)
            return '""'
        # sequence or other
        parts = [_atom_to_gbnf(a) for a in spec.items]
        return " ".join(p for p in parts if p)
