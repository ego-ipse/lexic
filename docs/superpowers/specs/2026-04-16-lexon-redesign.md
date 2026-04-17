# Lexon Redesign: Bidirectional GBNF ↔ Pydantic Pipeline

**Date:** 2026-04-16
**Status:** Approved

## Problem Statement

The current S02 implementation exposed three interrelated failures:

1. **Quantifiers are lost** — generated Pydantic models drop all quantifier information (`*`, `+`, `?`, `{N,M}`, char class bounds). Fields are untyped `str` with no constraints.
2. **`to_text()` is broken** — `ws` is stripped from models during codegen, so `to_text()` cannot reconstruct the original text. Round-trip fidelity fails.
3. **Code has no clear structure** — the pipeline is a flat bag of functions across `classify.py`, `emitter.py`, and `parse.py` with tangled responsibilities.

The root cause: `ClassSpec`/`FieldSpec` is a lossy intermediate representation. It cannot express what the GBNF actually says, so everything downstream — parsing, serialization, and eventually translation — pays for it.

## Goals

- GBNF is the source of truth. Models are generated from it.
- Generated models carry enough grammar metadata to **re-derive the GBNF** (bidirectional).
- Hand-authored Pydantic models with the correct base class and `__grammar__` attribute are also valid inputs to the pipeline.
- `to_text()` is exact byte-identical (whitespace preserved, not normalized).
- `to_gbnf()` reconstructs the original GBNF from model classes.
- `parse()` builds its Lark grammar from model class metadata — not from the GBNF file directly.
- Code is structured with single-responsibility classes (SOLID).
- Translation (`S04`) is a future consumer: `semantic_dump()` on a model instance excludes `ws` fields to support cross-grammar data transfer.

## Non-Goals

- No grammar-specific hardcoding anywhere.
- No `exec`/`eval`.
- CLI or web interface (deferred).
- S04 translation is a future slice — this design accommodates it but does not implement it.

---

## Architecture

### Pipeline

```
GBNF text
   ↓  GBNFParser (existing codegen/parser.py — unchanged)
GBNF AST  (Rule / Item / Atom nodes — existing codegen/ast.py — unchanged)
   ↓  IRBuilder  (new)
RuleSpec IR  ← the missing layer; carries complete grammar semantics
   ↓  ModelEmitter    → generated/*.py  (classes carry __grammar__)
   ↓  GBNFEmitter     → GBNF text       (reverse direction)
   ↓  LarkBuilder     → Lark grammar    (drives parse())

Runtime:
  ModelClass.__grammar__  →  GBNFEmitter   →  GBNF text
  ModelClass.__grammar__  →  LarkBuilder   →  Lark parser
  model_instance.to_text()                 ←  GrammarModel base walks __grammar__
  model_instance.to_gbnf()                 ←  delegates to GBNFEmitter
  model_instance.semantic_dump()           ←  model_dump() excluding ws fields (S04 prep)
```

---

## IR Layer (`src/codegen/ir.py`)

### Atoms

```python
@dataclass
class LiteralAtom:
    value: str                        # e.g. "=" or "("

@dataclass
class CharClassAtom:
    pattern: str                      # e.g. "a-z" or "a-z0-9_"
    min: int                          # 1 for [x], 0 for [x]*, 1 for [x]+
    max: int | None                   # 1 for [x] or [x]?, None for unbounded

@dataclass
class RuleRefAtom:
    rule_name: str                    # e.g. "ws", "expr", "term"
    min: int                          # 0 for optional, 1 for required
    max: int | None                   # None for unbounded (+/*)

@dataclass
class AlternationAtom:
    arms: list[RuleSpec]              # each arm is its own RuleSpec
```

### RuleSpec

```python
@dataclass
class RuleSpec:
    rule_name: str
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[LiteralAtom | CharClassAtom | RuleRefAtom | AlternationAtom]
    field_map: dict[str, int]         # pydantic field name → index into items
    # Only structural (literal, ws) items are absent from field_map.
    # Every non-structural item has an entry.
```

