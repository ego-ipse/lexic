# Log

**When to load:** checking what changed recently; orienting after a gap in the session.

Append-only chronological record. Most recent entry at top.

---

## 2026-07-03 — engine perf round 3 landed (Optimize.md, complete)

Full-grammar product on the disputed corpus (subset-920 self-emit): **25.6 → 17.25 µs/char** (−33%; **0.57× Lark** full-vs-full, was parity). Recognize ~8.0 µs/char. The two engine levers: **seed-layout** (Task 1 — `CodeTables.rule_seeds` stored as primitive seed-pairs, `_seed` dedup-free; kernel −15%, charts byte-identical) and **FIRST-gated prediction** (Task 2 — per-dot-0-arm `(dot0, next_sym, gate)` triples where `gate` is `None`=always-seed or a frozenset FIRST charset with nullable-prefix continuation; `_seed` gates on `text[i:i+1]`; charts deliberately NOT byte-identical, product IR equality + ambiguity counts verified across all suite grammars). Instance path got run collapse (Task 4, separate entry). Task 5 (comment skip-machine) killed — FIRST gating leaves comment noise at 4.8% of items (was 27%).

Consolidation extra: the memoised-collapse skeleton shared by `reduce.collapsed_tables` / `models.collapsed_instance_tables` / `lexruns.recognition_tables` is now **`lexruns.collapse_runs(grammar, run_mode)`** — grammar-side core shared, the licence (`run_mode: (tables, unit_rid) → mode | None`) injected as the policy half; memoisation stays per-caller. Official baseline: `tools/benchmark/bench_baseline.json` (`parse_bench.py --save`, dual workload). Suite 1364/0; `tools/run_checks.sh` (sanity+ruff+pyright+pylint over src+tests+getting_started) is the standing done-gate per user ruling 2026-07-03.

## 2026-07-03 — `IrRule.semantic` flag + repr default-omission + scanner dissolved (Optimize.md Task 6R)

Supersedes Task 6 (the move landed and is subsumed — the module dies from its new location). Three coordinated changes:

1. **Record repr omits trailing default-valued fields** (`IrNamedTuple.__repr__`, `ir/base.py`): walk fields from the end, drop while `self[i] == declared_default` (`==`, so `IrScalar` type-aware eq applies), stop at the first non-default or a field with no default. Still valid codegen. `IrItem(IrLiteral('a'), IrQuantifier(1,1))` → `IrItem(IrLiteral('a'))`. Landed first to absorb the golden churn once.
2. **`IrRule.semantic: bool = True`** (user polarity ruling: no negation in the attribute — a rule IS semantic by default; noise rules declare `semantic=False`). `IrRule.__eq__`/`__ne__`/`__hash__` exclude it (compile-channel metadata; the fixpoint rationale relocated here from IrAst). **`IrAst` dropped its `non_semantic` field and its Task-3 eq/hash override** — back to plain `(rules, start)` tuple equality, which composes `IrRule.__eq__` element-wise. `IrAst.non_semantic` is now a **derived property** (`frozenset(r.name for r in rules if not r.semantic)`), keeping the `@non-semantic` directive vocabulary though the flag polarity is positive. Consumers (`derive_specs`, `GBNF_NOISE`/`ABNF_NOISE`) unchanged. `hoist_helpers` preserves `semantic` through its rebuild.
3. **Scanner dissolved into `compile.py`**: `parse_directives` → private `_scan_directives`; `src/lexic/parsing/directives.py` + its moved test deleted (the Task-6 move subsumed). `compile_grammar` applies a directive by reconstructing each named rule with `semantic=False`. Flavours flag their noise rules `semantic=False` individually (18 ABNF, 2 GBNF); the `non_semantic=frozenset(...)` IrAst kwargs are gone. A directive naming an undefined rule is silently ignored (no rule flagged, so absent from the property — observably identical to before).

Fixpoints green (ABNF+GBNF equivalence 86/0). Expected test breakage (repr goldens + `IrAst(non_semantic=...)` 3-field constructions) enumerated for the Sonnet wave, not fixed by Opus. See [[ir-shapes]], [[flavour-system]].

