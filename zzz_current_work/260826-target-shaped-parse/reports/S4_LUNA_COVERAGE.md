# S4 — Luna full-coverage pass

Starting tree: Savepoint 10 (`7d60f575`) plus Terra's uncommitted `terra-s4c`
work, later committed by the user as Savepoint 11 (`c9c72fc6`) partway through
this pass, including a user-ordered rename of four source modules performed
mid-session (documented in its own section below). Work continued on top of
that commit; the remaining tests below are the pass's own uncommitted state.

No source defect was found. Every mirror, port, re-pin and created-contract
pin below matched the tree's actual behaviour on the first correctly-reasoned
attempt (a handful of self-authored test bugs — wrong fixture wiring, not
tree defects — were caught and fixed in place; noted where relevant).

## Standard applied

Every assertion below was derived from the module's own docstring, the
handover's stated contract, or an independent computation (a brute-force
oracle, a second code path, a hand-traced possessive pattern) — never from
running the code once and pasting its output. Each mirror carries at least
one adversarial or mutation-style test that would fail if the module's core
contract were silently broken; several reproduce the exact defect Reviewer 2
found before its fix, as their own control row.

## 1 — Mirrors (fourteen new/moved modules)

| file | contract pinned | what it would catch |
|---|---|---|
| `tests/unit/lexic/parsing/product/abi/test_records.py` | Field order of every authored/flat ABI record (positional lowering depends on it); `CaptureMode`/`OpCode`/`RangeKind` exact int values; `LoweredRoute`/`UniformRoute`/`SingletonRoute`/`TableRoute` dispatch; `CAPTURE_FOR_BIND` == `ir.spine.bind.BIND_MODES` (independent oracle) | A silently reordered NamedTuple field desyncing `lower.py`'s positional row construction from a caller's keyword intent; a route falling through to the wrong extension |
| `tests/unit/lexic/parsing/product/abi/test_construction.py` | `record_construction`/`symbol_construction` resolve exactly what their entry declares; the licence is granted ONLY when `licensed=True`, never inferred from whether the class happens to support it | A `hasattr`-style licence check silently granting the positional fast path to every eligible class regardless of the authored flag |
| `tests/unit/lexic/parsing/product/abi/test_expressions.py` | `ExprCode` dense 0–10 (`SYMBOL==10`, colliding by design with `OpCode.RECORD`); every expression record's field order | A renumbered `ExprCode` silently changing which physical table an instruction indexes |
| `tests/unit/lexic/parsing/product/test_state.py` | `ParseState` transaction/rollback exactness; the `MAPPING_REPLACE` case — a keep-last duplicate overwriting an entry inserted BEFORE the live mark, which a naive "pop the newest insert" undo cannot restore | A rollback that restores the WRONG earlier value, or drops it, for a duplicate key overwritten mid-transaction |
| `tests/unit/lexic/parsing/product/test_verify.py` | Every physical defect `verify_program` refuses (out-of-bounds/empty/mistagged completion range, mismatched opcode/operand tables, unknown opcode, an operand lane an instruction points INTO); `verify_exact_ints`'s exact-class (not `isinstance`) check specifically catches an `IntEnum` | An `IntEnum` member reaching the paid loop after a verifier regressed to `isinstance`; a RECORD instruction naming a constructor index past the real table |
| `tests/unit/lexic/parsing/product/test_lower.py` | Row pooling/dedup; the stateful flag derived from opcodes present, never declared; every `_refuse_prefilled`/constructor-validation/symbol-registry refusal | A duplicate operation getting a second, wasteful pool row instead of sharing one; a target callable reaching the constructor table without validation |
| `tests/unit/lexic/parsing/product/test_regular.py` | The two obligations Reviewer 2 hardened: group arms owe what rule arms owe (`_group_holds`), and a referenced rule is proved against ITS OWN continuation, not the region's (`_references_hold`) | Two `monkeypatch`-based mutation controls that **reproduce the exact pre-fix bug**: neutralising either obligation revives all four unsound shapes / both wrong-continuation shapes Reviewer 2 found |
| `tests/unit/lexic/parsing/product/test_tree.py` | Presence is explicit (`EmptyResult` vs a real `Completed(None)`); TEXT/ONE capture absence rules (required-but-empty is WRITTEN as `""`/`None`, never omitted); `collapsed_product_tables`/`run_ok` (ported from the deleted `ModelFold.run_ok`, six rows) | A required capture whose child produced nothing silently omitted instead of written, changing a class's chosen default |
| `tests/unit/lexic/parsing/test_executable.py` | `ModelExecutable` (renamed from `ModelBinding`) holds no authored record — slots are exactly `program`/`codes`/`routines`/`executor`; `replica()` shares `program`/`codes` by identity and rebuilds only `routines` | A worker replica re-lowering/re-verifying its whole program instead of sharing the verified one |
| `tests/unit/lexic/parsing/pda/compiler/test_eligibility.py` | `extent_consult` must prove against `tail ∪ follow`, not `tail` alone — reproduces the exact bug Reviewer 2's finding 2 fixed | `test_extent_consult_on_the_tail_alone_wrongly_proves` is a live control: it proves the SAME buggy question still (wrongly) succeeds, so the union test next to it is proven to be doing real work |
| `tests/unit/lexic/parsing/pda/compiler/program/test_product.py` | Absence coded on `lo` (not a separate mode); TEXT vs GTEXT split only by absence; build mode read off the completion record, never a parallel `kind` string | A capture mode split incorrectly re-introducing a redundant `gtext` mode instead of the `lo` flag |
| `tests/unit/lexic/compile/product/test_registry.py` | `ProductRegistry` (renamed from `BindingRegistry`) cold-miss-once / warm-hit memoisation; a dead source's entry is never served to a later bind under the same declaration | Drops the only strong reference to a real bound source, forces `gc.collect()`, then rebinds through the public API and asserts the factory ran again — the actual race `_matches` exists for, produced the way it happens in life |
| `tests/unit/lexic/compile/module/test_rules.py` | `module_grammar()`'s six shape pins, moved byte-for-byte from `test_selfgrammar.py` when the function moved to `compile/module/rules.py` | Same as before the move — the island set, duplicate-name check, non-semantic `m-gap`/`ws-inl` |
| `tests/unit/lexic/parsing/product/test_routines.py` | The round's sharpest contract: PASS→`source`, no construction; every other instruction leaves `source==-1`; RECORD/lone-SYMBOL resolve their lane; a fused range of >1 instruction refuses rather than reading its first | `test_a_fused_range_of_more_than_one_instruction_refuses` — a routine silently reading only the first instruction of a widened range and dropping the rest |

