"""What would a TYPED frame cost, or save?

The frame is a nine-slot heterogeneous positional record spelled `list[Any]`,
and the `Carry` bullet's sink table cannot be typed while it is read out of one
— `list` is invariant, so a typed local cannot reach through it without a cast
or a paid-path call. The alternative is a frame that is a slotted OBJECT, and
the bullet says nothing frame-shaped lands without a measurement.

Measuring it by rewriting the kernel would be a day of throwaway edits across
six modules for a number that two populations and one price already decide. So
this asks the question the way §7's arithmetic asks it:

1. **Population**, untimed: how many frames does a real parse push, and how
   many item steps does each frame live through? Counted from the live kernel
   over real documents, per grammar, with an attempt-heavy grammar among them.
2. **Price**, timed: what does ONE frame's whole lifecycle cost in each
   representation — construct, N item steps of the reads and writes the driver
   actually performs, then the completion's read of every slot? The two are
   swapped in one process, alternating, minimum of R rounds. Neither arm
   carries the other's machinery, so this is the toggleable case the protocol
   allows in-process.
3. **The verdict**: price × population, against the parse time of the same
   documents, measured here so the percentage is not borrowed.

A representation is worth changing when the product of those is bigger than
the control floor. Anything smaller is a day spent to move noise.

    --plan   populations only; nothing timed
    (none)   populations, prices, and the predicted whole-parse delta

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import argparse
import gc
import random
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple

from lexic.compile import compile_from_path
from lexic.compile.artifact import CompiledGrammar
from lexic.generate import generate
from lexic.parsing import ProductExecutor
from lexic.parsing.caches import reset_caches
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.pda.compiler.program.flatten import FlatArm
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.build import (
    F_ARM,
    F_CLONE,
    F_COUNT,
    F_ENDS,
    F_I,
    F_MODE,
    F_OUT,
    F_SINKS,
    F_START,
)
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.products import _model_product, reset_product_cache

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
SEEDS = tuple(range(200))
TARGET_CHARS = 20_000
ROUNDS = 7
LIFECYCLES = 200_000

type Lifecycle = Callable[[int, list[int]], int]
"""One frame's whole life, in one representation — what the price compares."""

WITNESSES = ("c.gbnf", "vyx.gbnf", "json.gbnf", "chess.gbnf")
"""At least three ground-truth grammars, including the attempt-heavy one.
``vyx`` is that one: its analysis leaves attempt clones the others do not
have, so a frame cost that only shows up under rollback shows up there."""


class Population(NamedTuple):
    """What one grammar's parse does with frames.

    :ivar name: The grammar.
    :ivar chars: Characters parsed.
    :ivar frames: Frames pushed.
    :ivar steps: Item steps those frames lived through, in total.
    :ivar seconds: What the parse itself cost.
    """

    name: str
    chars: int
    frames: int
    steps: int
    seconds: float

    @property
    def per_char(self) -> float:
        """Frames pushed per character of input."""
        return self.frames / max(self.chars, 1)

    @property
    def steps_each(self) -> float:
        """Item steps per frame."""
        return self.steps / max(self.frames, 1)


class Frame:
    """The typed alternative — the same nine slots, named and declared.

    Written out rather than generated so the comparison is against a real
    record with real attribute access, not against a stand-in.
    """

    __slots__ = ("arm", "i", "count", "out", "mode", "clone", "start", "ends", "sinks")

    def __init__(
        self,
        arm: object,
        out: object,
        mode: int,
        clone: object,
        start: int,
        ends: list[int],
    ) -> None:
        """Push one frame — the constructor the kernel's list literal replaces."""
        self.arm = arm
        self.i = 0
        self.count = 0
        self.out = out
        self.mode = mode
        self.clone = clone
        self.start = start
        self.ends = ends
        self.sinks: object = None


class CountingKernel[M](PdaKernel[M]):
    """The live kernel, counting the frames it pushes and their item widths.

    A subclass rather than an instrumented copy: the numbers must describe the
    kernel that ships, and a copy is a second thing that can drift from it.
    """

    def __init__(
        self, tables: PdaTables, text: str, executor: ProductExecutor[M] | None = None
    ) -> None:
        """Run the real constructor, then swap in a counting stack."""
        super().__init__(tables, text, executor)
        self.stack = _CountingStack(self.stack)


class _CountingStack(list):
    """The kernel's own stack, counting pushes and the arm widths pushed."""

    def __init__(self, initial: list) -> None:
        """Adopt whatever the kernel had already put on the stack."""
        super().__init__(initial)
        self.pushed = 0
        self.width = 0

    def append(self, frame: object) -> None:
        """Count one frame and the number of items it will step through."""
        self.pushed += 1
        if isinstance(frame, list):
            arm = frame[F_ARM]
            if isinstance(arm, FlatArm):
                self.width += arm.n
        super().append(frame)


class Defect(AssertionError):
    """A claim this harness makes that the tree does not support."""


def _check(claim: str, held: bool) -> None:
    """Refuse the harness the moment one claim stops holding."""
    if not held:
        raise Defect(f"s4 frame a/b: {claim}")


def _cold() -> None:
    """Drop every memo, so the next compile is a real one."""
    reset_product_cache()
    reset_caches()


