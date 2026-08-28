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

**OPEN USER DECISION (REVIEW_7 finding 10):** deleting templating for `select`
drops a reducer-free, `GrammarModel`-returning extraction capability that
worked over ANY compiled grammar (`template(compiled, shape, spec)` takes no
reducer; only JSON gains a semantic signature at §2). Options: (a) keep one
reducer-free extraction morphism in the new architecture (occurrence-demand
driven, `GrammarModel` or certified-extent codomain, no `SemanticSignature`
required) with `select` as the beginner surface over reducers; or (b) record
in `goal.md` that reducer-free grammar-native extraction is deliberately
dropped pre-0.1, rewrite ex10 as a JSON+reducer example, and delete rather
than port the toy-grammar extraction tests. §10's templating deletion and
§11's ex10 rewrite execute whichever the user rules; nothing else blocks on
it. Option (a)'s feasibility and exact contract are prototyped in
`proto/demand_selection.py` (`reports/PROTOTYPE_5.md` §6) — occurrence-demand
compiled into contextual clones, one parse per document, recognition-only
undemanded subtrees, a statically model-free extent variant — a feasibility
exhibit for the decision, not a decision.

This is the executable queue for `context.md`, `goal.md`, and `DESIGN.md`. Read
all three before touching source. Do not reopen settled architecture unless the
current code proves a stated contract impossible; report that proof instead of
inventing a bridge.

`TBD_after.md` is explicitly outside this queue. Do not begin its performance
and export follow-ups until every item here is complete.

## Working protocol

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
      `CLAUDE.md`/`AGENTS.md` package-map lines in the same phase (mechanical
      edit only), keeping `tests/integration/test_doc_drift.py` green
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
      alternating measurements and attribution; only the user's explicit final
      approval licenses it.
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

- [ ] Read, in order:
      `context.md`, `goal.md`, `DESIGN.md`, `docs/STYLE.md`,
      `.wiki/lexic/architecture.md`, `.wiki/lexic/decisions.md`,
      `.wiki/lexic/invariants.md`, `.wiki/lexic/public-api.md`,
      `.wiki/lexic/ir-shapes.md`, `.wiki/lexic/parallel-parsing.md`, and
      `.wiki/lexic/tokens.md`.
- [ ] Read the evidence:
      `zzz_current_work/260821-one-path/DEMAND_PROJECTION.md`,
      `zzz_current_work/260821-one-path/reports/i9_report.md`,
      `zzz_current_work/260821-one-path/reports/i23_report.md`, and
      `zzz_current_work/260821-one-path/reports/i24_report.md`.
- [ ] Run `git status --short` and preserve unrelated user work.
- [ ] Confirm that the direct-carrier commit and
      `src/lexic/parsing/parallel/stitch/carrier.py` are absent. The user
      deleted the untracked file; do not reconstruct it.
- [ ] Record the exact baseline commit and interpreter/build details in the new
      implementation report. Do not add a production timing seam.
- [ ] Before source edits, freeze the external baseline protocol and witness
      matrix: fixture hashes, environment/topology, public/direct engine route,
      requested/actual workers, engaged/declined split shape, result/refusal
      digest, cold compile/bind, cold first parse, warmed parse, opcode/capture
      counts, garbage-collector state per row, and product-table bytes.
      Production/acceptance rows run with the collector enabled; only rows
      with equal GC state compare (`reports/PROTOTYPE_5.md` §5 measures the
      +0.016948 s carrier delta); `src` never manipulates collector state.
      The baseline source remains reproducible
      from commit `0faa7289`; compare it later in alternating whole processes,
      not by trusting measurements from different machine states.
- [ ] Measure baseline peak RSS on the `0faa7289` tree in the §0 matrix —
      resident and cold/warm path rows — so `goal.md`'s "not above the
      baseline" RSS criterion is a recorded number before any candidate row
      exists. The only RSS figure in the record today is the prototype's own
      79–82 MiB retained-carrier increase, which is not a baseline.
- [ ] Inventory all callers before moving these symbols:
      `Reducer`, `ModelBody`, `ModelFold`, `RuleFold`, `fold_config`,
      `model_fold`, `derive_reduction`, `ReduceFold`, `Template`,
      `split_model`, `read`, `tokenizer_of`, and `IrTokenizer.from_merges`.

