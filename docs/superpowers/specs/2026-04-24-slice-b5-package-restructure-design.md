# Slice B.5 — Package restructure: generic `ir/` protocols + `parsing/` + thin `grammars/gbnf/` overrides

**Date:** 2026-04-24
**Status:** Approved (brainstormed)
**Implementation plan:** `docs/superpowers/plans/2026-04-24-slice-b5-package-restructure.md` (to be written)
**Roadmap entry:** `prototyping/next/3_ROADMAP.md` §Slice B.5 (to be inserted)
**Inserts before:** Slice B Phase 2 (atom collapse)

## Background

Phase 1 of Slice B delivered the flavour-seam scaffolding (`grammars/`, `flavours.py`, adapter, exception vocabulary, regex_portable). What it did not fix is the deeper layout problem: `codegen/` holds two completely different concerns bundled together.

**GBNF-specific IR construction** (`ir_builder.py`, `classify.py`, `seq_to_atoms.py`, `ast_utils.py`, `helpers.py`) sits alongside **generic downstream machinery** (`lark_builder.py`, `transformer/`, `model_emitter.py`, `naming.py`). The result: `lark_builder.py` imports `decode_gbnf_escapes` from `grammars/gbnf/` (a flavour-seam violation), and `codegen/__init__.py` must import `IRBuilder` (GBNF-specific) to run the pipeline.

This slice fixes the layout before the atom collapse (Phase 2) operates on it.

## Invariant

**No GBNF knowledge outside `grammars/gbnf/`.** Each package has exactly one flavour-agnostic responsibility.

## Package layout after Slice B.5

Every file belongs to exactly one bucket:

| Package | Knows | Contents |
|---------|-------|----------|
| `ir/` | IR types + generic protocols | `atoms.py`, `spec.py`, `regex_portable.py`, **`protocols.py`** (new) |
| `parsing/` | Lark + `list[RuleSpec]` | **`lark_builder.py`** (moved), **`transformer/`** (moved) |
| `grammars/gbnf/` | GBNF AST + IR protocols | `parser.py`, `emitter.py`, `adapter.py`, `ast.py`, **`ast_utils.py`** (moved), `escapes.py`, `charclass.py`, **`classify.py`** (moved), **`seq_to_atoms.py`** (moved), **`ir_builder.py`** (moved), **`naming_hints.py`** (new) |
| `codegen/` | Python source + generic naming | `model_emitter.py`, `naming.py` (lookup tables extracted) |

```
src/lexic/
  ir/
    __init__.py         re-exports atoms, Arm, RuleSpec, RuleClassifier, SequenceConverter,
                        HelperRuleRegistry, IRBuilder
    atoms.py            (unchanged)
    regex_portable.py   (unchanged)
    spec.py             (unchanged)
    protocols.py        NEW

  parsing/              NEW PACKAGE — zero GBNF knowledge
    __init__.py
    lark_builder.py     git mv from codegen/lark_builder.py
    transformer/        git mv from codegen/transformer/
      __init__.py
      registry.py
      builders.py
      build_transformer.py
      context.py

  grammars/
    __init__.py         (unchanged)
    flavours.py         (unchanged)
    gbnf/
      __init__.py       (unchanged)
      adapter.py        (unchanged)
      parser.py         GbnfParser.parse() now returns list[RuleSpec] directly
      emitter.py        (unchanged)
      ast.py            (unchanged)
      ast_utils.py      git mv from codegen/ast_utils.py
      escapes.py        (unchanged)
      charclass.py      (unchanged)
      classify.py       git mv from codegen/classify.py → GbnfClassifier(RuleClassifier[Rule])
      seq_to_atoms.py   git mv from codegen/seq_to_atoms.py → GbnfConverter(SequenceConverter[Rule])
      ir_builder.py     git mv from codegen/ir_builder.py → thin wiring only
      naming_hints.py   NEW — _CHARCLASS_NAMES, _LITERAL_NAMES extracted from codegen/naming.py

  codegen/
    __init__.py         calls adapter.parser.parse(text) → list[RuleSpec]; no IRBuilder import
    model_emitter.py    (unchanged)
    naming.py           generic naming only; gains optional hints parameter
```

## `ir/protocols.py`

