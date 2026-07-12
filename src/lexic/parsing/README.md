# `lexic.parsing` — the IR-native parse engine (predictive PDA + Earley)

`parsing` is a self-contained parse engine that runs **directly over an
`IrAst`**: a deterministic **predictive PDA** for the common case, backed by a
scannerless [Earley](https://en.wikipedia.org/wiki/Earley_parser) engine (full
SPPF, Scott 2008) as the sound completion. No meta-grammar strings, no
external parser. The premise: an `IrAst` already *is* a grammar — named rules,
each an alternation of sequences of atoms — so it drives a parser as-is.

**One engine, two jobs, both PDA-first:**

- **grammar-text → `IrAst`** — `parse_grammar` (in `compile.py`) parses a
  `.gbnf`/`.abnf` text against the flavour's own self-grammar
  (`GBNF_GRAMMAR`/`ABNF_GRAMMAR`). It runs the **reduce PDA** first
  (`self_grammar_pda(flavour)` → `parse_pda`); on `PdaFail` it completes with
  `parse_reduced` — the fused Earley pass that folds the forest to IR through
  the flavour's `Reducer`.
- **instance text → `GrammarModel`** — `CompiledGrammar.parse` parses input
  against the *codegen grammar*. It runs the **model PDA** first
  (`parse_pda(pda, text, fold)` — the fold is fused into the walk, no
  `ParseTree` is ever built); on `PdaFail` it completes with
  `parse_first` + `ModelFold.apply`.

