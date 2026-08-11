"""The session — what the hand has done, and what each gesture means.

The state IS the policy: the same keys `scene` already reads (`form`,
`graph.view`, `chart.clock`, `arrange.shares`, `tab.<column>`, `top.<facet>`),
so a gesture changes the reading's presentation the way every other part of
the instrument already understands it.

A pixel becomes an offset here; a click becomes a cursor or a co-selection; a
key becomes a letter or a command depending on what has the hand. The leaf
posts what happened and never what it meant.

One open table per question — `SAYS` for what was done, `LANDED` for what a
click landed on, `KEYS` for a named key — so a new gesture is a method and a
row, never an edit through a cascade.
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping

from praxis.history import Retype, retype
from praxis.reading import Reading

__all__ = ["Session"]

# how many lines a wheel notch moves a plane
STEP = 3


class Session:
    """One reading, and how the hand is looking at it."""

    __slots__ = (
        "at",
        "body",
        "generation",
        "playing",
        "main",
        "reading",
        "said",
        "state",
        "typed",
    )

    def __init__(self, reading: Reading) -> None:
        self.reading = reading
        self.at = 0.0
        self.playing = False
        self.generation = 1
        # the session's own policy, and whichever layer is being written to
        self.main: dict[str, str] = {}
        self.state: MutableMapping[str, str] = self.main
        # what has been typed but not yet read, per plane, and the last
        # re-reading's answer — a refusal is a result, and it is shown
        self.typed: dict[str, str] = {}
        self.said: Retype | None = None
        self.body = ""

    # ── what the frame asks the session ──────────────────────────────────
    def spelling(self, which: str, held: str) -> str:
        """What a plane SHOWS — what was typed, which may be ahead of the read."""
        return self.typed.get(which, held)

    def stale(self, which: str) -> bool:
        """Whether that plane has been typed in since it was last read."""
        return which in self.typed

    def frontier(self) -> int:
        """Where the last re-reading stopped, or -1 when it did not stop."""
        return (
            self.said.pos
            if self.said is not None and self.said.state == "refused"
            else -1
        )

    # ── the gesture, applied ─────────────────────────────────────────────
    def gesture(
        self, said: str, body: str = "", into: MutableMapping[str, str] | None = None
    ) -> None:
        """One gesture, applied.

        :param body: whatever rode along after it — a plane's whole text, when
            what happened is that someone typed in it.
        :param into: where this gesture's POLICY goes. A window carries its own
            view, camera and scroll, so a gesture made in one writes to that
            window's own layer; a `ChainMap` over the session's means it still
            reads everything the session knows. The CURSOR is not policy — it
            lives on the subject and stays visible everywhere at once.
        """
        words = said.strip().replace("~", " ").split()
        if not words:
            return
        was = self.state
        self.state = self.main if into is None else into
        self.body = body
        try:
            work = SAYS.get(words[0])
            if work is not None:
                work(self, words[1:])
        finally:
            self.state = was

    def _do(self, words: list[str]) -> None:
        """A chip standing for a gesture carries the gesture it stands for."""
        self.gesture(" ".join(words))

    def _at(self, words: list[str]) -> None:
        """A click, on whatever the frame said was there."""
        if words:
            work = LANDED.get(words[0])
            if work is not None:
                work(self, words[1:])

    def _set(self, words: list[str]) -> None:
        """A select in a facet's head — policy, said in its own key.

        A control whose value is already what it says is a control that turns
        itself off: that is what makes ◉ focus a switch rather than a latch.
        """
        if len(words) < 2:
            return
        key, value = words[0], words[1]
        if key == "pin.span":
            # a pin remembers the reading it was made against, so it can say
            # later that the reading has moved on without it
            self.state[key] = value
            self.state.setdefault("pin.gen", str(self.generation))
            return
        if key.endswith(".focus"):
            self.state[key] = "off" if self.state.get(key, "off") == value else value
        else:
            self.state[key] = value

    # ── what a click landed on ───────────────────────────────────────────
    def _span(self, words: list[str]) -> None:
        """A span in the lanes or the spine — the cursor goes to where it starts."""
        if words and ":" in words[0]:
            self.at = float(words[0].split(":")[0])

    def _gutter(self, words: list[str]) -> None:
        """A line number sets the cursor to where that line starts."""
        if words and words[0].isdigit():
            lines = self.reading.text.split("\n")[: int(words[0])]
            self.at = float(sum(len(line) + 1 for line in lines))

    def _rule(self, words: list[str]) -> None:
        """A rule — CO-SELECTED. Its spans outline violet wherever they are.

        A rule is a what, not a when: choosing one does not move the cursor.
        Clicking it again lets it go.
        """
        if words:
            self.state["chosen"] = (
                "" if self.state.get("chosen") == words[0] else words[0]
            )

    def _tab(self, words: list[str]) -> None:
        """A tab in a t-node — which of the group's leaves that region shows.

        The chip carries the column and the index, because the frame is what
        knows the arrangement; nothing here reconstructs it.
        """
        if words and ":" in words[0]:
            column, _, index = words[0].partition(":")
            if index.isdigit():
                self.state[f"tab.{column}"] = index

    def _facet(self, words: list[str]) -> None:
        """A dock chip — that facet's presence, toggled."""
        if not words:
            return
        key = f"facet.{words[0]}"
        self.state[key] = "off" if self.state.get(key, "on") == "on" else "on"

    def _strata(self, words: list[str]) -> None:
        """Pull back to the whole climb, or come back down into the reading."""
        self.main["showing"] = "" if (words and words[0] == "off") else "strata"
        self.main["place"] = ""

    def _rung(self, words: list[str]) -> None:
        """Travel to a rung of the ladder — and come back into the reading."""
        self.main["showing"] = ""

    def _place(self, words: list[str]) -> None:
        """Enter a room the reading holds — or leave the one you are in."""
        self.main["place"] = words[0] if words else ""
        self.main["showing"] = ""

    def _rail(self, words: list[str]) -> None:
        """▤ rail — show this rule as the track it describes, and go to it."""
        if not words:
            return
        self.state["graph.view"] = "rails"
        self.state["top.rails"] = f"rule:{words[0]}"
        self.state["tab.reader"] = "1"

    def _sel(self, words: list[str]) -> None:
        """Text selected in a plane — the smallest covering occurrence co-selects."""
        if len(words) < 3 or words[0] != "document":
            return
        a, b = int(words[1]), int(words[2])
        self.at = float(a)
        # where the hand is, so the chip can be raised there
        self.state["sel"] = f"{a}:{b}" if b > a else ""
        covering = [
            span
            for span in self.reading.spans
            if span.start <= a and span.end >= max(b, a + 1)
        ]
        if covering:
            tightest = min(covering, key=lambda span: span.end - span.start)
            self.state["chosen"] = tightest.rule

    # ── typing, and reading again ────────────────────────────────────────
    def _text(self, words: list[str]) -> None:
        """A plane's text as it now stands — the browser did the typing."""
        if words:
            self.typed[words[0]] = self.body

    def _key(self, words: list[str]) -> None:
        """A named key. What it means depends on whether a plane has the hand."""
        if words:
            work = KEYS.get(words[0])
            if work is not None:
                work(self, [])

    def _reread(self, _words: list[str]) -> None:
        """Read what has been typed, without saving. An edit is a RE-READING."""
        typed = self.typed.get("document")
        if typed is None:
            return
        self.said = retype(self.reading, 0, len(self.reading.text), typed)
        if self.said.state != "refused":
            self.typed.pop("document", None)
            self.generation += 1
            self.at = min(self.at, float(len(self.reading.text)))

    def _save(self, _words: list[str]) -> None:
        """Read it again, and — if it read — write it to the document's own file."""
        self._reread([])
        if self.said is not None and self.said.state != "refused":
            self.reading.document.write_text(self.reading.text)

    def _revert(self, _words: list[str]) -> None:
        """Back to the last good reading; the typing since then goes with it."""
        self.typed.clear()
        self.said = None

    # ── looking around ───────────────────────────────────────────────────
    def _scroll(self, words: list[str]) -> None:
        if len(words) < 2 or not words[1].lstrip("-").isdigit():
            return
        was = self.state.get(f"top.{words[0]}", "0")
        now = max(0, (int(was) if was.isdigit() else 0) + int(words[1]) * STEP)
        self.state[f"top.{words[0]}"] = str(now)

    def _scrolled(self, words: list[str]) -> None:
        """A real text plane scrolled itself; the drawing under it must follow."""
        if len(words) >= 2 and words[1].lstrip("-").isdigit():
            self.state[f"top.{words[0]}"] = str(max(0, int(words[1])))

    def _zoom(self, words: list[str]) -> None:
        """Ctrl+wheel — a plane's own scale, on the key the policy already has.

        A stack of diagrams reads like a document: the wheel scrolls it and
        Ctrl+wheel zooms it, which is the same pair the text planes use.
        """
        if len(words) < 2 or not words[1].lstrip("-").isdigit():
            return
        key = {
            "document": "doc.zoom",
            "chart": "chart.zoom",
            "spine": "spine.zoom",
        }.get(words[0], f"{words[0]}.zoom")
        was = float(self.state.get(key, "1"))
        self.state[key] = (
            f"{max(0.35, min(3.0, was * (1.1 if int(words[1]) < 0 else 0.9))):.3f}"
        )

    def _spin(self, words: list[str]) -> None:
        """The graph, turned — the same rates the leaf's drag used."""
        if len(words) < 2:
            return
        yaw = float(self.state.get("graph.yaw", "0.42")) + float(words[0]) * 0.006
        pitch = float(self.state.get("graph.pitch", "0.92")) + float(words[1]) * 0.005
        self.state["graph.yaw"] = f"{yaw:.3f}"
        self.state["graph.pitch"] = f"{max(-1.4, min(1.4, pitch)):.3f}"

    def _seam(self, words: list[str]) -> None:
        """A seam moved: its number is the split it stands for, in tree order."""
        if len(words) < 2:
            return
        at, share = int(words[0]), max(0.08, min(0.92, float(words[1])))
        shares = self.state.get("arrange.shares", "").split()
        while len(shares) <= at:
            shares.append("0")
        shares[at] = f"{share:.3f}"
        self.state["arrange.shares"] = " ".join(shares)

    def _step(self, words: list[str]) -> None:
        by = float(words[0]) if words and words[0].lstrip("-").isdigit() else 1.0
        self.at = max(0.0, min(self.at + by, float(len(self.reading.text))))

    def _go(self, words: list[str]) -> None:
        length = len(self.reading.text)
        where = words[0] if words else "0"
        self.at = float(
            length if where == "end" else (int(where) if where.isdigit() else 0)
        )

    def _back(self, _words: list[str]) -> None:
        """← — one character back through the reading."""
        self._step(["-1"])

    def _forward(self, _words: list[str]) -> None:
        self._step(["1"])

    def _home(self, _words: list[str]) -> None:
        self._go(["0"])

    def _end(self, _words: list[str]) -> None:
        self._go(["end"])

    def _play(self, _words: list[str]) -> None:
        self.playing = not self.playing

    def _speed(self, words: list[str]) -> None:
        was = float(self.state.get("speed", "1"))
        self.state["speed"] = (
            f"{max(0.25, min(8.0, was * (2 if words and words[0] == '+' else 0.5))):g}"
        )

    def _tick(self, _words: list[str]) -> None:
        if not self.playing:
            return
        length = len(self.reading.text)
        self.at = min(
            self.at + length / 90 * float(self.state.get("speed", "1")), length
        )
        self.playing = self.at < length


Said = Callable[["Session", list[str]], None]

# what the hand did
SAYS: dict[str, Said] = {
    "at": Session._at,
    "do": Session._do,
    "go": Session._go,
    "key": Session._key,
    "play": Session._play,
    "scroll": Session._scroll,
    "scrolled": Session._scrolled,
    "seam": Session._seam,
    "sel": Session._sel,
    "set": Session._set,
    "speed": Session._speed,
    "spin": Session._spin,
    "step": Session._step,
    "text": Session._text,
    "tick": Session._tick,
    "zoom": Session._zoom,
}

# what it landed on
LANDED: dict[str, Said] = {
    "facet": Session._facet,
    "gutter": Session._gutter,
    "place": Session._place,
    "rail": Session._rail,
    "rung": Session._rung,
    "strata": Session._strata,
    "rule": Session._rule,
    "span": Session._span,
    "tab": Session._tab,
}

# and which key is which
KEYS: dict[str, Said] = {
    "ArrowLeft": Session._back,
    "ArrowRight": Session._forward,
    "Ctrl+Enter": Session._reread,
    "Ctrl+s": Session._save,
    "End": Session._end,
    "Escape": Session._revert,
    "Home": Session._home,
    "Space": Session._play,
}
