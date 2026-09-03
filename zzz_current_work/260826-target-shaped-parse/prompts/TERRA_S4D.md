# Terra S4D — the §4 lint debt, cleared at the root (2026-09-03)

You are a fresh Opus implementer closing the last source work of §4 before
its commit: every pylint finding this effort introduced, fixed at the root,
with the paid path bytecode-identical. Nothing else in src changes.

## Read first, in this order

1. `CLAUDE.md`, `docs/STYLE.md` (§7 measurement, flat code, ≤4 indent
   levels, one-line docstrings).
2. `zzz_current_work/260826-target-shaped-parse/LEDGER.md` — the top block
   "NEXT SESSION — start here" and the entries dated 2026-09-03; every
   ruling there binds you.
3. `zzz_current_work/260826-target-shaped-parse/reports/S4_VEGA_CI.md` §4
   — the complete inventory of the 48 findings, grouped by code and file,
   with the R0801 duplicate quoted and its owner argued.
4. `zzz_current_work/260826-target-shaped-parse/reports/S4_TERRA.md`,
   sections "Zero tax, closed" and "The consumerless-surface pass" only.

Tree: Savepoint 11 `c9c72fc6` plus uncommitted test and tools work by
other agents — do not touch tests/ or tools/ except where a finding names a
test line (E1136) and the fix is in the source type it reads. Re-read every
file before editing it.

## The findings, and the honest fix for each

- **28 × W0621, a local `Carry` shadows the module-level `Carry`** in
  `pda/compiler/program/flatten.py`, `pda/runtime/build.py`,
  `product/abi/construction.py`, `product/tree.py`. Establish what the
  module-level `Carry` is (a leftover TypeVar? an alias?) and what the PEP
  695 per-function `[Carry]` parameters are for. One of the two goes: if
  the module-level name is a stale TypeVar, delete it and keep the PEP 695
  parameters; if the module-level name is the real generic and the
  functions merely re-declare it, drop the per-function parameters. No
  renaming to `Carry_`/`CarryT`.
- **6 × R0913 + 6 × R0917 on the same six sites** (too many arguments /
  positional arguments). The fix is a record for the arguments that travel
  together, or a split, never a config bump. BUT: if a site is on the paid
  path (kernel, execution, build, matchers, flatten readers, admission,
  decisions, islands — the functions `proto/s4_paid_path_opcodes.py`
  compares), a signature change alters bytecode and is forbidden without
  measurement. For those sites, report the exact function, its role, and
  why the arguments cannot be packed without a runtime cost, and STOP on
  that site for a ruling; fix the cold sites.
- **3 × R0903** (too few public methods): a class with one method is
  either a record (make it the record it is — `NamedTuple` on the spine
  conventions, or a dataclass where mutability is the point) or a function.
- **2 × R0914** (too many locals): split at a real seam into flat helpers
  with honest names, not a mechanical chop; same paid-path rule as above.
- **1 × W2301** (unnecessary ellipsis): remove it.
- **1 × E1136** `tests/unit/lexic/parsing/pda/runtime/kernel/test_decisions.py:106`,
  `frame[F_ENDS]` unsubscriptable: pylint infers the frame's type from the
  source. Find what the source declares for the frame the test builds; if
  the declared type is dishonest (e.g. `object`), fix the declaration in
  src; if the test builds the frame wrongly, say so and stop — tests are
  not yours.
- **R0801 between `earley/engine.py:229-242` and `products.py:166-179`**:
  extract the shared tail into ONE function in
  `parsing/earley/kernel/forest/support/ambiguity.py` beside
  `MeaningBuilder` and `different_meaning`, taking the pair, the builder
  and the resolver and returning the value; both call sites collapse to a
  single return. Layering: engine.py may not import products.py and vice
  versa; ambiguity.py sits beneath both and both already import it.
- **`products.py:183-184`**: the duplicated comment banner, one line
  deleted.

## Gates, by exit code, all required

- `tools/run_checks.sh` — **exit 0**. This is the whole point.
- `uv run pytest tests/ -q -n 8` — green (5516 passed at your start).
- `uv run pyright src tests tools` — 0.
- `uv run python tools/check_generated.py` — 0.
- `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_paid_path_opcodes.py`
  — every paid-path function bytecode-identical to `c9c72fc6` (extract it
  with `git archive` into /tmp if the witness needs a base tree). A row
  that changed is a defect unless it is a site you stopped on for ruling.
- Every `s3_*`/`s4_*` witness in `proto/` — exit 0 (skip the two timed
  harnesses; no timing at all this round).
- `git diff --check` — 0.

## Rules

No `# pylint: disable`, `# noqa`, `# type: ignore`; no `Any`/`object`/
`cast`; no private cross-module imports; no default-argument state; never
commit; never touch `pyproject.toml`; never revert a formatting hunk. Report
by appending a dated section to `reports/S4_TERRA.md` with a table: finding
→ file:line → fix → gate evidence, and a list of any site stopped for
ruling. Message the coordinator (SendMessage to team-lead) when
`run_checks.sh` exits 0 or when you stop on a ruling.
