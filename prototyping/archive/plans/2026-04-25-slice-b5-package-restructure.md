# Slice B.5 — Package Restructure Implementation Plan (Rewrite)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the codebase into four flavour-agnostic packages (`ir/`, `codegen/`, `parsing/`, `runtime/`) plus thin per-flavour adapters under `grammars/`, with a canonical IR (no flavour text in atoms), generic `FlavourEmitter` and `EscapeCodec` ABCs that own emit/escape algorithms with default canonical-atom handlers, bracket-expression enumeration lifted into core (`ir/charclass.py`), an open atom set with adapter-bound consumer-handler tables, per-module `__adapter__` runtime binding, and the `"ws"` string special case removed at all five sites.

**Architecture:** See `docs/superpowers/specs/2026-04-25-slice-b5-package-restructure-design.md`. Key invariants:
- Canonical IR — `LiteralAtom.value` is canonical Python (escapes decoded); `CharClassAtom.pattern` is POSIX-style; `InlineRegexAtom.canonical: str` replaces the dual `regex`/`gbnf` fields; `RuleSpec.non_semantic_fields` carries the trivia-field set.
- Generic algorithms in `ir/` (`IRBuilder`, `classify_rule`, generic `convert`, `FlavourEmitter` ABC, `EscapeCodec` ABC, `parse_charclass_chars`); flavours supply only AST-shape queries (`RuleClassifier[Node]`, `SequenceConverter[Node]`), syntax constants, escape tables (via `EscapeCodec` subclass), and atom handler extensions.
- Per-consumer handler tables live in `<consumer>/handlers/` sub-packages (canonical defaults), merged with `adapter.<consumer>_handlers` (extensions) at construction time.
- The string `"ws"` survives at exactly one site: `IRBuilder(trivia_rules={"ws"})` default.

**Tech stack:** Python 3.12+, `uv run pytest`, `uv run ruff check`, `git mv`. All commands are exact.

**Supersedes:** `docs/superpowers/plans/2026-04-25-slice-b5-package-restructure_old.md` (v2 — moved files but kept algorithms in `grammars/gbnf/` and the IR flavour-shaped).

---

## File map

### Creates

