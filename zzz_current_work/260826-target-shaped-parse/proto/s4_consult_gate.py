"""What does the proved consult cost, and what does it buy, per grammar?

The gate rows the value-string bullet is decided on. Two arms of ONE process,
alternating, minimum of R rounds, `time.process_time()`: the toggle is
compile-time (`_consults` returns an empty map for the second arm), so both
arms run byte-identical runtime code and the swap sees the consult's own
benefit and nothing else.

That is deliberate, and it is also the protocol's own warning: an in-process
swap cannot see the cost of machinery both arms carry. The one piece of
machinery the consult adds to a paid function — the third branch in
`run_span_once` — is therefore measured SEPARATELY, in `--micro`, against a
transcription of that function's body at the starting commit, on a clone of
each pre-existing arm kind.

Grammars that install no consult are the control rows: the change cannot reach
them, so whatever their delta reads is the noise floor of this harness, and no
consult-carrying row means anything unless it stands outside that floor.

The token-segmented row is separate by the bullet's own instruction: a token
grammar islands the predictive engine, so the consult cannot appear there, and
the row exists to show the parse did not regress rather than to show a win.

    --plan     compile and report populations and document sizes; no timing
    --gc-off   the provenance protocol: collector disabled in the timed region
    --micro  the `run_span_once` branch row only
    (none)   the whole gate

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import argparse
import gc
import random
import time
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

import lexic.parsing.pda.compiler.program.lower as lowering
import lexic.parsing.pda.compiler.program.specialize as specialize
from lexic.compile import Vocabulary, compile_text
from lexic.compile.artifact import CompiledGrammar
from lexic.exceptions import LexicError
from lexic.generate import generate
from lexic.ir import IrChr, IrMap, IrStr, IrTokenizer, IrTuple
from lexic.model import GrammarModel
from lexic.parsing.caches import reset_caches
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone
from lexic.parsing.pda.compiler.program.opcodes import OP_CC, OP_CONSULT, OP_LIT
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.build import build_vstr
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.pda.runtime.matchers import (
    CHARTABLE_CAP,
    consult_extent,
    match_cc,
    match_lit,
    run_span_once,
)
from lexic.parsing.products import (
    _model_product,
    reset_product_cache,
    token_model,
)

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
SEEDS = tuple(range(200))
TARGET_CHARS = 20_000
"""Documents are grown to about this size before timing. A row measured on
thirty characters is measuring the harness."""

ROUNDS = 7
MICRO_ITERATIONS = 200_000

THINK = "root ::= <think> thinking </think>\nthinking ::= !</think>*"
THINK_VOCAB = {"<think>": 0, "</think>": 1, "a": 2, "b": 3, "<": 4, "/think>": 5}
"""The token-segmented row's grammar and vocabulary — a vocabulary spelled here
rather than fetched, so the row runs without the LGPL fixtures."""

_CONSULT_MAP = lowering._consults
_BAKE_CONSULTS = specialize.bake_consults

INSTALLED: list[str] = []


class Row(NamedTuple):
    """One grammar's gate row.

    :ivar name: The grammar.
    :ivar consults: Consult clones installed.
    :ivar chars: Characters parsed per round.
    :ivar parses: Documents parsed per round.
    :ivar with_consult: Best process seconds with the consult live.
    :ivar without: Best process seconds with it suppressed.
    """

    name: str
    consults: int
    chars: int
    parses: int
    with_consult: float
    without: float

    @property
    def delta(self) -> float:
        """Per cent change the consult makes; negative is faster."""
        return 100.0 * (self.with_consult - self.without) / self.without

    @property
    def ns_per_char(self) -> float:
        """Nanoseconds per character with the consult live."""
        return 1e9 * self.with_consult / self.chars


class Defect(AssertionError):
    """A claim this harness makes that the tree does not support."""


def _check(claim: str, held: bool) -> None:
    """Refuse the harness the moment one claim stops holding."""
    if not held:
        raise Defect(f"s4 consult gate: {claim}")


def _recording_bake(clones: list[FlatClone], consults: object) -> None:
    """The shipped consult bake, plus a note of which clones took one."""
    _BAKE_CONSULTS(clones, consults)
    INSTALLED.extend(
        clone.name
        for clone in clones
        if clone.runarm is not None and clone.runarm.kinds[0] == OP_CONSULT
    )


def _cold() -> None:
    """Drop every memo, so the next compile runs under the live patches."""
    reset_product_cache()
    reset_caches()


def _grammars() -> list[Path]:
    """The ground-truth corpus, in a fixed order."""
    return (
        sorted(GROUND_TRUTH.glob("*.gbnf"))
        + sorted(GROUND_TRUTH.glob("*.abnf"))
        + sorted(GROUND_TRUTH.glob("*.ebnf"))
    )


def _parses(tables: PdaTables, compiled: CompiledGrammar, text: str) -> bool:
    """Whether the predictive engine alone claims this document."""
    try:
        pda_model(tables, text, compiled.executor)
    except PdaFail:
        return False
    return True


def _workload(compiled: CompiledGrammar, tables: PdaTables) -> list[str]:
    """One round's parsing work: documents totalling about ``TARGET_CHARS``.

    A grammar whose start rule is a repetition grows into ONE document, which
    is the better shape to measure — steady-state parsing rather than repeated
    entry. A grammar whose start rule is a single value (every JSON
    formulation, a vyx packet) cannot be grown that way, so its round parses
    the generated set repeatedly instead. Both are decided by asking the engine
    whether the bigger text still parses; no grammar is named.
    """
    ast = compiled.grammar
    rules = {str(rule.name): rule for rule in ast.rules}
    units = [
        text
        for seed in SEEDS
        if (text := generate(str(ast.start), rules, rng=random.Random(seed)))
        and _parses(tables, compiled, text)
    ]
    _check("the generator produced no parsable document", bool(units))
    joined = "".join(units)
    if _parses(tables, compiled, joined):
        grown = joined * max(1, TARGET_CHARS // len(joined))
        return [grown] if _parses(tables, compiled, grown) else [joined]
    total = sum(len(unit) for unit in units)
    return units * max(1, TARGET_CHARS // total)


def _tables(compiled: CompiledGrammar, chars: int, consulting: bool) -> PdaTables:
    """One compiled predictive program, with the consult live or suppressed."""
    if not consulting:
        lowering._consults = lambda _clones, _low: {}
    _cold()
    try:
        product = _model_product(
            compiled.codegen_grammar, compiled.product, tier_for(chars)
        )
    finally:
        lowering._consults = _CONSULT_MAP
    return product.pda


COLLECTOR_OFF = False
"""Whether the timed region runs with the garbage collector disabled.

