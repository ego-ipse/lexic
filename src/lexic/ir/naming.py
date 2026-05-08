"""assign_field_names: map a rule's atom sequence to Pydantic field positions.

Extracted from ir_builder.py so the naming policy can be evolved and
tested independently of GBNF semantics. Slice C will replace this module
with the four-tier cascade; for now the behaviour is identical to the
pre-extraction CHARCLASS_NAMES/_LITERAL_NAMES lookup.

Stateless. Per-rule scope (collision counters reset per call).
"""

from __future__ import annotations

import re
from collections.abc import Sequence as Seq

from lexic.ir.atoms import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)

CHARCLASS_NAMES: dict[str, str] = {
    "[0-9]": "digit",
    "[0-9a-fA-F]": "hex",
    "[a-fA-F0-9]": "hex",
    "[a-f]": "hex_lower",
    "[A-F]": "hex_upper",
    "[a-z]": "lower",
    "[A-Z]": "upper",
    "[a-zA-Z]": "letter",
    "[a-zA-Z_0-9]": "alnum",
}

_LITERAL_NAMES: dict[str, str] = {
    "-": "sign",
    "+": "sign",
    ".": "dot",
    ",": "comma",
    ":": "colon",
    ";": "semicolon",
    "=": "eq",
    "x": "x",
    "e": "e",
    "E": "E",
}


def _sanitize_pattern(pattern: str) -> str:
    inner = re.sub(r"[\[\]\^]", "", pattern)
    inner = inner.replace("-", "_").lower()
    inner = re.sub(r"[^a-z0-9_]", "", inner)
    inner = inner.strip("_")
    inner = re.sub(r"_+", "_", inner)
    if not inner:
        return ""
    if inner[0].isdigit():
        inner = "cc_" + inner
    return inner[:12].strip("_")


def _charclass_field_name(atom: CharClassAtom) -> str:
    if atom.pattern in CHARCLASS_NAMES:
        return CHARCLASS_NAMES[atom.pattern]
    hint = _sanitize_pattern(atom.pattern)
    if hint:
        return hint
    if atom.max is None:
        return "tail"
    if atom.min == 0 and atom.max == 1:
        return "opt"
    return "cc"


def _quantified_literal_field_name(value: str) -> str:
    if value in _LITERAL_NAMES:
        return _LITERAL_NAMES[value]
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", value).strip("_").lower()[:12]
    return sanitized or "lit"


def _inline_regex_field_name(gbnf: str) -> str:
    body = gbnf.strip()
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    first_arm = body.split("|")[0].strip().strip('"')
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", first_arm).strip("_").lower()
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")[:12]
    if not sanitized:
        return "inline"
    if sanitized[0].isdigit():
        sanitized = ("val_" + sanitized)[:12].strip("_")
    return sanitized


def assign_field_names(atoms: Seq[Atom]) -> dict[str, int]:
    """Assign semantic field names to atoms. Per-rule scope; stateless."""
    field_map: dict[str, int] = {}
    counts: dict[str, int] = {}

    def unique(base: str) -> str:
        n = counts.get(base, 0) + 1
        counts[base] = n
        return base if n == 1 else f"{base}{n}"

    for i, atom in enumerate(atoms):
        if isinstance(atom, LiteralAtom):
            continue
        if isinstance(atom, AlternationAtom):
            continue
        if isinstance(atom, InlineAlternationAtom):
            field_map[unique("value")] = i
        elif isinstance(atom, RuleRefAtom):
            field_map[unique(atom.rule_name.replace("-", "_"))] = i
        elif isinstance(atom, CharClassAtom):
            field_map[unique(_charclass_field_name(atom))] = i
        elif isinstance(atom, QuantifiedLiteralAtom):
            field_map[unique(_quantified_literal_field_name(atom.value))] = i
        elif isinstance(atom, InlineRegexAtom):
            field_map[unique(_inline_regex_field_name(atom.gbnf))] = i

    return field_map
