# new_codegen — IrItem-Shape Code Generator

**When to load:** implementing Tasks 9–14 (`new_codegen/`); understanding what `aliases.py` provides; building `model_emitter.py`; understanding the generated-code target shape.

See also: [[cutover-plan]], [[ir-shapes]], [[field-naming]], [[decisions]]

Renamed to `lexic.codegen` at cutover (Task 18, Slice 4). Until then lives at `src/lexic/new_codegen/`.

---

## What it builds (Tasks 8–14)

The new codegen takes `list[NewRuleSpec]` and emits a Python module. It is built task-by-task alongside the old `codegen/`, never touching it.

| Task | File | Adds |
|---|---|---|
| 8 ✓ | `aliases.py` | `PatternAlias`, `collect_aliases`, `regex_for_charclass`, `regex_for_group` |
| 9 | `model_emitter.py` | Class-body skeleton: `CANONICAL_IMPORTS`, class stubs, `_field_type_skeleton`, `_repr_iritem` |
| 10 | `model_emitter.py` | `_field_type` — `Annotated[str, StringConstraints(pattern=...)]` for pattern fields |
| 11 | `model_emitter.py` | `_is_pure_literal_alternation` + `_emit_literal_alternation` — `Literal[...]` |
| 12 | `model_emitter.py` | Module-level type alias block via `collect_aliases`; `regex_to_alias` substitution |
| 13 | `model_emitter.py` | `__grammar__ = RuleSpec(...)` moved to module footer (out of class body) |
| 14 | `__init__.py` | `codegen(specs, stem) -> dict[str, type]` — write + import + return classes |

---

## Task 8 — `aliases.py`

**`PatternAlias`** (`frozen dataclass`):
```python
PatternAlias(name: str, regex: str)
```
- `name`: CamelCase Python identifier (e.g. `Digit`, `Digits`)
- `regex`: anchored regex string (e.g. `^[0-9]+$`)

Emitted as: `Digits = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]`

**`collect_aliases(specs: list[NewRuleSpec]) -> list[PatternAlias]`**:
- Walks all `IrItem` nodes in all specs (including inside `IrGroup` arms via `_walk_items` / `_walk_item` / `_walk_seq`)
- Records one alias per unique regex (deduped on regex, not name; first-appearance wins for naming)
- Naming: Tier-2 `_CHARCLASS_NAMES` lookup on bracket-form-with-quantifier (e.g. `[0-9]+` → `digits` → `Digits`)
- Tier-3 fallback: `Pattern`, `Pattern2`, `Pattern3`, … (CamelCase, distinct from `_field_map`'s `head` / `part_N` lowercase positional names)
- Pure-literal `IrGroup` items (no `IrRuleRef` descendants via `_has_ruleref`) → `regex_for_group`
- `IrCharClass` items → `regex_for_charclass`
- `IrRuleRef` anywhere in an `IrGroup` makes the whole group ineligible

**Public regex helpers** (used by `model_emitter.py`):
- `regex_for_charclass(cc, q) -> str` — anchored, e.g. `^[0-9]+$`, `^[^"]$`, `^[a-z]?$`, `^[0-9]{0,15}$`
- `regex_for_group(grp, q) -> str` — anchored, e.g. `^([a-h]x)?$`, `^(foo|bar)+$`. Literal characters inside are `re.escape`'d.

---

## Task 9 — `model_emitter.py` skeleton

**`CANONICAL_IMPORTS`** (CQ #4): single string emitted unconditionally at module top. Imports `from __future__`, `typing` (`ClassVar, List, Literal, Optional, Union`), `pydantic` (`Field, StringConstraints`), `typing_extensions.Annotated`, `lexic.base.GrammarModel`, the full IR AST surface from `lexic.ir.nodes`, and `RuleSpec` from `lexic.ir.spec`.

**`emit_module_source(specs, *, stem) -> str`**: top-level entry point. Order: docstring → imports → alias block (Task 12) → classes → footer registration (Task 13).

**`_repr_iritem(item)`** (CQ #1): produces real Python for every IR shape — `IrItem(IrLiteral('x'), Quantifier(1, 1))`, `IrItem(IrCharClass('0-9', negated=False), …)`, `IrItem(IrGroup(IrAlternation(arms=(…,))), …)`. Never emits `# FIXME`.

**Type rules in `_field_type` (after Task 10):**
- `IrCharClass` → `regex_to_alias.get(regex, inline Annotated[...])`
- `IrGroup` (no rulerefs) → ditto via `regex_for_group`
- `IrLiteral` → `str`
- `IrRuleRef` → `cls` / `Optional[cls]` / `List[cls]` based on quantifier (`(1,1)`, `(0,1)`, else)
- `IrGroup` (with rulerefs, all arms single-ruleref) → `Union[A, B, ...]` of arm class names

---

## Task 14 — `codegen` entry point

```python
codegen(specs: list[RuleSpec], stem: str) -> dict[str, type]
```

- Writes `generated/<stem>.py` (overwrites; cwd-relative or repo-root resolved via `_resolve_generated_dir`)
- Imports the module via `importlib.util.spec_from_file_location` (purges `sys.modules[f"generated.{stem}"]` first)
- Returns `{spec.class_name: cls}` for every spec whose class loaded
- **No `flavour` parameter.** Codegen is flavour-agnostic; the spec already carries the IR.

---

## Target generated-code shape

From `prototyping/curr/2_LEXIC_GENERATED_CODE_PROPOSAL.md` (items 1–5):

1. Module-level type aliases (one per unique pattern — from `collect_aliases`)
2. `Annotated[str, StringConstraints(pattern=...)]` for char-class / pattern fields
3. `Literal["a", "b", ...]` for pure-literal alternations (every arm = single `IrLiteral` with `Quantifier(1,1)`)
4. Field declarations in grammar order with names from `field_map`
5. `__grammar__ = RuleSpec(...)` at module footer per class, **not** in class body
