# `lexic.parsing` — IR-native parsing (Earley + predictive PDA)

`parsing` is the Lark replacement: a scannerless [Earley](https://en.wikipedia.org/wiki/Earley_parser)
parser that runs **directly over an `IrAst`**, plus a **predictive PDA** sibling
that fuses parse and fold for the deterministic common case. No meta-grammar
string, no Lark grammar generation, no external parser. The premise is that **an
`IrAst` already *is* a grammar** — a set of named rules, each an alternation of
sequences of atoms — so it can drive a parser as-is.

**One engine, two jobs.** The same package drives both halves of the pipeline:

- **grammar-text → `IrAst`** — `parse_grammar` parses a `.gbnf`/`.abnf` file
  against the flavour's own self-grammar (`GBNF_GRAMMAR`/`ABNF_GRAMMAR`), fusing
  the Earley forest straight to IR through the flavour's `Reducer` (§8).
- **instance text → `GrammarModel`** — `CompiledGrammar.parse` parses input
  against the *codegen grammar*, building the Pydantic model. This path runs
  **PDA-first** (§10): a deterministic predictive runtime that builds the model
  during the walk, falling back to the Earley engine + a positional fold (§9) on
  any non-deterministic point.

The self-hosting fixpoint is the proof of the first job: take the ABNF-of-ABNF
grammar expressed as IR (`grammars/abnf.py`'s `ABNF_GRAMMAR`), emit its own
source text, parse that text back with itself, reduce, and recover the identical
`IrAst`.

**On the grammar-text product metric (text → `IrAst`) the Earley engine beats
Lark ~2×** — see §14.

```
── grammar-text path (parse_grammar) ───────────────────────────────────────────
grammar (IrAst) ─► normalize() ─► compile_tables() ─► ParserTables   (once/grammar)
text (str) ──────────────────────► Kernel(tables, text).run()        (per parse)
                                          │
                        FusedReduce ──► IrAst        (the product path, §8)

── instance path (CompiledGrammar.parse) ───────────────────────────────────────
codegen grammar ─► compile_pda() ─► PdaTables ─┐
                └─► normalize()  ─► ParserTables┤                   (once/grammar)
text (str) ─► parse_pda(pda, text, fold) ───────┼─► GrammarModel     (PDA-first, §10)
              └─PdaFail─► fold.apply(parse_first(tables, text)) ─► GrammarModel (§9)
```

---

## 1. Public API

Seven functions in `__init__.py`. Each is a thin wrapper that boxes the input
and drives exactly one `IrSelf` orchestration node in `engine.py`. Per the IR's
no-`IrBool` rule, a truth value is an `IrInt ∈ {0, 1}`.

| Function | Returns | Meaning |
|---|---|---|
| `recognize(grammar, text)` | `IrInt` 0/1 | Does `text` derive from the start rule? (No forest built.) |
| `parse(grammar, text)` | `ParseTree` | The single derivation. **Raises** on no-parse *or* ambiguity. |
| `parse_first(grammar, text, tables=None)` | `ParseTree` | The *first* derivation — deterministic under ambiguity. The instance-parse entry (§9). Raises only on no-parse. |
| `parse_reduced(grammar, text, reducer)` | `IrSelf` | **The grammar-text product path**: text → reduced IR in one fused pass. Raises like `parse`. |
| `parse_forest(grammar, text)` | `SppfNode` \| `IrNone` | The shared packed parse forest root, or `IrNone` on no-parse. |
| `derivations(grammar, text)` | `IrSeq[ParseTree]` | *Every* derivation, nothing silently dropped. |
| `is_ambiguous(grammar, text)` | `IrInt` 0/1 | Does the input have more than one derivation? (Short-circuits at 2.) |

The predictive PDA (§10) is driven through `compile.py`, not `__init__.py`:
`compile_pda(...) → PdaTables` and `parse_pda(pda, text, fold) → model`.

```python
from lexic.parsing import parse, parse_reduced, parse_first, recognize
from lexic.parsing.earley.normalize import normalize

g = normalize(MY_GRAMMAR)            # desugar to classical Earley shape first
assert recognize(g, "input text")    # IrInt(1)
tree = parse(g, "input text")        # a ParseTree (strict; raises on ambiguity)
ir = parse_reduced(g, "input text", MY_REDUCER)   # straight to IR — the product
```

> **The grammar must be normalised first** (§6). The parser assumes classical
> Earley shape: every quantifier is `(1, 1)` and every group is a named rule.
> Multi-char literals stay atomic (§5). `normalize()` is the caller's
> responsibility — kept separate so the desugaring stays isolated. The instance
> path normalises `lift_optional_nullables(codegen_grammar)` (§9).

---

## 2. The design in one sentence

**The grammar compiles once; the paid loop runs over the compiled form.**
`compile_tables()` / `compile_pda()` are the parser's "codegen moment": exactly
as `codegen/` emits Python classes from an `IrAst` (grammar stays ground truth,
the classes are its compiled representation), `tables.py`/`pda_tables.py` compile
an `IrAst` into flat int-coded tables, and `kernel.py`/`pda_kernel.py` run over
them with no per-item IR dispatch, no IR object as a hot-path key, and no tuple
allocation per advance.

The IR seams sit at the edges, all IR-native:

- **in:** `compile_tables(IrAst) → ParserTables` and
  `compile_pda(IrAst, …) → PdaTables` walk the grammar (memoised per grammar
  object, like constructing a `lark.Lark`);
- **out (grammar-text product):** `FusedReduce` folds the packed forest to IR
  against the flavour's `Reducer` policy tables (`IrMap`s of IR bodies);
- **out (instance product):** `ModelFold` folds a `ParseTree` to a
  `GrammarModel`, or `PdaKernel` fuses that fold into the parse and skips the
  tree entirely;
- **out (general):** `Kernel.to_chart()` decodes the packed SPPF into the
  IR-native `Chart` for the trampolined forest readers.

State objects (`ParserTables`, `Kernel`, `PdaKernel`, `KernelState`) ARE-AN
`IrLeaf`; logic lives on classes and per-parse state on cursors — but inside the
kernels the per-item work is list indexing and int arithmetic, deliberately:
this is the package's compiled-form zone, the scoped relaxation of per-item IR
dispatch that the measured performance floor demanded.

## 3. The compiled Earley tables (`tables.py`)

Every dotted position of every arm gets one int `code`, laid out so
consecutive dots are consecutive ints — **advancing an item's dot is `+ 1`**.
One flat list discriminates the classic Earley trichotomy with a single index:

| `next_sym[code]` | meaning |
|---|---|
| `rule_id + 1` (> 0) | dot faces that non-terminal — predict |
| `-(term_id + 1)` (< 0) | dot faces that terminal atom — scan |
| `0` | dot past the arm's end — complete |

An **Earley item** is the single int `code << 20 | origin` (a single-digit
CPython int for realistic grammars — set/dict operations at the primitive
floor); an **SPPF handle** `(item, end)` packs the same way again. Value-equal
arms of one rule intern to a single arm (the IR node IS its value), matching
the legacy item tuples' value semantics.

`ParserTables` splits along consumers: `CodeTables` (the code-space half the
loop indexes per item), `DecodeTables` (the IR-space half used only when
results decode back to IR), plus the terminal atoms, per-terminal scan kinds
(`term_lens`), and two per-grammar lazy caches (char → accepting terminals,
char → interned `IrLiteral`). `nullable_completes` precomputes the
Aycock-Horspool advance set per nullable rule.

## 4. The Earley kernel (`kernel.py`)

`Kernel(tables, text, record_links).run()` is the whole Earley loop: close
each column to a fixpoint (predict / complete, dispatched by one `next_sym`
index), scan between columns. Per-column indexes are position-indexed lists of
small containers keyed by bare `rule_id`/`term_id` ints — `seen` (dedup),
`waiting` (completer), `scannable` (scanner), `predicted`, and the Leo memo.

- **SPPF (Scott 2008), preserved in full.** `st.links[handle]` records packed
  families `(predecessor, pred_end, child)`; a key reached two ways files an
  additional family; identical families dedup; ≥ 2 families ⇒ ambiguity
  point. `child` is a packed handle or the consumed text itself.
- **Aycock-Horspool nullable advance**, recording the completer's own
  empty-completion handle so the two provenances collapse into one family.
- **Leo right recursion (Leo 1991).** A deterministic right-recursive
  completion jumps to the chain's topmost item; the skipped completions are
  deferred in `st.leo_links` (a *bucket* per top — converging ambiguous
  chains each file their bottom) and rebuilt lazily by `expand_leo`, O(chain),
  only when a derivation actually walks them. The climb rejects
  **same-column (empty-span) steps** — they are cycle- and ambiguity-prone
  and carry no asymptotic benefit, so the normal completer (which records
  every family) handles them; columns then strictly decrease up the climb and
  no cycle guard is needed.
- **Recognition skips the forest** (`record_links=False`) — no links, no
  allocation beyond the chart itself.
- **`longest_start_completion`** — a public windowed prefix-completion seam:
  run the start rule over a text window and return the longest completion. The
  PDA island sub-parse (§10) uses it; it is additive, off the main `run()` fast
  path.

`FastTree` is the unambiguous fast path: an explicit-stack walk of the packed
links building the single `ParseTree` (memoised per handle); any key packing
more than one family aborts to the trampolined enumeration over the decoded
chart. Depth lives in lists, never the C stack (N = 60,000 verified).

## 5. Scanning: chars, literals, runs

The scanner resolves which terminals a character can begin once per distinct
char (cached on the tables), then reads each column's `scannable` bucket:

- a **char class** advances one column;
- a **multi-char literal** is atomic — one C-level `text.startswith` and the
  advance lands k columns ahead (`normalize` no longer splits literals);
- a **run terminal** (§7) consumes its maximal run in one step and lands at
  the run's end.

## 6. Normalisation (`normalize.py`)

Two canonicalisations precede Earley, both `IrTransformer`s:

1. **Flatten inline groups** — an `IrAlternation` used as an atom is hoisted
   to a fresh synthetic rule (prefix `__`), keeping its quantifier.
2. **Desugar quantifiers** — a non-`(1, 1)` quantifier becomes a synthetic
   right-recursive rule (`*` → `X = "" / elem X`; `+` → `X = elem / elem X`;
   `?` → `X = "" / elem`; bounded counts unrolled). The `*`/`?` rules are
   *nullable*; Leo (§4) keeps the right recursion linear where it survives.

Large *bounded* counts (`{lo, hi}`) still unroll `hi`-deep at desugar time —
the one remaining rough edge.

## 7. Run terminals (`lexruns.py`) — the derived lexer

Lark's decisive constant-factor advantage was never a C parser (it has no C
extensions): its *dynamic lexer* matches hand-declared tokens with compiled
regexes, so its Earley loop steps over **tokens** (~5 chars each on the ABNF
workload) while a scannerless engine steps over **chars**. `lexruns.py`
closes that gap by *deriving* the token layer from the grammar — and unlike
Lark's silently-incomplete maximal munch, the collapse is **proved** safe:

A synthetic star/plus rule collapses into a single maximal-munch `RunTerm`
when:

1. **Fixed charset** — the unit resolves to a set of single chars (a terminal,
   or transitively a rule whose every arm is one such atom);
2. **Derivation uniqueness** — charset-rule alternatives are pairwise
   disjoint, so the collapse cannot hide ambiguity from the SPPF;
3. **Follow disjointness** — `FOLLOW(rule) ∩ charset = ∅` (classic
   FIRST/FOLLOW over the compiled tables), so no continuation can ever
   require a shorter-than-maximal match.

A char class too large to expand poisons the sets it touches and the affected
rules simply stay per-char. The reducer-side half of the decision lives in
`reduce.collapsed_tables(reducer, grammar)`: a run may only collapse when its
per-char reduction contributions are reconstructible from the run text — the
unit's leaf rules are DROP noise (`RUN_DROP`), YIELD text rules (`RUN_STR`), or
a bare terminal under the literal policy (`RUN_LEAF`). Anything else stays
per-char for that reducer. Collapsed tables are therefore **per (reducer,
grammar)** and memoised; only `parse_reduced` uses them — `parse`/`recognize`/
forest readers keep the plain tables and their exact `ParseTree` shapes. The
instance path has a sibling licence in `fold.collapsed_fold_tables` (§9).

On the ABNF self-host workload all six repetition rules collapse (wsp runs,
rulename tails, digit/hex runs, char-val bodies), which is most of the input.

## 8. Reduction (`reduce.py`) — the grammar-text meta-notation seam

A flavour's "meta notation" is `reductions` (an `IrMap` from a rule's
`IrRuleRef` to a body folding the rule's matched children into IR) and a
cleaning policy (`noise` per child rule: `DROP`/`KEEP_REDUCED`/…; `literal` for
terminal leaves). `YIELD` recovers a subtree's source text.

Two folds implement it:

- **`FusedReduce` — the product path.** One explicit-stack pass folds the
  packed SPPF straight to IR: no intermediate `ParseTree`. A `ReducePlan`
  (cached per reducer × tables) compiles the policies against the rule
  numbering; synthetic nodes splice; run children reconstruct per §7; and a
  rule whose body IS `YIELD` reduces to its **source span** —
  `text[origin:end]`, O(1) — whenever no DROP-noise rule is reachable
  beneath it (`can_drop` reachability), skipping the whole subtree. Any shape
  the plan can't compile (ambiguity, KEEP_RAW/custom noise) returns a miss and
  the caller falls back to a fresh plain-tables parse + the legacy fold.
- **`Reducer` over a `ParseTree`** — the general fold, driven by the
  iterative `_FastReduce` (explicit stack) with the trampolined
  `ReduceSource`/`ResolveSource` as its lineage. Feeds on `parse()` output.

## 9. The instance fold (`fold.py`) — text → `GrammarModel`

Instance parsing runs over the **real codegen grammar** (no `--f<idx>` wrapper
rules, no name protocol): `normalize()` replaces items in place, so an original
item is always exactly one symbol slot in the normalised arm — for a rule's
`ParseTree` node, `kids[i] ↔ items[i]`. `ModelFold` is a generic positional
tree → object fold whose authored form is a per-rule IR body-table
(`IrMap[IrRuleRef, ModelBody]`) that bakes to the plain-data config the compile
seam builds (`RuleFold(kind, ctor, n_items, fields)`, each field a
`FieldFold(item, mode, name, lo)`). It imports no `RuleSpec`, pydantic, or
`codegen`.

Fold behaviour per `kind` (`codegen/binding.py`'s `RuleKind`):

- `value_str` → `ctor(value=<subtree text>)`;
- `alternation` → pass-through to the single sub-model under the node (the
  matched arm's model identifies itself);
- `sequence` → per field, `kids[item]`: `text`/`gtext` take the slot's consumed
  text, `model`/`models` collect folded sub-models through synthetic layers;
  `None` values are omitted. A zero-kid node when `n_items > 0` is the rule's
  empty alternate arm → `ctor()`.

Instance parsing runs `parse_first` (deterministic first derivation) because an
all-nullable arm or an ambiguous rule (e.g. `json_ws`'s `int`) would otherwise
make the empty match ambiguous. `lift_optional_nullables` (`R? → R` for nullable
`R`) encodes that engine-ambiguity policy at normalise time; `collapsed_fold_tables`
is the fold-side run-collapse licence (safe iff no constructor-bearing rule sits
among a run's unit leaves).

## 10. The predictive PDA (the hybrid-parse fast path)

For the deterministic common case, the instance path does not run Earley at all.
`CompiledGrammar.parse` runs a **table-driven predictive parser** that builds the
model *during the walk* (the fold is fused into the parse — no `ParseTree`), and
falls back to Earley + `ModelFold` (§9) only where the grammar is genuinely
non-deterministic. The whole PDA is compiled out of the same codegen grammar and
opts *out* per-grammar (returns no PDA) when it meets a construct it can't handle
soundly (an unsupported construct, or a start rule that is itself an island).

**`charsets.py` — `CharSet`.** A polarity-aware `(chars, negated)` character set:
when `negated`, the set is every character *except* `chars`. Every operation
(`has`/`union`/`subtract`/`overlaps`) is exact across all four polarity
combinations, so an `IrNot([^"])` loop's co-finite FIRST stays exact instead of
"poisoning" its rule into a fake island. FOLLOW seeds end-of-input as the
character `""` in a *positive* set; `CharSet.ANY` (every real character) excludes
it, since EOF is not a character to exclude *from*.

**`analysis.py` — `GrammarAnalysis`, the compiler's oracle.** Over a *lifted
codegen grammar* it computes the classical predictive fixpoints — nullability,
FIRST (over `CharSet`), **hard-FIRST** (FIRST with nullable items skipped: the
chars a construct *requires*), FOLLOW (and hard-FOLLOW) — plus 2-char prefix
sets (the LL(2) discriminator, e.g. chess `fxf5` vs `f5`). It then runs the
**pivot-6 decision taxonomy**, classifying each decision point `island` /
`stopset` / `("pairs", set)` and yielding `conflicts` (the island set),
`demoted`, and `fail_islands` (semantic F1 stop-set-escape rules whose refs
*must* fail to the engine). Every per-atom-type decision routes through an open
`IrTypeMap` of `IrLambda` bodies (the `codegen.binding.mode_for` idiom); an
unknown atom raises `UnsupportedConstructError`, never a silent classify. Also
homes `nullable_names` (the single source `fold.lift_optional_nullables` reads).

**`pda_tables.py` — the clone compiler.** `compile_pda(lifted, instance_grammar,
fold_config) → PdaTables`. A rule is compiled once per distinct **hard
continuation** that reaches it (a *clone*, pivot 3), because the loop stop-sets
it bakes are call-site-exact (pivot 4). Each item lowers to a flat tuple-coded
`ItemSpec` (`lit`/`cc`/`ref`/`grp`) carrying its bounds and a loop gate — a
`StopGate` (non-greedy on `FIRST(atom) − continuation`) or a `PairGate` (an LL(2)
2-char prefix set). Arm selection is a list of FIRST-gated `ArmSpec` + at most
one nullable default. Every clone bakes its `RuleFold` so the runtime needs no
per-parse config lookup; a pure-terminal clone is flagged `match_only` (the
runtime slices `text[a:b]` instead of building sub-models). **Islands are not
cloned** — a reference to one carries an `IslandRef` marker and a lazy per-island
`ParserTables` cache; a *fail-island* ref (`IslandRef.fail`) is never parsed, the
runtime raises `PdaFail`.
The `CloneSpec`/`ItemSpec` NamedTuples are the compiler *intermediate* (what the
structural tests pin); `_flatten_program` lowers them, once per compile, into the
int-coded `PdaProgram`, kept on `PdaTables` alongside `.clones` (`.clones` for
islands/introspection, `.program` for the hot loop).

**`pda_flatten.py` — the flat runtime program.** The leaf half of the flatten:
`_FlatClone`/`_FlatArm`, `_OP_*` op-codes, pre-resolved `(chars, negated)`
membership sets — plus the post-flatten optimizer passes (`_optimize_program`:
exactly-once terminal/call specialisation, `value_str` inlining, frame-less leaf
marking, pass-through dispatch conversion). It imports nothing from `pda_tables`
(a leaf w.r.t. the compiler and the specs); the `spec → flat` bridge lives beside
the specs it reads.

**`pda_kernel.py` — `PdaKernel` / `parse_pda`, the fused runtime.** An explicit
descent stack of flat list frames (no Python recursion) walks the int-coded
`PdaProgram`, building the model directly. Terminal quantifier loops match inline
(`_match_lit`/`_match_cc`, no per-char call). A *clone frame* with a build-mode
captures what its fold needs and builds exactly one model on completion; a
*transparent frame* (inline group, or a no-constructor clone) funnels every model
inside it to its sink; capture bubbles to the nearest enclosing *bound* item,
through any number of group/loop layers — exactly as the fold's `_models_at`
collects. An **island** ref runs a windowed Earley sub-parse over `island_tables`
(`longest_start_completion`, doubling window, `FastTree` with first-derivation
fallback), folds it through the supplied `ModelFold`, and splices the
sub-model into the current capture. With no fold (`fold=None`, the island-free
path) or a fail-island ref, it raises `PdaFail`. **`PdaFail` is internal** —
caught by the compile seam and retried on the full engine, which owns the
user-facing diagnostics; it never surfaces to the caller.

## 11. Forest & ambiguity (`forest.py`, `chart.py`)

Ambiguity is never silently resolved on the strict path: `parse`/`parse_reduced`
raise on it; `parse_forest`/`derivations`/`is_ambiguous` expose every reading.
(`parse_first` — the instance entry — deliberately takes the first derivation
instead.) The general readers work over the IR-native decoded `Chart`
(`Kernel.to_chart()` expands all deferred Leo chains first): `SppfNode` handles,
the lazy replayable `IrStream`, and the depth-safe trampolined enumeration cogens
(`NodeDerivs`, `PrefixSource`, `ChildDerivs`). `BuildTree` is the strict
single-derivation façade over that path. `EarleyItem` — the decoded dotted-arm
tuple `(ref, seq, origin, end)` — lives in `chart.py`.

## 12. Module map

| Module | Responsibility |
|---|---|
| `tables.py` | `ParserTables`/`CodeTables`/`DecodeTables`, `RunTerm`, `compile_tables` (memoised) / `build_tables` (variants). |
| `kernel.py` | `Kernel` — the flat Earley loop (predict/scan/complete, Leo, packed SPPF), `FastTree`, `longest_start_completion`, decode to `Chart`. |
| `lexruns.py` | Run-terminal derivation: charset resolution, FIRST/FOLLOW, the three collapse proofs. |
| `normalize.py` | Desugar IR into classical Earley shape (groups, quantifiers). |
| `reduce.py` | `Reducer` + policies, `FusedReduce`, `ReducePlan`, `collapsed_tables` — the grammar-text product. |
| `fold.py` | `ModelFold` — the one authored instance-fold (`ParseTree` → model): an IR body-table (`IrMap[IrRuleRef, ModelBody]`) baking to `RuleFold`/`FieldFold` config; `lift_optional_nullables`, `collapsed_fold_tables`. |
| `charsets.py` | `CharSet` — polarity-aware co-finite char-set algebra (the PDA analysis substrate). |
| `analysis.py` | `GrammarAnalysis` — FIRST/hard-FIRST/FOLLOW/nullability + the pivot-6 island/stopset/LL(2) taxonomy; `nullable_names`. |
| `pda_tables.py` | `compile_pda` → `PdaTables` — per-(rule, continuation) clone compiler; `ItemSpec`/`ArmSpec`/`CloneSpec` specs, `IslandRef`, the spec→flat bridge. |
| `pda_flatten.py` | The int-coded runtime program (`PdaProgram`, `_OP_*`, membership sets) + post-flatten optimizer passes. |
| `pda_kernel.py` | `PdaKernel`/`parse_pda` — the fused predictive runtime (explicit frame stack, inline terminal loops, island sub-parse, `PdaFail`). |
| `engine.py` | The `IrSelf` orchestration nodes the public API drives. |
| `forest.py` | `ParseTree`/`SppfNode`, trampolined enumeration, `IrStream`, `BuildTree`. |
| `chart.py` | The decoded IR-native SPPF (`Chart`/`Links`) and the `EarleyItem` tuple alias. |
| `trampoline.py` | Depth-safe generator driver for the forest/reduce walks. |

## 13. Invariants

- **Grammar is canonical.** Neither engine mutates the grammar; the tables are
  its compiled representation, rebuilt from it alone.
- **PDA-first, engine-sound.** The PDA is an optimisation, never a semantics: on
  any non-deterministic point it raises `PdaFail` and the sound Earley engine
  reparses. Whole grammars opt out (no PDA) rather than parse a construct the
  clone compiler can't handle soundly.
- **Full SPPF.** Nullable completion (Aycock-Horspool), sharing and packed
  families (Scott 2008), exact ambiguity — including under Leo and under run
  collapse (both proved, §4/§7).
- **Depth-safe.** No tree walk recurses through the C stack (explicit
  stacks + trampoline; N = 60,000 verified) — including the PDA's descent stack.
- **One way per task.** One grammar-text product entry (`parse_reduced`), one
  instance product entry (`CompiledGrammar.parse`), one emit method.
- **The compiled-form zone is scoped.** Per-item IR dispatch is compiled away
  *inside* `kernel.py`/`tables.py`/`pda_kernel.py`/`pda_flatten.py` only; every
  seam in and out of the zone is IR-native, and orchestration, normalisation,
  analysis and reduction policy stay `IrSelf`/open-dispatch end to end.

## 14. Benchmark results (Earley grammar-text product vs Lark)

Measured with `zzz_current_work/bench_parsing.py` (2026-07-01), a
stage-for-stage race against **Lark 1.3.1** (`parser='earley'`, pure Python —
it ships no compiled extensions) on the ABNF self-host workload. Interleaved
medians; the `parse+reduce` row is the grammar-text product: text → `IrAst`.
Fixpoint holds on every path. (This measures the Earley engine, §3–§8; the
predictive PDA of §10 is a later, separate instance-parse fast path.)

### ABNF self-host (920 chars/copy)

| input | stage | Lark | `parsing` | ratio |
|---|---|---|---|---|
| x1 (920 ch) | recognize | 18.7 ms | **8.0 ms** | **0.42×** |
| | parse | 26.6 ms | 34.1 ms | 1.28× |
| | **parse+reduce** | 27.0 ms | **15.0 ms** | **0.55×** |
| x2 (1840 ch) | recognize | 36.9 ms | **15.2 ms** | **0.41×** |
| | parse | 52.4 ms | 64.3 ms | 1.23× |
| | **parse+reduce** | 53.7 ms | **28.9 ms** | **0.54×** |
| x4 (3680 ch) | recognize | 74.9 ms | **32.3 ms** | **0.43×** |
| | parse | 108.7 ms | 137.1 ms | 1.26× |
| | **parse+reduce** | 109.9 ms | **62.1 ms** | **0.56×** |

**The product beats Lark ~2× (44-48% faster) and recognition ~2.4×, stable
across sizes.** The rows are independent races, not an additive ladder — each
entry runs its own optimal pipeline: `recognize` on maximally collapsed
tables with no forest; `parse` on plain per-char tables (its contract is the
exact reducer-agnostic `ParseTree` — the one row still above Lark);
`parse_reduced` on reducer-collapsed tables plus the fused fold.

### Deep right-recursion — `S = "a"*`

Linear (µs/N flat), no stack overflow, and 2.5–3× **faster** than Lark:

| N | parse→tree | µs/N | Lark | ratio | | recognize | µs/N | Lark | ratio |
|---|---|---|---|---|---|---|---|---|---|
| 400 | 3.50 ms | 8.8 | 10.75 ms | 0.3× | | (1600) 6.91 ms | 4.3 | 16.17 ms | 0.4× |
| 1600 | 14.10 ms | 8.8 | 40.49 ms | 0.3× | | (6400) 28.40 ms | 4.4 | 71.95 ms | 0.4× |

### Lineage

The pre-kernel, per-item-IrSelf engine's history (3.33× → 2.22× on the
product through OPT1–OPT-REDUCE) is recorded in
`zzz_current_work/postleo/HANDOVER_postleo.md`; the compile/kernel/runs
rework plan and its measured phase gates are in
`zzz_current_work/postleo/PLAN_obliterate_lark.md` (kernel (A) 2.22× → 1.45×;
fused reduce (B) → 1.07×; derived runs (C) → **0.52×**). The predictive-PDA
effort (§10) is recorded under `zzz_current_work/260705-hybrid-parse-poc/` and
`zzz_current_work/260706-unified-parse-engine/`.

## References

- J. Earley (1970), *An Efficient Context-Free Parsing Algorithm*.
- J. Aycock & R. N. Horspool (2002), *Practical Earley Parsing* — nullable completion.
- J. M. I. M. Leo (1991), *A general context-free parsing algorithm running in
  linear time on every LR(k) grammar without using lookahead* — right-recursion.
- E. Scott (2008), *SPPF-Style Parsing From Earley Recognisers* — the shared packed
  parse forest via provenance links.
