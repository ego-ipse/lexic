# Plan review — target-shaped parsing

**Reviewed:** 2026-08-27, against `context.md`, `goal.md`, `DESIGN.md`,
`TODO.md`, `LEDGER.md`, `TBD_after.md` and the source tree at branch `targeter`
/ `0faa7289`.

**Verdict:** the architecture is sound and no finding is architectural. The
design correctly identifies the double-representation cost, refuses the two
directions already nuked (direct-carrier, post-parse demand projection), and
gates the one genuinely uncertain claim — typed `Carry` through flat int-coded
tables — behind a prototype in §1. Proof obligations 1–16 are real obligations.

The two surface findings below were subsequently addressed by the executable
prototype and revised design; `REVIEW_2.md` will judge those resolutions and
the newly exposed expression-program requirement before implementation starts.

---

## Resolved by the user's ruling (2026-08-27)

These were findings; they are now closed. Recorded so they are not re-raised.

1. **Checkpoint commits are licensed.** Commits happen at checkpoints under no
   obligation of full green, and squash into `main`. §4 (generated-model
   parsing recast onto the common ABI, existing behavior preserved) is the
   natural first checkpoint. The earlier concern — one commit across ~6k
   rewritten lines with no landable intermediate — is closed.
2. **Work branch exists:** `targeter`, from `0faa7289`.
3. **`proto/` and `reports/` exist.**
4. **No transitional shims, ever.** Under no circumstances does an end user need
   both routes; legacy is not a concern. This is a hard constraint on every
   item below, and it overrides any review suggestion that would create a
   second live production route.

---

## Review items

### 1 — Pull the reduction differential forward into §5; leave §10 where it is

**Severity:** high · **Owner:** coordinator, before Terra reaches §5

**Status:** CLOSED — incorporated into `TODO.md` §5.

**The problem this replaces.** An earlier reading of the plan suggested moving
the §10 deletions after §13, so Luna's adversarial/transactional/tokenizer
tests would have a live `ReduceFold` oracle. That is wrong and must not be
done: it would leave `_ReduceEntry` / `_reduce_entry` live in
`compile/artifact.py` for thirteen phases, so `CompiledGrammar.reduce` would
carry two production routes behind one public seam — precisely the
transitional dual-support that is forbidden.

**The real variable** is not when `ReduceFold` is deleted, but when its last
caller disappears.

**Action.** Make §5's currently parenthetical "during development only"
differential the phase's actual exit gate, executed by Terra before §6 opens:

- property differentials, ground-truth formulations across native/GBNF/ABNF/EBNF,
  refusal type *and* message parity, poisoned runs, epsilon, `DROP`, `YIELD`,
  contribution order, and ambiguity;
- capture frozen goldens for the fixed corpora while the oracle is still alive;
- record the run in `reports/`.

After that gate `ReduceFold` has no caller, and §10 deletes it on schedule.

**The line that keeps this shim-free.** At the moment §5 exits,
`compiled.reduce()` routes to exactly one product. The oracle survives only as
a function tests import directly — no flag, no `into="legacy"`, no fallback
branch, no adapter translating between representations. If anything needs to
*bridge* the two representations, that is the failure mode; stop the phase and
report it.

**Accepted residual cost.** Hypothesis differentials generate fresh inputs per
run, so frozen goldens do not cover them; after §10 that class of comparison is
gone permanently. Spend it deliberately — make §5's property run wide enough
that its coverage is the coverage you intend to keep. Run it under
`tools/guarded.sh`; never raise a committed `max_examples`.

---

### 2 — Add a measurement checkpoint at the §4 exit

**Severity:** high · **Owner:** coordinator

**Status:** CLOSED — incorporated into the `TODO.md` §4 exit gate.

**Evidence.** §4's exit asserts "no material hot-loop expansion." Terra's only
available tool is the static opcode-stream diff §4 already prescribes — a good
idea, but not a measurement. Instrumentation never touches `src`, and profiling
is the coordinator's job at §12, six phases later. A paid-loop regression
introduced by the ABI shape in §4 would not surface until §5–§11 are built on
top of it.

**Action.** Profile at the §4 checkpoint, generated-model product only:
alternating baseline/new processes, byte-identical control row, per
`docs/STYLE.md`. This is the cheapest point at which the ABI shape can still be
reshaped. Measuring before is already agreed; this pins where.

---

### 3 — Name the final templating surface before Terra starts

**Severity:** high · **Owner:** coordinator, into `DESIGN.md`

