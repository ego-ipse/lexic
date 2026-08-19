# `parsing/pda/runtime` — the fused predictive kernel

The runtime executes the compiled tables and builds the product **during** the
walk. Where the Earley kernel builds an SPPF that a fold later consumes,
`PdaKernel` walks the flat int-coded program and builds the model directly —
the fold is fused into the parse, so no intermediate `ParseTree` is ever
allocated on the deterministic path. This folder imports `../compiler` +
`../core`; it is the top of the chain.

## `kernel/` — the driver and its shed halves

The kernel package: `kernel.py` (`PdaKernel` — the flat-program walk, the
explicit frame stack, arm selection, the island splice), `decisions.py`
(the attempt/probe method group the kernel inherits — ordered attempt
entries, watermarked sub-runs, value-compared boundary probes) and
`reduce_runtime.py` (the grammar-text twin sharing the whole recognition
machinery; `pda_model` / `pda_reduce` are the public entries). Its own
`README.md` carries the detail.

## `admission.py` — the attempt-seam leaves

Arm admission tests (`admits`, `sole_admitted` — the first-char filter, the
entry's compiled leading-prefix pattern and its FIRST_k window, in that
order), the per-parse scratch (`KernelCaches`), and the
aliasing-true structural stack copy (`frames_copy`) the probes drive on.
Flat leaves: no kernel import, shared by name with the decision group.

## `build.py` — the frame layout and the fused build tail

The slot layout of the descent frame (the `F_*` indices) plus the free
functions that fold a completed frame into a model: a `sequence` clone's
per-field slot reads (fast or validated), an `alternation`'s pass-through, and
the empty-arm build. These read only the input `text` and a frame / clone —
never the kernel cursor — so they are shared **by public name** with the
reduce twin rather than crossing a boundary as private imports. Imports only
`../compiler/flatten` (the flat records + field-mode codes), `fold` (`RuleFold`)
and `../core/errors` (`PdaFail`); never the kernel.

## `matchers.py` — terminal matching

The cursor-free recognition leaf: a terminal item's whole quantifier loop
matched inline (literal runs, char-class runs, the `value_str` fast path)
plus the FIRST-gated `select_arm` / `select_gated` selection helpers the
kernel's `_enter` chain calls.

## `islands.py` — the windowed Earley escape

A decision the gate cascade could not license is an island: its reference pays
a full **windowed Earley sub-parse** (`longest_start_completion`) whose result
is folded and spliced into the current capture. That already-cold path is shed
here as free functions taking only plain values and Earley types — never the
`PdaKernel` cursor — so it is a leaf: the kernel imports it. (The hot
fold-build functions stay methods on `PdaKernel`; moving *them* off the class
would cost measurable throughput, which is why only the cold island path lives
here.)

See the package `README.md` (§12–§13) for the fused build, the reduce twin,
and island splicing in full.
