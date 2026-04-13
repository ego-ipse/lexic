# S01 — GBNF to Pydantic Model Generator — Research

**Date:** 2026-04-12
**Requirement:** R001 — SOLID model generation

## Summary

`src/` is empty; the entire slice is greenfield. All the AST infrastructure needed already exists in `llguidance.gbnf_to_lark` and was confirmed working against all 7 ground_truth grammars. The failed attempt's `FAILED_ATTEMPT/builder.py` has several utility functions that are correct and reusable (`load_grammar`, `to_class_name`, `to_field_name`, `_sequence_fields`, `ast_to_regex`, `decode_literal`). Only the model generation logic needs replacing.

The core task is to write `src/codegen.py` with a `build(grammar_path) -> dict[str, type]` function that applies the SOLID inheritance pattern to the parsed AST. The mechanics are well-understood: `AlternativeNode` rules become abstract bases + concrete subclasses; `SequenceNode` rules become classes with typed fields; single-ref rules become subclasses. The trickiest parts are (1) naming inline alternation branches that have no rule name, (2) the `root → start` rename that `resolve()` applies, and (3) circular Pydantic forward references which need `model_rebuild()`.

The implementation approach is to generate a Python code string and `exec()` it in a controlled namespace, then extract class objects by name. This is the simplest path — no file writing required, no import machinery, no importlib tricks.

## Recommendation

Write `src/codegen.py` as a single module. Port the utility functions from `FAILED_ATTEMPT/builder.py` directly (they're correct). Replace `generate_models()` with a new `_build_class_code()` that applies the SOLID pattern. Return `dict[str, type]` from `build()` after exec.

Do not write generated `.py` files to disk unless a later slice requires it. The verification check `mods['ObjectValue'].__bases__` only requires the class objects to exist with the right `__bases__`; the repr `src.generated.json_ws.Value` is produced by setting `__module__` on the generated classes, not by writing files.

## Implementation Landscape

### Key Files

- `FAILED_ATTEMPT/builder.py` — source of `load_grammar()` (lines 40–45), `to_class_name()` (53–55), `to_field_name()` (58–63), `pluralise()` (66–70), `decode_literal()` (73–96), `ast_to_regex()` (104–140), `_sequence_fields()` (186–242). All correct and directly portable to `src/codegen.py`. Do **not** port `generate_models()` or any parser generation code.
- `with_guidance.py:_gbnf_to_earley_lark()` (lines 255–269) — needed by S02, not S01, but read it to understand how `resolve()` + lowercase-rename produces Lark rules.
- `resources/ground_truth/` — 7 test grammars. Key ones for testing the generator: `json_ws.gbnf` (has both terminal and non-terminal refs in alternation, circular refs), `arithmetic.gbnf` (top-level RepetitionNode start rule, left-recursive expr), `c.gbnf` (8-branch statement alternation, complex).
- `src/codegen.py` — **create this file** (does not exist yet).
- `src/__init__.py` — **create empty** so `src` is a package.

### SOLID Pattern — Concrete Rules

**`AlternativeNode` rule** (e.g., `value ::= object | array | string | number | (...)`):
- Emit abstract `Value(BaseModel)` with `pass` body.
- For each alternative:
  - If `RuleRefNode` → target is non-terminal: emit `ObjectValue(Value)` with `value: Object` field
  - If `RuleRefNode` → target is terminal: emit `StringValue(Value)` with `value: str`
  - If inline `SequenceNode` or `AlternativeNode`: emit `{BaseName}Alt{i}(Value)` where `i` is 0-based index, with fields from `_sequence_fields()` if it's a sequence (or `value: str` if it's all literals)
- Class name for named-ref subclasses: `to_class_name(alt.name) + to_class_name(rule.name)` → `ObjectValue`

**`SequenceNode` rule** (e.g., `object ::= "{" ws (...) "}" ws`):
- Emit `Object(BaseModel)` with fields from `_sequence_fields()`.

**Single `RuleRefNode` rule** (e.g., `root ::= object`):
- If target is non-terminal: emit `Root(Object)` — subclass.
- If target is terminal: emit `Root(BaseModel)` with `value: str`.

**`RepetitionNode` rule** (e.g., `start ::= (expr "=" ws term "\n")+` in arithmetic):
- Emit `Start(BaseModel)` with `items: list[ExprLine]` or similar — the inner type depends on `_node_to_type()`.

