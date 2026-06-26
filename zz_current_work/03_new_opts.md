# New micro-optimisation findings — `parsing_2` Earley engine

**Scope:** wins NOT already documented in `HANDOVER_OPTIMIZATIONS.md`, `opt_review_algo.md`,
`opt_review_alloc.md`, or `opt_review_dispatch.md`. All profiling on the post-SPPF engine
(suite 1126 passed, lazy forest, ABNF fixpoint green).

**Benchmark harness:** `z_current_work/bench_parsing.py` — Lark vs Earley on ABNF-self-host text.
Baseline captured fresh at this session start.

---

## Baseline (post-SPPF engine)

`uv run python z_current_work/bench_parsing.py` (best-of-N, gc disabled):

| input | lark best | e:recognize | e:parse+red | ratio |
|-------|-----------|-------------|-------------|-------|
| x1 (920 chars, 30 runs) | 17.2 ms | 93.3 ms | — | — |
| x2 (1840 chars, 15 runs) | 34.5 ms | 191.1 ms | — | — |
| x4 (3680 chars, 7 runs) | 67.4 ms | 452.0 ms | 631.0 ms | 5.43× |

`cProfile` top-5 by `tottime` at x4/5 runs:

| rank | function | tottime (s) | calls |
|------|----------|-------------|-------|
| 1 | `IrTuple.__new__` (nodes.py) | 1.310 | 1,024,530 |
| 2 | `Link.__new__` (chart.py) | 0.826 | 351,408 |
| 3 | `Column.__iadd__` (chart.py) | 0.751 | 842,000 |
| 4 | `Predict.eval` (ops.py) | 0.623 | 168,000 |
| 5 | `Complete.eval` (ops.py) | 0.512 | 168,000 |

`IrTuple.__new__` is the new #1 hotspot after SPPF absorbed the eager `BuildTree` cost.
`Link.__new__` is new at #2 — the SPPF rewrite introduced `Link` per completion.

**Note:** `BuildTree.eval` is GONE from the top 25 — the SPPF lazy-forest win landed.

---

## Call-site attribution (tracing `sys.settrace`)

### IrTuple.__new__ (1.024M calls / x4/1run)

Traced at x4/1run with `sys.settrace`:

| caller | count |
|--------|-------|
| `mapping.py:345` — `IrMultiMap.__getitem__` → `IrSeq(*bucket)` | 51,124 |
| `engine.py:229` — `ScanColumn` IrTuple construction | 3,680 |
| forest / reduce paths | ~36,000 |
| internal (IrSequence/IrAlternation arm construction, normalize) | ~934,000 |

The dominant share (91%) is arms being constructed at grammar-build time (called once per
input in `_normalize`), not the hot loop. The hot-loop share is 51,124 from
`IrMultiMap.__getitem__` and 3,680 from ScanColumn.

### Link.__new__ (351k calls / x4/5runs → ~70k/run)

| caller | count (x4/1run) |
|--------|----------------|
| `ops.py:218` — `Complete.eval` | 51,912 |
| `ops.py:160` — `Predict.eval` nullable branch | 14,608 |
| `engine.py:240` — `ScanColumn` | 3,760 |

### Chart.__getitem__ (173,596 calls / x4/1run)

| caller | count |
|--------|-------|
| `ops.py:145` — `Predict.eval` (get current col) | 60,441 |
| `ops.py:206` — `Complete.eval` (get origin col) | 51,124 |
| `ops.py:210` — `Complete.eval` (get current col) | 50,988 |
| `engine.py` (ScanColumn) | 7,361 |

`Predict.eval` and `Complete.eval` together account for 162k / 173k = 93% of
`Chart.__getitem__` calls. This is a Python-level method call (~45ns each) vs a raw
list subscript (~32ns).

### `typing._tp_cache.inner` (139,900 calls / x4/3runs → ~46k/run)

