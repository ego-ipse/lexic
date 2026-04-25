# Slice B.5 — Package restructure: canonical IR + generic algorithms + thin flavour adapters

**Date:** 2026-04-25
**Status:** Approved (brainstormed)
**Supersedes:** `docs/superpowers/specs/2026-04-24-slice-b5-package-restructure-design.md`
**Implementation plan:** `docs/superpowers/plans/2026-04-25-slice-b5-package-restructure.md` (to be written)
**Roadmap entry:** `prototyping/next/3_ROADMAP.md` §Slice B.5
**Inserts before:** Slice B Phase 2 (atom collapse)

## Background

The 2026-04-24 spec (call it v1) defined a package restructure that moved files but kept the abstraction lazy: classifier, converter, naming hints, and IR-construction algorithms remained in `grammars/gbnf/` because they happened to import GBNF AST. The IR carried flavour text directly (`InlineRegexAtom.gbnf: str`, raw GBNF bracket strings in `CharClassAtom.pattern`, GBNF-escaped `LiteralAtom.value`). Three `if rule_name == "ws"` special cases were declared "out of slice" because they were string uses, not imports.

Critique on review:
1. Algorithms that are flavour-agnostic ended up in `grammars/gbnf/` — the abstraction was the file path, not the code.
2. Bad code (dead parameters, classes wrapping single functions, emit-time logic in the converter) was being moved verbatim.
3. The IR was not a flavour-agnostic pivot — translation between flavours would require a rewrite.

This spec rethinks the architecture with three commitments:

- **Canonical IR.** Atoms carry no flavour text. Every per-flavour escape, bracket form, or quantifier syntax is encoded on emit and decoded on parse. The IR is a true interchange.
- **Generic algorithms in core, syntax constants and AST-shape queries in the flavour.** The `FlavourEmitter`, `FlavourParser`, classifier, and converter algorithms live in `ir/` and consume small flavour-specific seams via Protocols and class attributes. Each flavour package contains only what is genuinely per-flavour.
- **Open atom set with adapter-bound handlers.** New atom types are added by a flavour without modifying core; consumer-side handlers (codegen, lark, transform, runtime) are passed via the adapter at construction time.

Translation between flavours is **not implemented** in this slice. The architecture must, however, make translation a mechanical follow-up rather than a rewrite.

## Architectural principles

**P1. Canonical IR.** Every atom field has a single canonical form. `LiteralAtom.value` is a Python string with all escapes already decoded. `CharClassAtom.pattern` is a POSIX-style bracket string (`[0-9]`, `[a-zA-Z_]`, `[^abc]`). Quantifiers are stored as `(min: int, max: int | None)` pairs, not syntax characters. No atom field carries flavour text.

**P2. Open atom set.** `Atom` is a `Protocol` (marker), not a closed `Union`. Core ships canonical concrete atoms as frozen dataclasses. A flavour that needs new atoms (e.g. Lark `LookaheadAtom`) defines its own dataclasses next to its adapter and registers handlers; no edit to core required.

**P3. Generic algorithms, narrow seams.** The classifier algorithm, converter algorithm, IRBuilder, naming policy, helper-rule registry, topological sort, and the `FlavourEmitter` base class all live in `ir/`. Flavours supply: a parser (text → `list[RuleSpec]`), AST-shape queries (`RuleClassifier[Node]`, `SequenceConverter[Node]`), syntax constants (`rule_separator`, `quote_char`, etc.), an escape codec, and atom handler tables.

**P4. Adapter-bound dispatch.** No global handler registries. Each consumer (`ModelEmitter`, `LarkBuilder`, `build_transformer`, `GrammarModel.to_text`) takes its handler table at construction time. Canonical defaults live next to the consumer; flavour extensions merge in via the adapter.

**P5. Capability declarations.** Each flavour's `supports: frozenset[str]` enumerates what it can emit. Translation (future) validates source-atom-set ⊆ target-supported-atoms before attempting.

**P6. Lookup-at-call-time on `GrammarModel`.** Generated modules carry a module-level `__adapter__` reference. `to_text()` and `to_grammar()` look up handlers via `self.__adapter__` at call time. No per-class `ClassVar` boilerplate.

## IR design (canonical)

`src/lexic/ir/atoms.py`:

