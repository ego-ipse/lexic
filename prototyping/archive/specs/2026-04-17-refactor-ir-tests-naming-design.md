# Lexic — Refactor Design: IR, Tests, Semantic Naming

**Date:** 2026-04-17
**Status:** Approved
**Scope:** Parts A, B, C (Part D — S04 translation — explicitly out of scope but kept in mind)

---

## Overview

Three sequential parts, each leaving the test suite green before the next begins:

- **Part A** — Package restructuring, IR refactor, atom split, emitter simplification, transformer extraction
- **Part B** — Test restructuring into unit/integration/property layers with a grammar-agnostic generator
- **Part C** — Semantic field naming for `CharClassAtom` fields

---

## Part A — IR Refactor and Package Restructuring

### A1. Package layout: `src/lexic/`

All source moves from the flat `src/` layout into `src/lexic/` (src-layout, the modern Python packaging standard). This makes `pip install lexic` produce an importable `lexic` package.

```
src/lexic/
  __init__.py          # public API: parse, codegen, generate
  base.py
  parse.py
  generate.py          # new — see Part B
  ir/
    __init__.py        # re-exports all atoms + RuleSpec
    atoms.py           # all 7 atom dataclasses + Atom union
    spec.py            # RuleSpec only
  utils/
    __init__.py
    escapes.py         # decode_gbnf_escapes() — single source of truth
    quantifiers.py     # bounds_to_quantifier() — single source of truth
  codegen/
    __init__.py        # codegen() entry point
    ast.py             # unchanged (do not touch)
    parser.py          # unchanged (do not touch)
    ir_builder.py
    model_emitter.py
    gbnf_emitter.py
    lark_builder.py    # grammar string only after transformer extraction
    transformer.py     # new — extracted from lark_builder.py
```

`pyproject.toml` simplifies to:
```toml
[tool.hatch.build.targets.wheel]
packages = ["src/lexic"]
```

The `force-include` hack for `base.py` and `parse.py` is removed.

**Public API** (`src/lexic/__init__.py`):
```python
from lexic.parse import parse
from lexic.codegen import codegen
from lexic.generate import generate
```

**Import graph** (no cycles, clean dependency direction):
```
lexic.ir/        ← no internal dependencies
lexic.utils/     ← no internal dependencies
lexic.base       ← lexic.ir, lexic.utils
lexic.codegen/   ← lexic.ir, lexic.utils
lexic.parse      ← lexic.codegen, lexic.base
lexic.generate   ← lexic.ir
generated/*.py   ← lexic.ir, lexic.base  (not lexic.codegen)
```

`lexic.codegen/` is purely build-time. `lexic.base` is purely runtime. `lexic.ir` and `lexic.utils` are shared infrastructure with no back-edges.

---

### A2. Atom types (`src/lexic/ir/atoms.py`)

Seven dataclasses replace the current four. The `Atom` union is the only type downstream code needs.

```python
@dataclass
class LiteralAtom:
    value: str
    # Structural glue — always present, never a field.
    # e.g. "=" in  expr "=" term

@dataclass
class CharClassAtom:
    pattern: str        # bracket expression exactly as in GBNF: "[a-z]", "[0-9]"
    min: int
    max: int | None
    # A true character class. Always a field.

@dataclass
class QuantifiedLiteralAtom:
    value: str          # raw content without quotes: "-" for "-"?
    min: int
    max: int | None
    # A quoted literal with a quantifier — must be a field.
    # Replaces the CharClassAtom('"-"', 0, 1) kludge.

@dataclass
class InlineRegexAtom:
    regex: str          # ready for Lark /regex/ terminal
    gbnf: str           # ready for GBNFEmitter: ("true"|"false"|"null")
    min: int
    max: int | None
    # An inlined group compiled at IR build time.
    # Both forms stored; each emitter picks its field.
    # Replaces CharClassAtom('("true"|"false"|"null")', ...) and
    # the _normalize_charclass_pattern_for_gbnf hack.

@dataclass
class RuleRefAtom:
    rule_name: str
    min: int
    max: int | None
    # Unchanged.

@dataclass
class AlternationAtom:
    arm_rule_names: list[str]
    # ONLY valid inside a RuleSpec with kind="alternation".
    # field_map is always {} when this atom is present.
    # Never appears in a sequence.

@dataclass
class InlineAlternationAtom:
    arm_rule_names: list[str]
    # ONLY valid inside a RuleSpec with kind="sequence".
    # Always in field_map. No quantifier — quantified inline alternations
    # are promoted to helper rules (existing behaviour).
    # e.g. (pawn | nonpawn | castle) → InlineAlternationAtom(["pawn","nonpawn","castle"])

Atom = (LiteralAtom | CharClassAtom | QuantifiedLiteralAtom | InlineRegexAtom
        | RuleRefAtom | AlternationAtom | InlineAlternationAtom)
```