The ACCEPTANCE protocol runs with it enabled, which is the default here: a
collector that never runs is not the interpreter the change ships under, and a
row measured without it can only ever be provenance for one that is. ``--gc-off``
reproduces the provenance protocol so the two can be compared directly. Every
row prints which one it was taken under."""


def _collector_off() -> None:
    """Disable the collector, if this run's protocol says to."""
    if COLLECTOR_OFF:
        gc.disable()


def _collector_on() -> None:
    """Re-enable it, if this run's protocol disabled it."""
    if COLLECTOR_OFF:
        gc.enable()


def _protocol() -> str:
    """How a row was taken, spelled for the row itself."""
    return f"{ROUNDS} rounds, process_time, gc {'OFF' if COLLECTOR_OFF else 'ON'}"


def _best(tables: PdaTables, compiled: CompiledGrammar, work: list[str]) -> float:
    """The lowest process time of one whole round over the rounds."""
    executor = compiled.executor
    best = float("inf")
    for _round in range(ROUNDS):
        _collector_off()
        started = time.process_time()
        try:
            for text in work:
                pda_model(tables, text, executor)
        finally:
            elapsed = time.process_time() - started
            _collector_on()
        best = min(best, elapsed)
        gc.collect()
    return best


def _alternating(
    live: PdaTables, plain: PdaTables, compiled: CompiledGrammar, work: list[str]
) -> tuple[float, float]:
    """Both arms, alternating, each reported as its own minimum."""
    with_consult = float("inf")
    without = float("inf")
    for _pass in range(2):
        with_consult = min(with_consult, _best(live, compiled, work))
        without = min(without, _best(plain, compiled, work))
    return with_consult, without


