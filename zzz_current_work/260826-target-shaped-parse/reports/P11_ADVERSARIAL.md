# P11 adversarial review, pass 4 — final

**Scope.** Full re-run of every prototype, a read of each mechanism changed
since pass 3 (the iterative fold, the widened differential, the cycle-pricing
ladder, the class-attribute gc lane, the four low fixes), and targeted attacks
on the three things the lead named: the iterative fold's value-lane arithmetic
under mixed kid types, whether walking `vars(type)` reintroduces a globals
escape, and whether deep-cycle charts still hold with islands and with sibling
roots. Same rules throughout: `uv run`, harness imports from the proto
directory, Qwen rows alone under `tools/guarded.sh`, strictly sequential.

**Verdict: READY.** Every pass-3 finding is fixed, I could not break any of the
three attack surfaces, and nothing new of substance turned up. Two one-line
staleness nits in the report's gate list are listed at the end; neither changes
a conclusion.

---

## Pass-3 findings: verification

| pass-3 finding | status | evidence from my re-run |
|---|---|---|
| **§1 blocker** — recursive cycle fold, `RecursionError` at 2,001 chars | **fixed** | `_tree_policy_meaning` is an explicit two-phase stack; `deep-cycle-pad2000` is a differential case and passes with `another_meaning=True`. My own deep probes now pass at 2,001 and 2,004 chars. Correctness attacked separately in §1 below |
| §2 — circular oracle on the cycle case | **fixed** | the `name != "unit-cycle"` exclusion is gone; fresh run shows `unit-cycle … another_meaning=True AGREE` and `deep-cycle-pad2000 … another_meaning=True AGREE`. The report states plainly that on cycle cases the enumeration oracle shares the fallback's implementation and the independent check is `another_meaning` |
| §3 — Cartesian cycle path unpriced | **fixed** | `cycle-fallback-pricing arm_points=1/2/3 → one_lap_ops=4/10/20, retained=3/8/16`, printed with the 2^k note; the rejection is reworded to "accepted solely as the bounded, 2^k-priced cycle fallback" in the conclusions, the mechanism verdicts, and the failed-candidates list |
| §4 — "verbatim" conflated mechanism with relation | **fixed** | conclusion 1 separates the TERMINATION mechanism (verbatim) from the RELATION (deliberately broader, interaction-exact); the printed `invariant` line itself now carries "on a CYCLIC chart the relation is one-lap-bounded (both here and in production) … strictly broader than production's single flips" |
| §5a — multi-root sky skip undocumented | **fixed** | code comment plus report caveat ("skipped under sibling accepting roots — sound, it only ever forgoes an early exit"), and it is in the printed invariant line too |
| §5b — gc walk blind to class attributes | **fixed** | `class Holder: artefact = g` → `True`, with no globals escape (§2 below) |
| §5c — unguarded `cell_contents` | **fixed** | `try/except ValueError: continue` |
| §5d — stale B conclusion string | **fixed** | now "covers the vocab, merge, **pipeline**, and verdict lanes" |