## 2026-07-03 — `parse_directives` relocated `ir/` → `parsing/` (Optimize.md Task 6)

With the directive *content* now living on `IrAst` (Task 3), `parse_directives` is a pure pre-lexical text scanner — parsing-side machinery (the comment-channel sibling of `parse_grammar`'s Earley half), not node algebra. `src/lexic/ir/directives.py` → `src/lexic/parsing/directives.py` (content unchanged; module docstring reframed off "IR-level"). `compile.py` imports from `lexic.parsing.directives` (the models/normalize/reduce submodule-seam precedent). Dropped from `lexic.ir.__init__` exports. `parsing/__init__.py` deliberately does NOT re-export it — `compile.py` is the only caller. Test mirror: `tests/unit/lexic/ir/test_directives.py` → `tests/unit/lexic/parsing/test_directives.py`; `test_init_ir.py`'s export assertion inverted to `test_directives_not_exported`. Also see [[architecture]].

## 2026-07-03 — instance-path run collapse: `parse_first` gets collapsed tables (Optimize.md Task 4)

`CompiledGrammar.parse` now parses over run-collapsed instance tables. `models.collapsed_instance_tables(grammar, fold)` (memoised per (fold, grammar)) mirrors `reduce.collapsed_tables`, gated by the ModelFold licence `_instance_run_ok`: a proved run collapses iff its unit leaves carry no `RuleSpec` and no field wrapper (`<rule>--f<idx>`) — bare-terminal units always ok, looked-through synthetic layers safe. Kept runs are `RUN_STR` (text-preserving); a collapsed run lands as one multi-char `IrLiteral` leaf (via `FastTree.char_leaf`), which `_subtree_text`/`_direct_models` consume identically to the per-char expansion — so round-trip fidelity holds. `RunTerm.mode` is never read by the tree path (only by `FusedReduce`). `CompiledGrammar` gains a `tables` field (compiled once at build); the public `parse_first` grew an optional `tables=` arg; a fast-path miss re-parses plain, ParseReduced-style. Collapses arithmetic ×2 / json_arr ×1 / json_ws ×1 / c ×3; zero for list/chess/japanese. Bench (arithmetic, charclass-heavy): kernel −78%, end-to-end −69%.

## 2026-07-03 — `IrAst.non_semantic`: structural-noise fact moved into the IR (Optimize.md Task 3)

The "which rules are structural noise" fact now lives on the IR as `IrAst.non_semantic: frozenset[str]` (non-child payload beside `start`), a single declaration feeding `derive_specs`, `semantic_dump`, and the reducer's noise map.

- **`IrAst`** (`ir/nodes.py`) grew `non_semantic: frozenset[str] = frozenset()` (third field; type params now `IrNamedTuple[IrSeq[IrRule], IrStr, frozenset[str]]`). `__eq__`/`__hash__` are **overridden to compare only `(rules, start)`** — `non_semantic` is compile-channel metadata (like a source location), and excluding it is what lets the self-hosting fixpoint `parse_grammar(flavour.apply(GRAMMAR), flavour) == GRAMMAR` survive (a fresh parse carries `frozenset()` while the authored self-grammar declares a non-empty set). `repr` still renders all three fields (valid codegen). See [[ir-shapes]].
- **`Directives` dataclass deleted.** `parse_directives(text, line_comment)` (still in `ir/directives.py`, docstring rewritten off the stale Lark `%ignore` framing) now returns a plain `(start, non_semantic)` tuple. The scan stays **pre-lexical** — settled decision: in-parse capture would make comments load-bearing and block below-chart noise collapse.
- **`compile_grammar`** resolves precedence (explicit arg > directive > fallback) then **rebinds** the resolved `start` / `non_semantic` onto the parsed `IrAst` (frozen record → reconstructed).
- **`derive_specs(ast)`** lost its `non_semantic_rules` parameter; it reads `ast.non_semantic`. `hoist_helpers` preserves `non_semantic` through the rebuild.
- **Flavours:** the private `_NON_SEMANTIC` tuples are gone; `GBNF_GRAMMAR`/`ABNF_GRAMMAR` declare `non_semantic=frozenset({...})`, and `GBNF_NOISE`/`ABNF_NOISE` iterate `<GRAMMAR>.non_semantic` — one source of truth. (`grammars/json.py` needed no change; its `IrAst` defaults `non_semantic=frozenset()`.)
- Not touched: `ir/emit.py` `render_specs` (dead-shim removal flagged separately, out of scope); `src/lexic/parsing/` (owned by concurrent agents — its `normalize.py`/`models.py` `IrAst` construction sites rely on the `frozenset()` default).
- Tests to port (mirror rule): `test_directives.py`, `test_init_ir.py::test_directives_exported`, `test_derive.py::test_derive_marks_non_semantic_field_min_zero`, `test_nodes.py::test_repr_irast_is_codegen`.

## 2026-07-02/03 — Lark→Earley cutover landed (Phases 0–8, `PLAN_cutover_parsing_v2.md`)

`src/lexic/parsing/` (formerly `parsing_2/`) is now the **only** parsing implementation in Lexic — both grammar-text parsing and generated-instance parsing. The old Lark-backed `src/lexic/parsing/` (`meta_parser.py`, `lark_builder.py`, `transformer/`) is deleted outright; no `parsing_legacy`/`parsing_old` shim. `lark` is removed from `pyproject.toml` and `uv.lock`; it survives only as the fixed reference baseline in `tools/benchmark/parse_bench.py` (pure Lark, zero lexic machinery, raced against the native engine).

Key landed shape:

- **`IrFlavour` (`ir/flavour.py`) is R1: zero methods** beyond the inherited `IrEmitter` protocol. `parse_quantifier`/`parse_charclass`/`normalize_literal`/`meta_grammar` are gone, replaced by nothing (not even as free functions) — everything a flavour needs for parsing is IR action algebra + data tables inside a `Reducer`. New ClassVars: `grammar: ClassVar[IrAst]` (the flavour's own self-grammar, authored directly as IR — no meta-grammar string anywhere) and `reducer: ClassVar[IrDispatch]` (a `lexic.parsing.reduce.Reducer` at runtime).
- **`grammars/gbnf.py` and `grammars/abnf.py`** are single flat modules (no `gbnf/`/`abnf/` subpackages) carrying emit `actions`, self-grammar, reductions/noise map, escapes, and the singleton all in one file. GBNF gained a full self-grammar + reducer (Phase 2, previously Lark-only). ABNF's self-grammar was extended to full RFC 5234+7405 parity (Phase 3): `[...]` option, num-sequences (`%x0D.0A`), comments + line-folding, `%s`/`%i` string markers, `%d`/`%b` values, prose-refusal, incremental `name =/ body`.
- **`compile_grammar`** (`compile.py`) now runs `parse_reduced(normalize(flavour.grammar), text, flavour.reducer)` — the same Earley engine instance parsing uses — with a per-flavour-name memo (`_NORM_GRAMMAR_CACHE`) so `normalize(flavour.grammar)`'s object identity stays stable across calls (keeps the engine's `compile_tables` memo hot).
- **`CompiledGrammar`** (`compile.py`) fields are now `classes`, `specs`, `grammar: IrAst`, `fold: ModelFold` — no `parser`/`transformer`. `.parse(text)` runs `fold.apply(parse_first(grammar, text))`; `parse_first` is the engine's deterministic-first-derivation entry (parity with Lark's `ambiguity="resolve"` — some ground-truth instance grammars, e.g. `json_ws`'s `int`, are genuinely ambiguous).
- **`parsing/models.py`** (new): `specs_to_grammar` reconstitutes derived `RuleSpec`s into an instance `IrAst`; `ModelFold` replaces `build_transformer`, folding a `ParseTree` into `GrammarModel` instances via an explicit-stack bottom-up walk (no recursion).
- **Engine gained `IrNot` support** (Phase 0 prerequisite — negated character classes, needed by 4 of the 7 ground-truth GBNF grammars and by GBNF's own self-grammar).
- **`tests/integration/test_{gbnf,abnf}_ir_equivalence.py`** converted from Lark-comparison gates to golden fingerprint tests: every ground-truth/fixture grammar reduces to an `IrAst` with an expected `(start_rule, rule_names)` fingerprint, unambiguously, and stays stable under emit→reparse.
- `utils/names.to_lark_name` deleted. `test_layering_invariants.py` gained `test_engine_package_does_not_import_grammars_or_codegen` and `test_engine_imported_by_runtime_only_via_compile_seam` (the engine is a leaf; `compile.py` is the only sanctioned runtime→`lexic.parsing` seam).

Open items left for the user (not yet resolved as of this entry): whether `gbnf.py`/`abnf.py`'s C0302 (too-many-lines) waiver stands permanently or the modules split; two ABNF parity gaps (`%d`/`%b` value-sequences, uppercase `%X`/`%D`/`%B`/`%S`/`%I` markers) fail as parse errors rather than an explicit `UnsupportedConstructError`. Wiki pages updated: [[architecture]], [[flavour-system]], [[public-api]], [[error-vocabulary]]; a CLAUDE.md refresh was prepared as a proposal (`zzz_current_work/postleo/CLAUDE_md_refresh_proposal.md`) rather than applied directly.

---

## 2026-06-08 — `Field` mutable-default fix + astroid `dataclass_transform` plugin

Two issues found reviewing `Field`/`IrCachingTuple` (`ir/base.py`):

1. **Mutable-default sharing bug.** `Field.build()` returned `self.default` by reference, so a mutable `default` (e.g. `ruleref_frames: list[bool] = Field(default=[False])` in `codegen/aliases.py`) was shared across **every** instance and persisted mutations across constructions (classic mutable-default footgun). Fixed by deep-copying in `build()`: a `default_factory` result is returned as-is; a plain `default` is now `copy.deepcopy`-d, so each instance gets an independent value. Regression tests added to `tests/unit/lexic/ir/test_base.py` (Field isolation + IrCachingTuple field-merge/default resolution — that file had **no** Field/IrCachingTuple coverage before).

2. **pylint false positives on `Field` defaults.** `Field.__new__` is typed (overloads) to return the field's type, which pyright honours but astroid does not — it infers `aliases: dict = Field(...)` as a `Field` instance, raising bogus `no-member`/`unsupported-membership-test` at read sites (`aliases.py` was 8.82/10). Root cause: astroid has no :pep:`681` `dataclass_transform` support for field types declared on a *base* class (`IrNamedTuple`/`IrCachingTuple`). Fixed with a repo astroid brain plugin `tools/pylint_lexic.py` that rebinds each annotated field of an IR field-record class to an instance of its annotation type (reusing astroid's `_infer_instance_from_annotation`). Wired via `[tool.pylint.main] load-plugins`/`init-hook` in `pyproject.toml`. No inline suppressions. Whole-`src` pylint back to clean (only the pre-existing `R0903` on `IrCachingTuple`).

Follow-ups in the same pass: **`Field` now requires exactly one of `default`/`default_factory`** (overloads reject `Field()` statically; `__new__` raises `TypeError` at runtime so a field never silently carries the `_MISSING` sentinel). **`IrCachingTuple.__init_subclass__` now merges every caching base's fields in reverse-MRO order** (the `dataclasses` convention, dedup'd) instead of only the nearest base — well defined under multiple inheritance, not just a linear chain. Note: the `*Ts` type params do **not** track merged fields, so positional *typing* of a subclass is unreliable (use named access / `tuple(inst)`); runtime field layout is correct. Full suite 628 passed; `pyright src/ tests/` = 0.