**`root → start` rename** — `resolve()` renames the root rule from `root` to `start` in both the dict key and `rule.name`. Before calling `resolve()`, capture the original name: `original_root_name = next(iter(rules))` (it's always first). After resolve, the `start` rule's `order == 0`. When generating the class for the start rule, use `to_class_name(original_root_name)` → `Root`.

**Forward references / circular deps** — `value` references `object` which references `value`. The exec'd code must begin with `from __future__ import annotations`. After all class definitions, call `model_rebuild()` on every class in the same order they were defined.

**`__module__` for repr** — After exec, iterate classes and set `cls.__module__ = f'src.generated.{grammar_stem}'` to match the expected `__bases__` repr.

### Build Order

1. **`src/__init__.py`** — empty, unblocks imports.
2. **`src/codegen.py`** — the whole slice. Port utilities from `builder.py`, implement `_build_class_code()` for SOLID pattern, implement `build()` with exec + module rename.
3. **Smoke test**: `uv run python -c "from src.codegen import build; mods = build('resources/ground_truth/json_ws.gbnf'); print(mods['ObjectValue'].__bases__)"` must print `(<class 'src.generated.json_ws.Value'>,)`.
4. **Breadth test**: run `build()` on all 7 grammars without error.

### Verification Approach

```bash
# Primary acceptance check
uv run python -c "
from src.codegen import build
mods = build('resources/ground_truth/json_ws.gbnf')
assert mods['ObjectValue'].__bases__ == (mods['Value'],), mods['ObjectValue'].__bases__
assert mods['ArrayValue'].__bases__ == (mods['Value'],)
assert issubclass(mods['Root'], mods['Object'])
print('PASS:', list(mods.keys()))
"

# All 7 grammars
uv run python -c "
from src.codegen import build
from pathlib import Path
for p in sorted(Path('resources/ground_truth').glob('*.gbnf*')):
    mods = build(p)
    print(p.name, '->', list(mods.keys()))
"
```

## Common Pitfalls

- **`root → start` rename** — `resolve()` mutates the dict: `rules['root']` becomes `rules['start']` and `rule.name` becomes `'start'`. Capture the original root name (via `next(iter(parser.parse(text)))`) before calling `resolve()`, OR rename back after resolve with `rules['root'] = rules.pop('start'); rules['root'].name = 'root'`.

- **Inline alternation alternatives have no name** — `value` alt[4] is `SequenceNode([AlternativeNode(["true","false","null"]), RuleRefNode(ws)])`. It has no `name` attr. Use positional name `{BaseName}Alt{i}` (e.g., `ValueAlt4`). Don't try to infer semantic names from literals.

- **Terminal rules don't get classes** — In `json_ws.gbnf`, `STRING`, `NUMBER`, `WS` are terminals (`rule_is_terminal=True`). Refs to them in sequences resolve to `str` fields. Don't emit classes for terminals.

- **`from __future__ import annotations` must be the first line** inside the exec'd string — otherwise forward refs in type annotations fail for circular deps (`Value` refs `Object` refs `Value`).

- **`_sequence_fields()` from builder.py handles deduplication** — field names that collide get `_2`, `_3` suffixes. Port this logic exactly; don't simplify.

- **`chess.gbnf` and `japanese.gbnf` have non-terminal `ws`** (lowercase, order 6) — unlike `json_ws.gbnf` where `WS` is terminal. The codegen must handle both cases cleanly.

- **`c.gbnf` `statement` has 8 alternation branches** — all inline sequences. All get `StatementAlt0` … `StatementAlt7` names. This is expected; don't try to be clever about names.

## Open Risks

- **`_sequence_fields()` for deeply-nested inline sequences** — the `c.gbnf` statement branches each contain 3–7 sub-sequences. `_sequence_fields()` only looks one level deep. May produce empty or incomplete field lists for complex branches. Needs testing against c.gbnf before declaring done.
- **`model_rebuild()` ordering** — Pydantic requires that all referenced classes exist before `model_rebuild()` is called on a class that references them. Emitting rebuilds in the same order as class definitions (by `rule.order`) should work for DAG-shaped deps; circular deps need all classes defined first, then all rebuilds.
