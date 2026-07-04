# Field Naming Policy

**When to load:** implementing or debugging `bind_fields`; adding a new atom type that needs a field name; investigating a field name collision; understanding `_HINT` vs `_TIER2` difference.

See also: [[ir-shapes]], [[codegen]]

Source: `codegen/binding.py` (`bind_fields`, `CHARCLASS_NAMES`, `LITERAL_NAMES`, `_HINT`, `_TIER2`, `mode_for`). The retired `ir/naming.py` (`assign_field_names`) and `ir/derive.py` (`_field_map`, `_FIELD_BASE`, `_ATOM_HINT`) are gone (2026-07-04 RuleSpec→IR-native codegen cutover) — this is the same three-tier cascade, moved wholesale into the binding view and rebuilt as open `IrDispatch`/`IrTypeMap` tables instead of closed `dict[type, …]` lookups.

## Three-tier cascade

### Tier 1 — Rule references

`IrRuleRef(name)` → field name = `name` with hyphens replaced by underscores.
Collisions disambiguated by suffix: `ws`, `ws2`, `ws3`, …

### Tier 2 — Pattern library

**`CHARCLASS_NAMES`** (8 entries — ground truth, do not add without discussion). Keys are **canonical** char-class patterns: the binding view reads the post-`canonicalize` codegen grammar, so members are already deduped, ranges coalesced, and sorted by codepoint — a pre-canonical spelling (e.g. `[a-fA-F0-9]` for hex) never appears as a key because it can never appear as input:

| Pattern | Name |
|---|---|
| `[0-9]` | `digit` |
| `[0-9A-Fa-f]` | `hex` |
| `[a-f]` | `hex_lower` |
| `[A-F]` | `hex_upper` |
| `[a-z]` | `lower` |
| `[A-Z]` | `upper` |
| `[A-Za-z]` | `letter` |
| `[0-9A-Z_a-z]` | `alnum` |

Falls back to `_pattern_slug` (strip brackets, lowercase, replace non-alnum with `_`, collapse underscore runs, strip leading digits with a `cc_` prefix, truncate to 12 chars) — empty string on total failure, then `"cc"`.

**`LITERAL_NAMES`** (for quantified literals):

| Value | Name |
|---|---|
| `-`, `+` | `sign` |
| `.` | `dot` |
| `,` | `comma` |
| `:` | `colon` |
| `;` | `semicolon` |
| `=` | `eq` |
| `x`, `e`, `E` | `x`, `e`, `E` |

Falls back to `_literal_token` (replace non-alnum with `_`, strip, lowercase, truncate to 12) then `"lit"`.

### Tier 3 — Positional fallback

First unmatched pattern atom → `head`. Subsequent → `part_2`, `part_3`, …

## Skip conditions

- **Unquantified `IrLiteral`** (`quantifier == IrQuantifier(1, 1)`, `_is_structural_literal`) → no field, never reaches Tier 3.
- **`IrAlternation` as a field-less pass-through** (an `"alternation"`-kind rule after `hoist_arms`) → no field — but an inline group *as an item's atom* (a ref-bearing or literal-only group inside a `"sequence"`-kind rule) IS bound, via Tier 2's `_group_field`/`_group_hint` bodies (`"kind"` for ref-bearing, its first atom's hint for literal-only, `None`/`"inline"` fallback → Tier 3).
- Quantified `IrLiteral` (`?`, `+`, `*`, `{m,n}`) → always names via Tier 2 (`_literal_token`), never Tier 3.

## Internal tables — open `IrDispatch` tables, not closed dicts

> **2026-07-04 note:** naming is now built as open `IrDispatch`/`IrTypeMap` tables (`_HINT`, `_TIER2` in `codegen/binding.py`) with a raising default, rather than the retired `_ATOM_HINT`/`_FIELD_BASE` closed `dict[type, …]` lookups — this is where the deferred open-set consumer rework (see [[decisions]]) actually landed for field naming. The tables still key on the str-leaf directly (the leaf IS-A `str`, so `LITERAL_NAMES.get(leaf)` / `CHARCLASS_NAMES.get(f"[{cc.pattern()}]")` work without a `.value`).

**`_HINT`** — used by `_group_hint` to name the first child of a literal-only group. Always yields a name (`_literal_field`/`_ref_field`/`_charclass_hint`/`_group_hint` bodies cover every atom type; an unregistered type raises via `IrDispatch`'s default, rather than silently returning `None`). A ref-bearing group → `"kind"`; a literal-only group → delegates to its first atom's hint.

**`_TIER2`** — used by `bind_fields` for top-level field naming. May yield `IrNone`. `IrNone` means no Tier-2 match; `bind_fields` falls through to Tier-3 positional naming (`head`, `part_N`). This is the key contract difference from `_HINT`.

`IrAlternation` in `_TIER2` → `_group_field`: ruleref group → `"kind"`, a good literal hint → that hint, a bad hint (`"inline"`, `"lit"`, `"cc"`) → `IrNone` (Tier-3 fallback).

## Fold mode — a sibling table, not part of naming

`mode_for(item)` (also `codegen/binding.py`) derives the field's fold mode (one of `BIND_MODES` — `text`/`gtext`/`model`/`models`, see [[ir-shapes]]'s `IrBind` section) from the same item, via its own `_MODE` `IrDispatch` table dispatched on the atom with the owning `IrItem` riding the argument channel (so the ref/group bodies can read the quantifier to decide `model` vs `models`). Naming and mode are computed independently — a field's name never encodes its mode.

## Collision handling

`counts[name]` increments on each use. First occurrence → `name`; subsequent → `name2`, `name3`, … Counters reset per rule (per `bind_fields` call).

## Future

The queued open-set consumer rework (see [[decisions]], [[ir-shapes]]'s open-set note) still has closed-set holdouts elsewhere (`generate.py`, parts of `codegen/model_emitter.py`) — field naming itself is already open-table.
