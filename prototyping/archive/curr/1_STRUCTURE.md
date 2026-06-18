# Lexic — proposed file & class structure

Companion to `OPUS_REVIEW_V3.md`. The review identifies three systemic risks:
(1) `_build_instance` in `transformer.py` as an untyped imperative bridge,
(2) semantic field naming that is identifier-safe but not semantic, and
(3) `parse()` that regenerates the module on every call. This document proposes a
concrete directory + class layout that addresses those risks and gives R005 /
R006 a place to land without growing existing modules further.

Nothing here is speculative *scope* — every module below corresponds to
functionality the codebase either already has (in a suboptimal location) or
needs for a live requirement (R005 / R006). Not to be implemented speculatively.

## Target layout

```
src/lexic/
  __init__.py
  base.py                       GrammarModel (runtime-only, no codegen imports)
  parse.py                      parse(text, grammar)        ← thin entry
  compile.py                    compile(grammar) → CompiledGrammar
  generate.py                   generate(rule, specs, rng)  ← random generator
  translate.py                  translate(instance, target) ← R006
  grammar_state.py              GrammarState for R005 constrained decoding

  ir/
    __init__.py                 re-exports Atom, RuleSpec, atom types
    atoms.py                    dataclasses only — no behaviour
    spec.py                     RuleSpec dataclass
    annotations.py              FieldAnnotation + parser for `# @field=...`

  codegen/                      build-time tools; runtime may not depend on this
    __init__.py                 codegen(grammar_path)
    ast.py                      [unchanged]
    parser.py                   [unchanged]
    ir_builder.py               IRBuilder — orchestrator only, <200 lines
    classify.py                 Classifier — extracted from ir_builder
    naming.py                   FieldNamer — extracted from ir_builder
    helpers.py                  HelperRuleRegistry — cross-rule dedup
    model_emitter.py            ModelEmitter
    gbnf_emitter.py             GBNFEmitter
    lark_builder.py             LarkBuilder (grammar text only)
    transformer/
      __init__.py               build_transformer(specs, classes)
      registry.py               BUILDER_BY_ATOM dispatch table
      builders.py               FieldBuilder implementations
      value_str.py              value_str reconstruction policy

  utils/
    __init__.py
    escapes.py                  decode_gbnf_escapes
    charclass.py                bracket-expression parsing (new)
    names.py                    to_lark_name, to_pascal (new, shared)
    quantifiers.py              bounds_to_quantifier
```

Three packages, one ownership each:

- **`lexic.ir`** — the contract everything else depends on. Pure data.
- **`lexic.codegen`** — build-time: parse GBNF, produce IR, render artifacts.
  Runtime code never imports this.
- **`lexic` (root)** — runtime: `parse`, `compile`, `generate`, `translate`,
  `grammar_state`. Depends on `lexic.ir` only.

This layering discharges V3 §9 (runtime → codegen back-edge) and §8 (parse
regenerates on every call).

## Key modules

### `lexic.compile` (new)

Splits the current `parse()` into compile-once / parse-many:

```python
@dataclass(frozen=True)
class CompiledGrammar:
    classes: dict[str, type[GrammarModel]]
    specs: dict[str, RuleSpec]          # by rule_name
    parser: lark.Lark
    transformer: Transformer

def compile(grammar_path: str | Path) -> CompiledGrammar: ...
```

- Memoised by `(path, mtime)` so repeated calls return the same object.
- `parse()` becomes a one-liner: `compile(grammar).parse(text)`.
- R005 and the property-test loop stop paying ~20ms per call.

### `lexic.codegen.transformer` (package, replacing the file)

Replaces the 267-line `transformer.py` with a dispatch table + per-atom
builders.

```python
# registry.py
BUILDER_BY_ATOM: dict[type[Atom], FieldBuilder] = {
    LiteralAtom:            LiteralSkipBuilder(),     # never a field
    CharClassAtom:          CharClassFieldBuilder(),
    QuantifiedLiteralAtom:  QuantifiedLiteralBuilder(),
    InlineRegexAtom:        InlineRegexBuilder(),
    RuleRefAtom:            RuleRefBuilder(),
    InlineAlternationAtom:  InlineAlternationBuilder(),
    AlternationAtom:        AbstractAlternationBuilder(),
}

