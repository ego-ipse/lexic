"""The COMPILING relation — a reader, as the machine it compiles to.

A room like any other, and a different subject from the reading it serves:
the reading is about a text, this is about the machine that reads it. Its
facts are read off the compiled artifact, so they cannot drift from what the
parse actually drives.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import machine
from reading import turn
from relate import KINDS, SUBJECT, Relation, Role, Thing

__all__ = ["Compiling"]


class Compiling(Relation):
    """A thing that can read, standing as the machine it becomes."""

    kind = "compiling"
    slots = (SUBJECT,)

    def __init__(self, rid: str, cast: Mapping[str, Thing]) -> None:
        super().__init__(rid, cast)
        self.clones = 0
        self.rules = 0
        self.classes: dict[str, int] = {}

    @classmethod
    def licenses(cls, role: Role, thing: Thing) -> bool:
        """Only what the engine actually compiles has a machine to show."""
        return role is SUBJECT and turn(thing) is not None

    def label(self) -> str:
        return f"{self.cast[SUBJECT.name].name} — as a machine"

    def hold(self) -> None:
        if self.held:
            return
        self.held = True
        turned = turn(self.cast[SUBJECT.name])
        if turned is None:
            return
        drawn = machine.automaton(turned.machine.pda_tables())
        self.clones = int(drawn.split(" ", 1)[1].split("\n", 1)[0])
        said = machine.verdicts(turned.machine).splitlines()
        self.rules = int(said[0].split(" ")[1])
        for row in said[1:]:
            parts = row.split(" ")
            if len(parts) >= 3 and parts[1].isdigit():
                self.classes[parts[0]] = self.classes.get(parts[0], 0) + 1

    def facts(self) -> str:
        """Built, and entered — two different facts about one machine.

        The compiler cuts a clone per hard continuation; a reading enters the
        ones its text asks for. Reporting only the first makes the automaton
        view look wrong, and only the second hides what was compiled.
        """
        said = " · ".join(f"{n} {k}" for k, n in sorted(self.classes.items()))
        return (
            f"{self.clones} clones built · {self.rules} rules"
            f"{' · ' + said if said else ''}"
        )

    def parts(self) -> Sequence[Thing]:
        return list(self.cast.values())


KINDS[Compiling.kind] = Compiling