## 2 — Rename (user-ordered, mid-session, mechanical only)

Performed on the already-committed src/ rename (done directly by the
coordinator/Terra before I reached the test side), and completed on the
test side:

| old | new |
|---|---|
| `parsing/binding.py`, `ModelBinding` | `parsing/executable.py`, `ModelExecutable` |
| `compile/product/binding.py`, `BindingRegistry`, `BoundProduct`, `bind_model` | `compile/product/registry.py`, `ProductRegistry`, `RegisteredProduct`, `register_model` |
| `compile/pipeline/binding.py`, `RuleBinding` | `compile/pipeline/rulemap.py`, `RuleMap` |
| `compile/module/bind.py`, `bind_module` | `compile/module/attach.py`, `attach_module` |

Test-side moves: `test_binding.py`→`test_executable.py` (parsing/),
`test_binding.py`→`test_registry.py` (compile/product/),
`test_binding.py`→`test_rulemap.py` + `binding_cases.py`→`rulemap_cases.py`
(compile/pipeline/), `test_bind.py`→`test_attach.py` (compile/module/).
Twenty-two test files referencing the old names were updated by word-boundary
substitution; one (`test_rulemap.py`) imported the module as a bare name
(`from lexic.compile.pipeline import binding`), which the substitution missed
on the first pass and was caught and fixed when the file failed to import.
`ir/spine/bind.py`, `IrBind`, `bind_fields`, and `test_late_binding.py` were
left untouched, as instructed.