# builders.py
class FieldBuilder(Protocol):
    def build(self, ctx: BuildContext) -> FieldResult: ...
```

Each builder is tested in isolation. `Optional[X]` and `List[X]` are handled by
*wrapping* builders (`OptionalFieldBuilder(inner)`, `ListFieldBuilder(inner)`),
not by conditional branches in the core loop.

This is the single change most likely to keep the pipeline correct as grammar
shapes grow. Addresses V3 §1.

### `lexic.codegen.classify` + `lexic.codegen.naming` + `lexic.codegen.helpers`

Extract three orthogonal concerns currently wound together in `ir_builder.py`
(670 lines):

- **`classify.py`** — `Classifier.classify(rule) -> Classification` where
  `Classification` is a data object (`kind`, `arms`, `needs_helpers`) rather
  than a string tag. Predicates live as methods on a `GbnfRuleTree` wrapper;
  each is unit-testable against hand-written AST fixtures. Addresses V3 §2.
- **`naming.py`** — `FieldNamer.name_for(atom, context)`. Owns
  `_CHARCLASS_NAMES`, `_LITERAL_NAMES`, `_sanitize_pattern`,
  `_inline_regex_field_name`, and the `_unique` collision counter.
  Consumes `FieldAnnotation` from `lexic.ir.annotations` for author overrides.
  Addresses V3 §3.
- **`helpers.py`** — `HelperRuleRegistry` passed into `_seq_to_atoms` once per
  `IRBuilder.build()`, so helper-rule name dedup is global rather than
  per-call. Addresses V3 §10.

`ir_builder.py` becomes an orchestrator (<200 lines) that wires these
together.

### `lexic.ir.annotations` (new)

GBNF comment annotations for author-controlled semantic names:

```python
# source.gbnf
pawn ::= ([a-h] "x")?    # @field=captureFile
         [a-h]            # @field=destFile
         [1-8]            # @field=destRank
         ("=" [NBKQR])?   # @field=promotion
```

```python
@dataclass(frozen=True)
class FieldAnnotation:
    field_name: str | None
    # Room to grow: type_hint, description, etc. — do not add speculatively.

def parse_annotations(gbnf_text: str) -> dict[AtomId, FieldAnnotation]: ...
```

`codegen.parser` (unchanged) parses the GBNF; an annotation pass runs
separately and attaches annotations by source position. `FieldNamer` prefers
`FieldAnnotation.field_name` when present, falls back to the current
pattern-derived naming. Discharges the R006 blocker identified in V3 §3.

### `lexic.translate` (new, for R006)

```python
def translate(
    instance: GrammarModel,
    target_cls: type[GrammarModel],
) -> GrammarModel: ...
```

Two-phase design:

1. **Extraction** — `instance.semantic_dump()` → a `SemanticValue` tree. Not a
   flat dict: preserves structural position so the target can match by
   shape when names don't align.
2. **Construction** — walk `target_cls.__grammar__.items`, map each field to a
   `SemanticValue`, construct the target instance.

Keeps the name-matching and shape-matching concerns separate. Annotations
land as a third resolution path (explicit mapping override).

### `lexic.grammar_state` (new, for R005)

The contract R005 constrained decoding actually needs, independent of any LLM
runtime:

```python
class GrammarState:
    def __init__(self, specs: dict[str, RuleSpec], root: str): ...
    def feed(self, char: str) -> "GrammarState": ...
    def allowed_next_chars(self) -> set[str]: ...
    def is_accepting(self) -> bool: ...
