"""Pure-Lark parse benchmark — the reference baseline for the engine-perf effort.

The old ``zzz_current_work/bench_parsing.py`` raced the native IR Earley engine
against *Lark-inside-lexic* (``MetaGrammarParser``). That path is deleted. This
bench keeps the same corpus and timing discipline but measures **pure Lark** —
zero lexic machinery on the Lark side — as the fixed reference the engine is
tuned against.

Corpus (unchanged): the ABNF-of-ABNF source (``ABNF_FLAVOUR.apply(grammar)``,
~2 KB) concatenated x1/x2/x4. A concatenation of valid rulelists is itself a
valid rulelist, so parse cost is what scales; duplicate rule names are
immaterial to the parser.

Timing (unchanged): interleaved samples (one of every variant per round, so
machine drift hits all alike), median ± stdev in ms, gc disabled around each
sample, and µs/char throughput in the verdict.

**What each stage times (the two sides are kept symmetric — construction and
table compilation are excluded from every timed loop via warm-up):**

  stage          engine                              pure lark
  parse          parse()          → ParseTree        Lark.parse → Lark Tree
  parse+reduce   parse_reduced()  → IrAst            (no counterpart — deleted)

The engine ``parse`` stage (text → native tree) is the symmetric race against
Lark ``parse`` (text → Lark Tree); that ratio is the verdict. ``parse+reduce``
is the engine's full product path (text → ``IrAst``); its historical Lark
counterpart was ``parse + _IrTagTransformer``, and the transformer is gone with
the meta-parser, so no honest Lark number survives for it — it is reported
engine-only.

Deliberate divergences from the old bench, documented per the brief:
  - Lark side is *pure* (no ``MetaGrammarParser`` wrapper); the meta-grammar is
    embedded here as a module constant, recovered verbatim from the pre-cutover
    ``src/lexic/grammars/abnf.py`` ``META_GRAMMAR``.
  - Lark parser options mirror the retired ``MetaGrammarParser`` exactly:
    ``parser="earley", ambiguity="resolve"``.
  - The headline ratio is the ``parse`` stage, not ``parse+reduce``, because the
    Lark reduce stage no longer exists to compare against.

Usage:
  uv run python tools/benchmark/parse_bench.py            # engine only + hint
  uv run --with lark python tools/benchmark/parse_bench.py  # both sides + ratios
"""

from __future__ import annotations

import gc
import importlib
import importlib.util
import statistics
import time
from types import ModuleType
from typing import Callable

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.parsing import parse as engine_parse
from lexic.parsing import parse_reduced as engine_parse_reduced
from lexic.parsing.normalize import normalize

# ── The pre-cutover Lark ABNF meta-grammar, recovered verbatim ─────────
# Source: git HEAD:src/lexic/grammars/abnf.py (the ``META_GRAMMAR`` string, RFC
# 5234 + RFC 7405). Embedded so the Lark side carries zero lexic machinery.
META_GRAMMAR = r"""
start: rule+

rule: NAME "=" alternation             -> ir_rule
    | NAME INCREMENTAL alternation     -> ir_rule_inc

alternation: sequence ("/" sequence)*  -> ir_alternation
sequence: item*                        -> ir_sequence

item: QUANTIFIER? element              -> ir_item
    | "[" alternation "]"              -> ir_option

element: LITERAL                       -> ir_literal
    | CS_STRING                        -> ir_literal_cs
    | CI_STRING                        -> ir_literal_ci
    | NUMSEQ                           -> ir_numseq
    | NUMVAL                           -> ir_charclass
    | PROSE                            -> ir_prose
    | NAME                             -> ir_ruleref
    | "(" alternation ")"              -> ir_group

INCREMENTAL.2: /=\//
NAME: /[A-Za-z][A-Za-z0-9_-]*/
LITERAL: /"[^"\r\n]*"/
CS_STRING: /%[sS]"[^"\r\n]*"/
CI_STRING: /%[iI]"[^"\r\n]*"/
NUMSEQ.2: /%[bdxBDX][0-9A-Fa-f]+(?:\.[0-9A-Fa-f]+)+/
NUMVAL: /%[bdxBDX][0-9A-Fa-f]+(?:-[0-9A-Fa-f]+)?/
PROSE: /<[^>\r\n]*>/
QUANTIFIER: /[0-9]*\*[0-9]*|[0-9]+/

%ignore /[ \t\r\n]+/
%ignore /;[^\n]*/
"""