The self-hosting fixpoint is the standing proof of the first job: emit the
ABNF-of-ABNF grammar (`grammars/abnf.py`'s `ABNF_GRAMMAR`) as text, parse that
text with itself, reduce, and recover the identical `IrAst`.

```
── grammar-text path (compile.py parse_grammar) ────────────────────────────────
flavour.grammar ─► lift_optional_nullables ─► normalize ─► compile_reduce_pda ─► PdaTables   (once/flavour)
text ─► parse_pda(pda, text, fold=None) ──────────────────────────► IrAst                    (per parse)
          └─PdaFail─► parse_reduced(normalize(flavour.grammar), text, flavour.reducer) ─► IrAst

── instance path (compile.py CompiledGrammar.parse) ────────────────────────────
codegen grammar ─► lift_optional_nullables ─► normalize ─┬─► compile_pda ─► PdaTables        (once/grammar)
                                                         └─► compile_tables ─► ParserTables
text ─► parse_pda(pda, text, fold) ───────────────────────────────► GrammarModel             (per parse)
          └─PdaFail─► fold.apply(parse_first(instance_grammar, text, tables)) ─► GrammarModel
```

The two grammar-text routes deliberately run **different normalised grammars**
(the PDA over the lifted grammar, the Earley completion over the unlifted
one). The divergence class is the ε-channel — a lifted nullable `R` (from
`R?`) matches ε and runs its reduction on empty children where the unlifted
route skips the node — and the authored reduce bodies absorb it; the
whole-corpus differential tests are the guard.

---

## 1. Public API (`__init__.py`)

Seven functions, all Earley-side. Each is a thin wrapper that boxes the input
and drives exactly one `IrSelf` orchestration node in `earley/engine.py`. Per
the IR's no-`IrBool` rule, a truth value is an `IrInt ∈ {0, 1}`.

| Function | Returns | Meaning |
|---|---|---|
| `recognize(grammar, text)` | `IrInt` 0/1 | Does `text` derive from the start rule? (No forest built.) |
| `parse(grammar, text)` | `ParseTree` | The single derivation. **Raises** on no-parse *or* ambiguity. |
| `parse_first(grammar, text, tables=None)` | `ParseTree` | The *first* derivation — deterministic under ambiguity. The instance-path completion (§8). Raises only on no-parse. |
| `parse_reduced(grammar, text, reducer)` | `IrSelf` | Text → reduced IR in one fused pass — the grammar-text completion (§7). Raises like `parse`. |
| `parse_forest(grammar, text)` | `SppfNode` \| `IrNone` | The shared packed parse forest root, or `IrNone` on no-parse. |
| `derivations(grammar, text)` | `IrSeq[ParseTree]` | *Every* derivation, nothing silently dropped. |
| `is_ambiguous(grammar, text)` | `IrInt` 0/1 | Does the input have more than one derivation? (Short-circuits at 2.) |

The PDA is driven through `compile.py` (the sole runtime seam), not through
`__init__.py`: `pda/clones.py`'s `compile_pda` / `compile_reduce_pda` →
`PdaTables`, and `pda/reduce_runtime.py`'s `parse_pda(tables, text, fold)` —
the single public runtime entry, dispatching the model kernel (`fold` given)
vs the reduce kernel (`fold=None`) behind one seam.

> **The grammar must be normalised first** (§6): every quantifier `(1, 1)`,
> every group a named rule. `normalize()` is the caller's responsibility —
> kept separate so the desugaring stays isolated. Both compiled paths
> normalise `lift_optional_nullables(grammar)` (§8), so the engine's
> identity-memoised tables are shared shapes.

## 2. The design in one sentence

**The grammar compiles once; the paid loop runs over the compiled form.**
`compile_tables()` / `compile_pda()` are the parser's "codegen moment":
exactly as `codegen/` emits Python classes from an `IrAst`, `earley/tables.py`
and `pda/clones.py` compile an `IrAst` into flat int-coded tables, and
`earley/kernel.py` / `pda/runtime.py` run over them with no per-item IR
dispatch, no IR object as a hot-path key, and no tuple allocation per advance.

The IR seams sit at the edges, all IR-native: `compile_tables`/`compile_pda`
walk the grammar in; `FusedReduce` (grammar-text) and `ModelFold` / the fused
PDA build (instance) carry the products out; `Kernel.to_chart()` decodes the
packed SPPF into the IR-native `Chart` for the forest readers. State objects
(`ParserTables`, `Kernel`, `PdaKernel`) ARE-AN `IrLeaf`; logic lives on
classes and per-parse state on cursors — but inside the kernels the per-item
work is list indexing and int arithmetic, deliberately: the package's
compiled-form zone, the scoped relaxation of per-item IR dispatch that the
measured performance floor demands.

## 3. Package layout

```
parsing/
  __init__.py       the seven-function Earley API (§1)
  fold.py           ModelFold — the authored instance fold (§8)
  earley/           the Earley engine (imports only itself)
    tables.py         ParserTables, compile_tables (memoised per IrAst identity)
    kernel.py         Kernel — predict/scan/complete, Leo, packed SPPF; FastTree;
                      longest_start_completion (the PDA island seam)
    chart.py          Chart/Links — the decoded SPPF; EarleyItem
    engine.py         per-capability orchestration nodes behind the public API
    forest.py         ParseTree, SppfNode, trampolined enumeration
    reduce.py         Reducer, FusedReduce, ReducePlan — forest → IrAst (§7)
    normalize.py      desugar IR into classical Earley shape (§6)
    lexruns.py        derived run terminals (§5)
    trampoline.py     depth-safe generator driver
  pda/              the predictive PDA (imports from earley/)
    charsets.py       CharSet — polarity-aware co-finite char sets (§9)
    analysis.py       GrammarAnalysis — fixpoints + the decision taxonomy (§10)
    kwindow.py        FIRST_k over CharSet tuples — bounded-lookahead gates (§10)
    noise.py          noise/semantic attribution — peek + structured gates (§10)
    scanner.py        structured-noise recognizer + ScanGate runtime (§10)
    taxonomy.py       Taxonomy — classified notes + the stored gate specs (§10)
    clones.py         compile_pda / compile_reduce_pda — the clone compiler (§11)
    flatten.py        the int-coded runtime program + optimizer passes (§11)
    runtime.py        PdaKernel — the fused model runtime (§12)
    reduce_runtime.py _ReducePdaKernel + parse_pda, the public entry (§12)
    reduce_pda.py     the reduce completion read off the ReducePlan (§12)
    islands.py        the windowed Earley island sub-parse (§13)
    delegate_compile.py DelegateSource — island-interior delegation (§13)
    errors.py         PdaFail — internal, never user-facing
```

Layering: the whole package is a leaf w.r.t. `lexic.codegen` and
`lexic.grammars`; `pda/` imports `earley/`, never the reverse;
`reduce_runtime` imports `runtime`, never the reverse; `flatten` imports
nothing from `clones`. `compile.py` is the only runtime module that imports
any of it.

## 4. The Earley tables and kernel (`earley/tables.py`, `earley/kernel.py`)

Every dotted position of every arm gets one int `code`, laid out so
consecutive dots are consecutive ints — **advancing an item's dot is `+ 1`**.
One flat list discriminates the classic Earley trichotomy with a single
index: `next_sym[code]` is `rule_id + 1` (predict), `-(term_id + 1)` (scan),
or `0` (complete). An **Earley item** is the single int `code << 20 | origin`;
an SPPF handle `(item, end)` packs the same way again.

`Kernel(tables, text, record_links).run()` is the whole loop: close each
column to a fixpoint, scan between columns.

- **SPPF (Scott 2008).** Packed families with dedup; ≥ 2 families ⇒ an
  ambiguity point. Recognition skips the forest entirely
  (`record_links=False`).
- **Aycock-Horspool nullable advance**, provenances collapsed into one
  family.
- **Leo right recursion (Leo 1991).** Deterministic right-recursive
  completions jump to the chain's top; skipped completions are deferred in
  per-top buckets and rebuilt lazily, O(chain), only when a derivation walks
  them. Same-column (empty-span) steps are rejected from the climb — the
  normal completer handles them — so columns strictly decrease and no cycle
  guard is needed.
- **`longest_start_completion`** — a public windowed prefix-completion seam:
  run a rule over a text window, return the longest completion. The PDA
  island sub-parse (§13) drives it; additive, off the `run()` fast path.

`FastTree` is the unambiguous fast path: an explicit-stack walk of the packed
links building the single `ParseTree`; any multi-family key aborts to the
trampolined enumeration over the decoded chart. Depth lives in lists, never
the C stack.

## 5. Scanning: chars, literals, runs (`earley/lexruns.py`)

The scanner resolves which terminals a character can begin once per distinct
char (cached on the tables). A char class advances one column; a multi-char
literal is atomic (one `text.startswith`, k columns); a **run terminal**
consumes its maximal run in one step. Run terminals are the *derived* lexer:
a synthetic star/plus rule collapses into a single maximal-munch `RunTerm`
only when three proofs hold — fixed charset, derivation uniqueness (pairwise
disjoint alternatives, so the collapse hides no ambiguity from the SPPF), and
follow disjointness (`FOLLOW(rule) ∩ charset = ∅`, so no continuation ever
needs a shorter match). The reducer-side licence is
`reduce.collapsed_tables` (a run may only collapse when its per-char
reduction contributions reconstruct from the run text); the fold-side sibling
is `fold.collapsed_fold_tables` (safe iff no constructor-bearing rule sits
among a run's unit leaves). Collapsed tables are per (policy, grammar) and
memoised; `parse`/`recognize`/forest readers keep plain tables and exact
`ParseTree` shapes.

## 6. Normalisation (`earley/normalize.py`)

Two `IrTransformer` canonicalisations precede either compiled form: inline
groups hoist to fresh synthetic rules (prefix `__`), and non-`(1, 1)`
quantifiers desugar to synthetic right-recursive rules (`*`/`?` nullable; Leo
keeps the recursion linear). Large *bounded* counts (`{lo, hi}`) still unroll
`hi`-deep at desugar time — the one remaining rough edge.

## 7. Reduction (`earley/reduce.py`) — the grammar-text meta-notation seam

A flavour's "meta notation" is its `Reducer`: `reductions` (an `IrMap` from a
rule's `IrRuleRef` to a body folding the rule's matched children into IR) and
a cleaning policy (`noise` per child rule, `literal` for terminal leaves;
`YIELD` recovers a subtree's source text). Two folds implement it:
**`FusedReduce`** — one explicit-stack pass folds the packed SPPF straight to
IR, no intermediate `ParseTree`; a `ReducePlan` (cached per reducer × tables)
compiles the policies against the rule numbering, `YIELD` bodies reduce to
O(1) source spans when `can_drop` reachability allows, and any shape the plan
can't compile falls back to a plain parse + the general **`Reducer`-over-
`ParseTree`** fold. The reduce PDA (§12) reads this same `ReducePlan` — one
compiled policy, three consumers.

## 8. The instance fold (`fold.py`) — text → `GrammarModel`

Instance parsing runs over the **real codegen grammar** (no wrapper rules, no
name protocol): `normalize()` replaces items in place, so `kids[i] ↔ items[i]`
positionally. `ModelFold` is a generic positional tree → object fold whose
authored form is a per-rule IR body-table (`IrMap[IrRuleRef, ModelBody]`)
baking to flat runtime records (`RuleFold`/`FieldFold`/`FastCtor`) on
construction — the same baked records every PDA clone carries (§11). Per
`kind`: `value_str` → `ctor(value=<subtree text>)`; `alternation` →
pass-through (the matched arm's sub-model identifies itself); `sequence` →
per-field slot reads (`text`/`gtext` take consumed text, `model`/`models`
collect sub-models through synthetic layers). The Earley completion runs
`parse_first` because an all-nullable arm would otherwise make the empty
match ambiguous; `lift_optional_nullables` (`R? → R` for nullable `R`)
encodes that policy at normalise time for both compiled paths.

## 9. `CharSet` (`pda/charsets.py`) — the analysis substrate

A polarity-aware `(chars, negated)` character set: when `negated`, the set is
every character *except* `chars`. Every operation (`has`/`union`/`subtract`/
`overlaps`) is exact across all four polarity combinations, so an
`IrNot`-derived loop's co-finite FIRST stays exact instead of poisoning its
rule into a fake island. FOLLOW seeds end-of-input as the character `""` in a
*positive* set; `CharSet.ANY` excludes it.

## 10. The analysis (`pda/analysis.py` + its leaves) — decide, then store

`GrammarAnalysis` runs over a lifted codegen grammar and computes the
classical predictive fixpoints — nullability, FIRST (over `CharSet`),
**hard-FIRST** (the chars a construct *requires*), FOLLOW and hard-FOLLOW —
then classifies every decision point (arm selection; loop take/skip). A
decision no gate family can make deterministic becomes an **island** (§13);
everything else compiles to a gate. The gate families, tried in order:

- **1- and 2-char lookahead** — disjoint FIRST sets, or 2-char prefix
  separation (`PairGate`).
- **k-window** (`kwindow.py`) — FIRST_k over `CharSet` tuples: does the
  decision separate positionwise at k ≤ 3 (END/MORE/UNK-tagged ≤k windows,
  rule-FOLLOW extension, *soft* FOLLOW only — hard FOLLOW is unsound here)?
  → `KTupleGate`.
- **noise-skip peek** (`noise.py`) — skip the maximal noise run
  (W = ⋃FIRST over nullable non-semantic rules, derived from the grammar,
  never hardcoded) non-consuming and decide on the first post-noise char
  → `PeekGate`.
- **structured scan** (`noise.py` + `scanner.py`) — folding-aware gates over
  a compiled noise recognizer: `SG_MATCH` (exact-match loop over a
  non-semantic ref, licensed by noise-only exits or a semantic-follow
  clearance check), `SG_SCAN` (skip noise roots, peek disjoint content
  leads), `SG_PROBE` (overlap refuted by the unique next-construct header,
  e.g. GBNF's `rulename n* "::="`) → `ScanGate`.
- **noise-greedy licence** (`noise.py`) — a greedy over-eat is provably
  noise↔noise re-splitting only (`sem_follow_table`: the chars that can
  follow a rule as *semantic* content), so greedy is safe.

A gated decision's spec is **stored** on the public `taxonomy: Taxonomy`
attribute — the clone compiler *reads* it back, never recomputes; a
FIRST-overlapping alternation with no stored spec **raises** (the anti-drift
tripwire → whole-grammar opt-out). Loops overlapping only *soft* (nullable)
continuations classify through the same cascade — never a silent greedy
stop-set. Every per-atom-type decision routes through an open `IrTypeMap`
with a raising default; `nullable_names` here is the single source
`fold.lift_optional_nullables` reads.

## 11. The clone compiler (`pda/clones.py`, `pda/flatten.py`)

`compile_pda(lifted, instance_grammar, fold_config) → PdaTables`. A rule is
compiled once per distinct **hard continuation** that reaches it (a *clone*),
because the stop-sets it bakes are call-site-exact. Each item lowers to a
tuple-coded `ItemSpec` (`lit`/`cc`/`ref`/`grp`) carrying its bounds and loop
gate (`StopGate`/`PairGate`/`KTupleGate`/`PeekGate`/`ScanGate`); arm
selection is FIRST-gated `ArmSpec`s (per-arm gate specs are attached inside
`compile_arms`' own enumeration so spec↔arm alignment cannot drift) plus at
most one nullable default. Every clone bakes its `RuleFold`; islands are not
cloned (`IslandRef`, §13). The `CloneSpec`/`ItemSpec` NamedTuples are the
compiler *intermediate* (what the structural tests pin); `flatten.py` lowers
them once per compile into the int-coded `PdaProgram`
(`_FlatClone`/`_FlatArm`, `_OP_*` op-codes, pre-resolved membership sets, the
gate runtimes — the EOF-exact ≤k window matcher, the non-consuming
noise-skip peek) and runs the post-flatten optimizer passes (exactly-once
terminal/call specialisation, `value_str` inlining, frame-less leaf marking,
pass-through dispatch conversion). `compile_reduce_pda` retargets the flat
clones for the reduce product (`reduce_pda.py` bakes `ReduceComp`s straight
off the reducer's compiled `ReducePlan` — no re-derivation).

## 12. The fused runtime (`pda/runtime.py`, `pda/reduce_runtime.py`)

`PdaKernel` is the model runtime: an explicit descent stack of flat list
frames (no Python recursion) walks the int-coded `PdaProgram`, **building the
model during the walk** — no `ParseTree`. Terminal quantifier loops match
inline; capture frames own per-item spans and sub-model sinks, capture
bubbles to the nearest bound item through transparent frames (groups,
no-constructor clones) exactly as `ModelFold` collects. `_ReducePdaKernel`
(`reduce_runtime.py`) is the grammar-text twin: it shares the whole
recognition machinery and overrides only the completion callbacks, producing
reduced IR per the baked `ReduceComp`s (including the O(1) `YIELD` span
stitch, mirroring `FusedReduce`). `parse_pda(tables, text, fold)` is the one
public entry dispatching the two. On *any* non-deterministic point the
runtime raises **`PdaFail`** (`errors.py`) — internal, caught by the compile
seam, retried on the Earley completion which owns user-facing diagnostics.

## 13. Islands and delegation (`pda/islands.py`, `pda/delegate_compile.py`)

A decision no gate family can license makes its rule an **island**: the ref
is compiled as an `IslandRef` marker with a lazy per-island `ParserTables`
cache, and the runtime runs a **windowed Earley sub-parse**
(`longest_start_completion`, doubling window) over just that span, folds the
sub-tree, and splices the sub-model into the current capture. A
**fail-island** (a semantic escape whose ref must fail to the full engine)
always raises `PdaFail` instead. `DelegateSource` cuts island cost from the
inside: it selects conflict-free, non-nullable, semantic *interior* rules of
an island above a triviality floor and compiles each to its own PDA clone cut
against the sub-grammar's hard FOLLOW, so the island's Earley sub-parse runs
those interiors on clones rather than the item machinery. Everything here is
fail-soft: a declined delegate falls through to normal prediction; a failed
island fails the PDA parse into the Earley completion.

## 14. Invariants

- **Grammar is canonical.** Neither engine mutates the grammar; every table
  is its compiled representation, rebuilt from it alone.
- **PDA-first, engine-sound.** The PDA is an optimisation, never a
  semantics: any non-deterministic point raises `PdaFail` and the Earley
  completion reparses. Whole grammars opt out (no PDA) rather than parse a
  construct the compiler can't handle soundly — totality escapes are
  `UnsupportedConstructError` or `pda=None`, never a wrong parse.
- **Gates are stored, not recomputed.** The analysis is the one place a
  demotion decision is made; the clone compiler reads `taxonomy` and raises
  on any unexplained overlap (drift becomes a loud opt-out, not a wrong
  gate).
- **Full SPPF.** Nullable completion, packed families, exact ambiguity —
  including under Leo and under run collapse (both proved, §4/§5). Ambiguity
  is never silently resolved on the strict path; `parse_first` is the one
  deliberate first-derivation entry.
- **Depth-safe.** No walk recurses through the C stack — explicit stacks and
  the trampoline everywhere, including the PDA descent stack.
- **The compiled-form zone is scoped.** Per-item IR dispatch is compiled
  away inside the kernels and tables only; every seam in and out is
  IR-native, and orchestration, normalisation, analysis, and policy stay
  `IrSelf`/open-dispatch end to end.

## 15. Performance

Benchmarks live in `tools/benchmark/`: `parse_bench.py` (grammar-text and
instance workloads on the ground-truth corpus and both self-grammars; Lark is
kept as an external reference baseline) and `pipeline_bench.py` (compile
pipeline). Saved baselines sit next to them. Characteristics: the Earley
engine alone beats Lark's Earley on the grammar-text product roughly 2×, with
linear deep right recursion; the PDA-first paths add roughly another 2× on
grammar text where the self-grammars gate deterministically, and up to an
order of magnitude on deterministic instance grammars — with the Earley
completion bounding the worst case at engine speed. Re-run the harness for
current numbers rather than trusting any figure written here.

## References

- J. Earley (1970), *An Efficient Context-Free Parsing Algorithm*.
- J. Aycock & R. N. Horspool (2002), *Practical Earley Parsing* — nullable
  completion.
- J. M. I. M. Leo (1991), *A general context-free parsing algorithm running
  in linear time on every LR(k) grammar without using lookahead* —
  right-recursion.
- E. Scott (2008), *SPPF-Style Parsing From Earley Recognisers* — the shared
  packed parse forest.