**astroid gotcha (R0903 root cause).** `IrCachingTuple` tripped `too-few-public-methods` because astroid **cannot resolve a sole base subscripted with a bare `TypeVarTuple`** — `class IrCachingTuple[*Ts](IrNamedTuple[*Ts])` gave astroid *zero* ancestors, so it counted ~0 public methods (the class actually inherits `eval`/`children`/`rebuild`/`bind`/`bound`/…). `IrNamedTuple`/`IrTuple` escape this only because they redundantly list a concrete `IrNode[IrSelf, IrSelf]` second base. Fix: do the same on `IrCachingTuple` (semantic no-op; `IrNode` is already reached via `IrNamedTuple`). Resolving the ancestors then surfaced a *second* astroid quirk: iterating `cls.__mro__[1:]` (a tuple slice) lets pylint infer the element types and emit false `no-member` on `base._fields`/`base._child_attrs`, whereas `reversed(cls.__mro__)` yields uninferable elements and is checked-clean. The two `__init_subclass__` loops were unified into the single `reversed` walk (tracking the nearest field-bearing base via last-write-wins), so no spurious `no-member`. `src/` pylint = 10.00.

---

## 2026-06-05 — Phase-0a algebra expansion (value tier + comparison/conjunction)

Added the value-aware action algebra on top of V2: `IrScalar(IrLeaf)` value-leaf base (hosts `eval` + type-aware `__eq__`/`__ne__`/`__hash__`/`__repr__`, all delegating to the primitive); `IrInt(IrScalar, int)`; `IrStr` re-parented onto `IrScalar` (its `__new__`/`eval` dropped). `IrField` now reads typed attrs via `out: type[IrScalar]` (default `IrStr`), made callable by a forwarding `IrScalar.__new__`. Comparison: `IrOp(IrStr)` operator leaf (the node IS its string — **no `Cmp` enum**) + `IrCompare` + short-circuit `IrAnd(IrTuple[IrSelf])`, all returning `IrInt ∈ {0,1}` (no `IrBool`). `IrTuple.eval` relaxed `-> Self` → `-> IrSelf` so reducers can override (no `[T,R]` generic). `IrCond` generalized `field: str` → `test: IrSelf`. New exports: `IrScalar`/`IrInt`/`IrOp`/`IrCompare`/`IrAnd`.