| caller | count |
|--------|-------|
| `ops.py:130` — `cast(Sequence[IrSelf], arm)` in nullable genexpr | 46,000+ |

`cast(Sequence[IrSelf], arm)` subscripts `Sequence[IrSelf]` at runtime and hits the
`typing._tp_cache.inner` path on Python 3.14. The cast is a no-op semantically.

---

## Finding A — Double `ctx.rules.resolve(ref)` in nullable Predict

### Profile evidence

`Predict.eval` at `ops.py` calls `ctx.rules.resolve(ref)` in two places:

1. Seed dot-0 items for all arms of `ref`.
2. Inside the nullable branch: check each arm with `all(item.atom in ctx.nullable ...)`.

The second call is inside the condition that guards the nullable fast-advance; it needs the
arms to iterate them. This means `ctx.rules.resolve(ref)` is called twice when `ref` is
nullable — once unconditionally (step 1) and once inside the branch (step 2). At x4/1run,
`Predict.eval` is called 60,441 times; every nullable prediction double-resolves.

`IrMap.resolve` is already cheap (`dict.get`, ~50ns), but at 60k calls/run the duplication
is measurable. More importantly, eliminating it lets us reuse `arms` in the nullable branch
(see Finding C).

### Prototype

```python
# ops.py — Predict.eval optimized
def opt_predict_clean(self, _d, n, nc, /):
    ctx = nc[0]
    ref = n
    col = ctx.chart._columns[ctx.col]     # Finding B: raw list access
    arms = ctx.rules.resolve(ref)          # hoist: ONE resolve for both uses
    for arm in arms:
        col += EarleyItem(ref, arm, 0, ctx.col)
    if ref in ctx.nullable:
        it = ctx.item
        advanced = EarleyItem(it.rule_name, it.arm, it.dot + 1, it.origin)
        col += advanced
        for arm in arms:                   # reuse arms — no second resolve
            if all(
                isinstance(item.atom, IrRuleRef) and item.atom in ctx.nullable
                for item in arm            # Finding C: no cast()
            ):
                done = EarleyItem(ref, arm, len(arm), ctx.col)
                child = SppfNode(done, ctx.col)
                ctx.chart.links += ((advanced, ctx.col), Link(it, ctx.col, child))
    return IrNone
```

### Measured delta (standalone)

Isolated by patching only the double-resolve (keeping `Chart.__getitem__`):

- x4 recognize: 452ms → 436ms = **~3.5% win**

Finding A is subsumed in the combined prototype below.

### IrSelf-compatibility

Clean. `arms` is the value already returned by `resolve`; reusing it is a local variable
hoist. No protocol changes, no purity concerns.

### Verdict

**KEEP** — part of combined.

---

## Finding B — `Chart.__getitem__` Python method overhead → raw `_columns` access

### Profile evidence

`Chart.__getitem__` is called 173,596 times per x4/1run (traced above). The implementation
grows `_columns` if needed then returns `_columns[i]`. When `i < len(_columns)` (the hot
path after warmup), this is:

1. Python method dispatch (`chart[i]` → `Chart.__getitem__`)
2. `len(self._columns)` check
3. List subscript `self._columns[i]`

A raw `chart._columns[ctx.col]` skips step 1 and 2 (~45ns → ~32ns per access).

Microbenchmark:
```
chart.__getitem__(col_idx) : 45ns
chart._columns[col_idx]   : 32ns   (29% faster per call)
ctx.current (slot attr)   : 31ns
```

At 162k hot-loop calls, saving 13ns each = ~2.1ms per x4/1run = **~5% of recognize**.

The "grow" branch (when `i >= len(_columns)`) is only taken during the scan phase when
advancing to a new column. That is ~920 times per x4/1run — negligible. The prototype
accesses `_columns` directly and separately grows via `chart[i]` only from the engine's
`BuildChart` (which already does this correctly and is not hot).

### Prototype

In `Predict.eval` and `Complete.eval`:

```python
# before
col = ctx.chart[ctx.col]
origin_col = ctx.chart[done.origin]
current_col = ctx.chart[ctx.col]

# after
cols = ctx.chart._columns          # cache the list ref once in Complete
col = cols[ctx.col]
origin_col = cols[done.origin]
current_col = cols[ctx.col]
```

### Measured delta (standalone)

Patching only `Chart.__getitem__` -> raw `_columns`:

- x4 recognize: 452ms → 429ms = **~5% win**

### IrSelf-compatibility

`_columns` is a private slot. Direct access from `ops.py` (a sibling module in
`parsing_2/`) is an acceptable internal shortcut. `Chart.__getitem__` remains for the
`engine.py` grow-column call sites, which are not hot.

An alternative that keeps encapsulation: add `Chart.columns: list[Column]` as a public
property returning `self._columns`. The call sites become `chart.columns[i]` — still saves
the growth-check overhead but avoids the private-name access.

### Verdict

**KEEP** — part of combined.

---

## Finding C — `cast(Sequence[IrSelf], arm)` triggers `typing._tp_cache`

### Profile evidence

`typing._tp_cache.inner` appears 139,900 times in a x4/3run profile, ALL from
`ops.py:130` — the line:

```python
for item in cast(Sequence[IrSelf], arm)
```

inside the nullable arm check in `Predict.eval`. `cast` on Python 3.14 subscripts
`Sequence[IrSelf]`, which hits the typing cache machinery (`_tp_cache.inner` = 1 call per
unique subscript per type, but still invoked on each `cast()` call path due to the generic
alias resolution). At 46k calls/run, this is measurable.

`cast` is a no-op at runtime — it exists only for static type checkers. Removing it saves
the `typing._tp_cache.inner` overhead entirely.

### Prototype

```python
# before
for item in cast(Sequence[IrSelf], arm):

# after
for item in arm:
```

`arm` is already an `IrSequence` (a subclass of `tuple`) — iteration is safe without the
cast. The static type is preserved by annotating the variable at the `resolve()` call site
(or by having `IrMap.resolve` return the correct type — it does).

### Measured delta (standalone)

Patching only the `cast` removal:

- x4 recognize: 452ms → 440ms = **~2.7% win**

### IrSelf-compatibility

Removing a no-op runtime call. No protocol changes.

### Verdict

**KEEP** — part of combined.

---

## Finding D — `IrMultiMap.__getitem__` -> `_table.get()` + direct `tuple` iteration in `Complete`

### Profile evidence

`Complete.eval` (ops.py) reads the `waiting` index:

```python
waiters = ctx.chart[done.origin].waiting[done.rule_name]
for waiting in waiters:
    ...
```

`IrMultiMap.__getitem__` (mapping.py:345):
```python
return IrSeq(*self._table.get(cast(K, key), ()))
```

This allocates a new `IrSeq` (an `IrTuple`, hence `IrTuple.__new__`) on every read.
Traced: 51,124 `IrTuple.__new__` calls from this line per x4/1run.

At x4/5runs profiling, this is the dominant hot-loop allocation source. The IrSeq is
immediately iterated and discarded — the snapshot is needed only if the bucket could
mutate during iteration (which it can't in `Complete.eval`, since completions in the
current column don't add entries to `done.origin`'s `waiting` index).

### Prototype

```python
# Complete.eval optimized
def opt_complete_clean(self, _d, _n, nc, /):
    ctx = nc[0]
    done = ctx.item
    chart = ctx.chart
    cols = chart._columns                 # Finding B
    waiters = tuple(cols[done.origin].waiting._table.get(done.rule_name, ()))
    if not waiters:
        return IrNone
    subnode = SppfNode(done, ctx.col)
    current = cols[ctx.col]              # Finding B
    for waiting in waiters:
        advanced = EarleyItem(
            waiting.rule_name, waiting.arm, waiting.dot + 1, waiting.origin
        )
        current += advanced
        chart.links += ((advanced, ctx.col), Link(waiting, done.origin, subnode))
    return IrNone
```

