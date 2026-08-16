# T9 — the completions lever: value_str interiors need no derivation

Design, 2026-08-16, from T8's lessons. Author: the reviewer (Fable),
building directly per the user's instruction. Status: design + ceiling;
implementation next.

## The lesson-derived reframe

T8 attacked PER-COMPLETE work and lost: the C-level ops are already
minimal, and the vstr tier was already key-first. But the dominant term
was never the work per complete — it is the NUMBER of completes
(measured 4.4× spread by formulation), and one class of completes is
provably wasted: **a value_str-bound subtree's interior derivation is
discarded by construction** — the model keeps only the raw text slice.
Every char/unescaped/digit complete inside a json string builds
machinery for a structure nobody stores. On T8's counts, 60% of json's
builds are vstr-tier (1,759 of 2,911), and each drags its own frame
pushes and interior record completes besides.

## The mechanism (all substrate exists)

At ANALYSIS time: license rules that are (a) value_str-bound in the
binding view and (b) purely lexical in their interior — no semantic
children, no token terminals — as SCAN-COLLAPSIBLE. This is lexruns'
derivation (parsing/lexruns.py: "where a grammar's lexical layer is
DERIVED") meeting the binding view; the P3/P5 ScanGate substrate
(pda/core/scanner.py) is the folding-aware recognizer shape to compile
them onto. At COMPILE time: lower a collapsible rule's interior to a
scan program (CharSet runs) instead of clone frames. At RUN time: one
scan per occurrence, one vstr build from the slice (the memo stays
key-first on (ctor, span)) — interior completes, frames and ENDS simply
never exist.

**Returns unchanged**: the parent stores the same value_str model built
from the same slice; round-trip is byte-identity on the slice itself.
Ambiguity honesty: a collapsible rule's interior is unambiguous BY
construction only if its lexical language is deterministic per position
— the analysis must prove the run's end is decision-free (FIRST_k /
kwindow substrate) or refuse the licence; a refused licence means the
rule parses as today. No behavior cliff: licences are per-rule,
computed, and drawn (the machine room's verdicts).

## Ceiling, honestly stated

Upper bound if all vstr interiors collapse on json: ~60% of builds plus
their interior frames — the 30-50% shape IS available here, and T8's
harness discipline (interleaved in-process A/B, 21 rounds, product
equality before timing) is the only acceptable verdict. Failure mode to
watch: grammars whose vstr runs average ~1 char (nothing to collapse) —
csv-like rows must be in the A/B set, and a ~0% result there is
expected and fine, not a refutation.

## Probe note

Module-level monkeypatching of build_vstr/build_fast counts ZERO — the
kernel binds builders at compile time, not through the module. Counting
probes must instrument the fold's own records or use compile-time
wrapping before artifact construction.

## Order of work

1. Analysis licence (binding view × lexrun derivation × decision-free
   proof), with per-rule verdicts and repository tests on json (string/
   number license; member does not), markdown (plain licenses), csv.
2. Compile lowering to the scan program; the flat program grows one op.
3. Kernel scan path; ENDS/frames untouched elsewhere (T6's structural
   gates must stay green — the trace sees one scan event, honest).
4. A/B under guarded.sh, T8's protocol exactly; suite byte-identity.
