"""opsis-radical/atlas — the terminal leaf, slice 2: the read-side instrument, in cells.

A third client of the unchanged wire, now carrying the browser instrument's
read side: THE READER (rule co-lighting), THE DOCUMENT (styled cells; span
shading is a background attribute — the weld is free on a grid), THE
DERIVATION (overview density + depth lanes over the visible window), THE
SPINE, the routes strip, and the fidelity verdict. Facets degrade by deriving
less: the reader hides below 140 columns, the chart below 34 rows.

Run from the repo root, in a real terminal (ghostty recommended):

    uv run python zzz_current_work/260807-opsis-radical/atlas/tui.py [fixture] [port]
    uv run python zzz_current_work/260807-opsis-radical/atlas/tui.py vyx --census

Hover co-selects · drag selects text → smallest covering occurrence · click
sets the cursor · click a reader rule → its spans mark violet everywhere ·
overview row scrubs · Space plays · ←/→ step · c toggles the chart · Esc
clears · q quits. Slice 3 (write side): the grid editor, Ctrl+Enter/Ctrl+S
via the kitty keyboard protocol, the refusal frontier.
"""

import os
import re
import select
import subprocess
import sys
import termios
import time
import tty
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

FIELD = (11, 14, 20)
INK = (232, 226, 214)
DIM = (102, 112, 127)
DIMMER = (58, 66, 80)
COOL = (111, 195, 201)
WARM = (226, 166, 92)
VIOLET = (217, 140, 245)
RED = (224, 96, 96)
GREEN = (121, 201, 154)
OPEN_BG = (16, 30, 36)
HOVER_BG = (42, 52, 66)
SEL_BG = (66, 52, 30)
VIOLET_BG = (52, 34, 62)
LIT_BG = (20, 34, 40)
SPINE_W = 38
GUTTER_W = 6
SGR0 = "\x1b[0m"
SHADES = " ░▒▓█"


def fg(c: tuple[int, int, int]) -> str:
    """Foreground SGR for a 24-bit colour."""
    return f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m"


def bg(c: tuple[int, int, int]) -> str:
    """Background SGR for a 24-bit colour."""
    return f"\x1b[48;2;{c[0]};{c[1]};{c[2]}m"


