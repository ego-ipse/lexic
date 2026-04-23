# Slice B — PatternAtom collapse + Tier 2.5 scaffolding + token reservation — Design Spec

**Date:** 2026-04-23
**Status:** Approved (brainstormed)
**Implementation plan:** `docs/superpowers/plans/2026-04-23-slice-b-pattern-atom-tier-2-5-tokens.md` (to be written)
**Roadmap entry:** `prototyping/next/3_ROADMAP.md` §Slice B

## Background

Slice B carries three bundled concerns:

1. **Atom collapse.** `CharClassAtom`, `QuantifiedLiteralAtom`, and `InlineRegexAtom` merge into a single `PatternAtom`. `InlineAlternationAtom` reshapes from helper-rule-references to inline-atom-arms. Atoms become `frozen=True`.
2. **Tier 2.5 flavour scaffolding.** The GBNF-specific parser, emitter, escape decoder, and bracket-expression parser move into `codegen/gbnf/`. A `FlavourAdapter` / `FlavourParser` / `FlavourEmitter` protocol triad lands in `codegen/flavours.py`. A `flavour="gbnf"` parameter is threaded through `codegen()`, `compile()`, and `GrammarModel.to_grammar()`.
3. **Token reservation.** The GBNF parser raises `UnsupportedConstructError` on `<name>`, `<[N]>`, and `!<name>` token references before any atom construction runs.

Plus four bundled cleanups that share files with the above work:
- Delete `LarkBuilder.build_transformer` (one-line indirection antipattern).
- Freeze all atom dataclasses.
- Create `lexic/exceptions.py` as the single home for library error classes.
- Strip `<<name>>` / `TokenAmbiguityError` references from `2_ARCHITECTURE.md` and `3_ROADMAP.md` (stale; that syntax does not exist in GBNF).

This spec resolves the four open questions deferred to Slice B's brainstorming in `3_ROADMAP.md` §Slice B and documents five additional decisions surfaced during the session.

## Open questions — resolutions

### Q1. `PatternAtom.regex` canonical form

**Resolution:** Unanchored, groups canonicalized to non-capturing `(?:...)`.

IR stores `[0-9]+`, `(?:int|float|char)`, `foo+` — never `^...$`. Anchors are an emission concern (Slice C will wrap with `^...$` when emitting `Annotated[str, StringConstraints(pattern=...)]`). Groups are canonicalized at parse time by the flavour adapter so that pattern-library lookups and round-trip equality are stable regardless of source syntax.

**Rationale.** Anchors belong in the emission contract, not the IR contract (IR describes shape; emission decides how a type system consumes it). Non-capturing groups prevent a "same pattern, two keys" bug in Slice C's pattern library (Tier 2 of the naming cascade).

**Rejected alternatives:** Anchored IR (conflates IR shape with Python-regex emission); as-seen groups (pattern-library lookup would fork on capturing vs non-capturing).

### Q2. Pure-literal inline alternations — `PatternAtom` or `InlineAlternationAtom`?

**Resolution:** Pure-literal inline alts stay as `InlineAlternationAtom`. Only mixed alts (with rule-refs) remain inline alternations too; both use the same atom type with inline arm content.

`("think" | "answer" | "none")` → `InlineAlternationAtom(arms=(Arm((LiteralAtom("think"),)), Arm((LiteralAtom("answer"),)), Arm((LiteralAtom("none"),))))`. Single-character pure-literal alts (`a | b | c`) are not special-cased — they're still pure literals.

**Rationale.** Slice C explicitly emits `Literal["think", "answer", "none"]` for pure-literal alternations; the IR must carry the individual literals for that emission to be possible. Collapsing pure-literal alts into a `PatternAtom(regex="(?:think|answer|none)")` would defer the structural information to a regex-to-literal recognizer in Slice C — more work, same end state, less-clean IR.

**Rejected alternatives:** Collapse-to-pattern (defers decision); split-by-arm-type (encodes a heuristic that stops making sense once `Literal[...]` exists).

### Q3. Portable regex subset — what does `PatternAtom.regex` accept?

**Resolution:** Per-flavour capability descriptor.

```python
# lexic/ir/regex_portable.py
PORTABLE_FEATURES: frozenset[str] = frozenset({
    "literal",
    "char_class",
    "negated_class",
    "shorthand",
    "quantifier",
    "alternation",
    "non_capturing_group",
    "unicode_escape",
})

def validate_portable(regex: str) -> None: ...    # raises UnsupportedConstructError
def features_used(regex: str) -> frozenset[str]: ...
```

```python
# codegen/flavours.py
class FlavourEmitter(Protocol):
    supports: frozenset[str]        # ⊆ PORTABLE_FEATURES
    def emit(self, specs: list[RuleSpec]) -> str: ...
```

At codegen time, the compile pipeline walks every `PatternAtom` and cross-checks:

```python
validate_portable(atom.regex)
missing = features_used(atom.regex) - adapter.emitter.supports
if missing:
    raise UnsupportedConstructError(
        f"Pattern {atom.regex!r} uses features {sorted(missing)} "
        f"not supported by {adapter.name!r} emitter"
    )
```

`validate_portable` is always enforced (IR contract). The `missing` check is flavour-specific.

