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
- **Cutover complete (2026-05-13).** The IrItem-based pipeline is the only pipeline. Old Atom shape, `atoms.py`, `new_gbnf/`, `flavours.py` are all gone. See `.wiki/lexic/cutover-plan.md` and `.wiki/lexic/slice-b-status.md` for what remains.

Specific instructions in this file override `docs/STYLE.md` for their domain.

## Commits

Never add `Co-Authored-By` lines. Commits belong entirely to the user.

## Commands

Always prefix with `uv run`. Never run `pytest` or `ruff` bare.

```bash
uv run pytest tests/ -q                  # full suite (474 tests)
uv run pytest tests/unit/lexic/ -q       # unit only
uv run pytest tests/integration/ -q      # integration only
uv run ruff check src/ tests/            # lint
uv run pylint src/lexic/path/to/file.py  # per-file quality gate
```

**Mechanical fixes first:** run `tools/auto_fix.sh` before touching code by hand. It runs `ruff format`, `isort`, and `ruff check --fix` in sequence.

If `ruff` flags files in `generated/`, fix the template in `src/lexic/codegen/model_emitter.py`, not the generated file.

## Current state — single IrItem pipeline

The IrItem-based cutover is complete. There is one pipeline:

- IR shape: `IrItem`-based nodes (`ir/nodes.py`) — `IrLiteral`, `IrCharClass`, `IrRuleRef`, `IrGroup`, `IrItem(atom, quantifier)`.
- Spec type: `RuleSpec` (in `ir/spec.py`).
- Entry: `compile_text` / `compile_from_path` in `compile.py` → `compile_grammar` → `codegen` → `build_lark`.
- Old `atoms.py`, `new_gbnf/`, `flavours.py`, `codegen/ir_builder.py`, `codegen/lark_builder.py`, `codegen/transformer/` are all gone.

## Project layout

