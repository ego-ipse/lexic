"""opsis-radical — a parse, watched.

The white whale: the derivation of a real document by a real compiled grammar,
animated on the settled clock — TEXT IS THE TIME AXIS. Every span is folded
from the parsed model's own tagged emit stream (`emit_parts`), the same stream
`to_text()` consumes, so the chart cannot drift from the text by construction.

Run from the repo root:

    uv run python zzz_current_work/260807-opsis-radical/spectacle.py             # plays once
    uv run python zzz_current_work/260807-opsis-radical/spectacle.py --census    # gate
    uv run python zzz_current_work/260807-opsis-radical/spectacle.py --shot 33 out.png

Hover the text or the lanes to scrub time. Space replays. Hover a span to read it.
"""

import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path as FsPath
from typing import NamedTuple

from present import MONO_FAMILIES, SANS_FAMILIES, FontCache, Frame
from scene import initial_session

from lexic.compile import compile_from_path
from lexic.model import GrammarModel

W, H = 1500, 730
MARGIN = 28
DOC_Y = 128
LANES_Y = 192
LANE_H = 38
TREE_X = 1075
TREE_W = 400
GRAMMAR = FsPath(__file__).resolve().parents[2] / "resources" / "ground_truth" / "json.gbnf"
DOCUMENT = '{"name": "opsis", "modes": [3, "d"], "live": true}'
CHARS_PER_SECOND = 11.0
TICK_MS = 30
CLOSED_FILL = "#10282e"
ACTIVE_FILL = "#3a2f18"


class Span(NamedTuple):
    """One model occurrence on the text axis — where it is, how deep, what it is."""

    start: int
    end: int
    depth: int
    label: str
    field: str


def fold_spans(model: GrammarModel) -> list[Span]:
    """Every model occurrence's span, folded from the tagged emit stream."""
    spans: list[Span] = []
    end = _fold(model, 0, 0, "", spans)
    if end != len(DOCUMENT):
        raise AssertionError(f"span fold ended at {end}, document is {len(DOCUMENT)} — the stream drifted")
    return spans


def _fold(part: object, depth: int, off: int, field: str, spans: list[Span]) -> int:
    """Advance the offset through one part, recording model spans on the way."""
    if part is None:
        return off
    if isinstance(part, str):
        return off + len(part)
    if isinstance(part, tuple) and not isinstance(part, GrammarModel):
        for element in part:
            off = _fold(element, depth, off, field, spans)
        return off
    start = off
    for tag, inner in part.emit_parts():
        off = _fold(inner, depth + 1, off, tag or "", spans)
    spans.append(Span(start, off, depth, type(part).__name__, field))
    return off