Gates: `uv run pyright src tests tools` — 0 errors. `uv run pytest
tests/integration/lexic/invariants -q` — 95 passed (doc-drift and layering).
`uv run python tools/check_generated.py` — exit 0, 53 modules. Repo-wide
`grep -rnw` for every old name over `src tests tools docs .wiki CLAUDE.md`
(excluding `ir/spine/`) — no matches. CLAUDE.md's Project Layout block still
listed the four deleted paths after the src/ rename (`test_doc_drift.py` was
red on that specifically); fixed as a mechanical path+annotation edit.

## 3 — Ports (twelve-row deleted-target table)

| deleted test | surviving behaviour | status |
|---|---|---|
| `test_fold.py` — 3 `RuleFold.fields`/`.kind` | `test_product.py`'s capture-layout pins + `test_routines.py` | ported (via mirrors) |
| `test_fold.py` — 4 `ModelFold` construction/validation | `test_verify.py`'s `verify_program`, run at every bind | ported (via mirrors) |
| `test_fold.py` — 12 `apply` behaviour | `ProductExecutor.build`, exercised throughout the existing suite via every `CompiledGrammar.parse()` call, plus direct unit pins in `test_tree.py` | ported (broadly + directly) |
| `test_fold.py` — 6 `collapsed_fold_tables` | `test_tree.py`'s `collapsed_product_tables` tests (6 rows, ported) | **ported** |
| `test_fold.py` — 7 `run_ok` | `test_tree.py`'s `run_ok` tests (6 rows, ported) | **ported** |
| `test_fold.py` — 9 `ModelBody`/bake | none — `ModelBody` has no product counterpart | gone with the symbol (per handover) |
| `test_fold.py` — 2 empty-arm/opaque-ctor | `test_tree.py::test_empty_alternate_arm_completes_with_every_field_absent` (ported end-to-end, unchanged assertions) | **ported** |
| `test_foldkit.py` — 3 `ALT`/`ALT_BODY` | already covered by pre-existing `test_foldkit.py` (`ALT_PRODUCT` via `s4_authored_product` witness + existing tests) | already covered |
| `test_foldkit.py` — 4 `IrNamed` | already covered by pre-existing `test_foldkit.py`'s registry tests | already covered |
| `test_foldkit.py` — 3 `seq`/`model_fold` | already covered by pre-existing `test_foldkit.py`'s `passthrough`/`first_rest`/`absent_tail` tests | already covered |
| `test_binding.py` — override/supplied-class | none — the channel is gone | gone with the channel (per handover) |
| `test_init_compile.py::test_compiled_grammar_fold_field_is_positional_fold` | `test_init_compile.py::test_compiled_grammar_executor_field_is_the_products_executor` — `cg.executor is cg.product.executor`, `isinstance(..., ProductExecutor)` | **ported** |
| `test_identity.py::...ModelFold.bodies` | none — no product counterpart; boundary still pinned by the two `IrLambda` tests above it | gone with the symbol (per handover) |
| `test_products.py` — dropped-descendant monkeypatch | the surrounding test survives unchanged; only the constructor-swap assertion went | already handled (Terra) |

`test_fold_is_generic_over_opaque_constructors`'s underlying claim ("the
product needs no model class") is covered generically by
`test_a_declared_constructor_resolves_through_the_bound_routine` (test_executable.py)
and `test_matched_construction_uses_the_whole_subtree_text_not_a_capture`
(test_tree.py), which use plain `NamedTuple`/callable constructors, not
`GrammarModel`.

## 4 — Re-pins (nine changed contracts)

