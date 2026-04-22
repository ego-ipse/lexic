# Lexic — Architecture

This document describes the *target* shape of the repository and the IR
after all five slices in `3_ROADMAP.md` have landed. Individual slices
do not need to reach this shape in one step; they each move one part of
the tree closer to it.

## Target module layout

```
src/lexic/
  __init__.py
  base.py                       GrammarModel (runtime-only)
  parse.py                      parse(text, grammar) — thin; calls compile()
  compile.py                    compile(text) + compile_from_path(path) → CompiledGrammar (memoised)
  generate.py                   generate(rule, specs, rng) — random generator
  grammar_rule.py               @grammar_rule decorator (lands in Slice D)
  exceptions.py                 Error classes (see §Error vocabulary)

  ir/
    __init__.py                 re-exports Atom, RuleSpec, atom types
    atoms.py                    five frozen dataclasses; no behaviour
    spec.py                     RuleSpec dataclass

  codegen/                      build-time; runtime imports only the two
                                deliberate seams (§Layering rules)
    __init__.py                 build_classes_and_specs(text, *, stem)
                                  + codegen(text, *, stem)
                                  + codegen_from_path(path)
    ast_utils.py                shared GBNF-AST helpers (strip_ws, etc.)
    classify.py                 Classifier + Classification union
    naming.py                   assign_field_names (module-level; not a class)
    helpers.py                  HelperRuleRegistry (global dedup)
    seq_to_atoms.py             seq_to_atoms + Group→pattern converters
    ir_builder.py               IRBuilder orchestrator (<200 LoC target)
    model_emitter.py            ModelEmitter
    lark_builder.py             LarkBuilder (grammar text only)
    transformer/
      __init__.py               build_transformer(specs, classes)
      registry.py               BUILDER_BY_ATOM dispatch table
      builders.py               FieldBuilder subclasses + wrapping builders
    gbnf/
      __init__.py               GbnfAdapter bundling parser + ir_builder + emitter
      ast.py                    (unchanged — moved)
      parser.py                 (moved from codegen/parser.py)
      emitter.py                (moved from codegen/gbnf_emitter.py)

  utils/
    __init__.py
    escapes.py                  decode_gbnf_escapes
    charclass.py                bracket-expression parsing (extracted from generate.py)
    names.py                    to_lark_name, to_pascal, to_snake
    quantifiers.py              bounds_to_quantifier
```

Three packages, one ownership each:

- **`lexic.ir`** — the contract. Pure data. Imports nothing from the rest
  of `lexic`.
- **`lexic.codegen`** — build-time. Produces and consumes IR; emits
  Python modules and grammar text. Has no runtime consumers except via
  the two deliberate edges below (`GrammarModel.to_grammar` and
  `compile()`).
- **`lexic` (root)** — runtime. Depends on `lexic.ir`; bridges into
  `lexic.codegen` at exactly two points: `base.py::to_grammar` and
  `compile.py::compile`.

## Layering rules

Imports flow one way. Violating any arrow is a review-blocking offence.

```
lexic.ir        ←  lexic.codegen        (codegen reads/writes IR)
lexic.ir        ←  lexic (runtime)      (runtime reads IR)
lexic (runtime) ←/  lexic.codegen       (runtime NEVER imports codegen
                                         except the two edges below)
```

**The two deliberate exceptions.**

1. `GrammarModel.to_grammar(flavour)` in `base.py` imports
   `lexic.codegen.gbnf.emitter` at module scope and calls it. This edge
   is explicit, eager (not a lazy intra-function import), and exists
   because round-trip to grammar text is part of the runtime contract.
   It closes V3 §9.
2. `compile()` and its thin wrapper `compile_from_path()` in
   `compile.py` import two public symbols from `lexic.codegen` at
   module scope:
   - `build_classes_and_specs(text, *, stem) -> (classes, specs)` from
     `lexic.codegen`, which runs the full parse + IR-build + emit + load
     pipeline once and returns both classes and specs. `compile.py`
     needs both; calling `codegen()` for classes and then re-running
     `parse_gbnf` + `IRBuilder` for specs would double the work and
     widen this seam to four imports — `build_classes_and_specs`
     exists precisely to keep the seam narrow.
   - `LarkBuilder` from `lexic.codegen.lark_builder`, which builds the
     lark grammar string and transformer factory.

   Both imports are explicit, eager, and public (no underscore
   symbols). The edge exists because the runtime contract of
   `compile(text) -> CompiledGrammar` is exactly "text → classes +
   specs + parser + transformer", which fundamentally requires codegen
   at call time. `compile.py` is the single runtime seam for this;
   every other runtime module that needs compiled classes goes through
   it (notably `parse.py`). The path-taking helpers (`compile_from_path`,
   `codegen_from_path`) are read-file wrappers that delegate to the
   string-primary functions — following the convention that the
   canonical operation takes the string and IO sits at the edges.

Every other runtime-touches-codegen path is forbidden. No lazy
intra-function imports of `lexic.codegen` from runtime modules. No
`TYPE_CHECKING` dodges. If a runtime module needs something that
currently lives in codegen, move the thing — don't open a back-edge.

## IR shape (post-Slice B)

Five atom types, all frozen dataclasses in `lexic/ir/atoms.py`:

```python
@dataclass(frozen=True)
class LiteralAtom:
    value: str                    # never becomes a Pydantic field

@dataclass(frozen=True)
class PatternAtom:
    regex: str                    # canonical Python `re` dialect, portable subset
    source_forms: dict[str, str]  # flavour-shadow map; "gbnf" populated today
    min: int
    max: int | None               # None = unbounded

@dataclass(frozen=True)
class RuleRefAtom:
    rule_name: str
    min: int
    max: int | None

@dataclass(frozen=True)
class AlternationAtom:
    arm_rule_names: list[str]     # top-level alternation; spec.kind = "alternation"

@dataclass(frozen=True)
class InlineAlternationAtom:
    arms: list[list[Atom]]        # alternation nested inside a sequence rule
```

### Closed-but-versioned

The atom union is **closed**: no code in the library constructs an atom
whose type is not in the list above. It is **versioned**: adding a sixth
type (for example `TokenAtom` if GBNF tokens are ever implemented) is a
minor version bump. Every dispatch table has the following shape:

```python
BUILDER_BY_ATOM: dict[type[Atom], FieldBuilder] = { ... }

def build(atom: Atom, ctx: BuildContext) -> FieldResult:
    builder = BUILDER_BY_ATOM.get(type(atom))
    if builder is None:
        raise UnsupportedConstructError(
            f"No builder registered for atom type {type(atom).__name__}"
        )
    return builder.build(atom, ctx)
```

An explicit `default` raise is **prescribed**, not optional. Ad-hoc
`isinstance` cascades are not acceptable after Slice A.

### `source_forms` semantics

`PatternAtom.source_forms` is a flavour-shadow map. Each entry is what
the atom looked like in its source flavour:

- `source_forms["gbnf"] = "[a-h]"` — the bracket expression as it
  appeared in the `.gbnf` file.
- Future: `source_forms["abnf"] = "0*15DIGIT"` — the ABNF equivalent.

The canonical, dialect-neutral representation is `regex` (Python `re`
dialect, portable subset — see `3_ROADMAP.md` Slice B for exact bounds).
Emitters prefer the matching source-form entry if present and fall back
to reconstructing from `regex`. Today only `"gbnf"` is populated, but
the shape is the shape.

## Extensibility protocols

### Flavour adapter contract (scaffold; only `GbnfAdapter` exists)

```python
class FlavourAdapter(Protocol):
    name: str                                    # e.g. "gbnf"
    extensions: tuple[str, ...]                  # e.g. (".gbnf",)

    def parse(self, text: str) -> list[RuleSpec]: ...
    def emit(self, specs: list[RuleSpec]) -> str: ...
```

`codegen/gbnf/__init__.py` exports the one implementation. Adding ABNF
(outside this arc's scope) means a new sibling subpackage
`codegen/abnf/`; no changes to the core are needed.

### Token reservation

The GBNF parser (in `codegen/gbnf/parser.py`) detects `<...>` syntax
before any atom construction code runs. On any match it raises, with
one of two error classes:

- `UnsupportedConstructError` — for any grammar containing a token
  reference. Message names "GBNF tokens (`<name>`, `<[id]>`, `!<name>`)"
  as the unsupported feature and points to the tokens addendum.
- `TokenAmbiguityError` — for the `<<name>>` case in Doc 5 §3.4.
  Message names the ambiguous token and recommends the ID form
  (`<[N]>`) as the unambiguous alternative.

When tokens are eventually implemented, these raises become the dispatch
entry points for a new `TokenAtom` handler.

## Error vocabulary

All error classes live in `lexic/exceptions.py`. Raising anything else
for a library-level failure is a review-blocking offence.

| Error | Raised by | Carries |
|---|---|---|
| `UnsupportedConstructError` | parsers, atom dispatches | the construct, where it was encountered |
| `TokenAmbiguityError` | GBNF parser | the ambiguous reference, the ID-form hint |
| `GrammarAuthoringError` | `@grammar_rule` decorator, `ModelEmitter` discriminator analysis | the offending fragment quoted, expected shape, concrete suggestion |
| `FieldValidationError` | subclass of Pydantic's ValidationError | field path, failing constraint, actual value |

Guidelines:

- No bare `raise ValueError`, no bare `raise Exception`. The four above
  cover every case this arc produces.
- Error messages use the format prescribed in `3_ROADMAP.md` Slice E:
  rule-first for parse errors, field-path-first for validation errors,
  fragment-quoted for authoring errors.
- Errors raised from internal callers (IR is malformed, builder
  received the wrong atom type) are still specific: use
  `UnsupportedConstructError` with an "internal" message prefix rather
  than inventing a new class.

## What this architecture does not decide

Three questions are deliberately left for their respective slices'
brainstorming sessions:

- **Regex dialect escape hatch** for users who need `\b` or lookahead
  constructs outside the portable subset (Doc 4 §5). Probably a
  per-field `portable=False` opt-in, but not decided here.
- **Sidecar merge semantics** — strictly structural (YAML keys) vs
  textual (preserve user comments and ordering) (Doc 2 §10.3). Slice C
  open question.
- **`@grammar_rule` template syntax** — Lexic mini-DSL vs rule-body
  syntax of the named flavour. Slice D open question; user leaning
  toward the mini-DSL.

Each of these becomes expensive if decided prematurely and cheap if
decided in context when the slice lands.
