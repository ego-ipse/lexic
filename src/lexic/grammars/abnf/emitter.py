"""AbnfEmitter — minimal-ABNF flavour emitter.

Overrides syntax constants and three decorators:
- rule_separator = "="
- alt_separator = " / "
- format_quantifier — emits ABNF prefix quantifiers (e.g. "1*", "*5", "2*5")
- place_quantifier — prepends quantifier string instead of appending (ABNF prefix rule)
- render_charclass — translates POSIX ranges to ABNF %x hex ranges

ABNF places the quantifier *before* the atom. `FlavourEmitter.DEFAULT_HANDLERS`
calls `e.place_quantifier(atom_str, q_str)`, so overriding `place_quantifier`
here is sufficient — no handler table override needed.
"""

from __future__ import annotations

from typing import ClassVar

from lexic.ir.emit import FlavourEmitter


def _hex_range_segment(seg: str) -> str:
    """Convert one POSIX range segment ('a-z' or single char) to ABNF hex."""
    if len(seg) == 3 and seg[1] == "-":
        lo, hi = seg[0], seg[2]
        return f"%x{ord(lo):02X}-{ord(hi):02X}"
    if len(seg) == 1:
        return f"%x{ord(seg):02X}"
    # Multi-char without dash: emit as a sequence of single-char hexes
    return " / ".join(f"%x{ord(c):02X}" for c in seg)


def _split_charclass_segments(pattern: str) -> list[str]:
    """Split a POSIX bracket interior into 3-char ranges and 1-char literals."""
    segments: list[str] = []
    i = 0
    while i < len(pattern):
        if i + 2 < len(pattern) and pattern[i + 1] == "-":
            segments.append(pattern[i : i + 3])
            i += 3
        else:
            segments.append(pattern[i])
            i += 1
    return segments


class AbnfEmitter(FlavourEmitter):
    """Minimal-ABNF flavour emitter."""

    rule_separator: str = "="
    alt_separator: str = " / "
    quote_char: str = '"'
    group_open: str = "("
    group_close: str = ")"
    empty_body: str = '""'

    supports: ClassVar[frozenset[str]] = frozenset(
        {
            "literal",
            "char_class",
            "quantifier",
            "alternation",
            "non_capturing_group",
        }
    )

    def format_quantifier(self, lo: int, hi: int | None) -> str:
        """Return the ABNF *prefix* quantifier string. Empty when (1, 1)."""
        if lo == 1 and hi == 1:
            return ""
        if lo == hi:
            return f"{lo}"
        if hi is None:
            return f"{lo}*" if lo != 0 else "*"
        return f"{lo}*{hi}" if lo != 0 else f"*{hi}"

    def place_quantifier(self, atom_str: str, q_str: str) -> str:
        """Combine atom rendering with quantifier. ABNF overrides to prefix."""
        return f"{q_str}{atom_str}"

    def render_charclass(self, canonical_pattern: str) -> str:
        segments = _split_charclass_segments(canonical_pattern)
        rendered = [_hex_range_segment(s) for s in segments]
        if len(rendered) == 1:
            return rendered[0]
        return "(" + " / ".join(rendered) + ")"
