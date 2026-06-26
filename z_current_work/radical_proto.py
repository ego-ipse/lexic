"""Radical prototype — two bets measured against the current engine.

Bet 1 (B1): Left-recursive desugaring in normalize.py  (F1 from opt_review_algo.md).
Bet 2 (B2): Per-column prediction dedup + IrMultiMap snapshot bypass (F4+F5).

Each bet is self-contained — patches the relevant class in-process, benchmarks,
then reverts. No permanent code changes.
"""

from __future__ import annotations

import gc
import statistics
import time
from typing import Sequence, cast

from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.abnf_2 import ABNF_GRAMMAR
from lexic.ir.base import (
    IrInt,
    IrLeaf,
    IrNone,
    IrNoneType,
    IrSelf,
    IrSeq,
    IrStr,
)
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing_2 import parse as earley_parse
from lexic.parsing_2 import recognize as earley_recognize
from lexic.parsing_2.normalize import (
    EXPAND,
    OPT_CHAIN,
    desugar_quantifiers,
    flatten_groups,
    split_literals,
)


def _normalize(g):
    return split_literals(desugar_quantifiers(flatten_groups(g)))


BASE_TEXT = str(ABNF_FLAVOUR.apply(ABNF_GRAMMAR))


def make_input(repeat: int) -> str:
    if repeat == 1:
        return BASE_TEXT
    return BASE_TEXT * repeat


def time_it(fn, text: str, n: int) -> list[float]:
    samples = []
    for _ in range(n):
        gc.disable()
        t0 = time.perf_counter()
        fn(text)
        t1 = time.perf_counter()
        gc.enable()
        samples.append(t1 - t0)
    return samples


def bench_label(label, fn, text, n):
    s = time_it(fn, text, n)
    best = min(s)
    med = statistics.median(s)
    print(f"  {label:24s}  best={best * 1e3:8.3f}ms  med={med * 1e3:8.3f}ms")
    return best


# ─── BET 1: left-recursive desugaring ────────────────────────────────────────


class LeftExpand(IrLeaf[IrSelf, IrSelf]):
    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrRuleRef:
        unit = cast(IrItem, n)
        lo = int(cast(int, nc[0]))
        hi = nc[1]
        minter = cast(object, d).minter  # type: ignore[attr-defined]
        name = str(minter.eval(d, IrStr("rep"), ()))
        ref = IrItem(IrRuleRef(name))
        if isinstance(hi, IrNoneType):
            if lo == 0:  # *  →  X = "" / X elem   (LEFT-recursive)
                body = IrAlternation(IrSequence(), IrSequence(ref, unit))
            elif lo == 1:  # +  →  X = elem / X elem  (LEFT-recursive)
                body = IrAlternation(IrSequence(unit), IrSequence(ref, unit))
            else:
                tail = IrItem(self.eval(d, unit, (IrInt(lo - 1), IrNone)))
                body = IrAlternation(IrSequence(unit, tail))
        else:
            hi_i = int(cast(int, hi))
            if lo == 0 and hi_i == 1:
                body = IrAlternation(IrSequence(), IrSequence(unit))
            elif lo == hi_i:
                body = IrAlternation(IrSequence(*((unit,) * lo)))
            else:
                tail = IrItem(LEFT_OPT_CHAIN.eval(d, unit, (IrInt(hi_i - lo),)))
                body = IrAlternation(IrSequence(*((unit,) * lo), tail))
        minter += IrRule(name, body)
        return IrRuleRef(name)


class LeftOptChain(IrLeaf[IrSelf, IrSelf]):
    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrRuleRef:
        unit = cast(IrItem, n)
        k = int(cast(int, nc[0]))
        minter = cast(object, d).minter  # type: ignore[attr-defined]
        name = str(minter.eval(d, IrStr("opt"), ()))
        if k == 1:
            body = IrAlternation(IrSequence(), IrSequence(unit))
        else:
            inner = IrItem(self.eval(d, unit, (IrInt(k - 1),)))
            body = IrAlternation(IrSequence(), IrSequence(inner, unit))
        minter += IrRule(name, body)
        return IrRuleRef(name)


LEFT_EXPAND = LeftExpand()
LEFT_OPT_CHAIN = LeftOptChain()


def patch_left_recursive():
    import lexic.parsing_2.normalize as nm

    nm.EXPAND = LEFT_EXPAND
    nm.OPT_CHAIN = LEFT_OPT_CHAIN


def unpatch_left_recursive():
    import lexic.parsing_2.normalize as nm

    nm.EXPAND = EXPAND
    nm.OPT_CHAIN = OPT_CHAIN


# ─── BET 2: micro-wins on top of the current engine ─────────────────────────