Exit: the report names the source baseline and every current consumer of a
surface scheduled to move/delete.

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
discipline, local meaning folds, GC delta) in `reports/PROTOTYPE_5.md`. No
production module was added merely
to discover the typing or performance model. The source implementation still
owes semantic differential, composed-shell certification, ready-tokenizer acceptance, and
paid-loop measurement gates; the prototypes do not claim them.

## 2 — add the declarative signature/schema vocabulary

- [ ] Extend `src/lexic/ir/reduction.py` with the strict declarative vocabulary
      for `SemanticSignature`, semantic sorts/events, `TargetSchema`, route
      classes, accepting/poisoned/recovery states, validation declarations, and
      meaning declarations.
- [ ] Keep this vocabulary as data on the IR spine. It owns no parser runtime,
      target-specific JSON declaration, mutable builder, or compile algorithm.
- [ ] Export the intended surface through `src/lexic/ir/__init__.py` and the
      relevant spine/package façades without introducing a second import path.
- [ ] Give every unknown event/action/schema construct a raising
      `UnsupportedConstructError` dispatch default.
- [ ] Implement the declared exception vocabulary exactly as `DESIGN.md`
      §validation records it: binding refusals, verifier failures, and syntax
      stay `UnsupportedConstructError`; raised semantic verdicts are the new
      `TargetRefusalError(LexicError)` over `SemanticVerdict` value records
      (never the bare name `Verdict` — `compile/verdict.py` owns it);
      `from_indexes` validation is `FieldValidationError`. Luna pins type and
      message against this declaration.
- [ ] Add the JSON semantic signature beside `JSON_REDUCER` in
      `src/lexic/grammars/json.py`: decoded null/bool/integer/fraction/string,
      array item/array, object entry/object, and completion. It contains no
      tokenizer field names.
- [ ] Bind the signature to the reducer through one real data channel. Do not
      create parallel registries keyed by reducer identity and do not infer
      semantic roles from grammar rule names.

Exit: native JSON and any compiled formulation using the same reducer expose
the same signature object; a mismatched target can be diagnosed before parse.

## 3 — introduce the engine-neutral product program

- [ ] Add the focused parsing-owned `src/lexic/parsing/product/` package:
      `records.py` owns immutable authored/flat ABI records, `state.py` owns
      parse-local builders and transactions, `verify.py` owns physical-table
      verification, and `__init__.py` is the one parsing-internal façade. Do
      not grow a monolithic product module or expose parallel import paths.
- [ ] Define the typed authored operation records, flat opcodes/tables,
      typed reducer-expression program, `CaptureSpec`, `RuleProduct`,
      `ProductProgram`, parse-local state, transaction marks, meaning contract,
      and fragment contract.
- [ ] Give every contextual PDA clone, Earley completion, token completion,
      attempt sub-clone, island, and delegate exactly one tagged completion
      range index. Verify its non-empty bounds and operand tables before
      execution; do not store parallel expression and fused fields.
- [ ] Convert every authored enum to an exact `int` during lowering. Assert the
      flattened rule, expression, and capture tables contain no `IntEnum`
      instances using `type(value) is int`, never `isinstance`; frequent
      completion dispatch compares/indexes plain ints.
- [ ] Lower an occurrence-scoped `RouteContinuation`; refuse a nullable or
      non-single-discriminator producer. In PDA frames store `(consumer
      position, route)` until that value occurrence successfully advances,
      with both integers under rollback. In Earley, route only producer
      completion through a sparse `(waiting contextual code, route) ->
      successor contextual code` table. The existing packed successor code is
      the filing/dedup identity; do not widen every item or touch ordinary
      `_advance_all`. The later forest fold cannot perform routing.
- [ ] Lower the producer's discriminator to direct scalar decode/classification
      at recognition-time completion. It must not call the general reducer
      expression evaluator or construct a model. Specialize the lookup by
      actual cardinality: uniform dynamic maps bypass it, singleton routes use
      direct equality, finite sets of two or more use a private dictionary
      lookup, and dense route ids index destinations without a tuple scan.
      Preserve the measured representation decision from `PROTOTYPE_3.md`.
- [ ] Run nested mapping witnesses through PDA, ordinary Earley fallback, and
      island/delegate execution. Outer and inner occurrences route
      independently, escaped-equivalent keys agree, and rollback/abandonment
      leaves no stale route for another attempt or member.
