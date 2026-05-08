# CLAUDE.md — Lexic

Lexic is the grammar engine layer of Vyx (an agent-to-agent protocol). It compiles grammar files (GBNF, ABNF) into Pydantic model classes; instances parse text and round-trip back to grammar. Grammar is the ground truth — classes are its Python representation, not the other way around.

## Wiki

**[.wiki/index.md](.wiki/index.md)** — persistent knowledge base (architecture, IR shapes, field naming, decisions, cutover plan, log). Read it. **Update it whenever new relevant knowledge is added**: new API surfaces, design decisions, invariants, or anything non-obvious that would otherwise need re-derivation from code. Add a log entry in `log.md` for every significant wiki change.

## Before you touch anything

Read these documents before editing code:

- **[docs/STYLE.md](docs/STYLE.md)** — coding standards (smaller methods, SOLID, avoid deep indentation, fix root causes, no muting errors). Apply to every change.
- **[prototyping/next/1_NORTH_STAR.md](prototyping/next/1_NORTH_STAR.md)** — invariants every slice must preserve.
- **[prototyping/next/2_ARCHITECTURE.md](prototyping/next/2_ARCHITECTURE.md)** — target module layout and layering rules. Consult before adding modules or splitting files.
- **[prototyping/next/3_ROADMAP.md](prototyping/next/3_ROADMAP.md)** — five slices A–E. Place all work in the right slice.
- **Active plan:** `docs/superpowers/plans/2026-05-08-parallel-track-ir-cutover.md` — parallel-track IR cutover. Tasks 1, 2, 4, 6, 7 done; Tasks 8–18 pending.

Specific instructions in this file override `docs/STYLE.md` for their domain.

## Commits

Never add `Co-Authored-By` lines. Commits belong entirely to the user.

## Commands

Always prefix with `uv run`. Never run `pytest` or `ruff` bare.

```bash
uv run pytest tests/ -q                  # full suite (743 tests + 1 xfail)
uv run pytest tests/unit/lexic/ -q       # unit only
uv run pytest tests/integration/ -q      # integration only
uv run ruff check src/ tests/            # lint
uv run pylint src/lexic/path/to/file.py  # per-file quality gate
```

**Mechanical fixes first:** run `tools/auto_fix.sh` before touching code by hand. It runs `ruff format`, `isort`, and `ruff check --fix` in sequence.

If `ruff` flags files in `generated/`, fix the template in `src/lexic/codegen/model_emitter.py`, not the generated file.

## Current state — two pipelines in parallel

The codebase is mid-transition. Two pipelines coexist and must not be mixed:

| | Old pipeline | New pipeline |
|---|---|---|
| IR shape | `Atom` dataclasses (`atoms.py`) | `IrItem`-based nodes (`nodes.py`) |
| Spec type | `RuleSpec` | `NewRuleSpec` |
| Entry | `codegen/` + `grammars/gbnf/` | `compile_grammar()` + `new_gbnf/` |
| Status | Production; all tests green | Parallel track; Tasks 8–18 pending |

Cutover (Task 18) renames `new_gbnf/` → `gbnf/`, installs `new_codegen/` → `codegen/`, and deletes `flavours.py`. Until then both live side-by-side.

## Project layout

