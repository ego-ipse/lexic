# T10 — proved runs in C: measured, implemented, REVERTED

**Negative result.** The gap is real but narrow, and closing it does not pay
across the bench. Two shapes were implemented and measured; one bench row
improves, five do not, and short inputs regress. Nothing shipped — `src/`,
`tests/` and `tools/` are byte-identical to `34f16a7`, and `tools/run_checks.sh`
EXIT=0 on the reverted tree.

Three things are worth keeping: the ceiling (a count, not an estimate), the
finding that the regex-free scheme beats `re` outright, and the reason the
premise is narrower than it looks.

---

## 1. The ceiling — measured first, and it kills most of the task

Fraction of corpus characters consumed inside licensed run loops, by
instrumenting the real parses (PDA `match_cc`/`match_lit` quantifier loops;
Earley `Kernel._run_end`).

| grammar | chars | run chars | % of corpus | run calls | mean run len | calls consuming ≤1 char |
|---|---|---|---|---|---|---|
| arithmetic | 4,000 | 0 | 0.0% | 0 | — | — |
| csv | 12,539 | 11,220 | 89.5% | 1,320 | 8.50 | 0 |
| json | 2,403 | 1,251 | 52.1% | 1,153 | 1.08 | 970 (548 of length 0) |
| gbnf-meta | 1,377 | 0 | 0.0% | 0 | — | — |
| abnf-meta | 2,020 | 0 | 0.0% | 0 | — | — |
| vyx | 3,461 | 2,141 | 61.9% | 910 | 2.35 | 358 |

**Three of six grammars have no run-shaped items at all**, in either engine. No
run optimisation can move them by construction. Their characters go through
`vstr_once` — one model built per iteration (arithmetic 2,976 `vstr` calls for
4,000 chars; abnf-meta 2,060 for 2,020; gbnf-meta 1,148 for 1,377). That work
cannot be delegated to C without changing what the parse returns, which is
exactly what `@lexical` (T9) already does.

So the brief's premise — "lexic executes runs as Python where the competitors
use C" — is true but narrow: on most of the bench, lexic's per-character work is
not in a run loop at all. And where it IS, run length decides everything: json's
mean run is 1.08 characters, so there is nothing for a C primitive to amortise
over.

The Earley side is separately hopeless: its run chars are the same, but its
µs/char is 13-41 (chart work dominates), so the run loop is a rounding error
there. Every Earley A/B row landed inside ±0.66% — see §4.

## 2. The regex-free scheme beats `re`, and that part is a clean win

Per run call, on the measured length distributions, using the real compiled arms:

| scheme | csv (mean 8.5) | json (mean 1.08) | vyx (mean 2.35) |
|---|---|---|---|
| per-char loop (today) | 763-801 ns | 257-260 ns | 444-452 ns |
| compiled `re`, `pattern.match(text, pos).end()` | ~158 ns | ~152 ns | ~145 ns |
| translate mask + `str.find` | **288 ns** | **219 ns** | **303 ns** |

The mask: build a two-symbol image of the input per gate — one sentinel where
the gate takes, another where it does not — then the run end is
`mask.find(STOP, pos)`. It is **exact, not FOLLOW-driven**: the translate table
answers for every character, so `find` lands on the index the per-character loop
would stop at, on malformed input exactly as on well-formed. The refusal
frontier therefore cannot move — no reasoning about FOLLOW enters at all, so the
predecessor's `PdaFail.pos` caution simply does not apply to it.

Two details that made it viable:

- The translate table is built from the **charset** (a `defaultdict` whose
  default carries the gate's polarity), not from the input's alphabet. Building
  it from `set(text)` costs 50.3 µs on a 12.5 KB corpus; from the charset, 2.4
  µs — and the two masks are byte-identical (asserted).
- A gate charset may carry the EOF sentinel `""`, which has no ordinal. End of
  input is the mask's LENGTH, so the sentinel is simply not in the table.

**The FOLLOW-driven `find` candidate is dead on arrival here**, for a reason
unrelated to the frontier: the bench's run charsets are large POSITIVE sets (63,
64, 62, 10, 4 characters), so their stop sets are co-finite and cannot be
enumerated. Only vyx has one co-finite run charset, and its stop set has 61
members — 61 `str.find` calls per run.