def patch_micro_wins():
    import lexic.parsing_2.ops as ops_mod

    _orig_complete_eval = ops_mod.Complete.eval
    _orig_predict_eval = ops_mod.Predict.eval

    def _fast_complete_eval(self, _d, _n, nc, /):
        ctx = nc[0]
        done = ctx.item
        chart = ctx.chart
        # F4: bypass IrMultiMap snapshot — read raw bucket directly.
        bucket = chart[done.origin].waiting._table.get(done.rule_name)
        if not bucket:
            return IrNone
        from lexic.parsing_2.chart import Link
        from lexic.parsing_2.forest import SppfNode
        from lexic.parsing_2.item import EarleyItem

        subnode = SppfNode(done, ctx.col)
        current = chart[ctx.col]
        n = len(bucket)
        for i in range(n):
            waiting = bucket[i]
            advanced = EarleyItem(
                waiting.rule_name, waiting.arm, waiting.dot + 1, waiting.origin
            )
            current += advanced
            chart.links += ((advanced, ctx.col), Link(waiting, done.origin, subnode))
        return IrNone

    ops_mod.Complete.eval = _fast_complete_eval

    # F5: per-column prediction skip. Column uses __slots__ so we can't add
    # _predicted as instance attr. Use a closure dict keyed by (chart_id, col),
    # cleared at the start of each parse (via BuildChart patch) to avoid id()
    # reuse causing stale hits across calls.
    _predicted: dict[tuple[int, int], set] = {}

    import lexic.parsing_2.engine as engine_mod

    _orig_build_chart = engine_mod.BuildChart.eval

    def _clearing_build_chart(self, d, n, nc, /):
        _predicted.clear()
        return _orig_build_chart(self, d, n, nc)

    engine_mod.BuildChart.eval = _clearing_build_chart

    def _predict_skip_eval(self, _d, n, nc, /):
        ctx = nc[0]
        ref = n
        col = ctx.col
        key = (id(ctx.chart), col)
        pred_set = _predicted.get(key)
        if pred_set is None:
            pred_set = set()
            _predicted[key] = pred_set
        if ref in pred_set:
            # Already predicted in this column. Still need Aycock-Horspool advance.
            if ref in ctx.nullable:
                it = ctx.item
                from lexic.ir.nodes import IrRuleRef as _IrRuleRef
                from lexic.parsing_2.chart import Link
                from lexic.parsing_2.forest import SppfNode
                from lexic.parsing_2.item import EarleyItem

                advanced = EarleyItem(it.rule_name, it.arm, it.dot + 1, it.origin)
                col_obj = ctx.chart[col]  # Column (mutable, in-place iadd)
                col_obj += advanced
                for arm in ctx.rules.resolve(ref):
                    if all(
                        isinstance(cast(IrItem, item).atom, _IrRuleRef)
                        and cast(IrItem, item).atom in ctx.nullable
                        for item in arm
                    ):
                        done = EarleyItem(ref, arm, len(arm), col)
                        child = SppfNode(done, col)
                        ctx.chart.links += ((advanced, col), Link(it, col, child))
            return IrNone
        pred_set.add(ref)
        return _orig_predict_eval(self, _d, n, nc)

    ops_mod.Predict.eval = _predict_skip_eval

    return _orig_complete_eval, _orig_predict_eval, _predicted, _orig_build_chart


def unpatch_micro_wins(saved):
    import lexic.parsing_2.engine as engine_mod
    import lexic.parsing_2.ops as ops_mod

    orig_complete, orig_predict, _, orig_build_chart = saved
    ops_mod.Complete.eval = orig_complete
    ops_mod.Predict.eval = orig_predict
    engine_mod.BuildChart.eval = orig_build_chart


# ─── Scaling sweep helper ─────────────────────────────────────────────────────


def make_rep_grammar(n_rules: int) -> IrAst:
    """Grammar: N single-char rules, root = 1*(choice), choice = r0 / r1 / ..."""
    rules = []
    refs = []
    for i in range(n_rules):
        name = f"r{i}"
        body = IrAlternation(IrSequence(IrItem(IrLiteral("A"))))
        rules.append(IrRule(name, body))
        refs.append(IrRuleRef(name))
    alts = [IrSequence(IrItem(ref)) for ref in refs]
    choice_rule = IrRule("choice", IrAlternation(*alts))
    rules.append(choice_rule)
    rep_item = IrItem(IrRuleRef("choice"), IrQuantifier(1, IrNone))
    root_rule = IrRule("root", IrAlternation(IrSequence(rep_item)))
    rules.append(root_rule)
    return IrAst(rules=IrSeq(*rules), start="root")