```python
from typing import Protocol, runtime_checkable
from dataclasses import dataclass

@runtime_checkable
class Atom(Protocol):
    """Marker protocol for IR atoms. Concrete atoms are frozen dataclasses.
    Atoms with bounded repetition expose `min: int` and `max: int | None`.
    """

@dataclass(frozen=True)
class LiteralAtom:
    value: str  # canonical Python string — all escapes decoded

@dataclass(frozen=True)
class CharClassAtom:
    pattern: str  # POSIX-style bracket: "[0-9]", "[a-zA-Z_]", "[^abc]"
    min: int
    max: int | None

@dataclass(frozen=True)
class QuantifiedLiteralAtom:
    value: str  # canonical
    min: int
    max: int | None

@dataclass(frozen=True)
class InlineRegexAtom:
    canonical: str  # canonical regex form. NO `gbnf` field.
    min: int
    max: int | None

@dataclass(frozen=True)
class RuleRefAtom:
    rule_name: str
    min: int
    max: int | None

@dataclass(frozen=True)
class AlternationAtom:
    arm_rule_names: list[str]

@dataclass(frozen=True)
class InlineAlternationAtom:
    arm_rule_names: list[str]
```

**Canonical char-class form (B1):** POSIX-style bracket strings. Today's GBNF strings already match. Translation to Lark/EBNF/ANTLR is mechanical (escape `/` for Lark, etc.). A structural representation (list of ranges + flags) is deferred to a future slice; this design does not preclude it.

**No flavour leak:** `InlineRegexAtom.gbnf` is removed. The atom carries a single canonical regex form; per-flavour emitters translate as they emit.

**RuleSpec changes:**

```python
@dataclass
class RuleSpec:
    rule_name: str
    class_name: str
    parent_class_name: str
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[Atom]
    field_map: dict[str, int]
    non_semantic_fields: frozenset[str] = frozenset()  # NEW
```

`non_semantic_fields` is populated by IRBuilder with field names whose atom is a `RuleRefAtom` pointing to a rule the flavour considers trivia (in GBNF: `"ws"`). `GrammarModel.semantic_dump` consults this attribute instead of doing a string match. This centralises the `"ws"` convention to one site (IRBuilder).

## Protocols (`ir/protocols.py`)

Type-only Protocols and handler aliases. No concrete code.

```python
from typing import Callable, Generic, Literal, Protocol, TypeVar
from lexic.ir.atoms import Atom
from lexic.ir.spec import RuleSpec

Node = TypeVar("Node")


class RuleClassifier(Protocol[Node]):
    """AST-shape queries on a single rule node."""
    def rule_name(self, rule: Node) -> str: ...
    def is_start_rule(self, rule: Node) -> bool: ...
    def kind(self, rule: Node) -> Literal["sequence", "alternation", "value_str"]: ...
    def alternation_arm_nodes(self, rule: Node) -> list[Node]: ...
    def sequence_body(self, rule: Node) -> Node: ...
    def value_str_body(self, rule: Node) -> Node: ...
    def single_ruleref(self, arm: Node) -> str | None: ...


class SequenceConverter(Protocol[Node]):
    """AST → Atom conversion (per-flavour AST shape, canonical Atom output)."""
    def value_str_atoms(self, body: Node) -> list[Atom]: ...
    def sequence_atoms(
        self,
        body: Node,
        parent_class_name: str,
        helpers: "HelperRuleRegistry",
    ) -> list[Atom]: ...


class FlavourParser(Protocol):
    """text → list[RuleSpec]. AST is package-internal."""
    def parse(self, text: str) -> list[RuleSpec]: ...


class EscapeCodec(Protocol):
    """Canonical Python ↔ flavour-text escape conversion."""
    def encode(self, value: str) -> str: ...   # canonical → flavour text
    def decode(self, source: str) -> str: ...  # flavour text → canonical


# Handler type aliases — one per consumer.
AtomEmitHandler = Callable[[Atom, "FlavourEmitter"], str]
FieldHandler = Callable[[Atom, "ModelEmitContext"], "FieldDef"]
LarkHandler = Callable[[Atom, "LarkContext"], str]
TransformHandler = Callable[[Atom, "TransformContext"], object]
ToTextHandler = Callable[[Atom, "ToTextContext"], str]


class FlavourAdapter(Protocol):
    parser: FlavourParser
    emitter: "FlavourEmitter"
    escapes: EscapeCodec
    supports: frozenset[str]

    # Atom handler extensions. Empty dicts for flavours using only canonical atoms.
    field_handlers: dict[type, FieldHandler]
    lark_handlers: dict[type, LarkHandler]
    transform_handlers: dict[type, TransformHandler]
    to_text_handlers: dict[type, ToTextHandler]
```

