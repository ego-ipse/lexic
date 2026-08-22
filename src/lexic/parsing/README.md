# `lexic.parsing` — the IR-native parse engine (predictive PDA + Earley)

`parsing` is a self-contained parse engine that runs **directly over an
`IrAst`**: a deterministic **predictive PDA** for the common case, backed by a
scannerless [Earley](https://en.wikipedia.org/wiki/Earley_parser) engine (full
SPPF, Scott 2008) as the sound completion. No meta-grammar strings, no
external parser. The premise: an `IrAst` already *is* a grammar — named rules,
each an alternation of sequences of atoms — so it drives a parser as-is.

**One engine, one product, PDA-first:**

- **instance text → model** — `parse_model(grammar, text, fold)`: parse
  input against a compiled grammar's rules and build the model object
  through the `ModelFold`.

The entry runs the PDA first — a table-driven predictive walk that builds
the product *during* the parse (no intermediate `ParseTree`) — and complete
on the Earley engine whenever the PDA cannot decide deterministically. That
policy, the PDA compilation, and its per-grammar memoisation all live inside
this package; consumers see one call. `lexic.compile` (the runtime's sole
consumer) imports nothing but this package's root API.

```
parse_model(grammar, text, fold)
        │  (once per grammar, memoised)
        ├─ lift + normalize ─► model PDA tables
        └─ lift + normalize ─► Earley tables
        │  (per parse)
        ├─ PDA walk ───────────────────► model
        └─ on PdaFail: parse_first + fold ─► model
```

---

## 1. Public API (`__init__.py`)

One product entry and six Earley functions. Everything a consumer needs
is exported from the package root; nothing outside `lexic.parsing` imports
its submodules (enforced by the layering test).

| Function | Returns | Meaning |
|---|---|---|
| `parse_model(grammar, text, fold: ModelFold[M])` | `M` | **Instance product.** PDA-first, `parse_first` + fold completion. Same authored-grammar contract; memoised per (grammar, fold) identity — the tables bake the fold's rule records and the collapsed lexical runs. Generic in the model type `M` the fold produces: the engine stays a leaf w.r.t. `lexic.model`, so the concrete model type rides the fold's type parameter rather than an import — `compile.py` binds `ModelFold[GrammarModel]`, so `CompiledGrammar.parse` types as `GrammarModel`. |
| `recognize(grammar, text)` | `IrInt` 0/1 | Does `text` derive from the start rule? (No forest built.) |
| `parse(grammar, text)` | `ParseTree` | The single derivation. **Raises** on no-parse *or* ambiguity. |
| `parse_first(grammar, text, tables=None)` | `ParseTree` | The *first* derivation — deterministic under ambiguity. Raises only on no-parse. |
| `parse_forest(grammar, text)` | `SppfNode` \| `IrNone` | The shared packed parse forest root, or `IrNone` on no-parse. |
| `derivations(grammar, text)` | `IrSeq[ParseTree]` | *Every* derivation, nothing silently dropped. |
| `is_ambiguous(grammar, text)` | `IrInt` 0/1 | More than one derivation? (Short-circuits at 2.) |

Also exported from the root: `ModelFold` (and its authoring
types), `ParseTree`, `SppfNode`, `ParserTables`, `compile_tables`,
`normalize`, `lift_optional_nullables` — plus the rest of the forest/chart
toolkit the root exports today (`Chart`, `Links`, `Link`, `EarleyItem`,
`Kernel`, `FastTree`, `EarleyParser`, `BuildTree`), which stays. Per the
IR's no-`IrBool` rule, a truth value is an `IrInt ∈ {0, 1}`.

> **Two grammar contracts.** The product entry takes the **authored**
> grammar and own the whole compilation pipeline internally. The tree/forest
> functions (`recognize` through `is_ambiguous`) are the lower-level Earley
> toolkit and take an **Earley-normalised** grammar (every quantifier
> `(1, 1)`, every group a named rule — `normalize()` is exported for this).
> The forest functions are Earley-only by construction: the PDA is
> fold-fused and never builds a tree or an SPPF.

