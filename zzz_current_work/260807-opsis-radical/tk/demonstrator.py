"""opsis-radical — lexic IR drawn live, by an instrument that is itself an IR value.

Run from the repo root:

    uv run python zzz_current_work/260807-opsis-radical/demonstrator.py

``--census`` draws one frame, performs a scripted self-modification and a scripted
refusal, prints the counts, and exits 0 only if all of it held.
``--shot out.png`` writes a PNG of the frame (canvas postscript through ghostscript).
"""

import re
import subprocess
import sys
import tkinter as tk
import tkinter.font as tkfont

from present import (
    MONO_FAMILIES,
    SANS_FAMILIES,
    Box,
    FontCache,
    Frame,
    draw_subject,
)
from scene import (
    Exhibit,
    Path,
    Session,
    Style,
    initial_session,
    node_at,
    set_at,
    spell_path,
    walk,
)

from lexic.ir import IrInt, IrNamedTuple, IrNone, IrNoneType, IrSelf, IrStr

W, H = 1500, 940
MARGIN = 28
CARD_W = 600
PANEL_X = 680
PANEL_W = 420
INSPECT_X = 1130
INSPECT_W = 340
HEX = re.compile(r"#[0-9a-fA-F]{6}")


def fact_lines(subject: IrSelf) -> list[tuple[str, bool]]:
    """Facts measured on the live subject, each with its verdict."""
    if isinstance(subject, IrNoneType):
        return [
            ("subject is IrNone", subject is IrNone),
            ("isinstance(subject, IrSelf) — absence fits any child slot", isinstance(subject, IrSelf)),
        ]
    if isinstance(subject, IrStr):
        plain = str(subject)
        return [
            (f"subject == {plain!r}", subject == plain),
            ("isinstance(subject, str)", isinstance(subject, str)),
            ("no '.value' accessor exists", not hasattr(subject, "value")),
        ]
    if isinstance(subject, IrNamedTuple):
        first = type(subject)._fields[0]
        return [
            (f"subject.{first} is subject[0]", getattr(subject, first) is subject[0]),
            ("isinstance(subject, tuple) — the record IS the tuple", isinstance(subject, tuple)),
            (
                f"len(subject) == {len(type(subject)._fields)} — nothing but the fields",
                len(subject) == len(type(subject)._fields),
            ),
        ]
    return []


def kind_line(node: IrSelf | int | str) -> str:
    """One sentence saying what tier of thing the selection is."""
    if isinstance(node, IrNoneType):
        return "the absence singleton — one spelling, compare with `is`"
    if isinstance(node, IrNamedTuple):
        return f"record — fields: {', '.join(type(node)._fields)}"
    if isinstance(node, IrSelf):
        return "value leaf — the node IS its payload"
    return f"plain {type(node).__name__} payload — carried by its record, not a node"


def detail_line(node: IrSelf | int | str) -> str:
    """The selection's own spelling for the inspector."""
    if isinstance(node, IrNamedTuple):
        return repr(node)
    if isinstance(node, str):
        return repr(str(node))
    if isinstance(node, int):
        return str(int(node))
    return repr(node)