Deviations from the plan (`docs/superpowers/plans/2026-06-04-phase-0a-algebra-expansion.md`) recorded in [[decisions]] (2026-06-05 entry): no `Cmp` enum (→ `IrOp`), `type[IrScalar]`+`__new__` instead of the `type[IrStr]|type[IrInt]` union, `IrScalar` hosting eq/hash/repr, and `IrTuple.eval -> IrSelf` instead of the two-param generic. Full suite 593 passed; `pyright src/ tests/` = 0. [[ir-shapes]] + `CLAUDE.md` updated.

---

## 2026-06-04 — Primitive-node model (V2) migration complete

The coercion-based node model is gone. Nodes now ARE their payload — three tiers: str-leaves (`IrStr`: `IrLiteral`/`IrCharClass`/`IrRuleRef` subclass `str`), variadic collections (`IrTuple`: `IrSequence`/`IrAlternation` subclass `tuple`), and fixed-arity records (`IrComposite` frozen dataclasses). Removed `IrType`, `coerce`, `_ir_field_types`, the load-bearing `__init__`, `IrStrLeaf`, `IrCollection`/`_items_attr`, and the `_str_name`/`__str__` cascade (now `__repr__`-is-codegen). No `.value`/`.items`/`.arms` accessors. Whole-tree `pyright src/ tests/` = 0 (genuine — the old `*args/**kwargs` init had masked ~174 errors); full suite 572 passed; pylint core 10/10.

