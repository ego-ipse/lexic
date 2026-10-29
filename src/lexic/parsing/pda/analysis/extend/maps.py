"""Extensions — the fixpoints' working maps, and the atom bodies they share.

EXTEND and NON_INITIAL each grow a map of every rule's set to a fixpoint, riding
the same :class:`Extensions` through ``nc``; the atom bodies here answer alike
in both tables.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple, Sequence, cast

from lexic.ir import IrRule, IrSelf
from lexic.parsing.pda.analysis.gates.windows import KWindowFirst
from lexic.parsing.pda.analysis.predicates import rule_alphabets
from lexic.parsing.pda.core.charsets import CharSet


class Extensions(NamedTuple):
    """An EXTEND or NON_INITIAL fixpoint's working maps, riding ``nc``.

    :ivar found: Rule name → its EXTEND (or NON_INITIAL) so far.
    :ivar alphabets: Rule name → its ALPHABET, the bound EXTEND falls back to.
    :ivar windows: FIRST\\ :sub:`2` over the grammar, for the shift test.
    """

    found: dict[str, CharSet]
    alphabets: dict[str, CharSet]
    windows: KWindowFirst

    @classmethod
    def empty(cls, rules: Mapping[str, IrRule]) -> Extensions:
        """Every rule's set empty, the fixpoint's start, over ``rules``."""
        found = {name: CharSet.EMPTY for name in rules}
        return cls(found, rule_alphabets(rules), KWindowFirst(rules, 2))


def nothing(_d: object, _n: IrSelf, _nc: object) -> CharSet:
    """A literal is one string and a class one character: nothing extends."""
    return CharSet.EMPTY


def anything(_d: object, _n: IrSelf, _nc: object) -> CharSet:
    """A token atom's extensions are not enumerable: conservatively all."""
    return CharSet.ANY


def found_ruleref(_d: object, n: IrSelf, nc: Sequence[object]) -> CharSet:
    """A rule ref reads its target at its CURRENT value in the fixpoint's
    maps — EXTEND and NON_INITIAL alike; an undefined one is ANY."""
    got = cast(Extensions, nc).found.get(str(n))
    return CharSet.ANY if got is None else got
