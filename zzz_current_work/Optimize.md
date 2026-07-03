# PLAN — engine perf round 3: full-grammar regression + open-noise fold-in

Date: 2026-07-03, branch `parse_proto_proto`. Merges three inputs:

1. `Disputed.md` — verified 2026-07-03: the 15→26 µs/char product regression is
   grammar-driven (prediction cost), engine mechanics intact (±5%).
2. This session's profiling (numbers below).
3. `postleo/PLAN_perf_round2.md` — reconciled; its Phase 1 is Task 1 here.

## Execution — agent class per task (dispatch policy)

| Task | Work | Agent class |
|---|---|---|
| 0 | bench harness repair + dual workload | Sonnet (trivial) |
| 1 | seed-layout lever (round-2 Phase 1) | Opus (nontrivial, kernel) |
| 2 | FIRST-gated prediction | **Fable** (critical) |
| 3 | `IrAst.non_semantic` / Directives retirement | Opus (nontrivial, wide) |
| 4 | instance-path run collapse | Opus (nontrivial) |
| 5 | noise skip-machine (if Task-2 evidence justifies) | **Fable** (critical) — decide after Task 2 |
| 6 | ~~relocate parse_directives ir/→parsing/~~ SUPERSEDED by 6R (move landed first, subsumed) | — |
| 6R | IrRule.non_semantic field (IrAst.non_semantic → derived property, eq/hash exclusion relocates IrRule-ward, IrAst override removed); composite repr omits TRAILING default-valued fields (general fix, lands first — kills golden churn); parse_directives dissolves into a private compile.py helper, parsing/directives.py deleted | Opus (reuse «task3-irast») — user rulings 2026-07-03: 1=go, 2=fix properly |

Test-writing for every task: Sonnet, dispatched after src lands, batched when
the tree is torn open. Agents of one class are reused via SendMessage until
context nears 250k, then replaced fresh. Async/background by default. Never
commit — landings stay staged; the user commits. Concurrent agents get
disjoint file sets (one shared tree, no worktrees) and format only their own
files.

## Progress (one line per step, newest at bottom — session-crash ledger)

If the session breaks (lost connection / token exhaustion): this ledger + the
staged-not-committed tree is the resume state. Write a "NEXT SESSION — start
here" block above this section at break time (see
`prototyping/archive/postleo/PLAN_cutover_parsing_v2.md` for the format).

