"""opsis-radical/atlas — the terminal leaf, slice 1: the interactive display, in cells.

A third client of the unchanged wire (`/scene`, `/cursor`): the document facet
as styled cells (span shading IS a background attribute — the weld the browser
needed canvases for is free on a grid), the spine beside it, one cursor of
document time. Mouse hovers co-select, clicks set the cursor, Space plays,
arrows step. Stdlib only; the server is spawned if not already up.

Run from the repo root, in a real terminal (ghostty recommended):

    uv run python zzz_current_work/260807-opsis-radical/atlas/tui.py [fixture] [port]
    uv run python zzz_current_work/260807-opsis-radical/atlas/tui.py vyx --census

Slice 1 deliberately excludes editing (the grid editor is slice 2, informed by
how selection feels here). q quits.
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
RED = (224, 96, 96)
GREEN = (121, 201, 154)
OPEN_BG = (16, 30, 36)
HOVER_BG = (42, 52, 66)
SPINE_W = 38
GUTTER_W = 6
ESCAPE = "\x1b"
SGR0 = "\x1b[0m"


def fg(c: tuple[int, int, int]) -> str:
    """Foreground SGR for a 24-bit colour."""
    return f"\x1b[38;2;{c[0]};{c[1]};{c[2]}m"


def bg(c: tuple[int, int, int]) -> str:
    """Background SGR for a 24-bit colour."""
    return f"\x1b[48;2;{c[0]};{c[1]};{c[2]}m"


class Scene:
    """The parsed frame: document, spans, rules — the leaf-side scene record."""

    def __init__(self, raw: str) -> None:
        self.meta: dict[str, str] = {}
        self.spans: list[tuple[int, int, int, int, int]] = []
        self.rule_names: list[str] = []
        self.field_names: list[str] = []
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
        self.line_starts = [0] + [k + 1 for k, ch in enumerate(self.doc) if ch == "\n"]
        self.by_end = sorted(range(len(self.spans)), key=lambda k: self.spans[k][1])

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

    def open_at(self, t: float) -> list[int]:
        """Spans open at time ``t``, shallowest first."""
        found = [k for k, (s, e, _d, _r, _f) in enumerate(self.spans) if s < t < e]
        return sorted(found, key=lambda k: self.spans[k][2])


class Tui:
    """The instrument in cells — one scene, one cursor, an immediate-mode frame."""

    def __init__(self, scene: Scene, cols: int, rows: int) -> None:
        self.sc = scene
        self.cols = cols
        self.rows = rows
        self.t = 0.0
        self.playing = False
        self.hover = -1
        self.top = 0  # first visible document line

    # ── geometry ──────────────────────────────────────────────────────

    def doc_w(self) -> int:
        """Columns available to the document text after gutter and spine."""
        return self.cols - SPINE_W - GUTTER_W - 3

    def doc_rows(self) -> int:
        """Rows available to the document pane."""
        return self.rows - 4

    def follow(self) -> None:
        """Keep the cursor's line inside the visible window."""
        line = self.sc.line_of(min(int(self.t), len(self.sc.doc) - 1))
        if line < self.top + 1:
            self.top = max(0, line - 1)
        elif line > self.top + self.doc_rows() - 3:
            self.top = min(line - self.doc_rows() + 3, len(self.sc.line_starts) - 1)

    def offset_at(self, x: int, y: int) -> int:
        """Document offset under terminal cell (x, y), or -1."""
        line = self.top + (y - 2)
        if not (0 <= line < len(self.sc.line_starts)) or y - 2 >= self.doc_rows():
            return -1
        if not (GUTTER_W < x <= GUTTER_W + self.doc_w()):
            return -1
        start = self.sc.line_starts[line]
        end = (self.sc.line_starts[line + 1] - 1) if line + 1 < len(self.sc.line_starts) else len(self.sc.doc)
        return min(start + (x - GUTTER_W - 1), end)

    # ── the frame ─────────────────────────────────────────────────────

    def render(self) -> str:
        """One frame — the whole display, rebuilt from scene + cursors."""
        self.follow()
        sc = self.sc
        read = int(self.t)
        open_now = sc.open_at(self.t)
        open_set: set[int] = set()
        for k in open_now:
            s, e, _d, _r, _f = sc.spans[k]
            if e - s < len(sc.doc):  # the root span would shade everything
                open_set.update((s, e))
        hover_range = sc.spans[self.hover][:2] if self.hover >= 0 else None
        out = [f"\x1b[H{bg(FIELD)}\x1b[2J"]
        state = "playing" if self.playing else ("complete" if self.t >= len(sc.doc) else "paused")
        title = (
            f" {fg(COOL)}\x1b[1mOPSIS · TUI{SGR0}{bg(FIELD)}{fg(DIM)}  {self.meta_line()}"
        )
        out.append(title[: self.cols * 8] + "\r\n")
        rows = self.doc_rows()
        for r in range(rows):
            out.append(self.render_line(self.top + r, read, open_now, hover_range))
        out.append(self.render_status(state))
        out.append(self.render_spine(open_now))
        return "".join(out)

    def meta_line(self) -> str:
        """The masthead facts."""
        m = self.sc.meta
        return (
            f"{m.get('fixture', '?')} · {len(self.sc.doc):,} chars · "
            f"{len(self.sc.spans):,} spans · read in {m.get('seconds', '?')}s · gen {m.get('generation', '?')}"
        )

    def render_line(self, line: int, read: int, open_now: list[int], hover_range) -> str:
        """One document row: gutter, then per-cell styled text."""
        sc = self.sc
        if line >= len(sc.line_starts):
            return f"{bg(FIELD)}\x1b[K\r\n"
        start = sc.line_starts[line]
        end = (sc.line_starts[line + 1] - 1) if line + 1 < len(sc.line_starts) else len(sc.doc)
        text = sc.doc[start:end][: self.doc_w()]
        cells = [f"{bg(FIELD)}{fg(DIMMER)}{line + 1:>5} "]
        spine_bounds = [sc.spans[k][:2] for k in open_now if sc.spans[k][1] - sc.spans[k][0] < len(sc.doc)]
        for col, ch in enumerate(text):
            off = start + col
            back, front = FIELD, (INK if off < read else DIM)
            if any(s <= off < e for s, e in spine_bounds):
                back = OPEN_BG
            if hover_range and hover_range[0] <= off < hover_range[1]:
                back = HOVER_BG
            if off == read and self.t < len(sc.doc):
                back, front = WARM, FIELD
            cells.append(f"{bg(back)}{fg(front)}{ch}")
        if read == end and sc.line_of(min(read, len(sc.doc) - 1)) == line and self.t < len(sc.doc):
            cells.append(f"{bg(WARM)} ")  # caret sitting on the newline
        cells.append(f"{bg(FIELD)}\x1b[K\r\n")
        return "".join(cells)

    def render_status(self, state: str) -> str:
        """The bottom strip: position, state, and the hovered span's words."""
        sc = self.sc
        line = sc.line_of(min(int(self.t), len(sc.doc) - 1)) + 1
        left = (
            f" char {min(int(self.t), len(sc.doc)):,} / {len(sc.doc):,} · line {line:,} · {state}"
            " · hover co-selects · click sets the cursor · Space plays · ←/→ step · q quits"
        )
        words = ""
        if self.hover >= 0:
            s, e, d, r, f_ = sc.spans[self.hover]
            field = sc.field_names[f_] if f_ < len(sc.field_names) else ""
            words = (
                f" {sc.rule_names[r]}{' · field ' + field if field else ''}"
                f" · {s:,}..{e:,} · d{d}"
            )
        return (
            f"{bg(FIELD)}{fg(WARM)}{words[: self.cols]}\x1b[K\r\n"
            f"{bg(FIELD)}{fg(DIM)}{left[: self.cols]}\x1b[K"
        )

    def render_spine(self, open_now: list[int]) -> str:
        """The right pane, drawn with absolute cursor moves: open stack + closures."""
        sc = self.sc
        x = self.cols - SPINE_W
        out = [f"\x1b[2;{x}H{bg(FIELD)}{fg(COOL)}\x1b[1mTHE SPINE{SGR0}{bg(FIELD)}{fg(DIM)} open at the cursor"]
        row = 3
        for i, k in enumerate(open_now[: self.doc_rows() - 10]):
            s, e, d, r, _f = sc.spans[k]
            colour = WARM if i == len(open_now) - 1 else INK
            out.append(
                f"\x1b[{row};{x}H{fg(DIMMER)}d{d:<3}{fg(colour)}{sc.rule_names[r][: SPINE_W - 18]}"
                f" {fg(DIM)}{s:,}..{e:,}\x1b[K"
            )
            row += 1
        if not open_now:
            out.append(f"\x1b[{row};{x}H{fg(DIM)}— nothing open")
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
            out.append(
                f"\x1b[{row};{x}H{fg(WARM if fresh else DIM)}{sc.rule_names[r][:14]} '{snip}'\x1b[K"
            )
            row += 1
        return "".join(out)


