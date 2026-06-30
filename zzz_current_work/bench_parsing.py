"""Parsing benchmark: native Earley (``parsing_2/``) vs Lark — **goal: beat Lark**.

Every Earley stage is paired with the **matching Lark stage** (same work), so each
row is a true earley-vs-lark comparison:

  stage          earley                         lark (parser='earley')
  recognize      recognize()        → bool      parse, ambiguity='forest' → SPPF, no tree
  parse          parse()            → ParseTree parse                     → Lark Tree
  parse+reduce   reduce(parse())    → IrAst     parse + transform         → IrAst   ← product

``recognize`` is Lark's parse stopped at the forest (no tree extraction) — its
cheapest "did it parse"; ``parse`` adds the tree; ``parse+reduce`` / lark-full add
the semantic transform (text → ``IrAst``, the grammar object you ship). The
``parse+reduce`` row is the headline "do we beat Lark".

Each cell is median ± stdev over **interleaved** samples (one of every variant per
round, so machine drift hits all alike). ``--save`` snapshots medians so a later
run prints Δ% per cell. ``--rightrec`` is the asymptotic story (deep ``S = "a"*``;
earley parse is O(n²) vs Lark O(n)). ``--profile`` cProfiles parse+reduce.

Usage:
  uv run python zzz_current_work/bench_parsing.py [label] [--save]
  uv run python zzz_current_work/bench_parsing.py --rightrec
  uv run python zzz_current_work/bench_parsing.py --profile
"""

from __future__ import annotations

import cProfile
import gc
import json
import pathlib
import pstats
import statistics
import sys
import time
from typing import Callable

import lark

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR, ABNF_REDUCER
from lexic.ir.base import IrNone, IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrSequence,
)
from lexic.parsing.meta_parser import MetaGrammarParser
from lexic.parsing_2 import parse as earley_parse
from lexic.parsing_2 import recognize as earley_recognize
from lexic.parsing_2.normalize import normalize

# ── Setup (excluded from timing) ──────────────────────────────────────
BASE_TEXT = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))
NORM_GRAMMAR = normalize(ABNF_GRAMMAR)
SIZES = (1, 2, 4)
BASELINE_PATH = pathlib.Path(__file__).parent / "bench_baseline.json"

_META = MetaGrammarParser.for_flavour(ABNF_FLAVOUR)
# Lark's three stages on the ABNF meta-grammar, matched to ours:
_LARK_RECOGNIZE = lark.Lark(  # parse → SPPF forest, no tree extraction
    ABNF_FLAVOUR.meta_grammar, parser="earley", ambiguity="forest"
)
_LARK_PARSE = _META._lark  # parse → Lark Tree (no transform)


# stage → (lark fn, earley fn). Order is the work ladder.
STAGES: list[tuple[str, Callable[[str], object], Callable[[str], object]]] = [
    ("recognize", _LARK_RECOGNIZE.parse, lambda t: earley_recognize(NORM_GRAMMAR, t)),
    ("parse", _LARK_PARSE.parse, lambda t: earley_parse(NORM_GRAMMAR, t)),
    (
        "parse+reduce",
        _META.parse,
        lambda t: ABNF_REDUCER.apply(earley_parse(NORM_GRAMMAR, t)),
    ),
]
PRODUCT = "parse+reduce"  # the headline row (text → IrAst)


def make_input(repeat: int) -> str:
    """``repeat`` concatenated copies of the ABNF-of-ABNF source.

    A concatenation of valid rulelists is itself a valid (longer) rulelist —
    parsing cost is what we measure, duplicate rule names are immaterial here.
    """
    return BASE_TEXT * repeat


def interleaved(text: str, rounds: int) -> dict[str, list[float]]:
    """Time every (stage, engine) ``rounds`` times, one sample each per round.

    Interleaving makes machine drift fall on all variants alike, so the
    earley/lark ratios stay honest even if absolute numbers wander.
    """
    keys = [f"{s}:{e}" for s, _, _ in STAGES for e in ("lark", "earley")]
    fns = {f"{s}:lark": lk for s, lk, _ in STAGES}
    fns.update({f"{s}:earley": ey for s, _, ey in STAGES})
    samples: dict[str, list[float]] = {k: [] for k in keys}
    for fn in fns.values():  # warm up
        fn(text)
    for _ in range(rounds):
        for k in keys:
            gc.disable()
            t0 = time.perf_counter_ns()
            fns[k](text)
            t1 = time.perf_counter_ns()
            gc.enable()
            samples[k].append((t1 - t0) / 1e6)
    return samples


def load_baseline() -> dict[str, float]:
    return json.loads(BASELINE_PATH.read_text()) if BASELINE_PATH.exists() else {}