- [x] Plan merged (fable, main session 2026-07-03): Disputed.md claims all verified by re-run; profiling done (26.3 vs 12.2 items/char, 31% DOA, noise 27%/num-val 13%); PLAN_perf_round2 reconciled; corpus pinned at tools/benchmark/corpus_subset_920.abnf. Baseline = Disputed.md table (engine product 25.6 µs/char, lark 29.9, subset-920 ×4).
- [x] Task 0 DONE (sonnet «task0-bench»): bench_parsing.py deleted (dead meta_parser imports); parse_bench.py dual-workload (self-emit + subset-920) + --save → tools/benchmark/bench_baseline.json; gates clean; staged. Polluted mid-flight smoke baseline deleted by coordinator — do NOT --save an official baseline until the tree is quiet.
- [x] Task 1 DONE (opus «task1-seed», coordinator-reviewed): CodeTables.rule_seeds stored primitive, rule_dot0 → derived @property (pylint 7-attr cap solved at root, keep the property off hot paths); _seed dedup-free with both invariants documented at site (seen intentionally omits dot-0 seeds; no lookup probes dot-0). Charts byte-identical (6/6 self-grammar configs + 3 instance grammars); kernel −15.6% product / −15.4% parse / −20.3% recognize (beats round-2 projections); verified via clean-HEAD overlay (tree was mid-Task-3); staged.
- [x] Task 3 DONE (opus «task3-irast», coordinator-reviewed): IrAst gains non_semantic payload; __eq__/__ne__/__hash__ exclude it (compile-channel metadata — fixpoint rationale in the IrAst docstring; IrBounds override precedent; start stays structural); repr keeps all 3 fields (repr-is-codegen, deliberate). Directives dataclass deleted; parse_directives → (start, non_semantic) tuple, pre-lexical scan retained (settled: in-parse capture would block below-chart comment collapse). derive_specs(ast) reads ast.non_semantic; flavours declare noise on their GRAMMAR, NOISE maps derived from it. Side effect: topo_sort start is now the RESOLVED start. CLAUDE.md updated. Wiki updated on disk only — .wiki/ is gitignored, intentionally local (user ruling 2026-07-03). Staged. Left 6 failures + 1 collection error, all expected test ports.
- [x] Full suite in place post-0/1/3 (coordinator): 1312 passed; only the 7 known Task-3 test-port items failing.
- [x] Task 2 DONE (fable «task2-first», coordinator-reviewed, suite 1341/0 verified in place): FIRST-gated prediction landed. Stored primitive is CodeTables.rule_seed_gates triples (dot0<<B, next_sym, gate: None=always-seed | frozenset FIRST) — gate fused into the seed tuple (no per-seed alloc); rule_seeds AND rule_dot0 both derived @properties now (pair-shape contract preserved, all 12 shape tests green; properties documented never-on-hot-path; lexruns per-loop reads hoisted). _FirstGates analysis in tables.py (all three table variants get gates; RunTerms contribute charsets); _expand_atom/_MAX_CHARSET/Charset hoisted lexruns→tables (lexruns re-imports). _seed gates on text[i:i+1] (EOF = empty slice ∉ any charset — always-seed arms only, branch-free); both invariant blocks at site. 88-check equality harness gated-vs-ungated ALL EQUAL (ABNF+GBNF self-grammars, 8 .gbnf sources, 7 instance grammars, ambiguity derivation counts). Canary linear. Bench: subset-920 ×4 product 25.6 (pre-effort) → 23.6 (Task 1) → **17.0-17.5 µs/char**; recognize 7.8; items/char 26.3 → 10.4; self-emit product 18.4 = **0.62× lark** (full-vs-full, was ~0.86×). Staged.
- FINDING (pre-existing, not Task 2): no GBNF emit-self-reparse fixpoint at HEAD — parse_reduced(GBNF self-emit) fails identically before/after gating; no test asserts it. Surface when convenient.
- [ ] Task 6 QUEUED (user ruling 2026-07-03): move parse_directives ir/directives.py → parsing/directives.py — with metadata now ON IrAst, the leftover is a pure text scanner, which belongs to the parsing side (sibling of parse_grammar's Earley half), not the node algebra. Scope: file move, compile.py import (sanctioned seam), ir/__init__ export removal, test mirror move to tests/unit/lexic/parsing/, CLAUDE.md + wiki. Dispatch to «task3-irast» AFTER Task 4 lands (compile.py contention).
- [x] Task 5 KILLED (user ruling 2026-07-03): comment skip-machine dead per round-2 kill-list discipline — FIRST gating leaves comment = 0 items, spec'd residue 4.8% (was 27%); remaining endrule/wsp cluster not automaton-shaped. Do not revisit without new evidence (e.g. a comment-HEAVY workload, where actual comment text still parses per-char).
- [x] Tests for Task 4 DONE (sonnet «task0-bench» reused): suite 1368/0 (+14). collapsed_instance_tables ×3 (real collapse on arithmetic asserted via lens==0 terminal — num+ident both collapse; identity-memoisation; zero-candidate grammar returns the plain object by identity); _instance_run_ok full truth table ×4; ParseFirst tables param ×4 incl. a genuine exercise of the fast-path-miss→plain-re-parse fallback on ambiguous input; CompiledGrammar.tables + collapsed-vs-plain model_dump/to_text parity on arithmetic + json_ws (the ambiguous-int case) ×3. One pyright narrowing solved with an isinstance assert at root, no suppression. Gates clean ×3 files. Staged.
- [ ] Task 6R IN FLIGHT (opus «task3-irast», user rulings 2026-07-03: redesign GO, repr FIX PROPERLY): step 1 — composite repr omits trailing default-valued fields (ir/base.py shared repr; stays a valid constructor call; fixes IrItem's IrQuantifier(1,1) noise everywhere); step 2 — IrRule.semantic: bool = True (user polarity ruling 2026-07-03: no negation in the attribute; noise rules declare semantic=False; eq/ne/hash exclude it, same compile-channel rationale relocated from IrAst; IrAst back to 2 fields, Task-3 override REMOVED, non_semantic stays as a derived property name — matches the @non-semantic directive vocabulary, consumers unchanged); step 3 — parse_directives dissolves into private compile.py helper, parsing/directives.py deleted (the 6-move is subsumed); flavours flag noise rules individually. Expected test breakage (repr goldens + directives tests + 3-field IrAst constructions) enumerated for the Sonnet wave, not fixed by Opus.
- [x] Tests for 0/1/3 DONE (sonnet «task0-bench» reused): suite 1341/0 (from 1312+7 known). All 7 items ported; repr test ported with precedent documented (IrTuple.__repr__ renders default-valued fields everywhere — IrItem's default IrQuantifier(1,1) is the sibling precedent). The old Directives-dataclass-default test's intent restored as test_defaults_to_none_and_empty_frozenset (successor noted in its docstring) — no assertions lost anywhere. +6 rule_seeds/rule_dot0 shape tests (pair contract only, no FIRST-gate assertions); +1 integration fixture test_corpus_subset_920.py (34 rules, start rulelist); tests/paths.py gains BENCHMARK constant. Gates clean on all 8 touched files. Staged.
- [x] Task 4 DONE (opus «task3-irast» reused, coordinator-reviewed, suite 1354/0 + property 6/0 verified in place): instance-path run collapse. models.collapsed_instance_tables (memoised per (fold, grammar)) + _instance_run_ok licence (unit leaves carry no RuleSpec and no --f wrapper; bare-terminal units ok) mirroring reduce._run_mode; RUN_STR text-preserving. CompiledGrammar gains `tables` (compiled once at build); public parse_first grew optional `tables=None` (coordinator-adjudicated scope flag: extends the one wrapper instead of pulling engine internals into compile.py — parsing/__init__.py touched beyond stated set, accepted); fast-path miss falls back to PLAIN-tables re-parse, ParseReduced-style. MECHANICAL FINDING: RunTerm mode is never read by the tree path (kernel records text[i:j] as the scanned child; FastTree makes it one multi-char IrLiteral leaf) — mode matters only to FusedReduce. Collapses: arithmetic ×2, json_arr ×1, json_ws ×1, c ×3; list/chess/japanese zero (legit). Equality collapsed-vs-plain ALL EQUAL (semantic_dump + model_dump + to_text, all 7 grammars). Bench arithmetic: kernel −78% / end-to-end −69% charclass-heavy; ~−3% on 1-char-run inputs (nothing to collapse). Gates clean ×4 files. Staged.
- [x] Tests for Task 2 DONE (sonnet «task0-bench» reused): suite 1354/0 (+13). Gate semantics ×9 in test_tables.py (empty-deriving/IrNot/over-cap→None incl. TRANSITIVE poison via ruleref; charset FIRST; nullable-prefix continuation union; multi-char literal first-char-only; RunTerm charset; triple[:2]==rule_seeds pairs); kernel behavior ×3 in test_kernel.py (gated arm absent from cols; EOF seeds gate-None only; empty-literal arm gate==frozenset() — real empty charset, distinct from the None sentinel — never seeds); 6 _expand_atom tests relocated to test_tables.py per mirror rule + one re-export identity smoke in test_lexruns.py (import verified live, not hypothetical). Gates clean ×3 files. Staged.
- [x] Task 6 DONE (opus «task3-irast» reused): parse_directives relocated ir/directives.py → parsing/directives.py (a pure pre-lexical text scanner is parsing-side machinery now the directive content lives on IrAst — the comment-channel sibling of parse_grammar's Earley half). git mv (content unchanged; docstring reframed off "IR-level"). compile.py imports from lexic.parsing.directives (submodule seam, models/normalize/reduce precedent); dropped from lexic.ir.__init__ exports; parsing/__init__.py deliberately NOT touched (no re-export — compile.py is sole caller — and test agent owns tests near test_init_parsing). Test mirror: git mv tests/unit/lexic/ir/test_directives.py → tests/unit/lexic/parsing/test_directives.py (import fixed); test_init_ir.py's export test inverted to test_directives_not_exported. Grep confirmed 3 importers (compile.py, ir/__init__, test_directives), all fixed; no others. CLAUDE.md ir/→parsing/ block move + §Directives path; wiki architecture.md + log. Suite 1354/0. Gates clean on all touched files incl. the moved test. Staged (git mv stages the move).

## Reconciliation with PLAN_perf_round2

- Its numbers are the **subset-era workload** (12.2 items/char, product
  0.53× Lark). The RFC-full grammar (landed after) runs 26.3 items/char on
  the same text — the game it declared closed ("near the pure-Python floor,
  exactly one high-EV change") is reopened by new evidence.
- Its gate harness `zzz_current_work/bench_parsing.py` **no longer runs at
  HEAD** (imports `lexic.parsing.meta_parser` + `ABNF_FLAVOUR.meta_grammar`,
  both deleted in the Lark obliteration). `tools/benchmark/parse_bench.py`
  is the survivor and becomes the canonical harness (Task 0).
- Its **Phase 1 (seed-layout lever) stands as specced** — measured
  −11.4…−16.6% kernel, byte-identical charts, minimal risk. It is Task 1,
  and its per-rule seed-pair table is exactly where Task 2's FIRST data goes.
- Its **Phase 2 (parse on collapsed tables + run re-expansion) stays
  declined** — `parse` has zero production callers. But `parse_first`
  (instance path) IS a production caller and gets Task 4 instead.
- Kill list: stays dead, except **"wider run-terminal coverage — KILL"**,
  which was explicitly workload-scoped ("on this workload"); the full
  grammar's 27% comment/newline noise is the new evidence its own rule
  demands. Re-scoped as Task 5 (deferred, re-measure after Task 2).

## Where the noise knowledge lives today (3 disconnected encodings)

| layer | mechanism | reaches the engine? |
|---|---|---|
| user grammar source | `@non-semantic` (`ir/directives.py`) | No — only `derive_specs` (min=0 relax + `semantic_dump` filter). |
| self-grammar parse | `_NON_SEMANTIC` tuples in `abnf.py:863` / `gbnf.py:905` → `Reducer.noise` | Partially — `collapsed_tables` collapses single-char runs only. |
| instance parse | — nothing — | No — `parse_first` runs plain tables, zero collapse. |

`IrAst` already carries `start` (the `@start` directive's content) as payload;
`@non-semantic`'s content is the one that never made it into the IR. Task 3
completes that move and retires the `Directives` shim; `derive`'s closed-set
rework proper stays the separate open-set-consumer effort.

**Settled in discussion (2026-07-03):** directive *content* moves into
`IrAst`; directive *extraction* stays a pre-lexical text scan — in-parse
capture would make comments load-bearing and permanently block collapsing
them below the chart (the Lark `%ignore` lesson, inverted).

## Measured facts (this session; disputed corpus = 920-char subset self-emit)

- Full grammar, reducer-collapsed: **26.3 items/char**; subset: **12.2** —
  the 2.16× item blow-up explains the wall-clock 1.7×.
- Noise machinery (`wsp`/`c-wsp`/`c-nl`/`crlf`/`SP`/`LF`/`endrule`/
  `comment`): **27% of items** on a corpus with zero comments;
  `num-val` family: **13%** with almost no `%x`.
- **31% of all chart items are dead on arrival** (next symbol cannot start
  at that position); 6,641 of 7,622 DOA items are dot-0 predictor seeds —
  and each dead seed also cascades further predictions (uncounted).
- Run collapse is exhausted: 10 candidates prove, 8 survive the reducer,
  recognition-maximal ≈ reducer-collapsed. **Prediction is the cost.**
  (Consistent with round-2's "66% of items are dot-0 seeds, `_seed` is #1
  self-time" — measured before the grammar grew.)
- Instance side (arithmetic.gbnf): plain kernel 10.4ms vs maximally
  collapsed 7.6ms (**1.37× on the table**); FastTree+ModelFold ≈ 46% of
  `CompiledGrammar.parse` on top.
- Lark reference (identical corpus, full META_GRAMMAR): 29.9 µs/char.
  Full-vs-full today: engine 25.6 — parity, not the old 0.53×.

## Tasks

### Task 0 — bench harness repair (prereq for every gate)

Make `tools/benchmark/parse_bench.py` the canonical harness; retire
`zzz_current_work/bench_parsing.py` (dead imports). Add the disputed-corpus
workload (old-subset self-emit) alongside the current self-emit so
full-grammar gates are comparable to `Disputed.md`'s table. Save a fresh
baseline JSON at HEAD before any change.

### Task 1 — seed-layout lever (round-2 Phase 1, verbatim)

As specced in `postleo/PLAN_perf_round2.md` §3, **plain variant** (the
stronger cols-skip variant stays measured-and-declined):

- `tables.py`: per-rule `tuple((code << ORIGIN_BITS, next_sym[code]) …)`
  seed-pair column.
- `kernel.py` `_seed`: loop the pairs — no `seen` test, no `seen.add`, no
  `next_sym` indexing (proof: dot-0 items are minted only by `_seed`, which
  is `predicted`-guarded at both call sites; state both invariants as
  comments at the site).
- Measured: −11.8% product / −11.4% parse / −16.6% recognize kernel,
  **byte-identical charts** (cols, links, accept).
- Gates: full suite green; ABNF fixpoint; ambiguity + property suites;
  N=60k right-recursion canary; ruff/pylint/pyright clean on parsing.

### Task 2 — FIRST-gated prediction (the headline)

Extends Task 1's seed-pair table; targets the 31%+cascades.

**Tables side** (`tables.py`, compile-time — hoist from
`lexruns._Analysis`): per dot-0 arm, `(first_charset | None, empty_deriving)`
— `first_charset` is the arm's FIRST char set computed with nullable-prefix
continuation (as `_Analysis._first_of_rule` already does, per-arm);
`None` = poisoned (huge class, `IrNot`) = never gate.

**Kernel side** (`_seed`): seed an arm iff `empty_deriving`, or FIRST is
poisoned, or `text[i] in first_charset` (at column n / EOF only
empty-deriving arms seed). `predicted` guard unchanged (char is fixed per
column, so per-rule marking stays valid).

**Correctness invariants** (state at the site):
- Empty-deriving arms always seed — `_nullable_advance` records their
  done-codes as SPPF children, and a nested-nullable arm's empty completion
  needs its own advance links in the chart for FastTree/FusedReduce.
- A gated arm can contribute to no derivation: non-empty derivation ⇒ first
  consumed char ∈ arm-FIRST (nullable-prefix-closed); empty ⇒ not gated.
- Leo: fewer waiters can only shrink buckets (may *enable* Leo more often —
  chart shape changes, language/derivations don't).
- Charts are NOT byte-identical (that's the point) — gates are semantic.

**Gates:** full suite; ABNF+GBNF fixpoints; product IR equality vs ungated
kernel across all suite grammars + hypothesis corpora; ambiguity suite
(`derivations` counts unchanged on the ambiguous fixtures); canary; bench —
full-grammar product on disputed corpus **≤ 19 µs/char** (from 25.6),
subset workload no worse than Task 1's numbers.

Optional recognize-only refinement (separate commit, only if free): with
`record_links=False`, empty-deriving arms whose FIRST misses may also skip
(A-H needs no provenance) — decline if it complicates `_seed`.

### Task 3 — `IrAst.non_semantic`: retire the `Directives` shim

- `IrAst` grows `non_semantic: frozenset[str] = frozenset()` payload
  (non-child, beside `start`). All construction sites mechanical-update.
- `Directives` dataclass dies. The comment scan (`parse_directives`) stays
  pre-lexical but feeds the parsed `IrAst` (rebuild with fields) in
  `compile_grammar`; precedence (explicit arg > directive > fallback)
  unchanged. Whether the scanner keeps its own module or folds into
  `compile.py` — implementer's call, flag in review.
- `derive_specs` loses `non_semantic_rules`; reads `ast.non_semantic`.
- Flavours: `_NON_SEMANTIC` tuples die; `ABNF_GRAMMAR`/`GBNF_GRAMMAR`
  declare `non_semantic=` on the IrAst; `ABNF_NOISE`/`GBNF_NOISE` are built
  *from the grammar's declaration* (one source of truth feeding reducer,
  derive, semantic_dump — and Tasks 4/5's collapse licence).
- Docs: directives.py's Lark-era docstring rewritten; CLAUDE.md §Directives
  + §IR types updated; wiki (`ir-shapes`, log entry).
- Tests: mirror rule applies (`test_directives.py` follows its module;
  ported, not deleted).
- Also sweep the adjacent dead shim: `ir/emit.py` `render_specs` is
  consumed only by its own test — propose deletion in review, don't just do it.

### Task 4 — instance-path run collapse (`parse_first` + `models.py`)

Today `ParseFirst` runs plain tables. Mirror `reduce._run_mode` with a
ModelFold-side licence: a grammar-proved run may collapse iff its unit
leaves carry **no RuleSpec and no wrapper rule** — the run then lands as
one multi-char str leaf, which `_subtree_text` already consumes.
`@non-semantic` instance rules stay **text-preserving** (RUN_STR-grade,
never RUN_DROP): round-trip fidelity requires `to_text()` to reproduce ws.
Wire through `build_instance_parser`/`compile.py` (the sanctioned seam).

Gates: full suite; round-trip property suite over all seven ground-truth
grammars; arithmetic kernel −20% or better; `CompiledGrammar.parse` output
identical on every integration fixture.

### Task 5 — DEFERRED: noise skip-machine (true `%ignore` parity)

Comment-shaped noise (`comment = ";" … CRLF` under `c-nl`/`c-wsp`) can't be
a charset run, but is reducer-DROPped — recognition-grade collapse licence
(no reconstruction needed) if compiled to a small scan automaton as table
data, guarded by the same FOLLOW-disjointness proof. **Do not start until
Task 2 lands and the full-grammar profile is re-taken** — FIRST gating kills
comment arms at predict time wherever `text[i] != ';'`, and may leave this
below the EV bar (round-2's kill-list discipline applies).

### Punted to the codegen refactor (user-announced, upcoming)

`models.py` wrapper diet: per-field `--f<idx>` wrapper rules cost a rule +
completion layer each; FastTree+ModelFold ≈ 46% of instance parse time.
Candidates recorded: skip wrappers for unquantified single rule-refs;
resolve fields from arm dot-positions. `utils/quantifiers.py` cleanup rides
along (sole consumer is `codegen/aliases.py`).

## Consolidation (after whichever tasks land)

Fresh baseline via Task-0 harness; README bench-table refresh; postleo-style
OUTCOME note; wiki log entry; update `Disputed.md` status line (claims
verified, fix landed) or fold it into the outcome note.

## Standing constraints (inherited, unchanged)

Purity ruling: tables data in `tables.py`, loop in `kernel.py` (compiled-form
zone); orchestration/normalize/reduce-policy stay IR-native; per-parse state
on cursors, no free functions. Full SPPF semantics; `parse` raises on
ambiguity; pure Python; suite + ruff + pylint 10.00 + pyright 0 at every
landing. Layering: engine stays a leaf; only `compile.py` touches it from
runtime.

## Expected outcome

Task 1: product 25.6 → ~23 µs/char on the full grammar (kernel −12%).
Task 2: → **≤ 19 µs/char** (31% DOA + cascades; subset workload also gains —
round-2 measured 66% of items are seeds even there). Task 4: instance parse
kernel −25%+ on charclass-heavy grammars. Task 5 only if the post-Task-2
profile still shows a comment-noise residue worth an automaton.