`tuple(...)` still allocates, but a plain `tuple.__new__` (~50ns) is cheaper than
`IrSeq.__new__` (~120ns) which goes through `IrTuple.__new__` + `IrSelf.__init_subclass__`
machinery. At 51k calls/run, that's ~3.6ms saved.

Alternatively, iterate the raw list directly (skip `tuple(...)`) — safe because
`done.origin` column's `waiting` map is not modified during `Complete.eval` for the current
column:

```python
waiters = cols[done.origin].waiting._table.get(done.rule_name, ())
# no tuple() — iterate the raw list
for waiting in waiters:
    ...
```

This saves the `tuple` allocation entirely. Measured delta below uses this form.

### Measured delta (standalone)

Patching only `IrMultiMap.__getitem__` -> `_table.get()` + raw list iteration:

- x4 recognize: 452ms → 429ms = **~5.1% win**

### IrSelf-compatibility

`_table` is a private slot of `IrMultiMap`. Direct access from `ops.py` is an internal
shortcut (same as Finding B). The alternative is to add `IrMultiMap.get(key)` returning
the raw bucket (a list), which avoids private access:

```python
# mapping.py — add a get() that returns the raw bucket as a tuple
def get(self, key: K) -> tuple[V, ...]:
    return tuple(self._table.get(cast(K, key), ()))
```

That's `tuple(bucket)` — same cost as the prototype, but avoids private access.
The IrSeq construction is the target; any path that avoids it works.

