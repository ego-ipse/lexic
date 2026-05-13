# src/lexic/ir/regex_portable.py
"""Portable regex subset for PatternAtom.regex.

Defines the IR-level contract: which regex features are allowed in canonical
PatternAtom.regex strings (CFG-portable subset), and utilities to validate a
regex against that contract and to enumerate the features it uses.

Each FlavourEmitter declares a `supports: frozenset[str]` subset of
PORTABLE_FEATURES; the codegen pipeline cross-checks every PatternAtom
against the target flavour's supports set before emission.
"""

from __future__ import annotations

# pylint: disable=no-member  # re._constants and re._parser are private; pylint cannot introspect them
import re._constants as _rc_impl  # type: ignore[attr-defined]  # private; no stubs in 3.11–3.13
import re._parser as _rp_impl  # type: ignore[attr-defined]  # private; no stubs in 3.11–3.13
from typing import Any

from lexic.exceptions import UnsupportedConstructError

# Typed as Any so attribute access is unrestricted by pyright/mypy.
_rc: Any = _rc_impl
_rp: Any = _rp_impl


_LITERAL_REGEX_ESCAPES: dict[str, str] = {
    # Control characters → regex escape sequences
    "\n": r"\n",
    "\r": r"\r",
    "\t": r"\t",
    # Backslash must come first so we don't double-escape other entries
    "\\": r"\\",
    # Lark regex delimiter
    "/": r"\/",
    # Regex metacharacters
    ".": r"\.",
    "^": r"\^",
    "$": r"\$",
    "*": r"\*",
    "+": r"\+",
    "?": r"\?",
    "{": r"\{",
    "}": r"\}",
    "[": r"\[",
    "]": r"\]",
    "(": r"\(",
    ")": r"\)",
    "|": r"\|",
}


def literal_to_regex_pattern(value: str) -> str:
    """Escape a literal string so it matches exactly when used inside a regex pattern.

    Handles control characters (\\n, \\r, \\t), the backslash, regex
    metacharacters, and the Lark regex delimiter (/).
    """
    return "".join(_LITERAL_REGEX_ESCAPES.get(c, c) for c in value)


PORTABLE_FEATURES: frozenset[str] = frozenset(
    {
        "literal",
        "char_class",
        "negated_class",
        "shorthand",
        "quantifier",
        "alternation",
        "non_capturing_group",
        "unicode_escape",
    }
)

_SubPattern = Any  # re._parser.SubPattern — private type, not exported

_AT_DESCRIPTIONS: dict[Any, str] = {
    _rc.AT_BEGINNING: "anchor ^",
    _rc.AT_END: "anchor $",
    _rc.AT_BOUNDARY: r"word boundary \b",
    _rc.AT_NON_BOUNDARY: r"non-word-boundary \B",
}

_SIMPLE_FORBIDDEN: dict[Any, str] = {
    _rc.ANY: "`.` (any-char); use an explicit char class",
    _rc.GROUPREF: "a backreference (not allowed in portable IR)",
}

_REPEAT_OPS: frozenset[Any] = frozenset({_rc.MAX_REPEAT, _rc.MIN_REPEAT})


def validate_portable(regex: str) -> None:
    """Raise UnsupportedConstructError if regex uses non-CFG features.

    Forbidden: anchors, lookarounds, backrefs, inline flags, capturing
    groups (must be non-capturing), word boundaries, `.` any-char.
    """
    _walk_validate(_parse(regex), regex)


def features_used(regex: str) -> frozenset[str]:
    """Return the PORTABLE_FEATURES subset this regex uses.

    Precondition: regex has been validated via validate_portable().
    """
    used: set[str] = set()
    _walk_features(_parse(regex), used)
    return frozenset(used)


def canonicalize_groups(regex: str) -> str:
    """Rewrite capturing groups to non-capturing.

    Phase 1: no-op stub.
    """
    return regex  # TODO(slice-b-phase-2): replace with real implementation


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse(regex: str) -> _SubPattern:
    try:
        return _rp.parse(regex)
    except Exception as exc:
        raise UnsupportedConstructError(f"Cannot parse regex {regex!r}: {exc}") from exc


def _walk_validate(tree: _SubPattern, regex: str) -> None:
    for op, arg in tree:
        if op is _rc.AT:
            desc = _AT_DESCRIPTIONS.get(arg, f"anchor {arg!r}")
            raise UnsupportedConstructError(
                f"Regex {regex!r} uses {desc} (not allowed in portable IR)"
            )
        desc = _SIMPLE_FORBIDDEN.get(op)
        if desc is not None:
            raise UnsupportedConstructError(f"Regex {regex!r} uses {desc}")
        if op is _rc.SUBPATTERN:
            _validate_subpattern(arg, regex)
        elif op is _rc.BRANCH:
            _, branches = arg
            for branch in branches:
                _walk_validate(branch, regex)
        elif op in _REPEAT_OPS:
            _, _, subtree = arg
            _walk_validate(subtree, regex)


def _validate_subpattern(arg: Any, regex: str) -> None:
    group_num, add_flags, del_flags, subtree = arg
    if group_num is not None:
        raise UnsupportedConstructError(
            f"Regex {regex!r} uses a capturing group (use (?:...) instead)"
        )
    if add_flags or del_flags:
        raise UnsupportedConstructError(
            f"Regex {regex!r} uses inline flags (not allowed in portable IR)"
        )
    _walk_validate(subtree, regex)


def _walk_features(tree: _SubPattern, used: set[str]) -> None:
    for op, arg in tree:
        if op in (_rc.LITERAL, _rc.NOT_LITERAL):
            used.add("literal")
        elif op is _rc.IN:
            _collect_charclass_features(arg, used)
        elif op is _rc.BRANCH:
            used.add("alternation")
            _, branches = arg
            for branch in branches:
                _walk_features(branch, used)
        elif op is _rc.SUBPATTERN:
            used.add("non_capturing_group")
            _, _, _, subtree = arg
            _walk_features(subtree, used)
        elif op in _REPEAT_OPS:
            used.add("quantifier")
            _, _, subtree = arg
            _walk_features(subtree, used)


def _collect_charclass_features(arg: Any, used: set[str]) -> None:
    negated = any(sub_op is _rc.NEGATE for sub_op, _ in arg)
    used.add("negated_class" if negated else "char_class")
    for sub_op, _ in arg:
        if sub_op is _rc.CATEGORY:
            used.add("shorthand")
