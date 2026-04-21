# Lexic — North star

## Core principle

> Grammar, in whichever flavour the user authored it, is the ground
> truth. Pydantic classes are how Lexic holds that grammar in Python —
> a bridge, not a source. One class per rule; field types correspond
> to atoms; `instance.to_grammar(flavour="gbnf")` round-trips to the
> original grammar. The `@grammar_rule` decorator is how a user
> declares "this Python class represents this grammar rule"; codegen-
> from-grammar-file and decorator-authored code produce the same
> `RuleSpec` IR and the same generated-code shape.

This overrides the "class declaration is the single source of truth"
framing in `prototyping/curr/2_LEXIC_GENERATED_CODE_PROPOSAL.md` §2.
Everything else in that document — pattern-typed fields, discriminated
unions, four-tier naming, sidecar, `_raw`, "looks hand-written" — stands
as a *rendering and authoring-ergonomics* target. The class is how
Python sees a grammar; the grammar remains canonical.

## Invariants every slice must preserve

- **Grammar is canonical.** Every class has a lossless
  `to_grammar(flavour)` path to the grammar text it represents.
- **Round-trip fidelity.** `parse(text, grammar).to_text() == text` on
  every grammar-valid input. Property-test round-trips on all seven
  ground-truth grammars stay green.
- **No regression.** The 312-test suite stays green after each slice.
- **One way to do each task.** One decorator, one parse function, one
  emit method, one round-trip method. No alternate APIs, no legacy
  shims, no "simpler subset" wrappers.
- **Arrows go one way.** Runtime depends on IR; codegen depends on IR;
  runtime does not depend on codegen. See `2_ARCHITECTURE.md` for the
  one deliberate exception.

## In scope for this arc

### From the review track (Docs 0–1)

- Table-driven transformer with per-atom `FieldBuilder`s (V3 §1).
- `CompiledGrammar` + memoised `compile()`; `parse()` becomes thin
  (V3 §8).
- Extraction of `Classifier`, `FieldNamer`, `HelperRuleRegistry` from
  `ir_builder.py` (V3 §2, §3, §10).
- Utils cleanup: `to_lark_name`, bracket-expression parser (V3 §B, §C).
- SOLID pass on remaining 40+-line or deeply-nested methods
  (STYLE §1, §2). `_build_instance`, `_classify`, `_seq_to_atoms`,
  `generate` are the principal candidates.

### From the Pydantic-shape track (Doc 2)

- Atom collapse: `CharClassAtom` + `QuantifiedLiteralAtom` +
  `InlineRegexAtom` → one `PatternAtom`.
- Type-driven emission: `Annotated[str, StringConstraints(...)]` for
  patterns; `Literal[...]` for pure-literal alternations.
- Four-tier naming cascade (alias / pattern library / structural
  positional / sidecar).
- Sidecar YAML for class/field renames on third-party grammars.
- Discriminator synthesis for every union-valued field.
- `_raw: dict[str, str]` for parsed-instance whitespace fidelity.
- `@grammar_rule` decorator authoring path.

### From the ecosystem track (Doc 3)

- Error messages as a product feature: named rules in parse errors,
  field paths in validation errors, fragment-quoting in authoring
  errors.
- Compose with external constraint engines (llama.cpp, llguidance,
  Outlines, XGrammar) — do not own the token-masking loop.

## Debt-prevention allowances (out-of-scope features, cheap scaffolding)

Each allowance below is a small change that preserves an option we have
deliberately deferred. Their total cost is roughly a day of work; the
cost of adding them later grows with every caller of the 1.0 API.

- **`PatternAtom.source_forms: dict[str, str]`** instead of a single
  `gbnf` shadow field — so flavour-specific sources have a home even
  when only `"gbnf"` is populated today. (Doc 4 §2.1.)
- **`codegen(flavour="gbnf")`** parameter accepting only `"gbnf"`
  today; any other value raises `ValueError`.
- **Module rename** `codegen/parser.py` → `codegen/gbnf/parser.py`,
  with a `GbnfAdapter` bundling parser + IR builder + emitter under
  `codegen/gbnf/`. (Doc 4 §3.3, §4.1.)
- **`instance.to_grammar(flavour="gbnf")`** as the forward-facing
  method; `to_gbnf()` preserved as a thin alias.
- **Atom dispatch tables** include an explicit `default` branch that
  raises `UnsupportedConstructError` — prescribed, not optional.
  (Doc 5 §5.2.)
- **GBNF parser raises on `<...>` token syntax**
  (`UnsupportedConstructError`) and on the `<<name>>` nested-angle-
  bracket case (`TokenAmbiguityError`, with an ID-form hint).
  (Doc 5 §5.1, §3.4.)

## Out of scope (no code)

- ABNF / EBNF / Lark / PEG adapters.
- Cross-flavour round-trip tests and `lexic convert` CLI.
- Cross-grammar data translation (R006).
- R005 constrained-decoding engine (token masks, logit biasing,
  llama.cpp sampler integration, tokeniser imports).
- `TokenAtom` in the IR. Parsers raise when they see token syntax;
  implementation is deferred.
- Cross-language codegen (TypeScript, Go, Ruby).
- Streaming API, automatic retry loops, Schema-Aligned Parsing.

## Why the grammar-ground-truth framing matters here

Doc 2's "class is the single source of truth" is a coherent position and
it unlocks a clean decorator DX. But it has two costs we are not willing
to pay:

1. It biases every future design decision toward "make the class more
   expressive" rather than "make the grammar-to-class mapping honest."
   Users who come to Lexic with an existing `.gbnf` (the llama.cpp
   population) become second-class.
2. It implicitly demotes the non-GBNF flavours Lexic wants to support
   later. "The class is the source" only makes sense if there's one
   grammar notation the class implies — once ABNF or EBNF lands as an
   input path, the class needs to carry "which flavour does this
   represent?" as data, not as a hidden assumption.

Making the grammar canonical and the class its Python representation
sidesteps both. It also preserves the cleanest version of Doc 2's DX
win: the *rendered* class still looks hand-written, and the decorator
path is still available for users who prefer to author in Python.