```
src/lexic/
  __init__.py
  base.py               GrammarModel base — to_text(), to_gbnf(), semantic_dump()
  compile.py            compile_grammar() [new pipeline] | compile_text/compile_from_path [old]
  exceptions.py         LexicError hierarchy (see §Error vocabulary)
  parse.py              parse(text, grammar_path) → GrammarModel  [thin wrapper over compile]
  generate.py           random string generator from RuleSpec

  ir/
    __init__.py         re-exports old Atom types, RuleSpec, IRBuilder, all protocols
    atoms.py            seven frozen Atom dataclasses  [OLD shape — used by codegen/]
    nodes.py            IrLiteral, IrCharClass, IrRuleRef, IrGroup, IrItem,
                        IrSequence, IrAlternation, IrRule, IrAst, Quantifier  [NEW shape]
    spec.py             RuleSpec (old) + NewRuleSpec (new) — both in one file
    builder.py          IRBuilder[Node] — generic orchestrator parameterised by
                        RuleClassifier + SequenceConverter protocols
    charclass.py        parse_charclass_chars()
    classify.py         classify_rule() — sequence / alternation / value_str
    convert.py          IrItem → Atom conversion helpers
    derive.py           derive_specs(IrAst, non_semantic_rules) → list[NewRuleSpec]
    directives.py       parse_directives() — extracts @start / @non-semantic
                        from grammar source comments before the meta-grammar parser runs
    emit.py             FlavourEmitter ABC — generic emit algorithm + default atom handlers
    escapes.py          EscapeCodec ABC + CANONICAL_ESCAPES
    helpers.py          HelperRuleRegistry — per-build synthetic rule naming (dedup)
    naming.py           CHARCLASS_NAMES, _LITERAL_NAMES, assign_field_names()
    protocols.py        RuleClassifier, SequenceConverter, FlavourAdapter,
                        handler type aliases — type-only, no runtime classes
    regex_portable.py   portable Python-re construction utilities
    topo.py             topo_sort(specs, is_start_rule) — dependency ordering
    walk.py             IrVisitor, IrTransformer — recursive tree walkers

  grammars/
    __init__.py         get_adapter(), adapter_for_extension(), register_adapter()
                        bootstraps GBNF adapter on import
    flavour.py          Flavour ABC — config bundle every flavour subclasses
    flavours.py         OLD Protocol registry (FlavourAdapter/Parser/Emitter + ADAPTERS);
                        deleted at cutover (Task 18)
    gbnf/               GBNF — OLD pipeline
      adapter.py        GbnfAdapter — wires parser + IRBuilder + emitter for old pipeline
      ast.py            GBNF AST node types  [stable; do not modify]
      charclass.py      bracket-expression parser
      emitter.py        GbnfEmitter: list[RuleSpec] → GBNF text
      escapes.py        GBNF escape encode/decode
      flavour.py        GbnfFlavour(Flavour) — binds meta_grammar, escapes, emitter
      meta_grammar.py   Lark meta-grammar string for GBNF
      parser.py         GBNF text → list[Rule] (AST)  [stable; do not modify]
    new_gbnf/           GBNF — NEW pipeline (replaces gbnf/ at cutover)
      emitter.py        GbnfEmitter: list[NewRuleSpec | IrItem] → GBNF text
      escapes.py        GbnfEscapes identity codec
      flavour.py        GbnfFlavour(Flavour)
      meta_grammar.py   Lark meta-grammar string (copy)
    abnf/               ABNF flavour
      emitter.py        AbnfEmitter: list[NewRuleSpec] → ABNF text
      escapes.py        AbnfEscapes codec
      flavour.py        AbnfFlavour(Flavour)
      meta_grammar.py   ABNF Lark meta-grammar

  codegen/              OLD pipeline build-time layer  (Atom-based)
    __init__.py         build_classes_and_specs(), codegen(), codegen_from_path()
    ir_builder.py       IRBuilder: GBNF AST → list[RuleSpec]  (old; wired to GbnfAdapter)
    model_emitter.py    ModelEmitter: list[RuleSpec] → Python source
    lark_builder.py     LarkBuilder: list[RuleSpec] → Lark grammar string + transformer
    ast_utils.py        GBNF AST helpers
    classify.py         rule classification helpers
    seq_to_atoms.py     sequence node → list[Atom] conversion
    transformer/
      build_transformer.py   builds a Lark Transformer from classes + specs
      builders.py            per-atom FieldBuilder subclasses
      context.py             build context for transformer construction
      registry.py            BUILDER_BY_ATOM dispatch table

  parsing/
    meta_parser.py      MetaGrammarParser — Lark-driven IrAst builder, flavour-agnostic.
                        Knows canonical tag names (ir_rule, ir_item, ir_literal, …);
                        dispatches token values to Flavour.parse_quantifier /
                        parse_charclass. Wraps Lark errors as UnsupportedConstructError.

  utils/
    names.py            to_pascal(), to_snake(), to_lark_name()
    quantifiers.py      quantifier_to_bounds(text) → (min, max | None)

tests/
  unit/lexic/           structural mirror of src/lexic/
  integration/          test_codegen, test_compile_grammar_{gbnf,abnf},
                        test_cross_flavour, test_full_round_trip, test_parse, …
  property/             hypothesis round-trip tests
  paths.py              GROUND_TRUTH, GENERATED path constants

resources/ground_truth/ seven .gbnf test grammars (arithmetic, c, chess, japanese,
                        json_arr, json_ws, list)
generated/              auto-generated Pydantic modules — git-ignored; never edit directly
```

## Architecture

### Pipeline flow

**Old pipeline (production):**
```
GBNF text ──► gbnf/parser.py ──► GBNF AST (list[Rule])
                                        │
                                        ▼
                         codegen/ir_builder.py (IRBuilder)
                                        │
                                        ▼
                         list[RuleSpec]  (Atom-based)
                                        │
                     ┌──────────────────┼──────────────────┐
                     ▼                  ▼                   ▼
             ModelEmitter          GbnfEmitter          LarkBuilder
            generated/*.py         GBNF text       Lark grammar + transformer
```