- [ ] Keep the parsing layer a leaf: imports may reach `lexic.ir`, never
      `lexic.compile`, `lexic.grammars`, or `lexic.api`.
- [ ] Lower operations to data. No target object or morphism is called from the
      character matcher, item loop, gate selection, or a frequent lexical
      completion.
- [ ] Keep the ABI capable of a closed cold/root constructor operation, but add
      no public custom callable/factory field and no custom operation at a
      frequent completion. The arbitrary-class public surface is gated in §6.
- [ ] Make `ParseState` parse-local and worker-local. Builders are owned by one
      occurrence handle in a dedicated typed frame lane; handles never widen
      or wrap `Carry`, and there is no global current collection.
- [ ] Allocate `ParseState` only for products with mutable builders or deferred
      verdicts. The generated-model product has no state allocation,
      transaction test, range-verifier call, generic instruction interpreter,
      or extra frame slot on its paid path.
- [ ] Implement mark/commit/rollback for speculative PDA work and island
      failure with constant-size marks and mutation-proportional undo. Measure
      valid and failed speculation across large retained builders. Commit a
      child to its parent only after successful completion.
- [ ] Give each actual competing Earley arm a fresh isolated `ParseState` and
      fold that candidate independently, matching the forest's existing
      alternate-build boundary. Do not clone live builders or mutation logs.
      Ordinary chart filing, prediction, nullable advancement, and split
      handling allocate no alternate product state; only the chosen candidate
      can reach root finalization.