So the bonus the user asked for wins on the primitive, and the `re` waiver's
condition is **not met**: `re` measured strictly worse than the regex-free
scheme on every row, and regressed json by +5.18% end to end.

## 3. What was implemented, and what it measured

`RunMasks` (a per-parse `dict` from gate `id` to mask, on `PdaKernel`), a
process-level memo of translate tables, and `match_cc` rewritten to consult it.
Threaded through `match_arm` / `vstr_once` / the driver — no optional channel.
Two variants, both measured with T8's protocol (in-process, interleaved, arms
swapped between rounds, `gc` off, 31 rounds, product equality and `to_text`
byte-identity asserted per row before any timing):

**Variant A — mask on every unbounded run.**

| case | chars | per-char | mask | Δ |
|---|---|---|---|---|
| arithmetic | 4,000 | 3.107 | 3.051 | −1.81% |
| csv | 12,539 | 0.799 | 0.758 | **−5.10%** |
| json | 2,403 | 1.898 | 1.937 | +2.06% |
| gbnf-meta | 1,377 | 4.895 | 4.884 | −0.21% |
| abnf-meta | 2,020 | 5.785 | 5.846 | +1.04% |
| vyx | 3,461 | 4.883 | 4.891 | +0.16% |
| csv (2 rows) | 95 | 1.025 | 1.015 | −0.99% |
| csv (1 cell) | 1 | 9.238 | 10.307 | **+11.57%** |
| json (1 row) | 48 | 2.413 | 2.568 | **+6.43%** |
| json (tiny) | 10 | 3.515 | 4.010 | **+14.11%** |

csv pays, short inputs pay for it. The prepass is O(n) per gate and a tiny input
has nothing to amortise it over.

**Variant B — walk two characters, then let the mask finish.** Two is where the
mask starts paying, so a grammar whose runs are all short never images its input.

| case | chars | per-char | control (noise) | mask | Δ | Δ, repeat run |
|---|---|---|---|---|---|---|
| arithmetic | 4,000 | 2.973 | +0.12% | 2.975 | +0.07% | +0.56% |
| csv | 12,539 | 0.824 | +0.25% | 0.791 | **−3.97%** | **−3.34%** |
| json | 2,403 | 1.845 | +2.94% | 1.874 | +1.53% | +1.30% |
| gbnf-meta | 1,377 | 4.863 | +0.81% | 4.876 | +0.27% | +0.22% |
| abnf-meta | 2,020 | 5.726 | +0.03% | 5.748 | +0.38% | +0.53% |
| vyx | 3,461 | 4.730 | −0.48% | 4.734 | +0.10% | +0.71% |
| csv (2 rows) | 95 | 1.026 | −3.14% | 1.023 | −0.36% | +3.02% |
| csv (1 cell) | 1 | 9.069 | +0.49% | 9.011 | −0.63% | +5.63% |
| json (1 row) | 48 | 2.458 | +0.22% | 2.486 | +1.14% | +2.26% |
| json (tiny) | 10 | 3.674 | +1.12% | 3.677 | +0.06% | +0.32% |

`control` is the per-char arm reached through one extra frame — a true noise
reading for the baseline. The three grammars with ZERO run calls do identical
work in both arms, so their spread (+0.07% to +0.56%) is the honest noise floor
of the whole table.

**The verdict is in the last two columns.** Only csv is reproducibly positive
(−5.10 / −3.97 / −3.34 across variants and runs). json is reproducibly slightly
NEGATIVE (+1.53 / +1.30 / +2.06). The short rows do not reproduce: run 1 says
−0.99 / −0.63 / +1.14, run 2 says +3.02 / +5.63 / +2.26 — the same tree, the
same protocol, opposite signs. A change whose sign flips between runs on a third
of its rows has not demonstrated a win.

So: one bench row gains 3-5%, one loses ~1.5%, three cannot move, and the short
inputs are unstable. That does not carry the machinery.

## 4. Earley: nothing, everywhere

Same protocol, the mask (and `re`) wired into `Kernel._run_end`:

| grammar | plain µs/char | re Δ | mask Δ |
|---|---|---|---|
| arithmetic | 61.879 | +0.55% | +0.41% |
| csv | 13.174 | +0.11% | +0.14% |
| json | 34.489 | +0.56% | +0.09% |
| gbnf-meta | 64.336 | +0.11% | +0.04% |
| abnf-meta | 60.629 | −0.66% | −0.26% |
| vyx | 48.739 | +0.56% | −0.28% |