**Invariants** (enforced by IRBuilder, verified by unit tests):

| Atom | In `field_map`? | Valid `kind` |
|---|---|---|
| `LiteralAtom` | never | any |
| `CharClassAtom` | always | sequence |
| `QuantifiedLiteralAtom` | always | sequence |
| `InlineRegexAtom` | always | sequence, value_str |
| `RuleRefAtom` | always | sequence |
| `AlternationAtom` | never | alternation only |
| `InlineAlternationAtom` | always | sequence only |

---

### A3. IRBuilder changes (`src/lexic/codegen/ir_builder.py`)

**`_seq_to_atoms` — updated atom construction:**

| Situation | Was | Now |
|---|---|---|
| `Literal` with no quantifier | `LiteralAtom` | `LiteralAtom` (unchanged) |
| `Literal` with `?`/`*`/`+` | `CharClassAtom('"-"', 0, 1)` kludge | `QuantifiedLiteralAtom("-", 0, 1)` |
| Group — all arms pure literals | `CharClassAtom("(a\|b)", ...)` | `InlineRegexAtom(regex, gbnf, ...)` |
| Group — all arms single rulerefs, no quantifier | `AlternationAtom` (wrong contract) | `InlineAlternationAtom(arm_rule_names)` |

**`_group_to_regex` → `_build_inline_regex`:**
Returns `InlineRegexAtom` instead of a raw string. Computes both `regex` and `gbnf` fields at build time so no emitter ever needs to convert between them.

**Bug fix — quantifier loss in inline literal alternation:**
The current inline-arm loop uses `it.atom.pattern` but silently drops `it.quantifier` on `CharClass` items inside arm sequences. Example: `[0-9]{0,15}` inside `([0-9] | [1-9] [0-9]{0,15})` is emitted as `[0-9]` in the generated `Number` class. Fix: append `it.quantifier or ""` after each pattern item in `_to_regex`.

**`_topo_sort` fix:**
Remove the post-hoc pop-and-reinsert. Seed the DFS traversal with the root rule first:
```python
if "root" in by_cls:
    visit("Root")
for s in specs:
    visit(s.class_name)
```

**`_classify` is unchanged.** Classification logic is independent of atom construction and can be improved separately.

---

### A4. Emitter simplifications

Each emitter becomes a clean `match` dispatch over the atom union. No shape-sniffing.

**`GBNFEmitter`** — `_normalize_charclass_pattern_for_gbnf` is deleted entirely. `_atom_to_gbnf` dispatches on atom type, using `InlineRegexAtom.gbnf` directly.

**`LarkBuilder`** — `is_complex_regex` heuristic deleted. `_atom_to_lark` dispatches on atom type, using `InlineRegexAtom.regex` directly.

**`ModelEmitter`** — `_field_type` gains `InlineAlternationAtom` → `Union[A, B, C]` and `QuantifiedLiteralAtom`/`InlineRegexAtom` → `str`. The three repeated scanning passes (`needs_list`, `needs_optional`, `needs_union`) collapse into one.

**`src/lexic/utils/quantifiers.py`** — `bounds_to_quantifier(min, max) -> str` replaces the duplicated `_bounds_to_quantifier`/`_bounds_to_gbnf_quantifier` in both emitters.

**`src/lexic/utils/escapes.py`** — `decode_gbnf_escapes(s) -> str` replaces the duplicated `_decode_gbnf_escapes` in `lark_builder.py` and the inline decoder in `base.py`.

---

### A5. Transformer extraction

`_build_instance`, `_flatten`, and all closure factories (`make_abstract`, `make_value`, `make_seq`, `ws_method`) move from `lark_builder.py` to `src/lexic/codegen/transformer.py`.

`LarkBuilder.build_transformer` becomes a one-liner:
```python
def build_transformer(self, classes: dict[str, type]) -> Transformer:
    from lexic.codegen.transformer import build_transformer
    return build_transformer(self._specs, classes)
```

`lark_builder.py` shrinks from ~410 lines to ~100, responsible only for grammar string generation.

---

### A6. File change summary

