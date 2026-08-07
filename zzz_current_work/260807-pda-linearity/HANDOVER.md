# pda-linearity — HANDOVER

**What this effort is:** the PDA's fast road — what knocks a parse off it, and
what that costs. Split out of `260807-opsis-radical/gate/` on 2026-08-07, once
it was clear the engine work had outgrown the ergonomics effort that surfaced it
(the split was the opsis-radical plan's own recommendation, and the reviewer's).

## Cold start — read in this order

1. **`PLAN.md`** — the order of work, with the ordering argument and the two
   calls reserved for the user. Start here.
2. `FINDING.md` — the relaxation bug and the fix that landed (§11), plus the
   review that shaped it (§10) and the D-premise measurement (§12).
3. `PROBE-QUADRATIC.md` — the biggest open item: the PDA is n² on pipe-heavy
   vyx packets, 73 s for 11 KB, 92% inside `_probe`.
4. `D-ISLANDING.md` — the islanding design, its soundness argument, its
   measured hit rate, and its review.
5. `TALLY.md` — the ledger. Newest last.

## State

**Landed and green** (the only `src/` change this effort has made):
`relax_non_semantic` narrowed to nullable noise rules. All ten ground-truth
grammars read by the metagrammar ride the PDA with no resolver; vyx
4.451 s → 0.029 s. `tools/run_checks.sh` exit 0, suite 3776 passed / 8 skipped,
parity + property 141 passed, `check_generated.py` CLEAN, `run_examples.sh`
exit 0. **Not committed.**

**Open:** everything in `PLAN.md`. The headline is the quadratic, not solution D.

## Run

```bash
# every probe × every variant, then the suite under the pre-fix relaxation
zzz_current_work/260807-pda-linearity/run_all.sh

# one probe; modes: today | off | unconditional  (unconditional = the pre-fix bug)
uv run python zzz_current_work/260807-pda-linearity/probes/<probe>.py [mode]

# suite-wide instruments (pytest plugins)
PYTHONPATH=zzz_current_work/260807-pda-linearity \
  uv run pytest tests/ -q -p forkcount        # forks/fails by raise site
PYTHONPATH=zzz_current_work/260807-pda-linearity \
  uv run pytest tests/ -q -p verdictcensus    # boundary class → verdict matrix
PYTHONPATH=zzz_current_work/260807-pda-linearity \
  uv run pytest tests/ -q -p relaxold         # the suite under the pre-fix pass
```

`PLAN.md`'s last section is the full instrument table — what each probe answers.

## Conventions carried over

- **The tally lives where the work lives.** Engine-line entries go in this
  folder's `TALLY.md`; `260807-opsis-radical/atlas/TALLY.md` holds the history
  from before the split and ends with a pointer here.
- Any engine change gates on `tools/run_checks.sh` exit 0 **plus** the parity
  differentials (`tests/integration/lexic/parity/`) — that suite is the real
  gate for anything that changes what the PDA commits to.
- Never commit; leave changes staged for the user.
- Isolation here is an effort directory or a branch — **never a worktree**.
- `run_checks.sh` does NOT run the tests. Run the suite separately.

## Traps (each cost time)

- A counting **subclass** of `PdaFail` breaks `except PdaFail` for `ProbeFork`
  (siblings) — 51 tests failed until the instrument patched `__init__` on the
  existing classes instead. Same lesson for any exception-hooking probe.
- Deduping exceptions by `id(...)` false-dedups: ids are reused after GC. Mark
  the object.
- `_fork_verdict` lives on `Attempting` (`kernel/decisions.py`), not on
  `PdaKernel` — patch the class that defines it.
- To A/B against pre-fix behaviour under a tool that imports lexic early (the
  benchmark), put `variants.apply("unconditional")` in a `sitecustomize.py` on
  `PYTHONPATH`.
- `tools/auto_fix.sh` formats the whole repo including `zzz_current_work/` —
  expect unrelated churn in other efforts' folders (the user's ruling: accept
  the formatting).