- `src/lexic/ir/protocols.py` (rewrite — current draft is v2's; replace fully; `EscapeCodec` is now re-exported from `lexic.ir.escapes`, no longer declared here)
- `src/lexic/ir/helpers.py` (move-from-codegen target)
- `src/lexic/ir/topo.py`
- `src/lexic/ir/classify.py`
- `src/lexic/ir/convert.py`
- `src/lexic/ir/builder.py`
- `src/lexic/ir/emit.py` (`FlavourEmitter` ABC)
- `src/lexic/ir/escapes.py` (`EscapeCodec` ABC + `CANONICAL_ESCAPES` instance)
- `src/lexic/ir/charclass.py` (`parse_charclass_chars(inner, codec)`; codec defaults to `CANONICAL_ESCAPES`)
- `src/lexic/codegen/handlers/__init__.py`
- `src/lexic/codegen/handlers/atom_fields.py`
- `src/lexic/parsing/__init__.py`
- `src/lexic/parsing/lark_builder.py` (move-from-codegen target — slimmed)
- `src/lexic/parsing/transformer.py` (consolidates `codegen/transformer/build_transformer.py`)
- `src/lexic/parsing/transformer_builders.py` (was `codegen/transformer/builders.py`)
- `src/lexic/parsing/transformer_context.py` (was `codegen/transformer/context.py`)
- `src/lexic/parsing/handlers/__init__.py`
- `src/lexic/parsing/handlers/lark.py`
- `src/lexic/parsing/handlers/transform.py`
- `src/lexic/runtime/__init__.py`
- `src/lexic/runtime/base.py` (move-from `src/lexic/base.py`)
- `src/lexic/runtime/parse.py` (move-from `src/lexic/parse.py`)
- `src/lexic/runtime/generate.py` (move-from `src/lexic/generate.py`)
- `src/lexic/runtime/handlers/__init__.py`
- `src/lexic/runtime/handlers/to_text.py`
- `src/lexic/runtime/handlers/generate.py`
- `src/lexic/grammars/gbnf/ast_to_ir.py` (collapses `codegen/classify.py` + `codegen/seq_to_atoms.py` + `codegen/ast_utils.py` into one module of AST queries)
- `src/lexic/grammars/gbnf/emit.py` (slim `GbnfEmitter` extending `FlavourEmitter` ABC)
- `tests/unit/lexic/ir/test_helpers.py` (move from `tests/unit/lexic/codegen/test_helpers.py`)
- `tests/unit/lexic/ir/test_topo.py`
- `tests/unit/lexic/ir/test_classify.py`
- `tests/unit/lexic/ir/test_convert.py`
- `tests/unit/lexic/ir/test_builder.py`
- `tests/unit/lexic/ir/test_emit.py`
- `tests/unit/lexic/ir/test_escapes.py`
- `tests/unit/lexic/ir/test_charclass.py`
- `tests/unit/lexic/parsing/__init__.py`
- `tests/unit/lexic/parsing/test_lark_builder.py`
- `tests/unit/lexic/parsing/test_transformer.py`
- `tests/unit/lexic/parsing/test_transformer_builders.py`
- `tests/unit/lexic/parsing/test_transformer_context.py`
- `tests/unit/lexic/parsing/test_handlers_lark.py`
- `tests/unit/lexic/parsing/test_handlers_transform.py`
- `tests/unit/lexic/parsing/test_import_boundary.py`
- `tests/unit/lexic/runtime/__init__.py`
- `tests/unit/lexic/runtime/test_base.py` (move)
- `tests/unit/lexic/runtime/test_parse.py` (move)
- `tests/unit/lexic/runtime/test_generate.py` (move)
- `tests/unit/lexic/runtime/test_handlers_to_text.py`
- `tests/unit/lexic/runtime/test_handlers_generate.py`
- `tests/unit/lexic/codegen/handlers/test_atom_fields.py`
- `tests/unit/lexic/grammars/gbnf/test_ast_to_ir.py` (replaces `test_classify.py` + `test_seq_to_atoms.py` + `test_ast_utils.py`)
- `tests/unit/lexic/grammars/gbnf/test_emit.py` (replaces `test_emitter.py`)

### Moves (`git mv`)

Source moves are listed inline per task. All test mirror moves match. Notable:
- `src/lexic/base.py` → `src/lexic/runtime/base.py`
- `src/lexic/parse.py` → `src/lexic/runtime/parse.py`
- `src/lexic/generate.py` → `src/lexic/runtime/generate.py`
- `src/lexic/codegen/lark_builder.py` → `src/lexic/parsing/lark_builder.py`
- `src/lexic/codegen/transformer/build_transformer.py` → `src/lexic/parsing/transformer.py`
- `src/lexic/codegen/transformer/builders.py` → `src/lexic/parsing/transformer_builders.py`
- `src/lexic/codegen/transformer/context.py` → `src/lexic/parsing/transformer_context.py`
- `src/lexic/codegen/transformer/registry.py` → folded into `src/lexic/parsing/handlers/transform.py` (registry semantics replaced by handler-table dispatch)
- `src/lexic/codegen/helpers.py` → `src/lexic/ir/helpers.py`

### Deletes

- `src/lexic/codegen/ir_builder.py`
- `src/lexic/codegen/classify.py`
- `src/lexic/codegen/seq_to_atoms.py`
- `src/lexic/codegen/ast_utils.py`
- `src/lexic/codegen/transformer/__init__.py` (subpackage gone)
- `src/lexic/codegen/transformer/registry.py`
- `src/lexic/grammars/gbnf/escapes.py` (folded into `adapter.py` via `GbnfEscapes(EscapeCodec)`)
- `src/lexic/grammars/gbnf/charclass.py` (algorithm now in `lexic.ir.charclass`)
- `src/lexic/grammars/gbnf/syntax.py` (Tasks 1–4 implementation file; folded into `adapter.py`)
- `src/lexic/grammars/gbnf/emitter.py` (replaced by slim `emit.py`)
- Test mirrors of every deletion above.

### Modified in place

- `src/lexic/ir/atoms.py` — `Atom` becomes a `Protocol` marker; `InlineRegexAtom` loses `gbnf`, renames `regex` → `canonical`.
- `src/lexic/ir/spec.py` — adds `non_semantic_fields: frozenset[str]`.
- `src/lexic/ir/naming.py` — `_CHARCLASS_NAMES`/`_LITERAL_NAMES` become `CHARCLASS_NAMES`/`LITERAL_NAMES` (public); `_inline_regex_field_name` takes `canonical` not `gbnf`.
- `src/lexic/ir/__init__.py` — re-exports.
- `src/lexic/grammars/flavours.py` — `FlavourParser`/`FlavourEmitter`/`FlavourAdapter` Protocols **deleted**; replaced by re-exports from `lexic.ir.protocols`. The registry (`ADAPTERS`, `register_adapter`, `get_adapter`, `adapter_for_extension`) stays.
- `src/lexic/grammars/gbnf/__init__.py` — re-exports `GbnfAdapter`.
- `src/lexic/grammars/gbnf/adapter.py` — declares `GbnfEscapes(EscapeCodec)` + module-level `decode_gbnf_escapes` / `encode_gbnf_escapes` aliases (formerly `syntax.py`); full handler-table wiring; passes its own `escapes` instance into the cached `GbnfEmitter`.
- `src/lexic/grammars/gbnf/parser.py` — `GbnfParser.parse()` returns `list[RuleSpec]`.
- `src/lexic/codegen/__init__.py` — drops `IRBuilder` import; calls `adapter.parser.parse(text)` directly; sets `__adapter__` on generated module.
- `src/lexic/codegen/model_emitter.py` — handler-based atom rendering; emits the `__adapter__ = ...` line.
- `src/lexic/compile.py` — import paths updated.
- `src/lexic/__init__.py` — re-exports updated for `runtime/` move.

---

## Phase order

Tasks build bottom-up. Each task ends with a green test suite; tests stay green at every commit.

| Task | Concern | Depends on |
|------|---------|------------|
| 1    | Foundations: protocols, RuleSpec, Atom Protocol marker, ir/helpers move, `EscapeCodec` ABC | — |
| 2    | Generic algorithms: topo, classify, convert, builder, charclass | 1 |
| 3    | FlavourEmitter ABC | 1 |
| 4    | GBNF flavour: declare `GbnfEscapes(EscapeCodec)` in `adapter.py`; delete `escapes.py`/`charclass.py`/`syntax.py` | 1 (needs `EscapeCodec` ABC) |
| 5    | GBNF ast_to_ir: GbnfClassifier + GbnfConverter; decode literals at parse time | 1, 2, 4 |
| 6    | Slim GbnfEmitter | 3, 4 |
| 7    | Drop InlineRegexAtom.gbnf — canonical regex form | 5, 6 |
| 8    | parsing/ package + handler dispatch + 3 ws fixes | 1, 7 |
| 9    | codegen handler dispatch | 1, 7 |
| 10   | runtime/ package + per-module __adapter__ + 2 ws fixes | 1, 7, 8, 9 |
| 11   | GbnfAdapter full wiring + FlavourAdapter move + dead-file cleanup | 1–10 |
| 12   | Docs + AST import-boundary test | 1–11 |

---

## Task 1: Foundations — protocols, RuleSpec, Atom Protocol marker, ir/helpers move, `EscapeCodec` ABC

Replace v2's `ir/protocols.py` draft with the canonical version (full Protocol surface + handler aliases). Add `Atom` as a runtime-checkable Protocol marker. Add `non_semantic_fields` to `RuleSpec`. Move `HelperRuleRegistry` from `codegen/` to `ir/`. Create `EscapeCodec` ABC in `ir/escapes.py` (algorithm-owning base; subclasses declare only escape tables).

**Files:**
- Modify: `src/lexic/ir/atoms.py`
- Modify: `src/lexic/ir/spec.py`
- Replace: `src/lexic/ir/protocols.py`
- Create: `src/lexic/ir/escapes.py`
- Create: `tests/unit/lexic/ir/test_escapes.py`
- Move: `src/lexic/codegen/helpers.py` → `src/lexic/ir/helpers.py`
- Move: `tests/unit/lexic/codegen/test_helpers.py` → `tests/unit/lexic/ir/test_helpers.py`
- Modify: `src/lexic/ir/__init__.py`
- Modify: `src/lexic/codegen/ir_builder.py` (import path: `lexic.codegen.helpers` → `lexic.ir.helpers`)
- Modify: `src/lexic/codegen/seq_to_atoms.py` (same)

- [ ] **Step 1: Make `Atom` a `Protocol` marker; keep concrete dataclasses.**

Edit `src/lexic/ir/atoms.py`. Replace the `Atom = LiteralAtom | CharClassAtom | ...` union near the bottom with:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Atom(Protocol):
    """Marker protocol for IR atoms.

    Concrete atoms are frozen dataclasses. Atoms with bounded repetition
    expose `min: int` and `max: int | None`. The IR is open: flavours may
    define their own atom dataclasses next to their adapter — they qualify
    as `Atom` structurally.
    """
```

Place the `Protocol` definition **above** the concrete atoms (so `from __future__ import annotations` in consumers continues to resolve forward refs). Add `frozen=True` to every `@dataclass` that does not already have it. Drop the trailing `Atom = LiteralAtom | ...` union line.

- [ ] **Step 2: Run the existing IR atom tests to confirm dataclasses still work.**

```bash
uv run pytest tests/unit/lexic/ir/test_atoms.py -q
```

Expected: PASS.

- [ ] **Step 3: Add `non_semantic_fields` to `RuleSpec`.**

Edit `src/lexic/ir/spec.py`:

```python
from dataclasses import dataclass, field
# ...

@dataclass
class RuleSpec:
    rule_name: str
    class_name: str
    parent_class_name: str
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[Atom] = field(default_factory=list)
    field_map: dict[str, int] = field(default_factory=dict)
    non_semantic_fields: frozenset[str] = field(default_factory=frozenset)
```

- [ ] **Step 4: Run RuleSpec tests.**

```bash
uv run pytest tests/unit/lexic/ir/test_spec.py -q
```

Expected: PASS (default `frozenset()` is backward-compatible).

- [ ] **Step 5: Move `HelperRuleRegistry`.**

```bash
git mv src/lexic/codegen/helpers.py src/lexic/ir/helpers.py
git mv tests/unit/lexic/codegen/test_helpers.py tests/unit/lexic/ir/test_helpers.py
```

Edit `src/lexic/ir/helpers.py` to update the import:

```python
"""HelperRuleRegistry: one-per-build registry for synthesised helper rules."""

from __future__ import annotations

from lexic.ir.spec import RuleSpec


class HelperRuleRegistry:
    def __init__(self) -> None:
        self._specs: list[RuleSpec] = []
        self._names: set[str] = set()

    def reserve(self, base_name: str) -> str:
        if base_name not in self._names:
            return base_name
        suffix = 2
        while f"{base_name}{suffix}" in self._names:
            suffix += 1
        return f"{base_name}{suffix}"

    def register(self, spec: RuleSpec) -> None:
        if spec.rule_name in self._names:
            raise ValueError(f"Helper rule {spec.rule_name!r} already registered")
        self._names.add(spec.rule_name)
        self._specs.append(spec)

    def all_specs(self) -> list[RuleSpec]:
        return list(self._specs)
```

Edit `tests/unit/lexic/ir/test_helpers.py`:

```python
from lexic.ir.helpers import HelperRuleRegistry
```

- [ ] **Step 6: Update import paths in remaining consumers.**

```bash
sed -i 's|from lexic.codegen.helpers import|from lexic.ir.helpers import|g' \
    src/lexic/codegen/ir_builder.py \
    src/lexic/codegen/seq_to_atoms.py \
    tests/unit/lexic/codegen/test_seq_to_atoms.py
```

- [ ] **Step 7: Write failing tests for `EscapeCodec` ABC.**

Create `tests/unit/lexic/ir/test_escapes.py`:

```python
"""EscapeCodec ABC — encode/decode/read_escape via fake subclass + canonical instance."""
from __future__ import annotations

import pytest

from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec


class _Codec(EscapeCodec):
    SHORT_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
    HEX_ESCAPES = (("x", 2), ("u", 4))


_C = _Codec()


@pytest.mark.parametrize("src,expected", [
    (r"\n", "\n"),
    (r"\t", "\t"),
    (r"\\", "\\"),
    (r"\"", '"'),
    (r"\x41", "A"),
    (r"é", "é"),
    (r"hello\nworld", "hello\nworld"),
    ("plain", "plain"),
])
def test_decode_short_and_hex(src, expected):
    assert _C.decode(src) == expected


@pytest.mark.parametrize("canonical,expected", [
    ("\n", r"\n"),
    ("\t", r"\t"),
    ("\\", r"\\"),
    ('"', r"\""),
    ("hello\nworld", r"hello\nworld"),
    ("plain", "plain"),
])
def test_encode_inverts_short_table(canonical, expected):
    assert _C.encode(canonical) == expected


def test_encode_decode_roundtrip_on_canonical_python():
    s = "tab\there\nnewline"
    assert _C.decode(_C.encode(s)) == s


def test_read_escape_short():
    assert _C.read_escape(r"\nrest", 0) == ("\n", 2)


def test_read_escape_hex():
    assert _C.read_escape(r"\x41rest", 0) == ("A", 4)


def test_read_escape_unrecognised_returns_literal_char():
    assert _C.read_escape(r"\zrest", 0) == ("z", 2)


def test_canonical_escapes_supports_posix_meta():
    # POSIX bracket-meta chars must be readable as themselves when escaped.
    assert CANONICAL_ESCAPES.read_escape(r"\]rest", 0) == ("]", 2)
    assert CANONICAL_ESCAPES.read_escape(r"\-rest", 0) == ("-", 2)
    assert CANONICAL_ESCAPES.read_escape(r"\^rest", 0) == ("^", 2)


def test_canonical_escapes_decodes_python_control_and_hex():
    assert CANONICAL_ESCAPES.decode(r"a\nb\x41") == "a\nbA"
```

- [ ] **Step 8: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/ir/test_escapes.py -q
```

- [ ] **Step 9: Create `src/lexic/ir/escapes.py`.**

```python
"""EscapeCodec ABC — canonical Python ↔ flavour-text escape conversion.

Subclasses declare two class attrs (SHORT_ESCAPES, HEX_ESCAPES); the
encode/decode/read_escape algorithms are shared. Mirrors FlavourEmitter's
ABC pattern: generic algorithm in core, syntax constants per flavour.
"""

from __future__ import annotations

import re
from abc import ABC
from functools import cache
from typing import ClassVar


class EscapeCodec(ABC):
    """Generic encode/decode/read_escape algorithms parameterised by tables."""

    SHORT_ESCAPES: ClassVar[dict[str, str]] = {}
    """Source follow-char → canonical char.  e.g. {"n": "\n", "\\": "\\"}"""

    HEX_ESCAPES: ClassVar[tuple[tuple[str, int], ...]] = ()
    """Hex tag chars + digit counts. e.g. (("x", 2), ("u", 4), ("U", 8))"""

    def decode(self, source: str) -> str:
        return self._decode_re().sub(self._replace, source)

    def encode(self, value: str) -> str:
        table = self._encode_table()
        return "".join(table.get(c, c) for c in value)

    def read_escape(self, source: str, i: int) -> tuple[str, int]:
        """Parse one escape starting at source[i] == '\\'. Returns (char, new_i)."""
        c = source[i + 1]
        if c in self.SHORT_ESCAPES:
            return self.SHORT_ESCAPES[c], i + 2
        for tag, n in self.HEX_ESCAPES:
            if c == tag and i + 1 + n < len(source):
                return chr(int(source[i + 2 : i + 2 + n], 16)), i + 2 + n
        return c, i + 2

    @classmethod
    @cache
    def _encode_table(cls) -> dict[str, str]:
        return {canon: f"\\{src}" for src, canon in cls.SHORT_ESCAPES.items()}

    @classmethod
    @cache
    def _decode_re(cls) -> re.Pattern[str]:
        parts: list[str] = []
        if cls.SHORT_ESCAPES:
            parts.append("[" + "".join(re.escape(c) for c in cls.SHORT_ESCAPES) + "]")
        for tag, n in cls.HEX_ESCAPES:
            parts.append(f"{re.escape(tag)}[0-9a-fA-F]{{{n}}}")
        return re.compile(r"\\(?:" + "|".join(parts) + ")")

    def _replace(self, m: re.Match[str]) -> str:
        seq = m.group(0)
        c = seq[1]
        if c in self.SHORT_ESCAPES:
            return self.SHORT_ESCAPES[c]
        return chr(int(seq[2:], 16))


class _CanonicalEscapes(EscapeCodec):
    """Escape rules for canonical POSIX-style bracket strings stored in the IR.

    Used by `ir/charclass.py` to enumerate chars from `CharClassAtom.pattern`.
    Set is narrow on purpose — canonical patterns must round-trip across every
    supported flavour.
    """

    SHORT_ESCAPES = {
        "n": "\n", "t": "\t", "r": "\r", "\\": "\\",
        "]": "]", "-": "-", "^": "^",
    }
    HEX_ESCAPES = (("x", 2), ("u", 4), ("U", 8))


CANONICAL_ESCAPES: EscapeCodec = _CanonicalEscapes()
```

- [ ] **Step 10: Run escape tests — PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_escapes.py -q
```

- [ ] **Step 11: Replace `src/lexic/ir/protocols.py` with the canonical version.**

`EscapeCodec` is no longer declared here — it is imported from `lexic.ir.escapes` and re-exported. Overwrite the entire file:

```python
"""IR-construction Protocols, FlavourAdapter Protocol, and handler type aliases.

Type-only. No runtime classes live here — HelperRuleRegistry is in
`lexic.ir.helpers`; IRBuilder is in `lexic.ir.builder`; FlavourEmitter ABC
is in `lexic.ir.emit`; EscapeCodec ABC is in `lexic.ir.escapes`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Literal, Protocol, TypeVar

from lexic.ir.atoms import Atom
from lexic.ir.escapes import EscapeCodec
from lexic.ir.spec import RuleSpec

if TYPE_CHECKING:
    from lexic.ir.helpers import HelperRuleRegistry
    from lexic.ir.emit import FlavourEmitter

Node = TypeVar("Node")


class RuleClassifier(Protocol[Node]):
    """AST-shape queries on a single rule node."""

    def rule_name(self, rule: Node) -> str: ...
    def is_start_rule(self, rule: Node) -> bool: ...
    def kind(self, rule: Node) -> Literal["sequence", "alternation", "value_str"]: ...
    def alternation_arm_nodes(self, rule: Node) -> list[Node]: ...
    def sequence_body(self, rule: Node) -> Node: ...
    def value_str_body(self, rule: Node) -> Node: ...
    def single_ruleref(self, arm: Node) -> str | None: ...


class SequenceConverter(Protocol[Node]):
    """AST → Atom conversion. Per-flavour AST shape, canonical Atom output."""

    def value_str_atoms(self, body: Node) -> list[Atom]: ...
    def sequence_atoms(
        self,
        body: Node,
        parent_class_name: str,
        helpers: "HelperRuleRegistry",
    ) -> list[Atom]: ...


class FlavourParser(Protocol):
    """text → list[RuleSpec]. AST is package-internal."""

    def parse(self, text: str) -> list[RuleSpec]: ...


# Per-consumer handler type aliases.
AtomEmitHandler = Callable[[Atom, "FlavourEmitter"], str]
FieldHandler = Callable[..., object]      # signature finalised in Task 9
LarkHandler = Callable[..., str]          # signature finalised in Task 8
TransformHandler = Callable[..., object]  # signature finalised in Task 8
ToTextHandler = Callable[..., str]        # signature finalised in Task 10


class FlavourAdapter(Protocol):
    """The full adapter surface a flavour package exposes."""

    name: str
    extensions: tuple[str, ...]
    parser: FlavourParser
    emitter: "FlavourEmitter"
    escapes: EscapeCodec
    supports: frozenset[str]

    field_handlers: dict[type, FieldHandler]
    lark_handlers: dict[type, LarkHandler]
    transform_handlers: dict[type, TransformHandler]
    to_text_handlers: dict[type, ToTextHandler]


__all__ = [
    "AtomEmitHandler",
    "EscapeCodec",
    "FieldHandler",
    "FlavourAdapter",
    "FlavourParser",
    "LarkHandler",
    "RuleClassifier",
    "SequenceConverter",
    "ToTextHandler",
    "TransformHandler",
]
```

- [ ] **Step 12: Update `src/lexic/ir/__init__.py`.**

`EscapeCodec` is sourced directly from `lexic.ir.escapes` (the ABC home); the rest comes from `protocols`.

```python
"""Public IR surface — import everything from here."""

from lexic.ir.atoms import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.protocols import (
    AtomEmitHandler,
    FieldHandler,
    FlavourAdapter,
    FlavourParser,
    LarkHandler,
    RuleClassifier,
    SequenceConverter,
    ToTextHandler,
    TransformHandler,
)
from lexic.ir.spec import RuleSpec

__all__ = [
    "AlternationAtom",
    "Atom",
    "AtomEmitHandler",
    "CANONICAL_ESCAPES",
    "CharClassAtom",
    "EscapeCodec",
    "FieldHandler",
    "FlavourAdapter",
    "FlavourParser",
    "HelperRuleRegistry",
    "InlineAlternationAtom",
    "InlineRegexAtom",
    "LarkHandler",
    "LiteralAtom",
    "QuantifiedLiteralAtom",
    "RuleClassifier",
    "RuleRefAtom",
    "RuleSpec",
    "SequenceConverter",
    "ToTextHandler",
    "TransformHandler",
]
```

- [ ] **Step 13: Run the full suite to confirm nothing broke.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

Expected: all green. (`ir/__init__.py` no longer re-exports `IRBuilder` — that lands in Task 2; `codegen/ir_builder.py:IRBuilder` is unaffected.)

- [ ] **Step 14: Commit.**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor(ir): foundations — Protocol Atom, RuleSpec.non_semantic_fields, EscapeCodec ABC, helpers move

- Atom is a runtime-checkable Protocol marker (open atom set).
- RuleSpec gains non_semantic_fields: frozenset[str] (used by D2 ws fix).
- HelperRuleRegistry moved codegen/ → ir/helpers.py.
- EscapeCodec is now an ABC in ir/escapes.py — owns encode/decode/read_escape;
  subclasses declare only SHORT_ESCAPES/HEX_ESCAPES tables.  CANONICAL_ESCAPES
  instance models POSIX bracket-string escape rules.
- ir/protocols.py rewritten with full Protocol surface + handler aliases;
  re-exports EscapeCodec from ir/escapes.py.
- ir/__init__.py re-exports updated.
EOF
)"
```

---

## Task 2: Generic algorithms — `topo`, `classify`, `convert`, `builder`, `charclass`

Implement the four generic algorithms in `ir/` plus `ir/charclass.py` (bracket-expression enumeration parameterised by `EscapeCodec`). Tests use minimal fake `RuleClassifier`/`SequenceConverter` implementations — no GBNF dependency. The existing GBNF pipeline (`codegen/ir_builder.py:IRBuilder`) is untouched in this task; Task 5 wires GBNF to use the new generic builder.

**Files:**
- Create: `src/lexic/ir/topo.py`
- Create: `src/lexic/ir/classify.py`
- Create: `src/lexic/ir/convert.py`
- Create: `src/lexic/ir/builder.py`
- Create: `src/lexic/ir/charclass.py`
- Create: `tests/unit/lexic/ir/test_topo.py`
- Create: `tests/unit/lexic/ir/test_classify.py`
- Create: `tests/unit/lexic/ir/test_convert.py`
- Create: `tests/unit/lexic/ir/test_builder.py`
- Create: `tests/unit/lexic/ir/test_charclass.py`
- Modify: `src/lexic/ir/__init__.py` (re-export `IRBuilder`, `topo_sort`, `classify_rule`, `parse_charclass_chars`)

- [ ] **Step 1: Write failing tests for `topo_sort`.**

Create `tests/unit/lexic/ir/test_topo.py`:

```python
"""topo_sort: orders specs so parent classes come before subclasses; start rule first."""
from __future__ import annotations

from lexic.ir import RuleSpec
from lexic.ir.topo import topo_sort


def _spec(name: str, parent: str = "GrammarModel") -> RuleSpec:
    return RuleSpec(
        rule_name=name,
        class_name=name.title(),
        parent_class_name=parent,
        kind="sequence",
        items=[],
        field_map={},
    )


def test_topo_sort_puts_start_rule_first():
    a, b, root = _spec("a"), _spec("b"), _spec("root")
    is_start = lambda s: s.rule_name == "root"
    out = topo_sort([a, b, root], is_start_rule=is_start)
    assert out[0].rule_name == "root"


def test_topo_sort_orders_parents_before_subclasses():
    parent = _spec("term")
    child = _spec("expr", parent="Term")
    root = _spec("root")
    is_start = lambda s: s.rule_name == "root"
    out = topo_sort([child, parent, root], is_start_rule=is_start)
    rule_names = [s.rule_name for s in out]
    assert rule_names.index("term") < rule_names.index("expr")
    assert rule_names[0] == "root"


def test_topo_sort_no_start_rule_falls_back_to_input_order():
    a, b = _spec("a"), _spec("b")
    is_start = lambda s: False
    out = topo_sort([a, b], is_start_rule=is_start)
    assert [s.rule_name for s in out] == ["a", "b"]
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/ir/test_topo.py -q
```

- [ ] **Step 3: Create `src/lexic/ir/topo.py`.**

```python
"""Generic topological sort over RuleSpecs."""

from __future__ import annotations

from typing import Callable

from lexic.ir.spec import RuleSpec


def topo_sort(
    specs: list[RuleSpec],
    *,
    is_start_rule: Callable[[RuleSpec], bool],
) -> list[RuleSpec]:
    """Order specs so parent classes appear before subclasses, with the start rule first.

    `is_start_rule` is a flavour-supplied predicate. When it matches multiple
    specs, the first one in input order wins.
    """
    by_cls = {s.class_name: s for s in specs}
    ordered: list[RuleSpec] = []
    visited: set[str] = set()

    def visit(cls_name: str) -> None:
        if cls_name in visited:
            return
        visited.add(cls_name)
        spec = by_cls.get(cls_name)
        if spec and spec.parent_class_name not in ("GrammarModel", "BaseModel"):
            visit(spec.parent_class_name)
        if spec:
            ordered.append(spec)

    start_spec = next((s for s in specs if is_start_rule(s)), None)
    if start_spec is not None:
        visit(start_spec.class_name)
    for s in specs:
        visit(s.class_name)

    return ordered
```

- [ ] **Step 4: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_topo.py -q
```

- [ ] **Step 5: Write failing tests for `classify_rule`.**

Create `tests/unit/lexic/ir/test_classify.py`:

```python
"""classify_rule: generic algorithm; takes a RuleClassifier protocol impl."""
from __future__ import annotations

from dataclasses import dataclass

from lexic.ir.classify import classify_rule


# Fake AST node + classifier for testing. No GBNF imports.
@dataclass(frozen=True)
class FakeNode:
    name: str
    kind: str  # "sequence" | "alternation" | "value_str"


class FakeClassifier:
    def rule_name(self, rule): return rule.name
    def is_start_rule(self, rule): return rule.name == "start"
    def kind(self, rule): return rule.kind
    def alternation_arm_nodes(self, rule): return []
    def sequence_body(self, rule): return rule
    def value_str_body(self, rule): return rule
    def single_ruleref(self, arm): return None


def test_classify_returns_kind_from_classifier():
    rule = FakeNode(name="r", kind="sequence")
    assert classify_rule(rule, FakeClassifier()) == "sequence"


def test_classify_value_str():
    rule = FakeNode(name="lit", kind="value_str")
    assert classify_rule(rule, FakeClassifier()) == "value_str"


def test_classify_alternation():
    rule = FakeNode(name="alt", kind="alternation")
    assert classify_rule(rule, FakeClassifier()) == "alternation"
```

- [ ] **Step 6: Run — expect ModuleNotFoundError.**

- [ ] **Step 7: Create `src/lexic/ir/classify.py`.**

```python
"""Generic rule classification — delegates to RuleClassifier protocol."""

from __future__ import annotations

from typing import Literal, TypeVar

from lexic.ir.protocols import RuleClassifier

Node = TypeVar("Node")


def classify_rule(
    rule: Node,
    classifier: RuleClassifier[Node],
) -> Literal["sequence", "alternation", "value_str"]:
    """Return the IR kind of a rule by asking the classifier.

    The historical `Classifier` class wrapped this in OO; the algorithm is
    a single delegation, so it stays a function.
    """
    return classifier.kind(rule)
```

- [ ] **Step 8: Run classify tests — PASS.**

- [ ] **Step 9: Write failing tests for the generic conversion.**

Create `tests/unit/lexic/ir/test_convert.py`:

```python
"""Generic conversion: takes a SequenceConverter, returns atoms + field_map."""
from __future__ import annotations

from dataclasses import dataclass

from lexic.ir import HelperRuleRegistry, LiteralAtom, RuleRefAtom
from lexic.ir.convert import convert_sequence, convert_value_str


@dataclass(frozen=True)
class FakeBody:
    expected_atoms: list


class FakeConverter:
    def value_str_atoms(self, body):
        return list(body.expected_atoms)
    def sequence_atoms(self, body, parent_class_name, helpers):
        return list(body.expected_atoms)


def test_convert_value_str_returns_atoms_from_converter():
    body = FakeBody(expected_atoms=[LiteralAtom(value="hi")])
    assert convert_value_str(body, FakeConverter()) == [LiteralAtom(value="hi")]


def test_convert_sequence_returns_atoms_from_converter():
    body = FakeBody(expected_atoms=[RuleRefAtom("x", 1, 1)])
    helpers = HelperRuleRegistry()
    out = convert_sequence(body, "Cls", helpers, FakeConverter())
    assert out == [RuleRefAtom("x", 1, 1)]
```

- [ ] **Step 10: Create `src/lexic/ir/convert.py`.**

```python
"""Generic conversion entry points — delegate to SequenceConverter protocol."""

from __future__ import annotations

from typing import TypeVar

from lexic.ir.atoms import Atom
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.protocols import SequenceConverter

Node = TypeVar("Node")


def convert_value_str(
    body: Node,
    converter: SequenceConverter[Node],
) -> list[Atom]:
    return converter.value_str_atoms(body)


def convert_sequence(
    body: Node,
    parent_class_name: str,
    helpers: HelperRuleRegistry,
    converter: SequenceConverter[Node],
) -> list[Atom]:
    return converter.sequence_atoms(body, parent_class_name, helpers)
```

- [ ] **Step 11: Run convert tests — PASS.**

- [ ] **Step 12: Write failing tests for `IRBuilder`.**

Create `tests/unit/lexic/ir/test_builder.py`:

```python
"""IRBuilder: generic orchestrator parameterised by RuleClassifier + SequenceConverter."""
from __future__ import annotations

from dataclasses import dataclass

from lexic.ir import (
    AlternationAtom,
    Atom,
    HelperRuleRegistry,
    LiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.ir.builder import IRBuilder


@dataclass(frozen=True)
class FakeNode:
    name: str
    kind: str
    items: list[Atom]
    arms: list = None  # for alternation
    is_start: bool = False


class FakeClassifier:
    def rule_name(self, rule): return rule.name
    def is_start_rule(self, rule): return rule.is_start
    def kind(self, rule): return rule.kind
    def alternation_arm_nodes(self, rule): return rule.arms or []
    def sequence_body(self, rule): return rule
    def value_str_body(self, rule): return rule
    def single_ruleref(self, arm):
        if len(arm.items) == 1 and isinstance(arm.items[0], RuleRefAtom):
            return arm.items[0].rule_name
        return None


class FakeConverter:
    def value_str_atoms(self, body): return list(body.items)
    def sequence_atoms(self, body, parent_class_name, helpers): return list(body.items)


def test_builder_value_str_rule_produces_one_value_str_spec():
    rule = FakeNode(name="num", kind="value_str", items=[LiteralAtom(value="0")], is_start=True)
    builder = IRBuilder(FakeClassifier(), FakeConverter())
    specs = builder.build([rule])
    assert len(specs) == 1
    assert specs[0].rule_name == "num"
    assert specs[0].kind == "value_str"


def test_builder_sets_min_zero_on_trivia_refs():
    rule = FakeNode(
        name="root",
        kind="sequence",
        items=[RuleRefAtom("ws", 1, 1), RuleRefAtom("expr", 1, 1)],
        is_start=True,
    )
    builder = IRBuilder(FakeClassifier(), FakeConverter())
    specs = builder.build([rule])
    ws_atom = specs[0].items[0]
    assert isinstance(ws_atom, RuleRefAtom)
    assert ws_atom.min == 0  # trivia rule → optional


def test_builder_populates_non_semantic_fields_for_trivia_refs():
    rule = FakeNode(
        name="root",
        kind="sequence",
        items=[RuleRefAtom("ws", 1, 1), RuleRefAtom("expr", 1, 1)],
        is_start=True,
    )
    builder = IRBuilder(FakeClassifier(), FakeConverter())
    spec = builder.build([rule])[0]
    # The "ws" field maps to the ws atom; that field must be in non_semantic_fields.
    ws_field = next(name for name, idx in spec.field_map.items()
                    if isinstance(spec.items[idx], RuleRefAtom)
                    and spec.items[idx].rule_name == "ws")
    assert ws_field in spec.non_semantic_fields


def test_builder_custom_trivia_rules_parameter():
    rule = FakeNode(
        name="root",
        kind="sequence",
        items=[RuleRefAtom("ignore", 1, 1)],
        is_start=True,
    )
    builder = IRBuilder(FakeClassifier(), FakeConverter(), trivia_rules=frozenset({"ignore"}))
    spec = builder.build([rule])[0]
    assert spec.items[0].min == 0


def test_builder_topo_sorts_with_start_rule_first():
    other = FakeNode(name="other", kind="sequence", items=[], is_start=False)
    root = FakeNode(name="root", kind="sequence", items=[], is_start=True)
    builder = IRBuilder(FakeClassifier(), FakeConverter())
    specs = builder.build([other, root])
    assert specs[0].rule_name == "root"
```

- [ ] **Step 13: Create `src/lexic/ir/builder.py`.**

```python
"""IRBuilder — generic orchestrator parameterised by classifier + converter.

Subclass to override per-step behaviour; the default implementation works
for any flavour whose classifier and converter satisfy the protocols.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from lexic.ir.atoms import (
    AlternationAtom,
    Atom,
    RuleRefAtom,
)
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.naming import assign_field_names
from lexic.ir.protocols import RuleClassifier, SequenceConverter
from lexic.ir.spec import RuleSpec
from lexic.ir.topo import topo_sort
from lexic.utils.names import to_pascal

Node = TypeVar("Node")


class IRBuilder(Generic[Node]):
    """list[Node] → list[RuleSpec]. Wired by a flavour adapter."""

    def __init__(
        self,
        classifier: RuleClassifier[Node],
        converter: SequenceConverter[Node],
        *,
        helpers: HelperRuleRegistry | None = None,
        trivia_rules: frozenset[str] = frozenset({"ws"}),
    ) -> None:
        self._classifier = classifier
        self._converter = converter
        self._helpers = helpers if helpers is not None else HelperRuleRegistry()
        self._trivia_rules = trivia_rules

    def build(self, rules: list[Node]) -> list[RuleSpec]:
        self._name_map = {self._classifier.rule_name(r): to_pascal(self._classifier.rule_name(r))
                          for r in rules}
        parent_of = self._compute_parents(rules)
        primary: list[RuleSpec] = []
        for rule in rules:
            primary.extend(self._build_rule(rule, parent_of))
        all_specs = primary + self._helpers.all_specs()
        all_specs = [self._mark_trivia(s) for s in all_specs]
        return topo_sort(all_specs, is_start_rule=self._is_start_spec)

    # ── overridable steps ────────────────────────────────────────────────

    def _compute_parents(self, rules: list[Node]) -> dict[str, str]:
        parent_of: dict[str, str] = {}
        for rule in rules:
            if self._classifier.kind(rule) != "alternation":
                continue
            parent_cls = self._name_map[self._classifier.rule_name(rule)]
            for arm in self._classifier.alternation_arm_nodes(rule):
                ref = self._classifier.single_ruleref(arm)
                if ref is not None:
                    parent_of[ref] = parent_cls
        return parent_of

    def _build_rule(self, rule: Node, parents: dict[str, str]) -> list[RuleSpec]:
        name = self._classifier.rule_name(rule)
        cls_name = self._name_map[name]
        parent_cls = parents.get(name, "GrammarModel")
        kind = self._classifier.kind(rule)
        if kind == "value_str":
            return self._build_value_str(rule, cls_name, parent_cls)
        if kind == "alternation":
            return self._build_named_alt(rule, cls_name, parent_cls)
        return self._build_sequence(rule, cls_name, parent_cls)

    def _build_value_str(self, rule: Node, cls_name: str, parent_cls: str) -> list[RuleSpec]:
        body = self._classifier.value_str_body(rule)
        atoms = self._converter.value_str_atoms(body)
        return [RuleSpec(
            rule_name=self._classifier.rule_name(rule),
            class_name=cls_name,
            parent_class_name=parent_cls,
            kind="value_str",
            items=atoms,
            field_map={},
        )]

    def _build_named_alt(self, rule: Node, cls_name: str, parent_cls: str) -> list[RuleSpec]:
        rule_name = self._classifier.rule_name(rule)
        arms = self._classifier.alternation_arm_nodes(rule)
        arm_rule_names: list[str] = []
        arm_specs: list[RuleSpec] = []
        for idx, arm in enumerate(arms, start=1):
            ref = self._classifier.single_ruleref(arm)
            if ref is not None:
                arm_rule_names.append(ref)
                continue
            arm_rule_name = f"{rule_name}-arm{idx}"
            arm_cls_name = f"{cls_name}Arm{idx}"
            arm_rule_names.append(arm_rule_name)
            atoms = self._converter.sequence_atoms(arm, arm_cls_name, self._helpers)
            arm_specs.append(RuleSpec(
                rule_name=arm_rule_name,
                class_name=arm_cls_name,
                parent_class_name=cls_name,
                kind="sequence",
                items=atoms,
                field_map=assign_field_names(atoms),
            ))
        abstract = RuleSpec(
            rule_name=rule_name,
            class_name=cls_name,
            parent_class_name=parent_cls,
            kind="alternation",
            items=[AlternationAtom(arm_rule_names=arm_rule_names)],
            field_map={},
        )
        return [abstract] + arm_specs

    def _build_sequence(self, rule: Node, cls_name: str, parent_cls: str) -> list[RuleSpec]:
        body = self._classifier.sequence_body(rule)
        atoms = self._converter.sequence_atoms(body, cls_name, self._helpers)
        return [RuleSpec(
            rule_name=self._classifier.rule_name(rule),
            class_name=cls_name,
            parent_class_name=parent_cls,
            kind="sequence",
            items=atoms,
            field_map=assign_field_names(atoms),
        )]

    # ── trivia handling (D2) ────────────────────────────────────────────

    def _mark_trivia(self, spec: RuleSpec) -> RuleSpec:
        """Set min=0 on every trivia-RuleRef and populate non_semantic_fields."""
        new_items: list[Atom] = []
        for atom in spec.items:
            if isinstance(atom, RuleRefAtom) and atom.rule_name in self._trivia_rules and atom.min > 0:
                new_items.append(RuleRefAtom(atom.rule_name, 0, atom.max))
            else:
                new_items.append(atom)
        non_sem = frozenset(
            name for name, idx in spec.field_map.items()
            if isinstance(new_items[idx], RuleRefAtom)
            and new_items[idx].rule_name in self._trivia_rules
        )
        if new_items == spec.items and non_sem == spec.non_semantic_fields:
            return spec
        return RuleSpec(
            rule_name=spec.rule_name,
            class_name=spec.class_name,
            parent_class_name=spec.parent_class_name,
            kind=spec.kind,
            items=new_items,
            field_map=spec.field_map,
            non_semantic_fields=non_sem,
        )

    def _is_start_spec(self, spec: RuleSpec) -> bool:
        # Default: a spec is the start if its rule_name matches the first input rule.
        # Subclasses may override; flavour classifiers may also expose is_start_rule
        # at the AST level — but by build-time we operate on RuleSpecs.
        return False  # set at the class level by callers when needed
```

- [ ] **Step 14: Run builder tests — most should pass.**

```bash
uv run pytest tests/unit/lexic/ir/test_builder.py -q
```

The first few tests pass. The `topo_sorts_with_start_rule_first` test fails because `_is_start_spec` returns False — the AST-level `is_start_rule` query isn't propagated to the spec level by default. The classifier knows about start rules; the builder must consult it during build, then use a name-based predicate at topo time.

- [ ] **Step 15: Wire start-rule detection through the build.**

Edit `src/lexic/ir/builder.py`:

```python
def build(self, rules: list[Node]) -> list[RuleSpec]:
    self._name_map = {self._classifier.rule_name(r): to_pascal(self._classifier.rule_name(r))
                      for r in rules}
    self._start_rule_names = frozenset(
        self._classifier.rule_name(r) for r in rules if self._classifier.is_start_rule(r)
    )
    parent_of = self._compute_parents(rules)
    primary: list[RuleSpec] = []
    for rule in rules:
        primary.extend(self._build_rule(rule, parent_of))
    all_specs = primary + self._helpers.all_specs()
    all_specs = [self._mark_trivia(s) for s in all_specs]
    return topo_sort(all_specs, is_start_rule=self._is_start_spec)

def _is_start_spec(self, spec: RuleSpec) -> bool:
    return spec.rule_name in self._start_rule_names
```

- [ ] **Step 16: Run builder tests — PASS.**

- [ ] **Step 17: Write failing tests for `parse_charclass_chars`.**

Create `tests/unit/lexic/ir/test_charclass.py`:

```python
"""parse_charclass_chars — bracket-expression enumeration over canonical patterns."""
from __future__ import annotations

from lexic.ir.charclass import parse_charclass_chars
from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec


def test_simple_range():
    assert parse_charclass_chars("a-c") == ["a", "b", "c"]


def test_multiple_ranges():
    assert parse_charclass_chars("a-cA-C") == ["a", "b", "c", "A", "B", "C"]


def test_literal_chars_only():
    assert parse_charclass_chars("xyz") == ["x", "y", "z"]


def test_mixed_range_and_literal():
    assert parse_charclass_chars("a-c_") == ["a", "b", "c", "_"]


def test_escape_in_range_endpoint():
    # \x41 = 'A', \x43 = 'C'
    assert parse_charclass_chars(r"\x41-\x43") == ["A", "B", "C"]


def test_escaped_meta_passes_through():
    # `\-` is a literal hyphen, not a range marker.
    assert parse_charclass_chars(r"a\-z") == ["a", "-", "z"]


def test_default_codec_is_canonical_escapes():
    # Same call without explicit codec produces the same result.
    assert parse_charclass_chars("a-c") == parse_charclass_chars("a-c", CANONICAL_ESCAPES)


def test_codec_is_parametric():
    # Custom codec exposes a different escape set.
    class _Custom(EscapeCodec):
        SHORT_ESCAPES = {"q": "Z"}
        HEX_ESCAPES = ()
    assert parse_charclass_chars(r"\q", _Custom()) == ["Z"]
```

- [ ] **Step 18: Run — expect ModuleNotFoundError.**

```bash
uv run pytest tests/unit/lexic/ir/test_charclass.py -q
```

- [ ] **Step 19: Create `src/lexic/ir/charclass.py`.**

```python
"""Bracket-expression enumeration over canonical POSIX patterns.

`parse_charclass_chars` is the generic algorithm used by `runtime.generate`
and any future flavour that needs to enumerate the chars of a CharClassAtom
pattern. Escape-reading is delegated to an `EscapeCodec`; default codec is
`CANONICAL_ESCAPES` since `CharClassAtom.pattern` is canonical POSIX.
"""

from __future__ import annotations

from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec


def parse_charclass_chars(
    inner: str,
    codec: EscapeCodec = CANONICAL_ESCAPES,
) -> list[str]:
    """Parse the interior of a bracket expression into a list of chars.

    `inner` is the body between `[` and `]`. Ranges (`a-z`) expand to all
    characters between the endpoints inclusive. Escapes are read via
    `codec.read_escape`.
    """
    chars: list[str] = []
    i = 0
    while i < len(inner):
        ch, i = _read_char(inner, i, codec)
        if i < len(inner) and inner[i] == "-" and i + 1 < len(inner):
            end_ch, i = _read_char(inner, i + 1, codec)
            chars.extend(chr(c) for c in range(ord(ch), ord(end_ch) + 1))
        else:
            chars.append(ch)
    return chars


def _read_char(s: str, i: int, codec: EscapeCodec) -> tuple[str, int]:
    if s[i] == "\\" and i + 1 < len(s):
        return codec.read_escape(s, i)
    return s[i], i + 1
```

- [ ] **Step 20: Run charclass tests — PASS.**

```bash
uv run pytest tests/unit/lexic/ir/test_charclass.py -q
```

- [ ] **Step 21: Update `src/lexic/ir/__init__.py` to re-export `IRBuilder` and `parse_charclass_chars`.**

Add:

```python
from lexic.ir.builder import IRBuilder
from lexic.ir.charclass import parse_charclass_chars
from lexic.ir.classify import classify_rule
from lexic.ir.topo import topo_sort
```

And add `"IRBuilder"`, `"classify_rule"`, `"parse_charclass_chars"`, `"topo_sort"` to `__all__`.

- [ ] **Step 22: Run full suite + ruff.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 23: Commit.**

```bash
git add -A
git commit -m "feat(ir): generic algorithms — topo, classify, convert, builder, charclass

IRBuilder is generic over Node; takes classifier+converter; sets min=0 on
trivia rule refs; populates RuleSpec.non_semantic_fields. Subclassable via
named overridable methods. Tests use fake classifier/converter (no GBNF dep).

parse_charclass_chars lifted from grammars/gbnf into ir/charclass.py;
parameterised by EscapeCodec; defaults to CANONICAL_ESCAPES since
CharClassAtom.pattern is canonical POSIX."
```

---

## Task 3: `FlavourEmitter` ABC

Generic emitter base class with default canonical-atom handlers and decorator hooks. Subclass declares only syntax constants and overrides `encode`/`render_charclass`/`render_inline_regex` if needed.

**Files:**
- Create: `src/lexic/ir/emit.py`
- Create: `tests/unit/lexic/ir/test_emit.py`
- Modify: `src/lexic/ir/__init__.py` (re-export `FlavourEmitter`, `bounds_to_quantifier` already in utils)

- [ ] **Step 1: Write failing tests (use a fake subclass — no GBNF).**

Create `tests/unit/lexic/ir/test_emit.py`:

```python
"""FlavourEmitter ABC — DEFAULT_HANDLERS + decorators tested via a fake subclass."""
from __future__ import annotations

from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.ir.emit import FlavourEmitter


class FakeEscapes:
    def encode(self, v): return v
    def decode(self, v): return v


class _TestEmitter(FlavourEmitter):
    @property
    def supports(self):
        return frozenset({"literal", "char_class", "alternation", "quantifier"})


def _new(handlers=None) -> _TestEmitter:
    return _TestEmitter(escapes=FakeEscapes(), handlers=handlers)


def test_default_literal_handler_quotes():
    e = _new()
    assert e._render_atom(LiteralAtom(value="hi")) == '"hi"'


def test_default_quantified_literal_appends_quantifier():
    e = _new()
    assert e._render_atom(QuantifiedLiteralAtom(value="-", min=0, max=1)) == '"-"?'


def test_default_charclass_appends_quantifier():
    e = _new()
    assert e._render_atom(CharClassAtom(pattern="[0-9]", min=1, max=None)) == "[0-9]+"


def test_default_ruleref_appends_quantifier():
    e = _new()
    assert e._render_atom(RuleRefAtom(rule_name="x", min=0, max=1)) == "x?"


def test_default_alternation_joins_with_alt_separator():
    e = _new()
    assert e._render_atom(AlternationAtom(arm_rule_names=["a", "b"])) == "a | b"


def test_default_inline_alternation_wraps_with_group():
    e = _new()
    assert e._render_atom(InlineAlternationAtom(arm_rule_names=["a", "b"])) == "(a | b)"


def test_emit_rule_renders_value_str_body():
    spec = RuleSpec(
        rule_name="num", class_name="Num", parent_class_name="GrammarModel",
        kind="value_str", items=[CharClassAtom("[0-9]", 1, None)], field_map={},
    )
    e = _new()
    assert e.emit_rule(spec) == "num ::= [0-9]+"


def test_emit_joins_rules_with_newlines():
    a = RuleSpec(rule_name="a", class_name="A", parent_class_name="GrammarModel",
                 kind="value_str", items=[LiteralAtom("x")], field_map={})
    b = RuleSpec(rule_name="b", class_name="B", parent_class_name="GrammarModel",
                 kind="value_str", items=[LiteralAtom("y")], field_map={})
    e = _new()
    assert e.emit([a, b]) == 'a ::= "x"\nb ::= "y"\n'


def test_subclass_can_override_quote_char():
    class SingleQuote(_TestEmitter):
        quote_char = "'"
    e = SingleQuote(escapes=FakeEscapes())
    assert e._render_atom(LiteralAtom(value="hi")) == "'hi'"


def test_subclass_can_register_extra_handler():
    from dataclasses import dataclass
    @dataclass(frozen=True)
    class CustomAtom:
        marker: str
    e = _new(handlers={**FlavourEmitter.DEFAULT_HANDLERS,
                       CustomAtom: lambda a, em: f"<{a.marker}>"})
    assert e._render_atom(CustomAtom(marker="x")) == "<x>"
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

- [ ] **Step 3: Create `src/lexic/ir/emit.py`.**

```python
"""FlavourEmitter ABC — generic emit algorithm + default canonical-atom handlers.

Concrete flavour subclasses declare:
    - syntax constants (rule_separator, quote_char, alt_separator, ...)
    - the @abstractmethod `supports` (set of capability names)
    - optional overrides: encode (escapes), render_charclass, render_inline_regex,
      format_quantifier, wrap_group, quote.

Atom handlers default to canonical implementations parameterised by the
decorators above; subclasses can pass extended handler tables in __init__.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from lexic.ir.atoms import (
    AlternationAtom,
    Atom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.ir.protocols import AtomEmitHandler, EscapeCodec
from lexic.ir.spec import RuleSpec
from lexic.utils.quantifiers import bounds_to_quantifier


class FlavourEmitter(ABC):
    """Generic emit algorithm + default canonical-atom handlers."""

    # Syntax constants — overridable as class attributes.
    rule_separator: str = "::="
    rule_terminator: str = ""
    alt_separator: str = " | "
    quote_char: str = '"'
    group_open: str = "("
    group_close: str = ")"
    empty_body: str = '""'

    DEFAULT_HANDLERS: ClassVar[dict[type, AtomEmitHandler]] = {
        LiteralAtom:           lambda a, e: e.quote(a.value),
        QuantifiedLiteralAtom: lambda a, e: e.quote(a.value)
                                            + e.format_quantifier(a.min, a.max),
        CharClassAtom:         lambda a, e: e.render_charclass(a.pattern)
                                            + e.format_quantifier(a.min, a.max),
        RuleRefAtom:           lambda a, e: a.rule_name
                                            + e.format_quantifier(a.min, a.max),
        AlternationAtom:       lambda a, e: e.alt_separator.join(a.arm_rule_names),
        InlineAlternationAtom: lambda a, e: e.wrap_group(
                                                e.alt_separator.join(a.arm_rule_names)),
        InlineRegexAtom:       lambda a, e: e.render_inline_regex(a.canonical)
                                            + e.format_quantifier(a.min, a.max),
    }

    def __init__(
        self,
        escapes: EscapeCodec,
        handlers: dict[type, AtomEmitHandler] | None = None,
    ) -> None:
        self._escapes = escapes
        self._handlers: dict[type, AtomEmitHandler] = (
            dict(handlers) if handlers is not None else dict(self.DEFAULT_HANDLERS)
        )

    @property
    @abstractmethod
    def supports(self) -> frozenset[str]: ...

    # ── Decorators (overridable per flavour) ──────────────────────────

    def quote(self, v: str) -> str:
        return f"{self.quote_char}{self.encode(v)}{self.quote_char}"

    def wrap_group(self, body: str) -> str:
        return f"{self.group_open}{body}{self.group_close}"

    def format_quantifier(self, lo: int, hi: int | None) -> str:
        return bounds_to_quantifier(lo, hi)

    def render_charclass(self, canonical_pattern: str) -> str:
        return canonical_pattern

    def render_inline_regex(self, canonical: str) -> str:
        return canonical

    def encode(self, v: str) -> str:
        return self._escapes.encode(v)

    # ── Generic algorithm ────────────────────────────────────────────

    def emit(self, specs: list[RuleSpec]) -> str:
        lines = [self.emit_rule(s) for s in specs]
        return "\n".join(lines) + "\n"

    def emit_rule(self, spec: RuleSpec) -> str:
        body = self._emit_body(spec)
        return f"{spec.rule_name} {self.rule_separator} {body}{self.rule_terminator}"

    def _emit_body(self, spec: RuleSpec) -> str:
        parts = [self._render_atom(a) for a in spec.items]
        parts = [p for p in parts if p]
        if not parts:
            return self.empty_body
        return " ".join(parts)

    def _render_atom(self, atom: Atom) -> str:
        try:
            handler = self._handlers[type(atom)]
        except KeyError as exc:
            raise NotImplementedError(
                f"{type(self).__name__} has no handler for {type(atom).__name__}"
            ) from exc
        return handler(atom, self)
```

- [ ] **Step 4: Run emit tests — PASS.**

- [ ] **Step 5: Re-export from `src/lexic/ir/__init__.py`.**

Add:

```python
from lexic.ir.emit import FlavourEmitter
```

Add `"FlavourEmitter"` to `__all__`.

- [ ] **Step 6: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add -A
git commit -m "feat(ir): FlavourEmitter ABC with default canonical-atom handlers

Generic emit + emit_rule + _emit_body + _render_atom; decorator hooks
(quote, wrap_group, format_quantifier, render_charclass,
render_inline_regex, encode); subclass override = class attrs only."
```

---

## Task 4: GBNF flavour — fold escape codec into `adapter.py`; delete `escapes.py`/`charclass.py`/`syntax.py`

`GbnfEscapes(EscapeCodec)` is declared at the top of `adapter.py` — the same file that already aggregates everything GBNF-specific. The encode/decode/read-escape algorithms are inherited from the ABC (Task 1).  Module-level `decode_gbnf_escapes` / `encode_gbnf_escapes` aliases are bound to a canonical instance for ergonomic functional callers downstream.  Bracket-canonicalisation helpers are dropped: today they are identities, and the GBNF parser/emitter can inline the conversion (or override `render_charclass`) when it ever stops being identity. `parse_charclass_chars` already lives in `lexic.ir.charclass` (Task 2).

**Note (amendment):** an earlier revision of this task created `src/lexic/grammars/gbnf/syntax.py` with `GbnfEscapes` + bracket converters + free-function aliases. The amendment folds those contents into `adapter.py` and drops the bracket-converter functions (YAGNI: identity today, hypothetical future Unicode-property logic belongs on `render_charclass` / parser-side, not on free functions).

**Files:**
- Modify: `src/lexic/grammars/gbnf/adapter.py` (prepend `GbnfEscapes(EscapeCodec)` + `GBNF_ESCAPES` + `decode_gbnf_escapes`/`encode_gbnf_escapes` aliases above the existing `GbnfAdapter` class)
- Delete: `src/lexic/grammars/gbnf/escapes.py`
- Delete: `src/lexic/grammars/gbnf/charclass.py`
- Modify: `tests/unit/lexic/grammars/gbnf/test_adapter.py` (absorb the GbnfEscapes / alias / encode-decode assertions; bracket-converter tests dropped)
- Delete: `tests/unit/lexic/grammars/gbnf/test_escapes.py`
- Delete: `tests/unit/lexic/grammars/gbnf/test_charclass.py`
- Update imports in: `src/lexic/codegen/lark_builder.py`, `src/lexic/codegen/transformer/build_transformer.py`, `src/lexic/base.py`, `src/lexic/grammars/gbnf/emitter.py`, `src/lexic/generate.py`, `src/lexic/ir/regex_portable.py` (if any). Note: `parse_charclass_chars` imports go to `lexic.ir.charclass`; everything else (`decode_gbnf_escapes`, `encode_gbnf_escapes`) goes to `lexic.grammars.gbnf.adapter`.

- [ ] **Step 1: Write failing tests in `tests/unit/lexic/grammars/gbnf/test_adapter.py`.**

Add the following block to the existing `test_adapter.py` (or create the section if absent):

```python
"""Adapter-resident codec tests — GbnfEscapes subclass + module-level aliases."""
from __future__ import annotations

import pytest

from lexic.grammars.gbnf.adapter import (
    GBNF_ESCAPES,
    GbnfEscapes,
    decode_gbnf_escapes,
    encode_gbnf_escapes,
)
from lexic.ir.escapes import EscapeCodec


def test_gbnf_escapes_is_subclass_of_escape_codec():
    assert issubclass(GbnfEscapes, EscapeCodec)


def test_module_aliases_are_bound_to_canonical_instance():
    assert decode_gbnf_escapes == GBNF_ESCAPES.decode
    assert encode_gbnf_escapes == GBNF_ESCAPES.encode


@pytest.mark.parametrize("src,expected", [
    (r"\n", "\n"), (r"\t", "\t"), (r"\r", "\r"),
    (r"\\", "\\"), (r"\"", '"'), (r"\x41", "A"),
    ("A", "A"), (r"hello\nworld", "hello\nworld"),
])
def test_decode_gbnf_escapes(src, expected):
    assert decode_gbnf_escapes(src) == expected


@pytest.mark.parametrize("canonical,expected", [
    ("\n", r"\n"), ("\t", r"\t"), ("\r", r"\r"),
    ("\\", r"\\"), ('"', r"\""),
    ("hello\nworld", r"hello\nworld"), ("plain", "plain"),
])
def test_encode_gbnf_escapes(canonical, expected):
    assert encode_gbnf_escapes(canonical) == expected


def test_decode_then_encode_roundtrip_on_pure_ascii():
    s = "abc-def_123"
    assert encode_gbnf_escapes(decode_gbnf_escapes(s)) == s


def test_encode_then_decode_roundtrip_on_canonical_python():
    s = "tab\there\nnewline"
    assert decode_gbnf_escapes(encode_gbnf_escapes(s)) == s
```

Bracket-converter tests are intentionally dropped — the functions go away.

- [ ] **Step 2: Run — expect ImportError until adapter.py is updated.**

- [ ] **Step 3: Prepend codec declaration to `src/lexic/grammars/gbnf/adapter.py`.**

Add **above** the existing `GbnfAdapter` class:

```python
from lexic.ir.escapes import EscapeCodec


class GbnfEscapes(EscapeCodec):
    """GBNF escape tables.  Algorithm is inherited from EscapeCodec."""

    SHORT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
    HEX_ESCAPES = (("x", 2), ("u", 4), ("U", 8))


GBNF_ESCAPES = GbnfEscapes()
decode_gbnf_escapes = GBNF_ESCAPES.decode
encode_gbnf_escapes = GBNF_ESCAPES.encode
```

The existing `GbnfAdapter` class stays (it is rewired in Task 11 to consume `GbnfEscapes` for `self.escapes`). For now, anything inside `GbnfAdapter` that referenced the old `syntax.py` aliases keeps working because the aliases are now declared in the same module.

- [ ] **Step 4: Run codec tests — PASS.**

- [ ] **Step 5: Redirect importers from `gbnf.syntax`/`gbnf.escapes`/`gbnf.charclass` to `gbnf.adapter`.**

```bash
grep -rn "from lexic.grammars.gbnf.escapes\|from lexic.grammars.gbnf.charclass\|from lexic.grammars.gbnf.syntax" src/ tests/
```

Bulk-rewrite the module path; the symbol names are unchanged (`decode_gbnf_escapes`, `encode_gbnf_escapes`, `GbnfEscapes`).

```bash
grep -rl "lexic.grammars.gbnf.escapes" src/ tests/ | xargs sed -i \
    's|lexic.grammars.gbnf.escapes|lexic.grammars.gbnf.adapter|g'
grep -rl "lexic.grammars.gbnf.charclass" src/ tests/ | xargs sed -i \
    's|lexic.grammars.gbnf.charclass|lexic.grammars.gbnf.adapter|g'
grep -rl "lexic.grammars.gbnf.syntax" src/ tests/ | xargs sed -i \
    's|lexic.grammars.gbnf.syntax|lexic.grammars.gbnf.adapter|g'
```

- [ ] **Step 6: Redirect `parse_charclass_chars` imports to `lexic.ir.charclass`.**

```bash
grep -rn "parse_charclass_chars" src/ tests/
```

For each call site, replace the `from lexic.grammars.gbnf.adapter import ...` line with `from lexic.ir.charclass import parse_charclass_chars`. If the line imports `parse_charclass_chars` alongside other names, split into two lines. Also drop any `parse_escape` imports — that name no longer exists (it became `EscapeCodec.read_escape`, called only inside `lexic.ir.charclass`).

Verification:
```bash
grep -rn "from lexic.grammars.gbnf.adapter import .*parse_charclass_chars\|from lexic.grammars.gbnf.adapter import .*parse_escape" src/ tests/
# Expected: zero hits.
```

- [ ] **Step 7: Delete `escapes.py`, `charclass.py`, `syntax.py`, and their tests.**

```bash
git rm src/lexic/grammars/gbnf/escapes.py src/lexic/grammars/gbnf/charclass.py src/lexic/grammars/gbnf/syntax.py
git rm tests/unit/lexic/grammars/gbnf/test_escapes.py tests/unit/lexic/grammars/gbnf/test_charclass.py tests/unit/lexic/grammars/gbnf/test_syntax.py
```

- [ ] **Step 8: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add -A
git commit -m "$(cat <<'EOF'
refactor(grammars/gbnf): fold escape codec into adapter.py; delete syntax.py

- GbnfEscapes(EscapeCodec) declared at the top of adapter.py — single home
  for all GBNF flavour declarations.  encode/decode/read_escape inherited
  from the ABC.
- Module-level decode_gbnf_escapes/encode_gbnf_escapes aliases preserved
  in adapter.py for downstream tasks 5–11; pruning deferred to end-of-B5.
- gbnf_bracket_to_canonical / canonical_to_gbnf_bracket dropped (YAGNI:
  identity today; future Unicode-property logic belongs on
  render_charclass and parser-side, not on free functions).
- parse_charclass_chars import path: lexic.ir.charclass (was gbnf.syntax).
- syntax.py + escapes.py + charclass.py deleted.
EOF
)"
```

---

## Task 5: GBNF AST → IR — `GbnfClassifier` + `GbnfConverter`; decode literals at parse time

Create `grammars/gbnf/ast_to_ir.py` consolidating the AST-shape queries (was `codegen/classify.py`, `seq_to_atoms.py`, `ast_utils.py`) into one module of GBNF-specific code. `GbnfClassifier` implements `RuleClassifier[Rule]`. `GbnfConverter` implements `SequenceConverter[Rule]`. **Crucial:** literal-decoding moves here — `LiteralAtom.value` is canonical Python from this point onward in the pipeline.

**Files:**
- Create: `src/lexic/grammars/gbnf/ast_to_ir.py`
- Create: `tests/unit/lexic/grammars/gbnf/test_ast_to_ir.py`
- Modify: `src/lexic/codegen/ir_builder.py` (use `GbnfClassifier` + `GbnfConverter` via the new generic `IRBuilder`)
- Modify: `src/lexic/grammars/gbnf/parser.py` (return `list[RuleSpec]`)

This task is large — split into clear sub-stages: (a) write classifier+converter, (b) wire generic IRBuilder into GBNF parser, (c) delete old codegen modules.

- [ ] **Step 1: Write failing tests for `GbnfClassifier`.**

Create `tests/unit/lexic/grammars/gbnf/test_ast_to_ir.py`:

```python
"""GBNF AST → IR — classifier + converter; canonical Python literals."""
from __future__ import annotations

from lexic.grammars.gbnf.ast import (
    Alternation, CharClass, Group, Item, Literal, Rule, RuleRef, Sequence,
)
from lexic.grammars.gbnf.ast_to_ir import GbnfClassifier, GbnfConverter
from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    HelperRuleRegistry,
    InlineAlternationAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)


def _seq(*items): return Sequence(list(items))
def _it(atom, q=None): return Item(atom, q)


# ── GbnfClassifier ───────────────────────────────────────────────────

def test_classifier_rule_name():
    rule = Rule("foo", Alternation([_seq()]))
    assert GbnfClassifier().rule_name(rule) == "foo"


def test_classifier_is_start_rule_only_for_root():
    cls = GbnfClassifier()
    assert cls.is_start_rule(Rule("root", Alternation([_seq()]))) is True
    assert cls.is_start_rule(Rule("expr", Alternation([_seq()]))) is False


def test_classifier_kind_value_str_for_pure_literal_alternation():
    rule = Rule("op", Alternation([
        _seq(_it(Literal("+"))),
        _seq(_it(Literal("-"))),
    ]))
    assert GbnfClassifier().kind(rule) == "value_str"


def test_classifier_kind_alternation_for_named_arms():
    rule = Rule("term", Alternation([
        _seq(_it(RuleRef("num"))),
        _seq(_it(RuleRef("ident"))),
    ]))
    assert GbnfClassifier().kind(rule) == "alternation"


def test_classifier_kind_sequence_for_single_arm_with_rulerefs():
    rule = Rule("expr", Alternation([
        _seq(_it(RuleRef("term")), _it(RuleRef("op")), _it(RuleRef("term"))),
    ]))
    assert GbnfClassifier().kind(rule) == "sequence"


def test_classifier_memoises_kind():
    cls = GbnfClassifier()
    rule = Rule("r", Alternation([_seq(_it(Literal("x")))]))
    k1 = cls.kind(rule)
    k2 = cls.kind(rule)
    assert k1 == k2
    # Same id → cached.
    assert cls._cache[id(rule)] is k1 or cls._cache[id(rule)] == k1


# ── GbnfConverter — canonical literal decoding ────────────────────────

def test_converter_decodes_literal_escapes():
    """\\n in GBNF source must become a canonical Python newline in LiteralAtom."""
    body = _seq(_it(Literal("a\\nb")))
    atoms = GbnfConverter().sequence_atoms(body, "Cls", HelperRuleRegistry())
    assert atoms == [LiteralAtom(value="a\nb")]


def test_converter_decodes_quantified_literal_escapes():
    body = _seq(_it(Literal("\\t"), q="?"))
    atoms = GbnfConverter().sequence_atoms(body, "Cls", HelperRuleRegistry())
    assert atoms == [QuantifiedLiteralAtom(value="\t", min=0, max=1)]


def test_converter_charclass_passthrough():
    body = _seq(_it(CharClass("[0-9]"), q="+"))
    atoms = GbnfConverter().sequence_atoms(body, "Cls", HelperRuleRegistry())
    assert atoms == [CharClassAtom(pattern="[0-9]", min=1, max=None)]


def test_converter_ruleref():
    body = _seq(_it(RuleRef("expr"), q="*"))
    atoms = GbnfConverter().sequence_atoms(body, "Cls", HelperRuleRegistry())
    assert atoms == [RuleRefAtom("expr", 0, None)]


def test_converter_value_str_atoms_decodes_literals():
    body = Alternation([_seq(_it(Literal("\\n")))])
    atoms = GbnfConverter().value_str_atoms(body)
    assert atoms == [LiteralAtom(value="\n")]


def test_converter_inline_alternation_of_named_rules():
    body = _seq(_it(Group(Alternation([
        _seq(_it(RuleRef("a"))),
        _seq(_it(RuleRef("b"))),
    ]))))
    atoms = GbnfConverter().sequence_atoms(body, "Cls", HelperRuleRegistry())
    assert atoms == [InlineAlternationAtom(arm_rule_names=["a", "b"])]
```

- [ ] **Step 2: Run — expect ModuleNotFoundError.**

- [ ] **Step 3: Create `src/lexic/grammars/gbnf/ast_to_ir.py`.**

Begin with the consolidated AST helpers + GbnfClassifier + GbnfConverter. Decode escapes via `decode_gbnf_escapes` when constructing `LiteralAtom` and `QuantifiedLiteralAtom`.

```python
"""GBNF AST → IR — classifier + converter + AST-shape predicates.

Consolidates what was `codegen/classify.py` + `codegen/seq_to_atoms.py` +
`codegen/ast_utils.py`. The classifier and converter implement the generic
ir.protocols protocols; the AST-shape predicates are private to this module.

Crucial: LiteralAtom.value is canonical Python (escapes decoded) from this
point onward. `parsing/`, `runtime/`, and `codegen/` do not decode.
"""

from __future__ import annotations

import re
from typing import Literal as TypingLiteral, cast

from lexic.grammars.gbnf.ast import (
    Alternation,
    CharClass,
    Group,
    Item,
    Literal,
    Rule,
    RuleRef,
    Sequence,
)
from lexic.grammars.gbnf.adapter import decode_gbnf_escapes
from lexic.ir import (
    Atom,
    CharClassAtom,
    HelperRuleRegistry,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.ir.naming import assign_field_names
from lexic.utils.names import to_pascal
from lexic.utils.quantifiers import quantifier_to_bounds


# ── AST-shape predicates (private) ───────────────────────────────────


def _is_ws_item(it: Item) -> bool:
    return isinstance(it.atom, RuleRef) and it.atom.name == "ws"


def _strip_ws(seq: Sequence) -> Sequence:
    return Sequence([it for it in seq.items if not _is_ws_item(it)])


def _is_pure_literal_seq(seq: Sequence) -> bool:
    if not seq.items:
        return False
    return all(isinstance(it.atom, Literal) for it in seq.items)


def _single_ruleref_of(seq: Sequence) -> str | None:
    stripped = _strip_ws(seq)
    if len(stripped.items) == 1:
        a = stripped.items[0]
        if isinstance(a.atom, RuleRef) and a.quantifier is None:
            return a.atom.name
    return None


def _unwrap_group_alt(alt: Alternation) -> Alternation:
    if len(alt.seqs) == 1 and len(alt.seqs[0].items) == 1:
        item = alt.seqs[0].items[0]
        if isinstance(item.atom, Group) and item.quantifier is None:
            return item.atom.alt
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
    return any(
        isinstance(it.atom, Group) and len(it.atom.alt.seqs) > 1
        for it in items
    )


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


# ── GbnfClassifier ───────────────────────────────────────────────────


class GbnfClassifier:
    """Implements RuleClassifier[Rule]."""

    def __init__(self) -> None:
        self._cache: dict[int, TypingLiteral["sequence", "alternation", "value_str"]] = {}

    def rule_name(self, rule: Rule) -> str:
        return rule.name

    def is_start_rule(self, rule: Rule) -> bool:
        return rule.name == "root"

    def kind(self, rule: Rule) -> TypingLiteral["sequence", "alternation", "value_str"]:
        cached = self._cache.get(id(rule))
        if cached is not None:
            return cached
        result = self._classify(rule)
        self._cache[id(rule)] = result
        return result

    def alternation_arm_nodes(self, rule: Rule) -> list[Sequence]:
        alt = _unwrap_group_alt(rule.body)
        return [_strip_ws(s) for s in alt.seqs if len(_strip_ws(s).items) > 0]

    def sequence_body(self, rule: Rule) -> Sequence:
        alt = _unwrap_group_alt(rule.body)
        paired = [(s, _strip_ws(s)) for s in alt.seqs if len(_strip_ws(s).items) > 0]
        if len(paired) == 1:
            return paired[0][0]
        # Falls back to first seq (kind=='sequence' implies single arm).
        return alt.seqs[0]

    def value_str_body(self, rule: Rule) -> Alternation:
        return _unwrap_group_alt(rule.body)

    def single_ruleref(self, arm: Sequence) -> str | None:
        return _single_ruleref_of(arm)

    # ── private classification ─────────────────────────────────────

    def _classify(self, rule: Rule) -> TypingLiteral["sequence", "alternation", "value_str"]:
        if _is_structurally_complex(rule.body):
            return "value_str"
        alt = _unwrap_group_alt(rule.body)
        paired = [(s, _strip_ws(s)) for s in alt.seqs if len(_strip_ws(s).items) > 0]
        if not paired:
            return "value_str"
        arms = [stripped for _, stripped in paired]
        if len(arms) > 1 and all(_is_pure_literal_seq(a) for a in arms):
            return "value_str"
        if (
            len(arms) == 1
            and len(arms[0].items) == 1
            and isinstance(arms[0].items[0].atom, Group)
            and arms[0].items[0].quantifier is None
            and all(_is_pure_literal_seq(_strip_ws(s)) for s in arms[0].items[0].atom.alt.seqs)
        ):
            return "value_str"
        if len(arms) == 1:
            full_seqs = alt.seqs
            has_any_rule_ref = any(
                any(isinstance(it.atom, RuleRef) for it in s.items) for s in full_seqs
            )
            if not has_any_rule_ref and _is_pure_literal_seq(arms[0]):
                return "value_str"
            return "sequence"
        return "alternation"


# ── GbnfConverter ────────────────────────────────────────────────────


def _to_canonical_regex_inner(group: Group) -> str:
    """Produce a canonical regex form for an inline group whose arms are pure literals."""
    arms: list[str] = []
    for seq in group.alt.seqs:
        parts: list[str] = []
        for it in seq.items:
            if isinstance(it.atom, Literal):
                q = it.quantifier or ""
                # Use re.escape on the *decoded* canonical string.
                parts.append(re.escape(decode_gbnf_escapes(it.atom.value)) + q)
            elif isinstance(it.atom, CharClass):
                q = it.quantifier or ""
                parts.append(it.atom.pattern + q)  # canonical POSIX already
            elif isinstance(it.atom, Group):
                q = it.quantifier or ""
                parts.append(_to_canonical_regex_inner(it.atom) + q)
        arms.append("".join(parts))
    body = "|".join(arms)
    return f"({body})" if len(arms) > 1 else body


def _build_inline_regex(group: Group, min_: int, max_: int | None) -> InlineRegexAtom:
    return InlineRegexAtom(
        canonical=_to_canonical_regex_inner(group),
        min=min_,
        max=max_,
    )


class GbnfConverter:
    """Implements SequenceConverter[Rule]."""

    def value_str_atoms(self, body: Alternation) -> list[Atom]:
        items: list[Atom] = []
        for seq in body.seqs:
            for it in seq.items:
                if isinstance(it.atom, CharClass):
                    lo, hi = quantifier_to_bounds(it.quantifier)
                    items.append(CharClassAtom(
                        pattern=it.atom.pattern,  # GBNF bracket text == canonical POSIX (ASCII subset)
                        min=lo, max=hi,
                    ))
                elif isinstance(it.atom, Literal):
                    decoded = decode_gbnf_escapes(it.atom.value)
                    if it.quantifier is not None:
                        lo, hi = quantifier_to_bounds(it.quantifier)
                        items.append(QuantifiedLiteralAtom(value=decoded, min=lo, max=hi))
                    else:
                        items.append(LiteralAtom(value=decoded))
                elif isinstance(it.atom, Group):
                    lo, hi = quantifier_to_bounds(it.quantifier)
                    items.append(_build_inline_regex(it.atom, lo, hi))
        return items

    def sequence_atoms(
        self,
        body: Sequence,
        parent_class_name: str,
        helpers: HelperRuleRegistry,
    ) -> list[Atom]:
        atoms: list[Atom] = []
        for item in body.items:
            if isinstance(item.atom, Literal):
                decoded = decode_gbnf_escapes(item.atom.value)
                if item.quantifier is not None:
                    lo, hi = quantifier_to_bounds(item.quantifier)
                    atoms.append(QuantifiedLiteralAtom(value=decoded, min=lo, max=hi))
                else:
                    atoms.append(LiteralAtom(value=decoded))
            elif isinstance(item.atom, CharClass):
                lo, hi = quantifier_to_bounds(item.quantifier)
                atoms.append(CharClassAtom(
                    pattern=item.atom.pattern,  # GBNF bracket text == canonical POSIX (ASCII subset)
                    min=lo, max=hi,
                ))
            elif isinstance(item.atom, RuleRef):
                lo, hi = quantifier_to_bounds(item.quantifier)
                atoms.append(RuleRefAtom(rule_name=item.atom.name, min=lo, max=hi))
            elif isinstance(item.atom, Group):
                atoms.extend(self._convert_group(item, parent_class_name, helpers))
        return atoms

    def _convert_group(
        self,
        item: Item,
        parent_class_name: str,
        helpers: HelperRuleRegistry,
    ) -> list[Atom]:
        group = cast(Group, item.atom)
        lo, hi = quantifier_to_bounds(item.quantifier)
        inner_arms = [_strip_ws(s) for s in group.alt.seqs if len(_strip_ws(s).items) > 0]

        if all(_is_pure_literal_seq(arm) for arm in inner_arms):
            return [_build_inline_regex(group, lo, hi)]

        if (
            item.quantifier is None
            and len(inner_arms) > 1
            and all(_single_ruleref_of(a) is not None for a in inner_arms)
        ):
            arm_names = [cast(str, _single_ruleref_of(a)) for a in inner_arms]
            return [InlineAlternationAtom(arm_rule_names=arm_names)]

        if item.quantifier is None and len(inner_arms) == 1:
            return self.sequence_atoms(inner_arms[0], parent_class_name, helpers)

        helper_rule_name = helpers.reserve(f"{parent_class_name.lower()}-item")
        helper_class_name = to_pascal(helper_rule_name)
        helper_atoms = self.sequence_atoms(
            inner_arms[0] if inner_arms else Sequence([]),
            helper_class_name,
            helpers,
        )
        helper_fm = assign_field_names(helper_atoms)
        helpers.register(RuleSpec(
            rule_name=helper_rule_name,
            class_name=helper_class_name,
            parent_class_name="GrammarModel",
            kind="sequence",
            items=helper_atoms,
            field_map=helper_fm,
        ))
        return [RuleRefAtom(rule_name=helper_rule_name, min=lo, max=hi)]
```

- [ ] **Step 4: Run ast_to_ir tests — PASS.**

- [ ] **Step 5: Wire `GbnfParser.parse()` to return `list[RuleSpec]`.**

Edit `src/lexic/grammars/gbnf/parser.py`:

```python
from lexic.grammars.gbnf.ast_to_ir import GbnfClassifier, GbnfConverter
from lexic.ir import IRBuilder, RuleSpec

# ... (existing parse_gbnf function unchanged)

class GbnfParser:
    def parse(self, text: str) -> list[RuleSpec]:
        rules = parse_gbnf(text)
        return IRBuilder(GbnfClassifier(), GbnfConverter()).build(rules)
```

Update the `FlavourParser` reference at the top of the file: replace `from lexic.grammars.flavours import FlavourParser` with `from lexic.ir import FlavourParser`.

- [ ] **Step 6: Update `codegen/__init__.py` — drop `IRBuilder` call.**

```python
def build_classes_and_specs(
    text: str, *, stem: str, flavour: str = "gbnf"
) -> tuple[dict[str, type], list[RuleSpec]]:
    adapter = get_adapter(flavour)
    specs = adapter.parser.parse(text)  # already list[RuleSpec]
    classes = _emit_and_load_module(specs, stem, source=None)
    return classes, specs
```

Remove the `from lexic.codegen.ir_builder import IRBuilder` line.

- [ ] **Step 7: Run the full pytest suite.**

```bash
uv run pytest tests/ -q
```

Expected: existing GBNF tests still pass because the new pipeline produces equivalent specs. **One known break:** `LiteralAtom.value` is now canonical (decoded), which means downstream consumers in `parsing/lark_builder.py`, `parsing/transformer/build_transformer.py`, and `runtime/base.py` that still call `decode_gbnf_escapes(atom.value)` will double-decode. Fix in this same task before committing.

- [ ] **Step 8: Remove redundant `decode_gbnf_escapes` calls from downstream consumers.**

Edit `src/lexic/codegen/lark_builder.py`. In `_atom_to_lark`:

```python
def _atom_to_lark(atom) -> str:
    if isinstance(atom, LiteralAtom):
        # LiteralAtom.value is canonical Python from GbnfConverter — no decode here.
        decoded = atom.value
        if any(c in decoded for c in "\n\t\r"):
            # Emit as regex so Lark handles control chars correctly.
            regex = ""
            for ch in decoded:
                if ch == "\n":   regex += "\\n"
                elif ch == "\t": regex += "\\t"
                elif ch == "\r": regex += "\\r"
                elif ch in r"\.^$*+?{}[]|()": regex += "\\" + ch
                else: regex += ch
            regex = _escape_lark_regex(regex)
            return f"/{regex}/"
        escaped = decoded.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    # ... CharClassAtom, RuleRefAtom unchanged
    if isinstance(atom, QuantifiedLiteralAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        decoded = atom.value  # canonical — no decode
        escaped = decoded.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"{q}'
    # ...
```

Drop the `from lexic.grammars.gbnf.adapter import decode_gbnf_escapes` import.

Edit `src/lexic/codegen/transformer/build_transformer.py`:
- Drop the `decode_gbnf_escapes` import.
- Replace `decode_gbnf_escapes(a.value)` and `decode_gbnf_escapes(atom.value)` with the bare `value`.

Edit `src/lexic/base.py`:
- Drop the `decode_gbnf_escapes` import.
- Replace `decoded = decode_gbnf_escapes(atom.value)` with `decoded = atom.value`.

Edit `src/lexic/grammars/gbnf/emitter.py`:
- Add `from lexic.grammars.gbnf.adapter import encode_gbnf_escapes`.
- In the `LiteralAtom` and `QuantifiedLiteralAtom` branches of `_atom_to_gbnf`, wrap value with `encode_gbnf_escapes` before emitting:
  ```python
  if isinstance(atom, LiteralAtom):
      return f'"{encode_gbnf_escapes(atom.value)}"'
  ```
  ```python
  if isinstance(atom, QuantifiedLiteralAtom):
      q = bounds_to_quantifier(atom.min, atom.max)
      return f'"{encode_gbnf_escapes(atom.value)}"{q}'
  ```

- [ ] **Step 9: Run full suite — green.**

```bash
uv run pytest tests/ -q
```

- [ ] **Step 10: Delete the old codegen modules.**

```bash
git rm src/lexic/codegen/ir_builder.py
git rm src/lexic/codegen/classify.py
git rm src/lexic/codegen/seq_to_atoms.py
git rm src/lexic/codegen/ast_utils.py
git rm tests/unit/lexic/codegen/test_ir_builder.py
git rm tests/unit/lexic/codegen/test_classify.py
git rm tests/unit/lexic/codegen/test_seq_to_atoms.py
git rm tests/unit/lexic/codegen/test_ast_utils.py
```

- [ ] **Step 11: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add -A
git commit -m "refactor(grammars/gbnf): GbnfClassifier+GbnfConverter; canonical Python literals at parse time

- Parser returns list[RuleSpec] via the generic IRBuilder.
- LiteralAtom.value and QuantifiedLiteralAtom.value are canonical Python
  (escapes decoded by GbnfConverter); downstream consumers stop decoding.
- GbnfEmitter calls encode_gbnf_escapes on emit.
- codegen/{ir_builder,classify,seq_to_atoms,ast_utils}.py deleted."
```

---

## Task 6: Slim `GbnfEmitter`

Replace `grammars/gbnf/emitter.py` with `grammars/gbnf/emit.py` extending `FlavourEmitter` ABC. Inherits all generic algorithms; declares only syntax constants + `encode` override.

**Files:**
- Create: `src/lexic/grammars/gbnf/emit.py`
- Delete: `src/lexic/grammars/gbnf/emitter.py`
- Create: `tests/unit/lexic/grammars/gbnf/test_emit.py`
- Delete: `tests/unit/lexic/grammars/gbnf/test_emitter.py`
- Modify: `src/lexic/grammars/gbnf/adapter.py` (import path)
- Modify: `src/lexic/grammars/gbnf/__init__.py` (re-export)

- [ ] **Step 1: Write failing tests.**

Create `tests/unit/lexic/grammars/gbnf/test_emit.py`:

```python
"""GbnfEmitter — slim subclass of FlavourEmitter; canonical IR → GBNF text."""
from __future__ import annotations

from lexic.grammars.gbnf.adapter import GbnfEscapes
from lexic.grammars.gbnf.emit import GbnfEmitter
from lexic.ir import (
    AlternationAtom, CharClassAtom, LiteralAtom, RuleRefAtom, RuleSpec,
)


def _emitter():
    return GbnfEmitter(escapes=GbnfEscapes())


def test_emit_literal_quotes_and_encodes():
    spec = RuleSpec(
        rule_name="r", class_name="R", parent_class_name="GrammarModel",
        kind="value_str", items=[LiteralAtom(value="hi")], field_map={},
    )
    assert _emitter().emit_rule(spec) == 'r ::= "hi"'


def test_emit_literal_with_newline_encodes_to_backslash_n():
    spec = RuleSpec(
        rule_name="r", class_name="R", parent_class_name="GrammarModel",
        kind="value_str", items=[LiteralAtom(value="\n")], field_map={},
    )
    assert _emitter().emit_rule(spec) == 'r ::= "\\n"'


def test_emit_charclass_with_quantifier():
    spec = RuleSpec(
        rule_name="num", class_name="Num", parent_class_name="GrammarModel",
        kind="value_str", items=[CharClassAtom("[0-9]", 1, None)], field_map={},
    )
    assert _emitter().emit_rule(spec) == "num ::= [0-9]+"


def test_emit_full_grammar_appends_trailing_newline():
    spec = RuleSpec(
        rule_name="root", class_name="Root", parent_class_name="GrammarModel",
        kind="sequence", items=[RuleRefAtom("expr", 1, 1)], field_map={"expr": 0},
    )
    out = _emitter().emit([spec])
    assert out.endswith("\n")
    assert "root ::= expr" in out


def test_emit_alternation_uses_pipe_separator():
    spec = RuleSpec(
        rule_name="t", class_name="T", parent_class_name="GrammarModel",
        kind="alternation",
        items=[AlternationAtom(arm_rule_names=["a", "b"])],
        field_map={},
    )
    assert _emitter().emit_rule(spec) == "t ::= a | b"
```

- [ ] **Step 2: Create `src/lexic/grammars/gbnf/emit.py`.**

```python
"""GbnfEmitter — slim FlavourEmitter subclass for GBNF surface syntax."""

from __future__ import annotations

from lexic.ir.emit import FlavourEmitter


class GbnfEmitter(FlavourEmitter):
    """GBNF flavour emitter.

    The FlavourEmitter defaults already match GBNF (rule_separator='::=',
    alt_separator=' | ', quote_char='"', wrap_group='(...)') and the
    default render_charclass / render_inline_regex are identity, which is
    correct for ASCII GBNF bracket and inline-regex syntax today.

    The escape codec is injected by the caller (typically GbnfAdapter,
    which holds the canonical GbnfEscapes() instance — see Task 11).
    """

    @property
    def supports(self) -> frozenset[str]:
        return frozenset({
            "literal", "char_class", "negated_class", "quantifier",
            "alternation", "non_capturing_group", "unicode_escape",
        })
```

`GbnfEmitter` no longer overrides `__init__`, `render_charclass`, or `render_inline_regex` — `FlavourEmitter.__init__(escapes, handlers)` is the only constructor.  Anyone instantiating `GbnfEmitter` directly must now pass `escapes=GbnfEscapes()` (or get an emitter via `GbnfAdapter().emitter`, which does this for them).  Update existing test code that does `GbnfEmitter()` accordingly.

- [ ] **Step 3: Run new emit tests — PASS.**

- [ ] **Step 4: Update import paths.**

`src/lexic/grammars/gbnf/__init__.py`:

```python
"""GBNF flavour — public surface."""
from lexic.grammars.gbnf.adapter import GbnfAdapter
from lexic.grammars.gbnf.emit import GbnfEmitter
from lexic.grammars.gbnf.parser import GbnfParser

__all__ = ["GbnfAdapter", "GbnfEmitter", "GbnfParser"]
```

`src/lexic/grammars/gbnf/adapter.py`:

```python
from lexic.grammars.gbnf.emit import GbnfEmitter  # was emitter
```

Anywhere else `from lexic.grammars.gbnf.emitter import` appears (`base.py`, `compile.py`, tests), replace with `from lexic.grammars.gbnf.emit import`.

```bash
grep -rl "lexic.grammars.gbnf.emitter" src/ tests/ | xargs sed -i \
    's|lexic.grammars.gbnf.emitter|lexic.grammars.gbnf.emit|g'
```

- [ ] **Step 5: Delete the old `emitter.py` and its tests.**

```bash
git rm src/lexic/grammars/gbnf/emitter.py
git rm tests/unit/lexic/grammars/gbnf/test_emitter.py
```

- [ ] **Step 6: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add -A
git commit -m "refactor(grammars/gbnf): slim GbnfEmitter extending FlavourEmitter ABC

GbnfEmitter is now ~25 lines: supports declaration + escape codec wiring
+ render_charclass/render_inline_regex overrides. emit/emit_rule/_emit_body
inherited from FlavourEmitter; canonical-atom handlers default to
DEFAULT_HANDLERS parameterised by quote_char/alt_separator/etc."
```

---

## Task 7: Drop `InlineRegexAtom.gbnf` — single canonical regex form

Rename `regex` → `canonical`; drop `gbnf` field; update all consumers in one coordinated commit.

**Files:**
- Modify: `src/lexic/ir/atoms.py`
- Modify: `src/lexic/grammars/gbnf/ast_to_ir.py` (constructor call)
- Modify: `src/lexic/codegen/lark_builder.py` (consumer)
- Modify: `src/lexic/grammars/gbnf/emit.py` (consumer — uses default handler now via canonical)
- Modify: `src/lexic/ir/naming.py` (consumer — `_inline_regex_field_name` reads `gbnf`; switch to `canonical`)
- Modify: `tests/unit/lexic/ir/test_atoms.py` (drop `gbnf` field references)
- Modify: any other test that constructs `InlineRegexAtom`

- [ ] **Step 1: Update the dataclass.**

Edit `src/lexic/ir/atoms.py`:

```python
@dataclass(frozen=True)
class InlineRegexAtom:
    """An inlined group represented as a canonical regex string.

    `canonical` is a regex form usable by Lark (after escape) and by GBNF
    emit (per-flavour render_inline_regex maps it back to the surface form).
    """

    canonical: str
    min: int
    max: int | None
```

- [ ] **Step 2: Update the GBNF converter constructor.**

In `src/lexic/grammars/gbnf/ast_to_ir.py`, the existing `_build_inline_regex` already constructs `InlineRegexAtom(canonical=..., ...)`. Confirm — no further change needed.

- [ ] **Step 3: Update Lark consumer.**

In `src/lexic/codegen/lark_builder.py:_atom_to_lark`, the `InlineRegexAtom` branch:

```python
if isinstance(atom, InlineRegexAtom):
    q = bounds_to_quantifier(atom.min, atom.max)
    safe = _escape_lark_regex(atom.canonical)
    return f"/{safe}/{q}"
```

Change `atom.regex` → `atom.canonical`.

- [ ] **Step 4: Update naming.**

Edit `src/lexic/ir/naming.py`. Rename and re-key:

```python
def _inline_regex_field_name(canonical: str) -> str:
    body = canonical.strip()
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    first_arm = body.split("|")[0].strip()
    sanitized = re.sub(r"[^a-zA-Z0-9]", "_", first_arm).strip("_").lower()
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")[:12]
    if not sanitized:
        return "inline"
    if sanitized[0].isdigit():
        sanitized = ("val_" + sanitized)[:12].strip("_")
    return sanitized
```

In `assign_field_names`:

```python
elif isinstance(atom, InlineRegexAtom):
    field_map[unique(_inline_regex_field_name(atom.canonical))] = i
```

- [ ] **Step 5: Update any test that constructs `InlineRegexAtom` with `regex`/`gbnf`.**

```bash
grep -rn "InlineRegexAtom(" src/ tests/
```

For each result, replace `regex=...` and remove `gbnf=...`. Single canonical positional or `canonical=...` keyword.

- [ ] **Step 6: Run full suite + ruff. Commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add -A
git commit -m "refactor(ir): InlineRegexAtom carries a single canonical regex string

Drop the GBNF flavour leak (regex+gbnf fields). All consumers use
atom.canonical; per-flavour emit translates via render_inline_regex."
```

---

## Task 8: `parsing/` package — move + handler dispatch + 3 ws fixes

Move `codegen/lark_builder.py` and the `transformer/` subpackage into `parsing/`. Replace the `_atom_to_lark` `isinstance` cascade with a handler-table dispatch keyed on atom type. Replace the `ws_method` special case in `build_transformer` with the generic `value_str` path. Replace the `is_ws` branch in `RuleRefBuilder` with a `field_name in spec.non_semantic_fields` check. Remove the `if spec.rule_name == "ws": continue` line in `LarkBuilder.build_grammar` and adapt the canonical CharClass Lark handler to inline `+/?/*` quantifiers when expressible (so the generic emit produces `/[ \t\n]+/`).

**Files:**
- Create: `src/lexic/parsing/__init__.py`
- Create: `src/lexic/parsing/handlers/__init__.py`
- Create: `src/lexic/parsing/handlers/lark.py`
- Create: `src/lexic/parsing/handlers/transform.py`
- Move: `src/lexic/codegen/lark_builder.py` → `src/lexic/parsing/lark_builder.py` (and rewrite to handler-dispatch)
- Move: `src/lexic/codegen/transformer/build_transformer.py` → `src/lexic/parsing/transformer.py`
- Move: `src/lexic/codegen/transformer/builders.py` → `src/lexic/parsing/transformer_builders.py`
- Move: `src/lexic/codegen/transformer/context.py` → `src/lexic/parsing/transformer_context.py`
- Delete: `src/lexic/codegen/transformer/registry.py` (replaced by handler-table dispatch)
- Delete: `src/lexic/codegen/transformer/__init__.py`
- Test mirror moves
- Modify: `src/lexic/compile.py` (import path)

This task is long — split execution across ~12 steps. Follow the order strictly so tests stay green at each commit.

- [ ] **Step 1: Create the `parsing/` package skeleton.**

```bash
mkdir -p src/lexic/parsing/handlers
mkdir -p tests/unit/lexic/parsing
```

Create empty `src/lexic/parsing/__init__.py` and `src/lexic/parsing/handlers/__init__.py`.
Create empty `tests/unit/lexic/parsing/__init__.py`.

- [ ] **Step 2: Write canonical Lark atom handlers.**

Create `src/lexic/parsing/handlers/lark.py`:

```python
"""Canonical-atom handlers for LarkBuilder.

Each handler returns the Lark grammar fragment for one atom. The handlers
inline `+/?/*` quantifiers into the regex when expressible, so a generic
`/[ \\t\\n]/+` becomes `/[ \\t\\n]+/` and the special-cased `ws : /[ \\t\\n]+/`
line that LarkBuilder used to hardcode is no longer needed.
"""

from __future__ import annotations

from lexic.ir import (
    AlternationAtom,
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.utils.names import to_lark_name
from lexic.utils.quantifiers import bounds_to_quantifier


def _escape_lark_regex(s: str) -> str:
    return s.replace("/", "\\/")


def _regex_quantifier_inline(lo: int, hi: int | None) -> str:
    """Return a regex-internal quantifier (?, +, *, {m,n}) — empty if none."""
    if lo == 1 and hi == 1:
        return ""
    if lo == 0 and hi == 1:
        return "?"
    if lo == 1 and hi is None:
        return "+"
    if lo == 0 and hi is None:
        return "*"
    if hi is None:
        return f"{{{lo},}}"
    return f"{{{lo},{hi}}}"


def lark_literal(atom: LiteralAtom, ctx) -> str:
    decoded = atom.value
    if any(c in decoded for c in "\n\t\r"):
        regex = ""
        for ch in decoded:
            if ch == "\n":   regex += "\\n"
            elif ch == "\t": regex += "\\t"
            elif ch == "\r": regex += "\\r"
            elif ch in r"\.^$*+?{}[]|()": regex += "\\" + ch
            else: regex += ch
        return f"/{_escape_lark_regex(regex)}/"
    escaped = decoded.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def lark_quantified_literal(atom: QuantifiedLiteralAtom, ctx) -> str:
    q = bounds_to_quantifier(atom.min, atom.max)
    escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"{q}'


def lark_charclass(atom: CharClassAtom, ctx) -> str:
    """Inline the quantifier into the regex when expressible.

    Inlining is what lets the generic emit produce `/[ \\t\\n]+/` from
    CharClassAtom("[ \\t\\n]", 1, None) — the same string the old
    LarkBuilder hardcoded as a special case for the ws rule.
    """
    safe = _escape_lark_regex(atom.pattern)
    return f"/{safe}{_regex_quantifier_inline(atom.min, atom.max)}/"


def lark_ruleref(atom: RuleRefAtom, ctx) -> str:
    name = to_lark_name(atom.rule_name)
    q = bounds_to_quantifier(atom.min, atom.max)
    return f"{name}{q}"


def lark_alternation(atom: AlternationAtom, ctx) -> str:
    return "(" + " | ".join(to_lark_name(n) for n in atom.arm_rule_names) + ")"


def lark_inline_alternation(atom: InlineAlternationAtom, ctx) -> str:
    return "(" + " | ".join(to_lark_name(n) for n in atom.arm_rule_names) + ")"


def lark_inline_regex(atom: InlineRegexAtom, ctx) -> str:
    safe = _escape_lark_regex(atom.canonical)
    q = bounds_to_quantifier(atom.min, atom.max)
    return f"/{safe}/{q}"


CANONICAL_LARK_HANDLERS: dict[type, object] = {
    LiteralAtom: lark_literal,
    QuantifiedLiteralAtom: lark_quantified_literal,
    CharClassAtom: lark_charclass,
    RuleRefAtom: lark_ruleref,
    AlternationAtom: lark_alternation,
    InlineAlternationAtom: lark_inline_alternation,
    InlineRegexAtom: lark_inline_regex,
}
```

Re-export from `src/lexic/parsing/handlers/__init__.py`:

```python
from lexic.parsing.handlers.lark import CANONICAL_LARK_HANDLERS

__all__ = ["CANONICAL_LARK_HANDLERS"]
```

- [ ] **Step 3: Tests for canonical Lark handlers — including charclass-quantifier inlining.**

Create `tests/unit/lexic/parsing/test_handlers_lark.py`:

```python
"""Canonical Lark atom handlers — including charclass-quantifier inlining (D2)."""
from __future__ import annotations

from lexic.ir import CharClassAtom, LiteralAtom, RuleRefAtom
from lexic.parsing.handlers.lark import (
    CANONICAL_LARK_HANDLERS, lark_charclass, lark_literal, lark_ruleref,
)


def test_lark_literal_quotes_simple_string():
    assert lark_literal(LiteralAtom(value="hi"), None) == '"hi"'


def test_lark_literal_emits_regex_for_control_char():
    assert lark_literal(LiteralAtom(value="\n"), None) == "/\\n/"


def test_lark_charclass_inlines_plus_quantifier():
    """The fix that retires the `ws : /[ \\t\\n]+/` special case."""
    assert lark_charclass(CharClassAtom("[ \\t\\n]", 1, None), None) == "/[ \\t\\n]+/"


def test_lark_charclass_inlines_optional():
    assert lark_charclass(CharClassAtom("[a-z]", 0, 1), None) == "/[a-z]?/"


def test_lark_charclass_required_one_no_quantifier():
    assert lark_charclass(CharClassAtom("[0-9]", 1, 1), None) == "/[0-9]/"


def test_lark_ruleref_with_optional_emits_question_mark():
    """The fix that retires the `if atom.rule_name == 'ws'` special case."""
    assert lark_ruleref(RuleRefAtom("ws", 0, 1), None) == "ws?"


def test_canonical_lark_handlers_includes_all_canonical_atom_types():
    expected = {"LiteralAtom", "QuantifiedLiteralAtom", "CharClassAtom",
                "RuleRefAtom", "AlternationAtom", "InlineAlternationAtom",
                "InlineRegexAtom"}
    assert {t.__name__ for t in CANONICAL_LARK_HANDLERS} == expected
```

- [ ] **Step 4: Run handler tests — PASS.**

- [ ] **Step 5: Move + rewrite `LarkBuilder` with handler dispatch.**

```bash
git mv src/lexic/codegen/lark_builder.py src/lexic/parsing/lark_builder.py
git mv tests/unit/lexic/codegen/test_lark_builder.py tests/unit/lexic/parsing/test_lark_builder.py
```

Replace the contents of `src/lexic/parsing/lark_builder.py`:

```python
"""LarkBuilder: list[RuleSpec] → Lark grammar string + start rule.

Flavour-agnostic. Atom rendering goes through a handler table; flavours
that introduce new atom types pass extended handlers via the adapter.
"""

from __future__ import annotations

from lark import Transformer

from lexic.ir import (
    AlternationAtom, Atom, LiteralAtom, RuleSpec,
)
from lexic.parsing.handlers.lark import CANONICAL_LARK_HANDLERS
from lexic.utils.names import to_lark_name


class LarkBuilder:
    """Builds a Lark grammar string from a list of RuleSpec."""

    def __init__(
        self,
        specs: list[RuleSpec],
        *,
        handlers: dict[type, object] | None = None,
    ) -> None:
        self._specs = specs
        self._by_rule = {s.rule_name: s for s in specs}
        self._handlers = handlers if handlers is not None else dict(CANONICAL_LARK_HANDLERS)

    def build_grammar(self) -> tuple[str, str]:
        """Return (lark_grammar_str, start_rule_name)."""
        lines = [self._spec_to_lark_rule(s) for s in self._specs]
        start = to_lark_name(self._specs[0].rule_name)
        return "\n".join(lines), start

    def _render_atom(self, atom: Atom) -> str:
        try:
            return self._handlers[type(atom)](atom, self)
        except KeyError as exc:
            raise NotImplementedError(
                f"LarkBuilder has no handler for {type(atom).__name__}"
            ) from exc

    def _spec_to_lark_rule(self, spec: RuleSpec) -> str:
        lark_name = to_lark_name(spec.rule_name)
        if spec.kind == "value_str":
            if spec.items and all(isinstance(a, LiteralAtom) for a in spec.items):
                body = " | ".join(self._render_atom(a) for a in spec.items)
            else:
                body = " ".join(self._render_atom(a) for a in spec.items) or '""'
            return f"{lark_name} : {body}"
        if spec.kind == "alternation":
            alt = spec.items[0] if spec.items else None
            if isinstance(alt, AlternationAtom):
                arms = " | ".join(to_lark_name(n) for n in alt.arm_rule_names)
                return f"{lark_name} : {arms}"
            return f"{lark_name} :"
        body = " ".join(self._render_atom(a) for a in spec.items)
        return f"{lark_name} : {body}" if body.strip() else f"{lark_name} :"
```

The two ws special-cases are gone:
1. The `if atom.rule_name == "ws": return "ws?"` is replaced by `lark_ruleref` which uses the generic quantifier (IRBuilder set `min=0` on ws RuleRefAtoms).
2. The `if spec.rule_name == "ws": continue` + hardcoded `ws : /[ \t\n]+/` is replaced by `lark_charclass` inlining the `+` quantifier so the generic emit produces the same string.

- [ ] **Step 6: Update `src/lexic/compile.py` import.**

```bash
sed -i 's|from lexic.codegen.lark_builder|from lexic.parsing.lark_builder|g' src/lexic/compile.py
```

- [ ] **Step 7: Run full suite. Commit lark mover.**

```bash
uv run pytest tests/ -q
git add -A
git commit -m "refactor(parsing): move LarkBuilder; handler-dispatch atom rendering; remove ws special cases

LarkBuilder takes a {type → handler} table seeded with CANONICAL_LARK_HANDLERS.
ws fix:
- if atom.rule_name == 'ws': return 'ws?'  → IRBuilder min=0 + lark_ruleref
- if spec.rule_name == 'ws': continue + hardcoded ws regex
  → lark_charclass inlines the quantifier into the regex"
```

- [ ] **Step 8: Move the transformer subpackage.**

```bash
git mv src/lexic/codegen/transformer/build_transformer.py src/lexic/parsing/transformer.py
git mv src/lexic/codegen/transformer/builders.py src/lexic/parsing/transformer_builders.py
git mv src/lexic/codegen/transformer/context.py src/lexic/parsing/transformer_context.py
git rm src/lexic/codegen/transformer/registry.py
git rm src/lexic/codegen/transformer/__init__.py
git mv tests/unit/lexic/codegen/transformer/test_build_transformer.py tests/unit/lexic/parsing/test_transformer.py
git mv tests/unit/lexic/codegen/transformer/test_builders.py tests/unit/lexic/parsing/test_transformer_builders.py
git mv tests/unit/lexic/codegen/transformer/test_context.py tests/unit/lexic/parsing/test_transformer_context.py
git rm tests/unit/lexic/codegen/transformer/test_registry.py
git rm tests/unit/lexic/codegen/transformer/__init__.py
```

Update internal imports in the moved files:

```bash
grep -rl "lexic.codegen.transformer" src/ tests/ | xargs sed -i \
    -e 's|lexic.codegen.transformer.build_transformer|lexic.parsing.transformer|g' \
    -e 's|lexic.codegen.transformer.builders|lexic.parsing.transformer_builders|g' \
    -e 's|lexic.codegen.transformer.context|lexic.parsing.transformer_context|g' \
    -e 's|lexic.codegen.transformer|lexic.parsing|g'
```

- [ ] **Step 9: Replace the registry mechanism with a handler-table parameter.**

In `src/lexic/parsing/transformer.py`, the existing `build_transformer(specs, classes)` uses a registry. Replace its body with explicit handler-table dispatch, accepting the table as a kwarg. Old registry imports go.

The simplest change: pass a `transform_handlers: dict[type, Callable] | None = None` parameter; if `None`, use `CANONICAL_TRANSFORM_HANDLERS` from `parsing/handlers/transform.py`. The handler signature is `(atom, ctx) -> object`.

Create `src/lexic/parsing/handlers/transform.py`:

```python
"""Canonical-atom handlers for build_transformer's per-atom routing."""

from __future__ import annotations

from lexic.ir import (
    AlternationAtom, CharClassAtom, InlineAlternationAtom,
    InlineRegexAtom, LiteralAtom, QuantifiedLiteralAtom, RuleRefAtom,
)
from lexic.parsing.transformer_builders import (
    AbstractAlternationBuilder,
    CharClassFieldBuilder,
    InlineAlternationBuilder,
    InlineRegexBuilder,
    LiteralSkipBuilder,
    QuantifiedLiteralBuilder,
    RuleRefBuilder,
)


CANONICAL_TRANSFORM_HANDLERS: dict[type, object] = {
    LiteralAtom:           LiteralSkipBuilder(),
    CharClassAtom:         CharClassFieldBuilder(),
    QuantifiedLiteralAtom: QuantifiedLiteralBuilder(),
    InlineRegexAtom:       InlineRegexBuilder(),
    RuleRefAtom:           RuleRefBuilder(),
    AlternationAtom:       AbstractAlternationBuilder(),
    InlineAlternationAtom: InlineAlternationBuilder(),
}
```

Add to `src/lexic/parsing/handlers/__init__.py`:

```python
from lexic.parsing.handlers.lark import CANONICAL_LARK_HANDLERS
from lexic.parsing.handlers.transform import CANONICAL_TRANSFORM_HANDLERS

__all__ = ["CANONICAL_LARK_HANDLERS", "CANONICAL_TRANSFORM_HANDLERS"]
```

Update `build_transformer` in `src/lexic/parsing/transformer.py`. In `_build_instance`, replace the call site `b = builder_for(atom)` (was using a registry singleton) with `b = handlers[type(atom)]`. Add `handlers=None` parameter to `build_transformer` and `_build_instance`; default to `CANONICAL_TRANSFORM_HANDLERS`.

- [ ] **Step 10: Remove the `ws_method` special case from `build_transformer`.**

In `src/lexic/parsing/transformer.py`, delete lines that define `ws_method` and assign `methods["ws"] = ws_method`. Delete the `if spec.rule_name == "ws": continue` line. The generic `value_str` path already builds `Ws(value=text)` if a `Ws` class exists; that's the same behaviour.

- [ ] **Step 11: Generalise `RuleRefBuilder` ws branch.**

In `src/lexic/parsing/transformer_builders.py`, replace `is_ws = atom.rule_name == "ws"` with a `field_name in spec.non_semantic_fields` check. Since `RuleRefBuilder.build` doesn't currently receive the `RuleSpec`, extend `BuildContext` to carry it. Edit `src/lexic/parsing/transformer_context.py`:

```python
@dataclass(frozen=True)
class BuildContext:
    spec: RuleSpec  # already present
    children: tuple
    hints: dict
    cursor: int
    # ...
```

(Confirm `spec` is already present in the existing `BuildContext`. If not, add it; the build orchestrator at `_build_instance` already constructs `BuildContext(spec=spec, ...)`.)

Replace `is_ws = atom.rule_name == "ws"` with:

```python
def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
    raw_hint = ctx.hints.get(field_name)
    hint = _unwrap_hint(raw_hint)
    is_trivia = field_name in ctx.spec.non_semantic_fields
    # ... (rest of the method, replacing every `is_ws` with `is_trivia`)
```

The behaviour is unchanged for ws; the string match is gone.

- [ ] **Step 12: Run full suite. Commit transformer.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add -A
git commit -m "refactor(parsing): move transformer; handler-table dispatch; trivia via non_semantic_fields

- transformer/build_transformer.py → parsing/transformer.py
- transformer/builders.py → parsing/transformer_builders.py
- transformer/context.py → parsing/transformer_context.py
- registry.py replaced by CANONICAL_TRANSFORM_HANDLERS dict
- ws_method + 'if rule_name == \"ws\"' special case removed (generic value_str path)
- RuleRefBuilder.is_ws → field_name in spec.non_semantic_fields"
```

---

## Task 9: codegen handler dispatch

Move atom-level field-emission logic out of `ModelEmitter._render_atom_inline` (or wherever it lives) into per-atom handlers. `ModelEmitter` becomes a generic walker keyed on a handler table.

**Files:**
- Create: `src/lexic/codegen/handlers/__init__.py`
- Create: `src/lexic/codegen/handlers/atom_fields.py`
- Modify: `src/lexic/codegen/model_emitter.py`
- Create: `tests/unit/lexic/codegen/handlers/__init__.py`
- Create: `tests/unit/lexic/codegen/handlers/test_atom_fields.py`

- [ ] **Step 1: Read the current `model_emitter.py` to identify per-atom branches.**

```bash
uv run pytest tests/unit/lexic/codegen/test_model_emitter.py -q
```

Inspect the existing `model_emitter.py`. Atom-specific logic typically appears in: field type derivation (`_field_type_for(atom)`), default value derivation, constructor argument naming.

- [ ] **Step 2: Extract per-canonical-atom handlers.**

Create `src/lexic/codegen/handlers/atom_fields.py`. Each handler is a function `(atom, ctx) -> FieldDef` where `FieldDef` is a small dataclass capturing the field type, default, and any decorators ModelEmitter needs.

(Concrete handler bodies depend on the existing `ModelEmitter` code. Lift the logic verbatim into one function per atom type; `ctx` carries the per-rule symbol table the existing emitter already maintains.)

- [ ] **Step 3: Rewrite `ModelEmitter._render_atom_inline` (or equivalent) to dispatch via the handler table.**

```python
def __init__(self, specs, source, *, field_handlers=None):
    self._specs = specs
    self._source = source
    self._field_handlers = field_handlers if field_handlers is not None else dict(CANONICAL_FIELD_HANDLERS)

def _render_field(self, atom, ctx) -> FieldDef:
    return self._field_handlers[type(atom)](atom, ctx)
```

- [ ] **Step 4: Run codegen tests — PASS.**

```bash
uv run pytest tests/unit/lexic/codegen -q
```

- [ ] **Step 5: Commit.**

```bash
git add -A
git commit -m "refactor(codegen): handler-dispatch atom rendering in ModelEmitter

Per-atom field emission moves into codegen/handlers/atom_fields.py.
ModelEmitter takes a {type → handler} table seeded with
CANONICAL_FIELD_HANDLERS; flavour adapters merge in extensions."
```

---

## Task 10: `runtime/` package + per-module `__adapter__` + 2 ws fixes

Move `src/lexic/{base,parse,generate}.py` into `src/lexic/runtime/`. Add per-module `__adapter__` binding emitted by `ModelEmitter`. Replace `to_text`'s `isinstance` cascade with a handler-table lookup via `self.__class__.__module__.__adapter__`. Replace the `atom.rule_name == "ws"` check in `semantic_dump` with `RuleSpec.non_semantic_fields`.

**Files:**
- Move: `src/lexic/base.py` → `src/lexic/runtime/base.py`
- Move: `src/lexic/parse.py` → `src/lexic/runtime/parse.py`
- Move: `src/lexic/generate.py` → `src/lexic/runtime/generate.py`
- Test mirror moves
- Create: `src/lexic/runtime/__init__.py`
- Create: `src/lexic/runtime/handlers/__init__.py`
- Create: `src/lexic/runtime/handlers/to_text.py`
- Create: `src/lexic/runtime/handlers/generate.py`
- Modify: `src/lexic/__init__.py` (re-export GrammarModel/parse/generate from runtime/)
- Modify: `src/lexic/codegen/model_emitter.py` (emit `__adapter__ = ...` line)

- [ ] **Step 1: Create `runtime/` package skeleton.**

```bash
mkdir -p src/lexic/runtime/handlers
mkdir -p tests/unit/lexic/runtime
```

- [ ] **Step 2: Move base/parse/generate.**

```bash
git mv src/lexic/base.py src/lexic/runtime/base.py
git mv src/lexic/parse.py src/lexic/runtime/parse.py
git mv src/lexic/generate.py src/lexic/runtime/generate.py
git mv tests/unit/lexic/test_base.py tests/unit/lexic/runtime/test_base.py
git mv tests/unit/lexic/test_parse.py tests/unit/lexic/runtime/test_parse.py
git mv tests/unit/lexic/test_generate.py tests/unit/lexic/runtime/test_generate.py
touch src/lexic/runtime/__init__.py tests/unit/lexic/runtime/__init__.py
```

- [ ] **Step 3: Update import paths in moved + dependent files.**

```bash
grep -rl "from lexic.base\|from lexic.parse\|from lexic.generate" src/ tests/ | \
    xargs sed -i \
        -e 's|from lexic.base|from lexic.runtime.base|g' \
        -e 's|from lexic.parse|from lexic.runtime.parse|g' \
        -e 's|from lexic.generate|from lexic.runtime.generate|g'
```

Update `src/lexic/__init__.py`:

```python
"""Public surface — top-level re-exports."""
from lexic.runtime.base import GrammarModel
from lexic.runtime.parse import parse
from lexic.runtime.generate import generate

__all__ = ["GrammarModel", "parse", "generate"]
```

(Keep any other top-level exports that already exist.)

- [ ] **Step 4: Run full suite — PASS (move only; behaviour unchanged).**

```bash
uv run pytest tests/ -q
```

- [ ] **Step 5: Write the canonical to_text handlers.**

Create `src/lexic/runtime/handlers/to_text.py`:

```python
"""Canonical-atom handlers for GrammarModel.to_text.

Each handler returns the string contribution of one atom, given the
field value resolved by the runtime walker.
"""

from __future__ import annotations

from lexic.ir import (
    AlternationAtom, CharClassAtom, InlineAlternationAtom,
    InlineRegexAtom, LiteralAtom, QuantifiedLiteralAtom, RuleRefAtom,
)


def to_text_literal(atom: LiteralAtom, value, ctx) -> str:
    # value is None — literal contributes its own value (no field).
    return atom.value


def to_text_charclass(atom: CharClassAtom, value, ctx) -> str:
    if value is None:
        return ""
    return str(value) if not isinstance(value, list) else "".join(str(v) for v in value)


def to_text_quantified_literal(atom: QuantifiedLiteralAtom, value, ctx) -> str:
    if value is None or value == "":
        return ""
    return str(value)


def to_text_ruleref(atom: RuleRefAtom, value, ctx) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "".join(item.to_text() if hasattr(item, "to_text") else str(item)
                       for item in value)
    return value.to_text() if hasattr(value, "to_text") else str(value)


def to_text_alternation(atom: AlternationAtom, value, ctx) -> str:
    if value is None:
        return ""
    return value.to_text() if hasattr(value, "to_text") else str(value)


def to_text_inline_alternation(atom: InlineAlternationAtom, value, ctx) -> str:
    if value is None:
        return ""
    return value.to_text() if hasattr(value, "to_text") else str(value)


def to_text_inline_regex(atom: InlineRegexAtom, value, ctx) -> str:
    if value is None:
        return ""
    return str(value)


CANONICAL_TO_TEXT_HANDLERS: dict[type, object] = {
    LiteralAtom:           to_text_literal,
    CharClassAtom:         to_text_charclass,
    QuantifiedLiteralAtom: to_text_quantified_literal,
    RuleRefAtom:           to_text_ruleref,
    AlternationAtom:       to_text_alternation,
    InlineAlternationAtom: to_text_inline_alternation,
    InlineRegexAtom:       to_text_inline_regex,
}
```

- [ ] **Step 6: Add `runtime/handlers/generate.py`** with canonical generate handlers (mirror `runtime.generate`'s per-atom switch).

(Generate atom-level logic exists in the current `generate.py`. Lift each branch into a function; build `CANONICAL_GENERATE_HANDLERS`.)

- [ ] **Step 7: Update `runtime/handlers/__init__.py`.**

```python
from lexic.runtime.handlers.to_text import CANONICAL_TO_TEXT_HANDLERS
from lexic.runtime.handlers.generate import CANONICAL_GENERATE_HANDLERS

__all__ = ["CANONICAL_TO_TEXT_HANDLERS", "CANONICAL_GENERATE_HANDLERS"]
```

- [ ] **Step 8: Rewrite `GrammarModel.to_text` and `semantic_dump` (D2 fix).**

Edit `src/lexic/runtime/base.py`:

```python
"""GrammarModel: base class for all generated Pydantic models.

to_text uses lookup-at-call-time via the generated module's __adapter__.
semantic_dump consults RuleSpec.non_semantic_fields (no string match).
"""

from __future__ import annotations

import importlib
import sys
from typing import Any, ClassVar

from pydantic import BaseModel

from lexic.ir import LiteralAtom, RuleSpec
from lexic.runtime.handlers.to_text import CANONICAL_TO_TEXT_HANDLERS


def _adapter_for(cls: type) -> object:
    mod = sys.modules.get(cls.__module__)
    if mod is None:
        mod = importlib.import_module(cls.__module__)
    return getattr(mod, "__adapter__", None)


class GrammarModel(BaseModel):
    __grammar__: ClassVar[RuleSpec]

    def to_text(self) -> str:
        spec = self.__grammar__
        if spec.kind == "value_str":
            return str(getattr(self, "value", ""))
        if spec.kind == "alternation":
            raise NotImplementedError(
                f"{type(self).__name__} is abstract — call to_text() on a concrete subclass"
            )

        adapter = _adapter_for(type(self))
        handlers: dict[type, object] = dict(CANONICAL_TO_TEXT_HANDLERS)
        if adapter is not None:
            handlers.update(getattr(adapter, "to_text_handlers", {}))

        inv = {idx: name for name, idx in spec.field_map.items()}
        parts: list[str] = []
        for i, atom in enumerate(spec.items):
            if isinstance(atom, LiteralAtom):
                parts.append(atom.value)  # already canonical
                continue
            if i not in inv:
                continue
            value = getattr(self, inv[i], None)
            handler = handlers.get(type(atom))
            if handler is None:
                continue
            parts.append(handler(atom, value, self))
        return "".join(parts)

    def to_grammar(self, flavour: str = "gbnf") -> str:
        from lexic.grammars import get_adapter
        adapter = get_adapter(flavour)
        return adapter.emit([self.__grammar__]).rstrip("\n")

    def semantic_dump(self) -> dict[str, Any]:
        return self.model_dump(exclude=set(self.__grammar__.non_semantic_fields))
```

The two ws special-cases are gone:
- `decode_gbnf_escapes(atom.value)` removed (LiteralAtom.value canonical).
- `if isinstance(atom, RuleRefAtom) and atom.rule_name == "ws"` removed; uses `non_semantic_fields`.

- [ ] **Step 9: Make `ModelEmitter` emit `__adapter__ = ...` on the generated module.**

Edit `src/lexic/codegen/model_emitter.py`. Add an `adapter_import` parameter or build it from `flavour`. The emitted module's preamble adds:

```python
from lexic.grammars.gbnf.adapter import GbnfAdapter
__adapter__ = GbnfAdapter()
```

(Generalise: the flavour name comes from `build_classes_and_specs(flavour=...)`. Map flavour → import path: `gbnf` → `lexic.grammars.gbnf.adapter`, class `GbnfAdapter`. Hardcode the GBNF mapping in `ModelEmitter`; future flavours register via the adapter registry.)

A simple way: introduce an `__adapter__` source line in the generated preamble derived from `get_adapter(flavour)`'s class:

```python
adapter_cls = get_adapter(flavour).__class__
adapter_module = adapter_cls.__module__
adapter_name = adapter_cls.__name__
preamble += f"from {adapter_module} import {adapter_name}\n"
preamble += f"__adapter__ = {adapter_name}()\n"
```

- [ ] **Step 10: Run full suite — PASS.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 11: Commit.**

```bash
git add -A
git commit -m "refactor(runtime): runtime/ package + per-module __adapter__ + ws fixes (D2 sites 4+5)

- src/lexic/{base,parse,generate}.py → src/lexic/runtime/.
- ModelEmitter emits __adapter__ = <Adapter>() on each generated module.
- GrammarModel.to_text uses lookup-at-call-time via the module's __adapter__;
  CANONICAL_TO_TEXT_HANDLERS in runtime/handlers/to_text.py.
- semantic_dump uses RuleSpec.non_semantic_fields (no \"ws\" string match).
- decode_gbnf_escapes call removed from runtime/base.py."
```

---

## Task 11: GbnfAdapter full wiring + FlavourAdapter Protocol move + dead-file cleanup

`GbnfAdapter` exposes the four handler-extension dicts (empty for plain GBNF). `FlavourAdapter`/`FlavourParser`/`FlavourEmitter` Protocols move from `grammars/flavours.py` to `lexic.ir.protocols` (already done in Task 1); `grammars/flavours.py` keeps only the registry. Verify no remaining dead imports.

**Files:**
- Modify: `src/lexic/grammars/gbnf/adapter.py` (full handler dicts)
- Modify: `src/lexic/grammars/flavours.py` (delete Protocol definitions; re-export from `lexic.ir`)
- Modify: `src/lexic/grammars/__init__.py` (re-exports unchanged)

- [ ] **Step 1: Update `GbnfAdapter`.**

Edit `src/lexic/grammars/gbnf/adapter.py`:

```python
"""GbnfAdapter — wires every seam of the GBNF flavour.

GbnfEscapes (declared above in this same module — see Task 4) is the
single instance the adapter exposes via `self.escapes` and passes into
the emitter.  No second instantiation; no separate syntax module.
"""

from __future__ import annotations

from functools import cached_property

from lexic.grammars.gbnf.emit import GbnfEmitter
from lexic.grammars.gbnf.parser import GbnfParser

# GbnfEscapes / GBNF_ESCAPES / decode_gbnf_escapes / encode_gbnf_escapes
# are declared at module top by Task 4 — no import needed here.


class GbnfAdapter:
    """GBNF flavour adapter.

    Plain GBNF uses only canonical atoms; the four handler-extension dicts
    are empty. Subclasses (or extension flavours derived from GBNF) merge
    in their own handlers.
    """

    name = "gbnf"
    extensions: tuple[str, ...] = (".gbnf",)
    supports = frozenset({
        "literal", "char_class", "negated_class", "quantifier",
        "alternation", "non_capturing_group", "unicode_escape",
    })
    field_handlers: dict[type, object] = {}
    lark_handlers: dict[type, object] = {}
    transform_handlers: dict[type, object] = {}
    to_text_handlers: dict[type, object] = {}

    def __init__(self) -> None:
        self.parser = GbnfParser()
        self.escapes = GbnfEscapes()

    @cached_property
    def emitter(self) -> GbnfEmitter:
        return GbnfEmitter(escapes=self.escapes)
```

- [ ] **Step 2: Trim `grammars/flavours.py`.**

```python
"""Flavour adapter registry."""

from __future__ import annotations

from pathlib import Path

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import FlavourAdapter, FlavourParser  # re-export for back-compat
from lexic.ir.emit import FlavourEmitter            # re-export

__all__ = [
    "ADAPTERS",
    "FlavourAdapter",
    "FlavourEmitter",
    "FlavourParser",
    "adapter_for_extension",
    "get_adapter",
    "register_adapter",
]


ADAPTERS: dict[str, FlavourAdapter] = {}


def register_adapter(adapter: FlavourAdapter) -> None:
    ADAPTERS[adapter.name] = adapter


def get_adapter(flavour: str) -> FlavourAdapter:
    try:
        return ADAPTERS[flavour]
    except KeyError:
        raise UnsupportedConstructError(
            f"Unknown flavour: {flavour!r}. Supported: {sorted(ADAPTERS)}"
        ) from None


def adapter_for_extension(path: str | Path) -> FlavourAdapter:
    suffix = Path(path).suffix
    for adapter in ADAPTERS.values():
        if suffix in adapter.extensions:
            return adapter
    known = sorted({ext for a in ADAPTERS.values() for ext in a.extensions})
    raise UnsupportedConstructError(
        f"No flavour adapter registered for extension {suffix!r}. Supported: {known}"
    )
```

- [ ] **Step 3: Run full suite + ruff.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
```

- [ ] **Step 4: Confirm no orphan imports.**

```bash
grep -rn "from lexic.codegen.helpers\|from lexic.codegen.classify\|from lexic.codegen.seq_to_atoms\|from lexic.codegen.ast_utils\|from lexic.codegen.transformer\|from lexic.codegen.lark_builder\|from lexic.codegen.ir_builder\|from lexic.grammars.gbnf.escapes\|from lexic.grammars.gbnf.charclass\|from lexic.grammars.gbnf.syntax\|from lexic.grammars.gbnf.emitter\|from lexic.base\|from lexic.parse\|from lexic.generate" src/ tests/
```

Expected: zero results.

- [ ] **Step 5: Commit.**

```bash
git add -A
git commit -m "refactor(grammars): GbnfAdapter exposes 4 handler-extension dicts; flavour Protocols centralised in lexic.ir.protocols"
```

---

## Task 12: Documentation + AST import-boundary test

Update `CLAUDE.md`, `prototyping/next/2_ARCHITECTURE.md`, `prototyping/next/3_ROADMAP.md`, the Slice B design spec. Add the AST-based import-boundary test.

**Files:**
- Create: `tests/unit/lexic/parsing/test_import_boundary.py`
- Modify: `CLAUDE.md`
- Modify: `prototyping/next/2_ARCHITECTURE.md`
- Modify: `prototyping/next/3_ROADMAP.md`
- Modify: `docs/superpowers/specs/2026-04-23-slice-b-design.md`

- [ ] **Step 1: Write the AST-based import-boundary test.**

Create `tests/unit/lexic/parsing/test_import_boundary.py`:

```python
"""AST-based import boundary checks.

No module under lexic.{parsing,codegen,runtime,ir} may import from
lexic.grammars.gbnf (or any flavour package). And no module under
lexic.grammars.gbnf may import from lexic.{parsing,codegen,runtime}.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[4] / "src" / "lexic"


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
    return out


def _modules_under(*packages: str) -> list[Path]:
    out: list[Path] = []
    for pkg in packages:
        out.extend((SRC / pkg).rglob("*.py"))
    return out


@pytest.mark.parametrize("path", _modules_under("ir", "codegen", "parsing", "runtime"))
def test_no_flavour_imports_from_core(path: Path):
    bad = [m for m in _imports(path) if m.startswith("lexic.grammars.gbnf")]
    assert not bad, f"{path.relative_to(SRC.parent.parent)} imports flavour: {bad}"


@pytest.mark.parametrize("path", _modules_under("grammars/gbnf"))
def test_no_flavour_imports_consumers(path: Path):
    bad = [
        m for m in _imports(path)
        if m.startswith(("lexic.parsing", "lexic.codegen", "lexic.runtime"))
    ]
    assert not bad, f"{path.relative_to(SRC.parent.parent)} imports consumer: {bad}"
```

- [ ] **Step 2: Run — expect PASS.**

```bash
uv run pytest tests/unit/lexic/parsing/test_import_boundary.py -q
```

If it fails, the failure points at a violation: fix that import (route through `ir/` or via the adapter).

- [ ] **Step 3: Update `CLAUDE.md`.**

Replace the "Project layout" tree with the new structure (`runtime/`, `parsing/`, expanded `ir/` and `codegen/`). Replace the "Architecture" prose with the canonical-IR + handler-dispatch summary. Update import-path examples to use `lexic.runtime.base` and `lexic.parsing.lark_builder`.

- [ ] **Step 4: Update `prototyping/next/2_ARCHITECTURE.md`.**

Replace target module layout. Update layering rules to name the four packages and describe canonical-IR + adapter-bound-handlers contract.

- [ ] **Step 5: Update `prototyping/next/3_ROADMAP.md`.**

Replace v1 Slice B.5 entry with a one-paragraph pointer to `docs/superpowers/specs/2026-04-25-slice-b5-package-restructure-design.md`. Note that Phase 2 (atom collapse) operates on the post-B.5 structure.

- [ ] **Step 6: Update `docs/superpowers/specs/2026-04-23-slice-b-design.md`.**

Add a one-paragraph note: "Phase 2 (atom collapse) operates on the post-B.5 structure with already-canonical atoms; `InlineRegexAtom.gbnf` removal happened in B.5, not Phase 2."

- [ ] **Step 7: Run full suite + ruff. Final commit.**

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add -A
git commit -m "docs(slice-b5): update CLAUDE.md, ARCHITECTURE.md, ROADMAP.md, slice-b spec; add AST import-boundary test"
```

---

## Self-review checklist

After all 12 tasks land, run this checklist against the spec exit criteria:

- [ ] `lexic/ir/atoms.py` defines `Atom` as a runtime-checkable Protocol; canonical concrete atoms are frozen dataclasses; `InlineRegexAtom.gbnf` does not exist; `InlineRegexAtom` carries `canonical: str`.
- [ ] `LiteralAtom.value` is canonical Python everywhere downstream of `GbnfConverter` (no `decode_gbnf_escapes` calls outside `grammars/gbnf/`).
- [ ] `CharClassAtom.pattern` is POSIX-style everywhere downstream.
- [ ] `RuleSpec.non_semantic_fields` is populated by IRBuilder for trivia refs; consumed by `semantic_dump` and `RuleRefBuilder.build`.
- [ ] `lexic/ir/protocols.py` declares `RuleClassifier`, `SequenceConverter`, `FlavourParser`, `FlavourAdapter`, and the five handler type aliases; re-exports `EscapeCodec` from `lexic.ir.escapes`.
- [ ] `lexic/ir/builder.py:IRBuilder` is generic over `Node`; takes `classifier`, `converter`, optional `helpers`, optional `trivia_rules`; sets `min=0` on trivia rule refs; populates `non_semantic_fields`.
- [ ] `lexic/ir/classify.py:classify_rule` is a function; the `Classifier` class is gone.
- [ ] `lexic/ir/convert.py` holds the generic conversion algorithm; dead `name_map`/`parent_of` parameters are gone.
- [ ] `lexic/ir/emit.py:FlavourEmitter` is an ABC with `DEFAULT_HANDLERS` and decorator hooks.
- [ ] `lexic/ir/escapes.py:EscapeCodec` is an ABC; declares `encode`/`decode`/`read_escape` algorithms; subclasses provide only `SHORT_ESCAPES` and `HEX_ESCAPES` class attrs. `CANONICAL_ESCAPES` instance is the default for `parse_charclass_chars`.
- [ ] `lexic/ir/charclass.py:parse_charclass_chars(inner, codec=CANONICAL_ESCAPES)` is the only place bracket-expression enumeration lives; no parallel implementation in `grammars/gbnf/`.
- [ ] `grammars/gbnf/adapter.py` declares `GbnfEscapes(EscapeCodec)` (≤ 5 lines of class body), `GBNF_ESCAPES` instance, and module-level `decode_gbnf_escapes`/`encode_gbnf_escapes` aliases (no separate `syntax.py`). No inline encode/decode/parse_charclass logic; no bracket-converter free functions.
- [ ] `lexic/parsing/`, `lexic/runtime/` exist; `lexic/codegen/handlers/`, `lexic/parsing/handlers/`, `lexic/runtime/handlers/` exist with canonical-atom handler tables.
- [ ] `lexic/codegen/{ir_builder,classify,seq_to_atoms,ast_utils,helpers}.py` and `lexic/codegen/transformer/` do not exist.
- [ ] `src/lexic/{base,parse,generate}.py` do not exist (moved to `runtime/`).
- [ ] `grammars/gbnf/{escapes,charclass,syntax,emitter}.py` do not exist (collapsed/renamed; `syntax.py` was an interim file from an earlier revision of Task 4 — its contents are now in `adapter.py`).
- [ ] `grammars/gbnf/` contains: `__init__.py`, `adapter.py`, `parser.py`, `ast.py`, `ast_to_ir.py`, `emit.py`.
- [ ] `grammars/gbnf/emit.py:GbnfEmitter` is ≤ 20 lines (no custom `__init__`, no `render_charclass`/`render_inline_regex` overrides — defaults are correct for ASCII GBNF).
- [ ] `grammars/gbnf/parser.py:GbnfParser.parse(text)` returns `list[RuleSpec]`.
- [ ] `grammars/gbnf/ast_to_ir.py` defines `GbnfClassifier(RuleClassifier[Rule])` (memoised by `id(rule)`) and `GbnfConverter(SequenceConverter[Rule])`.
- [ ] `GbnfAdapter` exposes `parser`, `emitter`, `escapes`, `supports`, `name`, `extensions`, and the four handler-extension dicts.
- [ ] `parsing/lark_builder.py` has no `if atom.rule_name == "ws"`, no `if spec.rule_name == "ws"`, no hardcoded `ws : /[ \t\n]+/`.
- [ ] `parsing/transformer.py` has no `ws_method` and no `if spec.rule_name == "ws"`.
- [ ] `parsing/transformer_builders.py:RuleRefBuilder` has no `is_ws = atom.rule_name == "ws"`; uses `field_name in spec.non_semantic_fields`.
- [ ] `runtime/base.py` has no `atom.rule_name == "ws"` check; `semantic_dump` uses `non_semantic_fields`.
- [ ] The string `"ws"` appears at most once in `src/lexic/` (`IRBuilder` default `trivia_rules={"ws"}`).
- [ ] No module under `lexic.{parsing,codegen,runtime,ir}` imports from `lexic.grammars.gbnf`.
- [ ] No module under `lexic.grammars.gbnf` imports from `lexic.{parsing,codegen,runtime}`.
- [ ] `tests/unit/lexic/parsing/test_import_boundary.py` is green.
- [ ] Every generated module sets `__adapter__ = <adapter>` at module level; `GrammarModel.to_text` and `to_grammar` resolve handlers via `self.__class__.__module__`'s `__adapter__`.
- [ ] All existing tests are green at every commit.
- [ ] `uv run ruff check src/ tests/` is clean.
- [ ] Round-trip property tests across all seven ground-truth grammars produce identical `list[RuleSpec]` (full `==` equality) before and after the refactor.
- [ ] `CLAUDE.md`, `prototyping/next/2_ARCHITECTURE.md`, `prototyping/next/3_ROADMAP.md`, and the Slice B design spec are updated.