New decisions recorded in [[decisions]]: type-aware `IrStr.__eq__` (distinct leaf kinds unequal, plain-`str` compatible — fixes `@cache`/tree-equality poisoning); `IrThis` + lazy `IrReturn` for declarative find-first (no `IrCallable`); two type params `[Iri, Ir_co]` with `_bound` from the **last**; no `cast`/suppressions; **open-set consumer rework deferred** to a separate spec (`derive`/`codegen`/`parsing`/`generate` still carry closed-set `isinstance`/`dict[type,…]` ladders — legacy, not the target). [[ir-shapes]] rewritten to V2; `CLAUDE.md` IR-types section and flavour template updated (flavour dataclasses must NOT use `init=False` — it silently empties `actions`). Plan: `docs/superpowers/plans/2026-06-01-ir-primitive-node-model.md` (Tasks 1–16).

---

## 2026-05-30 — IrNode construction: dataclass-generated `__init__` + `__post_init__` coercion

`IrNode` previously carried one hand-rolled `__init__(*args, **kwargs)` (decorators used `init=False`). Two bugs: type checkers/IDEs saw `(*args, **kwargs)` instead of real per-field signatures, and unknown keyword args were silently dropped (`IrLiteral('x', bogus=1)` constructed fine). Fixed by deleting the custom `__init__`, dropping `init=False` from every `IrNode`-subclass `@dataclass` across `ir/nodes.py`, `ir/action.py`, `ir/walk.py`, `ir/derive.py`, `codegen/aliases.py`, and both `grammars/*/flavour.py`, and moving coercion into a base `__post_init__`. Now signatures are real and unknown kwargs raise `TypeError`. Side effects: `IrReturn.__post_init__` calls `super().__post_init__()`; `_HoistTransformer.parent_name` gained a default (required-after-defaulted ordering); `IrRule.name` is now strictly required. Invariant recorded in [[ir-shapes]]; the flavour template in `CLAUDE.md` no longer prescribes `init=False`.

