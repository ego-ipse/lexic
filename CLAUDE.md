# CLAUDE.md — Lexic

Lexic is the grammar engine layer of Vyx (an agent-to-agent protocol).

## Style & plan

Before writing or editing code in this repo, read:

- **[docs/STYLE.md](docs/STYLE.md)** — coding standards: smaller methods, SOLID, avoid deep indentation, fix root causes (don't mute errors or patch symptoms), general Python practices. These rules apply to every change.
- **[prototyping/next/](prototyping/next/)** — the distilled plan for the next implementation arc: `1_NORTH_STAR.md` (invariants), `2_ARCHITECTURE.md` (target layout + layering rules + error vocabulary), `3_ROADMAP.md` (five slices A–E). Consult the architecture doc before adding new modules or splitting existing ones; consult the roadmap to place the work in the right slice.

If a rule in `docs/STYLE.md` conflicts with a specific instruction below, the specific instruction wins for its domain. Otherwise `docs/STYLE.md` is the default.

## Commands

Always prefix with `uv run`:

```bash
uv run pytest tests/ -q                  # full suite
uv run pytest tests/unit/lexic/ -q       # unit only
uv run ruff check src/ tests/            # lint
```

Never run `pytest` or `ruff` bare — always `uv run`.

If `ruff` flags generated files in `generated/`, fix the template in `src/lexic/codegen/model_emitter.py`, not the generated file.

## Project layout

```
src/lexic/
  __init__.py
  base.py                   GrammarModel base (to_text, to_gbnf, semantic_dump)
  parse.py                  parse(text, grammar_path) → GrammarModel (thin)
  generate.py               random string generator from RuleSpec
  ir/
    __init__.py             re-exports Atom, atom types, RuleSpec
    atoms.py                seven frozen Atom dataclasses
    spec.py                 RuleSpec dataclass
  grammars/                 flavour layer (Slice B target; see prototyping/next/2_ARCHITECTURE.md)
    __init__.py             public endpoint: get_adapter(), adapter_for_extension(), register_adapter()
    flavours.py             FlavourAdapter/Parser/Emitter protocols + ADAPTERS registry
    gbnf/                   GBNF flavour implementation
      adapter.py            GbnfAdapter
      parser.py             GBNF text → AST (moved from codegen/parser.py)
      emitter.py            GBNFEmitter: list[RuleSpec] → GBNF text (moved from codegen/gbnf_emitter.py)
      ast.py                GBNF AST nodes (moved from codegen/ast.py)
      escapes.py            decode_gbnf_escapes (moved from utils/escapes.py)
      charclass.py          GBNF bracket-expression parsing (moved from utils/charclass.py)
  codegen/
    __init__.py             codegen(grammar_path) → dict[name, type]
    ir_builder.py           IRBuilder: GBNF AST → list[RuleSpec]
    model_emitter.py        ModelEmitter: list[RuleSpec] → Python source
    lark_builder.py         LarkBuilder: list[RuleSpec] → Lark grammar
    transformer/            build_transformer: Lark tree → Pydantic instance
  utils/
    __init__.py
    quantifiers.py          bounds_to_quantifier
tests/
  unit/lexic/{codegen,ir,utils}/    mirror of src layout
  integration/                       test_codegen, test_gbnf_roundtrip, test_parse
  property/                          round-trip property tests (hypothesis)
resources/ground_truth/              seven .gbnf test grammars
generated/                           auto-generated Pydantic modules (git-ignored, do not edit)
```

## Architecture

The pipeline has one IR layer (`RuleSpec` + seven Atom types) between the GBNF AST and all downstream consumers:

```
GBNF AST  →  IRBuilder  →  RuleSpec IR  →  ModelEmitter  →  generated/*.py
                                        →  GBNFEmitter   →  GBNF text
                                        →  LarkBuilder   →  Lark grammar + Transformer
```

Each emitter has a single responsibility and knows nothing about the others.

### IR types (`src/lexic/ir/`)

Seven frozen `Atom` dataclasses, all re-exported from `lexic.ir`:

- `LiteralAtom(value)` — a literal string; never a Pydantic field
- `CharClassAtom(pattern, min, max)` — character class with quantifier bounds
- `QuantifiedLiteralAtom(value, min, max)` — literal with `?`/`+`/`*`/`{m,n}` quantifier
- `InlineRegexAtom(regex, gbnf, min, max)` — inline group flattened to a regex
- `RuleRefAtom(rule_name, min, max)` — reference to another rule
- `AlternationAtom(arm_rule_names)` — top-level named alternation
- `InlineAlternationAtom(arm_rule_names)` — alternation nested inside a sequence rule
- `RuleSpec(rule_name, class_name, parent_class_name, kind, items, field_map)` — one grammar rule

`kind` is one of: `"sequence"`, `"alternation"`, `"value_str"`.

`field_map` maps Pydantic field name → index into `items`. `LiteralAtom`s are never in `field_map`.

Note: Slice B of the next arc collapses `CharClassAtom` + `QuantifiedLiteralAtom` + `InlineRegexAtom` into a single `PatternAtom`. See `prototyping/next/3_ROADMAP.md` §Slice B.

### Semantic field naming (set by `IRBuilder`)

- `RuleRefAtom("ws")` → field `ws`, `ws2`, `ws3` …
- `RuleRefAtom("expr")` → field `expr` (rule name is the field name)
- `CharClassAtom` → semantic name via `_CHARCLASS_NAMES` lookup (e.g. `[0-9]` → `digit`, `[a-z]` → `lower`, `[a-zA-Z0-9_]` → `alnum`); falls back to `_sanitize_pattern(atom.pattern)`
- `QuantifiedLiteralAtom` → lookup in `_LITERAL_NAMES` (e.g. `-` → `sign`, `.` → `dot`)
- `InlineRegexAtom` → derived from the first alternation arm
- `LiteralAtom` → no field (emitted directly by `to_text()`)

Slice C of the next arc replaces this policy with a four-tier cascade (type alias → pattern library → structural positional → sidecar YAML).

### GrammarModel (`src/lexic/base.py`)

Every generated class inherits from `GrammarModel` and carries `__grammar__: ClassVar[RuleSpec]`.

- `to_text()` — walks `__grammar__.items` in order; emits `LiteralAtom.value` directly, looks up other atoms by `field_map`, calls `.to_text()` recursively on nested models.
- `to_gbnf()` — delegates to `GBNFEmitter`.
- `semantic_dump()` — `model_dump()` excluding fields whose `RuleSpec` item is `RuleRefAtom("ws")`.

### Import paths

`pyproject.toml` has `pythonpath = ["src"]`. All imports use:

```python
from lexic.ir import RuleSpec, LiteralAtom, ...
from lexic.base import GrammarModel
from lexic.codegen.ir_builder import IRBuilder
```

Never `from src.lexic...`.

## Key constraints

- run `ruff format` and `ruff check --fix` before trying to fix ruff issues manually.
- No `exec` or `eval` anywhere.
- No grammar-specific hardcoding.
- Generated files in `generated/` are write-once artifacts — fix template issues in `model_emitter.py`.
- `ast.py` and `parser.py` are stable dependencies — do not modify them.
- Runtime (`lexic/base.py`, `lexic/parse.py`, `lexic/generate.py`) imports from `lexic.ir` and — for the one deliberate `to_grammar` edge — from `lexic.grammars.gbnf.emitter`. All other codegen↔runtime edges are forbidden. See `prototyping/next/2_ARCHITECTURE.md` §Layering rules.

## Test file structure

`tests/unit/lexic/` is a structural mirror of `src/lexic/`:

```
src/lexic/foo/bar.py  →  tests/unit/lexic/foo/test_bar.py
```

**Whenever a source file is created, moved, renamed, or deleted, the corresponding test file must get the exact same treatment.** This is not optional. See `docs/STYLE.md` §10 for the full rule and exceptions.
