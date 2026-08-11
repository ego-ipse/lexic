"""What the instrument is coloured with — the register, on the server.

A tone is a NAME everywhere upstream: the drawings say `rail`, `live`,
`lost`, and only this module knows what those are made of. It used to live in
the leaf, which meant the leaf held a judgement — which boxes are outlined,
and in what — that no one downstream could see or change. It ships with the
frame now, so the picture and its colours arrive together.
"""

from __future__ import annotations

__all__ = ["ADVANCE", "EDGES", "FONTS", "MONO", "TONES", "register", "runs"]

MONO = '12.5px "JetBrains Mono", "DejaVu Sans Mono", ui-monospace, monospace'
SANS = '"Inter", "DejaVu Sans", system-ui, sans-serif'

# a tone that is set differently — the chrome is sans, the reading is mono
FONTS = {
    "title": f"600 12px {SANS}",
    "label": f"600 11.5px {SANS}",
    "note": f"11.5px {SANS}",
}

# what one glyph of a tone's face costs in width — how the server knows what
# fits before it says it, and where the next word starts
ADVANCE = {"title": 7.6, "label": 7.4, "note": 5.9}

TONES = {
    # the ground the instrument sits on
    "field": "#0b0e14",
    "head": "#0e131c",
    "panel": "#0e1219",
    "hair": "#1a2230",
    "ink": "#e8e2d6",
    "dim": "#66707f",
    "note": "#66707f",
    "dimmer": "#3a4250",
    "title": "#e8e2d6",
    "label": "#6fc3c9",
    "lit": "#141b26",
    # a span's standing against the cursor
    "closed": "#10282e",
    "live": "#e2a65c",
    "open": "#33271a",
    "ahead": "#2a3140",
    "kept": "#8fa3b8",
    "lost": "#4a1f22",
    "cursor": "#e2a65c",
    # what a thing IS — the grammar's own kinds
    "rail": "#6fc3c9",
    "loop": "#d98cf5",
    "token": "#8fa3b8",
    "ref": "#6fc3c9",
    "class": "#d98cf5",
    "name": "#e2a65c",
    "eps": "#3a4250",
    "good": "#79c99a",
    "bad": "#e06060",
    "hot": "#e2a65c",
    "cool": "rgba(111,195,201,0.18)",
    "seen": "#4a5568",
    # the model band's depths
    "modelband0": "#0e151d",
    "modelband1": "#152230",
    "modelband2": "#1d3143",
    "modelband3": "#274257",
}

# which fills are outlined, and in what — the judgement the leaf used to make
EDGES = {
    "closed": "#6fc3c9",
    "live": "#e2a65c",
    "open": "#6d5433",
    "ahead": "#3a4250",
    "kept": "#8fa3b8",
    "lost": "#e06060",
}


def register() -> list[str]:
    """The palette as wire lines — `tone <name> <colour>`, edges and all."""
    return [
        f"#FONT {MONO}",
        f"#TONES {len(TONES) + len(EDGES) + len(FONTS)}",
        *(f"fill {name} {said}" for name, said in TONES.items()),
        *(f"edge {name} {said}" for name, said in EDGES.items()),
        *(f"font {name} {said}" for name, said in FONTS.items()),
    ]


def runs(tone: str, said: str) -> float:
    """How wide those words are, in the face that tone is set in."""
    return len(said) * ADVANCE.get(tone, 7.0)