```python
from __future__ import annotations
from typing import Generic, Literal, Protocol, TypeVar
from lexic.ir.atoms import Atom

Node = TypeVar("Node")


class RuleClassifier(Protocol[Node]):
    """Determines the IR kind and structure of a single grammar rule node."""

    def rule_name(self, rule: Node) -> str: ...
    def kind(self, rule: Node) -> Literal["sequence", "alternation", "value_str"]: ...
    def alternation_arm_nodes(self, rule: Node) -> list[Node]: ...
    def sequence_body(self, rule: Node) -> Node: ...
    def single_ruleref(self, arm: Node) -> str | None: ...


class SequenceConverter(Protocol[Node]):
    """Converts flavour AST nodes to lists of IR Atoms."""

    def value_str_atoms(self, rule: Node) -> list[Atom]: ...
    def sequence_atoms(
        self,
        body: Node,
        cls_name: str,
        helpers: "HelperRuleRegistry",
        name_map: dict[str, str],
    ) -> list[Atom]: ...


class HelperRuleRegistry:
    """Accumulates synthesised helper RuleSpecs during IR construction.

    Moved from codegen/helpers.py — IR construction machinery, not Python-source generation.
    """
    # Implementation unchanged from codegen/helpers.py


class IRBuilder(Generic[Node]):
    """Generic orchestrator: list[Node] → list[RuleSpec].

    Parameterised by a RuleClassifier and SequenceConverter so it is
    completely flavour-agnostic. GBNF wires: IRBuilder[Rule](GbnfClassifier(), GbnfConverter()).
    """

    def __init__(
        self,
        classifier: RuleClassifier[Node],
        converter: SequenceConverter[Node],
    ) -> None: ...

    def build(self, rules: list[Node]) -> list[RuleSpec]:
        """Build and return specs in grammar order (root first)."""
        ...
    # Internals: _compute_parents, _build_rule, _build_value_str,
    # _build_named_alt, _build_sequence, _topo_sort — same logic as today,
    # generic over Node via the protocol methods.
```

`ir/__init__.py` re-exports `RuleClassifier`, `SequenceConverter`, `HelperRuleRegistry`, `IRBuilder`.

## GBNF thin overrides

### `grammars/gbnf/classify.py`

`GbnfClassifier` implements `RuleClassifier[Rule]`. The five protocol methods are the existing `Classifier.classify()` logic decomposed into single-purpose queries. Internal classification predicates and helpers (`_has_any_ruleref`, `strip_ws`, etc.) remain as module-level helpers.

### `grammars/gbnf/seq_to_atoms.py`

`GbnfConverter` implements `SequenceConverter[Rule]`. `sequence_atoms` and `value_str_atoms` are today's `seq_to_atoms` / `value_str_to_atoms` functions wrapped as methods. `sequence_atoms` passes GBNF naming hints into `assign_field_names`.

### `grammars/gbnf/naming_hints.py`

```python
_CHARCLASS_NAMES: dict[str, str] = { ... }   # extracted from codegen/naming.py
_LITERAL_NAMES: dict[str, str] = { ... }     # extracted from codegen/naming.py
```

`assign_field_names` in `codegen/naming.py` gains an optional `hints` parameter. `GbnfConverter.sequence_atoms` passes GBNF hints when calling it; all other callers use the default (empty hints → generic fallback names).

### `grammars/gbnf/ir_builder.py`

Thin wiring only:

```python
from lexic.ir import IRBuilder
from lexic.grammars.gbnf.classify import GbnfClassifier
from lexic.grammars.gbnf.seq_to_atoms import GbnfConverter

def build_specs(rules: list[Rule]) -> list[RuleSpec]:
    return IRBuilder(GbnfClassifier(), GbnfConverter()).build(rules)
```

`GbnfParser.parse()` in `parser.py` calls `build_specs()` and returns `list[RuleSpec]` directly.

## Data flow

```
GbnfParser.parse(text)                        [grammars/gbnf/]
  Lark parse → list[Rule]                     GBNF AST — stays inside grammars/gbnf/
  IRBuilder[Rule].build(rules)                generic orchestrator — in ir/
  → list[RuleSpec]                            IR — crosses the seam; AST does not

codegen/__init__.build_classes_and_specs(text):
  adapter.parser.parse(text)  → list[RuleSpec]   no IRBuilder import
  ModelEmitter(specs).render() → Python source

compile._compile_core(text):
  build_classes_and_specs(text)        → (classes, specs)
  LarkBuilder(specs).build_grammar()   → (grammar_str, start)   [parsing/]
  build_transformer(specs, classes)    → Transformer             [parsing/]
```

## `parsing/` invariant

`parsing/lark_builder.py` and `parsing/transformer/` must not import from `lexic.grammars.gbnf` or any flavour package. Two specific removals:

1. `decode_gbnf_escapes` import removed — `LiteralAtom.value` is canonical Python by the time it reaches `parsing/` (decoded by `GbnfParser` at parse time).
2. `if atom.rule_name == "ws": return "ws?"` removed — `IRBuilder.build()` sets `min=0` on ws `RuleRefAtom`s; `LarkBuilder` emits `rule_name?` uniformly for any `RuleRefAtom` with `min=0`.

## Creates, moves, deletes

**Creates:**
- `lexic/ir/protocols.py`
- `lexic/parsing/__init__.py`
- `lexic/grammars/gbnf/naming_hints.py`

