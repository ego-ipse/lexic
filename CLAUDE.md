# CLAUDE.md — Lexic

Lexic is the grammar engine layer of Vyx (an agent-to-agent protocol). It compiles grammar files (GBNF, ABNF) into Pydantic model classes; instances parse text and round-trip back to grammar. Grammar is the ground truth — classes are its Python representation, not the other way around.

## Wiki

**[.wiki/index.md](.wiki/index.md)** — persistent knowledge base (architecture, IR shapes, field naming, decisions, cutover plan, log). Read it. **Update it whenever new relevant knowledge is added**: new API surfaces, design decisions, invariants, or anything non-obvious that would otherwise need re-derivation from code. Add a log entry in `log.md` for every significant wiki change.

## Before you touch anything

Read these documents before editing code:

- **[docs/STYLE.md](docs/STYLE.md)** — coding standards (smaller methods, SOLID, avoid deep indentation, fix root causes, no muting errors). Apply to every change.
- **§Key invariants** (below) — every change must preserve them.
- **Active work plans** live at `zzz_current_work/<yymmdd>-<name>/PLAN.md` —
  one directory per effort (start date + unique name); the plan carries its
  own progress ledger and, on completion, an OUTCOME note. Check the newest
  one when orienting. New plans copy `zzz_current_work/TEMPLATE.md` (goal,
  rulings, dispatch-policy table, tasks with gates, one-line ledger).
  Current: `zzz_current_work/260706-unified-parse-engine/PLAN_v2.md`.
- **Cutover complete (2026-05-13).** The IrItem-based pipeline is the only pipeline. Old Atom shape, `atoms.py`, `new_gbnf/`, `flavours.py` are all gone. See `.wiki/lexic/cutover-plan.md` and `.wiki/lexic/slice-b-status.md` for what remains.
- **RuleSpec cutover complete (2026-07-04).** The `RuleSpec` middle layer, `ir/derive.py`, `ir/spec.py`, `ir/emit.py`, `ir/naming.py`, `ir/topo.py`, `parsing/models.py`, and the whole `utils/` package are gone. One canonical `IrAst` drives codegen, instance parsing, emission, generation, and round-trip. See `zzz_current_work/260703-ir-codegen/PLAN.md` for the effort that landed it.

Specific instructions in this file override `docs/STYLE.md` for their domain.

## Commits

Never add `Co-Authored-By` lines. Commits belong entirely to the user.

## Session-usage watch (required in agent-heavy sessions)

When coordinating subagents, run `tools/usage_watch.sh <threshold> <poll-s>
<duration-s>` as a background task (e.g. `90 60 540`) and relaunch it on every
wake. It polls the user's five-hour session utilization (OAuth usage endpoint,
via the CLI's stored credentials — never print the token) and exits with
`ALERT <pct>` at the threshold or `OK <pct>` at the end of the window. At
**90%**: tell every in-flight agent to stop and report; write partial state
and a ledger line to the active plan dir. At **95%**: force it — stop
messages regardless of task state, plus a "NEXT SESSION — start here" block
above the plan's ledger.

**Idle-and-resume:** agents are told to hold (idle, state preserved), not
exit. Then launch `tools/usage_resume.sh` as a background task — it sleeps
until the five-hour window resets (+10 min grace), confirms utilization
dropped, and exits `RESUME <pct>`, re-invoking the coordinator — and
schedule a chained wakeup as fallback. On resume: re-arm the watcher,
`SendMessage` every held agent to continue. One cold context re-read per
party at resume is expected (5-min prompt-cache TTL); it bills to the fresh
window.

## Commands

Always prefix with `uv run`. Never run `pytest` or `ruff` bare.

```bash
uv run pytest tests/ -q                  # full suite (~1568 tests)
uv run pytest tests/unit/lexic/ -q       # unit only
uv run pytest tests/integration/ -q      # integration only
uv run ruff check src/ tests/            # lint
uv run pylint src/lexic/path/to/file.py  # per-file quality gate
```

**Mechanical fixes first:** run `tools/auto_fix.sh` before touching code by hand. It runs `ruff format`, `isort`, and `ruff check --fix` in sequence.

If `ruff` flags files in `generated/`, fix the template in `src/lexic/codegen/model_emitter.py`, not the generated file.

## Current state — one IR-native pipeline, no Lark, no RuleSpec

The IrItem-based cutover (2026-05-13) is complete, and the **primitive-node
model (V2)** migration is done: nodes now *are* their payload (str-leaves
subclass `str`, variadic collections subclass `tuple`, fixed-arity records
are `IrNamedTuple` records — the node IS the tuple, fields read by name or by
index) — `IrType`/`coerce`/`IrStrLeaf`/`IrCollection`/`_items_attr` are gone.
See §IR types.

