# Parallel-track IR cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dual-shape IR migration (Tasks 19–25 of the prior plan) with a parallel-track build: stand up `new_gbnf/`, `new_codegen/`, and `parsing/lark_builder + transformer` against the IrItem shape, then cut over in one mechanical commit. `new_codegen/` is built directly to the target generated-code shape from `prototyping/curr/2_LEXIC_GENERATED_CODE_PROPOSAL.md` (items 1–5).

**Architecture:** New shape lands in fresh modules that don't touch legacy code. Old shape stays untouched until the final cutover commit, which routes `compile.py` through the new pipeline, deletes legacy modules, renames `new_*` → final names via `git mv` + `sed`, and tightens IR types. The integration suite is the cutover safety net — if it passes, the rerouted pipeline is correct end-to-end.

**Tech Stack:** Python 3.12, Pydantic v2, Lark, hypothesis, pytest, ruff, uv.

**Source spec:** `docs/superpowers/specs/2026-05-08-parallel-track-ir-cutover-design.md` (commit `e74f18c`).

---

## Conventions

- All commands run via `uv run`. Never bare `pytest` or `ruff`.
- Test layout mirrors src layout exactly. When a src file is created/moved/renamed/deleted, its test file gets the same treatment in the same commit.
- Substantive `__init__.py` files get test files named `test_init_<package>.py` (per CLAUDE.md memory; avoids collision).
- Commits never carry `Co-Authored-By` lines.
- No `# type: ignore`, `# noqa`, etc. Fix the root cause.
- Each task ends with `uv run pytest tests/ -q && uv run ruff check src/ tests/` green before commit.

## Reference imports (use these exactly)

```python
# IR AST
from lexic.ir.nodes import (
    IrAlternation, IrAst, IrCharClass, IrGroup, IrItem,
    IrLiteral, IrRule, IrRuleRef, IrSequence, Quantifier,
)
from lexic.ir.spec import RuleSpec, NewRuleSpec   # NewRuleSpec collapses in Slice 4

# IR services
from lexic.ir.derive import derive_specs
from lexic.ir.directives import parse_directives, Directives
from lexic.ir.escapes import EscapeCodec
from lexic.ir.emit import FlavourEmitter
from lexic.ir.walk import IrTransformer, IrVisitor

# Grammars
from lexic.grammars.flavour import Flavour
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.grammars.abnf.flavour import AbnfFlavour

# Parsing
from lexic.parsing.meta_parser import MetaGrammarParser

# Compile
from lexic.compile import compile_grammar, compile_text, compile_from_path
```

---

# Slice 1 — `new_gbnf/` (full mirror, IrItem-only)

## Task 1: `new_gbnf/` skeleton + pure-copy modules (`__init__.py`, `escapes.py`, `meta_grammar.py`)

**Why this task:** Lay down the package directory and the three files that are byte-equivalent to current `gbnf/` siblings. Imports inside these files are re-pointed at `lexic.grammars.new_gbnf.*` — that's the only difference from the originals.

**Files:**
- Create: `src/lexic/grammars/new_gbnf/__init__.py`
- Create: `src/lexic/grammars/new_gbnf/escapes.py`
- Create: `src/lexic/grammars/new_gbnf/meta_grammar.py`
- Create: `tests/unit/lexic/grammars/new_gbnf/__init__.py` (empty)
- Create: `tests/unit/lexic/grammars/new_gbnf/test_init_new_gbnf.py`
- Create: `tests/unit/lexic/grammars/new_gbnf/test_escapes.py`
- Create: `tests/unit/lexic/grammars/new_gbnf/test_meta_grammar.py`

- [ ] **Step 1: Read the existing `gbnf/escapes.py` and `gbnf/meta_grammar.py` to confirm what's being copied.**

```bash
cat src/lexic/grammars/gbnf/escapes.py
cat src/lexic/grammars/gbnf/meta_grammar.py
cat src/lexic/grammars/gbnf/__init__.py
```

- [ ] **Step 2: Create `src/lexic/grammars/new_gbnf/__init__.py`.**

```python
"""new_gbnf — IrItem-shape mirror of grammars/gbnf/.

Exists during the parallel-track IR cutover. Renamed to grammars/gbnf/
at cutover (Slice 4). Internal imports reference lexic.grammars.new_gbnf.X
so the slice can land green without touching legacy gbnf/.
"""

from lexic.grammars.new_gbnf.escapes import GbnfEscapes
from lexic.grammars.new_gbnf.flavour import GbnfFlavour as NewGbnfFlavour
from lexic.grammars.new_gbnf.meta_grammar import META_GRAMMAR

__all__ = ["GbnfEscapes", "META_GRAMMAR", "NewGbnfFlavour"]
```

