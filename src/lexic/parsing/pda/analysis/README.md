# `parsing/pda/analysis` — decide every point, then store the gate specs

`GrammarAnalysis` runs over a **lifted codegen grammar** and answers one
question for every decision point (arm selection; loop take/skip): can the
predictive runtime make this choice deterministically, and if so, with which
gate? A decision nothing can license becomes an **island** (the Earley engine
handles it); everything else compiles to a gate whose spec is **stored** on
the analysis' `taxonomy`. The compiler reads those specs back verbatim and
never recomputes — a stored gate must be honored in every clone of the rule,
so the single source of truth lives here.

This folder imports only `../core`. `noise.py`, `structured.py`, `kwindow.py`
and `taxonomy.py` are leaves *within* the folder too: each takes the analysis
as an `Any`-typed oracle argument (the rule table, `atom_first`,
`item_nullable`, `first`, `cont_at`, precomputed FOLLOW), so `analysis.py`
imports them, never the reverse.

## `analysis.py` — the fixpoints and the cascade

`GrammarAnalysis` computes the classical predictive fixpoints over `CharSet`:

- **nullability** — which rules/sequences can derive ε;
- **FIRST** and **hard-FIRST** — the chars a construct *can* vs *must* begin
  with (hard-FIRST excludes chars reachable only through a nullable prefix);
- **FOLLOW** and **hard-FOLLOW** — soft and hard continuation sets (hard
  FOLLOW skips nullable followers). Bounded-lookahead substrates use **soft
  FOLLOW only** — hard FOLLOW falsely separates and is unsound there;
- **bounded-lookahead prefixes** — the ≤k windows `kwindow.py` computes.

Each decision is classified — `island` / `stopset` / bounded-lookahead
`pairs` — into `conflicts` (island-worthy) / `demoted` (a gate licensed it) /
`fail_islands`, via an **open `IrTypeMap` atom dispatch** that raises
`UnsupportedConstructError` on an unknown atom rather than guessing. The
island set is closed **before** the clone compiler runs, so totality is an
analysis property, not a compiler fallback.

## The gate cascade, tried in order

1. **1- and 2-char lookahead** — disjoint FIRST sets, or a 2-char prefix
   separation (`atom_two_prefix` / `two_prefix_seq` in `kwindow.py`, the
   `PairGate` source).
2. **k-window** (`kwindow.py`) — `KWindowFirst` computes `FIRST_k` as sets of
   `≤k`-length `CharSet` tuples tagged END / MORE / UNK; `arm_gate` /
   `loop_gate` ask whether the decision separates positionwise at `k ≤ 3`
   (all-or-nothing per decision). This closes the nullable hole structurally:
   a nullable arm keeps its tuples short (ε contributes the empty tuple
   `()`), and short tuples collide with everything by construction — there is
   no nullable oracle to store and forget to consult.
3. **noise-skip peek** (`noise.py`) — skip the maximal run of a
   grammar-derived skippable alphabet `W` (`noise_alphabet`: the union of
   FIRST over *nullable non-semantic* rules — json/ABNF/GBNF whitespace and
   comment leads, never hardcoded) non-consuming, then decide on the first
   post-noise char (`ResidualFirst` — the first non-`W` chars a sequence
   reaches; a terminal mixing `W` and non-`W` poisons the branch).
4. **structured scan** (`structured.py`) — folding-aware gates over the
   `core/scanner` recognizer, for loops and for empty-arm alternations:
   `SG_MATCH` (exact-match over a non-semantic ref), `SG_SCAN` (skip the
   body's leading noise, take on a disjoint post-noise content lead), or
   `SG_PROBE` (the escalation when those leads overlap on the next
   construct's header `ref(R) noise* lit(L)` — the "rulename … defined-as"
   shape).
5. **noise-greedy licence** (`noise.py`) — a greedy over-eat is safe when it
   is provably noise↔noise re-splitting only. The raw soft-FOLLOW set cannot
   answer that (it forgets where its chars came from), so `noise.py` runs the
   FOLLOW fixpoint with **decomposed semantic attribution**: `_sem_first_table`
   counts a terminal only inside a `semantic=True` rule and excludes any
   ref to a non-semantic rule (its subtree is dropped from `semantic_dump`
   wholesale), and `sem_follow_table` re-runs FOLLOW over those semantic
   firsts, seeded empty. Over-eaten chars that can only be semantic deny the
   licence.

## `taxonomy.py` — the stored result

`Taxonomy` holds the classified notes (`conflicts` / `demoted` / `fail`) plus
the gate-spec store: one slot per gate family (`arm`, `loop`, `pn_arm`,
`pn_loop`, `struct_loop`, `struct_arm`), keyed by rule name (rule bodies) or
node identity (loop items). Each `store_*` carries a conflicting-re-store
tripwire — filing two different specs under one key is a
`UnsupportedConstructError`, the anti-guess guard. A `Taxonomy` is a pure-data
leaf (imports only `../core`); `GrammarAnalysis` owns the instance.

See the package `README.md` (§10) for the decide-then-store discipline and the
taxonomy↔compiler contract.
