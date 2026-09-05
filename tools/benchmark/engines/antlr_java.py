"""ANTLR's JAVA target, held in one live JVM for the whole benchmark.

`antlr4-python3-runtime` is a pure-Python ATN simulator; ANTLR's Java target is
a different animal, and it is the one people mean by "ANTLR". Benchmarking the
Python binding and calling that row `antlr` would name the tool for its slowest
port, so the Java target gets the row and the Python one is labelled for what it
is.

Measuring it without giving up the methodology is the whole design. A subprocess
timed from Python would be a cross-process comparison, which has misled this
benchmark before. Instead one JVM stays alive, Python sends it a framed input
per round, and it replies with the nanoseconds `System.nanoTime()` measured
around the parse — so the Java column interleaves with the Python ones exactly
as they interleave with each other, and neither JVM startup nor the pipe is
inside any number.

JIT warmup is not a round. :meth:`JavaAntlr.warm` parses a fixed budget large
enough to clear the JIT's last step down, then reports whether the tail held
still — because this JVM steps between long flat levels, and a warmup that
stops at the first stable-looking one publishes whichever level it landed on.
"""

from __future__ import annotations

import statistics
import subprocess
from contextlib import ExitStack
from pathlib import Path

from lexic.ir import IrAst
from tools.benchmark.emitters.directives import NO_MARKS, Marks
from tools.benchmark.engines.antlr_build import TOOL_VERSION, generate

_JAR = Path.home() / f".m2/repository/org/antlr/antlr4/{TOOL_VERSION}"
"""Where `antlr4-tools` leaves the jar it fetched — it carries the Java runtime."""

WARM_BATCH = 12
"""Parses per warmup batch; the median of a batch is what must settle."""

WARM_BUDGET = 60
"""Batches always parsed before the seat is read — 720 parses.

A FIXED budget, not a search for the earliest stable point, and that is the
whole correction. This JVM does not descend smoothly to a floor: it holds a
level flat for 10 to 25 batches, steps to roughly half it, and holds again,
with the last step landing between batch 40 and batch 75 depending on the
grammar. Any "has it stopped moving" test therefore certifies whichever step
the run is standing on when its counter runs out, and which step that is comes
down to where the counter happened to expire — measured across seven processes
on seven grammars, that put a 1.9x to 2.4x spread on every published figure.
Sixty batches clears the last step on every grammar measured, so the processes
agree instead.
"""

WARM_CONFIRM = 10
"""Batches median-compared at each end of the budget's tail to call it settled."""

WARM_STABLE = 0.03
"""Relative move between the tail's two halves that still counts as settled."""


def _classpath(classes: str) -> str:
    """The ANTLR runtime jar plus this grammar's compiled classes."""
    jar = _JAR / f"antlr4-{TOOL_VERSION}-complete.jar"
    if not jar.exists():
        raise RuntimeError(f"no ANTLR jar at {jar}")
    return f"{jar}:{classes}"


