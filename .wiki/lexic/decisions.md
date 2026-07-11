# Design Decisions

**When to load:** understanding why something is designed a specific way; before reversing or changing a design choice; after landing a non-obvious decision (add an entry).

Significant choices with reasoning. Add an entry whenever a non-obvious decision is made or reversed.

---

## 2026-07-11 — P6/P3 noise levers: attribution over hardcoding; peeks are fail-soft (Task 6.4)

**Decision 1 — the P6 licence carries a third clause.** SIM_60's pinned two-clause condition (`hard_follow ∩ FIRST = ∅` ∧ `gap ⊆ FIRST`) is sufficient for json but unsound in general: it would license a non-semantic loop eating into a *semantic* optional follower (`root ::= x "ab"?`, `x ::= [a-c]*` noise — `semantic_dump` changes). The plan's own risk note demands precision, so the licence adds `gap ∩ sem_follow(rule) = ∅`, where `sem_follow` is a FOLLOW fixpoint over *semantically-attributable* chars only (`pda/noise.py`): terminals count only inside semantic rules; a ref to a non-semantic rule contributes nothing (its subtree is excluded from `semantic_dump` wholesale, so chars stolen from it are noise↔noise by construction); a ref to a semantic rule contributes its *decomposition*, not its noise-polluted raw FIRST. This reproduces the SIM's json justification ("ws is the sole whitespace-leading rule") without hardcoding it.