```
src/lexic/
  __init__.py
  base.py               GrammarModel base — to_text(), to_grammar(), semantic_dump()
  compile.py            compile_text(), compile_from_path(), compile_grammar()
  exceptions.py         LexicError hierarchy (see §Error vocabulary)
  parse.py              parse(text, grammar_path) → GrammarModel  [thin wrapper over compile]
  generate.py           random string generator from RuleSpec

  ir/
    __init__.py         re-exports IrItem nodes, RuleSpec
    nodes.py            IrSelf mixin; IrNode[Ir_co] generic ABC; IrType/IrStr/IrTuple
                        typed bases; IrLeaf/IrStructure/IrCollection/IrComposite;
                        IrLiteral, IrCharClass, IrRuleRef, IrGroup, IrNot, IrItem,
                        IrQuantifier, IrSequence, IrAlternation, IrRule, IrAst;
                        IrNone absence sentinel
    action.py           Action-algebra nodes: IrField, IrCallable, IrChild, IrChildren,
                        IrConcat, IrJoin, IrCond, IrReturn, IrAction; default bodies
                        IrPass, IrWalk, IrRaise, IrEmit, IrRebuild
    walk.py             IrDispatch[Ir_co] — IrCollection of IrActions; presets
                        IrVisitor, IrTransformer, IrEmitter. Does NOT walk children
                        automatically — action bodies own recursion
    emit.py             render_specs() helper — list[RuleSpec] → text via a flavour
                        singleton. Currently only consumed by its own test; may be
                        wired into the broader pipeline later
    escapes.py          EscapeCodec ABC + CANONICAL_ESCAPES
    spec.py             RuleSpec(rule_name, class_name, parent_class_name, kind,
                                items: list[IrItem | IrAlternation], field_map,
                                non_semantic_fields); to_ir_rule()
    charclass.py        parse_charclass_chars()
    derive.py           derive_specs(IrAst, non_semantic_rules) → list[RuleSpec]
    directives.py       parse_directives() — extracts @start / @non-semantic
                        from grammar source comments before the meta-grammar parser runs
    naming.py           CHARCLASS_NAMES, _LITERAL_NAMES, _field_map()
    regex_portable.py   literal_to_regex_pattern(); PORTABLE_FEATURES, validate_portable
    topo.py             topo_sort(specs, is_start_rule) — dependency ordering

  grammars/
    __init__.py         get_flavour(), flavour_for_extension(), register_flavour()
                        eagerly registers GBNF_FLAVOUR and ABNF_FLAVOUR singletons
                        on import
    flavour.py          IrFlavour ABC — IrEmitter subclass + ClassVars (name,
                        extensions, meta_grammar, escapes: EscapeCodec instance,
                        line_comment) + abstract parse_quantifier / parse_charclass
    gbnf/               GBNF flavour
      flavour.py        META_GRAMMAR string; _GbnfEscapes (private) + GBNF_ESCAPES
                        singleton; GBNF_ACTIONS tuple of IrActions; _GbnfFlavour
                        (private) + GBNF_FLAVOUR singleton
    abnf/               ABNF flavour
      flavour.py        META_GRAMMAR string; _AbnfEscapes + ABNF_ESCAPES singleton;
                        ABNF_ACTIONS tuple; _AbnfFlavour + ABNF_FLAVOUR singleton

  codegen/
    __init__.py         codegen(specs, stem) → dict[str, type]
                        writes generated/<stem>.py (ruff-formatted), loads and returns classes
    aliases.py          PatternAlias, collect_aliases() — module-level type alias hoisting
    model_emitter.py    emit_module_source(specs, stem) → str
                        IrItem-shape RuleSpec list → Python source string

  parsing/
    meta_parser.py      MetaGrammarParser — Lark-driven IrAst builder, flavour-agnostic.
                        Knows canonical tag names (ir_rule, ir_item, ir_literal, …);
                        dispatches token values to Flavour.parse_quantifier /
                        parse_charclass. Wraps Lark errors as UnsupportedConstructError.
    lark_builder.py     LarkBuilder: list[RuleSpec] → Lark grammar string;
                        build_lark(specs, classes, start_rule) → (grammar_str, parser, transformer)
    transformer/
      build_transformer.py   build_transformer(specs, classes) → lark.Transformer

  utils/
    names.py            to_pascal(), to_snake(), to_lark_name()
    quantifiers.py      bounds_to_quantifier() — consumed by parsing/lark_builder.py
                        and codegen/aliases.py; flavours no longer use it.
                        Scheduled for later cleanup.

tests/
  unit/lexic/           structural mirror of src/lexic/
  integration/          test_compile_grammar_{gbnf,abnf}, test_cross_flavour,
                        test_full_round_trip, test_layering_invariants, test_parse, …
  property/             hypothesis round-trip tests
  paths.py              GROUND_TRUTH, GENERATED path constants

resources/ground_truth/ seven .gbnf test grammars (arithmetic, c, chess, japanese,
                        json_arr, json_ws, list)
generated/              auto-generated Pydantic modules — git-ignored; never edit directly.
                        compile_from_path writes <grammar-stem>.py (e.g. arithmetic.py);
                        compile_text writes anon_<sha1>.py. Files are ruff-formatted.
```

## Architecture

### Pipeline flow

```
grammar text ──► parse_directives(text, flavour.line_comment) ──► Directives
             └──► MetaGrammarParser.for_flavour(IrFlavour) ──► IrAst
                                                                   │
                                                                   ▼
                               derive_specs(ast, non_semantic_rules=…)
                                                                   │
                                                                   ▼
                                              (start_name, list[RuleSpec])
                                                                   │
                         ┌─────────────────────────────────────────┤
                         ▼                                         ▼
                  codegen(specs, stem)                  GBNF_FLAVOUR / ABNF_FLAVOUR
              writes generated/<stem>.py              flavour_singleton.apply(node)
              returns dict[str, type]                  (IrEmitter on IR-AST tree)
                         │
                         ▼
                   build_lark(specs, classes, start_rule)
                   → (grammar_str, lark.Lark, lark.Transformer)
```

