# PLAN — Cutover v2: `parsing_2` REPLACES `parsing`, no legacy package

## Progress (one line per step, newest at bottom — session-crash ledger)

- [x] Phase 0 DONE (opus): engine IrNot support; 1223 green; W0212 finding open.
- [x] Phase 1 DONE (sonnet): abnf_2 folded into abnf.py, tests ported; 1223 green.
- [x] Phase 2 src DONE (fable): GBNF_GRAMMAR/GBNF_REDUCER in gbnf.py + equivalence gate test; 1239 green; C0302 on gbnf.py user-accepted until Phase 6 (META_GRAMMAR dies); pyproject.toml is harness — NEVER touch.
- [ ] Phase 2 tests (sonnet): unit tests in test_gbnf.py — dispatched.
- [ ] Phase 3 (opus): ABNF full surface — dispatched.
- [x] Phase 4 design PROVEN in scratch (`zzz_current_work/scratch_models.py`): wrapper-rule-per-field instance grammar + ModelFold; 21/21 real-corpus round-trips (json/c invented samples fail on Lark too — pre-existing). Landing blocked until agents' gates finish. Findings: (a) `to_ir_rule` folds alternation-kind arms into ONE sequence — wrong shape, bridge builds its own; `base.py to_grammar` may share this latent bug — FLAG; (b) DP-2 RESOLVED-AS: deterministic first-derivation on ambiguous instance input (Lark `ambiguity="resolve"` parity; json_ws `int` is genuinely ambiguous) — revertible if user objects; (c) optional-nullable refs lifted `R?→R` (empty-span ambiguity, language-preserving).

> **For agentic workers:** execute task-by-task with the checkboxes; every phase
> lands green (full suite + ruff + pylint on touched files). **Never commit** —
> leave each landing staged for the user. Ask before dispatching any subagent;
> test-writing goes to Sonnet subagents after src is done, with this plan as the
> spec-contract.

Date: 2026-07-02. Supersedes `PLAN_cutover_parsing.md` per the same-day user
ruling recorded in its header: **no `parsing_legacy` / `parsing_old`** — the
Lark path is deleted outright, `parsing_2/` is renamed to `parsing/`, and the
public API (`compile_text` / `compile_from_path` / `parse`) is re-driven by the
Earley engine. IrFlavour **stays in `ir/`** (old D1 overridden). D4 stands: the
`_2` module names die (`abnf_2.py` folds into `abnf.py`).

**Goal:** `src/lexic/parsing/` IS the Earley engine; Lark is gone from source
and from `pyproject.toml`; all integration tests stay green.

**Architecture:** grammar parsing runs `parse_reduced(normalize(flavour.grammar),
text, flavour.reducer)` — each flavour carries its self-grammar as `IrAst` +
`Reducer` (ABNF already does; GBNF gets one). Instance parsing runs the engine
over an `IrAst` rebuilt from the derived `RuleSpec`s (`to_ir_rule`), folded to
model instances by a new spec-driven fold that replaces `build_transformer`.

Baseline: branch `parse_proto_proto`, clean tree, **1205 tests collected**,
engine beats Lark 2× on the product metric (`PLAN_obliterate_lark.md` outcome).

---

## Verified current-state facts (2026-07-02, re-verify only if the tree moved)

- `src/lexic/parsing/` = Lark path: `meta_parser.py`, `lark_builder.py`,
  `transformer/build_transformer.py`. Consumed only by `compile.py:47-48`.