`field_map` is the bridge between the Pydantic layer (named fields) and the grammar layer (ordered items). It is what allows `to_text()` to reconstruct literals and ws between semantic fields, and what allows `to_gbnf()` to emit the full rule.

### Example: `ident ::= [a-z] [a-z0-9_]* ws`

```python
RuleSpec(
    rule_name="ident",
    kind="sequence",
    items=[
        CharClassAtom("a-z", min=1, max=1),
        CharClassAtom("a-z0-9_", min=0, max=None),
        RuleRefAtom("ws", min=1, max=1),
    ],
    field_map={"first": 0, "rest": 1, "ws": 2},
)
```

Generated class:
```python
class Ident(Term):
    __grammar__: ClassVar[RuleSpec] = RuleSpec(...)

    first: str   # [a-z], exactly one char
    rest: str    # [a-z0-9_]*, zero or more
    ws: Ws       # whitespace, preserved for fidelity
```

### Example: `term ::= ident | num | "(" ws expr ")" ws`

```python
RuleSpec(
    rule_name="term",
    kind="alternation",
    items=[
        AlternationAtom(arms=[
            RuleSpec(rule_name="ident", ...),
            RuleSpec(rule_name="num", ...),
            RuleSpec(rule_name="term_arm3", kind="sequence", items=[
                LiteralAtom("("),
                RuleRefAtom("ws", min=1, max=1),
                RuleRefAtom("expr", min=1, max=1),
                LiteralAtom(")"),
                RuleRefAtom("ws", min=1, max=1),
            ], field_map={"ws1": 1, "expr": 2, "ws2": 4}),
        ])
    ],
    field_map={},
)
```

---

## Code Structure

```
src/
  codegen/
    ast.py            — GBNF AST nodes (unchanged)
    parser.py         — text → AST (unchanged)
    ir.py             — RuleSpec, all Atom types (new)
    ir_builder.py     — IRBuilder: AST → RuleSpec  (replaces classify.py logic)
    model_emitter.py  — ModelEmitter: RuleSpec → Python source  (replaces emitter.py)
    gbnf_emitter.py   — GBNFEmitter: RuleSpec → GBNF text  (new)
    lark_builder.py   — LarkBuilder: RuleSpec → Lark grammar string  (replaces parse.py logic)
  base.py             — GrammarModel: to_text(), to_gbnf(), semantic_dump()
  parse.py            — parse(text, grammar_path | model_cls) → GrammarModel  (thin)
  translate.py        — translate(instance_A, target_cls) → GrammarModel  (S04)
```

### Single Responsibilities

| Class | Input | Output | Knows about |
|---|---|---|---|
| `IRBuilder` | GBNF AST | `RuleSpec` IR | GBNF semantics only |
| `ModelEmitter` | `RuleSpec` IR | Python source (`generated/*.py`) | Python / Pydantic only |
| `GBNFEmitter` | `RuleSpec` IR | GBNF text string | GBNF syntax only |
| `LarkBuilder` | `RuleSpec` IR | Lark grammar string | Lark syntax only |
| `GrammarModel` | — | — | Drives `to_text()`, `to_gbnf()`, `semantic_dump()` from `__grammar__`; knows nothing about codegen |

---

## `GrammarModel` Base Class (`src/base.py`)

```python
class GrammarModel(BaseModel):
    __grammar__: ClassVar[RuleSpec]

    def to_text(self) -> str:
        """Walk __grammar__.items; emit literals directly, look up fields by field_map."""
        ...

    def to_gbnf(self) -> str:
        """Delegate to GBNFEmitter(self.__grammar__)."""
        ...

    def semantic_dump(self) -> dict:
        """model_dump() excluding fields whose RuleSpec item is a ws RuleRefAtom.
        Intended for S04 cross-grammar translation."""
        ...
```

