# Lexic Wiki — Index

**Context:** CLAUDE.md is always loaded. This wiki extends it with detail too dense for CLAUDE.md and dynamic state (task progress, decisions). Load pages only when you need what they contain — the descriptions below tell you exactly what's on each page.

---

## Quick lookup

| Question | Page |
|---|---|
| Which exception class for unknown syntax / unknown atom type? | [[lexic/error-vocabulary]] |
| How is a Pydantic field name decided for a given atom? | [[lexic/field-naming]] |
| Is this import legal? Which packages can depend on which? | [[lexic/architecture]] |
| What tasks are done vs pending? | [[lexic/cutover-plan]] |
| Old `Atom` shape vs new `IrItem` shape — fields, type aliases? | [[lexic/ir-shapes]] |
| How do I add a new grammar flavour? | [[lexic/flavour-system]] |
| Which compile function should I call? What does CompiledGrammar contain? | [[lexic/public-api]] |
| Why was design choice X made? | [[lexic/decisions]] |
| What test file do I create for src/lexic/foo/bar.py? | [[lexic/testing]] |
| What changed most recently? | [[log]] |
| What is GBNF / ABNF / EBNF syntax? | [[theory/grammar-formats]] |
| CFGs, PEGs, ASTs, parsing algorithms, toolchains? | [[theory/parsing-theory]] |

---

## Task routing

| Task | Pages to load |
|---|---|
| Slice B token reservation (Tasks 33–34) | [[lexic/slice-b-status]], [[lexic/error-vocabulary]] |
| Adding a new grammar flavour | [[lexic/flavour-system]], [[lexic/ir-shapes]] |
| Debugging field name collision | [[lexic/field-naming]], [[lexic/decisions]] |
| Adding a new IR node type | [[lexic/ir-shapes]], [[lexic/invariants]], [[lexic/error-vocabulary]] |
| Writing a parser or emitter | [[lexic/flavour-system]], [[lexic/error-vocabulary]] |
| Writing/debugging a grammar flavour emitter | [[theory/grammar-formats]], [[lexic/flavour-system]] |

---

## Reference pages

| Page | Contains |
|---|---|
| [[lexic/public-api]] | `parse`, `compile_text`, `compile_from_path`, `compile_grammar` signatures; `CompiledGrammar` fields; `GrammarModel` methods; which entry point to use; directive precedence |
| [[lexic/architecture]] | Four-layer diagram; the two deliberate runtime→codegen import exceptions (`base.py`, `compile.py`); module ownership table; both pipeline flows |
| [[lexic/ir-shapes]] | All `IrItem`/`IrLeaf`/`IrAtom` type aliases; `Quantifier` fields; `NewRuleSpec` vs `RuleSpec` field comparison; `kind` semantics table; hoisting (`hoist_helpers`); non-semantic relaxation |
| [[lexic/flavour-system]] | `Flavour` ABC full attribute list; canonical `ir_*` tag names for meta-grammars; `FlavourEmitter` syntax constants; old vs new flavour wiring comparison; step-by-step: adding a new flavour |
| [[lexic/field-naming]] | `CHARCLASS_NAMES` (9 entries, ground truth); `_LITERAL_NAMES` table; skip conditions (unquantified `IrLiteral`, `AlternationAtom`); `_ATOM_HINT` vs `_FIELD_BASE` contract distinction; collision counter mechanics |
| [[lexic/error-vocabulary]] | Exception class → raised-by mapping; dispatch table code pattern with `raise UnsupportedConstructError`; the engine/reducer/`compile_grammar` error boundary; which stubs are wired in which slice |
| [[lexic/invariants]] | Round-trip fidelity invariant; closed atom union rule; seven ground-truth grammars; what each invariant means for dispatch tables, `to_text()`, and import edges |
| [[lexic/testing]] | Test file mirror rule (`src/lexic/foo/bar.py` → `tests/unit/lexic/foo/test_bar.py`); `test_init_<pkg>.py` naming for `__init__.py` modules; test commands |
| [[lexic/new-codegen]] | What `new_codegen/` builds (Tasks 8–14); `PatternAlias` dataclass; `collect_aliases` contract; what Tasks 9–14 will add |
| [[theory/grammar-formats]] | GBNF, ABNF, EBNF syntax reference; operator precedence tables; escape notations; Lexic coverage gaps per format; GBNF vs ABNF vs EBNF comparison table |
| [[theory/parsing-theory]] | CFGs, PEGs, LL/LR/Earley algorithms; AST vs CST; Visitor vs Transformer patterns; grammar toolchains (Lexic's own native Earley engine, plus Lark/ANTLR4/tree-sitter as external reference points); IR design rationale |

---

## Active work

| Page | Contains |
|---|---|
| [[lexic/cutover-plan]] | Cutover complete (2026-05-13); what replaced what; Slice B remaining work pointer |
| [[lexic/slice-b-status]] | Slice B audit post-cutover: Phase 1 done/obsolete breakdown; Phase 2 entirely obsolete; Phase 3 (token reservation) still required |
| [[lexic/decisions]] | Dated design decisions with reasoning: grammar-is-canonical, parallel-track strategy, `_FIELD_BASE` dispatch table, `CHARCLASS_NAMES` ground truth, `IrItem` quantifier placement, `Flavour` ABC class-attributes-only |

---

## Operations

| Page | Contains |
|---|---|
| [[log]] | Append-only chronological record of significant changes; read to orient on what happened recently |