Entry points: `compile_text(text, flavour)` and `compile_from_path(path)` in `compile.py`. Both call `compile_grammar` then `codegen` then `build_lark` and return a `CompiledGrammar`.

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
1. `base.py` imports `get_flavour` from `lexic.grammars` to drive `to_grammar()` (which calls `flavour_singleton.apply(self.__grammar__.to_ir_rule())`). The GBNF singleton is `lexic.grammars.gbnf.flavour.GBNF_FLAVOUR`. Explicit, eager.
2. `compile.py` imports `codegen` from `lexic.codegen` and `build_lark` from `lexic.parsing.lark_builder`. Both explicit and public. This is the single runtime seam for compilation.

No `TYPE_CHECKING` dodges. No lazy intra-function imports of `lexic.codegen` from runtime modules. If a runtime module needs something that lives in codegen, move the thing.

## IR types (`ir/nodes.py` + `ir/action.py` + `ir/spec.py`)

Every IR node is callable: `node.__call__(d, n, nc) -> Ir_co` where `Ir_co` defaults to `IrSelf` (identity). The `IrSelf` mixin supplies the default identity `__call__` and the action-protocol `eval(d, n, nc) -> Ir_co`. Value-producing nodes override `eval`. `IrNode[Ir_co]` is a generic dataclass ABC that extends `IrSelf[Ir_co]`.

**Typed bases:** `IrType` is the base for `IrSelf`-shaped nodes that are also Python natives. `IrStr` is `IrType + str`; `IrTuple[T]` is `IrType + tuple` whose `eval` dispatches each element via `d` and rebuilds the tuple.

**Grammar AST nodes:**

```
IrLeaf       = IrLiteral | IrCharClass | IrRuleRef        (+ IrQuantifier)
IrAtom       = IrLeaf | IrGroup | IrNot                   (role marker)
IrStructure  = IrCollection | IrComposite                  (branch nodes)
IrCollection: IrSequence, IrAlternation, IrAst             (homogeneous items)
IrComposite:  IrGroup, IrNot, IrItem, IrRule               (named children)
```

`IrItem(atom: IrAtom, quantifier: IrQuantifier)` — the universal wrapper. `IrQuantifier(min, max | None)` carries repetition bounds. The pair `(_child_attrs, _items_attr)` declares which dataclass fields are dispatched children.

`IrLiteral` carries a **dual role**: as a grammar AST leaf (the literal string in a rule body) and as an action-language constant (a baked-in string an action body returns). The two are distinguished at eval time by the `nc` (node-children) parameter — see [[ir-shapes]].

**Action-algebra nodes** (`ir/action.py`) extend the IR with operations beyond identity: `IrField` reads a typed attribute from the dispatched node; `IrCallable` is the procedural escape hatch; `IrChild` / `IrChildren` resolve sibling children by name (hybrid: pre-walked from `nc` when populated, otherwise dispatched lazily via `d.eval`); `IrConcat` and `IrJoin` build strings; `IrCond` branches on a truthy field; `IrReturn` short-circuits via a `_Return` BaseException; `IrAction(target_type, body)` binds a target IR-node type to a callable IR body. Default bodies: `IrPass`, `IrWalk`, `IrRaise`, `IrEmit`, `IrRebuild`.

**Dispatch** (`ir/walk.py`): `IrDispatch[Ir_co]` is an `IrCollection[Ir_co]` whose items are the action table. It does **not** walk children automatically — action bodies do their own recursion. Resolution is concrete-first MRO walk, memoised. Entry seams are `eval(d, n, nc)` (protocol shape) and `apply(root)` (friendly façade). Presets: `IrVisitor` (side-effect walker; default `IrWalk`), `IrTransformer[IrNode]` (tree rewrites; default `IrRebuild`), `IrEmitter[IrLiteral]` (string emission; default `IrEmit`).

`RuleSpec(rule_name, class_name, parent_class_name, kind, items: list[IrItem | IrAlternation], field_map, non_semantic_fields)` — one rule. Carries `to_ir_rule()` for emission via a flavour.

### `kind` semantics

