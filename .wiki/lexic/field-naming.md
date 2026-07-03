# Field Naming Policy

**When to load:** implementing or debugging `_field_map`; adding a new atom type that needs a field name; investigating a field name collision; understanding `_ATOM_HINT` vs `_FIELD_BASE` difference.

See also: [[ir-shapes]]

Source: `ir/naming.py` (`assign_field_names`, `CHARCLASS_NAMES`, `_LITERAL_NAMES`) and `ir/derive.py` (`_field_map`, `_FIELD_BASE`, `_ATOM_HINT`).

## Three-tier cascade

### Tier 1 — Rule references

`IrRuleRef(name)` → field name = `name` with hyphens replaced by underscores.
Collisions disambiguated by suffix: `ws`, `ws2`, `ws3`, …

### Tier 2 — Pattern library

**`CHARCLASS_NAMES`** (9 entries — ground truth, do not add without discussion):

| Pattern | Name |
|---|---|
| `[0-9]` | `digit` |
| `[0-9a-fA-F]` | `hex` |
| `[a-fA-F0-9]` | `hex` (both orderings normalise to `hex`) |
| `[a-f]` | `hex_lower` |
| `[A-F]` | `hex_upper` |
| `[a-z]` | `lower` |
| `[A-Z]` | `upper` |
| `[a-zA-Z]` | `letter` |
| `[a-zA-Z_0-9]` | `alnum` |

Falls back to `_sanitize_pattern` (strip brackets, lowercase, replace non-alnum with `_`, strip leading digits with `cc_` prefix, truncate to 12 chars). Returns `""` on failure → falls to Tier 3.

**`_LITERAL_NAMES`** (for quantified literals):

| Value | Name |
|---|---|
| `-`, `+` | `sign` |
| `.` | `dot` |
| `,` | `comma` |
| `:` | `colon` |
| `;` | `semicolon` |
| `=` | `eq` |
| `x`, `e`, `E` | `x`, `e`, `E` |

Falls back to `_ascii_token` (replace non-alnum with `_`, lowercase, truncate to 12) then `"lit"`.

### Tier 3 — Positional fallback

First unmatched pattern atom → `head`. Subsequent → `part_2`, `part_3`, …

## Skip conditions

- **Unquantified `IrLiteral`** (`quantifier=(1,1)`) → no field, never reaches Tier 3.
- **`AlternationAtom`** → no field.
- Quantified `IrLiteral` (`?`, `+`, `*`, `{m,n}`) → goes through Tier 2 via `_LITERAL_NAMES`.

## Internal tables

> **V2 note (2026-06-04):** these tables key on the str-leaf directly — the leaf IS-A `str`, so `LITERAL_NAMES.get(leaf)` / `CHARCLASS_NAMES.get(_bracketed(leaf))` work without a `.value`. `_ATOM_HINT`/`_FIELD_BASE` are `dict[type, …]` closed-set tables; they are prime targets of the deferred open-set consumer rework (see [[decisions]]) — treat them as legacy, not the target shape.

**`_ATOM_HINT`** (`derive.py`) — used by `_group_hint` to name the first child of a literal-only group. Always returns `str` (sanitize/fallback ensures no `None`). `IrGroup` with rulerefs → `"kind"`; literal-only group → delegates to content.

**`_FIELD_BASE`** (`derive.py`) — used by `_field_map` for top-level field naming. Returns `str | None`. `None` means no Tier-2 match; `_field_map` falls through to Tier-3 positional naming. This is the key contract difference from `_ATOM_HINT`.

`IrGroup` in `_FIELD_BASE` → `_group_field_base`: ruleref group → `"kind"`, good literal hint → the hint, bad hint (`"inline"`, `"lit"`, `"cc"`) → `None` (Tier-3 fallback).

## Collision handling

`counts[base]` increments on each use. First occurrence → `base`; subsequent → `base2`, `base3`, … Counters reset per rule (per `_field_map` call).

## Future

Slice C replaces this policy with a four-tier cascade: type alias → pattern library → structural positional → sidecar YAML. `ir/naming.py` is intentionally isolated so it can be swapped with minimal blast radius.
