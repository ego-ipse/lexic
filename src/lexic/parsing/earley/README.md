# `parsing/earley` — the scannerless Earley engine

A self-contained Earley recogniser/parser (full SPPF, Scott 2008) over
`IrAst`-shaped grammars. It is the **sound completion** the predictive PDA
falls back to whenever a decision cannot be made deterministically, and it
drives the tree/forest reader functions the package root exports. It imports
only itself — never `pda/`, never the wider runtime.

The engine takes an **Earley-normalised** grammar; `normalize()` is
re-exported from the package root for callers holding an authored grammar.

## `normalize.py` — desugar IR into classical Earley shape

The IR is richer than textbook BNF, so two canonicalisations precede Earley,
in order (the second assumes the first):

1. **Flatten inline groups** — an `IrAlternation` used as an atom (a
   parenthesised group) is hoisted to a fresh synthetic rule, so every atom
   after the dot is a ruleref or a terminal. The hoisted item keeps its
   quantifier.
2. **Desugar quantifiers** — a non-`(1, 1)` `IrItem` becomes a reference to a
   synthetic right-recursive rule (`*` → `X = "" / elem X`; `+` → `X = elem /
   elem X`; `?` → `X = "" / elem`; bounded counts unrolled). `*` and `?`
   introduce *nullable* rules — the shape the PDA's `lift_optional_nullables`
   and the ε-channel differential guard around.

## `tables.py` / `kernel.py` — the compiled-form recogniser

`compile_tables` walks the normalised grammar into int-coded tables, memoised
per `IrAst` identity. `Kernel` is the **compiled-form zone**: the predict /
scan / complete loop runs over those tables and packed-int items — an item is
`code << ORIGIN_BITS | origin`, advance is a single integer add, so for
realistic grammars items stay small CPython ints and set/dict membership is
cheap. Logic stays on the class and per-parse state on the `Kernel` cursor, but
no `eval` runs per item and no IR object is ever a hot-path key. The **Leo
optimisation** keeps right-recursive derivations linear. `to_chart` decodes the
finished SPPF back out for the IR-native forest readers.
`longest_start_completion` is the windowed prefix seam the PDA island sub-parse
calls to complete a bounded slice of the input.

## `forest.py` / `chart.py` — the shared packed parse forest

Following Scott (2008), the chart's family table **is** a shared packed parse
forest:

- `SppfNode` — a shared, packed handle for a dotted item over a span, the
  pure-data pair `(item, end)`; its packed families are read on demand, the
  same handle always exposes the same families (sharing), and `> 1` family
  means the node is **ambiguous**. The handle is intrinsically binary.
- `ParseTree` — **one** derivation: a non-terminal over a span with its
  children (sub-trees, or `IrLiteral` leaves for consumed characters). This is
  the reducible/foldable output.
- `Chart` / `Links` — the decoded SPPF; `EarleyItem` the readable item shape.

Enumeration over an ambiguous forest is trampolined (`trampoline.py`, a
depth-safe generator driver) so an arbitrarily deep right-recursive derivation
never recurses through the Python call stack.

## `lexruns.py` — proved maximal-munch collapse

A synthetic star/plus rule collapses into a single maximal-munch `RunTerm`
only when three facts are **proved**, so the collapse is exact rather than a
silent approximation: (1) **fixed charset** — the repetition unit resolves to
single chars, transitively; (2) **derivation uniqueness** — iterating the unit
splits a run one way only and the charset alternatives are pairwise disjoint,
so the collapse hides no ambiguity from the SPPF; and (3) the run's leaves
carry no model-bearing constructor (checked by the fold's collapse licence).

## `engine.py` — the IR seam

One `IrSelf` orchestration node per public capability, each compiling the
grammar (memoised), running one `Kernel`, and reading the result its own way:
`Recognize` (accept, SPPF off), `Parse` (the strict single derivation via the
packed-links `FastTree`, falling back to trampolined enumeration on ambiguity),
`ParseForest` / `Enumerate` / `IsAmbiguous` (decode the packed SPPF and drive
the forest readers).

## Grammar-text reduction

The Earley engine has no grammar-text reduction product. A compiled grammar
artefact derives a pruned model grammar from a flavour's declarative reducer,
parses it through the ordinary model product, and applies a thin fold. The
engine therefore owns recognition and forest reading only.

See the package `README.md` for the recognition and forest mechanics.
