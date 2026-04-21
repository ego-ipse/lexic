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
memoised `compile_text`/`compile()` so `parse()` stops regenerating
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
3. Thread `self._helpers` through `_build_rule` and `_seq_to_atoms`
   instead of the local `helper_specs: list[RuleSpec]` parameter.
   Change the `_seq_to_atoms` signature to accept
   `helpers: HelperRuleRegistry` in place of `helper_specs`.
4. Replace the inline dedup block inside `_seq_to_atoms`:
   ```python
   # OLD
   helper_rule_name = f"{parent_class_name.lower()}-item"
   existing = {s.rule_name for s in helper_specs}
   suffix = 2
   candidate = helper_rule_name
   while candidate in existing:
       candidate = f"{helper_rule_name}{suffix}"
       suffix += 1
   helper_rule_name = candidate
   ```
   with:
   ```python
   helper_rule_name = helpers.reserve(f"{parent_class_name.lower()}-item")
   ```
5. Replace `helper_specs.append(helper_spec)` with
   `helpers.register(helper_spec)`.
6. In `build()`, collect per-rule output from `_build_rule` (non-helper
   specs only), then prepend `self._helpers.all_specs()` before
   topo-sort:
   ```python
   def build(self) -> list[RuleSpec]:
       parent_of = self._compute_parents()
       primary_specs: list[RuleSpec] = []
       for rule in self._rules:
           primary_specs.extend(self._build_rule(rule, parent_of))
       all_specs = primary_specs + self._helpers.all_specs()
       return self._topo_sort(all_specs)
   ```

- [ ] **Step 6: Run full suite; verify green**

- [ ] **Step 7: Commit**

```bash
git add src/lexic/codegen/helpers.py tests/unit/lexic/codegen/test_helpers.py src/lexic/codegen/ir_builder.py
git commit -m "refactor(ir_builder): extract HelperRuleRegistry, global helper dedup"
```

---

### Task 6: Extract `Classifier` into `codegen/classify.py` (union return)

**Files:**
- Create: `src/lexic/codegen/classify.py`
- Create: `tests/unit/lexic/codegen/test_classify.py`
- Modify: `src/lexic/codegen/ir_builder.py`

Rationale: closes V3 §2. Pulls ~150 lines of GBNF-AST analysis out of
`IRBuilder`.

**Per brainstorm decision (spec §Q2):** `Classification` is a union of
four per-kind frozen dataclasses. Each variant carries exactly the
payload its downstream handler needs — eliminates AST re-traversal in
callers.

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
    # A group-with-alt that is all-literal should collapse to value_str.
    # (Fixture left to plan executor to construct per exact signal of _is_structurally_complex.)
    pass


def test_empty_arms_returns_value_str():
    body = _alt()  # no sequences
    assert isinstance(Classifier().classify(_rule("empty", body)), ValueStr)
