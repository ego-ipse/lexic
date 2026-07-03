"""Name conversion utilities: snake_case and PascalCase."""

from __future__ import annotations

import keyword
import re


def to_pascal(name: str) -> str:
    """Convert 'jp-char' or 'json_ws' to 'JpChar' / 'JsonWs'.

    A result that collides with a Python keyword (``False``, ``True``,
    ``None``, …) is suffixed with ``_`` so it stays a valid class name.
    """
    parts = re.split(r"[-_]", name)
    pascal = "".join(p[0].upper() + p[1:] if p else "" for p in parts)
    return f"{pascal}_" if keyword.iskeyword(pascal) else pascal


_SNAKE_RE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_RE_2 = re.compile(r"([a-z0-9])([A-Z])")


def to_snake(name: str) -> str:
    """Convert 'JsonWs' or 'JPChar' to 'json_ws' / 'jp_char'."""
    s1 = _SNAKE_RE_1.sub(r"\1_\2", name)
    return _SNAKE_RE_2.sub(r"\1_\2", s1).lower()
