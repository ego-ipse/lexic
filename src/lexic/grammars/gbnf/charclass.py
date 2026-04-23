"""Parse GBNF bracket expressions into concrete character lists.

Shared by `lexic.generate` (random generation) and, eventually, any emitter
that needs to enumerate a character class.
"""

from __future__ import annotations


def parse_escape(s: str, i: int) -> tuple[str, int]:
    """Parse a GBNF escape sequence starting at s[i+1]. Returns (char, new_i)."""
    c = s[i + 1]
    if c == "n":
        return "\n", i + 2
    if c == "t":
        return "\t", i + 2
    if c == "r":
        return "\r", i + 2
    if c == '"':
        return '"', i + 2
    if c == "\\":
        return "\\", i + 2
    if c == "x" and i + 3 < len(s):
        return chr(int(s[i + 2 : i + 4], 16)), i + 4
    if c == "u" and i + 5 < len(s):
        return chr(int(s[i + 2 : i + 6], 16)), i + 6
    if c == "U" and i + 9 < len(s):
        return chr(int(s[i + 2 : i + 10], 16)), i + 10
    return c, i + 2


def parse_charclass_chars(inner: str) -> list[str]:
    """Parse the interior of a GBNF bracket expression into a list of chars.

    Supports ranges (a-z), direct Unicode, and escape sequences
    (\\n \\t \\r \\xXX \\uXXXX \\UXXXXXXXX).
    """
    chars: list[str] = []
    i = 0
    while i < len(inner):
        if inner[i] == "\\" and i + 1 < len(inner):
            ch, i = parse_escape(inner, i)
            if i < len(inner) and inner[i] == "-" and i + 1 < len(inner):
                if inner[i + 1] == "\\" and i + 2 < len(inner):
                    end_ch, i = parse_escape(inner, i + 1)
                else:
                    end_ch = inner[i + 1]
                    i += 2
                chars.extend(chr(c) for c in range(ord(ch), ord(end_ch) + 1))
            else:
                chars.append(ch)
        elif i + 2 < len(inner) and inner[i + 1] == "-":
            chars.extend(chr(c) for c in range(ord(inner[i]), ord(inner[i + 2]) + 1))
            i += 3
        else:
            chars.append(inner[i])
            i += 1
    return chars
