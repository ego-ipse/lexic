# Generic GBNF Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bidirectional pipeline — any GBNF grammar + Vyx-format spec → Pydantic `BaseModel` subclasses → parse text to model instances → emit model instances back to text → dump/load JSON.

**Architecture:** PEG interpreter walks `GBNFNode` IR (from existing `gbnf.py`) to parse arbitrary text and to emit it back. `builder.py` is refactored to produce plain `BaseModel` subclasses (removing `VyxBase` coupling). A spec layer (`extractor` → `compiler` → `enricher`) reads the Vyx-format spec and adds semantic constraints to the grammar models. No target-language knowledge is hardcoded anywhere.

**Tech Stack:** Python 3.12+, pydantic>=2.12.5, pytest

---

## Codebase Context

All source files live flat in `/home/mika/projects/vyx_2/` (no `src/` subdirectory).
Grammar file: `spec_built/grammar.gbnf`.
Reference implementations (read-only, do not modify): `project_meta/files/`.

Key existing files:
- `gbnf.py` — GBNF text → `GBNFNode` IR. **Do not modify.**
- `builder.py` — `GBNFNode` IR → `VyxBase` subclasses. **Refactor in Task 2.**
- `base.py` — `VyxBase`. Becomes unused after Task 2 — **do not delete**, harness.py still imports it.
- `parser.py` — Vyx-specific parser. Superseded by `interpreter.py` — **do not delete or modify**.
- `harness.py` — pydantic-ai agent harness. Update return types in Task 2.

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `gbnf.py` | unchanged | GBNF text → GBNFNode IR |
| `builder.py` | refactor | Remove VyxBase, produce plain BaseModel subclasses |
| `harness.py` | update | Change VyxBase return type annotations to BaseModel |
| `interpreter.py` | create | PEG interpreter: GBNFNode IR + text → model instances |
| `emitter.py` | create | model instances + GBNFNode IR → text |
| `spec/__init__.py` | create | empty |
| `spec/extractor.py` | create | markdown → (section_id, body_text) pairs |
| `spec/models.py` | create | DSection, GrammarBlock, ErrorCode |
| `spec/compiler.py` | create | body_text → DSection using interpreter |
| `spec/enricher.py` | create | DSection → add validators to grammar models |
| `tests/__init__.py` | create | empty |
| `tests/conftest.py` | create | shared grammar fixture |
| `tests/test_builder.py` | create | builder refactor tests |
| `tests/test_interpreter.py` | create | interpreter unit tests |
| `tests/test_emitter.py` | create | emitter unit tests |
| `tests/test_roundtrip.py` | create | parse → emit → parse integration |
| `tests/spec/__init__.py` | create | empty |
| `tests/spec/test_extractor.py` | create | extractor tests |
| `tests/spec/test_compiler.py` | create | compiler tests |
| `tests/spec/test_enricher.py` | create | enricher tests |

---

## Task 1: Project setup

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/spec/__init__.py`

- [ ] **Step 1: Add pytest to pyproject.toml**

Replace the `[project]` section dependencies and add test config. Open `pyproject.toml` and make it read:

```toml
[project]
name = "vyx-2"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.12.5",
    "pyparsing>=3.3.2",
]