def _one_grammar(path: Path, timed: bool) -> Row | None:
    """One grammar's row, or ``None`` when it compiles no predictive program."""
    from lexic.compile import compile_from_path

    _cold()
    try:
        compiled = compile_from_path(path)
    except LexicError:
        return None
    INSTALLED.clear()
    try:
        live = _tables(compiled, TARGET_CHARS, True)
    except LexicError:
        return None
    consults = len(INSTALLED)
    work = _workload(compiled, live)
    chars = sum(len(text) for text in work)
    plain = _tables(compiled, TARGET_CHARS, False)
    _check(
        f"{path.name}: the consult-free program declines its own workload",
        all(_parses(plain, compiled, text) for text in work[:1]),
    )
    if not timed:
        return Row(path.name, consults, chars, len(work), 0.0, 0.0)
    return Row(
        path.name,
        consults,
        chars,
        len(work),
        *_alternating(live, plain, compiled, work),
    )


def _token_row(timed: bool) -> tuple[int, float, float]:
    """The token-segmented row — the same document, both arms, Earley route."""
    tokenizer = IrTokenizer.from_vocab(
        "tokens", IrMap(*(IrTuple(IrStr(t), IrChr(i)) for t, i in THINK_VOCAB.items()))
    )
    _cold()
    compiled = compile_text(
        THINK, vocabulary=Vocabulary(tokenizer), cache_key="s4-consult-gate"
    )
    text = "<think>" + "ab" * 2000 + "</think>"
    bounds = {
        start: (tid, end - start) for start, end, tid in tokenizer.boundaries(text)
    }
    if not timed:
        return len(text), 0.0, 0.0
    arms: list[float] = []
    for consulting in (True, False, True, False):
        if not consulting:
            lowering._consults = lambda _clones, _low: {}
        _cold()
        try:
            best = float("inf")
            for _round in range(ROUNDS):
                _collector_off()
                started = time.process_time()
                try:
                    token_model(
                        compiled.codegen_grammar, text, compiled.product, bounds
                    )
                finally:
                    best = min(best, time.process_time() - started)
                    _collector_on()
                gc.collect()
        finally:
            lowering._consults = _CONSULT_MAP
        arms.append(best)
    return len(text), min(arms[0], arms[2]), min(arms[1], arms[3])


def _run_span_base[Carry](
    text: str, clone: FlatClone[Carry], sink: list[Carry], pos: int
) -> int:
    """`run_span_once` as it stood at the starting commit — two kinds, one test.

    Transcribed, not imported: the point is to price the third branch, and the
    two bodies have to run in one process for the comparison to mean anything.
    The bytecode witness is what says the transcription is faithful.
    """
    runarm = clone.runarm
    end = (
        match_cc(text, runarm, 0, pos)
        if runarm.kinds[0] == OP_CC
        else match_lit(text, runarm, 0, pos)
    )
    span = text[pos:end]
    table = clone.chartable
    model = table.get(span)
    if model is None:
        model = build_vstr(clone, span, {})
        if len(table) < CHARTABLE_CAP:
            table[span] = model
    sink.append(model)
    return end


def _micro_clone(kind: int) -> tuple[FlatClone, str] | None:
    """A real clone whose run arm is ``kind``, with text its arm matches."""
    from lexic.compile import compile_from_path

    for name in ("json.gbnf", "vyx.gbnf", "c.gbnf"):
        _cold()
        compiled = compile_from_path(GROUND_TRUTH / name)
        product = _model_product(
            compiled.codegen_grammar, compiled.product, tier_for(TARGET_CHARS)
        )
        found = _find_runarm(product.pda.program.start, kind)
        if found is not None:
            return found
    return None


def _find_runarm(start: object, kind: int) -> tuple[FlatClone, str] | None:
    """Walk the program for a clone whose run arm carries ``kind``."""
    seen: set[int] = set()
    work: list[object] = [start]
    while work:
        clone = work.pop()
        if not isinstance(clone, FlatClone) or id(clone) in seen:
            continue
        seen.add(id(clone))
        if clone.runarm is not None and clone.runarm.kinds[0] == kind:
            text = _text_for(clone.runarm)
            if text:
                return clone, text
        work.extend(_reachable(clone))
    return None


def _reachable(clone: FlatClone) -> list[object]:
    """Every object a clone points at that might be another clone."""
    pool: list[object] = [clone.default]
    pool += [entry[-1] for entry in clone.selectors]
    if clone.kwin_selectors is not None:
        pool += [arm for _windows, arm in clone.kwin_selectors]
    if clone.pn_selectors is not None:
        pool += [entry[-1] for entry in clone.pn_selectors[1]]
    if clone.attempt is not None:
        pool += [entry[-1] for entry in clone.attempt[1]]
    out = [found for found in pool if isinstance(found, FlatClone)]
    arms = [found for found in pool if isinstance(found, FlatArm)]
    for arm in arms:
        out += [p for p in arm.payloads if isinstance(p, FlatClone)]
    return out