**GBNF `supports` set:** `{"literal", "char_class", "negated_class", "quantifier", "alternation", "non_capturing_group", "unicode_escape"}`. Shorthand (`\d \w \s`) is *not* in GBNF's `supports` — the `GbnfParser` lowers shorthand to equivalent char classes at parse time (`\d` → `[0-9]`, `\w` → `[a-zA-Z0-9_]`, `\s` → `[ \t\n\r]`), so the IR never carries shorthand in a GBNF-parsed tree. If a non-GBNF parser produces shorthand and a user then tries to emit GBNF from that IR, the cross-check raises cleanly.

**Rationale.** "Portable" must be something code can assert and tests can verify, or it rots into "whatever the current GBNF adapter accepts" — exactly the hardcoding `source_forms` exists to avoid. The per-flavour capability set is the only shape that remains honest when a second adapter lands.

**Rejected alternatives:** Implicit portable subset (no testable contract); explicit contract without per-flavour support (cross-check must live somewhere — adapter is the right place).

### Q4. Where does `UnsupportedConstructError` live?

**Resolution:** `lexic/exceptions.py`, as prescribed by `2_ARCHITECTURE.md` §Error vocabulary.

Slice B creates `lexic/exceptions.py` with four classes:

```python
class LexicError(Exception): ...
class UnsupportedConstructError(LexicError): ...
class GrammarAuthoringError(LexicError): ...    # stub for Slice C
class FieldValidationError(LexicError): ...     # stub
```

`GrammarAuthoringError` and `FieldValidationError` are stub-landed to prevent import-path churn when Slice C wires them up.

`TokenAmbiguityError` is **not** created (see §Additional decisions, D5).

**Rationale.** `2_ARCHITECTURE.md` prescribes a single error-vocabulary home; the roadmap's Slice B scope text saying `raise ValueError("Unknown flavour: ...")` was a pre-architecture draft that this spec overrides.

## Additional decisions

Five decisions surfaced during brainstorming that are not in the roadmap's open-question list but are scope-shaping.

### D1. Delete `LarkBuilder.build_transformer` (antipattern cleanup)

The method is pure indirection — a one-liner forwarding to `build_transformer(self._specs, classes)`. Two callers exist (`src/lexic/compile.py:65`, `tests/unit/lexic/codegen/test_transformer.py:26`). Both are updated to call `build_transformer` directly. `LarkBuilder` becomes grammar-string-only (its docstring is amended accordingly).

### D2. `InlineAlternationAtom` shape change — inline arms, not helper-rule names

**Today:** `InlineAlternationAtom.arm_rule_names: list[str]` — arms are rule names pointing at synthesized helper rules.
**Slice B:** `InlineAlternationAtom.arms: tuple[Arm, ...]` where `Arm` is a new dataclass:

```python
@dataclass(frozen=True)
class Arm:
    """One branch of an alternation — an ordered sequence of atoms."""
    atoms: tuple["Atom", ...]

@dataclass(frozen=True)
class InlineAlternationAtom:
    arms: tuple[Arm, ...]
```

`Arm` is a named type, not an anonymous nested container. `tuple` instead of `list` at both levels for genuinely immutable semantics.

Inline-alt helper-rule synthesis in `seq_to_atoms.py` stops. `HelperRuleRegistry` stays — it's still used for quantified-list helpers.

`AlternationAtom` (top-level) keeps `arm_rule_names: tuple[str, ...]` — top-level arms are separate `RuleSpec`s referenced by name, a different concept from intra-rule branches.

### D3. Frozen atoms

All atom dataclasses gain `frozen=True`. `CLAUDE.md` already describes them as "seven frozen Atom dataclasses" — the current `@dataclass` without `frozen=True` is a documentation/code mismatch that Slice B corrects.

### D4. GBNF-specific code audit — move into `codegen/gbnf/`

Your rule: anything GBNF-specific lives in `codegen/gbnf/`. Three modules currently in `utils/` or shared locations are actually GBNF-specific and move:

| Currently at | Moves to | Why |
|---|---|---|
| `utils/escapes.py` (`decode_gbnf_escapes`) | `codegen/gbnf/escapes.py` | Function name tells you it's GBNF. Only the GBNF adapter should know GBNF's escape syntax. |
| `utils/charclass.py` (`parse_escape`, `parse_charclass_chars`) | `codegen/gbnf/charclass.py` | Parses GBNF bracket expressions (GBNF-flavored escapes). After Slice B the only consumer is the GBNF adapter. |

`utils/quantifiers.py::bounds_to_quantifier` and `utils/names.py` stay in utils — they are genuinely shared across flavour-family concerns (quantifier syntax is common to GBNF, Lark, Python regex, ECMAScript).

**Parse-time decode invariant (new):** `LiteralAtom.value` and `PatternAtom.regex` are *canonical Python* strings and regex respectively, already decoded from flavour-specific escapes by the adapter's parser. No downstream consumer (model emitter, lark builder, transformer, generator) knows any flavour's escape syntax. `LiteralAtom` does not need `source_forms` because re-escaping for emission is deterministic per flavour.

### D5. Drop `<<name>>` / `TokenAmbiguityError`

