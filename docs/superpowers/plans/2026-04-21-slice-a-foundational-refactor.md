# Slice A — Foundational Refactor Implementation Plan

**Status:** Authoritative (brainstormed, post-design-approval)
**Design spec:** `docs/superpowers/specs/2026-04-21-slice-a-design.md`
**Roadmap:** `prototyping/next/3_ROADMAP.md` §Slice A

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mechanical SOLID pass on Lexic's codegen pipeline — extract
three collaborators from the 669-line `ir_builder.py`, convert the
267-line imperative transformer into a table-driven `FieldBuilder`
dispatch, introduce `CompiledGrammar` with memoised `compile()`, and
finish the `utils/` extractions — all without changing any public API
or generated-code shape.

**Architecture:** Five parts run sequentially; each part leaves the
312-test suite green. Part A finishes the `utils/` extractions (pure
helpers). Part B decomposes `ir_builder.py` into `assign_field_names` +
`HelperRuleRegistry` + `Classifier` + per-kind `_build_*` methods (the
latter relocated from Part E per §B of the design spec). Part C
converts `transformer.py` into a `transformer/` sub-package with a
`BUILDER_BY_ATOM` dispatch and an **immutable** `BuildContext` +
`SkipField` tagged skip variant. Part D introduces `CompiledGrammar` +
memoised `compile()`/`compile_from_path()` so `parse()` stops regenerating
modules on every call. Part E sweeps the remaining 40+-line method
(principally `generate.py::generate`).

**Tech Stack:** Python 3.12, Pydantic v2, Lark, uv, pytest

**Prior-state notes:**
- The `src/ → src/lexic/` package rename already landed (commits
  `91fd8e2`, `67d61d4`).
- The IR split into `lexic/ir/atoms.py` + `lexic/ir/spec.py` already
  landed.
- `lexic/utils/escapes.py` and `lexic/utils/quantifiers.py` exist; this
  plan adds `names.py`, `charclass.py`, and the `quantifier_to_bounds`
  inverse function.
- The seven-atom dispatch keeps today's atoms (`CharClassAtom`,
  `QuantifiedLiteralAtom`, `InlineRegexAtom` are still separate here).
  Slice B collapses them into `PatternAtom`.

**Baseline verification (run before starting):**

```bash
uv run pytest tests/ -q
```
Expected: `312 passed`

```bash
uv run ruff check src/ tests/
```
Expected: `All checks passed!`

---

## PART A — Utils extractions

Small, sequential helper moves. Each task is one new module + one
caller update + one test file.

---

### Task 1: Add `quantifier_to_bounds` to `utils/quantifiers.py`

**Files:**
- Modify: `src/lexic/utils/quantifiers.py`
- Modify: `src/lexic/codegen/ir_builder.py:35-53` (remove
  `_quantifier_to_bounds`, import instead)
- Modify: `tests/unit/lexic/utils/test_quantifiers.py`

Rationale: the file already has the forward direction
(`bounds_to_quantifier`). The inverse (`_quantifier_to_bounds`) lives
in `ir_builder.py` and is the right home for both halves of the
conversion.

- [ ] **Step 1: Add failing tests for `quantifier_to_bounds`**

Append to `tests/unit/lexic/utils/test_quantifiers.py`:

```python
import pytest

from lexic.utils.quantifiers import quantifier_to_bounds


@pytest.mark.parametrize("q, expected", [
    (None,      (1, 1)),
    ("?",       (0, 1)),
    ("*",       (0, None)),
    ("+",       (1, None)),
    ("{3}",     (3, 3)),
    ("{0,15}",  (0, 15)),
    ("{2,}",    (2, None)),
])
def test_quantifier_to_bounds(q, expected):
    assert quantifier_to_bounds(q) == expected
```

- [ ] **Step 2: Run tests; verify they fail**

```bash
uv run pytest tests/unit/lexic/utils/test_quantifiers.py -v
```
Expected: `ImportError` or `AttributeError` — `quantifier_to_bounds`
does not exist.

- [ ] **Step 3: Implement `quantifier_to_bounds`**

Append to `src/lexic/utils/quantifiers.py`:

```python
def quantifier_to_bounds(q: str | None) -> tuple[int, int | None]:
    """Parse a GBNF/Lark quantifier string into (min, max). max=None means unbounded."""
    if q is None:
        return 1, 1
    if q == "?":
        return 0, 1
    if q == "*":
        return 0, None
    if q == "+":
        return 1, None
    inner = q[1:-1]
    if "," in inner:
        lo_str, hi_str = inner.split(",", 1)
        lo = int(lo_str)
        hi = int(hi_str) if hi_str else None
        return lo, hi
    n = int(inner)
    return n, n
```

- [ ] **Step 4: Run the new tests; verify they pass**

```bash
uv run pytest tests/unit/lexic/utils/test_quantifiers.py -v
```
Expected: all new tests pass.

- [ ] **Step 5: Replace `_quantifier_to_bounds` calls in `ir_builder.py`**

In `src/lexic/codegen/ir_builder.py`:

1. Add to the imports at the top:
   ```python
   from lexic.utils.quantifiers import quantifier_to_bounds
   ```
2. Delete the local `_quantifier_to_bounds` function (lines 35–53).
3. Replace every `_quantifier_to_bounds(...)` call with
   `quantifier_to_bounds(...)`. Six call sites: inside `_seq_to_atoms`
   (four) and `_build_rule` (two).

- [ ] **Step 6: Run the full suite; verify green**

```bash
uv run pytest tests/ -q
```
Expected: `312 passed`.

- [ ] **Step 7: Lint**

```bash
uv run ruff check src/ tests/
```
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add src/lexic/utils/quantifiers.py src/lexic/codegen/ir_builder.py tests/unit/lexic/utils/test_quantifiers.py
git commit -m "refactor(utils): move quantifier_to_bounds out of ir_builder"
```

---

### Task 2: Create `utils/names.py` (holds `to_pascal`, `to_lark_name`, and `to_snake`)

**Files:**
- Create: `src/lexic/utils/names.py`
- Create: `tests/unit/lexic/utils/test_names.py`
- Modify: `src/lexic/codegen/lark_builder.py:24-30` (delete
  `to_lark_name`, import instead)
- Modify: `src/lexic/codegen/ir_builder.py:29-32` (delete `to_pascal`,
  import instead)
- Modify: `src/lexic/codegen/transformer.py:19` (update import)

Rationale: `to_lark_name` currently lives in `lark_builder.py` but is
imported by `transformer.py`, creating a needless coupling. `to_pascal`
lives in `ir_builder.py`. Both (plus a `to_snake` needed for Slice D)
belong in one utils module.

- [ ] **Step 1: Write failing tests for all three functions**

Create `tests/unit/lexic/utils/test_names.py`:

```python
import pytest

from lexic.utils.names import to_lark_name, to_pascal, to_snake


@pytest.mark.parametrize("inp, expected", [
    ("root",          "root"),
    ("json-ws",       "json_ws"),
    ("JP-char",       "jp_char"),
    ("arm1",          "arm1"),
])
def test_to_lark_name(inp, expected):
    assert to_lark_name(inp) == expected


@pytest.mark.parametrize("inp, expected", [
    ("root",          "Root"),
    ("json-ws",       "JsonWs"),
    ("jp-char",       "JpChar"),
    ("arm_item_1",    "ArmItem1"),
    ("",              ""),
])
def test_to_pascal(inp, expected):
    assert to_pascal(inp) == expected


@pytest.mark.parametrize("inp, expected", [
    ("JsonWs",        "json_ws"),
    ("JPChar",        "jp_char"),
    ("Root",          "root"),
    ("AB",            "ab"),
])
def test_to_snake(inp, expected):
    assert to_snake(inp) == expected
```

- [ ] **Step 2: Run tests; verify they fail with ImportError**

```bash
uv run pytest tests/unit/lexic/utils/test_names.py -v
```
Expected: `ModuleNotFoundError: No module named 'lexic.utils.names'`.

- [ ] **Step 3: Implement the module**

Create `src/lexic/utils/names.py`:

```python
"""Identifier conversion utilities.

to_lark_name / to_pascal / to_snake convert grammar rule names between the
three casings we deal with: kebab/snake (GBNF/Lark), PascalCase (Python
classes), and snake_case (Python identifiers).
"""

from __future__ import annotations

import re


def to_lark_name(rule_name: str) -> str:
    """Convert a GBNF rule name to a valid Lark rule identifier."""
    return rule_name.replace("-", "_").lower()


def to_pascal(name: str) -> str:
    """Convert 'jp-char' or 'json_ws' to 'JpChar' / 'JsonWs'."""
    parts = re.split(r"[-_]", name)
    return "".join(p[0].upper() + p[1:] if p else "" for p in parts)


_SNAKE_RE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_RE_2 = re.compile(r"([a-z0-9])([A-Z])")


def to_snake(name: str) -> str:
    """Convert 'JsonWs' or 'JPChar' to 'json_ws' / 'jp_char'."""
    s1 = _SNAKE_RE_1.sub(r"\1_\2", name)
    return _SNAKE_RE_2.sub(r"\1_\2", s1).lower()
```

- [ ] **Step 4: Run tests; verify they pass**

```bash
uv run pytest tests/unit/lexic/utils/test_names.py -v
```
Expected: all 12 parametrized cases pass.

- [ ] **Step 5: Update `lark_builder.py` to import `to_lark_name`**

In `src/lexic/codegen/lark_builder.py`:

1. Delete the local `to_lark_name` function (lines 24–30).
2. Add to the imports:
   ```python
   from lexic.utils.names import to_lark_name
   ```

- [ ] **Step 6: Update `ir_builder.py` to import `to_pascal`**

In `src/lexic/codegen/ir_builder.py`:

1. Delete the local `to_pascal` function (lines 29–32).
2. Add to the imports:
   ```python
   from lexic.utils.names import to_pascal
   ```

- [ ] **Step 7: Update `transformer.py` import**

In `src/lexic/codegen/transformer.py`, change:

```python
from lexic.codegen.lark_builder import to_lark_name
```

to:

```python
from lexic.utils.names import to_lark_name
```

- [ ] **Step 8: Run the full suite; verify green**

```bash
uv run pytest tests/ -q && uv run ruff check src/ tests/
```
Expected: `312 passed`, ruff clean.

- [ ] **Step 9: Commit**

```bash
git add src/lexic/utils/names.py tests/unit/lexic/utils/test_names.py src/lexic/codegen/lark_builder.py src/lexic/codegen/ir_builder.py src/lexic/codegen/transformer.py
git commit -m "refactor(utils): consolidate to_lark_name/to_pascal/to_snake in utils.names"
```

---

### Task 3: Extract charclass parser into `utils/charclass.py`

**Files:**
- Create: `src/lexic/utils/charclass.py`
- Create: `tests/unit/lexic/utils/test_charclass.py`
- Modify: `src/lexic/generate.py:44-93` (delete `_parse_escape` and
  `_parse_charclass_chars`, import instead)

Rationale: closes V3 §B. These helpers also belong with any future
bracket-expression work in Slice B; centralising them now prevents a
second parallel parser.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/lexic/utils/test_charclass.py`:

```python
import pytest

from lexic.utils.charclass import parse_charclass_chars, parse_escape


def test_parse_escape_basic():
    assert parse_escape("\\n", 0) == ("\n", 2)
    assert parse_escape("\\t", 0) == ("\t", 2)
    assert parse_escape("\\\"", 0) == ('"', 2)
    assert parse_escape("\\\\", 0) == ("\\", 2)


def test_parse_escape_hex():
    assert parse_escape("\\x41", 0) == ("A", 4)
    assert parse_escape("\\u00e9", 0) == ("é", 6)


def test_parse_charclass_simple_range():
    assert parse_charclass_chars("a-c") == ["a", "b", "c"]
    assert parse_charclass_chars("0-3") == ["0", "1", "2", "3"]


def test_parse_charclass_escape_range():
    result = parse_charclass_chars("\\x00-\\x03")
    assert result == [chr(c) for c in range(0, 4)]


def test_parse_charclass_direct_chars():
    assert parse_charclass_chars("abc") == ["a", "b", "c"]


def test_parse_charclass_mixed():
    assert parse_charclass_chars("a-c_") == ["a", "b", "c", "_"]
```

