"""Editing — because an edit is a RE-READING, not a patch on the value.

Text is primary; the model is only the grammar's account of what the text
says. So a commit splices characters and reads again, and everything derived
re-derives or nothing changes. A refused re-read restores the document and
reports WHERE derivation died — measured off the kernel's own cursor, not
read out of an exception's prose.

Saving the instrument's own record APPLIES it. That is the ring: no special
machinery, because the record is a document like any other.
"""

from __future__ import annotations

from pathlib import Path

from clocks import ClockKernel
from lexic.exceptions import LexicError
from lexic.parsing.pda.core.errors import PdaFail
from reading import Reading, turn
from relate import DOCUMENT, READER, Session, Text

__all__ = ["Result", "frontier", "retype", "save"]

# The corpus is ground truth for the whole engine; the instrument reads it and
# refuses to be the thing that rewrites it.
GUARDED = ("resources/ground_truth",)


class Result:
    """What a re-reading did, in the words the wire uses."""

    __slots__ = ("held", "pos", "seconds", "state", "words")

    def __init__(self, state: str) -> None:
        self.state = state
        self.seconds = 0.0
        self.pos = -1
        self.words = ""
        self.held = ""

    def spell(self) -> str:
        if self.state == "refuse":
            return f"refuse {self.pos}\n{self.words}\n"
        if self.held:
            return f"ok {self.seconds:.2f} held {self.held}\n"
        tail = " saved" if self.state == "saved" else ""
        return f"ok {self.seconds:.2f}{tail}\n"


def frontier(relation: Reading, text: str) -> int:
    """Where the predictive route stopped — the kernel's own cursor, measured."""
    turned = turn(relation.cast[READER.name])
    if turned is None:
        return -1
    kernel = ClockKernel(turned.machine.pda_tables(), text, turned.machine.fold)
    try:
        kernel.run()
    except PdaFail:
        return kernel.pos
    except LexicError:
        return -1
    return -1


def retype(session: Session, rid: str, start: int, end: int, put: str) -> Result:
    """Splice the characters and read again. The value follows the text."""
    relation = session.relations.get(rid)
    if not isinstance(relation, Reading):
        return _refused("no reading is focused", -1)
    document = relation.cast[DOCUMENT.name]
    if not isinstance(document, Text):
        return _refused("this document is not text — it cannot be typed into", -1)
    was = document.text
    document.text = was[:start] + put + was[end:]
    relation.reread()
    if relation.words:
        stop = frontier(relation, document.text)
        words = relation.words
        document.text = was
        relation.reread()
        return _refused(words, stop)
    done = Result("ok")
    done.seconds = relation.seconds
    return done


def save(session: Session, rid: str, start: int, end: int, put: str) -> Result:
    """Re-read, then persist. Saving compiles; a refusal writes nothing."""
    done = retype(session, rid, start, end, put)
    if done.state != "ok":
        return done
    relation = session.relations[rid]
    if not isinstance(relation, Reading):
        return _refused("no reading is focused", -1)
    document = relation.cast[DOCUMENT.name]
    if apply_ring(session, relation):
        done.held = "this record IS the instrument — saving applied it"
        return done
    path = getattr(document, "path", None)
    if not isinstance(path, Path):
        done.held = "this document has no file behind it"
        return done
    if any(guard in str(path) for guard in GUARDED):
        done.held = "the ground-truth corpus is never overwritten"
        return done
    path.write_text(document.spelling())
    done.state = "saved"
    return done


def apply_ring(session: Session, relation: Reading) -> bool:
    """If this reading is the instrument's own record, pour it back in.

    The parse already proved the record well-formed; applying it is reading
    the lines it holds. Nothing else in the session knows this happened —
    the leaves poll the policy and rearrange.
    """
    if relation.cast[DOCUMENT.name].tid != "t.policy.record":
        return False
    fresh: dict[str, str] = {}
    for line in relation.document().splitlines():
        key, _, value = line.partition(" ")
        if key:
            fresh[key] = value
    session.policy.clear()
    session.policy.update(fresh)
    return True


def _refused(words: str, pos: int) -> Result:
    out = Result("refuse")
    out.words = words
    out.pos = pos
    return out
