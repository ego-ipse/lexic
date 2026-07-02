# PLAN — parsing_2 performance, round 2 (post int-kernel)

Date: 2026-07-02, branch `parse_proto_proto`. Produced by plan-perf agent; unreviewed by user. All numbers measured that session on this machine via `uv run python zzz_current_work/bench_parsing.py` and scratch experiments (Kernel subclasses in /tmp — **no src changes, nothing committed**).

Verified baseline (x4 = 3680 chars, interleaved medians): recognize **29.2ms / 0.40×** Lark, parse **131.0ms / 1.26×**, product parse+reduce **57.1ms / 0.53×**. Fixpoint True. Grammar-compile time excluded on both sides throughout, as before.

## 1. Where time actually goes NOW (fresh profiles; the postleo profiles are obsolete)

cProfile at x4 (10 reps; ~3× inflation, shares are what matter) + uninstrumented median stage decomposition:

| path | stage split (real, x4) | top functions (share of path, cProfile) |
|---|---|---|
| recognize (29ms) | kernel ≈ 100% | `_seed` 21% cum (0.292/0.942s), `_complete` 10% self, set.add 9%, dict.get 8%, `_try_leo`+`_leo_sole` ~9% |
| parse (131ms) | kernel(plain,links) **96.8ms** + FastTree **29.7ms** | `_close` 68% cum (2.563/3.781s), `_seed` 21% cum, `_complete` 30% cum, FastTree `_step` 25% cum, 2.8M dict.get = 8% |
| product (57ms) | kernel(collapsed,links) **37.4ms** + FusedReduce **18.8ms** | kernel ≈ 62% (`_seed` 17% cum, `_complete` 23% cum), fold ≈ 34% (`_step` cum; body-eval ~12%, `_collect`+`predecessor_chain` ~10%) |

x8 profiles are shape-identical (linear scaling). Chart shape on the ABNF x4 workload (measured):

| tables | items | items/char | link keys | scan steps |
|---|---|---|---|---|
| plain (parse path) | 121,042 | 32.9 | 36,508 | 3,680 (all per-char) |
| reducer-collapsed (product/recognize) | 45,014 | 12.2 | 14,744 | 2,192 (992 charclass + 1,200 runs) |

Runs cover 73% of columns; every links bucket has exactly one family on this workload; 45% of columns are fully empty (mid-run). **Key structural fact: 29,587 of 45,014 items (66%) are dot-0 prediction seeds, and `_seed` is the #1 self-time function on every path.**

## 2. The parse-at-1.26× gap — explained and adjudicated

The parse path pays two things the fused product path doesn't:
1. **Plain per-char tables.** `parse`'s contract is the exact reducer-agnostic ParseTree (synthetic chain shapes included), so it gets no run collapse today: 2.69× the items, 2.5× the link keys. This IS the kernel gap: 96.8ms vs 37.4ms.
2. **FastTree materialisation.** 21.5k ParseTree+IrSeq nodes with memo churn (29.7ms) vs the fold's direct-to-IR 2.5k reduce closes (18.8ms).