class Scene:
    """The parsed frame: document, reader, spans, rules — the leaf-side record."""

    def __init__(self, raw: str) -> None:
        self.meta: dict[str, str] = {}
        self.spans: list[tuple[int, int, int, int, int]] = []
        self.rule_names: list[str] = []
        self.field_names: list[str] = []
        self.ruledefs: list[tuple[str, int, int]] = []
        i = raw.index("\n") + 1
        while not raw.startswith("#", i):
            j = raw.index("\n", i)
            key, _, value = raw[i:j].partition(" ")
            self.meta[key] = value
            i = j + 1
        while i < len(raw):
            j = raw.index("\n", i)
            head = raw[i:j].split(" ")
            i = j + 1
            tag, n = head[0], int(head[1])
            if tag in ("#READER", "#DOC"):
                block = raw[i : i + n]
                i += n + 1
                setattr(self, "reader" if tag == "#READER" else "doc", block)
                continue
            lines = []
            for _ in range(n):
                j = raw.index("\n", i)
                lines.append(raw[i:j])
                i = j + 1
            if tag == "#SPANS":
                self.spans = [tuple(int(x) for x in ln.split(" ")) for ln in lines]
            elif tag == "#RULENAMES":
                self.rule_names = lines
            elif tag == "#FIELDNAMES":
                self.field_names = lines
            elif tag == "#RULEDEFS":
                for ln in lines:
                    name, a, b = ln.rsplit(" ", 2)
                    self.ruledefs.append((name, int(a), int(b)))
        self.rule_of = {name: (a, b) for name, a, b in self.ruledefs}
        self.reader_lines = self.reader.split("\n")
        self.line_starts = [0] + [k + 1 for k, ch in enumerate(self.doc) if ch == "\n"]
        self.by_end = sorted(range(len(self.spans)), key=lambda k: self.spans[k][1])
        self.maxdepth = max((s[2] for s in self.spans), default=0)
        cover = [0] * (len(self.doc) + 1)
        for s, e, _d, _r, _f in self.spans:
            cover[s] += 1
            cover[e] -= 1
        self.coverage, run = [], 0
        for d in cover[:-1]:
            run += d
            self.coverage.append(run)
        self.covtop = max(self.coverage, default=1)

    def line_of(self, off: int) -> int:
        """The line containing character ``off``."""
        lo, hi = 0, len(self.line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.line_starts[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def deepest_at(self, off: int) -> int:
        """Index of the deepest span containing ``off``, or -1."""
        best = -1
        for k, (s, e, d, _r, _f) in enumerate(self.spans):
            if s <= off < e and (best < 0 or d > self.spans[best][2]):
                best = k
        return best

    def smallest_over(self, lo: int, hi: int) -> int:
        """Index of the smallest span covering [lo, hi), or -1."""
        best = -1
        for k, (s, e, _d, _r, _f) in enumerate(self.spans):
            if s <= lo and hi <= e and (best < 0 or e - s < self.spans[best][1] - self.spans[best][0]):
                best = k
        return best

    def open_at(self, t: float) -> list[int]:
        """Spans open at time ``t``, shallowest first."""
        found = [k for k, (s, e, _d, _r, _f) in enumerate(self.spans) if s < t < e]
        return sorted(found, key=lambda k: self.spans[k][2])


class Tui:
    """The instrument in cells — one scene, subject cursors, an immediate frame."""

    def __init__(self, scene: Scene, cols: int, rows: int) -> None:
        self.sc = scene
        self.cols = cols
        self.rows = rows
        self.t = 0.0
        self.playing = False
        self.hover = -1
        self.sel = -1
        self.sel_range: tuple[int, int] | None = None
        self.rule = ""
        self.show_chart = True
        self.top = 0
        self.reader_top = 0
        self.drag: tuple[int, bool] | None = None  # (anchor offset, moved)
        self.routes = "route: measuring…"

    # ── layout ────────────────────────────────────────────────────────

    def reader_w(self) -> int:
        """The reader facet's width — 0 when the terminal is too narrow."""
        return 42 if self.cols >= 140 else 0

    def chart_rows(self) -> int:
        """Rows the chart band occupies — 0 when the terminal is too short."""
        return (min(self.sc.maxdepth, 11) + 3) if (self.show_chart and self.rows >= 34) else 0

    def doc_x(self) -> int:
        """First column of the document pane."""
        return self.reader_w() + 1

    def doc_row0(self) -> int:
        """First terminal row of the document pane."""
        return 2 + self.chart_rows()

    def doc_w(self) -> int:
        """Columns available to document text."""
        return self.cols - self.reader_w() - SPINE_W - GUTTER_W - 3

    def doc_rows(self) -> int:
        """Rows available to the document pane."""
        return self.rows - self.doc_row0() - 3

    def follow(self) -> None:
        """Keep the cursor's line inside the visible document window."""
        line = self.sc.line_of(min(int(self.t), len(self.sc.doc) - 1))
        if line < self.top + 1:
            self.top = max(0, line - 1)
        elif line > self.top + self.doc_rows() - 3:
            self.top = min(line - self.doc_rows() + 3, len(self.sc.line_starts) - 1)

    def offset_at(self, x: int, y: int) -> int:
        """Document offset under terminal cell (x, y), or -1."""
        line = self.top + (y - self.doc_row0())
        if not (0 <= line < len(self.sc.line_starts)) or not (0 <= y - self.doc_row0() < self.doc_rows()):
            return -1
        x0 = self.doc_x() + GUTTER_W
        if not (x0 <= x < x0 + self.doc_w()):
            return -1
        start = self.sc.line_starts[line]
        end = (self.sc.line_starts[line + 1] - 1) if line + 1 < len(self.sc.line_starts) else len(self.sc.doc)
        return min(start + (x - x0), end)

    # ── the frame ─────────────────────────────────────────────────────

    def render(self) -> str:
        """One frame — the whole display, rebuilt from scene + cursors."""
        self.follow()
        sc = self.sc
        out = [f"\x1b[H{bg(FIELD)}\x1b[2J"]
        out.append(self.render_masthead())
        if self.chart_rows():
            out.append(self.render_chart())
        out.append(self.render_doc())
        if self.reader_w():
            out.append(self.render_reader())
        out.append(self.render_spine())
        out.append(self.render_status())
        return "".join(out)

    def render_masthead(self) -> str:
        """Title, facts, and the fidelity verdict."""
        m = self.sc.meta
        facts = (
            f"{m.get('fixture', '?')} · {len(self.sc.doc):,} chars · {len(self.sc.spans):,} spans"
            f" · read in {m.get('seconds', '?')}s · gen {m.get('generation', '?')}"
        )
        verdict = "to_text == document — holds" if m.get("faithful") == "1" else "to_text == document — FAILS"
        vcol = GREEN if m.get("faithful") == "1" else RED
        pad = max(1, self.cols - 14 - len(facts) - len(verdict) - 3)
        return (
            f"\x1b[1;1H {fg(COOL)}\x1b[1mOPSIS · TUI{SGR0}{bg(FIELD)}{fg(DIM)}  {facts}"
            f"{' ' * pad}{fg(vcol)}{verdict}"
        )

    def chart_x(self) -> int:
        """First column of the chart band — clear of the reader pane."""
        return self.reader_w() + 2

    def chart_w(self) -> int:
        """Columns available to the chart band."""
        return self.cols - self.chart_x() - 1

    def render_chart(self) -> str:
        """THE DERIVATION band: overview density, then depth lanes of the window."""
        sc = self.sc
        x, w = self.chart_x(), self.chart_w()
        out = [f"\x1b[2;{x}H{bg(FIELD)}{fg(COOL)}THE DERIVATION{fg(DIMMER)} · overview scrubs · lanes = visible window"]
        cells = []
        per = max(1, len(sc.doc) // w)
        read = int(self.t)
        for c in range(w):
            a = c * per
            m = max(sc.coverage[a : a + per], default=0)
            shade = SHADES[min(4, (m * 5) // (sc.covtop + 1))]
            colour = COOL if a <= read else DIMMER
            cells.append(f"{fg(colour)}{shade}")
        cur = min(w - 1, read // per)
        cells[cur] = f"{bg(WARM)}{fg(FIELD)}█{bg(FIELD)}"
        out.append(f"\x1b[3;{x}H{''.join(cells)}")
        v0 = sc.line_starts[self.top]
        vend_line = min(self.top + self.doc_rows(), len(sc.line_starts) - 1)
        v1 = sc.line_starts[vend_line] if vend_line < len(sc.line_starts) else len(sc.doc)
        v1 = max(v1, v0 + 1)
        cpc = max(1, (v1 - v0) // w + 1)
        depths = min(sc.maxdepth, 11)
        grid = [[" "] * w for _ in range(depths + 1)]
        for s, e, d, _r, _f in sc.spans:
            if d > depths or e <= v0 or s >= v1:
                continue
            c0 = max(0, (s - v0) // cpc)
            c1 = min(w - 1, (e - 1 - v0) // cpc)
            state = 2 if e <= self.t else (1 if s < self.t else 0)
            for c in range(c0, c1 + 1):
                grid[d][c] = state
        for d in range(depths + 1):
            row = []
            for c in range(w):
                cell = grid[d][c]
                if cell == " ":
                    row.append(" ")
                elif cell == 2:
                    row.append(f"{fg(COOL)}█")
                elif cell == 1:
                    row.append(f"{fg(WARM)}▓")
                else:
                    row.append(f"{fg(DIMMER)}░")
            out.append(f"\x1b[{4 + d};{x}H{''.join(row)}")
        return "".join(out)

    def render_doc(self) -> str:
        """THE DOCUMENT: gutter + per-cell styled text, absolute-positioned."""
        sc = self.sc
        read = int(self.t)
        open_bounds = [
            sc.spans[k][:2] for k in sc.open_at(self.t)
            if sc.spans[k][1] - sc.spans[k][0] < len(sc.doc)
        ]
        hover_range = sc.spans[self.hover][:2] if self.hover >= 0 else None
        sel_span = sc.spans[self.sel][:2] if self.sel >= 0 else None
        rule_ranges = [s[:2] for s in sc.spans if self.rule and sc.rule_names[s[3]] == self.rule]
        x = self.doc_x()
        out = []
        for r in range(self.doc_rows()):
            line = self.top + r
            row = self.doc_row0() + r
            if line >= len(sc.line_starts):
                out.append(f"\x1b[{row};{x}H{bg(FIELD)}\x1b[K")
                continue
            start = sc.line_starts[line]
            end = (sc.line_starts[line + 1] - 1) if line + 1 < len(sc.line_starts) else len(sc.doc)
            text = sc.doc[start:end][: self.doc_w()]
            cells = [f"\x1b[{row};{x}H{bg(FIELD)}{fg(DIMMER)}{line + 1:>5} "]
            for col, ch in enumerate(text):
                off = start + col
                back, front = FIELD, (INK if off < read else DIM)
                if any(s <= off < e for s, e in open_bounds):
                    back = OPEN_BG
                if any(s <= off < e for s, e in rule_ranges):
                    back = VIOLET_BG
                if hover_range and hover_range[0] <= off < hover_range[1]:
                    back = HOVER_BG
                if sel_span and sel_span[0] <= off < sel_span[1]:
                    back = SEL_BG
                if self.sel_range and self.sel_range[0] <= off < self.sel_range[1]:
                    back, front = SEL_BG, INK
                if off == read and self.t < len(sc.doc):
                    back, front = WARM, FIELD
                cells.append(f"{bg(back)}{fg(front)}{ch}")
            cells.append(f"{bg(FIELD)}\x1b[K")
            out.append("".join(cells))
        return "".join(out)

    def render_reader(self) -> str:
        """THE READER: the grammar, with the co-selected rule lit."""
        sc = self.sc
        lit = None
        active = self.rule
        if not active and self.sel >= 0:
            active = sc.rule_names[sc.spans[self.sel][3]]
        hot = sc.rule_names[sc.spans[self.hover][3]] if self.hover >= 0 else ""
        for name in (active, hot):
            if name in sc.rule_of:
                lit = sc.rule_of[name]
                break
        rows = self.doc_rows() + self.chart_rows()
        if lit and not (self.reader_top <= lit[0] < self.reader_top + rows - 2):
            self.reader_top = max(0, lit[0] - rows // 3)
        w = self.reader_w() - 2
        out = [f"\x1b[2;1H{bg(FIELD)}{fg(COOL)} THE READER{fg(DIMMER)} · grammar is the ground truth"]
        for r in range(rows - 1):
            ln = self.reader_top + r
            row = 3 + r
            if ln >= len(sc.reader_lines):
                out.append(f"\x1b[{row};1H{bg(FIELD)}{' ' * (w + 2)}")
                continue
            in_active = lit and active in sc.rule_of and sc.rule_of[active][0] <= ln <= sc.rule_of[active][1]
            in_hot = hot in sc.rule_of and sc.rule_of[hot][0] <= ln <= sc.rule_of[hot][1]
            back = LIT_BG if (in_active or in_hot) else FIELD
            colour = VIOLET if (self.rule and in_active) else (INK if (in_active or in_hot) else DIM)
            text = sc.reader_lines[ln][:w]
            out.append(f"\x1b[{row};1H{bg(back)}{fg(colour)} {text}{' ' * max(0, w - len(text) + 1)}{bg(FIELD)}")
        return "".join(out)

    def render_spine(self) -> str:
        """THE SPINE: the open stack at the cursor, and the last closures."""
        sc = self.sc
        open_now = sc.open_at(self.t)
        x = self.cols - SPINE_W
        row0 = self.doc_row0()
        out = [f"\x1b[{row0};{x}H{bg(FIELD)}{fg(COOL)}\x1b[1mTHE SPINE{SGR0}{bg(FIELD)}{fg(DIM)} open at the cursor"]
        row = row0 + 1
        budget = self.doc_rows() - 10
        for i, k in enumerate(open_now[:budget]):
            s, e, d, r, _f = sc.spans[k]
            colour = WARM if i == len(open_now) - 1 else INK
            out.append(
                f"\x1b[{row};{x}H{fg(DIMMER)}d{d:<3}{fg(colour)}{sc.rule_names[r][: SPINE_W - 18]}"
                f" {fg(DIM)}{s:,}..{e:,}\x1b[K"
            )
            row += 1
        if not open_now:
            out.append(f"\x1b[{row};{x}H{fg(DIM)}— nothing open\x1b[K")
            row += 1
        row += 1
        out.append(f"\x1b[{row};{x}H{fg(COOL)}\x1b[1mJUST CLOSED{SGR0}{bg(FIELD)}")
        row += 1
        done = [k for k in sc.by_end if sc.spans[k][1] <= self.t][-6:]
        for k in done:
            s, e, _d, r, _f = sc.spans[k]
            snip = sc.doc[s:e].replace("\n", "↵")
            snip = snip if len(snip) <= 14 else snip[:13] + "…"
            fresh = self.t - e < 3
            out.append(f"\x1b[{row};{x}H{fg(WARM if fresh else DIM)}{sc.rule_names[r][:14]} '{snip}'\x1b[K")
            row += 1
        return "".join(out)

    def render_status(self) -> str:
        """Bottom strip: readout, position and keys, the routes line."""
        sc = self.sc
        state = "playing" if self.playing else ("complete" if self.t >= len(sc.doc) else "paused")
        line = sc.line_of(min(int(self.t), len(sc.doc) - 1)) + 1
        focus = self.sel if self.sel >= 0 else self.hover
        words = ""
        if focus >= 0:
            s, e, d, r, f_ = sc.spans[focus]
            field = sc.field_names[f_] if f_ < len(sc.field_names) else ""
            words = (
                f" {sc.rule_names[r]}{' · field ' + field if field else ''} · {s:,}..{e:,} · d{d}"
                + (" · from your selection" if self.sel >= 0 and self.sel_range else "")
            )
        elif self.rule:
            words = f" rule {self.rule} — its spans marked violet everywhere · Esc clears"
        keys = (
            f" char {min(int(self.t), len(sc.doc)):,} / {len(sc.doc):,} · line {line:,} · {state}"
            " · hover co-selects · drag selects · click sets cursor · rule-click lights"
            " · Space plays · ←/→ · c chart · Esc · q"
        )
        return (
            f"\x1b[{self.rows - 2};1H{bg(FIELD)}{fg(WARM)}{words[: self.cols]}\x1b[K"
            f"\x1b[{self.rows - 1};1H{bg(FIELD)}{fg(DIM)}{keys[: self.cols]}\x1b[K"
            f"\x1b[{self.rows};1H{bg(FIELD)}{fg(DIMMER)} {self.routes[: self.cols - 2]}\x1b[K"
        )


# ── terminal plumbing ─────────────────────────────────────────────────


def term_size() -> tuple[int, int]:
    """Current (cols, rows) of the controlling terminal."""
    size = os.get_terminal_size()
    return size.columns, size.lines


def fetch(port: int, path: str) -> str:
    """One GET from the server."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as resp:
        return resp.read().decode()


def post(port: int, path: str, body: str) -> None:
    """Fire-and-forget gesture."""
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body.encode()), timeout=2
        ).read()
    except OSError:
        pass


def ensure_server(fixture: str, port: int) -> subprocess.Popen | None:
    """Reuse a running server or spawn one, waiting for its first scene."""
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/scene", timeout=1)
        return None
    except OSError:
        pass
    proc = subprocess.Popen(
        ["uv", "run", "python", str(HERE / "serve.py"), fixture, str(port)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(240):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/scene", timeout=1)
            return proc
        except OSError:
            time.sleep(0.25)
    proc.kill()
    raise SystemExit(f"server for '{fixture}' did not come up on :{port}")


def routes_line(port: int) -> str:
    """The routes strip, as one sentence."""
    r = {}
    try:
        for ln in fetch(port, "/routes").split("\n"):
            k, _, v = ln.partition(" ")
            r[k] = v
    except OSError:
        return "route: unreachable"
    base = f"route: {r.get('primary', '?')} {r.get('primary_seconds', '?')}s"
    if r.get("status") == "pending":
        return base + " · the other engine is running…"
    if r.get("status") == "done":
        parity = r.get("parity", "unmeasured")
        word = "both engines built the same value — holds" if parity == "holds" else f"parity {parity}"
        return f"{base} · {r.get('name', '?')} {r.get('seconds', '?')}s · {word}"
    pos = r.get("pos", "-1")
    return f"{base} · {r.get('name', '?')} ended" + (f" at char {int(pos):,} — where the fast road stops" if pos != "-1" else "")


MOUSE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")


def run(fixture: str, port: int) -> int:
    """The interactive loop — raw mode, mouse tracking, immediate redraw."""
    proc = ensure_server(fixture, port)
    scene = Scene(fetch(port, "/scene"))
    cols, rows = term_size()
    ui = Tui(scene, cols, rows)
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[?1003h\x1b[?1006h")
    tty.setraw(fd)
    last_post = 0.0
    last_routes = 0.0
    try:
        ui.playing = True
        last = time.monotonic()
        buf = ""
        while True:
            timeout = 0.03 if ui.playing else 0.5
            ready, _, _ = select.select([fd], [], [], timeout)
            now = time.monotonic()
            if ui.playing:
                ui.t = min(ui.t + (len(scene.doc) / 22) * (now - last), float(len(scene.doc)))
                if ui.t >= len(scene.doc):
                    ui.playing = False
            last = now
            ui.cols, ui.rows = term_size()
            if ready:
                data = os.read(fd, 4096).decode(errors="replace")
                buf = handle(ui, buf + data, scene)
                if buf is None:
                    return 0
            if now - last_routes > 2.5:
                last_routes = now
                ui.routes = routes_line(port)
            if now - last_post > 0.4:
                last_post = now
                post(port, "/cursor", f"t {ui.t:.1f} sel {max(ui.sel, ui.hover)}")
            sys.stdout.write(ui.render())
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        sys.stdout.write("\x1b[?1003l\x1b[?1006l\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if proc is not None:
            proc.kill()


def mouse_event(ui: Tui, scene: Scene, code: int, x: int, y: int, kind: str) -> None:
    """One SGR mouse report — zones: overview row, reader pane, document pane."""
    if code in (64, 65):
        ui.top = max(0, min(ui.top + (3 if code == 65 else -3), len(scene.line_starts) - 1))
        return
    if y == 3 and ui.chart_rows() and code == 0 and kind == "M" and x >= ui.chart_x():
        frac = max(0.0, min((x - ui.chart_x()) / max(1, ui.chart_w()), 1.0))
        ui.playing = False
        ui.t = frac * len(scene.doc)
        return
    if ui.reader_w() and x <= ui.reader_w() and code == 0 and kind == "M":
        ln = ui.reader_top + (y - 3)
        for name, a, b in scene.ruledefs:
            if a <= ln <= b:
                ui.rule = "" if ui.rule == name else name
                return
        return
    off = ui.offset_at(x, y)
    if code in (35,):  # plain motion
        ui.hover = scene.deepest_at(off) if off >= 0 else -1
    elif code == 32 and kind == "M":  # press or drag with button 1
        if ui.drag is None:
            if off >= 0:
                ui.drag = (off, False)
        elif off >= 0:
            a = ui.drag[0]
            ui.drag = (a, True)
            ui.sel_range = (min(a, off), max(a, off) + 1)
    elif code == 0:
        if kind == "M":
            if off >= 0:
                ui.drag = (off, False)
        else:  # release
            if ui.drag and ui.drag[1] and ui.sel_range:
                ui.sel = scene.smallest_over(*ui.sel_range)
            elif off >= 0:
                ui.playing = False
                ui.t = float(off)
                ui.sel = -1
                ui.sel_range = None
            ui.drag = None


def handle(ui: Tui, buf: str, scene: Scene) -> str | None:
    """Consume input bytes; None means quit."""
    while buf:
        m = MOUSE.match(buf)
        if m:
            mouse_event(ui, scene, int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4))
            buf = buf[m.end():]
            continue
        ch = buf[0]
        if ch == "q":
            return None
        if ch == " ":
            if ui.t >= len(scene.doc):
                ui.t = 0.0
            ui.playing = not ui.playing
        elif ch == "c":
            ui.show_chart = not ui.show_chart
        elif buf.startswith("\x1b[C"):
            ui.playing = False
            ui.t = min(float(len(scene.doc)), int(ui.t) + 1.0)
            buf = buf[3:]
            continue
        elif buf.startswith("\x1b[D"):
            ui.playing = False
            ui.t = max(0.0, int(ui.t) - 1.0)
            buf = buf[3:]
            continue
        elif ch == "\x1b" and len(buf) < 3:
            return buf  # partial escape — wait for more bytes
        elif ch == "\x1b" and not buf.startswith("\x1b["):
            ui.sel = -1
            ui.sel_range = None
            ui.rule = ""
        buf = buf[1:]
    return buf


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def census(fixture: str, port: int) -> int:
    """Headless gate: scripted states rendered at a fixed size, asserted as text."""
    proc = ensure_server(fixture, port)
    try:
        scene = Scene(fetch(port, "/scene"))
        ui = Tui(scene, 190, 48)
        ui.routes = routes_line(port)
        ui.t = len(scene.doc) / 2
        ui.hover = scene.deepest_at(int(ui.t))
        mid = int(ui.t)
        ui.sel_range = (mid, mid + 5)
        ui.sel = scene.smallest_over(mid, mid + 5)
        frame = ui.render()
        plain = ANSI.sub("", frame)
        open_now = scene.open_at(ui.t)
        hover_rule = scene.rule_names[scene.spans[ui.hover][3]] if ui.hover >= 0 else ""
        checks = {
            "reader drawn": "THE READER" in plain,
            "reader lights the rule": (hover_rule not in scene.rule_of)
            or (hover_rule + " ::=" in plain),
            "chart drawn": "THE DERIVATION" in plain and any(s in plain for s in SHADES[1:]),
            "spine drawn": "THE SPINE" in plain and "JUST CLOSED" in plain,
            "spine bounded": len(open_now) <= scene.maxdepth + 1,
            "caret styled": bg(WARM) in frame,
            "selection co-selected": ui.sel >= 0 and bg(SEL_BG) in frame,
            "routes line": "route:" in plain,
            "verdict": "holds" in plain or "FAILS" in plain,
        }
        print(f"{fixture}: {len(scene.doc):,} chars · {len(scene.spans):,} spans · "
              f"frame {len(frame):,} bytes ({len(plain):,} visible)")
        print(" · ".join(f"{k} {v}" for k, v in checks.items()))
        ok = all(checks.values())
        print("census ok" if ok else "census FAILED")
        return 0 if ok else 1
    finally:
        if proc is not None:
            proc.kill()


def main() -> int:
    """Entry — interactive by default, census for the gate."""
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fixture = args[0] if args else "vyx"
    port = int(args[1]) if len(args) > 1 else 8919
    if "--census" in sys.argv:
        return census(fixture, port)
    if not sys.stdout.isatty():
        raise SystemExit("tui needs a terminal (use --census for the headless gate)")
    return run(fixture, port)


if __name__ == "__main__":
    raise SystemExit(main())
