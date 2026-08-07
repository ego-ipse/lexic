"""A parse over time — where the cursor was, step by step.

The execution bar is spatial: one mark per decision, placed where in
the INPUT it happened. This is the other axis. Step index runs left to
right and cursor position runs down, so the line is the parse's own
progress: flat where it descended without consuming, steep where it ate
text, and turned back where an attempt was tried and abandoned.

Scrubbing is what makes it a diagram rather than a picture. Drag to a
step and the input lights up to exactly where the cursor stood — the
parse, replayed, without re-running it.
"""

from __future__ import annotations

from typing import Sequence

from opsis.opsis.draw.canvas import el, raw
from opsis.opsis.draw.canvas import text as _text
from opsis.opsis.read.parts import bounded, facts, refusal, stack

from lexic.ir import IrDoc
from lexic.parsing import Step

__all__ = ["timeline_view"]

WIDE = 640
"""How wide the diagram is drawn, in its own coordinates."""

TALL = 220
"""How tall — the cursor axis, scaled to the input's length."""


def timeline_view(steps: Sequence[Step], text: str) -> IrDoc:
    """The cursor's path through one parse, scrubbable.

    Every step is a real recorded decision, so the line is measured
    rather than modelled. A parse that refused stops where it stopped,
    which is the shape worth seeing.
    """
    if not steps:
        return refusal("no decisions were recorded for this parse")
    span = max(len(text), 1)
    points = " ".join(
        f"{i / max(len(steps) - 1, 1) * WIDE:.1f},{s.start / span * TALL:.1f}"
        for i, s in enumerate(steps)
    )
    return stack(
        [
            facts(_measures(steps, text)),
            el(
                "div",
                {"class": "kairos"},
                raw(_svg(points, steps, span)),
                el(
                    "input",
                    {
                        "type": "range",
                        "min": "0",
                        "max": str(len(steps) - 1),
                        "value": str(len(steps) - 1),
                        "data-scrub": "1",
                    },
                ),
                el(
                    "div",
                    {"class": "note", "data-at": "1"},
                    _text(f"step {len(steps) - 1} · {steps[-1].name}"),
                ),
                el(
                    "pre",
                    {"class": "src", "data-replay": "1"},
                    _text(bounded(text, 2000)[0]),
                ),
            ),
        ]
    )


def _measures(steps: Sequence[Step], text: str) -> list[tuple[str, str, str]]:
    """What the shape of this parse amounts to, in numbers."""
    stalls = sum(1 for a, b in zip(steps, steps[1:]) if b.start == a.start)
    back = sum(1 for a, b in zip(steps, steps[1:]) if b.start < a.start)
    return [
        ("steps", f"{len(steps):,}", "decisions the runtime recorded"),
        (
            "last decision",
            f"@{steps[-1].start} of {len(text)}",
            "where the runtime last had to CHOOSE — not where the cursor "
            "ended, which is past this by whatever it then consumed",
        ),
        (
            "deepest",
            f"@{max(s.start for s in steps)}",
            "the furthest into the input any decision was made",
        ),
        ("descents", f"{stalls:,}", "steps that consumed nothing"),
        (
            "turned back",
            f"{back:,}",
            "an attempt was tried and abandoned"
            if back
            else "the parse never backtracked",
        ),
    ]


def _safe(name: str) -> str:
    """A clone name that cannot break out of the attribute it sits in."""
    return name.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _svg(points: str, steps: Sequence[Step], span: int) -> str:
    """The path itself, plus one dot per decision to scrub to."""
    dots = "".join(
        f'<circle class="kdot" data-step="{i}" data-name="{_safe(s.name)}" '
        f'cx="{i / max(len(steps) - 1, 1) * WIDE:.1f}" '
        f'cy="{s.start / span * TALL:.1f}" r="2.5"/>'
        for i, s in enumerate(steps)
    )
    return (
        f'<svg viewBox="-6 -6 {WIDE + 12} {TALL + 12}" class="ksvg">'
        f'<polyline class="kline" points="{points}"/>'
        f'<line class="kaxis" x1="0" y1="{TALL}" x2="{WIDE}" y2="{TALL}"/>'
        f"{dots}</svg>"
    )
