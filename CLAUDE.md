# CLAUDE.md — Lexic

Lexic is the grammar engine layer of Vyx (an agent-to-agent protocol). The repo is currently named `vyx_2`; the canonical name is Lexic.

## Style & structure

Before writing or editing code in this repo, read:

- **[STYLE.md](STYLE.md)** — coding standards: smaller methods, SOLID, avoid deep indentation, fix root causes (don't mute errors or patch symptoms), general Python practices. These rules apply to every change.
- **[STRUCTURE.md](STRUCTURE.md)** — proposed file/class layout for `src/lexic/`, tied to the concerns in `OPUS_REVIEW_V3.md`. Consult before adding new modules or splitting existing ones.

If a rule in `STYLE.md` conflicts with a specific instruction below, the specific instruction wins for its domain. Otherwise `STYLE.md` is the default.

## Commands

Always prefix with `uv run`:

```bash
uv run pytest tests/ -v          # full suite (220 tests)
uv run pytest tests/test_ir.py   # single file
uv run ruff check src/ tests/    # lint
```

Never run `pytest` or `ruff` bare — always `uv run`.

If `ruff` flags generated files in `generated/`, fix the template in `src/codegen/model_emitter.py`, not the generated file.

## Project layout

```
src/
  codegen/
    ast.py            GBNF AST nodes (unchanged — do not touch)
    parser.py         GBNF text → AST (unchanged — do not touch)
    ir.py             RuleSpec + all Atom dataclasses
    ir_builder.py     IRBuilder: GBNF AST → list[RuleSpec]
    model_emitter.py  ModelEmitter: list[RuleSpec] → Python source (generated/*.py)
    gbnf_emitter.py   GBNFEmitter: list[RuleSpec] → GBNF text
    lark_builder.py   LarkBuilder: list[RuleSpec] → Lark grammar + Transformer
    __init__.py       codegen() / generate_classes() entry point
  base.py             GrammarModel base class (to_text, to_gbnf, semantic_dump)
  parse.py            parse(text, grammar_path) → GrammarModel instance (thin)
tests/
  test_ir.py
  test_ir_builder.py
  test_model_emitter.py
  test_base.py
  test_lark_builder.py
  test_gbnf_emitter.py
  test_parser.py
  test_codegen.py
resources/ground_truth/   seven .gbnf test grammars
generated/                auto-generated Pydantic modules (git-ignored, do not edit)
```

## Architecture

The pipeline has one IR layer (`RuleSpec`) between the GBNF AST and all downstream consumers:

```
GBNF AST  →  IRBuilder  →  RuleSpec IR  →  ModelEmitter  →  generated/*.py
                                        →  GBNFEmitter   →  GBNF text
                                        →  LarkBuilder   →  Lark grammar
```

Each emitter has a single responsibility and knows nothing about the others.

### IR types (`src/codegen/ir.py`)

- `LiteralAtom(value)` — a literal string in the grammar (e.g. `"="`, `"("`); never a Pydantic field
- `CharClassAtom(pattern, min, max)` — character class with quantifier bounds
- `RuleRefAtom(rule_name, min, max)` — reference to another rule with quantifier bounds
- `AlternationAtom(arm_rule_names)` — list of arm rule names for an alternation
- `RuleSpec(rule_name, class_name, parent_class_name, kind, items, field_map)` — one grammar rule

`kind` is one of: `"sequence"`, `"alternation"`, `"value_str"`.

`field_map` maps Pydantic field name → index into `items`. `LiteralAtom`s are never in `field_map`.

### Semantic field naming (set by IRBuilder)

- `RuleRefAtom("ws")` → field `ws`, `ws2`, `ws3` ...
- `RuleRefAtom("expr")` → field `expr` (rule name is the field name)
- `CharClassAtom` → semantic name via `_CHARCLASS_NAMES` lookup (e.g. `[0-9]` → `digit`, `[a-z]` → `lower`, `[a-zA-Z0-9_]` → `alnum`); falls back to `_sanitize_pattern(atom.pattern)`; or `value` for `value_str` rules
- `LiteralAtom` → no field (emitted directly by `to_text()`)

### GrammarModel (`src/base.py`)

Every generated class inherits from `GrammarModel` and carries `__grammar__: ClassVar[RuleSpec]`.

- `to_text()` — walks `__grammar__.items` in order; emits `LiteralAtom.value` directly, looks up other atoms by `field_map`, calls `.to_text()` recursively on nested models
- `to_gbnf()` — delegates to `GBNFEmitter`
- `semantic_dump()` — `model_dump()` excluding fields whose `RuleSpec` item is `RuleRefAtom("ws")`

### Import paths

`pyproject.toml` has `pythonpath = ["src"]`. All imports use:

```python
from codegen.ir import RuleSpec, LiteralAtom, ...
from base import GrammarModel
```

Never `from src.codegen import ...`.

## Upcoming: S04 Translation

S04 is the next slice. It will implement cross-grammar translation:

```python
# src/translate.py  (not yet written)
def translate(instance: GrammarModel, target_cls: type[GrammarModel]) -> GrammarModel:
    ...
```

The idea: `instance.semantic_dump()` produces a whitespace-free dict keyed by semantic field names. S04 uses this dict (plus knowledge of `target_cls.__grammar__`) to construct an equivalent instance in the target grammar.

`semantic_dump()` is already implemented on every `GrammarModel` as S04 prep. When implementing S04:

- Source: `instance.semantic_dump()` — a dict with meaningful keys (`expr`, `term`, `value`, etc.), no `ws` keys
- Target: `target_cls.__grammar__` — walk its `field_map` to know what fields the target expects
- The translation mapping between source and target field names is the open design question for S04

Do not implement S04 speculatively. The groundwork is in place; wait for a proper spec.

## Key constraints

- No `exec` or `eval` anywhere
- No grammar-specific hardcoding
- Generated files in `generated/` are write-once artifacts — fix template issues in `model_emitter.py`
- `ast.py` and `parser.py` are stable dependencies — do not modify them
- The `SHIT/` directory is abandoned code — never reference or copy from it
