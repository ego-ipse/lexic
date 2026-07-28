"""The compiled payload — a parsed value as three flat literals.

A compiled text is a **payload plus a reference to an already-compiled shape**:
the shape is a property of the GRAMMAR (one set of classes per language, compiled
once), the payload a property of the TEXT (cheap data that names what it
references). ``project(value)`` produces the three tables;
:mod:`~lexic.compile.payload.reader` reads them back and imports no lexic at all.

The three targets — the twin's generated classes, ``lexic.ir`` spine nodes, or
nothing — are **not three formats**. They are one projection over one symbol
table, and which one you get is decided by the codomain of the reduction that
produced the value, never by a flag.
"""

from __future__ import annotations

from lexic.compile.payload.encode import Payload, project, project_checked
from lexic.compile.payload.export import built_under, export_value, render

__all__ = [
    "Payload",
    "built_under",
    "export_value",
    "project",
    "project_checked",
    "render",
]