Collateral: while landing this, the in-progress `derive.py` edit (`_extract_none` → `IrNone`, `_extract_group` filter rework) was left with `_hoist_item` still checking `is None`, which built helper rules with `IrNone` bodies. Resolved by keeping the `has_ruleref` filter in `_extract_group` (returning `IrNone`) and the `_hoist_item` guard on `is IrNone`; two `_EXTRACT_BODY` tests updated from `is None` to `is IrNone`.

## 2026-05-28 — Slice B substrate landed; flavour-as-IrEmitter migration; helpers cleanup

**Substrate landed.** Every IR node now descends from `IrSelf` and is callable: `node(d, n, nc) -> Ir_co`. The action-algebra (`ir/action.py`) and the `IrDispatch[Ir_co]` substrate (`ir/walk.py`) are in. Presets `IrVisitor` / `IrTransformer` / `IrEmitter[IrLiteral]` configure default bodies (`IrWalk`, `IrRebuild`, `IrEmit`). Dispatch is **action-table-driven**, concrete-first MRO resolution, memoised — and crucially, `IrDispatch` does NOT auto-walk children: action bodies own recursion.

**Flavour migration.** `IrFlavour` IS-AN `IrEmitter`. Each flavour is now a single `grammars/<name>/flavour.py` module: `META_GRAMMAR` string, private `_<Name>Escapes` + `<NAME>_ESCAPES` singleton, `<NAME>_ACTIONS: tuple[IrAction, ...]`, private `_<Name>Flavour` + `<NAME>_FLAVOUR` singleton. `grammars/__init__.py` imports and registers the singletons on import. `base.GrammarModel.to_grammar(flavour)` calls `get_flavour(flavour).apply(self.__grammar__.to_ir_rule())`.

**Cleanup.**
- Deleted: `ir/helpers.py` (HelperRuleRegistry), `grammars/gbnf/emitter.py`, `grammars/gbnf/escapes.py`, `grammars/gbnf/meta_grammar.py`, `grammars/abnf/emitter.py`, `grammars/abnf/escapes.py`, `grammars/abnf/meta_grammar.py`.
- `utils/quantifiers.py` survives — consumed by `parsing/lark_builder.py` and `codegen/aliases.py`. GBNF's `parse_quantifier` no longer uses it (uses the local `GBNF_QUANT_SYMBOLS` table). Scheduled for later cleanup.
- `ir/emit.py` ships `render_specs()` as a helper; currently only its own test consumes it.