def _text_for(runarm: FlatArm) -> str:
    """A document the run arm matches — one of its own accepted characters."""
    if runarm.kinds[0] == OP_LIT:
        return str(runarm.payloads[0]) * 8
    chars, negated = runarm.payloads[0]
    if negated or not chars:
        return ""
    return "".join(sorted(chars)[:1]) * 8


def micro(timed: bool) -> None:
    """Price the third branch on each pre-existing run-arm kind."""
    for label, kind in (("OP_CC", OP_CC), ("OP_LIT", OP_LIT)):
        found = _micro_clone(kind)
        if found is None:
            print(f"micro   \t{label:<8}no clone in the corpus carries this run arm")
            continue
        clone, text = found
        if not timed:
            print(f"micro   \t{label:<8}{clone.name!r}, text {text!r}")
            continue
        now = _micro_best(run_span_once, clone, text)
        base = _micro_best(_run_span_base, clone, text)
        print(
            f"micro   \t{label:<8}{clone.name:<16}now {now:.6f}s  base {base:.6f}s  "
            f"{100.0 * (now - base) / base:+.2f}%  "
            f"({1e9 * (now - base) / MICRO_ITERATIONS:+.1f} ns/call)  "
            f"gc {'OFF' if COLLECTOR_OFF else 'ON'}"
        )


def _micro_best(body: object, clone: FlatClone, text: str) -> float:
    """The lowest process time of ``MICRO_ITERATIONS`` calls of one body."""
    assert callable(body)
    best = float("inf")
    for _round in range(3):
        sink: list[object] = []
        _collector_off()
        started = time.process_time()
        try:
            for _call in range(MICRO_ITERATIONS):
                body(text, clone, sink, 0)
        finally:
            best = min(best, time.process_time() - started)
            _collector_on()
        gc.collect()
    return best


def _report(rows: list[Row], timed: bool) -> None:
    """Print the gate table — carrying rows first, then the controls."""
    carrying = [row for row in rows if row.consults]
    controls = [row for row in rows if not row.consults]
    print(
        f"\n{'grammar':<18}{'consults':>9}{'chars':>8}{'docs':>6}"
        f"{'with':>11}{'without':>11}{'delta':>9}{'ns/char':>9}{'gc':>5}"
    )
    for row in carrying + controls:
        if not timed:
            print(f"{row.name:<18}{row.consults:>9}{row.chars:>8}{row.parses:>6}")
            continue
        print(
            f"{row.name:<18}{row.consults:>9}{row.chars:>8}{row.parses:>6}"
            f"{row.with_consult:>11.6f}{row.without:>11.6f}"
            f"{row.delta:>8.2f}%{row.ns_per_char:>9.0f}"
            f"{'OFF' if COLLECTOR_OFF else 'ON':>5}"
        )
    if timed and controls:
        floor = max(abs(row.delta) for row in controls)
        print(
            f"\ncontrol floor\t{floor:.2f}% — the widest delta on a row the consult cannot reach"
        )


def main(arguments: Sequence[str] | None = None) -> None:
    """Run the gate, or just its plan."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--micro", action="store_true")
    parser.add_argument("--gc-off", action="store_true")
    options = parser.parse_args(arguments)
    timed = not options.plan
    global COLLECTOR_OFF
    COLLECTOR_OFF = options.gc_off
    specialize.bake_consults = _recording_bake
    try:
        if options.micro:
            micro(timed)
            return
        rows = [row for path in _grammars() if (row := _one_grammar(path, timed))]
        _report(rows, timed)
        chars, live, plain = _token_row(timed)
        if timed:
            print(
                f"\ntoken\tthink/{chars} chars\twith {live:.6f}s\twithout "
                f"{plain:.6f}s\t{100.0 * (live - plain) / plain:+.2f}%"
                f"\tgc {'OFF' if COLLECTOR_OFF else 'ON'}"
            )
        else:
            print(f"\ntoken\tthink/{chars} chars")
        micro(timed)
    finally:
        specialize.bake_consults = _BAKE_CONSULTS
        _cold()
    print(
        "\ns4 consult gate\tdone\t"
        + (
            "plan only, nothing timed"
            if not timed
            else f"{_protocol()} in the timed region"
        )
    )


if __name__ == "__main__":
    main()