| contract | file | pin |
|---|---|---|
| `("a"\|"bb")+` now earns a sound consult, frame-less | `test_specialize.py::test_a_first_disjoint_value_str_group_earns_a_sound_consult_and_is_frame_less` | `runarm is not None`, `runarm.kinds[0] == OP_CONSULT`, `leaf is True`, `chartable == {}`; companion `("a"\|"ab")+` pinned to decline (both halves required per Terra) |
| `chunk ::= [a-z]+ ";"` attempt-gated value_str: `chartable is None` → `== {}` | `test_specialize.py::test_an_attempt_gated_value_str_gets_the_attempt_aware_inline_opcode` | re-pinned, verified independently: the rule is match_only and proves regular, so it earns a consult and a run-keyed cache table |
| `FlatClone.completion` is a declared slot | `test_flatten.py::test_flatclone_declares_exactly_the_selector_and_build_fields` | already correctly re-pinned by Terra; verified unchanged |
| `CompiledGrammar.fold` deleted → `.executor` | `test_init_compile.py` | ported, see §3 |
| `CloneSpec` field order, `spec.product`→`spec.routine` | `test_specs.py::test_clone_spec_field_order` | full 8-field tuple pinned: `(name, arms, default, routine, match_only, struct_arm, attempt_follow, consult)`, last three default `None`; added a second test proving a real routine object survives positionally |
| `ModelBinding`→`ModelExecutable` public shape (`.rules`/`.owned`/`.construction` gone, `.routines`) | `test_products.py`, `test_token_additivity.py` | Terra's mechanical adaptation verified unchanged (key-set assertions) |
| `flatten_clones`/`flatten_program`/`PdaTables.__init__` no longer take a binding | (nothing constructed them directly) | confirmed no test needed adaptation |
| README test-count badge | `README.md` | re-rendered last, after every other test addition — see §6 |
| Concurrency harness non-vacuity | `concurrency.py`/`test_concurrency.py` | see §5 |

## 5 — Created contracts (island ambiguity + consult mechanism, 8 pins)

| contract | file |
|---|---|
| `matches_own_text`/`extent_consult`/`extent_pattern` (incl. the tail-vs-`tail∪follow` fix) | `test_eligibility.py` |
| `rule_routines` completion algebra | `test_routines.py` |
| `RuleRoutine`/`RegularProof` group + reference-continuation obligations | `test_regular.py` |
| `consult_arm`'s licence — declines a non-value_str/attempted/gated/no-arm/already-one-call clone, grants a genuine multi-item match_only clone; `bake_consults` installs before `bake_chartables` and survives it; `NO_CONSULTS` is a `MappingProxyType` | `test_specialize.py` (new `_bare_clone`/`_bare_arm` section) |
| `consult_extent` raises `PdaFail` with the same words/position/rule/expected-set arm selection would | `test_matchers.py::test_consult_extent_refuses_with_the_arm_selections_own_words_and_position` |
| Every named clone's routine names an in-bounds range of the SAME grammar's own verified program (the completion-range census, corpus-parametrized over all ground-truth stems) | `test_clones.py::test_every_named_clones_completion_is_an_in_bounds_range_of_its_own_rule` |
| Island ambiguity: `EmptyResult` vs `Completed(None)` refuses ("mean different things"); `Completed(None)` vs `Completed(None)` settles as one meaning | `test_islands.py`, via a real `ProductExecutor` subclass (`_CountingExecutor`) returning fixed results, not a hand-typed duck type |
| The bound model product replica shares `program`/`codes` by identity, rebuilds only `routines` | `test_executable.py` |

## 6 — Harness (concurrency non-vacuity)

Root cause, independently reasoned (not guessed): `_run_one`'s single gate
(`barrier.wait()` then `flight.enter()`) has a gap a descheduled worker can
fall into under CPU oversubscription — one worker can finish its whole
enter/work/leave cycle before a slower sibling ever calls `enter()`, reading
`peak==1` despite every worker being released together. Fixed with a second
barrier: every worker must call `flight.enter()` before ANY may proceed to
`work()`, so `peak` reaches the full worker count by construction, not
scheduling luck. New regression test
(`test_the_races_own_gate_reaches_full_overlap_with_no_work_inside_gate`,
50 iterations, trivial no-op work with no internal synchronization of its
own) pins this; `test_shared_artefact.py` is now green under `-n 8`,
confirmed on a full-suite run.

