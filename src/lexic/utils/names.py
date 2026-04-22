from __future__ import annotations

import re


def to_lark_name(rule_name: str) -> str:
    """Convert a GBNF rule name to a valid Lark rule identifier.

    Lark rules must be all-lowercase; terminals start with uppercase.
    Hyphens are not valid in identifiers, so we replace them with underscores.
    """
    return rule_name.replace("-", "_").lower()


def to_pascal(name: str) -> str:
    """Convert 'jp-char' or 'json_ws' to 'JpChar' / 'JsonWs'."""
    parts = re.split(r"[-_]", name)
    return "".join(p[0].upper() + p[1:] if p else "" for p in parts)


_SNAKE_RE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_RE_2 = re.compile(r"([a-z0-9])([A-Z])")


def to_snake(name: str) -> str:
    """Convert 'JsonWs' or 'JPChar' to 'json_ws' / 'jp_char'."""
    s1 = _SNAKE_RE_1.sub(r"\1_\2", name)
    return _SNAKE_RE_2.sub(r"\1_\2", s1).lower()