**Wiki / doc updates.**
- **CLAUDE.md**: test count → 474; file tree rebuilt (added `ir/action.py`, `ir/walk.py` substrate; removed deleted modules; flagged `utils/quantifiers.py`); pipeline diagram updated to `flavour_singleton.apply(node)`; IR-types section expanded with `IrSelf` mixin, `IrNode[Ir_co]` generic, action algebra, dispatch presets; `IrLiteral` dual role documented; layering exception #1 updated to `lexic.grammars.gbnf.flavour.GBNF_FLAVOUR`; import paths refreshed (`IrQuantifier`, action / walk surface, singletons).
- **[[architecture]]**: rewritten — single pipeline (no more two-pipeline section); IR substrate detailed with `IrSelf` / typed bases / dispatch / presets; flavour-as-`IrEmitter` documented; `IrLiteral` dual role section; deleted-modules note.
- **[[flavour-system]]**: rewritten — singleton convention (private class + public instance), action-tuple shape with GBNF example, `IrCallable` vs pure-algebra guidance, `IrFlavour` ABC, new step-by-step.
- **[[ir-shapes]]**: rewritten — substrate first (`IrSelf` / `IrType` / `IrStr` / `IrTuple`), then grammar AST, then action-algebra table, then dual-role note. `IrQuantifier` documented; `_child_attrs` / `_items_attr` convention spelled out.
- **[[decisions]]**: appended **P12–P18** — IR-pass-by-action-table; action bodies AND dispatcher are IR nodes; dispatcher generic in result type with LSP-compatible signature; concrete-first MRO resolution; `IrReturn` short-circuit via `_Return` BaseException; `IrLiteral` dual role; every IR node callable.
- **README.md**: rewritten — concise project intro, supported flavours, quick example, architecture pointer, dev setup, status.

Test suite green at 474 passed.

---

## 2026-05-13 — IrItem cutover complete; document sweep

**Cutover landed.** All 18 parallel-track tasks done. The IrItem-based pipeline is the only pipeline.

Pipeline changes:
- `compile_from_path` now uses `path.stem` as module stem (e.g. `arithmetic.gbnf` → `generated/arithmetic.py`); `compile_text` continues to use `anon_<sha1>.py`.
- `codegen(specs, stem)` in `codegen/__init__.py` ruff-formats generated source via `find_ruff_bin()` before writing.
- `Optional[...]` wrapping for optional sequence fields fixed in `model_emitter.py`.
- `Union[X]` single-arg bug fixed in `_group_type`.
- Layering invariant test fixed to skip its own source file when scanning for forbidden strings.

Wiki / doc updates:
- **CLAUDE.md**: test count corrected (448), "two pipelines" section replaced with "single IrItem pipeline", project layout rewritten, architecture diagram updated, layering exceptions updated, IR types section consolidated (old shape removed), import paths cleaned up, stale constraints removed.
- **[[cutover-plan]]**: rewrote to reflect completion; what-replaced-what table; pointer to Slice B remaining work.
- **[[public-api]]**: `compile_text` / `compile_from_path` / `compile_grammar` / `codegen` / `build_lark` descriptions updated; "Tasks 8–18" language removed.
- **[[index]]**: task routing updated (removed stale Tasks 8–18 rows; added Slice B token reservation row); cutover-plan active work entry updated.
- **[[slice-b-status]]** (new): audit of Slice B Phase 1 (done/obsolete), Phase 2 (entirely obsolete), Phase 3 (token reservation — still required).

Remaining Slice B work: token reservation (Tasks 33–34) — pre-tokenisation scan in GBNF for `<name>`, `<[N]>`, `!<name>` + `tests/integration/test_token_reservation.py`.

---

## 2026-05-10 — Vault reorganization + pipeline canvas
- Deleted empty `related-page.md`
- Moved Lexic pages into [[lexic/]] subfolder (11 pages)
- Split `grammar-theory.md` into [[theory/grammar-formats]] and [[theory/parsing-theory]]
- Created [[pipeline-map.canvas]] showing old and new pipeline flows
- Updated [[index]] — all wikilinks now folder-prefixed, two new theory rows
---

## 2026-05-09 — Ingested parallel-track IR cutover plan (Tasks 9–18)

Pulled concrete API and behaviour details from `docs/superpowers/plans/2026-05-08-parallel-track-ir-cutover.md` into the wiki.
- [[decisions]]: added "Cutover commitments (CQ #1, #2, #4)" entry covering no-FIXME, no `ws` hardcoding, fixed canonical imports.
- [[new-codegen]]: expanded Tasks 9–14 with `CANONICAL_IMPORTS`, `_field_type` rules, `_repr_iritem`, `regex_for_charclass`/`regex_for_group` public surface, `Pattern`/`Pattern2` Tier-3 fallback, `codegen(specs, stem)` signature (no `flavour` parameter).
- [[cutover-plan]]: replaced 8-bullet checklist with the 17 sub-step cutover sequence; added Slice 3 (`parsing/`) table for Tasks 15–17.
- [[public-api]]: added `codegen(specs, stem)` and `build_lark(specs, classes, start_rule)` future signatures.
- [[architecture]]: documented post-cutover `parsing/` directory shape and the layering-invariant test gate.