```
ADDED:
  src/lexic/__init__.py
  src/lexic/ir/__init__.py
  src/lexic/ir/atoms.py
  src/lexic/ir/spec.py
  src/lexic/utils/__init__.py
  src/lexic/utils/escapes.py
  src/lexic/utils/quantifiers.py
  src/lexic/codegen/transformer.py

MOVED (with import updates):
  src/*.py          → src/lexic/*.py
  src/codegen/**    → src/lexic/codegen/**

DELETED:
  src/codegen/ir.py   (replaced by src/lexic/ir/)

REGENERATED (automatically on next codegen() call):
  generated/*.py      (imports updated: lexic.base, lexic.ir)
```

---

## Part B — Test Restructuring

### B1. Folder structure

`tests/unit/` mirrors `src/lexic/` exactly. Integration and property tests are flat.

```
tests/
  unit/
    lexic/
      ir/
        test_atoms.py
        test_spec.py
      utils/
        test_escapes.py
        test_quantifiers.py
      codegen/
        test_ast.py
        test_parser.py
        test_ir_builder.py
        test_model_emitter.py
        test_gbnf_emitter.py
        test_lark_builder.py
        test_transformer.py      ← new, enabled by extraction
      test_base.py
      test_generate.py
  integration/
    test_codegen.py
    test_parse.py                ← complex cases (see B3)
    test_gbnf_roundtrip.py
  property/
    conftest.py                  ← session-scoped spec fixtures
    test_roundtrip.py            ← hypothesis-driven, all 7 grammars
```

Unit tests use hand-crafted `RuleSpec` objects and inline GBNF strings — no grammar files, no file I/O. Each test file is in strict 1:1 correspondence with its source module.

Integration tests exercise the full pipeline (`codegen()`, `parse()`) against grammar files.

Property tests generate random valid strings via `generate()` and assert `parse(x).to_text() == x`.

---

### B2. Generator (`src/lexic/generate.py`)

A first-class library component, not a test helper. Grammar-agnostic: works for any `RuleSpec` dict, including user-supplied grammars.

```python
def generate(
    rule_name: str,
    specs: dict[str, RuleSpec],
    *,
    rng: random.Random | None = None,
    max_depth: int = 5,
) -> str:
    """Generate a valid string for rule_name from a compiled RuleSpec dict.

    Works with any grammar — pass the result of IRBuilder.build() keyed by
    rule_name. max_depth caps recursion for self-referential rules.
    rng is accepted explicitly so hypothesis can seed it via st.integers().
    """
```

Walk order:
- `kind="alternation"` → pick one arm at random
- `kind="value_str"` → generate from atoms
- `kind="sequence"` → generate each atom in order
- `RuleRefAtom(min, max)` → generate `pick(min, min(max or 2, 2))` repetitions
- `CharClassAtom` / `QuantifiedLiteralAtom` → sample from pattern using `exrex` (added as a dev dependency)
- `InlineRegexAtom` → pick one arm from `gbnf` field
- `InlineAlternationAtom` → pick one arm, recurse

Exposed in `lexic.__init__` as a public API. Designed so R005 can reuse or extend it.

---

### B3. Complex integration test cases (additions to `test_parse.py`)

| Grammar | New cases |
|---|---|
| `arithmetic` | multi-assignment, nested parens `x=(a+(b*c))\n`, multi-char idents |
| `json_ws` | string with `\"` and `\\` escapes, `null`/`true`/`false`, decimal + exponent numbers, nested objects |
| `json_arr` | multi-element array, nested arrays, mixed value types |
| `chess` | promotion `e8=Q`, capture `exd5`, check `Nf3+`, castling `O-O`, three-move games |
| `c` | **currently zero parse tests** — add: function declaration, while loop, for loop, if/else, function call, multi-statement body |
| `japanese` | full multi-char sequence, boundary hiragana characters |
| `list` | ten-item list, items containing spaces |

---

### B4. Property test shape (`tests/property/test_roundtrip.py`)

```python
@pytest.fixture(scope="session")
def arithmetic_specs():
    rules = parse_gbnf((GRAMMAR_DIR / "arithmetic.gbnf").read_text())
    return {s.rule_name: s for s in IRBuilder(rules).build()}

@given(st.integers(0, 2**32 - 1))
def test_arithmetic_roundtrip(seed, arithmetic_specs):
    rng = random.Random(seed)
    text = generate("root", arithmetic_specs, rng=rng)
    inst = parse(text, GRAMMAR_DIR / "arithmetic.gbnf")
    assert inst.to_text() == text
    assert parse(inst.to_text(), GRAMMAR_DIR / "arithmetic.gbnf").model_dump() == inst.model_dump()
```

