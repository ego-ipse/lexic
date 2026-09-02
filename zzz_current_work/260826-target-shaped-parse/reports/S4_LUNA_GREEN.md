# S4 — Luna green-ground pass

Bounded mechanical-verification pass on branch `targeter`, starting from a
clean HEAD. No design or parse-semantics change. All six prescribed items
(A–F) applied exactly as specified; nothing stopped.

## A — tests/unit/lexic/parsing/pda/runtime/test_build.py

- **A1**: `make_frame`'s `frame = [None] * 9` → `frame: list = [None] * 9`
  (bare `list`, per STYLE §1). `uv run pyright` on the file alone: 0 errors.
- **A2**: `test_build_vstr_interns_by_ctor_and_span`'s stub `SimpleNamespace`
  was missing `plan` entirely (the real `AttributeError`) and passed
  `fast=None` where the real clone contract uses the sentinel. Added
  `no_fast_construction` to the import from
  `lexic.parsing.pda.compiler.program.flatten` and changed the stub to
  `SimpleNamespace(ctor=ctor, matched="value", fast=no_fast_construction, plan=())`.
  With `fast is no_fast_construction` and `plan == ()`, `vstr_model` falls
  through to `clone.ctor(**{clone.matched: span})`, exactly the path the
  test's `ctor(value)` and assertions pin. Assertion lines unchanged.

## B — tests/unit/lexic/parsing/pda/compiler/program/test_specialize.py

`test_inline_group_flattens_transparent_with_no_ctor_and_no_fast_ctor`
asserted `group.ctor is None` / `group.fast is None`. Traced the real
contract: `bake_product_build` (`src/lexic/parsing/pda/compiler/program/product.py:155-158`)
sets `clone.ctor = no_construction` then calls `clear_build`, which sets
`clone.fast = no_fast_construction` — never `None`. Imported both sentinels
from `lexic.parsing.pda.compiler.program.flatten` and re-pinned:
`assert group.ctor is no_construction` / `assert group.fast is no_fast_construction`.
Nothing else in the test changed. Confirmed via targeted run: 1 passed.

## C — tools/benchmark/bench.py, tools/benchmark/diagnostics/split_ab.py

`earley_model`'s third parameter is `binding: ModelBinding[M]`
(`src/lexic/parsing/products.py:85-90`); `CompiledGrammar.product` is that
binding (`src/lexic/compile/artifact.py:166`). In `bench.py`, replaced
`fold = bench.fold` with `binding = bench.compiled.product` and passed
`binding` at the one `earley_model` call site (the `pda_model(..., compiled.fold)`
call two lines below is untouched — `binding.fold` elsewhere in the file is
a separate local, confirmed still resolvable). In `split_ab.py`, replaced
`compiled.fold` with `compiled.product` at both `earley_model` call sites.
`uv run pyright tools`: 0 errors.

## D — Move `_close_loop` → `build.py:close_loop`

Moved the pure frame helper from `decisions.py` (was at line 134, right
before `class Attempting`) to `build.py`, placed immediately after the
`F_*` constant block (before `type InternKey[Carry] = ...`), renamed to the
public `close_loop`, body and docstring verbatim, no annotation changes.
In `decisions.py`: deleted the old definition, added `close_loop` to the
existing `from lexic.parsing.pda.runtime.build import (...)` block, and
renamed all four call sites. `wc -l`: `decisions.py` 700, `build.py` 394 —
both ≤ 700. `rg -n "_close_loop" src`: empty.

**One consequential fix, not separately prescribed but required by the
rename**: `tests/unit/lexic/parsing/pda/runtime/kernel/test_decisions.py`
imported the now-deleted private symbol `_close_loop` directly from
`decisions.py` (a private cross-module import, disallowed under rule 2
regardless). Updated its import to the new public home
(`from lexic.parsing.pda.runtime.build import ..., close_loop`), removed
`_close_loop` from the `decisions` import block, and renamed the one call
site (`_close_loop(frame, 1, 42)` → `close_loop(frame, 1, 42)`). No
assertion changed.

## E — Split `parsing/product/` → `parsing/product/abi/`

`git mv` of `records.py`, `construction.py`, `expressions.py` into new
`src/lexic/parsing/product/abi/`, with `abi/__init__.py` containing exactly
the one prescribed docstring line. Rewrote every
`lexic.parsing.product.(records|construction|expressions)` reference
(imports and Sphinx cross-refs) to `lexic.parsing.product.abi.…` via a
scoped `sed` across the nine hit files: `src/lexic/compile/product/lower.py`,
`src/lexic/parsing/pda/runtime/build.py`,
`src/lexic/parsing/pda/compiler/program/flatten.py`,
`src/lexic/parsing/product/__init__.py`, `tree.py`, `verify.py`, and the
three moved files' own intra-imports. Confirmed zero remaining
`lexic.parsing.product.(records|construction|expressions)` hits and zero
`product.abi.abi` double-prefixes. `product/__init__.py`'s `__all__`
re-export surface is untouched — `from lexic.parsing.product import X`
still resolves everywhere. `parsing/product/` now holds 5 top-level `.py`
files (was 8); `abi/` holds 4. No test mirror existed at
`tests/unit/lexic/parsing/product/` to `git mv`.