# ── Setup (excluded from every timed loop) ─────────────────────────────
BASE_TEXT = str(ABNF_FLAVOUR.apply(ABNF_FLAVOUR.grammar))
NORM_GRAMMAR = normalize(ABNF_FLAVOUR.grammar)
REDUCER = ABNF_FLAVOUR.reducer
SIZES = (1, 2, 4)
LARK_HINT = "run: uv run --with lark python tools/benchmark/parse_bench.py"

Variant = Callable[[str], object]


def load_lark() -> ModuleType | None:
    """Import ``lark`` if installed, else ``None`` — never a hard dependency.

    :returns: The ``lark`` module, or ``None`` when it is not importable.
    """
    if importlib.util.find_spec("lark") is None:
        return None
    return importlib.import_module("lark")


def make_input(repeat: int) -> str:
    """Return ``repeat`` concatenated copies of the ABNF-of-ABNF source.

    :param repeat: How many copies to concatenate.
    :returns: The concatenated (still valid) ABNF rulelist text.
    """
    return BASE_TEXT * repeat


def build_variants(lark_mod: ModuleType | None) -> dict[str, Variant]:
    """Map ``"stage:engine"`` names to their timed one-shot callables.

    Grammar construction and table compilation happen here, once, outside every
    timed loop; the loop's warm-up primes any remaining lazy engine state so the
    two sides stay symmetric.

    :param lark_mod: The ``lark`` module, or ``None`` to omit the Lark side.
    :returns: An ordered name → callable mapping of timed variants.
    """
    variants: dict[str, Variant] = {
        "parse:engine": lambda t: engine_parse(NORM_GRAMMAR, t),
        "parse+reduce:engine": lambda t: engine_parse_reduced(NORM_GRAMMAR, t, REDUCER),
    }
    if lark_mod is not None:
        lark_parser = lark_mod.Lark(META_GRAMMAR, parser="earley", ambiguity="resolve")
        variants["parse:lark"] = lark_parser.parse
    return variants


def interleaved(
    variants: dict[str, Variant], text: str, rounds: int
) -> dict[str, list[float]]:
    """Time every variant ``rounds`` times, one sample each per round (ms).

    Interleaving makes machine drift fall on all variants alike, so ratios stay
    honest even if absolute numbers wander.

    :param variants: Name → timed callable mapping.
    :param text: The input to parse.
    :param rounds: How many samples to take per variant.
    :returns: Name → list of per-sample durations in milliseconds.
    """
    samples: dict[str, list[float]] = {name: [] for name in variants}
    for fn in variants.values():  # warm up (compile tables, JIT lazy state)
        fn(text)
    for _ in range(rounds):
        for name, fn in variants.items():
            gc.disable()
            start = time.perf_counter_ns()
            fn(text)
            elapsed = time.perf_counter_ns() - start
            gc.enable()
            samples[name].append(elapsed / 1e6)
    return samples


def _cell(samples: list[float]) -> str:
    """Format one ``median±stdev`` millisecond cell.

    :param samples: Per-sample durations in milliseconds.
    :returns: A right-aligned ``med±sd ms`` string.
    """
    return f"{statistics.median(samples):>7.1f}±{statistics.stdev(samples):<4.1f}ms"


