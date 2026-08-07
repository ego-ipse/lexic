"""opsis-radical — the big bad wolf test: a parse, watched, at hostile scale.

The small spectacle drew fifty characters across a whole screen. This one faces
what actually exists: a ~16K-char JSON (12,219 spans, depth 19), and lexic's
own metagrammar reading `json.gbnf` and `vyx.gbnf` as documents. The answers:

- the text axis gets a VIEWPORT — an overview band holds the whole document as
  span-density; a detail stage shows a window of it at fixed, readable pitch;
- the right pane is the SPINE — the stack of spans open at the cursor. It is
  bounded by depth, never by document size;
- every count is stated: how many spans exist, how many are in view, and what
  the overview folds. No silent truncation.

Run from the repo root (fixture: long | meta | vyx):

    uv run python zzz_current_work/260807-opsis-radical/wolf.py [fixture]
    uv run python zzz_current_work/260807-opsis-radical/wolf.py [fixture] --census
    uv run python zzz_current_work/260807-opsis-radical/wolf.py [fixture] --shot 8000 out.png

Hover the overview to travel, the stage to scrub. Space replays. ←/→ step.
"""

import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from bisect import bisect_right
from pathlib import Path as FsPath
from typing import NamedTuple

from lexic.compile import compile_ast, compile_from_path
from lexic.grammars import GBNF_FLAVOUR
from lexic.model import GrammarModel

from present import MONO_FAMILIES, SANS_FAMILIES, FontCache, Frame
from scene import initial_session

HERE = FsPath(__file__).resolve().parent
ROOT = HERE.parents[1]
PITCH = 11
MARGIN = 28
TREE_W = 360
OV_Y, OV_H = 66, 44
SWEEP_SECONDS = 24.0
TICK_MS = 33
CLOSED_FILL = "#10282e"
ACTIVE_FILL = "#3a2f18"
PENDING_LINE = "#2a3140"
DENSITY = ("#0e151d", "#152230", "#1d3143", "#274257")


class Span(NamedTuple):
    """One model occurrence on the text axis."""

    start: int
    end: int
    depth: int
    label: str
    field: str


class Fixture(NamedTuple):
    """A grammar, a document, and how the reading was obtained."""

    key: str
    reader: str
    document: str
    model: GrammarModel
    seconds: float
    resolved: bool


def first(first_meaning: object, _witness: object) -> object:
    """The explicit ambiguity opt-out — a deterministic first-derivation resolver."""
    return first_meaning


def load_fixture(key: str) -> Fixture:
    """Compile, read, and time one of the wolf's three documents."""
    if key == "long":
        compiled = compile_from_path(str(ROOT / "resources" / "ground_truth" / "json.gbnf"))
        document = (HERE / "fixtures_long.json").read_text()
        reader, resolve = "json.gbnf", None
    else:
        compiled = compile_ast(GBNF_FLAVOUR.grammar)
        name = "vyx.gbnf" if key == "vyx" else "json.gbnf"
        document = (ROOT / "resources" / "ground_truth" / name).read_text()
        reader, resolve = "the GBNF metagrammar (90 rules)", first
    t0 = time.perf_counter()
    model = compiled.parse(document, resolve=resolve)
    seconds = time.perf_counter() - t0
    return Fixture(key, reader, document, model, seconds, resolve is not None)


def fold_spans(model: GrammarModel, document: str) -> list[Span]:
    """Every occurrence's span, folded from the model's own tagged emit stream."""
    spans: list[Span] = []
    end = _fold(model, 0, 0, "", spans)
    if end != len(document):
        raise AssertionError(f"span fold ended at {end}, document is {len(document)}")
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


