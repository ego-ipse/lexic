"""Shared authored-fold vocabulary — the build-path unification seed.

Every hand-authored grammar+fold pair in the compile package (the notation,
the module self-grammar, and future authored surfaces) repeats the same
idioms: an alternation pass-through, a value pass-through, and
``RuleFold``-table construction. This module is their single home, so a
fifth authored surface never copies a fourth variant.
"""

from __future__ import annotations

from lexic.parsing import RuleFold

__all__ = ["ALT", "passthrough"]


def _none() -> None:
    """The unused alternation ctor slot (`kind == "alternation"` ignores it)."""
    return None


ALT = RuleFold("alternation", _none, 0, ())
"""The shared alternation pass-through — the matched arm's model IS the result."""


def passthrough(v: object) -> object:
    """A single-field sequence rule's identity ctor.

    :param v: The one bound child.
    :returns: ``v`` unchanged.
    """
    return v
