# `parsing/pda/runtime/kernel` — the fused driver and its shed halves

The kernel is one class split across files by responsibility: `kernel.py`
holds the paid loop, `decisions.py` the attempt/probe method group it
inherits, and `reduce_runtime.py` the grammar-text twin. The split is
file-size discipline, not architecture — everything here is a single
cursor object walking one flat program.

## `kernel.py` — `PdaKernel`

**Flat program.** The kernel walks the int-coded `PdaProgram` — `OP_*`
op-codes, pre-resolved `(chars, negated)` membership sets, direct
`FlatClone` references — not the compiler's NamedTuple specs. Dispatch is
integer-indexed: no attribute descriptors, no per-character method calls
on the hot loop.

**Explicit frame stack.** Rule, group and loop descent runs on an explicit
stack of flat list frames — never Python recursion, so input depth never
touches the interpreter's recursion limit. Per-parse state (the input, the
cursor position, the frame stack) lives on the kernel; the `PdaProgram` is
shared and immutable across every parse. A frame owns its item cursor, its
captured spans, and its accumulating sub-models; captures bubble to the
nearest bound item, and transparent frames (groups, `fold=None` clones)
funnel their children through.

**Arm selection.** `_enter` chooses a clone's arm in a fixed order:
frame-less dispatch chase → k-window / noise-skip `select_gated` → the
structured `scan_gate_take` (refuse ⇒ the nullable escape arm) → leaf →
FIRST-gated select — and an attempt clone's ordered entries when the
analysis classified the site attemptable. When no arm matches, the kernel
raises `PdaFail` and the product entry completes on Earley.

**Islands.** A reference the gate cascade could not license delegates to a
windowed Earley sub-parse (`_island` / `_island_subparse` / `_delegates`);
these stay methods because the reduce twin overrides the splice. The flat
sub-parse machinery itself lives in `../islands.py`.

## `decisions.py` — the attempt/probe method group

The kernel's decision half, hosted as the `Attempting` class the kernel
inherits: ordered attempt entries with the commit audit (`attempt`),
licensed loop iterations run as watermarked sub-runs on top of the live
stack (`attempt_iteration` / `_attempt_run`), and the both-viable boundary
resolution — one probe per side driven to end-of-input on a structural
stack copy, verdicts compared on completed VALUES exactly as the forest
gate asks (`_fork_verdict` / `_probe`). Undecidable is `ProbeFork`, never
"this side failed": bailing reaches gated Earley, which refuses iff the
ambiguity is real.

## `reduce_runtime.py` — the grammar-text twin

The model kernel stays byte-for-byte unchanged in `kernel.py`; this module
homes the grammar-text completion, `_ReducePdaKernel`, which **shares the
whole recognition machinery** (`run` / `_drive` / `_enter` / `prefix_run` /
the terminal matchers) and overrides only the two completion callbacks
(`_complete`, `_island`) plus the delegate sub-run — so the reduce path
builds an `IrAst` where the model path builds a model, on identical
recognition. `pda_model` and `pda_reduce` are the public runtime entries,
one per product, so both kernels live behind one seam. A leaf w.r.t. the
model kernel: it imports `PdaKernel` from `kernel` and the frame vocabulary
from `../build`, never the reverse.
