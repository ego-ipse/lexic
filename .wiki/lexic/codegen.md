# codegen — IR-Native Code Generator

> **SUPERSEDED (2026-07-18).** `src/lexic/codegen/` is DELETED. The
> grammar→grammar passes and the binding view now live in the `compile/`
> package (`compile/pipeline/passes.py`, `compile/pipeline/binding.py`); classes are
> synthesized at runtime via `type()` in `compile/pipeline/synthesis.py` (no
> source-emit `model_emitter.py`, no automatic file write);
> `compile/module/export.py` renders an IMPORTABLE twin module on explicit request
> (`export_module` — see [[generated-modules]]). See [[public-api]] and
> [[architecture]] for the current shape. The content below is historical.

**When to load:** historical reference only — for current codegen-grammar passes, binding view, and class synthesis see [[public-api]] / [[architecture]] (`compile/` package).

See also: [[architecture]], [[ir-shapes]], [[field-naming]], [[decisions]]

Renamed from `new-codegen.md` (2026-07-04) — that page described the `new_codegen/` scaffold built against `NewRuleSpec` during the May 2026 Lark cutover; `lexic.codegen` has since been rebuilt a second time (2026-07-03/04) to be **IR-native**: it takes a canonical `IrAst` directly, with no `RuleSpec` middle layer at all. This page describes the current shape.

---

## What it builds

`lexic.codegen` is build-time only: canonical `IrAst` + a codegen-pass grammar + a binding view → a Python module string, written to `generated/<stem>.py` and loaded back as classes. It never imports `lexic.grammars` (no flavour adapters needed — codegen is IR-native) and never imports `lexic.parsing` (the engine is a leaf w.r.t. codegen too).

```
canonical IrAst ──► build_codegen_grammar (passes.py) ──► THE codegen grammar
                                                                  │
                                    ┌─────────────────────────────┤
                                    ▼                              ▼
                         compute_binding (binding.py)      emit_module_source (model_emitter.py)
                         list[RuleBinding]  ───────────────────────┘
                                    │
                                    ▼
                        codegen(canonical, codegen_grammar, binding, stem)
                        → generated/<stem>.py + dict[str, type]
```

## `codegen/passes.py` — grammar→grammar codegen passes

Three language-preserving-for-instances rewrites, composed as `build_codegen_grammar(ast) = relax_non_semantic(hoist_arms(hoist_groups(ast)))`:

- **`hoist_groups(ast)`** — a quantified ref-bearing group (an `IrAlternation` atom containing an `IrRuleRef` anywhere, via `has_ruleref`) becomes a named helper rule (`<rule>-item`, `<rule>-item2`, …), so every repeated model field is backed by a rule of its own. Pure-literal groups (no ruleref anywhere) are left intact regardless of quantifier — codegen treats them as regex patterns instead. Implemented as an `IrTransformer` subclass (`_HoistTransformer`) whose `name_set` is shared across per-rule dispatchers (globally unique helper names) and whose `helpers` list is fresh per rule.
- **`hoist_arms(ast)`** — every non-empty alternation arm that is not already a single unit ruleref hoists to a `<rule>-arm<N>` sequence rule, inserted right after its alternation (`N` counts non-empty arms from 1; empty arms stay in place — a zero-kid match discriminates them at fold time). Restores the "every non-empty alternation arm is a single unit ruleref" premise `compute_binding`'s parent inference and `parsing/fold.py`'s positional fold both rest on. Raises `UnsupportedConstructError` on an arm-name collision.
- **`relax_non_semantic(ast)`** — `min=0` on every **arm-level** ref to a rule named in `ast.non_semantic` (refs inside inline groups keep their bounds — matches the old derive-level relaxation).

## `codegen/binding.py` — the binding view

`compute_binding(codegen_grammar) -> list[RuleBinding]` is the open-table successor of the retired `derive_specs`'s classify/parents/naming jobs. `RuleBinding(rule_name, class_name, parent_class_name, kind, fields: dict[str, IrBind])`, one per rule, in emission order (`ir/order.py`'s `RuleOrder.ordered_parents_first` — parent-edge policy, so a base class is always emitted before its subclasses).

- **Kind** (`classify_rule`): `"value_str"` (no `IrRuleRef` anywhere), `"alternation"` (>1 non-empty arm after `hoist_arms`), else `"sequence"`.
- **Parent inference** (`_parent_rules`): a rule referenced as a unit-ref alternation arm gets that alternation as its parent class; everything else parents `GrammarModel` directly. Post arm-hoisting this covers both original single-ref arms and synthesized `-arm<N>` rules.
- **Field naming** (`bind_fields`, three-tier cascade — see [[field-naming]]): rule-ref → rule name; pattern-library lookup (`CHARCLASS_NAMES`/`LITERAL_NAMES`, hosted in this module, keyed by **canonical** char-class pattern since the binding view reads the post-`canonicalize` grammar); positional fallback (`head`, `part_2`, …). Structural (unquantified) literals get no field. Collisions get a numeric suffix (`ws`, `ws2`, …).
- **Fold mode** (`mode_for`): derived from the bound item's atom + quantifier, dispatched via an `IrDispatch` table (`_MODE`) — `text` (literal/charclass), `gtext` (literal-only group), `model`/`models` (ruleref or ref-bearing group, by quantifier `hi`).
- **`class_name_for`** absorbs the old `to_pascal` (hyphens/underscores → PascalCase; a Python keyword gets a `_` suffix).
- **`has_ruleref`** — cached (`@cache`), short-circuiting `IrVisitor` with an `IrReturn` body on `IrRuleRef` (the find-first idiom — see [[ir-shapes]]).