- [ ] **Step 2: Run; verify fail**

```bash
uv run pytest tests/unit/lexic/utils/test_charclass.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the module**

Create `src/lexic/utils/charclass.py`:

```python
"""Parse GBNF bracket expressions into concrete character lists.

Shared by `lexic.generate` (random generation) and, eventually, any emitter
that needs to enumerate a character class.
"""

from __future__ import annotations


def parse_escape(s: str, i: int) -> tuple[str, int]:
    """Parse a GBNF escape sequence starting at s[i+1]. Returns (char, new_i)."""
    c = s[i + 1]
    if c == "n":
        return "\n", i + 2
    if c == "t":
        return "\t", i + 2
    if c == "r":
        return "\r", i + 2
    if c == '"':
        return '"', i + 2
    if c == "\\":
        return "\\", i + 2
    if c == "x" and i + 3 < len(s):
        return chr(int(s[i + 2 : i + 4], 16)), i + 4
    if c == "u" and i + 5 < len(s):
        return chr(int(s[i + 2 : i + 6], 16)), i + 6
    if c == "U" and i + 9 < len(s):
        return chr(int(s[i + 2 : i + 10], 16)), i + 10
    return c, i + 2


def parse_charclass_chars(inner: str) -> list[str]:
    """Parse the interior of a GBNF bracket expression into a list of chars.

    Supports ranges (a-z), direct Unicode, and escape sequences
    (\\n \\t \\r \\xXX \\uXXXX \\UXXXXXXXX).
    """
    chars: list[str] = []
    i = 0
    while i < len(inner):
        if inner[i] == "\\" and i + 1 < len(inner):
            ch, i = parse_escape(inner, i)
            if i < len(inner) and inner[i] == "-" and i + 1 < len(inner):
                if inner[i + 1] == "\\" and i + 2 < len(inner):
                    end_ch, i = parse_escape(inner, i + 1)
                else:
                    end_ch = inner[i + 1]
                    i += 2
                chars.extend(chr(c) for c in range(ord(ch), ord(end_ch) + 1))
            else:
                chars.append(ch)
        elif i + 2 < len(inner) and inner[i + 1] == "-":
            chars.extend(chr(c) for c in range(ord(inner[i]), ord(inner[i + 2]) + 1))
            i += 3
        else:
            chars.append(inner[i])
            i += 1
    return chars
```

- [ ] **Step 4: Run new tests; verify pass**

- [ ] **Step 5: Update `generate.py`**

In `src/lexic/generate.py`:

1. Delete `_parse_escape` (lines 44–63) and `_parse_charclass_chars`
   (lines 66–93).
2. Add to imports:
   ```python
   from lexic.utils.charclass import parse_charclass_chars
   ```
3. Replace the one call to `_parse_charclass_chars` (inside
   `_gen_charclass`) with `parse_charclass_chars`.

- [ ] **Step 6: Run the full suite; verify green**

```bash
uv run pytest tests/ -q && uv run ruff check src/ tests/
```
Expected: `312 passed`, clean.

- [ ] **Step 7: Commit**

```bash
git add src/lexic/utils/charclass.py tests/unit/lexic/utils/test_charclass.py src/lexic/generate.py
git commit -m "refactor(utils): extract charclass parser from generate.py"
```

---

## PART B — Decompose `ir_builder.py`

Four extractions plus the per-kind `_build_rule` split (relocated from
Part E per design spec §B). After Part B, `ir_builder.py` should hold
only the `IRBuilder` orchestrator class and be under 200 lines.

---

### Task 4: Extract `assign_field_names` into `codegen/naming.py`

**Files:**
- Create: `src/lexic/codegen/naming.py`
- Create: `tests/unit/lexic/codegen/test_naming.py`
- Modify: `src/lexic/codegen/ir_builder.py` (delete naming helpers,
  delegate to `assign_field_names`)

Rationale: closes V3 §3. The naming policy is ~110 lines of behaviour
currently intermixed with IR-building logic. Pulling it into one module
lets us test it in isolation and lets Slice C replace it with the
four-tier cascade without touching `IRBuilder`.

**Per brainstorm decision (spec §Q4):** a module-level function, not a
class. Per-rule stateless (unchanged semantic).

- [ ] **Step 1: Write failing unit tests**

Create `tests/unit/lexic/codegen/test_naming.py`:

```python
import pytest

from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.codegen.naming import assign_field_names


def test_literal_atom_has_no_field():
    atoms = [LiteralAtom("+"), LiteralAtom("-")]
    assert assign_field_names(atoms) == {}


def test_charclass_uses_known_semantic_name():
    atoms = [CharClassAtom(pattern="[0-9]", min=1, max=1)]
    assert assign_field_names(atoms) == {"digit": 0}


def test_charclass_falls_back_to_sanitized_pattern():
    atoms = [CharClassAtom(pattern="[NBKQR]", min=1, max=1)]
    fm = assign_field_names(atoms)
    assert list(fm.keys())[0] == "nbkqr"


def test_ruleref_uses_rule_name():
    atoms = [RuleRefAtom(rule_name="expr", min=1, max=1)]
    assert assign_field_names(atoms) == {"expr": 0}


def test_collisions_are_numbered():
    atoms = [
        RuleRefAtom(rule_name="ws", min=0, max=1),
        LiteralAtom("="),
        RuleRefAtom(rule_name="ws", min=0, max=1),
    ]
    fm = assign_field_names(atoms)
    assert fm == {"ws": 0, "ws2": 2}


def test_inline_alternation_gets_value_field():
    atoms = [InlineAlternationAtom(arm_rule_names=["a", "b"])]
    assert assign_field_names(atoms) == {"value": 0}


def test_quantified_literal_named_from_lookup():
    atoms = [QuantifiedLiteralAtom(value="-", min=0, max=1)]
    assert assign_field_names(atoms) == {"sign": 0}


def test_inline_regex_named_from_first_arm():
    atoms = [InlineRegexAtom(
        regex="(true|false)", gbnf='("true"|"false")', min=1, max=1
    )]
    fm = assign_field_names(atoms)
    assert list(fm.keys())[0] == "true"


def test_alternation_atom_has_no_field():
    atoms = [AlternationAtom(arm_rule_names=["a", "b"])]
    assert assign_field_names(atoms) == {}
```

- [ ] **Step 2: Run; verify fail**

- [ ] **Step 3: Implement the module**

Create `src/lexic/codegen/naming.py`:

```python
"""assign_field_names: map a rule's atom sequence to Pydantic field positions.

Extracted from ir_builder.py so the naming policy can be evolved and
tested independently of GBNF semantics. Slice C will replace this module
with the four-tier cascade; for now the behaviour is identical to the
pre-extraction _CHARCLASS_NAMES/_LITERAL_NAMES lookup.

Stateless. Per-rule scope (collision counters reset per call).
"""

from __future__ import annotations

import re

from lexic.ir import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)


_CHARCLASS_NAMES: dict[str, str] = {
    "[0-9]": "digit",
    "[1-9]": "digit",
    "[0-9a-fA-F]": "hex",
    "[a-fA-F0-9]": "hex",
    "[a-f]": "hex_lower",
    "[A-F]": "hex_upper",
    "[a-z]": "lower",
    "[A-Z]": "upper",
    "[a-zA-Z]": "alpha",
    "[a-z0-9_]": "alnum",
    "[a-zA-Z_]": "name_start",
    "[a-zA-Z0-9_]": "alnum",
    "[a-zA-Z_0-9]": "alnum",
    "[+\\-*/]": "op",
    "[-+*/]": "op",
    "[+#]": "annotation",
    "[ \\t\\n]": "ws_char",
    "[ \\t]": "hspace",
    "[^\\n]": "non_newline",
    '[^"\\\\]': "str_char",
}

_LITERAL_NAMES: dict[str, str] = {
    "-": "sign",
    "+": "sign",
    ".": "dot",
    ",": "comma",
    ":": "colon",
    ";": "semicolon",
    "=": "eq",
    "x": "x",
    "e": "e",
    "E": "E",
}


def _sanitize_pattern(pattern: str) -> str:
    inner = re.sub(r"[\[\]\^]", "", pattern)
    inner = inner.replace("-", "_").lower()
    inner = re.sub(r"[^a-z0-9_]", "", inner)
    inner = inner.strip("_")
    inner = re.sub(r"_+", "_", inner)
    if not inner:
        return ""
    if inner[0].isdigit():
        inner = "cc_" + inner
    return inner[:12].strip("_")


def _charclass_field_name(atom: CharClassAtom) -> str:
    if atom.pattern in _CHARCLASS_NAMES:
        return _CHARCLASS_NAMES[atom.pattern]
    hint = _sanitize_pattern(atom.pattern)
    if hint:
        return hint
    if atom.max is None:
        return "tail"
    if atom.min == 0 and atom.max == 1:
        return "opt"
    return "cc"


def _quantified_literal_field_name(value: str) -> str:
    if value in _LITERAL_NAMES:
        return _LITERAL_NAMES[value]
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", value).strip("_").lower()[:12]
    return sanitized or "lit"


def _inline_regex_field_name(gbnf: str) -> str:
    body = gbnf.strip()
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    first_arm = body.split("|")[0].strip().strip('"')
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", first_arm).strip("_").lower()
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")[:12]
    if not sanitized:
        return "inline"
    if sanitized[0].isdigit():
        sanitized = ("val_" + sanitized)[:12].strip("_")
    return sanitized


def assign_field_names(atoms: list[Atom]) -> dict[str, int]:
    """Assign semantic field names to atoms. Per-rule scope; stateless."""
    field_map: dict[str, int] = {}
    counts: dict[str, int] = {}

    def unique(base: str) -> str:
        n = counts.get(base, 0) + 1
        counts[base] = n
        return base if n == 1 else f"{base}{n}"

    for i, atom in enumerate(atoms):
        if isinstance(atom, LiteralAtom):
            continue
        if isinstance(atom, AlternationAtom):
            continue
        if isinstance(atom, InlineAlternationAtom):
            field_map[unique("value")] = i
        elif isinstance(atom, RuleRefAtom):
            field_map[unique(atom.rule_name.replace("-", "_"))] = i
        elif isinstance(atom, CharClassAtom):
            field_map[unique(_charclass_field_name(atom))] = i
        elif isinstance(atom, QuantifiedLiteralAtom):
            field_map[unique(_quantified_literal_field_name(atom.value))] = i
        elif isinstance(atom, InlineRegexAtom):
            field_map[unique(_inline_regex_field_name(atom.gbnf))] = i

    return field_map
```

- [ ] **Step 4: Run new tests; verify pass**

- [ ] **Step 5: Delete naming helpers from `ir_builder.py`**

In `src/lexic/codegen/ir_builder.py`:

1. Delete the semantic-field-naming block (lines ~238–375).
2. Add import:
   ```python
   from lexic.codegen.naming import assign_field_names
   ```
3. Replace all three `_assign_field_names(...)` call sites (one in
   `_seq_to_atoms`, two in `_build_rule`) with
   `assign_field_names(...)`.

- [ ] **Step 6: Run full suite; verify green**

```bash
uv run pytest tests/ -q && uv run ruff check src/ tests/
```
Expected: `312 passed`, clean.

- [ ] **Step 7: Commit**

```bash
git add src/lexic/codegen/naming.py tests/unit/lexic/codegen/test_naming.py src/lexic/codegen/ir_builder.py
git commit -m "refactor(ir_builder): extract assign_field_names into codegen/naming.py"
```

---

### Task 5: Extract `HelperRuleRegistry` into `codegen/helpers.py`

**Files:**
- Create: `src/lexic/codegen/helpers.py`
- Create: `tests/unit/lexic/codegen/test_helpers.py`
- Modify: `src/lexic/codegen/ir_builder.py`

Rationale: closes V3 §10. A single `HelperRuleRegistry` instance held
by `IRBuilder` makes helper-rule dedup globally consistent rather than
per-`_seq_to_atoms`-invocation.

- [ ] **Step 1: Write failing unit tests**

Create `tests/unit/lexic/codegen/test_helpers.py`:

```python
from lexic.ir import RuleSpec
from lexic.codegen.helpers import HelperRuleRegistry