`<<name>>` double-angle-bracket token syntax does not exist in GBNF. The `TokenAmbiguityError` class described in `2_ARCHITECTURE.md` §Error vocabulary and the `<<name>>` case in `3_ROADMAP.md` §Slice B are both based on an incorrect reading of the GBNF token addendum. They are removed from both docs as part of Slice B.

Token reservation reduces to one error path (see §Token reservation below).

## Architecture delta

### Target module layout after Slice B

```
src/lexic/
  __init__.py
  base.py                         to_grammar(flavour="gbnf"); to_gbnf() is alias
  compile.py                      compile(text, *, cache_key, flavour="gbnf")
  exceptions.py                   NEW
  generate.py                     updated atom dispatches; regex-aware sampling
  parse.py                        unchanged
  ir/
    __init__.py                   re-exports 5 atom types + Arm + RuleSpec
    atoms.py                      frozen; 5 atom types (was 7)
    regex_portable.py             NEW
    spec.py                       unchanged
  codegen/
    __init__.py                   codegen(text, *, stem, flavour="gbnf")
                                  build_classes_and_specs(text, *, stem, flavour="gbnf")
                                  codegen_from_path(path, *, flavour=None)
    classify.py                   unchanged
    naming.py                     updated for new atom shapes
    helpers.py                    unchanged (still used for quantified-list helpers)
    seq_to_atoms.py               updated; no helper-rule synthesis for inline alts
    ir_builder.py                 updated atom construction
    model_emitter.py              single PatternAtom branch; new InlineAlternationAtom
    lark_builder.py               single PatternAtom branch; delete build_transformer
    flavours.py                   NEW — FlavourAdapter/Parser/Emitter protocols + ADAPTERS
    transformer/
      __init__.py                 unchanged public surface
      registry.py                 single PatternAtom entry; updated InlineAlternationAtom
      builders.py                 PatternFieldBuilder (merges three); updated InlineAlt
      build_transformer.py        unchanged
      context.py                  unchanged
    gbnf/
      __init__.py                 NEW — exports GbnfAdapter; side-effect registers it
      adapter.py                  NEW — class GbnfAdapter(FlavourAdapter)
      parser.py                   moved from codegen/parser.py; wrapped as class GbnfParser(FlavourParser)
      emitter.py                  moved from codegen/gbnf_emitter.py; wrapped as class GbnfEmitter(FlavourEmitter)
      ast.py                      moved from codegen/ast.py (internal to GbnfParser)
      escapes.py                  moved from utils/escapes.py
      charclass.py                moved from utils/charclass.py
  utils/
    __init__.py
    names.py                      unchanged
    quantifiers.py                unchanged
```

### Creates, moves, deletes

**Creates:**
- `lexic/exceptions.py`
- `lexic/ir/regex_portable.py`
- `lexic/codegen/flavours.py`
- `lexic/codegen/gbnf/__init__.py`
- `lexic/codegen/gbnf/adapter.py`

**Moves (via `git mv` for rename detection):**
- `lexic/codegen/parser.py` → `lexic/codegen/gbnf/parser.py`
- `lexic/codegen/ast.py` → `lexic/codegen/gbnf/ast.py`
- `lexic/codegen/gbnf_emitter.py` → `lexic/codegen/gbnf/emitter.py`
- `lexic/utils/escapes.py` → `lexic/codegen/gbnf/escapes.py`
- `lexic/utils/charclass.py` → `lexic/codegen/gbnf/charclass.py`

**Deletes:**
- `LarkBuilder.build_transformer` method (keep the class; `build_grammar` still lives there).
- `CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom` dataclasses.

## IR shape

### Five atoms, all `@dataclass(frozen=True)`

```python
@dataclass(frozen=True)
class LiteralAtom:
    value: str                    # canonical Python string; never becomes a field

@dataclass(frozen=True)
class PatternAtom:
    regex: str                    # canonical Python re, unanchored, canonicalized groups
    source_forms: dict[str, str]  # flavour-shadow map; GbnfParser populates "gbnf"
    min: int
    max: int | None

@dataclass(frozen=True)
class RuleRefAtom:
    rule_name: str
    min: int
    max: int | None

@dataclass(frozen=True)
class AlternationAtom:            # top-level; spec.kind == "alternation"
    arm_rule_names: tuple[str, ...]

@dataclass(frozen=True)
class Arm:
    atoms: tuple["Atom", ...]

@dataclass(frozen=True)
class InlineAlternationAtom:
    arms: tuple[Arm, ...]

Atom = LiteralAtom | PatternAtom | RuleRefAtom | AlternationAtom | InlineAlternationAtom
```

`lexic/ir/__init__.py` re-exports all six names (five atoms + `Arm`) plus `RuleSpec` and `Atom`.

### Migration rules — atom collapse

| Old atom | New atom |
|---|---|
| `CharClassAtom(pattern, min, max)` | `PatternAtom(regex=pattern, source_forms={"gbnf": pattern}, min, max)` |
| `QuantifiedLiteralAtom(value, min, max)` | `PatternAtom(regex=re.escape(value), source_forms={"gbnf": f'"{value}"'}, min, max)` (with GBNF quote re-escaping for the source form) |
| `InlineRegexAtom(regex, gbnf, min, max)` | `PatternAtom(regex=canonicalize_groups(regex), source_forms={"gbnf": gbnf}, min, max)` |