- `src/lexic/parsing_2/` = the engine. Public API (`__init__.py`): `recognize`,
  `parse`, `parse_reduced`, `parse_forest`, `derivations`, `is_ambiguous`.
  Engine **expects a pre-normalized grammar** (`tables.py:501,510` raise "run
  normalize() before compiling"); `compile_tables` memoises by object identity.
- `Reducer` (reduce.py:796) IS-AN `IrDispatch` → `ir/flavour.py` can type the
  new ClassVar as `IrDispatch` with no `ir → parsing` import.
- ABNF: `grammars/abnf_2.py` has `ABNF_GRAMMAR` + `ABNF_REDUCER`, fixpoint
  proven — **but it is a subset**: no comments, no `[...]` option, no `=/`,
  no `%s`/`%i`, no num-seq (`%x0D.0A`), no prose; `char-val` reduces to a plain
  case-sensitive `IrLiteral`, whereas the Lark path's `normalize_literal`
  expands case-insensitively (`abnf.py:306-318`). Gap must close (Phase 3).
- GBNF: has only the Lark `META_GRAMMAR` (gbnf.py:51). No IR self-grammar.
- **Engine has zero `IrNot` support** (no reference anywhere in `parsing_2/`),
  but 4/7 ground-truth grammars use negated charclasses (`json`, `json_ws`,
  `json_arr`, `list`, `c` — `grep -c '\[\^' resources/ground_truth/*.gbnf`),
  and the GBNF self-grammar itself needs them. Prerequisite (Phase 0).
- `CORE_RULES` (abnf.py:101) is **dead data** — its "the meta-parser injects"
  docstring is aspirational; no consumer exists. Dies with the Lark path.
- `utils/names.to_lark_name` — consumers are only `parsing/` (Lark) + tests.
  Dies. `utils/quantifiers.bounds_to_quantifier` — still used by
  `codegen/aliases.py`. Stays.
- Lark instance parser is built with `ambiguity="resolve"` (silent pick); the
  engine's `parse` **raises** on ambiguity. See Decision point DP-2.
- `"parsing_2"` string appears in: all `src/lexic/parsing_2/*`, its test mirror,
  `grammars/abnf_2.py`, `pyproject.toml:41` (perf-marker text),
  `tests/performance/test_lazy_forest_perf.py`, `zzz_current_work/
  bench_parsing.py`, `zzz_current_work/spike_iterative_forest.py`. Error-message
  prefixes `"parsing_2: …"` exist in engine modules; no test asserts on them.

## Rulings (settled by user 2026-07-02 — build as decided, do not reopen)

- **R1 — the new flavour class has NONE of the ad-hoc methods.** Target
  surface after cutover, exactly:

  ```python
  class IrFlavour(IrEmitter, ABC):
      name: ClassVar[str]
      extensions: ClassVar[tuple[str, ...]]
      line_comment: ClassVar[str] = ""
      escapes: ClassVar[EscapeCodec]   # render-side data; emit actions read it
      grammar: ClassVar[IrAst]         # the flavour's self-grammar (raw — ground truth)
      reducer: ClassVar[IrDispatch]    # parse-tree → IrAst (a parsing Reducer at runtime)
  ```

  Metadata ClassVars + emitter `actions` + `grammar` + `reducer`. **Zero
  methods** beyond the inherited emitter protocol — `parse_quantifier`,
  `parse_charclass`, `normalize_literal`, `meta_grammar` all die with the Lark
  path; nothing replaces them as methods. Anything a reducer needs is IR
  action algebra + data tables inside the reduction, never a flavour callback.
- **R2 — escaping/encoding is a rendering feature, not an AST property.**
  The AST holds neutral, decoded payloads (decoded text in `IrLiteral`,
  neutral codepoints in `IrChr` — consistent with the earlier emit-time
  spelling ruling). Encoding happens only in the emit actions; decoding
  happens only in the reducer's actions, with the escape mapping carried as
  render-side *data* (IrMap-style tables, `IrUnradix` precedent — GBNF
  literals carry `\n \t \" \\ \xNN \uNNNN \UNNNNNNNN`). No escape knowledge on
  AST nodes, no decode method on the flavour.
- **R3 — execution model tiers.** Sonnet for trivial/mechanical work, Opus
  for nontrivial work, Fable (this session or another Fable) for the most
  critical. Per-phase assignment in §Execution below. Test-writing is always
  Sonnet, after src, with this plan as the spec-contract. Still ask the user
  before each dispatch.

## Decision points (flag to user; do not decide unilaterally mid-execution)

- **DP-2 — instance-parse ambiguity policy.** If any ground-truth instance
  input parses ambiguously under the engine (Lark silently resolved), choose:
  (a) fix the spec-derived grammar (preferred — honest), or (b) a documented
  deterministic first-derivation mode for the instance path. Surface with the
  failing corpus case; do not silently pick (b).
- **DP-3 — ABNF surface parity scope.** Phase 3 targets full parity with the
  Lark `META_GRAMMAR` (abnf.py:53-85). If any construct is deliberately left
  out, it needs an explicit `UnsupportedConstructError` in the reducer *and*
  user sign-off — north-star "no regression" is the default.
- **DP-4 — `CompiledGrammar` shape.** `parser: lark.Lark` / `transformer:
  lark.Transformer` fields disappear. Proposed replacement fields:
  `grammar: IrAst` (the normalized instance grammar) + `fold` (the model
  fold). Anything in tests touching `.parser`/`.transformer` gets ported.

---

> **Execution log (2026-07-02).** Phase 0 LANDED (opus agent): tables.py only
> src change (+IrNot terminal branch, `_charclass_contains`, explicit raise on
> unknown inner); normalize/lexruns needed nothing (negated classes are
> already poison for run-collapse — correct, just unaccelerated); 1223 green,
> all gates, bench 0.55×. Finding left open: 2 pre-existing W0212 in
> test_tables.py cache-growth tests (no trivial fix; needs a ruling on a
> public cache-size accessor). Phase 2 core PROVEN in scratch
> (`zzz_current_work/scratch_gbnf_ir.py`): all seven ground-truth files parse
> to IrAsts exactly equal to MetaGrammarParser's, zero ambiguity. Key lessons
> baked into the scratch, for the gbnf.py landing + tests:
> - **Bare `IrChr` constants self-render on eval** (emit-time spelling) — a
>   reduction constant must be wrapped `IrBuild(IrChr, IrTuple(IrStr(...)))`.
> - **Three ambiguity classes** had to be engineered away (Lark's lexer gave
>   maximal munch for free): name-after-name inside a sequence (`seq-rest: n
>   item | item-nonname`), rule-boundary re-segmentation (inter-rule noise is
>   REQUIRED: `rules-rest: n rule`), and bare-dash-in-charclass vs ranges
>   (dash legal only leading/trailing/range-hi).
> - **Leading-noise discipline** around nullable arms: GBNF allows empty
>   alternation arms (`ws ::= | " " | ...` in json_arr/json_ws) — `arm:
>   sequence | empty-seq` with an authored ε-rule (engine supports them),
>   `bar-arm: n? "|" arm`, rule drops its post-`::=` noise slot, group drops
>   its leading one, `first-item: n? item` owns arm-leading noise.
> - Documented divergences (grammar-defined, corpus-absent): malformed hex
>   escapes raise instead of passing through verbatim; pathological charclass
>   dashes (`^`/bare `-` as range lo) parse grammar-defined; fully-empty rule
>   bodies (`a ::=`) ARE supported (via empty-seq).

## Phase 0 — engine prerequisite: negated charclasses (`IrNot(IrCharClass)`)

**Files:** modify `src/lexic/parsing_2/tables.py`, `src/lexic/parsing_2/
normalize.py` (only if desugar touches atoms), possibly `src/lexic/parsing_2/
lexruns.py` (run-terminal regex for negated classes: `[^…]`). Tests:
`tests/unit/lexic/parsing_2/test_tables.py`, `test_normalize.py`.

- [ ] Read `tables.py:100-115` (`atom_accepts`) and the `_term_id` /
      `term_atoms` plumbing; extend the terminal-atom union
      `IrLiteral | IrCharClass | RunTerm` with `IrNot` (inner `IrCharClass`)
      and implement negated membership. Unknown inner type → explicit
      `UnsupportedConstructError` (house rule: no silent default).
- [ ] Check `normalize.py` passes `IrNot` atoms through untouched as terminals;
      add handling if it raises.
- [ ] `lexruns.py`: negated classes render as `[^…]` in derived-run regexes, or
      are excluded from run-collapse if the safety analysis can't cover them
      (exclusion is behavior-preserving — just slower).
- [ ] Engine-level proof: `parse(normalize(g), text)` succeeds for a minimal
      grammar with `IrNot(IrCharClass(...))` (e.g. a JSON-string shape
      `"\"" [^"]* "\""`).
- [ ] Gate: `tools/auto_fix.sh` → `uv run pytest tests/ -q` → `uv run ruff
      check src/ tests/` → pylint on touched files. Bench sanity:
      `uv run python zzz_current_work/bench_parsing.py` (no regression).

## Phase 1 — fold `abnf_2.py` into `abnf.py` (D4, mechanical)

- [ ] Move `ABNF_GRAMMAR`, `_NON_SEMANTIC`, `ABNF_NOISE`, `_cp0`/`_cp1`/`_dec`
      helpers, `ABNF_REDUCTIONS`, `ABNF_REDUCER` + module-docstring content into
      `src/lexic/grammars/abnf.py` under a section banner; `git rm
      src/lexic/grammars/abnf_2.py`.
- [ ] Repoint importers: `tests/unit/lexic/parsing_2/test_normalize.py:28`,
      `zzz_current_work/bench_parsing.py:46`, the "forthcoming abnf_2.py" prose
      in `src/lexic/parsing_2/__init__.py:5` and `src/lexic/parsing_2/README.md`.
- [ ] Tests (mirror rule): merge `tests/unit/lexic/grammars/test_abnf_2.py`
      into `test_abnf.py` — **every test ported** (incl. the fixpoint suite),
      imports → `lexic.grammars.abnf`; delete `test_abnf_2.py` only after.
- [ ] Gate (as Phase 0). `grep -rn "abnf_2" src tests` → empty.

## Phase 2 — GBNF self-grammar + reducer (the big new artifact)

**Files:** modify `src/lexic/grammars/gbnf.py` (add `GBNF_GRAMMAR: IrAst`,
`GBNF_NOISE`, `GBNF_REDUCTIONS`, `GBNF_REDUCER: Reducer`); a decode-side
action leaf in `ir/action.py` (escape mapping as data, per R2) if the
existing algebra can't express it. Template: the (now-folded) ABNF block in
`abnf.py`. Tests: `tests/unit/lexic/grammars/test_gbnf.py` + a new equivalence
gate in `tests/integration/`.

The IR grammar must accept exactly what `META_GRAMMAR` (gbnf.py:51-71) accepts:

- rules `name ::= alternation`, alternation `|`, sequences, items with postfix
  `? * + {n} {n,} {n,m}` quantifiers;
- atoms: quoted literals with GBNF escapes, charclasses
  `[...]` / `[^...]` with ranges and `\`-escapes, rule refs
  (`[a-zA-Z_][a-zA-Z0-9_-]*`), parenthesised groups;
- noise: whitespace runs and `#` line comments (Lark `%ignore`d them; here they
  are grammar rules routed to `ABNF`-style `DROP` in `GBNF_NOISE`) — directives
  (`# @start …`) keep working because `parse_directives` runs on raw text first.