def _spec(name: str) -> RuleSpec:
    return RuleSpec(
        rule_name=name, class_name="X", parent_class_name="GrammarModel",
        kind="sequence", items=[], field_map={},
    )


def test_reserve_returns_base_on_first_use():
    reg = HelperRuleRegistry()
    assert reg.reserve("arithmetic-item") == "arithmetic-item"


def test_reserve_numbers_collisions():
    reg = HelperRuleRegistry()
    reg.register(_spec("arithmetic-item"))
    assert reg.reserve("arithmetic-item") == "arithmetic-item2"
    reg.register(_spec("arithmetic-item2"))
    assert reg.reserve("arithmetic-item") == "arithmetic-item3"


def test_reserve_is_idempotent_before_register():
    """Reserve does NOT mutate the registry — only register() does."""
    reg = HelperRuleRegistry()
    reg.register(_spec("a"))
    assert reg.reserve("a") == "a2"
    assert reg.reserve("a") == "a2"  # still a2, because a2 isn't registered yet


def test_all_specs_returned_in_registration_order():
    reg = HelperRuleRegistry()
    reg.register(_spec("p"))
    reg.register(_spec("q"))
    reg.register(_spec("r"))
    assert [s.rule_name for s in reg.all_specs()] == ["p", "q", "r"]


def test_register_rejects_duplicate_name():
    import pytest
    reg = HelperRuleRegistry()
    reg.register(_spec("x"))
    with pytest.raises(ValueError, match=r"already registered"):
        reg.register(_spec("x"))
```

- [ ] **Step 2: Run; verify fail**

- [ ] **Step 3: Implement**

Create `src/lexic/codegen/helpers.py`:

```python
"""HelperRuleRegistry: one-per-build registry for anonymous helper rules."""

from __future__ import annotations

from lexic.ir import RuleSpec


class HelperRuleRegistry:
    def __init__(self) -> None:
        self._specs: list[RuleSpec] = []
        self._names: set[str] = set()

    def reserve(self, base_name: str) -> str:
        """Return a unique rule_name. Does NOT mark the name as taken."""
        if base_name not in self._names:
            return base_name
        suffix = 2
        while f"{base_name}{suffix}" in self._names:
            suffix += 1
        return f"{base_name}{suffix}"

    def register(self, spec: RuleSpec) -> None:
        if spec.rule_name in self._names:
            raise ValueError(
                f"Helper rule {spec.rule_name!r} already registered"
            )
        self._names.add(spec.rule_name)
        self._specs.append(spec)

    def all_specs(self) -> list[RuleSpec]:
        return list(self._specs)
```

- [ ] **Step 4: Run new tests; verify pass**

- [ ] **Step 5: Wire `HelperRuleRegistry` into `IRBuilder`**

In `src/lexic/codegen/ir_builder.py`:

1. Add import:
   ```python
   from lexic.codegen.helpers import HelperRuleRegistry
   ```

2. In `IRBuilder.__init__`, add:
   ```python
   self._helpers = HelperRuleRegistry()
   ```

3. **Change `_seq_to_atoms` signature.** Replace the `helper_specs`
   parameter with `helpers: HelperRuleRegistry`. Current signature
   (`src/lexic/codegen/ir_builder.py:381`):
   ```python
   def _seq_to_atoms(
       seq: Sequence,
       parent_class_name: str,
       helper_specs: list[RuleSpec],     # DELETE
       name_map: dict[str, str],
       parent_of: dict[str, str],
   ) -> list[Atom]:
   ```
   becomes:
   ```python
   def _seq_to_atoms(
       seq: Sequence,
       parent_class_name: str,
       helpers: HelperRuleRegistry,       # NEW
       name_map: dict[str, str],
       parent_of: dict[str, str],
   ) -> list[Atom]:
   ```

4. **Update every call site of `_seq_to_atoms`.** There are three in
   the current file (line numbers are approximate — grep to confirm):

   a. **Recursive single-arm-group inline call** (~line 442). Change
      the third positional arg from `helper_specs` to `helpers`.

   b. **Recursive helper-group call** (~line 460). Same — third arg
      becomes `helpers`.

   c. **`_build_rule` named-alt arm call** (~line 587–592). The local
      `helper_specs: list[RuleSpec] = []` goes away, and the trailing
      `arm_specs.extend(helper_specs)` goes away. Current:
      ```python
      helper_specs: list[RuleSpec] = []
      arm_atoms = _seq_to_atoms(
          stripped, arm_cls_name, helper_specs, self._name_map, parent_of
      )
      ...
      arm_specs.extend(helper_specs)
      ```
      becomes:
      ```python
      arm_atoms = _seq_to_atoms(
          stripped, arm_cls_name, self._helpers, self._name_map, parent_of
      )
      # helpers are registered into self._helpers; no local accumulation.
      ```

   d. **`_build_rule` sequence-kind call** (~line 631–644). Delete the
      local `helper_specs_seq`; return only the primary spec. Current:
      ```python
      helper_specs_seq: list[RuleSpec] = []
      arm_atoms = _seq_to_atoms(
          full_arms[0], cls_name, helper_specs_seq, self._name_map, parent_of
      )
      ...
      return helper_specs_seq + [seq_spec]
      ```
      becomes:
      ```python
      arm_atoms = _seq_to_atoms(
          full_arms[0], cls_name, self._helpers, self._name_map, parent_of
      )
      ...
      return [seq_spec]
      ```

5. **Replace the inline dedup block inside `_seq_to_atoms`** (currently
   ~line 449–457). Current:
   ```python
   helper_rule_name = f"{parent_class_name.lower()}-item"
   existing = {s.rule_name for s in helper_specs}
   suffix = 2
   candidate = helper_rule_name
   while candidate in existing:
       candidate = f"{helper_rule_name}{suffix}"
       suffix += 1
   helper_rule_name = candidate
   ```
   becomes a single call into the registry:
   ```python
   helper_rule_name = helpers.reserve(f"{parent_class_name.lower()}-item")
   ```

6. **Replace `helper_specs.append(helper_spec)`** (~line 476) with
   `helpers.register(helper_spec)`.

7. **Rewrite `build()`** to gather helper specs from the registry once,
   at the end:
   ```python
   def build(self) -> list[RuleSpec]:
       """Build and return specs in grammar order (root first)."""
       parent_of = self._compute_parents()
       primary_specs: list[RuleSpec] = []
       for rule in self._rules:
           primary_specs.extend(self._build_rule(rule, parent_of))
       all_specs = primary_specs + self._helpers.all_specs()
       return self._topo_sort(all_specs)
   ```
   Note: `_build_rule` no longer takes `existing_specs` — that
   parameter existed purely to feed the old per-call helper dedup, and
   the registry replaces it.

8. **Update `_build_rule`'s signature.** Current:
   ```python
   def _build_rule(
       self,
       rule: Rule,
       parent_of: dict[str, str],
       existing_specs: list[RuleSpec],     # DELETE
   ) -> list[RuleSpec]:
   ```
   becomes:
   ```python
   def _build_rule(
       self,
       rule: Rule,
       parent_of: dict[str, str],
   ) -> list[RuleSpec]:
   ```
   Every reference to `existing_specs` inside `_build_rule` was feeding
   the inline helper dedup in `_seq_to_atoms`, which is now gone.

- [ ] **Step 6: Run full suite; verify green**

- [ ] **Step 7: Commit**

```bash
git add src/lexic/codegen/helpers.py tests/unit/lexic/codegen/test_helpers.py src/lexic/codegen/ir_builder.py
git commit -m "refactor(ir_builder): extract HelperRuleRegistry, global helper dedup"
```

---

### Task 6: Extract `Classifier` into `codegen/classify.py` (union return)

**Files:**
- Create: `src/lexic/codegen/ast_utils.py` (shared GBNF-AST helpers —
  the home for traversal helpers consumed by more than one codegen
  module)
- Create: `src/lexic/codegen/classify.py`
- Create: `tests/unit/lexic/codegen/test_ast_utils.py`
- Create: `tests/unit/lexic/codegen/test_classify.py`
- Modify: `src/lexic/codegen/ir_builder.py`

Rationale: closes V3 §2. Pulls ~150 lines of GBNF-AST analysis out of
`IRBuilder`.

**Per brainstorm decision (spec §Q2):** `Classification` is a union of
four per-kind frozen dataclasses. Each variant carries exactly the
payload its downstream handler needs — eliminates AST re-traversal in
callers.

**Per plan-review finding P1.5:** `strip_ws`, `unwrap_group_alt`, and
`single_ruleref_of` are consumed by both `classify.py` and the residual
orchestrator code in `ir_builder.py` (`_compute_parents`,
`_seq_to_atoms`, the per-kind build methods). They are AST utilities,
not classifier internals — they live in `codegen/ast_utils.py` as
first-class public functions. Never re-export via module-bottom aliases
of leading-underscore names — that is the exact leaky abstraction this
refactor closes.

- [ ] **Step 1: Write failing unit tests**

Create `tests/unit/lexic/codegen/test_classify.py`:

```python
import pytest

from lexic.codegen.ast import (
    Alternation, CharClass, Group, Item, Literal, Rule, RuleRef, Sequence,
)
from lexic.codegen.classify import (
    Classifier,
    NamedAlt,
    PureLiteralAlt,
    SequenceKind,
    ValueStr,
)


def _rule(name: str, body: Alternation) -> Rule:
    return Rule(name=name, body=body)


def _seq(*items: Item) -> Sequence:
    return Sequence(items=list(items))


def _alt(*seqs: Sequence) -> Alternation:
    return Alternation(seqs=list(seqs))


def _lit(v: str, q: str | None = None) -> Item:
    return Item(atom=Literal(value=v), quantifier=q)


def _cc(pat: str, q: str | None = None) -> Item:
    return Item(atom=CharClass(pattern=pat), quantifier=q)


def _ref(name: str, q: str | None = None) -> Item:
    return Item(atom=RuleRef(name=name), quantifier=q)


def test_pure_literal_alternation_returns_arms():
    body = _alt(_seq(_lit("+")), _seq(_lit("-")), _seq(_lit("*")))
    result = Classifier().classify(_rule("op", body))
    assert isinstance(result, PureLiteralAlt)
    assert result.arms == [["+"], ["-"], ["*"]]


def test_named_alternation_returns_arm_sequences():
    body = _alt(_seq(_ref("a")), _seq(_ref("b")), _seq(_ref("c")))
    result = Classifier().classify(_rule("u", body))
    assert isinstance(result, NamedAlt)
    assert len(result.arms) == 3


def test_sequence_returns_body():
    body = _alt(_seq(_ref("expr"), _lit("="), _ref("expr")))
    result = Classifier().classify(_rule("assign", body))
    assert isinstance(result, SequenceKind)
    assert len(result.body.items) == 3


def test_value_str_single_arm_no_refs():
    body = _alt(_seq(_cc("[0-9]", "+")))
    assert isinstance(Classifier().classify(_rule("num", body)), ValueStr)


def test_structurally_complex_returns_value_str():
    # A single arm whose only item is a multi-arm group, where no arm
    # references a rule, is "structurally complex" (see _is_structurally_complex:
    # all_no_refs and has_group_alt). It should collapse to ValueStr.
    inner = _alt(_seq(_lit("a")), _seq(_lit("b")))
    body = _alt(_seq(Item(atom=Group(alt=inner), quantifier=None)))
    assert isinstance(Classifier().classify(_rule("choice", body)), ValueStr)


def test_empty_arms_returns_value_str():
    body = _alt()  # no sequences
    assert isinstance(Classifier().classify(_rule("empty", body)), ValueStr)