**Status:** ADDRESSED FOR REVIEW — `select(spec)` returns the real
`ReductionMorphism[Selection]`; execution is only
`CompiledGrammar.reduce(..., into=selection)`. `MapShape`, `Template`,
`Template.run`, `spanify`, and raw-surface paths are scheduled for deletion.
The exact surface is recorded in `DESIGN.md` and `reports/PROTOTYPE.md` for
review pass 2.

**Evidence.** `MapShape`, `Template`, and `spanify` are public exports of
`lexic.compile` (`src/lexic/compile/__init__.py:30-39`, re-exported at
`:109-128`), pinned by
`tests/integration/lexic/invariants/test_public_api_drift.py`, and driven by
`getting_started/ex10_templating.py`, which must exit 0 under
`tools/run_examples.sh`. §10 says only "Preserve a public templating task only
through the common product" — it does not say what that task is called, what it
takes, or which of the three exports survive. It is the plan's least-specified
deletion and it has three hard gates attached.

**The no-shims rule simplifies this.** There is nothing to preserve for
compatibility's sake. Either name the replacement surface, or name the deletion
and rewrite `ex10`. Both are legal; the ambiguity is not.

**Action.** Decide the final surface in `DESIGN.md`, then add
`getting_started/ex10_templating.py` and `test_public_api_drift.py` explicitly
to §11's checklist. `src/lexic/compile/output/transpile.py` does **not** import
templating (verified) — the transpiler code is unaffected. Its documentation is
not; see item 5.

---

### 4 — `LEDGER.md` baseline is stale

**Severity:** high (cheap) · **Owner:** coordinator

**Status:** CLOSED — `LEDGER.md` now records `targeter` / `0faa7289`; the
deleted carrier is recorded as absent.