Updated `CLAUDE.md`'s package map: removed the three moved lines from
`product/`'s block, added the `abi/` sub-block with the three annotations
copied verbatim, at the file's existing indentation (6-space subpackage,
8-space files, matching the `earley/kernel/tables/` precedent).
`test_doc_drift.py`: passes.

**One regression caught and fixed before it reached the report**: the new
`abi/` folder had no `README.md`, which
`test_every_active_source_folder_has_a_readme` requires of every active
source directory. Added `src/lexic/parsing/product/abi/README.md` (four
sentences, matching the terse sibling style e.g.
`earley/kernel/forest/support/README.md`). Re-ran that test plus
`test_test_parity` plus `test_doc_drift` together: only the pre-existing
`test_test_parity` gap remains (see Verification §2).

## F — src/lexic/parsing/trace.py

`WatchedKernel[M]`'s three override signatures widened to `object`/lost
their `M` binding. Changed exactly as specified:
- `_enter(self, clone: FlatClone, out: list[object]) -> bool` →
  `_enter(self, clone: FlatClone[M], out: list[M]) -> bool`
- `_attempt_run(self, sub: FlatClone, pos: int) -> tuple[int, list[object]] | None`
  → `_attempt_run(self, sub: FlatClone[M], pos: int) -> tuple[int, list[M]] | None`
- `_probe`'s `taken: tuple[int, list[object]] | None` →
  `taken: tuple[int, list[M]] | None`, return type
  `tuple[list[object] | None, bool]` → `tuple[list[M] | None, bool]`

`uv run pyright src/lexic/parsing/trace.py`: 0 errors.

## Items stopped