```

- [ ] **Step 2: Run; verify fail**

- [ ] **Step 3a: Implement shared AST helpers in `codegen/ast_utils.py`**

Create `src/lexic/codegen/ast_utils.py`:

```python
"""Shared GBNF-AST traversal helpers.

These three functions are consumed by both classify.py and the residual
orchestration code in ir_builder.py. They are public (no leading
underscore) because more than one module depends on them; the
alternative — re-exporting underscore names — is a known leaky
abstraction and is not used here.
"""

from __future__ import annotations

from lexic.codegen.ast import (
    Alternation,
    Group,
    Item,
    RuleRef,
    Sequence,
)


def is_ws_item(item: Item) -> bool:
    return isinstance(item.atom, RuleRef) and item.atom.name == "ws"


def strip_ws(seq: Sequence) -> Sequence:
    """Drop `ws` rulerefs from a sequence; preserve order."""
    return Sequence([it for it in seq.items if not is_ws_item(it)])


def unwrap_group_alt(alt: Alternation) -> Alternation:
    """If `alt` is a 1-arm wrapper around a single unquantified group,
    return the inner alternation. Otherwise return `alt` unchanged."""
    if len(alt.seqs) != 1:
        return alt
    stripped = strip_ws(alt.seqs[0])
    if len(stripped.items) == 1:
        it = stripped.items[0]
        if isinstance(it.atom, Group) and it.quantifier is None:
            return it.atom.alt
    return alt


def single_ruleref_of(seq: Sequence) -> str | None:
    """If `seq` (ws-stripped) reduces to a single unquantified ruleref —
    either directly or as a 1-item 1-arm group containing a ruleref —
    return the referenced rule name. Otherwise return None."""
    stripped = strip_ws(seq)
    if len(stripped.items) != 1:
        return None
    it = stripped.items[0]
    if it.quantifier is not None:
        return None
    if isinstance(it.atom, RuleRef):
        return it.atom.name
    if isinstance(it.atom, Group):
        inner = it.atom.alt
        if len(inner.seqs) == 1:
            inner_stripped = strip_ws(inner.seqs[0])
            if len(inner_stripped.items) == 1:
                inner_it = inner_stripped.items[0]
                if inner_it.quantifier is None and isinstance(inner_it.atom, RuleRef):
                    return inner_it.atom.name
    return None
```

- [ ] **Step 3b: Write failing unit tests for `ast_utils`**

Create `tests/unit/lexic/codegen/test_ast_utils.py`:

```python
from lexic.codegen.ast import (
    Alternation, CharClass, Group, Item, Literal, RuleRef, Sequence,
)
from lexic.codegen.ast_utils import (
    is_ws_item,
    single_ruleref_of,
    strip_ws,
    unwrap_group_alt,
)


def _item(atom, q=None):
    return Item(atom=atom, quantifier=q)


def test_strip_ws_drops_ws_rulerefs():
    seq = Sequence(items=[
        _item(Literal(value="a")),
        _item(RuleRef(name="ws")),
        _item(Literal(value="b")),
    ])
    assert [it.atom for it in strip_ws(seq).items] == [
        Literal(value="a"), Literal(value="b"),
    ]


def test_is_ws_item_true_only_for_ws_ruleref():
    assert is_ws_item(_item(RuleRef(name="ws"))) is True
    assert is_ws_item(_item(RuleRef(name="other"))) is False
    assert is_ws_item(_item(Literal(value="ws"))) is False


def test_single_ruleref_direct():
    seq = Sequence(items=[_item(RuleRef(name="expr"))])
    assert single_ruleref_of(seq) == "expr"


def test_single_ruleref_through_group():
    inner = Alternation(seqs=[Sequence(items=[_item(RuleRef(name="inner"))])])
    seq = Sequence(items=[_item(Group(alt=inner))])
    assert single_ruleref_of(seq) == "inner"


def test_single_ruleref_rejects_quantified():
    seq = Sequence(items=[_item(RuleRef(name="expr"), q="+")])
    assert single_ruleref_of(seq) is None


def test_unwrap_group_alt_peels_single_arm_wrapper():
    inner = Alternation(seqs=[
        Sequence(items=[_item(Literal(value="a"))]),
        Sequence(items=[_item(Literal(value="b"))]),
    ])
    outer = Alternation(seqs=[Sequence(items=[_item(Group(alt=inner))])])
    assert unwrap_group_alt(outer) is inner


def test_unwrap_group_alt_passes_through_multi_arm():
    alt = Alternation(seqs=[
        Sequence(items=[_item(Literal(value="a"))]),
        Sequence(items=[_item(Literal(value="b"))]),
    ])
    assert unwrap_group_alt(alt) is alt
```

- [ ] **Step 3c: Run ast_utils tests; verify pass**

- [ ] **Step 3d: Implement `Classification` union + classify-internal predicates**

Create `src/lexic/codegen/classify.py`:

```python
"""Classifier: determine a GBNF rule's IR kind.

Given a Rule from the GBNF AST, classify() returns one of four
Classification variants, each carrying exactly the payload its
downstream handler needs. Classify-internal predicates live as module
helpers (underscore-prefixed); shared AST helpers are imported from
codegen.ast_utils.
"""

from __future__ import annotations

from dataclasses import dataclass

from lexic.codegen.ast import (
    Alternation,
    CharClass,
    Group,
    Item,
    Literal,
    Rule,
    RuleRef,
    Sequence,
)
from lexic.codegen.ast_utils import (
    is_ws_item,
    single_ruleref_of,
    strip_ws,
    unwrap_group_alt,
)


@dataclass(frozen=True)
class ValueStr:
    pass


@dataclass(frozen=True)
class PureLiteralAlt:
    arms: list[list[str]]          # literal strings per arm


@dataclass(frozen=True)
class NamedAlt:
    arms: list[Sequence]           # ws-stripped sequences, per arm


@dataclass(frozen=True)
class SequenceKind:
    body: Sequence                 # single ws-stripped sequence


Classification = ValueStr | PureLiteralAlt | NamedAlt | SequenceKind


def _is_pure_literal(item: Item) -> bool:
    return isinstance(item.atom, (Literal, CharClass))


def _is_pure_literal_seq(seq: Sequence) -> bool:
    stripped = strip_ws(seq)
    return len(stripped.items) > 0 and all(
        _is_pure_literal(it) for it in stripped.items
    )


def _has_any_ruleref(items: list[Item]) -> bool:
    for it in items:
        if is_ws_item(it):
            continue
        if isinstance(it.atom, RuleRef):
            return True
        if isinstance(it.atom, Group):
            for seq in it.atom.alt.seqs:
                if _has_any_ruleref(seq.items):
                    return True
    return False


def _has_nontrivial_group(items: list[Item]) -> bool:
    for it in items:
        if isinstance(it.atom, Group):
            for seq in it.atom.alt.seqs:
                if any(isinstance(i.atom, Group) for i in seq.items):
                    return True
    return False


def _has_group_with_alt(items: list[Item]) -> bool:
    for it in items:
        if isinstance(it.atom, Group) and len(it.atom.alt.seqs) > 1:
            return True
    return False


def _is_structurally_complex(alt: Alternation) -> bool:
    for seq in alt.seqs:
        stripped = strip_ws(seq)
        for it in stripped.items:
            if isinstance(it.atom, Group) and it.quantifier == "*":
                for inner_seq in it.atom.alt.seqs:
                    if _has_nontrivial_group(inner_seq.items):
                        return True
    all_no_refs = not any(_has_any_ruleref(strip_ws(seq).items) for seq in alt.seqs)
    has_group_alt = any(_has_group_with_alt(strip_ws(seq).items) for seq in alt.seqs)
    return all_no_refs and has_group_alt


def _literal_strings_for_arm(seq: Sequence) -> list[str]:
    """Extract the literal values of a pure-literal arm (for PureLiteralAlt)."""
    stripped = strip_ws(seq)
    out: list[str] = []
    for it in stripped.items:
        if isinstance(it.atom, Literal):
            out.append(it.atom.value)
        elif isinstance(it.atom, CharClass):
            out.append(it.atom.pattern)
    return out


class Classifier:
    """Exhaustive GBNF-rule → Classification dispatch.

    Every rule lands in exactly one of the four Classification variants.
    Branches are ordered from most-specific to most-general; the final
    arm is the multi-arm general case. Each return below must cover a
    disjoint, exhaustive slice of the input space — adding a new branch
    requires re-proving exhaustiveness.
    """

    def classify(self, rule: Rule) -> Classification:
        alt = unwrap_group_alt(rule.body)
        if _is_structurally_complex(alt):
            return ValueStr()
        arms = [a for a in (strip_ws(seq) for seq in alt.seqs) if len(a.items) > 0]
        if not arms:
            return ValueStr()
        if len(arms) > 1 and all(_is_pure_literal_seq(a) for a in arms):
            return PureLiteralAlt(arms=[_literal_strings_for_arm(a) for a in arms])
        if (
            len(arms) == 1
            and len(arms[0].items) == 1
            and isinstance(arms[0].items[0].atom, Group)
            and arms[0].items[0].quantifier is None
            and all(
                _is_pure_literal_seq(strip_ws(s))
                for s in arms[0].items[0].atom.alt.seqs
            )
        ):
            inner_arms = [strip_ws(s) for s in arms[0].items[0].atom.alt.seqs]
            return PureLiteralAlt(
                arms=[_literal_strings_for_arm(a) for a in inner_arms]
            )
        if len(arms) == 1:
            full_seqs = alt.seqs
            has_any_rule_ref = any(
                any(isinstance(it.atom, RuleRef) for it in s.items)
                for s in full_seqs
            )
            if not has_any_rule_ref and _is_pure_literal_seq(arms[0]):
                return ValueStr()
            return SequenceKind(body=arms[0])
        # len(arms) > 1 and not all-pure-literal → treat as named alternation,
        # whether or not any arm is a single ruleref.
        assert len(arms) > 1, "single-arm case handled above"
        return NamedAlt(arms=arms)
```

- [ ] **Step 4: Run new tests; verify pass**

- [ ] **Step 5: Delete predicates from `ir_builder.py`**

In `src/lexic/codegen/ir_builder.py`:

1. Delete: `_is_ws_item`, `_strip_ws`, `_is_pure_literal`,
   `_is_pure_literal_seq`, `_is_single_ruleref`, `_unwrap_group_alt`,
   `_has_any_ruleref`, `_has_nontrivial_group`, `_has_group_with_alt`,
   `_is_structurally_complex`, `_classify`. Keep `_to_regex`, `_to_gbnf`,
   `_build_inline_regex`.
2. Add imports — the orchestrator pulls classification variants from
   `classify.py` and the shared AST helpers from `ast_utils.py`:
   ```python
   from lexic.codegen.ast_utils import (
       single_ruleref_of,
       strip_ws,
       unwrap_group_alt,
   )
   from lexic.codegen.classify import (
       Classifier,
       NamedAlt,
       PureLiteralAlt,
       SequenceKind,
       ValueStr,
   )
   ```
   Do **not** re-export underscore names from `classify.py` under new
   aliases. `ast_utils.py` is the canonical home for shared helpers.
3. In `IRBuilder.__init__`, add `self._classifier = Classifier()`.
4. Rewrite `_compute_parents` to consume the `Classifier` / union
   (replacing the old `_classify(rule) == "named_alt"` string compare
   and ad-hoc helper calls):
   ```python
   def _compute_parents(self) -> dict[str, str]:
       """For each rule that is a named arm of an alternation, record
       its parent class."""
       parent_of: dict[str, str] = {}
       for rule in self._rules:
           classification = self._classifier.classify(rule)
           if not isinstance(classification, NamedAlt):
               continue
           parent_cls = self._name_map[rule.name]
           for seq in classification.arms:
               ref = single_ruleref_of(seq)
               if ref is not None:
                   parent_of[ref] = parent_cls
       return parent_of
   ```
   Note: `classification.arms` is already ws-stripped (see
   `NamedAlt.arms` in classify.py), so the outer `strip_ws` call from
   the legacy implementation is no longer needed.

- [ ] **Step 6: Run full suite; verify green**

- [ ] **Step 7: Commit**

```bash
git add \
    src/lexic/codegen/ast_utils.py \
    src/lexic/codegen/classify.py \
    src/lexic/codegen/ir_builder.py \
    tests/unit/lexic/codegen/test_ast_utils.py \
    tests/unit/lexic/codegen/test_classify.py