`PdaFail` — the PDA's non-determinism signal — is internal to the package.
It is raised and caught inside the product entry; no caller ever sees it.

## 2. The design in one sentence

**The grammar compiles once; the paid loop runs over the compiled form.**
`compile_tables()` and the PDA compile are the parser's "codegen moment":
exactly as `codegen/` emits Python classes from an `IrAst`, `earley/tables.py`
and `pda/clones.py` compile an `IrAst` into flat int-coded tables, and
`earley/kernel.py` / `pda/runtime/kernel/kernel.py` run over them with no per-item IR
dispatch, no IR object as a hot-path key, and no tuple allocation per
advance.

The IR seams sit at the edges, all IR-native: the compiles walk the grammar
in; `ModelFold` / the fused PDA build carry the model out;
`Kernel.to_chart()` decodes the packed
SPPF into the IR-native `Chart` for the forest readers. State objects
(`ParserTables`, `Kernel`, `PdaKernel`) ARE-AN `IrLeaf`; logic lives on
classes and per-parse state on cursors — but inside the kernels the per-item
work is list indexing and int arithmetic, deliberately: the package's
compiled-form zone, the scoped relaxation of per-item IR dispatch that the
measured performance floor demands.

## 3. Package layout

```
parsing/
  __init__.py       the public API (§1): one product entry + the Earley toolkit
  fold.py           ModelFold — the authored instance fold (§8)
  caches.py         the identity-memo registry — what every `id()`-keyed cache
                    registers with, and how an artefact's death frees it
  earley/           the Earley engine (imports only itself)
    tables.py         ParserTables, compile_tables (memoised per IrAst identity)
    kernel.py         Kernel — predict/scan/complete, Leo, packed SPPF; FastTree;
                      longest_start_completion (the PDA island seam)
    chart.py          Chart/Links — the decoded SPPF; EarleyItem
    engine.py         per-capability orchestration nodes behind the public API
    forest.py         ParseTree, SppfNode, trampolined enumeration
    normalize.py      desugar IR into classical Earley shape (§6)
    lexruns.py        derived run terminals (§5)
    trampoline.py     depth-safe generator driver
  pda/              the predictive PDA (imports earley/) — a one-way
    │               core ← analysis ← compiler ← runtime chain
    core/             shared leaves (imported everywhere, import ~nothing)
      charsets.py       CharSet — polarity-aware co-finite char sets (§9)
      scanner.py        structured-noise recognizer + ScanGate runtime (§10)
      errors.py         PdaFail — internal, never user-facing
    analysis/         decide every point, then store the gate specs (§10)
      analysis.py       GrammarAnalysis — fixpoints + the decision taxonomy
      noise.py          noise/semantic attribution — peek + structured gates
      structured.py     folding-aware structured/probe gates
      kwindow.py        FIRST_k over CharSet tuples — bounded-lookahead gates
      taxonomy.py       Taxonomy — classified notes + the stored gate specs
    compiler/         compile the IrAst into flat int-coded tables (§11)
      clones.py         the model clone compiler
      specs.py          the compiler-intermediate NamedTuple vocabulary
      flatten.py        the int-coded runtime program + optimizer passes
      delegate_compile.py DelegateSource — island-interior delegation (§13)
    runtime/          execute the tables — the fused model build (§12)
      kernel/           the driver and its shed halves
        kernel.py         PdaKernel — the fused model runtime
        decisions.py      the attempt/probe method group the kernel inherits
      admission.py      attempt-seam leaves — admission tests, scratch, stack copy
      build.py          frame-slot layout + the fused model-build tail
      matchers.py       terminal matching — the cursor-free recognition leaf
      islands.py        the windowed Earley island sub-parse (§13)
```

