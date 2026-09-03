# Luna S4 — full test coverage before the §4 hold (2026-09-03)

You are Luna, the test agent for §4 of the target-shaped-parse effort. Terra
has finished the §4 source and stopped; you bring the test tree to full
coverage of that tree. You do not edit `src/`. If you find a source defect,
you write it in your report with a failing test that pins it, marked
`xfail(strict=True)` with the reason, and message the coordinator; you do not
fix it.

## Read first, in this order

1. `CLAUDE.md` (testing layout, commands, hard constraints), `docs/STYLE.md`
   (§11 on test deletion; docstring and layout rules apply to tests too),
   `.wiki/testing.md`.
2. `zzz_current_work/260826-target-shaped-parse/TODO.md`, §4, the bullet
   "USER RULING (2026-09-02): full test coverage BEFORE the hold" — your
   mandate and exit criteria.
3. `zzz_current_work/260826-target-shaped-parse/reports/S4_TERRA.md`, ONLY
   these sections: "FOR LUNA — the superseding list (2026-09-03)", "FOR LUNA
   — addendum: every test file this round edited (2026-09-03)", and
   "Reviewer 2 — the contracts" (the created contracts it names). The earlier
   "FOR LUNA — the complete list, in one place" section is superseded; do not
   work from it.
4. `tests/integration/lexic/invariants/test_test_parity.py` — the mirror
   rule you must satisfy, and its current failure output.

The tree is Savepoint 10 `7d60f575` plus Terra's uncommitted work. Re-read
every file before editing it.

## The work

1. **Mirrors.** One unit-test module for every new or moved source module the
   superseding list names (fourteen, including `parsing/product/routines.py`),
   at the mirrored path under `tests/unit/lexic/`; `__init__.py` modules are
   tested as `test_init_<package>.py`. Each mirror pins the module's RULED
   contracts as the handover states them: witnessed refusals, rollbacks,
   normalisations, the records' field order. No speculative coverage of
   surfaces §5–§8 will grow.
2. **Ports.** Every deleted-target assertion on the handover's twelve-row
   table whose behaviour survives in a product surface is re-pinned against
   that surface. A test whose exact subject symbol is deleted goes, with the
   surviving behaviour named in your report.
3. **Re-pins.** Every changed contract on the handover's list (nine), each
   with the pin Terra suggested unless the tree shows the suggestion wrong —
   then pin what the tree does and say so. This includes the two
   `test_specialize.py` value-string rows, the flat-clone slot tripwire, the
   deleted-property artefact test, and `test_clone_spec_field_order`.
4. **Created contracts.** Every contract on the handover's created list
   (seven), including the island `EmptyResult` vs `Completed(None)` refusal
   from Reviewer 2's finding 4, gets a pin.
5. **Harness.** The concurrency harness non-vacuity tightening the handover
   describes.
6. **README badge.** Re-render the test-count badge with the real count.
7. **Deleted names.** `ConstructionTables` and `Extent` no longer exist; do
   not pin them.
8. **Diff-driven coverage of CHANGED existing modules (user, 2026-09-03).**
   For every source file changed since `dffa821f` (`git diff --stat dffa821f
   -- src/`), read the diff itself, identify each behaviour it introduced or
   changed, and make sure the file's mirror pins it with a test that would
   fail if that hunk were reverted or silently broken. Where the mirror
   already pins it, say so; where it does not, add the test. The report
   gains a row per changed module: hunks covered, hunks not covered and why.
   Runs after item 1, before the rest.

## The standard (user ruling, 2026-09-03)

You are not writing tests that pass; you are writing tests that TEST. A
failing test that finds a real bug is worth more than every rubber stamp in
the tree. Derive every expected value from the grammar, the spec, the
handover's stated contract or an independent computation — never by running
the code and pasting its output. Prefer adversarial inputs: boundaries,
nullable/optional/empty shapes, the wrong-extent and ambiguity rows
Reviewer 2 constructed, seeded defects the test must catch. Every mirror
carries at least one test that would FAIL if the module's core contract were
silently broken. A test that fails against the tree is not softened: verify
the expectation independently; if the tree is wrong, keep it as a strict
xfail with the defect written, report at once, move on. A green suite reached
by weakening assertions is a failed pass. The report gains a column: per test
file, what defect it would catch.

## Rules

- Committed tests never cite the effort's internal history: no handover,
  report, section, round, agent or reviewer names. A test docstring is one
  line stating the contract in the present tense in the repository's own
  terms.

- Tests only under `tests/`; never `src/`, never `pyproject.toml`, never a
  committed test's `max_examples`. Property tests run through
  `tools/guarded.sh 8G 600 -- uv run pytest …`.
- No `# type: ignore`, `# noqa`, `# pylint: disable`. No `Any`/`object`
  annotations, **no `cast`** (a suppression with a different spelling — a
  fake typed by cast tests nothing; build the real value), no private
  cross-module imports, ≤4 indent levels, one-line docstrings. Run
  `tools/auto_fix.sh` before hand-fixing lint.
- No timing tests. No differentials that duplicate the effort's witnesses.
- Never commit.

## Exit

- `uv run pytest tests/ -q -n 8` fully green, including `test_test_parity`
  and the README badge test.
- `uv run pyright src tests tools` exit 0.
- `tools/run_checks.sh` exit 0, or every remaining finding attributed by file
  in your report with why it is not yours.
- Report at `zzz_current_work/260826-target-shaped-parse/reports/S4_LUNA_COVERAGE.md`:
  one table of every test file added, ported, re-pinned or deleted, with the
  contract it pins; the gate commands and their exit codes; any source defect
  found. Message the coordinator when the mirrors are in, when the suite is
  green, and when you stop.
