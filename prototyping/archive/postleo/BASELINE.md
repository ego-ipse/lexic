# Baseline — before vs after the `leoparse` commit

Measured on this machine with the **HEAD** harness (`zzz_current_work/bench_parsing.py`)
run against both commits, so the measurement code is identical across the comparison.

- **BEFORE** = `1df8365 wip` (parent of leoparse) — raw: `bench_before_leoparse.txt`, `rightrec_before_leoparse.txt`
- **AFTER**  = `da0ee2d commitdocs` (== `5af435d leoparse` code + postmortem doc; present HEAD) — raw: `bench_after_leoparse.txt`, `rightrec_after_leoparse.txt`

## A. Product metric — ABNF self-host, text→IrAst (plain bench, no `--rightrec`)

`parse+reduce` vs `lark:full`. Full raw output in `bench_{before,after}_leoparse.txt`.

| stage | input | BEFORE earley med | BEFORE e/lark | AFTER earley med | AFTER e/lark |
|---|---|---|---|---|---|
| recognize | x4 (3680) | 154.2 ms | 2.01x | 153.1 ms | 2.10x |
| parse | x4 (3680) | 312.7 ms | 2.95x | 298.7 ms | 2.90x |
| **parse+reduce** | **x1 (920)** | 80.7 ms | **2.98x** | 81.7 ms | **3.06x** |
| **parse+reduce** | **x2 (1840)** | 164.5 ms | **3.06x** | 165.8 ms | **3.10x** |
| **parse+reduce** | **x4 (3680)** | 372.6 ms | **3.42x** | 354.9 ms | **3.32x** |

Fixpoint canary (earley IrAst == lark IrAst): **True** both.
At x4 earley ≈ 96 µs/char vs lark ≈ 29 µs/char.

The product metric barely moved — the ABNF gap is **constant factor**, not asymptotic.

## B. Asymptotic — deep right-recursion `S = "a"*`, parse→tree (`--rightrec`)

| N | BEFORE µs/N | BEFORE e/lark | AFTER µs/N | AFTER e/lark |
|---|---|---|---|---|
| 100 | 70.4 | 2.8x | 21.4 | 0.8x |
| 200 | 123.6 | 4.8x | 20.7 | 0.8x |
| 400 | 247.2 | 10.1x | 20.3 | 0.8x |
| 800 | 516.6 | 20.7x | 20.4 | 0.8x |
| 1600 | 1077.8 | 43.5x | 20.8 | 0.8x |

**BEFORE: O(n²)** (µs/N grows linearly, blows to 43.5× Lark and widening).
**AFTER: O(n)** (µs/N flat ~20, **beats Lark 0.8×** on deep right-recursion).

`recognize` was already O(n) (~8–9 µs/N, ~0.8–0.9× Lark) in both.

## Takeaway for the explorations

- leoparse delivered the **asymptotic** win on right-recursion (Leo-on-parse); neutral-to-
  slightly-better on the ABNF product metric.
- The **ABNF product metric is still 3.3× behind Lark** — pure constant factor.
- Two open fronts: (1) `parse` is ~2.9× `lark:parse` at constant factor on ABNF;
  (2) `reduce` adds ~17% vs Lark's ~4% transform.
- Transversal question — *why is parsing super-linear?* — on ABNF it is **not** super-linear
  in the leoparse build; it is a constant-factor gap. Super-linearity only showed on
  pathological deep right-recursion, which leoparse fixed. Each exploration should report
  **both** the plain bench (A) and the `--rightrec` asymptotic (B), and check whether residual
  super-linear behaviour remains on other grammar shapes.