git commit -m "refactor(ir_builder): extract Classifier + ast_utils with per-kind union return"
```

---

### Task 7: Split `IRBuilder._build_rule` into per-kind methods (relocated from Part E)

**Files:**
- Modify: `src/lexic/codegen/ir_builder.py`

Rationale: `_build_rule` has three branches (`value_str`/`pure_literal_alt`,
`named_alt`, `sequence`). Splitting mirrors the `Classification` union
and makes each branch independently readable. Each helper receives the
matched variant's payload directly.

Source content preserved at
`prototyping/next/draft/slice-b-moved.md`; this task adapts that
content to consume the Classification union introduced in Task 6.

- [ ] **Step 1: Read the current `_build_rule`; map each branch**

Open `src/lexic/codegen/ir_builder.py` and locate `_build_rule`. It
currently contains three consecutive branches selected by the
classification kind; after Task 6 lands, the selector is a match on
the `Classification` union but the branch *bodies* are unchanged and
re-used as-is. Identify:

1. `value_str` / `pure_literal_alt` branch → becomes `_build_value_str`.
   Starts at the comment `# value_str / pure_literal_alt → single
   `value: str` field`. Ends just before the `# named_alt` comment.
2. `named_alt` branch → becomes `_build_named_alt`. Starts at the
   `# named_alt` comment, ends just before the sequence branch. Use the
   `classification in (...)` / `if` marker in source to anchor the
   boundary; do not rely on line numbers, since Task 5 changed the
   surrounding file shape.
3. `sequence` branch → becomes `_build_sequence`. The final branch;
   runs through to the `return helper_specs_seq + [seq_spec]` (which
   Task 5 already turned into `return [seq_spec]`).

Copy each branch body verbatim into the corresponding new method in
Step 2; the match dispatch in Step 3 will be the only call site.

- [ ] **Step 2: Extract into three private methods**

In `src/lexic/codegen/ir_builder.py`, add three methods to
`IRBuilder`:

```python
def _build_value_str(self, rule, cls_name, parent_cls) -> list[RuleSpec]:
    alt = unwrap_group_alt(rule.body)
    items: list[Atom] = []
    for seq in alt.seqs:
        for it in seq.items:
            if isinstance(it.atom, CharClass):
                min_, max_ = quantifier_to_bounds(it.quantifier)
                items.append(CharClassAtom(it.atom.pattern, min_, max_))
            elif isinstance(it.atom, Literal):
                if it.quantifier is not None:
                    min_, max_ = quantifier_to_bounds(it.quantifier)
                    items.append(QuantifiedLiteralAtom(it.atom.value, min_, max_))
                else:
                    items.append(LiteralAtom(it.atom.value))
            elif isinstance(it.atom, Group):
                min_, max_ = quantifier_to_bounds(it.quantifier)
                items.append(_build_inline_regex(it.atom, min_, max_))
    return [RuleSpec(
        rule_name=rule.name, class_name=cls_name, parent_class_name=parent_cls,
        kind="value_str", items=items, field_map={},
    )]


def _build_named_alt(self, rule, cls_name, parent_cls, parent_of) -> list[RuleSpec]:
    alt = unwrap_group_alt(rule.body)
    arm_rule_names: list[str] = []
    arm_specs: list[RuleSpec] = []
    arm_idx = 0

    for seq in alt.seqs:
        stripped = strip_ws(seq)
        if not stripped.items:
            continue
        arm_idx += 1
        ref = single_ruleref_of(stripped)
        if ref is not None:
            arm_rule_names.append(ref)
        else:
            arm_rule_name = f"{rule.name}-arm{arm_idx}"
            arm_cls_name = f"{cls_name}Arm{arm_idx}"
            arm_rule_names.append(arm_rule_name)
            atoms = _seq_to_atoms(
                stripped, arm_cls_name, self._helpers, self._name_map, parent_of,
            )
            fm = assign_field_names(atoms)
            arm_specs.append(RuleSpec(
                rule_name=arm_rule_name, class_name=arm_cls_name,
                parent_class_name=cls_name, kind="sequence",
                items=atoms, field_map=fm,
            ))

    abstract_spec = RuleSpec(
        rule_name=rule.name, class_name=cls_name, parent_class_name=parent_cls,
        kind="alternation",
        items=[AlternationAtom(arm_rule_names=arm_rule_names)],
        field_map={},
    )
    return [abstract_spec] + arm_specs


def _build_sequence(self, rule, cls_name, parent_cls, parent_of) -> list[RuleSpec]:
    alt = unwrap_group_alt(rule.body)
    full_arms = [s for s in alt.seqs if strip_ws(s).items]
    arms = [strip_ws(s) for s in full_arms]
    if not arms:
        return [RuleSpec(
            rule_name=rule.name, class_name=cls_name, parent_class_name=parent_cls,
            kind="value_str", items=[], field_map={},
        )]
    atoms_seq = _seq_to_atoms(
        full_arms[0], cls_name, self._helpers, self._name_map, parent_of,
    )
    fm_seq = assign_field_names(atoms_seq)
    return [RuleSpec(
        rule_name=rule.name, class_name=cls_name, parent_class_name=parent_cls,
        kind="sequence", items=atoms_seq, field_map=fm_seq,
    )]
```

Rewrite `_build_rule` as a match-dispatch on the `Classification`
variant:

```python
from typing import assert_never

def _build_rule(self, rule, parent_of) -> list[RuleSpec]:
    classification = self._classifier.classify(rule)
    cls_name = self._name_map[rule.name]
    parent_cls = parent_of.get(rule.name, "GrammarModel")

    match classification:
        case ValueStr() | PureLiteralAlt():
            return self._build_value_str(rule, cls_name, parent_cls)
        case NamedAlt():
            return self._build_named_alt(rule, cls_name, parent_cls, parent_of)
        case SequenceKind():
            return self._build_sequence(rule, cls_name, parent_cls, parent_of)
        case _:
            assert_never(classification)
```

Delete the old `_build_rule` body.

The `assert_never` default makes the match statically exhaustive: adding
a sixth variant to the `Classification` union without adding a `case`
here will fail `mypy` / `pyright` and raise at runtime rather than
falling through silently.

- [ ] **Step 3: Run the full suite**

```bash
uv run pytest tests/ -q && uv run ruff check src/ tests/
```
Expected: all tests green.

- [ ] **Step 4: Commit**

```bash
git add src/lexic/codegen/ir_builder.py
git commit -m "refactor(ir_builder): split _build_rule into per-kind methods (match-dispatch)"
```

---

## PART C — Table-driven transformer

Convert `codegen/transformer.py` (the 267-line imperative
`_build_instance`) into a `transformer/` sub-package with explicit
`FieldBuilder` dispatch.

**Per brainstorm decision (spec §Q1):** `BuildContext` is frozen; the
orchestrator owns the cursor; builders return `FieldResult | SkipField`
(tagged union; no `_MISSING` sentinel).

Three tasks: first the scaffold with the protocol types and empty
registry; then per-atom builders; then the `Optional`/`List` wrapping
builders that replace the nested type-hint branches.

---

### Task 8: Scaffold `transformer/` sub-package + protocol types

**Files:**
- Create: `src/lexic/codegen/transformer/` (directory)
- Create: `src/lexic/codegen/transformer/__init__.py`
- Create: `src/lexic/codegen/transformer/context.py`
- Create: `src/lexic/codegen/transformer/registry.py`
- Create: `src/lexic/codegen/transformer/builders.py` (stubs)
- Create: `src/lexic/codegen/transformer/build_transformer.py` (moved
  contents of current `transformer.py`)
- Delete: `src/lexic/codegen/transformer.py`
- Create: `tests/unit/lexic/codegen/test_transformer_builders.py`

- [ ] **Step 1: Write failing tests for the protocol types and the empty registry**

Create `tests/unit/lexic/codegen/test_transformer_builders.py`:

```python
import dataclasses

import pytest

from lexic.ir import LiteralAtom, RuleSpec
from lexic.codegen.transformer.context import (
    BuildContext,
    FieldResult,
    SKIP_FIELD,
    SkipField,
)
from lexic.codegen.transformer.registry import BUILDER_BY_ATOM, builder_for


def _spec(items):
    return RuleSpec(
        rule_name="r", class_name="R", parent_class_name="GrammarModel",
        kind="sequence", items=items, field_map={},
    )


def test_build_context_is_immutable():
    ctx = BuildContext(spec=_spec([]), children=("a", "b", "c"), hints={}, cursor=0)
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        ctx.cursor = 5


def test_build_context_peek_exhausted():
    empty = BuildContext(spec=_spec([]), children=(), hints={})
    assert empty.exhausted() is True
    assert empty.peek() is None
    populated = BuildContext(spec=_spec([]), children=("x",), hints={})
    assert populated.exhausted() is False
    assert populated.peek() == "x"


def test_field_result_is_frozen():
    r = FieldResult(value=42, consumed=1)
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        r.value = 43


def test_skip_field_singleton():
    assert isinstance(SKIP_FIELD, SkipField)


def test_builder_for_unknown_raises():
    class FakeAtom: pass
    with pytest.raises(ValueError):
        builder_for(FakeAtom())
```

- [ ] **Step 2: Run; verify ImportError**

- [ ] **Step 3: Implement the scaffolding**

Create `src/lexic/codegen/transformer/__init__.py`:

```python
"""Build a Lark Transformer from RuleSpec IR + Pydantic classes.

Public surface: build_transformer(specs, classes). Internals:
- context.py    BuildContext, FieldResult, SkipField, SKIP_FIELD, BuildResult
- registry.py   BUILDER_BY_ATOM dispatch table + builder_for()
- builders.py   FieldBuilder implementations per atom type
"""

from lexic.codegen.transformer.build_transformer import build_transformer

__all__ = ["build_transformer"]
```

Create `src/lexic/codegen/transformer/context.py`:

```python
"""Protocol types for FieldBuilder dispatch.

Per design spec §Q1: BuildContext is frozen; orchestrator owns cursor.
Builders return FieldResult | SkipField (tagged union, no sentinels).

FieldBuilder (the Protocol) lives here — next to the types it quantifies
over (BuildContext, BuildResult) — so that builders.py implements it and
registry.py consumes it without creating a registry→builders→registry
import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from lexic.ir import Atom, RuleSpec


@dataclass(frozen=True)
class BuildContext:
    spec: RuleSpec
    children: tuple[Any, ...]
    hints: Mapping[str, type]
    cursor: int = 0

    def peek(self) -> Any | None:
        return self.children[self.cursor] if self.cursor < len(self.children) else None

    def exhausted(self) -> bool:
        return self.cursor >= len(self.children)


@dataclass(frozen=True)
class SkipField:
    """Signal: do not include this field in kwargs."""


SKIP_FIELD = SkipField()


@dataclass(frozen=True)
class FieldResult:
    value: Any
    consumed: int


BuildResult = FieldResult | SkipField


class FieldBuilder(Protocol):
    def build(
        self, atom: Atom, field_name: str, ctx: BuildContext
    ) -> BuildResult: ...
```

Create `src/lexic/codegen/transformer/registry.py`:

```python
"""BUILDER_BY_ATOM dispatch table."""

from __future__ import annotations

from lexic.ir import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.codegen.transformer.builders import (
    AbstractAlternationBuilder,
    CharClassFieldBuilder,
    InlineAlternationBuilder,
    InlineRegexBuilder,
    LiteralSkipBuilder,
    QuantifiedLiteralBuilder,
    RuleRefBuilder,
)
from lexic.codegen.transformer.context import FieldBuilder


BUILDER_BY_ATOM: dict[type, FieldBuilder] = {
    LiteralAtom:           LiteralSkipBuilder(),
    CharClassAtom:         CharClassFieldBuilder(),
    QuantifiedLiteralAtom: QuantifiedLiteralBuilder(),
    InlineRegexAtom:       InlineRegexBuilder(),
    RuleRefAtom:           RuleRefBuilder(),
    InlineAlternationAtom: InlineAlternationBuilder(),
    AlternationAtom:       AbstractAlternationBuilder(),
}


def builder_for(atom: Atom) -> FieldBuilder:
    builder = BUILDER_BY_ATOM.get(type(atom))
    if builder is None:
        raise ValueError(
            f"No builder registered for atom type {type(atom).__name__}"
        )
    return builder
```

