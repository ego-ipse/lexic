# parsing_2 optimization review — allocation / object-churn angle

**Scope:** allocation and per-item object churn in the hot Earley loops
(`ops.py` Predict/Complete, `chart.py` Column, `item.py` EarleyItem,
`forest.py` BuildTree, and the IR-leaf eq/hash they lean on).

**Measured baseline** (this machine, `uv run python bench_parsing.py`, x4 / 3680 ch):

| metric | Lark | parsing_2 |
|---|---|---|
| recognize | — | ~434 ms |
| parse | — | ~418 ms |
| parse+reduce | 109 ms | ~500 ms (4.6x slower) |

Key structural fact from the bench: **recognize ≈ parse**. Almost the entire
cost is `BuildChart` (recognition); tree extraction at the end is cheap, and
reduce is only ~16%. So the chart-construction inner loop is the target, and —
critically — **`Complete` builds a full `ParseTree` subtree on every completion
even during recognition** (it doesn't need to). That is the single biggest
mislocated allocation.

All experiments below were prototyped by monkeypatch, measured, then reverted.
No production code was changed.

---

## Profile evidence (cProfile, x4, 5 runs, parse+reduce, sorted tottime)

```
255620  0.848  ops.py:165   Complete.eval      (cumtime 3.355  ← dominant)
302205  0.736  ops.py:114   Predict.eval       (cumtime 2.781)
769480  0.643  chart.py:137 Column.__iadd__
254945  0.572  forest.py:73 BuildTree.eval     (cumtime 1.032)
 18405  0.542  engine.py:171 CloseColumn.eval   (cumtime 7.833 ← whole loop)
2864992 0.473  object.__new__
981625  0.397  base.py:581  IrTuple.__new__
704475  0.366  walk.py:57   IrDispatch.eval    (cumtime 6.803 ← dispatch tax)
495187  0.281  base.py:421  IrScalar.__eq__
842520  0.219  item.py:55   EarleyItem.__new__
704475  0.211  mapping.py:250 IrTypeMap.resolve
```

Per **single** parse of the x4 input (instrumented counts):

- `BuildTree` invoked **50 989** times (once per non-empty completion) — even in
  `recognize`, which never consumes the resulting tree.
- `Column.__iadd__`: 140 895 accepted, 13 001 rejected as dup (**8.4%** dup).
- `IrMultiMap.__getitem__` (waiting-bucket snapshot): 51 124 calls, only 136
  empty → nearly every Complete allocates a fresh `IrSeq` snapshot.
- Predict emits 98 223 dot-0 arm-items, 13 001 (**13.2%**) already present.

---

## Findings, ranked by measured payoff

### F1 — `Complete` builds the derivation subtree eagerly; defer it (lazy links)
**Severity: HIGH — ~15% on parse+reduce, ~36% on recognize (measured).**

**Evidence.** `Complete.eval` (`ops.py:179`) calls
`BUILD_TREE.eval(_d, done, IrTuple(chart, IrInt(ctx.col)))` for **every**
completion with waiters — 50 989 `ParseTree`+`IrSeq` allocations per parse, each
walking the provenance chain. This runs unconditionally, including during
`recognize`, where the tree is thrown away. cProfile: `BuildTree` cumtime 1.032 s
(≈10% of total), and it is the reason `recognize ≈ parse`.

The redundancy is also algorithmic: a sub-derivation gets fully built the moment
a rule completes, but it is only *needed* if that completion ends up on the
final accepted path. Many completions are dead ends.

**Proposed change.** Don't build the subtree in `Complete`. Store enough to
rebuild it on demand: record the `Link.child` as a small marker carrying
`(done_item, col)` instead of the materialised `ParseTree`. `BuildTree.eval`
(`forest.py:73`) already walks links; when it meets a marker child it recurses
`self.eval(_d, marker.done, (chart, IrInt(marker.col)))`. Only links on the
accepted spine are ever expanded, so recognition allocates **zero** subtrees and
parse allocates only the ones it returns.

- `ops.py:165-190` (`Complete.eval`) — drop the `BUILD_TREE.eval` call; store a
  marker in the `Link`.
- `forest.py:73-91` (`BuildTree.eval`) — expand marker children recursively.
- `recognize` (`engine.py:270`) then does no tree work at all.

**Measured.** fused-out: parse+reduce 488→365 ms (1.34x of the combined run),
recognize 434→278 ms. In isolation (lazy only) parse+reduce 505→431 ms (1.17x).

**Constraint impact.** **Keeps IrSelf purity.** The marker should itself be a
tiny `IrNamedTuple`/`IrLeaf` (e.g. `LazyChild(done: EarleyItem, col: IrInt)`,
`_child_attrs = ()`) so it stays an `IrSelf` engine node, exactly like `Link`.
`BuildTree` stays an `IrLeaf` with an `eval` body. No free functions. The only
nuance: `BuildTree.eval` now branches on `isinstance(child, LazyChild)` — a
closed-set check, but it is intrinsic engine logic (the same kind `Complete`
already does), not a consumer-policy ladder.

**Skeptical note.** The win on *parse+reduce* is smaller than on recognize
(1.17–1.34x) because parse must still build every subtree that lands on the
accepted spine — for an unambiguous grammar that is most of them. The big,
clean win is on `recognize`; if recognition is not a user-facing path, weight F1
lower and lead with F2.

---

### F2 — Per-item dispatch indirection in the close loop (fuse the three ops)
**Severity: HIGH — ~21% on recognize (measured), but a purity cost.**

**Evidence.** Every item in `CloseColumn` is routed
`d.eval → IrDispatch.eval (walk.py:57) → IrTypeMap.resolve (mapping.py:250) →
body.eval`. That is 140 895 round-trips/parse: `walk.py:57` 704 475 calls (cumtime
6.8 s — i.e. essentially the whole loop passes through it), `IrTypeMap.resolve`
704 475 calls. Per item this is two Python frames and a `dict.get` purely to pick
which of three known bodies to run.

**Proposed change.** Inline predict/complete/scan-skip directly into
`CloseColumn.eval` (`engine.py:171`), branching on
`isinstance(symbol, IrRuleRef)` / dot-at-end inline, instead of dispatching each
item through `EARLEY_OPS`. `Scan` then disappears entirely (it is a no-op target
that only exists to satisfy dispatch).

**Measured.** fused close loop alone: recognize 439→363 ms (1.21x). Combined with
F1 (lazy): recognize 434→**278 ms (1.56x)**, parse+reduce 488→**365 ms (1.34x)**.

**Constraint impact — CALLED OUT.** This **weakens the "operation = IR dispatch"
design**: the three ops cease to be independently-resolved `IrAction` bodies and
become inline branches in one method. The memory note "the Earley engine must
stay an IR construct — eval/dispatch + logic on classes" is *partly* honoured
(the logic stays on `CloseColumn`, an `IrLeaf`, via its `eval`; per-parse state
stays in `ParseCtx`), but the *type-dispatch substrate* that made predict/
complete/scan a clean table is collapsed. `EARLEY_OPS` / `EarleyParser` would
become vestigial.

**Recommended compromise.** Keep `Predict`/`Complete` as `IrLeaf` op classes
(so the algebra is still inspectable), but have `CloseColumn` call them
**directly** — `PREDICT.eval(...)` / `COMPLETE.eval(...)` chosen by an inline
`isinstance` — instead of via `IrDispatch.eval`+`IrTypeMap.resolve`. This removes
the `resolve` round-trip and the `Scan` no-op while keeping each op a self-
contained IrSelf body. Expect most of the 1.21x (the `resolve` + extra frame is
the bulk; the dead `Scan` dispatch is only ~1%, see F6). This preserves IrSelf
purity and only sacrifices the *open* table for a *fixed* three-way branch — and
the engine's op set is genuinely fixed (predict/scan/complete is the algorithm),
so the open-set value here is low.

**Skeptical note.** If you keep full `IrDispatch` dispatch for design reasons,
you forgo this ~21%. The bench gap to Lark cannot be closed on F1 alone.

---

### F3 — `IrMultiMap.__getitem__` snapshots the waiting bucket every Complete
**Severity: LOW–MED — ~3% (measured).**

**Evidence.** `Complete.eval` reads `chart[done.origin].waiting[done.rule_name]`
(`ops.py:176`). `IrMultiMap.__getitem__` (`mapping.py:317`) builds a fresh
`IrSeq(*bucket)` — a memoised-class lookup + tuple build — **51 124 times/parse**,
136 of them empty. The snapshot exists so a reader can iterate safely while the
live bucket grows (origin == col case). But `Complete` only needs to iterate; a
plain `tuple(bucket)` snapshot (or iterating a frozen copy) is enough and skips
the `IrSeq` class-synthesis path.

**Proposed change.** In `Complete.eval`, read the raw bucket and snapshot to a
plain tuple: `bucket = origin_col.waiting._table.get(done.rule_name)`; guard
`if not bucket: return IrNone`; iterate `tuple(bucket)`. (Or add a method-free
read dunder to `IrMultiMap` that returns a plain-tuple snapshot.) Also hoist
`chart`, `current`, `links`, `current._seen` out of the loop — small but free.

**Measured.** 431→419 ms (1.03x) in isolation.

**Constraint impact.** Reaching `waiting._table` from `ops.py` pokes the map's
private backing dict — acceptable since `IrMultiMap` is explicitly the engine's
internal mutable-chart exception, but cleaner to expose a dunder
(`__call__`/`__getitem__` variant) returning a plain tuple. Keeps IrSelf purity;
no free functions.

---

### F4 — Pre-check membership before allocating the advanced `EarleyItem`
**Severity: LOW — ~2–3%, and partly subsumed by F2.**

**Evidence.** The `advanced = EarleyItem(...)` then `if advanced not in col`
pattern (in `Predict`, `Complete`, `ScanColumn`) allocates 842 520 `EarleyItem`s
(`item.py:55`) + the underlying `tuple.__new__`, then **discards 8.4–13.2%**.
`EarleyItem.__new__` is already a fast positional `tuple.__new__`; the residual
cost is the allocation + the membership hash of a tuple that gets thrown away.

**Proposed change.** Key the column's `_seen` set on the **raw 4-tuple**
`(rule_name, arm, dot+1, origin)` so membership can be tested *before* building
the `EarleyItem`, allocating only on a true miss. Requires `Column._seen` to hold
plain tuples and `__iadd__` to accept the pre-built item (it already does).

**Measured.** Not separately benched to a clean number — the discarded-allocation
fraction is small (8–13%) and `tuple.__new__` is cheap, so the expected win is
~2–3%, mostly overlapping F2's fused loop (which already hoists the membership
test). **Likely not worth the readability cost on its own.**

