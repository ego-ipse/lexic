"""Bracket-expression enumeration over canonical POSIX patterns.

`parse_charclass_chars` is the generic algorithm used by `runtime.generate`
and any future flavour that needs to enumerate the chars of a CharClassAtom
pattern.  Escape-reading is delegated to an `EscapeCodec`; default codec is
`CANONICAL_ESCAPES` since `CharClassAtom.value` is canonical POSIX.
"""

from __future__ import annotations

from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec


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
