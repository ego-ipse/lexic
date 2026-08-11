"""The road not taken — the other engine, run behind the parse.

One parse, two observations. The product always comes from the engine's own
composition; the instrument additionally runs the other engine in the
background and draws what it found. A parity verdict is a MEASUREMENT: the
two values are structurally equal AND re-emit the same text, or they are not.

Pending is drawn as a sentence. A result whose reading has moved on is
discarded rather than shown against the wrong text.
"""

from __future__ import annotations

import threading
import time

from lexic.compile import CompiledGrammar
from lexic.exceptions import LexicError
from lexic.model import GrammarModel
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.products import earley_model

__all__ = ["Road", "frame", "start"]


class Road:
    """What the other engine found, and whether it agreed."""

    __slots__ = ("name", "parity", "seconds", "status", "words")

    def __init__(self) -> None:
        self.status = "pending"
        self.name = "Earley (explicit)"
        self.seconds = 0.0
        self.parity = ""
        self.words = ""


_ROADS: dict[str, Road] = {}


def start(
    rid: str, compiled: CompiledGrammar, text: str, primary: GrammarModel
) -> None:
    """Run the other engine for this reading, once, off the parse's path."""
    if rid in _ROADS:
        return
    road = Road()
    _ROADS[rid] = road
    thread = threading.Thread(
        target=_run, args=(road, compiled, text, primary), daemon=True
    )
    thread.start()


def _run(
    road: Road, compiled: CompiledGrammar, text: str, primary: GrammarModel
) -> None:
    """The pass pair IS the instance-grammar recipe, not a flag."""
    clock = time.perf_counter()
    try:
        grammar = normalize(lift_optional_nullables(compiled.codegen_grammar))
        other = earley_model(grammar, text, compiled.fold)
    except (LexicError, RecursionError, ValueError) as refusal:
        road.seconds = time.perf_counter() - clock
        road.status = "failed"
        road.words = str(refusal)[:200]
        return
    road.seconds = time.perf_counter() - clock
    road.status = "done"
    same = other == primary
    spelled = isinstance(other, GrammarModel) and other.to_text() == primary.to_text()
    road.parity = "holds" if same and spelled else "fails"
    road.words = (
        "both engines built the same value"
        if same and spelled
        else f"structural {'==' if same else '!='} · text {'==' if spelled else '!='}"
    )


def frame(rid: str, primary_seconds: float) -> str:
    """What the two roads say — pending included, because pending is an answer."""
    road = _ROADS.get(rid)
    if road is None:
        return (
            "primary the engine's own composition\n"
            f"primary_seconds {primary_seconds:.2f}\nstatus pending\n"
        )
    return "\n".join(
        [
            "primary the engine's own composition",
            f"primary_seconds {primary_seconds:.2f}",
            f"status {road.status}",
            f"name {road.name}",
            f"seconds {road.seconds:.2f}",
            f"parity {road.parity}",
            "pos -1",
            f"words {road.words}",
            "",
        ]
    )