`to_text()` algorithm:
1. Build inverse map: `item_index → field_name` from `__grammar__.field_map`
2. Walk `__grammar__.items` in order
3. For each item:
   - `LiteralAtom` → emit `atom.value`
   - item index in inverse map → `getattr(self, field_name)`:
     - if `GrammarModel` subclass → call `.to_text()`
     - if `list` → `"".join(i.to_text() if isinstance(i, GrammarModel) else str(i) for i in val)`
     - if `str` → emit directly

---

## Semantic Field Naming

Current codegen emits `field1`, `field2`, etc. — unusable for S04 translation via `model_dump()`.

New naming rules (applied in `IRBuilder`):
- `RuleRefAtom("ws")` → field name `ws` (or `ws2`, `ws3` if repeated in same sequence)
- `RuleRefAtom("expr")` → field name `expr` (rule ref name is always the field name)
- `RuleRefAtom("term")` → field name `term`
- `CharClassAtom` → field name derived from position: first char class in rule → `value` if rule is `value_str`, otherwise `first`, `second`, `third` by position index among char class atoms in the sequence
- `LiteralAtom` → **never a Pydantic field**. Literals are always emitted directly from `atom.value` in `to_text()`. They appear in `items` but are absent from `field_map`. This is intentional: a literal is part of the grammar's typography, not the data. `semantic_dump()` therefore naturally excludes them.
- Repeated refs of the same non-ws name → suffixed: `term`, `term2`, `term3`

This ensures `model_dump()` and `semantic_dump()` produce meaningful dicts that can be reasoned about by S04 translation logic.

---

## Whitespace Fidelity

`Ws` remains a first-class generated model with a `value: str` field. It is treated as a regular `RuleRefAtom` in `RuleSpec`. `to_text()` calls `ws.to_text()` → `ws.value`, preserving the exact whitespace string seen at parse time.

`semantic_dump()` excludes `ws` fields (identified by their `RuleSpec` item being `RuleRefAtom("ws")`), producing a clean dict for cross-grammar translation in S04.

---

## Bidirectional Contract

| Direction | Mechanism |
|---|---|
| GBNF → Models | `IRBuilder` + `ModelEmitter` → `generated/*.py` |
| Models → GBNF | `GBNFEmitter(ModelClass.__grammar__)` → GBNF text |
| GBNF → Lark | `LarkBuilder(ModelClass.__grammar__)` → Lark grammar |
| Instance → text | `GrammarModel.to_text()` walks `__grammar__` |
| Instance → GBNF | `GrammarModel.to_gbnf()` → delegates to `GBNFEmitter` |

`parse(text, grammar_path)` uses `grammar_path` to load (or generate) the model classes, then uses `LarkBuilder` on those classes — not on the raw GBNF — to build the Lark grammar. This means `parse()` works equally well with hand-authored model classes.

---

## Ground Truth Grammars

All 7 grammars in `resources/ground_truth/` remain the authoritative test targets:
`arithmetic`, `c`, `chess`, `japanese`, `json_arr`, `json_ws`, `list`.

`vyx.gbnf` is not a test target (broken, per `issues.md`).

---

## Slicing Strategy

This redesign replaces the current S02 implementation. It does not need to be done all at once:

1. **IR layer first** — `ir.py` + `ir_builder.py`. No emitters yet. Validated by unit tests against all 7 grammars.
2. **ModelEmitter** — replaces `emitter.py`. Generates `generated/*.py` with `__grammar__`. Validated by existing S01 codegen tests + new `__grammar__` presence tests.
3. **GrammarModel base** — `base.py` with `to_text()`. Validated by round-trip tests.
4. **LarkBuilder + parse()** — replaces current `parse.py`. Validated by parse round-trip tests across all 7 grammars.
5. **GBNFEmitter** — `gbnf_emitter.py`. Validates bidirectional: `parse_gbnf(GBNFEmitter(cls.__grammar__))` round-trips.

S03 (generation) and S04 (translation) consume this pipeline unchanged.