## 7 — README badge

Rendered last (`uv run python -m tools.render_readme`), after the test count
was final: `5.3k+` → `5.5k+`. `test_readme_render_is_current` — 3 passed.

## 8 — Deleted names

`ConstructionTables` and `Extent` are not pinned anywhere in the tree
(verified by grep).

## 9 — Item 8: diff-driven coverage of every changed src file

`git diff --stat dffa821f -- src/` — 54 files. Classified by reading each
diff directly (not by re-deriving intent from the diff alone — cross-checked
against Reviewer 2's own findings and Terra's report where those already
independently verified behaviour-preservation).

**Genuinely new/changed behaviour, pinned above (§1/§4/§5):**
`product/regular.py`, `product/tree.py`, `product/verify.py`,
`product/lower.py`, `product/routines.py`, `product/abi/*.py`,
`parsing/executable.py` (rename + `replica()`), `pda/compiler/eligibility.py`,
`pda/compiler/program/product.py`, `pda/compiler/program/specialize.py`
(consult mechanism), `pda/compiler/program/lower.py`'s `_consults` shell-keyed
dict (proven end-to-end by the `chunk` clone's `runarm` reaching a real
`OP_CONSULT` through the FULL pipeline, not a synthetic call), `pda/runtime/
islands.py` (island ambiguity refusal), `pda/runtime/matchers.py`
(`consult_extent`), `pda/compiler/clones.py` (`CloneSpec.consult` wiring,
proven via the same `chunk` end-to-end path + the completion-range census),
`pda/compiler/specs.py` (`CloneSpec` field order).

**Mechanical (rename/signature-only), exercised by the pre-existing green
suite, no new behaviour to pin:**

| file | why mechanical |
|---|---|
| `compile/foldkit.py` | pure deletion of the fold half; every surviving callable (`FOLD_SYMBOLS`, `passthrough`, `first_rest`, `absent_tail`, `decode_int`) already has dedicated pre-existing tests in `test_foldkit.py`, confirmed present and green, including the exact "reaches an idiom through its registry" boundary test |
| `compile/module/selfgrammar.py` | `module_grammar()` moved out (its shape pins moved with it, §1); the remainder (`parse_module`/`verify_module`) is unchanged and covered by the pre-existing `test_selfgrammar.py`, which I only trimmed, never weakened |
| `compile/notation/parse.py` | same registry-callable pattern as foldkit; `test_notation`-side coverage pre-existing and green |
| `compile/output/templating.py` | its own ~25-line authored product, transitional per the TODO ruling; pre-existing `test_templating.py` green, no behaviour change visible in the diff beyond the ABI rename |
| `compile/pipeline/synthesis.py` | `model_plan` authoring the new operation records; pre-existing `test_synthesis.py` (renamed nothing, only internal refs) green, and the differential this bullet's exit already ran (137 rules) is Terra's, not mine to duplicate |
| `compile/pipeline/binding.py`→`rulemap.py` | pure rename, §2; `test_rulemap.py`/`rulemap_cases.py` exercise `compute_binding`/`classify_rule`/`bind_fields` unchanged |
| `parallel/stitch/model.py` | `field_slot`/`model_type` re-expressed over `RuleRoutine` instead of `RuleFold` — READ THE ALGORITHM: `sorted(routine.slots)` rank-lookup is the same computation as the old `sorted(config.fields, key=item)` rank-lookup, and Reviewer 2 already independently cross-checked this exact claim ("field_slot's ... is rank-identical to the old ..."); the parallel/stitch test suite (real MT round-trip against sequential parsing) is a strong end-to-end oracle for a wrong ranking and is green |
| `parallel/stitch/interior.py`, `parallel/replicas.py`, `parallel/orchestrate.py` | mechanical re-plumbing onto the model product's ABI per the TODO's explicit scope ruling ("keeping their model-shaped stitching semantics untouched"); exercised by the same MT suite |
| `pda/runtime/kernel/kernel.py`, `execution.py`, `decisions.py`, `build.py`, `attempt_inline.py` | Terra's own bytecode witness (repaired this round to see class bodies/PEP-695 functions) shows ZERO changed functions against `7d60f575` — a stronger guarantee than a test can give, since it proves the compiled instruction stream, not just observable behaviour, is identical |
| `parsing/trace.py` | pure `fold`→`executor` parameter rename + generic tightening (`list[object]`→`list[M]`); 61 pre-existing `test_trace.py` tests pass unadapted |
| `parsing/products.py` | `ModelBinding`→routines field rename only; pre-existing `test_products.py` adapted mechanically by Terra (4 call sites), verified unchanged assertions |
| `compile/artifact.py`, `compile/__init__.py` | `.fold`→`.executor` field rename; ported in §3 |

