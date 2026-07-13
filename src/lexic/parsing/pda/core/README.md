# `parsing/pda/core` — the shared PDA substrate

The three leaves the rest of the PDA rests on. Each imports at most
`lexic.ir`; nothing here imports another `pda/` module. This is the bottom
of the `core ← analysis ← compiler ← runtime` chain, so a change here ripples
everywhere and is held deliberately small.

## `charsets.py` — exact co-finite character algebra

FIRST/FOLLOW analysis needs exact set algebra over single characters,
**including sets defined by exclusion**: the FIRST of an `IrNot([^"])` loop
is "every character except `"`" — a co-finite set a bare `frozenset` cannot
represent without enumerating ~1.1M code points (or approximating it away and
poisoning the rule into a false island).

`CharSet` stores `(chars, negated)`:

- `negated == False` → the set **is** `chars`.
- `negated == True` → the set is **every character except** `chars`.

Every operation — `has`, `union`, `subtract`, `overlaps` — is exact across
all four polarity combinations (pos/pos, pos/neg, neg/pos, neg/neg), so an
`IrNot` loop or a wide charclass range stays exactly analysable. Two
conventions the layers above rely on:

- The empty string `""` is the **EOF sentinel** and a legal member; a "real
  characters only" licence must `subtract` it away explicitly (it is not
  removed for free).
- `CharSet.EMPTY` is the identity for `union`; `is_empty()` distinguishes a
  genuinely empty positive set from a co-finite one.

## `scanner.py` — the structured-noise recognizer

A flat character alphabet can skip a run of whitespace, but it cannot skip
**comment-bearing** noise: GBNF `#…\n` and ABNF `;…\n` have co-finite comment
interiors, and ABNF LWS folding (`c-nl` continues a run only when a `wsp`
follows) is a two-character decision. For the self-grammars the flat noise
alphabet is even *empty* (their noise rules are non-nullable), so those spines
would stay islands without this module.

`build_recognizer(rules, roots)` compiles the flavour's own noise rules —
read from the lifted `IrAst` it is handed, so the engine never imports
`lexic.grammars` — into a small **backtracking recognizer**: one flat rule per
acyclic closure member, arms tried in order with a **full position reset on
arm failure**. That reset is what makes folding fall out for free:
`c-wsp = wsp / (c-nl wsp)` matched arm-in-order rejects a bare `c-nl` not
followed by `wsp`, so `(c-wsp)*` stops exactly at the terminator — the exact
fold semantics, derived from the grammar, never hardcoded. `build_recognizer`
returns `None` on a cycle, an inline group, or an undefined ref, and the
decision stays an island.

On top of the recognizer sit the gate value types the analysis stores and the
runtime consults (both non-consuming — they decide, they never eat input):

- `ScanGate(kind, …)` with `kind ∈ {SG_MATCH, SG_SCAN, SG_PROBE}` — the loop
  and empty-arm gate: exact-match, skip-noise-then-peek, or a next-construct
  header probe.
- `ArmGate(gate, escape)` — the arm-selection twin: a `ScanGate` plus the
  index of the nullable escape arm to take when the gate refuses.
- `scan_run` / `scan_match` / `scan_gate_take` — the runtime half: run the
  recognizer at a position without consuming, and answer take/refuse.

## `errors.py` — `PdaFail`

The predictive-parse failure signal, homed in its own leaf so the runtime and
the island escape can raise it without an import cycle. It is internal to
`lexic.parsing` and never reaches a caller — the product entries catch it and
complete on the Earley engine. The runtime module re-exports it for
convenience.

See the package `README.md` (§9–§10) for how these feed the analysis and the
gate cascade.
