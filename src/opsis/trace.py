"""Trace — the recording kernel and the engine execution view.

The Dbg pattern as a standing instrument: :class:`TraceKernel` subclasses
the PDA kernel, overrides its decision seams, records, and delegates to
``super()`` — zero hooks added to lexic. The engine view renders the
recorded run: the input timeline colored by who owned each character
(deterministic walk / island sub-parse / attempt-probe activity), a
scrubber over the event log, and the outcome (including a fallback
diagnosis when the PDA bails).

This module shares the recorded one-level engine-import exemption with
:mod:`opsis.verdict` — it must subclass the kernel; nothing is written
back.
"""

from __future__ import annotations

from html import escape
from typing import Any

from lexic.exceptions import LexicError
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.products import _model_product

_CAP = 20_000
"""Recorded events per run — a runaway parse truncates, honestly labeled."""


class TraceKernel(PdaKernel):
    """The model kernel with its decision seams recorded."""

    __slots__ = ("events", "islands")

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.events: list[tuple[int, str, str]] = []
        self.islands: list[tuple[int, int, str]] = []

    def _note(self, pos: int, kind: str, detail: str) -> None:
        if len(self.events) < _CAP:
            self.events.append((pos, kind, detail))

    def _enter(self, clone: Any, out: Any) -> bool:
        fold = getattr(clone, "fold", None)
        if fold is not None and not self._caches.probing:
            self._note(self.pos, "enter", getattr(fold.ctor, "__name__", "?"))
        return super()._enter(clone, out)

    def attempt_iteration(self, frame: Any, arm: Any, i: int, pos: int) -> int:
        before = self.pos
        got = super().attempt_iteration(frame, arm, i, pos)
        if not self._caches.probing:
            took = "take" if got == i else "close"
            self._note(pos, "attempt", f"loop {took} → {self.pos if took == 'take' else before}")
        return got

    def _fork_verdict(self, arm: Any, i: int, pos: int, taken: Any) -> int:
        verdict = super()._fork_verdict(arm, i, pos, taken)
        name = ("TAKE", "STOP", "FORK")[verdict]
        self._note(pos, "verdict", f"both-viable boundary → {name}")
        return verdict

    def _probe(self, arm: Any, i: int, pos: int, taken: Any) -> Any:
        got = super()._probe(arm, i, pos, taken)
        side = "take" if taken is not None else "stop"
        outcome = "completes" if got[0] is not None else "dies"
        self._note(pos, "probe", f"{side}-side probe {outcome}")
        return got

    def _island(self, name: str, sink: Any) -> None:
        start = self.pos
        super()._island(name, sink)
        self.islands.append((start, self.pos, name))
        self._note(start, "island", f"{name} · Earley window [{start},{self.pos})")


def run_trace(cg: Any, text: str) -> tuple[TraceKernel, str | None]:
    """One recorded PDA run of ``text``; ``(kernel, failure | None)``."""
    tables = _model_product(cg.codegen_grammar, cg.fold).pda
    kernel = TraceKernel(tables, text, cg.fold)
    try:
        kernel.run()
        return kernel, None
    except (PdaFail, LexicError) as exc:
        return kernel, f"{type(exc).__name__}: {exc}"


def engine_html(cg: Any, text: str) -> str:
    """The engine execution view for one input."""
    kernel, failure = run_trace(cg, text)
    owner = ["p"] * len(text)
    for start, end, _name in kernel.islands:
        for i in range(start, min(end, len(text))):
            owner[i] = "i"
    for pos, kind, _d in kernel.events:
        if kind in ("attempt", "verdict", "probe") and pos < len(text):
            owner[pos] = "a"
    timeline = _timeline(text, owner, failure)
    events = kernel.events
    log = "".join(
        f'<div class="ev ev-{kind}" data-pos="{pos}">'
        f'<span class="pos">{pos}</span> <b>{kind}</b> {escape(detail)}</div>'
        for pos, kind, detail in events
    )
    cap = (
        f'<div class="warn">event log truncated at {_CAP}</div>'
        if len(events) >= _CAP else ""
    )
    outcome = (
        f'<div class="warn">PDA bailed — the public parse completes on gated '
        f"Earley: {escape(failure)}</div>"
        if failure else
        '<div class="okline">PDA completed deterministically</div>'
    )
    slider = (
        f'<input id="scrub" type="range" min="0" max="{max(len(events) - 1, 0)}" '
        'value="0">'
    )
    legend = (
        '<div class="legend"><span class="tl-p">deterministic</span>'
        '<span class="tl-i">island (Earley)</span>'
        '<span class="tl-a">attempt / probe</span></div>'
    )
    return (
        f"{outcome}{legend}{timeline}{slider}{cap}"
        f'<div id="evlog">{log}</div>'
    )


def _timeline(text: str, owner: list[str], failure: str | None) -> str:
    """The input as owner-colored runs, one span per run."""
    parts = ['<pre class="timeline">']
    i = 0
    while i < len(text):
        j = i
        while j < len(text) and owner[j] == owner[i]:
            j += 1
        parts.append(
            f'<span class="tl-{owner[i]}" data-a="{i}" data-b="{j}">'
            f"{escape(text[i:j])}</span>"
        )
        i = j
    if failure:
        parts.append('<span class="tl-x">⟵ bail</span>')
    parts.append("</pre>")
    return "".join(parts)