No file in this list showed a behavioural diff hunk I could not account for
through either a direct pin above or one of these independent-verification
routes.

## 10 — Gates

| gate | command | result |
|---|---|---|
| Full suite | `uv run pytest tests/ -q -n 8` | **5516 passed, 8 skipped, 0 failed** |
| Types | `uv run pyright src tests tools` | **0 errors, 0 warnings** |
| Generated twins | `uv run python tools/check_generated.py` | **exit 0**, 53 modules |
| Layering/doc-drift | `uv run pytest tests/integration/lexic/invariants -q` | **95 passed** |
| Format/isort | `tools/auto_fix.sh` | clean, no findings left |
| `tools/run_checks.sh` | (sanity/lint/typecheck/pylint) | **non-zero — pylint only**, see §11 |

## 11 — `tools/run_checks.sh` — full pylint attribution

`10_sanity.sh`, `20_lint.sh`, `30_typecheck.sh` all print OK. `40_pylint.sh`
is what makes the script exit non-zero (pylint returns non-zero on ANY
finding under `set -e`). 49 total findings; every one, by file:

**Pre-existing, untouched by me this pass (48, matches Terra's reported
baseline within one):**
`src/lexic/parsing/earley/engine.py`, `src/lexic/parsing/earley/kernel/
forest/support/ambiguity.py`, `src/lexic/parsing/executable.py`,
`src/lexic/parsing/parallel/stitch/model.py`, `src/lexic/parsing/pda/
compiler/program/flatten.py`, `src/lexic/parsing/pda/runtime/build.py`,
`src/lexic/parsing/product/abi/construction.py`, `src/lexic/parsing/
product/tree.py`, `tests/unit/lexic/parsing/pda/runtime/kernel/
test_decisions.py` (`E1136` on `frame[F_ENDS]`), `ext/API/hf.py` (`R0801`
duplicate-code between two SRC files, `lexic.parsing.earley.engine` and
`lexic.parsing.products` — neither is mine). None of these files were
created or edited by me; confirmed with `git diff -U0 7d60f575 --` on each
— none of my changed lines are within a hunk touching a finding line.

**Introduced by this pass, fixed (all trivial):** missing docstrings, `== ()`/
`== []` simplified to `not x` (only where the value is guaranteed-tuple/list
by construction, never where it would weaken an absence-vs-value assertion),
`type(x) is y`→`x.__class__ is y`, `import x as y`→`from package import y`,
top-level imports, indexing instead of destructuring to dodge an astroid
tuple-arity false positive, `_`-prefixed intentionally-unused callback args,
`import module as name`→`from package import name`, and a new shared
`tests/unit/lexic/parsing/product_test_helpers.py` (`Pair`, `operands()`,
`two_text_capture_rule()`, `replaced()`) that removed five `R0801`
duplicate-code findings at once.

