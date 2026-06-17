"""Charclass flat views — Lark-era shims, deliberately OUTSIDE ir/.

Relocated from ``ir/charclass.py``: the IR carries pure structure;
flattening a structured :class:`~lexic.ir.nodes.IrCharClass` back to text
(or enumerating its chars) is strictly a convenience for the condemned
Lark-side consumers (``derive`` naming keys, ``lark_builder`` regexes,
``codegen.aliases``, ``generate``). Dies with the Lark pipeline.
"""

from __future__ import annotations

from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec
from lexic.ir.nodes import IrCharClass, IrRange

_CLASS_METACHARS = frozenset("[]^")


def charclass_pattern(cls: IrCharClass) -> str:
    """Flatten a structured class to a regex/source-safe interior pattern.

    :param cls: The structured character class.
    :returns: The flat interior pattern, members escaped for a regex class.
    """
    raw = "".join(
        f"{el.lo}-{el.hi}" if isinstance(el, IrRange) else str(el) for el in cls
    )
    return _escape_class_text(raw)


def _escape_class_text(text: str) -> str:
    """Make a flat char-class interior valid inside a regex ``[...]``.

    Three jobs: pre-escaped units (GBNF stores ``\\x1F`` / ``\\]`` as text) pass
    through; raw metacharacter members (ABNF decodes ``%x5C`` to a bare ``\\``,
    ``%x5D`` to ``]``) get escaped; non-printable points become
    ``\\xNN`` / ``\\uNNNN`` / ``\\UNNNNNNNN``.

    The backslash rule is a heuristic: ``\\`` followed by a char is taken as an
    existing escape and passed through, a lone ``\\`` is escaped. Enough for the
    current grammars; the clean fix is the neutral-codepoint reshape that
    retires this Lark-era module (members become code points, escaped once at
    emit, and this guessing disappears).
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            if i + 1 < n:
                out.append(text[i : i + 2])
                i += 2
            else:
                out.append("\\\\")
                i += 1
            continue
        if ch in _CLASS_METACHARS:
            out.append(f"\\{ch}")
        elif ch.isprintable():
            out.append(ch)
        elif (point := ord(ch)) <= 0xFF:
            out.append(f"\\x{point:02x}")
        elif point <= 0xFFFF:
            out.append(f"\\u{point:04x}")
        else:
            out.append(f"\\U{point:08x}")
        i += 1
    return "".join(out)


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
