# PLAN — Deep rework of `parsing_2`: obliterate Lark

Date: 2026-07-01. Baseline this machine, post-OPT-REDUCE (`7c98085`):
**product x4 = 2.22×** Lark (237.6ms vs 107.0ms), parse 1.88×, recognize 1.65×.
Fixpoint True, 1151 tests green.

---

## 1. The two decisive facts (new analysis, both verified today)

### Fact 1 — Lark is pure Python. There is no C core.

`lark 1.3.1` in this venv ships **zero compiled extensions** (`*.so` count: 0).
`lark/parsers/earley.py` is plain Python. The handover's premise ("Lark's C
Earley core", "forest built in C", "C-backed transformer") is **wrong**. Every
prior ceiling argument ("Python vs C is a constant-factor wall") was reasoning
against an opponent that doesn't exist.

### Fact 2 — Lark steps over tokens; we step over characters. 5× fewer steps.

Measured on the ABNF self-host text (920 chars): Lark's parse consumes
**182 tokens, avg 5.05 chars/token**. Its Earley chart has ~183 columns; ours
has 921. Each of our columns carries the full predict/complete/insert churn
(31.8 items/char — ~29k items vs Lark's ~2-3k), in Python. The chars *between*
token boundaries — which cost us the majority of all engine work — are consumed
by Lark inside single C `re` calls (its "dynamic lexer" matches terminals with
compiled regexes during the parse).

**So the 2.22× gap decomposes as: ≈5× step-count disadvantage × per-step costs,
partially clawed back by our leaner items.** Micro-opting the per-item cost
(all sessions to date) attacked the smaller factor. The step count is the lever
nobody has pulled.

### Corroborating profile (post-OPT-REDUCE, x4, 5 reps)

~65% chart loop (`Column.__iadd__` 0.53s, `Predict.eval` 0.46s cum 1.36s,
`Complete.eval` 0.23s, `CloseColumn` 0.29s own), ~10% `_FastTree`, ~12% reduce
(`_FastReduce` + recursive `Yield.eval` 0.24s cum), remainder spread over
1.78M `dict.get`, 2.36M `len`, 1.43M `isinstance`, 1.06M `typing.cast` (65ms —
`cast` is not free). `_try_leo` runs 145k times (once per completion) for 0.13s.

---

## 2. Target architecture — compile the grammar, then run a flat kernel

The rework separates **grammar-compile time** (once per grammar, like `Lark()`
construction — excluded from the race, exactly as Lark's is) from **parse time**
(the paid loop). Today we rebuild `RuleIndex`/`NullableRules`/`CharAccepts` on
*every parse* and then interpret IR nodes per item. Instead:

```
parsing_2/
  normalize.py     (kept; SplitLiterals REMOVED — literals stay atomic)
  compile.py       GrammarCompiler: IrAst → ParserTables.  IR-facing walk,
                   the parser's "codegen moment". Runs once per grammar.
  tables.py        ParserTables — frozen int-coded tables + compiled regexes.
  kernel.py        The flat Earley core. Ints, lists, sets, one module,
                   explicitly documented as the compiled-form zone.
  forest.py        SPPF readers (kept for derivations/ambiguity) + fused reducer
  reduce.py        Reducer policy surface (IrMap tables unchanged, public API kept)
  engine.py        IrSelf orchestration façade — public API unchanged.
```

**The architectural story:** grammar is ground truth; `ParserTables` is a
*compiled representation* of the IrAst, exactly as `codegen/` emits Python
classes from `RuleSpec`. The IR seam moves to compile time (GrammarCompiler
walks IR) and reduce time (reduction bodies stay IrMap/IrSelf). The per-char
inner loop runs over the compiled form. This needs an explicit ruling — see §6.

### Pillar A — int-coded items (per-step cost, ~3-4× on the loop)

Compile-time numbering, laid out so **dot-advance is `+1`**:

- Every `(rule, arm, dot)` position gets one int `code`; consecutive dots are
  consecutive codes (`base[arm] + dot`). Advancing an item is an integer add.
- `next_sym[code]` — one flat list: `>0` rule_id → predict; `<0` terminal_id →
  scan; `0` → complete. **Replaces every `isinstance` and the dispatch table on
  the hot path with one list index.**
- An Earley item is `code << ORIGIN_BITS | origin` — a **single int**. Column
  dedup = `set[int]` (int hashing is the cheapest membership test Python has;
  no tuple allocation per advance at all). SPPF link keys likewise packed ints.
- Per-column `waiting` / `predicted`: lists indexed by rule_id (grammar is
  small and dense after compile), not dicts keyed by objects. Kills the
  `IrScalar.__eq__` class of problems *by construction* — no IR object is ever
  a hot-path key again.
- Columns preallocated once (`len(text)+1`), not grown via `while len <= i`.

Evidence this direction works: Exploration 3's flat engine — still using
str/tuple items, per-char columns, no int packing — already hit **0.91×** Lark
on recognition. Int-packing + array indexing goes materially below that.

### Pillar B — terminal compilation: step over runs, not chars (~3-5× step count)

The step-count lever. At compile time (on the **pre-desugar** IR, where
`IrQuantifier` still exists):

1. **Atomic multi-char literals.** Delete `SplitLiterals`. A k-char literal is
   one scan atom matched by `text.startswith(lit, i)` (C), advancing origin→i+k
   in one step. `"false"` = 1 step, not 5.
2. **Regex-compiled lexical rules.** A rule/sub-expression whose body is built
   only from terminals, charclasses, quantifiers, groups and alternations of
   those (no recursion, no semantic sub-rules) denotes a **regular language**
   with a direct IR→regex rendering: `rulename = ALPHA *(ALPHA / DIGIT / "-")`
   compiles to `[A-Za-z][A-Za-z0-9-]*`. Match it with one C `re.match` per
   occurrence — this is precisely the dynamic-lexer trick Lark uses, except we
   *derive* it from the IR instead of requiring the author to declare tokens.
   ABNF's `rulename`, `wsp`/`c-nl` noise runs, digit/hex runs all qualify —
   i.e. the bulk of the 920 columns collapses into ~200 token-run steps.
3. **Correctness discipline (this is where Lark actually cheats):** maximal
   munch is only complete when the terminal's follow set is disjoint from its
   own continuation set. Compute that check per compiled terminal from the
   grammar; where it fails, either emit all match prefixes as parallel scans
   (still batched — one regex, k advances) or fall back to per-char for that
   atom. We keep full SPPF/ambiguity semantics **provably**, where Lark's
   default `lexer='dynamic'` just accepts the incompleteness silently.
4. Quantifiers that survive (over non-regular sub-rules) still desugar to
   right recursion; **Leo stays** for exactly those. With run-terminals eating
   the `C*` cases, `_try_leo`'s 145k calls/x4 mostly disappear as a bonus.

### Pillar C — fused SPPF→IrAst reduction (the product-metric lever)

Today the product path materialises 67k `ParseTree`+`IrSeq` nodes
(`_FastTree`), then walks them all again (`_FastReduce`), then `Yield.eval`
re-walks subtrees char-by-char to recover text (and RecursionErrors at
N≈1600 — the flagged pre-existing bug).

Fold the binarised SPPF **directly** into IR with one explicit-stack pass
(same frame discipline as `_FastTree`/`_FastReduce`, one pass instead of two):

- Each SPPF node already carries `(rule, origin, end)`. For rules whose
  reduction is `YIELD`, the subtree text is **`text[origin:end]`** — an O(1)
  C-level slice — minus noise sub-spans, and "can contain noise" is decidable
  per rule at compile time (ABNF's yield rules mostly can't ⇒ pure slice).
  This deletes the `Yield` recursion entirely, *fixing the RecursionError bug
  as a side effect*.
- Synthetic-rule splicing happens during the fold (as `_FastReduce` does now).
- `ParseTree`, `derivations`, `is_ambiguous`, the trampoline: **kept** as the
  general/ambiguous path. The fused fold is the unambiguous product path, with
  the same fall-back contract `_FastTree` has today.

### Pillar D — memory management

Follows from A-C rather than being separate work: items are ints (no per-item
allocation), columns preallocated, `waiting`/`predicted` are index-addressed
lists reset per parse, link buckets reuse lists, and the product path allocates
only the IR nodes that survive into the answer. The only remaining per-step
allocations are SPPF link entries — and only when `record_links` is on.

---

## 3. Why this crushes rather than matches

Budget at x4 (3680 chars; Lark full = 107ms):

| component | today | after A (flat kernel) | after B (run-terminals) | after C (fused reduce) |
|---|---|---|---|---|
| chart (recognize) | 123ms | ~65-70ms (Expl-3 measured 0.91×; int-packing below that) | ~25-40ms (3-5× fewer steps on this workload) | — |
| +links, tree | +74ms | ~35-45ms | ~15-25ms | fold absorbed below |
| reduce | +40ms | ~35ms | ~30ms | ~15-25ms total for fold |
| **product** | **238ms (2.22×)** | **~135-150ms (~1.3×)** | **~70-95ms (~0.7-0.9×)** | **~45-70ms (~0.45-0.65×)** |

Phase-A numbers are anchored to Exploration 3's *measured* engine (0.91×
recognition, 1.31× parse) rather than hope; B's multiplier is anchored to the
measured 5.05 chars/token; C's to the measured tree+reduce share (~75ms) plus
the throwaway plain-recursive-reducer result (1.56× on reduce alone).
End state: **~1.5-2× faster than Lark on the product metric**, pure Python,
full SPPF semantics — and unlike Lark, provably complete under ambiguity.

## 4. Phasing (each lands green: 1151 tests, ruff, pylint 10/10, fixpoint True, amb False, bench delta recorded)

- **Phase A — tables + int kernel.** `compile.py`/`tables.py`/`kernel.py`
  behind the existing API; `normalize` unchanged (still per-char, SplitLiterals
  still in). Pure representation swap, behaviour-identical, easiest to verify.
  Gate: recognize ≤ 0.95×, parse ≤ 1.35×, product ≤ 1.6×.
- **Phase B — fused reduce.** Product path folds SPPF→IrAst directly; Yield
  bug retired. Gate: product ≤ 1.15×.
- **Phase C — run-terminal compilation.** Kill SplitLiterals; regex-compile
  lexical rules with the follow-set safety check; per-char fallback where
  unsafe. The correctness-riskiest phase, so it goes last, on a proven kernel,
  with the ambiguity/property suites as the tripwire. Gate: product ≤ 0.75×.
- **Phase D — consolidation.** Leo interplay audit, dead-path removal
  (`Matches`, per-parse index nodes), README/wiki rewrite, bench baseline
  re-save.

Ordering rationale: A before C because run-terminals change *which* steps
exist — debugging them on the legible int kernel with per-char semantics still
available as a flag/fallback is far safer than changing representation and
step structure at once.

## 5. Correctness invariants (unchanged, enforced per phase)

- Full SPPF: every derivation representable; `parse` raises on ambiguity;
  `derivations`/`is_ambiguous` exact. The 24 ambiguity tests + property suite
  are the gate, plus the follow-set proof obligation in Phase C.
- Depth-safety: kernel is iterative by construction; fused fold uses the
  explicit-stack discipline; N=60k canary stays.
- ABNF self-host fixpoint `True` at every landing.
- Public API of `parsing_2/__init__.py` unchanged.

## 6. Rulings needed before Phase A

1. **The purity ruling (the big one).** The kernel module is deliberately
   *not* IrSelf-dispatched per item — the IR seam moves to compile time
   (GrammarCompiler walks the IrAst) and to the reduction tables. Framing:
   `ParserTables` is to the parser what `generated/*.py` is to `codegen` — a
   compiled representation with grammar as ground truth. This supersedes
   "every engine operation IS-AN IrSelf" *for the inner loop only*;
   orchestration, normalize, compile, reduce policy stay IR-native. The
   handover already posed this as decision #2/#3; the measured answer is that
   the per-item dispatch identity costs the majority of the remaining gap.
2. **Lexer-completeness stance for Phase C.** Exact mode (follow-set check +
   prefix fan-out fallback — never wrong, occasionally slower) vs Lark-style
   maximal munch flag for grammars the check can't clear. Recommendation:
   exact only; it's the honest differentiator.
3. **README/handover correction.** Purge the "Lark is C" claims so future
   sessions stop reasoning against a phantom (this file is the start).