```

R005 then becomes a token-to-char bridge that uses this — llama.cpp-specific
code lives outside `lexic`. Building `GrammarState` from the existing
RuleSpec IR avoids introducing a second grammar representation. Discharges
V3 §7.

### `lexic.utils.charclass` (new)

Move `_parse_escape` and `_parse_charclass_chars` out of `generate.py` into a
shared module. The "which escapes does GBNF support" knowledge then lives in
exactly one place alongside `escapes.py`. Addresses V3 §B.

### `lexic.utils.names` (new)

Home for `to_lark_name`, `to_pascal`, and any other rule-name mangling. Breaks
the cosmetic cycle between `lark_builder.py` and `transformer/` (V3 §C).

### `lexic.gbnf_emitter` (proposed move)

Because `GrammarModel.to_gbnf()` is the last runtime → codegen back-edge
(V3 §9), move `gbnf_emitter.py` out of `codegen/` — e.g. to the root alongside
`base.py`, or under a new `lexic.emit/` if other emitters move too. `base.py`
can then import eagerly, and a runtime-only deployment can drop `codegen/`
entirely.

Optional; do only if you actually need a runtime-without-codegen path.

## Class responsibilities at a glance

| Module | Class / fn | Owns |
|---|---|---|
| `ir.atoms` | `LiteralAtom`, `CharClassAtom`, … | Pure data shape of an atom |
| `ir.spec` | `RuleSpec` | Pure data shape of a rule |
| `ir.annotations` | `FieldAnnotation`, `parse_annotations` | Author overrides parsed from GBNF comments |
| `codegen.classify` | `Classifier` | "What kind of rule is this?" (pure functions on AST) |
| `codegen.naming` | `FieldNamer` | "What do we call this field?" — one policy, one place |
| `codegen.helpers` | `HelperRuleRegistry` | Global dedup of synthetic helper rules |
| `codegen.ir_builder` | `IRBuilder` | Orchestration only — wires classifier/namer/helpers |
| `codegen.model_emitter` | `ModelEmitter` | `RuleSpec → Python source` |
| `codegen.gbnf_emitter` | `GBNFEmitter` | `RuleSpec → GBNF text` |
| `codegen.lark_builder` | `LarkBuilder` | `RuleSpec → Lark grammar string` |
| `codegen.transformer.registry` | `BUILDER_BY_ATOM` | Dispatch table atom → builder |
| `codegen.transformer.builders` | `FieldBuilder` subclasses | One policy per atom-kind × field-shape cell |
| `codegen.transformer.value_str` | `ValueStrReconstructor` | The reconstruction rule extracted from `make_value` |
| `compile` | `CompiledGrammar`, `compile()` | Memoised "compile once" surface |
| `parse` | `parse()` | One-liner: `compile(grammar).parse(text)` |
| `generate` | `generate()` | Random string from IR, used by property tests |
| `grammar_state` | `GrammarState` | Char-level constraint oracle for R005 |
| `translate` | `translate()` | Cross-grammar translation (R006) |

## Migration order (suggested)

These are independent enough to land incrementally:

1. **`lexic.utils.names` + `lexic.utils.charclass`** — lowest risk, unblocks
   cycles and deduplicates parsing.
2. **`lexic.codegen.transformer` package split** — biggest maintainability win,
   doesn't change any external behaviour.
3. **`lexic.ir.annotations` + `FieldNamer` extraction** — unblocks R006.
4. **`lexic.compile` / `CompiledGrammar`** — unblocks R005 performance, tiny
   change to `parse.py`.
5. **`lexic.codegen.classify` extraction** — depends on nothing; do when
   `_classify` next needs changing.
6. **`lexic.grammar_state`** — R005 groundwork.
7. **`lexic.translate`** — R006.

Steps 1-4 should land before S04. Steps 5-7 sit behind explicit requirements
and should not be pre-built.

## Non-goals

- **Do not** migrate atoms to polymorphic `to_gbnf()` / `to_lark()` methods
  yet. V3 §5 flags this as a real option but also notes the coupling cost.
  Keep atoms data-only until the `isinstance` cascades actually start costing
  correctness — dispatch tables (as in the transformer package) are the
  cheaper first step.
- **Do not** replace Pydantic with hand-rolled validation. The Union-arm
  discrimination concern in V3 §6 is addressed with a
  `model_validator(mode='before')` on the affected generated classes, not
  with a parallel validation stack.
- **Do not** introduce a second IR. `RuleSpec` + the seven atom types are
  enough; `GrammarState` and `translate` should be views over this IR, not
  rewrites of it.