```

- [ ] **Step 2: Run; verify fail**

- [ ] **Step 3: Implement `Classification` union + predicates**

Create `src/lexic/codegen/classify.py`:

```python
"""Classifier: determine a GBNF rule's IR kind.

Given a Rule from the GBNF AST, classify() returns one of four
Classification variants, each carrying exactly the payload its
downstream handler needs. AST-traversal predicates live as module
helpers (used only by Classifier).
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


def _is_ws_item(item: Item) -> bool:
    return isinstance(item.atom, RuleRef) and item.atom.name == "ws"


def _strip_ws(seq: Sequence) -> Sequence:
    return Sequence([it for it in seq.items if not _is_ws_item(it)])


def _is_pure_literal(item: Item) -> bool:
    return isinstance(item.atom, (Literal, CharClass))


def _is_pure_literal_seq(seq: Sequence) -> bool:
    stripped = _strip_ws(seq)
    return len(stripped.items) > 0 and all(
        _is_pure_literal(it) for it in stripped.items
    )


def _is_single_ruleref(seq: Sequence) -> str | None:
    stripped = _strip_ws(seq)
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
            inner_stripped = _strip_ws(inner.seqs[0])
            if len(inner_stripped.items) == 1:
                inner_it = inner_stripped.items[0]
                if inner_it.quantifier is None and isinstance(inner_it.atom, RuleRef):
                    return inner_it.atom.name
    return None


def _unwrap_group_alt(alt: Alternation) -> Alternation:
    if len(alt.seqs) != 1:
        return alt
    stripped = _strip_ws(alt.seqs[0])
    if len(stripped.items) == 1:
        it = stripped.items[0]
        if isinstance(it.atom, Group) and it.quantifier is None:
            return it.atom.alt
    return alt


def _has_any_ruleref(items: list[Item]) -> bool:
    for it in items:
        if _is_ws_item(it):
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
        stripped = _strip_ws(seq)
        for it in stripped.items:
            if isinstance(it.atom, Group) and it.quantifier == "*":
                for inner_seq in it.atom.alt.seqs:
                    if _has_nontrivial_group(inner_seq.items):
                        return True
    all_no_refs = not any(_has_any_ruleref(_strip_ws(seq).items) for seq in alt.seqs)
    has_group_alt = any(_has_group_with_alt(_strip_ws(seq).items) for seq in alt.seqs)
    return all_no_refs and has_group_alt


def _literal_strings_for_arm(seq: Sequence) -> list[str]:
    """Extract the literal values of a pure-literal arm (for PureLiteralAlt)."""
    stripped = _strip_ws(seq)
    out: list[str] = []
    for it in stripped.items:
        if isinstance(it.atom, Literal):
            out.append(it.atom.value)
        elif isinstance(it.atom, CharClass):
            out.append(it.atom.pattern)
    return out


class Classifier:
    def classify(self, rule: Rule) -> Classification:
        alt = _unwrap_group_alt(rule.body)
        if _is_structurally_complex(alt):
            return ValueStr()
        arms = [a for a in (_strip_ws(seq) for seq in alt.seqs) if len(a.items) > 0]
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
                _is_pure_literal_seq(_strip_ws(s))
                for s in arms[0].items[0].atom.alt.seqs
            )
        ):
            inner_arms = [_strip_ws(s) for s in arms[0].items[0].atom.alt.seqs]
            return PureLiteralAlt(
                arms=[_literal_strings_for_arm(a) for a in inner_arms]
            )
        if len(arms) > 1 and any(_is_single_ruleref(a) is not None for a in arms):
            return NamedAlt(arms=arms)
        if len(arms) == 1:
            full_seqs = alt.seqs
            has_any_rule_ref = any(
                any(isinstance(it.atom, RuleRef) for it in s.items)
                for s in full_seqs
            )
            if not has_any_rule_ref and _is_pure_literal_seq(arms[0]):
                return ValueStr()
            return SequenceKind(body=arms[0])
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
2. Add imports — **only what the orchestrator still needs**:
   ```python
   from lexic.codegen.classify import (
       Classifier,
       NamedAlt,
       PureLiteralAlt,
       SequenceKind,
       ValueStr,
   )
   ```
   Note: unlike the pre-brainstorming draft, we do **not** re-export
   the predicates. `_compute_parents` and `_seq_to_atoms` need tiny
   helpers for `_strip_ws`/`_unwrap_group_alt`/`_is_single_ruleref` —
   these become public helpers on a small module (`classify_helpers` or
   exposed from `classify.py` as `strip_ws`/`unwrap_group_alt`/`single_ruleref_of`
   without underscores), since the underscore-re-export pattern is the
   exact leaky abstraction this refactor is closing.

   Concretely: expose three names from `classify.py` without the
   leading underscore:
   ```python
   # In classify.py, add at module bottom:
   strip_ws = _strip_ws
   unwrap_group_alt = _unwrap_group_alt
   single_ruleref_of = _is_single_ruleref
   ```
   and import those from `ir_builder.py`.
3. In `IRBuilder.__init__`, add `self._classifier = Classifier()`.

- [ ] **Step 6: Run full suite; verify green**

- [ ] **Step 7: Commit**

```bash
git add src/lexic/codegen/classify.py tests/unit/lexic/codegen/test_classify.py src/lexic/codegen/ir_builder.py
git commit -m "refactor(ir_builder): extract Classifier with per-kind union return"
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

Identify the three blocks:
1. Lines ~532–566: `value_str` / `pure_literal_alt` → `_build_value_str`
2. Lines ~568–612: `named_alt` → `_build_named_alt`
3. Lines ~614–644: `sequence` → `_build_sequence`

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
```

Delete the old `_build_rule` body.

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
    import dataclasses
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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from lexic.ir import RuleSpec


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
```

Create `src/lexic/codegen/transformer/registry.py`:

```python
"""BUILDER_BY_ATOM dispatch table."""

from __future__ import annotations

from typing import Protocol

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
from lexic.codegen.transformer.context import BuildContext, BuildResult


class FieldBuilder(Protocol):
    def build(
        self, atom: Atom, field_name: str, ctx: BuildContext
    ) -> BuildResult: ...


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
  `ctx.hints[field_name]`. Four cases, each with its own test:
  - ws rule, child available: consume and return the child.
  - ws rule, no child: return `FieldResult(value=hint(value=""), consumed=0)`
    (construct an empty `Ws`).
  - non-ws rule, child available: consume and return the child.
  - non-ws rule, no child: if the hint accepts a string, return
    `FieldResult(value="", consumed=0)`. Otherwise return `SKIP_FIELD`.

- **`InlineAlternationBuilder`** — field is `str` (via `value` field
  name). Consumes one string child.

`AbstractAlternationBuilder` is handled at the orchestrator level, not
per-field — the stub's `raise AssertionError` is correct.

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
    """Wraps an inner builder; returns FieldResult(None, 0) on exhaustion or
    wrong-typed next child; otherwise delegates."""

    def __init__(self, inner):
        self._inner = inner

    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        if ctx.exhausted():
            return FieldResult(value=None, consumed=0)
        # Delegate — inner builder decides whether the next child is consumable.
        result = self._inner.build(atom, field_name, ctx)
        if isinstance(result, FieldResult) and result.consumed == 0 and result.value in ("", None):
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

Remove `_is_ws_ref` and `_is_optional_char` — their logic now lives in
the per-atom builders. `_literal_is_quoted` stays.

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
- Primary entry: `compile_text(text, *, cache_key=None)`.
- `compile(path)` is the thin wrapper; both share one cache.
- `CompiledGrammar.specs: dict[str, RuleSpec]` (matches roadmap).

---

### Task 11: Introduce `CompiledGrammar`, `compile_text`, and `compile()`

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

from lexic.compile import CompiledGrammar, compile, compile_text, _cache_clear

GROUND_TRUTH = Path(__file__).resolve().parents[2] / "resources" / "ground_truth"


@pytest.fixture(autouse=True)
def clear_cache():
    _cache_clear()
    yield
    _cache_clear()


def test_compile_returns_compiled_grammar():
    cg = compile(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg, CompiledGrammar)
    assert cg.classes
    assert isinstance(cg.specs, dict)
    assert cg.specs


def test_compile_memoises_by_path_mtime_size():
    src = GROUND_TRUTH / "arithmetic.gbnf"
    cg1 = compile(src)
    cg2 = compile(src)
    assert cg1 is cg2


def test_compile_invalidates_on_mtime_change(tmp_path):
    src = tmp_path / "g.gbnf"
    src.write_text("root ::= \"a\"\n")
    cg1 = compile(src)
    time.sleep(0.01)
    src.write_text("root ::= \"b\"\n")
    cg2 = compile(src)
    assert cg1 is not cg2


def test_compile_invalidates_on_size_change_same_mtime(tmp_path, monkeypatch):
    """Same mtime but different size should invalidate — catches test-FS edge case."""
    src = tmp_path / "g.gbnf"
    src.write_text("root ::= \"aa\"\n")
    cg1 = compile(src)
    # Preserve mtime; change size.
    original_mtime = src.stat().st_mtime
    src.write_text("root ::= \"bbb\"\n")
    import os
    os.utime(src, (original_mtime, original_mtime))
    cg2 = compile(src)
    assert cg1 is not cg2


def test_compile_text_no_cache_by_default():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg1 = compile_text(text)
    cg2 = compile_text(text)
    assert cg1 is not cg2  # no cache_key → no memoization


def test_compile_text_with_cache_key():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg1 = compile_text(text, cache_key="fixture-a")
    cg2 = compile_text(text, cache_key="fixture-a")
    assert cg1 is cg2


def test_compile_and_compile_text_share_cache():
    """compile(path) should cache-hit after a prior compile_text(text, cache_key=key)
    with the same key — they use one _CACHE dict."""
    path = GROUND_TRUTH / "arithmetic.gbnf"
    resolved = str(path.resolve())
    stat = path.stat()
    key = (resolved, stat.st_mtime, stat.st_size)
    cg1 = compile_text(path.read_text(), cache_key=key)
    cg2 = compile(path)
    assert cg1 is cg2


def test_compiled_grammar_parse_roundtrips():
    cg = compile(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("1+1")
    assert inst.to_text() == "1+1"


def test_repeated_parse_is_fast():
    cg = compile(GROUND_TRUTH / "arithmetic.gbnf")
    cg.parse("1+1")  # warm
    start = time.perf_counter()
    for _ in range(100):
        cg.parse("1+1")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"100 cached parses took {elapsed:.3f}s"
```

- [ ] **Step 2: Run; verify fail**

- [ ] **Step 3: Implement `compile.py`**

Create `src/lexic/compile.py`:

```python
"""CompiledGrammar: the compile-time artefacts parse() needs.