class Watch:
    """The instrument — one compiled grammar, one document, one derivation, watched."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.st = initial_session().style
        self.compiled = compile_from_path(str(GRAMMAR))
        self.model = self.compiled.parse(DOCUMENT)
        self.faithful = self.model.to_text() == DOCUMENT
        self.spans = fold_spans(self.model)
        self.depths = max(s.depth for s in self.spans) + 1
        self.t = 0.0
        self.playing = False
        self.hover: tuple[int, ...] | None = None
        self.font_cache: FontCache = {}
        self.hits: list = []
        families = set(tkfont.families(root))
        self.mono_family = next((n for n in MONO_FAMILIES if n in families), "Courier")
        self.sans_family = next((n for n in SANS_FAMILIES if n in families), "Helvetica")
        root.title("opsis-radical — a parse, watched")
        self.cv = tk.Canvas(root, width=W, height=H, highlightthickness=0)
        self.cv.pack()
        pitch_width = TREE_X - 2 * MARGIN - 12
        self.pitch = pitch_width / len(DOCUMENT)
        self.cv.bind("<Motion>", self.on_motion)
        root.bind("<Key-space>", self.on_space)
        self.redraw()
        root.after(400, self.play)

    def x_of(self, offset: float) -> float:
        """The x pixel of a text offset — the one scale document and lanes share."""
        return MARGIN + 8 + offset * self.pitch

    # ── the frame ──────────────────────────────────────────────────────

    def redraw(self) -> None:
        """One frame at time ``t`` — the whole watched derivation, redrawn."""
        st = self.st
        self.cv.delete("all")
        f = Frame(self.cv, st, self.font_cache, self.mono_family, self.sans_family, self.hover, None, None)
        self.cv.create_rectangle(0, 0, W, H, fill=str(st.field), outline="")
        self.draw_header(f)
        self.draw_document(f)
        self.draw_lanes(f)
        self.draw_tree(f)
        self.draw_cursor(f)
        self.draw_status(f)
        self.hits = f.hits

    def draw_header(self, f: Frame) -> None:
        """The masthead — what is being watched, and on whose authority."""
        t = f.text(MARGIN, 22, "A PARSE, WATCHED", str(f.st.cool), f.font("sans", 4, "bold"))
        f.text(
            t[2] + 18, 28,
            f"json.gbnf · compiled by lexic · {len(DOCUMENT)} chars · {len(self.spans)} spans · "
            "every span folded from the model's own emit stream — the chart cannot drift from the text",
            str(f.st.dim), f.font("sans", -1),
        )

    def draw_document(self, f: Frame) -> None:
        """The document, one glyph per pitch — read behind the cursor, unread ahead."""
        read = int(self.t)
        for i, ch in enumerate(DOCUMENT):
            colour = str(f.st.ink) if i < read else str(f.st.dim)
            if i == read and self.t < len(DOCUMENT):
                colour = str(f.st.warm)
            self.cv.create_text(
                self.x_of(i + 0.5), DOC_Y, text=ch, fill=colour, font=f.font("mono", 5), anchor="s"
            )
        for offset in range(0, len(DOCUMENT) + 1, 10):
            x = self.x_of(offset)
            self.cv.create_line(x, DOC_Y + 6, x, DOC_Y + 12, fill=str(f.st.dim))
            self.cv.create_text(x, DOC_Y + 14, text=str(offset), fill=str(f.st.dim), font=f.font("mono", -3), anchor="n")

    def draw_lanes(self, f: Frame) -> None:
        """The span chart — depth is the lane, text is the axis, state is the cursor's."""
        for i, span in enumerate(self.spans):
            if span.end == span.start:
                continue
            self.draw_span(f, i, span)

    def draw_span(self, f: Frame, i: int, span: Span) -> None:
        """One occurrence's bar — pending, active-with-progress, or closed."""
        x1, x2 = self.x_of(span.start), self.x_of(span.end)
        y1 = LANES_Y + span.depth * LANE_H
        y2 = y1 + LANE_H - 10
        if span.end <= self.t:
            self.cv.create_rectangle(x1, y1, x2, y2, fill=CLOSED_FILL, outline=str(f.st.cool))
        elif span.start < self.t:
            xm = self.x_of(min(self.t, span.end))
            self.cv.create_rectangle(x1, y1, xm, y2, fill=ACTIVE_FILL, outline="")
            self.cv.create_rectangle(x1, y1, x2, y2, outline=str(f.st.warm))
        else:
            self.cv.create_rectangle(x1, y1, x2, y2, outline="#2a3140")
        label_font = f.font("mono", -3)
        if label_font.measure(span.label) < (x2 - x1) - 6:
            shade = str(f.st.ink) if span.start < self.t else str(f.st.dim)
            self.cv.create_text(x1 + 4, (y1 + y2) / 2, text=span.label, fill=shade, font=label_font, anchor="w")
        f.region((i,), (int(x1), int(y1), int(x2), int(y2)))

    def draw_tree(self, f: Frame) -> None:
        """The model, assembling — an occurrence appears the moment its span closes."""
        st = f.st
        t = f.text(TREE_X, LANES_Y - 36, "THE MODEL, ASSEMBLING", str(st.cool), f.font("sans", 0, "bold"))
        shown = [s for s in self.spans if s.depth <= 4 and s.end > s.start]
        done = sorted((s for s in shown if s.end <= self.t), key=lambda s: (s.end, -s.depth, s.start))
        yc = t[3] + 10
        for span in done:
            fresh = self.t - span.end < 1.6
            colour = str(st.warm) if fresh else str(st.ink)
            snippet = DOCUMENT[span.start : span.end]
            snippet = snippet if len(snippet) <= 13 else snippet[:12] + "…"
            line = f"{'· ' * span.depth}{span.label}  {snippet!r}"
            b = f.text(TREE_X, yc, line, colour, f.font("mono", -2), width=TREE_W)
            yc = b[3] + 3
        active = [s for s in shown if s.start < self.t < s.end]
        for span in sorted(active, key=lambda s: s.depth)[-1:]:
            f.text(
                TREE_X, yc + 8, f"reading {span.label} · {span.start}..{span.end}",
                str(st.warm), f.font("mono", -2),
            )
        folded = len(self.spans) - len(shown)
        f.text(
            TREE_X, H - 116, f"depths 0..4 shown here · {folded} deeper spans live in the lanes",
            str(st.dim), f.font("sans", -2), width=TREE_W,
        )

    def draw_cursor(self, f: Frame) -> None:
        """The cursor — one warm vertical truth from the glyphs down through the lanes."""
        x = self.x_of(min(self.t, len(DOCUMENT)))
        bottom = LANES_Y + self.depths * LANE_H
        self.cv.create_line(x, DOC_Y - 26, x, bottom, fill=str(f.st.warm))
        self.cv.create_line(x + 1, DOC_Y - 26, x + 1, bottom, fill=ACTIVE_FILL)

    def draw_status(self, f: Frame) -> None:
        """The bottom strip — where in time, what under the pointer, what holds."""
        st = f.st
        state = "playing" if self.playing else ("complete" if self.t >= len(DOCUMENT) else "paused")
        left = f"t = {self.t:5.1f} / {len(DOCUMENT)} · {state} · hover the text to scrub · Space replays"
        f.text(MARGIN, H - 36, left, str(st.dim), f.font("sans", -1))
        if self.hover is not None:
            s = self.spans[self.hover[0]]
            words = f"{s.label} · field {s.field or '—'} · span {s.start}..{s.end} · depth {s.depth} · {DOCUMENT[s.start:s.end]!r}"
            f.text(MARGIN, H - 62, words, str(st.warm), f.font("mono", -1), width=1000)
        verdict = "— holds" if self.faithful else "— fails"
        colour = str(st.green) if self.faithful else str(st.red)
        b = f.text(W - MARGIN, H - 36, verdict, colour, f.font("mono", -2), anchor="ne")
        f.text(b[0] - 6, H - 36, "model.to_text() == document ", str(st.dim), f.font("mono", -2), anchor="ne")

    # ── time and the hand ──────────────────────────────────────────────

    def play(self) -> None:
        """Start the sweep from wherever t stands (or the top, if complete)."""
        if self.t >= len(DOCUMENT):
            self.t = 0.0
        self.playing = True
        self.tick()

    def tick(self) -> None:
        """One animation step — time advances only while something is happening."""
        if not self.playing:
            return
        self.t = min(self.t + CHARS_PER_SECOND * TICK_MS / 1000.0, float(len(DOCUMENT)))
        if self.t >= len(DOCUMENT):
            self.playing = False
        self.redraw()
        if self.playing:
            self.root.after(TICK_MS, self.tick)

    def on_motion(self, event: "tk.Event[tk.Canvas]") -> None:
        """Scrubbing and span-reading — the pointer owns time while it is over the chart."""
        in_chart = DOC_Y - 30 <= event.y <= LANES_Y + self.depths * LANE_H + 8
        hover = None
        for box, path in reversed(self.hits):
            if box[0] <= event.x <= box[2] and box[1] <= event.y <= box[3]:
                hover = path
                break
        moved = hover != self.hover
        self.hover = hover
        if in_chart:
            self.playing = False
            self.t = max(0.0, min((event.x - self.x_of(0)) / self.pitch, float(len(DOCUMENT))))
            self.redraw()
        elif moved:
            self.redraw()

    def on_space(self, _event: "tk.Event[tk.Tk]") -> None:
        """Space toggles the sweep."""
        if self.playing:
            self.playing = False
            self.redraw()
        else:
            self.play()