Entry points: `compile_text()`, `compile_from_path()` in `compile.py`; `codegen()`, `codegen_from_path()` in `codegen/__init__.py`.

**New pipeline (parallel track):**
```
grammar text ──► parse_directives(text, flavour.line_comment) ──► Directives
             └──► MetaGrammarParser.for_flavour(Flavour) ──► IrAst
                                                                   │
                                                                   ▼
                               derive_specs(ast, non_semantic_rules=…)
                                                                   │
                                                                   ▼
                                              (start_name, list[NewRuleSpec])
                                                                   │
                                                       new_codegen/  ← Tasks 8–18
```

Entry point: `compile_grammar(text, flavour)` in `compile.py`. Returns `(start_name, list[NewRuleSpec])`.

### Layering rules

Arrows go one way. **Violating any of these is a review-blocking offence.**

```
lexic.ir        ← lexic.grammars       grammars read and write IR
lexic.ir        ← lexic.codegen        codegen reads and writes IR
lexic.ir        ← lexic  (runtime)     runtime reads IR
lexic.grammars  ← lexic.codegen        codegen gets adapters from grammars
lexic (runtime) ↗ lexic.codegen        runtime NEVER imports codegen — two exceptions below
```

**The two deliberate exceptions:**
1. `base.py` imports `lexic.grammars.gbnf.emitter` at module scope for `to_gbnf()`. Explicit, eager, one import.
2. `compile.py` imports `build_classes_and_specs` from `lexic.codegen` and `LarkBuilder` from `lexic.codegen.lark_builder`. Both explicit and public. This is the single runtime seam for compilation.

No `TYPE_CHECKING` dodges. No lazy intra-function imports of `lexic.codegen` from runtime modules. If a runtime module needs something that lives in codegen, move the thing.

## IR types

### Old shape (`ir/atoms.py` + `ir/spec.py`)

Seven frozen Atom dataclasses, re-exported from `lexic.ir`:

| Atom | Fields | Notes |
|---|---|---|
| `LiteralAtom` | `value` | Never a Pydantic field; emitted directly |
| `CharClassAtom` | `pattern, min, max` | Character class with quantifier bounds |
| `QuantifiedLiteralAtom` | `value, min, max` | Literal with `?`/`+`/`*`/`{m,n}` |
| `InlineRegexAtom` | `regex, gbnf, min, max` | Literal-only group → regex |
| `RuleRefAtom` | `rule_name, min, max` | Reference to another rule |
| `AlternationAtom` | `arm_rule_names` | Top-level named alternation |
| `InlineAlternationAtom` | `arm_rule_names` | Alternation nested inside a sequence |

`RuleSpec(rule_name, class_name, parent_class_name, kind, items: list[Atom], field_map)` — one rule.

### New shape (`ir/nodes.py` + `ir/spec.py`)

Quantifiers travel on `IrItem`, not on leaves.

```
IrLeaf   = IrLiteral | IrCharClass | IrRuleRef
IrAtom   = IrLeaf | IrGroup
IrNode   = IrAst | IrRule | IrAlternation | IrSequence | IrItem | IrAtom
```

`IrItem(atom: IrAtom, quantifier: Quantifier)` — the universal wrapper.

`NewRuleSpec(rule_name, class_name, parent_class_name, kind, items: list[IrItem | IrAlternation], field_map)` — one rule.

### `kind` semantics (same in both shapes)

- `"value_str"` — no `IrRuleRef` anywhere in the body; emits a single `value: str` field.
- `"alternation"` — abstract class; `items` holds the arm refs; `field_map` is empty.
- `"sequence"` — concrete class; `items` in grammar order; `field_map` populated.

Multi-arm `value_str`: `items = [IrAlternation(...)]`; emitters dispatch on `isinstance`.

## Flavour system (`grammars/flavour.py`)

Every grammar flavour subclasses `Flavour` and declares class attributes only — no imperative code:

```python
class MyFlavour(Flavour):
    name = "myflavour"
    extensions = (".mf",)
    meta_grammar = "..."          # Lark grammar with canonical ir_* tag names
    escapes = MyEscapeCodec       # EscapeCodec subclass
    emitter = MyEmitter           # FlavourEmitter subclass (class ref, not instance)
    line_comment = "#"            # empty string disables @directive parsing

    @staticmethod
    def parse_quantifier(text: str) -> Quantifier: ...

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]: ...  # (pattern, negated)

    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrGroup: ...  # optional
```

`MetaGrammarParser.for_flavour(MyFlavour)` builds the Lark parser and transformer from the meta-grammar; `parse(text)` returns `IrAst`. The flavour only controls token values; the tree-walking is generic.

