# mapping8 perf session — 2026-06-29

Baseline this session (original mapping.py, no swap): recognize 94.3ms, parse 121.0ms.
mapping8 swap (handover state): recognize ~85ms (+10% vs original), parse ~110ms.

## Findings

### Opt1 — EAFP on `IrMapping.resolve`  ✅ KEPT (in mapping8.py)
The adversarial review applied EAFP to `IrTypeMap.resolve` (patch A) and
`IrMapping.__getitem__` (patch B) but MISSED `IrMapping.resolve` — used by
`ctx.rules.resolve(ref)` (an IrMap) 93,835×/parse on the hot Predict path,
still doing `.get()+None-check`. Switched to `try: table[n] except KeyError`.
Micro: 49.6µs → 31.5µs (37% faster) on the hit-dominant pattern. Same logic
& safety as patches A/B. e2e effect below noise (resolve is ~1.2% of total),
but strictly positive and zero-risk.

### Dispatch frame win — direct `_table` only (encapsulation fork, NOT applied)
`IrDispatch.eval` paid a full `resolve`/`__getitem__` **method frame** per
dispatch (167,475/parse). Inlining the exact-type lookup as
`actions._table[type(n)]` (C-level slot read + dict getitem, zero frames) gives
**+1.4–1.9%** on recognize (interleaved, drift-free). BUT it reaches past the
public `resolve`/subscript seam into `_table`. The clean public-subscript route
`actions[type(n)]` is **+0.0%** — the IrKeyError-raising `__getitem__` override
re-introduces the frame. Tradeoff left to the user.

### Option 4 — `IrMapping` subclasses `dict`  ❌ REJECTED (measured slower)
Idea: node IS its dict (V2: str→str, tuple→tuple, map→dict), so
`actions[type(n)]` becomes native `dict.__getitem__` (clean AND fast), and
~6 delegating methods vanish. Required relaxing the bare-subscript contract from
IrKeyError → plain KeyError (only consumer is the dispatch line, which catches
KeyError; `resolve` still raises IrKeyError — the meaningful seam). Prototyped
fully; all behavior correct; 7 representation/contract tests need porting.
**Measured ~2.5% SLOWER overall** (recognize 87.7 vs slot 85.4; parse 113 vs
110.6; non-overlapping groups). The dict-subclass taxes the much-hotter
`IrMultiMap` ops (`__iadd__`/`__getitem__` via unbound `dict.get(self,…)` /
`dict.__setitem__(self,…)`, plus CPython de-opting dict internals once dunders
are overridden) more than the dispatch lookup saves. Net negative → keep the
slot-backed design.

## Net recommendation
Keep slot-based mapping8 + Opt1. Decide the dispatch `_table` fork separately
(+1.4–1.9% for a soft encapsulation break within ir/).