Reduction semantics to reproduce from `parsing/meta_parser.py` (read it first —
it is the behavior contract): literal unquote + escape decode (per R2: in the
reducer's actions, mapping as render-side data — never on the AST, never a
flavour method); charclass
→ structured `IrCharClass(IrChr/IrRange…)`, `^` → `IrNot` wrap
(meta_parser.py:94-120); quantifier text → `IrQuantifier` (digit decode via
`IrUnradix`, precedent in the ABNF `repeat` reduction); group → `IrGroup`
semantics as meta_parser builds them; missing quantifier → `IrQuantifier(1,1)`.

- [ ] Write `GBNF_GRAMMAR` (GBNF-of-GBNF, in IR) + `GBNF_NOISE`.
- [ ] Write `GBNF_REDUCTIONS` + `GBNF_REDUCER` (pure IrSelf bodies; escape
      decode per R2 — no `IrCallable` reach-back into codec methods).
- [ ] **Equivalence gate (the contract):** for each of the seven
      `resources/ground_truth/*.gbnf` files:
      `parse_reduced(normalize(GBNF_GRAMMAR), text, GBNF_REDUCER)
      == MetaGrammarParser.for_flavour(GBNF_FLAVOUR).parse(text)`
      (structural IrAst equality; both paths alive during this phase).
      Park this as a temporary integration test — it is deleted with the Lark
      path in Phase 6 after converting to golden expectations if wanted.