compile_text(text, *, cache_key) is the primary entry. compile(path) is
a thin wrapper that stats the file, builds a (path, mtime, size) key,
checks the cache to skip the file read on hit, and delegates.

One cache covers both entry points.
"""

from __future__ import annotations

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


def _cache_clear() -> None:
    _CACHE.clear()


def _compile_core(text: str) -> CompiledGrammar:
    rules = parse_gbnf(text)
    specs_list = IRBuilder(rules).build()
    specs = {s.rule_name: s for s in specs_list}

    # codegen() currently takes a path; for compile_text we need a text-only
    # variant. Delegate to the internal emit path.
    # NOTE: this refactor is Slice A's responsibility; ensure codegen.codegen
    # is refactored to accept text or use a shared primitive.
    classes = codegen(text)  # placeholder — implementor to verify signature

    builder = LarkBuilder(specs_list)
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(
        grammar_str, parser="earley", ambiguity="resolve", start=start_rule
    )
    transformer = builder.build_transformer(classes)

    return CompiledGrammar(
        classes=classes, specs=specs, parser=parser, transformer=transformer
    )


def compile_text(text: str, *, cache_key: Hashable | None = None) -> CompiledGrammar:
    """Compile from a grammar string. cache_key=None means 'do not memoize'."""
    if cache_key is not None:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            return cached
    cg = _compile_core(text)
    if cache_key is not None:
        _CACHE[cache_key] = cg
    return cg


def compile(grammar_path: str | Path) -> CompiledGrammar:
    """Compile from a file path; memoised by (path, mtime, size)."""
    path = Path(grammar_path).resolve()
    stat = path.stat()
    key = (str(path), stat.st_mtime, stat.st_size)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    return compile_text(path.read_text(), cache_key=key)
```

**Note for implementor:** `codegen()` today accepts a path, not text.
Before `compile_text` can work from text alone, the internal emit path
in `lexic.codegen.__init__` must factor out a text-accepting primitive.
Concretely: extract `codegen_from_text(text: str) -> dict[str, type]`
and make `codegen(path)` call `codegen_from_text(Path(path).read_text())`.
Add this factorisation as the first step of this task if it isn't
already present.

- [ ] **Step 4: Run new tests; verify pass**

- [ ] **Step 5: Rewrite `parse.py` on top of `compile()`**

Replace `src/lexic/parse.py` in full:

```python
"""parse(text, grammar_path) → GrammarModel instance.

