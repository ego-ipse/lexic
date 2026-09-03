# Terra S4E — Review 17's source corrections and the two rulings (2026-09-03)

You continue as the §4 implementer on Savepoint 12 `0614c940`. Your earlier
first batch is in that commit; your second batch was reverted and is not on
disk. Re-read every file before editing.

## Read first, in this order

1. `CLAUDE.md`, `docs/STYLE.md`.
2. `reports/REVIEW_17.md` — the active NO-GO checkpoint. It governs.
3. `LEDGER.md`, the top block "Review 17 rulings (user, 2026-09-03 evening)".
4. `humanotes.md`.

## The work, in the review's order, each closed at the root with evidence

1. **Immutability after verification** (`executable.py`). The public
   executable and everything reachable from it — `codes`, `routines`,
   `RecordConstructor.defaults`, `Construction.defaults`, `LoweredRoute`'s
   writable slots, `TableRoute.lookup`, the replica's shared `codes` — are
   frozen at the cold binding boundary. The hot reader may keep a
   worker-local plain dict as its private physical projection with zero
   added lookup cost. Test: every public mutation path after binding
   raises; the test that pinned the alias pins immutability instead.
2. **The verifier rejects malformed current completions** (`verify.py`),
   cold: a PASS source exists and names a single-value capture; a RECORD's
   capture count equals its names; optional indices in range; constructor
   names, defaults, matched-text ownership and licensed field order
   consistent; an operation the executor cannot run is refused at binding
   with words, never carried as `source == -1, construction is None`. The
   invalid PASS in `tests/unit/lexic/parsing/test_executable.py:30-35`
   becomes a refusal row (you may edit that test; list it).
3. **Ambiguity settlement**: keep `chosen_meaning` and the sibling
   extraction; delete `MeaningPolicy` and `ModelExecutable.meaning_policy()`
   (per-parse allocation) and `Flip`/`_flips()` (eager list); pass the
   builder and resolver; restore early, allocation-free alternate
   iteration. The R0913 sites this reopens are solved without any per-parse
   or per-alternate allocation.
4. **Close the four `object` boundaries** this effort added:
   `LoweringOwned.registry`, `_field_order`'s licence shape,
   `_model_defaults`, `verify_exact_ints` — named protocols, carrier
   parameters or concrete table shapes. The frame sink is no longer a
   residue after item 6.
5. **Structural typing**: `construction.py`'s `getattr(cls,
   "fast_construct", None)` becomes two constructor shapes (licensed and
   unlicensed) the type checker can tell apart; no reflection. Delete
   `tests/unit/lexic/parsing/product_test_helpers.py::replaced` and its
   tests and return every site to `_replace` (pylint 4.0.8 resolves it).
   **Ruling 1**: extend `tools/pylint_lexic.py` with an astroid transform
   that removes PEP 695 `type`-statement parameters from module scope, so
   the 28 W0621 vanish with no code change; pin it with a probe test under
   `tests/unit/tools/` (a module with `type A[C] = list[C]` and
   `def f[C](x: C) -> C` yields no W0621; a genuine module-level `C`
   shadowed by a function still does).
6. **Ruling 2, A3**: the slotted, typed `Frame[M]` lands now. The six
   modules that index frames by `F_*` (kernel, execution, build, admission,
   decisions, trace) read and write slot attributes; the admission stack
   copy is a slot copy; `build_sequence` and `build_validated` take the
   frame and fall to four arguments with zero allocation; the `_NO_SINK`
   `list[Any]` disappears with the type; CLAUDE.md's "plain lists and
   mutable cursors are deliberate" sentence is amended mechanically to say
   frames are typed slotted records, lanes stay plain; the §8 frame bullet
   in `TODO.md` is marked pulled forward (one line). `_captured` takes a
   per-rule `CaptureSpec(slot, mode, optional, name)` tuple built cold in
   `routines.py` and verified (this is item 2's RECORD relation), removing
   the per-slot zip/enumerate/`in` from the Earley loop. Bytecode witness:
   list every changed paid-path row; each is one of these two changes.
7. Remaining cold lint: R0903 at `executable.py`, R0914 at
   `parallel/stitch/model.py` (694 lines: propose the ownership move that
   makes room and do it; never shave prose), anything else pylint reports
   in `src/`. Target: `uv run pylint src ext` at 10.00/10, exit 0.

## Gates, by exit code

pyright 0; `uv run pytest tests/ -q -n 8` green; `check_generated.py` 0;
every `s3_*`/`s4_*` witness 0 (no timed harness, no timing at all — the
measurement is item 7 of the review and belongs to the corrected gate);
`tools/run_checks.sh` exit 0; `git diff --check` 0. Report: a dated section
in `reports/S4_TERRA.md` with one row per item and the evidence. Message the
coordinator (SendMessage to team-lead) at each item closed and when you
stop. Never commit; never touch `pyproject.toml`; no suppressions, no
`Any`/`object`/`cast`; ≤4 indent levels; one-line docstrings.
