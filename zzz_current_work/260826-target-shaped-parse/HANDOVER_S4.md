# HANDOVER — §4 remaining work (written 2026-09-01, coordinator session ending)

Read `LEDGER.md` top-down alongside this; every ruling cited here is recorded
there in full. `TODO.md` §4 carries the execution map and per-bullet
annotations. The tree sits at the user's unverified `Savepoint 5` plus a few
uncommitted coordinator edits (listed at the bottom).

## Where §4 stands

Steps 1–2 and slice 2a/2b of step 3 are LANDED (slice 2b unverified): the
model product is authored from the binding view (`model_plan`,
`RecordConstructor` with `matched_field`), the PDA bake is product-side and
unconditional (`bake_product_build`; `_build_plan` deleted), `CloneSpec`
carries `product`, `ConstructionTables(constructors, symbols)` threads
`compile_pda → flatten_* → bake`, the eight runtime `clone.fold` reads are
gone (`FlatClone` lost `fold`, gained `ctor`/`matched`/`n_items`;
`build.py`/`execution.py`/`specialize.py` read clone slots), `_build_mode`
derives from the completion record, `needs_ends` covers TEXT-or-EXTENT, and
the three authored surfaces (notation 21 rules, selfgrammar 63, templating 9)
author products beside their fold tables with a checked-duplicate
differential. The channel (`ModelBinding(fold, rules, construction)`) is live
through every parse entry with the memo keyed on binding identity.

**Nothing has been verified since `construction.py` was restored.** Last
verified-green state was pre-one-shot (5339/8/1-attributed at `-n 8`,
gates 0, pyright 0/0/0).

## Exactly what is left, in order

### 0. Verify the landed one-shot
Gates 10/20/30/40 UNPIPED one at a time reading `$?` (pylint prints 10.00/10
while exiting nonzero). Suite `uv run pytest tests/ -q -n 8` — NEVER `-n
auto` (harness overlap witness fails at workers==cores; ledgered). Known
reds going in: `templating.py` at 704 lines; `proto/s3_lowering.py` witness
(call sites still pass bare strings where `LoweringOwned.symbols` is now
`tuple[SymbolConstructor, ...]`); the attributed `test_test_parity` gate.
A 13-test regression (`m-int` naming `"int"`) was already fixed pre-stop.
Anything else is undiagnosed.

### 1. templating.py line ceiling (704/700)
Honest relocation only — terra-3 already folded `_entry_body`/`_entry_rule`
into `_entry_pair` and trimmed its own prose; do NOT trim further prose or
contort code. A committed gate red from a good change is a REPORT.

### 2. Step 4 — Earley / island / delegated completion onto the product ABI
The big open half. `ModelFold.apply` (parsing/fold.py) is still the Earley
executor, driven by `RuleFold` recipes baked from authored `ModelBody`
tables. Target: a product-driven fold executor consuming
`ModelBinding.rules + .construction` — same recipe derivation the PDA bake
uses (`Construction` in `pda/compiler/program/product.py`; factor a shared
helper rather than a second derivation). Consumers to move:
- `products.py::earley_model` + `collapsed_fold_tables(grammar, fold, bits)`
  — the run-collapse licence `run_ok` reads `fold.config` keys; re-source
  from `binding.rules` keys (equivalent set by the two coverage guards).
- `pda/runtime/islands.py`, `pda/runtime/kernel/kernel.py` (fold-typed
  seams), `earley/engine.py`, `earley/kernel/forest/forest.py` fold refs.
- `parallel/replicas.py` (clones the binding already; fold typing remains),
  `parallel/stitch/{model,tasks,interior}.py` — `stitch/model.py` reads
  RuleFold field slots; re-source from `RecordConstructor.names` + capture
  layout. Stitching SEMANTICS stay byte-identical (ruled).
- Keep `fold.py`'s span/offsets machinery (`wants_spans`, `_tree_offsets`,
  `_slot_span`) — it moves WITH the executor (templating's EXTENT captures
  need it); `MeaningMemo`/`remembered`/`replayed` in
  `earley/.../ambiguity.py` take the fold as a parameter — re-point them.
- The two §3 executor findings apply here too: Begin*-at-descent,
  MANY-through-transparent-nodes; and the value-once `folded`-set discipline
  (recently fixed) must survive the rewrite.
- `ModelBinding` then loses `fold`; `bind_model` (compile/product/binding.py)
  stops building folds; `verify_covered`/`_check_covered` re-aim (their fold
  side dies).

### 3. Step 5 — compile side + trace.py
- `pipeline/synthesis.py`: delete `fold_config` (model_plan stays);
  `pipeline/binding.py` drops its `ModelBody` reference.