Create `src/lexic/codegen/transformer/builders.py` with stubs (Task 9
fills in behaviour):

```python
"""FieldBuilder implementations per atom type.

Each builder is stateless; BuildContext is frozen and passed in. Task 9
fills in the real behaviour.
"""

from __future__ import annotations

from lexic.codegen.transformer.context import (
    BuildContext,
    BuildResult,
    FieldResult,
    SKIP_FIELD,
)


class LiteralSkipBuilder:
    """LiteralAtoms are never fields; this builder is never called."""

    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise AssertionError("LiteralSkipBuilder should never be invoked")


class CharClassFieldBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise NotImplementedError


class QuantifiedLiteralBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise NotImplementedError


class InlineRegexBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise NotImplementedError


class RuleRefBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise NotImplementedError


class InlineAlternationBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise NotImplementedError


class AbstractAlternationBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        raise AssertionError(
            "AbstractAlternationBuilder handled at orchestrator level"
        )
```

- [ ] **Step 4: Move existing `build_transformer` into the sub-package unchanged**

Create `src/lexic/codegen/transformer/build_transformer.py` with the
exact contents of today's `src/lexic/codegen/transformer.py` — this
preserves all behaviour while the dispatch plumbing is being wired in.
Task 10 replaces `_build_instance`'s body with the dispatch.

Update imports at the top of the new file:
```python
from lark import Token, Transformer, Tree

from lexic.ir import (
    CharClassAtom,
    LiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.utils.escapes import decode_gbnf_escapes
from lexic.utils.names import to_lark_name
```

- [ ] **Step 5: Delete the old `src/lexic/codegen/transformer.py`**

```bash
git rm src/lexic/codegen/transformer.py
```

- [ ] **Step 6: Run the full suite + new scaffold tests**

```bash
uv run pytest tests/ -q && uv run ruff check src/ tests/
```
Expected: `312 + N new scaffold tests` passed, clean.

- [ ] **Step 7: Commit**

```bash
git add src/lexic/codegen/transformer/ tests/unit/lexic/codegen/test_transformer_builders.py
git add -u src/lexic/codegen/transformer.py
git commit -m "refactor(transformer): scaffold transformer/ sub-package with immutable BuildContext + SkipField"
```

---

### Task 9: Implement per-atom `FieldBuilder`s

**Files:**
- Modify: `src/lexic/codegen/transformer/builders.py`
- Modify: `tests/unit/lexic/codegen/test_transformer_builders.py`

Rationale: fills in each builder's behaviour with unit tests first.
Behaviour mirrors the branches of today's `_build_instance`; Task 10
replaces the body of `_build_instance` with the dispatch.

**Per brainstorm decision (spec §E):** `RuleRefBuilder` gets tests
covering all four behavioral branches (ws/non-ws × child-present/absent).

- [ ] **Step 1: Write tests for `CharClassFieldBuilder`**

Append to `tests/unit/lexic/codegen/test_transformer_builders.py`:

```python
from lark import Token

from lexic.ir import CharClassAtom
from lexic.codegen.transformer.builders import CharClassFieldBuilder


def _mktoken(text: str) -> Token:
    return Token("X", text)


def test_charclass_single_char():
    atom = CharClassAtom(pattern="[0-9]", min=1, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(_mktoken("7"),), hints={"d": str})
    result = CharClassFieldBuilder().build(atom, "d", ctx)
    assert result == FieldResult(value="7", consumed=1)


def test_charclass_multi_char_consumes_consecutive_tokens():
    atom = CharClassAtom(pattern="[0-9]", min=1, max=None)
    children = (_mktoken("1"), _mktoken("2"), _mktoken("3"))
    ctx = BuildContext(spec=_spec([atom]), children=children, hints={"d": str})
    result = CharClassFieldBuilder().build(atom, "d", ctx)
    assert result == FieldResult(value="123", consumed=3)


def test_charclass_optional_with_no_child_returns_empty():
    atom = CharClassAtom(pattern="[+-]", min=0, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"opt": str})
    result = CharClassFieldBuilder().build(atom, "opt", ctx)
    assert result == FieldResult(value="", consumed=0)
```

- [ ] **Step 2: Run; verify the three new tests fail with `NotImplementedError`**

- [ ] **Step 3: Implement `CharClassFieldBuilder`**

Replace the class body in `builders.py`:

```python
from lark import Token

from lexic.ir import CharClassAtom


class CharClassFieldBuilder:
    def build(self, atom: CharClassAtom, field_name: str, ctx: BuildContext) -> BuildResult:
        if ctx.exhausted():
            return FieldResult(value="", consumed=0)
        c = ctx.peek()
        if not isinstance(c, (Token, str)):
            return FieldResult(value="", consumed=0)
        if atom.max != 1:
            parts = [str(c)]
            i = ctx.cursor + 1
            while i < len(ctx.children) and isinstance(ctx.children[i], (Token, str)):
                parts.append(str(ctx.children[i]))
                i += 1
            return FieldResult(value="".join(parts), consumed=i - ctx.cursor)
        return FieldResult(value=str(c), consumed=1)
```

Note: the pre-brainstorming draft had a dead branch (`if atom.min == 0`
on both paths of an if/else doing the same thing). Removed here.

- [ ] **Step 4: Run; verify `CharClassFieldBuilder` tests pass**

- [ ] **Step 5: Repeat the test-first cycle for each remaining builder**

For each of `QuantifiedLiteralBuilder`, `InlineRegexBuilder`,
`RuleRefBuilder`, `InlineAlternationBuilder`:

1. Add unit tests covering the happy path + edge cases.
2. Run — verify fail.
3. Implement by lifting behaviour from the corresponding branch of
   today's `_build_instance` (now at
   `src/lexic/codegen/transformer/build_transformer.py`).
4. Run — verify pass.

Behaviour to lift:

- **`QuantifiedLiteralBuilder`** — field is `str`; consumes up to 1
  Token/str child if present, otherwise returns `""`.

- **`InlineRegexBuilder`** — field is `str`; consumes 1 Token/str child
  if present, otherwise returns `""`.

- **`RuleRefBuilder`** — field is a `GrammarModel` subclass named by
  `ctx.hints[field_name]`. Four cases; each has its own test (below).

- **`InlineAlternationBuilder`** — field is `str` (via `value` field
  name). Consumes one string child.

`AbstractAlternationBuilder` is handled at the orchestrator level, not
per-field — the stub's `raise AssertionError` is correct.

**`RuleRefBuilder` test matrix** — write these four tests verbatim into
`tests/unit/lexic/codegen/test_transformer_builders.py`:

```python
from lexic.base import GrammarModel
from lexic.ir import RuleRefAtom
from lexic.codegen.transformer.builders import RuleRefBuilder


class _Ws(GrammarModel):
    value: str = ""


class _Expr(GrammarModel):
    value: str = ""


def test_ruleref_ws_with_child_consumes():
    atom = RuleRefAtom(rule_name="ws", min=1, max=1)
    child = _Ws(value=" ")
    ctx = BuildContext(
        spec=_spec([atom]), children=(child,), hints={"ws": _Ws}
    )
    result = RuleRefBuilder().build(atom, "ws", ctx)
    assert result == FieldResult(value=child, consumed=1)


def test_ruleref_ws_without_child_returns_empty_instance():
    atom = RuleRefAtom(rule_name="ws", min=0, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"ws": _Ws})
    result = RuleRefBuilder().build(atom, "ws", ctx)
    assert isinstance(result, FieldResult)
    assert result.consumed == 0
    assert isinstance(result.value, _Ws)


def test_ruleref_nonws_with_child_consumes():
    atom = RuleRefAtom(rule_name="expr", min=1, max=1)
    child = _Expr(value="1+1")
    ctx = BuildContext(
        spec=_spec([atom]), children=(child,), hints={"expr": _Expr}
    )
    result = RuleRefBuilder().build(atom, "expr", ctx)
    assert result == FieldResult(value=child, consumed=1)


def test_ruleref_nonws_missing_child_with_str_hint_returns_empty():
    atom = RuleRefAtom(rule_name="expr", min=0, max=1)
    # Hint accepts str; the four-case matrix's "no child + str-accepting hint"
    # case returns FieldResult(value="", consumed=0) rather than SKIP_FIELD.
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"expr": str})
    result = RuleRefBuilder().build(atom, "expr", ctx)
    assert result == FieldResult(value="", consumed=0)


def test_ruleref_nonws_missing_child_with_model_hint_skips():
    atom = RuleRefAtom(rule_name="expr", min=0, max=1)
    # Hint is a GrammarModel subclass with no default; the "no child +
    # non-str hint" case returns SKIP_FIELD so the orchestrator omits it.
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"expr": _Expr})
    result = RuleRefBuilder().build(atom, "expr", ctx)
    assert isinstance(result, SkipField)
```

The five tests (four primary + the SKIP_FIELD branch) cover every
behavioral path of the `RuleRefBuilder` — no branch is exercised only
by integration tests.

- [ ] **Step 6: Run the full suite + new builder tests**

- [ ] **Step 7: Commit**

```bash
git add src/lexic/codegen/transformer/builders.py tests/unit/lexic/codegen/test_transformer_builders.py
git commit -m "feat(transformer): implement per-atom FieldBuilders with unit tests"
```

---

### Task 10: Add `Optional`/`List` wrapping builders + replace `_build_instance` body

**Files:**
- Modify: `src/lexic/codegen/transformer/builders.py`
- Modify: `src/lexic/codegen/transformer/build_transformer.py`
- Modify: `tests/unit/lexic/codegen/test_transformer_builders.py`

Rationale: the last big branch of `_build_instance` is the type-hint
tri-split (list / optional / plain). Express these as wrapping builders
so the core dispatch loop has zero `isinstance` checks against type
hints.

- [ ] **Step 1: Write tests for `OptionalFieldBuilder` and `ListFieldBuilder`**

Append:

```python
from lexic.codegen.transformer.builders import (
    ListFieldBuilder,
    OptionalFieldBuilder,
)


def test_optional_empty_returns_none():
    inner = CharClassFieldBuilder()
    wrapped = OptionalFieldBuilder(inner)
    atom = CharClassAtom(pattern="[0-9]", min=0, max=1)
    ctx = BuildContext(spec=_spec([atom]), children=(), hints={"opt": str})
    assert wrapped.build(atom, "opt", ctx) == FieldResult(value=None, consumed=0)


def test_optional_with_child_delegates_to_inner():
    inner = CharClassFieldBuilder()
    wrapped = OptionalFieldBuilder(inner)
    atom = CharClassAtom(pattern="[0-9]", min=0, max=1)
    ctx = BuildContext(
        spec=_spec([atom]), children=(_mktoken("5"),), hints={"opt": str}
    )
    assert wrapped.build(atom, "opt", ctx) == FieldResult(value="5", consumed=1)


def test_list_collects_while_inner_matches():
    inner = CharClassFieldBuilder()
    wrapped = ListFieldBuilder(inner, inner_type=str)
    atom = CharClassAtom(pattern="[0-9]", min=0, max=None)
    ctx = BuildContext(
        spec=_spec([atom]),
        children=(_mktoken("1"), _mktoken("2"), _mktoken("3")),
        hints={"xs": list[str]},
    )
    result = wrapped.build(atom, "xs", ctx)
    assert result.consumed == 3


def test_list_with_grammarmodel_inner_collects_matching_models():
    """ListFieldBuilder must walk the GrammarModel branch (not just the
    str branch). Covers the isinstance(c, GrammarModel) path at line
    ~2233 of the implementation."""
    from lexic.ir import RuleRefAtom
    from lexic.codegen.transformer.builders import RuleRefBuilder

    class _Item(GrammarModel):
        value: str = ""

    atom = RuleRefAtom(rule_name="item", min=0, max=None)
    a, b = _Item(value="a"), _Item(value="b")
    ctx = BuildContext(
        spec=_spec([atom]),
        children=(a, b),
        hints={"items": list[_Item]},
    )
    wrapped = ListFieldBuilder(RuleRefBuilder(), inner_type=_Item)
    result = wrapped.build(atom, "items", ctx)
    assert result.value == [a, b]
    assert result.consumed == 2
```