`canonicalize_groups` rewrites any capturing group `(...)` in the parsed regex to `(?:...)`. Implemented via `sre_parse.parse` + a round-trip back to source (stdlib-only). Lives in `lexic/ir/regex_portable.py` alongside `validate_portable` and `features_used` — it is canonical-form territory, consumed by every adapter's parser.

**`source_forms["gbnf"]` scope:** pattern-only, never including the quantifier. The quantifier lives in `min, max` and is re-applied by emission logic. Examples: user wrote `[a-h]+` → `source_forms["gbnf"] == "[a-h]"` (not `"[a-h]+"`); user wrote `"foo"?` → `source_forms["gbnf"] == '"foo"'` (not `'"foo"?'`). Matches the precedent of `InlineRegexAtom.gbnf` today.

**Control-character canonicalization:** when the source contains literal control characters (newline, tab, etc.) inside char classes or literals, `PatternAtom.regex` stores the **escape form** (`"[a-z\\n]"` — two-character sequence), not the literal character. Rationale: Slice C's `BUILTIN_PATTERNS` keys like `r"^[ \t\n]+$"` use escape form; storing literal control characters would break those lookups, and escape-form is the customary way regex text is written. `source_forms["gbnf"]` stores whatever form the user wrote, so round-trip preserves the user's choice.

### Migration rules — `InlineAlternationAtom`

Today, `IRBuilder` / `seq_to_atoms.py` process an inline alt `("a" | "b" | "c")` by:
1. For each arm, synthesize a helper `RuleSpec` (`container-arm1`, `container-arm2`, ...).
2. Register helpers via `HelperRuleRegistry.register`.
3. Emit `InlineAlternationAtom(arm_rule_names=["container-arm1", "container-arm2", "container-arm3"])`.

Slice B replaces this with:
1. For each arm, convert the arm's atoms directly.
2. Emit `InlineAlternationAtom(arms=(Arm((atom,)), Arm((atom,)), Arm((atom,))))`.
3. No helper rules are registered.

Consumers that previously looked up helper-rule specs by name (`lark_builder.py`, `model_emitter.py`, `transformer/registry.py`, `generate.py`) now read `atom.arms[i].atoms` directly.

### Closed-but-versioned dispatch — every consumer gets a `default` raise