[dependency-groups]
dev = ["pytest>=8.0.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create test directory scaffolding**

```bash
mkdir -p tests/spec
touch tests/__init__.py tests/spec/__init__.py
```

- [ ] **Step 3: Create conftest.py with grammar fixture**

Create `tests/conftest.py`:

```python
from pathlib import Path
import pytest
from gbnf import GBNFParser, GBNFNode

GRAMMAR_PATH = Path(__file__).parent.parent / "spec_built" / "grammar.gbnf"


@pytest.fixture(scope="session")
def vyx_grammar_text() -> str:
    return GRAMMAR_PATH.read_text()


@pytest.fixture(scope="session")
def vyx_rules(vyx_grammar_text: str) -> dict[str, GBNFNode]:
    return GBNFParser().parse(vyx_grammar_text)
```

- [ ] **Step 4: Write smoke test for gbnf.py**

Create `tests/test_gbnf_smoke.py`:

```python
from gbnf import GBNFParser, GBNFAlternation, GBNFRepetition, _unescape


def test_unescape_backslash():
    assert _unescape('"\\"') == "\\"


def test_unescape_newline():
    assert _unescape('"\\n"') == "\n"


def test_unescape_nl_force():
    assert _unescape('"# "') == "# "


def test_parse_body_line_is_alternation(vyx_rules):
    from gbnf import GBNFAlternation
    assert isinstance(vyx_rules["body-line"], GBNFAlternation)


def test_body_is_repetition_min1(vyx_rules):
    body = vyx_rules["body"]
    assert isinstance(body, GBNFRepetition)
    assert body.min == 1
```

- [ ] **Step 5: Run tests**

```bash
cd /home/mika/projects/vyx_2
uv run pytest tests/test_gbnf_smoke.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git init  # if not already a repo
git add pyproject.toml tests/
git commit -m "chore: add pytest setup and gbnf smoke tests"
```

---

## Task 2: Refactor builder.py — remove VyxBase

The current `builder.py` produces `VyxBase` subclasses and maintains a sigil registry. The refactor removes all `VyxBase` coupling so models are plain `BaseModel` subclasses. Charclass repetitions (`[a-z]+`) become `str` fields (not `list[str]`).

**Files:**
- Modify: `builder.py`
- Modify: `harness.py`
- Create: `tests/test_builder.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_builder.py`:

```python
from pydantic import BaseModel
from builder import GBNFModelBuilder
from gbnf import GBNFParser

SIMPLE = """
greeting ::= "hello" " " name
name ::= [a-zA-Z]+
"""

KV = """
kv-pair ::= key "=" val
key ::= [a-zA-Z]+
val ::= [0-9]+
"""


def test_models_are_basemodel_subclasses():
    rules = GBNFParser().parse(SIMPLE)
    models = GBNFModelBuilder(rules).build()
    for model in models.values():
        assert issubclass(model, BaseModel)


def test_no_sigil_attr():
    rules = GBNFParser().parse(SIMPLE)
    models = GBNFModelBuilder(rules).build()
    for model in models.values():
        assert not hasattr(model, "SIGIL")


def test_no_children_attr():
    rules = GBNFParser().parse(SIMPLE)
    models = GBNFModelBuilder(rules).build()
    for model in models.values():
        assert not hasattr(model, "_children")


def test_charclass_repetition_is_str_not_list():
    """[a-z]+ should produce a str field, not list[str]."""
    rules = GBNFParser().parse(KV)
    models = GBNFModelBuilder(rules).build()
    key_model = models["key"]
    fields = key_model.model_fields
    # key rule is [a-zA-Z]+ — should have one str field
    assert len(fields) == 1
    field = next(iter(fields.values()))
    assert field.annotation is str


def test_vyx_grammar_builds(vyx_rules):
    """Full Vyx grammar should produce BaseModel subclasses for all rules."""
    models = GBNFModelBuilder(vyx_rules).build()
    assert len(models) > 30
    for model in models.values():
        assert issubclass(model, BaseModel)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_builder.py -v
```

Expected: FAIL on `test_no_sigil_attr` (current builder puts `SIGIL` on models), `test_charclass_repetition_is_str_not_list` (currently produces `list[str]`).

- [ ] **Step 3: Rewrite builder.py**

Replace `builder.py` with:

```python
"""GBNFModelBuilder — derives Pydantic BaseModel subclasses from GBNF grammar.

No target-language knowledge lives here. Sigils, dispatch tables, and Vyx-
specific base classes are all absent. One plain BaseModel subclass per rule.

Charclass repetitions ([a-z]+) produce str fields for ergonomics.
Non-charclass repetitions produce list[...] fields.
"""

from __future__ import annotations

from typing import Any, Literal

from gbnf import (
    GBNFAlternation,
    GBNFCharClass,
    GBNFLiteral,
    GBNFNode,
    GBNFOptional,
    GBNFParser,
    GBNFReference,
    GBNFRepetition,
    GBNFSequence,
    _element_name,
)
from pydantic import BaseModel, Field, create_model


class GBNFModelBuilder:
    """Compiles a GBNF grammar into a registry of BaseModel subclasses.

    Usage::

        grammar = Path("grammar.gbnf").read_text()
        rules   = GBNFParser().parse(grammar)
        models  = GBNFModelBuilder(rules).build()
        schema  = models["packet"].model_json_schema()
    """

    def __init__(self, rules: dict[str, GBNFNode]) -> None:
        self._rules = rules
        self._registry: dict[str, type[BaseModel]] = {}

    @classmethod
    def from_grammar(cls, grammar: str) -> GBNFModelBuilder:
        return cls(GBNFParser().parse(grammar))

    def build(self) -> dict[str, type[BaseModel]]:
        for name in self._rules:
            if name not in self._registry:
                self._build(name)
        return self._registry

    # ------------------------------------------------------------------
    # GBNFNode → Python type annotation
    # ------------------------------------------------------------------

    def _python_type(self, node: GBNFNode) -> Any:
        match node:
            case GBNFLiteral(values=values) if values:
                if len(values) == 1:
                    return Literal[values[0]]  # type: ignore[misc]
                return Literal[values]  # type: ignore[misc]

            case GBNFAlternation(arms=arms):
                if all(isinstance(a, GBNFLiteral) for a in arms):
                    vals: tuple[str, ...] = tuple(
                        v for a in arms for v in a.values  # type: ignore[union-attr]
                    )
                    return Literal[vals]  # type: ignore[misc]
                types = [self._python_type(a) for a in arms]
                result = types[0]
                for t in types[1:]:
                    result = result | t
                return result

            case GBNFRepetition(element=el):
                # Charclass repetitions → str (joining chars is always intended)
                if isinstance(el, GBNFCharClass):
                    return str
                return list[self._python_type(el)]  # type: ignore[misc]

            case GBNFOptional(element=el):
                return self._python_type(el) | None

            case GBNFReference(rule=r):
                return self._ref(r)

            case GBNFCharClass():
                return str

            case GBNFSequence():
                fields = self._fields_for(node)
                return create_model("_inline", **fields)

            case _:
                return Any

    # ------------------------------------------------------------------
    # GBNFNode → Pydantic field definitions
    # ------------------------------------------------------------------

    def _fields_for(self, node: GBNFNode) -> dict[str, tuple[type, Any]]:
        match node:
            case GBNFSequence(elements=elements):
                fields: dict[str, tuple[type, Any]] = {}
                seen: dict[str, int] = {}
                for el in elements:
                    base = el.name
                    count = seen.get(base, 0)
                    fname = base if count == 0 else f"{base}_{count}"
                    seen[base] = count + 1
                    py_type = self._python_type(el.node)
                    if isinstance(el.node, GBNFRepetition) and el.node.min > 0:
                        if isinstance(el.node.element, GBNFCharClass):
                            fields[fname] = (str, Field(..., min_length=el.node.min))
                        else:
                            fields[fname] = (py_type, Field(..., min_length=el.node.min))
                    elif el.required:
                        fields[fname] = (py_type, ...)
                    else:
                        fields[fname] = (py_type, None)
                return fields

            case GBNFRepetition(element=el, min=min_):
                fname = _element_name(el, 0)
                if isinstance(el, GBNFCharClass):
                    f = Field(..., min_length=min_) if min_ > 0 else Field(default="")
                    return {fname: (str, f)}
                inner = self._python_type(el)
                f = (
                    Field(..., min_length=min_)
                    if min_ > 0
                    else Field(default_factory=list)
                )
                return {fname: (list[inner], f)}  # type: ignore[misc]

            case GBNFOptional(element=el):
                return {_element_name(el, 0): (self._python_type(el) | None, None)}

            case GBNFAlternation() | GBNFLiteral() | GBNFCharClass():
                return {"value": (self._python_type(node), ...)}

            case GBNFReference(rule=r):
                return {r.replace("-", "_"): (self._ref(r), ...)}

            case _:
                return {"value": (Any, None)}

    # ------------------------------------------------------------------
    # Rule → model (placeholder handles mutual recursion)
    # ------------------------------------------------------------------

    def _build(self, name: str) -> type[BaseModel]:
        if name in self._registry:
            return self._registry[name]

        self._registry[name] = BaseModel  # placeholder for recursion

        node = self._rules[name]
        fields = self._fields_for(node)
        model = create_model(name, **fields)
        self._registry[name] = model
        return model

    def _ref(self, rule: str) -> type[BaseModel]:
        if rule in self._registry:
            t = self._registry[rule]
            return t if t is not BaseModel else BaseModel
        if rule in self._rules:
            return self._build(rule)
        return BaseModel  # unknown rule — permissive fallback
```

- [ ] **Step 4: Update harness.py**

In `harness.py`, change:
- `from base import VyxBase` → `from pydantic import BaseModel`
- Both `-> VyxBase:` return annotations → `-> BaseModel:`

```python
# In harness.py, change these two imports at the top:
# OLD: from base import VyxBase
# NEW: from pydantic import BaseModel

# And change:
# OLD:   def emit(self, rule: str, prompt: str, **kwargs: Any) -> VyxBase:
# NEW:   def emit(self, rule: str, prompt: str, **kwargs: Any) -> BaseModel:

# OLD:   async def emit_async(self, rule: str, prompt: str, **kwargs: Any) -> VyxBase:
# NEW:   async def emit_async(self, rule: str, prompt: str, **kwargs: Any) -> BaseModel:
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_builder.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add builder.py harness.py tests/test_builder.py
git commit -m "refactor: builder produces plain BaseModel subclasses, removes VyxBase"
```

---

## Task 3: Create interpreter.py

PEG interpreter over `GBNFNode` IR. No Vyx-specific knowledge. Handles all 7 node types.

**Important — charclass patterns:** The grammar file stores hex ranges as `[\\xHH-\\xHH]` (two backslashes before `x`). Python's `re` engine needs one backslash (`[\xHH-\xHH]`). The helper `_charclass_to_re` applies `pattern.replace('\\\\', '\\')` before compiling.

**Files:**
- Create: `interpreter.py`
- Create: `tests/test_interpreter.py`

- [ ] **Step 1: Write failing tests for atoms**

Create `tests/test_interpreter.py`:

```python
import pytest
from gbnf import GBNFParser
from builder import GBNFModelBuilder
from interpreter import GBNFInterpreter


def make(grammar: str) -> GBNFInterpreter:
    rules = GBNFParser().parse(grammar)
    models = GBNFModelBuilder(rules).build()
    return GBNFInterpreter(rules, models)


# --- Literal ---

def test_literal_match():
    interp = make('tag ::= "hello"')
    result = interp.parse("tag", "hello world", 0)
    assert result is not None
    value, pos = result
    assert value == "hello"
    assert pos == 5


def test_literal_no_match():
    interp = make('tag ::= "hello"')
    assert interp.parse("tag", "world", 0) is None


def test_literal_at_offset():
    interp = make('tag ::= "!"')
    result = interp.parse("tag", "xx!", 2)
    assert result is not None
    assert result[1] == 3


# --- CharClass ---

def test_charclass_match():
    interp = make('letter ::= [a-z]')
    result = interp.parse("letter", "abc", 0)
    assert result is not None
    value, pos = result
    assert value == "a"
    assert pos == 1


def test_charclass_no_match():
    interp = make('letter ::= [a-z]')
    assert interp.parse("letter", "ABC", 0) is None


def test_charclass_hex_range():
    """Grammar uses \\xHH notation for hex ranges — must match correctly."""
    # unquoted chars span 0x21-0x7E (printable ASCII)
    interp = make('ch ::= [\\x21-\\x7E]')
    result = interp.parse("ch", "!", 0)   # 0x21 = '!'
    assert result is not None
    assert result[0] == "!"
    result2 = interp.parse("ch", "~", 0)  # 0x7E = '~'
    assert result2 is not None
    assert result2[0] == "~"


# --- Alternation ---

def test_alternation_first_arm():
    interp = make('word ::= "hello" | "world"')
    result = interp.parse("word", "hello", 0)
    assert result is not None
    assert result[0] == "hello"


def test_alternation_second_arm():
    interp = make('word ::= "hello" | "world"')
    result = interp.parse("word", "world", 0)
    assert result is not None
    assert result[0] == "world"


def test_alternation_no_match():
    interp = make('word ::= "hello" | "world"')
    assert interp.parse("word", "foo", 0) is None


# --- Repetition ---

def test_repetition_zero_or_more():
    interp = make('letters ::= [a-z]*')
    result = interp.parse("letters", "abc123", 0)
    assert result is not None
    value, pos = result
    assert value == "abc"   # charclass rep → str
    assert pos == 3


def test_repetition_one_or_more_match():
    interp = make('word ::= [a-z]+')
    result = interp.parse("word", "hello", 0)
    assert result is not None
    assert result[0] == "hello"
    assert result[1] == 5


def test_repetition_one_or_more_fail():
    interp = make('word ::= [a-z]+')
    assert interp.parse("word", "123", 0) is None


def test_repetition_zero_or_more_empty():
    """Zero-or-more with no match should succeed returning empty string."""
    interp = make('letters ::= [a-z]*')
    result = interp.parse("letters", "123", 0)
    assert result is not None
    value, pos = result
    assert value == ""
    assert pos == 0


# --- Optional ---

def test_optional_present():
    interp = make('maybe ::= "x"?')
    result = interp.parse("maybe", "x", 0)
    assert result is not None
    assert result[0] == "x"
    assert result[1] == 1


def test_optional_absent():
    interp = make('maybe ::= "x"?')
    result = interp.parse("maybe", "y", 0)
    assert result is not None
    value, pos = result
    assert value is None
    assert pos == 0


# --- Reference ---

def test_reference():
    grammar = 'outer ::= inner\ninner ::= "ok"'
    interp = make(grammar)
    result = interp.parse("outer", "ok", 0)
    assert result is not None
    assert result[1] == 2


# --- Sequence with model instantiation ---

def test_sequence_produces_model_instance():
    # Inline charclass repetitions → str fields directly (Task 2 optimization)
    # _element_name gives: elem_0 (charclass rep), token_1 (literal "="), elem_2 (charclass rep)
    grammar = 'pair ::= [a-zA-Z]+ "=" [0-9]+'
    rules = GBNFParser().parse(grammar)
    models = GBNFModelBuilder(rules).build()
    interp = GBNFInterpreter(rules, models)

    result = interp.parse("pair", "foo=42", 0)
    assert result is not None
    instance, pos = result
    assert pos == 6
    from pydantic import BaseModel
    assert isinstance(instance, BaseModel)
    assert instance.elem_0 == "foo"
    assert instance.token_1 == "="
    assert instance.elem_2 == "42"


# --- Vyx grammar smoke ---

def test_parse_kv_pair_vyx(vyx_rules):
    from builder import GBNFModelBuilder
    from interpreter import GBNFInterpreter
    models = GBNFModelBuilder(vyx_rules).build()
    interp = GBNFInterpreter(vyx_rules, models)

    result = interp.parse("kv-pairs", "city=Porto", 0)
    assert result is not None
    _, pos = result
    assert pos == 10
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_interpreter.py -v
```

Expected: ImportError — `interpreter.py` does not exist yet.

- [ ] **Step 3: Create interpreter.py**

Create `interpreter.py`:

```python
"""PEG interpreter — walks GBNFNode IR to parse arbitrary text.

No knowledge of any target language. Driven entirely by grammar rules.

Usage:
    rules  = GBNFParser().parse(grammar_text)
    models = GBNFModelBuilder(rules).build()
    interp = GBNFInterpreter(rules, models)

    result = interp.parse("rule-name", input_text)
    # Returns (value, consumed_pos) or None if no match.
    #
    # Value types by node kind:
    #   GBNFLiteral            → str (the matched literal)
    #   GBNFCharClass          → str (the matched character)
    #   GBNFRepetition/charclass → str (joined chars)
    #   GBNFRepetition/other   → list[Any]
    #   GBNFOptional           → inner value or (None, same_pos) on no match
    #   GBNFSequence           → BaseModel instance if rule has a model, else dict
    #   GBNFAlternation        → value from first matching arm
    #   GBNFReference          → result of recursing into named rule
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from gbnf import (
    GBNFAlternation,
    GBNFCharClass,
    GBNFLiteral,
    GBNFNode,
    GBNFOptional,
    GBNFReference,
    GBNFRepetition,
    GBNFSequence,
)


def _charclass_to_re(pattern: str) -> re.Pattern[str]:
    """Convert GBNF character class to a compiled Python regex.

    GBNF stores hex ranges as \\xHH (two backslash bytes + xHH).
    Python re needs \\xHH (one backslash) to interpret them as hex escapes.
    Simple alpha ranges like [a-z] pass through unchanged.
    """
    # Each pair of consecutive backslashes in the grammar file arrives here
    # as two actual backslash characters. Replace them with one so Python re
    # interprets \\xHH as a hex escape for the right codepoint.
    py_pattern = pattern.replace("\\\\", "\\")
    return re.compile(py_pattern)


class GBNFInterpreter:
    """PEG interpreter over GBNFNode IR."""

    def __init__(
        self,
        rules: dict[str, GBNFNode],
        models: dict[str, type[BaseModel]],
    ) -> None:
        self._rules = rules
        self._models = models
        self._re_cache: dict[str, re.Pattern[str]] = {}

    def parse(self, rule: str, text: str, pos: int = 0) -> tuple[Any, int] | None:
        """Parse text[pos:] against the named rule.

        Returns (value, new_pos) or None on no match.
        """
        if rule not in self._rules:
            return None
        return self._match(self._rules[rule], text, pos, rule_name=rule)

    # ------------------------------------------------------------------
    # Core matching — one method per GBNFNode type
    # ------------------------------------------------------------------

    def _match(
        self,
        node: GBNFNode,
        text: str,
        pos: int,
        rule_name: str | None = None,
    ) -> tuple[Any, int] | None:
        match node:
            case GBNFLiteral(values=values):
                for v in values:
                    if text[pos : pos + len(v)] == v:
                        return v, pos + len(v)
                return None

            case GBNFCharClass(pattern=pattern):
                compiled = self._re_cache.get(pattern)
                if compiled is None:
                    compiled = _charclass_to_re(pattern)
                    self._re_cache[pattern] = compiled
                m = compiled.match(text, pos)
                if m:
                    return m.group(), m.end()
                return None

            case GBNFAlternation(arms=arms):
                for arm in arms:
                    result = self._match(arm, text, pos)
                    if result is not None:
                        return result
                return None

            case GBNFSequence(elements=elements):
                return self._match_sequence(elements, text, pos, rule_name)

            case GBNFRepetition(element=el, min=min_count):
                return self._match_repetition(el, text, pos, min_count)

            case GBNFOptional(element=el):
                result = self._match(el, text, pos)
                if result is None:
                    return None, pos
                return result

            case GBNFReference(rule=r):
                return self.parse(r, text, pos)

            case _:
                return None

    def _match_sequence(
        self,
        elements: tuple,
        text: str,
        pos: int,
        rule_name: str | None,
    ) -> tuple[Any, int] | None:
        fields: dict[str, Any] = {}
        cur = pos
        seen: dict[str, int] = {}
        for el in elements:
            result = self._match(el.node, text, cur)
            if result is None:
                return None
            base = el.name
            count = seen.get(base, 0)
            fname = base if count == 0 else f"{base}_{count}"
            seen[base] = count + 1
            fields[fname], cur = result

        # Instantiate the Pydantic model for this rule if one exists
        if rule_name and rule_name in self._models:
            try:
                return self._models[rule_name](**fields), cur
            except Exception:
                pass  # fall through to dict on validation error
        return fields, cur

    def _match_repetition(
        self,
        element: GBNFNode,
        text: str,
        pos: int,
        min_count: int,
    ) -> tuple[Any, int] | None:
        is_charclass = isinstance(element, GBNFCharClass)
        items: list[Any] = []
        cur = pos

        while True:
            result = self._match(element, text, cur)
            if result is None or result[1] == cur:
                break  # no match or zero-length match — stop to avoid infinite loop
            items.append(result[0])
            cur = result[1]

        if len(items) < min_count:
            return None

        if is_charclass:
            return "".join(str(i) for i in items), cur
        return items, cur
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_interpreter.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add interpreter.py tests/test_interpreter.py
git commit -m "feat: add PEG interpreter over GBNFNode IR"
```

---

## Task 4: Create emitter.py

Emits text from a model instance using the same `GBNFNode` IR. Round-trip invariant: `parse(emit(instance)) == instance`.

**Files:**
- Create: `emitter.py`
- Create: `tests/test_emitter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_emitter.py`:

```python
import pytest
from gbnf import GBNFParser
from builder import GBNFModelBuilder
from interpreter import GBNFInterpreter
from emitter import emit


def roundtrip(grammar: str, rule: str, text: str) -> bool:
    rules = GBNFParser().parse(grammar)
    models = GBNFModelBuilder(rules).build()
    interp = GBNFInterpreter(rules, models)
    result = interp.parse(rule, text, 0)
    if result is None:
        return False
    instance, _ = result
    emitted = emit(rules, models, rule, instance)
    return emitted == text


def test_emit_literal():
    assert roundtrip('tag ::= "hello"', "tag", "hello")


def test_emit_charclass_repetition():
    assert roundtrip('word ::= [a-z]+', "word", "hello")


def test_emit_alternation_first():
    assert roundtrip('w ::= "foo" | "bar"', "w", "foo")


def test_emit_alternation_second():
    assert roundtrip('w ::= "foo" | "bar"', "w", "bar")


def test_emit_sequence():
    grammar = 'kv ::= key "=" val\nkey ::= [a-z]+\nval ::= [0-9]+'
    assert roundtrip(grammar, "kv", "foo=42")


def test_emit_optional_present():
    grammar = 'line ::= [a-z]+ "!"?'
    assert roundtrip(grammar, "line", "hello!")


def test_emit_optional_absent():
    grammar = 'line ::= [a-z]+ "!"?'
    assert roundtrip(grammar, "line", "hello")


def test_emit_kv_pairs_vyx(vyx_rules):
    from builder import GBNFModelBuilder
    from interpreter import GBNFInterpreter
    models = GBNFModelBuilder(vyx_rules).build()
    interp = GBNFInterpreter(vyx_rules, models)
    text = "city=Porto"
    result = interp.parse("kv-pairs", text, 0)
    assert result is not None
    instance, _ = result
    emitted = emit(vyx_rules, models, "kv-pairs", instance)
    assert emitted == text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_emitter.py -v
```

Expected: ImportError — `emitter.py` does not exist.

- [ ] **Step 3: Create emitter.py**

Create `emitter.py`:

```python
"""Text emitter — walks model instances back to text using GBNFNode IR.

No knowledge of any target language. Round-trip invariant:
    parse(emit(instance)) == instance   (structural identity)

Usage:
    from emitter import emit
    text = emit(rules, models, "rule-name", instance)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from gbnf import (
    GBNFAlternation,
    GBNFCharClass,
    GBNFLiteral,
    GBNFNode,
    GBNFOptional,
    GBNFReference,
    GBNFRepetition,
    GBNFSequence,
)


def emit(
    rules: dict[str, GBNFNode],
    models: dict[str, type[BaseModel]],
    rule: str,
    value: Any,
) -> str:
    """Emit text for a model instance according to the named grammar rule."""
    if rule not in rules:
        return str(value) if value is not None else ""
    return _emit_node(rules, models, rules[rule], value, rule_name=rule)


def _emit_node(
    rules: dict[str, GBNFNode],
    models: dict[str, type[BaseModel]],
    node: GBNFNode,
    value: Any,
    rule_name: str | None = None,
) -> str:
    match node:
        case GBNFLiteral(values=values):
            # value is the matched literal string; emit it directly.
            # If value is None (shouldn't happen for required literal), use first.
            if isinstance(value, str) and value in values:
                return value
            return values[0] if values else ""

        case GBNFCharClass():
            # value is a single matched character str
            return str(value) if value is not None else ""

        case GBNFRepetition(element=el):
            if isinstance(value, str):
                # charclass repetition stored as str
                return value
            if isinstance(value, list):
                return "".join(
                    _emit_node(rules, models, el, item) for item in value
                )
            return ""

        case GBNFOptional(element=el):
            if value is None:
                return ""
            return _emit_node(rules, models, el, value)

        case GBNFAlternation(arms=arms):
            # For all-literal alternations, value is a str — find and return it.
            if isinstance(value, str):
                for arm in arms:
                    if isinstance(arm, GBNFLiteral) and value in arm.values:
                        return value
                # value is a str but no arm matches literally — emit as-is
                return value
            # For model-valued alternations, find the arm whose model matches.
            for arm in arms:
                if isinstance(arm, GBNFReference):
                    arm_model = models.get(arm.rule)
                    if arm_model and isinstance(value, arm_model):
                        return emit(rules, models, arm.rule, value)
            # Fallback: emit the value's own rule if it's a BaseModel
            if isinstance(value, BaseModel):
                model_name = type(value).__name__
                if model_name in rules:
                    return emit(rules, models, model_name, value)
            return str(value) if value is not None else ""

        case GBNFSequence(elements=elements):
            return _emit_sequence(rules, models, elements, value)

        case GBNFReference(rule=r):
            return emit(rules, models, r, value)

        case _:
            return str(value) if value is not None else ""


def _emit_sequence(
    rules: dict[str, GBNFNode],
    models: dict[str, type[BaseModel]],
    elements: tuple,
    value: Any,
) -> str:
    parts: list[str] = []
    seen: dict[str, int] = {}
    for el in elements:
        base = el.name
        count = seen.get(base, 0)
        fname = base if count == 0 else f"{base}_{count}"
        seen[base] = count + 1

        if isinstance(value, BaseModel):
            field_value = getattr(value, fname, None)
        elif isinstance(value, dict):
            field_value = value.get(fname)
        else:
            field_value = None

        parts.append(_emit_node(rules, models, el.node, field_value))
    return "".join(parts)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_emitter.py -v
```

Expected: All pass. If `test_emit_optional_absent` fails, check that `GBNFOptional` in `_match_repetition` doesn't consume input when the optional element is absent.

- [ ] **Step 5: Commit**

```bash
git add emitter.py tests/test_emitter.py
git commit -m "feat: add text emitter, round-trip invariant for grammar-driven models"
```

---

## Task 5: Round-trip integration test

Full pipeline: parse real Vyx text → model instances → emit back → parse again → structural identity.

**Files:**
- Create: `tests/test_roundtrip.py`

- [ ] **Step 1: Write round-trip tests**

Create `tests/test_roundtrip.py`:

```python
from pathlib import Path
import pytest
from gbnf import GBNFParser
from builder import GBNFModelBuilder
from interpreter import GBNFInterpreter
from emitter import emit


@pytest.fixture(scope="module")
def pipeline(vyx_rules):
    models = GBNFModelBuilder(vyx_rules).build()
    interp = GBNFInterpreter(vyx_rules, models)
    return vyx_rules, models, interp


VYX_BODY_SAMPLES = [
    ("kv-pairs", "city=Porto"),
    ("kv-pairs", "city=Porto temp=22 wind=12"),
    ("scope-line", "ship: meth=express carr=DHL"),
    ("nl-force", "# This is a comment line"),
    ("ref", "^myref"),
    ("spread", "~myspread"),
]


@pytest.mark.parametrize("rule,text", VYX_BODY_SAMPLES)
def test_roundtrip(pipeline, rule, text):
    rules, models, interp = pipeline
    result = interp.parse(rule, text, 0)
    assert result is not None, f"parse failed for {rule!r} on {text!r}"
    instance, consumed = result
    assert consumed == len(text), f"did not consume full input: consumed {consumed} of {len(text)}"
    emitted = emit(rules, models, rule, instance)
    result2 = interp.parse(rule, emitted, 0)
    assert result2 is not None, f"re-parse failed on emitted: {emitted!r}"
    instance2, _ = result2
    assert instance.model_dump() == instance2.model_dump(), (
        f"structural identity failed\n  original:  {instance.model_dump()}\n  re-parsed: {instance2.model_dump()}"
    )
```

- [ ] **Step 2: Run round-trip tests**

```bash
uv run pytest tests/test_roundtrip.py -v
```

Expected: All pass. If a test fails on `consumed == len(text)`, the interpreter is stopping short — inspect which rule and character causes the early stop. Print `interp.parse(rule, text, 0)` to debug.

- [ ] **Step 3: Commit**

```bash
git add tests/test_roundtrip.py
git commit -m "test: add parse→emit→parse round-trip integration tests"
```

---

## Task 6: spec/extractor.py

Reads a markdown file, finds Vyx fences (`` ```@:section_id `` to `` ``` ``), returns `(section_id, body_text)` pairs. Pure string extraction — no Vyx parsing.

**Files:**
- Create: `spec/__init__.py`, `spec/extractor.py`
- Create: `tests/spec/test_extractor.py`

- [ ] **Step 1: Write failing tests**

Create `tests/spec/test_extractor.py`:

```python
from spec.extractor import extract_sections

SAMPLE_MD = """\
## D.1 — Natural Language

```@:D.1
full="Natural Language"
detect=residual cost=0
```
<!-- @D.1 -->

## D.3 — Key-Value Pairs

```@:D.3
full="Key-Value Pairs"
key: pattern="[a-zA-Z][a-zA-Z0-9_-]*" max=32
```
<!-- @D.3 -->
"""


def test_extract_returns_list_of_tuples():
    sections = extract_sections(SAMPLE_MD)
    assert isinstance(sections, list)
    assert all(isinstance(s, tuple) and len(s) == 2 for s in sections)


def test_extract_section_ids():
    sections = extract_sections(SAMPLE_MD)
    ids = [s[0] for s in sections]
    assert "D.1" in ids
    assert "D.3" in ids


def test_extract_body_text():
    sections = extract_sections(SAMPLE_MD)
    d1 = next(body for sid, body in sections if sid == "D.1")
    assert 'full="Natural Language"' in d1
    assert "detect=residual" in d1


def test_extract_body_excludes_fence_markers():
    sections = extract_sections(SAMPLE_MD)
    for _, body in sections:
        assert not body.strip().startswith("```")
        assert not body.strip().endswith("```")


def test_extract_vyx_spec(tmp_path):
    from pathlib import Path
    spec_path = Path(__file__).parent.parent.parent / "spec_built" / "metameta.md"
    if not spec_path.exists():
        pytest.skip("metameta.md not found")
    text = spec_path.read_text()
    sections = extract_sections(text)
    ids = [s[0] for s in sections]
    # All D sections must be present
    for n in range(1, 18):
        assert f"D.{n}" in ids, f"D.{n} missing"
    # None should have empty body
    for sid, body in sections:
        assert body.strip(), f"section {sid!r} has empty body"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/spec/test_extractor.py -v
```

Expected: ImportError — `spec/extractor.py` does not exist.

- [ ] **Step 3: Create spec/__init__.py and spec/extractor.py**

```bash
touch spec/__init__.py
```

Create `spec/extractor.py`:

```python
"""Spec extractor — pulls Vyx fence blocks out of a markdown file.

Finds fences of the form:
    ```@:section_id
    ...body...
    ```

Returns (section_id, body_text) pairs in document order.
No Vyx parsing — pure string extraction.
"""

from __future__ import annotations

import re

# Matches the opening fence: ```@:SECTION_ID (optional trailing whitespace)
_OPEN = re.compile(r"^```@:(\S+)\s*$", re.MULTILINE)
# Matches the closing fence: ``` alone on a line
_CLOSE = re.compile(r"^```\s*$", re.MULTILINE)


def extract_sections(markdown: str) -> list[tuple[str, str]]:
    """Return [(section_id, body_text)] for every Vyx fence in markdown.

    body_text is the raw text between the opening and closing fence markers,
    with leading/trailing blank lines stripped.
    """
    results: list[tuple[str, str]] = []
    pos = 0

    while True:
        open_match = _OPEN.search(markdown, pos)
        if not open_match:
            break

        section_id = open_match.group(1)
        body_start = open_match.end()

        close_match = _CLOSE.search(markdown, body_start)
        if not close_match:
            break  # unclosed fence — stop

        body_text = markdown[body_start : close_match.start()]
        results.append((section_id, body_text.strip()))
        pos = close_match.end()

    return results
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/spec/test_extractor.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add spec/__init__.py spec/extractor.py tests/spec/test_extractor.py
git commit -m "feat: add spec extractor (markdown → Vyx fence body_text pairs)"
```

---

## Task 7: spec/models.py

Pydantic models for compiled spec output. These are the data structures the compiler populates and the enricher reads.

**Files:**
- Create: `spec/models.py`
- Create: `tests/spec/test_models.py`

- [ ] **Step 1: Write tests**

Create `tests/spec/test_models.py`:

```python
from spec.models import DSection, GrammarBlock, ErrorCode


def test_dsection_minimal():
    s = DSection(id="D.1", full="Natural Language")
    assert s.id == "D.1"
    assert s.fields == {}
    assert s.tables == {}
    assert s.grammar is None
    assert s.errors == {}


def test_grammar_block():
    g = GrammarBlock(
        rules={"kv_pair": "key \"=\" val"},
        terminals={"MERGE_EQ": "\"+=\""},
        deps=["value", "SP"],
    )
    assert "kv_pair" in g.rules


def test_error_code_severity():
    e = ErrorCode(condition="line with = fails KV parse", severity="soft")
    assert e.severity == "soft"


def test_error_code_invalid_severity():
    import pytest
    with pytest.raises(Exception):
        ErrorCode(condition="x", severity="wrong")  # type: ignore


def test_dsection_with_grammar():
    s = DSection(
        id="D.3",
        full="Key-Value Pairs",
        grammar=GrammarBlock(rules={"kv_pair": "..."}, terminals={}, deps=[]),
        errors={"AMBIGUOUS_LINE": ErrorCode(condition="line with =", severity="soft")},
    )
    assert s.grammar is not None
    assert "AMBIGUOUS_LINE" in s.errors
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/spec/test_models.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create spec/models.py**

Create `spec/models.py`:

```python
"""Pydantic models for compiled spec sections."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorCode(BaseModel):
    condition: str
    severity: Literal["soft", "hard", "fatal"]


class GrammarBlock(BaseModel):
    rules: dict[str, str] = Field(default_factory=dict)
    terminals: dict[str, str] = Field(default_factory=dict)
    deps: list[str] = Field(default_factory=list)


class DSection(BaseModel):
    id: str
    full: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    tables: dict[str, list[Any]] = Field(default_factory=dict)
    grammar: GrammarBlock | None = None
    errors: dict[str, ErrorCode] = Field(default_factory=dict)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/spec/test_models.py -v
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add spec/models.py tests/spec/test_models.py
git commit -m "feat: add spec DSection, GrammarBlock, ErrorCode models"
```

---

## Task 8: spec/compiler.py

Parses each `(section_id, body_text)` pair from the extractor using the interpreter against the Vyx grammar. Walks the resulting model instances to populate `DSection` fields.

**Files:**
- Create: `spec/compiler.py`
- Create: `tests/spec/test_compiler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/spec/test_compiler.py`:

```python
import pytest
from pathlib import Path
from spec.extractor import extract_sections
from spec.compiler import compile_spec
from spec.models import DSection


@pytest.fixture(scope="module")
def compiled(vyx_rules):
    spec_path = Path(__file__).parent.parent.parent / "spec_built" / "metameta.md"
    if not spec_path.exists():
        pytest.skip("metameta.md not found")
    text = spec_path.read_text()
    sections = extract_sections(text)
    return compile_spec(sections, vyx_rules)


def test_compile_returns_dict(compiled):
    assert isinstance(compiled, dict)


def test_all_d_sections_present(compiled):
    for n in range(1, 18):
        assert f"D.{n}" in compiled, f"D.{n} missing"


def test_dsection_type(compiled):
    for section in compiled.values():
        assert isinstance(section, DSection)


def test_d3_full_name(compiled):
    assert compiled["D.3"].full == "Key-Value Pairs"


def test_d3_has_grammar_block(compiled):
    assert compiled["D.3"].grammar is not None
    assert "kv_pair" in compiled["D.3"].grammar.rules or \
           "kv-pair" in compiled["D.3"].grammar.rules


def test_d3_has_errors(compiled):
    assert len(compiled["D.3"].errors) > 0
    # AMBIGUOUS_LINE and INVALID_MERGE_CONTEXT are defined in D.3
    error_names = set(compiled["D.3"].errors.keys())
    assert "AMBIGUOUS_LINE" in error_names or "INVALID_MERGE_CONTEXT" in error_names


def test_d9_has_tables(compiled):
    # D.9 (Tables) has $RES, header: scope, etc.
    d9 = compiled["D.9"]
    assert d9.fields or d9.tables, "D.9 should have fields or tables"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/spec/test_compiler.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create spec/compiler.py**

Create `spec/compiler.py`:

```python
"""Spec compiler — parses Vyx fence body_text into DSection models.

Uses the PEG interpreter against the Vyx grammar to parse each section body.
Walks the resulting model instances to extract:
  - KV fields (top-level key=value pairs)
  - Tables ($TAG rows)
  - grammar: scope (rules, terminals, deps)
  - errors: scope (error code definitions)

No Vyx-specific field names are hardcoded. All extraction is driven by
the structure of the parsed model instances.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from builder import GBNFModelBuilder
from gbnf import GBNFNode
from interpreter import GBNFInterpreter
from spec.models import DSection, ErrorCode, GrammarBlock


def compile_spec(
    sections: list[tuple[str, str]],
    rules: dict[str, GBNFNode],
) -> dict[str, DSection]:
    """Compile a list of (section_id, body_text) pairs into DSection models.

    Args:
        sections: Output of spec.extractor.extract_sections().
        rules:    GBNFNode IR for the Vyx grammar (from GBNFParser().parse()).

    Returns:
        {section_id: DSection} for every section.
    """
    models = GBNFModelBuilder(rules).build()
    interp = GBNFInterpreter(rules, models)
    result: dict[str, DSection] = {}

    for section_id, body_text in sections:
        result[section_id] = _compile_section(section_id, body_text, interp, rules, models)

    return result


def _compile_section(
    section_id: str,
    body_text: str,
    interp: GBNFInterpreter,
    rules: dict[str, GBNFNode],
    models: dict[str, type[BaseModel]],
) -> DSection:
    """Parse one section body and extract its structured fields."""
    fields: dict[str, Any] = {}
    tables: dict[str, list[Any]] = {}
    grammar_block: GrammarBlock | None = None
    errors: dict[str, ErrorCode] = {}
    full_name: str = ""

    for line in body_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Try to parse as kv-pairs
        parsed = interp.parse("kv-pairs", stripped, 0)
        if parsed is not None:
            instance, consumed = parsed
            if consumed > 0:
                _extract_kv(instance, fields)

        # Detect grammar: scope opener
        if stripped.startswith("grammar:"):
            grammar_block = _extract_grammar_scope(body_text, line)

        # Detect errors: scope opener
        if stripped.startswith("errors:"):
            errors = _extract_errors_scope(body_text, line, interp)

        # Extract full= field for the section name
        if stripped.startswith('full='):
            val = stripped[5:].strip().strip('"')
            full_name = val

        # Detect table header $TAG [n]{fields}:
        if stripped.startswith("$") and "[" in stripped and ":" in stripped:
            tag, rows = _extract_table(body_text, line)
            if tag:
                tables[tag] = rows

    return DSection(
        id=section_id,
        full=full_name,
        fields=fields,
        tables=tables,
        grammar=grammar_block,
        errors=errors,
    )


def _extract_kv(instance: Any, fields: dict[str, Any]) -> None:
    """Walk a parsed kv-pairs instance and collect key→value into fields."""
    if isinstance(instance, BaseModel):
        for key, val in instance.model_dump().items():
            if val is not None:
                fields[key] = val
    elif isinstance(instance, dict):
        fields.update({k: v for k, v in instance.items() if v is not None})


def _extract_grammar_scope(body_text: str, trigger_line: str) -> GrammarBlock:
    """Extract grammar: scope content from body_text after trigger_line."""
    rules_dict: dict[str, str] = {}
    terminals_dict: dict[str, str] = {}
    deps_list: list[str] = []

    lines = body_text.splitlines()
    in_grammar = False
    in_rules = False
    in_terminals = False

    for line in lines:
        stripped = line.strip()
        if line.strip() == trigger_line.strip():
            in_grammar = True
            continue
        if not in_grammar:
            continue
        # Detect sub-scopes
        if stripped.startswith("rules:"):
            in_rules = True
            in_terminals = False
            continue
        if stripped.startswith("terminals:"):
            in_terminals = True
            in_rules = False
            continue
        if stripped.startswith("deps:"):
            deps_raw = stripped[5:].strip().strip("|").strip('"')
            deps_list = [d.strip() for d in deps_raw.split("|") if d.strip()]
            continue
        # Unindented non-empty line that isn't a sub-scope = end of grammar block
        if stripped and not line.startswith(" ") and not line.startswith("\t"):
            if not stripped.startswith("rules:") and not stripped.startswith("terminals:") and not stripped.startswith("deps:"):
                break
        # Collect rule/terminal lines (indented content)
        if (in_rules or in_terminals) and line.startswith(" ") and ":" in stripped:
            name, _, rest = stripped.partition(":")
            name = name.strip()
            val = rest.strip().strip('"')
            if in_rules:
                rules_dict[name] = val
            else:
                terminals_dict[name] = val

    return GrammarBlock(rules=rules_dict, terminals=terminals_dict, deps=deps_list)


def _extract_errors_scope(
    body_text: str,
    trigger_line: str,
    interp: GBNFInterpreter,
) -> dict[str, ErrorCode]:
    """Extract errors: scope content from body_text after trigger_line."""
    result: dict[str, ErrorCode] = {}
    lines = body_text.splitlines()
    in_errors = False

    for line in lines:
        if line.strip() == trigger_line.strip():
            in_errors = True
            continue
        if not in_errors:
            continue
        stripped = line.strip()
        if not stripped or stripped == "none":
            continue
        # Unindented non-empty line = end of errors block
        if stripped and not line.startswith(" ") and not line.startswith("\t"):
            break
        # Parse error lines: ERROR_NAME: condition="..." severity=soft
        if ":" in stripped:
            name, _, rest = stripped.partition(":")
            name = name.strip()
            rest = rest.strip()
            # Extract severity
            severity = "soft"
            if "severity=hard" in rest:
                severity = "hard"
            elif "severity=fatal" in rest:
                severity = "fatal"
            elif "severity=soft" in rest:
                severity = "soft"
            # Extract condition
            condition = ""
            cond_start = rest.find('condition="')
            if cond_start != -1:
                cond_start += len('condition="')
                cond_end = rest.find('"', cond_start)
                if cond_end != -1:
                    condition = rest[cond_start:cond_end]
            if name and name[0].isupper():
                result[name] = ErrorCode(condition=condition, severity=severity)  # type: ignore[arg-type]

    return result


def _extract_table(body_text: str, header_line: str) -> tuple[str, list[Any]]:
    """Extract $TAG rows from body_text starting at header_line."""
    stripped = header_line.strip()
    # Parse tag name
    if not stripped.startswith("$"):
        return "", []
    tag_end = 1
    while tag_end < len(stripped) and (stripped[tag_end].isalnum() or stripped[tag_end] in "_"):
        tag_end += 1
    tag = stripped[1:tag_end]

    rows: list[Any] = []
    lines = body_text.splitlines()
    collecting = False

    for line in lines:
        if line.strip() == stripped:
            collecting = True
            continue
        if not collecting:
            continue
        row_stripped = line.strip()
        if not row_stripped:
            break
        # Stop on another header-level line
        if row_stripped.startswith("$") or row_stripped.startswith("grammar:") or row_stripped.startswith("errors:"):
            break
        # Split row into cells
        cells = row_stripped.split(" ")
        rows.append(cells)

    return tag, rows
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/spec/test_compiler.py -v
```

Expected: Most pass. `test_d3_has_grammar_block` and `test_d3_has_errors` are the key validators — if they fail, print `compiled["D.3"].grammar` and `compiled["D.3"].errors` to inspect what was extracted. The compiler uses heuristic line-walking rather than full semantic parsing, so some sections may need adjustment.

- [ ] **Step 5: Commit**

```bash
git add spec/compiler.py tests/spec/test_compiler.py
git commit -m "feat: add spec compiler (body_text → DSection models)"
```

---

## Task 9: spec/enricher.py

Reads `DSection` models, derives field-level constraints and error codes, applies them to the grammar-derived `BaseModel` subclasses via `model_rebuild()`.

**Files:**
- Create: `spec/enricher.py`
- Create: `tests/spec/test_enricher.py`

- [ ] **Step 1: Write failing tests**

Create `tests/spec/test_enricher.py`:

```python
import pytest
from pathlib import Path
from pydantic import ValidationError
from builder import GBNFModelBuilder
from spec.extractor import extract_sections
from spec.compiler import compile_spec
from spec.enricher import enrich_models


@pytest.fixture(scope="module")
def enriched(vyx_rules):
    spec_path = Path(__file__).parent.parent.parent / "spec_built" / "metameta.md"
    if not spec_path.exists():
        pytest.skip("metameta.md not found")
    text = spec_path.read_text()
    sections_raw = extract_sections(text)
    compiled = compile_spec(sections_raw, vyx_rules)
    models = GBNFModelBuilder(vyx_rules).build()
    return enrich_models(models, compiled)


def test_enrich_returns_dict(enriched):
    assert isinstance(enriched, dict)


def test_enriched_models_are_subclasses(enriched):
    from pydantic import BaseModel
    for model in enriched.values():
        assert issubclass(model, BaseModel)


def test_key_max_length_enforced(enriched):
    """D.3 specifies key: max=32. Keys longer than 32 chars should fail."""
    key_model = enriched.get("key")
    if key_model is None:
        pytest.skip("key model not in registry")
    long_key = "a" * 33
    with pytest.raises((ValidationError, ValueError)):
        key_model(**{next(iter(key_model.model_fields)): long_key})


def test_error_codes_registered(enriched):
    """After enrichment, error codes from spec should be accessible."""
    from spec.enricher import get_error_registry
    registry = get_error_registry()
    # D.3 defines AMBIGUOUS_LINE
    assert "AMBIGUOUS_LINE" in registry or "INVALID_MERGE_CONTEXT" in registry
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/spec/test_enricher.py -v
```

Expected: ImportError.

- [ ] **Step 3: Create spec/enricher.py**

Create `spec/enricher.py`:

```python
"""Spec enricher — applies DSection constraints to grammar-derived models.

Reads the compiled DSection models and adds Pydantic validators and field
constraints to the grammar models via model_rebuild().

Nothing is hardcoded. All constraints are derived from DSection.fields
and DSection.errors.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, create_model

from spec.models import DSection, ErrorCode

# Global registry of error codes collected during enrichment.
# Keys are error names (e.g. "AMBIGUOUS_LINE"), values are ErrorCode instances.
_ERROR_REGISTRY: dict[str, ErrorCode] = {}


def get_error_registry() -> dict[str, ErrorCode]:
    """Return the error code registry populated by enrich_models()."""
    return dict(_ERROR_REGISTRY)


def enrich_models(
    models: dict[str, type[BaseModel]],
    sections: dict[str, DSection],
) -> dict[str, type[BaseModel]]:
    """Apply spec constraints to grammar-derived models.

    Returns the same dict (models are mutated via model_rebuild where needed).
    """
    _ERROR_REGISTRY.clear()

    # Collect all error codes from all sections
    for section in sections.values():
        _ERROR_REGISTRY.update(section.errors)

    # Apply field constraints per section
    for section_id, section in sections.items():
        _apply_constraints(models, section)

    return models


def _apply_constraints(
    models: dict[str, type[BaseModel]],
    section: DSection,
) -> None:
    """Apply constraints from one DSection to the relevant models."""
    fields_meta = section.fields

    # Look for max= and min= constraints on named grammar constructs.
    # e.g. "key: max=32" → add max_length=32 to the "key" model's str field.
    for field_name, constraint_value in fields_meta.items():
        # field_name might be "key", "id", "tag" etc.
        if field_name not in models:
            continue
        model = models[field_name]
        _apply_length_constraints(model, field_name, constraint_value, models)


def _apply_length_constraints(
    model: type[BaseModel],
    model_name: str,
    constraint_spec: Any,
    models: dict[str, type[BaseModel]],
) -> None:
    """Parse constraint_spec dict and apply max_length/min_length to str fields."""
    if not isinstance(constraint_spec, dict):
        return

    max_len = constraint_spec.get("max")
    min_len = constraint_spec.get("min")

    if max_len is None and min_len is None:
        return

    # Rebuild model fields with the new constraints on str fields
    new_fields: dict[str, Any] = {}
    changed = False

    for fname, field_info in model.model_fields.items():
        ann = field_info.annotation
        if ann is str or ann == str:
            kwargs: dict[str, Any] = {}
            if max_len is not None:
                try:
                    kwargs["max_length"] = int(max_len)
                except (ValueError, TypeError):
                    pass
            if min_len is not None:
                try:
                    kwargs["min_length"] = int(min_len)
                except (ValueError, TypeError):
                    pass
            if kwargs:
                new_fields[fname] = (str, Field(..., **kwargs))
                changed = True
            else:
                new_fields[fname] = (ann, field_info)
        else:
            new_fields[fname] = (ann, field_info)

    if changed:
        rebuilt = create_model(model_name, **new_fields)
        models[model_name] = rebuilt
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/spec/test_enricher.py -v
```

Expected: `test_enrich_returns_dict`, `test_enriched_models_are_subclasses`, `test_error_codes_registered` pass. `test_key_max_length_enforced` may require inspecting the compiled D.3 section to confirm `key: max=32` is being parsed into `section.fields["key"]["max"] = 32`. If the constraint isn't applying, add a debug print: `print(compiled["D.3"].fields)` to check what the compiler extracted.

- [ ] **Step 5: Commit**

```bash
git add spec/enricher.py tests/spec/test_enricher.py
git commit -m "feat: add spec enricher (DSection constraints → model validators)"
```

---

## Task 10: Full suite and validation

Run all tests, verify the GBNF→Pydantic→GBNF roundtrip using the llama.cpp tool.

**Files:**
- No new source files
- Validation script only (not committed to tests/)

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: All tests pass. Fix any failures before continuing.

- [ ] **Step 2: Verify GBNF → Pydantic → GBNF roundtrip**

Run this in the project root:

```python
# Save as validate_roundtrip.py and run with: uv run python validate_roundtrip.py
import sys, json
from pathlib import Path
from gbnf import GBNFParser
from builder import GBNFModelBuilder

GRAMMAR_PATH = Path("spec_built/grammar.gbnf")
LLAMA_TOOL = Path("/home/mika/llama.cpp/examples/pydantic_models_to_grammar.py")

grammar_text = GRAMMAR_PATH.read_text()
rules = GBNFParser().parse(grammar_text)
models = GBNFModelBuilder(rules).build()

# Export JSON schemas for key rules
schemas = {}
for rule_name in ["kv-pair", "kv-pairs", "scope-line", "table-block", "packet"]:
    if rule_name in models:
        schemas[rule_name] = models[rule_name].model_json_schema()

print(f"Built {len(models)} models from grammar")
print(f"Sample schemas exported for: {list(schemas.keys())}")
for name, schema in schemas.items():
    print(f"\n  {name}:")
    print(f"  {json.dumps(schema, indent=2)[:200]}...")
```

```bash
uv run python validate_roundtrip.py
```

Expected: Prints model count and schema excerpts without errors.

- [ ] **Step 3: Final commit**

```bash
git add docs/
git commit -m "docs: add design spec and implementation plan"
```

---

## Notes

- `base.py` and `parser.py` are not deleted — they are referenced by `example.py` and serve as historical reference.
- `example.py` section 4 references `VyxBase._sigil_registry` which no longer exists after the builder refactor — it will print warnings or errors but this does not affect the new pipeline.
- The compiler (Task 8) uses heuristic line-walking rather than full semantic Vyx parsing because the spec is self-referential. This is intentional for the bootstrap layer — a future iteration can replace the heuristic extractor with a fully interpreter-driven one once the round-trip is stable.