**Constraint impact.** Mild: `_seen` would key on raw tuples rather than
`EarleyItem`s, a small leak of the item's structure into the column. Keeps
IrSelf purity otherwise.

---

### F5 — Cheaper `EarleyItem` hash via `id(arm)` — **REJECTED, measured slower**
**Severity: NONE (negative).**

**Hypothesis tested.** `EarleyItem` is a 4-tuple; CPython recomputes its hash
each probe, recursing into the `IrSequence` arm's deep tuple hash. Replacing it
with `hash((hash(rule), id(arm), dot, origin))` + identity-arm `__eq__` should be
cheaper.

**Measured: 0.81x (≈20% SLOWER).** The Python-level `__hash__`/`__eq__` (property
access, manual `hash()` calls) costs more than CPython's C-level tuple hash/eq,
which is already fast because the arm object is shared and its hash, once
computed, is cheap to re-probe. **Do not pursue.** Likewise `IrScalar.__eq__`
(495 k calls, `base.py:421`) is only reached on genuine element comparison, not
every probe, and is not a productive target.

---

### F6 — `Scan` is a no-op dispatch target; skip dispatching terminals
**Severity: VERY LOW — ~1%.**

**Evidence.** Terminal items dispatch to `Scan.eval`, which does nothing
(`ops.py:146`). Skipping the dispatch for non-ruleref symbols in `CloseColumn`
removes that chain. Measured 436→431 ms (1.01x) — there simply aren't many scan
items relative to predict/complete (80 vs thousands per the instrumented count).
**Folds into F2** (the fused/compromise loop drops `Scan` for free); not worth a
standalone change.

