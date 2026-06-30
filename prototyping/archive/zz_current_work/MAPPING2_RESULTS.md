# MAPPING2 Results

## What was built

`src/lexic/ir/mapping2.py` adds three classes coexisting alongside the originals (not wired in):

- **`IrMultiMap2`** — primary win. Replaces the `IrMultiMap` tuple-element-0 backing dict with a genuine `__slots__ = ("_d",)` field. Subclasses `IrLeaf` (a lightweight `IrSelf`-derived base with no tuple ancestry), so `_d` is a true C-level slot load instead of `tuple.__getitem__(self, 0)` through a property. Adds `get_live(key) -> list[V]` for callers that don't need snapshot isolation.
- **`IrMap2`** — thin subclass of `IrMap`. No behavioural change; ships no speedup (see verdict).
- **`IrTypeMap2`** — thin subclass of `IrTypeMap`. No behavioural change; ships no speedup (see verdict).

## Benchmark table

Hardware: Linux 6.17.0-35-generic. Method: gc.disable() per trial, median ± stdev over 31 trials.

### INSERT (N=5000 inserts, 5 keys, ~1000 values/bucket)

| implementation | median µs | stdev µs | ×vs raw dict |
|---|---|---|---|
| raw dict | 1121.5 | 44.1 | ×1.00 (floor) |
| `IrMultiMap` (current) | 1670.9 | 33.9 | **×1.49** |
| `IrMultiMap2` (new) | 1451.3 | 13.4 | **×1.29** |

Insert win: **×1.49 → ×1.29** (≈13% faster than current). The residual ×1.29 overhead is the Python `__iadd__` method frame + tuple-unpack; the dict ops themselves are at floor.

### READ (N=5000 hot-bucket reads)

| implementation | median µs | stdev µs | ×vs raw dict |
|---|---|---|---|
| raw dict `.get()` | 875.8 | 10.6 | ×1.00 (floor) |
| `IrMultiMap` snapshot read | 35447.5 | 542.5 | **×40.48** |
| `IrMultiMap2` snapshot read | 34902.3 | 178.1 | **×39.85** |
| `IrMultiMap2` live read (`get_live`) | 1044.8 | 4.4 | **×1.19** |

**Key finding:** the read bottleneck is NOT the tuple-element-0 property — it is `IrSeq` allocation. Both snapshot read paths are ~×40 vs dict because every `__getitem__` call constructs a fresh `IrSeq(*bucket)`. The live read (`get_live`, returning the backing list directly) is ×1.19 — near floor.

This changes the hot-path strategy: callers that do not need snapshot isolation (i.e. that do not grow the bucket while iterating) should use `get_live` instead of `mm[key]`.

### DISPATCH (1000 resolve calls, realistic node-type mix)

| implementation | median µs | stdev µs | ×vs current |
|---|---|---|---|
| `IrTypeMap.resolve` (current) | 97.6 | 1.7 | ×1.00 |
| `IrTypeMap2.resolve` (new) | 97.5 | 2.8 | **×1.00** |

No measurable difference — the parent's `dict.get(type(n))` fast-path already has no recoverable Python-layer overhead.

## Purity justification

### `IrMultiMap2`

- IS-A `IrSelf` (via `IrLeaf[IrSelf, IrSelf]`): satisfies the IR-substrate contract.
- Behaviour lives on the class: `__iadd__`, `__getitem__`, `__contains__`, `get_live`, `__eq__`/`__ne__`/`__hash__`, `children`, `__repr__` — all dunders or named accessors, no free functions.
- Mutable state lives in `_d`, a slots field on the `IrSelf`-derived object. The class IS the map — no external dict owner.
- Identity equality/hash: consistent with `IrMultiMap`; a mutable map is its own value.
- No `exec`/`eval`, no `# type: ignore`/`# noqa`/`# pylint: disable`, no grammar-specific hardcoding.

### `IrMap2` / `IrTypeMap2`

- Thin subclasses, inherit all purity properties from `IrMap`/`IrTypeMap`.
- No code added — exist only as test targets and benchmark anchors.

## Verdicts

| class | ship-worthy? | reason |
|---|---|---|
| `IrMultiMap2` | **Yes** — when wired in | ×1.49 → ×1.29 insert improvement; stdev drops (lower noise). Unlock `get_live` for the Earley predictor hot path (~×34 read speedup for non-iterating callers). |
| `IrMap2` | **No** (keep as thin alias) | No measurable dispatch speedup; adding a class buys nothing. |
| `IrTypeMap2` | **No** (keep as thin alias) | Dispatch identical to parent; parent's fast-path is already optimal at Python layer. |

## Test status

`uv run pytest tests/unit/lexic/ir/test_mapping2.py -q`: **30 passed**
`uv run pytest tests/ -q -p no:randomly`: **1156 passed** (1126 pre-existing + 30 new)