Repo hygiene: `git status --porcelain` shows exactly the five round files (plus
tracked `__pycache__`/`.ruff_cache` noise); `git diff --stat -- src tests` is
empty staged and unstaged; the planning documents are untouched (mtimes
12:33–12:39, hours before this pass's 17:05–17:06 edits). `5 files already
formatted`, `All checks passed!`, Pyright `0 errors, 0 warnings, 0
informations`, and the forbidden-construct grep returns only the docstring
sentence about `__qualname__` removal. §A's quoted block is byte-for-byte fresh
output: **26 quoted lines, 26 fresh lines, 0 mismatches**.

---

## 1. Attacked: the iterative fold's value-lane arithmetic — correct

The concern was an off-by-one silently reordering children. I
differential-tested the iterative fold against an independent recursive
reference (`sys.setrecursionlimit(100000)` so the reference survives the depth),
across four grammars chosen for hostile kid shapes and five policies including
the order-sensitive `swap`/`wrap`:

```
cd /home/mika/projects/lexic/zzz_current_work/260826-target-shaped-parse/proto
uv run python -c "<inline: iterative vs recursive fold over every FastTree derivation>"

literals-interleaved   trees=  2 nodes=   5 literals=   5 multi_kid_nodes=  1 -> ok
asym-nested            trees=  2 nodes=   6 literals=   6 multi_kid_nodes=  2 -> ok
sibling-roots          trees=  2 nodes=   3 literals=   2 multi_kid_nodes=  0 -> ok
deep-list              trees=  4 nodes= 604 literals= 301 multi_kid_nodes=301 -> ok
total comparisons: 50  mismatches: 0
```

The specific mixed-kid case needed a delegated leaf sitting *between* two
subtree kids, which none of those grammars produce, so I built one
(`root ::= a "(" t ")" b` with `t` delegated):

```
root kid kinds: ['ParseTree', 'IrLiteral', 'PayloadLeaf', 'IrLiteral', 'ParseTree']
  {}                            -> ('root', ('a',), ('t', ('pair', ('onetwo',))), ('b',))
  {'root': 'swap'}              -> ('root', ('b',), ('t', ('pair', ('onetwo',))), ('a',))
  {'root': 'wrap'}              -> ('root', ('layer', ('a',), ('t', …), ('b',)))
payload-in-the-middle iterative == recursive: True
swap is the exact reversal of the kid lane: True
```

Eight further comparisons, each with both island alternates substituted through
the override table. The payload keeps its middle slot, subtree values land in
their original positions, literals are dropped in both implementations, and
`swap` is an exact reversal — a reordering bug would have surfaced here. The
`taken`/`position` arithmetic also degenerates correctly for leaf nodes
(`del values[len(values):]` deletes nothing).

Whole-file cost is unchanged: `ambiguity_interaction.py` runs in **1.67 s** with
the 2,001-character deep-cycle case included.

---

## 2. Attacked: does walking `vars(type)` reintroduce a globals escape? — no

```
uv run python -c "<inline: five retention shapes through the gc walk>"
class ATTRIBUTE via instance      -> True      (pass-3 residue, now caught)
method __globals__ (must be False)-> False     (no escape)
staticmethod/property closure     -> True      (descriptors traversed to their functions)
generator in a class attr         -> False     (no frame/f_globals escape)
real bound view -> False   walk wall=0.6 ms
```

The design holds. Class dicts are walked, but every callable found there — plain
function, `staticmethod`, `classmethod`, `property` — routes through the
`FunctionType` branch that follows `__closure__` and `__defaults__` and never
`__globals__`. I checked the two escapes that would have made this unsound in
the other direction (false positives that would fail an honest binding): a
method whose module globals hold a `CompiledGrammar` is not reported, and a
generator in a class attribute does not leak `f_globals` through its frame. The
walk still answers `False` for the real bound view, in 0.6 ms, so the added lane
costs nothing.

---

## 3. Attacked: deep cycle combined with islands and with sibling roots — holds

```
deep-cycle + sibling roots: chars=2001 cycle=YES accepting_roots=2 value_sets=True hybrid=True another_meaning=True -> AGREE
deep-cycle + islands:       chars=2004 cycle=YES seeds=1 value_sets=True hybrid=True ops=4010
  same chart, dropping w:   value_sets=False (expected False)
```

Both combinations detect the cycle, take the one-lap fallback, survive the depth
that killed pass 3, and return the right verdict — including the dropping
negative on the same deep cyclic island chart, which is the case that would
expose an over-refusal. The island combination folds 4,010 operations at that
depth, which is the fallback's expected nodes × 2^k shape and is now disclosed.

---

## 4. Numbers checked against fresh runs

All structural counts match exactly; timings vary in the usual band.

- **§A**: 26/26 lines verbatim (mechanically diffed); eleven
  `chart-differential` cases, all AGREE; pricing ladder 4/10/20 ops.
- **§B Qwen**: `entries=151669 merges=151387 pipeline_specials=26`; tokenizer
  `merges` and `pipeline` both `equal=False` (1.384 / 1.423 s cold total against
  0.073 / 0.074 s document-level); `duplicate` verdict delta present; retained
  81,422,768 B (report 81.4 MB). Reader setup 107.5 s CPU / 16.8 s wall,
  excluded from the structure rows.
- **§C / §E**: outputs identical to the quoted blocks modulo timing digits.
- **§D**: unchanged this pass (`ambiguity_rss.py` mtime 16:49 predates the
  17:05–17:06 edits), and I verified every figure in pass 3 against this exact
  file content: array bytes 448,340 / 1,792,340 / 7,168,340; structure-retained
  1,265,820 / 4,785,812 / 18,762,596 → 316.4 / 299.1 / 293.2 B/char, 6.0–6.5×;
  `post_release_residual_bytes=8328`; `two-key-parity keys=2 cone_sizes=[3, 3]
  shared_ancestors=2 distinct=True`; frames 96.2–98.2 B/frame.

---

## 5. Two staleness nits (non-blocking, one line each)

- **The gate list says "ten charts"; there are eleven.** Conclusion 1 correctly
  says "eleven-case", but the *Conclusively closed* bullet still reads "an
  independent exhaustive-enumeration oracle on ten charts (siblings, negatives,
  a unit cycle, shared nodes)" — the `deep-cycle-pad2000` case added this pass
  is missing from both the count and the parenthetical. A fresh run prints 11.
- **"counted cold-root-only constructor traffic"** survives in the same bullet,
  contradicting the §E body's own pass-3 correction, which restates it as the
  single-call-site structural property. Drop the word here too.

---

## Reproduction log

Sequential; the Qwen row alone under `tools/guarded.sh 8G 900`.

| command | outcome |
|---|---|
| `uv run python ambiguity_interaction.py` | exit 0, 1.67 s; 11/11 differential cases AGREE; pricing ladder printed; §A verbatim 26/26 |
| `uv run python resolver_pair.py` | exit 0; identical to §C modulo timings |
| `uv run python custom_class_target.py` | exit 0; identical to §E modulo timings |
| `uv run python keyed_product_rows.py` | exit 0; seven kinds × five products at 128 and 8,192; conclusion string names the pipeline lane |
| `tools/guarded.sh 8G 900 -- … --mode qwen` | exit 0, 44 s wall / 120 s CPU; merges and pipeline both refused |
| `ruff format --check` / `ruff check` / `pyright` | `5 files already formatted`, `All checks passed!`, `0 errors, 0 warnings, 0 informations` |
| forbidden-construct grep | one hit: the docstring sentence about `__qualname__` removal |
| `git status --porcelain`, `git diff --stat -- src tests` | exactly the five round files; src/tests empty; planning docs untouched |
| iterative-vs-recursive fold differential | 58 comparisons across 5 grammars × 5 policies, including a payload between two subtree kids; **0 mismatches** |
| gc-walk retention shapes (5) | class attribute caught; no globals escape via methods, descriptors, or generators; real view clean in 0.6 ms |
| deep-cycle + islands / + sibling roots | both detect the cycle, survive depth, agree with production where checkable, and give the right dropping negative |

Nothing failed to reproduce, and no probe I ran produced a disagreement with
production `another_meaning` anywhere it is a valid oracle.

---

## Verdict

**READY.**

No blocking findings. Both pass-2 blockers and the pass-3 blocker are fixed and
independently verified — I re-derived the fold's correctness against my own
reference implementation rather than trusting the harness, attacked the gc
walk's new lane from five directions including the two false-positive escapes,
and ran the deep-cycle combinations. The four pass-3 disclosure items (relation
versus mechanism, the one-lap-bounded invariant, 2^k pricing, oracle
circularity) are all stated in the report, and two of them are carried in the
program's own printed `invariant` line, which is the right place for them.

Before delivery, fix the two nits in §5 — the gate bullet's "ten charts" →
eleven with the deep-cycle case named, and the leftover "counted". Both are
one-line edits to `PROTOTYPE_11.md`; neither affects a conclusion, a number, or
a gate.

Standing residues, already recorded in the report and correctly classified as §8
production obligations rather than closed items: per-edge `choice_free`
granularity (the certificate is inert below any packed arm choice),
dictionary-free dense numbering for the flat index, and the shared-node meet on
production-shaped charts — the last of which this round's witnesses now exercise
at prototype scale.