## Generic algorithms

### `ir/builder.py` — IRBuilder

Class with overridable methods. Generic over `Node`. Subclass to override; default implementation is what GBNF needs.

```python
class IRBuilder(Generic[Node]):
    def __init__(
        self,
        classifier: RuleClassifier[Node],
        converter: SequenceConverter[Node],
        *,
        helpers: HelperRuleRegistry | None = None,
        field_namer: FieldNamer | None = None,
        trivia_rules: frozenset[str] = frozenset({"ws"}),
    ): ...

    def build(self, rules: list[Node]) -> list[RuleSpec]:
        """Build specs in topological order; start rule first."""

    # Overridable steps
    def _compute_parents(self, rules: list[Node]) -> dict[str, str]: ...
    def _build_rule(self, rule: Node, parents: dict[str, str]) -> list[RuleSpec]: ...
    def _build_value_str(self, rule, parents) -> list[RuleSpec]: ...
    def _build_named_alt(self, rule, parents) -> list[RuleSpec]: ...
    def _build_sequence(self, rule, parents) -> list[RuleSpec]: ...
    def _topo_sort(self, specs: list[RuleSpec]) -> list[RuleSpec]: ...
    def _set_trivia_min_zero(self, atoms: list[Atom]) -> list[Atom]: ...
    def _mark_non_semantic_fields(self, spec: RuleSpec) -> RuleSpec: ...
```

`trivia_rules` parameter generalises the `"ws"` hardcode. IRBuilder sets `min=0` on every `RuleRefAtom` whose `rule_name` is in `trivia_rules`, and populates `RuleSpec.non_semantic_fields` for fields pointing to trivia rules.

### `ir/classify.py` — generic classification

```python
def classify_rule(rule: Node, classifier: RuleClassifier[Node]) -> Classification: ...
```

