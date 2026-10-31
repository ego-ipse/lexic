"""Extensions — the fixpoints' working maps, and the atom bodies they share.

EXTEND and NON_INITIAL each grow a map of every rule's set to a fixpoint, riding
the same :class:`Extensions` through ``nc``; the atom bodies here answer alike
in both tables.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple, Sequence, cast

from lexic.ir import IrAtom, IrItem, IrRule, IrSelf
from lexic.parsing.pda.analysis.gates.windows import KWindowFirst
from lexic.parsing.pda.analysis.predicates import rule_alphabets
from lexic.parsing.pda.core.charsets import CharSet

type Arm = Sequence[IrItem]
"""One arm, or any sequence of items, held by identity."""

type RunKey = tuple[tuple[int, ...], CharSet]
"""A sequence's items by identity, and the run class it is read against. The
entry holds the items, so no id in a live key can be another object's."""


type TailsKey = tuple[str, CharSet]
"""A rule and the run class its TAILS are read against."""

type Verdict = tuple[Arm | IrAtom, bool]
"""The sequence (or repeated atom) a verdict was asked at, and the verdict."""


class Solve(NamedTuple):
    """One TAILS solve under way, from the ask that started it.

    :ivar keys: Every key it has met, in the order met.
    :ivar busy: The keys whose arms are being read now.
    :ivar looped: The keys read while busy — a cycle, which passes settle.
    :ivar verdicts: The verdicts read since the current pass began.
    """

    keys: list[TailsKey]
    busy: set[TailsKey]
    looped: set[TailsKey]
    verdicts: dict[tuple[int, int], Verdict]


class Confinement(NamedTuple):
    """R3's answers over one EXTEND build — a shift confined to a run.

    The structural lanes read the grammar alone and hold for the whole build.
    ``tails`` and the verdicts read the maps: a False verdict is kept as the
    maps grow (it falls back to the sound bound), and :meth:`reopen` drops the
    rest so the build re-asks them on its final maps.

    :ivar runs: Every character some run holds, once read.
    :ivar leads: Items and a class K → the items, and the class of their
        leading runs.
    :ivar led: Items and a run class → the items, and whether they are led
        by it.
    :ivar heads: Items and a run class → the items, and their first
        characters past it.
    :ivar made: An atom's id → the atom, and one occurrence of it, which R3
        reads in its place. Kept, so it keeps one identity.
    :ivar apart: Two arms' ids → the arms and whether they part on a run.
    :ivar tails: A rule and a run class → TAILS so far.
    :ivar solve: The TAILS solve under way, if one is.
    :ivar verdicts: A sequence's id and an index (an atom's id and -1, for a
        repetition) → the sequence or atom, and R3's verdict there.
    """

    runs: list[CharSet]
    leads: dict[RunKey, tuple[Arm, CharSet | None]]
    led: dict[RunKey, tuple[Arm, bool]]
    heads: dict[RunKey, tuple[Arm, CharSet]]
    made: dict[int, tuple[IrAtom, IrItem]]
    apart: dict[tuple[int, int], tuple[Arm, Arm, bool]]
    tails: dict[TailsKey, CharSet]
    solve: list[Solve]
    verdicts: dict[tuple[int, int], Verdict]

    @classmethod
    def empty(cls) -> Confinement:
        """No answer read yet."""
        return cls([], {}, {}, {}, {}, {}, {}, [], {})

    def once(self, atom: IrAtom) -> IrItem:
        """One occurrence of ``atom``, the same item at every ask."""
        held = self.made.get(id(atom))
        if held is None:
            held = self.made[id(atom)] = (atom, IrItem(atom))
        return held[1]

    def verdict(self, key: tuple[int, int], site: Arm | IrAtom) -> bool | None:
        """The verdict kept at ``site`` — for the build, or for the solve's
        current pass — or ``None``."""
        for kept in (self.verdicts, *(one.verdicts for one in self.solve)):
            held = kept.get(key)
            if held is not None and held[0] is site:
                return held[1]
        return None

    def keep(self, key: tuple[int, int], site: Arm | IrAtom, got: bool) -> None:
        """Keep a verdict: for the solve's current pass while one is under way,
        whose TAILS may still grow, else for the build."""
        kept = self.solve[0].verdicts if self.solve else self.verdicts
        kept[key] = (site, got)

    def reopen(self) -> list[tuple[Arm | IrAtom, int]]:
        """Drop every answer the maps could still refute — TAILS and the True
        verdicts — and return each dropped verdict's site and index."""
        stale = [key for key, (_, ok) in self.verdicts.items() if ok]
        sites = [(self.verdicts.pop(key)[0], key[1]) for key in stale]
        self.tails.clear()
        return sites


class Extensions(NamedTuple):
    """An EXTEND or NON_INITIAL fixpoint's working maps, riding ``nc``.

    :ivar found: Rule name → its EXTEND (or NON_INITIAL) so far.
    :ivar alphabets: Rule name → its ALPHABET, the bound EXTEND falls back to.
    :ivar windows: FIRST\\ :sub:`2` over the grammar, for the shift test.
    :ivar confined: R3's answers, which only EXTEND reads.
    """

    found: dict[str, CharSet]
    alphabets: dict[str, CharSet]
    windows: KWindowFirst
    confined: Confinement

    @classmethod
    def empty(cls, rules: Mapping[str, IrRule]) -> Extensions:
        """Every rule's set empty, the fixpoint's start, over ``rules``."""
        found = {name: CharSet.EMPTY for name in rules}
        alphabets = rule_alphabets(rules)
        return cls(found, alphabets, KWindowFirst(rules, 2), Confinement.empty())


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
