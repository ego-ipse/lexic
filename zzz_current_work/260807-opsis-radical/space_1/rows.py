"""The presentation rows — one per kind, each a claim about what a thing IS.

A row is data, not a method: it takes a value and the address that reached
it, and returns regions. Rows are registered by type name and found by MRO,
so ``IrStr`` is met by the scalar row without anyone editing a cascade, and a
kind nobody authored draws the refusal in place.

Two claims are made here and they are the whole design:

- A SCALAR is its payload, so it shows its payload and nothing else.
- A RECORD is its field tuple, so every field is a region addressed by the
  field's own name — which is what makes a click mean ``value.member.string``
  rather than "the thing at x=412".
"""

from __future__ import annotations

from collections.abc import Sequence

from lexic.model import GrammarModel
from screen import ROWS, Region, Row, spell

__all__ = ["register"]

CEILING = 512


def register(name: str, row: Row) -> None:
    """Claim a kind. Later claims win, so a domain row can outrank a generic."""
    ROWS[name] = row


def _kids(thing: object) -> list[tuple[str, object]]:
    """This thing's parts, named the way its own tier names them.

    A record IS its field tuple — read the tuple, not ``children()``, because
    the filtered view cannot see that one object sits in two hundred places.
    """
    fields = getattr(type(thing), "_fields", ())
    if fields and isinstance(thing, tuple):
        return [(str(name), thing[at]) for at, name in enumerate(fields)]
    if isinstance(thing, tuple):
        return [(str(at), part) for at, part in enumerate(thing)]
    ask = getattr(thing, "children", None)
    kids = ask() if callable(ask) else ()
    if isinstance(kids, Sequence):
        return [(str(at), part) for at, part in enumerate(kids)]
    return []


def scalar(thing: object, at: str) -> Region:
    """A scalar IS its payload: show the payload, claim nothing else."""
    ink = str(thing).replace("\n", "\\n")
    return Region("scalar", ink[:120], at)


def record(thing: object, at: str) -> Region:
    """A record IS its field tuple: one region per field, addressed by name."""
    held = []
    for name, part in _kids(thing)[:CEILING]:
        held.append(spell(part, f"{at}.{name}" if at else name))
    return Region("record", type(thing).__name__, at, held)


def model(thing: object, at: str) -> Region:
    """A model spells itself, and its text IS the address space of the parse."""
    text = thing.to_text() if isinstance(thing, GrammarModel) else ""
    held = [spell(part, f"{at}.{name}" if at else name) for name, part in _kids(thing)]
    return Region("model", f"{type(thing).__name__} · {len(text):,} chars", at, held)


def absent(thing: object, at: str) -> Region:
    """Absence is a VALUE here, so it gets a region rather than a hole."""
    return Region("absent", "—", at)


register("IrStr", scalar)
register("IrInt", scalar)
register("IrChr", scalar)
register("str", scalar)
register("int", scalar)
register("IrNoneType", absent)
register("IrNamedTuple", record)
register("IrSeq", record)
register("IrTuple", record)
register("tuple", record)
register("IrSelf", record)
register("GrammarModel", model)
