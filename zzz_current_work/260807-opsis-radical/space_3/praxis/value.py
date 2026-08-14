"""Immutable Lexic-value snapshots of mutable Praxis state.

Praxis objects have application lifetimes: a Session and its Graph mutate as
the hand travels.  Lexic values are immutable structural data.  The proper
boundary is therefore a projection, not making application owners inherit an
engine value type.  One snapshot puts Reading, Facet, Rung, Subject, Relation,
and Session on the same generic value spine used by every other IrSelf.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lexic.ir import IrInt, IrNamedTuple, IrStr, IrTuple

from praxis.state import Rung

if TYPE_CHECKING:
    from praxis.graph import Relation, Subject
    from praxis.reading import Facet, Reading
    from praxis.session import Session

__all__ = [
    "PraxisFacet",
    "PraxisReading",
    "PraxisRelation",
    "PraxisRung",
    "PraxisSession",
    "PraxisSubject",
    "snapshot",
]


class PraxisFacet(IrNamedTuple[IrStr, IrStr, IrInt, IrInt, IrStr, IrStr, IrStr]):
    """One reading surface and the room it requires."""

    name: IrStr
    kind: IrStr
    wide: IrInt
    tall: IrInt
    title: IrStr
    column: IrStr
    relation: IrStr


class PraxisReading(
    IrNamedTuple[IrStr, IrStr, IrStr, IrStr, IrInt, IrInt, IrStr, IrStr]
):
    """One read relation, addressed by the content it joins."""

    identity: IrStr
    reader: IrStr
    document: IrStr
    flavour: IrStr
    faithful: IrInt
    spans: IrInt
    seconds: IrStr
    verdict: IrStr


class PraxisRung(IrNamedTuple[IrStr, IrStr, IrInt, IrInt]):
    """One rung of the ladder projection."""

    document: IrStr
    reader: IrStr
    level: IrInt
    visited: IrInt


class PraxisSubject(IrNamedTuple[IrStr, IrStr, IrStr, IrInt]):
    """One content-addressed graph subject."""

    identity: IrStr
    kind: IrStr
    name: IrStr
    chars: IrInt


class PraxisRelation(IrNamedTuple[IrStr, IrStr, IrStr, IrStr, IrStr, IrInt]):
    """One graph edge with its roles and compile flavour retained."""

    identity: IrStr
    kind: IrStr
    flavour: IrStr
    reader: IrStr
    document: IrStr
    generation: IrInt


class PraxisPolicy(IrNamedTuple[IrStr, IrStr]):
    """One effective presentation-policy entry."""

    key: IrStr
    value: IrStr


class PraxisSession(
    IrNamedTuple[
        PraxisReading,
        IrTuple,
        IrTuple,
        IrTuple,
        IrTuple,
        IrTuple,
        IrStr,
        IrInt,
        IrStr,
    ]
):
    """The instrument's current Praxis topology as one immutable value."""

    reading: PraxisReading
    facets: IrTuple
    rungs: IrTuple
    subjects: IrTuple
    relations: IrTuple
    policy: IrTuple
    focus: IrStr
    generation: IrInt
    cursor: IrStr


def _reading(reading: Reading) -> PraxisReading:
    return PraxisReading(
        IrStr(reading.identity),
        IrStr(reading.reader_name),
        IrStr(reading.document.name),
        IrStr(reading.flavour or "unresolved"),
        IrInt(reading.faithful),
        IrInt(len(reading.spans)),
        IrStr(f"{reading.seconds:.6f}"),
        IrStr("holds" if reading.faithful else reading.words or "unread"),
    )


def _facet(facet: Facet) -> PraxisFacet:
    return PraxisFacet(
        IrStr(facet.name),
        IrStr(facet.kind),
        IrInt(facet.wide),
        IrInt(facet.tall),
        IrStr(facet.title),
        IrStr(facet.column),
        IrStr(facet.relation),
    )


def _rung(rung: Rung) -> PraxisRung:
    return PraxisRung(
        IrStr(rung.document),
        IrStr(rung.reader),
        IrInt(rung.level),
        IrInt(rung.visited),
    )


def _subject(subject: Subject) -> PraxisSubject:
    return PraxisSubject(
        IrStr(subject.sid),
        IrStr(subject.kind),
        IrStr(subject.name),
        IrInt(subject.chars),
    )


def _relation(relation: Relation) -> PraxisRelation:
    return PraxisRelation(
        IrStr(relation.rid),
        IrStr(relation.kind),
        IrStr(relation.flavour or "unresolved"),
        IrStr(relation.reader),
        IrStr(relation.document),
        IrInt(relation.generation),
    )


def snapshot(session: Session) -> PraxisSession:
    """Project the live session without transferring ownership or identity."""
    climbed = session.climbed
    rungs = [
        Rung(reading.document.name, reading.reader_name, at, True)
        for at, reading in enumerate(climbed)
    ]
    return PraxisSession(
        _reading(session.reading),
        IrTuple(*(_facet(facet) for facet in session.reading.facets())),
        IrTuple(*(_rung(rung) for rung in rungs)),
        IrTuple(
            *(_subject(item) for _, item in sorted(session.graph.subjects.items()))
        ),
        IrTuple(
            *(_relation(item) for _, item in sorted(session.graph.relations.items()))
        ),
        IrTuple(
            *(
                PraxisPolicy(IrStr(key), IrStr(value))
                for key, value in sorted(session.main.items())
            )
        ),
        IrStr(session.graph.focus),
        IrInt(session.generation),
        IrStr(f"{session.at:.3f}"),
    )
