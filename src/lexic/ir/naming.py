"""IR field-naming lookup tables.

CHARCLASS_NAMES and LITERAL_NAMES are the Tier-1 / Tier-2 lookup tables used
by ir/derive.py::_field_map and codegen/aliases.py::collect_aliases.
"""

from __future__ import annotations

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

LITERAL_NAMES: dict[str, str] = {
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

__all__ = ["CHARCLASS_NAMES", "LITERAL_NAMES"]
