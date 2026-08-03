"""The table window — a dispatch table as the data it is.

Lexic dispatches on open tables with a raising default, and that is the
mechanism the whole engine turns on: a flavour's reductions, its emit
actions, its escape codec, opsis's own views registry. All of them are
maps, so all of them open the same way.

The registry that decides which view a product gets is itself in here,
which is what makes the coverage doctrine self-inspecting: the table
that would refuse an uncovered product is a table you can look at.
"""

from __future__ import annotations

from inspect import isroutine
from typing import NamedTuple

from lexic.ir import IrAst, IrDoc, IrFlavour, IrMapping
from opsis.opsis.read.views import VIEWS, bounded, facts, grid, panel, refusal, titled

__all__ = [
    "Table",
    "flavour_view",
    "registry_view",
    "table_view",
    "tables_of",
]

ROWS = 200
"""How many rows one table draws before it states the rest."""


class Table(NamedTuple):
    """One dispatch table, named and explained."""

    name: str
    what: str
    rows: tuple[tuple[str, str], ...]
    total: int


def tables_of(carrier: object) -> list[Table]:
    """Every dispatch table a thing carries, found by what it IS.

    Nothing is listed by name: a flavour's tables are its own mapping
    attributes, so a flavour that grows one shows it here without opsis
    being told. That is the same reason the views registry appears —
    it is a mapping, and it is asked the same question.
    """
    found = [_table(name, value) for name, value in _mappings(carrier)]
    return [t for t in found if t.total]


def _mappings(
    carrier: object, prefix: str = "", depth: int = 1
) -> list[tuple[str, IrMapping]]:
    """The mapping-valued attributes of a thing, and of the things it holds.

    One level in, because a flavour's tables are not all directly on
    it: its reductions live on its reducer and its spellings live on its
    escape codec, and those are its tables just the same. Deeper than
    that is someone else's structure, not this thing's tables.
    """
    out: list[tuple[str, IrMapping]] = []
    for name in dir(carrier):
        if name.startswith("_"):
            continue
        value = getattr(carrier, name, None)
        if isinstance(value, IrMapping):
            out.append((prefix + name, value))
        elif depth and _holds_tables(value):
            out.extend(_mappings(value, f"{prefix}{name}.", 0))
    return out


def _holds_tables(value: object) -> bool:
    """Whether a thing is worth asking for its own tables.

    Not everything an object holds is a part of it: a method and a
    whole grammar are not table carriers, and walking into them would
    turn a flavour's tables into a tour of lexic. Being callable is no
    disqualification and neither is being a tuple — a reducer IS its
    field tuple and IS callable, and it holds the reductions that
    matter most here.
    """
    return (
        value is not None
        and not isinstance(value, (IrAst, type))
        and not isroutine(value)
        and type(value).__module__.startswith("lexic")
    )


def _table(name: str, mapping: IrMapping) -> Table:
    """One mapping as rows, bounded and counted."""
    pairs = list(mapping.items())
    rows = tuple((_short(key), _short(value)) for key, value in pairs[:ROWS])
    return Table(name, _what(mapping), rows, len(pairs))


def _what(mapping: IrMapping) -> str:
    """What kind of table this is, from the type it IS."""
    return f"{type(mapping).__name__} · dispatches with a raising default"


def _short(value: object) -> str:
    """One cell — the value itself, cut where a cell has to stop."""
    shown, _note = bounded(str(value), 160)
    return shown.replace("\n", " ")


def table_view(carrier: object, title: str) -> IrDoc:
    """Everything ``carrier`` dispatches on, as tables.

    A carrier with no tables is not an error and is not blank: it says
    it has none, which is a fact about it.
    """
    tables = tables_of(carrier)
    if not tables:
        return refusal(f"{title} carries no dispatch tables")
    return panel(
        f"{title} · {len(tables)} tables · "
        f"{sum(t.total for t in tables):,} rows in all",
        *(_one(table) for table in tables),
    )


def _one(table: Table) -> IrDoc:
    """One table: its name, what it is, and its rows."""
    more = table.total - len(table.rows)
    note = f"{table.total:,} rows" + (f" · {more:,} not drawn" if more else "")
    return titled(table.name, note, table.what, grid(table.rows))


def registry_view() -> IrDoc:
    """The views registry — the coverage doctrine, looking at itself.

    If a product type is missing from this table, its window draws the
    refusal instead of a body. That is the runtime half of "opsis covers
    lexic": the gap is visible rather than silent, and the table that
    would refuse is right here.
    """
    return panel(
        "what a product's window is built from — open, MRO-ordered, "
        "raising default. A type not in here draws its refusal.",
        _one(_table("VIEWS", VIEWS)),
    )


def flavour_view(flavour: IrFlavour) -> IrDoc:
    """A flavour as what it is: metadata and tables, no methods.

    A flavour defines zero parsing methods — it is a config bundle, and
    seeing its tables IS seeing it — but that is what the tables window
    is FOR, and showing them here too would be the same thing twice.
    This one answers the other question: what it is CALLED, what it
    claims, and whether it can carry a directive at all.
    """
    kind = type(flavour)
    comments = bool(flavour.line_comment or flavour.block_comment)
    shown = [
        ("name", str(kind.name), "what a grammar names to be read by it"),
        (
            "extensions",
            ", ".join(str(e) for e in kind.extensions) or "none",
            "what a file has to end in for this to be inferred",
        ),
        (
            "line comment",
            str(flavour.line_comment) or "none",
            "" if flavour.line_comment else "so a @directive cannot be written",
        ),
        ("block comment", str(flavour.block_comment) or "none", ""),
        (
            "directives",
            "yes" if comments else "no",
            "a comment-less surface carries them as arguments instead",
        ),
        (
            "rules",
            f"{len(list(flavour.grammar.rules))}",
            "in the self-grammar — open shape to walk them",
        ),
    ]
    return facts(shown)