- [ ] Self-hosting bonus check (not a gate): `GBNF_FLAVOUR.apply(GBNF_GRAMMAR)`
      re-parses to `GBNF_GRAMMAR` (the ABNF fixpoint pattern).
- [ ] Gate (as Phase 0).

## Phase 3 — ABNF grammar/reducer: close the subset gap (DP-3)

**Files:** modify `src/lexic/grammars/abnf.py` (`ABNF_GRAMMAR` +
`ABNF_REDUCTIONS`). Tests: `tests/unit/lexic/grammars/test_abnf.py` + the same
style of equivalence gate as Phase 2.

Constructs to add, matching the Lark `META_GRAMMAR` + `MetaGrammarParser`
behavior: `;` comments as noise (directives depend on comment syntax);
`[...]` option → group with `IrQuantifier(0,1)` (tag `ir_option` behavior);
incremental `name =/ body` (arms merged into the existing rule); `%s"…"` →
raw `IrLiteral`, `%i"…"` and bare `"…"` → **case-insensitive expansion**
identical to `_AbnfFlavour.normalize_literal` (alpha chars → per-char
`IrCharClass(IrChr(lower), IrChr(upper))` inside an `IrAlternation`-wrapped
sequence — abnf.py:306-318); num-seq `%x0D.0A` → code-point `IrLiteral`;
prose `<…>` recognised and rejected with `UnsupportedConstructError`; full
prefix-repeat forms `*`, `*m`, `n*`, `n*m`, `n`.