Each folder carries its own `README.md` orientation note. Layering: the
whole package is a leaf w.r.t. `lexic.compile` and `lexic.grammars`; `pda/`
imports `earley/`, never the reverse. Inside `pda/` the arrows point one
way — `core ← analysis ← compiler ← runtime`: `analysis/` imports only
`core/`, `compiler/` imports `analysis/` + `core/`, `runtime/` executes
what `compiler/` produced. Cross-module imports use **public names only** —
a name two modules share is public at its defining module; `_underscore`
names never cross a module boundary. Consumers import the package root
only. All of this is enforced by `tests/integration/
test_layering_invariants.py`.

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
needs a shorter match). The fold-side licence is
`fold.collapsed_fold_tables` (safe iff no constructor-bearing rule sits
among a run's unit leaves). Collapsed tables are per (policy, grammar) and
memoised; `parse`/`recognize`/forest readers keep plain tables and exact
`ParseTree` shapes.

## 6. Normalisation (`earley/normalize.py`)

Two `IrTransformer` canonicalisations precede either compiled form: inline
groups hoist to fresh synthetic rules (prefix `__`), and non-`(1, 1)`
quantifiers desugar to synthetic right-recursive rules (`*`/`?` nullable; Leo
keeps the recursion linear). Large *bounded* counts (`{lo, hi}`) still unroll
`hi`-deep at desugar time — the one remaining rough edge.

## 8. The instance fold (`fold.py`) — text → model

Instance parsing runs over the **real codegen grammar** (no wrapper rules, no
name protocol): `normalize()` replaces items in place, so `kids[i] ↔ items[i]`
positionally. `ModelFold[M]` is a positional tree → model fold, generic in the
model type `M` it produces (`apply -> M`), whose
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

`GrammarAnalysis` runs over a lifted grammar and computes the classical
predictive fixpoints — nullability, FIRST (over `CharSet`), **hard-FIRST**
(the chars a construct *requires*), FOLLOW and hard-FOLLOW — then classifies
every decision point (arm selection; loop take/skip). A decision no gate
family can make deterministic becomes an **island** (§13); everything else
compiles to a gate. The gate families, tried in order:

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
  a compiled noise recognizer, for loops AND for arm selection (including
  alternations with an empty/all-nullable arm): `SG_MATCH` (exact-match loop
  over a non-semantic ref, licensed by noise-only exits or a semantic-follow
  clearance check), `SG_SCAN` (skip noise roots, peek disjoint content
  leads), `SG_PROBE` (overlap refuted by the unique next-construct header,
  e.g. GBNF's `rulename n* "::="` — which also covers an empty arm abutting
  the next rule) → `ScanGate`.
- **noise-greedy licence** (`noise.py`) — a greedy over-eat is provably
  noise↔noise re-splitting only (`sem_follow_table`: the chars that can
  follow a rule as *semantic* content), so greedy is safe.

A gated decision's spec is **stored** on the public `taxonomy: Taxonomy`
attribute — the clone compiler *reads* it back, never recomputes. A decision
the cascade cannot license — including an arm-FIRST overlap with no stored
spec — **islands its rule**: sound and fail-soft, never a guessed gate,
never a whole-grammar refusal. That call is made in the analysis itself:
the island set is closed before the clone compiler runs. A stored gate spec
the compiler cannot attach to the arms it sees (taxonomy↔compiler
misalignment) is a **hard error**, not an island — drift is a bug. Every
per-atom-type decision routes through an open `IrTypeMap` with a raising
default (a genuine boundary error, not a downgrade); `nullable_names` here
is the single source `fold.lift_optional_nullables` reads.

## 11. The clone compiler (`pda/clones.py`, `pda/flatten.py`)

The clone compiler is **total**: it always returns tables. A rule is
compiled once per distinct **hard continuation** that reaches it (a
*clone*), because the stop-sets it bakes are call-site-exact. Each item
lowers to a tuple-coded `ItemSpec` (`lit`/`cc`/`ref`/`grp`) carrying its
bounds and loop gate (`StopGate`/`PairGate`/`KTupleGate`/`PeekGate`/
`ScanGate`); arm selection is FIRST-gated `ArmSpec`s (per-arm gate specs are
attached inside the compiler's own arm enumeration so spec↔arm alignment
cannot drift) plus at most one nullable default. Every clone bakes its
`RuleFold`; island rules are not cloned (`IslandRef`, §13). A start rule
that is itself an island compiles to a start that fails immediately to the Earley completion: the
tables are still total, there is no `None` and no windowed self-parse of
the whole input. The `CloneSpec`/`ItemSpec`
NamedTuples are the compiler *intermediate* (what the structural tests pin);
`flatten.py` lowers them once per compile into the int-coded `PdaProgram`
(flat clone/arm records, op-codes, pre-resolved membership sets, the gate
runtimes — the EOF-exact ≤k window matcher, the non-consuming noise-skip
peek, the arm-side scan selector) and runs the post-flatten optimizer passes
(exactly-once terminal/call specialisation, `value_str` inlining, frame-less
leaf marking, pass-through dispatch conversion). Everything `flatten.py` exposes to its
sibling consumers (op-codes, flat records, gate helpers) is public by name.

## 12. The fused runtime (`pda/runtime/kernel/`)

`PdaKernel` is the model runtime: an explicit descent stack of flat list
frames (no Python recursion) walks the int-coded `PdaProgram`, **building the
model during the walk** — no `ParseTree`. Terminal quantifier loops match
inline; capture frames own per-item spans and sub-model sinks, capture
bubbles to the nearest bound item through transparent frames (groups,
no-constructor clones) exactly as `ModelFold` collects. `pda_model` is the
single predictive runtime entry. On *any* non-deterministic point the runtime raises **`PdaFail`**
(`errors.py`) — caught inside the product entries, which retry on the Earley
completion; the completion owns user-facing diagnostics.

## 13. Islands and delegation (`pda/islands.py`, `pda/delegate_compile.py`)

**Islands are the engine's only escape mechanism, and they are per-rule.**
A decision no gate family can license makes its rule an island: the ref is
compiled as an `IslandRef` marker with a lazy per-island `ParserTables`
cache, and the runtime runs a **windowed Earley sub-parse**
(`longest_start_completion`, doubling window) over just that span, folds the
sub-tree, and splices the sub-product into the current capture. A
**fail-island** (a semantic escape whose ref must fail to the full engine)
raises `PdaFail` instead. `DelegateSource` cuts island cost from the inside:
it selects conflict-free, non-nullable, semantic *interior* rules of an
island above a triviality floor and compiles each to its own PDA clone cut
against the sub-grammar's hard FOLLOW, so the island's Earley sub-parse runs
those interiors on clones rather than the item machinery — always on,
unconditional. Everything here is fail-soft: a declined delegate falls
through to normal prediction; a failed island fails the PDA parse into the
Earley completion.

## 14. Invariants

- **Grammar is canonical.** Neither engine mutates the grammar; every table
  is its compiled representation, rebuilt from it alone.
- **PDA-first, engine-sound, total.** The PDA is an optimisation, never a
  semantics: any non-deterministic point raises `PdaFail` internally and the
  Earley completion reparses. Islands are the only escape — per-rule,
  fail-soft. There is **no whole-grammar opt-out and no PDA-less mode**;
  `UnsupportedConstructError` marks genuine boundary errors only and is
  never caught into a downgrade.
- **The engine owns its API.** Both products are package-root entries;
  consumers import the root only; `PdaFail` never crosses the package
  boundary. No `_underscore` name crosses any module boundary.
- **Gates are stored, not recomputed.** The analysis is the one place a
  demotion decision is made; the clone compiler reads `taxonomy` back. An
  unexplained overlap islands the rule — never a guessed gate.
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
