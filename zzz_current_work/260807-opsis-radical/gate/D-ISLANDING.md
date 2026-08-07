# Solution D, second half — island the fork instead of failing whole-document

**Status:** designed, not implemented. The feasibility read is done and the
soundness argument is closed — which turned out to be the actual work. The
kernel splice is the remaining step and wants to land as one reviewed change.

Prize, measured (`FINDING.md` §12): the nine surviving ProbeForks are all
vyx.gbnf-as-instance-grammar, and the fallback there is a flat **×7–8, linear**.
Bounded, not urgent — read this design with that number in hand.

## 1. What I expected to find, and what is actually there

The review called this half "constitutional" (escapes are islands) and I
assumed it was mostly wiring: the island machinery exists, so catch the fork and
call it. That assumption was wrong in an interesting way, and then right for a
better reason.

**Wrong:** islanding at a runtime fork is not obviously sound. A compile-time
island is chosen because the analysis proved the rule's *interior* is conflicted
while its *boundary* is decidable. A ProbeFork is the opposite — the
undecidability IS the boundary. Splicing "the longest completion" there is
exactly the silent pick this repo refuses ("a span whose derivations build two
different models raises rather than one engine quietly picking").

**Right:** `island_parse` already carries the guard that closes the gap —
`policy.follow` (`runtime/islands.py:187`):

```python
if policy.follow is not None:
    for alt in start_completion_ends(kern):
        if alt < end and policy.follow.has(text[pos + alt]):
            raise PdaFail(f"island {name!r} at {pos}: arm choice spans two ends …")
```

A second completion end whose next character the continuation accepts is a
cross-span arm choice the seam refuses to settle — it bails, and the gated
engine's whole-input view owns the question. So an island splice is sound
**exactly when it is handed a correct continuation set**, and the compile-time
path's own note says what "correct" may be: `PdaTables.island_follow` is
rule-level, unioned over reference sites, and therefore *⊇ any one site's
continuation* — "an error can only be a spurious bail, never a wrong commit."

That property is what makes this change safe by construction. **Every uncertain
outcome degrades to today's behaviour.** The change can cost a wasted island
attempt; it cannot commit anything Earley would have refused.

## 2. The mechanism

On `ProbeFork`, instead of unwinding to the whole-document fallback:

1. **Climb** the live stack to the innermost frame whose `F_CLONE` is a *named
   rule* (not a synthetic group/arm clone).
2. **Roll back** to that frame's `F_START` — the primitive exists and is already
   trusted: `_attempt_run` (`kernel/decisions.py:384-400`) runs sub-runs on top
   of the live stack behind a `floor` watermark and unwinds with
   `del self.stack[floor:]` / `self.pos = saved_pos`.
3. **Island that rule** from `F_START` via the existing `_island(name, sink)`,
   with `policy.for_island(follow=<that rule's FOLLOW>)`.
4. **On any island refusal** (`PdaFail` — no completion, ambiguous ends, refusing
   fold) re-raise the original `ProbeFork`, and the whole-document fallback runs
   exactly as it does today.

Where the parse resumes: the island's model splices into the *parent* frame's
sink and the driver continues at the parent's item — the same splice
`_island` already performs for a compile-time island reference, one frame up.

## 3. The one thing that has to be built

`PdaTables` retains FOLLOW **only for declared islands**:

```python
self.island_follow = {name: follow[name] for name in compiler.islands}
```

A runtime island needs it for whichever rule the climb lands on, so this becomes
a full `rule_follow: dict[str, CharSet]` (the analysis already computes it for
every rule — `compiler.analysis.follow`). Additive, no behaviour change on its
own, independently testable. `island_follow` stays as the island-set view, or
becomes a derived read.

## 4. Risks, in the order they should be checked

- **The climb target.** Landing on a transparent/synthetic clone would island a
  rule the grammar does not name and whose FOLLOW is not in the table. Skip to
  the nearest named ancestor; if the stack has none (the fork is inside the
  start rule's own top frame), there is nothing to island — fall back as today.
- **`PROBE_DEPTH` forks are different.** `admission.py`'s depth cap raises
  ProbeFork as an over-approximation ("the cap only ever costs a fallback").
  Those are not boundary questions and islanding them buys nothing; they should
  keep falling back.
- **Reduce path parity.** `reduce_runtime.py` is the b1 twin. Either the change
  covers both completions or it is explicitly model-only, stated.
- **Cost.** A failed island attempt is pure loss on top of a fallback the run was
  going to pay anyway. With the prize at ×8, an island that bails often could
  make things *slower*. This needs the `forkcount.py` instrument re-run to count
  island-attempted vs island-succeeded before the change is called a win.

## 5. Gate

`tools/run_checks.sh` exit 0 · full suite · **the parity differentials are the
real gate here** (`tests/integration/lexic/parity/`) — this changes what the PDA
commits to, so raw model equality against Earley is the invariant that matters ·
`forkcount.py` before/after, to show forks that now island rather than fall back
· `probes/scaling.py` before/after, to show the ×8 actually collapsing.

If scaling does not move, the honest outcome is to revert: the design is sound
but the prize was never large, and a correct mechanism that does not pay is
still not worth carrying.

---

## 6. The hit rate, predicted — `probes/island_trial.py`

The risk that decides this design (§4, last bullet) is now measured, without a
single `src/` change: a `PdaKernel` subclass catches each fork while the live
stack is intact, runs exactly the trial §2 prescribes — climb to the innermost
fold-bearing frame, island that rule from its `F_START` with the rule's analysis
FOLLOW as the guard — and re-raises, so the parse behaves as it does today.

```
   3  island SETTLES          fork@2 → island 'pipe-list-item3'@1: settles, 5 chars
   2  island BAILS            fork@12 → island 'dict-entry'@10: BAIL
                              "arm choice spans two ends (3, 4) and the shorter could compose"
```

**Three of five settle, and the split is by construct, not by luck:**

- **pipe-lists island cleanly** (`pipe-list`, `pipe-list-item3`) — their fork is
  a loop boundary the enclosing rule's extent settles.
- **dict-defs always bail**, and through the *right* door: `dict-entry` has two
  completion ends and the shorter one composes, so `policy.follow` refuses. That
  is a genuine cross-span arm choice, not a defect — the guard doing its job.

So the mechanism works and is sound on live subjects. The remaining question is
purely economic, and it is a real one: **a bail pays the island attempt AND the
fallback.** For dict-defs this change is strictly slower. Whether it nets out
depends on the island window (≤256 chars) against the whole-document fallback —
favourable on large packets, unfavourable on the short lines the corpus has.

Two caveats on the sample, stated because they bound the conclusion: eight forks
from one grammar on inputs of tens of characters. A `dict-entry`-heavy packet is
the adversarial case and nothing in the corpus exercises it at size.

## 7. Remaining work, in order

1. `PdaTables.rule_follow` — FOLLOW for every rule, not just declared islands
   (§3). Additive, independently testable.
2. **Clone → rule name.** `flatten_program` discards `flatten_clones`'s
   `dict[CloneKey, FlatClone]`, and neither `FlatClone` nor `RuleFold` carries a
   name — the trial probe had to recover it through
   `compute_binding` (class name → rule name), which the kernel cannot do.
   Either give `FlatClone` a `name` slot or retain the shells map on
   `PdaProgram`.
3. The kernel climb + rollback + splice (§2), model path first, reduce path
   stated either way.
4. Re-run `forkcount.py`, `island_trial.py` and `probes/scaling.py` before/after.
   **If `scaling.py` does not move, revert** — §5 stands.

---

## 8. Review — the opsis-radical session's take

Endorsed, and §1 is the best paragraph in the gate folder: the trap ("it's
constitutional, just wire it") named, the reason islanding a *runtime* fork is
not obviously sound stated exactly, and the escape found in machinery that
already exists — sound-by-construction because every uncertain outcome
degrades to today's behaviour and the union-FOLLOW guard can only bail
spuriously, never commit wrongly. The §6 trial (hit rate measured live,
without touching src, split by construct with dict-defs bailing through the
RIGHT door) is the premise-check discipline at its best. Four notes:

1. **Make the interior-ambiguity refusal explicit.** The follow-guard covers
   cross-span END choices; equal-extent, different-meaning derivations inside
   the island must be refused by the island's own engine run (they should be
   already — it is the same `island_parse` compile-time islands pass parity
   with today). One sentence in §1 saying so closes the soundness argument
   completely instead of implicitly.
2. **Prefer the `FlatClone.name` slot over retaining the shells map.** The
   trial recovering names through `compute_binding` is a layering smell the
   kernel must not inherit (runtime reaching into compile's binding); a name
   on the flat record is honest provenance, and it rhymes with the standing
   readout ask (engine artifacts should carry their names — the `__rep_N`
   finding's moral). Cost to state in the plan: `specs.py` is a pinned test
   vocabulary, so the slot moves pinned specs.
3. **Run the economics BEFORE the kernel splice.** §6's own caveat is the
   decider: nothing in the corpus exercises dict-heavy packets at size. The
   pieces exist to settle it pre-implementation: `lexic.generate` walks a
   canonical grammar — generate large vyx packets (pipe-list-heavy and
   dict-heavy variants), run them through the §6 trial subclass, and price
   attempt+fallback against fallback-alone at real sizes. That moves the §5
   kill-criterion ("if scaling does not move, revert") from post- to
   pre-implementation, which is cheaper for everyone. Worth stating too:
   vyx-as-instance is not a corner — it is the product grammar; packets at
   production size are the actual workload, so the answer matters even
   though the constant is bounded.
4. **Priority.** With option A landed and the constant flat, this ranks
   behind nothing on correctness grounds and behind the measurement in note
   3 on economics grounds. Model path first, the b1 reduce twin stated
   either way, parity differentials as the true gate — §5 as written.
