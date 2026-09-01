# TODO — target-shaped parsing

**Status:** substantive reviews 4 and 5 independently approve §2 and the
ABI/lifecycle work in §3. Review 6 exposed a non-composable tokenizer timing
account and index-order ambiguity; `reports/PROTOTYPE_4.md` supplies the revised
carrier, representation decision, and scenario boundaries. `reports/REVIEW_7.md`
audited feasibility arithmetic and gate placement; its rulings are folded into
this queue, `goal.md`, and `DESIGN.md`, with the supporting mechanisms measured
in `reports/PROTOTYPE_5.md` (regular-region lowering + identity, interpreted
completion-op throughput, shared-forest fold discipline, ambiguity-local
meaning folds, GC-enabled carrier budget). Source implementation has not
started.

`reports/PROTOTYPE_6.md` records the consistency iteration after that ruling:
the third reducer-free overload and exact model/extent capture types, compatible
map-shape scope, all-formulation/arity/edge regular-lowering witnesses,
root-sibling ambiguity handling, and the corrected order-balanced GC result.

`reports/REVIEW_8.md` rejects the child-local ambiguity scope, identifies the
unscheduled value-string recognizer consult, and requires an authoritative
regular proof. `reports/PROTOTYPE_7.md` supplies the correction set:
root-equivalent ancestor-cone replay, conservative possessive-boundary proof,
signature-derived JSON and non-JSON regions, in-process controlled
interpreted/capture timing, declaration-only morphisms, zero-arm raw routing,
transparent-synthetic DAG accounting, and an even-order GC row. The queue below
uses these mechanisms. `reports/PROTOTYPE_8.md` then closes §0 with exact
source/environment/consumer inventory and scenario-matched RSS rows, and adds
the persistent exact meaning representation needed to keep flat eager
accumulators from rebuilding once per alternate. Source implementation has
still not begun.

`reports/REVIEW_9.md` gives GO for §2 and finds ten later-phase corrections.
`reports/PROTOTYPE_9.md` closes the executable proof, non-sibling routing, and
hot-callback contradictions. This queue records every remaining mechanism plan
or evidence choice as an explicit gate; none is delegated silently to an
implementer.

`reports/PROTOTYPE_10.md` and `PROTOTYPE_11.md` establish the one-flip defect,
exact acyclic reference relation, real carrier costs, complete resolver-pair
and one-island splice feasibility, flat-index parity, and the initial custom
binding lifecycle. `PROTOTYPE_12.md` supplies the cyclic, tokenizer, flat/frame,
and real-pool round. `PROTOTYPE_13.md` is the authoritative correction: it
removes arbitrary cyclic caps, scopes quantified-nullable semantic families
and Leo-complete readout, limits the control to an external fused-product
protocol, and records the gates still open below. Resolver scope was a separate
question at that checkpoint; the later complete-document ruling closes
it below. `PROTOTYPE_14.md` and `P14_ADVERSARIAL.md`, as corrected
by the coordinator rerun, close the investigable cyclic and tokenizer gates,
pin the third shipped ambiguity defect, and separate the parser's recognition
grammar from its constructor-binding grammar. `PROTOTYPE_15.md` closes the
island-continuation composition: the compiled per-occurrence row, its universal
constant and existential injective certificates, the exact interaction rule,
occurrence identity across siblings and nesting, and the separation of semantic
settlement from resolver-tree materialization. `PROTOTYPE_16.md`, corrected by
`P16_ADVERSARIAL.md` and closed by `REVIEW_16.md`, completes the shared-DAG
relation and exact-lane policy. Shared nodes are values computed once; their
parent-slot occurrences choose independently. Exact execution is uncapped and
uses only proved constant, injective-route, and second-meaning exits. No
planning question or user decision blocks §2. Production source began
2026-08-31: §2 is implemented and coordinator-accepted (see the LEDGER §2
entry for the Reducer.events ruling and verification), and §3 is in progress
on the warm Terra agent. No parse regression is authorized by any of this
evidence.

**Finding 10 (REVIEW_7):** the reducer-free extraction capability stays. It
is one grammar-demand selection morphism — `select_raw(entry, spec)` — with
`select` as the beginner surface over signature-bearing reducers. Feasibility
and contract are prototyped in `proto/demand_selection.py`
(`reports/PROTOTYPE_5.md` §6): occurrence demand compiled into contextual
clones, one parse per document, recognition-only undemanded subtrees, a
statically model-free extent variant. §6 implements it, §10's templating
deletion names it as the successor, §11 keeps ex10's grammar-generic story, and
§13 tests it.

This is the executable queue for `context.md`, `goal.md`, and `DESIGN.md`. Read
all three before touching source. Do not reopen settled architecture unless the
current code proves a stated contract impossible; report that proof instead of
inventing a bridge.

`TBD_after.md` is explicitly outside this queue. Do not begin its performance
and export follow-ups until every item here is complete.

## Working protocol

Marker meanings are binding:

- **DECISION REQUIRED** — architecture or acceptance is not yet ruled. Stop
  before the named phase exit and obtain the recorded decision.
- **PLANNING REQUIRED** — the architecture is ruled, but its exact mechanism,
  owner, witness, or measurement row must be written down before source work in
  the consuming phase begins.
- **USER DECISION REQUIRED** — only the user can authorize the stated outcome.

An unmarked checklist item is implementation work under an already settled
design. An implementer must not resolve a marked item implicitly while coding.

- [ ] Terra owns the complete source implementation and source cleanup.
- [ ] The coordinator guides Terra, reviews every phase, and is the only agent
      allowed to commit or push.
- [ ] The coordinator makes checkpoint commits on branch `targeter` after the
      §4, §5, §7, §9, and §11 exit gates. A checkpoint preserves reviewed
      progress; it does not claim the full repository done-gate is green. The
      completed series is squashed into `main` after Luna's final gates.
- [ ] At every checkpoint Terra writes its report and updates `LEDGER.md`, then
      remains warm for the adjacent increment. Continue that same agent through
      follow-up work; do not replace it merely because a phase ended.
- [ ] Run `tools/usage_watch.sh 90 60 540` during agent-heavy stretches and
      follow the repository hold/resume protocol at its thresholds.
- [ ] The coordinator profiles the generated-model product at the §4
      checkpoint and the complete source tree externally after §11.
- [ ] Only after the complete-source §12 profile does Luna create/port tests
      and run formatting, linting, pyright, and repository gates.
- [ ] At EVERY phase exit from §4 on, Terra runs `uv run pytest tests/ -q -n
      auto` and `uv run pyright` and ledgers the exact failing-file set with a
      one-line attribution each. An exit is blocked by any failure not
      attributable to a deliberate deletion; the attributed set may only
      shrink once §13 begins. This is visibility, not test authorship — Terra
      writes no committed tests.
- [ ] Each phase that adds, moves, or deletes a source module updates the
      `CLAUDE.md` package-map lines in the same phase (mechanical edit only),
      keeping `tests/integration/lexic/invariants/test_doc_drift.py` green
      throughout; §11 remains the prose pass.
- [ ] Terra and Luna run sequentially, never concurrently.
- [ ] Run no two multithreaded benchmarks at once.
- [ ] During every timing window, hold all agents and unrelated repository
      work. A benchmark process owns the machine from preparation through
      warm-up, timing, and shutdown; do not concurrently prepare waiting MT
      workers.
- [ ] Put prototypes only in
      `zzz_current_work/260826-target-shaped-parse/proto/`, never `/tmp`.
- [ ] Put measurement/review output under
      `zzz_current_work/260826-target-shaped-parse/reports/` in the existing
      report style.
- [ ] Instrumentation never touches `src`.
- [ ] Prefix Python/test commands with `uv run`.
- [ ] Add no `Any`, `object`, `eval`, `exec`, suppression, or ignore directive.
- [ ] Do not touch `pyproject.toml`.
- [ ] Keep parsing generic: no JSON/tokenizer names, rule-name cases, or Qwen
      policy in `lexic.parsing` or generic compile code.
- [ ] Do not raise the 2 KiB split floor or hide an eligible regression.
- [ ] On the 11,422,654-byte Qwen3 witness, pursue less than 0.100 s wall for
      the complete reduced recursive Python mapping/list product and less than
      1.000 s wall for a resident-text ready `IrTokenizer`, then continue toward
      the standing roughly 105x Qwen tokenizer goal. Report resident, cold-path,
      and warm-path comparisons separately. The 105x objective is not a
      universal gate for every reduction: compare each codomain with the
      current path producing the same result. These remain generic
      grammar-derived products, not JSON/Qwen parser cases.
- [ ] Existing parsing performance must remain equally fast or become faster.
      A later reduction,
      tokenizer, memory, or MT win cannot offset a parse regression. If a
      correctness bugfix necessarily regresses parsing, stop with isolated
      alternating measurements and attribution. **USER DECISION REQUIRED:**
      only the user's explicit final approval licenses that regression.
- [ ] Do not land an incomplete public path, compatibility adapter, deprecated
      alias, feature flag, or fallback through model + fold.
- [x] Obtain substantive re-review of the post-`REVIEW_2` mechanisms. Do not
      begin broad source implementation while an architectural blocker remains;
      implementation-phase proof obligations become hard phase exits below.
      `reports/REVIEW_4.md` and `reports/REVIEW_5.md` both give GO for §2 and
      ABI/lifecycle §3; neither licenses §4 before the §3 exit.
- [x] Obtain a fresh substantive review of the completed performance-feasibility
      iteration in `reports/REVIEW_6.md`. It must challenge genericity, duplicate
      work, typed-hole certification, physical recognizer ownership, final-index
      semantics, and whether the measured budget can actually produce a ready
      tokenizer. It returned NO-GO on the claimed additive ready-tokenizer
      budget. `PROTOTYPE_4.md` measures one carrier path, rejects per-entry IR
      leaves, fixes canonical index identity, and separates resident/path
      metrics. The user will supply the next review; do not send another agent.
- [ ] Active grant, recorded verbatim from the user for this effort: “Grants
      remain applicable. Commit meaningfully (orchestrator only).” The user's
      2026-08-27 ruling also licenses checkpoint commits without the full done
      gate. The coordinator alone commits; final integration still waits for
      profiling, Luna's gates, and coordinator review.

## 0 — orient and pin the starting tree

- [x] Read, in order:
      `context.md`, `goal.md`, `DESIGN.md`, `docs/STYLE.md`,
      `.wiki/lexic/architecture.md`, `.wiki/lexic/decisions.md`,
      `.wiki/lexic/invariants.md`, `.wiki/lexic/public-api.md`,
      `.wiki/lexic/ir-shapes.md`, `.wiki/lexic/parallel-parsing.md`, and
      `.wiki/lexic/tokens.md`.
- [x] Read the evidence:
      `zzz_current_work/260821-one-path/DEMAND_PROJECTION.md`,
      `zzz_current_work/260821-one-path/reports/i9_report.md`,
      `zzz_current_work/260821-one-path/reports/i23_report.md`, and
      `zzz_current_work/260821-one-path/reports/i24_report.md`.
- [x] Run `git status --short` and preserve unrelated user work.
- [x] Confirm that the direct-carrier commit and
      `src/lexic/parsing/parallel/stitch/carrier.py` are absent. The user
      deleted the untracked file; do not reconstruct it.
- [x] Record the exact baseline commit and interpreter/build details in the new
      implementation report. Do not add a production timing seam.
- [x] Before source edits, freeze the external baseline protocol and witness
      matrix: fixture hashes, environment/topology, public/direct engine route,
      requested/actual workers, engaged/declined split shape, result/refusal
      digest, cold compile/bind, cold first parse, warmed parse, opcode/capture
      counts, garbage-collector state per row, and product-table bytes.
      Production/acceptance rows run with the collector enabled; only rows
      with equal GC state compare (`reports/PROTOTYPE_7.md` records the even,
      order-balanced eight-pair row: +0.004562 s process CPU / -0.002075 s
      wall, with the wall sign treated as noise); `src` never manipulates
      collector state.
      The baseline source remains reproducible
      from commit `0faa7289`; compare it later in alternating whole processes,
      not by trusting measurements from different machine states.
