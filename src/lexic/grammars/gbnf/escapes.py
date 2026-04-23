from __future__ import annotations

import re


def decode_gbnf_escapes(s: str) -> str:
    """Decode GBNF string escape sequences to real chars.

    Handles: \\n \\t \\r \\" \\\\ \\xXX \\uXXXX \\UXXXXXXXX
    """

    def _replace(m: re.Match) -> str:
        seq = m.group(0)
        c = seq[1]
        if c == "n":
            return "\n"
        if c == "t":
            return "\t"
        if c == "r":
            return "\r"
        if c == '"':
            return '"'
        if c == "\\":
            return "\\"
        if c == "x":
            return chr(int(seq[2:4], 16))
        if c == "u":
            return chr(int(seq[2:6], 16))
        if c == "U":
            return chr(int(seq[2:10], 16))
        return seq

    return re.sub(
        r'\\(?:[ntr"\\]|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})', _replace, s
    )