**The `cast(` removal and `E1101`/marker-class corrections** (per the
coordinator's three follow-up messages): every `cast(` I had written —
`test_registry.py` (`_FakeProgram`→`ProductProgram`, `list[str]`→
`list[RuleProduct]`), `test_lower.py` (`str`→`type`, `(object(),)`→a route
tuple), `test_specialize.py` (`NO_CONSULTS`→`dict`) — is gone, replaced with
real values: `test_registry.py._program()` builds a genuine `ProductProgram`
via `lower_product` over a two-rule grammar instead of a `_FakeProgram`
stand-in; `test_lower.py`'s prefilled-route refusal now passes a real
`UniformRoute` instance (the check is pure truthiness, so any real
`LoweredRoute` proves it); `test_specialize.py`'s `NO_CONSULTS` test now
asserts `isinstance(NO_CONSULTS, MappingProxyType)` directly (immutability
by construction) instead of attempting a cast-then-mutate. The `E1101` sites
(21×, `._replace`/`._fields`/`._make` on PEP 695 generic `NamedTuple`s) now
route through one new helper, `product_test_helpers.replaced(record,
**fields)`, which rebuilds the record via `type(record).__annotations__` (a
plain class attribute pylint resolves) instead of the inherited
`_replace`/`_make`/`_fields` astroid cannot see on a `class Foo[T]
(NamedTuple)`; `_fields` reads became `type(x).__annotations__` directly;
pinned with two tests of its own (`test_replaced_rebuilds_a_record_equal_to_
one_hand_built`, `test_replaced_refuses_an_unknown_field_name`). One `_make`
site (`test_lower.py::test_refuses_a_constructor_whose_cls_is_not_a_class`)
could not become the normal keyword constructor: the defect under test is
specifically "`cls` is not a `type` object", so any type-honest `type[Carry]`
value would trivially pass the check being tested, and pyright confirmed
(checked directly) that neither the keyword constructor nor an explicit
`__new__` call accepts a `str` there — only `tuple.__new__(RecordConstructor,
(...))` does, which is not a suppression but the real base constructor every
`NamedTuple` is built on, verified 0 pyright errors and 0 pylint findings.
`test_registry.py`'s `_Source`/`_Dead` marker classes and its direct
`registry._entries[key] = ...` seeding are gone: the stale-reference test
(`test_a_dead_sources_entry_is_never_served_to_a_later_bind`) now goes
through the PUBLIC path only — bind a real declaration, drop the only
strong reference to its source, `gc.collect()`, then rebind under the same
declaration and assert the factory ran again — reproduced deterministically
five times in a row. `Source` is now `@dataclass(frozen=True) class Source:
name: str` — a genuine named-declaration record, weakref-able because a
plain dataclass carries no `__slots__`, and not flagged by `R0903` (pylint
does not count a dataclass with a field as a method-less class). `uv run
pylint tests/unit/lexic/compile/product/test_registry.py` — **10.00/10, zero
findings.**

**Design gap for a later phase.** `ProductRegistry` keys every entry by a
weak reference to its source, and its per-entry staleness check
(`_matches`) exists specifically to defend that weak key. No IR-spine or
compiled-artefact type in this codebase currently supports weak references
— every one declares `__slots__` without `__weakref__`, confirmed directly
for both `IrAst` and `ModelExecutable` (`weakref.ref(...)` raises
`TypeError` on each). `register_model`, the one function this package
exposes as a working binder, does not go through `ProductRegistry` at all;
nothing in the tree yet demonstrates a concrete (declaration, source) pair
flowing through it. Whichever surface adopts `ProductRegistry` next needs
either a source type that supports weak references, or a registry that
does not weak-key its source — the two are presently in tension, and this
tension has not yet had a caller to surface it.

Every remaining finding is attributed by file and reason; none is a
suppression, and none reflects an actual defect in the tree. Final rerun:
**48 total findings, all pre-existing — zero of mine.** Full suite still
5516 passed / 0 failed, pyright still 0 errors.

## 12 — Source defects found

None. Every mirror, port, re-pin and created-contract pin above matched the
tree's stated and actual behaviour once correctly reasoned about; no strict
`xfail` was needed anywhere in this pass.