def _workload(compiled: CompiledGrammar, tables: PdaTables) -> list[str]:
    """One round's documents, grown the way the gate harness grows them."""
    ast = compiled.grammar
    rules = {str(rule.name): rule for rule in ast.rules}
    units: list[str] = []
    for seed in SEEDS:
        text = generate(str(ast.start), rules, rng=random.Random(seed))
        if text and _parses(tables, compiled, text):
            units.append(text)
    _check("the generator produced no parsable document", bool(units))
    joined = "".join(units)
    if _parses(tables, compiled, joined):
        grown = joined * max(1, TARGET_CHARS // len(joined))
        return [grown] if _parses(tables, compiled, grown) else [joined]
    total = sum(len(unit) for unit in units)
    return units * max(1, TARGET_CHARS // total)


def _parses(tables: PdaTables, compiled: CompiledGrammar, text: str) -> bool:
    """Whether the predictive engine alone claims this document."""
    try:
        PdaKernel(tables, text, compiled.executor).run()
    except PdaFail:
        return False
    return True


def _population(name: str, timed: bool) -> Population:
    """One grammar's frame population, and what its parse costs."""
    _cold()
    compiled = compile_from_path(GROUND_TRUTH / name)
    product = _model_product(
        compiled.codegen_grammar, compiled.product, tier_for(TARGET_CHARS)
    )
    work = _workload(compiled, product.pda)
    chars = sum(len(text) for text in work)
    frames = steps = 0
    for text in work:
        kernel = CountingKernel(product.pda, text, compiled.executor)
        kernel.run()
        stack = kernel.stack
        assert isinstance(stack, _CountingStack)
        frames += stack.pushed
        steps += stack.width
    seconds = _parse_seconds(product.pda, compiled, work) if timed else 0.0
    return Population(name, chars, frames, steps, seconds)


def _parse_seconds(
    tables: PdaTables, compiled: CompiledGrammar, work: list[str]
) -> float:
    """The lowest process time of one round of the same documents."""
    executor = compiled.executor
    best = float("inf")
    for _round in range(ROUNDS):
        gc.disable()
        started = time.process_time()
        try:
            for text in work:
                PdaKernel(tables, text, executor).run()
        finally:
            best = min(best, time.process_time() - started)
            gc.enable()
        gc.collect()
    return best


def _list_lifecycle(steps: int, ends: list[int]) -> int:
    """One frame's whole life as the kernel lives it today, on a list.

    Construct, then per item step read the arm, the index and the count, write
    the index, the count and one end — then read every slot at completion. The
    access mix is the driver's, not an invented one.
    """
    frame = [None, 0, 0, None, 3, None, 0, ends, None]
    total = 0
    for step in range(steps):
        total += 1 if frame[F_ARM] is None else 0
        i = frame[F_I]
        frame[F_COUNT] = frame[F_COUNT] + 1
        frame[F_I] = i + 1
        frame[F_ENDS][step % len(ends)] = step
    return (
        total
        + frame[F_I]
        + frame[F_COUNT]
        + frame[F_MODE]
        + frame[F_START]
        + (0 if frame[F_OUT] is None else 1)
        + (0 if frame[F_CLONE] is None else 1)
        + (0 if frame[F_SINKS] is None else 1)
    )


def _object_lifecycle(steps: int, ends: list[int]) -> int:
    """The same life on the typed record — same operations, named slots."""
    frame = Frame(None, None, 3, None, 0, ends)
    total = 0
    for step in range(steps):
        total += 1 if frame.arm is None else 0
        i = frame.i
        frame.count = frame.count + 1
        frame.i = i + 1
        frame.ends[step % len(ends)] = step
    return (
        total
        + frame.i
        + frame.count
        + frame.mode
        + frame.start
        + (0 if frame.out is None else 1)
        + (0 if frame.clone is None else 1)
        + (0 if frame.sinks is None else 1)
    )


def _price(lifecycle: Lifecycle, steps: int) -> float:
    """The lowest process time of ``LIFECYCLES`` frame lifetimes."""
    ends = [0] * max(steps, 1)
    best = float("inf")
    for _round in range(3):
        gc.disable()
        started = time.process_time()
        try:
            for _each in range(LIFECYCLES):
                lifecycle(steps, ends)
        finally:
            best = min(best, time.process_time() - started)
            gc.enable()
        gc.collect()
    return best


def main(arguments: Sequence[str] | None = None) -> None:
    """Report the populations, and — unless ``--plan`` — the price and verdict."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    options = parser.parse_args(arguments)
    timed = not options.plan
    populations = [_population(name, timed) for name in WITNESSES]
    print(
        f"{'grammar':<14}{'chars':>8}{'frames':>9}{'/char':>8}"
        f"{'steps/frame':>13}{'parse s':>10}"
    )
    for row in populations:
        print(
            f"{row.name:<14}{row.chars:>8}{row.frames:>9}{row.per_char:>8.3f}"
            f"{row.steps_each:>13.2f}{row.seconds:>10.6f}"
        )
    if not timed:
        print("\ns4 frame a/b\tplan only, nothing timed")
        return
    steps = max(1, round(sum(r.steps_each for r in populations) / len(populations)))
    as_list = _price(_list_lifecycle, steps)
    as_object = _price(_object_lifecycle, steps)
    delta = (as_object - as_list) / LIFECYCLES
    print(
        f"\nprice\t{steps} steps/frame\tlist {as_list:.6f}s\tobject "
        f"{as_object:.6f}s\t{1e9 * delta:+.1f} ns per frame"
    )
    print(f"\n{'grammar':<14}{'frames':>9}{'predicted':>12}{'of parse':>10}")
    for row in populations:
        predicted = delta * row.frames
        print(
            f"{row.name:<14}{row.frames:>9}{1e3 * predicted:>11.3f}ms"
            f"{100.0 * predicted / row.seconds:>9.2f}%"
        )
    print(
        "\ns4 frame a/b\tdone\tprice is toggleable and in-process; the population "
        "is the live kernel's own count"
    )


if __name__ == "__main__":
    main()