**Moves (via `git mv`):**
- `codegen/lark_builder.py` → `parsing/lark_builder.py`
- `codegen/transformer/` → `parsing/transformer/`
- `codegen/ast_utils.py` → `grammars/gbnf/ast_utils.py`
- `codegen/classify.py` → `grammars/gbnf/classify.py`
- `codegen/seq_to_atoms.py` → `grammars/gbnf/seq_to_atoms.py`
- `codegen/ir_builder.py` → `grammars/gbnf/ir_builder.py`

**Deletes:**
- `codegen/helpers.py` — `HelperRuleRegistry` absorbed into `ir/protocols.py`

**Extractions (content moves, file stays):**
- `_CHARCLASS_NAMES`, `_LITERAL_NAMES` out of `codegen/naming.py` → `grammars/gbnf/naming_hints.py`

## Testing

Pure refactor — no behaviour change. All existing tests stay green at every commit.

**Test file mirror:** test files follow their source files:
- `tests/unit/lexic/codegen/test_lark_builder.py` → `tests/unit/lexic/parsing/test_lark_builder.py`
- `tests/unit/lexic/codegen/transformer/` → `tests/unit/lexic/parsing/transformer/`
- `tests/unit/lexic/codegen/test_ir_builder.py` → `tests/unit/lexic/grammars/gbnf/test_ir_builder.py`
- `tests/unit/lexic/codegen/test_classify.py` → `tests/unit/lexic/grammars/gbnf/test_classify.py`
- `tests/unit/lexic/codegen/test_seq_to_atoms.py` → `tests/unit/lexic/grammars/gbnf/test_seq_to_atoms.py`

**New tests:**
- `tests/unit/lexic/ir/test_protocols.py` — `IRBuilder[Rule]` wired with `GbnfClassifier` + `GbnfConverter` produces the same `list[RuleSpec]` as today's `IRBuilder` for all seven ground-truth grammars.
- Import-boundary assertion: a test in `tests/unit/lexic/parsing/` checks that no module under `lexic.parsing` imports from `lexic.grammars.gbnf`.

## Document updates

The following documents must be updated as part of Slice B.5 (before or alongside the implementation commits):

- **`prototyping/next/3_ROADMAP.md`** — insert Slice B.5 section between Phase 1 and Phase 2 of Slice B.
- **`prototyping/next/2_ARCHITECTURE.md`** — update target module layout; update layering rules to name `parsing/` and describe the `ir/` protocol contract; update `codegen/` responsibilities.
- **`docs/superpowers/specs/2026-04-23-slice-b-design.md`** — update §Architecture delta / target layout (Phase 2 and Phase 3 now operate on the post-B.5 structure); update §Creates, moves, deletes; note that `LarkBuilder.build_transformer` deletion (D1) and the `ws` special-case removal are Slice B.5 scope, not Phase 2.
- **`CLAUDE.md`** — update project layout table: add `parsing/`, update `codegen/` entry, add `ir/protocols.py`.

## Exit criteria

- [ ] `lexic/ir/protocols.py` exists with `RuleClassifier`, `SequenceConverter`, `HelperRuleRegistry`, `IRBuilder` (all generic over `Node`).
- [ ] `lexic/parsing/__init__.py` exists; `lark_builder.py` and `transformer/` live under `parsing/`.
- [ ] `codegen/lark_builder.py`, `codegen/transformer/`, `codegen/ast_utils.py`, `codegen/classify.py`, `codegen/seq_to_atoms.py`, `codegen/ir_builder.py`, `codegen/helpers.py` do not exist.
- [ ] `grammars/gbnf/classify.py` implements `RuleClassifier[Rule]`; `grammars/gbnf/seq_to_atoms.py` implements `SequenceConverter[Rule]`.
- [ ] `grammars/gbnf/ir_builder.py` contains only wiring — `IRBuilder(GbnfClassifier(), GbnfConverter()).build(rules)`.
- [ ] `grammars/gbnf/naming_hints.py` exists; `_CHARCLASS_NAMES` and `_LITERAL_NAMES` removed from `codegen/naming.py`.
- [ ] `GbnfParser.parse()` returns `list[RuleSpec]` directly.
- [ ] `codegen/__init__.py` contains no `IRBuilder` import.
- [ ] `parsing/lark_builder.py` has no import from `lexic.grammars.gbnf`; no `rule_name == "ws"` special case.
- [ ] `IRBuilder.build()` sets `min=0` on ws `RuleRefAtom`s.
- [ ] `assign_field_names` in `codegen/naming.py` accepts optional hints; defaults to empty (generic fallback).
- [ ] All existing tests green; `uv run ruff check src/ tests/` clean.
- [ ] `tests/unit/lexic/ir/test_protocols.py` green.
- [ ] Import-boundary test green.
- [ ] All four documents updated.