- `"value_str"` — no `IrRuleRef` anywhere in the body; emits a single `value: str` field.
- `"alternation"` — abstract class; `items` holds the arm refs; `field_map` is empty.
- `"sequence"` — concrete class; `items` in grammar order; `field_map` populated.

Multi-arm `value_str`: `items = [IrAlternation(...)]`; emitters dispatch on `isinstance`.

## Flavour system (`grammars/flavour.py`)

An `IrFlavour` IS-AN `IrEmitter` — its `actions` tuple holds the per-IR-type rendering rules, and `apply(root)` walks an IR tree to a string. Each flavour module exposes the class as **private** (`_GbnfFlavour`) and the constructed singleton as **public** (`GBNF_FLAVOUR`).

```python
@dataclass(frozen=True, slots=True, init=False, repr=False)
class _MyFlavour(IrFlavour):
    actions: tuple[IrAction, ...] = MY_ACTIONS   # class-level default

    name: ClassVar[str] = "myflavour"
    extensions: ClassVar[tuple[str, ...]] = (".mf",)
    meta_grammar: ClassVar[str] = META_GRAMMAR
    escapes: ClassVar[EscapeCodec] = MY_ESCAPES   # instance, not class
    line_comment: ClassVar[str] = "#"             # empty disables @directive parsing

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier: ...
    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]: ...   # (pattern, negated)
    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrGroup: ...  # optional

MY_FLAVOUR = _MyFlavour()
```

`MY_ACTIONS` is a `tuple[IrAction, ...]` mapping each IR-AST node type (`IrLiteral`, `IrCharClass`, `IrNot`, `IrRuleRef`, `IrGroup`, `IrQuantifier`, `IrItem`, `IrSequence`, `IrAlternation`, `IrRule`, `IrAst`) to a callable IR body — pure algebra (`IrConcat`, `IrJoin`, `IrField`, `IrChild`, `IrChildren`) wherever possible, with `IrCallable(handler)` as the procedural escape hatch when needed.

`MetaGrammarParser.for_flavour(flavour)` builds the Lark parser and transformer from the meta-grammar; `parse(text)` returns `IrAst`. The flavour only controls token values; tree-walking is generic.

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

- `to_text()` — emits unquantified `IrLiteral` values directly; looks up other fields via `field_map`; recurses into nested models.
- `to_grammar(flavour="gbnf")` — looks up the flavour singleton and calls `flavour.apply(self.__grammar__.to_ir_rule())`.
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
- Generated files in `generated/` are write-once — fix template issues in `model_emitter.py`.
- The two deliberate runtime→codegen import edges (`base.py` → `lexic.grammars` for the flavour singleton; `compile.py` → `lexic.codegen` and `lexic.parsing.lark_builder`) are the only ones permitted.

## Import paths

```python
from lexic.ir.nodes import IrItem, IrAst, IrQuantifier, IrLiteral, IrCharClass, IrRuleRef, IrGroup
from lexic.ir.action import IrAction, IrCallable, IrChild, IrChildren, IrConcat, IrJoin, IrField
from lexic.ir.walk import IrDispatch, IrVisitor, IrTransformer, IrEmitter
from lexic.ir.spec import RuleSpec
from lexic.ir.derive import derive_specs
from lexic.base import GrammarModel
from lexic.compile import compile_grammar, compile_text, compile_from_path
from lexic.grammars.flavour import IrFlavour
from lexic.grammars import get_flavour, flavour_for_extension, GBNF_FLAVOUR, ABNF_FLAVOUR
```

Never `from src.lexic...`. `pyproject.toml` sets `pythonpath = ["src"]`.

## Test file structure

`tests/unit/lexic/` is a structural mirror of `src/lexic/`:

```
src/lexic/foo/bar.py  →  tests/unit/lexic/foo/test_bar.py
```

**When a source file is created, moved, renamed, or deleted, the test file gets the exact same treatment.** Not optional.

Naming rule for `__init__.py` modules: use `test_init_<package>.py` (not `test___init__.py`) to avoid filesystem collisions.