class Wolf:
    """The instrument — one hostile reading, watched through a viewport."""

    def __init__(self, root: tk.Tk, fixture: Fixture) -> None:
        self.root = root
        self.fx = fixture
        self.st = initial_session().style
        self.doc = fixture.document
        self.faithful = fixture.model.to_text() == self.doc
        self.spans = fold_spans(fixture.model, self.doc)
        self.drawable = sorted(
            (s for s in self.spans if s.end > s.start), key=lambda s: (s.start, s.depth)
        )
        self.maxdepth = max(s.depth for s in self.spans)
        self.starts = [s.start for s in self.drawable]
        self.line_starts = self.find_lines()
        self.coverage = self.find_coverage()
        self.t = 0.0
        self.view0 = 0
        self.playing = False
        self.hover: tuple[int, ...] | None = None
        self.in_view = 0
        self.font_cache: FontCache = {}
        self.hits: list = []
        self.w, self.h = 1500, 880
        families = set(tkfont.families(root))
        self.mono_family = next((n for n in MONO_FAMILIES if n in families), "Courier")
        self.sans_family = next((n for n in SANS_FAMILIES if n in families), "Helvetica")
        root.title(f"opsis-radical — the wolf · {fixture.key}")
        self.cv = tk.Canvas(root, width=self.w, height=self.h, highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Configure>", self.on_resize)
        self.cv.bind("<Motion>", self.on_motion)
        root.bind("<Key-space>", self.on_space)
        root.bind("<Key-Left>", self.on_step)
        root.bind("<Key-Right>", self.on_step)
        self.redraw()
        root.after(500, self.play)

    # ── precomputation ────────────────────────────────────────────────

    def find_lines(self) -> list[int]:
        """Offsets where lines start — for the line readout."""
        starts = [0]
        for i, ch in enumerate(self.doc):
            if ch == "\n":
                starts.append(i + 1)
        return starts

    def find_coverage(self) -> list[int]:
        """How many spans cover each character — the overview's density source."""
        diff = [0] * (len(self.doc) + 1)
        for s in self.drawable:
            diff[s.start] += 1
            diff[s.end] -= 1
        cov, running = [], 0
        for d in diff[:-1]:
            running += d
            cov.append(running)
        return cov

    # ── geometry ──────────────────────────────────────────────────────

    def stage_x(self) -> int:
        """Left edge of the detail stage."""
        return MARGIN

    def stage_w(self) -> int:
        """Width of the detail stage in pixels."""
        return self.w - TREE_W - 2 * MARGIN - 24

    def visible(self) -> int:
        """How many characters the stage can show at readable pitch."""
        return max(24, self.stage_w() // PITCH)

    def ov_x(self, offset: float) -> float:
        """Overview x of a text offset — the whole document across the width."""
        return MARGIN + (offset / max(1, len(self.doc))) * (self.w - 2 * MARGIN)

    def sx(self, offset: float) -> float:
        """Stage x of a text offset within the current viewport."""
        return self.stage_x() + (offset - self.view0) * PITCH

    def follow(self) -> None:
        """Keep the cursor around the stage's leading third while playing."""
        vis = self.visible()
        lead = self.view0 + int(vis * 0.62)
        if self.t > lead or self.t < self.view0:
            self.view0 = int(max(0, min(self.t - vis * 0.62, len(self.doc) - vis)))

    # ── the frame ─────────────────────────────────────────────────────

    def redraw(self) -> None:
        """One frame — overview, stage, spine, status, all from the same spans."""
        st = self.st
        self.cv.delete("all")
        f = Frame(self.cv, st, self.font_cache, self.mono_family, self.sans_family, self.hover, None, None)
        self.cv.create_rectangle(0, 0, self.w, self.h, fill=str(st.field), outline="")
        self.draw_header(f)
        self.draw_overview(f)
        self.draw_stage(f)
        self.draw_spine(f)
        self.draw_status(f)
        self.hits = f.hits

    def draw_header(self, f: Frame) -> None:
        """What is being watched, at what cost, on what authority."""
        t = f.text(MARGIN, 20, "THE WOLF", str(f.st.cool), f.font("sans", 4, "bold"))
        resolved = " · ambiguity settled by a supplied first-derivation resolver" if self.fx.resolved else ""
        f.text(
            t[2] + 18, 26,
            f"{self.fx.reader} read {len(self.doc):,} chars ({len(self.line_starts):,} lines) "
            f"in {self.fx.seconds:.2f}s · {len(self.spans):,} spans · depth {self.maxdepth}{resolved}",
            str(f.st.dim), f.font("sans", -1),
        )

    def draw_overview(self, f: Frame) -> None:
        """The whole document as span density — nothing is off the map."""
        st = self.st
        y2 = OV_Y + OV_H
        top = max(self.coverage) if self.coverage else 1
        step = max(1, len(self.doc) // max(1, self.w - 2 * MARGIN))
        run_x, run_level = MARGIN, -1
        for off in range(0, len(self.doc), step):
            level = min(3, (max(self.coverage[off : off + step]) * 4) // (top + 1))
            x = self.ov_x(off)
            if level != run_level:
                if run_level >= 0:
                    self.cv.create_rectangle(run_x, OV_Y, x, y2, fill=DENSITY[run_level], outline="")
                run_x, run_level = x, level
        if run_level >= 0:
            self.cv.create_rectangle(run_x, OV_Y, self.ov_x(len(self.doc)), y2, fill=DENSITY[run_level], outline="")
        read_x = self.ov_x(min(self.t, len(self.doc)))
        self.cv.create_rectangle(MARGIN, y2 + 3, read_x, y2 + 6, fill=CLOSED_FILL, outline=str(st.cool))
        vis = self.visible()
        self.cv.create_rectangle(
            self.ov_x(self.view0), OV_Y - 3, self.ov_x(min(self.view0 + vis, len(self.doc))), y2 + 8,
            outline=str(st.warm),
        )
        self.cv.create_line(read_x, OV_Y - 6, read_x, y2 + 10, fill=str(st.warm))
        f.text(MARGIN, OV_Y - 22, "the whole document · brightness = how many spans cover a character", str(st.dim), f.font("sans", -3))

    def draw_stage(self, f: Frame) -> None:
        """The viewport — glyphs, ruler, and every span that crosses the window."""
        st = self.st
        vis = self.visible()
        v0, v1 = self.view0, min(self.view0 + vis, len(self.doc))
        glyph_y = OV_Y + OV_H + 56
        read = int(self.t)
        for i in range(v0, v1):
            ch = self.doc[i]
            shown = "↵" if ch == "\n" else ch
            colour = str(st.ink) if i < read else str(st.dim)
            if i == read and self.t < len(self.doc):
                colour = str(st.warm)
            if ch == "\n":
                colour = PENDING_LINE if i >= read else str(st.dim)
            self.cv.create_text(self.sx(i + 0.5), glyph_y, text=shown, fill=colour, font=f.font("mono", 2), anchor="s")
        for off in range((v0 // 20 + 1) * 20, v1, 20):
            x = self.sx(off)
            self.cv.create_line(x, glyph_y + 4, x, glyph_y + 9, fill=str(st.dim))
            self.cv.create_text(x, glyph_y + 10, text=f"{off:,}", fill=str(st.dim), font=f.font("mono", -3), anchor="n")
        lanes_y = glyph_y + 34
        lane_h = max(13, min(34, (self.h - lanes_y - 84) // (self.maxdepth + 1)))
        lo = bisect_right(self.starts, v1)
        shown_count = 0
        for i in range(lo):
            span = self.drawable[i]
            if span.end <= v0:
                continue
            self.draw_span(f, i, span, v0, v1, lanes_y, lane_h)
            shown_count += 1
        self.in_view = shown_count
        for d in range(0, self.maxdepth + 1, 2):
            f.text(self.stage_x() - 22, lanes_y + d * lane_h + 2, f"d{d}", str(st.dim), f.font("mono", -4))

    def draw_span(self, f: Frame, i: int, span: Span, v0: int, v1: int, lanes_y: int, lane_h: int) -> None:
        """One occurrence's bar, clipped to the viewport, state given by the cursor."""
        st = self.st
        x1 = self.sx(max(span.start, v0))
        x2 = self.sx(min(span.end, v1))
        y1 = lanes_y + span.depth * lane_h
        y2 = y1 + lane_h - max(3, lane_h // 4)
        if span.end <= self.t:
            self.cv.create_rectangle(x1, y1, x2, y2, fill=CLOSED_FILL, outline=str(st.cool))
        elif span.start < self.t:
            xm = self.sx(min(self.t, min(span.end, v1)))
            if xm > x1:
                self.cv.create_rectangle(x1, y1, xm, y2, fill=ACTIVE_FILL, outline="")
            self.cv.create_rectangle(x1, y1, x2, y2, outline=str(st.warm))
        else:
            self.cv.create_rectangle(x1, y1, x2, y2, outline=PENDING_LINE)
        if lane_h >= 15:
            label_font = f.font("mono", -3)
            if label_font.measure(span.label) < (x2 - x1) - 6:
                shade = str(st.ink) if span.start < self.t else str(st.dim)
                self.cv.create_text(x1 + 4, (y1 + y2) / 2, text=span.label, fill=shade, font=label_font, anchor="w")
        f.region((i,), (int(x1), int(y1), int(x2), int(y2)))

    def draw_spine(self, f: Frame) -> None:
        """The stack open at the cursor — bounded by depth, whatever the document is."""
        st = self.st
        x = self.w - TREE_W - MARGIN + 24
        t = f.text(x, OV_Y + OV_H + 22, "THE SPINE — open at the cursor", str(st.cool), f.font("sans", 0, "bold"))
        yc = t[3] + 8
        open_now = [s for s in self.drawable if s.start < self.t < s.end]
        for k, span in enumerate(sorted(open_now, key=lambda s: s.depth)):
            deepest = k == len(open_now) - 1
            colour = str(st.warm) if deepest else str(st.ink)
            b = f.text(x, yc, f"d{span.depth:<3}{span.label}  {span.start:,}..{span.end:,}", colour, f.font("mono", -2))
            yc = b[3] + 3
        if not open_now:
            b = f.text(x, yc, "— nothing open (before the first span, or complete)", str(st.dim), f.font("sans", -2), width=TREE_W - 24)
            yc = b[3] + 3
        closed = [s for s in self.drawable if s.end <= self.t]
        yc += 12
        h = f.text(x, yc, "JUST CLOSED", str(st.cool), f.font("sans", -2, "bold"))
        yc = h[3] + 6
        for span in sorted(closed, key=lambda s: s.end)[-8:]:
            fresh = self.t - span.end < 2.5
            colour = str(st.warm) if fresh else str(st.dim)
            snippet = self.doc[span.start : span.end].replace("\n", "↵")
            snippet = snippet if len(snippet) <= 15 else snippet[:14] + "…"
            b = f.text(x, yc, f"{span.label}  {snippet!r}", colour, f.font("mono", -2))
            yc = b[3] + 3

    def draw_status(self, f: Frame) -> None:
        """Integers only: where, what state, what is drawn, what holds."""
        st = self.st
        state = "playing" if self.playing else ("complete" if self.t >= len(self.doc) else "paused")
        line = bisect_right(self.line_starts, int(min(self.t, len(self.doc) - 1))) if self.doc else 1
        left = (
            f"char {int(min(self.t, len(self.doc))):,} / {len(self.doc):,} · line {line:,} / {len(self.line_starts):,} · {state}"
            f" · overview travels · stage scrubs · Space replays · ←/→ step"
        )
        f.text(MARGIN, self.h - 30, left, str(st.dim), f.font("sans", -1))
        if self.hover is not None:
            s = self.drawable[self.hover[0]]
            snippet = self.doc[s.start : s.end].replace("\n", "↵")
            snippet = snippet if len(snippet) <= 40 else snippet[:39] + "…"
            f.text(MARGIN, self.h - 54, f"{s.label} · field {s.field or '—'} · {s.start:,}..{s.end:,} · depth {s.depth} · {snippet!r}",
                   str(st.warm), f.font("mono", -1), width=self.w - TREE_W - 2 * MARGIN)
        verdict = "— holds" if self.faithful else "— fails"
        colour = str(st.green) if self.faithful else str(st.red)
        b = f.text(self.w - MARGIN, self.h - 30, verdict, colour, f.font("mono", -2), anchor="ne")
        f.text(b[0] - 6, self.h - 30, f"in view {self.in_view:,} of {len(self.drawable):,} spans · to_text == document ",
               str(st.dim), f.font("mono", -2), anchor="ne")

    # ── time and the hand ─────────────────────────────────────────────

    def play(self) -> None:
        """Sweep the whole document in about SWEEP_SECONDS, following the cursor."""
        if self.t >= len(self.doc):
            self.t, self.view0 = 0.0, 0
        self.playing = True
        self.tick()

    def tick(self) -> None:
        """One step of document time."""
        if not self.playing:
            return
        self.t = min(self.t + (len(self.doc) / SWEEP_SECONDS) * TICK_MS / 1000.0, float(len(self.doc)))
        if self.t >= len(self.doc):
            self.playing = False
        self.follow()
        self.redraw()
        if self.playing:
            self.root.after(TICK_MS, self.tick)

    def on_resize(self, event: "tk.Event[tk.Canvas]") -> None:
        """The window is the user's — recompute everything from its actual size."""
        if (event.width, event.height) != (self.w, self.h):
            self.w, self.h = event.width, event.height
            self.redraw()

    def on_motion(self, event: "tk.Event[tk.Canvas]") -> None:
        """Overview travels; the stage scrubs; spans read out under the pointer."""
        if OV_Y - 8 <= event.y <= OV_Y + OV_H + 12:
            self.playing = False
            frac = (event.x - MARGIN) / max(1, self.w - 2 * MARGIN)
            self.t = max(0.0, min(frac, 1.0)) * len(self.doc)
            self.view0 = int(max(0, min(self.t - self.visible() * 0.5, len(self.doc) - self.visible())))
            self.redraw()
            return
        hover = None
        for box, path in reversed(self.hits):
            if box[0] <= event.x <= box[2] and box[1] <= event.y <= box[3]:
                hover = path
                break
        stage_top = OV_Y + OV_H + 30
        if stage_top <= event.y <= self.h - 70 and event.x < self.w - TREE_W - MARGIN:
            self.playing = False
            self.t = max(0.0, min(self.view0 + (event.x - self.stage_x()) / PITCH, float(len(self.doc))))
        elif hover == self.hover:
            return
        self.hover = hover
        self.redraw()

    def on_space(self, _event: "tk.Event[tk.Tk]") -> None:
        """Space toggles the sweep."""
        if self.playing:
            self.playing = False
            self.redraw()
        else:
            self.play()

    def on_step(self, event: "tk.Event[tk.Tk]") -> None:
        """One character at a time, viewport following."""
        self.playing = False
        delta = 1 if event.keysym == "Right" else -1
        self.t = float(max(0, min(int(self.t) + delta, len(self.doc))))
        self.follow()
        self.redraw()


def census(wolf: Wolf) -> int:
    """The gate — fidelity, fold integrity, bounded spine, honest view counts."""
    doc = wolf.doc
    ok_faithful = wolf.faithful
    ok_end = max(s.end for s in wolf.spans) == len(doc)
    worst_view, worst_spine = 0, 0
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        wolf.t = frac * len(doc)
        wolf.follow()
        wolf.redraw()
        worst_view = max(worst_view, wolf.in_view)
        worst_spine = max(worst_spine, len([s for s in wolf.drawable if s.start < wolf.t < s.end]))
    print(f"{wolf.fx.key}: {len(doc):,} chars · {len(wolf.spans):,} spans · depth {wolf.maxdepth} · parse {wolf.fx.seconds:.2f}s")
    print(f"to_text == document: {ok_faithful} · fold reaches end: {ok_end}")
    print(f"worst in-view spans {worst_view:,} · worst spine {worst_spine} (bound {wolf.maxdepth + 1}) · resolver {wolf.fx.resolved}")
    ok = ok_faithful and ok_end and worst_spine <= wolf.maxdepth + 1 and worst_view > 0
    print("census ok" if ok else "census FAILED")
    return 0 if ok else 1


def shot(wolf: Wolf, t: float, out: str) -> None:
    """One frame at document time ``t``, written as a PNG through ghostscript."""
    import subprocess

    wolf.playing = False
    wolf.t = t
    wolf.follow()
    wolf.redraw()
    wolf.root.update()
    ps_path = out + ".ps"
    wolf.cv.postscript(file=ps_path, colormode="color", width=wolf.w, height=wolf.h)
    subprocess.run(
        ["gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m", "-dEPSCrop",
         "-r120", f"-sOutputFile={out}", ps_path],
        check=True,
        capture_output=True,
    )
    print(f"wrote {out}")


def main() -> int:
    """Entry — fixture then mode; plays once by default."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    key = args[0] if args else "long"
    print(f"compiling and reading fixture '{key}' …")
    fixture = load_fixture(key)
    root = tk.Tk()
    wolf = Wolf(root, fixture)
    if "--census" in sys.argv:
        code = census(wolf)
        root.destroy()
        return code
    if "--shot" in sys.argv:
        at = sys.argv.index("--shot")
        shot(wolf, float(sys.argv[at + 1]), sys.argv[at + 2])
        root.destroy()
        return 0
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
