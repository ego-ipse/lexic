# gate — suggested order of work

Everything in this folder started as one question ("why does the PDA fork one
char into the first rulename?") and turned into four findings, one landed fix,
and a stack of candidates. This is the ordering argument over what remains.

Written 2026-08-07. Read `FINDING.md` for the investigation, `D-ISLANDING.md`
for the islanding design, `PROBE-QUADRATIC.md` for the biggest open item.

## Where things stand

**Landed and green:** `relax_non_semantic` narrowed to nullable noise rules
(`FINDING.md` §11). All ten ground-truth grammars read by the metagrammar ride
the PDA with no resolver; vyx 4.451 s → 0.029 s. Suite 3776 passed, run_checks
exit 0, parity + property 141 passed.

**Open, ranked below:** the PDA's n² on pipe-heavy vyx packets; solution D's two
halves; the provenance/readout asks; two deferred cleanliness items.

**Nothing else in `src/` has been touched since the relaxation fix.**

## The order

### 1 — Scope the quadratic (cheap, first)

Two measurements before committing to the fix, both with instruments that
already exist in this folder:

- **How general is it?** Run the probe-counter over the whole corpus, not just
  vyx. Is n² general to any repeated attempt-gated construct, or vyx-shaped?
  This sizes the prize and decides whether item 2 is a lexic priority or a vyx
  footnote.
- **Is `STOP_FORCED` reachable?** It occurs **zero** times in 3,829 verdicts
  (`verdictcensus.py`), and its only known subject — gbnf-meta's terminator
  theft — stopped forking when the relaxation fix landed. If it is genuinely
  unreachable the stop-probe goes and the problem halves *before* anyone
  optimises it. This wants a grammar-level argument, not a suite count: "never
  observed" is not "cannot happen", and this is a soundness check.

### 2 — Lockstep convergence in `_fork_verdict`

The linear fix (`PROBE-QUADRATIC.md`, last section). The biggest prize on the
table: unbounded n², on the product grammar's own common syntax, on the path
that already *succeeds* — 73 s for an 11 KB packet, 92% of it inside `_probe`.

Land it behind the step-budget escape so the worst case is exactly today's
behaviour and today's answer; correctness then cannot regress, only the budget's
tuning is at stake. Gate on the parity differentials — this changes what the PDA
commits to.

### 3 — Re-measure

`probes/scaling.py`, `probes/economics.py`, and
`tools.benchmark.bench --only gbnf-meta`. The same three that would have caught
this earlier. Item 6's go/no-go depends on the numbers this produces.

### 4 — `FlatClone.name` slot

Cheap, additive, two masters: D's prerequisite (`D-ISLANDING.md` §7.2) *and* the
standing readout ask — engine artifacts should carry their names. Costs churn in
`specs.py`'s pinned vocabulary; that is a cost, not an objection.

### 5 — Refusal position on the record

The effort's own standing lexic ask. `PdaFail` spells its position in prose
("no arm at N") and the public surface discards even that, so atlas regex-reads
the kernel's words — honest but fragile, and load-bearing for the instrument. A
readout-shaped, additive surface fixes it, and rung 2's engine clocks will want
the same seam.

### 6 — Solution D, second half (islanding), if it still pays

Sound, with affordable economics (0.1% of the parse at size, even when it
bails), but the subject narrowed to dict-defs-inside-packets and the prize is a
bounded ×7–8. Do it after the quadratic, and only if item 3 still shows it
paying. `D-ISLANDING.md` §5's revert condition stands: **if `scaling.py` does not
move, revert.**

### Deferred, with reasons

- **D's first half (per-site attempt licences).** Needs its own measurement of
  the clone-identity trade — per-tail clones cost 60% of sub-runs on the vyx
  corpus, and reversing that on the common path to help the rare one is a
  gamble until someone prices it.
- **`nullable_names` → `ir/grammar/`.** Pure cleanliness (grammar nullability is
  a property of an `IrAst`, not of an engine). No forcing function.

## Two calls that are not mine

**The effort split.** Items 1–3 and 6, plus both deferred items, are lexic
engine work this ergonomics effort happened to surface. They want their own
directory and their own gate. opsis-radical should not absorb them silently —
that is how a plan stops describing what is being built.

**Whether atlas rung 2 preempts all of it.** The two engine clocks are this
effort's actual live line, and items 4–5 are partly in service of it. If the
goal is the instrument rather than the engine, the order becomes **4 → 5 → rung
2**, and the quadratic parks as a filed, reproducible finding.

The case for the engine first: 73 seconds on an 11 KB packet is a real workload
failing on the product grammar. The case against: it is pre-existing, it is not
a regression, and nothing currently in the corpus trips it at painful size.

## The instruments, so none of this is re-derived

| what | answers |
|---|---|
| `variants.py` + `relaxoff.py` / `relaxold.py` | relaxation A/B; `unconditional` reproduces the pre-fix bug |
| `forkcount.py` | every `PdaFail` / `ProbeFork` by raise site, suite-wide |
| `verdictcensus.py` | boundary class → verdict matrix (killed the cheap shortcut) |
| `probes/repro.py` | the ten-char repro + the charset prediction |
| `probes/gate_dump.py` | every attempt gate in a grammar, both charsets |
| `probes/shapes.py` | what the relaxation pass rewrites |
| `probes/corpus.py` | route, timing, resolver, round-trip over all ten grammars |
| `probes/cost.py` | the fix's cost — language table + clone counts |
| `probes/scaling.py` | the fallback's cost as a packet grows |
| `probes/island_trial.py` | would an island settle each fork? (hit rate) |
| `probes/economics.py` | island attempt vs fallback, at production sizes |
| `run_all.sh` | every probe × every variant, then the suite |

A/B against pre-fix behaviour anywhere: put `variants.apply("unconditional")` in
a `sitecustomize.py` on `PYTHONPATH` so it lands before anything imports lexic —
that is how the benchmark row was checked for a regression (5.508 → 5.471
µs/char, inside the bench's own 2.80% noise floor; there was none).

---

## Review — the opsis-radical session's take

The plan is right-shaped and the quadratic work behind it is the folder's
standard: cause counted (92% inside `_probe`, linear probes × linear cost),
non-regression A/B'd through `sitecustomize`, and — best of all — the cheap
shortcut MEASURED DEAD with four counterexamples before anyone shipped it.
Also noted: my D-economics worry (bail cost) did not survive contact with
real sizes (0.1%), and D's subject narrowed again; demoting it is correct.
Endorsed, with five notes:

1. **The lockstep's load-bearing soundness piece is the convergence
   predicate, and the step-budget escape does not protect it.** Escape (3)
   makes the *not-converged* path exactly today's behaviour — but a
   too-coarse stack signature declaring FALSE convergence would commit what
   the engine refuses, and no budget catches that. The signature should be
   born conservative and only cheapened under the parity gate, and the
   convergence test deserves its own adversarial fixtures (identical
   (pos, shallow-signature) with divergent pending values). Same for the
   "values accumulated before convergence" equivalence — that is a proof
   obligation, not a refactor.
2. **STOP_FORCED**: agreed it wants a grammar-level argument, and if the
   argument closes and the probe goes, keep `verdictcensus.py` as the
   standing tripwire. If the argument cannot be closed, keep the probe —
   it costs a constant, and constants are cheap insurance on soundness.
3. **Item 1's probe-counter should sweep GENERATED packets at size**, not
   only the corpus — the corpus never trips this at painful scale, which is
   exactly how it survived until now (economics.py already does this;
   make it explicit for the counter).
4. **Items 4–5 first, regardless of the split.** Both are small, additive,
   and double-mastered (D's prerequisite + the readout ask; the refusal
   position + rung 2's clocks). For 5, the two-step shape: structured
   attributes on the failure records NOW (`pos` — atlas drops its
   regex-over-prose the same day), the fuller readout record with
   expected-next when the clocks want it.
5. **On the two calls reserved for the user, my recommendation:** split the
   engine work into its own effort directory with its own gate and
   handover (this folder has outgrown "gate"); order 4 → 5 → 1 (cheap,
   parallel to instrument work) → then decide 2 vs rung-2-clocks on item
   1's generality numbers and one question only the user can answer:
   whether real vyx workloads reach 11 KB pipe-heavy packets soon. If yes,
   the quadratic outranks everything else in this folder. Note the repo's
   standing convention: isolation here is an effort directory or a branch,
   not a worktree.
