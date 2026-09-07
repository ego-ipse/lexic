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

Two things make that reading reproducible, and they are separate. :meth:`warm`
parses a fixed budget large enough to clear the JIT's last step down, because
this JVM steps between long flat levels and a warmup that stops at the first
stable-looking one publishes whichever level it landed on. Then every reading
is the median of a back-to-back BURST, because the JVM also decays while the
harness is between rounds, and one parse taken after that pause is a
resumption cost rather than a parse cost. Both are stated budgets, and what
they buy is reproducibility — see :data:`SETTLE_BURST` for what they do not.
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

DRIVER = Path(__file__).with_name("Driver.java")
"""The long-lived JVM's source, compiled beside every generated parser."""

WARM_BATCH = 12
"""Parses per warmup batch; the median of a batch is what must settle."""

WARM_BUDGET = 200
"""Batches always parsed before the seat is read — 2400 parses.

A FIXED budget, not a search for the earliest stable point. This JVM does not
descend smoothly to a floor: it holds a level flat, steps to roughly half it,
and holds again, so any "has it stopped moving" test certifies whichever step
the run is standing on when its counter runs out.

The budget is set from the per-batch trajectory, traced over 400 batches in
three processes on every grammar. The steps are reproducible in POSITION, not
just in size, and the last one lands late: five of the twelve grammars step
between batch 60 and batch 150, and one of those steps again around 250. A
budget of 60 therefore published a figure 2.0x to 2.9x above the settled level
on `json`, `gbnf-meta`, `nested`, `backtrack` and `mixedends` — not a spread,
a systematic overstatement of ANTLR's cost. Two hundred clears every step
observed, and the tail check below then agrees with what the processes do.
"""

WARM_CONFIRM = 10
"""Batches median-compared at each end of the budget's tail to call it settled."""

WARM_STABLE = 0.03
"""Relative move between the tail's two halves that still counts as settled."""

SETTLE_BURST = 24
"""Parses run back-to-back for ONE reading; their median is the number.

This JVM decays when it is left idle. A pause of a few tens of milliseconds —
which is what the harness's own between-round work costs a process holding
compiled grammars — leaves the next parse running some 13% slow, and it
recovers gradually over the following dozen with no sharp settled point. A
reading taken from one parse after that pause is therefore a resumption cost,
and which resumption it caught moved the published figure by 1.07x to 1.77x
between processes measuring the same grammar. Every Python row is flat under
the same treatment, so this is the JVM's property and the correction belongs
here rather than in the sampler.

What a burst buys is REPRODUCIBILITY, not truth: the figure it publishes is
what this parser costs parsing back-to-back, which is the most generous state
ANTLR has and not what a caller parsing one document occasionally would see.
"""


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
    sources = sorted(str(path) for path in target.glob("*.java")) + [str(DRIVER)]
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
        """Parse ``text``, reading the median of a back-to-back settling burst.

        The burst is what makes the reading reproducible across processes; see
        :data:`SETTLE_BURST` for what it does and does not buy. A refusal
        raises out of the first parse, so a rejected input costs one.
        """
        readings = [self.round(text) for _ in range(SETTLE_BURST)]
        self._parse_ns = statistics.median(spent for spent, _ in readings)
        self._stream_ns = statistics.median(stream for _, stream in readings)
        return "ParserRuleContext"

    def round(self, text: str) -> tuple[float, float]:
        """One parse in the JVM, as its own ``(parse ns, CharStream ns)``.

        Returns the reading rather than posting it, so a burst can reduce a
        list of them and nothing has to reach into the seat to see one.

        :param text: The whole input to parse.
        :returns: The nanoseconds the JVM measured, and the share of them
            spent building the CharStream.
        :raises SyntaxError: When the parser refuses the input.
        """
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
        spent = float(parse_ns)
        if self.cold_us_per_char is None:
            self.cold_us_per_char = spent / 1e3 / max(len(text), 1)
        return spent, float(stream_ns)

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

        Warming runs single rounds, never the reading burst: the budget counts
        parses, and warming through the burst would multiply the number it
        reports by :data:`SETTLE_BURST` without changing what it certifies.

        :param corpus: The document to warm on — the one that will be timed.
        :returns: ``(parses spent, whether the tail held still)`` — an unsettled
            warmup is reported, never silently accepted as if it had converged.
        """
        medians = []
        for _ in range(WARM_BUDGET):
            times = sorted(self.round(corpus)[0] for _ in range(WARM_BATCH))
            medians.append(times[len(times) // 2])
        late = statistics.median(medians[-WARM_CONFIRM:])
        early = statistics.median(medians[-2 * WARM_CONFIRM : -WARM_CONFIRM])
        settled = abs(late - early) / max(late, early, 1e-9) < WARM_STABLE
        self.warmed = (WARM_BUDGET * WARM_BATCH, settled)
        return self.warmed

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