# ── Self-host benchmark ───────────────────────────────────────────────
def main(label: str, save: bool) -> None:
    print(f"== parsing benchmark: {label} ==")
    earley_ir = STAGES[2][2](BASE_TEXT)
    print(
        f"ABNF self-host, {len(BASE_TEXT)} chars/copy.  "
        f"earley IrAst == lark IrAst (fixpoint): {earley_ir == ABNF_GRAMMAR}"
    )
    print("each row pairs the same work — earley vs lark; ratio>1 ⇒ we are slower.\n")

    baseline = load_baseline()
    medians: dict[str, float] = {}
    for repeat in SIZES:
        text = make_input(repeat)
        rounds = max(7, 40 // repeat)
        s = interleaved(text, rounds)
        print(f"input x{repeat}  ({len(text)} chars · {rounds} rounds):")
        print(
            f"  {'stage':<14} {'lark med±sd':>16} {'earley med±sd':>18} "
            f"{'earley/lark':>12}  {'Δ base':>7}"
        )
        for stage, _, _ in STAGES:
            lk, ey = s[f"{stage}:lark"], s[f"{stage}:earley"]
            lk_m, ey_m = statistics.median(lk), statistics.median(ey)
            medians[f"x{repeat}/{stage}:lark"] = lk_m
            medians[f"x{repeat}/{stage}:earley"] = ey_m
            tail = "  ← product" if stage == PRODUCT else ""
            prev = baseline.get(f"x{repeat}/{stage}:earley")
            delta = f"{(ey_m / prev - 1) * 100:+.0f}%" if prev else "—"
            print(
                f"  {stage:<14} "
                f"{lk_m:>7.1f}±{statistics.stdev(lk):<4.1f}ms "
                f"{ey_m:>9.1f}±{statistics.stdev(ey):<4.1f}ms "
                f"{ey_m / lk_m:>10.2f}x  {delta:>7}{tail}"
            )
        print()

    big = f"x{SIZES[-1]}"
    lk_m = medians[f"{big}/{PRODUCT}:lark"]
    ey_m = medians[f"{big}/{PRODUCT}:earley"]
    ratio = ey_m / lk_m
    chars = len(make_input(SIZES[-1]))
    print(f"== VERDICT ({big}, {chars} chars) — product text→IrAst ==")
    if ratio <= 1:
        print(f"  earley {ey_m:.0f}ms BEATS lark {lk_m:.0f}ms by {(1 - ratio) * 100:.0f}%")
    else:
        print(
            f"  lark {lk_m:.0f}ms wins {ratio:.2f}x over earley {ey_m:.0f}ms — "
            f"cut {(ratio - 1) / ratio * 100:.0f}% of earley time to match it"
        )
    print(
        f"  throughput: earley {ey_m / chars * 1e3:.1f} µs/char  "
        f"vs lark {lk_m / chars * 1e3:.1f} µs/char\n"
    )
    if save:
        BASELINE_PATH.write_text(json.dumps(medians, indent=2, sort_keys=True))
        print(f"baseline saved → {BASELINE_PATH.name}")


# ── Asymptotic benchmark (deep right-recursion) ───────────────────────
def _best(fn: Callable[[str], object], n: int, reps: int = 4) -> float:
    text = "a" * n
    gc.disable()
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn(text)
        ts.append(time.perf_counter() - t0)
    gc.enable()
    return min(ts)


def rightrec() -> None:
    """Deep right-recursion ``S = "a"*`` — the algorithmic gap, per stage vs lark.

    ``parse`` (build a tree) is O(n²) for earley (no Leo on the SPPF) vs Lark O(n)
    — the gap Leo+SPPF must close. ``recognize`` (earley → bool; lark → forest) is
    O(n) for both; earley wins on this stage. Memory note: the parse chart is
    O(n²), so parse N is capped below recognize N.
    """
    g = normalize(
        IrAst(
            rules=IrSeq(
                IrRule(
                    "S",
                    IrAlternation(
                        IrSequence(IrItem(IrLiteral("a"), IrQuantifier(0, IrNone)))
                    ),
                )
            ),
            start="S",
        )
    )
    lk_rec = lark.Lark('start: "a"*', parser="earley", ambiguity="forest")
    lk_parse = lark.Lark('start: "a"*', parser="earley")

    print('== deep right-recursion: S = "a"* ==\n')
    print("parse → tree  (earley O(n²) vs lark O(n)):")
    print(
        f"  {'N':>6} {'earley':>10} {'µs/N':>8} {'µs/N²':>7}  "
        f"{'lark':>9} {'µs/N':>8}  {'earley/lark':>11}"
    )
    for n in (100, 200, 400, 800, 1600):
        ey = _best(lambda t: earley_parse(g, t), n)
        lk = _best(lk_parse.parse, n)
        print(
            f"  {n:>6} {ey * 1e3:>8.2f}ms {ey / n * 1e6:>8.2f} "
            f"{ey / n / n * 1e6:>7.3f}  {lk * 1e3:>7.2f}ms {lk / n * 1e6:>8.2f}  "
            f"{ey / lk:>10.1f}x"
        )

    print("\nrecognize  (earley → bool vs lark → forest; both O(n)):")
    print(
        f"  {'N':>6} {'earley':>10} {'µs/N':>8}  {'lark':>9} {'µs/N':>8}  "
        f"{'earley/lark':>11}"
    )
    for n in (200, 800, 1600, 3200, 6400):
        ey = _best(lambda t: earley_recognize(g, t), n)
        lk = _best(lk_rec.parse, n)
        print(
            f"  {n:>6} {ey * 1e3:>8.2f}ms {ey / n * 1e6:>8.2f}  "
            f"{lk * 1e3:>7.2f}ms {lk / n * 1e6:>8.2f}  {ey / lk:>10.1f}x"
        )


def profile() -> None:
    """cProfile parsing_2 parse+reduce on the x4 input (treat as a hint)."""
    text = make_input(4)
    STAGES[2][2](text)
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(5):
        STAGES[2][2](text)
    pr.disable()
    print("\n=== cProfile parsing_2 (parse+reduce), x4, sorted by tottime ===")
    pstats.Stats(pr).sort_stats("tottime").print_stats(25)


if __name__ == "__main__":
    if "--profile" in sys.argv:
        profile()
    elif "--rightrec" in sys.argv:
        rightrec()
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        main(args[0] if args else "run", save="--save" in sys.argv)
