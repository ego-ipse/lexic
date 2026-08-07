# Proposal — two post-flatten optimizer gaps

**Status:** investigated and **prototyped to failure, twice** — which is what
made the proposal correct. §1 as first written does not work, and §6 records why
and what the real change is. No `src/` changes.

Context: `OPTIMIZATION.md`. The common path (`bench --only vyx`, 5.658 µs/char
on real traffic) costs **1.56 clone entries per character**, and time tracks
entries, not models — a 46% model cut bought 16%, an 11% entry cut bought the
same 16%.

---

## 1 — The gap: attempt sub-clones never see the optimizer

`flatten_clones` (`compiler/lower.py`) runs in this order:

```python
shells = {key: FlatClone.__new__(FlatClone) for key in clones}
...fill each shell...
optimize_program(list(shells.values()))          # ← the five passes
for key, spec in clones.items():                 # ← AFTER
    if spec.attempt_follow is not None:
        clone.attempt = (spec.attempt_follow, _attempt_entries(clone, ...))
```

`_attempt_entries` builds a single-arm **sub-clone** per attempt entry
(`_sub_clone`, which copies the parent's final baked state and shares its
`FlatArm`). Those sub-clones are created *after* `optimize_program` has already
run over the shell set, and they are not in it — so `_convert_dispatch` and
`_mark_leaves` never see them.

### Evidence

31 sub-clones exist in the compiled vyx program. At runtime they account for
**1,396 clone entries per parse — 25.9% of all 5,394**:

```
  452  kv-pair      SUB-CLONE
  444  value        SUB-CLONE
  330  body-line    SUB-CLONE
  144  scope-item   SUB-CLONE
   26  bare-val     SUB-CLONE
```

Every one is `BUILD_ALT`, one arm, one exactly-once ref — the exact shape
`_convert_dispatch` exists to make frame-less, and whose conversion its own
docstring calls "observationally identical to the frame it replaces".

### The change — REVISED, see §6

Running the specialisation passes over the sub-clones is necessary but **not
sufficient**, and doing only that crashes the runtime. §6 has the diagnosis and
the two-part change it actually requires.

**One thing must widen for it to fire.** `_unit_ref_target` accepts only
`OP_REF`. A sub-clone shares its parent's arm, and `_specialize_calls` has
already rewritten that arm's ref to `OP_REF1`. `OP_REF1` is the same thing —
an exactly-once clone reference with a `FlatClone` payload — so the test should
read `kind in (OP_REF, OP_REF1)`. That widening is safe for the main pass too,
where nothing is `OP_REF1` yet, so it is a no-op there.

### Expected win

Unquantified on purpose. By the §4 calibration an 11% entry cut moved time 16%;
this is a 26% entry cut, so the same ratio would put it well past the model
route. **But the ratio is one data point and these entries are not the same
entries** — a dispatch conversion removes a frame push and a completion, not a
whole sub-parse. Treat 16% as the floor of what an entry cut has been worth, not
as a prediction.

### Risk

Attempt sub-clones are entered through the **sub-run seam**
(`_attempt_run` → `_enter`), not the ordinary driver path. A dispatch clone is
chased frame-lessly in `_enter`, which is where the sub-run's `floor`
watermark is taken. Whether a frame-less chase interacts correctly with
rollback is the question this proposal cannot answer from the outside, and is
the first thing an implementation should establish. The parity differentials
are the gate.

---

## 2 — The smaller gap: `OP_VSTR` disqualifies a bigger optimization

Measured at pass time during a real compile: of 21 `BUILD_ALT` clones,
9 converted and 12 declined —

```
  7  attempt (arms tried in order)                        deliberate
  5  gated arm not a unit ref: n=1 kind=OP_VSTR lo=1 hi=1  ← a gap
```

`_inline_value_strs` runs before `_convert_dispatch` and rewrites a
terminal-only ref to `OP_VSTR`. `_unit_ref_target` does not recognise it, so a
single-arm alternation over a value_str rule loses the dispatch conversion
because it won an inlining. This is the same pass-ordering hazard
`optimize_program`'s docstring already guards for `OP_REF1` ("which must not
pre-empt the dispatch pass's unit-ref shape check") — unguarded for `OP_VSTR`.

Worth ~**52 entries per parse (1%)**, so this is a correctness-of-design fix
rather than a performance one. `OP_VSTR`'s payload is a clone, like `OP_REF`'s,
but the runtime treats it differently (it runs the value_str loop inline), so
whether dispatch can chase it needs checking — it may be that the honest fix is
to run dispatch conversion *before* value-str inlining rather than to widen the
test.

---

## 3 — Also found, not proposed

**Single-char value_str models.** 54% of all models are one character
(`nl-word ::= nl-tail+` over a char-class rule). Collapsing them into a text
span was prototyped grammar-side: **46% fewer models, 16% faster**. Not proposed
because it changes the generated class surface — `tuple[NlTail, ...]` becomes a
string — which is a design decision about what the model layer promises, not an
optimization. Recorded because it bounds that route: 16% is its ceiling, and it
costs an API change to collect.