Every atom-dispatch table drops its silent fall-through (e.g. `lark_builder.py:83`'s `return '""'`) and raises explicitly:

```python
def dispatch(atom: Atom, ctx: ...) -> ...:
    handler = HANDLER_BY_ATOM.get(type(atom))
    if handler is None:
        raise UnsupportedConstructError(
            f"No handler registered for atom type {type(atom).__name__}"
        )
    return handler(atom, ctx)
```

Sites to update:
- `codegen/lark_builder.py::_atom_to_lark` (currently an `isinstance` chain with `return '""'` fallback).
- `codegen/model_emitter.py` atom dispatch.
- `codegen/gbnf/emitter.py` (formerly `gbnf_emitter.py`) atom dispatch.
- `codegen/transformer/registry.py::BUILDER_BY_ATOM` dispatch (already has an implicit `KeyError`; make it explicit via wrapping function).
- `generate.py` atom dispatch.

## Flavour seam

### `codegen/flavours.py` — protocols and registry

```python
from typing import Protocol
from lexic.ir import RuleSpec

class FlavourParser(Protocol):
    def parse(self, text: str) -> list[RuleSpec]: ...

class FlavourEmitter(Protocol):
    supports: frozenset[str]                    # ⊆ PORTABLE_FEATURES
    def emit(self, specs: list[RuleSpec]) -> str: ...

class FlavourAdapter(Protocol):
    name: str
    extensions: tuple[str, ...]
    parser: FlavourParser
    emitter: FlavourEmitter


ADAPTERS: dict[str, FlavourAdapter] = {}

def register_adapter(adapter: FlavourAdapter) -> None:
    ADAPTERS[adapter.name] = adapter

def get_adapter(flavour: str) -> FlavourAdapter:
    try:
        return ADAPTERS[flavour]
    except KeyError:
        raise UnsupportedConstructError(
            f"Unknown flavour: {flavour!r}. Supported: {sorted(ADAPTERS)}"
        ) from None

def adapter_for_extension(path: str | Path) -> FlavourAdapter:
    """Find the adapter whose .extensions include this path's suffix."""
    suffix = Path(path).suffix
    for adapter in ADAPTERS.values():
        if suffix in adapter.extensions:
            return adapter
    raise UnsupportedConstructError(
        f"No flavour adapter registered for extension {suffix!r}. "
        f"Supported: {[ext for a in ADAPTERS.values() for ext in a.extensions]}"
    )
```

### `codegen/gbnf/adapter.py`

```python
class GbnfAdapter:
    name = "gbnf"
    extensions = (".gbnf",)

    def __init__(self) -> None:
        self.parser = GbnfParser()
        self.emitter = GbnfEmitter()
```

Registration lives in `codegen/flavours.py` itself — the module eagerly imports `lexic.codegen.gbnf.adapter` at module load and calls `register_adapter(GbnfAdapter())`. `codegen/gbnf/__init__.py` is a pure re-export with no side effects. This guarantees that `from lexic.codegen.flavours import get_adapter` returns a populated registry regardless of whether the caller also imported `lexic.codegen`.

### Public API surface

```python
# codegen/__init__.py
def codegen(
    text: str, *, stem: str = "grammar", flavour: str = "gbnf"
) -> dict[str, type[GrammarModel]]: ...

def build_classes_and_specs(
    text: str, *, stem: str, flavour: str = "gbnf"
) -> tuple[dict[str, type], dict[str, RuleSpec]]: ...

def codegen_from_path(
    path: str | Path, *, flavour: str | None = None
) -> dict[str, type[GrammarModel]]: ...
# codegen_from_path infers flavour from extension via adapter_for_extension() when None

# compile.py
def compile(
    text: str, *, cache_key: Hashable, flavour: str = "gbnf"
) -> CompiledGrammar: ...

def compile_from_path(
    path: str | Path, *, flavour: str | None = None
) -> CompiledGrammar: ...

# base.py
class GrammarModel:
    def to_grammar(self, flavour: str = "gbnf") -> str: ...
    def to_gbnf(self) -> str:
        return self.to_grammar("gbnf")
```

Unknown flavour → `UnsupportedConstructError` (via `get_adapter`). `to_gbnf()` stays as a two-line alias indefinitely (no deprecation warning, no cost).

### Cross-check at codegen time

In `codegen.__init__.codegen()` (and `build_classes_and_specs`), after parse and before emit:

```python
for spec in specs:
    for atom in walk_atoms(spec):
        if isinstance(atom, PatternAtom):
            validate_portable(atom.regex)
            missing = features_used(atom.regex) - adapter.emitter.supports
            if missing:
                raise UnsupportedConstructError(
                    f"Pattern {atom.regex!r} in rule {spec.rule_name!r} "
                    f"uses features {sorted(missing)} not supported by "
                    f"{adapter.name!r} emitter"
                )
```

`walk_atoms` is a generator that descends into `InlineAlternationAtom.arms[*].atoms` recursively so nested patterns are checked too.

## Portable regex module

### `lexic/ir/regex_portable.py`

```python
PORTABLE_FEATURES: frozenset[str] = frozenset({
    "literal",              # plain character matching
    "char_class",           # [a-z], [abc]
    "negated_class",        # [^abc]
    "shorthand",            # \d \w \s \D \W \S
    "quantifier",           # ?, +, *, {m,n}, {m,}, {n}
    "alternation",          # |
    "non_capturing_group",  # (?:...)
    "unicode_escape",       # \xNN, \uNNNN, \UNNNNNNNN
})

def validate_portable(regex: str) -> None:
    """Raise UnsupportedConstructError if regex uses non-CFG features.

    Forbidden: anchors (^, $, \\A, \\Z), lookarounds ((?=...), (?!...), (?<=...), (?<!...)),
    backrefs (\\1 ... \\9, \\g<name>), inline flags ((?i), (?m), etc.),
    capturing groups (...) (must be (?:...)), word boundaries \\b \\B, any-char `.`.
    """

def features_used(regex: str) -> frozenset[str]:
    """Return the PORTABLE_FEATURES subset this regex uses.

    Precondition: regex has been validated via validate_portable().
    """
```

Implementation walks `re.sre_parse.parse(regex)`'s tree. No hand-rolled regex parsing. Lives in `lexic/ir/` because it's an IR-contract concern (the allowed shape of `PatternAtom.regex`), not a codegen concern.

### GBNF `supports` set

```python
# codegen/gbnf/emitter.py
class GbnfEmitter:
    supports = frozenset({
        "literal",
        "char_class",
        "negated_class",
        "quantifier",
        "alternation",
        "non_capturing_group",
        "unicode_escape",
    })
    # Notably absent: "shorthand". GbnfParser lowers \d \w \s to char classes
    # at parse time, so GBNF-parsed IR never carries shorthand.
```

## `source_forms` contract

### Semantics
- Keys are flavour names (`"gbnf"`, future `"abnf"`).
- Values are the source-form rendering for that flavour — either verbatim from user input (when set by a parser) or canonically reconstructed (when set by an emitter fallback, though emitters don't typically write back to `source_forms`).
- Map is never `None`; missing key means "no source form recorded for this flavour".

### Population
- `GbnfParser.parse()` sets `source_forms["gbnf"]` on every `PatternAtom` it constructs — the exact bracket expression, quoted literal (with quotes), or inline group expression as it appeared in the user's text.
- Future adapters for flavours we do not support today do not populate anything.
- IR-constructed atoms (future `@grammar_rule` decorator, out of scope here) start with `source_forms = {}`.

### Emission
- `GbnfEmitter.emit()` asks each `PatternAtom`: is `source_forms["gbnf"]` present? If yes, emit it verbatim (then append the quantifier from `min, max`). If no, the reconstruction fallback runs.
- **Slice B fallback implementation:** a stub that raises `NotImplementedError("regex→GBNF reconstruction is Slice D scope, when @grammar_rule first produces IR-constructed atoms without source_forms")`. A unit test asserts the stub raises on an atom with empty `source_forms`. When Slice D needs it, the failing test is the implementation trigger.
- **Invariant:** `GbnfEmitter` never reads any key other than `"gbnf"`.

### Round-trip guarantee
`parse(text).to_text()` preserves pattern source rendering for parsed input (via `source_forms["gbnf"]`). This is the pattern-syntax analogue of Slice C's planned `_raw` field (which handles whitespace). Slice B lays the plumbing; Slice C wires the end-to-end test when `_raw` lands.

## Token reservation

### Detection

`GbnfParser.parse()` runs a pre-tokenisation scan on the raw source text **before** any rule parsing. A single regex pass locates GBNF token syntax; any match raises.

| Pattern | Error | Message template |
|---|---|---|
| `<name>`, `<[N]>`, `!<name>` | `UnsupportedConstructError` | `f"GBNF tokens ({match!r}) at line {n} are not supported. Tokens are a reserved construct."` |

Detection is on the source text, not the AST, so tokens can never be constructed as atoms.

### Error origin

Errors are raised from `GbnfParser.parse()` (not from `GbnfAdapter` or a higher wrapper). Tests can exercise the parser directly without going through `codegen()`.

## Testing strategy

### Phase 1 (scaffolding) — no behaviour change

- All 414 existing tests green.
- New `tests/unit/lexic/codegen/test_flavours.py`:
  - `get_adapter("gbnf")` returns the registered adapter.
  - `get_adapter("abnf")` raises `UnsupportedConstructError` with `"Supported: ['gbnf']"` in the message.
  - `adapter_for_extension("foo.gbnf")` returns the GBNF adapter.
  - `adapter_for_extension("foo.abnf")` raises `UnsupportedConstructError`.

### Phase 2 (atom collapse) — behaviour-preserving for GBNF

- All 414 existing tests green.
- Seven ground-truth grammars in `resources/ground_truth/` regenerate into `generated/*.py` identically to pre-Phase-2 modulo the atom-type renames in the emitted `__grammar__` literals. Property round-trips on all seven still green.
- New `tests/unit/lexic/ir/test_regex_portable.py`:
  - Every entry in `PORTABLE_FEATURES` has a positive case: a sample regex that parses, validates, and is reported by `features_used`.
  - Every forbidden construct has a negative case that `validate_portable` rejects with `UnsupportedConstructError` naming the offending feature.
- New `tests/unit/lexic/ir/test_atom_shapes.py`:
  - `PatternAtom`, `Arm`, `InlineAlternationAtom`, and all other atom types are frozen (write attempts raise `FrozenInstanceError`).
  - `Arm.atoms` is a `tuple`, not a `list`.
  - `source_forms={}` equality works correctly.
  - `tuple` vs `list` in `arms` doesn't break pickling / `dataclasses.replace`.
- New `tests/unit/lexic/codegen/gbnf/test_parser.py` (relocated + expanded from current `tests/unit/lexic/codegen/test_parser.py`):
  - Parses each ground-truth grammar.
  - Asserts `source_forms["gbnf"]` is populated pattern-only (no quantifier) on every `PatternAtom`: user wrote `[a-h]+` → `source_forms["gbnf"] == "[a-h]"`; user wrote `"foo"?` → `source_forms["gbnf"] == '"foo"'`.
  - Asserts `LiteralAtom.value` is canonical Python (GBNF escapes decoded into real characters); `PatternAtom.regex` uses **escape form** for control characters (user wrote `[a-z\n]` → `regex == "[a-z\\n]"`).
  - Asserts the regex→GBNF reconstruction fallback in `GbnfEmitter` raises `NotImplementedError` for an atom with empty `source_forms` (confirms stub is in place for Slice D).
- New `tests/integration/test_source_forms_roundtrip.py`:
  - For each ground-truth grammar: parse, walk all `PatternAtom`s, emit via `GbnfEmitter.emit()`, confirm the emitted text matches source-form entries where present.
- Updated existing tests that construct atoms by name: `CharClassAtom(...)` → `PatternAtom(regex=..., source_forms={}, ...)` etc. These are mechanical edits.

### Phase 3 (token reservation)

- New `tests/integration/test_token_reservation.py`:
  - Grammar containing `<think>` → `UnsupportedConstructError` with `"GBNF tokens"` in the message and the quoted fragment.
  - Grammar containing `<[42]>` → same error.
  - Grammar containing `!<name>` → same error.
  - Each assertion checks error class, line-number presence in message, and the offending fragment quoted.

### Regression protection

- `uv run pytest tests/ -q` must pass at the end of each phase commit — the tree is green at every commit boundary.
- `uv run ruff check src/ tests/` must pass at the end of each phase commit.

## Non-goals (explicit)

Carried from roadmap, restated to prevent scope creep:

- No ABNF/EBNF parsing or emission. `flavour=` accepts only `"gbnf"`.
- No `TokenAtom` in the IR. Tokens only reserve raises.
- No generated-code shape changes. `ModelEmitter` still emits today's field types over the merged atoms.
- No `@grammar_rule` decorator (Slice D).
- No four-tier naming cascade (Slice C).
- No `_raw` field, no `Annotated[str, StringConstraints(...)]` emission (Slice C).
- No `portable=False` escape hatch (left open per `2_ARCHITECTURE.md`).
- No changes to `utils/quantifiers.py`, `utils/names.py`, `codegen/classify.py`, `codegen/helpers.py`, `codegen/ir_builder.py` orchestration beyond the atom-type renames required by the collapse.
- No changes to `TokenAmbiguityError` behaviour — class is removed entirely (D5).

## Per-phase structure

Three phases, landing as three commits inside one PR titled `Slice B: PatternAtom + Tier 2.5 + token reservation`.

### Phase 1 — Scaffolding (behaviour-preserving)

All changes that don't touch atom shapes or parser behaviour:

- Create `lexic/exceptions.py` with four error classes.
- Create `lexic/ir/regex_portable.py` with `PORTABLE_FEATURES`, `validate_portable`, `features_used`.
- Create `lexic/codegen/flavours.py` with three protocols, `ADAPTERS`, `register_adapter`, `get_adapter`, `adapter_for_extension`, **and an eager import of `lexic.codegen.gbnf.adapter` with `register_adapter(GbnfAdapter())` at module load**.
- `git mv` five files into `codegen/gbnf/` (parser, ast, emitter, escapes, charclass).
- Create `codegen/gbnf/__init__.py` (pure re-export, no side effects), `codegen/gbnf/adapter.py`. Wrap `GbnfParser` and `GbnfEmitter` as classes implementing their protocols (currently module-level functions).
- Add `GbnfEmitter.supports` frozenset.
- Add `flavour="gbnf"` parameter to `codegen()`, `build_classes_and_specs()`, `compile()`, `GrammarModel.to_grammar()`. `to_gbnf()` becomes a two-line alias.
- `codegen_from_path()` and `compile_from_path()` infer flavour from extension when `flavour=None`.
- Delete `LarkBuilder.build_transformer`; update two call sites.
- Freeze all atom dataclasses (`frozen=True`).
- Update `2_ARCHITECTURE.md`: drop `TokenAmbiguityError` from the error-vocabulary table; drop the `<<name>>` case from §Token reservation.
- Update `3_ROADMAP.md` §Slice B: drop the `<<name>>` bullet from scope and the corresponding exit-criteria line.

Phase 1 ends green on 414 tests + new `test_flavours.py`.

### Phase 2 — Atom collapse (behaviour-preserving for GBNF)

All atom-shape changes and their consumer updates:

- `lexic/ir/atoms.py`: remove `CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom`. Add `PatternAtom`, `Arm`. Reshape `InlineAlternationAtom.arms` to `tuple[Arm, ...]`. Reshape `AlternationAtom.arm_rule_names` to `tuple[str, ...]` (list → tuple for genuine frozenness).
- `lexic/ir/regex_portable.py`: add `canonicalize_groups(regex: str) -> str` alongside `validate_portable` and `features_used`. Rewrites any capturing group `(...)` to `(?:...)` via `sre_parse` round-trip.
- `lexic/ir/__init__.py`: update re-exports.
- `codegen/ir_builder.py`: atom construction produces `PatternAtom` where the three old types applied.
- `codegen/seq_to_atoms.py`: inline-alt path produces `InlineAlternationAtom(arms=tuple(Arm(tuple(atoms_for_arm))))` directly, without helper-rule synthesis. Quantified-list helpers continue to use `HelperRuleRegistry`.
- `codegen/gbnf/parser.py` (`GbnfParser.parse`): populate `source_forms["gbnf"]` on every `PatternAtom`. Lower shorthand `\d \w \s` into char classes at parse time. Decode GBNF escapes into canonical Python values in `LiteralAtom.value` and `PatternAtom.regex`.
- `codegen/gbnf/emitter.py` (`GbnfEmitter.emit`): read `source_forms["gbnf"]` first, fall back to reconstructing from `regex`. Single `PatternAtom` dispatch branch. Explicit `default`-raise.
- `codegen/lark_builder.py::_atom_to_lark`: collapse three `isinstance` branches into one `PatternAtom` branch. Handle new `InlineAlternationAtom.arms` by emitting a Lark alternation over inline atom sequences. Remove the `return '""'` fallback; replace with `UnsupportedConstructError`. Remove `decode_gbnf_escapes` usage (no longer needed — `LiteralAtom.value` is already decoded).
- `codegen/model_emitter.py`: single `PatternAtom` dispatch. Update `InlineAlternationAtom` emission to descend into arm atoms. Explicit `default`-raise.
- `codegen/transformer/registry.py` and `codegen/transformer/builders.py`: merge three builders into one `PatternFieldBuilder`. Update `InlineAlternationBuilder` to descend into `Arm.atoms`. Explicit `default`-raise in the dispatch wrapper.
- `generate.py`: single `PatternAtom` sampling branch. Replace GBNF bracket-parsing (`utils.charclass`) with Python-regex-aware sampling (one of: stdlib `sre_parse` walk, `hypothesis.strategies.from_regex`, or a minimal handwritten sampler). Update `InlineAlternationAtom` handling for new `arms` shape. Explicit `default`-raise.
- `codegen/naming.py`: handle new `InlineAlternationAtom.arms` shape when assigning field names.
- Add codegen-time `validate_portable` + emitter-supports cross-check in `codegen.__init__`.
- Regenerate seven ground-truth grammars; diff should show only atom-type renames and `source_forms={}` additions.
- New test files land: `test_regex_portable.py`, `test_atom_shapes.py`, `tests/unit/lexic/codegen/gbnf/test_parser.py`, `test_source_forms_roundtrip.py`.
- Existing tests that construct atoms by the old names are mechanically updated.

Phase 2 ends green on all tests.

### Phase 3 — Token reservation

- `codegen/gbnf/parser.py::GbnfParser.parse`: add pre-tokenisation regex scan for `<name>`, `<[N]>`, `!<name>`; raise `UnsupportedConstructError` on any match.
- New `tests/integration/test_token_reservation.py`.

Phase 3 ends green on all tests.

## Per-phase exit criteria

### Phase 1

- [ ] `lexic/exceptions.py` exists with four error classes.
- [ ] `lexic/ir/regex_portable.py` exists with `PORTABLE_FEATURES`, `validate_portable`, `features_used`.
- [ ] `lexic/codegen/flavours.py` exists with three protocols + registry.
- [ ] `lexic/codegen/gbnf/` package exists; `parser.py`, `ast.py`, `emitter.py`, `escapes.py`, `charclass.py` live inside it (via `git mv`, so history follows).
- [ ] `lexic/codegen/gbnf/adapter.py::GbnfAdapter` exists and self-registers on import.
- [ ] `lexic/utils/escapes.py` and `lexic/utils/charclass.py` no longer exist.
- [ ] `lexic/codegen/parser.py`, `lexic/codegen/ast.py`, `lexic/codegen/gbnf_emitter.py` no longer exist.
- [ ] `codegen(flavour="gbnf")` works; `codegen(flavour="abnf")` raises `UnsupportedConstructError`.
- [ ] `GrammarModel.to_grammar("gbnf")` works; `to_gbnf()` is a two-line alias.
- [ ] `LarkBuilder.build_transformer` method removed; two callers updated.
- [ ] All atom dataclasses frozen.
- [ ] `2_ARCHITECTURE.md` and `3_ROADMAP.md` updated to drop `<<name>>` / `TokenAmbiguityError` references.
- [ ] All 414 existing tests green; `test_flavours.py` green.
- [ ] `uv run ruff check src/ tests/` clean.

### Phase 2

- [ ] Five atom types in `lexic.ir`: `LiteralAtom`, `PatternAtom`, `RuleRefAtom`, `AlternationAtom`, `InlineAlternationAtom`. `Arm` also exported.
- [ ] `CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom` removed.
- [ ] `InlineAlternationAtom.arms: tuple[Arm, ...]`; no helper-rule synthesis for inline alts.
- [ ] Seven ground-truth grammars regenerate identically modulo atom-type renames and `source_forms={...}` additions.
- [ ] Property round-trips green on all seven grammars.
- [ ] `source_forms["gbnf"]` populated on every `PatternAtom` produced by `GbnfParser`.
- [ ] `generate.py`, `lark_builder.py`, `model_emitter.py`, `transformer/registry.py`, `codegen/gbnf/emitter.py` each have a single `PatternAtom` branch where they used to have three.
- [ ] Every atom dispatch has an explicit `default` raise of `UnsupportedConstructError`.
- [ ] Codegen-time `validate_portable` + emitter-supports cross-check in place.
- [ ] New test files green: `test_regex_portable.py`, `test_atom_shapes.py`, `tests/unit/lexic/codegen/gbnf/test_parser.py`, `test_source_forms_roundtrip.py`.
- [ ] All existing tests still green.
- [ ] `uv run ruff check src/ tests/` clean.

### Phase 3

- [ ] `GbnfParser.parse` raises `UnsupportedConstructError` on `<name>`, `<[N]>`, `!<name>` before any atom construction.
- [ ] `tests/integration/test_token_reservation.py` green.
- [ ] All existing tests still green.
- [ ] `uv run ruff check src/ tests/` clean.

## Doc updates bundled into Slice B

- `prototyping/next/2_ARCHITECTURE.md`:
  - §Error vocabulary: remove the `TokenAmbiguityError` row.
  - §Token reservation: remove the `TokenAmbiguityError` bullet and the `<<name>>` description.
- `prototyping/next/3_ROADMAP.md` §Slice B:
  - Scope: remove the `<<name>>` / `TokenAmbiguityError` bullet under "Token reservation".
  - Exit criteria: remove the `<<name>>` assertion line.
  - Open questions: strike-through the four resolved questions (matching the Slice A doc's convention).
- `CLAUDE.md`: update the "Seven frozen Atom dataclasses" → "Five frozen Atom dataclasses" line; update the IR overview to reflect `PatternAtom` + `Arm` + reshaped `InlineAlternationAtom`; mention `codegen/gbnf/` layout; mention `flavour=` parameter.

## Implementation notes

- User may implement parts of `src/` manually; spec is authoritative and tests are the contract. When the plan lands, agent tasks focus on test authoring, source-form population audits, and consumer-update fixups that can be done mechanically against this spec.
- Phases commit separately inside one PR; each commit must leave the tree green on tests and ruff.
- `git mv` for the five file moves (preserves history).
- No `--no-verify`, no hook skips, no amends to published commits.