---

## 2026-05-09 — Wiki improved for agent token efficiency

Rewrote `index.md`: query-answerable page descriptions, quick lookup table, task routing section. Added `When to load:` line to every page. Added new pages: [[testing]], [[new-codegen]]. Updated [[cutover-plan]] to mark Task 8 done. Fixed template name (`note.md.md` → `note.md`).

---

## 2026-05-09 — Task 8 landed (uncommitted)

`new_codegen/aliases.py`: `PatternAlias` frozen dataclass + `collect_aliases`. Walks `IrItem` nodes via `IrVisitor`, dedupes on regex, names via Tier-2 `CHARCLASS_NAMES` (CamelCase) or `"Pattern"` fallback. Tests in `tests/unit/lexic/new_codegen/`.

---

## 2026-05-09 — `public-api` wiki page added

Documented the stable public surface: `parse`, `compile_text`, `compile_from_path`, `compile_grammar`; `CompiledGrammar` fields; `GrammarModel` methods (`to_text`, `to_grammar`, `semantic_dump`); GBNF grammar format and directive precedence rules.

---

## 2026-05-09 — Wiki created

Created initial wiki structure with pages for [[architecture]], [[ir-shapes]], [[flavour-system]], [[field-naming]], [[error-vocabulary]], [[invariants]], [[cutover-plan]], [[decisions]].

Source: CLAUDE.md audit + code reading session. All pages reflect codebase state at this date.

---

## 2026-05-09 — CLAUDE.md updated

Rewrote CLAUDE.md to reflect current codebase state: both pipelines documented, layering rules reproduced in full, flavour system described, error vocabulary table added, `tools/auto_fix.sh` prominently in Commands.

---

## 2026-05-09 — Tasks 6 and 7 completed

**Task 6 (`ir/naming.py`):** `CHARCLASS_NAMES` reduced from ~10 entries to 9 authoritative entries. `[a-zA-Z]` → `"letter"` (was `"alpha"`). Both hex orderings normalise to `"hex"`. All tests updated to match new ground truth.

**Task 7 (`ir/derive.py`):** Replaced 13-branch `if isinstance` chain in `_field_map` with `_FIELD_BASE` dispatch table. `_ATOM_HINT[IrGroup]` bug fixed: was returning `"value"` for ruleref groups; now correctly returns `"kind"` consistent with `_group_field_base`.

---

## 2026-05-08 — Tasks 1, 2, 4 completed

**Task 1:** `grammars/new_gbnf/` skeleton created. Pure-copy of stable modules from `gbnf/`.

**Task 2:** `grammars/new_gbnf/flavour.py` — `GbnfFlavour(Flavour)` class attribute wiring. `emitter = GbnfEmitter` (class ref, not instance). Fixed `type: ignore` by using class reference.

**Task 4:** `grammars/new_gbnf/emitter.py` — IrItem-only `GbnfEmitter`. Fixed pyright error (`Atom` vs `IrItem` in generator guard). Fixed test `_spec()` `kind` parameter annotation.

Tasks 3 and 5 deleted from plan — dead weight, no behaviour without `flavours.py`.

---

## 2026-05-08 — `quantifier_to_bounds("")` fix

`utils/quantifiers.py`: changed `if q is None` to `if not q` so empty string is treated same as `None` (returns `(1,1)`). Needed because GBNF parser emits empty string for bare atoms with no quantifier token.

---

## 2026-05-08 — Plan: parallel-track IR cutover

`docs/superpowers/plans/2026-05-08-parallel-track-ir-cutover.md` created. 18 tasks; builds `new_gbnf/`, `new_codegen/`, `parsing/` against the IrItem shape alongside legacy code, then cuts over atomically in Task 18.