None. All six items (A–F) completed exactly as prescribed; the one
consequential fix in item D (test_decisions.py's import) was a direct,
mechanical, non-restructuring consequence of the prescribed rename, not an
invented alternative.

## Verification

1. **`uv run pyright src tests tools`** → `0 errors, 0 warnings, 0 informations`.
   (Interim: after A–F alone, one residual error surfaced —
   `tests/unit/lexic/parsing/pda/runtime/kernel/test_decisions.py:23:5 -
   "_close_loop" is unknown import symbol` — from the consequential test
   fix above; resolved before this final run.)

2. **`uv run pytest tests/ -q -n 8`** (nothing else running) → final state:
   **`1 failed, 5339 passed, 8 skipped, 4 warnings`**, exit 1. The one
   failure is the documented, out-of-scope
   `tests/integration/lexic/invariants/test_test_parity.py::test_every_source_module_has_a_mirrored_unit_test_file`
   — **12 gaps, same count as documented pre-existing**; three now show the
   new `abi/` path (`construction.py`/`expressions.py`/`records.py` under
   `parsing/product/abi/`) in place of their old `parsing/product/` path,
   but the gap count is unchanged — moving the files did not create a new
   gap, it only renamed three existing ones.

   Two intermediate full runs during this pass are also on record:
   run 1 (before the README fix) showed **2 failed** — the above, plus a
   genuine regression, `test_every_active_source_folder_has_a_readme`
   (missing `abi/README.md`), fixed as described in item E. Run 2 (after
   the README fix, before reverting `auto_fix.sh`'s out-of-scope reformats)
   showed **2 failed** — `test_test_parity` plus one
   `tests/integration/lexic/concurrency/test_shared_artefact.py` row,
   documented as machine-load-flaky; rerun alone: **12 passed**, confirming
   it was load noise, not a regression.

3. **Witness scripts** under `zzz_current_work/260826-target-shaped-parse/proto/`,
   each `uv run python <file>`:

   | Script | Exit |
   |---|---|
   | s3_lowering.py | 0 |
   | s3_product_abi.py | **1** |
   | s3_dirty_cone.py | 0 |
   | s3_earley_target.py | **1** |
   | s3_lifecycle.py | 0 |
   | s3_route_lane.py | 0 |
   | s3_route_program.py | **1** |
   | s3_shared_forest.py | 0 |
   | s3_speculation_cost.py | 0 |
   | s4_authored_census.py | 0 |
   | s4_authored_product.py | 0 |
   | s4_model_plan.py | 0 |
   | s4_bake_identity.py | 0 |
   | s4_validated_path_census.py | **1** |
   | s4_switch_differential.py | 0 |

   All four non-zero exits are genuine logic/assertion failures, **not**
   import errors — each traceback runs deep into real program logic
   (`verify_program` raising `UnsupportedConstructError` on a 0-entry
   table for `s3_product_abi.py`/`s3_earley_target.py`/`s3_route_program.py`;
   an `AssertionError` in `s4_validated_path_census.py`'s own
   `_check` asserting `clone.ctor is None` for a `BUILD_TRANSPARENT`
   clone — the same `None`-vs-sentinel drift item B re-pinned in its test,
   but here inside a proto script outside this task's scope). Per the
   stop condition ("any other failure is reported, not fixed"), none of
   these four were touched.

4. **`uv run python tools/check_generated.py`** → `exported 53 modules` /
   `CLEAN: 0 pyright errors, 0 unaccepted pylint findings`, exit 0.

5. **`tools/run_checks.sh`** → exit 1. Gate-by-gate:
   - `10_sanity.sh`: OK.
   - `20_lint.sh`: **fails** — `ruff check` clean, but `ruff format --check`
     reports 4 files needing reformat, all pre-existing and **none touched
     by this pass**: `src/lexic/parsing/earley/kernel/forest/support/ambiguity.py`,
     `src/lexic/parsing/pda/runtime/kernel/execution.py`,
     `src/lexic/parsing/pda/runtime/kernel/kernel.py`,
     `tests/unit/lexic/parsing/test_fold.py`. `run_checks.sh` has `set -e`,
     so `30_typecheck.sh` and `40_pylint.sh` never execute as part of this
     gate.
   - `30_typecheck.sh` / `40_pylint.sh` (run manually for completeness,
     since `set -e` short-circuits them): typecheck is clean (0 errors,
     matches §1). Pylint reports pre-existing findings (score 9.99/10);
     spot-checked every finding that lands in a file this pass touched or
     moved (`product/abi/construction.py`: R0917/R0903/W0621 ×3;
     `product/abi/records.py`: W0621; `test_decisions.py:106`: E1136) by
     running pylint directly against the unmodified `git show HEAD:...`
     content of each — **every one reproduces identically on the
     unmodified HEAD file**, confirming none are new. `40_pylint.sh` is
     not reached by `run_checks.sh` and is reported, not treated as a gate
     this pass owns.

   **`auto_fix.sh` scope discipline**: running it once (as instructed)
   reformatted the 4 files above plus import-sorted 2 more untouched files
   (`src/lexic/parsing/products.py`,
   `src/lexic/parsing/pda/compiler/program/product.py`) and 2 untouched
   proto scripts (`s4_authored_product.py`, `s4_model_plan.py`) — none
   confined to files this pass touched. Reverted all eight with
   `git checkout --` (a forward restoration of tool side-effects on
   files never edited by this pass, not a rollback of any of this pass's
   own work) and kept the mechanical reformat only where it landed inside
   an already-touched file (`build.py`, `test_build.py`,
   `product/abi/construction.py`, `product/tree.py`,
   `product/__init__.py`'s import order). Re-verified after reverting:
   `ruff check` clean; `ruff format --check` and `isort --check-only`
   reproduce exactly the same 4-file / 2-file pre-existing drift,
   confirming the revert was exact.

## Restart point

Tree is at branch `targeter`, uncommitted, holding exactly items A–F plus
the one consequential test-decisions import fix and the one abi/README.md
addition — nothing else. `git status --short`:

```
 M CLAUDE.md
 M src/lexic/compile/product/lower.py
 M src/lexic/parsing/pda/compiler/program/flatten.py
 M src/lexic/parsing/pda/runtime/build.py
 M src/lexic/parsing/pda/runtime/kernel/decisions.py
 M src/lexic/parsing/product/__init__.py
RM src/lexic/parsing/product/construction.py -> src/lexic/parsing/product/abi/construction.py
RM src/lexic/parsing/product/expressions.py -> src/lexic/parsing/product/abi/expressions.py
RM src/lexic/parsing/product/records.py -> src/lexic/parsing/product/abi/records.py
 M src/lexic/parsing/product/tree.py
 M src/lexic/parsing/product/verify.py
 M src/lexic/parsing/trace.py
 M tests/unit/lexic/parsing/pda/compiler/program/test_specialize.py
 M tests/unit/lexic/parsing/pda/runtime/kernel/test_decisions.py
 M tests/unit/lexic/parsing/pda/runtime/test_build.py
 M tools/benchmark/bench.py
 M tools/benchmark/diagnostics/split_ab.py
?? src/lexic/parsing/product/abi/README.md
?? src/lexic/parsing/product/abi/__init__.py
```

`pyright src tests tools` is clean. The full suite has exactly one failure
left, `test_test_parity` (documented pre-existing, not this pass's to
close). `run_checks.sh` still exits 1 solely on 4 pre-existing
`ruff format` findings in files this pass never touched — the same 4 that
were present before this pass started. `check_generated.py` is clean. Four
witness scripts fail on pre-existing logic defects unrelated to the moves
in this pass (see §3); `s4_validated_path_census.py`'s failure is the same
`ctor is None` vs. sentinel contract drift item B fixed in its test, still
open in that proto script.

The production implementer can resume directly: no design or parse
semantics changed, only pyright/test-contract/file-layout mechanics.