def census(watch: Watch) -> int:
    """The gate — fidelity, span integrity, and the three cursor states, measured."""
    ok_faithful = watch.faithful
    ok_end = max(s.end for s in watch.spans) == len(DOCUMENT)
    watch.t = 0.0
    watch.redraw()
    pending = len(watch.hits)
    watch.t = float(len(DOCUMENT))
    watch.redraw()
    closed = len(watch.hits)
    print(f"spans {len(watch.spans)} · depths {watch.depths} · drawn regions {closed}")
    print(f"to_text == document: {ok_faithful} · fold reaches len(document): {ok_end}")
    print(f"regions at t=0: {pending} · at t=end: {closed} · stable: {pending == closed}")
    ok = ok_faithful and ok_end and pending == closed and closed > 0
    print("census ok" if ok else "census FAILED")
    return 0 if ok else 1


def shot(watch: Watch, t: float, out: str) -> None:
    """One frame at time ``t``, written as a PNG through ghostscript."""
    import subprocess

    watch.playing = False
    watch.t = t
    watch.redraw()
    watch.root.update()
    ps_path = out + ".ps"
    watch.cv.postscript(file=ps_path, colormode="color", width=W, height=H)
    subprocess.run(
        ["gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m", "-dEPSCrop",
         "-r120", f"-sOutputFile={out}", ps_path],
        check=True,
        capture_output=True,
    )
    print(f"wrote {out}")


def main() -> int:
    """Entry — plays once by default; census and shot modes for verification."""
    root = tk.Tk()
    watch = Watch(root)
    if "--census" in sys.argv:
        code = census(watch)
        root.destroy()
        return code
    if "--shot" in sys.argv:
        at = sys.argv.index("--shot")
        shot(watch, float(sys.argv[at + 1]), sys.argv[at + 2])
        root.destroy()
        return 0
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