- [x] Measure baseline peak RSS on the `0faa7289` tree in the §0 matrix —
      resident and cold/warm path rows — so `goal.md`'s "not above the
      baseline" RSS criterion is a recorded number before any candidate row
      exists. `reports/PROTOTYPE_8.md` records 633,000 KiB resident-first,
      632,888 KiB path-cold, and 838,120 KiB on the second call in one retained
      warm process, all with the same final-table digest. The 79–82 MiB
      retained-carrier increase is a separate prototype figure, not a baseline.
- [x] Inventory all callers before moving these symbols:
      `Reducer`, `ModelBody`, `ModelFold`, `RuleFold`, `fold_config`,
      `model_fold`, `derive_reduction`, `ReduceFold`, `Template`,
      `split_model`, `read`, `tokenizer_of`, and `IrTokenizer.from_merges`.

Exit: passed. `reports/PROTOTYPE_8.md` names the exact source baseline,
environment, frozen matrix, scenario-matched RSS rows, and every current
production consumer of a surface scheduled to move/delete.

## 1 — prove the types and flat ABI before broad source edits

- [x] In `zzz_current_work/260826-target-shaped-parse/proto/`, write focused
      type-only prototype for:
      `ProductProgram[Carry, Result]`, `BoundProduct[Result]`,
      `ParseState[Carry]`, `ProductMark`, `RuleProduct[Carry]`,
      `FragmentProduct[Carry]`, and a recursive Python JSON `Carry`.
- [x] Prove that `Carry` remains typed through PDA frames, Earley result tables,
      meaning operations, worker fragments, and the bound runner without
      `Any`, `object`, casts at call sites, or an empty catch-all protocol.
- [x] Prove the cache shape: the public morphism is recursively immutable
      signature/schema/algebra data and contains no cache, lock, factory, or
      executor. A distinct private compiler/artifact registry has a typed weak
      source identity memo, serialized cold construction, lock-free warm
      lookup, and a result-only bound entry which cannot retain an expired
      source artefact. Eviction cannot change binding semantics.
- [x] Specify the authored product-operation union:
      `PassOp`, `ConstantOp`, `DecodeOp`, `RouteOp`, `ValidateOp`,
      distinct sequence/mapping begin/append-or-insert/finish records,
      `RecordOp`, `MeaningOp`, and `RootOp`.
- [x] Specify `CaptureSpec` modes `SKIP`, `TEXT`, `EXTENT`, `ONE`, and `MANY`.
- [x] Specify the flat representation: separate typed operand tables plus one
      checked tagged completion-range index and plain-int capture layout per
      contextual rule. Authored enums must be converted to exact `int` values
      before runtime; do not use one heterogeneous payload array.
- [x] Remove target-supplied scalar decoder, validator, and record-constructor
      callables from frequent-completion operand tables. Scalar decode,
      validation, insertion, and declared record construction use engine-owned
      closed operations selected by plain integers. Only collection finish,
      root finalization, and meaning comparison may retain typed target
      callables; `proto/product_types.py` executes this boundary.
- [x] Inventory the real GBNF, ABNF, EBNF, and JSON reducer expressions and
      specify the separate typed `ExprProgram[Carry]` lowering they require.
      A contextual rule executes its reducer-expression range or its fused
      target range, never both.
- [x] Specify constant-size marks and mutation-proportional undo for sequence
      append, map insert/duplicate set, ordered verdict, nested builder, and
      root finalization. A successful outer mark release performs no
      whole-builder copy.
- [x] Keep sequence and mapping handles in dedicated frame lanes rather than
      widening or wrapping `Carry`; only finished semantic values enter parent,
      meaning, island, or fragment slots.
- [x] Specify `RouteOp` key/discriminator classification including known decoded
      keys, escape-equivalent spellings, `EXTENSION`, and uniform dynamic-map
      entries such as vocabulary.
- [x] Prototype the route continuation which publishes at discriminator
      completion and selects the following contextual child before entry. Use
      a rollback-owned PDA route lane and sparse Earley routed-successor table;
      preserve route and occurrence identity without widening ordinary Earley
      items or their advance path.
- [x] Prototype a routed shell suspension over the current routed planner with
      no generated-model shell, plus associative carry/duplicate/verdict joins
      using a stable total verdict key.
- [x] Specify and execute the finite nested-mapping `select` contract:
      declaration order, missing paths, retained value identity, unselected
      recognition, repeated decoded keys, nested shape mismatch, and
      syntax-first failure.
- [x] Treat this phase as a hard feasibility gate. If `Carry` cannot remain
      typed under the stated constraints, stop and report the exact erasure
      boundary. Do not add `Any`, `object`, a suppression, or a call-site cast;
      no constraint relaxes without an explicit user ruling.

Exit: passed under the repository Pyright environment with real compiled
grammars, reducers, generated models, and `IrTokenizer`; see
`reports/PROTOTYPE.md`, `reports/PROTOTYPE_2.md`, and
`reports/PROTOTYPE_3.md`, with the corrected composed carrier and acceptance
boundaries in `reports/PROTOTYPE_4.md`, and the REVIEW_7 mechanism prototypes
(regular lowering + identity, interpreted-ABI throughput, shared-forest fold
discipline, local meaning folds, GC delta) in `reports/PROTOTYPE_5.md`.
The REVIEW_9 corrections are executed and typed in `reports/PROTOTYPE_9.md`.
No production module was added merely to discover the typing or performance
model. The source implementation still owes semantic differential,
composed-shell certification, ready-tokenizer acceptance, and paid-loop
measurement gates; the prototypes do not claim them.

## 2 — add the declarative signature/schema vocabulary

- [x] Extend `src/lexic/ir/reduction.py` with the strict declarative vocabulary
      for `SemanticSignature`, semantic sorts/events, `TargetSchema`, route
      classes, accepting/poisoned/recovery states, validation declarations, and
      meaning declarations.
- [x] Keep this vocabulary as data on the IR spine. It owns no parser runtime,
      target-specific JSON declaration, mutable builder, or compile algorithm.
- [x] Export the intended surface through `src/lexic/ir/__init__.py` and the
      relevant spine/package façades without introducing a second import path.
- [x] Give every unknown event/action/schema construct a raising
      `UnsupportedConstructError` dispatch default.
- [x] Implement the declared exception vocabulary exactly as `DESIGN.md`
      §validation records it: binding refusals, verifier failures, and syntax
      stay `UnsupportedConstructError`; raised semantic verdicts are the new
      `TargetRefusalError(LexicError)` over `SemanticVerdict` value records
      (never the bare name `Verdict` — `compile/verdict.py` owns it);
      `from_indexes` validation is `FieldValidationError`. Luna pins type and
      message against this declaration. This intentionally replaces the
      tokenizer reader's current semantic `UnsupportedConstructError` cases;
      pre-0.1 gets no compatibility subclass, alias, or adapter.
- [x] Add the JSON semantic signature beside `JSON_REDUCER` in
      `src/lexic/grammars/json.py`: decoded null/bool/integer/fraction/string,
      array item/array, object entry/object, and completion. It contains no
      tokenizer field names.
- [x] Bind the signature to the reducer through one real data channel. Do not
      create parallel registries keyed by reducer identity and do not infer
      semantic roles from grammar rule names.

Exit: native JSON and any compiled formulation using the same reducer expose
the same signature object; a mismatched target can be diagnosed before parse.

## 3 — introduce the engine-neutral product program

- [x] **PLANNING REQUIRED BEFORE §3 — CLOSED:** fix the frequent-completion
      operation boundary before source work. `proto/product_types.py` now uses
      plain-int engine-owned scalar decoders and no target decoder/validator/
      record-constructor callable table. Target callables are limited to
      collection finish, root finalization, and meaning comparison.
- [x] **PLANNING REQUIRED BEFORE §3 — CLOSED:** make routing independent of
      producer/consumer sibling placement. `proto/route_continuation.py` now
      carries a finite route through an intervening contextual PDA clone and
      Earley successor code; the implementation rule is the descendant clone
      chain described below.

- [x] Add the focused parsing-owned `src/lexic/parsing/product/` package:
      `records.py` owns immutable authored/flat ABI records, `state.py` owns
      parse-local builders and transactions, `regular.py` owns the
      authoritative regular-language proof, `verify.py` owns physical-table
      verification, and `__init__.py` is the one parsing-internal façade. Do
      not grow a monolithic product module or expose parallel import paths.
      `regular.py` imports and reuses `CharSet`, `build_recognizer`, and
      `compile_source` from the existing `parsing/pda/core/` leaves; it must not
      reimplement first-set algebra or possessive lowering. (Coordinator-
      accepted deviation 2026-08-31: `regular.py` also imports the first-set
      algebra `KWindowFirst`/`collide`/`separable`/`extend_follow` from
      `parsing/pda/analysis/gates/windows.py` — importing the repo's one
      first-set implementation IS the no-reimplementation clause's intent.
      Accepted 2026-09-01: a sixth module, `expressions.py`, carries the
      reducer-expression layer split out of `records.py` at the 700-line
      ceiling — one-way dependency, pure relocation.)
- [x] Define the typed authored operation records, flat opcodes/tables,
      typed reducer-expression program, `CaptureSpec`, `RuleProduct`,
      `ProductProgram`, parse-local state, transaction marks, meaning contract,
      and fragment contract.
- [ ] **To be done in §4.** Give every contextual PDA clone, Earley completion, token completion,
      attempt sub-clone, island, and delegate exactly one tagged completion
      range index. Verify its non-empty bounds and operand tables before
      execution; do not store parallel expression and fused fields.
- [x] Convert every authored enum to an exact `int` during lowering. Assert the
      flattened rule, expression, and capture tables contain no `IntEnum`
      instances using `type(value) is int`, never `isinstance`; frequent
      completion dispatch compares/indexes plain ints. (Done 2026-08-31 in
      `compile/product/lower.py` + `parsing/product/verify.py`; the
      engine-side int dispatch lands with the engine integration bullets.)
- [ ] **To be done in §6** (mechanism landed in §3; producer refusals need the schema compiler).
      Lower an occurrence-scoped `RouteContinuation`; refuse a nullable or
      non-single-discriminator producer. It records a descendant consumer path,
      not merely one sibling position. In PDA frames store `(consumer path,
      route)` until the first routed child successfully advances, with the lane
      under rollback; route-specialized intervening clones bake every deeper
      child. In Earley, route producer completion through a sparse `(waiting
      contextual code, route) -> successor contextual code` chain. The existing
      packed successor codes carry route and occurrence identity; do not widen
      every item or touch ordinary `_advance_all`. The later forest fold cannot
      perform routing.
      (Coordinator ruling 2026-08-31: the PDA lane is CURSOR-SIDE — one
      `PdaKernel` slot, `None` for every non-routing program, indexed by frame
      depth so it IS the parent frame's lane semantically, copied beside the
      stack at the two fork sites. Widening the uniform 9-slot frame literal
      would tax the generated-model paid path, which this section forbids;
      "under rollback" is satisfied by the kernel's own copy-discard
      speculation shape. A lane entry's validity is tied to its exact parent
      frame instance: the stale-route witnesses must cover a same-depth later
      sibling and an abandoned attempt.)
- [ ] **To be done in §6.** Lower the producer's discriminator to direct scalar
      decode/classification
      at recognition-time completion. It must not call the general reducer
      expression evaluator or construct a model. Specialize the lookup by
      actual cardinality: uniform dynamic maps bypass it, singleton routes use
      direct equality, finite sets of two or more use a private dictionary
      lookup, and dense route ids index destinations without a tuple scan.
      Preserve the measured representation decision from `PROTOTYPE_3.md`.