def _build(ast: IrAst, name: str, marks: Marks = NO_MARKS) -> Path:
    """Generate the Java parser, compile it with the driver, return the class dir.

    :raises RuntimeError: When the ANTLR tool or `javac` refuses — a capability
        result about the toolchain, reported rather than worked around.
    """
    target = generate(ast, name, "Java", marks)
    driver = Path(__file__).with_name("Driver.java")
    sources = sorted(str(path) for path in target.glob("*.java")) + [str(driver)]
    done = subprocess.run(
        [
            "javac",
            "-nowarn",
            "-cp",
            _classpath(str(target)),
            "-d",
            str(target),
            *sources,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(f"javac: {done.stderr.strip().splitlines()[0]}")
    return target


class JavaAntlr:
    """A live JVM parsing on the Java target, one framed round per call.

    Calling the instance parses and returns what it built; the parse's own
    nanosecond reading stays on the instance for :meth:`measured_us`, which is
    what the benchmark records. Whatever the pipe costs is therefore outside the
    number, as JVM startup and the `javac` build are.

    :ivar warmed: Parses spent reaching a stable median, and whether it settled.
    """

    def __init__(self, ast: IrAst, name: str, marks: Marks = NO_MARKS) -> None:
        """Build the parser, start the JVM, and leave it waiting on stdin.

        The JVM must outlive this call — that is the whole design — so it is
        owned by an `ExitStack` on the instance rather than a `with` block, and
        :meth:`close` unwinds it.
        """
        target = _build(ast, name, marks)
        self._owned = ExitStack()
        self._proc = self._owned.enter_context(
            subprocess.Popen(
                ["java", "-cp", _classpath(str(target)), "Driver", name],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        )
        self._parse_ns = 0.0
        self._stream_ns = 0.0
        self.cold_us_per_char: float | None = None
        self.warmed: tuple[int, bool] = (0, False)

    def __call__(self, text: str) -> object:
        """Parse ``text`` whole in the JVM, raising on any syntax error."""
        body = text.encode("utf-8")
        stdin, stdout = self._proc.stdin, self._proc.stdout
        if stdin is None or stdout is None:
            raise RuntimeError("JVM pipes are closed")
        stdin.write(f"{len(body)}\n".encode("ascii") + body)
        stdin.flush()
        reply = stdout.readline().decode("utf-8").strip()
        if not reply:
            raise RuntimeError(f"JVM died — {self._stderr()}")
        if reply.startswith("ERR "):
            raise SyntaxError(reply[4:])
        _ok, parse_ns, stream_ns = reply.split()
        self._parse_ns, self._stream_ns = float(parse_ns), float(stream_ns)
        if self.cold_us_per_char is None:
            self.cold_us_per_char = self.measured_us() / max(len(text), 1)
        return "ParserRuleContext"

    def measured_us(self) -> float:
        """Microseconds the JVM itself measured for the last parse."""
        return self._parse_ns / 1e3

    def charstream_share(self) -> float:
        """Fraction of the last parse spent building the input CharStream.

        ANTLR takes a `CharStream`, not a `str`, so a decode-and-copy of the
        whole input is per-parse work no other engine here pays. It is inside
        the number — a user pays it — and this says how much of it that is.
        """
        return self._stream_ns / max(self._parse_ns, 1.0)

    def warm(self, corpus: str) -> tuple[int, bool]:
        """Parse a fixed budget, then say whether the tail actually held still.

        Stability is CHECKED here, never searched for — see :data:`WARM_BUDGET`
        for why searching cannot work against a JIT that steps between long
        flat levels. The check compares the median of the last
        :data:`WARM_CONFIRM` batches against the median of the
        :data:`WARM_CONFIRM` before them; medians rather than a spread because
        this JVM throws single slow batches — a deoptimisation, a collection —
        that say nothing about the level the run has reached.

        :param corpus: The document to warm on — the one that will be timed.
        :returns: ``(parses spent, whether the tail held still)`` — an unsettled
            warmup is reported, never silently accepted as if it had converged.
        """
        medians = []
        for _ in range(WARM_BUDGET):
            times = sorted(self._sample(corpus) for _ in range(WARM_BATCH))
            medians.append(times[len(times) // 2])
        late = statistics.median(medians[-WARM_CONFIRM:])
        early = statistics.median(medians[-2 * WARM_CONFIRM : -WARM_CONFIRM])
        settled = abs(late - early) / max(late, early, 1e-9) < WARM_STABLE
        self.warmed = (WARM_BUDGET * WARM_BATCH, settled)
        return self.warmed

    def _sample(self, corpus: str) -> float:
        """One parse, reported as the microseconds the JVM measured."""
        self(corpus)
        return self.measured_us()

    def _stderr(self) -> str:
        """Whatever the JVM said on its way out, as one line."""
        stream = self._proc.stderr
        return "" if stream is None else " ".join(stream.read().decode().split())[:120]

    def close(self) -> None:
        """Send the quit frame, wait for the JVM to exit, release its pipes."""
        if self._proc.poll() is None and self._proc.stdin is not None:
            self._proc.stdin.write(b"-1\n")
            self._proc.stdin.flush()
            self._proc.wait(timeout=10)
        self._owned.close()


def java_antlr_parser(ast: IrAst, name: str, marks: Marks = NO_MARKS) -> JavaAntlr:
    """A live Java-target ANTLR parser for ``ast``, its JVM running.

    The JIT settles separately, through :meth:`JavaAntlr.warm`, because warmup
    belongs to the timing loop and not to building a parser.

    :param ast: The one canonical grammar, as for every other competitor.
    :param name: A Java-identifier grammar name; also the class prefix.
    :returns: The parser, ready to take a round.
    :raises RuntimeError: When the toolchain refuses the grammar.
    """
    return JavaAntlr(ast, name, marks)