- [ ] Make the Earley product fold execute each shared forest node's VALUE
      exactly once, guarded at fold entry, with occurrence-owned effects
      (appends, map inserts, verdicts, duplicate-set entries) applied from the
      parent's slot consumption so effect counts follow occurrences. The
      current walk's count is a traversal accident — `proto/
      shared_forest_refold.py` measures 2/2/1 fold-body executions for
      identical two-slot sharing across its three witness shapes
      (duplicate-slot, pending-frame, sibling-memo); all three shapes run
      through the Earley fallback as §3 exit witnesses with deterministic
      value-once/effect-per-occurrence counts.
- [ ] Define the lifecycle seam through the existing
      `parsing.caches.memo/track/adopt/release` protocol. Product programs and
      bound runners retain no source artefact; derived PDA/Earley/replica cache
      entries release transitively. Exercise explicit release, collection,
      concurrent first bind, and a pool-retained bound program after release.

Exit: the product ABI executes a tiny sequence/map target through actual PDA,
Earley, and island/delegate paths; occurrence routing selects the following
child during recognition; every physical execution table verifies one exact-int
completion range; rollback, fresh-alternate isolation, and cache release pass;
side-effecting completion is exactly-once per shared forest node with
per-occurrence effects across all three shared-subtree witness shapes;
and measured valid/failed speculation exposes no unaccounted frequent-path
branch, allocation, or whole-state copy. §4 remains closed until all of this
holds.

## 4 — migrate generated-model parsing onto the common ABI

- [ ] Start from `src/lexic/parsing/fold.py`. Re-express model field capture and
      construction as the generated-model specialization of `ProductProgram`.
- [ ] Delete `FOLD_KINDS`, `FieldFold`, `FastCtor`, `RuleFold`, `ModelBody`,
      and `ModelFold` after their callers move; do not preserve them as wrappers
      or generic-looking renames. Generated-model synthesis lowers directly to
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
      notation/generated-self-grammar caller, to the final vocabulary. Preserve
      `foldkit`'s authored-data role; do not fold it into runtime reduction.
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
      and item loops.
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

- [ ] Add `src/lexic/compile/product/` with the pinned layout (the sibling
      `parsing/product/` is pinned; this one is too): `signature.py` owns
      signature verification, `compose.py` owns lower × upper state
      composition, `demand.py` owns demand propagation, `lower.py` owns
      lower-action and operation lowering, `binding.py` owns the private
      bound-product registry/cache, `morphism.py` owns the public
      `ReductionMorphism` surface, and `__init__.py` is the one façade.
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
      binding registry. Bound entries use weak source references, lock-free warm
      lookup, double-checked serialized cold build, and no source retention by
      the result-only bound program; eviction must only cause equivalent
      recompilation. Adopt derived product/PDA/Earley/replica cache entries into
      `parsing.caches` release ownership and test concurrent first binding,
      explicit release, and a pool-retained bound program after release.
- [ ] Make that private artifact registry the sole cache of
      `(CompiledGrammar, morphism) -> BoundProduct`. `parsing.products` owns no
      second bound-product memo; `parsing.caches` owns only tables/replicas
      derived from the bound program, and a pool is an explicit lifetime owner.
- [ ] Update `CompiledGrammar.reduce` in `compile/artifact.py` to select a
      `BoundProduct`: omitted `into` returns `IrSelf`; supplied
      `ReductionMorphism[T]` returns `T`; `cores` reaches the same product.
- [ ] Give `reduce` the two exact overloads recorded in `DESIGN.md` and
      `reports/PROTOTYPE.md`, and give BOTH overloads the same `resolve=`
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
- [ ] After coordinator review of the differential report, create the §5
      checkpoint commit and resume the same warm Terra agent.

Exit: default reduction constructs its `IrSelf` during parsing with exact
current parity and no `GrammarModel` or `ReduceFold` on the executed route
(ambiguity-refusal divergences between the variant-model and value-meaning
relations are enumerated and attributed per `goal.md`'s ruling, not required
to be zero). The old oracle has no production caller and its last broad
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
      second route implementation.
- [ ] Implement poisoned schema states. A semantic mismatch records its ordered
      verdict, routes the remaining value/document through generic lower-syntax
      recovery, and defers raising until syntax succeeds.
- [ ] Implement full Python JSON as the shape-preserving witness: recursive
      Python scalars/list/dict directly, including declared fraction and
      duplicate behavior, with no generated or IR JSON tree.
- [ ] Implement the parser-certified extent target. State its validity contract
      in the result type; do not infer or scan delimiters.
- [ ] Prototype arbitrary-class construction as an immutable constructor symbol
      lowered through a private write-once, eviction-stable binding. If it
      requires a public callable/factory, mutable rebinding registry, bare
      reflection, or second executor, omit the optional custom-class surface;
      do not compromise the core architecture to keep it.
- [ ] Implement `select(spec)` as the finite nested-mapping morphism specified
      in `DESIGN.md`: declaration-ordered path results, absent missing paths,
      retained reducer values, recognition-only extensions, decoded duplicate
      refusal, and syntax-first nested-shape verdicts. Refuse an incompatible
      source signature at binding; do not add array/predicate sugar.
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

Exit: one compiled mechanism builds default IR, Python JSON, and extents with
their distinct semantics and costs. No target is a post-reduction mapper.

## 7 — implement the layered tokenizer product

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
      roles over one immutable mapping base: primitive `str -> int` encode,
      `int -> str` decode, and `(str, str) -> int` ranks. Encode/decode order is
      canonical by id and merges by rank. Validate and freeze an already
      canonical direct builder without sorting; order a noncanonical
      public/readback input once. Equal indexes must share hash,
      iteration/repr, notation, and payload order. Add the one final constructor
      `IrTokenizer.from_indexes`, accepting all three together. Direct parsing
      populates them together: no inverse derivation, rank re-index, repr-key
      sort, IR scalar/dyad per entry, or dyad list. Keep public encoding return
      types while using primitive internal lookups. Make
      `from_vocab`/`from_merges` converge on the same validation and
      record-construction tail. Update payload/notation/emission and every
      tokenizer field type for the new pre-alpha representation; retain no
      compatibility adapter to `IrMap` fields.
- [x] Before fixing that source layout, use the real Qwen cardinalities in an
      external prototype to compare pair-buffer/duplicate-set and indexed
      accumulators. `PROTOTYPE_4.md` rejects per-entry IR leaves at 0.346817 s
      and selects primitive tokenizer-index payloads. Both dominant regions
      through capture/join, canonical freeze, and actual tokenizer-record
      construction measure 0.138739 s at eight workers, with about 79–82 MiB
      first-run RSS growth. Re-prove rollback, payload/notation fixpoint,
      deterministic emission, and final semantic equality in source.
- [ ] Change `json_tokenizer.read`/`read_from_path` to use
      `compiled.reduce(..., into=tokenizer_morphism)` and return the ready
      tokenizer.
- [ ] Keep `tokenizer_of` for already-reduced documents. Ensure `read` never
      invokes it directly or on decline.
- [ ] Verify root finalization is independent of JSON object key order and runs
      exactly once.
- [ ] Implement the proved-regular capturing lowering as a gated task at this
      exit: a composed region the compiler proves regular — repeated entry,
      acyclic simple closure, no arm ambiguity — lowers to one capturing
      recognizer per entry with demand-derived positional groups over the
      rules' own pattern sources, no grammar-name case. Prove it identical to
      the generic product on the same region and gate it the way §4 gates the
      model path; a region losing the proof declines to the interpreted
      product. Mechanism, genericity (native + GBNF formulations), decline,
      and four-way identity are prototyped in
      `proto/regular_region_lowering.py`; the ~105x objective is contingent
      on this task, the <1.000 s envelope is not
      (`reports/PROTOTYPE_5.md` §§1–2).
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

- [ ] Replace any generated-model-only ambiguity hook with the product's typed
      `MeaningOp` and equality law in
      `parsing/earley/kernel/forest/support/ambiguity.py` and its callers.
- [ ] Default IR and generated-model products reproduce their current ambiguity
      semantics.
- [ ] A narrower schema rejects derivations outside its language before meaning
      comparison. A projection identifies a discarded difference only when its
      declared meaning law says so.
- [ ] Keep nullable/repetition split families separate from arm-choice
      ambiguity.
- [ ] Fold base and each alternate Earley derivation from a fresh isolated
      product state. Never copy the base candidate's live builders/logs.
- [ ] Root alternate meaning folds at the ambiguity family's differing CHILD
      subtrees with fresh local state — never a root-rooted whole-document
      refold per flipped point, and never a build from the packed point
      itself (it re-enters the parent chain and its dropping policies). This
      is what makes the design's "computes only the declared local meaning"
      true, prices ambiguity per point instead of n+1 full folds, and keeps a
      difference a dropping parent erases; mechanism, verdict table, and cost
      (4 folds versus 2,414 on a 601-char witness) are in
      `proto/local_meaning_fold.py` / `reports/PROTOTYPE_5.md` §4.
- [ ] Make the target equality walk iterative: the current recursive
      `same_value` overflows the interpreter stack near depth 1000, and deep
      meanings are ordinary under quantifier desugaring.
- [ ] Exercise adversarial rollback: a failed PDA attempt, failed island, and
      unchosen ambiguity alternative must leave vocab/map entries, duplicate
      sets, and verdict order unchanged.
- [ ] Carry no ambiguity witness graph on a statically/predictively unambiguous
      path.
- [ ] Re-run the §5 property differential through `tools/guarded.sh` from this
      effort's `proto/` at this exit (the oracle is retained for exactly this)
      and record command and result in `reports/`.

Exit: PDA, Earley, islands, and target projections agree on acceptance,
refusal, and chosen product without retained shadow models.

## 9 — derive target-aware parallel fragments

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
- [ ] Delete `MapShape`, `Template`, `Template.run`, `spanify`, raw-surface
      selection paths, the separate parse/extract architecture, and old
      span/skip fold machinery. Add `select(spec) -> ReductionMorphism[Selection]`
      over decoded semantic keys; it executes only through
      `CompiledGrammar.reduce(..., into=...)`.
- [ ] Delete committed target/model stitch duplication. Never adopt an
      untracked `parallel/stitch/carrier.py`; the user already deleted the
      rejected file, so do not reconstruct it.
- [ ] Remove every fallback, decline-to-old-route branch, old/new mode switch,
      compatibility adapter, deprecated alias, unused import, and dead cache.
- [ ] Port shared `foldkit` callers to the final vocabulary, then delete old
      helpers which have no caller. Do not delete live notation/generated
      self-grammar behavior.
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
- [ ] Update `AGENTS.md`/`CLAUDE.md` exhaustive package maps and annotations for
      every added, moved, or deleted source module.
- [ ] Update API docstrings and examples for `reduce(..., into=...)`, semantic
      signatures/schemas, `select({"key": KEEP})`, direct tokenizer reading,
      any custom codomain surface which actually passed §6, and MT behavior.
      Rewrite
      `getting_started/ex10_templating.py` and its README row to the final
      selection surface.
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
- [ ] Gate less than 1.000 s wall for the resident-text ready tokenizer at the
      public `cores=AUTO` engaged shape on the 11,422,654-byte Qwen3 witness,
      the sequential row reported beside it, and the sequential row gated
      against the same envelope when route anchors decline. Pursue less than
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