- [ ] **To be done in §6.** Run nested mapping witnesses through PDA, ordinary Earley fallback, and
      island/delegate execution. Outer and inner occurrences route
      independently, escaped-equivalent keys agree, and rollback/abandonment
      leaves no stale route for another attempt or member. Include the
      non-sibling `member ::= string tail; tail ::= separator value` shape and
      assert the route reaches the descendant value in all three execution
      paths.
      (Coordinator ruling 2026-08-31: EXECUTES AT §6, not §3. `PdaTables`
      carries no route data and cannot until a `TargetSchema` declares a
      discriminator — wiring `_enter`/the Earley successor table now would
      guard a branch that cannot fire, on the model product's paid path.
      §3 proves the mechanism: the lane with four stale cases, both fork
      sites, and the authored→lowered→verified route chain with cardinality
      specialization. This bullet's witnesses run at §6 against the first
      compiled schema routes, under the same wording. §6 obligation: prefer a
      clone-baked consult — routed consumer clones marked in their own data —
      over a global per-entry test, so unrouted programs' clone entries gain
      no new branch; §12's parse rows still gate whatever shape lands.)
- [x] Keep the parsing layer a leaf: imports may reach `lexic.ir`, never
      `lexic.compile`, `lexic.grammars`, or `lexic.api`.
- [ ] **To be done in §4** (the property becomes provable when the engines execute products). Lower operations to data. No target object or morphism is called from the
      character matcher, item loop, gate selection, or any frequent completion.
      Scalar decode, validation, insertion, and declared record construction
      dispatch through engine-owned closed int codes. Keep collection-finish,
      root-finalizer, and meaning-comparator callables in separate typed cold/
      boundary tables.
- [x] Keep the ABI capable of a closed cold/root constructor operation, but add
      no public custom callable/factory field and no custom operation at a
      frequent completion. The arbitrary-class public surface is gated in §6.
- [x] Make `ParseState` parse-local and worker-local. Builders are owned by one
      occurrence handle in a dedicated typed frame lane; handles never widen
      or wrap `Carry`, and there is no global current collection.
- [x] Allocate `ParseState` only for products with mutable builders or deferred
      verdicts. The generated-model product has no state allocation,
      transaction test, range-verifier call, generic instruction interpreter,
      or extra frame slot on its paid path.
- [x] Implement mark/commit/rollback for speculative PDA work and island
      failure with constant-size marks and mutation-proportional undo. Measure
      valid and failed speculation across large retained builders. Commit a
      child to its parent only after successful completion.
- [x] Make the Earley product capable of retaining immutable completed-handle
      meanings for the default derivation and replaying a dirty ancestor cone
      in a fresh isolated `ParseState`. The memo contains no builder handle or
      mutation log. Ordinary/unambiguous chart execution carries neither the
      dependency index nor alternate state; only an actual arm-choice enables
      it. §8 pins the root-equivalent verdict mechanism.
- [x] Make the Earley product fold execute each shared forest node's VALUE
      exactly once, guarded at fold entry, with occurrence-owned effects
      (appends, map inserts, verdicts, duplicate-set entries) applied from the
      parent's slot consumption so effect counts follow occurrences. The
      current walk's count is a traversal accident — `proto/
      shared_forest_refold.py` measures 2/2/1 fold-body executions for
      identical two-slot sharing across its three witness shapes
      (duplicate-slot, pending-frame, sibling-memo); all three shapes run
      through the Earley fallback, plus its transparent `__rep_1` witness whose
      missing value-table entry currently repeats. Use a finished set distinct
      from the value table; all four shapes are §3 exit witnesses with
      deterministic value-once/effect-per-occurrence counts.
- [x] Define the lifecycle seam through the existing
      `parsing.caches.memo/track/adopt/release` protocol. Product programs and
      bound runners retain no source artefact; derived PDA/Earley/replica cache
      entries release transitively. Exercise explicit release, collection,
      concurrent first bind, and a pool-retained bound program after release.
      (Done 2026-08-31 in `compile/product/binding.py` + `proto/s3_lifecycle.py`;
      transitive release of REAL engine-derived cache entries is re-exercised
      when the engines integrate.)

Exit: the product ABI executes a tiny sequence/map target over REAL EARLEY
RECOGNITION (a proto-side post-order product executor over the real
chart/FastTree — real text, real tree shapes, ParseState transactions and
duplicate policies exercised, built value asserted); the PDA and
island/delegate end-to-end execution rides §4's model-product migration as
its FIRST differential, per the 2026-08-31 ruling — `FlatClone` carries no
product data and a parallel §3 completion path would cost the model-path
branch this section forbids; the occurrence-routing MECHANISM is proved
(lane stale cases, both fork sites, authored→lowered→verified route chain) —
recognition-time route selection executes at §6 with the first compiled schema
routes, per the 2026-08-31 ruling above; every physical execution table
verifies one exact-int
completion range; rollback, fresh-alternate isolation, and cache release pass;
side-effecting completion is exactly-once per shared forest node with
per-occurrence effects across all four shared-subtree/synthetic witness shapes;
and measured valid/failed speculation exposes no unaccounted frequent-path
branch, allocation, or whole-state copy. §4 remains closed until all of this
holds.

## 4 — migrate generated-model parsing onto the common ABI

- [x] **PLANNING REQUIRED BEFORE §4 — CLOSED:** strengthen the authoritative
      regular proof before the value-string consult can use it. A nullable arm
      must be last, and `(variable or atom.nullable) and FIRST(atom) overlaps
      FOLLOW(atom)` declines. `proto/regular_region_lowering.py --mode identity`
      executes the `{1,1}` nullable-reference and early-nullable-arm witnesses.

- [ ] Start from `src/lexic/parsing/fold.py`. Re-express model field capture and
      construction as the generated-model specialization of `ProductProgram`.
      (Coordinator ruling 2026-09-01: the constructor operand table holds one
      immutable `ModelConstructor` record per rule — `cls` + field-name order
      + optional-capture indices + defaults + the `fast` validation-skip flag
      — not a bare class. `CaptureSpec(mode, slot)` cannot carry
      `FieldFold`'s `name`/`lo`, and dropping `lo` silently turns gtext
      ABSENCE into empty string. The record is binding-owned inert data with
      no callable — it TIGHTENS today's bound-method `FastCtor.make` table.
      Widening CaptureSpec with strings and a parallel per-rule field table
      were rejected. The gtext absence-vs-empty-string case is a mandatory §4
      differential row.)
- [ ] Delete `FOLD_KINDS`, `FieldFold`, `FastCtor`, `RuleFold`, `ModelBody`,
      and `ModelFold` after their callers move; do not preserve them as wrappers
      or generic-looking renames. (Scope ruling 2026-09-01: the caller set
      spans 28 src files including `parallel/` — orchestrate, replicas, all
      four stitch modules — which are IN §4 scope for the mechanical
      re-plumbing onto the model product's ABI, keeping their model-shaped
      stitching semantics untouched; §9's `FragmentProduct` generalization
      stays §9. `compile/output/templating.py` moves only minimally/
      mechanically to stay compiling — never re-expressed as a product — and
      §10 deletes it unchanged.) Generated-model synthesis lowers directly to
      `CaptureSpec`, `RuleProduct[GrammarModel]`, the typed constructor operand
      table, and one `ProductProgram[GrammarModel, GrammarModel]`
      specialization — the start class is synthesized at runtime and has no
      static name, so the static bound is `GrammarModel` exactly as
      `ModelFold[M]` spells it today; the real constraint is that the model
      product's `Result` never widens past `GrammarModel`.
- [ ] Rewrite `parsing/trace.py` alongside this migration: it is a public
      `PdaKernel` subclass shadowing exactly the completion surfaces §4
      rewrites. It follows the rewrite with its public surface unchanged; its
      port target is `tests/unit/lexic/parsing/test_trace.py`.
- [ ] Update `src/lexic/compile/pipeline/synthesis.py::fold_config` and binding
      callers to author the model product through the new operation records.
- [ ] Migrate `src/lexic/compile/foldkit.py::seq` and `model_fold`, plus every
      notation/generated-self-grammar caller, to the final vocabulary. Account
      explicitly for `IrNamed`, `FOLD_SYMBOLS`, `first_rest`, `absent_tail`,
      `ABSENT`, `FIRST_REST`, and `DECODE_INT`; preserve the no-`eval` notation
      symbol channel. Preserve `foldkit`'s authored-data role; do not fold it
      into runtime reduction.
- [ ] Update `src/lexic/parsing/products.py` so PDA and Earley receive one bound
      product. Preserve the public generated-model and segmented-token products.
- [ ] Update `pda/compiler/specs.py::CloneSpec`,
      `pda/compiler/clones.py::PdaCompiler`/`compile_pda`, and
      `pda/compiler/program/lower.py::_bake_build`/`_build_plan` to carry
      `RuleProduct` capture/completion data.
- [ ] Update `pda/compiler/program/flatten.py::FlatClone`/`PdaProgram` with
      separate typed product operand tables. Preserve the existing specialized
      model opcodes where their opcode stream is already optimal.
- [ ] Replace model-only completion in
      `pda/runtime/build.py` and
      `pda/runtime/kernel/execution.py::_run_leaf`/`_complete` with common
      product completion. Target selection must be absent from the character
      and item loops. (§3 executor finding, 2026-08-31: collection Begin* ops
      run at DESCENT/clone entry — a pure post-order walk inserts into an
      accumulator that does not exist yet — and a MANY capture must look
      THROUGH transparent repetition nodes to reach real elements;
      `proto/s3_earley_target.py` demonstrates both.)
- [ ] Implement the generic eligible-value-string specialization in
      `pda/compiler/program/specialize.py`: when
      `parsing/product/regular.py` proves one `value_str` occurrence exact,
      compile one recognizer consult returning its extent instead of the
      current per-character program. A declined rule retains the current
      program. Completion/capture remains the ordinary rule range; the
      recognizer invokes no target code. Gate ordinary generated-model and
      token-segmented parse rows separately so this task cannot trade a parsing
      regression for later target speed. The controlled mechanism row is in
      `PROTOTYPE_7.md` §4. The proof must enforce nullable-arm-last and
      nullable-atom continuation ownership, not only variable repetition.
- [ ] Update `earley_model`, `ModelFold.apply`'s replacement, island completion,
      and delegated completion to execute the same rule operation/captures.
- [ ] Compare flat programs/opcode streams for the generated-model target before
      and after. Explain every added paid-loop opcode; remove any target-only
      branch from the model path.
- [ ] Treat the existing direct generated-model completion/frame shape as the
      zero-tax baseline. A common ABI is not permission to route it through a
      generic completion interpreter or allocate otherwise-unused product
      state; only a measured faster simplification may change that shape.
- [ ] Run the existing generated-model, PDA, Earley, island, token, round-trip,
      and ambiguity tests relevant to changed files. Terra does not add the new
      committed tests or run lint; Luna does that after profiling.
- [ ] Run `uv run python tools/check_generated.py` at this exit. §4 changes the
      authored fold vocabulary and its notation/generated-self-grammar users;
      the generated-twin gate cannot wait until §7.
- [ ] Pause Terra at the completed §4 tree. The coordinator profiles the
      generated-model product with alternating baseline/new processes and a
      byte-identical control row under `docs/STYLE.md`. Instrumentation remains
      outside `src`.
- [ ] Gate generated-model and token-segmented parsing row by row across PDA,
      Earley fallback, islands/delegates, ambiguity, and eligible MT shapes.
      Compare structural opcode/capture streams as well as alternating timing.
      A slower delta outside the byte-identical control envelope fails; an
      ambiguous row is rerun with enough samples to resolve it and does not pass
      by assumption.
- [ ] Record opcode comparison and dynamic measurements in this effort's
      `reports/`. Any parse regression closes the gate: reshape the ABI and
      remeasure. A bugfix-related regression still requires the user's explicit
      final approval; do not build §5 on it merely because correctness improved.
- [ ] After review and the §4 measurement gate, the coordinator creates the
      first checkpoint commit and resumes the same warm Terra agent.

Exit: `CompiledGrammar.parse` and token-segmented parsing use the common product
ABI with existing behavior and no parsing-performance regression. There is
still only one generated-model route, and the §4 checkpoint is recorded. Any
bugfix-related exception has the user's explicit final approval recorded first.

## 5 — compile reducer semantics directly into products

- [x] **PLANNING REQUIRED BEFORE §5 — CLOSED:** use the private `_bind`
      protocol proved by `proto/product_types.py` and one homogeneous typed
      registry per declaration kind. `proto/reducer_free_surface.py` is
      explicitly only the public data-half witness; it is not a second binding
      design.

- [ ] Add `src/lexic/compile/product/` with the pinned layout (the sibling
      `parsing/product/` is pinned; this one is too): `signature.py` owns
      signature verification, `compose.py` owns lower × upper state
      composition and semantic-role × target-demand region derivation,
      `shape.py` privately owns the binding-derived recursive raw-map analysis
      moved from `MapShape.for_entry`, `demand.py` owns demand propagation, `lower.py` owns
      lower-action and operation lowering, `binding.py` owns the private
      bound-product registry/cache, `morphism.py` owns the public
      `ReductionMorphism` and reducer-free `GrammarMorphism` surfaces, and
      `__init__.py` is the one façade.
- [ ] Use open `IrDispatch`/`IrTypeMap` lowering over authored action types with
      a raising default. No closed `isinstance` cascade and no runtime action
      evaluator fallback.
- [ ] Lower every action used by shipped GBNF, ABNF, EBNF, JSON, notation, and
      generated-self-grammar reducers/folds into the typed expression ABI.
      Fuse a contextual rule to target completion operations only where the
      semantic signature proves equivalence; one rule never executes both.
- [ ] Refactor useful analysis from `src/lexic/compile/reduction.py` into the new
      owner: contribution order, `DROP`, `YIELD`, epsilon, text equivalence,
      contextual occurrence demand, and language-preserving lexical/run
      transforms.
- [ ] Do not reproduce `ReduceFold.channel`, its caches, or its whole-model
      traversal under new names. Reducer actions lower once to rule completion
      operations.
- [ ] Preserve poisoned-run behavior without a model/fold sub-product. A run
      uses the same direct product and transaction semantics for its declared
      subgrammar; no lease recursion or parallel nested pool is introduced.
- [ ] Implement the immutable default IR morphism declaration and its separate
      private typed binding registry.
- [ ] Make morphism declarations recursively immutable data only. Put locks,
      factories, executors, and entries in a distinct private compiler/artifact
      binding registries. The declaration's private `_bind` enters the one
      homogeneous registry for its kind, preserving `BoundProduct[Result]`
      without a cast or heterogeneous result bag. Bound entries use weak source
      references, lock-free warm lookup, double-checked serialized cold build,
      and no source retention by the result-only bound program; eviction must
      only cause equivalent recompilation. Adopt derived product/PDA/Earley/
      replica cache entries into `parsing.caches` release ownership and test
      concurrent first binding, explicit release, and a pool-retained bound
      program after release.
- [ ] Permit no second cache of the same binding. Reduction registries key
      `(CompiledGrammar, reducer, morphism)` and grammar registries key
      `(CompiledGrammar, morphism)`, each producing one typed `BoundProduct`.
      `parsing.products` owns no
      second bound-product memo; `parsing.caches` owns only tables/replicas
      derived from the bound program, and a pool is an explicit lifetime owner.
- [ ] Update `CompiledGrammar.reduce` in `compile/artifact.py` to select a
      `BoundProduct`: omitted `into` returns `IrSelf`; supplied
      `ReductionMorphism[T]` returns `T`; `cores` reaches the same product.
- [ ] Give `reduce` the three exact overloads recorded in `DESIGN.md` and
      `proto/reducer_free_surface.py`: default reducer → `IrSelf`, reducer plus
      `ReductionMorphism[T]` → `T`, and reducer-free
      `GrammarMorphism[T]` → `T`. Give ALL overloads the same `resolve=`
      resolver parameter `parse` carries — the resolver is the one ambiguity
      opt-out and it reaches whichever engine chooses; target products are not
      exempt. The overload declarations are typing only; the
      implementation performs one pre-engine target choice and one cached bind.
      A repeated-document pool retains the bound product directly.
- [ ] Support char and token-segmented grammars through the existing grammar
      token binding. Do not add a char-only direct path followed by token-model
      fallback.
- [ ] Before §6 opens, run the direct default product against
      `_ReduceEntry.variant.parse + ReduceFold.reduce` as §5's mandatory exit
      oracle. Cover property-generated values, fixed ground-truth formulations
      across native/GBNF/ABNF/EBNF, refusal type and message, poisoned runs,
      epsilon, `DROP`, `YIELD`, contribution order, and ambiguity.
- [ ] Run the temporary property differential through `tools/guarded.sh` from
      this effort's `proto/`; Terra does not add committed tests. Make this run
      deliberately broad because fresh-input comparison ends when the oracle
      is deleted.
- [ ] Capture frozen semantic and refusal goldens for fixed corpora under this
      effort and record the exact commands/results in `reports/` for Luna to
      port after the old oracle is gone.
- [ ] At §5 exit, `CompiledGrammar.reduce` executes exactly the new product.
      `ReduceFold` remains importable only as the uncommitted direct oracle
      THROUGH THE §9 EXIT (not merely §5): the most differential-hungry
      changes — contextual clones at §6, ambiguity rewiring at §8, parallel
      composition at §9 — come after §5, and fresh-input comparison must
      survive them. No production caller, flag, fallback, adapter, or
      representation bridge may reach it; §10 deletes it.
- [ ] At the §5 exit, run a timed direct-IR throughput probe (default product
      versus the current route, sequential, alternating processes, from this
      effort's `proto/`) and record it in `reports/` — the first timed number
      for any target product must not wait until §12.
- [ ] Stop before §6 if the warmed direct-IR row is more than 3x the remeasured
      current route on the same codomain, or if any generated-model parsing row
      regresses outside its control floor. The 3x threshold is an architectural
      early-warning bound, not permission to land a slower final product.
- [ ] After coordinator review of the differential report, create the §5
      checkpoint commit and resume the same warm Terra agent.

Exit: default reduction constructs its `IrSelf` during parsing with exact
current parity and no `GrammarModel` or `ReduceFold` on the executed route.
Ambiguity compares complete root values; divergences caused solely by replacing
the variant-model relation are enumerated, while child-local language narrowing
is forbidden. The old oracle has no production caller and its last broad
differential of THIS phase is frozen; the oracle itself stays importable for
the §8/§9 re-runs.

## 6 — implement signature composition and target-dependent products

- [ ] Implement semantic-signature verification and the lower occurrence ×
      upper schema state product in `compile/product/`.
- [ ] Propagate value, validation, text, extent, accumulation, and meaning demand
      backwards through reducer operations to a fixed point.
- [ ] Generate occurrence-sensitive contextual clones when one lower rule has
      different upper states/demands under different parents.
- [ ] Compile schema `RouteOp` data into the occurrence-scoped continuation
      mechanism proven at §3. Known valid routes select precompiled specialized
      child states; this is not a Python callback, grammar-rule-name lookup, or
      second route implementation. Per the 2026-08-31 ruling this is also
      where recognition-time routing first EXECUTES: route data enters
      `PdaTables`, `_enter` consults the lane (clone-baked consult preferred —
      routed consumer clones marked in their own data, no global per-entry
      test), the sparse Earley routed-successor table lands, and §3's moved
      nested-mapping/non-sibling/stale-route witnesses run through real
      PDA / Earley fallback / island-delegate parses here.
- [ ] Implement poisoned schema states. A semantic mismatch records its ordered
      verdict, routes the remaining value/document through generic lower-syntax
      recovery, and defers raising until syntax succeeds.
- [ ] Implement full Python JSON as the shape-preserving witness: recursive
      Python scalars/list/dict directly, including declared fraction and
      duplicate behavior, with no generated or IR JSON tree.
- [ ] Implement the parser-certified extent target. State its validity contract
      in the result type; do not infer or scan delimiters.
- [x] **DECISION REQUIRED AT §6 EXIT — CLOSED:** arbitrary classes remain in
      scope. Their inert declaration carries exactly one immutable class object
      as the constructor symbol plus field/path data. A homogeneous private
      registry caches a result-free plan, and binding reconstructs the
      result-typed view without casts. No bound callable, factory, mutable
      rebinding registry, import-path lookup, reflection, or second executor is
      admitted. `PROTOTYPE_10.md` proves the public/typing shape; omission was
      rejected by the user.
- [x] **PLANNING REQUIRED AT §6 EXIT — NON-POOL BINDING PART CLOSED:**
      `proto/custom_class_target.py` binds without class inspection, retains
      derived grammar data and tables rather than the source artefact, runs
      after source death and registry eviction, recompiles a larger table tier,
      tolerates unhashable constructor classes and identity reuse through an
      identity-plus-pin cache, recomputes equivalently after eviction, and
      cold-binds once under the free-threaded interpreter. Construction has one
      structural call site after the completion walk.
- [x] **PLANNING REQUIRED AT §6 EXIT — POOL LIFECYCLE CLOSED:** the real
      `ParsePool` is the bound executable's sole owner after the source
      artefact and registry entry die. Multiple and concurrent maps, tier
      escape, constructor failure, eviction/rebind, shutdown refusal, and
      cleanup pass in `proto/custom_class_target.py`.
- [ ] **PRODUCTION MEASUREMENT REQUIRED AT §6 EXIT:** prove that the landed
      completion executor contains no constructor or callback traffic before
      root finalization and compare it with the default product through the
      same paid loop. Prototype 12's timed walk builds and extracts a
      `ParseTree`, so its near-1.0 ratio does not close this source-path gate.
- [ ] Implement `select(spec)` as the finite nested-mapping morphism specified
      in `DESIGN.md`: declaration-ordered path results, absent missing paths,
      retained reducer values, recognition-only extensions, decoded duplicate
      refusal, and syntax-first nested-shape verdicts. Refuse an incompatible
      source signature at binding; do not add array/predicate sugar.
- [ ] Implement `select_raw(entry, spec)` — the reducer-free grammar-demand
      selection morphism (`proto/demand_selection.py` pins the contract):
      binding requires and derives a compatible recursive map shape from the
      entry rule's own binding data
      and requires no reducer or signature; the selection compiles into
      occurrence-demand contextual states so ONE parse recognizes the
      document, kept values build during it, undemanded subtrees stay
      recognition-only, and the extent variant constructs no values; raw
      duplicates refuse at selected levels, escape-equivalent spellings are
      distinct, and a selected non-mapping value is a syntax-first shape
      verdict. Default model capture and `capture=EXTENT` are typed declaration
      values producing exact `RawSelection[GrammarModel]` and
      `RawSelection[CertifiedExtent]` results, never a boolean execution mode or
      result union. It executes only through the one `reduce` morphism channel —
      no `Template.run` twin, no second parse API — and the prototype's
      resolver-based route stand-in is replaced by the real route
      continuation.
- [ ] Prove raw and decoded routing add zero grammar arms: discriminator
      completion writes a finite route and the following contextual code reads
      it, as in `proto/route_continuation.py`. `resolve=` remains untouched and
      reaches genuine authored ambiguity only. The toy raw selection and every
      JSON formulation must have zero route-created arm-choice ambiguity points.
- [ ] Implement the declared empty-edge rulings so tests cannot freeze an
      accident: `select({})` refuses at declaration (an empty selection
      declares no demand — `UnsupportedConstructError`); a spec leaf that is
      neither `KEEP` nor a mapping refuses at declaration; a non-mapping root
      document under a selection is a target-shape verdict after syntax
      succeeds, exactly like nested non-mappings; a present-but-empty
      `model.vocab`/`model.merges` is valid and produces empty indexes
      (empty merges are a real tokenizer shape) — whether a model type
      requires a nonempty vocabulary is a declared root cross-field check,
      not an index-level refusal.
- [ ] Exercise the same target over native JSON plus GBNF/ABNF/EBNF JSON
      formulations using the shared semantic signature. If any target lowering
      names a formulation rule, stop and fix the signature.
- [ ] Derive at least one non-JSON repeated region from a distinct semantic
      signature and the same target-demand mechanism before §7; the catalog
      witness in `regular_region_lowering.py` pins the required separation.

Exit: one compiled mechanism builds default IR, Python JSON, extents, decoded
selection, and reducer-free raw selection with their distinct semantics and
costs. No target is a post-reduction mapper.

## 7 — implement the layered tokenizer product

- [x] **DECISION REQUIRED BEFORE §7 — CLOSED:** the `<1.000 s` gate applies to
      the public engaged `cores=AUTO` tokenizer row. A route-anchor decline to
      sequential is reported with CPU-per-byte and named attribution but is not
      gated against the same envelope. It still must submit no work and cannot
      conceal a base-parse regression.
- [x] **PLANNING REQUIRED BEFORE FINALIZING `from_indexes` — CLOSED:** inventory Qwen,
      GPT-2, SmolLM2, Gemma, and the small fixture for three currently accepted
      lanes: negative versus sparse nonnegative ordinals, merge dyads naming
      spellings outside the vocabulary, and pipeline byte-fallback/unknown
      spellings outside the vocabulary. `proto/tokenizer_validation_lanes.py`
      accepts every nonnegative ordinal including sparse/above-count ids,
      accepts merge parts outside vocab, preserves declared fallback, unknown,
      fused-unknown, remap, and atomic added-token data, and refuses conflicts.
      Its nine verdict lanes are ordered independently of document entry order.
      The real-fixture candidate retains every lane-relevant pipeline field
      presented to `IrTokenizer`. Format-level `special` flags remain distinct schema
      inputs for the explicit reader-contract task below; `pipeline.specials`
      names every atomic added token, including entries whose format flag is
      false. Existing reader permissiveness is evidence, never authority.

- [ ] In `src/lexic/api/json_tokenizer.py`, declare the tokenizer
      `TargetSchema` against the JSON semantic signature. Generic compile/parser
      modules contain none of these field names.
- [ ] Inventory every value consumed or checked by the current reader as
      evidence, then author the final pre-alpha target contract deliberately:
      model type, vocab, merges, model knobs, byte fallback, unknown/fused
      unknown behavior, added tokens and flags, normalizers, pre-tokenizers,
      patterns, and pipeline configuration. Retain no accidental permissiveness
      or structure merely because the old reader had it.
- [ ] Make every tokenizer schema mapping explicit and closed. Classify each
      key as consumed, deliberately irrelevant/recognition-only, or refused
      through syntax-first recovery. Dynamic maps such as vocab are explicitly
      open because keys are data. Inventory real fixtures to author the
      irrelevant set; do not preserve accidental current-reader permissiveness.
- [ ] Decode every schema-covered object key needed for routing/duplicate
      refusal. Treat escape-equivalent spellings as the same key.
- [ ] Pin tokenizer failure order in the implementation:
      full lower syntax first; earliest ordered semantic verdict second; root
      missing/cross-field checks last.
- [ ] Add parse-local tokenizer accumulators:
      vocab encode/decode, ordered merge ranks, added tokens, normalizers,
      pre-tokenizers, model knobs, and deferred cross-field checks.
- [ ] Stream `model.vocab` and `model.merges` directly. Do not construct JSON
      entries, tuple dyads, merge lists, or a complete intermediate map.
- [ ] Review `src/lexic/ir/text/tokenizer.py::_vocab_map`, `_rank_map`,
      `IrTokenizer.from_merges`, and `_build`. Add three tokenizer-native index
      roles as distinct subclasses of the immutable `IrMapping` base:
      primitive `str -> int` encode,
      `int -> str` decode, and `(str, str) -> int` ranks. Encode/decode order is
      canonical by id and merges by rank. Validate and freeze an already
      canonical direct builder without sorting; order a noncanonical
      public/readback input once. Equality and hash are order-insensitive and
      cannot certify canonicality; validate order at every constructor and pin
      `tuple(items())`, repr, notation, payload, and generated-module order.
      Add the one final constructor
      `IrTokenizer.from_indexes`, accepting all three together. Direct parsing
      populates them together: no inverse derivation, rank re-index, repr-key
      sort, IR scalar/dyad per entry, or dyad list. Keep public encoding return
      types while using primitive internal lookups. Make
      `from_vocab`/`from_merges` converge on the same validation and
      record-construction tail. Preserve the existing segmentation-tokenizer
      binding and encoding-registry/concretization lifecycle: indexes created
      by direct parse, notation, payload readback, and public constructors all
      reach the same bind/registry tail exactly once. Update
      payload/notation/emission and every tokenizer field type for the new
      pre-alpha representation; retain no compatibility adapter to `IrMap`
      fields.
- [x] Before fixing that source layout, use the real Qwen cardinalities in an
      external prototype to compare pair-buffer/duplicate-set and indexed
      accumulators. `PROTOTYPE_4.md` rejects per-entry IR leaves at 0.346817 s
      and selects primitive tokenizer-index payloads. Both dominant regions
      through capture/join, canonical freeze, and actual tokenizer-record
      construction currently measures 0.700274 s median process CPU /
      0.130779 s median wall with GC enabled at eight workers, with about
      79–82 MiB first-run RSS growth. The older 0.138739 s GC-disabled
      decomposition is provenance only. Re-prove rollback, payload/notation fixpoint,
      deterministic emission, and final semantic equality in source.
- [ ] Change `json_tokenizer.read`/`read_from_path` to use
      `compiled.reduce(..., into=tokenizer_morphism)` and return the ready
      tokenizer.
- [ ] Keep `tokenizer_of` for already-reduced documents. Ensure `read` never
      invokes it directly or on decline.
- [ ] Verify root finalization is independent of JSON object key order and runs
      exactly once.
- [ ] Implement the proved-regular capturing lowering as a gated task at this
      exit. `compile/product/compose.py` derives a repeated region from semantic
      roles × target demand. `parsing/product/regular.py` proves acyclic simple
      closure, first-disjoint ordered arms, and deterministic repetition,
      nullable-atom, and entry/capture boundaries against separator/terminator
      before atomic or possessive sources become authoritative. A nullable arm
      must be last. A variable or nullable atom whose first set overlaps its
      continuation declines, including a once-required nullable reference. The
      surrounding parser owns the opener and terminator. An acyclic simple shape
      whose possessive atom steals its successor must decline. A proved region lowers to one capturing
      recognizer per entry with demand-derived positional groups over the
      rules' own pattern sources, no grammar-name case. Support arbitrary
      demanded capture arity; empty proved regions remain valid. Prove it
      identical on valid, empty, malformed, and boundary cases to the generic
      product on the same region, across native/GBNF/ABNF/EBNF formulations,
      and gate it the way §4 gates the
      model path; a region losing the proof declines to the interpreted
      product. The recursive, variable-boundary, `{1,1}` nullable-reference,
      and early-nullable-arm witnesses must all decline. Mechanism,
      JSON/non-JSON derivation, all formulation rows,
      controlled timing, and decline are prototyped in
      `proto/regular_region_proof.py` and `regular_region_lowering.py`; the
      ~105x objective is contingent on this task. The 0.351784 s interpreted
      microkernel assumes §4's scheduled rule recognizer consult and still
      omits driver, frame, transaction, merge-region, and remaining-document
      work, so it does not prove the complete `<1.000 s` envelope; the §7 timed
      exit decides that gate (`reports/PROTOTYPE_7.md` §§2–4).
- [ ] Run the payload/notation/generated-twin fixpoint gate before this
      checkpoint: the three-index `IrTokenizer` rework touches the payload
      codec, the zero-import reader, notation, and the twin modules — run
      `uv run python tools/check_generated.py` plus a notation/payload
      round-trip over the new representation and record the result.
- [ ] Time the resident tokenizer row AT THIS EXIT: ready tokenizer from
      resident text, sequential and `cores=AUTO`, external alternating
      processes with a byte-identical control, recorded in `reports/` with
      the existing proto harness. Stop factor: if the row misses the
      <1.000 s envelope by more than 3x, the effort halts here with the old
      path still present in the tree, and the miss is attributed before any
      §8+ work opens. §12 remains the complete matrix.
- [ ] After coordinator review of sequential target parity, create the §7
      checkpoint commit and resume the same warm Terra agent.

Exit: Qwen, GPT-2, SmolLM2, Gemma, and the small fixture can reach a ready
`IrTokenizer` without generated JSON models, JSON `IrMap`, or `tokenizer_of`,
and the timed resident row is recorded inside its stop factor.

## 8 — make ambiguity and failure isolation target-correct

- [x] **PLANNING REQUIRED BEFORE §8 — CONTINUATION CERTIFICATE AND NON-SHARED
      COMPOSITION CLOSED:**
      the enclosing continuation is a compiled artefact, one immutable row per
      contextual occurrence keyed `(consuming clone, channel slot, requested
      root, bound product)`, holding the slot's operation class and two
      reachability lanes and no parse value or callback.
      `proto/island_continuation.py` executes the certificate on real tables,
      the real delegated island seam and real authored reducer bodies in two
      flavours: a universally constant continuation discards the occurrence's
      alternates — and the rule-level half is read BEFORE the island
      enumerates, so those alternates are never built and no ambiguity
      operation executes. The former claim that an injective continuation also
      proves inequality without execution is superseded: `PROTOTYPE_16.md`
      constructs two local meanings and carries both through one family-aware
      realized route. Only then may it conclude requested-root inequality. Two
      refusals keep the rows sound and both cost work, not correctness: a rule
      whose pre- and post-normalization contributing references differ has no
      law (the authored `IrArg` index is not the chart's chain slot wherever a
      hoisted group or quantified repeat splices), and a `grow` derived by
      retaining a mapped focus has no law. Closing `PROTOTYPE_14.md` §4's exact
      channel-index obligation is what widens the first.
      Everything else runs the exact per-node relation; interacting
      occurrences compose through deduplicated option products, with both
      one-flip comparisons equal to the baseline and the joint choice
      differing. Occurrence identity is the delegated leaf object, so one
      island rule settles differently at two sites, and nested delegation adds
      no second mechanism. Every exercised non-shared candidate agrees with an
      independent complete-Earley-fold oracle. Production reads the key off the
      island's entry frame or waiter code instead of the prototype's root-down
      descent, and a cyclic chart is refused by name to `cyclic_meaning`.
- [x] **PLANNING REQUIRED BEFORE §8 — SHARED-OCCURRENCE COMPOSITION CLOSED:**
      `proto/shared_occurrence_ambiguity.py` agrees with an occurrence-unrolled
      complete-derivation oracle on duplicate-slot, pending-frame, sibling-
      memo, arm-shared, mixed, separate-root, delegated, unambiguous, and both
      genuinely shared transparent-synthetic shapes. A completed chart node is
      a value: compute its meaning set once. Every grammatical occurrence is
      the `(consuming handle, family index, kid slot)` edge which reaches that
      node, and each such slot ranges over the set independently. Occurrence-
      owned append, insert, verdict, and duplicate work executes per slot
      consumption. A family assignment keyed globally by the packed handle is
      forbidden because it correlates independent occurrences and loses
      meanings.
- [ ] Fix `ForestCtx` before relying on `forest.DERIVATIONS` for ambiguity or
      resolver materialization. Its open-handle set currently treats a
      suspended shared zero-width handle as a nullable cycle, emits an empty
      prefix, and produces two malformed derivations where the grammar derives
      four. Pin duplicate-slot and pending-frame regressions and preserve real
      nullable-cycle termination.
- [ ] Implement the exact lane over the DIRTY CONE, not the whole chart: fold
      every completed node once to its baseline meaning — that fold is the
      parse's own product — and run the meaning-SET lane only on the upward
      closure of nodes holding a live occurrence or carrying more than one
      family. Apply bottom semantics: a refusing family contributes no meaning,
      an empty child image removes only consuming families, and the document
      refuses only when no requested-root meaning survives. Introduce a
      distinct value-refusal exception first; `UnsupportedConstructError`
      cannot distinguish an operation's empty image from an unsupported
      construct. Take each node's baseline from the first family which produces
      a value, use production `same_value` for deduplication, and form no global
      family assignment anywhere, island seeds included.
- [ ] Build the family-resolved chart and occurrence edges on demand after a
      real semantic-choice family is found. The unambiguous path allocates none
      of them. Cache each evaluated family's baseline outcome and reuse it for
      liveness, route discovery, and lifting; do not re-run reducer bodies merely
      to rediscover that a family is live. Count reducer applications and value
      comparisons separately in the implementation report.
- [ ] Route an EXECUTE verdict on the predictive path to Earley deliberately.
      The exact lane needs the family-aware chart and a PDA-first parse holds
      no SPPF, so that escalation is real and must be a named, measured route
      rather than an accident; constant and injective rows settle with no chart
      at all and must keep doing so. On the shipped self-grammars the census
      puts EXECUTE at 73.9–95.6% of rows, so this is the common path.
- [ ] Retain one island kernel per AMBIGUOUS delegated occurrence — and only
      while its alternate is unsettled — so a resolver pair is spliced rather
      than re-recognized. An unambiguous island retains nothing. Define and
      test the release boundary; `proto/island_continuation.py` proves the
      splice and counts the retention but does not settle when production
      drops it.
- [x] **PLANNING REQUIRED BEFORE THE EXACT LANE LANDS — EXACT-LANE POLICY
      CLOSED:** no arbitrary multiplicity ceiling or resource refusal lands.
      At node `h`, full enumeration performs exactly
      `sum(family products of child-image widths)` reducer applications, plus
      image-dependent `same_value` comparisons whose structural cost remains a
      §12 measurement. The current worst case is exponential in local
      multiplicity. Two exact shortcuts reduce it: constant continuations, and
      a family-aware `ident`/`grow` certificate which constructs two local
      meanings and carries both through one realized route to an accepting
      item. Enumeration also stops as soon as a second distinct requested-root
      meaning is certified. None concludes equality; an unproved case executes
      the exact relation. The prototype's reported witness/lift application
      count is not the lane's total cost: baseline folding, family liveness,
      failed candidate nodes, route length, and value comparisons remain real
      work. Production must reuse family evaluations and measure the complete
      lane. No parse regression is authorized.
- [x] **PLANNING REQUIRED BEFORE §8 — SINGLE-SEED PART CLOSED:** an island with
      a second target meaning remains in the predictive product and does not
      decide at its span. `PROTOTYPE_10.md` proves the baseline-plus-alternates
      seed, Earley leaf dependency/cone, PDA-shaped continuation trace,
      isolated replay, dropping-parent result, and sibling-accepting-item
      requirement for one alternate substitution. Equal requested roots retain
      the predictive result without recognizing the document again.
- [x] **PLANNING REQUIRED BEFORE §8 — ACYCLIC INTERACTION PART CLOSED:**
      production one-flip replay is disproven on a real two-point chart. On an
      acyclic completed-node graph, the exact reference relation is the
      semantic-deduplicated value set over each node's packed families and
      island-leaf options, unioned across sibling accepting items. A compiler
      may refuse early when some path from the differing node to a requested
      root is proved injective in the carried slot. A constant edge blocks that
      path. Purity alone never grants the certificate.
- [x] **PLANNING REQUIRED BEFORE §8 — CYCLIC REFUSAL DECISION CLOSED:** use
      carrier-scoped zero-width SCCs under the per-slot `const` / `ident` /
      declared-`finite` / proper-subvalue-`grow` algebra. Safe components reach
      a monotone exact-set fixpoint. An invisible growing carrier is opaque; an
      injectively visible carrier proves requested-root ambiguity; the
      remaining unrepresentable consumer class refuses at binding. Family and
      island censuses iterate to a structural fixpoint. Numeric census and
      semantic-lap caps, the one-lap relation, and chart-wide Cartesian
      assignment enumeration are forbidden.
- [x] **PLANNING REQUIRED BEFORE §8 — CYCLIC PRODUCTION COMPLETION CLOSED:**
      `proto/operation_slot_laws.py` maps every current completion operation and
      child slot through an open type-keyed law table with a raising default;
      independent finite argument images multiply and alternative images add.
      `proto/scc_resolver_pair.py` constructs the engine's accepting derivation
      plus one addressed growing closed-walk splice, trying every certified
      carrier in `O(E × (V + E))` with no numeric lap count. Production still
      implements the law rows, refuses undeclared future operations with words,
      and differentials real tables against both prototypes.
- [x] **PLANNING REQUIRED BEFORE §8 — SEMANTIC FAMILY UNIVERSE CLOSED:** a
      quantifier admitting more than one occurrence count over a nullable atom
      creates semantic count families. `*`, `+`, bounded variable counts,
      groups, empty rules, and `?` all reach complete target-meaning comparison.
      They are not ordinary text-allocation splits. Remove
      `lift_optional_nullables`; it erases the `?` absent/present difference and
      changes which model wins. The canonical ground-truth grammars have zero
      such sites, while `@non-semantic` relaxation manufactures 71 across six
      codegen grammars. Those 71 do not enter the family universe because the
      parser recognizes the pre-relaxation armed grammar; the relaxed grammar
      remains only the binding/synthesis shape for optional constructor fields.
      Authored optionality remains in armed and is fully observable. For a
      token-bound artefact, concretize armed into a distinct parse-ready moment
      rather than reusing resolved-relaxed. The six exposed fixtures must keep
      byte-identical models through both parser engines; the prototype proves
      this separation with the current fold.
- [x] **PLANNING REQUIRED BEFORE §8 — COMPLETE READOUT CLOSED:** ambiguity
      point discovery expands all deferred Leo provenance before walking the
      links. The same finished kernel currently reports `0` points before and
      `2` after expansion; caller ordering is not a supported precondition.
- [x] **PLANNING REQUIRED BEFORE §8 — RESOLVER MECHANISM PART CLOSED:** both
      complete-document trees are constructible and associated with their
      replayed meanings. A context-sensitive resolver can choose differently
      between island-local and complete pairs. On the one-island
      Earley-delegated witness, occurrence replacement constructs the two
      island derivations and splices them into a structurally identical
      complete pair with no second document recognition. Today's island gate
      decides inline and discards its kernel, so this is new deferred state,
      not free reuse. Refusal and equal-root paths perform no document reparse.
- [x] **DECISION REQUIRED BEFORE §8 — RESOLVER SCOPE CLOSED:** `resolve=`
      receives complete-document pairs under both engines. Semantic settlement
      constructs no pair. After root meanings differ and only when `resolve=`
      is actually invoked, use occurrence-identified multi-island splicing;
      the fused PDA may perform one cold Earley recognition because it retains
      no document `ParseTree`. Refusal and equal-root paths perform none of
      this work. An island-local pair is not a second public contract.
- [x] **DECISION REQUIRED AT §8 EXIT — PYTHON AND IRMAP CLOSED:** real carrier
      rows cover equal, changed-value, key-set-changing, duplicate, dropped,
      merge-order, pipeline, and finalization cases. Recursive Python mappings
      keep the exact isolated cold comparison; their normalized comparison is
      slower at the measured medium scale. `IrMap` uses document-level
      key/value/duplicate normalization rather than reconstructing an alternate
      carrier. Ordered contribution trees and the incremental keyed treap stay
      rejected.
- [x] **PLANNING REQUIRED AT §8 EXIT — CURRENT TOKENIZER RELATION CLOSED:**
      the document meaning carries every input and ordered refusal for the
      shipped `from_merges` and prototype `from_indexes` constructors,
      including duplicate spellings, ordinals, merge dyads, inverse/rank,
      special, pipeline, and segmenter lanes. Every ordered pair in the
      21-document family agrees with eager construction. Prototype 14 closes
      ordinal-domain, merge-reference, and pipeline fallback/unknown policy
      against five real fixtures and proves that accepted lane-relevant
      pipeline payloads survive final construction.

- [ ] Give `CompileMoments` separate recognition and binding grammar moments.
      Recognition starts from `moments.grammar.armed` and, when an encoding
      registry is bound, concretizes that armed shape independently. Binding,
      synthesis, field defaults, and emission continue to consume the relaxed
      shape. Route `CompiledGrammar.parse`, PDA clone compilation, token scan,
      parallel speculation, and every product table through the parse-ready
      moment. Delete `lift_optional_nullables` and every call/documented
      precondition around it; do not retain a relax-then-lift compatibility
      path. Differential the six exposed ground-truth grammars and authored
      nullable-quantifier witnesses before ambiguity-family work proceeds.
- [ ] Replace any generated-model-only ambiguity hook with the product's typed
      root-meaning operation and equality law in
      `parsing/earley/kernel/forest/support/ambiguity.py` and its callers.
- [ ] Remove `another_meaning`'s single-flip claim. No public entry currently
      accepts its arbitrary `build` callable, but the internal contract is
      false. Replace it with the settled exact interaction mechanism; do not
      preserve the callable-shaped helper as pre-alpha compatibility surface.
- [ ] Generated-model products reproduce current model-value ambiguity
      semantics. Default IR uses the definitive complete reduced-root relation;
      enumerate and review differences from the superseded variant-model
      relation. Do not narrow acceptance through child-local comparison.
      `proto/island_continuation.py` supplies the first executable member of
      that enumeration: a document whose two derivations build different
      generated models but the same reducer value, refused by the shipped
      `reduce` and accepted by the root-value relation. Port it as a pinned
      §5/§8 divergence case.
- [ ] A narrower schema rejects derivations outside its language before meaning
      comparison. A projection identifies a discarded difference only when its
      declared meaning law says so.
- [ ] Compile three distinct family classes: authored arms, semantic
      quantified-nullable count choices, and ordinary extent splits. Only the
      last receives the leftmost allocation answer without target-meaning
      comparison. Do not infer the class solely from generated choice identity.
- [ ] Retain immutable completed-handle meanings from the default Earley
      derivation. For one alternate family, mark its completed owner and
      ancestors dirty, replay only that cone in a fresh isolated product state,
      and reuse unchanged sibling meanings. Never copy the base candidate's
      live builders/logs or its document-sized meaning memo: use a read-only
      baseline plus one sparse alternate overlay. **Precedence:** the exact
      per-node meaning-set relation over the dirty cone is the governing
      mechanism (`DESIGN.md` §Earley and islands); this single-alternate
      overlay replay is its permitted SPECIALIZATION, admissible only where the
      compiled completion operations carry the proved separability certificate
      — the same certificate one-flip evaluation needs and, absent it, does not
      have. Where the certificate is absent the per-node relation governs and
      no overlay is built. Index every predecessor key
      in a resolved completion chain to its owning completed handle; a packed
      choice can live in that
      column rather than at a direct child handle. Completion ranges are
      selected by completed code so contextual clones retain their own meaning
      operation. The verdict must equal a complete root refold on every witness;
      the dropping-parent case must remain accepted.
      `proto/root_meaning_incremental.py` measures three alternate fold bodies
      versus a 1,207-body baseline on the distant case; this is a
      semantic-operation count, not an eager-container allocation claim.
      `local_meaning_fold.py` is the rejected child-local counterexample.
      The predecessor/parent dependency index is proportional to the default
      derivation and is built once only after a real semantic-choice family;
      unambiguous and ordinary split-only parses allocate none. A dict-of-sets index is
      forbidden by `PROTOTYPE_10.md`'s measured memory growth.
- [x] **FLAT-INDEX RETAINED-LAYOUT PART CLOSED:** `proto/ambiguity_rss.py`
      proves default-family dirty-cone parity for CSR/forward-star parent and
      owner edges across the 2,000/8,000/32,000 ladder and a two-key
      shared-ancestor witness. The retained arrays cost 98–112 B per character;
      the external numbering/build transient costs 1200–1223 B per character
      and is released before retained pricing.
- [ ] Assign dense completed-handle numbers during production completion so no
      numbering dictionary survives. Include parent and owner edges required by
      every semantic family, not only the default derivation. Measure integrated
      numbering, index build, replay CPU, wall, and RSS; prove dirty-cone parity
      and cleanup. The retained external arrays do not prove this integration.
- [ ] Give sequence-like built-in accumulators an immutable persistent
      contribution meaning.
      Path-copy only dirty ancestors, identity-share unchanged branches, and
      compare them with an exact iterative structural walk which skips shared
      branches. A hash/digest may reject quickly but is never equality proof.
      Materialize the selected eager sequence once after ambiguity resolution.
      Exercise a large flat accumulation so ancestor
      replay does not hide an O(document)-per-alternate container rebuild.
      `proto/persistent_meaning.py` proves 18/33 visited nodes for changed/equal
      paths over 65,536 leaves and one final materialization. For map, IR, and
      tokenizer products, either prove an exact persistent meaning against that
      product's equality, duplicate, and order law or use and measure an exact
      isolated whole-result cold comparison; do not transfer the sequence
      result by analogy. Ordered trees and the incremental keyed treap are
      rejected for keyed products. An admitted custom target without exact
      shareable meaning uses the same honest fallback. Never move it onto the
      unambiguous path.
- [ ] Handle separate accepting root items explicitly: construct each complete
      root meaning once because no internal packed-family point contains that
      choice. With
      `resolve=`, PDA bails before target-state commit and Earley supplies the
      existing complete derivation pair to the resolver; only its chosen
      meaning materializes the final target product.
- [ ] Replace island-local ambiguity settlement with the planned alternate seed
      and outer continuation replay. An unambiguous island still splices
      locally; a second island meaning is substituted into isolated semantic
      replay from that occurrence to the root. The dropping-parent island
      witness must be accepted without whole-document reparse when its complete
      root meanings are equal. If they differ, refusal needs no reparse; only an
      invoked `resolve=` may construct the selected complete-document pair.
      Search sibling accepting items as well as
      internal ambiguity points. Multiple/nested seeds follow the proved
      interaction rule; never infer one-flip exactness from purity.
- [ ] Make the target equality walk iterative: the current recursive
      `same_value` overflows the interpreter stack near depth 1000, and deep
      meanings are ordinary under quantifier desugaring. `PROTOTYPE_10.md`
      reproduces the failure at pad 2,000.
- [ ] Exercise adversarial rollback: a failed PDA attempt, failed island, and
      unchosen ambiguity alternative must leave vocab/map entries, duplicate
      sets, and verdict order unchanged.
- [ ] Carry no ambiguity witness graph on a statically/predictively unambiguous
      path.
- [x] **EXTERNAL FRAME SHAPE CLOSED:** real seed and frame records allocate one
      child tuple per completion, shared only among seeds crossing that
      completion. The measured range is 144.2–446.4 B per completion and
      96.8–177.7 B per frame across depth, seed count, arity, and dirty slot.
      Reprice the landed records at §12; the Prototype 11 shared-depth figure
      remains rejected.
- [ ] Re-run the §5 property differential through `tools/guarded.sh` from this
      effort's `proto/` at this exit (the oracle is retained for exactly this)
      and record command and result in `reports/`.

Exit: PDA and Earley agree on acceptance, refusal, and chosen products without
retained shadow models. Unambiguous islands splice identically; ambiguous
islands replay through the enclosing product continuation and never settle at
their span or trigger unconditional whole-document recognition.

## 9 — derive target-aware parallel fragments

Entry condition: lift `parallel/orchestrate.py::split_model` and its request/
result typing off the current `IrNamedTuple` bound before implementing any
target fragment. `IrTokenizer` happens to satisfy that bound; recursive Python
`dict`/`list` does not, and no later bullet can compensate for the mismatch.

- [ ] Keep `SplitPlan`, cut certification, worker policy, replicas, and
      `MIN_CHUNK` in the existing parallel packages. Generic discovery remains
      for products which require it, but it is not an unconditional target
      pre-pass.
- [ ] Compile lower/upper route-anchor proposals for regular target regions.
      Use them to propose the shell and O(workers) entry cuts directly. Before
      submission, run a typed-hole shell through the same composed product and
      require its prefix, interstitial syntax, suffix, and exact
      lower/upper/route states to agree; certify every fragment's entry and exit
      during execution. An unavailable, escaped, reordered, ambiguous, or false
      anchor declines before work submission to the same sequential direct
      product. Do not run an all-mark/all-entry discovery pass before capturing
      the same high-volume syntax. Preserve the 0.001864 s shell-control result
      as a budget, then replace its stdlib stand-in with the production product.
- [ ] Give every concurrently hot compiled recognizer a physically distinct
      worker-owned pattern. Equal source sent repeatedly through `re.compile`
      is not a replica because the regex cache returns one mortal pattern.
      Keep cache distinction in cold binding; no worker branch enters runtime.
- [ ] Extend that ownership to every per-completion-hot shared object where
      measurement shows refcount traffic — the `ProductProgram`/`BoundProduct`
      flat operand and route tables are the same contention shape
      `parallel/replicas.py` exists for. The §12 ladder attributes any scaling
      loss to a NAMED object, never an aggregate.
- [ ] Generalize `parallel/orchestrate.py::Request` and execution around a bound
      product without narrowing the result to `IrNamedTuple`.
- [ ] Compile one `FragmentProduct[Carry]` per licensed target/split shape with:
      lower-rule entry, upper-schema entry, initial continuation, allowed exits,
      ordered verdict/deferred validation, and associative ordered join.
- [ ] Give vocab pieces the vocab-entry schema state and merge pieces the
      merge-item state. Do not reconstruct target state from text or model
      fields.
- [ ] Implement terminated, separated/envelope, routed-interior, and
      region-shell composition through product laws. Preserve source order,
      duplicate policy, and failure order.
- [ ] For routed-interior and region-shell shapes, suspend the coordinator's
      product at the certified hole with exact lower/upper/route state,
      capture/accumulator handles, extents, and resume position. Attach the
      joined direct carry and resume/finalize once; never parse a stand-in
      generated-model shell.
- [ ] Assign verdicts stable source/phase/declaration/serial keys independent of
      worker grouping. Prove carry, boundary duplicate state, deferred
      validation, and verdict merges associative over at least three fragments.
- [ ] Workers own disjoint state and never run root validation/finalization.
      The coordinator checks the state chain, joins once, validates once, and
      finalizes once.
- [ ] For merge fragments, normalize fragment-local source-order ranks while
      constructing the one coordinator-owned final rank index. Do not pre-scan
      every entry merely to assign worker rank bases and do not retain a dyad
      tuple sidecar.
- [ ] Keep generated-model reconstruction in `parallel/stitch/model.py` as the
      generated-model product's composition implementation — DECIDED, not
      optional: migrating it into the common fragment vocabulary is not
      attempted in this effort (an optional consolidation at phase 9 of 14
      would not happen and must not linger as an open choice).
- [ ] Do not copy `stitch/model.py`, add `DirectCarrier`, or adopt the rejected
      `stitch/carrier.py`.
- [ ] If composition cannot be proved, run the same direct product sequentially
      from the start. Never perform partial work and then parse/fold again.
- [ ] Re-run the §5 property differential through `tools/guarded.sh` from this
      effort's `proto/` at this exit — the last fresh-input comparison before
      §10 deletes the oracle — and record command and result in `reports/`.
- [ ] After coordinator review of sequential/parallel parity and fragment laws,
      create the §9 checkpoint commit and resume the same warm Terra agent.

Exit: every supported split shape returns the same target/refusal as sequential
execution; unsupported shapes execute exactly one sequential direct product.

## 10 — delete superseded source before profiling

This phase is mandatory. “Unused but retained” is failure.

- [ ] Delete `src/lexic/compile/reduce/fold.py` and `ReduceFold`.
- [ ] Delete `_ReduceEntry`, `_reduce_entry`, reduction-only
      `_variant_artifact`, and `_sub_run` from `compile/artifact.py`; replace
      generally useful seams with final product names/owners.
- [ ] Delete obsolete `ReduceDerivation`, `FoldPlan`, `RunSpec`, `SubRun`,
      channel/binding evaluators, and reduction-only helpers from
      `compile/reduction.py`. Move only proven generally useful transforms.
- [ ] Delete the reduction-specific public surface of `compile/reduce/variant.py`
      after occurrence composition owns it. Remove `compile/reduce/` entirely
      if nothing final remains.
- [ ] Delete the old model-only fold/build records and helpers after all model
      callers use the product ABI. Retain only genuinely specialized final
      model operations, in their correct owner.
- [ ] Delete `MapShape`, `Template`, `Template.run`, `spanify`, the separate
      parse/extract architecture, and old span/skip fold machinery. Their
      capability survives as the two selection morphisms through the one
      `reduce` channel: `select(spec)` over decoded semantic keys
      (signature-bearing reducers) and `select_raw(entry, spec)` over raw-span
      keys (a compiled grammar with the compatible binding-derived map shape,
      §6). The public `MapShape` export disappears, but its needed private
      analysis has already moved to `compile/product/shape.py`. Port the toy-grammar templating test
      assertions to `select_raw`; delete only tests whose exact deleted symbol
      (`Template`, `spanify`, ...) is the subject.
- [ ] Delete committed target/model stitch duplication. Never adopt an
      untracked `parallel/stitch/carrier.py`; the user already deleted the
      rejected file, so do not reconstruct it.
- [ ] Remove every fallback, decline-to-old-route branch, old/new mode switch,
      compatibility adapter, deprecated alias, unused import, and dead cache.
- [ ] Port shared `foldkit` callers to the final vocabulary, then delete old
      helpers which have no caller. Account by name for `IrNamed`,
      `FOLD_SYMBOLS`, `seq`, `model_fold`, `first_rest`, `absent_tail`,
      `ABSENT`, `FIRST_REST`, and `DECODE_INT`. Do not delete the live
      notation/generated-self-grammar behavior or weaken its no-`eval` symbol
      channel.
- [ ] Keep `tokenizer_of` only as the already-reduced input API; remove any
      reader fallback through it.
- [ ] Search the complete tree for deleted names and old pipeline language:
      `ReduceFold`, `_ReduceEntry`, `_reduce_entry`, `DirectCarrier`,
      `CarrierComposition`, model-plus-fold, compatibility fallback, and the
      removed package paths. Every remaining occurrence must be a test oracle
      awaiting Luna's port or a work report, never shipped code/docs.

Exit: the production tree contains only the final architecture. The source
implementation is complete before any performance claim or handoff to Luna.

## 11 — general README and documentation pass

Do this after source cleanup so documentation describes the tree which actually
exists.

- [ ] Review and update root `README.md`, `src/lexic/README.md`, and every
      affected package README—not only files containing a deleted symbol.
- [ ] Add/readjust README coverage for the new `compile/product` and parsing
      product owners. Remove the `compile/reduce` README/package if deleted.
- [ ] Update at least:
      `.wiki/lexic/architecture.md`, `public-api.md`, `ir-shapes.md`,
      `parallel-parsing.md`, `tokens.md`, `flavour-system.md`,
      `invariants.md`, `testing.md`, `decisions.md`, `transpilation.md`, and
      `codegen.md` where the final design changes their claims.
- [ ] Add a `.wiki/log.md` entry for the significant knowledge change.
- [ ] Update `CLAUDE.md`'s exhaustive package map and annotations for
      every added, moved, or deleted source module.
- [ ] Update API docstrings and examples for `reduce(..., into=...)`, semantic
      signatures/schemas, `select({"key": KEEP})`, direct tokenizer reading,
      any custom codomain surface which actually passed §6, and MT behavior.
      Rewrite
      `getting_started/ex10_templating.py` and its README row to the final
      selection surface — `select_raw` keeps ex10's "works over any compatible
      map-shaped compiled grammar" story without requiring a reducer.
- [ ] Remove descriptions of model → `ReduceFold`, the separate templating
      parser, old build records, old stitch ownership, and old fallbacks.
- [ ] Review getting-started examples and public exports for one canonical path
      per task. Do not add a sugar API beside `into=`.
- [ ] After coordinator review of cleanup, documentation, examples, and package
      maps, create the §11 checkpoint commit. Terra's source work is then
      complete and the coordinator begins §12 profiling.

Exit: a reader starting from README/wiki sees the final architecture and can
find every public entry and owner without consulting this gitignored work
folder.

## 12 — external profile of Terra's complete source

- [ ] Confirm `git diff -- src/` contains only the implementation, never timing
      instrumentation.
- [ ] Use `tools/profile_tokenizer_path.py` and/or a new external tool under
      `tools/` or `zzz_current_work/260826-target-shaped-parse/proto/`; first
      prove observer/control equivalence.
- [ ] Run one benchmark process at a time. Announce and preserve a quiet window
      for every multithreaded row.
- [x] **PLANNING REQUIRED BEFORE §12 — WITNESS PART CLOSED:** retain the generic
      `DISTANT` grammar at pads 2,000, 8,000, and 32,000. It exposes linear
      completed-meaning and dependency populations while a distant alternate's
      replay cone stays constant. Run every scale/mode in an isolated process;
      record the input digest, GC state, semantic verdict, wall, process CPU,
      populations, and peak RSS. This is separate from the unambiguous
      tokenizer ceiling.
- [x] **PLANNING REQUIRED BEFORE §12 — CONTROL/FRAME PROTOCOL CLOSED:** the
      unambiguous control runs an existing fused PDA product, constructs no
      `ParseTree` or completed-handle meaning table. The current source has no
      candidate ambiguity factories to instrument, so zero-allocation is not
      claimed by the external control. Real frame pricing allocates one child
      tuple per completion and shares it only among crossing seeds. Lazy Leo
      expansion stays outside attributed structure windows.
- [ ] **PRODUCTION EVIDENCE REQUIRED BEFORE §12:** define unchanged
      baseline/candidate commands and run the landed ambiguity factories under
      the refusing fused-product control. The ambiguous row uses production
      completion-time numbering, every required family-aware edge, and asserts
      its semantic result. Measure integrated flat build, replay, cleanup, and
      RSS; the external retained arrays and allocator cannot prove future source
      wiring. Do not improvise corrections inside the benchmark window.
- [ ] Do not use `tools/benchmark/compare.py` unchanged for MT rows: its worker
      cohort is prepared concurrently, and preparation performs real parses.
      Prepare, warm, time, and close one entire baseline/candidate/control
      process before starting the next, alternating their order.
- [ ] For structural changes, alternate separate baseline/new processes and
      carry a byte-identical control row as `docs/STYLE.md` requires.
- [ ] Measure Qwen general JSON recognition and composed tokenizer recognition
      separately from target construction/finalization.
- [ ] Measure default IR, Python JSON, extent, and ready `IrTokenizer` with
      their own cost accounts; do not apply one codomain's multiplier to
      another.
- [ ] For the tokenizer, report resident `read(text, ...)`, cold
      `read_from_path`, and warm `read_from_path` separately. Re-measure the
      `0faa7289` baseline rows in the SAME alternating session as the
      candidate — §0's own rule; the quoted 17.203148 s / 17.416359 s
      constants remain provenance, never the comparison denominator. Do not
      add an isolated source-read median to a resident product and call the
      sum a measured path.
- [ ] Measure tokenizer 1/2/4/8/16-worker ladders one at a time and include every
      eligible split shape. Keep the 2 KiB floor.
- [ ] Attribute route proposal, composed shell/fragment certification,
      capture, join/rank normalization, tokenizer-index freeze, smaller fields,
      root validation, and record/pipeline finalization separately. Confirm the
      target fast path does not also run complete generic region discovery.
- [ ] Compare shared and physically worker-owned compiled recognizers in the
      landed implementation; identity-check the patterns so the regex cache
      cannot make a nominal replica row shared.
- [ ] Record wall, aggregate process CPU as core-seconds AND per byte, source
      bytes, decoded bytes, constructed objects/containers, final table sizes,
      peak RSS against the §0 baseline, garbage-collector state, and semantic
      witness equality — CPU per byte is a gate quantity beside wall in every
      row, so an MT row cannot pass by burning cores unreported.
- [ ] Measure peak RSS for the planned ambiguous-input row. Report the default
      meaning memo, flat dependency-index nodes/edges, alternate overlay, and
      actual island seed/trace populations beside peak RSS. This row is
      separate from the unambiguous tokenizer ceilings and is the cost account
      for §8's document-sized cold ambiguity structures.
- [ ] On production ambiguity machinery, report exact-lane reducer
      applications, `same_value` comparisons, route length, failed marked
      nodes, baseline-family cache hits, and family-chart build cost. Include a
      real unambiguous document, a real ambiguous document, and a shipped-
      grammar census of wide-multiplicity nodes which actually become dirty.
      Prototype 16's four witness/lift applications and three-node control are
      not production cost measurements.
- [ ] Gate less than 1.000 s wall for the resident-text ready tokenizer at the
      public `cores=AUTO` engaged shape on the 11,422,654-byte Qwen3 witness,
      with the sequential row reported beside it. When route anchors decline,
      report the sequential row, CPU-per-byte, whether any work was submitted,
      and named attribution; the declined row is diagnostic and is not gated
      against the engaged `<1.000 s` envelope. Pursue less than
      0.100 s wall for the complete reduced recursive Python product and
      report its multiplier against the current route as its gate quantity
      (`goal.md`'s ruling — 0.084940 s `json.loads` makes the absolute number
      a frontier, not a floor for pass/fail). Continue toward roughly 105x for
      the Qwen tokenizer scenario, but do not make that multiplier a universal
      gate on other reductions. For every scenario, publish current and new
      wall, process CPU, RSS, and multiplier. If a target is missed, attribute
      and optimize remaining recognition, decode, final-table, allocation, and
      RSS costs rather than hiding work or falling back.
- [ ] If the implementation regresses or duplicated work remains, return it to
      Terra. Do not send it to Luna until the source design and numbers are
      acceptable.
- [ ] Write the profile report under
      `zzz_current_work/260826-target-shaped-parse/reports/` in the existing
      numbered/report style.

Exit: the user receives real numbers for the completed implementation before
test-authoring handoff, with no simultaneous benchmark contamination.

## 13 — Luna ports/authors tests and owns all linting

- [ ] Luna reads `context.md`, `goal.md`, `DESIGN.md`, this TODO, Terra's report,
      and the full source diff before writing tests.
- [ ] Mirror every new/moved source module under `tests/unit/lexic/`.
- [ ] Port assertions from deleted reduction/model/template tests to the new
      owners. Delete only tests whose exact public/internal symbol disappeared;
      preserve the behavior they defended.
- [ ] Consume the §5 frozen semantic/refusal goldens explicitly. Port fixed
      corpus cases to deterministic direct-product value/refusal tests. Retain
      the fresh-input generators in
      `tests/property/lexic/test_reduce_differential.py`,
      `test_reduce_differential_abnf.py`, and
      `test_reduce_differential_ebnf.py`; replace the deleted model+fold oracle
      in `reduce_differential_helpers.py` with surviving one-path invariants:
      deterministic repeated reduction, exact refusal contract, contribution
      order, and flavour grammar round-trip/canonical equality where defined.
      Do not replace generated coverage with only frozen examples, and do not
      retain `ReduceFold` as a test-only legacy oracle.
- [ ] Add semantic-signature tests proving native/GBNF/ABNF/EBNF formulation
      independence and mismatched-signature refusal.
- [ ] Add product-op ABI tests for typed captures, route tables, decode,
      validation, sequence/map accumulation, root finalization, and raising
      defaults.
- [ ] Add transactional tests for nested builders, PDA attempts, island
      failure, Earley alternate isolation, duplicate rollback, and verdict
      rollback/order.
- [ ] Add Python JSON differential tests against its declared semantics:
      nested maps/lists, fractions, escapes, duplicates, empty values, and
      malformed input.
- [ ] Add tokenizer schema tests for key order, escape-equivalent and duplicate
      keys, extension fields, wrong types, missing fields, unsupported knobs,
      added-token flags, normalizer/pre-tokenizer recursion, malformed discarded
      values, syntax-versus-semantic precedence, and final-table equality.
- [ ] Add real tokenizer differentials for Qwen, GPT-2, SmolLM2, and Gemma; use
      fetched fixtures and preserve skips when absent.
- [ ] Add the `select` contract tests: declaration order, absence, retained
      value identity, decoded/escape-equivalent duplicates, shape verdicts,
      syntax-first precedence, and every §6 empty-edge ruling (`select({})`,
      non-KEEP/non-mapping leaves, non-mapping root, empty vocab/merges).
- [ ] Add the `select_raw` contract tests, porting the toy-grammar templating
      assertions: raw-key selection over a reducer-less grammar in one parse,
      declaration order, absence, extent certification with no value
      materialized, raw-duplicate refusal at selected levels only,
      escape-twin distinctness, syntax-first shape verdicts, demand locality,
      exact model/extent result typing, zero route-added grammar arms, the
      caller resolver seeing genuine authored ambiguity only, and
      native/GBNF/ABNF/EBNF formulation agreement.
- [ ] Pin `TargetRefusalError` as the intentional pre-0.1 tokenizer-reader
      semantic failure: test its ordered verdict payload, syntax-first
      precedence, and the absence of an `UnsupportedConstructError`
      compatibility adapter.
- [ ] Exercise tokenizer indexes through direct parse, public construction,
      notation, payload readback, generated modules, segmentation-tokenizer
      binding, encoding registry, and concretization. Assert exact item order
      directly before and after every fixpoint; mapping equality/hash is not an
      order oracle. Include noncanonical public/readback input and prove it is
      ordered once.
- [ ] Add committed extent-target tests — the only codomain otherwise without
      a committed-test row: certified bounds, the declared validity contract,
      and refusal shapes.
- [ ] Add binding-registry lifecycle regression guards: concurrent cold bind
      compiles once, eviction recomputes equivalently, a bound program retains
      no source artefact, a pool-retained program stays valid after release,
      and derived caches release transitively — the design's hardest
      concurrency claims must not remain Terra-side one-time witnesses.
- [ ] Add ambiguity tests for equal/different target meanings, dropped child
      meaning, schema-rejected alternatives, and permitted split families.
      Cover a choice owned by a predecessor-column key, contextual completed
      codes with different operations, unchanged root siblings, separate
      accepting roots, a deep iterative comparison, and a large flat persistent
      accumulation whose selected eager product materializes once.
- [ ] Add `FragmentProduct` tests for entry/exit state, associative ordered join,
      deferred validation, duplicate/failure order, root-finalize-once, every
      supported split shape, and sequential decline without submitted work.
- [ ] Retain the freethreaded fork-safety regression:
      `tests/integration/lexic/concurrency/test_fork_safety.py::test_a_retained_pool_does_not_prove_a_split_engaged`.
- [ ] Add performance/invariant tests which prove discarded values allocate no
      model/IR product and no route performs direct plus superseded work. Keep
      timing thresholds robust and run property tests through `guarded.sh`.
- [ ] Run `tools/auto_fix.sh`; Luna owns any resulting formatting/import edits.
- [ ] Run targeted tests while iterating, then:
      `uv run python tools/check_generated.py`, `tools/run_examples.sh`, and
      `tools/run_checks.sh`.
- [ ] Run the full suite with the prescribed memory guard where applicable.
      Never raise a committed Hypothesis `max_examples`.
- [ ] If Luna finds a source defect, Luna reports it and stops. Resume Terra for
      the source correction, rerun the external profile against that exact
      source tree, then return to Luna. Terra and Luna remain sequential.
- [ ] If formatting changes `src`, inspect the change and rerun the external
      profile before accepting the final gates; measurements must describe the
      exact source which will be committed.
- [ ] Recheck the documentation against any post-profile source correction and
      rerun doc-drift before handoff.
- [ ] Write the test/lint report under
      `zzz_current_work/260826-target-shaped-parse/reports/`.

Exit: all tests, formatting, lint, pyright, examples, generated checks, and the
done-gate pass on the complete cleaned/documented source.

## 14 — coordinator final review, squash, and push

- [ ] Review the complete staged and unstaged diff; preserve unrelated user
      changes.
- [ ] Verify no new forbidden forms in added lines:
      `Any`, `object`, `eval`, `exec`, `type: ignore`, `noqa`, pylint disables,
      or other suppression.
- [ ] Verify no grammar/tokenizer/Qwen hardcoding in generic compile/parsing
      code and no target branch in the character/item loop.
- [ ] Verify source, tests, package READMEs, wiki, public exports, and exhaustive
      package maps agree.
- [ ] Verify every deletion in §10 and every acceptance item in `goal.md`.
- [ ] Verify Terra's performance report and Luna's test/lint report correspond
      to the exact tree being committed.
- [ ] Squash the reviewed checkpoint series into `main` after all gates. The
      coordinator alone performs integration; add no `Co-Authored-By`.
- [ ] Push the squashed result under the active user grant and report the final
      commit, measurements, and gates.

Done means the final tree has one target-shaped parser product and none of the
superseded reduction/template/carrier implementation—not merely that a faster
branch exists.