- [ ] Extend `ABNF_GRAMMAR` rules + noise; extend `ABNF_REDUCTIONS`.
- [ ] Keep the fixpoint suite green (self-grammar unchanged in what it *emits*;
      it only accepts more).
- [ ] **Equivalence gate:** every ABNF grammar string in
      `tests/integration/test_compile_grammar_abnf.py` and
      `test_cross_flavour.py`, plus anything `ABNF_FLAVOUR.apply` emits for the
      seven GBNF ground-truth spec sets, parses identically via both paths.
- [ ] `CORE_RULES`: confirm still consumer-less; leave in place (deleted
      Phase 6).
- [ ] Gate (as Phase 0).

## Phase 4 — instance-parsing bridge: `parsing_2/models.py` replaces Lark

**Files:** create `src/lexic/parsing_2/models.py`; modify
`src/lexic/compile.py`; export from `src/lexic/parsing_2/__init__.py`.
Test mirror: create `tests/unit/lexic/parsing_2/test_models.py`.

Design (consumer of `RuleSpec` — closed-set dispatch acceptable per the
deferred open-set rework note):

- `specs_to_grammar(specs: list[RuleSpec], start: str) -> IrAst` —
  `IrAst(IrTuple(*(s.to_ir_rule() for s in specs)), start)`. Specs already
  encode non-semantic min→0 optionality, so this is the faithful analogue of
  what `LarkBuilder` consumed.
