# `parsing/pda` — the predictive PDA

A table-driven predictive parser that runs **directly over an `IrAst`** and
builds the product — a model, or reduced IR — *during* the walk, with no
intermediate `ParseTree`. It is the fast path; a decision it cannot make
deterministically completes on the Earley engine (`../earley`). The failure
signal `PdaFail` is internal to the package and never reaches a caller: the
product entries in `parsing/products.py` catch it and complete on Earley.

## Parse-time flow

Compilation happens once per grammar (memoised), the walk once per input:

```
lifted IrAst ─► analysis: decide every point, store gate specs on taxonomy
             ─► compiler: bake clones + int-coded tables (read specs back)
             ─► runtime:  walk the tables, fold-fused, build the product
                          └─ island / no viable arm ─► PdaFail ─► Earley completion
```

Two invariants make this sound:

- **Decide, then store.** The analysis computes every gate spec and stores it
  on `taxonomy`; the compiler reads it back verbatim and never recomputes, so
  the runtime honors the same decision in every clone of a rule.
- **Totality without opt-out.** The island set — the decisions no gate family
  can license — is closed by the analysis **before** any clone is compiled.
  A stored spec the compiler cannot attach to the arms it sees is a hard
  `UnsupportedConstructError` (drift is a bug, not an escape), and a
  start-rule island compiles to an immediate-`PdaFail` start so the product
  simply completes on Earley per parse. There is no `PdaTables | None`
  channel and no whole-grammar refusal.

## The one-way chain

The package is a four-layer DAG — **every import points left, nothing
back-edges** — and the folders encode that invariant. Each carries its own
`README.md` with the per-module detail:

```
core ◄──── analysis ◄──── compiler ◄──── runtime
```

- **`core/`** — the shared substrate: `CharSet` (exact co-finite character
  algebra), the structured-noise `scanner` + `ScanGate`, and `PdaFail`.
- **`analysis/`** — `GrammarAnalysis`: the predictive fixpoints, the ordered
  gate cascade (1-/2-char → k-window → noise-skip peek → structured scan →
  noise-greedy licence), and the stored `taxonomy`.
- **`compiler/`** — the clone compiler: a rule compiled once per hard
  continuation into flat int-coded tables, the reduce-path bake, and
  island-interior delegation.
- **`runtime/`** — `PdaKernel`: the fused kernel that walks the tables and
  builds the model directly, its grammar-text twin, the shared frame/build
  vocabulary, and the windowed Earley island escape.

The whole package is a leaf w.r.t. `lexic.compile` and `lexic.grammars`, and
imports `../earley` but never the reverse.

See the package `README.md` (§9–§13) for the analysis, clone compiler, runtime
and island mechanics in full.