**Decision 2 — W is grammar-derived, not per-flavour.** The P3 skippable alphabet is ⋃FIRST over **nullable** non-semantic rules: nullability is what separates a noise *run* (ws, filler) from a required-but-dropped token marker (dquote, defined) — exactly the ⚠ 6.0 constraint, with W itself derived. Gives json whitespace, ABNF ws+`;`, GBNF ws+`#` (matching the SIM's hand-pinned sets).

**Decision 3 — the P3 peek is non-consuming, hence fail-soft by construction.** The runtime skips the maximal W run only to *look*; the winning arm/iteration re-parses its noise from the original position. A wrong pick can therefore only fail-then-fallback, never silently mis-build — so the analysis separability conditions are a *determinism* (zero-fallback perf) guarantee, and mixed-terminal poisoning / end-open bailing in `ResidualFirst` err conservative without soundness pressure. Corollary: comment-bearing noise (GBNF `#…`, ABNF `;…`) poisons the char-set residual FIRST (the skip could land inside a comment body), so the GBNF/ABNF spine's P3 decisions stay islands until the folding-aware structured scanner lands with P5 (which needs it regardless).

**Decision 4 — stored gates are honored in every clone.** The compiler consulted taxonomy gates only under its per-clone hard-cont overlap heuristic; a clone whose hard tail didn't overlap the loop FIRST silently baked a stop-set that ate the soft-only noise run the gate exists to adjudicate (caught live by a `\t`-bearing json input). Rule: a stored gate is the analysis's decision for that node — judged against the rule's soft FOLLOW, which covers every clone — and is read back unconditionally.

**Decision 5 — staging flags die once their lever lands.** `P2_DEMOTION_ENABLED` deleted (user ruling: pre-v1, no legacy); flag-seam tests deleted with their symbol. `DELEGATES_ENABLED` stays until Task 8 — it is the still-standing delegation A/B gate, not a landed lever's leftover.

**Impact:** json island-free (16× vs 6.2 on the instance path: 751→46 ms); `Taxonomy` carries four gate channels; `pda/noise.py` + `test_noise.py` new; `_gate_take`/`_select_gated` shared runtime helpers in `flatten.py`.

---

## 2026-07-11 — P2 gate-spec channel: analysis stores, compiler reads (unified-parse-engine Task 6.3c)

**Decision:** The k-window gates the analysis consults during demotion are **stored on the taxonomy** and read back by the clone compiler — never recomputed. `GrammarAnalysis.taxonomy` (the renamed `_tax` slot, now a public **attribute** — deliberately not a property/method, so the R0904 20-public-method and R0902 7-slot caps are both untouched) is a `Taxonomy` carrying `arm_gates: dict[str, windows-per-arm]` and `loop_gates: dict[int, taken-windows]`.

- **Why option (a) (store) over recompute-in-compiler?** Dual derivation of the same soundness-critical spec is a divergence risk (task63fix F1: the seam previously carried *no* spec — the gates were computed and discarded). Single source of truth; the compiler's only job is alignment.
- **Arm gates keyed by rule name, licensed for rule bodies ONLY.** `arm_conflicts`' `label` for a rule body IS the rule name (`label in self.rules` is the discriminator — bracketed group labels can never collide with rule names). An inline group's arm overlap now stays a **hard note → the rule islands**, which strictly dominates the old part-(b) whole-grammar opt-out (the engine parses one rule instead of everything). Corpus has no such group.
- **Loop gates keyed by `id(IrItem)` — node identity.** Analysis and clone compiler walk the *same* lifted tree (`compile_pda` builds the analysis from the `lifted` it compiles), so the item node is the exact decision identity; label-keying (`rule[idx]`) is ambiguous between a rule arm's item k and a group sub-arm's item k. A conflicting re-store under one id raises (`UnsupportedConstructError` → whole-grammar opt-out) — the shared-node hazard is closed, not assumed away.
- **Specs stored cooked** (`kwindow.windows_of`: END/MORE/UNK tags dropped — the runtime's positionwise consistency test never reads them (task63fix finding 4) — dedup'd, deterministically sorted so specs compare with `!=`).
- **Alignment lives inside `compile_arms`' own enumeration** (`windows[idx]` attached in the same loop that drops empty-FIRST arms) — window↔arm drift is structurally impossible rather than checked after the fact. A FIRST-overlapping alternation reaching the compiler with **no** spec raises — the anti-trap tripwire (F2: an empty gate mis-parses, PdaFail-falls-back, and passes island-move + parity gates while unsound and slower).
- **Verified live:** chess `nonpawn` (loop, k=3) 0.0% fallback + 8.6× faster than the 6.2 island-hit path; `lo>k` EOF-exact arm selection end-to-end; GBNF-self 17→8 / ABNF-self 9→7 island moves exactly per the coverage map.

**Impact:** `Taxonomy` is public (`analysis.__all__`); `KTupleGate`/`ArmSpec.windows` reinstated in `clones.py` as read-side only; LL(2) 2-prefix machinery now lives in `kwindow.py` as free fns (`loop_policy` calls across); `_bake_reduce`/`_reduce_rewrite` live in `reduce_pda.py`. `P2_DEMOTION_ENABLED` defaults **True**; `False` is the A/B seam. See [[architecture]], the PLAN_v5 ledger, and log 2026-07-11.

---

## 2026-07-06 — One IR fold type: `ModelFold` + `ModelBody` (unified-parse-engine Task 3)

**Decision:** The instance fold's authored form is now **one IR-native type**, `ModelFold` (`parsing/fold.py`), whose `bodies` is a per-rule `IrMap[IrRuleRef, ModelBody]` — the *same shape* the grammar-text `Reducer` carries its `reductions` in (a per-rule `IrMap` to `IrSelf` bodies). A `ModelBody(kind, ctor, n_items, fields, fast)` (an `IrNamedTuple`, `_child_attrs=()`) carries the model constructor as an `IrLambda` (`IrNone` for an `alternation`, which has none) plus structural metadata. On construction `ModelFold` **bakes** every body (`ModelBody.bake()`) to the flat-runtime `config: dict[str, RuleFold]` (`.baked`) — the record the PDA clone compiler and the engine-fallback `apply` consume **byte-for-byte unchanged**. `RuleFold`/`FieldFold`/`FastCtor` survive as that lowered/baked representation; `ModelBody.of(rf)` is the inverse lift and `ModelFold.from_config(dict)` the direct-from-baked (lowered) constructor.

- **Why merge `PositionalFold` into `ModelFold` rather than add a wrapper?** The task called for *one* fold type; the old `PositionalFold` was only the runtime executor over `dict[str, RuleFold]`. Absorbing its `apply`/`run_ok` onto `ModelFold` (which reads the same `self.config`) keeps the runtime logic unchanged while making the authored form the IR body-table. `collapsed_fold_tables(grammar, fold)` re-signs to `ModelFold`; nothing else in the engine changes.
- **Why `IrLambda(cls)` for the ctor?** It is the sanctioned procedural escape and `IrLambda(cls).eval IS cls` (free unwrap) — so baking recovers the exact constructor with zero indirection. Proven by `spike_bake.py` (176 rules across all 10 ground truths bake runtime-identically; 0 rules need an arbitrary body).
- **Name reclaimed.** The retired wrapper-rule `ModelFold` (`parsing/models.py`, deleted 2026-07-04) is unrelated; the name is now the one authored instance-fold.
- **Behavior-frozen.** A differential over 600 generated samples × both parse paths (PDA + engine) is byte-identical before/after; no perf loss (the flat clone is unchanged).

**Why:** unify the *authored* fold to an IR body-table so Task 4 can express the `Reducer` as the same per-rule `IrMap`-to-`IrSelf`-body type. The lowered `RuleFold` int-mode contract with the flat clone is deliberately preserved — the change is at the authoring seam, not the runtime.

**Impact:** New public exports `ModelFold`, `ModelBody` (`parsing/fold.py`); `PositionalFold` removed. `compile._fold_config` now returns the `IrMap` body-table; `_build_pda` takes `fold.baked`. See [[public-api]], [[architecture]].

---

## 2026-06-05 — Phase-0a algebra: `IrScalar`/`IrInt`, `IrOp` (no `Cmp` enum), `IrTuple.eval -> IrSelf`

**Decision:** Added the value-aware action algebra, deviating from the plan's prescribed shapes on four points:

1. **`IrScalar(IrLeaf)`** is the value-leaf base; it hosts `eval` *and* the type-aware `__eq__`/`__ne__`/`__hash__`/`__repr__` (consolidated up from `IrStr`). `IrStr(IrScalar, str)` and `IrInt(IrScalar, int)` carry only `_bound`. `IrStr.__new__`/`eval` removed. Added `__ne__` to fix a latent inconsistency (`str`/`int` supply their own `__ne__`, which ignored the leaf-kind check, so `a != b` disagreed with `not (a == b)`).
2. **`IrField.out: type[IrScalar]`** (default `IrStr`), made constructor-callable by a forwarding **`IrScalar.__new__(*args)`** — NOT the plan's `type[IrStr] | type[IrInt]` union (closed-set, forbidden) and NOT generic (a concrete default on a generic `out` is unsound for pyright).
3. **`IrOp(IrStr)`** operator leaf instead of the plan's **`Cmp` enum** (user directive: no Enum). The operator IS its string (`IrOp(">")`); `_OPS` maps it to an `operator` builtin; `eval` applies it to the operands in `nc`. `IrCompare(left, op: IrOp, right)` supplies both operands; `IrAnd` is short-circuit conjunction. A truth value is `IrInt ∈ {0,1}` — no `IrBool`. (User directive: comparison ops are a string-leaf node, never a Python `Enum`.)
4. **`IrTuple.eval` relaxed `-> Self` → `-> IrSelf`** so reducer subclasses (`IrAnd(IrTuple[IrSelf])`) can override `eval` to return `IrInt` — NOT the plan's `IrTuple[T, R]` two-param generic + `cast`. `IrSequence`/`IrAlternation` are untouched.

**Why:** Open classes over closed-set dispatch (no enum, no enumerated leaf union); avoid the plan's heavier generics where a one-line return-type relaxation suffices. All verified empirically (apply→pyright→suite).

**Impact:** `IrCond` now takes `test: IrSelf` (was `field: str`). New public exports: `IrScalar`, `IrInt`, `IrOp`, `IrCompare`, `IrAnd`. Full suite green (593), `pyright src/ tests/` = 0. See [[ir-shapes]].

---

## 2026-06-04 — Primitive-node model (V2): a node IS its payload

**Decision:** Replace the coercion-based node model with one where nodes *are* their payload. Three tiers: str-leaves (`IrLiteral`/`IrCharClass`/`IrRuleRef`) subclass `str` via `IrStr`; variadic collections (`IrSequence`/`IrAlternation`) subclass `tuple` via `IrTuple`; fixed-arity records (`IrItem`/`IrQuantifier`/`IrGroup`/`IrNot`/`IrRule`/`IrAst`) are frozen `IrComposite` dataclasses. Removed: `IrType`, `coerce`, the load-bearing `*args/**kwargs` `IrNode.__init__`, `_ir_field_types`, `IrStrLeaf`, `IrCollection`/`_items_attr`, and the `_str_name`/`_inner_str`/`__str__` cascade (replaced by `__repr__`-is-codegen). There are **no** `.value`/`.items`/`.arms` accessors — use the node directly.

**Why:** The old `__init__(*args, **kwargs)` masked ~174 pyright errors (standard-mode 0 was a lie). Making nodes their payload eliminates coercion, the load-bearing init, and the variance that produced those errors. Construction is now honest per-field dataclass `__init__`/`__new__`; whole-tree pyright is genuinely 0.

**Impact:** Every consumer reads leaves as `str` and collections as `tuple`; construction is variadic (`IrSequence(*items)`, `IrAlternation(*arms)`, `IrAst(IrTuple(*rules), start)`). Full suite green (572 tests), `pyright src/ tests/` = 0. See [[ir-shapes]].

---

## 2026-06-04 — Type-aware `IrStr.__eq__`

**Decision:** `IrStr.__eq__` is type-aware against other `IrStr` (distinct leaf kinds never compare equal — `IrLiteral("x") != IrRuleRef("x")`) but falls back to native `str` equality against a plain `str` (`IrLiteral("x") == "x"`). `__hash__` stays native `str.__hash__`.

**Why:** With leaves subclassing `str`, `IrLiteral("x") == IrRuleRef("x")` was `True`, poisoning structural tree equality and hashing (a `@cache` on `has_ruleref` returned stale results because structurally-distinct trees compared equal). The transitivity tension — `leaf == "x"` for both kinds *forces* `IrLiteral("x") == IrRuleRef("x")` — is resolved by making equality type-aware only among `IrStr` while preserving plain-`str` compatibility. Native hash means same-text different-kind leaves collide but compare unequal (eq is the tiebreaker), and leaves still match plain-`str` dict keys.

---

## 2026-06-04 — `IrThis` + lazy `IrReturn` for find-first (no callable)

**Decision:** Added `IrThis` — an identity body whose `eval` returns the dispatched node `n`. `IrReturn` lazy-evaluates its body against `(d, n, nc)` and re-raises the result, defaulting `value=IrThis()` so `IrReturn()` surfaces the matched node. `has_ruleref`'s visitor is pure algebra: `IrAction(IrRuleRef, IrReturn())`.

**Why:** Returning the *found* node from a predicate visitor needs access to `n` at eval time, which a constant `IrReturn(x)` cannot capture. An `IrCallable` raising `IrReturn(n)` was rejected — keep the action table declarative, no procedural escape hatch where algebra suffices. `IrThis` is the declarative "current node" primitive; `IrReturn` evaluating its body composes it cleanly and stays backward-compatible (`IrReturn(IrLiteral("v"))` still returns the literal).

---

## 2026-06-04 — Two type parameters `[Iri, Ir_co]`; `_bound` from the last

**Decision:** Generic nodes/actions carry two PEP 695 parameters `[Iri: IrSelf, Ir_co: …]` — `Iri` the input node type, `Ir_co` the covariant return type. `IrSelf.__init_subclass__` derives `_bound` from the class's **last** own type parameter (i.e. `Ir_co`), not the first.

**Why:** Adding `Iri` first shifted `Ir_co` to second position; the old `params[0]` derivation then resolved `_bound` to `IrSelf` (Iri's bound), breaking `IrField`/`IrConcat`/`IrJoin`/`IrEmitter` (`IrSelf() takes no arguments`, `'IrSelf' has no attribute 'join'`). `Ir_co` is conventionally last (sole param on single-parameter nodes, second in the pair), so taking the last is correct and keeps the existing `_Probe[T: …]` contract test passing.

---

## 2026-06-04 — No `cast`, no suppressions (reaffirmed)

**Decision:** During the V2 port, type errors are fixed at the root — correct annotations, `isinstance` guards that `raise` on the unexpected branch, or constructing the real node. No `cast`, no `# type: ignore`/`# noqa`/`# pylint: disable`. Owner instruction: "absolutely no cast."

**Why:** A `cast` re-hides exactly the variance the V2 model exists to expose. An `isinstance`-guard-then-`raise` documents the invariant and fails loudly if violated; a cast asserts it silently.

---

## 2026-06-04 — Open-set consumer rework deferred

**Decision:** The V2 migration is a mechanical port; IR consumers (`derive`, `codegen`, `parsing`, `generate`) keep their closed-set `isinstance` ladders and `dict[type, …]` tables for now. A **separate** spec/plan will re-home node-intrinsic logic onto the nodes and consumer policy onto open `IrDispatch` tables.

**Why:** Finish the migration green first (the safety net), then refactor — two independently-verifiable passes rather than one giant change. These ladders are legacy, not the target.

---

## 2026-05-28 — P12: IR passes are action tables, not closed subclasses

**Decision:** Every IR pass — transformer, emitter, visitor — is a `tuple[IrAction, ...]` plugged into a single concrete `IrDispatch[Ir_co]` (via `IrVisitor` / `IrTransformer` / `IrEmitter` presets). Passes are **constructed**, not subclassed. New IR types are added by extending the action tuple; no dispatcher subclassing required.

**Why:** Strengthens the original "open classes" rule. A closed pass-subclass forces every consumer to know every node type at subclass-definition time; an action table lets the table grow per-flavour or per-pass without touching the dispatcher. New AST node types ripple through table-builders, not through case statements.

**Impact:** `IrFlavour` IS-AN `IrEmitter`, configured by `actions = <FLAVOUR>_ACTIONS`. Adding a flavour means writing a new action tuple, not a new dispatcher class.

---

## 2026-05-28 — P13: Action bodies AND dispatcher are IR nodes

**Decision:** Both the per-target action body and the dispatcher itself live on the `IrNode` substrate. `IrDispatch[Ir_co]` IS-AN `IrCollection[Ir_co]` whose `_items_attr = "actions"`. Action bodies (`IrField`, `IrCallable`, `IrConcat`, `IrJoin`, etc.) are `IrNode`s with overridden `eval`.

> **Superseded (2026-06-04, V2):** `IrCollection`/`_items_attr` are gone. `IrDispatch[Iri, Ir_co]` is now an `IrComposite` whose `actions` is a plain tuple field (NOT a dispatched child). The "dispatcher and bodies are IR nodes" principle stands; only the base tier changed.

**Why:** Self-describing system. Dispatchers can be walked, rebuilt, printed via the same machinery as any IR tree. No special-case "outside the IR" objects.

**Impact:** The action-algebra modules (`ir/action.py`) and the dispatcher module (`ir/walk.py`) compose freely. `IrTransformer` can rewrite a flavour's action table just like any other IR tree.

---

## 2026-05-28 — P14: Dispatcher is generic in result type with LSP-compatible signature

**Decision:** `IrDispatch[Ir_co: IrSelf]` is generic in the produced type. Every dispatcher method follows the protocol shape `eval(d, n, nc) -> Ir_co` — identical for the dispatcher itself and every action body.

**Why:** A single `(d, n, nc) -> Ir_co` signature lets action bodies invoke `d.eval(d, child, ())` without any cast or shape conversion. Substitutability across the algebra is automatic.

**Impact:** Presets bind `Ir_co`: `IrVisitor` inherits `IrSelf`, `IrTransformer` binds `IrNode`, `IrEmitter` binds `IrLiteral`. `apply(root)` is the friendly entry that seeds `d = self`.

---

## 2026-05-28 — P15: Concrete-first MRO resolution; `IrAction` is a default-override unit

**Decision:** `IrDispatch._resolve(type(n))` walks `type(n).__mro__` left-to-right (concrete-first) and returns the first matching `IrAction`. Memoised per dispatcher instance. Misses fall through to `self.default` wrapped in a synthetic `IrAction`.

**Why:** A more specific `target_type` beats an ancestor without table reordering. Default-override is a single field swap on the preset; no special "default branch" mechanism is needed.

**Impact:** Adding a specialised action for `IrCharClass` doesn't break the generic `IrLeaf` action it inherits from. `default=IrRaise()` (strict) and `default=IrEmit()` (lenient) are interchangeable in one line.

---

## 2026-05-28 — P16: Short-circuit is intrinsic to `IrReturn` via `_Return`

**Decision:** `IrReturn` mixes `IrLeaf` and a private `_Return(BaseException)`. `eval` raises `self`; the surrounding `IrDispatch.apply` catches it and surfaces `.value` (or the instance, depending on the bound).

**Why:** Short-circuit needs no protocol participation from every other node. Any nested action can raise `IrReturn` and unwind to the dispatcher. `_Return` is a `BaseException` subclass so `IrCallable` handlers' `except Exception:` clauses cannot swallow it.

**Impact:** Conditional emission becomes trivial: `IrCond(field, IrReturn(IrStr("")), normal_op)` short-circuits cleanly. The `IrReturn` instance IS-AN `IrNode`, fitting the dispatcher's bound when surfaced.

---

## 2026-05-28 — P17: `IrLiteral` carries dual role (grammar literal + action constant)

**Decision:** `IrLiteral` is used both as a grammar AST leaf (the literal string in a rule body) and as an action-language constant (e.g. `IrConcat(parts=(IrLiteral("("), ...))`). The two are distinguished at eval time by `nc`-marker semantics: lazy `IrChild` puts a dispatched literal through `d.eval` (action body fires); direct calls inside action algebra short-circuit to `self.value`.

**Why:** Refusing to introduce a separate `IrText` constant node keeps the algebra small and uniform. Reusing `IrLiteral` means any constant string in an action body could be the target of an `IrTransformer` rewrite (e.g. "change all parenthesisation").

**Impact:** No `IrText` exists. Constants are just `IrLiteral(value)`. The role disambiguation is implicit in the calling convention, not in the type.

---

## 2026-05-28 — P18: Every IR node is callable

**Decision:** Every node implements `__call__(d, n, nc) -> Ir_co`. The default — inherited from `IrSelf` — is identity (`return self`). Value-producing nodes override. `Ir_co` defaults to `IrSelf`.

**Why:** A unified call shape lets *anything* in the IR be the body of an `IrAction`. The substrate has one protocol; specialisation is opt-in.

**Impact:** `IrAction(target, IrLiteral("x"))` is a valid action body — the dispatcher invokes `IrLiteral("x")(d, n, nc)` and gets `IrLiteral("x")` back. Pure-data nodes need no boilerplate to participate in dispatch.

---

## 2026-05-08 — Grammar is the ground truth, not the class

**Decision:** Grammar files are canonical. Pydantic classes are Python representations of a grammar, not sources of truth.

**Why:** The alternative ("class is canonical") biases every design toward "make the class more expressive" and demotes non-GBNF users (the llama.cpp population who come with existing `.gbnf` files). It also breaks cleanly once ABNF or other flavours land — "the class implies a flavour" only works if there's one notation.

**Impact:** `to_grammar(flavour)` is a first-class method on every generated class. `@grammar_rule` decorator (Slice D) produces the same `RuleSpec` shape as codegen-from-file — two authoring paths, one IR.

---

## 2026-05-08 — Parallel-track IR cutover (not in-place migration)

**Decision:** New IrItem-based pipeline built in `new_gbnf/` and future `new_codegen/` alongside the old pipeline. Single cutover commit (Task 18) replaces everything atomically.

**Why:** In-place migration would require every intermediate commit to satisfy both old and new tests simultaneously, creating complex invariant juggling. The parallel track lets each component be built and tested independently; the cutover is a rename + delete.

**Tradeoff:** Temporary code duplication (`new_gbnf/` mirrors parts of `gbnf/`). Acceptable given the cutover is planned and bounded.

---

## 2026-05-08 — Tasks 3 and 5 deleted (no parser wrapper, no adapter for new pipeline)

**Decision:** Deleted `new_gbnf/parser.py` (wrapper around `MetaGrammarParser`) and `new_gbnf/adapter.py` (adapter bridging old registry) from the plan.

**Why:** The new pipeline calls `MetaGrammarParser.for_flavour(GbnfFlavour)` directly. A wrapper would be a thin passthrough with no behaviour of its own. The adapter was needed only because the old `flavours.py` registry exists — once `flavours.py` is deleted at cutover, the adapter concept disappears too.

---

## 2026-05-08 — `_FIELD_BASE` lookup table replacing if/elif chain in `_field_map`

**Decision:** Replaced a 13-branch `if isinstance(atom, X)` chain with a `_FIELD_BASE: dict[type, Callable]` dispatch table.

**Why:** pylint flagged the chain as too many branches. The table is also consistent with `_ATOM_HINT` (already a table) and with the architecture's prescribed dispatch pattern (`BUILDER_BY_ATOM`).

**Contract distinction:** `_ATOM_HINT` always returns `str` (used for naming only); `_FIELD_BASE` returns `str | None` where `None` signals "fall through to Tier-3 positional". This difference is documented in comments and in [[field-naming]].

---

## 2026-05-08 — `CHARCLASS_NAMES` ground truth: 9 entries, `letter` not `alpha`

**Decision:** `[a-zA-Z]` → `"letter"` (not `"alpha"`). 9 entries total; `[a-zA-Z0-9_]` → `"alnum"` (only `_0-9` ordering, not `0-9_`).

**Why:** `letter` is more natural English than `alpha` (which implies "alphabetic" in a more technical sense). `alnum` captures the common identifier char class. The table is intentionally small — any unknown pattern falls back to `_sanitize_pattern`.

**Note:** Both orderings of hex digits (`[0-9a-fA-F]` and `[a-fA-F0-9]`) map to `"hex"` — intentional normalisation.

---

## 2026-04-29 — IrItem shape: quantifier on wrapper, not on leaves

**Decision:** `IrItem(atom, quantifier)` wraps every atom; leaves (`IrLiteral`, `IrCharClass`, `IrRuleRef`) carry no quantifier.

**Why:** In the old shape, quantifiers were fields on `CharClassAtom`, `QuantifiedLiteralAtom`, `RuleRefAtom`. This meant `LiteralAtom` had no quantifier (special case), and adding quantifiers to a new atom type required touching the dataclass. The new shape separates concerns: leaves are pure values, `IrItem` owns repetition.

**Impact:** An unquantified `IrLiteral` is `IrItem(IrLiteral("x"), Quantifier(1,1))`. A quantified literal is `IrItem(IrLiteral("-"), Quantifier(0,1))`. `_field_map` skips only `IrLiteral` with exactly `(1,1)`.

---

## 2026-05-08 — Cutover commitments (CQ #1, #2, #4)

**Decision:** Three named commitments enforced by Tasks 9–17 of the cutover plan.

- **CQ #1 — No `# FIXME` placeholders in emitted Python source.** `_repr_iritem` (in `new_codegen/model_emitter.py`) produces real Python for every IR shape; emitted modules never carry placeholder comments.
- **CQ #2 — No name-string hardcoding in `parsing/lark_builder.py`.** Non-semantic optionality flows from `RuleSpec.non_semantic_fields` + `IrItem.quantifier`. No `atom.name == "ws"` checks. Enforced by `test_no_ws_string_check_in_source`.
- **CQ #4 — Fixed canonical import block in every generated module.** `model_emitter.CANONICAL_IMPORTS` is a constant emitted unconditionally; no per-module import inference. Includes `Annotated`, `StringConstraints`, `Literal`, `ClassVar`, the full IR-AST surface (`IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral, IrRule, IrRuleRef, IrSequence, Quantifier`), `RuleSpec`, and `GrammarModel`.

**Why:** All three are anti-temptation rules. Without CQ #1 emitters reach for placeholder text in unfamiliar shapes; without CQ #2 the lark builder accumulates one-off rule-name special cases; without CQ #4 import lists drift between generated modules.

---

## 2026-04-29 — `Flavour` ABC with class attributes only

**Decision:** Each flavour is a class with class attributes (`meta_grammar`, `escapes`, `emitter`, …) and two static methods (`parse_quantifier`, `parse_charclass`). No `__init__`, no instances as configuration.

**Why:** Flavours have no mutable state — they are configuration bundles. Class attributes are readable, introspectable, and don't require instantiation. `MetaGrammarParser.for_flavour(Cls)` takes the class, not an instance.

**Tradeoff:** The `emitter` class attribute uses `ClassVar[Any]` (typed loosely) to avoid an import cycle. Acceptable — the type is checked at test time.