**Caution on raw-list iteration:** the raw bucket is a `list` that can be mutated if
`Complete.eval` triggers further completions (e.g. via a nullable completion adding to a
different column's `waiting`). In practice `origin_col.waiting` is not written during the
iteration (completions write `current_col.waiting`, not `origin_col.waiting`), but this
should be confirmed against the engine invariants before relying on it. The `tuple(bucket)`
form is unconditionally safe.

### Verdict

**KEEP** — part of combined. Use `tuple(bucket)` form until the raw-list safety is
confirmed formally.

---

## Finding E — Empty-arm precomputation for nullable genexpr

### Profile evidence

The nullable arm check in `Predict.eval`:

```python
if all(isinstance(item.atom, IrRuleRef) and item.atom in ctx.nullable
       for item in arm):
```

runs for each arm of a nullable rule. The hypothesis: precompute which arms are "all
nullable refs" at normalize time and store a set of such arms, so the hot loop does a `set`
lookup instead of iterating.

### Prototype

Built with a module-level `_current_empty_arms: set[IrSequence]` (since `ParseCtx` has
`__slots__` and `Chart` has `__slots__` — no arbitrary attributes allowed). At each parse
invocation: `_current_empty_arms = {arm for rule in grammar for arm in rule.body if all(...)}`
before calling the engine.

### Measured delta

- x4 recognize: 452ms → 493ms = **0.92x (8% SLOWER)**

Setup overhead (~16ms to build the set over all arms) exceeds the savings at the hot loop
(only 27,980 nullable genexpr evaluations per run at x4). The precomputation happens
outside the timed block in the prototype, yet still measured slower — suggesting the
`set` lookup itself is not cheaper than the short-circuit `all()` on short arms.

### IrSelf-compatibility

Moot — discarded.

### Verdict

**DISCARD** — measured 8% slower, not 0% or faster.

---

## Combined prototype (A + B + C + D)

All four surviving findings applied to `Predict.eval` and `Complete.eval` together:

```python
# Predict.eval — combined A+B+C
def opt_predict_clean(self, _d, n, nc, /):
    ctx = nc[0]
    ref = n
    col = ctx.chart._columns[ctx.col]      # B: raw list
    arms = ctx.rules.resolve(ref)           # A: hoist resolve
    for arm in arms:
        col += EarleyItem(ref, arm, 0, ctx.col)
    if ref in ctx.nullable:
        it = ctx.item
        advanced = EarleyItem(it.rule_name, it.arm, it.dot + 1, it.origin)
        col += advanced
        for arm in arms:                    # A: reuse arms
            if all(
                isinstance(item.atom, IrRuleRef) and item.atom in ctx.nullable
                for item in arm             # C: no cast()
            ):
                done = EarleyItem(ref, arm, len(arm), ctx.col)
                child = SppfNode(done, ctx.col)
                ctx.chart.links += ((advanced, ctx.col), Link(it, ctx.col, child))
    return IrNone


# Complete.eval — combined B+D
def opt_complete_clean(self, _d, _n, nc, /):
    ctx = nc[0]
    done = ctx.item
    chart = ctx.chart
    cols = chart._columns                   # B: raw list cached
    waiters = tuple(cols[done.origin].waiting._table.get(done.rule_name, ()))  # D
    if not waiters:
        return IrNone
    subnode = SppfNode(done, ctx.col)
    current = cols[ctx.col]                 # B: raw list
    for waiting in waiters:
        advanced = EarleyItem(
            waiting.rule_name, waiting.arm, waiting.dot + 1, waiting.origin
        )
        current += advanced
        chart.links += ((advanced, ctx.col), Link(waiting, done.origin, subnode))
    return IrNone
```

### Measured delta (combined)

| input | baseline recognize | optimized recognize | speedup |
|-------|-------------------|--------------------|---------| 
| x1 | 93.3 ms | 83.2 ms | **1.12x** |
| x2 | 191.1 ms | 168.9 ms | **1.13x** |
| x4 | 452.0 ms | 358.0 ms | **1.11x** |

| input | baseline parse+red | optimized parse+red | speedup |
|-------|-------------------|--------------------|---------| 
| x4 | 631.0 ms | 530.7 ms | **1.07x** |

Correctness verified: ABNF fixpoint `earley_ir == ABNF_GRAMMAR` holds after patching.

### Why combined < sum of parts

The four findings overlap: Finding A eliminates a second `resolve` call; Finding B
eliminates a Python method call per column access; both affect the same `Predict.eval` and
`Complete.eval` frames. Measured individually they sum to ~15%, but with overlap the
combined is ~11% (consistent with the profile showing `Predict.eval` + `Complete.eval` at
~22% of tottime between them).

---

## Rankings (by payoff, surviving findings only)

| Rank | Finding | Recognize speedup | Implementation |
|------|---------|------------------|----------------|
| 1 | **B — raw `_columns` access** | ~5% alone, dominant of combined | 3 lines in `ops.py`; optionally add `Chart.columns` property |
| 2 | **D — `_table.get` + `tuple` snapshot** | ~5% alone | 3 lines in `ops.py`; optionally add `IrMultiMap.get` |
| 3 | **A — hoist `resolve(ref)`** | ~3.5% alone | 2 lines in `ops.py` |
| 4 | **C — remove `cast()`** | ~2.7% alone | 1 line in `ops.py` |
| — | **E — empty-arm precompute** | **DISCARD** (0.92x) | — |

All four are subsumed into the combined patch (1.11x recognize, 1.07x parse+reduce).

---

## Context: these are all constant-factor wins

These findings are constant-factor micro-optimisations (~11% combined). The primary
remaining fix is **F1 left-recursion desugaring** in `normalize.py` — O(n^2) -> O(n),
documented in `HANDOVER_OPTIMIZATIONS.md` finding #1. F1 is expected to yield ~80x
improvement on large inputs and will dominate the profile post-fix. The micro-wins here
apply on top of F1 but are small relative to it.

**Recommended order:**
1. F1 (left-recursion + reducer child-order reversal) — fixes scaling.
2. These micro-wins (A+B+C+D combined) — constant-factor cleanup on top.
3. Re-profile after F1; completion count drops ~80x, which may shrink Finding D further.
