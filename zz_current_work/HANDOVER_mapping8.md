# Handover — `mapping8.py` (fast IR map family) — 2026-06-28

## What it is
`src/lexic/ir/mapping8.py` — a faster, drop-in candidate to **replace**
`src/lexic/ir/mapping.py`. Common ancestor + slot-backed `_table` (no tuple
ancestry, no per-table synthesized classes):

- `IrMapping[K, V, R]` (on `IrLeaf`, `__slots__=("_table",)`) — owns the whole
  surface: empty `__new__`, frozen `__setattr__`/`__delattr__`, `__getitem__`
  (value, raise on miss — EAFP), `__contains__`/`get`/`__len__`/`keys`/`values`/
  `items`/`__iter__`, `resolve` (+`IR_DEFAULT`)/`eval`, structural
  `__eq__`/`__ne__`/`__hash__`, `__repr__`. `R` = read-return type (value vs bucket).
- `IrMap(IrMapping[K,V,V])` — adds only the dyad-indexing `__new__` (canonical
  key-repr-sorted `_table`).
- `IrTypeMap(IrMap[type, IrSelf])` — `resolve` (exact `table[type(n)]` EAFP → MRO →
  `IR_DEFAULT`) + typed `eval`.
- `IrMultiMap(IrMapping[K,V,Sequence[V]])` — overrides `__getitem__` to return the
  **live** bucket (`_table.get(key, ())`, no copy), `__iadd__` (O(1)), identity
  `__eq__`/`__hash__`. Backing dict is the same `_table` slot, so `Links` /
  `Column.waiting` subclasses need no change.

## Status
- **Not wired in.** Coexists; nothing imports it yet. `mapping.py` untouched.
- Gates: pyright **0**, ruff clean, pylint **10**. `tests/unit/lexic/ir/test_mapping8.py` **31 pass**.
- Adversarial review done: `zz_current_work/MAPPING8_ADVERSARIAL_REVIEW.md`.
  Patches **A** (`IrTypeMap.resolve` EAFP) + **B** (`IrMapping.__getitem__` EAFP)
  already applied. C/D (EAFP on `__iadd__` / `IrMultiMap.__getitem__`) rejected —
  miss-heavy, exception cost regresses them.

## Performance (vs original `mapping.py`, gc-off median)
- Real-workload swap: ABNF **recognize +5.7%, parse +8.1%**, fixpoint True.
- IrMap read **×1.07** of dict floor; IrMultiMap read **×1.12** (~×35 faster than
  the original's `IrSeq` snapshot); IrTypeMap dispatch **~44µs** (orig ~60);
  insert −17%.

## Cutover steps (when ready to land — NOT done)
1. Replace `mapping.py` contents with `mapping8.py` (file rename; class names are
   already canonical `IrMap`/`IrTypeMap`/`IrMultiMap`/`IR_DEFAULT`). Delete mapping8.py.
2. Migrate `forest.py::ForestCtx` (the one tuple-coupled consumer): tuple-slot-1
   `chart` → real slot — `__slots__=("chart",)`, `__new__` does
   `super().__new__(cls)` + `object.__setattr__(obj,"chart",chart)`, drop the
   `chart` property + `tuple.__new__`. (`Links`/`Column.waiting` need nothing.)
3. Rewrite the **8 representation-pinned tests** that assert the old tuple ancestry
   (not behaviour): in `test_mapping.py` — `test_data_map_positional_int_returns_dyad`,
   `test_data_map_slice_returns_tuple`, `test_plain_int_zero_is_positional_*`,
   `test_contains_is_key_based_not_dyad_based`, `test_synthesized_class_is_weakly_held*`;
   `test_walk.py::test_irdispatch_is_caching_tuple`;
   `test_chart.py::test_links_getitem_snapshot_is_safe_while_bucket_grows` (now a
   **live** bucket, not a snapshot); `test_engine.py::test_nullable_rules_returns_irseq`
   (returns `IrMultiMap`, not `IrSeq`). Port `test_mapping8.py` over `test_mapping.py`.

## Validation recipe (used throughout)
Temp shim `mapping.py` → `from lexic.ir.mapping8 import *` + the ForestCtx
migration, then: ABNF fixpoint True and full suite **1149 pass** with exactly the
8 expected failures above. Always `git checkout` the temp edits after.

## Key design notes / caveats
- `__getitem__`/`__iter__`/`__repr__` reconstruct dyads from `_table` (lose the
  original dyad object type, e.g. `IrAction`), but `repr` still round-trips to a
  **structurally equal** map (equality is over `_table`), so it stays valid codegen.
- EAFP (`dict[key]`) only wins where misses are rare (rule/dispatch lookups → A,B).
  Do **not** apply it to `__iadd__` (first-insert-dominant) or
  `IrMultiMap.__getitem__` (`Complete` reads empty `waiting` buckets often).
- Constraints kept: IrSelf-derived, no `# type: ignore`/`# noqa`/`# pylint: disable`,
  no `exec`/`eval`, pyright-clean. `cast` is allowed (none needed currently).

## Pointers / leftovers (all untracked in `zz_current_work/`)
- `MAPPING8_ADVERSARIAL_REVIEW.md`, `bench_mapping8.py` (+ adversary scratch benches,
  `*_original_backup.py`).
- Superseded prototypes still on disk: `mapping5.py`, `mapping6.py`, `mapping7.py`
  (+ their benches). mapping8 is the live one.
- Round-4 parsing spikes (separate effort): `HANDOVER_round4.md`,
  `SPIKE_f1_base_cost.md`, `SPIKE_char_indexed_scan.md`.

Never `git commit` autonomously — leave staged for the user.
