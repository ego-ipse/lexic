"""Opsis — the spectacle of lexic.

Opsis does not compute. Lexic computes. Opsis holds intent, invokes
lexic, and renders the trace — live (:func:`explore`) or frozen
(:func:`report`).
"""

from __future__ import annotations

from pathlib import Path

from opsis.praxis import Praxis
from opsis.serve import serve
from opsis.shell import artifact

__all__ = ["Praxis", "explore", "report"]


def explore(source: str = "", flavour: str = "gbnf", port: int = 0) -> None:
    """Open the live shell (blocks until Ctrl-C)."""
    praxis = Praxis()
    if source:
        praxis.compile(source, flavour)
    server = serve(praxis, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


def report(source: str, flavour: str = "gbnf", out: str | Path = "opsis.html",
           input_text: str = "") -> Path:
    """Compile ``source`` (and parse ``input_text`` if given); write the
    frozen artifact; returns the path.

    :raises ValueError: When the grammar — or the input — refuses; an
        artifact of a failed session is no artifact at all.
    """
    praxis = Praxis()
    sections = praxis.compile(source, flavour)
    if "error" in sections:
        raise ValueError(f"opsis: grammar refused — {sections['error']}")
    if input_text:
        got = praxis.parse(input_text)
        if "error" in got:
            raise ValueError(f"opsis: input refused — {got['error']}")
    path = Path(out)
    path.write_text(
        artifact(source, flavour, praxis.sections, input_text), encoding="utf-8"
    )
    return path