- [ ] **Step 2: Run; verify fail**

- [ ] **Step 3: Implement `OptionalFieldBuilder` and `ListFieldBuilder`**

Append to `src/lexic/codegen/transformer/builders.py`:

```python
from dataclasses import replace
from typing import Any

from lark import Token

from lexic.base import GrammarModel


class OptionalFieldBuilder:
    """Wraps an inner builder; returns FieldResult(None, 0) when the
    inner declines (SkipField, or FieldResult with consumed==0 and an
    empty/None value). Otherwise delegates to the inner result."""

    _EMPTY_VALUES: frozenset[object] = frozenset(("", None))

    def __init__(self, inner):
        self._inner = inner

    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        if ctx.exhausted():
            return FieldResult(value=None, consumed=0)
        result = self._inner.build(atom, field_name, ctx)
        if isinstance(result, SkipField):
            return FieldResult(value=None, consumed=0)
        if (
            isinstance(result, FieldResult)
            and result.consumed == 0
            and result.value in self._EMPTY_VALUES
        ):
            return FieldResult(value=None, consumed=0)
        return result


class ListFieldBuilder:
    """Collects a list of inner-builder results until inner stops consuming."""

    def __init__(self, inner, *, inner_type: type):
        self._inner = inner
        self._inner_type = inner_type

    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        collected: list[Any] = []
        cursor = ctx.cursor
        while cursor < len(ctx.children):
            local_ctx = replace(ctx, cursor=cursor)
            c = local_ctx.peek()
            if self._inner_type is str or self._inner_type is type(None):
                if not isinstance(c, (Token, str)):
                    break
            else:
                if isinstance(c, GrammarModel) and isinstance(c, self._inner_type):
                    pass
                elif isinstance(c, (Token, str)):
                    # Stray filler token between list items — skip it.
                    cursor += 1
                    continue
                else:
                    break
            sub = self._inner.build(atom, field_name, local_ctx)
            if isinstance(sub, SkipField) or (isinstance(sub, FieldResult) and sub.consumed == 0):
                break
            collected.append(sub.value)
            cursor += sub.consumed
        return FieldResult(value=collected, consumed=cursor - ctx.cursor)
```

Note: builders synthesise a fresh frozen `BuildContext` via
`dataclasses.replace` rather than mutating. The `ListFieldBuilder`
advances a local `cursor` and only surfaces the total `consumed` in the
returned `FieldResult`.

- [ ] **Step 4: Run; verify the three new tests pass**

- [ ] **Step 5: Rewrite `_build_instance` to dispatch through `BUILDER_BY_ATOM`**

In `src/lexic/codegen/transformer/build_transformer.py`, replace the
entire `_build_instance` function (the big imperative block) with:

```python
def _build_instance(cls, spec: RuleSpec, items: list):
    """Build a Pydantic instance via BUILDER_BY_ATOM dispatch.

    Replaces the imperative 140-line body with:
      1. Filter filtered-literal tokens out of `items`.
      2. For each named field, look up the atom's base builder, wrap it in
         Optional/List if the hint requires it, and delegate.
    """
    from dataclasses import replace as dc_replace
    from typing import get_args, get_origin, get_type_hints

    from lexic.codegen.transformer.context import (
        BuildContext, FieldResult, SkipField,
    )
    from lexic.codegen.transformer.registry import builder_for
    from lexic.codegen.transformer.builders import (
        ListFieldBuilder, OptionalFieldBuilder,
    )

    children = tuple(i for i in items if i is not None)

    non_field_regex_values = {
        decode_gbnf_escapes(a.value)
        for a in spec.items
        if isinstance(a, LiteralAtom) and not _literal_is_quoted(a.value)
    }
    if non_field_regex_values:
        children = tuple(
            c
            for c in children
            if not (isinstance(c, Token) and str(c) in non_field_regex_values)
        )

    try:
        hints = get_type_hints(cls)
    except Exception:
        hints = {k: v for k, v in cls.__annotations__.items()}

    ctx = BuildContext(spec=spec, children=children, hints=hints, cursor=0)
    ordered = sorted(spec.field_map.items(), key=lambda x: x[1])
    kwargs: dict[str, object] = {}

    for fname, item_idx in ordered:
        atom = spec.items[item_idx] if 0 <= item_idx < len(spec.items) else None
        if atom is None:
            continue
        hint = hints.get(fname)
        base = builder_for(atom)
        origin = get_origin(hint)
        args = get_args(hint)
        if origin is list:
            inner = args[0] if args else str
            b = ListFieldBuilder(base, inner_type=inner)
        elif hint is not None and type(None) in (args or ()):
            b = OptionalFieldBuilder(base)
        else:
            b = base
        result = b.build(atom, fname, ctx)
        match result:
            case SkipField():
                continue
            case FieldResult(value=v, consumed=n):
                kwargs[fname] = v
                ctx = dc_replace(ctx, cursor=ctx.cursor + n)

    return cls(**kwargs)
```

- [ ] **Step 6: Delete now-dead helpers in `build_transformer.py`**

Remove `_is_ws_ref`, `_is_optional_char`, and the unused `_flatten`
helper (dead code — no external callers; only self-recursive). Their
logic (for the first two) now lives in the per-atom builders.
`_literal_is_quoted` stays because the orchestrator still uses it to
filter regex-terminal literal tokens out of `children` before
dispatch.

- [ ] **Step 7: Run the full suite**

```bash
uv run pytest tests/ -q && uv run ruff check src/ tests/
```
Expected: all green. If a property test fails on one of the seven
grammars, diff the failing case's tree against the old `_build_instance`
behaviour — the dispatch must match it exactly.

- [ ] **Step 8: Verify no `isinstance` cascade over atom types in `builders.py`**

```bash
uv run grep -n "isinstance.*Atom" src/lexic/codegen/transformer/builders.py
```
Expected: zero matches inside builder bodies. Type-narrowing
`isinstance` on `Token`/`GrammarModel` is permitted; cascading over
atom types is not.

- [ ] **Step 9: Commit**

```bash
git add src/lexic/codegen/transformer/
git commit -m "refactor(transformer): dispatch _build_instance through BUILDER_BY_ATOM (immutable ctx)"
```

---

## PART D — `CompiledGrammar` + memoised `compile()`

Eliminates the per-call codegen in `parse()`. Closes V3 §8.

**Per brainstorm decision (spec §Q3):**
- Memo key: `(str(path), mtime, size)` — one-line upgrade over the
  pre-brainstorming draft's `(path, mtime)`.
- Primary entry: `compile(text, *, cache_key=None)` — the string-taker is
  the canonical name; path-accepting is the wrapper.
- `compile_from_path(path)` is the thin wrapper; both share one cache.
- `CompiledGrammar.specs: dict[str, RuleSpec]` (matches roadmap).

---

### Task 11: Introduce `CompiledGrammar`, `compile`, and `compile_from_path`

**Files:**
- Create: `src/lexic/compile.py`
- Create: `tests/unit/lexic/test_compile.py`
- Modify: `src/lexic/parse.py`

- [ ] **Step 1: Write failing tests for `CompiledGrammar`**

Create `tests/unit/lexic/test_compile.py`:

```python
import time
from pathlib import Path

import pytest

from lexic.compile import (
    CompiledGrammar,
    compile,
    compile_from_path,
    reset_cache_for_tests,
)

GROUND_TRUTH = Path(__file__).resolve().parents[2] / "resources" / "ground_truth"


@pytest.fixture(autouse=True)
def clear_cache():
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def test_compile_from_path_returns_compiled_grammar():
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg, CompiledGrammar)
    assert cg.classes
    assert isinstance(cg.specs, dict)
    assert cg.specs


def test_compile_from_path_memoises_by_path_mtime_size():
    src = GROUND_TRUTH / "arithmetic.gbnf"
    cg1 = compile_from_path(src)
    cg2 = compile_from_path(src)
    assert cg1 is cg2


def test_compile_from_path_invalidates_on_mtime_change(tmp_path):
    src = tmp_path / "g.gbnf"
    src.write_text("root ::= \"a\"\n")
    cg1 = compile_from_path(src)
    time.sleep(0.01)
    src.write_text("root ::= \"b\"\n")
    cg2 = compile_from_path(src)
    assert cg1 is not cg2


def test_compile_from_path_invalidates_on_size_change_same_mtime(tmp_path, monkeypatch):
    """Same mtime but different size should invalidate — catches test-FS edge case."""
    src = tmp_path / "g.gbnf"
    src.write_text("root ::= \"aa\"\n")
    cg1 = compile_from_path(src)
    # Preserve mtime; change size.
    original_mtime = src.stat().st_mtime
    src.write_text("root ::= \"bbb\"\n")
    import os
    os.utime(src, (original_mtime, original_mtime))
    cg2 = compile_from_path(src)
    assert cg1 is not cg2


def test_compile_no_cache_by_default():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg1 = compile(text)
    cg2 = compile(text)
    assert cg1 is not cg2  # no cache_key → no memoization


def test_compile_with_cache_key():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg1 = compile(text, cache_key="fixture-a")
    cg2 = compile(text, cache_key="fixture-a")
    assert cg1 is cg2


def test_compile_and_compile_from_path_share_cache():
    """compile_from_path(path) should cache-hit after a prior compile(text, cache_key=key)
    with the same key — they use one _CACHE dict."""
    path = GROUND_TRUTH / "arithmetic.gbnf"
    resolved = str(path.resolve())
    stat = path.stat()
    key = (resolved, stat.st_mtime, stat.st_size)
    cg1 = compile(path.read_text(), cache_key=key)
    cg2 = compile_from_path(path)
    assert cg1 is cg2


def test_compiled_grammar_parse_roundtrips():
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("1+1")
    assert inst.to_text() == "1+1"


def test_repeated_parse_is_fast():
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    cg.parse("1+1")  # warm
    start = time.perf_counter()
    for _ in range(100):
        cg.parse("1+1")
    elapsed = time.perf_counter() - start
    # 0.5s = 5ms/call — 5x the <1ms/call design target (safety margin for
    # CI) and 10x under the ~5s a regressed per-parse-codegen path would
    # take. This gate catches regressions, not hair-splits.
    assert elapsed < 0.5, f"100 cached parses took {elapsed:.3f}s"
```

- [ ] **Step 2: Run; verify fail**

- [ ] **Step 3: Implement `compile.py`**

Create `src/lexic/compile.py`:

```python
"""CompiledGrammar: the compile-time artefacts parse() needs.

compile(text, *, cache_key) is the primary entry. compile_from_path(path)
is a thin wrapper that stats the file, builds a (path, mtime, size) key,
checks the cache to skip the file read on hit, and delegates to compile().

One cache covers both entry points.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Hashable

import lark

from lexic.codegen import codegen
from lexic.codegen.ir_builder import IRBuilder
from lexic.codegen.lark_builder import LarkBuilder
from lexic.codegen.parser import parse_gbnf

if TYPE_CHECKING:
    from lexic.base import GrammarModel
    from lexic.ir import RuleSpec


@dataclass(frozen=True)
class CompiledGrammar:
    classes: dict[str, type]
    specs: dict[str, "RuleSpec"]
    parser: "lark.Lark"
    transformer: "lark.Transformer"

    def parse(self, text: str) -> "GrammarModel":
        tree = self.parser.parse(text)
        return self.transformer.transform(tree)


_CACHE: dict[Hashable, CompiledGrammar] = {}


def reset_cache_for_tests() -> None:
    """Public test seam: clear the compile cache. Public name so tests do
    not reach into a leading-underscore symbol across modules."""
    _CACHE.clear()


def _stem_for_text(text: str) -> str:
    """Stable filename for a grammar string with no path."""
    return "anon_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _compile_core(text: str) -> CompiledGrammar:
    rules = parse_gbnf(text)
    specs_list = IRBuilder(rules).build()
    specs = {s.rule_name: s for s in specs_list}

    # codegen(text, *, stem) is the string-primary entry in lexic.codegen;
    # see the implementor note below for the required codegen factorisation.
    classes = codegen(text, stem=_stem_for_text(text))

    builder = LarkBuilder(specs_list)
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(
        grammar_str, parser="earley", ambiguity="resolve", start=start_rule
    )
    transformer = builder.build_transformer(classes)

    return CompiledGrammar(
        classes=classes, specs=specs, parser=parser, transformer=transformer
    )


def compile(text: str, *, cache_key: Hashable | None = None) -> CompiledGrammar:
    """Compile from a grammar string. cache_key=None means 'do not memoize'."""
    if cache_key is not None:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            return cached
    cg = _compile_core(text)
    if cache_key is not None:
        _CACHE[cache_key] = cg
    return cg


def compile_from_path(grammar_path: str | Path) -> CompiledGrammar:
    """Compile from a file path; memoised by (path, mtime, size).

    Thin read-file wrapper over compile(text, ...).
    """
    path = Path(grammar_path).resolve()
    stat = path.stat()
    key = (str(path), stat.st_mtime, stat.st_size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    return compile(path.read_text(), cache_key=key)
```

**Note for implementor:** Today `codegen()` accepts a path, but the
target API inverts the naming direction to match Pydantic's string-
primary convention. Before `compile()` can work, the codegen surface in
`lexic.codegen.__init__` must be flipped:
- `codegen(text: str, *, stem: str) -> dict[str, type]` becomes the
  primary string-taker.
- `codegen_from_path(grammar_path: str | Path) -> dict[str, type]`
  becomes the 2-line read-file wrapper that delegates to `codegen(...)`
  with `stem=path.stem`.

Add this flip as the first step of this task if it isn't already
present. Every existing in-tree call site of `codegen(path)` must be
updated to `codegen_from_path(path)`.

- [ ] **Step 4: Run new tests; verify pass**

- [ ] **Step 5: Rewrite `parse.py` on top of `compile_from_path()`**

Replace `src/lexic/parse.py` in full:

```python
"""parse(text, grammar_path) → GrammarModel instance.

Thin entry point: compile the grammar (memoised) then parse the text.
"""

from __future__ import annotations

from pathlib import Path

from lexic.base import GrammarModel
from lexic.compile import compile_from_path


def parse(text: str, grammar_path: str | Path) -> GrammarModel:
    """Parse text against a GBNF grammar and return a typed GrammarModel instance."""
    return compile_from_path(grammar_path).parse(text)
```

- [ ] **Step 6: Run the full suite**

- [ ] **Step 7: Commit**

```bash
git add src/lexic/compile.py tests/unit/lexic/test_compile.py src/lexic/parse.py
git commit -m "feat(compile): introduce CompiledGrammar + compile(text) + compile_from_path"
```

---

## PART E — SOLID pass on remaining large methods

---

### Task 12: Split `generate.generate` into per-kind helpers

**Files:**
- Modify: `src/lexic/generate.py`

Rationale: `generate()` is ~95 lines (lines 179–274) with three nested
behavioural branches. Split into `_gen_alternation`, `_gen_sequence`,
plus the existing `_gen_value_str`; `generate` dispatches.

- [ ] **Step 1: Ensure test coverage**

Ensure `tests/unit/lexic/test_generate.py` exercises:
- A sequence rule (e.g. root of arithmetic)
- An alternation rule
- A value_str rule (e.g. `num`)
- Recursion cap (max_depth=0 picks non-recursive arm)

If missing, add them.

- [ ] **Step 2: Refactor `generate.py`**

Split `generate()` into:

```python
def _gen_alternation(arms: list[str], specs, rng, max_depth) -> str:
    if not arms:
        return ""
    arm = rng.choice(arms)
    return generate(arm, specs, rng=rng, max_depth=max_depth - 1)


def _gen_sequence(spec, specs, rng, max_depth) -> str:
    parts: list[str] = []
    for atom in spec.items:
        if isinstance(atom, LiteralAtom):
            parts.append(decode_gbnf_escapes(atom.value))
        elif isinstance(atom, CharClassAtom):
            parts.append(_gen_charclass(atom.pattern, atom.min, atom.max, rng))
        elif isinstance(atom, QuantifiedLiteralAtom):
            count = _pick_count(atom.min, atom.max, rng)
            parts.append(decode_gbnf_escapes(atom.value) * count)
        elif isinstance(atom, InlineRegexAtom):
            parts.append(_gen_inline_regex(atom.gbnf, atom.min, atom.max, rng))
        elif isinstance(atom, RuleRefAtom):
            count = _pick_count(atom.min, atom.max, rng)
            for _ in range(count):
                parts.append(generate(atom.rule_name, specs, rng=rng, max_depth=max_depth - 1))
        elif isinstance(atom, (InlineAlternationAtom, AlternationAtom)):
            arm = rng.choice(atom.arm_rule_names)
            parts.append(generate(arm, specs, rng=rng, max_depth=max_depth - 1))
    return "".join(parts)


def _gen_sequence_min_depth(spec, specs, rng) -> str:
    parts: list[str] = []
    for atom in spec.items:
        if isinstance(atom, LiteralAtom):
            parts.append(decode_gbnf_escapes(atom.value))
        elif isinstance(atom, CharClassAtom) and atom.min >= 1:
            parts.append(_gen_charclass(atom.pattern, atom.min, atom.min, rng))
        elif isinstance(atom, QuantifiedLiteralAtom) and atom.min >= 1:
            parts.append(decode_gbnf_escapes(atom.value) * atom.min)
        elif isinstance(atom, InlineRegexAtom) and atom.min >= 1:
            parts.append(_gen_inline_regex(atom.gbnf, atom.min, atom.min, rng))
        elif isinstance(atom, RuleRefAtom) and atom.min >= 1:
            parts.append(generate(atom.rule_name, specs, rng=rng, max_depth=0))
    return "".join(parts)


def generate(rule_name, specs, *, rng=None, max_depth=5) -> str:
    if rng is None:
        rng = _random.Random()
    spec = specs.get(rule_name)
    if spec is None:
        return ""

    if max_depth <= 0:
        if spec.kind == "alternation":
            first = spec.items[0] if spec.items else None
            arms = first.arm_rule_names if isinstance(first, AlternationAtom) else []
            for arm in arms:
                result = generate(arm, specs, rng=rng, max_depth=0)
                if result:
                    return result
            return ""
        if spec.kind == "value_str":
            return _gen_value_str(spec, rng)
        return _gen_sequence_min_depth(spec, specs, rng)

    if spec.kind == "alternation":
        first = spec.items[0] if spec.items else None
        arms = first.arm_rule_names if isinstance(first, AlternationAtom) else []
        return _gen_alternation(arms, specs, rng, max_depth)
    if spec.kind == "value_str":
        return _gen_value_str(spec, rng)
    return _gen_sequence(spec, specs, rng, max_depth)
```

- [ ] **Step 3: Run the full suite**

- [ ] **Step 4: Commit**

```bash
git add src/lexic/generate.py
git commit -m "refactor(generate): split generate() into per-kind helpers"
```

---

### Task 13: Final exit-criteria audit

**Files:**
- (read-only) `src/lexic/**`, `tests/**`

- [ ] **Step 1: Confirm all 312+ tests pass**

```bash
uv run pytest tests/ -q
```

- [ ] **Step 2: Confirm `ir_builder.py` is under 200 lines**

```bash
wc -l src/lexic/codegen/ir_builder.py
```
Expected: output's line count ≤ 200. The architecture doc's "<200 LoC
target" is the hard gate for this audit.

- [ ] **Step 3: Confirm every `FieldBuilder` has a unit test**

```bash
grep -n "^class .*Builder" src/lexic/codegen/transformer/builders.py
uv run pytest tests/unit/lexic/codegen/test_transformer_builders.py -v --collect-only
```
Expected: for each builder class listed in the first command, the
second's output contains a `test_*` referencing it. Audit the two
lists by eye; they must agree. `RuleRefBuilder` must have five
collected tests (four behavioral branches + the SKIP_FIELD branch).

- [ ] **Step 4: Confirm no atom-type `isinstance` cascade**

```bash
grep -n "isinstance.*Atom" src/lexic/codegen/transformer/builders.py
```
Expected: no matches. (Architecture doc §Closed-but-versioned
prescribes dispatch-table lookups; ad-hoc isinstance cascades are not
acceptable after Slice A.)

- [ ] **Step 5: Confirm `parse()` uses `compile()` memo**

```bash
uv run pytest tests/unit/lexic/test_compile.py::test_repeated_parse_is_fast -v
uv run pytest tests/unit/lexic/test_compile.py::test_compile_from_path_memoises_by_path_mtime_size -v
uv run pytest tests/unit/lexic/test_compile.py::test_compile_and_compile_from_path_share_cache -v
```
Expected: all three pass. If `test_repeated_parse_is_fast` fails on a
slow CI runner but passes locally, inspect the elapsed number in the
failure message before loosening the threshold — the test's purpose is
to catch a regression where codegen runs per parse (typically ~50ms
each, so 100 iterations of a regressed path would take ≥ 5s).

- [ ] **Step 6: Confirm runtime→codegen edges are exactly the two
      deliberate ones**

```bash
grep -n "from lexic.codegen" src/lexic/base.py
grep -n "from lexic.codegen" src/lexic/compile.py
grep -n "from lexic.codegen" src/lexic/parse.py
grep -n "from lexic.codegen" src/lexic/generate.py
```
Expected:
- `base.py`: exactly one module-scope import (the `to_grammar`/
  `to_gbnf` edge).
- `compile.py`: exactly one module-scope import (the `codegen` edge
  documented as the second deliberate runtime↔codegen edge in
  `prototyping/next/2_ARCHITECTURE.md` §Layering rules).
- `parse.py`, `generate.py`: **no matches**. These runtime modules
  must not import from `lexic.codegen` directly — parse goes through
  `compile_from_path`.

- [ ] **Step 7: Confirm no lazy intra-function `lexic.codegen` imports
      from runtime**

```bash
grep -Ern "^\s{4,}from lexic\.codegen" src/lexic/base.py src/lexic/compile.py src/lexic/parse.py src/lexic/generate.py
```
Expected: no matches. Every runtime→codegen import is at module
scope; `TYPE_CHECKING` dodges and lazy intra-function imports from
runtime modules are forbidden (see `2_ARCHITECTURE.md` §Layering
rules).

- [ ] **Step 8: Confirm `BuildContext` is frozen**

```bash
grep -n "@dataclass(frozen=True)" src/lexic/codegen/transformer/context.py
```
Expected: `frozen=True` on `BuildContext`, `FieldResult`, and
`SkipField` (three matches minimum).

- [ ] **Step 9: Final lint**

```bash
uv run ruff check src/ tests/
```

- [ ] **Step 10: Final commit (empty if no diff)**

```bash
git add -u
git commit -m "chore: slice A exit-criteria audit fixes" || true
```

---

## Self-review checklist

- [x] Every Slice A scope item in `prototyping/next/3_ROADMAP.md` has a
      task.
- [x] Every exit criterion has an audit step in Task 13.
- [x] Brainstorm decisions (spec §Q1–§Q4) are reflected in the task
      detail.
- [x] Task 7 (was draft's Task 12) lives in Part B, consumes the
      Classification union.
- [x] `CompiledGrammar.specs` is `dict[str, RuleSpec]` (matches
      roadmap).
- [x] `BuildContext` is immutable; orchestrator owns cursor;
      `SkipField` replaces `_MISSING`.
- [x] `assign_field_names` is a module-level function, not a class.
- [x] `RuleRefBuilder` tests cover all 4 branches
      (ws/non-ws × child-present/absent).
- [x] Every task ends with a commit step.
