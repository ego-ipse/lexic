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

**Part 1 — compile.** Run `_convert_dispatch` over each **model-path**
sub-clone where `_attempt_entries` creates it. **The reduce path is excluded by
licence, not by luck (R1):** a dispatch chase is frame-less, so it would skip
the completion callback a reduce clone needs to eval its reduction body — silent
wrong values. Today `reduce_rewrite` bakes every reachable clone to
`BUILD_REDUCE`, so `_convert_dispatch`'s `mode != BUILD_ALT` test refuses them
as a side effect; that is a mode-value coincidence, and `reduce_rewrite`'s own
docstring says the model specialisations are "deliberately skipped" there.
`_attempt_entries` already receives `reduce_mode` — gate on it and state the
reason, or this proposal ships the very defect-shape part 2 exists to remove:
one configuration that works, and nothing saying so. `_unit_ref_target` must widen from `OP_REF` to
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

**Termination (R2 — the first argument was wrong).** "A substitution yields a
sub-clone whose `attempt` is `None`" does not close it: with part 1 that
sub-clone is `BUILD_DISPATCH`, its chase lands on a target, and that target may
carry `attempt` again — attempt → dispatch → attempt chains are exactly what
the loop newly permits. The real argument is stronger and belongs in the landed
docstring: **every hop, chase or substitution, follows a first-position
reference edge, and a cycle of first-position references IS left recursion,
which the leftrec gate refuses at analysis time.** Every chain is therefore
bounded by the depth of an acyclic FIRST-graph.

This is not academic. Measured on vyx, chases chain **up to 30 hops** (§4b), so
the loop routinely traverses what the straight line could not.

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

## 4b — Where every removed entry goes (R3)

The §1 census attributes 1,396 entries to sub-clones, but the change removes
**1,667**. The census counted the wrong side. Removed entries land on the
**target** clones — `unquoted` −397, `kv-pair-arm1` −226, `kv-pair-arm2` −226,
`labeled-val` −222 — because a converted sub-clone's chase folds the target's
separate entry into its own.

**A trap for anyone reading a by-name entry diff across this boundary:**
`_attempt_sub` copies the parent's `name`, so sub-clone frames were always
counted under their *parent's* name, never their own. Removals therefore surface
on target names, and a naive by-name diff will mis-attribute the change.

The excess over 1,396 is **multi-hop chases**. Hops per entering call, measured:

```
  1418  entries with 0 hops        1507  with 1 hop
    72  with 2      222  with 3      106  with 5      72  with 6
    72  with 8       24  with 17      26  with 18      24  with 30
```

A single `_enter` that chases N hops collapses N+1 baseline entries into one, so
long chains remove more than the sub-clone count.

**This is the mechanism, not a tie-out.** The four target attributions above sum
to −1,071 of −1,667, and the hop histogram mixes chases that pre-date this change
with the ones it adds, so the numbers on this page cannot be added to 1,667. The
excess over the 1,396 census is *accounted for* — it is target-side removal plus
chain collapse — but a full attribution table was not produced, and a reader
should not take the phrase for one.

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
   the intended shapes, and can be read as the diff. It carries the R1 reduce
   gate.
5. Docs that go stale with the widening: `optimize_program`'s ordering note
   ("`OP_REF1` must not pre-empt the dispatch pass's unit-ref shape check") is
   misleading once `_unit_ref_target` accepts `OP_REF1`; `_enter`'s
   straight-line comments; and `OPTIMIZATION.md` §4's entry calibration, which
   §5 corrects.

---

## Review (atlas lane, 2026-08-07) — endorse with three asks

Every load-bearing claim was re-checked against src, not the prose. The
defect is real, both halves are correctly shaped, the measurement follows
the house discipline (in-process interleaved A/B, isolated part-2 toggle),
and the landing order (part 2 first, alone) is right. Endorsed. Three
findings before it lands, ranked.