**Model interning is already effective** — 3,342 model references resolve to 561
distinct objects. No lever there.

---

## 4 — The failed prototype, recorded as a warning

I tried to prototype §1 by walking the finished program and calling
`_convert_dispatch` on every reachable clone post-hoc. It produced a corrupt
program: `AttributeError: 'FlatClone' object has no attribute 'n'`, because a
converted clone's `selectors` hold clone payloads where the driver expected a
`FlatArm`.

The lesson is the same one §8 of `OPTIMIZATION.md` records: **these passes are
order-dependent and cannot be applied out of band.** A real prototype has to run
inside `flatten_clones`, at the point the sub-clones are created. That is a
`src/` change, which this investigation was scoped out of — so the proposal is
handed over diagnosed rather than demonstrated, and the first implementation
step is to build that prototype properly and measure it before believing any of
the numbers above.

---

## 5 — What a reviewer should push on

- **Is the sub-clone actually equivalent to its dispatch conversion under
  rollback?** §1's risk. If not, the whole 26% is unavailable and §2's 1% is
  what remains.
- **Is `OP_REF1` genuinely the same as `OP_REF` for `_unit_ref_target`?** It
  should be — same payload, same bounds — but the specialisation exists because
  the driver treats them differently, and that difference is exactly what the
  dispatch path bypasses.
- **Is 16% really the floor for an entry cut?** It is one calibration point from
  a grammar-side rewrite that changed several things at once (entries, models,
  and `_run_leaf` all moved). A cleaner calibration would strengthen or kill the
  case for §1 before it is built.


---

## 6 — Iteration: the prototype failed twice, and the second failure is the answer

Prototyped §1 properly — inside the pipeline, patching `_attempt_entries` so
each sub-clone gets `_convert_dispatch` + `_mark_leaves` at the point it is
born, with `_unit_ref_target` widened to accept `OP_REF1`. It crashes:

```
_enter → self.stack.append([arm, 0, 0, out, clone.mode, clone, ...  [0] * arm.n
AttributeError: 'FlatClone' object has no attribute 'n'
```

The same crash as the out-of-band attempt in §4, which rules out "applied at the
wrong time" as the explanation. Reading `_enter` gives the real one:

```python
char = self.text[self.pos : self.pos + 1]
if clone.mode == BUILD_DISPATCH:      # ← the chase happens HERE
    clone = self._chase_dispatch(clone, char)
if clone.attempt is not None:
    sole = sole_admitted(clone.attempt[1], self.text, self.pos)
    ...
    clone = sole                      # ← ...and the clone is REPLACED here
...
for chars, negated, candidate in clone.selectors:   # ← generic arm path
```

**The dispatch chase runs before the attempt-entry substitution.** When
`sole_admitted` picks a single admitted entry, `clone = sole` installs a
different clone and execution falls through to the generic selector loop — which
finds a `FlatClone` where a `FlatArm` is expected, because the sub-clone was
converted. The mode is right and nothing ever looks at it again.

### So the real change is two-part

1. **Compile:** run `_convert_dispatch` / `_mark_leaves` over the attempt
   sub-clones where `_attempt_entries` creates them, with `_unit_ref_target`
   widened to accept `OP_REF1` (a sub-clone shares its parent's
   already-specialised arm).
2. **Runtime:** `_enter` must re-check the specialisations after `clone = sole`
   — the substitution installs a clone that has not been through the checks
   above it. The same applies in principle to `clone = chased`, though a
   dispatch target is a concrete rule clone and is already covered by the pass.

Part 2 is the load-bearing half and is the reason this could not be prototyped
by a compile-side patch alone. The cleanest shape is probably to make `_enter`'s
head a small loop — chase, substitute, re-check — rather than a straight-line
sequence of three independent tests, since the current shape has exactly one
ordering that works and no way to say so.

### What this does to the sizing

Unchanged in principle — 1,396 entries (25.9%) are still the population, and
they are still the shape dispatch exists for. But the risk named in §1 was
**correct and is now concrete**: the sub-run seam does not compose with a
frame-less chase *as the runtime is currently written*. That is a real change to
the entry path, not a pass-ordering fix, and it wants the parity differentials
plus the attempt-heavy grammars (vyx, c.gbnf) as its gate.

### Recommendation, revised

- **§2 (the `OP_VSTR` gap) is the safe, small win** — 1%, self-contained,
  compile-side only. Take it first and independently.
- **§1 is worth doing but is not a small change.** It touches `_enter`, which is
  the hottest path in the engine. An implementer should build the two-part
  change together and measure before believing the 26%, because part 2 adds work
  to every entry to save work on a quarter of them — and that trade is exactly
  what the calibration in §4 cannot predict.