def main():
    print("=" * 70)
    print("RADICAL PROTOTYPE — Bet 1 (left-recursion) + Bet 2 (micro-wins)")
    print("=" * 70)

    norm_grammar = _normalize(ABNF_GRAMMAR)

    # ── Baseline ──────────────────────────────────────────────────────────
    print("\n── Baseline (current: right-recursive) ──")
    baselines = {}
    for repeat in (1, 2, 4):
        text = make_input(repeat)
        n = max(3, 30 // repeat)
        print(f"\n  x{repeat} ({len(text)} chars, {n} runs):")
        r = bench_label("recog", lambda t: earley_recognize(norm_grammar, t), text, n)
        p = bench_label("parse", lambda t: earley_parse(norm_grammar, t), text, n)
        baselines[repeat] = (r, p)

    # ── Bet 1: left-recursive ─────────────────────────────────────────────
    print("\n── Bet 1: left-recursive desugaring ──")
    print("  Checking recognition correctness...")
    patch_left_recursive()
    try:
        left_norm = _normalize(ABNF_GRAMMAR)
        ok = bool(earley_recognize(left_norm, BASE_TEXT))
        print(f"  Recognition on BASE_TEXT: {'PASS' if ok else 'FAIL'}")

        rule_count_orig = len(list(norm_grammar.rules))
        rule_count_left = len(list(left_norm.rules))
        print(f"  Rules (orig={rule_count_orig}, left={rule_count_left})")

        bet1 = {}
        for repeat in (1, 2, 4):
            text = make_input(repeat)
            n = max(3, 30 // repeat)
            print(f"\n  x{repeat} ({len(text)} chars, {n} runs):")
            r = bench_label(
                "left-recog", lambda t: earley_recognize(left_norm, t), text, n
            )
            p = bench_label("left-parse", lambda t: earley_parse(left_norm, t), text, n)
            br, bp = baselines[repeat]
            print(f"    recog speedup={br / r:.2f}x  parse speedup={bp / p:.2f}x")
            bet1[repeat] = (r, p)
    finally:
        unpatch_left_recursive()

    # ── Bet 2: micro-wins alone ────────────────────────────────────────────
    print("\n── Bet 2: micro-wins alone (right-recursive base) ──")
    saved = patch_micro_wins()
    try:
        for repeat in (1, 2, 4):
            text = make_input(repeat)
            n = max(3, 30 // repeat)
            print(f"\n  x{repeat} ({len(text)} chars, {n} runs):")
            r = bench_label(
                "micro-recog", lambda t: earley_recognize(norm_grammar, t), text, n
            )
            p = bench_label(
                "micro-parse", lambda t: earley_parse(norm_grammar, t), text, n
            )
            br, bp = baselines[repeat]
            print(f"    recog speedup={br / r:.2f}x  parse speedup={bp / p:.2f}x")
    finally:
        unpatch_micro_wins(saved)

    # ── Bet 1 + Bet 2 combined ─────────────────────────────────────────────
    print("\n── Bet 1 + Bet 2 combined ──")
    patch_left_recursive()
    saved = patch_micro_wins()
    try:
        combo_norm = _normalize(ABNF_GRAMMAR)
        for repeat in (1, 2, 4):
            text = make_input(repeat)
            n = max(3, 30 // repeat)
            print(f"\n  x{repeat} ({len(text)} chars, {n} runs):")
            r = bench_label(
                "combo-recog", lambda t: earley_recognize(combo_norm, t), text, n
            )
            p = bench_label(
                "combo-parse", lambda t: earley_parse(combo_norm, t), text, n
            )
            br, bp = baselines[repeat]
            print(f"    recog speedup={br / r:.2f}x  parse speedup={bp / p:.2f}x")
    finally:
        unpatch_micro_wins(saved)
        unpatch_left_recursive()

    # ── Scaling sweep ─────────────────────────────────────────────────────
    print("\n── Scaling sweep: right-rec vs left-rec on rep_grammar ──")
    print(
        f"  {'N':>5}  {'chars':>5}  {'right-rec ms':>13}  {'left-rec ms':>12}  {'speedup':>8}"
    )

    for n_rules in (10, 20, 50, 100, 200, 400):
        g = make_rep_grammar(n_rules)
        text = "A" * n_rules
        n_bench = 3

        right_norm = _normalize(g)
        r_best = min(time_it(lambda t: earley_recognize(right_norm, t), text, n_bench))

        patch_left_recursive()
        try:
            left_norm = _normalize(g)
        finally:
            unpatch_left_recursive()
        l_best = min(time_it(lambda t: earley_recognize(left_norm, t), text, n_bench))

        speedup = r_best / l_best if l_best > 0 else float("inf")
        print(
            f"  {n_rules:>5}  {len(text):>5}  {r_best * 1e3:>13.3f}  {l_best * 1e3:>12.3f}  {speedup:>8.1f}x"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