# ── terminal plumbing ─────────────────────────────────────────────────


def term_size() -> tuple[int, int]:
    """Current (cols, rows) of the controlling terminal."""
    size = os.get_terminal_size()
    return size.columns, size.lines


def fetch_scene(port: int) -> Scene:
    """One frame from the server."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/scene", timeout=10) as resp:
        return Scene(resp.read().decode())


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


MOUSE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")


def run(fixture: str, port: int) -> int:
    """The interactive loop — raw mode, mouse tracking, immediate redraw."""
    proc = ensure_server(fixture, port)
    scene = fetch_scene(port)
    cols, rows = term_size()
    ui = Tui(scene, cols, rows)
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[?1003h\x1b[?1006h")
    tty.setraw(fd)
    last_post = 0.0
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
            if ready:
                buf += os.read(fd, 1024).decode(errors="replace")
                buf = handle(ui, buf, scene)
                if buf is None:
                    return 0
            if now - last_post > 0.4:
                last_post = now
                post(port, "/cursor", f"t {ui.t:.1f} sel {ui.hover}")
            sys.stdout.write(ui.render())
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        sys.stdout.write("\x1b[?1003l\x1b[?1006l\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if proc is not None:
            proc.kill()


def handle(ui: Tui, buf: str, scene: Scene) -> str | None:
    """Consume input bytes; None means quit."""
    while buf:
        m = MOUSE.match(buf)
        if m:
            code, x, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            off = ui.offset_at(x, y)
            if code in (35, 32):  # motion
                ui.hover = scene.deepest_at(off) if off >= 0 else -1
            elif code == 0 and m.group(4) == "M" and off >= 0:  # press
                ui.playing = False
                ui.t = float(off)
            elif code in (64, 65):  # wheel
                ui.top = max(0, min(ui.top + (3 if code == 65 else -3), len(scene.line_starts) - 1))
            buf = buf[m.end():]
            continue
        ch = buf[0]
        if ch == "q":
            return None
        if ch == " ":
            if ui.t >= len(scene.doc):
                ui.t = 0.0
            ui.playing = not ui.playing
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
        buf = buf[1:]
    return buf


ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def census(fixture: str, port: int) -> int:
    """Headless gate: scripted states rendered at a fixed size, asserted as text."""
    proc = ensure_server(fixture, port)
    try:
        scene = fetch_scene(port)
        ui = Tui(scene, 170, 44)
        ui.t = len(scene.doc) / 2
        ui.hover = scene.deepest_at(int(ui.t))
        frame = ui.render()
        plain = ANSI.sub("", frame)
        open_now = scene.open_at(ui.t)
        doc_line = scene.line_of(int(ui.t))
        line_text = scene.doc[scene.line_starts[doc_line]:].split("\n")[0][:40]
        ok_doc = line_text[:20] in plain if line_text.strip() else True
        ok_spine = "THE SPINE" in plain and "JUST CLOSED" in plain
        ok_bound = len(open_now) <= max(s[2] for s in scene.spans) + 1
        ok_caret = bg(WARM) in frame
        ok_hover = ui.hover >= 0 and scene.rule_names[scene.spans[ui.hover][3]] in plain
        print(f"{fixture}: {len(scene.doc):,} chars · {len(scene.spans):,} spans · "
              f"frame {len(frame):,} bytes ({len(plain):,} visible)")
        print(f"doc text drawn {ok_doc} · spine drawn {ok_spine} (open {len(open_now)}, bounded {ok_bound}) · "
              f"caret styled {ok_caret} · hover co-selected {ok_hover}")
        ok = ok_doc and ok_spine and ok_bound and ok_caret and ok_hover
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