All of the naming/mode logic is built as open `IrDispatch`/`IrTypeMap` tables with raising defaults (`_HINT`, `_TIER2`, `_MODE`) — no closed `isinstance` ladder, no `dict[type, ...]` keying. This is where the open-set consumer rework (queued since the primitive-node migration) actually landed for codegen's classification/naming/mode jobs.

## `codegen/model_emitter.py` — the emitter

`emit_module_source(canonical, codegen_grammar, binding, *, stem) -> str`. Per class:

- **Fields** — `Annotated[<type>, IrBind(item, mode[, semantic])]`, `= None` default when the wrapped type is `Optional[...]`. Base type dispatches on `(mode, atom kind)`: `model`/`models` → the ref's class (or a `Union[...]` for a group with multiple single-ref arms, or plain `str` if no clean ref arm exists); `gtext`/`text` on an `IrCharClass`/pattern group → a `StringConstraints`-patterned type (see `PatternAlias` below); `text` on `IrLiteral` → plain `str`. Wrapped `List[...]` for `models`; wrapped `Optional[...]` when the item's own quantifier is optional, or unconditionally when the rule carries an empty alternate arm (every field of the non-empty arm may then be absent).
- **`value_str` classes** — a plain `value: <type>` field, **no `IrBind`** (the fold keys off `kind`, not a bind, for this case). A lone single-item arm takes that atom's pattern type; a pure-literal alternation becomes `Literal["a", "b", ...]`; anything else is flat `str`.
- **`alternation` classes** — no fields at all (a pass-through; the matched arm's sub-model identifies itself at fold time).
- **`__grammar__: ClassVar[IrRule]`** footer per class — the class's own rule from the **codegen** grammar (post-pass: this is the shape the class structurally IS and what `to_text()` walks).
- **Module footer** — `GRAMMAR: IrAst` = the **canonical** (pre-pass) grammar (the transpile/re-emit source — what the user's grammar IS) + `START: str`.

`CANONICAL_IMPORTS` is a fixed string emitted unconditionally at module top (`from __future__ import annotations`, `typing` names, the pattern-constrained string type, `lexic.base.GrammarModel`, the full IR-AST surface from `lexic.ir`) — no per-module import inference, no `# FIXME` placeholders (repr-is-codegen on every IR node means `__grammar__`/`GRAMMAR` always render real, re-importable Python).

## `codegen/aliases.py` — pattern alias hoisting

**`PatternAlias`** (`frozen dataclass`):
```python
PatternAlias(name: str, regex: str)
```
Emitted as a module-level type alias: `Digit = Annotated[str, StringConstraints(pattern=r"^[0-9]$")]`.

**`collect_aliases(grammar: IrAst) -> list[PatternAlias]`**:
- Walks every item of every rule arm in the (post-pass) codegen grammar via a stateful `IrVisitor` subclass (`_PatternAliasVisitor`), tracking a stack of "ruleref seen" frames — one per enclosing group — to distinguish a pure-pattern group (no `IrRuleRef` descendant, alias-eligible) from a ref-bearing one (not eligible; propagates dirty to its enclosing group).
- Records one alias per unique regex (deduped on regex, not name; first appearance wins for naming).
- Naming: Tier-2 `CHARCLASS_NAMES` lookup (imported from `codegen/binding.py`) on the bracket-only form (no quantifier suffix), CamelCased; falls back to `"Pattern"`. Different regexes resolving to the same base name get a numeric suffix on later occurrences (`Digit`, `Digit2`).
- `regex_for_charclass(cc, q, *, negated=False) -> str` / `regex_for_group(grp, q) -> str` — anchored regex builders also consumed directly by `model_emitter.py` for non-aliased inline `Annotated` types.
- `_bounds_to_suffix(lo, hi)` — quantifier → regex suffix (`""`/`?`/`*`/`+`/`{m,n}`), absorbed from the retired `utils/quantifiers.py`.

## `codegen/__init__.py` — the entry point

```python
codegen(canonical: IrAst, codegen_grammar: IrAst, binding: list[RuleBinding], stem: str) -> dict[str, type]
```

Renders the module source, writes `generated/<stem>.py` (ruff-formatted), imports it (purging any stale `sys.modules[f"generated.{stem}"]` first), calls `model_rebuild()` on every loaded class (**required** — under `from __future__ import annotations` a field's `IrBind` metadata only resolves to real objects after the deferred annotations are evaluated), and returns `{class_name: cls}` for every class the binding names. **No `flavour` parameter** — codegen is flavour-agnostic and needs no flavour adapters at all (unlike the pre-cutover shape, which is why `lexic.codegen` no longer imports `lexic.grammars`).
