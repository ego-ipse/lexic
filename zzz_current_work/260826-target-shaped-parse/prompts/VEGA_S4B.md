# Vega S4B — the same-run A/B works across a public rename (2026-09-03)

User ruling: dropping rows from the performance gate is rejected with
prejudice. The A/B must work, all 72 rows, on PR #22 whose base tree names
the compiled grammar's build object `CompiledGrammar.fold` and whose HEAD
names it `.product`. No shim (`getattr` fallback, positional access, branch
on which name exists), no legacy name kept in src, no rows skipped.

## Starting point: a clean `tools/`

The user ran `git restore tools/` (2026-09-03): the public-surface
migration in `bench.py`, `cases/grammars.py` and `diagnostics/split_ab.py`
is GONE, deliberately — "I'd rather not have a half-working solution, so
start from scratch." Re-read every file before editing; nothing you
remember writing is on disk. Under the per-tree design HEAD's harness may
use HEAD's names freely, so do not redo the internal-reach cleanup for its
own sake; change only what the per-tree design needs. Re-apply exactly one
thing from the previous pass because it is a real bug independent of this
effort: `diagnostics/split_ab.py` computes the repository root as
`parents[2]`, one level short since its move into `diagnostics/`, hiding
the vyx case; it is `parents[3]`, matching `cases/grammars.py`.

## Read first

1. `CLAUDE.md`, `docs/STYLE.md` §7.
2. `zzz_current_work/260826-target-shaped-parse/reports/S4_VEGA_CI.md` —
   your predecessor's report; §6 is the migration already landed (36 of 72
   rows cross through the public surface) and the exact residue.
3. `tools/benchmark/compare.py`, `tools/benchmark/execution/isolation.py`,
   `tools/benchmark/bench.py`, `tools/benchmark/cases/grammars.py`,
   `.github/workflows/performance.yml`.
4. The `LEDGER.md` entry "User ruling on the A/B (2026-09-03)".

## The design

The harness's invariant "HEAD's harness held constant, only lexic swapped"
cannot survive a public rename by construction. Restate it as: **row
definitions are held constant by NAME; each arm's worker code runs from its
own tree against its own lexic.** Concretely:

- HEAD's `compare.py` remains the orchestrator and the comparator. It
  launches the base arm's exact-row workers from the base checkout — the
  workflow already has it at `../base` (the "Check out base" step) — with
  base's `tools/benchmark` on the path and base's `src` as its lexic; HEAD's
  workers run from HEAD. Same interpreter, same runner, same rounds,
  alternating, as today.
- Before any timing, the two arms' row-name sets are asserted equal; a
  difference is a refusal with the missing names, never a silent subset.
- The comparison reads rows by name, as it does now.
- `tools/benchmark/README.md` states the invariant and why: a cross-version
  A/B must survive exactly the public renames a PR makes, so the worker
  code must be each tree's own; what is held constant is the row
  definition (grammar, document, engine noun, rounds) by name.

Local reproduction, exactly as the workflow: base sha is the PR base
(`git merge-base main HEAD`, currently `0faa7289`); extract it into this
effort's own scratch — `git archive <sha> | tar -x -C
zzz_current_work/260826-target-shaped-parse/scratch_vega/lexic-base`, which is
gitignored so the arm never enters the checkout, and never a worktree, and
never `/tmp` — and run HEAD's compare with the base source and base record
arguments the
workflow passes, plus whatever argument the new design needs for the base
tools path — add it to `performance.yml` (the one place outside tools/ you
may edit, mechanically, to pass the base checkout's path). Exit 0 with all
72 rows compared is the gate; record the numbers.

## Rules

Write scope: `tools/benchmark/**`, `.github/workflows/performance.yml`,
your report. Never src/, never tests/, never `pyproject.toml`. No
suppressions, no `Any`/`object`/`cast`, no try/except import fallbacks.
Never commit. `ruff`, `pylint` 10.00/10 and `pyright` clean on every file
you touch; `tests/integration/lexic/invariants` green. Report: append to
`reports/S4_VEGA_CI.md` a dated section "§7 — per-tree workers" with the
design as landed, the command, the exit code, the 72-row table, and the
control-floor row. Message the coordinator (SendMessage to team-lead) when
the compare exits 0 on all 72 rows, or when you stop.