The classification algorithm (today's `_is_structurally_complex`, paired-arm walk, `PureLiteralAlt` detection) lives here. Flavour AST-shape queries come through the `RuleClassifier` protocol.

### `ir/convert.py` — generic conversion

The converter algorithm walks atom items via the `SequenceConverter` protocol. Helper-rule synthesis and group-inlining decisions live here as generic logic; per-flavour atom-from-AST handlers come through `SequenceConverter.sequence_atoms`.

### `ir/emit.py` — `FlavourEmitter` ABC

```python
class FlavourEmitter(ABC):
    # Syntax constants — subclass overrides where it differs.
    rule_separator: str = "::="
    rule_terminator: str = ""
    alt_separator: str  = " | "
    quote_char: str     = '"'
    group_open: str     = "("
    group_close: str    = ")"
    empty_body: str     = '""'

    # Decorators — flavour-tunable; sensible defaults.
    def quote(self, v: str) -> str:
        return f"{self.quote_char}{self.encode(v)}{self.quote_char}"
    def wrap_group(self, body: str) -> str:
        return f"{self.group_open}{body}{self.group_close}"
    def format_quantifier(self, lo: int, hi: int | None) -> str:
        return bounds_to_quantifier(lo, hi)  # default: ?, +, *, {m,n}
    def render_charclass(self, canon: str) -> str:
        return canon  # default: canonical pattern is the flavour pattern
    def render_inline_regex(self, canon: str) -> str:
        return canon  # default: canonical regex is the flavour regex; override per flavour
    def encode(self, v: str) -> str:
        return self._escapes.encode(v)

    @property
    @abstractmethod
    def supports(self) -> frozenset[str]: ...

    # Default canonical-atom handlers, parameterised by decorators.
    DEFAULT_HANDLERS: ClassVar[dict[type, AtomEmitHandler]] = {
        LiteralAtom:           lambda a, e: e.quote(a.value),
        QuantifiedLiteralAtom: lambda a, e: e.quote(a.value)
                                          + e.format_quantifier(a.min, a.max),
        CharClassAtom:         lambda a, e: e.render_charclass(a.pattern)
                                          + e.format_quantifier(a.min, a.max),
        RuleRefAtom:           lambda a, e: a.rule_name
                                          + e.format_quantifier(a.min, a.max),
        AlternationAtom:       lambda a, e: e.alt_separator.join(a.arm_rule_names),
        InlineAlternationAtom: lambda a, e: e.wrap_group(
                                              e.alt_separator.join(a.arm_rule_names)),
        InlineRegexAtom:       lambda a, e: e.render_inline_regex(a.canonical)
                                          + e.format_quantifier(a.min, a.max),
    }

    def __init__(self, escapes: EscapeCodec,
                 handlers: dict[type, AtomEmitHandler] | None = None):
        self._escapes = escapes
        self._handlers = handlers or dict(self.DEFAULT_HANDLERS)

    # Generic algorithms — owned here; never overridden in flavour subclasses.
    def emit(self, specs: list[RuleSpec]) -> str: ...
    def emit_rule(self, spec: RuleSpec) -> str: ...
    def _emit_body(self, spec: RuleSpec) -> str: ...
    def _render_atom(self, atom: Atom) -> str: ...
```

A flavour subclass declares syntax constants, registers its escape codec, and optionally overrides `render_charclass` / `render_inline_regex` if its char-class or regex syntax differs from POSIX.

## Package layout

```
src/lexic/
  ir/
    atoms.py         Atom Protocol + canonical concrete dataclasses
    spec.py          RuleSpec (with non_semantic_fields)
    protocols.py     RuleClassifier, SequenceConverter, FlavourParser,
                     EscapeCodec, FlavourAdapter, handler type aliases
    builder.py       IRBuilder
    classify.py      classify_rule (generic algorithm)
    convert.py       generic conversion algorithm
    emit.py          FlavourEmitter ABC + DEFAULT_HANDLERS
    naming.py        assign_field_names + canonical hint tables
                     (CHARCLASS_NAMES, LITERAL_NAMES)
    helpers.py       HelperRuleRegistry
    topo.py          topo_sort(specs, is_start_rule)
    regex_portable.py  (unchanged)

  codegen/
    __init__.py      build_classes_and_specs(text, adapter)
    model_emitter.py ModelEmitter
    handlers/
      __init__.py    re-exports CANONICAL_FIELD_HANDLERS
      atom_fields.py per-canonical-atom field handlers

  parsing/
    __init__.py
    lark_builder.py  LarkBuilder
    transformer.py   build_transformer
    handlers/
      __init__.py    CANONICAL_LARK_HANDLERS, CANONICAL_TRANSFORM_HANDLERS
      lark.py        per-canonical-atom Lark fragment handlers
      transform.py   per-canonical-atom transform handlers

  runtime/
    __init__.py
    base.py          GrammarModel — uses self.__adapter__ at call time
    parse.py         parse(text, grammar_path) — selects adapter via extension
    generate.py      generate(...)
    handlers/
      __init__.py    CANONICAL_TO_TEXT_HANDLERS, CANONICAL_GENERATE_HANDLERS
      to_text.py
      generate.py

  grammars/
    __init__.py      get_adapter, register_adapter, ADAPTERS registry
    flavours.py      (still has the FlavourAdapter Protocol — to be removed
                     once it is replaced by ir/protocols.py)
    gbnf/
      __init__.py    re-exports GbnfAdapter
      adapter.py     GbnfAdapter — wires every seam
      parser.py      Lark grammar for GBNF + transformer; calls IRBuilder
      ast.py         GBNF AST dataclasses (package-internal)
      ast_to_ir.py   GbnfClassifier(RuleClassifier[Rule])
                     + GbnfConverter(SequenceConverter[Rule])
                     + AST predicates (private)
      emit.py        GbnfEmitter — class attrs + render_charclass override
      syntax.py      encode/decode escapes + canonical↔GBNF bracket conversion
      atoms.py       (absent — only if extending atoms)
      handlers.py    (absent — only if extending atoms)
```

`grammars/gbnf/` floor: 7 mandatory files, ~410 lines. None empty.

## Data flow

```
Text in flavour F
   │
   ▼
GbnfAdapter.parser.parse(text)             [grammars/gbnf/parser.py]
   ├─ Lark parse → AST (package-internal)
   ├─ IRBuilder(GbnfClassifier(), GbnfConverter()).build(ast) → list[RuleSpec]
   │     (escapes already decoded; brackets canonicalised)
   ▼
list[RuleSpec]   ◄── canonical IR; crosses the seam

Downstream consumers — pass `adapter` so each can merge its own handlers:
   ModelEmitter(specs, handlers={**CANONICAL_FIELD, **adapter.field_handlers})
       → Python source                   [codegen/]
   LarkBuilder(specs, handlers={**CANONICAL_LARK, **adapter.lark_handlers})
       → Lark grammar string             [parsing/]
   build_transformer(specs, classes, handlers={...})
       → Lark Transformer                [parsing/]
   GbnfAdapter.emitter.emit(specs)
       → GBNF text                       [grammars/gbnf/emit.py]
```

## ws rule handling (decision D2)

All four sites lose their `"ws"` string special case:

1. **`parsing/lark_builder.py:64-65`** (`if atom.rule_name == "ws": return "ws?"`) — removed. IRBuilder sets `min=0` on every `RuleRefAtom` whose `rule_name ∈ trivia_rules`. The generic `RuleRefAtom` Lark handler emits `name?` from the bounds.

2. **`parsing/lark_builder.py:99-105`** (`if spec.rule_name == "ws": continue` + hardcoded `ws : /[ \t\n]+/`) — removed. The Lark `CharClassAtom` handler folds the quantifier *inside* the regex when expressible (`min=1, max=None` → `+`; `min=0, max=None` → `*`; `min=0, max=1` → `?`), producing `/[ \t\n]+/` from the IR's `CharClassAtom("[ \t\n]", 1, None)`. The generic emit produces the same line the special case hardcoded.

3. **`parsing/transformer.py:88-100`** (special `ws_method` + `if spec.rule_name == "ws": continue`) — removed. The generic `value_str` handler builds `Ws(value=text)` if the class exists, else returns the joined text — identical behaviour.

4. **`runtime/base.py:97`** (`if isinstance(atom, RuleRefAtom) and atom.rule_name == "ws"`) — removed. `semantic_dump` uses `RuleSpec.non_semantic_fields` populated by IRBuilder.

The `"ws"` string is now hardcoded in **one** place: `IRBuilder(trivia_rules={"ws"})` default. Future flavours can pass a different set or override the parameter to extend the trivia rule list.

## Runtime adapter binding (decision C2)

Per-module binding. ModelEmitter writes a single `__adapter__ = <adapter expr>` at the top of each generated module:

```python
# generated/arithmetic.py
from lexic.grammars.gbnf.adapter import GbnfAdapter
__adapter__ = GbnfAdapter()

class Expr(GrammarModel):
    __grammar__: ClassVar[RuleSpec] = ...
```

`GrammarModel.to_text` resolves `self.__class__.__module__` → that module's `__adapter__` (cached on first call) and dispatches via `__adapter__.to_text_handlers[type(atom)]`. No per-class boilerplate.

`to_grammar(flavour="gbnf")` continues to use `get_adapter(flavour)` — that path supports cross-flavour emit on demand.

## Translation prerequisites

Translation (parse-A → emit-B) is **not implemented** here. The architecture makes it mechanical:

1. **Capability check.** `set(type(a) for spec in specs for a in spec.items) ⊆ target.supported_atom_types`.
2. **Pivot.** Both sides operate on the canonical IR.
3. **Per-flavour escape and bracket transforms.** Each flavour's `EscapeCodec` and `render_charclass` translate canonical strings to flavour text on emit.

The future `translate()` API will be a one-liner over the existing emitter:

```python
def translate(text: str, source: FlavourAdapter, target: FlavourAdapter) -> str:
    specs = source.parser.parse(text)
    target._validate(specs)  # capability check
    return target.emitter.emit(specs)
```

## Extension points

A flavour that introduces a new atom type (e.g. Lark `LookaheadAtom`):

```python
# grammars/lark/atoms.py
@dataclass(frozen=True)
class LookaheadAtom:
    pattern: str

# grammars/lark/handlers.py
def lookahead_field(atom, ctx):    return SkipField()  # structural; no Pydantic field
def lookahead_lark(atom, ctx):     return f"(?= /{atom.pattern}/ )"
def lookahead_emit(atom, e):       return f"&{atom.pattern}"  # Lark surface syntax
def lookahead_to_text(atom, ctx):  return ""  # zero-width

# grammars/lark/adapter.py
class LarkAdapter:
    field_handlers     = {LookaheadAtom: lookahead_field}
    lark_handlers      = {LookaheadAtom: lookahead_lark}
    to_text_handlers   = {LookaheadAtom: lookahead_to_text}
    transform_handlers = {LookaheadAtom: lambda a, c: c.skip}
    supports = frozenset({"literal", "char_class", "alternation", "quantifier",
                          "non_capturing_group", "lookahead"})

    @cached_property
    def emitter(self) -> FlavourEmitter:
        return LarkEmitter(escapes=self.escapes,
                           handlers={**FlavourEmitter.DEFAULT_HANDLERS,
                                     LookaheadAtom: lookahead_emit})
```

A flavour that overrides existing behaviour (e.g. custom field naming) supplies a different `FieldNamer` to `IRBuilder`. A flavour that lacks an atom (e.g. no inline alternation) simply never produces it from its parser; no work needed in core.

## Cleanups bundled into this slice

These are byproducts of the rethink, not optional cleanups:

- **`Classifier` class → `classify_rule` function** (moved to `ir/classify.py`). One method, no state.
- **Dead parameters dropped.** `seq_to_atoms`'s `name_map` and `parent_of` are forwarded recursively but never read; gone.
- **Emit logic out of converter.** `seq_to_atoms._to_regex` and `_to_gbnf` (lines 37-75) are emit-time concerns. Moved into the respective per-flavour atom emit handlers (Lark and GBNF) and a generic regex-from-canonical helper.
- **Asymmetric protocol fixed.** `value_str_atoms` and `sequence_atoms` both take bodies (not rules); classifier supplies bodies via `value_str_body` / `sequence_body`.
- **`GbnfClassifier` memoised** by `id(rule)` to avoid re-classifying during parent computation.
- **`InlineRegexAtom.gbnf` removed.** Atom carries `canonical` only; emitters translate.
- **Topo sort generalised.** `_topo_sort` consults `classifier.is_start_rule`; the `"root"` hardcode is gone.
- **Backwards-compat alias `GBNFEmitter = GbnfEmitter`** removed (was scheduled for removal at end of Slice B; this slice is the natural site).

## Creates, moves, deletes

**Creates:**
- `src/lexic/ir/protocols.py`
- `src/lexic/ir/builder.py`
- `src/lexic/ir/classify.py`
- `src/lexic/ir/convert.py`
- `src/lexic/ir/emit.py` (new — `FlavourEmitter` ABC)
- `src/lexic/parsing/__init__.py`
- `src/lexic/parsing/handlers/__init__.py`
- `src/lexic/parsing/handlers/lark.py`
- `src/lexic/parsing/handlers/transform.py`
- `src/lexic/codegen/handlers/__init__.py`
- `src/lexic/codegen/handlers/atom_fields.py`
- `src/lexic/runtime/__init__.py`
- `src/lexic/runtime/handlers/__init__.py`
- `src/lexic/runtime/handlers/to_text.py`
- `src/lexic/runtime/handlers/generate.py`
- `src/lexic/grammars/gbnf/ast_to_ir.py` (collapsed classifier + converter)
- `src/lexic/grammars/gbnf/syntax.py` (collapsed escapes + charclass)

**Moves (via `git mv`):**
- `codegen/lark_builder.py` → `parsing/lark_builder.py`
- `codegen/transformer/build_transformer.py` → `parsing/transformer.py`
  (the rest of `codegen/transformer/` — `registry.py`, `builders.py`, `context.py` — folds into `parsing/transformer.py` or `parsing/handlers/transform.py`; see the implementation plan)
- `src/lexic/base.py` → `src/lexic/runtime/base.py`
- `src/lexic/parse.py` → `src/lexic/runtime/parse.py`
- `src/lexic/generate.py` → `src/lexic/runtime/generate.py`
- `src/lexic/grammars/gbnf/escapes.py` content → `src/lexic/grammars/gbnf/syntax.py`
- `src/lexic/grammars/gbnf/charclass.py` content → `src/lexic/grammars/gbnf/syntax.py`
- `src/lexic/grammars/gbnf/emitter.py` → `src/lexic/grammars/gbnf/emit.py` (slimmed)

**Deletes:**
- `src/lexic/codegen/ir_builder.py` (logic absorbed into `ir/builder.py` + `grammars/gbnf/ast_to_ir.py`)
- `src/lexic/codegen/classify.py` (logic absorbed into `ir/classify.py` + `grammars/gbnf/ast_to_ir.py`)
- `src/lexic/codegen/seq_to_atoms.py` (logic absorbed into `ir/convert.py` + `grammars/gbnf/ast_to_ir.py`)
- `src/lexic/codegen/ast_utils.py` (predicates fold into `grammars/gbnf/ast_to_ir.py`)
- `src/lexic/codegen/helpers.py` (moved to `ir/helpers.py`)
- `src/lexic/codegen/naming.py` (moved to `ir/naming.py`; hint tables stay there as canonical)
- `src/lexic/grammars/gbnf/escapes.py` (collapsed into `syntax.py`)
- `src/lexic/grammars/gbnf/charclass.py` (collapsed into `syntax.py`)

**Extractions (content moves, file stays):**
- `_atom_to_lark` body in `parsing/lark_builder.py` → per-canonical-atom handler functions in `parsing/handlers/lark.py`. `LarkBuilder.build_grammar` becomes generic and dispatches via the handler table.
- `_atom_to_gbnf` body in `grammars/gbnf/emit.py` → defaulted via `FlavourEmitter.DEFAULT_HANDLERS`. `GbnfEmitter` keeps only class attrs + `render_charclass` override.
- Field handler logic in `codegen/model_emitter.py` → per-canonical-atom handler functions in `codegen/handlers/atom_fields.py`.
- `to_text` per-atom logic in `runtime/base.py` → per-canonical-atom handler functions in `runtime/handlers/to_text.py`.

## Testing strategy

Pure refactor + IR canonicalisation. All seven ground-truth grammars must round-trip identically; behaviour is unchanged externally.

**New tests:**
- `tests/unit/lexic/ir/test_protocols.py` — `IRBuilder` wired with `GbnfClassifier` + `GbnfConverter` produces specs equal to today's IR (full `RuleSpec ==` equality) for all seven ground-truth grammars.
- `tests/unit/lexic/ir/test_emit.py` — `FlavourEmitter` defaults via a fake test subclass; verifies decorators compose correctly.
- `tests/unit/lexic/ir/test_builder.py` — IRBuilder's overridable steps, trivia handling, non_semantic_fields population.
- `tests/unit/lexic/grammars/gbnf/test_syntax.py` — encode/decode round-trip; canonical↔GBNF bracket conversion.
- `tests/unit/lexic/parsing/test_handlers_lark.py` — canonical Lark handlers on each canonical atom; charclass-quantifier inlining produces `/[ \t\n]+/` from `CharClassAtom("[ \t\n]", 1, None)`.
- **Import-boundary test** (AST-based, not substring): walks the AST of every module under `lexic.parsing` and `lexic.codegen` and asserts no `ImportFrom` node has a module path starting with `lexic.grammars.gbnf`. (And vice versa: `lexic.grammars.gbnf` may not import from `lexic.parsing` or `lexic.codegen`.)
- **Adapter-binding test** — `runtime/test_base.py` verifies `to_text` resolves handlers via `__adapter__` lookup, not via hardcoded `isinstance`.

**Test file moves** (mechanical mirror of source moves; full list deferred to plan).

**Existing tests must remain green at every commit** of the implementation plan.

## Document updates

- **`prototyping/next/3_ROADMAP.md`** — replace the v1 Slice B.5 entry with a pointer to this spec.
- **`prototyping/next/2_ARCHITECTURE.md`** — update target module layout (`runtime/`, `parsing/`, `ir/`, expanded `codegen/`); update layering rules to name the four packages and describe the canonical-IR + adapter-bound-handlers contract.
- **`docs/superpowers/specs/2026-04-23-slice-b-design.md`** — note that Phase 2 (atom collapse) operates on the post-B.5 structure with already-canonical atoms; `InlineRegexAtom.gbnf` removal happens here, not Phase 2.
- **`CLAUDE.md`** — update project layout: `runtime/`, `parsing/`, `ir/` (expanded), revised `codegen/`. Update import-boundary section.

## Exit criteria

**IR & protocols:**
- [ ] `lexic/ir/atoms.py` defines `Atom` as a runtime-checkable Protocol; canonical concrete atoms are frozen dataclasses; `InlineRegexAtom.gbnf` does not exist.
- [ ] `LiteralAtom.value` is a canonical Python string everywhere in the IR pipeline (no `decode_gbnf_escapes` calls outside `grammars/gbnf/`).
- [ ] `CharClassAtom.pattern` is a POSIX-style bracket string everywhere in the IR pipeline.
- [ ] `RuleSpec` has `non_semantic_fields: frozenset[str]`; populated by IRBuilder; consumed by `semantic_dump`.
- [ ] `lexic/ir/protocols.py` declares `RuleClassifier`, `SequenceConverter`, `FlavourParser`, `EscapeCodec`, `FlavourAdapter`, and the five handler type aliases.

**Algorithms:**
- [ ] `lexic/ir/builder.py:IRBuilder` is generic over `Node`; takes `classifier`, `converter`, optional `helpers`/`field_namer`/`trivia_rules`; sets `min=0` on trivia rule refs; populates `non_semantic_fields`.
- [ ] `lexic/ir/classify.py:classify_rule` is a function; the `Classifier` class is gone.
- [ ] `lexic/ir/convert.py` holds the generic conversion algorithm; `seq_to_atoms`'s dead `name_map`/`parent_of` parameters are gone.
- [ ] `lexic/ir/emit.py:FlavourEmitter` is an ABC with `DEFAULT_HANDLERS`, decorator methods, generic `emit`/`emit_rule`/`_emit_body`/`_render_atom`.

**Packages:**
- [ ] `lexic/parsing/`, `lexic/runtime/` exist; `lexic/codegen/handlers/`, `lexic/parsing/handlers/`, `lexic/runtime/handlers/` exist with canonical-atom handler tables.
- [ ] `lexic/codegen/ir_builder.py`, `classify.py`, `seq_to_atoms.py`, `ast_utils.py`, `helpers.py` do not exist.
- [ ] `src/lexic/base.py`, `parse.py`, `generate.py` do not exist (moved to `runtime/`).
- [ ] `grammars/gbnf/escapes.py`, `charclass.py` do not exist (collapsed into `syntax.py`).

**Flavour seam:**
- [ ] `grammars/gbnf/` contains exactly seven mandatory files: `__init__.py`, `adapter.py`, `parser.py`, `ast.py`, `ast_to_ir.py`, `emit.py`, `syntax.py`.
- [ ] `grammars/gbnf/emit.py:GbnfEmitter` is ≤ 30 lines: `supports`, `encode`, `render_charclass`.
- [ ] `grammars/gbnf/parser.py:GbnfParser.parse(text)` returns `list[RuleSpec]` directly; AST is not exposed.
- [ ] `grammars/gbnf/ast_to_ir.py` defines `GbnfClassifier(RuleClassifier[Rule])` and `GbnfConverter(SequenceConverter[Rule])`; classifier is memoised by `id(rule)`.
- [ ] `GbnfAdapter` exposes `parser`, `emitter`, `escapes`, `supports`, and the four handler-extension dicts (empty for plain GBNF).

**ws cleanup:**
- [ ] `parsing/lark_builder.py` has no `if atom.rule_name == "ws"` and no `if spec.rule_name == "ws"`; no hardcoded `ws : /[ \t\n]+/` line.
- [ ] `parsing/transformer.py` has no special `ws_method` and no `if spec.rule_name == "ws"`.
- [ ] `runtime/base.py` has no `atom.rule_name == "ws"` check; `semantic_dump` uses `non_semantic_fields`.
- [ ] The string `"ws"` appears at most once in `src/lexic/` (the IRBuilder default `trivia_rules={"ws"}`).

**Import boundaries:**
- [ ] No module under `lexic.parsing`, `lexic.codegen`, `lexic.runtime`, or `lexic.ir` imports from `lexic.grammars.gbnf` (or any other flavour package).
- [ ] No module under `lexic.grammars.gbnf` imports from `lexic.parsing`, `lexic.codegen`, or `lexic.runtime`.
- [ ] AST-based import-boundary test passes.

**Runtime adapter binding:**
- [ ] Every generated module sets `__adapter__ = <adapter>` at module level.
- [ ] `GrammarModel.to_text` and `to_grammar` resolve handlers via `self.__class__.__module__`'s `__adapter__`; no `decode_gbnf_escapes` import in `runtime/base.py`.

**Tests:**
- [ ] All existing tests green at every commit.
- [ ] `uv run ruff check src/ tests/` clean.
- [ ] New tests under `tests/unit/lexic/ir/`, `tests/unit/lexic/parsing/`, `tests/unit/lexic/runtime/`, and `tests/unit/lexic/grammars/gbnf/` are green.
- [ ] Round-trip property tests across all seven ground-truth grammars produce identical `list[RuleSpec]` (full `==` equality) before and after the refactor.

**Documents:**
- [ ] `CLAUDE.md`, `prototyping/next/2_ARCHITECTURE.md`, `prototyping/next/3_ROADMAP.md`, and the Slice B design spec are updated.