**Evidence.** `LEDGER.md` pins "branch `performancer` at `56236f20` (`Pin split
engagement to its result`)". Actual: branch `targeter` at `0faa7289` (`Prepare
0.0.2a0 release`), one commit ahead. §0 instructs the implementer to record the
exact baseline commit — they will record something the ledger contradicts.

**Action.** Update the ledger's starting-tree paragraph to `targeter` /
`0faa7289`.

Also confirmed while checking: `src/lexic/parsing/parallel/stitch/carrier.py`
is **absent** from the tree. §0's instruction to preserve it if present is now
a no-op; nothing to preserve, nothing to delete.

---

### 5 — Two wiki pages missing from §11's documentation list

**Severity:** high · **Owner:** Terra at §11

**Status:** CLOSED — both wiki pages are now named in `TODO.md` §11.

**Evidence.** §11 lists `architecture.md`, `public-api.md`, `ir-shapes.md`,
`parallel-parsing.md`, `tokens.md`, `flavour-system.md`, `invariants.md`,
`testing.md`, `decisions.md`. It omits `.wiki/lexic/transpilation.md` and
`.wiki/lexic/codegen.md`. `public-api.md:118` grounds the transpiler in "the
templating precedent's shape: bake once, run many" — a claim item 3
invalidates. Doc-drift tests assert both directions.

**Action.** Add both pages to §11.

---

### 6 — `reduce()` needs overloads

**Severity:** medium · **Owner:** Terra at §1

**Status:** ADDRESSED FOR REVIEW — both overloads type-check against default,
beginner-selection, and real `IrTokenizer` results. They are static only;
runtime selects one cached bound product before either engine. Exact signatures
and the binding cost boundary are recorded in `DESIGN.md` and
`reports/PROTOTYPE.md` for review pass 2.

**Evidence.** Current signature:
`reduce(self, text: str, reducer: Reducer, *, cores: int = AUTO) -> IrSelf`
(`src/lexic/compile/artifact.py:311`). With
`into: ReductionMorphism[T] | None = None`, the honest signature is two
`@overload`s. Without them the return collapses to `IrSelf | T` and every
existing caller must narrow — which, under the no-`Any` / no-`object` /
no-suppression rule, means churn at every call site.

**Action.** Settle the overload shape in §1's typing prototype, alongside the
`BoundProduct[Result]` question. Record the final signature in the §1 exit
report.

---

### 7 — §1 is a feasibility gate with no failure branch

**Severity:** medium · **Owner:** coordinator

**Status:** CLOSED — `TODO.md` §1 now stops and reports without relaxing any
constraint; only an explicit user ruling can authorize a change.

**Evidence.** §1 requires proving `Carry` stays typed through PDA frames,
Earley result tables, meaning operations, worker fragments, and the bound
runner "without `Any`, `object`, casts at call sites, or an empty catch-all
protocol". Hiding an existential type parameter behind `BoundProduct[Result]`
is genuinely awkward in Python's type system. This is the hardest single claim
in the design and the plan defines no outcome if it fails.

**Action.** Before §1 starts, state which constraint relaxes first and who
rules on it. Note `src/lexic/compile/output/transpile.py:48` already imports
`cast`, so a precedent exists in `compile/` — but the plan's ban is on the new
code, and relaxing it is the user's call, not the implementer's.

---

### 8 — Plan the implementer's checkpoint cadence

**Severity:** medium · **Owner:** coordinator

**Status:** CLOSED — `TODO.md` and `LEDGER.md` define the checkpoint, warm-agent,
and usage-watch protocol.

**Evidence.** §0–§11 is twelve phases of source work plus a full documentation
pass for one implementer, with no test-authoring relief until §13.

**Action.** Adjacent increments continue the warm implementer via
`SendMessage`; a fresh spawn is for unrelated work only. Context-window length
is never a reason to hold or replace an agent (user ruling 2026-08-25). Run
`tools/usage_watch.sh` as a background task during agent-heavy stretches.

---

### 9 — Stray empty directory

**Severity:** low · **Owner:** anyone

**Status:** CLOSED — the verified-empty directory was deleted.

`zzz_current_work/260821-one-path/target-shaped-parse/` is empty and shares
this effort's name. Delete it so "check the newest plan directory when
orienting" does not hit a decoy.

---

## Verified while reviewing

- All 26 symbols the plan schedules for move or deletion exist in the tree:
  `_ReduceEntry`, `_reduce_entry`, `_variant_artifact`, `_sub_run`,
  `ReduceDerivation`, `FoldPlan`, `RunSpec`, `SubRun`, `FOLD_KINDS`,
  `FieldFold`, `FastCtor`, `RuleFold`, `ModelBody`, `ModelFold`, `fold_config`,
  `model_fold`, `derive_reduction`, `split_model`, `tokenizer_of`, `MapShape`,
  `_resolve_shape`, `spanify`, `MIN_CHUNK`, `reachable_rules`,
  `elide_subtrees`, `from_merges`.
- Every file `context.md` names exists, except `stitch/carrier.py` (absent —
  see item 4).
- All four tokenizer fixtures are present: `qwen3`, `gpt2`, `smollm2`,
  `gemma4`.
- The fork-safety regression §13 retains exists at
  `tests/integration/lexic/concurrency/test_fork_safety.py`.
- `transpile.py` does not import templating.

**Scale, for planning.** Directly rewritten: `parsing/fold.py` (679),
`compile/reduction.py` (695), `compile/output/templating.py` (638),
`pda/compiler/program/lower.py` (639), `compile/artifact.py` (579),
`compile/reduce/fold.py` (525), plus `flatten.py` (427), `build.py` (336),
`kernel/execution.py` (336), `products.py` (324), `api/json_tokenizer.py`
(433), `foldkit.py` (227), `reduce/variant.py` (66) — about 5.9k lines, inside
24.8k lines of `parsing/` and 10.4k of `compile/`, against 59k lines of tests
to port.

---

## What is right, and worth not losing

- **Phase order §3 → §4 → §5** — build the ABI, recast the *existing* model
  product onto it with existing behavior as the gate, only then add new
  products. This is the strongest idea in the plan.
- **Parallel composition last**, "so it cannot dictate a model-shaped carrier."
  The direct lesson from the nuked carrier attempt, correctly applied.
- **Per-codomain cost accounts** (`recognition + demanded decoding + final
  allocation`) with an explicit refusal to transfer the 105x extent multiplier
  to the tokenizer. That discipline is why the previous effort's numbers
  misled.
- **`foldkit` identified as shared authored vocabulary**, not disposable
  reduction machinery — with its notation and generated-self-grammar callers
  named as migration blockers.
- **§4's opcode-stream diff before/after.** Keep it even with item 2's
  measurement added; static and dynamic evidence answer different questions.

---

## Suggested order

1. Review the revised design and prototypes in `REVIEW_2.md`, concentrating on
   one-product execution, expression-versus-target lowering, paid opcode shape,
   and the two addressed public surfaces.
2. Iterate every substantive finding through the prototypes and active design.
3. Start §0 only when review pass 2 leaves no architectural or performance
   blocker.