(The `flavour.py` import will fail at this step — that's fine; we land it in Task 2.)

- [ ] **Step 3: Copy `escapes.py`.** Open `src/lexic/grammars/gbnf/escapes.py` and reproduce its contents at `src/lexic/grammars/new_gbnf/escapes.py`. Re-point any `from lexic.grammars.gbnf.X` imports to `from lexic.grammars.new_gbnf.X` (typically there are none — `escapes.py` only imports from `lexic.ir.escapes`).

- [ ] **Step 4: Copy `meta_grammar.py`.** Same procedure for `src/lexic/grammars/new_gbnf/meta_grammar.py`. Re-point imports if any reference `lexic.grammars.gbnf.*`.

- [ ] **Step 5: Write the test files.**

`tests/unit/lexic/grammars/new_gbnf/test_init_new_gbnf.py`:

```python
"""Sanity: new_gbnf package re-exports the right names."""
from __future__ import annotations


def test_imports():
    from lexic.grammars import new_gbnf

    assert hasattr(new_gbnf, "GbnfEscapes")
    assert hasattr(new_gbnf, "META_GRAMMAR")
    assert hasattr(new_gbnf, "NewGbnfFlavour")
```

`tests/unit/lexic/grammars/new_gbnf/test_escapes.py`:

```python
"""GbnfEscapes (mirror) parity with the legacy module."""
from __future__ import annotations

from lexic.grammars.new_gbnf.escapes import GbnfEscapes as NewEscapes
from lexic.grammars.gbnf.escapes import GbnfEscapes as LegacyEscapes


def test_decode_parity():
    cases = [r"\n", r"\t", r"\r", r"\\", r"\"", r"ÿ", r"\x41", "abc"]
    for s in cases:
        assert NewEscapes().decode(s) == LegacyEscapes().decode(s)


def test_encode_parity():
    cases = ["\n", "\t", "\\", '"', "abc", "\x00"]
    for s in cases:
        assert NewEscapes().encode(s) == LegacyEscapes().encode(s)
```

`tests/unit/lexic/grammars/new_gbnf/test_meta_grammar.py`:

```python
"""META_GRAMMAR mirror parity."""
from __future__ import annotations

from lexic.grammars.new_gbnf.meta_grammar import META_GRAMMAR as NEW
from lexic.grammars.gbnf.meta_grammar import META_GRAMMAR as LEGACY


def test_meta_grammar_byte_identical():
    assert NEW == LEGACY
```

- [ ] **Step 6: Run — expect ImportError because `new_gbnf/flavour.py` is missing.**

```bash
uv run pytest tests/unit/lexic/grammars/new_gbnf/ -q
```

Expected: `test_init_new_gbnf.py` fails with `ImportError`. Other tests may pass standalone.

- [ ] **Step 7: Make `__init__.py` defer the flavour import until Task 2.** Adjust `__init__.py`:

```python
"""new_gbnf — IrItem-shape mirror of grammars/gbnf/.

Exists during the parallel-track IR cutover. Renamed to grammars/gbnf/
at cutover (Slice 4). Internal imports reference lexic.grammars.new_gbnf.X
so the slice can land green without touching legacy gbnf/.
"""

from lexic.grammars.new_gbnf.escapes import GbnfEscapes
from lexic.grammars.new_gbnf.meta_grammar import META_GRAMMAR

__all__ = ["GbnfEscapes", "META_GRAMMAR"]
```

(Add `NewGbnfFlavour` re-export back in Task 2 once `flavour.py` lands.)

- [ ] **Step 8: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/grammars/new_gbnf/ -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 9: Commit.**

```bash
git add src/lexic/grammars/new_gbnf/__init__.py \
        src/lexic/grammars/new_gbnf/escapes.py \
        src/lexic/grammars/new_gbnf/meta_grammar.py \
        tests/unit/lexic/grammars/new_gbnf/
git commit -m "feat(new_gbnf): scaffold + escapes + meta_grammar mirrors"
```

---

## Task 2: `new_gbnf/flavour.py` (re-pointed imports)

**Why this task:** `Flavour` subclass for the new mirror. Almost identical to current `gbnf/flavour.py`; only difference is internal imports reference `new_gbnf` siblings.

**Files:**
- Create: `src/lexic/grammars/new_gbnf/flavour.py`
- Create: `tests/unit/lexic/grammars/new_gbnf/test_flavour.py`
- Modify: `src/lexic/grammars/new_gbnf/__init__.py` (re-add `NewGbnfFlavour` export)

- [ ] **Step 1: Read `gbnf/flavour.py`.**

```bash
cat src/lexic/grammars/gbnf/flavour.py
```

- [ ] **Step 2: Write the failing test.**

`tests/unit/lexic/grammars/new_gbnf/test_flavour.py`:

```python
"""GbnfFlavour mirror parity check."""
from __future__ import annotations

from lexic.grammars.new_gbnf.flavour import GbnfFlavour as NewFlavour
from lexic.grammars.gbnf.flavour import GbnfFlavour as LegacyFlavour
from lexic.grammars.flavour import Flavour
from lexic.ir.nodes import Quantifier


def test_subclass():
    assert issubclass(NewFlavour, Flavour)


def test_metadata():
    assert NewFlavour.name == LegacyFlavour.name == "gbnf"
    assert NewFlavour.extensions == LegacyFlavour.extensions == (".gbnf",)


def test_meta_grammar_identity():
    assert NewFlavour.meta_grammar == LegacyFlavour.meta_grammar


def test_parse_quantifier_parity():
    cases = ["", "?", "+", "*", "{2,5}", "{0,15}", "{3}"]
    for s in cases:
        assert NewFlavour.parse_quantifier(s) == LegacyFlavour.parse_quantifier(s)


def test_parse_charclass_parity():
    cases = ["[a-z]", "[0-9]", "[^abc]", r"[\\\"]"]
    for s in cases:
        assert NewFlavour.parse_charclass(s) == LegacyFlavour.parse_charclass(s)


def test_line_comment_token():
    assert NewFlavour.line_comment == LegacyFlavour.line_comment
```

- [ ] **Step 3: Run — expect `ModuleNotFoundError`.**

```bash
uv run pytest tests/unit/lexic/grammars/new_gbnf/test_flavour.py -q
```

- [ ] **Step 4: Create `src/lexic/grammars/new_gbnf/flavour.py`.** Copy the contents of `src/lexic/grammars/gbnf/flavour.py`. The only change: the `emitter` ClassVar must point at the new emitter (which lands in Task 4). Until Task 4 lands, leave `emitter` as a placeholder identical to legacy:

```python
# At the top of new_gbnf/flavour.py, when copying gbnf/flavour.py, every
# reference to lexic.grammars.gbnf.X gets re-pointed to lexic.grammars.new_gbnf.X
# EXCEPT lexic.grammars.gbnf.emitter (the legacy emitter) — that stays
# referencing legacy until Task 4 lands the new emitter, at which point this
# file is updated to point at new_gbnf.emitter.
from lexic.grammars.new_gbnf.escapes import GbnfEscapes
from lexic.grammars.new_gbnf.meta_grammar import META_GRAMMAR
# Temporary: emitter still points at legacy until Task 4 rewires it.
from lexic.grammars.gbnf.emitter import GbnfEmitter

# … rest copied verbatim from gbnf/flavour.py …
```

(Marking the temporary import: a single-line comment is fine. It's removed in Task 4.)

- [ ] **Step 5: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/grammars/new_gbnf/test_flavour.py -q
```

- [ ] **Step 6: Re-add the export to `new_gbnf/__init__.py`:**

```python
"""new_gbnf — IrItem-shape mirror of grammars/gbnf/."""

from lexic.grammars.new_gbnf.escapes import GbnfEscapes
from lexic.grammars.new_gbnf.flavour import GbnfFlavour
from lexic.grammars.new_gbnf.meta_grammar import META_GRAMMAR

__all__ = ["GbnfEscapes", "GbnfFlavour", "META_GRAMMAR"]
```

Update `tests/unit/lexic/grammars/new_gbnf/test_init_new_gbnf.py` to assert:

```python
def test_imports():
    from lexic.grammars import new_gbnf

    assert hasattr(new_gbnf, "GbnfEscapes")
    assert hasattr(new_gbnf, "GbnfFlavour")
    assert hasattr(new_gbnf, "META_GRAMMAR")
```

- [ ] **Step 7: Run full suite + ruff + commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/new_gbnf/flavour.py \
        src/lexic/grammars/new_gbnf/__init__.py \
        tests/unit/lexic/grammars/new_gbnf/test_flavour.py \
        tests/unit/lexic/grammars/new_gbnf/test_init_new_gbnf.py
git commit -m "feat(new_gbnf): GbnfFlavour mirror (emitter re-wired in Task 4)"
```

---

## Task 3: `new_gbnf/parser.py` (thin `MetaGrammarParser.for_flavour` wrapper)

**Why this task:** The `parser.py` in legacy `gbnf/` still goes through the legacy AST. The mirror's `parser.py` is a thin wrapper around the new pipeline.

**Files:**
- Create: `src/lexic/grammars/new_gbnf/parser.py`
- Create: `tests/unit/lexic/grammars/new_gbnf/test_parser.py`

- [ ] **Step 1: Write the failing test.**

`tests/unit/lexic/grammars/new_gbnf/test_parser.py`:

```python
"""GbnfParser (new) — thin wrapper around MetaGrammarParser.for_flavour."""
from __future__ import annotations

from lexic.grammars.new_gbnf.parser import GbnfParser, parse_gbnf
from lexic.ir.nodes import IrAst, IrRule


def test_parse_gbnf_returns_ir_ast():
    text = 'root ::= "hello"\n'
    ast = parse_gbnf(text)
    assert isinstance(ast, IrAst)
    assert len(ast.rules) == 1
    assert ast.rules[0].name == "root"


def test_class_form():
    parser = GbnfParser()
    text = 'root ::= "x" "y"\n'
    ast = parser.parse(text)
    assert isinstance(ast, IrAst)
    assert ast.rules[0].name == "root"


def test_class_uses_new_gbnf_flavour():
    """GbnfParser must drive MetaGrammarParser via new_gbnf.GbnfFlavour, not legacy."""
    from lexic.grammars.new_gbnf.flavour import GbnfFlavour as NewFlavour

    parser = GbnfParser()
    ast = parser.parse('root ::= "x"\n')
    # Tracer test: the parser delegates to MetaGrammarParser.for_flavour(NewFlavour);
    # the line_comment token from NewFlavour is what was used to strip directives.
    # We can't introspect the internal flavour from the IrAst, but we can confirm
    # round-trip through both new_gbnf.GbnfFlavour and the legacy one produce
    # equivalent IrAst on simple inputs (since the mirror's flavour is a copy):
    from lexic.parsing.meta_parser import MetaGrammarParser
    expected = MetaGrammarParser.for_flavour(NewFlavour).parse('root ::= "x"\n')
    assert len(ast.rules) == len(expected.rules)
    assert ast.rules[0].name == expected.rules[0].name
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/grammars/new_gbnf/test_parser.py -q
```

- [ ] **Step 3: Create `src/lexic/grammars/new_gbnf/parser.py`.**

```python
"""GbnfParser: thin wrapper around MetaGrammarParser.for_flavour(GbnfFlavour).

Replaces the legacy ast.py + Lark transformer pipeline. The new parser
delegates entirely to MetaGrammarParser, which produces an IrAst directly
from text via the canonical-tagged Lark grammar.
"""

from __future__ import annotations

from lexic.grammars.new_gbnf.flavour import GbnfFlavour
from lexic.ir.nodes import IrAst
from lexic.parsing.meta_parser import MetaGrammarParser


def parse_gbnf(text: str) -> IrAst:
    """Parse GBNF text via the new IR-AST pipeline."""
    return MetaGrammarParser.for_flavour(GbnfFlavour).parse(text)


class GbnfParser:
    """Class form for adapter binding.

    Stateless; instances exist only to satisfy the FlavourParser protocol.
    """

    def parse(self, text: str) -> IrAst:
        return parse_gbnf(text)
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/grammars/new_gbnf/test_parser.py -q
```

- [ ] **Step 5: Run full suite + ruff + commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/new_gbnf/parser.py tests/unit/lexic/grammars/new_gbnf/test_parser.py
git commit -m "feat(new_gbnf): GbnfParser thin wrapper around MetaGrammarParser"
```

---

## Task 4: `new_gbnf/emitter.py` (IrItem-only `GbnfEmitter`)

**Why this task:** The single most important emitter for cross-flavour round-trip. Dispatches on IrItem.atom shapes — IrLiteral, IrCharClass, IrRuleRef, IrGroup — plus the bare `IrAlternation` top-level case for multi-arm `value_str` (Decision C from the prior plan).

**Files:**
- Create: `src/lexic/grammars/new_gbnf/emitter.py`
- Create: `tests/unit/lexic/grammars/new_gbnf/test_emitter.py`
- Modify: `src/lexic/grammars/new_gbnf/flavour.py` (re-point `emitter` ClassVar at the new emitter)

- [ ] **Step 1: Write the failing tests.**

`tests/unit/lexic/grammars/new_gbnf/test_emitter.py`:

```python
"""GbnfEmitter (IrItem-shape only)."""
from __future__ import annotations

from lexic.grammars.new_gbnf.emitter import GbnfEmitter
from lexic.ir.nodes import (
    IrAlternation, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrRuleRef, IrSequence, Quantifier,
)
from lexic.ir.spec import RuleSpec


def _spec(name: str, kind: str, items, field_map=None):
    return RuleSpec(
        rule_name=name, class_name=name.title(),
        parent_class_name="GrammarModel",
        kind=kind, items=list(items), field_map=field_map or {},
    )


def test_emit_literal():
    s = _spec("greet", "value_str", [IrItem(IrLiteral("hello"))])
    out = GbnfEmitter([]).emit_rule(s)
    assert out == 'greet ::= "hello"'


def test_emit_charclass_with_quantifier():
    s = _spec("digit", "value_str",
              [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    assert GbnfEmitter([]).emit_rule(s) == "digit ::= [0-9]+"


def test_emit_negated_charclass():
    s = _spec("nq", "value_str", [IrItem(IrCharClass('"', negated=True))])
    assert GbnfEmitter([]).emit_rule(s) == 'nq ::= [^"]'


def test_emit_ruleref_with_quantifier():
    s = _spec("expr", "sequence",
              [IrItem(IrRuleRef("term"), Quantifier(1, None))])
    assert GbnfEmitter([]).emit_rule(s) == "expr ::= term+"


def test_emit_group_inline_alternation():
    grp = IrGroup(IrAlternation((
        IrSequence((IrItem(IrRuleRef("a")),)),
        IrSequence((IrItem(IrRuleRef("b")),)),
    )))
    s = _spec("r", "sequence", [IrItem(grp)])
    assert "(a | b)" in GbnfEmitter([]).emit_rule(s)


def test_emit_group_with_quantifier():
    grp = IrGroup(IrAlternation((
        IrSequence((IrItem(IrLiteral("foo")),)),
        IrSequence((IrItem(IrLiteral("bar")),)),
    )))
    s = _spec("r", "value_str", [IrItem(grp, Quantifier(1, None))])
    out = GbnfEmitter([]).emit_rule(s)
    assert out.endswith("+")
    assert '"foo"' in out and '"bar"' in out


def test_emit_alternation_kind():
    """kind='alternation': items are IrItem(IrRuleRef(arm_name)) per arm."""
    s = _spec("kind", "alternation",
              [IrItem(IrRuleRef("num")), IrItem(IrRuleRef("ident"))])
    assert GbnfEmitter([]).emit_rule(s) == "kind ::= num | ident"


def test_emit_value_str_multi_arm_via_bare_alternation():
    """Decision C: multi-arm value_str places IrAlternation at items[0]."""
    alt = IrAlternation((
        IrSequence((IrItem(IrLiteral("int")),)),
        IrSequence((IrItem(IrLiteral("float")),)),
    ))
    s = _spec("ty", "value_str", [alt])
    out = GbnfEmitter([]).emit_rule(s)
    assert out == 'ty ::= "int" | "float"'


def test_emit_full_grammar_concatenates():
    specs = [
        _spec("root", "sequence",
              [IrItem(IrRuleRef("expr"))], {"expr": 0}),
        _spec("expr", "value_str",
              [IrItem(IrCharClass("a-z"), Quantifier(1, None))]),
    ]
    out = GbnfEmitter(specs).emit()
    assert "root ::= expr" in out
    assert "expr ::= [a-z]+" in out
    assert out.endswith("\n")
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/grammars/new_gbnf/test_emitter.py -q
```

- [ ] **Step 3: Create `src/lexic/grammars/new_gbnf/emitter.py`.**

```python
"""GbnfEmitter: RuleSpec list (IrItem-shape) → GBNF text.

Single-shape only — no legacy-atom dispatch. The mirror replaces
grammars/gbnf/emitter.py at cutover (Slice 4).
"""

from __future__ import annotations

from typing import ClassVar

from lexic.ir.emit import FlavourEmitter
from lexic.ir.nodes import (
    IrAlternation, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrRuleRef, IrSequence,
)
from lexic.ir.spec import RuleSpec
from lexic.utils.quantifiers import bounds_to_quantifier


def _quant_suffix(q) -> str:
    return bounds_to_quantifier(q.min, q.max)


def _bracket(pattern: str, negated: bool) -> str:
    return f"[{'^' if negated else ''}{pattern}]"


def _atom_to_gbnf_item(item: IrItem) -> str:
    atom = item.atom
    q = _quant_suffix(item.quantifier)
    if isinstance(atom, IrLiteral):
        return f'"{atom.value}"{q}'
    if isinstance(atom, IrCharClass):
        return _bracket(atom.pattern, atom.negated) + q
    if isinstance(atom, IrRuleRef):
        return atom.name + q
    if isinstance(atom, IrGroup):
        body = _alt_to_gbnf(atom.body)
        return f"({body}){q}" if q else f"({body})"
    raise TypeError(f"Unsupported IR atom for GBNF emit: {type(atom).__name__}")


def _seq_to_gbnf(seq: IrSequence) -> str:
    return " ".join(_atom_to_gbnf_item(it) for it in seq.items)


def _alt_to_gbnf(alt: IrAlternation) -> str:
    return " | ".join(_seq_to_gbnf(s) for s in alt.arms)


class GbnfEmitter(FlavourEmitter):
    """Emit GBNF text from RuleSpec list with IrItem-shaped items."""

    supports: ClassVar[frozenset[str]] = frozenset({
        "literal", "char_class", "negated_class", "quantifier",
        "alternation", "non_capturing_group", "unicode_escape",
    })

    def __init__(self, specs: list[RuleSpec]) -> None:
        self._specs = specs

    def emit(self, specs: list[RuleSpec] | None = None) -> str:
        if specs is None:
            specs = self._specs
        return "\n".join(self.emit_rule(s) for s in specs) + "\n"

    def emit_rule(self, spec: RuleSpec) -> str:
        return f"{spec.rule_name} ::= {self._emit_body(spec)}"

    def _emit_body(self, spec: RuleSpec) -> str:
        if not spec.items:
            return '""'
        if spec.kind == "alternation":
            # items are IrItem(IrRuleRef(arm_name)) per arm
            return " | ".join(
                it.atom.name for it in spec.items
                if isinstance(it, IrItem) and isinstance(it.atom, IrRuleRef)
            )
        first = spec.items[0]
        if isinstance(first, IrAlternation):
            # Multi-arm value_str: bare IrAlternation at items[0]
            return _alt_to_gbnf(first)
        # Sequence of IrItems
        return " ".join(_atom_to_gbnf_item(it) for it in spec.items)
```

- [ ] **Step 4: Re-wire `new_gbnf/flavour.py` to use the new emitter.** Replace the temporary import:

```python
# Was:  from lexic.grammars.gbnf.emitter import GbnfEmitter
# Now:
from lexic.grammars.new_gbnf.emitter import GbnfEmitter
```

Remove the temporary-comment line.

- [ ] **Step 5: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/grammars/new_gbnf/ -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 6: Commit.**

```bash
git add src/lexic/grammars/new_gbnf/emitter.py \
        src/lexic/grammars/new_gbnf/flavour.py \
        tests/unit/lexic/grammars/new_gbnf/test_emitter.py
git commit -m "feat(new_gbnf): GbnfEmitter (IrItem-shape only) + flavour rewire"
```

---

## Task 5: `new_gbnf/adapter.py` (`GbnfAdapter` with `flavour_cls`)

**Why this task:** Adapter glue that exposes `parser` + `emitter` and announces `flavour_cls = GbnfFlavour`. At cutover (Slice 4) this becomes the canonical adapter.

**Files:**
- Create: `src/lexic/grammars/new_gbnf/adapter.py`
- Create: `tests/unit/lexic/grammars/new_gbnf/test_adapter.py`
- Modify: `src/lexic/grammars/new_gbnf/__init__.py` (export `GbnfAdapter`)

- [ ] **Step 1: Write the failing test.**

`tests/unit/lexic/grammars/new_gbnf/test_adapter.py`:

```python
"""GbnfAdapter (new) — exposes parser + emitter + flavour_cls."""
from __future__ import annotations

from lexic.grammars.new_gbnf.adapter import GbnfAdapter
from lexic.grammars.new_gbnf.emitter import GbnfEmitter
from lexic.grammars.new_gbnf.flavour import GbnfFlavour
from lexic.grammars.new_gbnf.parser import GbnfParser
from lexic.ir.nodes import IrAst


def test_metadata():
    a = GbnfAdapter()
    assert a.name == "gbnf"
    assert a.extensions == (".gbnf",)
    assert a.flavour_cls is GbnfFlavour


def test_parser_returns_ir_ast():
    a = GbnfAdapter()
    ast = a.parser.parse('root ::= "x"\n')
    assert isinstance(ast, IrAst)


def test_emitter_is_gbnf_emitter():
    a = GbnfAdapter()
    assert isinstance(a.emitter, GbnfEmitter)


def test_parser_is_gbnf_parser():
    a = GbnfAdapter()
    assert isinstance(a.parser, GbnfParser)
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/grammars/new_gbnf/test_adapter.py -q
```

- [ ] **Step 3: Create `src/lexic/grammars/new_gbnf/adapter.py`.**

```python
"""GbnfAdapter (new): binds parser + emitter for the IrItem-shape pipeline."""

from __future__ import annotations

from lexic.grammars.new_gbnf.emitter import GbnfEmitter
from lexic.grammars.new_gbnf.flavour import GbnfFlavour
from lexic.grammars.new_gbnf.parser import GbnfParser


class GbnfAdapter:
    """Adapter glue. Replaces grammars/gbnf/adapter.py at cutover."""

    name: str = "gbnf"
    extensions: tuple[str, ...] = (".gbnf",)
    flavour_cls: type = GbnfFlavour

    def __init__(self) -> None:
        self.parser = GbnfParser()
        self.emitter = GbnfEmitter([])
```

- [ ] **Step 4: Update `src/lexic/grammars/new_gbnf/__init__.py`:**

```python
"""new_gbnf — IrItem-shape mirror of grammars/gbnf/."""

from lexic.grammars.new_gbnf.adapter import GbnfAdapter
from lexic.grammars.new_gbnf.emitter import GbnfEmitter
from lexic.grammars.new_gbnf.escapes import GbnfEscapes
from lexic.grammars.new_gbnf.flavour import GbnfFlavour
from lexic.grammars.new_gbnf.meta_grammar import META_GRAMMAR
from lexic.grammars.new_gbnf.parser import GbnfParser, parse_gbnf

__all__ = [
    "GbnfAdapter", "GbnfEmitter", "GbnfEscapes", "GbnfFlavour",
    "GbnfParser", "META_GRAMMAR", "parse_gbnf",
]
```

- [ ] **Step 5: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/grammars/new_gbnf/ -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 6: Commit.**

```bash
git add src/lexic/grammars/new_gbnf/adapter.py \
        src/lexic/grammars/new_gbnf/__init__.py \
        tests/unit/lexic/grammars/new_gbnf/test_adapter.py
git commit -m "feat(new_gbnf): GbnfAdapter with flavour_cls; package exports"
```

End of Slice 1. The mirror is self-contained; nothing in production code imports from `new_gbnf` yet.

---

# Slice 2 — `new_codegen/` (target-shape)

## Task 6: Tier 2 expansion in `lexic/ir/naming.py`

**Why this task:** Extend the well-known-pattern table to the full 10-entry list from the proposal §6.2. No structural change yet; just data.

**Files:**
- Modify: `src/lexic/ir/naming.py`
- Modify: `tests/unit/lexic/ir/test_naming.py`

- [ ] **Step 1: Read the current `naming.py` Tier 2 tables.**

```bash
cat src/lexic/ir/naming.py
```

Confirm the current contents of `_CHARCLASS_NAMES` and `_LITERAL_NAMES`.

- [ ] **Step 2: Add tests for new Tier 2 entries.**

Append to `tests/unit/lexic/ir/test_naming.py`:

```python
def test_charclass_names_full_table():
    """Tier 2 (proposal §6.2): 10-entry built-in pattern library."""
    from lexic.ir.naming import _CHARCLASS_NAMES

    expected = {
        "[0-9]": "digit",
        "[0-9]+": "digits",
        "[a-z]": "lower",
        "[A-Z]": "upper",
        "[a-zA-Z]": "letter",
        "[a-zA-Z_]": "letter",
        "[a-zA-Z_0-9]": "alnum",
        "[a-zA-Z_0-9]*": "alnum_tail",
        "[ \\t]+": "spaces",
        "[ \\t\\n]+": "ws",
    }
    for pattern, name in expected.items():
        assert _CHARCLASS_NAMES.get(pattern) == name, (
            f"Tier 2: {pattern} → expected {name!r}, got {_CHARCLASS_NAMES.get(pattern)!r}"
        )
```

- [ ] **Step 3: Run — expect failures.**

```bash
uv run pytest tests/unit/lexic/ir/test_naming.py::test_charclass_names_full_table -v
```

- [ ] **Step 4: Update `_CHARCLASS_NAMES` in `src/lexic/ir/naming.py`** to include the 10 entries above. Preserve any pre-existing entries that aren't in this set (no entries get removed, only added).

- [ ] **Step 5: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_naming.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 6: Commit.**

```bash
git add src/lexic/ir/naming.py tests/unit/lexic/ir/test_naming.py
git commit -m "feat(naming): expand Tier 2 pattern library to 10 entries"
```

---

## Task 7: Tier 3 positional naming in `lexic/ir/derive.py::_field_map`

**Why this task:** Replace the `_sanitize_pattern` fallback with structural positional names (`head` / `part_2` / `part_3` for IrCharClass; `kind` / `kind_2` for IrGroup-with-rulerefs).

**Files:**
- Modify: `src/lexic/ir/derive.py` (`_field_map`, `_ATOM_HINT`)
- Modify: `src/lexic/ir/naming.py` (drop `_sanitize_pattern` if no remaining caller; otherwise leave)
- Modify: `tests/unit/lexic/ir/test_derive.py`
- Modify: `tests/unit/lexic/ir/test_naming.py` (drop `_sanitize_pattern`-dependent assertions if any)

- [ ] **Step 1: Read `derive.py:_field_map` and `_ATOM_HINT`.**

```bash
sed -n '180,220p' src/lexic/ir/derive.py
```

- [ ] **Step 2: Write the failing tests.**

Append to `tests/unit/lexic/ir/test_derive.py`:

```python
def test_field_map_tier3_pattern_positional_head():
    """First IrCharClass without Tier 2 match → 'head'."""
    from lexic.ir.derive import _field_map
    from lexic.ir.nodes import IrCharClass, IrItem, Quantifier

    items = [IrItem(IrCharClass("xyz_unmatched"), Quantifier(1, 1))]
    fm = _field_map(items)
    assert list(fm.keys()) == ["head"]


def test_field_map_tier3_pattern_positional_part_n():
    """Second IrCharClass without Tier 2 match → 'part_2'."""
    from lexic.ir.derive import _field_map
    from lexic.ir.nodes import IrCharClass, IrItem, Quantifier

    items = [
        IrItem(IrCharClass("xyz_unmatched"), Quantifier(1, 1)),
        IrItem(IrCharClass("abc_unmatched"), Quantifier(1, 1)),
    ]
    fm = _field_map(items)
    assert list(fm.keys()) == ["head", "part_2"]


def test_field_map_tier2_match_takes_precedence_over_tier3():
    """An IrCharClass matching the Tier 2 library uses the library name."""
    from lexic.ir.derive import _field_map
    from lexic.ir.nodes import IrCharClass, IrItem, Quantifier

    items = [IrItem(IrCharClass("0-9"), Quantifier(1, None))]
    fm = _field_map(items)
    assert list(fm.keys()) == ["digits"]


def test_field_map_mixed_tier2_and_tier3():
    """A Tier-2 hit + Tier-3 fallback in the same rule."""
    from lexic.ir.derive import _field_map
    from lexic.ir.nodes import IrCharClass, IrItem, Quantifier

    items = [
        IrItem(IrCharClass("0-9"), Quantifier(1, None)),       # → 'digits'
        IrItem(IrCharClass("xyz_unmatched"), Quantifier(1, 1)),  # → 'head' (first Tier-3 pattern)
    ]
    fm = _field_map(items)
    assert list(fm.keys()) == ["digits", "head"]


def test_field_map_irgroup_with_ruleref_named_kind():
    """IrGroup containing rulerefs (inline alternation) → 'kind' (was 'value')."""
    from lexic.ir.derive import _field_map
    from lexic.ir.nodes import (
        IrAlternation, IrGroup, IrItem, IrRuleRef, IrSequence, Quantifier,
    )

    grp = IrGroup(IrAlternation((
        IrSequence((IrItem(IrRuleRef("a")),)),
        IrSequence((IrItem(IrRuleRef("b")),)),
    )))
    items = [IrItem(grp, Quantifier(1, 1))]
    fm = _field_map(items)
    assert list(fm.keys()) == ["kind"]


def test_field_map_ruleref_unchanged_uses_rule_name():
    """Tier 3 does NOT change ruleref naming. Field name stays the rule name."""
    from lexic.ir.derive import _field_map
    from lexic.ir.nodes import IrItem, IrRuleRef, Quantifier

    items = [IrItem(IrRuleRef("expr"), Quantifier(1, 1))]
    fm = _field_map(items)
    assert list(fm.keys()) == ["expr"]
```

Update `tests/unit/lexic/ir/test_naming.py` — replace the existing `nbkqr` assertion at line 26 with a Tier-3 assertion:

```python
def test_pattern_field_falls_back_to_positional_not_sanitized():
    """A non-Tier-2 pattern produces a positional Tier-3 name, not _sanitize_pattern output."""
    from lexic.ir.derive import _field_map
    from lexic.ir.nodes import IrCharClass, IrItem, Quantifier

    items = [IrItem(IrCharClass("NBKQR"), Quantifier(1, 1))]
    fm = _field_map(items)
    # Tier 3: first pattern field → 'head' (not 'nbkqr')
    assert list(fm.keys()) == ["head"]
    assert "nbkqr" not in fm
```

(Delete the original `test_charclass_field_name_NBKQR` test or whichever asserts `nbkqr` — it's replaced by the test above.)

- [ ] **Step 3: Run — expect failures.**

```bash
uv run pytest tests/unit/lexic/ir/test_derive.py tests/unit/lexic/ir/test_naming.py -q
```

- [ ] **Step 4: Update `src/lexic/ir/derive.py::_field_map`.** Replace with a position-aware version:

```python
def _field_map(items: Sequence[IrItem]) -> dict[str, int]:
    """Map atoms to field names.

    Naming cascade:
      Tier 2 (pattern library): _CHARCLASS_NAMES / _LITERAL_NAMES lookup.
      Tier 3 (structural positional): for IrCharClass without a Tier-2 hit,
        first pattern field → 'head', subsequent → 'part_2', 'part_3', …
        For IrGroup containing rulerefs, the field is named 'kind'.
      Rule-ref fields keep the rule name.
      Pure-pattern groups (IrGroup with no rulerefs) fall through Tier 2 +
        Tier 3 via _group_hint.
    """
    result: dict[str, int] = {}
    counts: defaultdict[str, int] = defaultdict(int)
    pattern_position = 0  # counts Tier-3 pattern fields for head/part_N
    for i, item in enumerate(items):
        if isinstance(item.atom, IrLiteral) and item.quantifier == Quantifier(1, 1):
            continue
        atom = item.atom
        if isinstance(atom, IrCharClass):
            tier2 = _CHARCLASS_NAMES.get(_bracketed(atom))
            if tier2:
                base = tier2
            else:
                pattern_position += 1
                base = "head" if pattern_position == 1 else f"part_{pattern_position}"
        elif isinstance(atom, IrLiteral):
            base = _LITERAL_NAMES.get(atom.value) or _ascii_token(atom.value) or "lit"
        elif isinstance(atom, IrRuleRef):
            base = atom.name.replace("-", "_")
        elif isinstance(atom, IrGroup):
            if _has_ruleref(atom):
                base = "kind"
            else:
                # Pure pattern group: try Tier 2 hint via _group_hint;
                # fall back to a Tier-3 positional name.
                hint = _group_hint(atom)
                if hint and hint not in {"inline", "lit", "cc"}:
                    base = hint
                else:
                    pattern_position += 1
                    base = "head" if pattern_position == 1 else f"part_{pattern_position}"
        else:
            continue
        counts[base] += 1
        result[base if counts[base] == 1 else f"{base}{counts[base]}"] = i
    return result
```

Drop the `_ATOM_HINT` table at the top of the file (it's now inlined). Keep `_group_hint`, `_bracketed`, `_has_ruleref`, `_ascii_token` — they're still used.

If `_sanitize_pattern` is no longer imported from `lexic.ir.naming` after this change, drop the import from `derive.py`. (Don't yet drop the function from `naming.py` — Slice 4's `naming.py` slim does that.)

- [ ] **Step 5: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/ -q
```

If failures appear in other test files (because field names changed), update those assertions too. Specifically expect to fix `tests/integration/test_codegen.py:256-262` (chess assertions) — the new field names will be Tier-3 positional. The chess `[a-h]` doesn't match Tier 2 (it's a single char range, not in the library); chess `[1-8]` likewise. So `Pawn` fields become `head` (`[a-h]`), `part_2` (`[1-8]`), `part_3` (the inline-regex group), etc. Read what `_field_map` actually produces and update the assertions:

```bash
uv run pytest tests/integration/test_codegen.py -q -x
```

Adjust assertions to match the actual names from `_field_map`. The assertions become e.g.:

```python
# Was:    assert "a_h_x" in Pawn.model_fields
# Becomes: assert "head" in Pawn.model_fields  (or whichever Tier-3 name applies)
```

If chess `[a-h]` should be Tier 2 (proposal hints `lower` for `[a-z]`), and the test expects a positional name, that's the answer. Read the actual output and assert accordingly — the spec's success criterion is "no `a_h_x`", not a specific positional name.

- [ ] **Step 6: Run full suite + ruff + commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/ir/derive.py src/lexic/ir/naming.py tests/
git commit -m "feat(naming): Tier 3 positional fallback (head/part_N) replacing _sanitize_pattern"
```

---

## Task 8: `new_codegen/aliases.py` — pattern alias collection

**Why this task:** Walk a list of `RuleSpec`s, collect every unique `IrCharClass` pattern (with quantifier and negation) plus every pure-pattern `IrGroup` regex, name each one via the naming pipeline, return a dict for the emitter.

**Files:**
- Create: `src/lexic/new_codegen/__init__.py` (skeleton; entry point comes in Task 14)
- Create: `src/lexic/new_codegen/aliases.py`
- Create: `tests/unit/lexic/new_codegen/__init__.py`
- Create: `tests/unit/lexic/new_codegen/test_init_new_codegen.py`
- Create: `tests/unit/lexic/new_codegen/test_aliases.py`

- [ ] **Step 1: Write the failing tests.**

`tests/unit/lexic/new_codegen/test_init_new_codegen.py`:

```python
"""Sanity: new_codegen package importable."""
def test_imports():
    import lexic.new_codegen  # noqa: F401
```

`tests/unit/lexic/new_codegen/test_aliases.py`:

```python
"""Pattern alias collection — module-level alias names for IrCharClass / pure-pattern IrGroup."""
from __future__ import annotations

from lexic.ir.nodes import (
    IrAlternation, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrRuleRef, IrSequence, Quantifier,
)
from lexic.ir.spec import RuleSpec
from lexic.new_codegen.aliases import (
    PatternAlias, collect_aliases, regex_for_charclass, regex_for_group,
)


def _spec(name, kind, items, field_map=None):
    return RuleSpec(
        rule_name=name, class_name=name.title(), parent_class_name="GrammarModel",
        kind=kind, items=list(items), field_map=field_map or {},
    )


def test_regex_for_charclass_simple():
    cc = IrCharClass("0-9")
    assert regex_for_charclass(cc, Quantifier(1, None)) == r"^[0-9]+$"


def test_regex_for_charclass_negated():
    cc = IrCharClass('"', negated=True)
    assert regex_for_charclass(cc, Quantifier(1, 1)) == r'^[^"]$'


def test_regex_for_charclass_bounded_quantifier():
    cc = IrCharClass("0-9")
    assert regex_for_charclass(cc, Quantifier(0, 15)) == r"^[0-9]{0,15}$"


def test_regex_for_charclass_optional():
    cc = IrCharClass("a-z")
    assert regex_for_charclass(cc, Quantifier(0, 1)) == r"^[a-z]?$"


def test_regex_for_group_pure_pattern():
    """([a-h] 'x')? → ^([a-h]x)?$."""
    grp = IrGroup(IrAlternation((
        IrSequence((
            IrItem(IrCharClass("a-h"), Quantifier(1, 1)),
            IrItem(IrLiteral("x"), Quantifier(1, 1)),
        )),
    )))
    assert regex_for_group(grp, Quantifier(0, 1)) == r"^([a-h]x)?$"


def test_regex_for_group_alternation():
    """('foo' | 'bar')+ → ^(foo|bar)+$."""
    grp = IrGroup(IrAlternation((
        IrSequence((IrItem(IrLiteral("foo"), Quantifier(1, 1)),)),
        IrSequence((IrItem(IrLiteral("bar"), Quantifier(1, 1)),)),
    )))
    assert regex_for_group(grp, Quantifier(1, None)) == r"^(foo|bar)+$"


def test_collect_aliases_dedupes_identical_patterns():
    """Two rules with identical [0-9]+ pattern share one alias."""
    s1 = _spec("a", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    s2 = _spec("b", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    aliases = collect_aliases([s1, s2])
    assert len(aliases) == 1
    a = aliases[0]
    assert isinstance(a, PatternAlias)
    assert a.regex == r"^[0-9]+$"
    assert a.name == "Digits"  # Tier 2: _CHARCLASS_NAMES['[0-9]+'] == 'digits' → CamelCase


def test_collect_aliases_distinguishes_different_quantifiers():
    """[0-9] and [0-9]+ produce different aliases."""
    s = _spec("r", "sequence", [
        IrItem(IrCharClass("0-9"), Quantifier(1, 1)),
        IrItem(IrCharClass("0-9"), Quantifier(1, None)),
    ])
    aliases = collect_aliases([s])
    regexes = {a.regex for a in aliases}
    assert regexes == {r"^[0-9]$", r"^[0-9]+$"}


def test_collect_aliases_naming_via_tier_pipeline():
    """Tier 2 lookup → CamelCase; Tier 3 fallback → 'Pattern' / 'Pattern2'."""
    s = _spec("r", "sequence", [
        IrItem(IrCharClass("a-z"), Quantifier(1, None)),       # Tier 2 miss (lower is single char)
        IrItem(IrCharClass("0-9"), Quantifier(1, None)),       # Tier 2: digits → Digits
    ])
    aliases = collect_aliases([s])
    names = {a.name for a in aliases}
    assert "Digits" in names


def test_collect_aliases_empty_for_no_patterns():
    """A grammar with only literals + rulerefs has no pattern aliases."""
    s = _spec("r", "sequence", [
        IrItem(IrLiteral("hi"), Quantifier(1, 1)),
        IrItem(IrRuleRef("expr"), Quantifier(1, 1)),
    ])
    assert collect_aliases([s]) == []
```

- [ ] **Step 2: Run — expect failures.**

```bash
uv run pytest tests/unit/lexic/new_codegen/ -q
```

- [ ] **Step 3: Create `src/lexic/new_codegen/__init__.py`** (skeleton):

```python
"""new_codegen — IR → Pydantic Python source.

Target-shape codegen rebuilt from scratch during the parallel-track IR
cutover. Emits module-level type aliases, Annotated[str, StringConstraints]
for pattern fields, Literal[...] for pure-literal alternations, Tier 2/3
positional naming, and __grammar__ at module footer.

Renamed to lexic.codegen at cutover (Slice 4).
"""
```

- [ ] **Step 4: Create `src/lexic/new_codegen/aliases.py`.**

```python
"""Pattern-alias collection: walk specs, collect unique pattern regexes.

A "pattern" here is either an IrCharClass with a quantifier or a pure-pattern
IrGroup (no IrRuleRef descendants). Each unique regex produces one PatternAlias
that the emitter renders as a module-level type alias.

Naming flows through the IR-naming pipeline:
  - Tier 2: known patterns (`[0-9]+` → `Digits`)
  - Tier 3: positional fallback (`Pattern`, `Pattern2`)

Names are CamelCased for the alias (because they're type names).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from lexic.ir.naming import _CHARCLASS_NAMES
from lexic.ir.nodes import (
    IrAlternation, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrRuleRef, IrSequence, Quantifier,
)
from lexic.ir.spec import RuleSpec
from lexic.utils.quantifiers import bounds_to_quantifier


@dataclass(frozen=True)
class PatternAlias:
    name: str   # CamelCase Python identifier
    regex: str  # anchored regex, ready for StringConstraints(pattern=...)


def _bracket(pattern: str, negated: bool) -> str:
    return f"[{'^' if negated else ''}{pattern}]"


def _suffix(q: Quantifier) -> str:
    return bounds_to_quantifier(q.min, q.max)


def regex_for_charclass(cc: IrCharClass, q: Quantifier) -> str:
    """Anchored regex for an IrCharClass + Quantifier."""
    return f"^{_bracket(cc.pattern, cc.negated)}{_suffix(q)}$"


def _atom_regex_fragment(item: IrItem) -> str:
    """Inner regex fragment for any pattern atom (no anchors)."""
    atom = item.atom
    q = _suffix(item.quantifier)
    if isinstance(atom, IrLiteral):
        # Escape regex meta-chars in literals
        return re.escape(atom.value) + q
    if isinstance(atom, IrCharClass):
        return _bracket(atom.pattern, atom.negated) + q
    if isinstance(atom, IrGroup):
        return f"({_alt_regex_fragment(atom.body)}){q}"
    raise TypeError(f"Pattern fragment cannot include {type(atom).__name__}")


def _seq_regex_fragment(seq: IrSequence) -> str:
    return "".join(_atom_regex_fragment(it) for it in seq.items)


def _alt_regex_fragment(alt: IrAlternation) -> str:
    return "|".join(_seq_regex_fragment(s) for s in alt.arms)


def regex_for_group(grp: IrGroup, q: Quantifier) -> str:
    """Anchored regex for a pure-pattern IrGroup + outer Quantifier."""
    return f"^({_alt_regex_fragment(grp.body)}){_suffix(q)}$"


def _has_ruleref(atom) -> bool:
    if isinstance(atom, IrRuleRef):
        return True
    if isinstance(atom, IrGroup):
        return _alt_has_ruleref(atom.body)
    return False


def _seq_has_ruleref(seq: IrSequence) -> bool:
    return any(_has_ruleref(it.atom) for it in seq.items)


def _alt_has_ruleref(alt: IrAlternation) -> bool:
    return any(_seq_has_ruleref(s) for s in alt.arms)


def _camel(s: str) -> str:
    """snake_case → CamelCase for type alias names."""
    return "".join(p.capitalize() for p in s.split("_"))


def _name_for_charclass(cc: IrCharClass, q: Quantifier) -> str:
    bracketed = _bracket(cc.pattern, cc.negated) + _suffix(q)
    tier2 = _CHARCLASS_NAMES.get(bracketed)
    if tier2:
        return _camel(tier2)
    return ""  # Tier 3 fallback assigned by collect_aliases via positional counter


def _walk_items(spec: RuleSpec):
    """Yield (atom, quantifier) for every IrItem at any nesting depth."""
    for item in spec.items:
        if isinstance(item, IrAlternation):
            for arm in item.arms:
                yield from _walk_seq(arm)
        elif isinstance(item, IrItem):
            yield from _walk_item(item)


def _walk_item(item: IrItem):
    yield item.atom, item.quantifier
    if isinstance(item.atom, IrGroup):
        for arm in item.atom.body.arms:
            yield from _walk_seq(arm)


def _walk_seq(seq: IrSequence):
    for it in seq.items:
        yield from _walk_item(it)


def collect_aliases(specs: list[RuleSpec]) -> list[PatternAlias]:
    """Return one PatternAlias per unique pattern regex across all specs.

    Order is insertion order (first appearance wins for naming).
    """
    seen: dict[str, PatternAlias] = {}
    tier3_count = 0
    for spec in specs:
        for atom, q in _walk_items(spec):
            if isinstance(atom, IrCharClass):
                regex = regex_for_charclass(atom, q)
            elif isinstance(atom, IrGroup) and not _has_ruleref(atom):
                regex = regex_for_group(atom, q)
            else:
                continue
            if regex in seen:
                continue
            if isinstance(atom, IrCharClass):
                name = _name_for_charclass(atom, q)
            else:
                name = ""
            if not name:
                tier3_count += 1
                name = "Pattern" if tier3_count == 1 else f"Pattern{tier3_count}"
            seen[regex] = PatternAlias(name=name, regex=regex)
    return list(seen.values())
```

- [ ] **Step 5: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/new_codegen/ -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 6: Commit.**

```bash
git add src/lexic/new_codegen/ tests/unit/lexic/new_codegen/
git commit -m "feat(new_codegen): aliases — pattern collection with Tier 2/3 naming"
```

---

## Task 9: `new_codegen/model_emitter.py` skeleton — class-body emission

**Why this task:** Render specs to Python source — class headers, field declarations (with primitive types only — `str`, rule-class names, `Optional[X]`, `List[X]`), but no `__grammar__`, no aliases, no `Literal[...]`, no `Annotated`. The skeleton produces a module that imports cleanly. Subsequent tasks (10–13) layer on the target shape.

**Files:**
- Create: `src/lexic/new_codegen/model_emitter.py`
- Create: `tests/unit/lexic/new_codegen/test_model_emitter.py`

- [ ] **Step 1: Write the failing tests.**

`tests/unit/lexic/new_codegen/test_model_emitter.py`:

```python
"""Model emitter — class-body emission (skeleton)."""
from __future__ import annotations

from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrRuleRef, Quantifier
from lexic.ir.spec import RuleSpec
from lexic.new_codegen.model_emitter import emit_module_source


def _spec(name, kind, items, parent="GrammarModel", field_map=None):
    return RuleSpec(
        rule_name=name, class_name=name.title(), parent_class_name=parent,
        kind=kind, items=list(items), field_map=field_map or {},
    )


def test_emit_value_str_class_body():
    spec = _spec("digit", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([spec], stem="m")
    assert "class Digit(GrammarModel):" in src
    # Skeleton stage: pattern field emitted as plain `str`. Refined in Task 10.
    assert "value: str" in src


def test_emit_sequence_class_with_ruleref_field():
    inner = _spec("expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))])
    outer = _spec("root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0})
    src = emit_module_source([outer, inner], stem="m")
    assert "class Root(GrammarModel):" in src
    assert "expr: Expr" in src


def test_emit_optional_field_for_quantifier_0_1():
    inner = _spec("expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))])
    outer = _spec("r", "sequence", [IrItem(IrRuleRef("expr"), Quantifier(0, 1))], field_map={"expr": 0})
    src = emit_module_source([outer, inner], stem="m")
    assert "Optional[Expr]" in src or "Expr | None" in src


def test_emit_list_field_for_quantifier_unbounded():
    inner = _spec("expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))])
    outer = _spec("r", "sequence", [IrItem(IrRuleRef("expr"), Quantifier(1, None))], field_map={"expr": 0})
    src = emit_module_source([outer, inner], stem="m")
    assert "List[Expr]" in src


def test_emitted_module_has_canonical_imports():
    """Decision CQ #4: full IR-AST surface, fixed import block."""
    spec = _spec("r", "value_str", [IrItem(IrLiteral("x"))])
    src = emit_module_source([spec], stem="m")
    expected_lines = [
        "from lexic.base import GrammarModel",
        "from lexic.ir.spec import RuleSpec",
        "from lexic.ir.nodes import",
    ]
    for line in expected_lines:
        assert line in src, f"missing canonical import: {line}"


def test_no_fixme_in_emitted_source():
    """Decision CQ #1: never emit # FIXME placeholders."""
    from lexic.ir.nodes import IrAlternation, IrGroup, IrSequence

    grp = IrGroup(IrAlternation((
        IrSequence((IrItem(IrLiteral("a")),)),
        IrSequence((IrItem(IrLiteral("b")),)),
    )))
    spec = _spec("r", "value_str", [IrItem(grp, Quantifier(1, 1))])
    src = emit_module_source([spec], stem="m")
    assert "# FIXME" not in src
    assert "FIXME" not in src
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_model_emitter.py -q
```

- [ ] **Step 3: Create `src/lexic/new_codegen/model_emitter.py`** (skeleton):

```python
"""Model emitter — IrItem-shape RuleSpec → Python source string.

Target-shape commitments land incrementally:
  Task 9 (this task): class body skeleton + canonical imports + __grammar__ in class body.
  Task 10: Annotated[str, StringConstraints(...)] for pattern fields.
  Task 11: Literal[...] for pure-literal alternations.
  Task 12: Module-level type aliases hoisted from collect_aliases().
  Task 13: __grammar__ moved to module footer.

Decision CQ #1 (no # FIXME): _repr_iritem produces real Python for every shape.
Decision CQ #4 (fixed imports): emit a canonical import block always.
"""

from __future__ import annotations

from io import StringIO

from lexic.ir.nodes import (
    IrAlternation, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrRuleRef, IrSequence, Quantifier,
)
from lexic.ir.spec import RuleSpec

CANONICAL_IMPORTS = """\
from __future__ import annotations
from typing import ClassVar, List, Literal, Optional, Union

from pydantic import Field, StringConstraints
from typing_extensions import Annotated

from lexic.base import GrammarModel
from lexic.ir.nodes import (
    IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrRule, IrRuleRef, IrSequence, Quantifier,
)
from lexic.ir.spec import RuleSpec
"""


def _is_required(q: Quantifier) -> bool:
    return q.min == 1 and q.max == 1


def _is_optional(q: Quantifier) -> bool:
    return q.min == 0 and q.max == 1


def _field_type_skeleton(item: IrItem, specs_by_rule: dict[str, RuleSpec]) -> str:
    """Skeleton: pattern fields → str; rule refs → cls / Optional[cls] / List[cls]."""
    atom = item.atom
    q = item.quantifier
    if isinstance(atom, (IrLiteral, IrCharClass)):
        return "str"
    if isinstance(atom, IrRuleRef):
        ref = specs_by_rule.get(atom.name)
        cls = ref.class_name if ref else atom.name.replace("-", "_").title()
        if _is_required(q):
            return cls
        if _is_optional(q):
            return f"Optional[{cls}]"
        return f"List[{cls}]"
    if isinstance(atom, IrGroup):
        # Skeleton stage: treat IrGroup as 'str' if no rulerefs, otherwise Union of arm refs.
        arm_refs = []
        for arm in atom.body.arms:
            if len(arm.items) == 1 and isinstance(arm.items[0].atom, IrRuleRef):
                arm_refs.append(arm.items[0].atom.name)
        if arm_refs:
            cls_names = [
                specs_by_rule[n].class_name for n in arm_refs if n in specs_by_rule
            ] or [n.replace("-", "_").title() for n in arm_refs]
            return f"Union[{', '.join(cls_names)}]"
        return "str"
    return "str"


def _repr_quantifier(q: Quantifier) -> str:
    return f"Quantifier({q.min}, {q.max!r})"


def _repr_atom_value(atom) -> str:
    if isinstance(atom, IrLiteral):
        return f"IrLiteral({atom.value!r})"
    if isinstance(atom, IrCharClass):
        return f"IrCharClass({atom.pattern!r}, negated={atom.negated})"
    if isinstance(atom, IrRuleRef):
        return f"IrRuleRef({atom.name!r})"
    if isinstance(atom, IrGroup):
        return f"IrGroup({_repr_alternation(atom.body)})"
    raise TypeError(f"Cannot serialise atom: {type(atom).__name__}")


def _repr_alternation(alt: IrAlternation) -> str:
    if not alt.arms:
        return "IrAlternation(arms=())"
    arms = ", ".join(_repr_sequence(s) for s in alt.arms)
    return f"IrAlternation(arms=({arms},))"


def _repr_sequence(seq: IrSequence) -> str:
    if not seq.items:
        return "IrSequence(items=())"
    items = ", ".join(_repr_iritem(it) for it in seq.items)
    return f"IrSequence(items=({items},))"


def _repr_iritem(item: IrItem) -> str:
    return f"IrItem({_repr_atom_value(item.atom)}, {_repr_quantifier(item.quantifier)})"


def _repr_items(spec: RuleSpec) -> str:
    parts = []
    for item in spec.items:
        if isinstance(item, IrAlternation):
            parts.append(_repr_alternation(item))
        elif isinstance(item, IrItem):
            parts.append(_repr_iritem(item))
        else:
            raise TypeError(f"Unsupported items entry: {type(item).__name__}")
    return "[" + ", ".join(parts) + "]"


def _repr_field_map(spec: RuleSpec) -> str:
    items = ", ".join(f"{k!r}: {v}" for k, v in spec.field_map.items())
    return "{" + items + "}"


def _repr_rulespec(spec: RuleSpec) -> str:
    return (
        f"RuleSpec(\n"
        f"    rule_name={spec.rule_name!r},\n"
        f"    class_name={spec.class_name!r},\n"
        f"    parent_class_name={spec.parent_class_name!r},\n"
        f"    kind={spec.kind!r},\n"
        f"    items={_repr_items(spec)},\n"
        f"    field_map={_repr_field_map(spec)},\n"
        f"    non_semantic_fields=frozenset({sorted(spec.non_semantic_fields)!r}),\n"
        f")"
    )


def _emit_class(
    spec: RuleSpec, specs_by_rule: dict[str, RuleSpec], out: StringIO
) -> None:
    out.write(f"\n\nclass {spec.class_name}({spec.parent_class_name}):\n")
    inv = {idx: name for name, idx in spec.field_map.items()}
    body_lines: list[str] = []
    body_lines.append(f"    __grammar__: ClassVar[RuleSpec] = {_repr_rulespec(spec)}")
    if spec.kind == "value_str":
        body_lines.append("    value: str")
    elif spec.kind == "alternation":
        # Abstract base — no fields
        pass
    else:  # sequence
        for idx, item in enumerate(spec.items):
            if not isinstance(item, IrItem):
                continue
            if idx not in inv:
                continue
            name = inv[idx]
            ftype = _field_type_skeleton(item, specs_by_rule)
            body_lines.append(f"    {name}: {ftype}")
    if not body_lines or all(line.startswith("    __grammar__") for line in body_lines):
        body_lines.append("    pass")
    for line in body_lines:
        out.write(line + "\n")


def emit_module_source(specs: list[RuleSpec], *, stem: str) -> str:
    """Render specs to a Python module source string."""
    specs_by_rule = {s.rule_name: s for s in specs}
    out = StringIO()
    out.write(f'"""Generated module: {stem}. Do not edit; regenerated from grammar."""\n')
    out.write(CANONICAL_IMPORTS)
    for spec in specs:
        _emit_class(spec, specs_by_rule, out)
    return out.getvalue()
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_model_emitter.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 5: Commit.**

```bash
git add src/lexic/new_codegen/model_emitter.py tests/unit/lexic/new_codegen/test_model_emitter.py
git commit -m "feat(new_codegen): model_emitter skeleton — class bodies + canonical imports"
```

---

## Task 10: S2.2 — `Annotated[str, StringConstraints(...)]` for pattern fields

**Why this task:** Replace `field: str` with the constrained type for `IrCharClass` and pure-pattern `IrGroup`. Direct inline emission for now (module-level aliases land in Task 12).

**Files:**
- Modify: `src/lexic/new_codegen/model_emitter.py`
- Modify: `tests/unit/lexic/new_codegen/test_model_emitter.py`

- [ ] **Step 1: Add tests.**

Append to `tests/unit/lexic/new_codegen/test_model_emitter.py`:

```python
def test_charclass_field_emits_annotated_string_constraints():
    spec = _spec("d", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([spec], stem="m")
    assert 'Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]' in src


def test_negated_charclass_field_inverts_pattern():
    spec = _spec("nq", "value_str", [IrItem(IrCharClass('"', negated=True))])
    src = emit_module_source([spec], stem="m")
    assert r'Annotated[str, StringConstraints(pattern=r"^[^\"]$")]' in src


def test_pure_pattern_group_field_composes_regex():
    """([a-h] 'x')? → ^([a-h]x)?$ as field type."""
    from lexic.ir.nodes import IrAlternation, IrGroup, IrSequence

    grp = IrGroup(IrAlternation((
        IrSequence((
            IrItem(IrCharClass("a-h"), Quantifier(1, 1)),
            IrItem(IrLiteral("x"), Quantifier(1, 1)),
        )),
    )))
    spec = _spec("p", "sequence", [IrItem(grp, Quantifier(0, 1))], field_map={"head": 0})
    src = emit_module_source([spec], stem="m")
    assert 'Annotated[str, StringConstraints(pattern=r"^([a-h]x)?$")]' in src
```

- [ ] **Step 2: Run — expect failures.**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_model_emitter.py -q
```

- [ ] **Step 3: Update `_field_type_skeleton`** in `model_emitter.py` to dispatch on pattern shapes:

```python
from lexic.new_codegen.aliases import (
    _has_ruleref, regex_for_charclass, regex_for_group,
)


def _field_type(item: IrItem, specs_by_rule: dict[str, RuleSpec]) -> str:
    atom = item.atom
    q = item.quantifier
    if isinstance(atom, IrCharClass):
        regex = regex_for_charclass(atom, q)
        return f'Annotated[str, StringConstraints(pattern=r"{regex}")]'
    if isinstance(atom, IrGroup) and not _has_ruleref(atom):
        regex = regex_for_group(atom, q)
        return f'Annotated[str, StringConstraints(pattern=r"{regex}")]'
    if isinstance(atom, IrLiteral):
        return "str"
    if isinstance(atom, IrRuleRef):
        ref = specs_by_rule.get(atom.name)
        cls = ref.class_name if ref else atom.name.replace("-", "_").title()
        if _is_required(q):
            return cls
        if _is_optional(q):
            return f"Optional[{cls}]"
        return f"List[{cls}]"
    if isinstance(atom, IrGroup):  # has rulerefs
        arm_refs = []
        for arm in atom.body.arms:
            if len(arm.items) == 1 and isinstance(arm.items[0].atom, IrRuleRef):
                arm_refs.append(arm.items[0].atom.name)
        if arm_refs:
            cls_names = [
                specs_by_rule[n].class_name for n in arm_refs if n in specs_by_rule
            ] or [n.replace("-", "_").title() for n in arm_refs]
            return f"Union[{', '.join(cls_names)}]"
        return "str"
    return "str"
```

Replace the call site in `_emit_class` from `_field_type_skeleton(item, specs_by_rule)` to `_field_type(item, specs_by_rule)`. Delete `_field_type_skeleton`.

The `value_str` branch in `_emit_class` also needs updating: `value: str` becomes the constrained type when items[0] is a single pattern atom. Update:

```python
    if spec.kind == "value_str":
        # If items is a single pattern IrItem, emit the constrained type.
        if (
            len(spec.items) == 1
            and isinstance(spec.items[0], IrItem)
            and isinstance(spec.items[0].atom, (IrCharClass, IrGroup))
        ):
            ftype = _field_type(spec.items[0], specs_by_rule)
            body_lines.append(f"    value: {ftype}")
        else:
            body_lines.append("    value: str")
```

- [ ] **Step 4: Update Task 9's transitional assertion.** Task 9's `test_emit_value_str_class_body` asserts `"value: str" in src` for an IrCharClass-fielded value_str rule; that assertion was explicitly marked "Skeleton stage: refined in Task 10." Update the test:

```python
def test_emit_value_str_class_body():
    spec = _spec("digit", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([spec], stem="m")
    assert "class Digit(GrammarModel):" in src
    assert 'value: Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]' in src
```

- [ ] **Step 5: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_model_emitter.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 6: Commit.**

```bash
git add src/lexic/new_codegen/model_emitter.py tests/unit/lexic/new_codegen/test_model_emitter.py
git commit -m "feat(new_codegen): S2.2 — Annotated[str, StringConstraints] for pattern fields"
```

---

## Task 11: S2.3 — `Literal[...]` for pure-literal alternations

**Why this task:** Detect `kind="value_str"` rules whose `items[0]` is a bare `IrAlternation` with every arm being a single `IrLiteral` and emit `Literal["a", "b", ...]` instead of `value: str`.

**Files:**
- Modify: `src/lexic/new_codegen/model_emitter.py`
- Modify: `tests/unit/lexic/new_codegen/test_model_emitter.py`

- [ ] **Step 1: Add tests.**

```python
def test_pure_literal_alternation_emits_literal_type():
    from lexic.ir.nodes import IrAlternation, IrSequence
    alt = IrAlternation((
        IrSequence((IrItem(IrLiteral("int"), Quantifier(1, 1)),)),
        IrSequence((IrItem(IrLiteral("float"), Quantifier(1, 1)),)),
        IrSequence((IrItem(IrLiteral("char"), Quantifier(1, 1)),)),
    ))
    spec = _spec("ty", "value_str", [alt])
    src = emit_module_source([spec], stem="m")
    assert 'value: Literal["int", "float", "char"]' in src


def test_mixed_alternation_does_not_emit_literal():
    """Arms mixing literal + ruleref keep the helper-class shape (no Literal)."""
    from lexic.ir.nodes import IrAlternation, IrSequence
    alt = IrAlternation((
        IrSequence((IrItem(IrLiteral("int"), Quantifier(1, 1)),)),
        IrSequence((IrItem(IrRuleRef("typename"), Quantifier(1, 1)),)),
    ))
    spec = _spec("t", "value_str", [alt])
    src = emit_module_source([spec], stem="m")
    assert "Literal[" not in src.split("class T")[1].split("\n\n")[0]


def test_quantified_literal_arm_does_not_emit_literal():
    """An arm with a quantified literal (min!=max!=1) is not a pure-literal."""
    from lexic.ir.nodes import IrAlternation, IrSequence
    alt = IrAlternation((
        IrSequence((IrItem(IrLiteral("a"), Quantifier(1, 1)),)),
        IrSequence((IrItem(IrLiteral("b"), Quantifier(0, 1)),)),  # quantified
    ))
    spec = _spec("t", "value_str", [alt])
    src = emit_module_source([spec], stem="m")
    assert "Literal[" not in src.split("class T")[1].split("\n\n")[0]
```

- [ ] **Step 2: Run — expect failures.**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_model_emitter.py -q
```

- [ ] **Step 3: Add detection helper + emission branch in `model_emitter.py`.**

```python
def _is_pure_literal_alternation(alt: IrAlternation) -> bool:
    """Every arm is exactly one IrLiteral with quantifier (1, 1)."""
    for arm in alt.arms:
        if len(arm.items) != 1:
            return False
        item = arm.items[0]
        if not isinstance(item, IrItem):
            return False
        if not isinstance(item.atom, IrLiteral):
            return False
        if item.quantifier != Quantifier(1, 1):
            return False
    return True


def _emit_literal_alternation(alt: IrAlternation) -> str:
    values = ", ".join(repr(arm.items[0].atom.value) for arm in alt.arms)
    return f"Literal[{values}]"
```

In `_emit_class`, update the `value_str` branch to check for the literal-alternation case first:

```python
    if spec.kind == "value_str":
        if (
            len(spec.items) == 1
            and isinstance(spec.items[0], IrAlternation)
            and _is_pure_literal_alternation(spec.items[0])
        ):
            ltype = _emit_literal_alternation(spec.items[0])
            body_lines.append(f"    value: {ltype}")
        elif (
            len(spec.items) == 1
            and isinstance(spec.items[0], IrItem)
            and isinstance(spec.items[0].atom, (IrCharClass, IrGroup))
        ):
            ftype = _field_type(spec.items[0], specs_by_rule)
            body_lines.append(f"    value: {ftype}")
        else:
            body_lines.append("    value: str")
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_model_emitter.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 5: Commit.**

```bash
git add src/lexic/new_codegen/model_emitter.py tests/unit/lexic/new_codegen/test_model_emitter.py
git commit -m "feat(new_codegen): S2.3 — Literal[...] for pure-literal alternations"
```

---

## Task 12: S2.1 — module-level type aliases

**Why this task:** Hoist pattern types out of inline `Annotated[...]` repetitions into named module-level aliases. Repeated patterns share an alias.

**Files:**
- Modify: `src/lexic/new_codegen/model_emitter.py`
- Modify: `tests/unit/lexic/new_codegen/test_model_emitter.py`

- [ ] **Step 1: Add tests.**

```python
def test_module_emits_pattern_aliases_at_top():
    """Patterns get module-level aliases; field types reference the alias."""
    spec = _spec("d", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([spec], stem="m")
    # Tier 2 hit: [0-9]+ → 'digits' → CamelCase 'Digits'
    assert 'Digits = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]' in src
    # Field type uses the alias, not the inline form
    assert "value: Digits" in src
    # The inline form should NOT appear in the class body section
    class_section = src.split("class D(")[1] if "class D(" in src else ""
    assert "Annotated[" not in class_section.split("\n\n")[0]


def test_repeated_pattern_shares_one_alias():
    """Two rules with [0-9]+ produce one alias."""
    s1 = _spec("a", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    s2 = _spec("b", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([s1, s2], stem="m")
    # One alias declaration
    assert src.count("Digits = Annotated[") == 1
    # Both classes reference Digits
    assert "value: Digits" in src
```

- [ ] **Step 2: Run — expect failures.**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_model_emitter.py -q
```

- [ ] **Step 3: Update `emit_module_source`** to use `collect_aliases` + a regex→alias map:

```python
from lexic.new_codegen.aliases import collect_aliases


def emit_module_source(specs: list[RuleSpec], *, stem: str) -> str:
    specs_by_rule = {s.rule_name: s for s in specs}
    aliases = collect_aliases(specs)
    regex_to_alias = {a.regex: a.name for a in aliases}

    out = StringIO()
    out.write(f'"""Generated module: {stem}. Do not edit; regenerated from grammar."""\n')
    out.write(CANONICAL_IMPORTS)

    if aliases:
        out.write("\n\n# ── Pattern aliases ──────────────────────────────────────────\n")
        for a in aliases:
            out.write(f'{a.name} = Annotated[str, StringConstraints(pattern=r"{a.regex}")]\n')

    for spec in specs:
        _emit_class(spec, specs_by_rule, regex_to_alias, out)
    return out.getvalue()
```

Update `_field_type` and `_emit_class` to take `regex_to_alias` and substitute the alias name when the regex matches:

```python
def _field_type(item: IrItem, specs_by_rule, regex_to_alias) -> str:
    atom = item.atom
    q = item.quantifier
    if isinstance(atom, IrCharClass):
        regex = regex_for_charclass(atom, q)
        return regex_to_alias.get(regex, f'Annotated[str, StringConstraints(pattern=r"{regex}")]')
    if isinstance(atom, IrGroup) and not _has_ruleref(atom):
        regex = regex_for_group(atom, q)
        return regex_to_alias.get(regex, f'Annotated[str, StringConstraints(pattern=r"{regex}")]')
    # … rest unchanged
```

Update `_emit_class` to forward `regex_to_alias` to `_field_type`. Update the `value_str` pattern-field branch to also pass it.

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_model_emitter.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 5: Commit.**

```bash
git add src/lexic/new_codegen/model_emitter.py tests/unit/lexic/new_codegen/test_model_emitter.py
git commit -m "feat(new_codegen): S2.1 — module-level type aliases for patterns"
```

---

## Task 13: S2.5 — `__grammar__` to module footer

**Why this task:** Pull the `__grammar__: ClassVar[RuleSpec] = RuleSpec(...)` line out of class bodies and emit a footer block that registers each one. Class bodies become field-only.

**Files:**
- Modify: `src/lexic/new_codegen/model_emitter.py`
- Modify: `tests/unit/lexic/new_codegen/test_model_emitter.py`

- [ ] **Step 1: Add tests.**

```python
def test_class_body_has_no_grammar_assignment():
    """Class body contains only field declarations (and pass for empty)."""
    import ast
    spec = _spec("d", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([spec], stem="m")
    tree = ast.parse(src)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(classes) == 1
    # No __grammar__ assignment inside class body
    for stmt in classes[0].body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            assert stmt.target.id != "__grammar__", \
                "__grammar__ leaked into class body"


def test_module_footer_registers_grammar():
    """Footer block sets cls.__grammar__ for each class."""
    spec = _spec("d", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    src = emit_module_source([spec], stem="m")
    assert "D.__grammar__ = RuleSpec(" in src


def test_emitted_module_executes_and_grammar_attribute_present():
    """The emitted source runs and Foo.__grammar__ is reachable at runtime."""
    spec = _spec("d", "value_str", [IrItem(IrLiteral("x"))])
    src = emit_module_source([spec], stem="m")
    ns: dict = {}
    exec(compile(src, "<m>", "exec"), ns)
    cls = ns["D"]
    assert hasattr(cls, "__grammar__")
    assert cls.__grammar__.rule_name == "d"


def test_grammar_round_trip_through_exec():
    """exec the source, reconstruct __grammar__.items[0] == original IR."""
    grp_spec = _spec(
        "r", "sequence",
        [IrItem(IrCharClass("0-9"), Quantifier(1, None))],
        field_map={"digits": 0},
    )
    src = emit_module_source([grp_spec], stem="m")
    ns: dict = {}
    exec(compile(src, "<m>", "exec"), ns)
    item0 = ns["R"].__grammar__.items[0]
    assert item0.atom == IrCharClass("0-9")
    assert item0.quantifier == Quantifier(1, None)
```

- [ ] **Step 2: Run — expect failures.**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_model_emitter.py -q
```

- [ ] **Step 3: Update `_emit_class` to skip `__grammar__` and add a footer pass.**

```python
def _emit_class(
    spec: RuleSpec, specs_by_rule, regex_to_alias, out: StringIO
) -> None:
    out.write(f"\n\nclass {spec.class_name}({spec.parent_class_name}):\n")
    inv = {idx: name for name, idx in spec.field_map.items()}
    body_lines: list[str] = []
    if spec.kind == "value_str":
        if (
            len(spec.items) == 1
            and isinstance(spec.items[0], IrAlternation)
            and _is_pure_literal_alternation(spec.items[0])
        ):
            body_lines.append(f"    value: {_emit_literal_alternation(spec.items[0])}")
        elif (
            len(spec.items) == 1
            and isinstance(spec.items[0], IrItem)
            and isinstance(spec.items[0].atom, (IrCharClass, IrGroup))
        ):
            body_lines.append(f"    value: {_field_type(spec.items[0], specs_by_rule, regex_to_alias)}")
        else:
            body_lines.append("    value: str")
    elif spec.kind == "alternation":
        pass
    else:  # sequence
        for idx, item in enumerate(spec.items):
            if not isinstance(item, IrItem):
                continue
            if idx not in inv:
                continue
            body_lines.append(
                f"    {inv[idx]}: {_field_type(item, specs_by_rule, regex_to_alias)}"
            )
    if not body_lines:
        body_lines.append("    pass")
    for line in body_lines:
        out.write(line + "\n")


def _emit_grammar_registration(spec: RuleSpec, out: StringIO) -> None:
    out.write(f"\n{spec.class_name}.__grammar__ = {_repr_rulespec(spec)}\n")


def emit_module_source(specs: list[RuleSpec], *, stem: str) -> str:
    specs_by_rule = {s.rule_name: s for s in specs}
    aliases = collect_aliases(specs)
    regex_to_alias = {a.regex: a.name for a in aliases}

    out = StringIO()
    out.write(f'"""Generated module: {stem}. Do not edit; regenerated from grammar."""\n')
    out.write(CANONICAL_IMPORTS)

    if aliases:
        out.write("\n\n# ── Pattern aliases ──────────────────────────────────────────\n")
        for a in aliases:
            out.write(f'{a.name} = Annotated[str, StringConstraints(pattern=r"{a.regex}")]\n')

    for spec in specs:
        _emit_class(spec, specs_by_rule, regex_to_alias, out)

    out.write("\n\n# ── Grammar registration ─────────────────────────────────────\n")
    for spec in specs:
        _emit_grammar_registration(spec, out)

    return out.getvalue()
```

Verify the canonical imports already include `ClassVar` (they do). The class-body emission no longer references `ClassVar[RuleSpec]` since `__grammar__` lives at module footer; the import stays for any pre-existing user need but is harmless.

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_model_emitter.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 5: Commit.**

```bash
git add src/lexic/new_codegen/model_emitter.py tests/unit/lexic/new_codegen/test_model_emitter.py
git commit -m "feat(new_codegen): S2.5 — __grammar__ registration moved to module footer"
```

---

## Task 14: `new_codegen/__init__.py` — `codegen(specs, stem)` entry point

**Why this task:** Public surface: take specs + stem, emit module source, write `generated/<stem>.py`, import the module, return `dict[name, type]`.

**Files:**
- Modify: `src/lexic/new_codegen/__init__.py`
- Modify: `tests/unit/lexic/new_codegen/test_init_new_codegen.py`

- [ ] **Step 1: Add tests.**

```python
"""new_codegen public entry point."""
from __future__ import annotations

from pathlib import Path

from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrRuleRef, Quantifier
from lexic.ir.spec import RuleSpec
from lexic.new_codegen import codegen


def _spec(name, kind, items, field_map=None):
    return RuleSpec(
        rule_name=name, class_name=name.title(), parent_class_name="GrammarModel",
        kind=kind, items=list(items), field_map=field_map or {},
    )


def test_codegen_returns_dict_of_classes(tmp_path, monkeypatch):
    """codegen(specs, stem) writes generated/<stem>.py and returns the loaded class dict."""
    # Run with a sandbox `generated/` directory so we don't pollute the repo
    monkeypatch.chdir(tmp_path)
    Path("generated").mkdir()
    spec = _spec("greet", "value_str", [IrItem(IrLiteral("hi"))])
    classes = codegen([spec], stem="test_codegen_simple")
    assert "Greet" in classes
    assert classes["Greet"].__grammar__.rule_name == "greet"


def test_codegen_handles_rule_refs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("generated").mkdir()
    inner = _spec("expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))])
    outer = _spec("root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0})
    classes = codegen([outer, inner], stem="test_codegen_refs")
    assert "Root" in classes
    assert "Expr" in classes


def test_codegen_no_flavour_parameter():
    """Spec invariant: codegen does not take a flavour."""
    import inspect
    sig = inspect.signature(codegen)
    assert "flavour" not in sig.parameters
```

- [ ] **Step 2: Run — expect failures (codegen not exported).**

```bash
uv run pytest tests/unit/lexic/new_codegen/test_init_new_codegen.py -q
```

- [ ] **Step 3: Update `src/lexic/new_codegen/__init__.py`.**

```python
"""new_codegen — IR → Pydantic Python source.

Renamed to lexic.codegen at cutover (Slice 4).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from lexic.ir.spec import RuleSpec
from lexic.new_codegen.model_emitter import emit_module_source

__all__ = ["codegen", "emit_module_source"]


def _resolve_generated_dir() -> Path:
    """Locate the project's generated/ directory.

    Searches up from this file's location to the repo root, then drops down
    into generated/. Falls back to the cwd-relative `generated/` if the
    repo-root layout isn't found (test sandboxes use this fallback).
    """
    here = Path(__file__).resolve()
    # src/lexic/new_codegen/__init__.py → repo root four levels up
    candidate = here.parent.parent.parent.parent / "generated"
    if candidate.exists():
        return candidate
    # Fallback: cwd-relative
    cwd_candidate = Path.cwd() / "generated"
    cwd_candidate.mkdir(parents=True, exist_ok=True)
    return cwd_candidate


def codegen(specs: list[RuleSpec], stem: str) -> dict[str, type]:
    """Emit a Pydantic module from specs; return the dict of generated classes.

    Side effect: writes `generated/<stem>.py`. The file is regenerated on
    every call.
    """
    out_dir = _resolve_generated_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.py"
    out_path.write_text(emit_module_source(specs, stem=stem))

    module_name = f"generated.{stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, out_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load generated module from {out_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)

    return {
        s.class_name: getattr(mod, s.class_name)
        for s in specs
        if hasattr(mod, s.class_name)
    }
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/new_codegen/ -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 5: Commit.**

```bash
git add src/lexic/new_codegen/__init__.py tests/unit/lexic/new_codegen/test_init_new_codegen.py
git commit -m "feat(new_codegen): codegen(specs, stem) entry point — write + import"
```

End of Slice 2. `new_codegen` is self-contained; only its own tests exercise it.

---

# Slice 3 — `parsing/lark_builder.py` + `parsing/transformer/`

## Task 15: `parsing/lark_builder.py` — IrItem-only LarkBuilder + `build_lark`

**Why this task:** Translate a list of RuleSpecs into a Lark grammar string + start-rule + (later) a Transformer factory. The legacy lives at `codegen/lark_builder.py`. The new version dispatches on IrItem only — no name-string check on `"ws"`; non-semantic optionality flows from `RuleSpec.non_semantic_fields` and `IrItem.quantifier` (Decision CQ #2).

**Files:**
- Create: `src/lexic/parsing/lark_builder.py`
- Create: `tests/unit/lexic/parsing/test_lark_builder.py`

- [ ] **Step 1: Read the legacy `codegen/lark_builder.py`** to understand the contract:

```bash
cat src/lexic/codegen/lark_builder.py
```

Note the public surface: `LarkBuilder(specs)`, `build_grammar()` returning `(grammar_str, start_rule)`, `build_transformer(classes)` returning a Lark `Transformer`.

- [ ] **Step 2: Write the failing tests.**

`tests/unit/lexic/parsing/test_lark_builder.py`:

```python
"""parsing.lark_builder — IrItem-only Lark grammar generation."""
from __future__ import annotations

import lark

from lexic.ir.nodes import (
    IrAlternation, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrRuleRef, IrSequence, Quantifier,
)
from lexic.ir.spec import RuleSpec
from lexic.parsing.lark_builder import LarkBuilder, build_lark


def _spec(name, kind, items, field_map=None, parent="GrammarModel", non_semantic=()):
    return RuleSpec(
        rule_name=name, class_name=name.title(), parent_class_name=parent,
        kind=kind, items=list(items), field_map=field_map or {},
        non_semantic_fields=frozenset(non_semantic),
    )


def test_build_grammar_simple_literal():
    s = _spec("greet", "value_str", [IrItem(IrLiteral("hi"))])
    grammar, start = LarkBuilder([s]).build_grammar()
    assert start == "greet"
    parser = lark.Lark(grammar, parser="earley", start=start)
    assert parser.parse("hi") is not None


def test_build_grammar_charclass_quantified():
    s = _spec("d", "value_str", [IrItem(IrCharClass("0-9"), Quantifier(1, None))])
    grammar, start = LarkBuilder([s]).build_grammar()
    parser = lark.Lark(grammar, parser="earley", start=start)
    assert parser.parse("123") is not None


def test_build_grammar_ruleref():
    inner = _spec("expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))])
    outer = _spec("root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0})
    grammar, start = LarkBuilder([outer, inner]).build_grammar()
    parser = lark.Lark(grammar, parser="earley", start=start)
    assert parser.parse("abc") is not None


def test_build_grammar_alternation_kind():
    a = _spec("a", "value_str", [IrItem(IrLiteral("a"))])
    b = _spec("b", "value_str", [IrItem(IrLiteral("b"))])
    alt = _spec("either", "alternation", [IrItem(IrRuleRef("a")), IrItem(IrRuleRef("b"))])
    grammar, start = LarkBuilder([alt, a, b]).build_grammar()
    parser = lark.Lark(grammar, parser="earley", start=start)
    assert parser.parse("a") is not None
    assert parser.parse("b") is not None


def test_no_ws_string_check_in_source():
    """Decision CQ #2: lark_builder does not key on rule names like 'ws'."""
    src = (__file__).replace("tests/unit/lexic/parsing/test_lark_builder.py",
                             "src/lexic/parsing/lark_builder.py")
    from pathlib import Path
    content = Path(src).read_text()
    assert 'atom.name == "ws"' not in content
    assert "atom.name == 'ws'" not in content
    assert 'rule_name == "ws"' not in content


def test_build_lark_returns_parser_and_transformer_factory():
    """build_lark(specs, classes, start) returns (grammar_str, parser, transformer)."""
    inner = _spec("expr", "value_str", [IrItem(IrCharClass("a-z"), Quantifier(1, None))])
    outer = _spec("root", "sequence", [IrItem(IrRuleRef("expr"))], field_map={"expr": 0})
    classes = {}  # transformer construction uses these — supplied by codegen
    grammar_str, parser, transformer = build_lark([outer, inner], classes, "root")
    assert isinstance(grammar_str, str)
    assert isinstance(parser, lark.Lark)
    # transformer is a lark.Transformer instance
    assert isinstance(transformer, lark.Transformer)
```

- [ ] **Step 3: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/parsing/test_lark_builder.py -q
```

- [ ] **Step 4: Implement `src/lexic/parsing/lark_builder.py`.** Port the legacy `codegen/lark_builder.py` to IrItem-only dispatch. The structure stays similar (a `LarkBuilder` class + helpers + `build_lark` orchestrator), but every `isinstance(atom, LiteralAtom|CharClassAtom|...)` becomes `isinstance(atom, IrLiteral|IrCharClass|...)`.

```python
"""LarkBuilder — RuleSpec list (IrItem-shape) → Lark grammar + Transformer.

Replaces the legacy codegen/lark_builder.py at cutover (Slice 4).

Decision CQ #2: non-semantic optionality is driven by RuleSpec.non_semantic_fields
+ IrItem.quantifier. No `name == "ws"` hardcoding.
"""

from __future__ import annotations

import lark

from lexic.ir.nodes import (
    IrAlternation, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrRuleRef, IrSequence, Quantifier,
)
from lexic.ir.spec import RuleSpec
from lexic.utils.names import to_lark_name
from lexic.utils.quantifiers import bounds_to_quantifier


def _quant(q: Quantifier) -> str:
    return bounds_to_quantifier(q.min, q.max)


def _bracket(pattern: str, negated: bool) -> str:
    return f"[{'^' if negated else ''}{pattern}]"


def _atom_to_lark(item: IrItem) -> str:
    atom = item.atom
    q = _quant(item.quantifier)
    if isinstance(atom, IrLiteral):
        # Lark literal: "..."
        escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"{q}'
    if isinstance(atom, IrCharClass):
        return f"/{_bracket(atom.pattern, atom.negated)}/{q}"
    if isinstance(atom, IrRuleRef):
        return f"{to_lark_name(atom.name)}{q}"
    if isinstance(atom, IrGroup):
        body = " | ".join(_seq_to_lark(s) for s in atom.body.arms)
        return f"({body}){q}"
    raise TypeError(f"Unsupported IR atom for Lark emit: {type(atom).__name__}")


def _seq_to_lark(seq: IrSequence) -> str:
    return " ".join(_atom_to_lark(it) for it in seq.items)


class LarkBuilder:
    """Build a Lark grammar string + Transformer factory from RuleSpecs."""

    def __init__(self, specs: list[RuleSpec], *, start_rule: str | None = None) -> None:
        self.specs = specs
        self._start_rule = start_rule or (specs[0].rule_name if specs else "")

    def build_grammar(self) -> tuple[str, str]:
        lines = [self._emit_rule(s) for s in self.specs]
        return "\n".join(lines) + "\n", to_lark_name(self._start_rule)

    def _emit_rule(self, spec: RuleSpec) -> str:
        name = to_lark_name(spec.rule_name)
        body = self._emit_body(spec)
        return f"{name}: {body}"

    def _emit_body(self, spec: RuleSpec) -> str:
        if not spec.items:
            return '""'
        if spec.kind == "alternation":
            return " | ".join(
                to_lark_name(it.atom.name) for it in spec.items
                if isinstance(it, IrItem) and isinstance(it.atom, IrRuleRef)
            )
        first = spec.items[0]
        if isinstance(first, IrAlternation):
            return " | ".join(_seq_to_lark(s) for s in first.arms)
        return " ".join(_atom_to_lark(it) for it in spec.items if isinstance(it, IrItem))

    def build_transformer(self, classes: dict[str, type]) -> lark.Transformer:
        from lexic.parsing.transformer.build_transformer import build_transformer
        return build_transformer(self.specs, classes)


def build_lark(
    specs: list[RuleSpec], classes: dict[str, type], start_rule: str
) -> tuple[str, lark.Lark, lark.Transformer]:
    """One-call helper for compile.py: specs → (grammar_str, parser, transformer)."""
    builder = LarkBuilder(specs, start_rule=start_rule)
    grammar_str, start = builder.build_grammar()
    parser = lark.Lark(grammar_str, parser="earley", ambiguity="resolve", start=start)
    transformer = builder.build_transformer(classes)
    return grammar_str, parser, transformer
```

(`build_transformer` import is forward to Task 16; the test in Step 2 that exercises it depends on Task 16 landing. Mark that single test as `@pytest.mark.xfail(reason="awaiting Task 16")` or skip it for now and unskip in Task 16.)

Actually simpler: split the failing test out and gate it on Task 16. Leave the test in this file but mark it:

```python
import pytest

@pytest.mark.skip(reason="build_transformer lands in Task 16")
def test_build_lark_returns_parser_and_transformer_factory():
    ...
```

- [ ] **Step 5: Run — expect PASS for everything except the skipped test.**

```bash
uv run pytest tests/unit/lexic/parsing/test_lark_builder.py -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 6: Commit.**

```bash
git add src/lexic/parsing/lark_builder.py tests/unit/lexic/parsing/test_lark_builder.py
git commit -m "feat(parsing): lark_builder — IrItem-only grammar + transformer-factory"
```

---

## Task 16: `parsing/transformer/build_transformer.py` (IrItem-only)

**Why this task:** Generate a runtime `lark.Transformer` that turns Lark trees into Pydantic instances. IrItem-shape only.

**Files:**
- Create: `src/lexic/parsing/transformer/__init__.py`
- Create: `src/lexic/parsing/transformer/build_transformer.py`
- Create: `tests/unit/lexic/parsing/transformer/__init__.py`
- Create: `tests/unit/lexic/parsing/transformer/test_build_transformer.py`

- [ ] **Step 1: Read the legacy `codegen/transformer/build_transformer.py`.**

```bash
cat src/lexic/codegen/transformer/build_transformer.py
```

Note the contract: `build_transformer(specs, classes)` → `lark.Transformer`.

- [ ] **Step 2: Write the failing tests.**

`tests/unit/lexic/parsing/transformer/test_build_transformer.py`:

```python
"""build_transformer — IR specs + classes → Lark Transformer."""
from __future__ import annotations

import lark

from lexic.base import GrammarModel
from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrRuleRef, Quantifier
from lexic.ir.spec import RuleSpec
from lexic.parsing.lark_builder import LarkBuilder
from lexic.parsing.transformer.build_transformer import build_transformer


def _spec(name, kind, items, field_map=None, parent="GrammarModel"):
    return RuleSpec(
        rule_name=name, class_name=name.title(), parent_class_name=parent,
        kind=kind, items=list(items), field_map=field_map or {},
    )


def test_transformer_round_trip_value_str_literal():
    spec = _spec("greet", "value_str", [IrItem(IrLiteral("hi"))])
    builder = LarkBuilder([spec])
    grammar_str, start = builder.build_grammar()

    # Build a class for greet
    class Greet(GrammarModel):
        value: str = "hi"
    Greet.__grammar__ = spec
    classes = {"Greet": Greet}

    parser = lark.Lark(grammar_str, parser="earley", start=start)
    tree = parser.parse("hi")
    transformer = build_transformer([spec], classes)
    result = transformer.transform(tree)
    assert isinstance(result, Greet)
    assert result.value == "hi"


def test_transformer_round_trip_sequence():
    inner_spec = _spec("expr", "value_str",
                        [IrItem(IrCharClass("a-z"), Quantifier(1, None))])
    outer_spec = _spec("root", "sequence",
                        [IrItem(IrRuleRef("expr"))], field_map={"expr": 0})

    class Expr(GrammarModel):
        value: str
    Expr.__grammar__ = inner_spec

    class Root(GrammarModel):
        expr: Expr
    Root.__grammar__ = outer_spec

    classes = {"Expr": Expr, "Root": Root}
    builder = LarkBuilder([outer_spec, inner_spec])
    grammar_str, start = builder.build_grammar()
    parser = lark.Lark(grammar_str, parser="earley", start=start)
    tree = parser.parse("abc")
    transformer = build_transformer([outer_spec, inner_spec], classes)
    result = transformer.transform(tree)
    assert isinstance(result, Root)
    assert isinstance(result.expr, Expr)
    assert result.expr.value == "abc"
```

- [ ] **Step 3: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/parsing/transformer/ -q
```

- [ ] **Step 4: Create `src/lexic/parsing/transformer/__init__.py`** (empty docstring placeholder):

```python
"""parsing.transformer — Lark tree → Pydantic instance machinery."""
```

- [ ] **Step 5: Implement `src/lexic/parsing/transformer/build_transformer.py`** by porting the legacy `codegen/transformer/build_transformer.py` to IrItem-shape. Replace every legacy-atom isinstance check with the IR-AST equivalent. The shape of the returned Transformer is unchanged (one method per rule, returning a Pydantic instance built from the children).

(Adapt the legacy code: replace `LiteralAtom` → `IrLiteral`, `CharClassAtom` → `IrCharClass`, `RuleRefAtom` → `IrRuleRef`, `AlternationAtom`/`InlineAlternationAtom` → `IrGroup`/`IrAlternation`, `QuantifiedLiteralAtom` → `IrLiteral` + `Quantifier`, `InlineRegexAtom` → `IrGroup` (pure pattern). Use `Quantifier` from `lexic.ir.nodes`, not `min`/`max` attributes on atoms.)

- [ ] **Step 6: Update `parsing/lark_builder.py`** — un-skip the test that was gated:

```python
def test_build_lark_returns_parser_and_transformer_factory():  # remove the @pytest.mark.skip
    ...
```

- [ ] **Step 7: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/parsing/ -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 8: Commit.**

```bash
git add src/lexic/parsing/transformer/ tests/unit/lexic/parsing/
git commit -m "feat(parsing): transformer/build_transformer — IrItem-only Lark Transformer"
```

---

## Task 17: `parsing/transformer/builders.py` — IrItem-only field builders

**Why this task:** Per-atom field-construction strategies the transformer dispatches to. Mirrors the legacy `codegen/transformer/builders.py` over IrItem.

**Files:**
- Create: `src/lexic/parsing/transformer/builders.py`
- Create: `tests/unit/lexic/parsing/transformer/test_builders.py`
- Modify: `src/lexic/parsing/transformer/build_transformer.py` (route through `builders.py`)

- [ ] **Step 1: Read the legacy `codegen/transformer/builders.py`.**

```bash
cat src/lexic/codegen/transformer/builders.py
```

Note the dispatch table layout: `BUILDER_BY_ATOM: dict[type[Atom], FieldBuilder]`.

- [ ] **Step 2: Write the failing tests.**

`tests/unit/lexic/parsing/transformer/test_builders.py`:

```python
"""IR-atom field builders for the transformer."""
from __future__ import annotations

from lexic.ir.nodes import IrCharClass, IrItem, IrLiteral, IrRuleRef, Quantifier
from lexic.ir.spec import RuleSpec
from lexic.parsing.transformer.builders import BUILDER_BY_ATOM, FieldBuilder


def test_builder_table_covers_every_ir_atom():
    """Every concrete atom type has a registered builder."""
    expected = {IrLiteral, IrCharClass, IrRuleRef}
    # IrGroup is also expected
    from lexic.ir.nodes import IrGroup
    expected.add(IrGroup)
    assert set(BUILDER_BY_ATOM.keys()) == expected


def test_builder_protocol():
    """Each builder implements the FieldBuilder protocol."""
    for builder in BUILDER_BY_ATOM.values():
        assert callable(getattr(builder, "build", None))


# Add at minimum one round-trip test per atom type using a small spec + lark
# (use the same harness as test_build_transformer.py).
```

(Add per-atom round-trip tests modeled after Task 16's tests — one per IrLiteral, IrCharClass, IrRuleRef, IrGroup. Keep them small.)

- [ ] **Step 3: Run — expect failures.**

```bash
uv run pytest tests/unit/lexic/parsing/transformer/test_builders.py -q
```

- [ ] **Step 4: Implement `src/lexic/parsing/transformer/builders.py`.** Port the legacy structure. The protocol:

```python
"""Per-atom field builders used by the runtime Lark Transformer.

Each builder converts a Lark tree node (or token) for one atom into a value
suitable for a Pydantic field. Wrapper builders handle Optional/List
quantifier shapes around the underlying atom builder.
"""

from __future__ import annotations

from typing import Protocol

from lexic.ir.nodes import IrCharClass, IrGroup, IrLiteral, IrRuleRef


class FieldBuilder(Protocol):
    def build(self, ctx) -> object: ...


class LiteralSkipBuilder:
    def build(self, ctx) -> object:
        return ...   # legacy semantics: skipped (no field)


class CharClassFieldBuilder:
    def build(self, ctx) -> object:
        return ctx.value  # the raw matched substring


class RuleRefBuilder:
    def build(self, ctx) -> object:
        return ctx.value  # delegated to child class instance


class GroupBuilder:
    def build(self, ctx) -> object:
        return ctx.value  # depends on whether group is pattern or alternation


BUILDER_BY_ATOM: dict[type, FieldBuilder] = {
    IrLiteral: LiteralSkipBuilder(),
    IrCharClass: CharClassFieldBuilder(),
    IrRuleRef: RuleRefBuilder(),
    IrGroup: GroupBuilder(),
}
```

(The actual `ctx` shape and the build logic must match what `build_transformer.py` calls. Adapt the legacy contract.)

- [ ] **Step 5: Update `build_transformer.py`** to dispatch through `BUILDER_BY_ATOM` instead of inline isinstance branches.

- [ ] **Step 6: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/parsing/ -q
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 7: Commit.**

```bash
git add src/lexic/parsing/transformer/builders.py \
        src/lexic/parsing/transformer/build_transformer.py \
        tests/unit/lexic/parsing/transformer/test_builders.py
git commit -m "feat(parsing): transformer/builders — IR-atom dispatch table"
```

End of Slice 3. The new pipeline is fully built. `compile.py` still routes through legacy.

---

# Slice 4 — Cutover

## Task 18: Cutover — single landable commit

**Why this task:** The "one fell swoop." Switch `compile.py` to the new pipeline, delete legacy modules, rename `new_*` → final names, sed imports, tighten IR types.

**This task does NOT use TDD.** Each sub-step is mechanical. The full suite is run after each sub-step or at the end; if any step breaks tests, fix in place before continuing. The whole task lands as one commit.

**Files modified / deleted / created — see spec for the full list.**

- [ ] **Sub-step 1: Reroute `_compile_core` in `src/lexic/compile.py`.**

Open `src/lexic/compile.py`. Replace `_compile_core` body:

```python
def _compile_core(text: str, *, stem: str, flavour: str = "gbnf") -> CompiledGrammar:
    from lexic.compile import compile_grammar
    from lexic.grammars import get_flavour
    from lexic.codegen import codegen
    from lexic.parsing.lark_builder import build_lark

    flavour_cls = get_flavour(flavour)
    start_rule, specs_list = compile_grammar(text, flavour_cls)
    classes = codegen(specs_list, stem)
    grammar_str, parser, transformer = build_lark(specs_list, classes, start_rule)
    specs = {s.rule_name: s for s in specs_list}
    return CompiledGrammar(
        classes=classes, specs=specs, parser=parser, transformer=transformer
    )
```

(Note: this references `lexic.codegen` and `lexic.parsing.lark_builder`. After the renames in sub-step 4, both resolve. We do this edit *before* the rename so the diff is one cohesive change.)

`compile_grammar` already exists in this file. Leave it.

- [ ] **Sub-step 2: Registry consolidation in `src/lexic/grammars/__init__.py`.**

Replace contents:

```python
"""Grammar-flavour layer — public endpoint.

Registry keyed on the Flavour ABC. Built-in flavours (GBNF, ABNF) are
registered eagerly so callers get a fully populated registry on first import.
"""

from __future__ import annotations

from pathlib import Path

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.flavour import Flavour
from lexic.grammars.gbnf.flavour import GbnfFlavour
from lexic.grammars.abnf.flavour import AbnfFlavour

_FLAVOURS: dict[str, type[Flavour]] = {}


def register_flavour(flavour_cls: type[Flavour]) -> None:
    _FLAVOURS[flavour_cls.name] = flavour_cls


def get_flavour(name: str) -> type[Flavour]:
    try:
        return _FLAVOURS[name]
    except KeyError:
        raise UnsupportedConstructError(
            f"Unknown flavour: {name!r}. Supported: {sorted(_FLAVOURS)}"
        ) from None


def flavour_for_extension(path: str | Path) -> type[Flavour]:
    suffix = Path(path).suffix
    for fc in _FLAVOURS.values():
        if suffix in fc.extensions:
            return fc
    known = sorted({ext for fc in _FLAVOURS.values() for ext in fc.extensions})
    raise UnsupportedConstructError(
        f"No flavour for extension {suffix!r}. Supported: {known}"
    )


register_flavour(GbnfFlavour)
register_flavour(AbnfFlavour)


__all__ = ["Flavour", "register_flavour", "get_flavour", "flavour_for_extension"]
```

(Note the `from lexic.grammars.gbnf.flavour import GbnfFlavour` — this resolves *after* sub-step 4's rename. To make the edit atomic, the cutover commit must contain both this file AND the rename. Don't run tests between sub-steps 2 and 4; sub-step 5 is when the suite runs.)

If any other module currently imports from `lexic.grammars` looking for `register_adapter`, `get_adapter`, `adapter_for_extension`, `ADAPTERS`, `FlavourAdapter`, etc. — those callers must update to the new names. Sub-step 6 (sed) catches some of these; manual review handles the rest.

- [ ] **Sub-step 3: Delete legacy modules and their tests.**

```bash
git rm -r src/lexic/codegen
git rm -r src/lexic/grammars/gbnf
git rm src/lexic/grammars/flavours.py
git rm src/lexic/ir/atoms.py src/lexic/ir/builder.py
git rm src/lexic/ir/classify.py src/lexic/ir/convert.py

# tests cascade with src deletion (mirror principle)
git rm -r tests/unit/lexic/codegen
git rm -r tests/unit/lexic/grammars/gbnf
git rm tests/unit/lexic/ir/test_atoms.py
git rm tests/unit/lexic/ir/test_builder.py
git rm tests/unit/lexic/ir/test_classify.py
git rm tests/unit/lexic/ir/test_convert.py
```

- [ ] **Sub-step 4: Rename `new_*` directories.**

```bash
git mv src/lexic/new_codegen src/lexic/codegen
git mv src/lexic/grammars/new_gbnf src/lexic/grammars/gbnf
git mv tests/unit/lexic/new_codegen tests/unit/lexic/codegen
git mv tests/unit/lexic/grammars/new_gbnf tests/unit/lexic/grammars/gbnf
```

- [ ] **Sub-step 5: Sed import paths.**

```bash
find src tests -name '*.py' -print0 | xargs -0 sed -i \
    -e 's|lexic\.grammars\.new_gbnf|lexic.grammars.gbnf|g' \
    -e 's|lexic\.new_codegen|lexic.codegen|g'
```

- [ ] **Sub-step 6: Tighten `lexic/ir/spec.py`.**

```python
"""RuleSpec — canonical representation of one grammar rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lexic.ir.nodes import IrAlternation, IrItem


@dataclass
class RuleSpec:
    """Complete specification of one grammar rule."""

    rule_name: str
    class_name: str
    parent_class_name: str
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[IrItem | IrAlternation] = field(default_factory=list)
    field_map: dict[str, int] = field(default_factory=dict)
    non_semantic_fields: frozenset[str] = field(default_factory=frozenset)
```

Drop the `NewRuleSpec` separate class. Drop `from lexic.ir.atoms import Atom` and any `Atom` references.

If any caller imports `NewRuleSpec`, replace with `RuleSpec`. The sed in sub-step 5 doesn't catch this — manual sweep:

```bash
grep -rn "NewRuleSpec" src/ tests/
```

For each hit, change `NewRuleSpec` → `RuleSpec`.

- [ ] **Sub-step 7: Tighten `lexic/ir/emit.py`.**

Open `src/lexic/ir/emit.py`. Replace any handler dispatch over legacy atom types (`LiteralAtom`, `CharClassAtom`, etc.) with handlers over IR AST nodes (`IrLiteral`, `IrCharClass`, `IrRuleRef`, `IrGroup`). Drop legacy-atom imports.

- [ ] **Sub-step 8: Slim `lexic/ir/naming.py`.**

Keep `_CHARCLASS_NAMES`, `_LITERAL_NAMES`. Drop `_sanitize_pattern` (Tier 3 replaces it). Drop `assign_field_names`, `_charclass_field_name`, `_quantified_literal_field_name`, `_inline_regex_field_name`. The result should be a small data + lookup-helper module.

- [ ] **Sub-step 9: Tighten `lexic/ir/protocols.py`.**

Drop `RuleClassifier` and `SequenceConverter`. Update `__all__`.

- [ ] **Sub-step 10: Update `lexic/ir/__init__.py`.**

Drop legacy atom exports (`Atom`, `LiteralAtom`, `CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom`, `RuleRefAtom`, `AlternationAtom`, `InlineAlternationAtom`). Add IR AST exports:

```python
"""Lexic IR public surface."""

from lexic.ir.derive import (
    classify_kind, compute_parents, derive_specs, hoist_helpers,
)
from lexic.ir.directives import Directives, parse_directives
from lexic.ir.nodes import (
    IrAlternation, IrAst, IrCharClass, IrGroup, IrItem, IrLiteral,
    IrRule, IrRuleRef, IrSequence, Quantifier,
)
from lexic.ir.spec import RuleSpec
from lexic.ir.walk import IrTransformer, IrVisitor

__all__ = [
    "classify_kind", "compute_parents", "derive_specs", "hoist_helpers",
    "Directives", "parse_directives",
    "IrAlternation", "IrAst", "IrCharClass", "IrGroup", "IrItem", "IrLiteral",
    "IrRule", "IrRuleRef", "IrSequence", "Quantifier",
    "RuleSpec",
    "IrTransformer", "IrVisitor",
]
```

- [ ] **Sub-step 11: Tighten `src/lexic/base.py::to_text`.**

Replace the legacy-atom dispatch with IrItem-only. Drop `from lexic.grammars.gbnf.adapter import decode_gbnf_escapes` (literals are canonical from MetaGrammarParser; no GBNF-specific decoding at this layer). Drop `LiteralAtom`, `RuleRefAtom` imports; use `IrLiteral`, `IrRuleRef` from `lexic.ir.nodes`.

The `to_grammar(name)` edge calls `grammars.get_flavour(name).emitter` — ensure this is the new path, not via the deleted `flavours.py` registry.

- [ ] **Sub-step 12: Tighten `src/lexic/generate.py`.**

Replace legacy-atom dispatch with IrItem-only. Drop legacy-atom imports.

- [ ] **Sub-step 13: Tighten `src/lexic/grammars/flavour.py::Flavour.emitter`.**

```python
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from lexic.ir.emit import FlavourEmitter


class Flavour(ABC):
    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    meta_grammar: ClassVar[str]
    escapes: ClassVar[EscapeCodec]
    emitter: ClassVar["FlavourEmitter"]    # was: ClassVar[Any]
    line_comment: ClassVar[str] = ""
    # … rest unchanged
```

- [ ] **Sub-step 14: Clear stale generated/ artifacts and run the full suite + ruff. Iterate.**

`generated/` is git-ignored; on the test runner's filesystem, files from before the cutover may have legacy-atom content that fails to import after the legacy modules are deleted. Clear the cache so the first `compile()` call regenerates everything via the new pipeline.

```bash
rm -f generated/*.py
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected failures during cutover (some are mechanical; fix in place):

1. **Imports of legacy names.** `from lexic.grammars import get_adapter` → `get_flavour`. `from lexic.grammars.flavours import …` → from `lexic.grammars.flavour` (or replaced entirely). Search for residual references and update:

   ```bash
   grep -rn "get_adapter\|adapter_for_extension\|FlavourAdapter\|register_adapter\|ADAPTERS" src/ tests/
   ```

   Each hit is updated.

2. **Tests that hardcoded old field names.** Already addressed in Tasks 6–7; if any straggle, update.

3. **Generated module shape.** `tests/integration/test_codegen.py` and similar may assert on generated source layout. Update assertions to the new shape (aliases at top, `Annotated` types, footer registration).

Continue iterating until green.

- [ ] **Sub-step 15: Add layering-invariant integration test.**

Create `tests/integration/test_layering_invariants.py`:

```python
"""Layering invariants asserted via static grep over the source tree.

Per the spec § Layering rules and § Success criteria.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "lexic"


def _grep(directory: Path, needle: str) -> list[Path]:
    return [p for p in directory.rglob("*.py") if needle in p.read_text()]


def test_ir_does_not_import_grammars_parsing_codegen():
    bad = (
        _grep(SRC / "ir", "from lexic.grammars")
        + _grep(SRC / "ir", "from lexic.parsing")
        + _grep(SRC / "ir", "from lexic.codegen")
    )
    assert not bad, f"lexic.ir leaks: {bad}"


def test_codegen_does_not_import_grammars_or_parsing():
    bad = (
        _grep(SRC / "codegen", "from lexic.grammars")
        + _grep(SRC / "codegen", "from lexic.parsing")
    )
    assert not bad, f"lexic.codegen leaks: {bad}"


def test_parsing_imports_only_flavour_abc_from_grammars():
    parsing = SRC / "parsing"
    for p in parsing.rglob("*.py"):
        for line in p.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("from lexic.grammars", "import lexic.grammars")):
                assert "from lexic.grammars.flavour" in stripped, (
                    f"{p}: imports from lexic.grammars beyond the Flavour ABC: {stripped}"
                )


def test_no_flavours_module_anywhere():
    """grammars/flavours.py is gone; no imports of it anywhere."""
    assert not (SRC / "grammars" / "flavours.py").exists()
    bad = list(SRC.rglob("*.py"))
    for p in bad:
        content = p.read_text()
        assert "from lexic.grammars.flavours" not in content, f"{p} imports flavours"
        assert "import lexic.grammars.flavours" not in content, f"{p} imports flavours"


def test_no_legacy_atoms_anywhere():
    """ir.atoms, ir.builder, ir.classify, ir.convert are gone."""
    for name in ("atoms.py", "builder.py", "classify.py", "convert.py"):
        assert not (SRC / "ir" / name).exists(), f"ir/{name} still present"


def test_no_new_gbnf_or_new_codegen_residual():
    """new_* names from the parallel-track build are sed'd away."""
    for p in (SRC.rglob("*.py")):
        content = p.read_text()
        assert "lexic.grammars.new_gbnf" not in content, f"{p}: residual new_gbnf"
        assert "lexic.new_codegen" not in content, f"{p}: residual new_codegen"
    for p in (ROOT / "tests").rglob("*.py"):
        content = p.read_text()
        assert "lexic.grammars.new_gbnf" not in content, f"{p}: residual new_gbnf"
        assert "lexic.new_codegen" not in content, f"{p}: residual new_codegen"


def test_rulespec_items_typed_list_iritem():
    spec_py = SRC / "ir" / "spec.py"
    content = spec_py.read_text()
    assert "list[IrItem | IrAlternation]" in content or "list[IrItem]" in content
    assert "from lexic.ir.atoms import Atom" not in content
```

Run it:

```bash
uv run pytest tests/integration/test_layering_invariants.py -q
```

If any test fails, the cutover left a stray reference. Fix and re-run.

- [ ] **Sub-step 16: Final full-suite + ruff check.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Both must be green.

- [ ] **Sub-step 17: Commit (single commit covering all sub-steps).**

```bash
git add -A
git commit -m "refactor(ir): cutover — IR AST canonical pipeline replaces legacy IRBuilder

- compile.compile_text routes through compile_grammar + new_codegen + parsing.lark_builder.
- grammars.flavours removed; registry consolidated on the Flavour ABC.
- new_gbnf/ → grammars/gbnf/; new_codegen/ → codegen/. Sed updates imports.
- ir/atoms.py, ir/builder.py, ir/classify.py, ir/convert.py deleted.
- RuleSpec.items typed list[IrItem | IrAlternation]; NewRuleSpec collapsed.
- ir/protocols.py: RuleClassifier, SequenceConverter dropped.
- ir/naming.py slimmed to data + lookup helpers.
- Flavour.emitter typing tightened to ClassVar[FlavourEmitter].
- AbnfFlavour now registered alongside GbnfFlavour.
- tests/integration/test_layering_invariants.py asserts spec layering rules."
```

End of plan.

---

## Self-review checklist (run before handing off)

- [ ] Every spec section has a task. Tasks 1–5 cover Slice 1, 6–14 cover Slice 2, 15–17 cover Slice 3, 18 covers Slice 4.
- [ ] No `TBD`, `TODO`, `implement later` strings in the plan.
- [ ] No `Co-Authored-By` lines in commit templates.
- [ ] `__init__.py` test files use `test_init_<package>.py` (per memory note).
- [ ] No `# type: ignore` / `# noqa` directives anywhere.
- [ ] Each task ends with full-suite + ruff before commit.
- [ ] Type and method names used in later tasks match what earlier tasks define (e.g., `_field_type` in Task 10 onward, `collect_aliases` from Task 8 onward, `build_lark` from Task 15 onward).
- [ ] Cutover commit (Task 18) is single-commit-landable; sub-steps are mechanical.
