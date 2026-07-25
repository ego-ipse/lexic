# `parsing/pda/runtime` — the fused predictive kernel

The runtime executes the compiled tables and builds the product **during** the
walk. Where the Earley kernel builds an SPPF that a fold later consumes,
`PdaKernel` walks the flat int-coded program and builds the model directly —
the fold is fused into the parse, so no intermediate `ParseTree` is ever
allocated on the deterministic path. This folder imports `../compiler` +
`../core`; it is the top of the chain.

## `runtime.py` — `PdaKernel`

**Flat program.** The kernel walks the int-coded `PdaProgram` — `OP_*`
op-codes, pre-resolved `(chars, negated)` membership sets, direct `FlatClone`
references — not the compiler's NamedTuple specs. Dispatch is integer-indexed:
no attribute descriptors, no per-character method calls on the hot loop.

**Explicit frame stack.** Rule, group and loop descent runs on an explicit
stack of flat list frames — never Python recursion, so input depth never
touches the interpreter's recursion limit. Per-parse state (the input, the
cursor position, the frame stack) lives on the kernel; the `PdaProgram` is
shared and immutable across every parse. A frame owns its item cursor, its
captured spans, and its accumulating sub-models; captures bubble to the
nearest bound item, and transparent frames (groups, `fold=None` clones) funnel
their children through.

**Arm selection.** `_enter` chooses a clone's arm in a fixed order:
frame-less dispatch chase → k-window / noise-skip `select_gated` → the
structured `scan_gate_take` (refuse ⇒ the nullable escape arm) → leaf →
FIRST-gated select. When no arm matches, the kernel raises `PdaFail` and the
product entry completes on Earley.

## `build.py` — the frame layout and the fused build tail

The slot layout of the descent frame (the `F_*` indices) plus the free
functions that fold a completed frame into a model: a `sequence` clone's
per-field slot reads (fast or validated), an `alternation`'s pass-through, and
the empty-arm build. These read only the input `text` and a frame / clone —
never the kernel cursor — so they are shared **by public name** with the
reduce twin rather than crossing a boundary as private imports. Imports only
`../compiler/flatten` (the flat records + field-mode codes), `fold` (`RuleFold`)
and `../core/errors` (`PdaFail`); never `runtime`.

## `reduce_runtime.py` — the grammar-text twin

The model kernel stays byte-for-byte unchanged in `runtime.py`; this module
homes the grammar-text completion, `_ReducePdaKernel`, which **shares the
whole recognition machinery** (`run` / `_drive` / `_enter` / `prefix_run` /
the terminal matchers) and overrides only the two completion callbacks
(`_complete`, `_island`) plus the delegate sub-run — so the reduce path builds
an `IrAst` where the model path builds a model, on identical recognition.
`pda_model` and `pda_reduce` are the public runtime entries, one per product
here, so both kernels live behind one seam. A leaf w.r.t. the model kernel: it
imports `PdaKernel` from `runtime` and the frame vocabulary from `build`, never
the reverse.

## `islands.py` — the windowed Earley escape

A decision the gate cascade could not license is an island: its reference pays
a full **windowed Earley sub-parse** (`longest_start_completion`) whose result
is folded and spliced into the current capture. That already-cold path is shed
here as free functions taking only plain values and Earley types — never the
`PdaKernel` cursor — so it is a leaf: `runtime` imports it. (The hot fold-build
functions stay methods on `PdaKernel`; moving *them* off the class would cost
measurable throughput, which is why only the cold island path lives here.)

See the package `README.md` (§12–§13) for the fused build, the reduce twin,
and island splicing in full.