class App:
    """The instrument — one session value, the hand that edits it, and the loop."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.session = initial_session()
        self.hover: Path | None = None
        self.selection: Path | None = None
        self.buffer: str | None = None
        self.note: tuple[str, str] = (
            "dim",
            "click a value · type to retype it · Enter commits · Esc cancels — "
            "grey text is opsis speaking; everything monospace is a live lexic value",
        )
        self.font_cache: FontCache = {}
        self.hits: list[tuple[Box, Path]] = []
        self.counts = (0, 0)
        families = set(tkfont.families(root))
        self.mono_family = next((n for n in MONO_FAMILIES if n in families), "Courier")
        self.sans_family = next((n for n in SANS_FAMILIES if n in families), "Helvetica")
        root.title("opsis-radical")
        self.cv = tk.Canvas(root, width=W, height=H, highlightthickness=0)
        self.cv.pack()
        self.cv.bind("<Motion>", self.on_motion)
        self.cv.bind("<Button-1>", self.on_click)
        root.bind("<Key>", self.on_key)
        self.redraw()

    # ── the frame ──────────────────────────────────────────────────────

    def redraw(self) -> None:
        """One frame — everything on screen, rebuilt from the session value."""
        st = self.session.style
        self.cv.delete("all")
        f = Frame(
            self.cv, st, self.font_cache, self.mono_family, self.sans_family,
            self.hover, self.selection, self.buffer,
        )
        self.cv.create_rectangle(0, 0, W, H, fill=str(st.field), outline="")
        self.draw_header(f)
        y = 96
        for i, exhibit in enumerate(self.session.exhibits):
            y = self.draw_card(f, exhibit, (1, i), MARGIN, y) + max(8, int(st.pad) // 2) + 4
        self.draw_axiom(f, MARGIN, y + 2)
        self.draw_instrument(f, PANEL_X, 96)
        self.draw_inspector(f, INSPECT_X, 96)
        self.draw_status(f)
        self.hits = f.hits
        self.counts = (len(f.hits), len(f.refusals))

    def draw_header(self, f: Frame) -> None:
        """The masthead — the instrument's one sentence about itself."""
        t = f.text(MARGIN, 24, "OPSIS — RADICAL", str(f.st.cool), f.font("sans", 4, "bold"))
        f.text(
            t[2] + 18, 30,
            "every region below is a live lexic value · one open table draws lexic's IR, "
            "the instrument, and the instrument's own configuration",
            str(f.st.dim), f.font("sans", -1),
        )

    def draw_card(self, f: Frame, exhibit: Exhibit, path: Path, x: int, y: int) -> int:
        """One exhibit — title, claim, the live subject, and its measured facts."""
        pad = int(f.st.pad)
        title = f.text(x + pad, y, str(exhibit.title), str(f.st.cool), f.font("sans", 1, "bold"))
        claim = f.text(
            x + pad, title[3] + 5, str(exhibit.claim), str(f.st.dim),
            f.font("sans", -1), width=CARD_W - 2 * pad,
        )
        sbox = draw_subject(f, exhibit[2], path + (2,), x + pad, claim[3] + max(6, pad // 2) + 2)
        yc = sbox[3] + max(6, pad // 2) + 2
        for words, ok in fact_lines(exhibit[2]):
            wbox = f.text(x + pad, yc, "· " + words + " ", str(f.st.dim), f.font("mono", -2))
            colour = str(f.st.green) if ok else str(f.st.red)
            f.text(wbox[2] + 4, yc, "— holds" if ok else "— fails", colour, f.font("mono", -2))
            yc = wbox[3] + 4
        f.cv.create_line(x, y, x, yc, fill=str(f.st.cool))
        return yc

    def draw_axiom(self, f: Frame, x: int, y: int) -> int:
        """IrSelf's portrait — not a card among the cards, but the ground they share."""
        pad = int(f.st.pad)
        nodes = list(walk(self.session))
        all_ir = all(isinstance(n, IrSelf) for n in nodes)
        t = f.text(x + pad, y, "IrSelf", str(f.st.ink), f.font("sans", 1, "bold"))
        f.text(
            t[2] + 10, y + 3, "— not one of the things above; what every one of them is",
            str(f.st.dim), f.font("sans", -1),
        )
        line = f"· census: {len(nodes)} nodes reachable from the session value · all isinstance IrSelf "
        wbox = f.text(x + pad, t[3] + 6, line, str(f.st.dim), f.font("mono", -2))
        colour = str(f.st.green) if all_ir else str(f.st.red)
        f.text(wbox[2] + 4, t[3] + 6, "— holds" if all_ir else "— fails", colour, f.font("mono", -2))
        b = f.text(
            x + pad, wbox[3] + 4,
            "its portrait is uniformity: the inspector asks any selection the same questions",
            str(f.st.dim), f.font("sans", -2), width=CARD_W - 2 * pad,
        )
        f.cv.create_line(x, y, x, b[3], fill=str(f.st.ink))
        return b[3]

    def draw_instrument(self, f: Frame, x: int, y: int) -> int:
        """The reflective panel — opsis's own configuration, drawn by the same table."""
        pad = int(f.st.pad)
        violet = str(f.st.violet)
        t = f.text(x + pad, y, "THE INSTRUMENT", violet, f.font("sans", 1, "bold"))
        sub = f.text(
            x + pad, t[3] + 5,
            "opsis, as a subject — its Style record drawn by the SAME table entry that drew "
            "the IrQuantifier at left, and retyped the same way",
            str(f.st.dim), f.font("sans", -1), width=PANEL_W - 2 * pad - 40,
        )
        sbox = draw_subject(f, self.session[0], (0,), x + pad, sub[3] + pad)
        g = int(self.session.generation)
        l1 = f.text(
            x + pad, sbox[3] + pad,
            f"generation {g} — every commit rebuilt the whole Session value",
            violet, f.font("mono", -2), width=PANEL_W - 2 * pad,
        )
        l2 = f.text(
            x + pad, l1[3] + 4,
            "frame = render(session) · modification is reconstruction — records are tuples; "
            "nothing on screen is patched",
            str(f.st.dim), f.font("sans", -2), width=PANEL_W - 2 * pad,
        )
        hint = f.text(
            x + pad, l2[3] + 6,
            "try: warm → #4fd1ff · pad → 22 · text → 15 — click the value, retype, Enter",
            str(f.st.warm), f.font("sans", -2), width=PANEL_W - 2 * pad,
        )
        f.cv.create_line(x, y, x, hint[3], fill=violet)
        return hint[3]

    def draw_inspector(self, f: Frame, x: int, y: int) -> int:
        """The selection, asked the same questions whatever it is — IrSelf made concrete."""
        pad = int(f.st.pad)
        t = f.text(x + pad, y, "SELECTION", str(f.st.cool), f.font("sans", 1, "bold"))
        yc = t[3] + 8
        if self.selection is None:
            b = f.text(
                x + pad, yc,
                "nothing selected — hover previews (dim halo), click selects (warm halo)",
                str(f.st.dim), f.font("sans", -1), width=INSPECT_W - 2 * pad,
            )
            f.cv.create_line(x, y, x, b[3], fill=str(f.st.cool))
            return b[3]
        node = node_at(self.session, self.selection)
        rows = [
            ("path", spell_path(self.session, self.selection)),
            ("type", type(node).__name__),
            ("mro", " → ".join(c.__name__ for c in type(node).__mro__[:4])),
            ("kind", kind_line(node)),
            ("value", detail_line(node)),
        ]
        for label, value in rows:
            lb = f.text(x + pad, yc, label, str(f.st.dim), f.font("sans", -2))
            vb = f.text(x + pad + 52, yc, value, str(f.st.ink), f.font("mono", -2), width=INSPECT_W - 2 * pad - 52)
            yc = max(lb[3], vb[3]) + 6
        if isinstance(node, (str, int)):
            e = f.text(
                x + pad, yc + 2, "editable — type to retype · Enter commits · Esc cancels",
                str(f.st.warm), f.font("sans", -2), width=INSPECT_W - 2 * pad,
            )
            yc = e[3]
        f.cv.create_line(x, y, x, yc, fill=str(f.st.cool))
        return yc

    def draw_status(self, f: Frame) -> None:
        """The bottom strip — the last outcome in its own words, and the frame census."""
        kind, words = self.note
        colours = {"green": str(f.st.green), "red": str(f.st.red), "dim": str(f.st.dim)}
        f.text(MARGIN, H - 36, words, colours[kind], f.font("sans", -1), width=1050)
        census = f"regions {len(f.hits)} · refusals {len(f.refusals)} · generation {int(self.session.generation)}"
        f.text(W - MARGIN, H - 36, census, str(f.st.dim), f.font("mono", -2), anchor="ne")

    # ── the hand ───────────────────────────────────────────────────────

    def hit_at(self, x: int, y: int) -> Path | None:
        """The topmost region under the pointer, if any."""
        for box, path in reversed(self.hits):
            if box[0] - 3 <= x <= box[2] + 3 and box[1] - 2 <= y <= box[3] + 2:
                return path
        return None

    def on_motion(self, event: "tk.Event[tk.Canvas]") -> None:
        """Hover tracking — redraw only when the hovered address changes."""
        hit = self.hit_at(event.x, event.y)
        if hit != self.hover:
            self.hover = hit
            self.redraw()

    def on_click(self, event: "tk.Event[tk.Canvas]") -> None:
        """Click selects an address; clicking elsewhere deselects."""
        hit = self.hit_at(event.x, event.y)
        if hit == self.selection:
            return
        self.selection = hit
        self.buffer = None
        self.redraw()

    def on_key(self, event: "tk.Event[tk.Tk]") -> None:
        """The whole keyboard contract: retype, commit, cancel."""
        if self.selection is None:
            return
        if event.keysym == "Return":
            self.commit()
        elif event.keysym == "Escape":
            self.buffer = None
            self.note = ("dim", "edit cancelled — the session value was never touched")
            self.redraw()
        elif event.keysym == "BackSpace":
            if self.ensure_buffer():
                self.buffer = (self.buffer or "")[:-1]
                self.redraw()
        elif event.char and event.char.isprintable():
            if self.ensure_buffer():
                self.buffer = (self.buffer or "") + event.char
                self.redraw()

    def ensure_buffer(self) -> bool:
        """Open an edit buffer on the selection, or refuse in words."""
        node = node_at(self.session, self.selection or ())
        if not isinstance(node, (str, int)):
            self.note = ("red", f"{type(node).__name__} is not retypeable — absence has one spelling")
            self.redraw()
            return False
        if self.buffer is None:
            self.buffer = str(node) if isinstance(node, str) else str(int(node))
        return True

    def reread(self, node: IrSelf | int | str, text: str) -> tuple[IrSelf | int | str | None, str | None]:
        """The buffer read back as the selected leaf's kind — or a refusal, in words."""
        sel = self.selection or ()
        if isinstance(node, str):
            if sel[:1] == (0,) and len(sel) == 2 and sel[1] < 8 and not HEX.fullmatch(text):
                return None, f"'{text}' does not spell a colour — Style.{Style._fields[sel[1]]} reads #rrggbb"
            return type(node)(text), None
        try:
            value = int(text)
        except ValueError:
            return None, f"'{text}' does not spell an integer — {type(node).__name__} carries an int payload"
        if sel == (0, 8) and not 4 <= value <= 60:
            return None, f"pad {value} is outside 4..60 — the instrument refuses to become unreadable"
        if sel == (0, 9) and not 7 <= value <= 32:
            return None, f"text {value} is outside 7..32 — the instrument refuses to become unreadable"
        return type(node)(value), None

    def commit(self) -> None:
        """Rebuild the session with the reread value — modification is reconstruction."""
        if self.selection is None or self.buffer is None:
            return
        node = node_at(self.session, self.selection)
        value, refusal = self.reread(node, self.buffer)
        if refusal is not None or value is None:
            self.note = ("red", refusal or "unreadable")
            self.redraw()
            return
        spelled = spell_path(self.session, self.selection)
        generation = IrInt(int(self.session.generation) + 1)
        rebuilt = set_at(self.session, self.selection, value)
        self.session = Session.ensure(set_at(rebuilt, (2,), generation), "commit: the rebuilt session")
        self.buffer = None
        self.note = (
            "green",
            f"generation {int(generation)} — {spelled} rebuilt · this whole frame is a render of the new value",
        )
        self.redraw()


def census(app: App) -> int:
    """One frame's counts, a scripted self-modification, and a scripted refusal."""
    regions, refusals = app.counts
    print(f"regions {regions} · refusals {refusals} (expected exactly 1)")
    app.selection = (0, 8)
    app.buffer = "22"
    app.commit()
    pad_ok = int(app.session.style.pad) == 22 and int(app.session.generation) == 1
    print(f"self-modification: style.pad → {int(app.session.style.pad)} · generation → {int(app.session.generation)}")
    app.buffer = "notanumber"
    app.commit()
    refusal_ok = app.note[0] == "red"
    print(f"refusal path: {app.note[1]!r}")
    ok = pad_ok and refusal_ok and refusals == 1 and regions > 0
    print("census ok" if ok else "census FAILED")
    return 0 if ok else 1


def shot(app: App, out: str) -> None:
    """The frame as a PNG — canvas postscript rendered through ghostscript."""
    app.root.update()
    ps_path = out + ".ps"
    app.cv.postscript(file=ps_path, colormode="color", width=W, height=H)
    subprocess.run(
        ["gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m", "-dEPSCrop",
         "-r120", f"-sOutputFile={out}", ps_path],
        check=True,
        capture_output=True,
    )
    print(f"wrote {out}")


def main() -> int:
    """Entry — live instrument by default; census and shot modes for verification."""
    root = tk.Tk()
    app = App(root)
    if "--shot" in sys.argv:
        shot(app, sys.argv[sys.argv.index("--shot") + 1])
    if "--census" in sys.argv:
        code = census(app)
        root.destroy()
        return code
    if "--shot" in sys.argv:
        root.destroy()
        return 0
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
