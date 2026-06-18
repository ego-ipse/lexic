# Lexic — Roadmap

Five slices. Each is independently landable and leaves the tree in a
shippable state with the 312-test suite green.

```
A  →  B  →  C  →  D
                  ↘
                   E  (partially parallelizable with D)
```

Uniform card template per slice:

- **Scope** — what lands.
- **Rationale** — which prior-document concerns the slice closes.
- **Entry criteria** — what must be true before starting.
- **Exit criteria** — observable success at completion.
- **Non-goals** — what this slice does not touch.
- **Open questions** — decisions deliberately deferred to this slice's
  own brainstorming session.

The roadmap is intended to be crisp enough that each slice's future
brainstorming session can go straight into writing-plans, with no
metaplan step in between.

---

## Slice A — Foundational refactor

### Scope

Mechanical SOLID pass on methods that violate STYLE.md §1 (single
responsibility) and §2 (function size and shape), plus the package
move that every later slice assumes. Concrete targets:

- **Package rename.** `src/codegen/` → `src/lexic/codegen/`,
  `src/base.py` → `src/lexic/base.py`, `src/parse.py` → `src/lexic/parse.py`,
  `src/generate.py` → `src/lexic/generate.py`. Create `src/lexic/__init__.py`
  and `src/lexic/utils/`. Update `pyproject.toml` `pythonpath` and every
  import from `from codegen.ir import ...` to `from lexic.ir import ...`.