Thin entry point: compile the grammar (memoised) then parse the text.
"""

from __future__ import annotations

from pathlib import Path

from lexic.base import GrammarModel
from lexic.compile import compile


def parse(text: str, grammar_path: str | Path) -> GrammarModel:
    """Parse text against a GBNF grammar and return a typed GrammarModel instance."""
    return compile(grammar_path).parse(text)
```

- [ ] **Step 6: Run the full suite**

- [ ] **Step 7: Commit**

```bash
git add src/lexic/compile.py tests/unit/lexic/test_compile.py src/lexic/parse.py
git commit -m "feat(compile): introduce CompiledGrammar + compile_text + memoised compile()"
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

- [ ] **Step 3: Confirm every `FieldBuilder` has a unit test**

```bash
uv run grep -l "class .*FieldBuilder\|class .*Builder" src/lexic/codegen/transformer/builders.py
uv run pytest tests/unit/lexic/codegen/test_transformer_builders.py -v --collect-only
```

- [ ] **Step 4: Confirm no atom-type `isinstance` cascade**

```bash
uv run grep -n "isinstance.*Atom" src/lexic/codegen/transformer/builders.py
```
Expected: no matches.

- [ ] **Step 5: Confirm `parse()` uses `compile()` memo**

```bash
uv run pytest tests/unit/lexic/test_compile.py::test_repeated_parse_is_fast -v
uv run pytest tests/unit/lexic/test_compile.py::test_compile_memoises_by_path_mtime_size -v
```

- [ ] **Step 6: Confirm `base.py` has at most one `lexic.codegen` import**

```bash
uv run grep -n "from lexic.codegen" src/lexic/base.py
```
Expected: exactly one.

- [ ] **Step 7: Confirm no lazy intra-function `lexic.codegen` imports**

```bash
uv run grep -rn "    from lexic.codegen" src/lexic/*.py
```
Expected: only the one inside `base.py::to_gbnf` (pre-existing; Slice B
replaces wholesale).

- [ ] **Step 8: Confirm `BuildContext` is frozen**

```bash
uv run grep -n "@dataclass(frozen=True)" src/lexic/codegen/transformer/context.py
```
Expected: frozen=True on `BuildContext`, `FieldResult`, `SkipField`.

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