- `compile/foldkit.py`: delete the fold-authoring half (`seq`, `model_fold`,
  `ModelBody` use); KEEP the product vocabulary (`AuthoredProduct`,
  `ALT_PRODUCT`, `product_rules`) and the `FOLD_SYMBOLS`/`IrNamed` no-eval
  registry with the named symbols (`first_rest`, `absent_tail`, `DECODE_INT`,
  `decode_int` — added because builtin `int` is positional-only; `"int"`
  stays registered for the committed pin). Account for every named symbol
  per the §4 bullet.
- `notation/parse.py`, `module/selfgrammar.py`, `output/templating.py`:
  drop their `_BODIES`/fold tables; bindings from product tables alone.
  This retires the checked duplicate — retire its differential rows
  DELIBERATELY (they assert product-vs-fold agreement; the fold side is
  gone), keeping the product-side property assertions.
- `parsing/trace.py`: rewrite — it is a public `PdaKernel` subclass
  shadowing exactly the completion surfaces that moved; public surface
  unchanged; port target noted in TODO §4.
- `compile/artifact.py`: fold-free binding path.

### 4. Step 6 — delete the six symbols
`FOLD_KINDS`, `FieldFold`, `FastCtor`, `RuleFold`, `ModelBody`, `ModelFold`
from `parsing/fold.py`, plus `parsing/__init__.py` exports, `CloneSpec.fold`,
`_bake_build`'s residual `fold` parameter, and every README/CLAUDE.md map
line. No wrappers, no generic-looking renames. The class-side
`fast_construct` licence stays (it is the model layer's; `_licence_of`
reads it cold).

### 5. Value-string specialization (§4 bullet, UNSTARTED)
In `pda/compiler/program/specialize.py`: where
`parsing/product/regular.py::prove_regular` proves a `value_str` occurrence
exact, compile ONE recognizer consult returning its extent instead of the
per-character program; declined rules keep the current program; completion/
capture stays the ordinary rule range; no target code in the recognizer.
Gate generated-model and token rows separately (measurement is the
coordinator's, at the §4 gate).

### 6. Step 7 — §4 exit protocol (after src is in)
Close the per-step opcode account (entries in LEDGER; final before/after
comparison per the §4 bullet). Run `uv run python tools/check_generated.py`.
Full suite + pyright with the failing-file set ledgered and attributed.
CLAUDE.md map updated for every moved/deleted module. Then the COORDINATOR:
external alternating profile with a byte-identical control on a quiet
machine (docs/STYLE §7; instrumentation outside src; one benchmark at a
time), §4 checkpoint commit under the recorded grant, then the
USER-SCHEDULED scoped Luna pass (unit-test mirrors only — restores a fully
green suite; §13 still re-homes/completes). The user is preparing an
EXTERNAL REVIEW to be read before test milestones — check before declaring
any test-passing milestone.

### 7. Witness repairs (effort proto/, not src)
Fix `s3_lowering`'s `LoweringOwned(symbols=...)` call sites to
`SymbolConstructor` records; re-run ALL witnesses; `s4_switch_differential`
has not run since the ABI change; `s4_bake_identity` re-tests the widened
unlicensed-fields contract.

## Standing rules that bind the next session
- Roles: Opus implements nontrivial src; Sonnet does lint/pyright/mechanical
  fixes and stabilization; NEVER Opus on mechanical loops. Terra/Luna strictly
  sequential — one active agent at a time.
- Proportion rule (user-imposed): fallout beyond ONE adaptation cycle stops
  and reports the blast radius. Mechanical test adaptation: construction/call
  syntax only, assertions byte-for-byte, files listed.
- Gates by `$?`, unpiped. Suite at `-n 8` on this host. Kernel edits by hand
  on unique context. Witnesses for every claim; negative controls that can
  actually fail. Every increment names the §4 bullet it serves.
- No commits/stages/pushes except the coordinator under the recorded grant
  ("Commit meaningfully (orchestrator only)" + checkpoint ruling). User
  savepoints in history are unreviewed backups; §14's squash accounts for
  them.
- No parse-performance regression without the user's explicit post-measurement
  approval. Zero-tax on the model paid path is the §4 gate's core claim.

## Uncommitted coordinator edits in the tree (disclosed)
- `tests/integration/lexic/invariants/test_source_structure.py`: `.md` files
  no longer count toward the folder-file cap (USER-ORDERED correction;
  `__init__.py` was already exempt). The 700-LINE ceiling still applies to
  .py files — templating's 704 is a real red.
- Effort docs: LEDGER/TODO/INDEX/DESIGN updates through this session.