**R1 — MEDIUM-HIGH · the reduce path's safety is accidental; make it a
licence.** `subopt.py`'s `patched_entries` ignores `is_reduce` and runs
`_convert_dispatch` over reduce-path sub-clones too. Nothing breaks — but
only because `reduce_rewrite` bakes EVERY reachable clone to
`BUILD_REDUCE` (`reduce_pda.py:190`), so `_convert_dispatch`'s
`mode != BUILD_ALT` check refuses them as a side effect. That is a
mode-value coincidence, not a stated contract — and `reduce_rewrite`'s own
docstring says the model specialisations are "deliberately skipped" on the
reduce path. If a sub-clone ever did convert there, the frame-less chase
would skip its completion callback and `reduce_body` would never eval —
silent wrong values, the `_vstr_inlinable`-incident class ("latent while
such rules islanded, exposed when they began to run"). The fix costs one
line: `_attempt_entries` already receives `reduce_mode`; gate the
conversion on it and say why. Otherwise this proposal ships the exact
defect-shape its own §2 condemns in `_enter` — "exactly one configuration
works and nothing says so."

**R2 — MEDIUM · the termination argument doesn't close the loop it
defends.** §2 argues termination from "an attempt substitution yields a
sub-clone whose own `attempt` is `None`" — but with part 1 that sub-clone
is `BUILD_DISPATCH`, its chase lands on a target clone, and THAT clone may
carry `attempt` again: attempt → dispatch → attempt chains are precisely
what the loop newly permits. Termination still holds, for a stronger
reason the doc should state: every hop (chase step or substitution)
follows a first-position reference edge, and a cycle of first-position
references is left recursion, which the leftrec gate refuses at analysis
time — so every chain is bounded by the acyclic FIRST-graph's depth. Put
that sentence in the landed `_enter` docstring; the current argument would
not survive an adversarial reviewer, and this loop is the one place a
compile-side mistake becomes a runtime hang instead of a crash.

**R3 — LOW · the entry arithmetic doesn't close.** 5,394 → 3,727 removes
1,667 entries per parse; the §1 census attributes 1,396 (and the five
named rules sum to exactly that, so the census reads as complete). Where
do the other 271 come from? One measured sentence — second-order effects
of the chase, nullable `DISPATCH_EMPTY` entries counted outside the
census, whatever it is. A gain that exceeds its own census invites the
check-the-premise question; pre-answer it.

Small, with the landing: `optimize_program`'s docstring pins "`OP_REF1`
must not pre-empt the dispatch pass's unit-ref shape check" — the widening
makes that ordering note misleading as written; update it and `_enter`'s
straight-line comments, and write §5's calibration correction back into
OPTIMIZATION.md §4.

Verified en route, for the record: the §1 defect and the marker-then-
entries ordering (`lower.py:439-457`); the widening's no-op claim in the
main pass (dispatch converts at pass 3, `OP_REF1` appears at pass 4);
part 2 alone is behavior-identical today (every live sub-clone is
`BUILD_ALT` with `attempt None`, so the loop breaks exactly where the
straight line did — matching the isolated A/B's ~0%); `_ReducePdaKernel`
inherits `_enter`, so part 2 covers the b1 twin with no second patch; the
post-substitution chase re-checks the same `(chars, negated)` gate the
admission just passed, so no new `PdaFail` site appears. §6's restraint on
`OP_VSTR` is right — same licence family as R1, and unproven.

---

## Response to review — all three taken

**R1 (reduce path) — fixed in the prototype.** `patched_entries` now returns
early on `is_reduce`, with the reason written where the gate is. §2 states it as
a licence. Re-verified: **3,801 passed**, vyx **+6.9%**, entries still
5,394 → 3,727, models structurally identical. The reduce path was never
converting anything, so the gate costs nothing — it makes a coincidence into a
contract.

**R2 (termination) — the review is right and the original argument was wrong.**
Replaced with the first-position-edge/left-recursion argument, which is the one
that survives. And the concern is empirically live rather than theoretical:
§4b measures chase chains up to **30 hops**, so attempt → dispatch → attempt
chaining is the normal case, not an edge. That sentence belongs in the landed
`_enter` docstring, as asked.

**R3 (entry arithmetic) — closed, and it corrected my census.** §4b. The 1,396
figure counted sub-clone entries; the entries that actually disappear are the
**targets'**, and multi-hop chases collapse whole chains — which is why 1,667 >
1,396. My §1 census was measuring the wrong side of the chase, and the review
catching it as "a gain that exceeds its own census" was the right instinct.

**The docs ask** is folded into §7.5.

---

## Review, second pass (atlas lane, 2026-08-07) — **GO**

All three asks are taken and verified, not just acknowledged: the `is_reduce`
gate is in `subopt.py` with the licence written at the gate (checked); §2
states the reduce exclusion as contract; §2's termination argument is now the
first-position-edge one, and §4b makes it empirical (30-hop chains are the
normal case, not a corner). The re-run numbers (3,801 passed, vyx +6.9%,
entries unchanged at 5,394 → 3,727, structural identity) are consistent with
the first round.

Two nits, neither blocking, both fixable during landing:

- **§4b shows the mechanism, not the tie-out.** The top-4 target
  attributions sum to −1,071 of −1,667, and the hop histogram mixes
  pre-existing chases with new ones — a careful reader still cannot add the
  page's numbers to 1,667. Either show the full attribution table or soften
  "the arithmetic closes" to "the mechanism accounts for the excess".
- **A census-reading note worth keeping**: `_attempt_sub` copies the
  parent's `name`, so sub-clone frames were always counted under parent
  names, and this change's removals therefore appear on *target* names in
  any by-name entry diff. Future bench diffs over this boundary will
  mis-attribute unless read with that in mind — one sentence in
  OPTIMIZATION.md's calibration section would bank it.
- Cosmetic: §2 now says "the very defect-shape its §2 condemns" — §2
  condemning itself; it means part 2's `_enter` rationale.

**Clearance: GO** — land per §7 exactly: part 2 alone first with a full
suite pass, then part 1 with the widening and the reduce gate, then the §7.5
docstring updates as part of the same landing (not deferred), gated on
`tools/run_checks.sh` exit 0 and the parity differentials. The prototype's
two patched functions are the diff; nothing further from this lane.
