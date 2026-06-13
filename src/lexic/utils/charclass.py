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


def charclass_pattern(cls: IrCharClass) -> str:
    """Flatten a structured class to its interior pattern (encoded units).

    :param cls: The structured character class.
    :returns: The flat interior pattern, escapes still encoded.
    """
    return "".join(
        f"{el.lo}-{el.hi}" if isinstance(el, IrRange) else str(el) for el in cls
    )


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