## Field naming (`ir/naming.py`)

`assign_field_names(atoms)` and `_field_map(items)` apply a three-tier cascade:

1. **Rule-ref:** field name = rule name (hyphens → underscores). Collisions → `ws`, `ws2`, `ws3` …
2. **Pattern library (Tier 2):** `CHARCLASS_NAMES` (9 entries; `[0-9]` → `digit`, `[a-z]` → `lower`, `[a-zA-Z]` → `letter`, etc.) and `_LITERAL_NAMES` (`-` → `sign`, `.` → `dot`, …). Falls back to `_sanitize_pattern`.
3. **Positional (Tier 3):** first unmatched pattern field → `head`; subsequent → `part_2`, `part_3` …

Unquantified `IrLiteral` (quantifier `(1,1)`) → no field, never reaches Tier 3. Quantified literals do produce a field via Tier 2.

`_ATOM_HINT` (always returns `str`) — used inside `_group_hint` to name literal-only group content.
`_FIELD_BASE` (returns `str | None`) — used by `_field_map`; `None` means no Tier-2 match, fall through to Tier 3.

## GrammarModel (`base.py`)

Every generated class carries `__grammar__: ClassVar[RuleSpec]`.

- `to_text()` — emits `LiteralAtom.value` directly; looks up other atoms via `field_map`; recurses into nested models.
- `to_gbnf()` — delegates to `GbnfEmitter`.
- `semantic_dump()` — `model_dump()` minus `non_semantic_fields` (e.g. whitespace refs).

## Directives (`ir/directives.py`)

Scanned from source comments *before* the meta-grammar parser runs (Lark strips comments):

```
# @start my_rule          — override the start rule (default: first defined rule)
# @non-semantic ws sp     — mark rules as structural; their refs get min=0
```

`parse_directives(text, flavour.line_comment)` returns a `Directives` frozen dataclass. `compile_grammar()` applies it; priority is explicit arg > directive > positional fallback.

## Error vocabulary (`exceptions.py`)

No bare `raise ValueError` or `raise Exception` for library-level failures.

| Exception | Raised by |
|---|---|
| `UnsupportedConstructError` | Parsers (unknown syntax), atom dispatch tables (unknown type), MetaGrammarParser boundary |
| `GrammarAuthoringError` | `@grammar_rule` decorator, ModelEmitter discriminator analysis |
| `FieldValidationError` | Pydantic constraint failures (Slice C) |

All dispatch tables must have an explicit `raise UnsupportedConstructError(...)` default — never a silent `pass` or bare `None` return.

## Key invariants

From `prototyping/next/1_NORTH_STAR.md`:

- **Grammar is canonical.** Every class has a lossless `to_grammar(flavour)` path.
- **Round-trip fidelity.** `parse(text, grammar).to_text() == text` on every valid input.
- **No regression.** Full test suite stays green after every change.
- **One way per task.** One parse function, one emit method, one round-trip method — no alternate APIs.
- **Arrows go one way.** See §Layering rules.

## Key constraints

- No `# type: ignore`, `# noqa`, or `# pylint: disable` without explicit permission. Fix the root cause.
- No `exec` or `eval` anywhere.
- No grammar-specific hardcoding in generic code.
- `grammars/gbnf/ast.py` and `grammars/gbnf/parser.py` are stable; do not modify them.
- `new_gbnf/` and future `new_codegen/` use `NewRuleSpec` + `IrItem`. Never mix them with old `RuleSpec` + `Atom`.
- Generated files in `generated/` are write-once — fix template issues in `model_emitter.py`.
- The two deliberate runtime→codegen import edges are the only ones permitted.

## Import paths

```python
from lexic.ir import RuleSpec, LiteralAtom, ...          # old shape
from lexic.ir.nodes import IrItem, IrAst, Quantifier, ...  # new shape
from lexic.ir.spec import NewRuleSpec                      # new spec
from lexic.ir.derive import derive_specs
from lexic.base import GrammarModel
from lexic.compile import compile_grammar, compile_text
from lexic.grammars.flavour import Flavour
from lexic.grammars import get_adapter, adapter_for_extension
```

Never `from src.lexic...`. `pyproject.toml` sets `pythonpath = ["src"]`.

## Test file structure

`tests/unit/lexic/` is a structural mirror of `src/lexic/`:

```
src/lexic/foo/bar.py  →  tests/unit/lexic/foo/test_bar.py
```

**When a source file is created, moved, renamed, or deleted, the test file gets the exact same treatment.** Not optional.

Naming rule for `__init__.py` modules: use `test_init_<package>.py` (not `test___init__.py`) to avoid filesystem collisions.