---

### F7 — Per-column predicted-ref skip set — **REJECTED, measured neutral**
**Severity: NONE.**

**Hypothesis.** 13.2% of predicted dot-0 items are duplicates; a per-column
"already predicted this ref" set would skip re-seeding its arms.

**Measured: 0.99x (neutral).** The bookkeeping (the extra set + membership) costs
as much as the `_seen`-dedup it avoids, because `Column.__iadd__`'s `_seen` check
already rejects the dups cheaply. Allocation saved ≈ allocation spent. **Do not
pursue** — a clean example of a plausible "win" that doesn't materialise.

---

## Recommended program (by payoff / risk)

1. **F1 (lazy subtree in Complete)** — biggest clean win, fully IrSelf-pure,
   especially if `recognize` matters. ~15% parse / ~36% recognize.
2. **F2 compromise (direct op calls, drop `IrDispatch.resolve` round-trip and the
   `Scan` no-op, keep Predict/Complete as IrLeaf bodies)** — ~21% recognize,
   modest purity cost (fixed three-way branch replaces an open table; the op set
   is genuinely fixed). Stacks with F1 to **1.56x recognize / 1.34x parse+reduce**.
3. **F3 (plain-tuple waiting snapshot + loop hoisting)** — ~3%, low risk.

F4/F6 fold into F2. F5/F7 are measured dead ends — recorded so they are not
re-attempted.

**Reality check on the 4.6x gap.** F1+F2+F3 land roughly **1.5–1.6x** on the
construction loop. That closes a meaningful chunk but does **not** reach Lark
(which is a C-accelerated LALR-ish parser doing far less per token than a general
Earley recognizer in pure Python). Earley is asymptotically heavier and
interpreted; parity with Lark is not a realistic target from allocation tuning
alone — the honest ceiling here is "materially closer," not "as fast."
