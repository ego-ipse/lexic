"""The road not taken, run in the background.

One parse, two observations. The product always comes from the engine's own
composition — there is no route flag anywhere near the parse — and the
instrument additionally runs the explicit Earley route to see whether both
engines built the same value. On this document that costs about two seconds
against the fifty milliseconds the real parse took, which is exactly why it
happens on a thread and why the strip says `running…` until it lands.

Pending is DRAWN, never blank: a strip that is empty while it thinks is
indistinguishable from a strip that has nothing to say.
"""

from __future__ import annotations

from threading import Thread

from kairos.parse import parity

from lexic.compile import CompiledGrammar

__all__ = ["Aside", "Routes"]


class Aside:
    """A sentence a facet's head carries, and a shorter way of saying it.

    A verdict cut off mid-phrase is worse than a short one: `both engines
    built the same value` clipped at `built the same` still reads as a
    finding, and clipped earlier it reads as its opposite. So the head is
    given both, and says the one that fits.
    """

    __slots__ = ("brief", "said", "tone")

    def __init__(self, said: str = "", brief: str = "", tone: str = "fsub") -> None:
        self.said = said
        self.brief = brief or said
        self.tone = tone


class Routes:
    """What the other engine made of this reading, once it has finished."""

    __slots__ = ("done", "generation", "seconds", "verdict", "words")

    def __init__(self) -> None:
        self.generation = -1
        self.done = False
        self.seconds = 0.0
        self.verdict = ""
        self.words = ""

    def ask(self, machine: CompiledGrammar | None, text: str, generation: int) -> None:
        """Start the other route for this reading, if it is not already running."""
        if machine is None or generation == self.generation:
            return
        self.generation = generation
        self.done = False
        self.seconds = 0.0
        self.verdict = ""
        self.words = ""
        Thread(target=self._run, args=(machine, text, generation), daemon=True).start()

    def _run(self, machine: CompiledGrammar, text: str, generation: int) -> None:
        """Run it. A result for a reading that has moved on is discarded."""
        seconds, verdict, words = parity(machine, text)
        if generation != self.generation:
            return
        self.seconds = seconds
        self.verdict = verdict
        self.words = words
        self.done = True

    def line(self) -> Aside:
        """What the strip says, long and short, and the tone it says it in."""
        if self.generation < 0:
            return Aside()
        if not self.done:
            return Aside("· route: the other engine is running…", "· route: running…")
        if self.verdict == "holds":
            return Aside(
                f"· route: Earley (explicit) {self.seconds:.2f}s · "
                "both engines built the same value — holds",
                f"· both engines agree — {self.seconds:.2f}s",
                "green",
            )
        if self.verdict == "failed":
            return Aside(
                f"· route: the other engine refused — {self.words}",
                "· the other engine REFUSED",
                "red",
            )
        return Aside(
            f"· route: the engines DISAGREE — {self.words}",
            "· the engines DISAGREE",
            "red",
        )
