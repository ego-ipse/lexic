"""The visual system — `leaf.css`, moved to the server without changing it.

Nothing here is new. Every colour, face and metric below is the one the
instrument already uses; the only change is WHERE it lives, so a frame
arrives with its own appearance instead of the leaf holding a second opinion
about it. Monospace is lexic's output; sans-serif is opsis speaking.
"""

from __future__ import annotations

__all__ = ["ADVANCE", "EDGES", "FONTS", "MONO", "TONES", "register", "runs"]

# --mono, --sans, --fs, --lh
MONO = '12.5px "JetBrains Mono", "DejaVu Sans Mono", ui-monospace, monospace'
SANS = '"Inter", "DejaVu Sans", system-ui, sans-serif'
CODE = '"JetBrains Mono", "DejaVu Sans Mono", monospace'

FONTS = {
    # #title: cool, 700, 14px, letter-spacing .18em
    "title": f"700 14px {SANS}",
    # .facet h2 b: the title is inside a `<b>`, so it is BOLD — the tag does
    # that, and a canvas asked for "10.5px" draws a different, thinner word
    "ftitle": f"700 10.5px {SANS}",
    # #sub and #status: 12px sans, dim, in a <span> — normal weight
    "fsub": f"12px {SANS}",
    # .facet h2 em: the same words, but inside an <h2>, and a heading is BOLD.
    # One face for both drew the facet heads a visibly lighter instrument.
    "hsub": f"700 12px {SANS}",
    # #verdict, #readout, #pos, #pincount: mono 11px
    "verdict": f"11px {CODE}",
    # .tabbar .tab, #dock .fnode-chip, #ladder .rung, the selects: mono 10px
    "chip": f"10px {CODE}",
    # .gchip: font-size: calc(10px * var(--glabel)) and the projection scales
    # it — a node's distance is in the SIZE of its name, clamped 0.55..1.2 as
    # the reference clamps it. Three bands, because a face is a registered
    # thing and a scale is not something a mark can carry.
    # #railchip: 11px var(--sans), not mono — it is a BUTTON floating over
    # the picture, not a word set into one
    "railchip": f"11px {SANS}",
    # `paint.js` sets every DRAWING in 11px mono — the graphs, the rails, the
    # automaton, the lanes. It is not the body face and it is not a chip.
    "drawn": f"11px {CODE}",
    "gnear": f"12px {CODE}",
    "gfar": f"8px {CODE}",
}

