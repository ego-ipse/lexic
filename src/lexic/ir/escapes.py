"""EscapeCodec ABC — canonical Python ↔ flavour-text escape conversion.

Subclasses declare two class attrs (SHORT_ESCAPES, HEX_ESCAPES); the
encode/decode/read_escape algorithms are shared. Mirrors FlavourEmitter's
ABC pattern: generic algorithm in core, syntax constants per flavour.
"""

from __future__ import annotations

import re
from abc import ABC
from functools import cache
from typing import ClassVar


class EscapeCodec(ABC):
    """Generic encode/decode/read_escape algorithms parameterised by tables."""

    SHORT_ESCAPES: ClassVar[dict[str, str]] = {}
    """Source follow-char → canonical char.  e.g. {"n": "\\n", "\\\\": "\\\\"}"""

    HEX_ESCAPES: ClassVar[tuple[tuple[str, int], ...]] = ()
    """Hex tag chars + digit counts.  e.g. (("x", 2), ("u", 4), ("U", 8))"""

    def decode(self, source: str) -> str:
        """Decode a flavour-text source string into canonical Python."""
        return self._decode_re().sub(self._replace, source)

    def encode(self, value: str) -> str:
        """Encode canonical Python into the flavour's escape syntax."""
        table = self._encode_table()
        return "".join(table.get(c, c) for c in value)

    def read_escape(self, source: str, i: int) -> tuple[str, int]:
        """Parse one escape starting at source[i] == '\\'.  Returns (char, new_i)."""
        c = source[i + 1]
        if c in self.SHORT_ESCAPES:
            return self.SHORT_ESCAPES[c], i + 2
        for tag, n in self.HEX_ESCAPES:
            if c == tag and i + 1 + n < len(source):
                return chr(int(source[i + 2 : i + 2 + n], 16)), i + 2 + n
        return c, i + 2

    @classmethod
    @cache
    def _encode_table(cls) -> dict[str, str]:
        return {canon: f"\\{src}" for src, canon in cls.SHORT_ESCAPES.items()}

    @classmethod
    @cache
    def _decode_re(cls) -> re.Pattern[str]:
        parts: list[str] = []
        if cls.SHORT_ESCAPES:
            parts.append("[" + "".join(re.escape(c) for c in cls.SHORT_ESCAPES) + "]")
        for tag, n in cls.HEX_ESCAPES:
            parts.append(f"{re.escape(tag)}[0-9a-fA-F]{{{n}}}")
        if not parts:
            return re.compile(r"(?!)")
        return re.compile(r"\\(?:" + "|".join(parts) + ")")

    def _replace(self, m: re.Match[str]) -> str:
        seq = m.group(0)
        c = seq[1]
        if c in self.SHORT_ESCAPES:
            return self.SHORT_ESCAPES[c]
        return chr(int(seq[2:], 16))


class _CanonicalEscapes(EscapeCodec):
    """Escape rules for canonical POSIX-style bracket strings stored in the IR.

    Used by `ir/charclass.py` to enumerate chars from `CharClassAtom.value`.
    Set is narrow on purpose — canonical patterns must round-trip across every
    supported flavour.
    """

    SHORT_ESCAPES = {
        "n": "\n",
        "t": "\t",
        "r": "\r",
        "\\": "\\",
        "]": "]",
        "-": "-",
        "^": "^",
    }
    HEX_ESCAPES = (("x", 2), ("u", 4), ("U", 8))


CANONICAL_ESCAPES: EscapeCodec = _CanonicalEscapes()
