"""Charclass flat views — text-shaped convenience, deliberately OUTSIDE ir/.

Relocated from ``ir/charclass.py``: the IR carries pure structure;
flattening a structured :class:`~lexic.ir.nodes.IrCharClass` back to text
(or enumerating its chars) is strictly a convenience for the text-shaped
consumers (``derive`` naming keys, ``codegen.aliases``, ``generate``) that
still key on flattened patterns.
"""

from __future__ import annotations

from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec
from lexic.ir.nodes import IrCharClass, IrRange

_CLASS_METACHARS = frozenset("[]^")


def charclass_pattern(cls: IrCharClass) -> str:
    """Flatten a structured class to a regex/source-safe interior pattern.

    Each member is a code point (or a code-point range); every code point is
    escaped on its own value — regex metacharacters get a backslash, a bare
    backslash doubles, non-printable points become ``\\xNN`` / ``\\uNNNN`` /
    ``\\UNNNNNNNN``. No char run is interpreted as a pre-existing escape.

    :param cls: The structured character class.
    :returns: The flat interior pattern, members escaped for a regex class.
    """
    parts: list[str] = []
    for el in cls:
        if isinstance(el, IrRange):
            parts.append(f"{_escape_point(int(el.lo))}-{_escape_point(int(el.hi))}")
        else:
            parts.append("".join(_escape_point(ord(c)) for c in str(el)))
    return "".join(parts)


def _escape_point(point: int) -> str:
    """Escape a single code point for safe use inside a regex ``[...]``.

    :param point: The code point to escape.
    :returns: The escaped single-member text.
    """
    ch = chr(point)
    if ch == "\\":
        return "\\\\"
    if ch in _CLASS_METACHARS:
        return f"\\{ch}"
    if ch.isprintable():
        return ch
    if point <= 0xFF:
        return f"\\x{point:02x}"
    if point <= 0xFFFF:
        return f"\\u{point:04x}"
    return f"\\U{point:08x}"


def parse_charclass_chars(
    inner: str,
    codec: EscapeCodec = CANONICAL_ESCAPES,
) -> list[str]:
    """Parse the interior of a bracket expression into a list of chars.

    `inner` is the body between `[` and `]`.  Ranges (`a-z`) expand to all
    characters between the endpoints inclusive.  Escapes are read via
    `codec.read_escape`.
    """
    chars: list[str] = []
    i = 0
    while i < len(inner):
        ch, i = _read_char(inner, i, codec)
        if i < len(inner) and inner[i] == "-" and i + 1 < len(inner):
            end_ch, i = _read_char(inner, i + 1, codec)
            chars.extend(chr(c) for c in range(ord(ch), ord(end_ch) + 1))
        else:
            chars.append(ch)
    return chars


def _read_char(s: str, i: int, codec: EscapeCodec) -> tuple[str, int]:
    if s[i] == "\\" and i + 1 < len(s):
        return codec.read_escape(s, i)
    return s[i], i + 1