- `ModelFold` — explicit-stack bottom-up fold (the `_FastReduce` frame
  discipline; **no recursion, no closures in eval-alikes** per house rules)
  from the engine's `ParseTree` to model instances. Per-rule behavior is the
  `build_transformer.py` contract, re-read it before writing:
  - synthetic-rule splicing: kids under a `SYNTHETIC_PREFIX` symbol splice
    inline (same rule `reduce.py` applies at reduce.py:166,293);
  - `kind == "sequence"`: consume kids against `spec.items` in grammar order —
    unquantified `IrLiteral` items consume their chars and produce no field;
    terminal items join consumed `IrLiteral` char-leaves to a `str`; rule-ref
    items take the sub-model (list when `hi` unbounded/>1; the optional-ref
    type-disambiguation trick at build_transformer.py:121-131 carries over);
    map positions to kwargs via `spec.field_map`; construct `classes[
    spec.class_name](**kwargs)`;
  - `kind == "value_str"`: the node's matched span joined to
    `cls(value=...)` — with the engine this is simply the concatenation of the
    subtree's terminal leaves (no Lark token-dropping workaround needed);
  - `kind == "alternation"`: pass the single sub-model through;
  - unknown kind / unmatchable item → explicit `UnsupportedConstructError`.
- `CompiledGrammar` (compile.py): fields become `classes`, `specs`,
  `grammar: IrAst` (normalized instance grammar, held so `compile_tables`
  identity-memoisation works across `.parse` calls), and the fold; `.parse(
  text)` = fold over `parse(self.grammar, text)` (strict single derivation —
  DP-2 if ambiguity fires). `_compile_core` / `compile_from_path` build these
  instead of calling `build_lark`. `import lark` leaves `compile.py`.

- [ ] Implement `specs_to_grammar` + `ModelFold` + engine-driven
      `CompiledGrammar.parse`.
- [ ] Rewire `compile.py`; delete its `lark` / `build_lark` imports (the
      `MetaGrammarParser` import stays until Phase 5).
- [ ] Gate: full suite — `tests/integration/test_parse.py`,
      `test_full_round_trip.py`, `tests/property/test_roundtrip.py` are the
      behavior contract. Round-trip invariant: `parse(text, g).to_text() ==
      text` for every ground-truth sample.

## Phase 5 — grammar-parse seam: flavours carry `grammar` + `reducer`

**Files:** modify `src/lexic/ir/flavour.py`, `src/lexic/grammars/gbnf.py`,
`src/lexic/grammars/abnf.py`, `src/lexic/compile.py`. Tests:
`tests/unit/lexic/ir/test_flavour.py`, `tests/unit/lexic/grammars/test_*.py`.

- [ ] `IrFlavour` gains the R1 ClassVars (annotation-only — ir/ stays leaf):

      ```python
      grammar: ClassVar[IrAst]      # the flavour's self-grammar (raw, un-normalised — ground truth)
      reducer: ClassVar[IrDispatch] # parse-tree → IrAst policy (a parsing Reducer at runtime)
      ```

      This is the final surface (R1) minus the deletions Phase 6 performs —
      no new method of any kind is introduced here or later.
- [ ] `_GbnfFlavour`: `grammar = GBNF_GRAMMAR`, `reducer = GBNF_REDUCER`;
      `_AbnfFlavour`: `grammar = ABNF_GRAMMAR`, `reducer = ABNF_REDUCER`.
