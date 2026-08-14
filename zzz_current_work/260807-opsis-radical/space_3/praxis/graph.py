"""Content-addressed subjects and the reading relations between them.

The ladder is deliberately absent from storage. It is a projection of the
lineage edges rooted at the first reading, so entering the policy relation
cannot splice the instrument into that lineage.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praxis.reading import Reading

__all__ = ["Graph", "Relation", "Subject", "digest"]


def digest(kind: str, *parts: str) -> str:
    """Return a stable content address with unambiguous part boundaries."""
    made = hashlib.sha256()
    for part in (kind, *parts):
        raw = part.encode("utf-8")
        made.update(len(raw).to_bytes(8, "big"))
        made.update(raw)
    return made.hexdigest()


@dataclass(frozen=True, slots=True)
class Subject:
    """One small graph node; its characters stay on the reading, not twice."""

    sid: str
    kind: str
    name: str
    chars: int


@dataclass(slots=True)
class Relation:
    """One reading: subjects cast in the reader and document roles."""

    rid: str
    kind: str
    flavour: str
    reader: str
    document: str
    reading: Reading
    generation: int = 1


class Graph:
    """All subjects and reading relations held for one instrument session."""

    __slots__ = (
        "_by_object",
        "focus",
        "lineage",
        "relations",
        "root",
        "subjects",
    )

    def __init__(self, reading: Reading) -> None:
        self.subjects: dict[str, Subject] = {}
        self.relations: dict[str, Relation] = {}
        self.lineage: dict[str, str] = {}
        self._by_object: dict[int, str] = {}
        canonical = self.add(reading)
        self.root = canonical.identity
        self.focus = self.root

    def _subject(self, name: str, text: str) -> str:
        sid = digest("text", text)
        self.subjects.setdefault(sid, Subject(sid, "text", name, len(text)))
        return sid

    def add(self, reading: Reading, kind: str = "read") -> Reading:
        """Add a relation or return the live reading already representing it."""
        reader = self._subject(reading.reader_name, reading.reader_text)
        document = self._subject(reading.document.name, reading.text)
        rid = digest(
            "reading",
            kind,
            reading.flavour or "unresolved",
            reader,
            document,
        )
        known = self.relations.get(rid)
        if known is not None:
            return known.reading
        self.relations[rid] = Relation(
            rid, kind, reading.flavour, reader, document, reading
        )
        self._by_object[id(reading)] = rid
        return reading

    def relation(self, reading: Reading) -> Relation | None:
        """Return the relation holding this exact live object, if present."""
        rid = self._by_object.get(id(reading))
        return self.relations.get(rid) if rid is not None else None

    def enter(self, reading: Reading, kind: str = "read") -> Reading:
        """Focus a relation, deduplicating equal content on the way in."""
        canonical = self.add(reading, kind)
        relation = self.relation(canonical)
        if relation is None:  # pragma: no cover - guarded by add()
            raise RuntimeError("graph lost a relation it just added")
        self.focus = relation.rid
        return canonical

    def link(self, below: Reading, above: Reading) -> Reading:
        """Record one lineage edge and return the canonical upper reading."""
        lower = self.add(below)
        upper = self.add(above)
        low = self.relation(lower)
        high = self.relation(upper)
        if low is None or high is None:  # pragma: no cover - guarded by add()
            raise RuntimeError("graph lost a lineage endpoint")
        self.lineage[low.rid] = high.rid
        return upper

    def walked(self) -> list[Reading]:
        """Derive the rooted lineage path from graph edges."""
        out: list[Reading] = []
        seen: set[str] = set()
        rid = self.root
        while rid not in seen and rid in self.relations:
            seen.add(rid)
            out.append(self.relations[rid].reading)
            following = self.lineage.get(rid)
            if following is None:
                break
            rid = following
        return out

    def refresh(self, reading: Reading) -> Reading:
        """Re-address a successfully edited relation without stale graph keys."""
        old_rid = self._by_object.get(id(reading))
        if old_rid is None:
            return self.add(reading)
        old = self.relations[old_rid]
        reader = self._subject(reading.reader_name, reading.reader_text)
        document = self._subject(reading.document.name, reading.text)
        new_rid = digest(
            "reading",
            old.kind,
            reading.flavour or "unresolved",
            reader,
            document,
        )
        if new_rid == old_rid:
            old.generation += 1
            return reading

        replacement = self.relations.get(new_rid)
        if replacement is None:
            replacement = Relation(
                new_rid,
                old.kind,
                reading.flavour,
                reader,
                document,
                reading,
                old.generation + 1,
            )
            self.relations[new_rid] = replacement
        else:
            replacement.generation += 1

        self._by_object.pop(id(reading), None)
        self._by_object[id(replacement.reading)] = new_rid
        if self.root == old_rid:
            self.root = new_rid
        if self.focus == old_rid:
            self.focus = new_rid
        self.lineage = {
            (new_rid if start == old_rid else start):
            (new_rid if stop == old_rid else stop)
            for start, stop in self.lineage.items()
        }
        del self.relations[old_rid]
        return replacement.reading