- **Split IR into its own package.** `src/codegen/ir.py` → `src/lexic/ir/`
  with `atoms.py` (five — soon — dataclasses live here; Slice A keeps
  today's seven) and `spec.py` (`RuleSpec`). `lexic/ir/__init__.py`
  re-exports. No runtime or codegen module imports from each other via
  `ir` — all IR consumers import from `lexic.ir`.

- **Extract `FieldNamer`** from `ir_builder.py` into
  `lexic/codegen/naming.py`. Owns `_CHARCLASS_NAMES`,
  `_LITERAL_NAMES`, `_sanitize_pattern`, `_inline_regex_field_name`, and
  the `_unique` collision counter. One policy, one module.

- **Extract `HelperRuleRegistry`** from `ir_builder.py` into
  `lexic/codegen/helpers.py`. Single registry per `IRBuilder.build()`
  call so helper-rule dedup is globally consistent rather than
  per-`_seq_to_atoms`-invocation. Closes V3 §10.

- **Extract `Classifier`** from `ir_builder.py` into
  `lexic/codegen/classify.py`. `Classifier.classify(rule)` returns a
  `Classification` data object (kind + arms + helper requirements);
  predicates live as methods on a `GbnfRuleTree` wrapper and are
  unit-tested against hand-written AST fixtures. Closes V3 §2.

  **(Brainstorm-resolved, 2026-04-21):** `Classification` is a union of
  per-kind frozen dataclasses (`ValueStr | PureLiteralAlt | NamedAlt |
  SequenceKind`), each carrying its variant-specific payload. Dispatch
  is via `match`. See
  `docs/superpowers/specs/2026-04-21-slice-a-design.md` §Q2.

- **Split `IRBuilder._build_rule` into per-kind methods.** Relocated
  into this Part B decomposition from the Part E SOLID-sweep pass,
  since the per-kind methods naturally consume the Classification-union
  variants landed alongside `Classifier`. (Relocated 2026-04-21;
  preserved draft content at
  `prototyping/next/draft/slice-b-moved.md`.)

- **Table-driven transformer.** Replace `_build_instance` (267 lines,
  five interleaved policies — V3 §1) with:

  ```python
  # registry.py
  BUILDER_BY_ATOM: dict[type[Atom], FieldBuilder] = {
      LiteralAtom:           LiteralSkipBuilder(),
      CharClassAtom:         CharClassFieldBuilder(),
      QuantifiedLiteralAtom: QuantifiedLiteralBuilder(),
      InlineRegexAtom:       InlineRegexBuilder(),
      RuleRefAtom:           RuleRefBuilder(),
      InlineAlternationAtom: InlineAlternationBuilder(),
      AlternationAtom:       AbstractAlternationBuilder(),
  }

  # builders.py
  class FieldBuilder(Protocol):
      def build(self, ctx: BuildContext) -> FieldResult: ...
  ```

  `Optional[X]` and `List[X]` are *wrapping* builders
  (`OptionalFieldBuilder(inner)`, `ListFieldBuilder(inner)`), not
  forked branches in the core loop. Every builder is unit-tested in
  isolation.

  Note: the seven-entry dispatch table above matches the *current*
  seven atom types. After Slice B, three of these (`CharClassAtom`,
  `QuantifiedLiteralAtom`, `InlineRegexAtom`) collapse into a single
  `PatternAtom` entry. Keeping Slice A's transformer dispatch faithful
  to today's atoms makes the Slice B collapse a two-line registry
  change rather than a rewrite.

- **`CompiledGrammar` + memoised `compile()`.** Replace the per-call
  codegen in `parse()` (V3 §8) with:

  ```python
  @dataclass(frozen=True)
  class CompiledGrammar:
      classes: dict[str, type[GrammarModel]]
      specs: dict[str, RuleSpec]
      parser: lark.Lark
      transformer: Transformer

      def parse(self, text: str) -> GrammarModel: ...

  def compile(grammar_path: str | Path) -> CompiledGrammar: ...
  # memoised by (path, mtime)
  ```

  `parse(text, grammar)` becomes `compile(grammar).parse(text)` — a
  one-liner.

- **Utils cleanup.** Move `to_lark_name` from `lark_builder.py` into
  `lexic/utils/names.py` (closes V3 §C module cycle). Extract
  `_parse_escape` and `_parse_charclass_chars` from `generate.py` into
  `lexic/utils/charclass.py` (closes V3 §B, removes the parallel
  bracket-expression parser).

- **SOLID pass on any remaining 40+-line or 4+-level-nested method.**
  Known candidates beyond those above: `generate.py::generate` (274
  lines), `IRBuilder._seq_to_atoms`, `IRBuilder.build` orchestration,
  any method flagged by STYLE §2's signals. Split; do not abstract for
  hypothetical future needs (STYLE §4).

  Note (2026-04-21): `IRBuilder._build_rule` splitting was originally
  slated here but was relocated into the `Classifier` extraction bullet
  above, since the per-kind split consumes the Classification union
  variants directly. See `docs/superpowers/specs/2026-04-21-slice-a-design.md`
  §B.

### Rationale

Every item is prescribed by Docs 0–1 and is a pure cleanup — none
commit to the new IR shape or the new authoring surface, so each lands
and ships independently. The table-driven transformer is prerequisite
for Slice B: collapsing three atom types into one is cheap over a
dispatch table and expensive over five interleaved `isinstance`
branches.

### Entry criteria

- None. Can start today.

### Exit criteria

- All 312+ tests pass; property round-trips on all seven ground-truth
  grammars green.
- `ir_builder.py` under 200 lines.
- Every `FieldBuilder` in the new transformer has its own unit test
  that exercises it against a focused IR fixture.
- `parse()` does not regenerate modules on repeated calls with the
  same grammar path; the per-call cost after the first compile drops
  below 1ms (the current cost is ~20ms per call, noted in
  `tests/property/conftest.py`).
- `transformer/builders.py` contains no `isinstance` cascade over atom
  types.
- `base.py` has at most one `lexic.codegen` import (the existing
  `GBNFEmitter` import powering `to_gbnf()`). Slice B replaces that
  with the documented eager `to_grammar` edge to
  `lexic.codegen.gbnf.emitter`. No lazy intra-function imports from
  `base.py` at any point.
- `from codegen.X` imports no longer appear anywhere in the tree;
  every import is `from lexic.X`.

### Non-goals

- No changes to IR atom types.
- No `flavour=` parameter.
- No `@grammar_rule` decorator.
- No sidecar.
- No changes to generated-code shape.

### Open questions

**All four resolved in brainstorming 2026-04-21. Full rationale:
`docs/superpowers/specs/2026-04-21-slice-a-design.md`.**

- ~~Exact contract of `BuildContext` and `FieldResult`~~ — **Resolved:**
  frozen `BuildContext` (no mutation); orchestrator owns cursor;
  builders return `FieldResult | SkipField` (tagged union, no sentinel).
- ~~Flat `Classification` or union?~~ — **Resolved:** union of per-kind
  frozen dataclasses; `match`-dispatched downstream.
- ~~`CompiledGrammar` memo key~~ — **Resolved:** `(path, mtime, size)`;
  `compile(text, *, cache_key)` primary, `compile_from_path(path)` thin
  wrapper; one shared cache.
- ~~`FieldNamer` lifetime~~ — **Resolved:** not a class. Module-level
  `assign_field_names(atoms)` function. Per-rule scope unchanged.

---

## Slice B — PatternAtom collapse, Tier 2.5 scaffolding, token reservation

### Scope

- **Atom collapse.** Three existing atom types merge into one:

  ```python
  @dataclass(frozen=True)
  class PatternAtom:
      regex: str                    # canonical Python re dialect
      source_forms: dict[str, str]  # flavour-shadow map
      min: int
      max: int | None
  ```

  `source_forms["gbnf"]` is populated by the GBNF adapter's parser and
  read by the GBNF emitter. Any future flavour reads/writes its own key.
  V3's three-atom split is preserved inside `source_forms` granularity
  (each source-form string captures what that flavour saw), not in the
  atom type.

- **Five-atom union, closed but versioned.** `LiteralAtom`,
  `PatternAtom`, `RuleRefAtom`, `AlternationAtom`, `InlineAlternationAtom`.
  Every dispatch table (transformer, model emitter, GBNF emitter,
  generator) has an explicit `default` branch raising
  `UnsupportedConstructError`. (Doc 5 §5.2.)

- **Tier 2.5 flavour scaffolding** (Doc 4 §3.3):
  - Rename `src/lexic/codegen/parser.py` → `src/lexic/codegen/gbnf/parser.py`.
    Move `ast.py` with it. Create `src/lexic/codegen/gbnf/__init__.py`
    exporting a `GbnfAdapter` that implements the `FlavourAdapter`
    protocol from `2_ARCHITECTURE.md`.
  - Add `flavour: str = "gbnf"` parameter to `codegen()`. Any other
    value raises `ValueError("Unknown flavour: {flavour}. Supported: gbnf")`.
  - Add `GrammarModel.to_grammar(flavour: str = "gbnf")`. Keep
    `to_gbnf()` as a thin alias calling `to_grammar("gbnf")`.
  - Move `gbnf_emitter.py` into `codegen/gbnf/emitter.py`. Change
    `base.py::to_grammar` to an eager module-level import (no lazy
    intra-function import). Closes V3 §9.

- **Token reservation** (Doc 5 §5.1):
  - GBNF parser raises `UnsupportedConstructError` on any `<...>`
    token-reference syntax, with a one-line message naming "GBNF
    tokens (`<name>`, `<[id]>`, `!<name>`)" as the unsupported feature.
  - GBNF parser raises `TokenAmbiguityError` on the `<<name>>` nested-
    angle-bracket case (Doc 5 §3.4), with a message recommending the
    ID form (`<[N]>`) as the unambiguous alternative.

### Rationale

Atom collapse is the single refactor that most simplifies every
downstream consumer and folds V3 §1 (transformer bridge), §2 (classifier
cascade), and §5 (`generate.py` structural duplication) partially or
fully. `source_forms` accommodates flavour shadows without locking the
atom into GBNF. Tier 2.5 items are nearly free alongside the collapse —
same files, same tests — and every day they're deferred is another day
of 1.0-API callers whose code would break when the parameters change.
Token reservation is one raise per codepath and a test; skipping it now
means the feature quietly locks in an implementation path the first
time a user lands a grammar with `<think>`.

### Entry criteria

- Slice A complete. Table-driven transformer in place; `Classifier`,
  `FieldNamer`, `HelperRuleRegistry` extracted.

### Exit criteria

- Five atom types in `lexic.ir`. `CharClassAtom`,
  `QuantifiedLiteralAtom`, `InlineRegexAtom` are gone.
- All 312+ tests pass; property round-trips green.
- `codegen(grammar, flavour="gbnf")` works; `codegen(grammar, flavour="abnf")`
  raises with a clear diagnostic naming supported values.
- `instance.to_grammar("gbnf")` works; `to_gbnf()` still works; both
  produce byte-identical output for the seven ground-truth grammars.
- Test `tests/integration/test_token_reservation.py` asserts that
  `<think>` in a grammar raises `UnsupportedConstructError` naming
  tokens as the unsupported feature.
- Same test file asserts that `<<name>>` raises `TokenAmbiguityError`
  with the ID-form hint.
- `base.py` has no `codegen` imports other than the explicit
  `to_grammar` edge documented in `2_ARCHITECTURE.md`.

### Non-goals

- No ABNF/EBNF parsing (the `flavour=` slot exists but accepts only
  `"gbnf"`).
- No `TokenAtom` in the IR.
- No generated-code shape changes — `ModelEmitter` still produces
  today's shape, just over the merged atom.
- No `@grammar_rule` decorator.
- No four-tier naming (Slice C).

### Open questions

- What's the exact portable regex subset? (Doc 4 §4.2 lists one;
  needs tightening to "Lark-safe and expressible in GBNF bracket
  syntax".)
- Does `PatternAtom.regex` have a canonical form (always anchored
  with `^$`, always non-capturing groups), or does it carry whatever
  the parser saw?
- `InlineAlternationAtom` vs `PatternAtom` — is a pure-character
  alternation like `(a|b|c)` flattened into a pattern, or kept as
  an inline alternation?
- Where does `UnsupportedConstructError` live — `lexic.exceptions`
  (established in `2_ARCHITECTURE.md`) vs per-package exception
  modules?

---

## Slice C — Type-driven IR contract + GBNF-path emission retrofit

### Scope

- **Type-driven emission.** `ModelEmitter` emits:
  - `Annotated[str, StringConstraints(pattern=...)]` for every
    `PatternAtom`. The emitted pattern is `^` + `PatternAtom.regex` + `$`
    (anchored).
  - `Literal[...]` for pure-literal alternations — every arm is a
    single `LiteralAtom`, min=max=1. Mixed alternations
    (literal + rule-ref) still use helper classes.

  From Doc 2 §5.2, representative mapping:

  | GBNF source | Emitted type |
  |---|---|
  | `[a-h]` | `Annotated[str, StringConstraints(pattern=r"^[a-h]$")]` |
  | `[0-9]+` | `Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]` |
  | `[0-9]{0,15}` | `Annotated[str, StringConstraints(pattern=r"^[0-9]{0,15}$")]` |
  | `"int" \| "float" \| "char"` | `Literal["int", "float", "char"]` |
  | `"+" \| "-" \| "*" \| "/"` | `Literal["+", "-", "*", "/"]` |

- **Four-tier naming cascade** (Doc 2 §6):
  - **Tier 1 — type-alias names.** A field whose type is bound to a
    module-level `Annotated`/`Literal` alias gets the alias's
    snake-cased name by default. Collisions: `digits`, `digits_2`.
  - **Tier 2 — built-in pattern library.** ~10 entries mapping
    well-known regex strings to conventional names:

    ```python
    BUILTIN_PATTERNS = {
        r"^[0-9]$":         "digit",
        r"^[0-9]+$":        "digits",
        r"^[a-z]$":         "lower",
        r"^[A-Z]$":         "upper",
        r"^[a-zA-Z]$":      "letter",
        r"^[a-zA-Z_]$":     "letter",
        r"^[a-zA-Z_0-9]$":  "alnum",
        r"^[a-zA-Z_0-9]*$": "alnum_tail",
        r"^[ \t]+$":        "spaces",
        r"^[ \t\n]+$":      "ws",
    }
    ```

    Extensible via `lexic.register_pattern(...)` or
    `[tool.lexic.patterns]` in `pyproject.toml`. Users do not fork
    Lexic to add a pattern.
  - **Tier 3 — structural positional.** `head`, `body`, `kind`,
    `part_2`. Honest about structure, not lying about semantics.
    Fugly on purpose — exists so every rule has a valid generated
    shape, and so the sidecar has something to rename.
  - **Tier 4 — sidecar YAML.** `<module>.lexic.yaml` next to the
    generated module; renames tiers 1–3 per field or per class.

    Precedence: **sidecar > tier 1 > tier 2 > tier 3**.

- **Discriminator synthesis.** Every union-valued field emits an
  `Annotated[Union[...], Discriminator(fn)]` alias and a generated
  `_discriminate_<name>` function. From Doc 2 §7.6:

  ```python
  Factor = Annotated[
      Identifier | Number | UnaryTerm | FuncCall | ParenExpression,
      Discriminator(_discriminate_factor),
  ]

  def _discriminate_factor(v):
      if isinstance(v, GrammarModel):
          return type(v).__name__
      if isinstance(v, dict):
          if "expression" in v: return "ParenExpression"
          if "args" in v:       return "FuncCall"
          if "factor" in v:     return "UnaryTerm"
          if "digits" in v:     return "Number"
          if "value" in v:      return "Identifier"
      raise TypeError(f"Cannot discriminate Factor: {v!r}")
  ```

  Analysis at codegen time: required field sets must be unique across
  arms; ambiguous arms raise `GrammarAuthoringError` with the
  ambiguous pair named.

- **List-tail flattening.** Grammars of shape `X (sep X)*` where `sep`
  is pure-literal or `ws` flatten to `List[X]` with a separator
  annotation on the atom. Semantic separators (e.g. `term ([-+*/] term)*`)
  keep their helper class. Eliminates most `ArrayItem` / `StatementArm7Item`
  leakage (Doc 2 §1 problem 4).

- **`_raw: dict[str, str]` on parsed instances.** Parsed instances
  populate `_raw` with whitespace and separator fragments recorded by
  the transformer; constructed instances have `_raw = None` and emit
  canonical form. Excluded from `model_dump()`, `__eq__`,
  `semantic_dump()`. Replaces the visible `ws`, `ws2` fields on
  consuming classes.

  Contract:
  - `parse(text).to_text() == text` — exact round-trip for parsed input.
  - `Constructed(...).to_text() == canonical_form` — canonical emission.
  - `parse(Constructed(...).to_text())` — always succeeds.

### Rationale

The Pydantic-first *rendering* target materialises. Generated code
stops being a grammar-AST transcription and starts looking like
something a user would have written. The four-tier cascade replaces
`a_h_x` / `val_0_92` with a real precedence ladder; discriminator
synthesis unblocks construction-from-dict for every union (prerequisite
for Slice D's decorator path); `_raw` makes round-trip explicit instead
of leaking whitespace into visible fields. Grammar remains ground truth
— the emitted code is a cleaner Python-side representation *of* that
grammar.

### Entry criteria

- Slice B complete. `PatternAtom` with `source_forms` exists; five-atom
  union with `default`-raise dispatch; token reservation in place.

### Exit criteria

- All seven ground-truth grammars regenerate; all existing tests pass.
- `generated/chess.py` has no `a_h_x` / `nbkqr` field names; fields
  use tier-1/2/4 naming (e.g. `dest_file`, `dest_rank`, `promotion`).
- `generated/json_ws.py::Number` has `sign`, `integer_part`,
  `fractional_part`, `exponent`.
- Every `Union` field in generated code carries a `Discriminator`
  annotation and a generated `_discriminate_*` function.
- Parsed-instance round-trip goes through `_raw`; constructed-instance
  emission produces canonical form. Both are asserted in tests.
- Sidecar absent → tier 1–3 defaults only; sidecar present → renames
  applied structurally; sidecar with unknown class/field → raises
  `GrammarAuthoringError` naming the unknown key.

### Non-goals

- No `@grammar_rule` decorator.
- No decorator template DSL.
- No ABNF/EBNF emission.
- No changes to the GBNF parser beyond what tier-1/2 naming needs.

### Open questions

- Exact sidecar YAML schema. Doc 2 §6.4 sketches one; details need a
  session.
- Tier-1 mechanism: since codegen *emits* type aliases rather than
  reading them, alias discovery is structural (pattern library +
  collision disambiguation). How does this reconcile with decorator-
  authored code in Slice D, where aliases may be user-declared?
- Analysis rule for "ambiguous arms" — is required-field-set
  uniqueness sufficient, or does it need to consider the full field
  shape (including types)?
- Where does the pattern library live and what's the extension API
  — `lexic.register_pattern(name, regex)`, `[tool.lexic.patterns]` in
  `pyproject.toml`, or both?
- How does `_raw` survive `model_validate_json` / `model_dump_json`?
  Private field, omitted entirely, or opt-in serialisation?

---

## Slice D — Decorator authoring path + sidecar parser

### Scope

- **`@grammar_rule` decorator** in `src/lexic/grammar_rule.py`. From
  Doc 2 §4.3:

  ```python
  def grammar_rule(template: str, *, flavour: str = "gbnf"):
      def decorate(cls: type[GrammarModel]) -> type[GrammarModel]:
          tokens = _parse_template(template, flavour)
          _validate_field_refs(tokens, cls.model_fields)
          atoms  = _build_atoms(tokens, cls.model_fields, _module_aliases(cls))
          cls.__grammar__ = RuleSpec(
              rule_name=_snake(cls.__name__),
              class_name=cls.__name__,
              parent_class_name="GrammarModel",
              kind="sequence",
              items=atoms,
              field_map=_derive_field_map(atoms, cls.model_fields),
          )
          _resolve_forward_refs(cls)
          return cls
      return decorate
  ```

- **Class-time validation.** Every field referenced in the template
  must exist on the class; every field on the class must appear in
  the template (except `_raw`); type mismatches (template expects a
  pattern field, class has a rule-ref field) raise
  `GrammarAuthoringError` with the offending fragment quoted and a
  concrete suggestion.

- **Sidecar parser formalisation.** Slice C already emits/consumes a
  sidecar from the GBNF-first path. This slice formalises the parser
  surface, adds the merge-with-regenerated-defaults behaviour
  (Doc 2 §10.3), and validates sidecar keys against real class/field
  names at codegen time.

- **Interop with the GBNF-first path.** `parse(text, grammar)` accepts
  either a grammar-file path (compile-then-parse) or a module/class
  produced by decorator authoring. `semantic_dump()` on an instance is
  identical regardless of which path produced the classes.

### Rationale

The Pydantic-first *authoring* target materialises. A user can
`pip install lexic`, write a small Pydantic class file, and parse text
— no GBNF file required. This is the Instructor-equivalent DX win from
Doc 3 §1.1. Importantly: grammar is still ground truth; the decorator
declares "this class represents this grammar rule" and
`to_grammar("gbnf")` is the faithful inverse.

### Entry criteria

- Slice C complete.

### Exit criteria

- `tests/integration/test_decorator_authored.py` declares the
  arithmetic grammar via decorators and round-trips against
  hand-written input.
- `parse(text, DecoratorAuthoredModule)` and
  `parse(text, "arithmetic.gbnf")` produce `semantic_dump()`-equal
  instances on the same input.
- Sidecar parser accepts the Doc 2 §6.4 schema (as refined in Slice C)
  and raises clear errors on keys that don't map.
- Decorator-authored classes emit GBNF via `to_grammar("gbnf")` that
  re-parses to the same `RuleSpec` list (modulo canonical rule order).

### Non-goals

- No ABNF/EBNF rule-body parsing in the decorator (the `flavour=`
  slot accepts only `"gbnf"` today).
- No cross-grammar translation.
- No auto-synthesised helper classes at decorator time — the decorator
  raises with a clear diagnostic, the user decomposes explicitly.

### Open questions

- **Template syntax — deferred from brainstorming Pass 2.** One of:

  - **(A) Lexic mini-DSL.** The strict-subset-of-GBNF grammar from
    Doc 2 §4.1:

    ```
    rule       := item*
    item       := literal | field_ref
    field_ref  := name quantifier?
    quantifier := "?" | "+" | "*" | ("+" | "*") separator
    separator  := "[" sep_item+ "]"
    sep_item   := literal | bare_rule_ref   # no fields allowed inside
    literal    := '"' chars '"'
    name       := identifier                # must match a field on the class
    ```

    The decorator parses the template using a Lexic-owned parser; the
    string is *not* literal GBNF and is *not* the rule-body of any
    named flavour. **User is leaning toward this option.** Pros:
    bounded syntax, no coupling to flavour parsers, clean errors.
    Cons: a third authoring surface to document alongside GBNF text
    and Pydantic classes. Cons: interacts awkwardly with the
    grammar-is-ground-truth framing (the decorator template is a
    Lexic-specific surface, not the grammar itself).

  - **(B) Rule-body syntax of the named flavour.** `flavour="gbnf"`
    means the template is a valid GBNF rule body, parsed via
    `GbnfAdapter`'s subset mode. Pros: one fewer syntax to learn;
    respects grammar-is-ground-truth uncompromisingly — the template
    literally is grammar. Cons: more coupling between decorator and
    adapter; richer syntax means more decorator-time errors to
    diagnose; constructs like nested groups with rule refs force an
    immediate decision on whether to raise or synthesise.

  Both options are compatible with the rest of the plan. Resolution
  happens in this slice's brainstorming session.

- When a rule body contains constructs that don't map to a Pydantic
  field (nested grouping with rule refs, mixed literal/rule-ref
  alternations), does the decorator raise with a clear diagnostic, or
  synthesise helper classes silently? The non-goal says raise; confirm
  in-session.

- How are recursive forward references resolved — `model_rebuild()`
  with which namespace, and at what point in class creation?

- How does the decorator handle discriminated-union aliases defined
  before their arms (forward-declared arms)?

---

## Slice E — Round-trip polish + error-quality pass

### Scope

- **Error message overhaul** (Doc 3 §3.3):
  - **Parse errors name the rule first.**
    `"Expected 'expression' after '=' at line 3, got '}'"` beats
    `"UnexpectedToken at col 42"`.
  - **Validation errors name the field path plus the constraint.**
    `"Number.integer_part: pattern ^(0|[1-9][0-9]{0,15})$ did not match '007'"`
    beats `"ValidationError on Number"`.
  - **Grammar-authoring errors quote the offending fragment.**
    `"@grammar_rule('expr \"=\" missing_field'): 'missing_field' is not a field of Assignment. Did you mean 'result'?"`

- **Textual GBNF round-trip.** `emit(parse(text)) == text` modulo
  documented normalisation (canonical whitespace, canonical rule
  order), asserted for all seven ground-truth grammars. Closes V3
  testing gap §4.

- **Fix `generate.py` quantifier-generation bias** (V3 §A):
  `_pick_count` actually explores `[0, max]` in random mode;
  `minimal=True` stays available for non-exploratory uses. Add
  `c.gbnf` to the property-test parameterisation (currently skipped
  because its root is `(declaration)*` and the generator returned
  `""` for optional roots).

- **Failure-mode tests.** Ill-formed text after valid prefix,
  unclosed brackets, trailing garbage — each with an assertion on
  the specific error raised. Closes V3 testing gap §3.

- **Documentation pass.** README example reordered (Pydantic-first
  example first, GBNF authoring second — Doc 3 §3.4). Seven runnable
  examples, one per ground-truth grammar. Sidecar cookbook: rename,
  flatten, opt-into-Literal, mark-transparent.

- **Any deferred cleanup** from earlier slices that didn't fit
  without inflating their scope.

### Rationale

Takes the codebase from "works for the maintainer" to "works for a
stranger with a grammar they didn't write." Error quality is where
small libraries beat large ones (Doc 3 §3.3). Round-trip textual
fidelity is the contract the whole value proposition rests on and
is currently asserted only structurally.

### Entry criteria

- Slices A–D complete. This is the one slice partially
  parallelizable with D — textual round-trip work and the
  `generate.py` fix can start during D, but the error-message pass
  needs D's new error surface to be meaningful.

### Exit criteria

- Every parse-error path has a named rule and a clear diagnostic.
- Every `StringConstraints` validation failure surfaces the field
  path.
- `c.gbnf` has a non-empty round-trip test; all seven grammars have
  `emit(parse(text)) == text` asserted.
- Failure-mode test suite covers at least: unclosed bracket, trailing
  garbage, leading whitespace when `strict=True`, malformed
  alternation.
- README example is Pydantic-first; seven runnable example grammars
  linked.

### Non-goals

- No streaming API.
- No retry loop / Schema-Aligned Parsing / LLM-output cleanup layer.
- No CLI beyond what already exists.

### Open questions

- Where does the error-message template live — per-exception class
  (encapsulated formatting) or a central formatter (single policy)?
- Is there a `strict=False` parse mode (skip leading whitespace /
  trailing garbage, Doc 3 §1.2), or is every parse strict?
- Documentation medium — markdown in-repo only, a docs site, or both?
