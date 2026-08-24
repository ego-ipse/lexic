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

JIT warmup is not a round. :meth:`JavaAntlr.warm` parses until the median stops
moving and reports how many parses that took, because a fixed count nobody
checked is how an unwarmed JVM gets published as a slow engine.
"""

from __future__ import annotations

import subprocess
from contextlib import ExitStack
from pathlib import Path

from lexic.ir import IrAst
from tools.benchmark.antlr_build import TOOL_VERSION, generate
from tools.benchmark.directives import NO_MARKS, Marks

_JAR = Path.home() / f".m2/repository/org/antlr/antlr4/{TOOL_VERSION}"
"""Where `antlr4-tools` leaves the jar it fetched — it carries the Java runtime."""

WARM_BATCH = 12
"""Parses per warmup batch; the median of a batch is what must settle."""

WARM_SETTLED = 3
"""Consecutive stable batches required before the JIT is called settled. One
was not enough — a C1 plateau reads as convergence while C2 still compiles."""

WARM_STABLE = 0.03
"""Relative move between consecutive batch medians that counts as warm."""

WARM_LIMIT = 40
"""Batches before warmup gives up and reports what it reached."""


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
        """Parse until the median stops moving; record and return the cost.

        Stability must hold for :data:`WARM_SETTLED` CONSECUTIVE batches. One
        batch is not enough against a tiered JIT: HotSpot plateaus at C1 while
        C2 is still compiling, and that plateau passed a single-window test.
        Measured on the json row, six processes read 0.297 / 0.254 / 0.253 /
        0.140 / 0.247 / 0.221 µs/char — a 2.1x spread in which the ONE fast
        reading was also the one that happened to warm 192 parses instead of
        72. The row was bimodal because the warmup was, so every antlr
        comparison carried an unstated error bar.

        :returns: ``(parses spent, whether it settled)`` — an unsettled warmup is
            reported, never silently accepted as if it had converged.
        """
        previous, stable = 0.0, 0
        for batch in range(1, WARM_LIMIT + 1):
            times = sorted(self._sample(corpus) for _ in range(WARM_BATCH))
            median = times[len(times) // 2]
            moved = abs(median - previous) / max(median, previous, 1e-9)
            stable = stable + 1 if previous and moved < WARM_STABLE else 0
            if stable >= WARM_SETTLED:
                self.warmed = (batch * WARM_BATCH, True)
                return self.warmed
            previous = median
        self.warmed = (WARM_LIMIT * WARM_BATCH, False)
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