Same pattern parametrized across all 7 grammars.

---

## Part C — Semantic Field Naming

### C1. Approach: lookup table + pattern sanitization + quantifier-role fallback

`_assign_field_names` in `ir_builder.py` replaces the `_CC_NAMES = ["first", "second", ...]` scheme with a three-tier lookup for `CharClassAtom` fields. Same scheme applied to `QuantifiedLiteralAtom` (using `value` content) and `InlineRegexAtom` (using `gbnf` arm content).

**Tier 1 — known pattern table:**
```python
_CHARCLASS_NAMES: dict[str, str] = {
    "[0-9]":          "digit",
    "[1-9]":          "digit",
    "[0-9a-fA-F]":    "hex",
    "[a-f]":          "hex_lower",
    "[a-z]":          "lower",
    "[A-Z]":          "upper",
    "[a-zA-Z]":       "alpha",
    "[a-z0-9_]":      "alnum",
    "[a-zA-Z_]":      "name_start",
    "[a-zA-Z0-9_]":   "alnum",
    "[+\\-*/]":       "op",
    "[+#]":           "annotation",
    "[ \\t\\n]":      "ws",
    "[ \\t]":         "hspace",
    "[^\\n]":         "non_newline",
}
```

**Tier 2 — pattern sanitization:**
Strip `[`, `]`, `^`; replace `-` with `_`; lowercase; truncate to 12 chars.
- `[NBKQR]` → `nbkqr`
- `[a-h]` → `a_h`
- `[1-8]` → `1_8`
- `[eE]` → `ee`

**Tier 3 — quantifier role fallback** (when tiers 1–2 produce empty string):
- `max is None` → `tail`
- `min == 0, max == 1` → `opt`
- otherwise → `cc` (last resort, never `first`/`second`)

**Collision handling:** same as existing `RuleRefAtom` logic — first occurrence keeps the base name, subsequent get `name2`, `name3`, etc.

**`QuantifiedLiteralAtom` naming:** use the `value` content directly as name hint — `"-"` → `sign`, `"x"` → `x`, `"."` → `dot`. A small lookup maps common single-char literals to readable names.

**`InlineRegexAtom` naming:** extract the first arm from `gbnf` and sanitize, e.g. `("true"|"false"|"null")` → `true` → name `true_false` or just `keyword`.

### C2. Examples

`arithmetic.Ident` (`[a-z] [a-z0-9_]* ws`):

| Was | Now |
|---|---|
| `first: str` | `lower: str` |
| `second: str` | `alnum: str` |
| `ws: Ws` | `ws: Ws` (unchanged) |

`chess.Pawn` (`([a-h]"x")? [a-h] [1-8] ("="[NBKQR])?`):

| Was | Now |
|---|---|
| `first: str` | `a_h: str` |
| `second: str` | `a_h2: str` |
| `third: str` | `1_8: str` |
| `fourth: str` | `nbkqr: str` |

`json_ws.Number` (`"-"? (...) ("."[0-9]+)? ([eE]...)?`):

| Was | Now |
|---|---|
| `first: str` | `sign: str` |
| `second: str` | `digit: str` |
| `third: str` | `dot: str` |
| `fourth: str` | `ee: str` |

### C3. README TODO

Add a section to `README.md` noting that field names for character-class fields are derived automatically from the pattern. Grammar authors who need precise control can use GBNF inline comments (`# @field=captureFile`) — this annotation mechanism is planned but not yet implemented.

---

## Sequencing

Parts are strictly ordered. Each must leave the test suite green before the next begins.

```
A → B → C
```

Within Part A, the recommended commit order:
1. Package rename (`src/` → `src/lexic/`), update all imports, confirm tests pass
2. Add `src/lexic/ir/` and `src/lexic/utils/`, delete `codegen/ir.py`
3. Atom split (`CharClassAtom` → 3 types, add `InlineAlternationAtom`)
4. Update all emitters + `IRBuilder` to use new atoms; fix quantifier bug; fix `_topo_sort`
5. Extract transformer to `codegen/transformer.py`

---

## Out of Scope

- **Part D (S04 cross-grammar translation):** explicitly deferred. All decisions above keep D in mind — `InlineAlternationAtom`, `semantic_dump()`, and the generator in `src/lexic/generate.py` are all D-compatible.
- **GBNF annotation mechanism** (`# @field=name`): noted as README TODO; not implemented.
- **`_classify` refactor:** flagged in `OPUS_REVIEW_V2.md` as a future improvement; not in scope here.