Every cell inside noise, csv included, despite its 89.5% run share. Earley's
per-character cost is chart work; the run walk is not where its time goes. I
would not touch `_run_end` on any future attempt at this.

## 5. The frontier gate — passed, and it was never the risk

639 refusal observations (597 `PdaFail`, 42 accepted) across the six bench
grammars and six purpose-built ones: every `rejects` fixture, truncations of
each corpus at 17-character strides, each truncation poisoned with `\x00`,
`\x01` and `�` (the two mask sentinels and a non-ASCII character), plus
mandatory-run misses, `*` vs `+` bounds, a co-finite `[^"]*` run, a `{2,4}`
bounded run, and inputs made entirely of the sentinel characters. Recorded as
`(type, PdaFail.pos, message)` before the change and re-recorded after each of
the four implementation revisions.

**Byte-identical every time.** The full suite was green at each revision too
(4,162 passed, 8 skipped — the twelve initial failures were the matcher tests'
construction syntax, ported, plus one real bug found and fixed).

This is the expected result, and it is worth saying why: the mask is a faithful
per-character image, so it is not an approximation whose frontier needs
defending. The predecessor's caution was correctly aimed at the FOLLOW-driven
scheme, which was never viable here for a different reason (§2).

## 6. The one real bug the work surfaced

A gate charset can contain the EOF sentinel `""`, which `ord()` rejects — it
crashed five vyx round-trip tests. Worth recording because it is a live property
of `FlatArm.gate_data` that a reader of `flatten.py`'s docstring would not
predict: the sentinel appears in NEGATED stop gates in practice, not only in the
"FOLLOW-extended END position" positive case the docstring describes.

## 7. Placement, for context only (cross-process — never a verdict)

| csv | µs/char | | json | µs/char |
|---|---|---|---|---|
| lark-lalr | 0.747 | | lexic-lex-ns | 1.966 |
| lexic-lex-ns | 0.831 | | parsimonious | 2.157 |
| lexic-lex | 0.867 | | lexic-pda | 2.373 |
| lexic-pda | 0.952 | | lark-lalr | 3.584 |
| parsimonious | 1.226 | | | |

This is what made the attempt worth finishing rather than stopping at the
ceiling: csv is the one row where lexic trails lark-lalr, and it is exactly the
run-heavy shape. A −4% would have closed about a third of that gap. It did not
hold up on repeat, and it cost json.

## 8. What argued against the brief

- **"Both winning competitors delegate run recognition to compiled C."** True,
  but they delegate a whole TOKEN layer, not a run. lexic's equivalent lever is
  `@lexical` (T9, 10-17%), which cuts model count. Runs are the smaller half.
- **"Run matching becomes `pattern.match(...).end()` in both engines' run
  paths."** `re` is the wrong primitive (§2) and Earley is the wrong engine (§4).
- **"A no-op row (a grammar with no licensed runs pays ~nothing)."** Satisfied —
  and it turned out three of six bench rows ARE that row, which is the finding
  rather than the control.

## 9. If anyone picks this up again

Do not re-measure the mask; it is measured. The remaining run-shaped cost is in
`vstr_once`, not in `match_cc` — that is where arithmetic, gbnf-meta and
abnf-meta spend their characters, and it is a model-count question, not a
recognition one. That is the T9 lever, and T8 already established model count as
the dominant term.

Probes used and discarded (not in the tree): `/tmp/t10_ceiling.py`,
`/tmp/t10_ceiling2.py`, `/tmp/t10_shapes.py`, `/tmp/t10_prim.py`,
`/tmp/t10_ab.py`, `/tmp/t10_ab2.py`, `/tmp/t10_ab3.py`, `/tmp/t10_ab_final.py`,
`/tmp/t10_micro.py`, `/tmp/t10_micro2.py`, `/tmp/t10_frontier.py`, and the
frontier records `/tmp/frontier_{before,after,after2,after3,after4,after5}.json`.

## Gates

`src/`, `tests/`, `tools/` byte-identical to `34f16a7`. No commits, no
suppressions, no `pyproject.toml`, no wiki or CLAUDE.md change (nothing shipped,
so no module to document). `tools/run_checks.sh` **EXIT=0** on the reverted tree.