def _report_scale(
    samples: dict[str, list[float]], text: str, rounds: int, have_lark: bool
) -> None:
    """Print the per-stage table for one input scale.

    :param samples: Name → per-sample durations for this scale.
    :param text: The scale's input (for the char count).
    :param rounds: Rounds used (for the header).
    :param have_lark: Whether the Lark side ran.
    """
    print(
        f"input x{len(text) // len(BASE_TEXT)}  ({len(text)} chars · {rounds} rounds):"
    )
    print(
        f"  {'stage':<14} {'lark med±sd':>16} {'engine med±sd':>18} {'engine/lark':>12}"
    )
    for stage, tail in (("parse", ""), ("parse+reduce", "  ← product")):
        engine = samples[f"{stage}:engine"]
        if have_lark and f"{stage}:lark" in samples:
            lark_samples = samples[f"{stage}:lark"]
            ratio = statistics.median(engine) / statistics.median(lark_samples)
            lark_cell, ratio_cell = _cell(lark_samples), f"{ratio:>10.2f}x"
        else:
            lark_cell, ratio_cell = f"{'—':>14}", f"{'—':>11}"
        print(f"  {stage:<14} {lark_cell} {_cell(engine)} {ratio_cell}{tail}")
    print()


def _verdict(medians: dict[str, float], have_lark: bool) -> None:
    """Print the headline verdict on the largest scale's ``parse`` stage.

    :param medians: ``"x{n}/{stage}:{engine}"`` → median ms.
    :param have_lark: Whether the Lark side ran.
    """
    big, chars = SIZES[-1], len(make_input(SIZES[-1]))
    engine_ms = medians[f"x{big}/parse:engine"]
    product_ms = medians[f"x{big}/parse+reduce:engine"]
    print(f"== VERDICT (x{big}, {chars} chars) — parse stage, text→tree ==")
    if not have_lark:
        print(
            f"  engine parse {engine_ms:.0f}ms · {engine_ms / chars * 1e3:.1f} µs/char"
        )
        print(f"  lark side skipped — {LARK_HINT}")
        print(
            f"  engine product (parse+reduce) {product_ms:.0f}ms · "
            f"{product_ms / chars * 1e3:.1f} µs/char\n"
        )
        return
    lark_ms = medians[f"x{big}/parse:lark"]
    ratio = engine_ms / lark_ms
    if ratio <= 1:
        print(
            f"  engine {engine_ms:.0f}ms BEATS lark {lark_ms:.0f}ms by {(1 - ratio) * 100:.0f}%"
        )
    else:
        print(
            f"  lark {lark_ms:.0f}ms wins {ratio:.2f}x over engine {engine_ms:.0f}ms — "
            f"cut {(ratio - 1) / ratio * 100:.0f}% of engine time to match it"
        )
    print(
        f"  throughput: engine {engine_ms / chars * 1e3:.1f} µs/char  "
        f"vs lark {lark_ms / chars * 1e3:.1f} µs/char"
    )
    print(
        f"  engine product (parse+reduce, no lark counterpart): "
        f"{product_ms / chars * 1e3:.1f} µs/char\n"
    )


def main() -> None:
    """Run the benchmark across all scales and print the verdict."""
    lark_mod = load_lark()
    have_lark = lark_mod is not None
    variants = build_variants(lark_mod)
    side = "engine + pure lark" if have_lark else "engine only (lark not installed)"
    print(f"== pure-lark parse benchmark: {side} ==")
    fixpoint = (
        engine_parse_reduced(NORM_GRAMMAR, BASE_TEXT, REDUCER) == ABNF_FLAVOUR.grammar
    )
    print(
        f"ABNF self-host, {len(BASE_TEXT)} chars/copy.  "
        f"engine parse+reduce fixpoint: {fixpoint}"
    )
    if not have_lark:
        print(f"lark not importable — {LARK_HINT}")
    print()

    medians: dict[str, float] = {}
    for repeat in SIZES:
        text = make_input(repeat)
        rounds = max(7, 40 // repeat)
        samples = interleaved(variants, text, rounds)
        for name, series in samples.items():
            medians[f"x{repeat}/{name}"] = statistics.median(series)
        _report_scale(samples, text, rounds, have_lark)

    _verdict(medians, have_lark)


if __name__ == "__main__":
    main()
