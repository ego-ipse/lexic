from __future__ import annotations


def decode_gbnf_escapes(s: str) -> str:
    """Decode GBNF string escape sequences to real chars."""
    return (
        s.replace("\\\\", "\x00BS\x00")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace("\\r", "\r")
        .replace('\\"', '"')
        .replace("\x00BS\x00", "\\")
    )
