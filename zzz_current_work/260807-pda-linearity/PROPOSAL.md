# Proposal — optimize the attempt sub-clones

**Status: prototyped, working, measured, and passing the full suite.** The
prototype lives at `subopt.py` (a pytest plugin that applies both halves by
monkeypatch). No `src/` changes.

**The number: vyx +7.1%, clone entries 5,394 → 3,727 (−31%).** Every other
grammar is unchanged, and the runtime half costs nothing where there is nothing
to gain (measured, §4).

---

## 1 — The defect

`flatten_clones` (`compiler/lower.py`) runs `optimize_program` over the shell
set, and only **afterwards** builds the attempt entries:

```python
optimize_program(list(shells.values()))     # the five specialisation passes
for key, spec in clones.items():            # ← AFTER
    if spec.attempt_follow is not None:
        clone.attempt = (spec.attempt_follow, _attempt_entries(clone, ...))
```

`_attempt_entries` creates one single-arm **sub-clone** per entry. Those
sub-clones are born after the passes and are not in the set, so
`_convert_dispatch` never sees them — even though every one is `BUILD_ALT` with
a single exactly-once ref, the exact shape dispatch conversion exists to make
frame-less.

31 such sub-clones exist in the compiled vyx program, and they take **1,396 of
5,394 clone entries per parse (25.9%)**: `kv-pair` 452, `value` 444,
`body-line` 330, `scope-item` 144, `bare-val` 26.

## 2 — The change (two parts; both are required)

**Part 1 — compile.** Run `_convert_dispatch` over each sub-clone where
`_attempt_entries` creates it. `_unit_ref_target` must widen from `OP_REF` to
`kind in (OP_REF, OP_REF1)`: a sub-clone shares its parent's arm, which
`_specialize_calls` has already rewritten. `OP_REF1` is the same fact — an
exactly-once reference with a `FlatClone` payload — and the widening is a no-op
in the main pass, where nothing is `OP_REF1` yet.

**Part 2 — runtime.** `PdaKernel._enter` must re-check the specialisations after
it substitutes a clone. Today its head is three straight-line tests:

```python
if clone.mode == BUILD_DISPATCH:  clone = self._chase_dispatch(clone, char)
if clone.attempt is not None:     ...; clone = sole      # ← installs a NEW clone
for chars, negated, candidate in clone.selectors:        # ← generic arm path
```

The attempt substitution installs a clone that never passes the dispatch test
above it, so a converted sub-clone falls through to the generic loop and a
`FlatClone` lands where a `FlatArm` is expected. **Part 1 alone crashes the
runtime** — that is not a risk, it is measured, twice.

The fix is to make the head a loop — chase, substitute, re-check — which also
removes the current situation where exactly one ordering works and nothing says
so:

```python
while True:
    if clone.mode == BUILD_DISPATCH:
        chased = self._chase_dispatch(clone, char)
        if chased is None: return False
        clone = chased; continue
    if clone.attempt is not None:
        sole = sole_admitted(clone.attempt[1], self.text, self.pos)
        if sole is None: self.attempt(clone, out); return False
        clone = sole; continue
    break
```

It terminates: a dispatch chase yields a concrete rule clone, and an attempt
substitution yields a sub-clone whose own `attempt` is `None`.

## 3 — Correctness evidence

- **Full suite under the prototype: 3,801 passed, 8 skipped** — including the
  parity differentials, which are the gate for anything changing what the PDA
  commits to.
- **Models are structurally identical** on every benchmark grammar
  (`arithmetic`, `csv`, `json`, `gbnf-meta`, `abnf-meta`, `vyx`), compared by
  class name and content rather than by identity — the two compilations produce
  distinct class objects, so `==` is a false negative and was one on the first
  run.
- Round-trip holds on every grammar measured.

## 4 — Performance evidence

Per-grammar A/B, one process, min-of-11:

| grammar | chars | base µs/char | opt µs/char | Δ | entries |
|---|---|---|---|---|---|
| **vyx** | 3,461 | 5.118 | **4.756** | **+7.1%** | 5,394 → 3,727 |
| arithmetic | 4,000 | 3.244 | 3.156 | +2.7% | unchanged |
| csv | 12,539 | 0.872 | 0.870 | +0.2% | unchanged |
| json | 2,403 | 1.977 | 2.030 | −2.7% | unchanged |
| gbnf-meta | 1,377 | 5.043 | 5.050 | −0.1% | unchanged |
| abnf-meta | 2,020 | 5.728 | 5.823 | −1.7% | unchanged |

Only vyx has attempt sub-clones, so only vyx changes entry count — and the
±2.7% scatter on the others is noise, not part 2's overhead. **Isolated by
interleaved A/B**, toggling only `_enter` between rounds on one compiled
artefact:

```
json       orig 1.954  looped 1.960   −0.3%
abnf-meta  orig 5.875  looped 5.866   +0.2%
vyx        orig 4.770  looped 4.785   −0.3%
```

**The loop is free.** The risk that part 2 taxes every entry to help a quarter
of them is measured and does not exist.

## 5 — Scope, honestly

**This helps grammars with attempt sub-clones and no others.** vyx is the only
one in the corpus, and it is the product grammar — but a reviewer should read
+7.1% as "on vyx", not as an engine-wide gain.

It is also smaller than the entry cut suggests: a 31% cut in entries bought
7.1%. That corrects `OPTIMIZATION.md` §4's calibration, which put the floor for
an entry cut at 16% — that figure came from a grammar-side rewrite that moved
entries, models and `_run_leaf` together, and it over-predicts a change that
removes only a frame push and a completion.

## 6 — Not proposed: the `OP_VSTR` gap

`_inline_value_strs` runs before `_convert_dispatch` and rewrites a
terminal-only ref to `OP_VSTR`, which `_unit_ref_target` does not recognise — so
5 clones lose the dispatch conversion because they won an inlining. That is the
same pass-ordering hazard `optimize_program` documents for `OP_REF1` and does
not guard for `OP_VSTR`.

**I have not prototyped this and it is not part of the proposal.** It is worth
~52 entries per parse (1%), `OP_VSTR`'s runtime semantics differ from `OP_REF`'s
(it runs the value_str loop inline rather than descending), and whether dispatch
can chase it is unestablished. Recorded as a lead, not a recommendation.

## 7 — How to land it

1. Apply part 2 first, alone, and run the suite — it is a pure refactor of
   `_enter`'s head and should be a no-op (the interleaved A/B says it costs
   nothing).
2. Then part 1, with the `_unit_ref_target` widening.
3. Gate: `tools/run_checks.sh` exit 0, full suite, and the parity differentials
   specifically. Re-run `bench --only vyx` and the per-grammar table above.
4. `subopt.py` is the working prototype — the two patched functions in it are
   the intended shapes, and can be read as the diff.