TONES = {
    # :root, verbatim
    "field": "#0b0e14",
    "field2": "#0e1219",
    "ink": "#e8e2d6",
    "dim": "#66707f",
    "dimmer": "#3a4250",
    "cool": "#6fc3c9",
    "warm": "#e2a65c",
    "violet": "#d98cf5",
    "red": "#e06060",
    "green": "#79c99a",
    "hair": "#1a2230",
    # the same values under the names the renderers say them in
    "title": "#6fc3c9",
    "ftitle": "#6fc3c9",
    "fsub": "#66707f",
    "hsub": "#66707f",
    "verdict": "#66707f",
    "chip": "#66707f",
    # .gchip is --dim at every size: a name's DISTANCE is its size, and its
    # ROLE is its colour, and neither may be read off the other
    "railchip": "#d98cf5",
    "drawn": "#66707f",
    "gnear": "#66707f",
    "gfar": "#66707f",
    "caret": "#e2a65c",
    "cursor": "#e2a65c",
    "rail": "#6fc3c9",
    "loop": "#d98cf5",
    "token": "#8fa3b8",
    "ref": "#6fc3c9",
    "class": "#d98cf5",
    "name": "#e2a65c",
    "eps": "#3a4250",
    "hot": "#e2a65c",
    "cool_wash": "rgba(111,195,201,0.18)",
    "seen": "#4a5568",
    "faded": "rgba(102,112,127,0.16)",
    # a span against the cursor, as the lanes have always drawn it: the fill
    # for what is closed, the DARK amber for what is open, and nothing at all
    # for what is still ahead — which is why the lanes read as structure
    "span": "#2a3140",
    # what a FILLED drawing-box is filled with — the reference fills only
    # `closed` and `live`, and with a fill variant, never with the edge tone
    "closedfill": "#10282e",
    "livefill": "#3a2f18",
    "closed": "#10282e",
    "active": "#3a2f18",
    "pending": "#2a3140",
    "live": "#e2a65c",
    "ahead": "#2a3140",
    "kept": "#8fa3b8",
    "lost": "#4a1f22",
    # co-selection: #grammarBody .ln.lit / .ln.hot / .ln.live
    "lit": "rgba(111,195,201,0.07)",
    # what the cursor stands INSIDE, washed under the document's own text
    "open": "rgba(111,195,201,0.045)",
    "hotline": "rgba(226,166,92,0.12)",
    "liveline": "rgba(226,166,92,0.10)",
    # a clone's mode at the weight a finished frame is filled with
    "cool20": "rgba(111,195,201,0.20)",
    "warm20": "rgba(226,166,92,0.20)",
    "token20": "rgba(143,163,184,0.20)",
    "violet20": "rgba(217,140,245,0.20)",
    "dim20": "rgba(102,112,127,0.20)",
    # the model band's depths
    # the clock bands: a texture, not a picture. The PDA's is stack depth in
    # cool with a warm mark where it DECIDED; Earley's is live hypotheses in
    # violet, red where they died and blended where both happened at once.
    # `chart.js` ramps the alpha continuously; a tone is a name, so these are
    # its endpoints in four steps.
    "pdaband0": "rgba(111,195,201,0.10)",
    "pdaband1": "rgba(111,195,201,0.28)",
    "pdaband2": "rgba(111,195,201,0.47)",
    "pdaband3": "rgba(111,195,201,0.65)",
    "pdadecided": "#e2a65c",
    "hypband0": "rgba(217,140,245,0.08)",
    "hypband1": "rgba(217,140,245,0.25)",
    "hypband2": "rgba(217,140,245,0.45)",
    "hypband3": "rgba(217,140,245,0.68)",
    "hypdead": "rgba(224,96,96,0.40)",
    # where hypotheses both stood and died, the blend still RAMPS with how
    # many stood — a flat tone made every bucket the same and the band said
    # nothing at all about a document where both happen everywhere
    "hypboth0": "rgba(199,123,155,0.25)",
    "hypboth1": "rgba(199,123,155,0.40)",
    "hypboth2": "rgba(199,123,155,0.55)",
    "hypboth3": "rgba(199,123,155,0.70)",
    "modelband0": "#0e151d",
    "modelband1": "#152230",
    "modelband2": "#1d3143",
    "modelband3": "#274257",
}

# which fills are outlined, and in what
EDGES = {
    "kept": "#8fa3b8",
    "lost": "#e06060",
}

# what one glyph costs, in the face a tone is set in
# --fs 12.5px in --mono is 7.5px per glyph: the body face, and what a tone
# with no face of its own is set in. It was 7.0 here, which is a sixteenth of
# a character short per glyph — enough that a name's own extent, placed after
# it, sat on top of its last letter.
CELL = 7.5
ADVANCE = {
    "title": 9.4,
    "ftitle": 7.0,
    "fsub": 6.4,
    "hsub": 6.8,
    "verdict": 6.6,
    "chip": 6.0,
    "railchip": 5.6,
    "drawn": 6.6,
    "gnear": 7.2,
    "gfar": 4.8,
}


def runs(tone: str, said: str) -> float:
    """How wide those words are, in the face that tone is set in.

    A glyph outside ASCII is not one cell wide: `◉`, `⧉` and `⊳` are drawn
    from a fallback face and take about half again as much room, which is how
    two chips in a facet's head ended up overlapping each other.
    """
    cell = ADVANCE.get(tone, CELL)
    # tracked-out text is WIDER, and a width that forgets it overlaps the
    # next thing along
    space = {"title": 2.5, "chip": 0.6, "ftitle": 1.5}.get(tone, 0.0)
    return sum(
        cell + space if glyph.isascii() else cell * 1.6 + space for glyph in said
    )


# letter-spacing is part of a face, not decoration: #title is 0.18em and a
# rung is 0.06em, and a canvas that ignores it draws a different word.
TRACKING = {"title": "0.18em", "chip": "0.06em", "ftitle": "0.14em"}


def register() -> list[str]:
    """The palette as wire lines — fills, edges and faces."""
    return [
        f"#FONT {MONO}",
        f"#TONES {len(TONES) + len(EDGES) + len(FONTS) + len(TRACKING)}",
        *(f"fill {name} {said}" for name, said in TONES.items()),
        *(f"edge {name} {said}" for name, said in EDGES.items()),
        *(f"font {name} {said}" for name, said in FONTS.items()),
        *(f"track {name} {said}" for name, said in TRACKING.items()),
    ]