**Callers: `parse` has zero production callers.** Only tests import it (tests/unit/lexic/grammars/test_abnf_2.py, tests/performance/test_lazy_forest_perf.py, parsing_2's own suites). The product pipeline goes exclusively through `parse_reduced`. Verdict: not worth a dedicated high-risk effort. Phase 1 pulls parse to ~1.13× for free; Phase 2 (optional) can take it to ~0.5× if the public number matters; otherwise document it as the exact-tree diagnostic path.

## 3. Phase 1 — seed-layout lever (the one measured kernel win)

**Proof by construction:** a dot-0 item is created only by `_seed`, and `_seed` runs at most once per (column, rule) — both call sites are `predicted`-guarded (kernel.py:177-182, run() line 156-157). Advanced items (completer, scanner, nullable-advance, Leo top) always carry dot ≥ 1, and every dotted position has a globally unique code, so a seed can never collide with anything in `seen`. The per-seed membership test AND the `seen.add` are pure waste — ~29.6k redundant set-op pairs per x4 product parse.

Landing shape (measured as a subclass experiment):
- At table-build time, add a `CodeTables` column: per rule, `tuple((code << ORIGIN_BITS, next_sym[code]) for code in rule_dot0[rid])`.
- `_seed` loops those pairs: `new = shifted | i`, append to `cols`, file into `waiting`/`scannable` by the precomputed sym — no `seen` test, no `seen.add`, no `next_sym` indexing.

**Measured (kernel-only, x4, medians; chart asserted byte-identical — cols, links, accept all equal):**

| kernel | base | seed lever | Δ |
|---|---|---|---|
| product (collapsed+links) | 37.8ms | 33.3ms | **−11.8%** |
| parse (plain+links) | 99.1ms | 87.8ms | **−11.4%** |
| recognize (collapsed, no links) | 28.4ms | 23.7ms | **−16.6%** |

**Projected bench (x4): product ≈ 52ms → ≈0.49×; parse ≈ 117ms → ≈1.13×; recognize ≈ 24.5ms → ≈0.34×.**

A stronger variant (also skipping the `cols` append for scan-facing seeds, which are inert in `_close`) measured only ~0.5–2% more (−12.2/−13.9/−15.8%), was verified output-identical (accept, links, product IR, ParseTree, x1 fixpoint) but changes `cols` observability — test_kernel.py column-content assertions would need deliberate porting. **Recommendation: land the plain variant** (byte-identical state, same win); record the stronger variant as measured-and-declined.

- Risk: minimal. One method + one table column, all inside the sanctioned compiled-form zone; purity ruling untouched.
- Gate: x4 bench recognize ≤ 0.36×, parse ≤ 1.17×, product ≤ 0.51×; 1205 tests green; ambiguity + property suites; ABNF fixpoint; N=60,000 right-recursion canary; ruff, pylint 10.00, pyright 0 on parsing_2.
- Tripwires: the no-collision proof depends on (a) both `_seed` call sites staying `predicted`-guarded, (b) no future code minting dot-0 items outside `_seed`. State both as invariant comments at the `_seed` site.

## 4. Phase 2 (optional — decide before starting) — parse on collapsed tables with run re-expansion

Take `parse` below 1× by running its kernel on **grammar-proved** collapsed tables (`recognition_tables`' proof set — reducer-independent) and having FastTree re-expand each run child into the exact synthetic-chain ParseTree. Re-expansion is deterministic by the existing collapse proofs: derivation uniqueness means each run char maps to exactly one unit-arm chain — precompute per RunTerm a char → interned unit-subtree map and rebuild the right-recursive `__rep` chain (star/plus/empty-arm shape from `has_empty`) over the run text.

- Estimate: kernel ~33ms (Phase-1 collapsed) + tree ~16–20ms (14.7k links instead of 36.5k, ~2 allocs per run char over ~2.9k chars) ≈ **50–55ms → ~0.5×**, matching the product row.
- Risk: highest of the plan — new correctness surface is exact tree equality with the plain path. Gate on a property test `collapsed_parse(text) == plain_parse(text)` across all suite grammars + hypothesis inputs, plus the ambiguity suite; any FastTree fast-path miss falls back to a fresh plain-tables parse (the exact fallback contract ParseReduced already has). Must NOT be reducer-aware — parse stays reducer-agnostic.
- EV: medium. Real speedup, no production caller behind it. Schedule only if the public parse number is worth ~a day of correctness work; otherwise skip.

## 5. Phase 3 — consolidation

README §12 bench-table refresh; document parse as the exact-tree/diagnostic path (with the §2 explanation) if Phase 2 is skipped; `bench_parsing.py --save` new baseline; postleo-style OUTCOME note; wiki log entry.

## 6. Kill list (all measured this session — do not revisit without new evidence)

| idea | measured result | verdict |
|---|---|---|
| Fuse advance+record passes in `_complete`/`_scan` | −1.8% product kernel, **+1.4% parse, +4.3% recognize** | noise — KILL |
| defaultdict waiting/scannable buckets | **+7.3% worse** (2×N per-column defaultdict allocation swamps the saved gets) | KILL |
| `_scan` early-out on empty scannable (45% of columns) | +0.8% — the branch costs what `terms_for` saves | KILL |
| Single-family links (bare tuple, promote on 2nd) | **+1.7% worse on the write side alone**, before reader complexity; buckets are already all size-1 | KILL |
| Wider run-terminal coverage | remaining 992 per-char scans are structural singles (`=` 136, `"` 136, `\n` 136, `*` 76, `/` 64, `%`+`x` 80, rulename-head ALPHA 344); all 6 repetition rules already collapse — **nothing left to widen on this workload** | KILL |
| Compound-lexeme regex compilation (collapse whole YIELD-pure regular rules, e.g. `rulename`) | bounded by 344 head scans + ~7–10% of items ⇒ ≤5–8% product, for regex derivation + new follow/reducer proof surface | DEFER — negative EV vs Phase 1's one-method win |
| Per-parse container churn / lazy KernelState | construction is 2–3% of run time (1.19ms of 37.3ms at x4) | KILL |
| Repacking ORIGIN_BITS for single-digit handles | needs origin ≤ 11 bits → 2047-char input cap | KILL |
| FusedReduce alloc reduction | 0.5MB peak per x4 parse — no churn problem exists | KILL |
| Normalize-time work | outside the race (compile time, excluded like Lark() construction) | N/A |

## 7. Standing constraints (unchanged)

Purity ruling stands: seed-pair tables live in tables.py, the loop in kernel.py — both inside the compiled-form zone; orchestration/normalize/reduce-policy stay IR-native. Full SPPF semantics, parse raises on ambiguity, N=60k canary, pure Python, 1205 green + ruff + pylint 10.00 + pyright 0 at every landing.

**Bottom line:** the engine is near the pure-Python floor; the profile supports exactly one high-EV change. Phase 1 is roughly a one-method landing for product 0.53× → ~0.49×, recognize 0.40× → ~0.34×, parse 1.26× → ~1.13×, with byte-identical charts. The parse gap is fully explained (plain per-char tables 2.69× items + FastTree materialisation) and has no production caller; Phase 2 is specced but explicitly optional. Everything else was measured dead and is documented above so it stays dead.