A second cutover (Lark→Earley, 2026-07-02/03) is also complete:
**`src/lexic/parsing/` is a native Earley engine, not a Lark wrapper** — Lark
is gone from source entirely (it survives only as
`tools/benchmark/parse_bench.py`'s external reference baseline). This one
engine drives *both* grammar-text parsing (`parse_grammar` → `parse_reduced`
against each flavour's own self-grammar) and generated-instance parsing
(`CompiledGrammar.parse` → `parse_first` + a fold) — there is no separate
meta-grammar-parser layer anymore. `IrFlavour` (`ir/flavour.py`) carries its
self-grammar and parse policy as data (`grammar: ClassVar[IrAst]`,
`reducer: ClassVar[IrDispatch]`), not as parser methods — see §Flavour system.

A third cutover (RuleSpec → IR-native codegen, 2026-07-03/04) is also
complete: the `RuleSpec` middle layer is gone. One canonical `IrAst` — parsed,
then **canonicalized** to a language-preserving normal form (`ir/canonical.py`)
so two flavours describing the same language converge on the same tree —
drives everything: codegen, instance parsing, emission, generation,
round-trip. Generated classes carry `__grammar__: ClassVar[IrRule]` directly
(the class's own rule, from the *codegen* grammar — post group/arm-hoisting)
and every bound field an `IrBind(item, mode, semantic)` in its `Annotated`
metadata, tying it to a positional slot in that rule's sequence arm — no
parallel spec object. Instance parsing is a **positional fold**
(`parsing/fold.py`'s `PositionalFold`) over the *real* codegen grammar
(`normalize()` replaces items in place, so `kids[i] ↔ items[i]`) — no
`--f<idx>` wrapper rules, no name protocol.

- IR shape: `IrItem`-based nodes (`ir/nodes.py`) — `IrLiteral`, `IrCharClass`,
  `IrRuleRef`, `IrItem(atom, quantifier)`.
- Entry: `compile_text` / `compile_from_path` in `compile.py` →
  `canonical_grammar` (parse + canonicalize + directive flags) →
  `build_codegen_grammar` (`lexic.codegen.passes` — hoist groups, hoist arms,
  relax non-semantic refs) → `compute_binding` (`lexic.codegen.binding`) →
  `codegen` (`lexic.codegen`, emits `Annotated`/`IrBind` fields) → fold config
  → `PositionalFold` (`lexic.parsing.fold`); `parse_grammar(text, flavour)` is
  the public grammar-text → `IrAst` seam, unchanged by this cutover.
- Old `atoms.py`, `new_gbnf/`, `flavours.py`, `codegen/ir_builder.py`,
  `codegen/lark_builder.py`, `codegen/transformer/` are all gone (2026-05-13
  cutover). `parsing/meta_parser.py`, `parsing/lark_builder.py`,
  `parsing/transformer/` are gone (2026-07-02/03 cutover). `ir/derive.py`,
  `ir/spec.py` (`RuleSpec`), `ir/emit.py`, `ir/naming.py`, `ir/topo.py`,
  `parsing/models.py`, and the whole `utils/` package are gone (2026-07-04
  cutover) — no `parsing_legacy`/`parsing_old` shim, no RuleSpec shim, of any
  kind. `ir/regex_portable.py` (unrelated, pre-dates this effort) is also gone.

## Project layout

```
src/lexic/
  __init__.py
  base.py               GrammarModel base — to_text(), to_grammar(), semantic_dump()
                        (walks __grammar__: ClassVar[IrRule] + each field's IrBind)
  compile.py            compile_text(), compile_from_path(), canonical_grammar(),
                        parse_grammar() — the sole runtime seam onto codegen + the engine
  exceptions.py         LexicError hierarchy (see §Error vocabulary)
  parse.py              parse(text, grammar_path) → GrammarModel  [thin wrapper over compile]
  generate.py           random string generator — walks a rule-name → IrRule mapping
                        (a canonical grammar's rules) directly, no spec layer

  ir/
    __init__.py         public IR surface — nodes, action algebra, dispatch,
                        IrBind, canonicalize, RuleOrder
    meta.py             IrMeta (ABCMeta) — dataclass-transform + auto-derived
                        _bound; Singleton/Borg/IrSingleton metaclasses
    base.py             IrSelf[Iri,Ir_co] generic root; IrNode ABC; IrAtom role
                        marker; three tiers: IrScalar value-leaves (IrStr ⇒
                        IrLiteral/IrCharClass/IrRuleRef; IrInt), IrTuple variadic
                        (IrSeq homogeneous — IrSequence, IrAlternation),
                        IrNamedTuple fixed-arity records (the node IS the tuple;
                        fields read by name or by index) — IrItem, IrQuantifier,
                        IrRule, IrAst; IrCachingTuple (IrNamedTuple whose Field()
                        defaults resolve fresh per instance — dispatcher/transformer
                        state); IrNoneType/IrNone sentinel. IrScalar hosts
                        eval/eq/ne/hash/repr (type-aware: distinct leaf kinds never
                        equal); IrScalar.__new__ forwards the payload to str/int (so
                        type[IrScalar] is constructor-callable); IrStr/IrInt carry
                        only _bound
    nodes.py            Concrete grammar-AST nodes on the base.py spine: IrLiteral,
                        IrCharClass (intrinsic pattern()/members()/sample()/
                        normalized()/complement()), IrRuleRef, IrSequence,
                        IrAlternation, IrBounds/IrQuantifier/IrRange, IrItem,
                        IrRule(name, body, semantic=True), IrAst(rules, start) —
                        non_semantic is a derived property, not a field
    operators.py        IrOp(IrStr) infix-operator leaf (no Cmp enum), IrOpNode +
                        Monadic/Dyadic/VariadicOp, IrNot, IrEq, IrAnd
    action.py           Action-algebra nodes: IrField (out: type[IrScalar], reads
                        typed attrs), IrCompare/IrAnd (-> IrInt), IrChild, IrChildren,
                        IrConcat, IrJoin, IrCond (test: IrSelf), IrThis, IrReturn,
                        IrAction; default bodies IrPass, IrWalk, IrRaise, IrEmit,
                        IrRebuild
    mapping.py          IrMapping/IrMap/IrTypeMap (concrete-first MRO type→IrSelf
                        table) / IrMultiMap — IR-native mapping nodes
    walk.py             IrDispatch[Iri,Ir_co] — an IrCachingTuple of
                        (actions, default); actions is an IrTypeMap (not a tuple);
                        presets IrVisitor, IrTransformer, IrEmitter. Does NOT walk
                        children automatically — action bodies own recursion
    flavour.py          IrFlavour ABC — IrEmitter subclass + ClassVars (name,
                        extensions, line_comment, escapes: EscapeCodec instance,
                        grammar: IrAst — the flavour's self-grammar, reducer:
                        IrDispatch — a parsing.reduce.Reducer at runtime) + actions.
                        Zero methods beyond the inherited emitter protocol —
                        parse_quantifier/parse_charclass/normalize_literal/
                        meta_grammar are gone with the Lark path, nothing replaces
                        them as methods
    canonical.py        canonicalize(IrAst) → IrAst — language-preserving normal
                        form (charclass/alternation/literal-run merges, IrNot →
                        positive spans, name folding, canonical rule order); the
                        mandatory second stage of compile.py's canonical_grammar
    bind.py             IrBind(item, mode, semantic=True) — the field-binding
                        marker generated fields carry as Annotated metadata;
                        BIND_MODES = (text, gtext, model, models)
    order.py            RuleOrder — deterministic start-first ordering over a
                        supplied edge relation; by_refs/order_by_refs (ref-edges,
                        canonicaliser's rule order) and ordered_parents_first
                        (parent-edges, codegen emission order)
    escapes.py          EscapeCodec ABC + CANONICAL_ESCAPES

  grammars/
    __init__.py         get_flavour(), flavour_for_extension(), register_flavour()
                        eagerly registers GBNF_FLAVOUR and ABNF_FLAVOUR singletons
                        on import
    gbnf.py             GBNF flavour — one flat module (no subpackage):
                        GBNF_ACTIONS (emit half), GBNF_GRAMMAR + GBNF_REDUCTIONS +
                        GBNF_NOISE + GBNF_REDUCER (parse half — the full GBNF
                        surface, natively, no Lark meta-grammar), private
                        _GbnfEscapes + public GBNF_ESCAPES singleton, private
                        _GbnfFlavour + public GBNF_FLAVOUR singleton
    abnf.py             ABNF flavour — same shape as gbnf.py. Full RFC 5234+7405
                        surface (num-seq, [...] option, comments/folding, %s/%i,
                        %d/%b, prose-refusal, incremental =/)
    json.py             JSON_GRAMMAR — the JSON grammar (RFC 8259) authored
                        directly as IrAst, not derived from either flavour; the
                        flavour-neutral canonical target both front-ends reduce to

  codegen/
    __init__.py         codegen(canonical, codegen_grammar, binding, stem) →
                        dict[str, type] — writes generated/<stem>.py (ruff-formatted
                        + model_rebuild()'d so IrBind metadata resolves), loads and
                        returns classes
    passes.py           Grammar→grammar codegen passes: hoist_groups (quantified
                        ref-bearing groups → named helper rules), hoist_arms
                        (every multi-item/non-ref alternation arm → a named
                        <rule>-arm<N> rule — restores the single-arm premise the
                        positional fold rests on), relax_non_semantic (min=0 on
                        refs to semantic=False rules); build_codegen_grammar()
                        composes all three
    binding.py          compute_binding(codegen_grammar) → list[RuleBinding]
                        (rule_name, class_name, parent_class_name, kind, fields:
                        dict[str, IrBind]) — the open-table successor of
                        derive_specs's classify/parents/naming; also hosts
                        CHARCLASS_NAMES/LITERAL_NAMES, class_name_for (absorbed
                        to_pascal), has_ruleref
    model_emitter.py    emit_module_source(canonical, codegen_grammar, binding,
                        stem) → str — Annotated[<type>, IrBind(...)] fields, a
                        per-class __grammar__: ClassVar[IrRule] footer (from the
                        codegen grammar), and module-level GRAMMAR (canonical
                        IrAst) + START footers
    aliases.py          PatternAlias, collect_aliases() — module-level type
                        alias hoisting; also hosts _bounds_to_suffix (regex
                        quantifier suffix, absorbed from utils/quantifiers.py)

  parsing/
    __init__.py         Public API: recognize, parse, parse_first, parse_reduced,
                        parse_forest, derivations, is_ambiguous — a native Earley
                        engine (SPPF, Scott 2008) over IrAst-shaped grammars, not
                        a Lark wrapper. Drives BOTH grammar-text parsing
                        (flavour.grammar + flavour.reducer) and generated-instance
                        parsing (the codegen grammar + PositionalFold)
    tables.py           ParserTables, compile_tables() (memoised by IrAst identity)
    kernel.py           Kernel (predict/scan/complete, Leo optimisation), FastTree;
                        longest_start_completion — public windowed prefix-completion
                        seam for the PDA island sub-parse (additive, off the main
                        run() fast path; hybrid-PDA 260705)
    chart.py            Chart / Links — the decoded SPPF
    engine.py           Per-capability orchestration nodes behind the public API
    forest.py           ParseTree, SppfNode
    reduce.py           Reducer — forest → IrAst (the meta-notation seam)
    normalize.py        Desugar IR into classical Earley-shaped rules
    fold.py             PositionalFold — generic positional ParseTree → object
                        fold over the codegen grammar (kids[i] ↔ items[i], no
                        RuleSpec/pydantic/codegen imports); RuleFold/FieldFold
                        plain-data config; lift_optional_nullables (R? → R for
                        nullable R, engine-ambiguity policy); collapsed_fold_tables
                        (run-collapse licence: safe iff no constructor-bearing
                        rule among a run's unit leaves)
    charsets.py         CharSet — polarity-aware co-finite char sets (the
                        hybrid-PDA analysis substrate; 260705 effort)
    analysis.py         GrammarAnalysis — FIRST/hard-FIRST/FOLLOW/nullability
                        fixpoints + pivot-6 decision taxonomy (island/stopset/
                        LL(2) pairs) over a lifted codegen grammar; islands +
                        fail_islands (semantic F1 stop-set-escape rules whose refs
                        must fail to the engine, a subset of islands); open
                        IrTypeMap atom dispatch, raising default; homes
                        nullable_names (single source for fold's
                        lift_optional_nullables) (hybrid-PDA; 260705 effort)
    pda_tables.py       compile_pda(lifted, instance_grammar, fold_config) →
                        PdaTables — per-(rule, hard-continuation) clone compiler
                        (pivot 3); flat tuple-coded ItemSpec (lit/cc/ref/grp) +
                        StopGate/PairGate loop gates, FIRST-gated ArmSpec + baked
                        RuleFold; islands not cloned (IslandRef marker + lazy
                        per-island ParserTables cache; IslandRef.fail marks a
                        fail-island — a semantic F1 escape whose ref raises
                        PdaFail, never parsed); open IrTypeMap atom
                        dispatch, raising default. The CloneSpec/ItemSpec
                        NamedTuples are the compiler INTERMEDIATE (what tests
                        pin); the spec→flat bridge (_flatten_program etc.) lowers
                        them once per compile into the int-coded PdaProgram, kept
                        on PdaTables alongside .clones (.clones for islands/
                        introspection, .program for the loop). compile_pda,
                        PdaTables, IslandRef, spec NamedTuples import from here
                        (Task 8 flatten; hybrid-PDA; 260705 effort)
    pda_flatten.py      The leaf half of the flatten: the int-coded runtime
                        program (_FlatClone/_FlatArm/PdaProgram, _OP_* op-codes,
                        pre-resolved (chars,negated) membership sets) + the
                        post-flatten optimizer passes (_optimize_program:
                        exactly-once terminal/call specialisation, value_str
                        inlining, frame-less leaf marking, pass-through dispatch
                        conversion). Imports nothing from pda_tables (a leaf
                        w.r.t. the compiler + specs); the kernel walks it (split
                        out of pda_tables for C0302; hybrid-PDA; 260705 effort)
    pda_kernel.py       PdaKernel/parse_pda — the fused predictive runtime: an
                        explicit descent stack of flat list frames (no Python
                        recursion; the kernel.py int-array explicit-stack
                        precedent — PdaKernel is the class cursor) over the flat
                        PdaProgram, building the model directly during the walk
                        (fold fusion — no ParseTree). Int-coded op dispatch,
                        terminal quantifier loops matched inline (no per-char
                        call). Per-parse state on the cursor, tables shared;
                        capture frames own per-item span (ends) + sub-model
                        (sinks) capture bubbling to the nearest bound item,
                        transparent frames (groups / fold=None clones) funnel
                        through; an
                        island ref runs a windowed Earley sub-parse over
                        island_tables (longest completion, doubling window, FastTree
                        + first-derivation fallback), folds it through the supplied
                        PositionalFold and splices the sub-model into the current
                        capture (PdaKernel(tables, text, fold); fold=None ⇒ island
                        raises PdaFail, the island-free path; a fail-island ref
                        always raises PdaFail, independent of fold). PdaFail is
                        internal, never user-facing (hybrid-PDA; 260705 effort)
    lexruns.py, trampoline.py

tests/
  unit/lexic/           structural mirror of src/lexic/
  integration/          test_compile_grammar_{gbnf,abnf}, test_cross_flavour,
                        test_codegen_ir, test_full_round_trip,
                        test_layering_invariants, test_parse, …
  property/             hypothesis round-trip tests
  paths.py              GROUND_TRUTH, GENERATED path constants

resources/ground_truth/ eight .gbnf test grammars (arithmetic, c, chess,
                        japanese, json, json_arr, json_ws, list) plus two .abnf
                        siblings (arithmetic, json) for cross-flavour parity
generated/              auto-generated Pydantic modules — git-ignored; never edit directly.
                        compile_from_path writes <grammar-stem>.py (e.g. arithmetic.py);
                        compile_text writes anon_<sha1>.py. Files are ruff-formatted.
```

## Architecture

### Pipeline flow

```
grammar text ──► _scan_directives(text, flavour.line_comment) ──► (start, non_semantic)
             │    [private helper in compile.py — pre-lexical comment scan]
             └──► parse_grammar(text, flavour)  [public seam, compile.py]
                  = parse_reduced(normalize(flavour.grammar), text, flavour.reducer)
                                                                   │  (lexic.parsing — the
                                                                   │   Earley engine; flavour.grammar
                                                                   │   is IrAst, flavour.reducer a Reducer)
                                                                   ▼
                                                                 IrAst
                                                                   │  canonicalize(ast)  [ir/canonical.py —
                                                                   │  language-preserving normal form; two
                                                                   │  flavours of the same language converge]
                                                                   ▼
                                                          canonical_grammar()  [compile.py's public front half:
                                                                   │           parse + canonicalize + directive
                                                                   │           flags → start bound, named rules
                                                                   │           reconstructed semantic=False]
                                                                   ▼
                                                              canonical IrAst
                                                                   │
                                                                   ▼
                                        build_codegen_grammar(ast)  [lexic.codegen.passes:
                                                                      hoist_groups → hoist_arms →
                                                                      relax_non_semantic]
                                                                   │
                                                                   ▼
                                                          THE codegen grammar (one IrAst)
                         ┌─────────────────────────────────────────┼──────────────────────────┐
                         ▼                                         ▼                          ▼
              compute_binding(codegen_grammar)              codegen(canonical,        GBNF_FLAVOUR / ABNF_FLAVOUR
              (lexic.codegen.binding — class            codegen_grammar, binding,     flavour_singleton.apply(node)
              names, kinds, parents, field names,             stem)                    (IrEmitter on IR-AST tree)
              open IrDispatch tables)                writes generated/<stem>.py
                         │                            (Annotated/IrBind fields,
                         │                             __grammar__ footers;
                         │                             returns dict[str, type])
                         └─────────────┬───────────────────────────┘
                                       ▼
                     fold config (plain data: per-rule ctor + kind +
                     n_items + [(item idx, mode, field, lo)])
                                       │
                                       ▼
          instance_grammar = normalize(lift_optional_nullables(codegen_grammar))
          — the SAME normalize as the grammar-text path, so the engine's
          identity-memoised tables are shared shapes
                                       │
                                       ▼
          CompiledGrammar(classes, grammar=canonical ast, instance_grammar, fold, tables,
                          pda=_build_pda(lifted, instance_grammar, fold_config))
          .parse(text) = PDA-first: parse_pda(pda, text, fold) when pda is not None,
                         PdaFail → engine fallback fold.apply(parse_first(instance_grammar,
                         text, tables)). pda is None on whole-grammar opt-out (unsupported
                         construct, or start rule is itself an island).
```

Entry points: `compile_text(text, flavour)` and `compile_from_path(path)` in
`compile.py`. Both run `canonical_grammar` → `build_codegen_grammar` →
`compute_binding` → `codegen` → fold config → `normalize(lift_optional_nullables(...))`
and return a `CompiledGrammar`. `compile.py` is the sole runtime seam onto
both `lexic.codegen` and the engine (`lexic.parsing`/`.fold`/`.normalize`/`.reduce`).

`parse_grammar(text, flavour)` (re-exported from `lexic`) is the public
grammar-text → `IrAst` seam — `canonical_grammar` calls it; so do transpilers
(`getting_started/ex04`). `canonical_grammar(text, flavour)` is the public
front half (parse + canonicalize + directive flags → flagged `IrAst`);
`generate.py` builds on it directly.

`parse_grammar` normalizes and memoises each flavour's `grammar` ClassVar
once per flavour name (`compile.py`'s `_NORM_GRAMMAR_CACHE`) so the engine's
identity-keyed `compile_tables` stays hot across calls.

### Layering rules

Arrows go one way. **Violating any of these is a review-blocking offence.**

```
lexic.ir        ← lexic.grammars       grammars read and write IR
lexic.ir        ← lexic.parsing        the engine reads and writes IR only
lexic.ir        ← lexic.codegen        codegen reads and writes IR
lexic.ir        ← lexic  (runtime)     runtime reads IR
lexic.codegen   ✗ lexic.grammars       codegen is IR-native; it needs no flavour adapters
lexic.parsing   ✗ lexic.grammars, lexic.codegen   (the engine is a leaf w.r.t. both)
lexic (runtime) ↗ lexic.codegen, lexic.parsing    runtime NEVER imports either directly — two exceptions below
```

**The two deliberate exceptions:**
1. `base.py` imports `get_flavour` from `lexic.grammars` to drive `to_grammar()`
   (which calls `get_flavour(flavour).apply(self.__grammar__)` — `__grammar__`
   is already an `IrRule`, no intermediate conversion). The GBNF singleton is
   `lexic.grammars.gbnf.GBNF_FLAVOUR`. Explicit, eager.
2. `compile.py` is the single runtime seam onto both `lexic.codegen`
   (`codegen`, `build_codegen_grammar`, `compute_binding`) and the Earley
   engine (`lexic.parsing` — `parse_first`, `parse_reduced`;
   `lexic.parsing.fold` — `PositionalFold`, `RuleFold`, `FieldFold`,
   `collapsed_fold_tables`, `lift_optional_nullables`;
   `lexic.parsing.normalize.normalize`; `lexic.parsing.reduce.Reducer`). All
   explicit, all public.

No `TYPE_CHECKING` dodges. No lazy intra-function imports of `lexic.codegen`
or `lexic.parsing` from runtime modules. If a runtime module needs something
that lives in codegen or the engine, move the thing.
`tests/integration/test_layering_invariants.py` enforces all of this by
static grep, including that only `compile.py` may import `lexic.parsing`
among top-level runtime modules.

## IR types (`ir/base.py` + `ir/nodes.py` + `ir/action.py`)

The **primitive-node model** ("V2"): a node *is* its payload. Every IR node is callable: `node.__call__(d, n, nc) -> Self` (identity) and carries the action protocol `eval(d, n, nc) -> Ir_co`. `IrSelf[Iri, Ir_co]` is the generic root supplying the identity `__call__`, default `eval`, `children`/`rebuild`, and the `bound`/`bind` helpers. `Iri` is the input node type; `Ir_co` the covariant return type. `_bound` is auto-derived from the **last** own type parameter (`Ir_co`) or set explicitly (`IrStr._bound = str`, `IrTuple._bound = tuple`, `IrEmit._bound = IrLiteral`). `IrNode[Iri, Ir_co](IrSelf, ABC)` adds `__repr__`-is-codegen (no `__str__`/`_str_name` cascade).

**Absence** is the singleton `IrNone` — the value of `@final IrNoneType(IrSelf)`, never Python `None`. It IS-A `IrSelf`, so it fits every dispatch slot and keeps signatures union-free. Use `IrNoneType` for `isinstance`/annotations; pass bare `IrNone`; compare `x is IrNone`.

**Three tiers — the node IS its payload (there are NO `.value` / `.items` / `.arms` accessors):**

```
value-leaves IrScalar(IrLeaf)              IrStr ⇒ IrLiteral/IrCharClass/IrRuleRef; IrInt — the node IS the scalar
variadic     IrTuple[*Ts]/IrSeq[T](tuple)  IrSequence, IrAlternation — the node IS its children tuple
records      IrNamedTuple[*Ts](tuple)      IrItem, IrQuantifier, IrRule, IrAst — the node IS the tuple, by name or index
```

`IrScalar(IrLeaf)` is the value-leaf base; it hosts `eval` (self-evaluating), the type-aware `__eq__`/`__ne__`, `__hash__`, and codegen `__repr__` — all delegating to the primitive via `super()` / `self._bound`. `IrScalar.__new__(*args)` forwards the payload to `str`/`int`, which (a) lets `object.__init__` tolerate the construction arg and (b) makes `type[IrScalar]` constructor-callable (used by `IrField.out`). `IrStr(IrScalar, str)` and `IrInt(IrScalar, int)` carry only their explicit `_bound`. A **truth value is `IrInt ∈ {0,1}` — there is no `IrBool`** (`IrCompare`/`IrAnd` return it).

`IrAtom(IrNode)` is a **non-generic role marker** mixed into atoms (`IrLiteral`/`IrCharClass`/`IrRuleRef`/`IrAlternation` as an inline group/`IrNot`); `IrItem.atom: IrAtom` accepts any. There is no separate `IrGroup` type — an inline `(...)` group is just an `IrAlternation` used as an atom.

- **str-leaves** subclass `str` — use the leaf directly as a `str` (`leaf == "x"`, `LITERAL_NAMES.get(leaf)`). The type-aware `__eq__`/`__ne__`/`__hash__` live on `IrScalar` (shared by `IrStr` and `IrInt`): `IrLiteral("x") != IrRuleRef("x")` (distinct leaf kinds never compare equal) yet `IrLiteral("x") == "x"` (plain-primitive compatibility preserved). This keeps structural tree equality/hashing honest (so `@cache`, dict/set keys, and `tree == tree` work) while leaves still match plain-`str`/`int` dict keys.
- **variadic collections** subclass `tuple` — iterate/index the node directly (`seq[0]`, `for arm in alt`). `IrTuple[*Ts]` is the heterogeneous base; `IrSeq[T]` names a homogeneous specialisation (`IrSequence(IrSeq["IrItem"])`, `IrAlternation(IrSeq[IrSequence], IrAtom)`). Construct variadically: `IrSequence(*items)`, `IrAlternation(seq1, seq2)`, `IrAst(IrSeq(*rules), start)`. Authoring coercion widens `__new__` on `IrSequence`/`IrAlternation`/`IrItem`/`IrRule` so a bare atom/item/sequence lifts to the wrapping shape (`IrItem(IrLiteral('a'))`, `IrRule("cr", IrCharClass(...))`) — unknown types pass through unchanged so transformer rebuilds are undisturbed.
- **records** are `IrNamedTuple[*Ts]` subclasses — `dataclass_transform`-decorated fixed-arity named tuples: storage IS the tuple (no separate per-field slots), each class-body annotation names a field in declaration order, and a `property(itemgetter(i))` descriptor makes `rec.field` and `rec[i]` the same read. The ClassVar `_child_attrs` names which fields are dispatched children (defaults to all fields; a record with scalar-only payload, e.g. `IrBounds`, declares an empty `_child_attrs`) — no `_items_attr`, `IrCollection` is gone. `IrItem(atom, quantifier)`, `IrQuantifier(lo: int, hi: int | IrNone)`, `IrRule(name: str, body: IrAlternation, semantic: bool = True)`, `IrAst(rules: IrSeq[IrRule], start: str)` — note `IrAst.children()` returns `(rules_tuple,)`, so code wanting the rules iterates `ast.rules`. A record's repr **omits the trailing run of default-valued fields** (still valid codegen — the omitted fields reconstruct to their defaults): `IrItem(IrLiteral('a'), IrQuantifier(1,1))` reprs as `IrItem(IrLiteral('a'))`. `IrRule.semantic` is `False` for structural-noise rules (whitespace/comments/delimiters) — compile-channel metadata, so `IrRule.__eq__`/`__hash__` exclude it (a freshly parsed rule is `semantic=True` while the authored self-grammar flags its noise rules `semantic=False`; the exclusion is what keeps the self-hosting fixpoint). `IrAst` has **no** non_semantic field and no equality override — plain tuple equality over `(rules, start)` composes `IrRule.__eq__`; `IrAst.non_semantic` is a **derived property** (frozenset of names of rules with `semantic=False`) feeding the codegen passes (`lexic.codegen.passes.relax_non_semantic`) and the flavour NOISE maps. `IrCachingTuple[*Ts]` is a further `IrNamedTuple` specialisation whose `Field(default=...)`/`Field(default_factory=...)` field values resolve to a fresh per-instance value (deep-copied/factory-called) rather than one object shared across every instance — used for dispatcher/transformer state (`IrDispatch.actions`, `_HoistTransformer.helpers`).

`IrLiteral` keeps a **dual role**: a grammar-AST leaf and an action-language constant — distinguished at eval time by the `nc` parameter; see [[ir-shapes]].

**Action-algebra nodes** (`ir/action.py`): `IrField` reads a named attribute and wraps it via a runtime `out: type[IrScalar]` (default `IrStr`; `IrField("min", IrInt)` reads an int) — cast-free, open (any `IrScalar` subtype), no enumerated union; `IrOp(IrStr)` (`ir/operators.py`) is an infix-operator leaf (the node IS its operator string, e.g. `IrOp(">")`; **no `Cmp` enum**) whose `eval` applies the mapped `operator` builtin to the operands in `nc`; `IrCompare(left, op: IrOp, right)` evals both operands and hands them to `op` → `IrInt(0/1)`; `IrAnd(IrSeq[IrSelf])` is a short-circuit conjunction → `IrInt`; `IrLambda` (`ir/base.py`) is the procedural escape hatch; `IrChild`/`IrChildren` resolve children; `IrConcat`/`IrJoin` build strings (`parts: IrTuple`); `IrCond(test: IrSelf, then_op, else_op)` branches on `test.eval(...)` (truthy ⇒ `then_op`); `IrThis` is the identity body returning the dispatched node `n`; `IrReturn` short-circuits — it lazy-evaluates its body against `(d, n, nc)` and re-raises the result via the `_Return` BaseException, defaulting to `IrThis()` so `IrReturn()` surfaces the matched node (the find-first pattern); `IrAction(target_type, body)` binds a node type to a body. Default bodies: `IrPass`, `IrWalk`, `IrRaise`, `IrEmit`, `IrRebuild`. Comparison/branch operands are typed `IrSelf` (not `IrNode`) because `IrNode`'s `Ir_co` is invariant — a value operand like `IrField` wouldn't be assignable to a bare `IrNode` slot.

**Dispatch** (`ir/walk.py`): `IrDispatch[Iri, Ir_co]` is an `IrCachingTuple` of `(actions, default)` — `actions` an `IrTypeMap` (concrete-first MRO type→`IrAction` table, not a plain tuple), `_child_attrs = ()` so the dispatcher is never itself walked as a grammar node. It does **not** walk children automatically — action bodies own recursion. Resolution is the map's own concrete-first MRO lookup (one `getattr` per `type(n).__mro__` entry); falls back to `default` only on a full miss. Entry seams: `eval(d, n, nc)` (protocol) and `apply(root)` (façade, catches `IrReturn`). Presets: `IrVisitor` (default `IrWalk`), `IrTransformer` (default `IrRebuild`), `IrEmitter` (default `IrEmit`).

> **Open-set consumer rework complete (2026-07-04).** `generate.py` (`_GEN_ATOM` + `_Generator`), `codegen/model_emitter.py` (`_MODEL_TYPE`/`_GTEXT_TYPE`/`_TEXT_TYPE` per fold-mode, `_VALUE_TYPE`), and `codegen/aliases.py` (`_FRAGMENT`) all moved their atom-type dispatch onto open `IrDispatch`/`IrTypeMap` tables with raising defaults, matching `codegen/binding.py`/`codegen/passes.py`'s idiom; every silent fallback (`generate`'s old `return ""`) is now an explicit `UnsupportedConstructError`, and the post-canon-dead `IrNot` branches are deleted. `_group_union_type` (a ref-arm filter, not a classification ladder) and `_visit_item`'s recursing group-frame `isinstance` were deliberately left as-is — they aren't atom-type dispatch. See the open-classes principle and [[decisions]].

### `kind` semantics (`codegen/binding.py`)

There is no `RuleSpec.kind` field anymore — `classify_rule(rule)` (in the binding view) derives a rule's `RuleKind` fresh from the codegen grammar, and `RuleBinding.kind` carries the result:

- `"value_str"` — no `IrRuleRef` anywhere in the body; the class emits a single implicit `value` field (no `IrBind` — the fold keys off `kind`, not a bind).
- `"alternation"` — abstract class; after `hoist_arms` every non-empty arm is a single unit ruleref, so the class is a field-less pass-through (the matched arm's sub-model identifies itself).
- `"sequence"` — concrete class; fields come from `bind_fields` over the rule's single sequence arm, each an `IrBind(item, mode, semantic)` in the field's `Annotated` metadata.

Multi-arm `value_str` (a pure-literal alternation with no rulerefs) becomes a `Literal[...]` field type in the emitter (`_value_str_type`); a rule with an empty alternate arm (`_has_empty_arm`) forces every field of its non-empty arm `Optional`.

## Flavour system (`ir/flavour.py`)

An `IrFlavour` IS-AN `IrEmitter` — its `actions` table (an `IrTypeMap`, not a
tuple) holds the per-IR-type rendering rules, and `apply(root)` walks an IR
tree to a string. It also carries its own self-grammar and parse policy as
data — `grammar: ClassVar[IrAst]` and `reducer: ClassVar[IrDispatch]` (a
`lexic.parsing.reduce.Reducer` at runtime) — driven by the Earley engine
(`lexic.parsing`) from the outside; **the flavour itself defines zero parsing
methods**. Each flavour module exposes the class as **private**
(`_GbnfFlavour`) and the constructed singleton as **public** (`GBNF_FLAVOUR`),
in one flat module (`grammars/gbnf.py` — no subpackage).

```python
@dataclass(frozen=True, slots=True, repr=False)
class _MyFlavour(IrFlavour):
    actions: IrTypeMap = MY_ACTIONS   # class-level default — the emit half
    # NOTE: do NOT use init=False — it suppresses the generated __init__ so
    # `actions` silently resolves to the empty IrDispatch default at runtime.

    name: ClassVar[str] = "myflavour"
    extensions: ClassVar[tuple[str, ...]] = (".mf",)
    escapes: ClassVar[EscapeCodec] = MY_ESCAPES     # instance, not class
    line_comment: ClassVar[str] = "#"               # empty disables @directive parsing
    grammar: ClassVar[IrAst] = MY_GRAMMAR           # the flavour's own self-grammar
    reducer: ClassVar[Reducer] = MY_REDUCER         # the parse half

MY_FLAVOUR = _MyFlavour()
```

`MY_ACTIONS` is an `IrTypeMap` mapping each IR-AST node type (`IrLiteral`,
`IrCharClass`, `IrNot`, `IrRuleRef`, `IrGroup`, `IrQuantifier`, `IrItem`,
`IrSequence`, `IrAlternation`, `IrRule`, `IrAst`) to a callable IR body — pure
algebra (`IrConcat`, `IrJoin`, `IrField`, `IrChild`, `IrChildren`) wherever
possible, with `IrLambda(handler)` (`ir/base.py`) as the procedural escape hatch when
needed. This is the emit half (IR → text).

`MY_GRAMMAR` (an `IrAst`, authored directly — no meta-grammar string) and
`MY_REDUCER` (a `Reducer = Reducer(reductions=MY_REDUCTIONS, noise=MY_NOISE,
literal=DROP)`) are the parse half (text → IR): `parse_grammar` drives
`parse_reduced(normalize(flavour.grammar), text, flavour.reducer)` through the
same Earley engine that later parses generated instances. `MY_REDUCTIONS` is
an `IrMap[IrRuleRef, IrSelf]` from a rule's ref to a body folding its matched
children into IR; `MY_NOISE` marks which children are structural
(whitespace/delimiters/comments) and dropped before a reduction body sees
them.

## Field naming (`codegen/binding.py`)

`bind_fields(items, non_semantic)` applies the same three-tier cascade the old `ir/naming.py` + `ir/derive.py` used, now as open `IrDispatch`/`IrTypeMap` tables (`_HINT`, `_TIER2`) instead of a closed dispatch:

1. **Rule-ref:** field name = rule name (hyphens → underscores). Collisions → `ws`, `ws2`, `ws3` …
2. **Pattern library (Tier 2):** `CHARCLASS_NAMES` (8 entries, keyed by **canonical** char-class pattern post-`ir/canonical.py` — `[0-9]` → `digit`, `[a-z]` → `lower`, `[A-Za-z]` → `letter`, `[0-9A-Fa-f]` → `hex`, etc.) and `LITERAL_NAMES` (`-`/`+` → `sign`, `.` → `dot`, …). Falls back to a sanitised slug of the pattern (`_pattern_slug`), then `"cc"` (char class) / `"lit"` (literal) / `"kind"` (ref-bearing group) / `"inline"` (literal-only group).
3. **Positional (Tier 3):** first unmatched pattern field → `head`; subsequent → `part_2`, `part_3` …

Unquantified `IrLiteral` (quantifier `(1,1)`, `_is_structural_literal`) → no field, never reaches Tier 3. Quantified literals always name via Tier 2 (`_literal_token`), never Tier 3.

`_HINT` (always yields a name — used inside `_group_hint` to label literal-only group content) vs `_TIER2` (may yield `IrNone`, routing the field to Tier-3 positional names) is the same hint/field-base distinction the old `_ATOM_HINT`/`_FIELD_BASE` pair drew. Fold **mode** derivation (`mode_for`/`_MODE`, one of `BIND_MODES` — `text`/`gtext`/`model`/`models`) is a sibling `IrDispatch` table in the same module, dispatched on the atom with the owning `IrItem` riding the argument channel so ref/group bodies can read the quantifier.

## GrammarModel (`base.py`)

Every generated class carries `__grammar__: ClassVar[IrRule]` — its own rule from the codegen grammar (post group/arm-hoisting) — and every bound field an `IrBind(item, mode, semantic)` in its `Annotated` field metadata, read back via `model_fields[name].metadata` (`_bound_fields()` builds the `item slot → (field name, IrBind)` map once per call).

- `to_text()` — walks `__grammar__.body`'s single non-empty arm in item order: a bound slot emits its field's value (recursing into nested `GrammarModel`s, joining lists — `_field_text`); an unbound unquantified `IrLiteral` emits itself; anything else is structural and silent. A `value_str` class (implicit `value` field, no binds) emits `str(self.value)`; a rule whose empty alternate arm matched (all bound values `None`) emits `""`; an abstract alternation class (no fields at all) raises `NotImplementedError` — call `to_text()` on the concrete arm instance instead.
- `to_grammar(flavour="gbnf")` — `get_flavour(flavour).apply(self.__grammar__)` (no `RuleSpec`/`to_ir_rule()` conversion — `__grammar__` already is the `IrRule` the flavour renders).
- `semantic_dump()` — `model_dump()` excluding fields whose `IrBind.semantic` is `False` (structural-noise refs, e.g. whitespace).

## Directives (`compile._scan_directives`)

Scanned from source comments *before* the grammar is parsed (the self-grammars route comments to noise):

```
# @start my_rule          — override the start rule (default: first defined rule)
# @non-semantic ws sp     — mark rules as structural; their refs get min=0
```

`_scan_directives(text, line_comment)` — a **private helper in `compile.py`** (no standalone module; the leftover scanner dissolved there once the metadata moved onto `IrRule`) — returns a plain `(start, non_semantic)` tuple (`start: str | None`, `non_semantic: frozenset[str]`); the pre-lexical scan stays out of the parser so comments never become load-bearing. `canonical_grammar()` resolves precedence (explicit arg > directive > positional fallback), canonicalizes, binds the resolved `start` onto the rebuilt `IrAst`, and reconstructs each named rule with `semantic=False`; the codegen passes (`lexic.codegen.passes.relax_non_semantic`) and `base.py`'s `semantic_dump()` then read the derived `ast.non_semantic` property. A directive naming a rule the grammar never defines is silently ignored (no rule is flagged for it). A flavour's own self-grammar carries its structural rules the same way — `GBNF_GRAMMAR`/`ABNF_GRAMMAR` flag their noise rules `semantic=False` individually, and `GBNF_NOISE`/`ABNF_NOISE` are built *from `<GRAMMAR>.non_semantic`* (single source of truth feeding the reducer and the codegen passes). There is no `Directives` dataclass and no `parse_directives` symbol.

## Error vocabulary (`exceptions.py`)

No bare `raise ValueError` or `raise Exception` for library-level failures.

| Exception | Raised by |
|---|---|
| `UnsupportedConstructError` | Parsers (unknown syntax), atom dispatch tables (unknown type), the engine (no parse / ambiguous parse), `parse_grammar`/`canonical_grammar` boundary checks (missing/wrong-shaped `Reducer`, non-`IrAst` reduction, unknown start rule), codegen passes (arm-name collision), the fold (unknown kind/mode, kid-count mismatch) |
| `GrammarAuthoringError` | `@grammar_rule` decorator, ModelEmitter discriminator analysis |
| `FieldValidationError` | Pydantic constraint failures (Slice C) |

All dispatch tables must have an explicit `raise UnsupportedConstructError(...)` default — never a silent `pass` or bare `None` return.

## Key invariants

- **Grammar is canonical.** Every class has a lossless `to_grammar(flavour)` path.
- **Round-trip fidelity.** `parse(text, grammar).to_text() == text` on every valid input.
- **No regression.** Full test suite stays green after every change.
- **One way per task.** One parse function, one emit method, one round-trip method — no alternate APIs.
- **Arrows go one way.** See §Layering rules.

## Key constraints

- No `# type: ignore`, `# noqa`, or `# pylint: disable` without explicit permission. Fix the root cause.
- No `exec` or `eval` anywhere.
- No grammar-specific hardcoding in generic code.
- Generated files in `generated/` are write-once — fix template issues in `model_emitter.py`.
- The two deliberate runtime import edges (`base.py` → `lexic.grammars` for the flavour singleton; `compile.py` → `lexic.codegen` and the `lexic.parsing` engine seam) are the only ones permitted.

## Import paths

```python
from lexic.ir.nodes import IrItem, IrAst, IrQuantifier, IrLiteral, IrCharClass, IrRuleRef
from lexic.ir.operators import IrNot, IrOp
from lexic.ir.action import IrAction, IrChild, IrChildren, IrConcat, IrJoin, IrField
from lexic.ir.walk import IrDispatch, IrVisitor, IrTransformer, IrEmitter
from lexic.ir.bind import IrBind, BIND_MODES
from lexic.ir.canonical import canonicalize, fold_name
from lexic.ir.order import RuleOrder, order_by_refs
from lexic.ir.flavour import IrFlavour
from lexic.base import GrammarModel
from lexic.compile import canonical_grammar, compile_text, compile_from_path, parse_grammar
from lexic.grammars import get_flavour, flavour_for_extension, GBNF_FLAVOUR, ABNF_FLAVOUR
from lexic.parsing import recognize, parse, parse_first, parse_reduced, parse_forest, derivations, is_ambiguous
from lexic.parsing.fold import PositionalFold, RuleFold, FieldFold, lift_optional_nullables
from lexic.codegen import codegen, build_codegen_grammar, compute_binding, RuleBinding
from lexic.codegen.binding import class_name_for, classify_rule
```

Never `from src.lexic...`. `pyproject.toml` sets `pythonpath = ["src"]`.

## Test file structure

`tests/unit/lexic/` is a structural mirror of `src/lexic/`:

```
src/lexic/foo/bar.py  →  tests/unit/lexic/foo/test_bar.py
```

**When a source file is created, moved, renamed, or deleted, the test file gets the exact same treatment.** Not optional.

Naming rule for `__init__.py` modules: use `test_init_<package>.py` (not `test___init__.py`) to avoid filesystem collisions.