- [ ] `compile_grammar` swaps `MetaGrammarParser.for_flavour(flavour)
      .parse(text)` for the engine: memoise `normalize(flavour.grammar)` once
      per flavour (module-level dict keyed by flavour name — keeps
      `compile_tables`' identity memo hot), `isinstance(flavour.reducer,
      Reducer)` narrow with explicit `UnsupportedConstructError` on miss, then
      `ast = parse_reduced(norm_grammar, text, flavour.reducer)`; verify the
      result is an `IrAst` (reduction contract), directives/start resolution
      unchanged.
- [ ] Gate: full suite (both integration compile_grammar suites now run the
      engine end to end). Phase 2/3 equivalence gates still green — last
      landing where both paths exist.

## Phase 6 — obliterate the Lark path

- [ ] `git rm -r src/lexic/parsing/` (meta_parser, lark_builder, transformer/).
- [ ] Test mirror: delete `tests/unit/lexic/parsing/` (test_meta_parser,
      test_lark_builder, transformer/, conftest) — **first sweep them for
      assertions whose behavior survives** (quantifier-text → IrQuantifier,
      charclass-text → IrCharClass/IrNot, literal decode): port those to the
      reducer test suites in `tests/unit/lexic/grammars/` before deleting
      ("port tests, never delete" — only drop what targeted deleted symbols).
- [ ] Strip the Lark surface: `ir/flavour.py` loses `meta_grammar`,
      `parse_quantifier`, `parse_charclass`, `normalize_literal`;
      `gbnf.py`/`abnf.py` lose `META_GRAMMAR`, their `parse_quantifier`/
      `parse_charclass`/`normalize_literal` bodies, and `CORE_RULES` — same
      port-first sweep for their tests.
- [ ] **R1 gate:** after the strip, `IrFlavour` and both concrete flavours
      define zero methods (nothing but the R1 ClassVars + `actions`); add a
      test asserting no callables are defined on the flavour classes beyond
      what `IrEmitter` inherits.
- [ ] Delete `utils/names.to_lark_name` + its block in
      `tests/unit/lexic/utils/test_names.py`. Keep `utils/quantifiers.py`
      (codegen/aliases.py still consumes it).
- [ ] Phase 2/3 equivalence-gate tests: the Lark side of the comparison is
      gone — convert to golden-expectation tests (engine output vs checked-in
      expected IrAst/spec shapes) or fold into the compile_grammar suites.
- [ ] `pyproject.toml`: remove `"lark>=1.3.1"`; `uv lock`/sync as needed.
- [ ] `tests/integration/test_layering_invariants.py`: strengthen — the engine
      package imports neither `lexic.grammars` nor `lexic.codegen`; runtime
      imports of `lexic.parsing` remain only via the sanctioned `compile.py`
      seam; drop assertions about the deleted modules.
- [ ] Gate: full suite; `grep -rln "lark" src/ | grep -v parsing_2` → nothing
      real (docstring mentions inside `parsing_2` are cleaned in Phase 7);
      `grep -rn "import lark\|from lark" src tests` → empty.

## Phase 7 — the rename: `parsing_2` → `parsing`

No two-pass ordering hazard (the old package is already gone).

- [ ] `git mv src/lexic/parsing_2 src/lexic/parsing` (includes README.md).
- [ ] `git mv tests/unit/lexic/parsing_2 tests/unit/lexic/parsing`;
      `git mv tests/unit/lexic/parsing/test_init_parsing_2.py
      tests/unit/lexic/parsing/test_init_parsing.py` (`test_init_<pkg>` rule).
- [ ] Rewrite `parsing_2` → `parsing` everywhere: imports, `:mod:`/`:class:`
      docstring refs, README self-references, the `"parsing_2: …"`
      error-message prefixes (engine.py/normalize.py/tables.py/kernel.py/
      forest.py — no test asserts on them), `pyproject.toml:41` marker text,
      `tests/performance/test_lazy_forest_perf.py`,
      `zzz_current_work/bench_parsing.py`,
      `zzz_current_work/spike_iterative_forest.py`.
- [ ] Leave `zzz_current_work/postleo/*` and `HANDOVER_beat_lark.md` untouched
      (historical record).
- [ ] Gate: full suite; `grep -rn "parsing_2" src tests pyproject.toml` →
      empty; bench sanity run.

## Phase 8 — docs sweep (same landing as Phase 7 or immediately after)

- [ ] Wiki: `.wiki/lexic/architecture.md` (module table: `parsing/` = IR-native
      Earley engine; Lark gone), `.wiki/lexic/flavour-system.md` (surface =
      metadata + emitter actions + `grammar` + `reducer`; Lark-era members
      gone), `.wiki/lexic/public-api.md` (`CompiledGrammar` engine-backed),
      `log.md` entries per landing.
- [ ] CLAUDE.md refresh: §Project layout (`parsing/` contents, no
      `transformer/`, `grammars/abnf_2.py` gone), §Pipeline flow
      (`MetaGrammarParser`/`build_lark` → engine seam), §Flavour system
      (grammar/reducer ClassVars, no `parse_quantifier`/`parse_charclass`/
      `meta_grammar`), §Import paths. Offer the user the diff rather than
      rewriting wholesale unprompted.

---

## Execution — model assignment per phase (R3; ask before each dispatch)

| Phase | Work | Model |
|---|---|---|
| 0 | engine `IrNot` support | Opus |
| 1 | fold `abnf_2` → `abnf.py` | Sonnet |
| 2 | GBNF self-grammar + reducer | **Fable** (most critical) |
| 3 | ABNF full-surface extension | Opus |
| 4 | instance bridge + `CompiledGrammar` re-drive | **Fable** (most critical) |
| 5 | flavour ClassVars + compile seam swap | Opus |
| 6 | obliterate Lark (port-first test sweeps) | Opus (porting judgment) |
| 7 | rename `parsing_2` → `parsing` | Sonnet |
| 8 | wiki + CLAUDE.md sweep | Sonnet |

Test-writing for every phase: Sonnet, dispatched after src lands, plan as
spec-contract. Never commit; leave landings staged.

---

## Test-migration table

| Old | New | How / when |
|---|---|---|
| `tests/unit/lexic/grammars/test_abnf_2.py` | merged into `test_abnf.py` | port all, then delete (P1) |
| `tests/unit/lexic/parsing/test_meta_parser.py` | behavior-surviving assertions → `tests/unit/lexic/grammars/test_{gbnf,abnf}.py` reducer suites | port then delete (P6) |
| `tests/unit/lexic/parsing/test_lark_builder.py` | dies with target | delete (P6) |
| `tests/unit/lexic/parsing/transformer/test_build_transformer.py` | contract re-expressed against `models.py` in `test_models.py` | port semantics (P4), delete (P6) |
| `tests/unit/lexic/ir/test_flavour.py` (Lark-surface tests) | reducer/grammar ClassVar tests | port (P5/P6) |
| `tests/unit/lexic/utils/test_names.py` (`to_lark_name`) | dies with target | delete (P6) |
| `tests/unit/lexic/parsing_2/**` | `tests/unit/lexic/parsing/**` | git mv (P7) |
| `tests/unit/lexic/parsing_2/test_init_parsing_2.py` | `tests/unit/lexic/parsing/test_init_parsing.py` | git mv + rename (P7) |

## Risks

- **Phase 2 is the long pole** — a full GBNF-of-GBNF + reducer. The
  equivalence gate over the seven ground-truth files is the only honest
  done-signal; do not proceed to Phase 5 on partial coverage.
- **Ambiguity surfacing (DP-2)** — Lark's `ambiguity="resolve"` may have been
  masking genuinely ambiguous instance grammars (optional-`ws` chains). First
  corpus failure stops the phase and goes to the user.
- **ABNF case-insensitivity (Phase 3)** — the reducer currently produces
  case-sensitive literals; cross-flavour round-trips will silently change
  behavior if the expansion isn't ported exactly.
- **Import-time weight** — after Phase 5, `import lexic` loads the engine via
  `grammars` → flavour singletons. Accepted consequence of "the flavour
  carries its grammar" (per the superseded plan's D5, unchanged).
- **Perf** — instance parsing moves from Lark to the engine; the engine wins
  on the ABNF product benchmark, but ground-truth instance grammars are a new
  workload. Run `bench_parsing.py` at each gate; a regression is a finding,
  not a blocker.
