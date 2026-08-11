"""The instrument as a subject of itself — the ring.

The session's presentation state is already a line-oriented text; giving it a
grammar makes it a READING like any other, with spans, a spine, a verdict and
rooms. Nothing special is built for it: the ladder closes into a ring because
the instrument is one more thing the standard pipeline can read.
"""

from __future__ import annotations

from pathlib import Path

from reading import Reading
from relate import DOCUMENT, READER, Session, Text

__all__ = ["POLICY_GRAMMAR", "refresh"]

POLICY_GRAMMAR = Path(__file__).resolve().parent / "fixtures" / "policy.gbnf"

_READER = "t.policy.reader"
_RECORD = "t.policy.record"


def text_of(session: Session) -> str:
    """The policy as the record it is — one key and value per line."""
    return "".join(f"{key} {value}\n" for key, value in sorted(session.policy.items()))


def refresh(session: Session) -> str | None:
    """Read the instrument's own state, again. Returns the relation's address.

    Called whenever the state moves, because a reading of a text that has
    changed is a new reading — the record is the document, and the document
    is what changed.
    """
    record = text_of(session)
    if not record.strip():
        return None
    reader = _thing(session, _READER, POLICY_GRAMMAR.name, POLICY_GRAMMAR.read_text())
    document = _thing(session, _RECORD, "the session policy", record)
    if document.text != record:
        document.text = record
    rid = session.find("reading", {READER.name: reader, DOCUMENT.name: document})
    if rid is not None:
        relation = session.relations[rid]
        if isinstance(relation, Reading) and relation.held:
            relation.reread()
        return rid
    return session.enter(
        "reading", {READER.name: reader, DOCUMENT.name: document}, hold=False
    )


_THINGS: dict[str, Text] = {}


def _thing(session: Session, tid: str, name: str, text: str) -> Text:
    """One thing per address, kept so identity — and the graph — survive."""
    if tid not in _THINGS:
        _THINGS[tid] = Text(tid, name, text)
    return _THINGS[tid]
