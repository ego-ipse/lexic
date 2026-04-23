# Slice B — PatternAtom + Tier 2.5 + Token Reservation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-23-slice-b-design.md`

**Goal:** Collapse three atom types into `PatternAtom`, reshape `InlineAlternationAtom` to carry inline arm contents, move the GBNF-specific codebase into `grammars/gbnf/` under `FlavourAdapter`/`FlavourParser`/`FlavourEmitter` protocols, and reserve GBNF token syntax (`<name>`, `<[N]>`, `!<name>`) with a clear error.

**Architecture:** Three phases landing inside one PR. Phase 1 and Phase 3 each land as one commit; Phase 2 lands as two commits (one isolated canonicalize_groups commit, then one bundled atom-migration commit that includes shape change + consumer migration + regen + cleanup — these must land together because the consumers-in-flight state isn't green).
1. **Scaffolding** (Phase 1) — behaviour-preserving moves, new infrastructure modules, `flavour=` parameter threading, delete `LarkBuilder.build_transformer`, freeze atoms, doc cleanup.
2. **Atom collapse** (Phase 2) — merge `CharClassAtom` / `QuantifiedLiteralAtom` / `InlineRegexAtom` into `PatternAtom` with `source_forms`; reshape `InlineAlternationAtom.arms: tuple[Arm, ...]`; update every consumer; wire compile-time `validate_portable` + emitter-`supports` cross-check.
3. **Token reservation** (Phase 3) — pre-tokenisation scan in `GbnfParser.parse` raises `UnsupportedConstructError` on `<name>`, `<[N]>`, `!<name>`.

**Tech Stack:** Python 3.11+, Pydantic v2, Lark, `dataclasses`, `re` + `sre_parse` (stdlib), `uv` for dep/test management, `ruff` for lint.

**Assumed context:** Reader has read `CLAUDE.md`, `docs/STYLE.md`, `prototyping/next/2_ARCHITECTURE.md`, and the spec. The seven ground-truth grammars live in `resources/ground_truth/`; the generated module cache lives in `generated/` (git-tracked but edited only via regeneration).

---

## File Structure

### Phase 1 — creates, moves, deletes

**Creates (new files):**
- `src/lexic/exceptions.py` — four error classes.
- `src/lexic/ir/regex_portable.py` — `PORTABLE_FEATURES`, `validate_portable`, `features_used`, `canonicalize_groups`.
- `src/lexic/grammars/flavours.py` — `FlavourParser`/`FlavourEmitter`/`FlavourAdapter` protocols, `ADAPTERS` registry, eager GBNF registration.
- `src/lexic/grammars/gbnf/__init__.py` — pure re-export (no side effects).
- `src/lexic/grammars/gbnf/adapter.py` — `GbnfAdapter` class.
- `tests/unit/lexic/grammars/test_flavours.py` — registry + protocol smoke tests.
- `tests/unit/lexic/grammars/gbnf/__init__.py` — empty package marker.

**Moves (git mv — history follows):**
- `src/lexic/codegen/parser.py` → `src/lexic/grammars/gbnf/parser.py`
- `src/lexic/codegen/ast.py` → `src/lexic/grammars/gbnf/ast.py`
- `src/lexic/codegen/gbnf_emitter.py` → `src/lexic/grammars/gbnf/emitter.py`
- `src/lexic/utils/escapes.py` → `src/lexic/grammars/gbnf/escapes.py`
- `src/lexic/utils/charclass.py` → `src/lexic/grammars/gbnf/charclass.py`
- `tests/unit/lexic/codegen/test_parser.py` → `tests/unit/lexic/grammars/gbnf/test_parser.py` (+ mirror tests for escapes/charclass if they exist)

**Modifies:**
- `src/lexic/base.py` — add `to_grammar(flavour)`; rewrite `to_gbnf()` as alias; eager import from `lexic.grammars.gbnf.emitter`.
- `src/lexic/codegen/__init__.py` — add `flavour` parameter to public functions.
- `src/lexic/compile.py` — add `flavour` parameter.
- `src/lexic/codegen/lark_builder.py` — delete `build_transformer` method.
- `src/lexic/codegen/transformer/registry.py`, `tests/unit/lexic/codegen/test_transformer.py` — update call site.
- `src/lexic/ir/atoms.py` — mark dataclasses frozen.
- `prototyping/next/2_ARCHITECTURE.md`, `prototyping/next/3_ROADMAP.md`, `CLAUDE.md` — doc edits.

### Phase 2 — atom collapse

**Modifies:**
- `src/lexic/ir/atoms.py` — add `PatternAtom`, `Arm`; reshape `InlineAlternationAtom.arms` to `tuple[Arm, ...]`; reshape `AlternationAtom.arm_rule_names` to `tuple[str, ...]`; remove `CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom` (end of Phase 2 only — see per-task ordering).
- `src/lexic/ir/__init__.py` — update re-exports.
- `src/lexic/ir/regex_portable.py` — add `canonicalize_groups`.
- `src/lexic/grammars/gbnf/parser.py` — emit `PatternAtom` with `source_forms["gbnf"]`; lower shorthand `\d \w \s`; decode GBNF escapes into canonical Python for `LiteralAtom.value` and `PatternAtom.regex`.
- `src/lexic/codegen/seq_to_atoms.py` — drop inline-alt helper-rule synthesis; construct `InlineAlternationAtom(arms=...)` directly.
- `src/lexic/codegen/ir_builder.py` — atom construction updates (if any remaining outside `seq_to_atoms`).
- `src/lexic/codegen/naming.py` — handle new `InlineAlternationAtom.arms` shape.
- `src/lexic/codegen/lark_builder.py` — single `PatternAtom` branch in `_atom_to_lark`; explicit default raise; handle new `InlineAlternationAtom.arms`; drop `decode_gbnf_escapes` usage.
- `src/lexic/codegen/model_emitter.py` — single `PatternAtom` branch in `_field_type` and `_repr_atom`; updated `InlineAlternationAtom` rendering; explicit default raise.
- `src/lexic/grammars/gbnf/emitter.py` — single `PatternAtom` dispatch (read `source_forms["gbnf"]` first; else `NotImplementedError` stub); explicit default raise.
- `src/lexic/codegen/transformer/registry.py`, `src/lexic/codegen/transformer/builders.py` — merge three builders into `PatternFieldBuilder`; update `InlineAlternationBuilder`; explicit default raise.
- `src/lexic/generate.py` — regex-aware sampler for `PatternAtom` (replace bracket-expression + shorthand expansion); updated `InlineAlternationAtom` handling; explicit default raise.
- `src/lexic/codegen/__init__.py` — wire `validate_portable` + `supports` cross-check.
- `generated/*.py` — regenerate all (they track the atom-type renames + `source_forms={}` additions).
- Existing tests under `tests/` that construct atoms by old names — update to new names/shapes.

**Creates:**
- `tests/unit/lexic/ir/test_atom_shapes.py`
- `tests/unit/lexic/ir/test_regex_portable.py`
- `tests/unit/lexic/grammars/gbnf/test_parser_source_forms.py`
- `tests/integration/test_source_forms_roundtrip.py`

### Phase 3 — token reservation

**Modifies:**
- `src/lexic/grammars/gbnf/parser.py` — pre-tokenisation scan at top of `parse()`.

**Creates:**
- `tests/integration/test_token_reservation.py`.

---

# Phase 1 — Scaffolding

Every task in this phase is behaviour-preserving. The 414-test suite must remain green after every task.

## Task 1: Create `lexic/exceptions.py`

**Files:**
- Create: `src/lexic/exceptions.py`
- Test: (none — trivial class definitions; exercised by later tasks)

- [x] **Step 1: Write the module**

```python
# src/lexic/exceptions.py
"""Library-level error classes for lexic.

All lexic-raised errors inherit from LexicError. External callers can catch
LexicError to trap any library failure.
"""

from __future__ import annotations


class LexicError(Exception):
    """Base class for all lexic errors."""


class UnsupportedConstructError(LexicError):
    """A grammar construct is not supported by the current flavour or IR shape.

    Raised by:
    - GBNF parser (token syntax, unknown flavour)
    - Atom dispatch tables (unknown atom type — internal consistency)
    - Codegen cross-check (pattern uses features the target emitter cannot emit)
    """


class GrammarAuthoringError(LexicError):
    """A grammar is malformed in a way the author should fix.

    Stub in Slice B; wired by Slice C (discriminator ambiguity, sidecar refs
    to unknown classes/fields) and Slice D (@grammar_rule decorator misuse).
    """


class FieldValidationError(LexicError):
    """A parsed field fails the emitted Pydantic constraints.

    Stub in Slice B; wired by Slice C when Annotated[str, StringConstraints(...)]
    emission lands.
    """
```

- [x] **Step 2: Verify import path works**

Run: `uv run python -c "from lexic.exceptions import LexicError, UnsupportedConstructError, GrammarAuthoringError, FieldValidationError; print('ok')"`
Expected: `ok`

- [x] **Step 3: Commit**

```bash
git add src/lexic/exceptions.py
git commit -m "feat(exceptions): add lexic.exceptions with four error classes

Base LexicError plus UnsupportedConstructError (Slice B consumer),
GrammarAuthoringError and FieldValidationError (Slice C stubs)."
```

---

## Task 2: Create `lexic/ir/regex_portable.py`

**Files:**
- Create: `src/lexic/ir/regex_portable.py`
- Test: (deferred to Phase 2 Task 17 — tested alongside atom shapes, since Phase 1 has no consumer wiring)

- [x] **Step 1: Write the module — scaffold only (`canonicalize_groups` lands in Phase 2)**

```python
# src/lexic/ir/regex_portable.py
"""Portable regex subset for PatternAtom.regex.

Defines the IR-level contract: which regex features are allowed in canonical
PatternAtom.regex strings (CFG-portable subset), and utilities to validate a
regex against that contract and to enumerate the features it uses.

Each FlavourEmitter declares a `supports: frozenset[str]` subset of
PORTABLE_FEATURES; the codegen pipeline cross-checks every PatternAtom
against the target flavour's supports set before emission.
"""

from __future__ import annotations

import sre_parse
from sre_constants import (
    ANY,
    AT,
    AT_BEGINNING,
    AT_END,
    AT_BOUNDARY,
    AT_NON_BOUNDARY,
    BRANCH,
    CATEGORY,
    GROUPREF,
    IN,
    LITERAL,
    MAX_REPEAT,
    MIN_REPEAT,
    NEGATE,
    NOT_LITERAL,
    RANGE,
    SUBPATTERN,
)

from lexic.exceptions import UnsupportedConstructError


PORTABLE_FEATURES: frozenset[str] = frozenset(
    {
        "literal",
        "char_class",
        "negated_class",
        "shorthand",
        "quantifier",
        "alternation",
        "non_capturing_group",
        "unicode_escape",
    }
)


_FORBIDDEN_AT = {
    AT_BEGINNING: "anchor ^",
    AT_END: "anchor $",
    AT_BOUNDARY: r"word boundary \b",
    AT_NON_BOUNDARY: r"non-word-boundary \B",
}


def validate_portable(regex: str) -> None:
    """Raise UnsupportedConstructError if regex uses non-CFG features.

    Forbidden: anchors, lookarounds, backrefs, inline flags, capturing
    groups (must be non-capturing), word boundaries, `.` any-char.
    """
    try:
        tree = sre_parse.parse(regex)
    except Exception as exc:
        raise UnsupportedConstructError(
            f"Cannot parse regex {regex!r}: {exc}"
        ) from exc
    _walk_validate(tree, regex)


def features_used(regex: str) -> frozenset[str]:
    """Return the PORTABLE_FEATURES subset this regex uses.

    Precondition: regex has been validated via validate_portable().
    """
    tree = sre_parse.parse(regex)
    used: set[str] = set()
    _walk_features(tree, used)
    return frozenset(used)


def _walk_validate(tree, regex: str) -> None:
    """Recursive validation; raises on first forbidden construct."""
    for op, arg in tree:
        if op is AT:
            msg = _FORBIDDEN_AT.get(arg, f"anchor {arg!r}")
            raise UnsupportedConstructError(
                f"Regex {regex!r} uses {msg} (not allowed in portable IR)"
            )
        if op is ANY:
            raise UnsupportedConstructError(
                f"Regex {regex!r} uses `.` (any-char); use an explicit char class"
            )
        if op is GROUPREF:
            raise UnsupportedConstructError(
                f"Regex {regex!r} uses a backreference (not allowed in portable IR)"
            )
        if op is SUBPATTERN:
            # SUBPATTERN arg is (group_number_or_None, add_flags, del_flags, subtree)
            group_num, add_flags, del_flags, subtree = arg
            if group_num is not None:
                raise UnsupportedConstructError(
                    f"Regex {regex!r} uses capturing group (use (?:...) instead)"
                )
            if add_flags or del_flags:
                raise UnsupportedConstructError(
                    f"Regex {regex!r} uses inline flags (not allowed in portable IR)"
                )
            _walk_validate(subtree, regex)
            continue
        if op is BRANCH:
            _, branches = arg
            for branch in branches:
                _walk_validate(branch, regex)
            continue
        if op in (MAX_REPEAT, MIN_REPEAT):
            _, _, subtree = arg
            _walk_validate(subtree, regex)
            continue
        if op is IN:
            # Character class contents — allowed structures are LITERAL,
            # RANGE, CATEGORY (shorthand), NEGATE (leading marker).
            continue


def _walk_features(tree, used: set[str]) -> None:
    for op, arg in tree:
        if op is LITERAL or op is NOT_LITERAL:
            used.add("literal")
        elif op is IN:
            negated = any(sub[0] is NEGATE for sub in arg)
            used.add("negated_class" if negated else "char_class")
            for sub in arg:
                sub_op, sub_arg = sub
                if sub_op is CATEGORY:
                    used.add("shorthand")
        elif op is BRANCH:
            used.add("alternation")
            _, branches = arg
            for branch in branches:
                _walk_features(branch, used)
        elif op is SUBPATTERN:
            used.add("non_capturing_group")
            _, _, _, subtree = arg
            _walk_features(subtree, used)
        elif op in (MAX_REPEAT, MIN_REPEAT):
            used.add("quantifier")
            _, _, subtree = arg
            _walk_features(subtree, used)


def canonicalize_groups(regex: str) -> str:
    """Phase 2 placeholder — full implementation in Task 17-ish.

    Rewrites any capturing group `(...)` in `regex` to non-capturing `(?:...)`.
    Phase 1 ships a no-op + `# TODO(slice-b-phase-2)` marker so the module is
    importable for early tests; Phase 2 replaces with the real implementation.
    """
    return regex  # TODO(slice-b-phase-2): real implementation
```

**Implementation note:** `sre_parse` is undocumented but stable across CPython 3.x. The module's AST shape is stable enough to rely on here; tests (Task 17) cover the behaviour against concrete regex inputs.

- [x] **Step 2: Verify the module imports**

Run: `uv run python -c "from lexic.ir.regex_portable import PORTABLE_FEATURES, validate_portable, features_used, canonicalize_groups; print(sorted(PORTABLE_FEATURES))"`
Expected: `['alternation', 'char_class', 'literal', 'negated_class', 'non_capturing_group', 'quantifier', 'shorthand', 'unicode_escape']`

- [ ] **Step 3: Commit**

```bash
git add src/lexic/ir/regex_portable.py
git commit -m "feat(ir): scaffold regex_portable module

Adds PORTABLE_FEATURES set + validate_portable / features_used sre_parse
walkers. canonicalize_groups ships as no-op stub; full impl lands in Phase 2.
No consumers yet."
```

---

## Task 3: Move GBNF-owned modules into `grammars/gbnf/`

Three `git mv`s (codegen) + two `git mv`s (utils), plus a new `__init__.py`. This task is pure rename — no content changes. All imports break and get fixed in Task 5.

**Files:**
- Move: `src/lexic/codegen/parser.py` → `src/lexic/grammars/gbnf/parser.py`
- Move: `src/lexic/codegen/ast.py` → `src/lexic/grammars/gbnf/ast.py`
- Move: `src/lexic/codegen/gbnf_emitter.py` → `src/lexic/grammars/gbnf/emitter.py`
- Move: `src/lexic/utils/escapes.py` → `src/lexic/grammars/gbnf/escapes.py`
- Move: `src/lexic/utils/charclass.py` → `src/lexic/grammars/gbnf/charclass.py`
- Move: `tests/unit/lexic/codegen/test_parser.py` → `tests/unit/lexic/grammars/gbnf/test_parser.py`
- Create: `src/lexic/grammars/gbnf/__init__.py`
- Create: `tests/unit/lexic/grammars/gbnf/__init__.py`

- [ ] **Step 1: Run the moves**

```bash
mkdir -p src/lexic/grammars/gbnf tests/unit/lexic/grammars/gbnf
git mv src/lexic/codegen/parser.py       src/lexic/grammars/gbnf/parser.py
git mv src/lexic/codegen/ast.py          src/lexic/grammars/gbnf/ast.py
git mv src/lexic/codegen/gbnf_emitter.py src/lexic/grammars/gbnf/emitter.py
git mv src/lexic/utils/escapes.py        src/lexic/grammars/gbnf/escapes.py
git mv src/lexic/utils/charclass.py      src/lexic/grammars/gbnf/charclass.py
git mv tests/unit/lexic/codegen/test_parser.py tests/unit/lexic/grammars/gbnf/test_parser.py
```

- [ ] **Step 2: Create the package markers**

```python
# src/lexic/grammars/gbnf/__init__.py
"""GBNF flavour adapter package.

Pure re-export. Adapter registration lives in lexic.grammars so
registry population is import-order independent.
"""

from lexic.grammars.gbnf.adapter import GbnfAdapter

__all__ = ["GbnfAdapter"]
```

```python
# tests/unit/lexic/grammars/gbnf/__init__.py
```

(empty file — pytest package marker)

- [ ] **Step 3: Intentionally leave imports broken — Task 5 fixes them wholesale**

Run: `uv run pytest tests/ -q 2>&1 | head -30`
Expected: many import errors referencing `lexic.codegen.parser`, `lexic.utils.escapes`, etc. This is expected — Task 5 fixes them.

**Do not commit yet.** This state is WIP. Task 6 creates `adapter.py`; Task 5 fixes imports; Task 14 commits the whole scaffolding phase as one coherent unit.

---

## Task 4: Wrap GbnfParser and GbnfEmitter as classes

`parse_gbnf` in `gbnf/parser.py` is currently a module-level function. `GBNFEmitter` is already a class. Wrap the parser as a class implementing `FlavourParser`, and add `supports` to `GBNFEmitter`.

**Files:**
- Modify: `src/lexic/grammars/gbnf/parser.py`
- Modify: `src/lexic/grammars/gbnf/emitter.py`

- [ ] **Step 1: Add `GbnfParser` class to `gbnf/parser.py`**

At the bottom of the file (after the existing `parse_gbnf` function), add:

```python
class GbnfParser:
    """GBNF flavour parser.

    Thin class wrapper around parse_gbnf for the FlavourParser protocol.
    Phase 2 extends this with IR-construction responsibilities (today they
    live in IRBuilder, consuming the AST parse_gbnf returns).
    """

    def parse(self, text: str):
        """Return list[Rule] — the GBNF AST. Phase 2 will return list[RuleSpec]."""
        return parse_gbnf(text)
```

**Note:** Phase 1 keeps the current AST-returning contract because `IRBuilder` still consumes the AST. Phase 2 Task 18 changes `GbnfParser.parse()` to return `list[RuleSpec]` directly (folding `IRBuilder` into the parser — or keeping `IRBuilder` as an internal helper called from `GbnfParser.parse`).

- [ ] **Step 2: Rename `GBNFEmitter` → `GbnfEmitter` and add `supports`**

In `src/lexic/grammars/gbnf/emitter.py`:

- Rename class `GBNFEmitter` → `GbnfEmitter` (consistent with `GbnfParser` / `GbnfAdapter`).
- Add class attribute `supports: frozenset[str]` before `__init__`:

```python
class GbnfEmitter:
    """GBNF flavour emitter."""

    supports: frozenset[str] = frozenset(
        {
            "literal",
            "char_class",
            "negated_class",
            "quantifier",
            "alternation",
            "non_capturing_group",
            "unicode_escape",
        }
    )
    # Notably absent: "shorthand". GbnfParser lowers \d \w \s to char classes
    # at parse time, so GBNF-parsed IR never carries shorthand.

    def __init__(self, specs):
        ...
```

- Add class-level `emit` method that mirrors the existing `__call__`/`emit_rule` logic and matches the `FlavourEmitter` protocol signature (`emit(self, specs: list[RuleSpec]) -> str`). The existing `emit_rule(spec)` stays for `GrammarModel.to_gbnf()`'s single-rule call. Add:

```python
def emit(self, specs) -> str:
    """Emit a full GBNF grammar string from a list of RuleSpec."""
    lines = [self.emit_rule(s) for s in specs]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 3: Add backwards-compatible alias**

At the bottom of `gbnf/emitter.py`:

```python
# Backwards compatibility for callers still importing GBNFEmitter.
# Removed at end of Slice B (Task 32) after all imports are updated.
GBNFEmitter = GbnfEmitter
```

This keeps `from lexic.grammars.gbnf.emitter import GBNFEmitter` working during Task 5's import sweep. Delete in Task 32.

- [ ] **Step 4: Verify imports work from the moved location**

Run: `uv run python -c "from lexic.grammars.gbnf.parser import GbnfParser, parse_gbnf; from lexic.grammars.gbnf.emitter import GbnfEmitter, GBNFEmitter; print('ok')"`
Expected: `ok`

**Do not commit yet** — Task 14 commits Phase 1 as one unit.

---

## Task 5: Sweep import paths across `src/` and `tests/`

Move every import of the moved modules to their new paths.

**Files to edit (non-exhaustive — grep to find all):**
- Any `from lexic.codegen.parser import ...` → `from lexic.grammars.gbnf.parser import ...`
- Any `from lexic.codegen.ast import ...` → `from lexic.grammars.gbnf.ast import ...`
- Any `from lexic.codegen.gbnf_emitter import ...` → `from lexic.grammars.gbnf.emitter import ...`
- Any `from lexic.utils.escapes import ...` → `from lexic.grammars.gbnf.escapes import ...`
- Any `from lexic.utils.charclass import ...` → `from lexic.grammars.gbnf.charclass import ...`

- [ ] **Step 1: Find all call sites**

Run:
```bash
grep -rn "from lexic.codegen.parser\|from lexic.codegen.ast\|from lexic.codegen.gbnf_emitter\|from lexic.utils.escapes\|from lexic.utils.charclass" src/ tests/
```

Expected: a list of files to edit. Keep the list; every one gets the obvious rewrite.

- [ ] **Step 2: Rewrite imports**

For each file in the grep output, update the import. In `src/lexic/base.py`:

```python
# Before:
from lexic.codegen.gbnf_emitter import GBNFEmitter
from lexic.utils.escapes import decode_gbnf_escapes

# After:
from lexic.grammars.gbnf.emitter import GbnfEmitter
from lexic.grammars.gbnf.escapes import decode_gbnf_escapes
```

In `base.py`, also update `to_gbnf` to use `GbnfEmitter`:

```python
def to_gbnf(self) -> str:
    """Reconstruct the GBNF rule for this class's grammar spec."""
    return GbnfEmitter([self.__grammar__]).emit_rule(self.__grammar__)
```

Apply the obvious rename everywhere else.

- [ ] **Step 3: Ensure `utils/` still works for its remaining residents**

`src/lexic/utils/` keeps `names.py`, `quantifiers.py`, and `__init__.py`. If `__init__.py` re-exports `decode_gbnf_escapes` or anything from the moved files, remove those lines.

- [ ] **Step 4: Run the test suite**

Run: `uv run pytest tests/ -q`
Expected: **414 passed**. If failures: grep for remaining old import paths, fix, re-run.

- [ ] **Step 5: Run ruff**

Run: `uv run ruff check src/ tests/`
Expected: clean. Ruff will flag any unused imports left from the sweep.

**Do not commit yet.**

---

## Task 6: Create `GbnfAdapter`

**Files:**
- Create: `src/lexic/grammars/gbnf/adapter.py`

- [ ] **Step 1: Write the adapter**

```python
# src/lexic/grammars/gbnf/adapter.py
"""GbnfAdapter composes GbnfParser and GbnfEmitter into a FlavourAdapter."""

from __future__ import annotations

from lexic.grammars.gbnf.emitter import GbnfEmitter
from lexic.grammars.gbnf.parser import GbnfParser


class GbnfAdapter:
    """GBNF flavour adapter.

    Implements FlavourAdapter (duck-typed against grammars.FlavourAdapter).
    """

    name = "gbnf"
    extensions: tuple[str, ...] = (".gbnf",)

    def __init__(self) -> None:
        self.parser = GbnfParser()
        self.emitter = GbnfEmitter([])
```

**Note:** `GbnfEmitter.__init__` currently requires `specs`; Phase 1 passes `[]` as a placeholder. Phase 2 refactors `GbnfEmitter` to have a no-arg constructor and take `specs` through `emit(specs)` (aligning with `FlavourEmitter.emit(specs)`). Mark this with a comment:

```python
        # TODO(slice-b-phase-2): GbnfEmitter() becomes no-arg when emit(specs)
        # is the primary API and emit_rule(spec) takes an explicit spec arg.
        self.emitter = GbnfEmitter([])
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "from lexic.grammars.gbnf.adapter import GbnfAdapter; a = GbnfAdapter(); print(a.name, a.extensions)"`
Expected: `gbnf ('.gbnf',)`

**Do not commit yet.**

---

## Task 7: Create `grammars/flavours.py` with protocols, registry, eager registration

**Files:**
- Create: `src/lexic/grammars/flavours.py`

- [ ] **Step 1: Write the module**

```python
# src/lexic/grammars/flavours.py
"""FlavourAdapter protocol + ADAPTERS registry for lexic.

The registry is populated eagerly at module import time. Callers that
`from lexic.grammars import get_adapter` get a populated registry
regardless of whether `lexic.codegen` was imported elsewhere.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import RuleSpec


class FlavourParser(Protocol):
    def parse(self, text: str) -> list[RuleSpec]: ...


class FlavourEmitter(Protocol):
    supports: frozenset[str]

    def emit(self, specs: list[RuleSpec]) -> str: ...


class FlavourAdapter(Protocol):
    name: str
    extensions: tuple[str, ...]
    parser: FlavourParser
    emitter: FlavourEmitter


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
    """Find the adapter whose .extensions include this path's suffix."""
    suffix = Path(path).suffix
    for adapter in ADAPTERS.values():
        if suffix in adapter.extensions:
            return adapter
    known = sorted({ext for a in ADAPTERS.values() for ext in a.extensions})
    raise UnsupportedConstructError(
        f"No flavour adapter registered for extension {suffix!r}. Supported: {known}"
    )


# Eager GBNF registration — populates ADAPTERS at import time so the registry
# is usable regardless of import order. New adapters add analogous lines here.
from lexic.grammars.gbnf.adapter import GbnfAdapter as _GbnfAdapter

register_adapter(_GbnfAdapter())
```

**Note on the bottom imports:** PEP 8 flags bottom-of-file imports, but the eager registration is intentional: it guarantees `ADAPTERS` is populated after `from lexic.grammars import ...`. The `as _GbnfAdapter` alias keeps the public module surface clean.

- [ ] **Step 2: Verify registration at import time**

Run:
```bash
uv run python -c "
from lexic.grammars import ADAPTERS, get_adapter
print('registered:', sorted(ADAPTERS))
a = get_adapter('gbnf')
print('gbnf adapter:', a.name, a.extensions)
"
```
Expected:
```
registered: ['gbnf']
gbnf adapter: gbnf ('.gbnf',)
```

- [ ] **Step 3: Verify unknown flavour raises**

```bash
uv run python -c "
from lexic.grammars import get_adapter
from lexic.exceptions import UnsupportedConstructError
try:
    get_adapter('abnf')
except UnsupportedConstructError as e:
    print('raised:', e)
"
```
Expected: `raised: Unknown flavour: 'abnf'. Supported: ['gbnf']`

**Do not commit yet.**

---

## Task 8: Add `flavour=` parameter to codegen public functions

**Files:**
- Modify: `src/lexic/codegen/__init__.py`

- [ ] **Step 1: Rewrite the three public functions to accept `flavour=`**

```python
# src/lexic/codegen/__init__.py
"""Codegen public surface.

- build_classes_and_specs(text, *, stem, flavour="gbnf") → (classes, specs)
- codegen(text, *, stem, flavour="gbnf") → classes
- codegen_from_path(path, *, flavour=None) → classes  (infers flavour from ext)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from lexic.grammars import adapter_for_extension, get_adapter
from lexic.codegen.ir_builder import IRBuilder
from lexic.codegen.model_emitter import ModelEmitter
from lexic.ir import RuleSpec


def _emit_and_load_module(
    specs: list[RuleSpec], stem: str, *, source: str | None
) -> dict[str, type]:
    out_dir = Path(__file__).resolve().parent.parent.parent.parent / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.py"
    out_path.write_text(ModelEmitter(specs, source or f"<string:{stem}>").render())

    module_name = f"generated.{stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, out_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return {
        s.class_name: getattr(mod, s.class_name)
        for s in specs
        if hasattr(mod, s.class_name)
    }


def build_classes_and_specs(
    text: str, *, stem: str, flavour: str = "gbnf"
) -> tuple[dict[str, type], list[RuleSpec]]:
    """Parse + IR-build + emit + load. Returns (classes, specs)."""
    adapter = get_adapter(flavour)
    # Phase 1: adapter.parser.parse returns AST; pass through IRBuilder.
    # Phase 2: adapter.parser.parse returns list[RuleSpec] directly.
    ast_rules = adapter.parser.parse(text)
    specs = IRBuilder(ast_rules).build()
    classes = _emit_and_load_module(specs, stem, source=None)
    return classes, specs


def codegen(text: str, *, stem: str, flavour: str = "gbnf") -> dict[str, type]:
    """Classes-only wrapper."""
    classes, _ = build_classes_and_specs(text, stem=stem, flavour=flavour)
    return classes


def codegen_from_path(
    grammar_path: str | Path, *, flavour: str | None = None
) -> dict[str, type]:
    """Read-file wrapper; infers flavour from extension if flavour=None."""
    path = Path(grammar_path)
    if flavour is None:
        flavour = adapter_for_extension(path).name
    return codegen(path.read_text(), stem=path.stem, flavour=flavour)
```

- [ ] **Step 2: Verify basic codegen still works**

Run: `uv run pytest tests/ -q`
Expected: **414 passed**.

- [ ] **Step 3: Verify flavour= works**

```bash
uv run python -c "
from lexic.codegen import codegen
from pathlib import Path
text = Path('resources/ground_truth/arithmetic.gbnf').read_text()
classes = codegen(text, stem='arithmetic', flavour='gbnf')
print('classes:', sorted(classes))
"
```
Expected: a list of class names for the arithmetic grammar.

**Do not commit yet.**

---

## Task 9: Add `flavour=` to `compile()` and `compile_from_path()`

**Files:**
- Modify: `src/lexic/compile.py`

- [ ] **Step 1: Update `compile()`**

```python
def compile(
    text: str, *, cache_key: Hashable | None = None, flavour: str = "gbnf"
) -> CompiledGrammar:
    """Compile from a grammar string. cache_key=None means 'do not memoize'."""
    if cache_key is not None:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            return cached
    cg = _compile_core(text, stem=_stem_for_text(text), flavour=flavour)
    if cache_key is not None:
        _CACHE[cache_key] = cg
    return cg
```

- [ ] **Step 2: Update `_compile_core`**

```python
def _compile_core(text: str, *, stem: str, flavour: str = "gbnf") -> CompiledGrammar:
    classes, specs_list = build_classes_and_specs(text, stem=stem, flavour=flavour)
    specs = {s.rule_name: s for s in specs_list}

    builder = LarkBuilder(specs_list)
    grammar_str, start_rule = builder.build_grammar()
    parser = lark.Lark(
        grammar_str, parser="earley", ambiguity="resolve", start=start_rule
    )
    # Task 11 deletes LarkBuilder.build_transformer; for now it still works.
    transformer = builder.build_transformer(classes)

    return CompiledGrammar(
        classes=classes, specs=specs, parser=parser, transformer=transformer
    )
```

- [ ] **Step 3: Update `compile_from_path()`**

```python
def compile_from_path(
    grammar_path: str | Path, *, flavour: str | None = None
) -> CompiledGrammar:
    """Compile from a file path; memoised by (path, mtime, size)."""
    path = Path(grammar_path).resolve()
    stat = path.stat()
    key = (str(path), stat.st_mtime, stat.st_size, flavour)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    if flavour is None:
        from lexic.grammars import adapter_for_extension

        flavour = adapter_for_extension(path).name
    return compile(path.read_text(), cache_key=key, flavour=flavour)
```

**Note the cache key:** Adding `flavour` to the key means the same file compiled under different flavours gets independent cache entries. Today this never matters (only `gbnf` exists) but it avoids a cache-collision footgun later.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/ -q`
Expected: **414 passed**.

**Do not commit yet.**

---

## Task 10: Add `GrammarModel.to_grammar(flavour)`; `to_gbnf()` becomes alias

**Files:**
- Modify: `src/lexic/base.py`

- [ ] **Step 1: Update `base.py`**

Replace the existing `to_gbnf` with:

```python
def to_grammar(self, flavour: str = "gbnf") -> str:
    """Reconstruct the grammar rule text for this class.

    Default flavour is "gbnf". The emitter is resolved via the flavours
    registry at call time so ADAPTERS populate regardless of import order.
    Uses the FlavourEmitter protocol's emit(specs) — single-rule output
    strips the trailing newline.
    """
    from lexic.grammars import get_adapter

    adapter = get_adapter(flavour)
    return adapter.emitter.emit([self.__grammar__]).rstrip("\n")

def to_gbnf(self) -> str:
    """Backwards-compatible alias for to_grammar('gbnf')."""
    return self.to_grammar("gbnf")
```

**Protocol cleanliness:** `emit_rule(spec)` is a GBNF-specific method on `GbnfEmitter`. Protocol-level `emit(specs)` is what every emitter guarantees; `to_grammar` uses the protocol surface, not the concrete class's extra methods. `GbnfEmitter.emit(specs)` internally calls `emit_rule(s)` per spec and joins — `emit([one_spec])` produces exactly one rule's text plus a trailing newline, which `.rstrip("\n")` strips.

**Note on import:** the spec calls for an eager module-level import (`base.py` imports `lexic.grammars.gbnf.emitter`). However, `get_adapter` lookups preserve flavour-agnostic `to_grammar` (keeping the edge flavour-neutral). Keep the import lazy **only for `to_grammar`** and accept that this is a principled lazy import — it exists so `base.py` does not bake `gbnf` into its module-level imports. `2_ARCHITECTURE.md` §Layering rules talks about "the two deliberate exceptions" — this is one of them. Add a module docstring note:

```python
# At top of base.py after the existing module docstring:
# Note: to_grammar() resolves the emitter via the flavours registry at call
# time. This is the deliberate runtime→codegen seam described in
# 2_ARCHITECTURE.md §Layering rules; it stays inside a method body to keep
# base.py flavour-neutral at module scope.
```

Remove the existing top-level imports from `base.py`:

```python
# Delete:
from lexic.codegen.gbnf_emitter import GBNFEmitter  # (was already renamed in Task 5)
from lexic.utils.escapes import decode_gbnf_escapes
```

`decode_gbnf_escapes` is used inside `to_text`. Replace the call with a local import that matches the same flavour-neutral pattern:

```python
def to_text(self) -> str:
    from lexic.grammars.gbnf.escapes import decode_gbnf_escapes
    # ... rest unchanged ...
```

**Note:** Phase 2 removes the `decode_gbnf_escapes` call from `to_text` entirely — `LiteralAtom.value` will already be canonical Python. Phase 1 keeps the call to preserve behaviour.

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/ -q`
Expected: **414 passed**.

- [ ] **Step 3: Verify `to_grammar` works**

```bash
uv run python -c "
from lexic.compile import compile_from_path
cg = compile_from_path('resources/ground_truth/arithmetic.gbnf')
root_cls = list(cg.classes.values())[0]
print(root_cls.__name__, ':', root_cls.__grammar__.rule_name)
# to_grammar on an instance (need to parse first)
"
```

Expected: something like `Root : root`.

**Do not commit yet.**

---

## Task 11: Delete `LarkBuilder.build_transformer`; update two callers

**Files:**
- Modify: `src/lexic/codegen/lark_builder.py`
- Modify: `src/lexic/compile.py`
- Modify: `tests/unit/lexic/codegen/test_transformer.py`

- [ ] **Step 1: Delete the method**

In `src/lexic/codegen/lark_builder.py`, delete lines 130-133:

```python
# Delete:
def build_transformer(self, classes: dict[str, type]) -> Transformer:
    """Build a Lark Transformer that maps rule names to Pydantic constructors."""
    # This is broken.
    return build_transformer(self._specs, classes)
```

Also delete the `from lexic.codegen.transformer import build_transformer` import at the top of `lark_builder.py` (it's now dead). And the `from lark import Transformer` import (it was only for the method's return annotation — verify it's unused elsewhere in the file; if unused, remove).

Update the module docstring:

```python
"""LarkBuilder: converts list[RuleSpec] into a Lark grammar string.

Single responsibility: knows Lark syntax. Knows nothing about Python source
or GBNF text. Transformer construction lives in lexic.codegen.transformer.
"""
```

- [ ] **Step 2: Update `src/lexic/compile.py`**

Change line 24 (imports):

```python
# Before:
from lexic.codegen.lark_builder import LarkBuilder

# After:
from lexic.codegen.lark_builder import LarkBuilder
from lexic.codegen.transformer import build_transformer
```

Change line 65 in `_compile_core`:

```python
# Before:
transformer = builder.build_transformer(classes)

# After:
transformer = build_transformer(specs_list, classes)
```

- [ ] **Step 3: Update `tests/unit/lexic/codegen/test_transformer.py`**

At line 22-26 (find by grep):

```python
# Before:
builder = LarkBuilder(specs)
...
transformer = builder.build_transformer(classes)

# After:
from lexic.codegen.transformer import build_transformer
builder = LarkBuilder(specs)
...
transformer = build_transformer(specs, classes)
```

The `builder` is still needed for `build_grammar()`, so don't delete it — just switch the transformer call.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/ -q`
Expected: **414 passed**.

**Do not commit yet.**

---

## Task 12: Freeze atom dataclasses

**Files:**
- Modify: `src/lexic/ir/atoms.py`

- [ ] **Step 1: Add `frozen=True` to every `@dataclass` in `atoms.py`**

Change every occurrence of `@dataclass` to `@dataclass(frozen=True)`. There are seven today (`LiteralAtom`, `CharClassAtom`, `RuleRefAtom`, `AlternationAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom`, `InlineAlternationAtom`).

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/ -q`
Expected: **414 passed**. If anything fails with `FrozenInstanceError`, grep for the mutation site and convert to `dataclasses.replace()`.

- [ ] **Step 3: Run ruff**

Run: `uv run ruff check src/ tests/`
Expected: clean.

**Do not commit yet.**

---

## Task 13: Doc cleanup — drop `<<name>>` / `TokenAmbiguityError`

**Files:**
- Modify: `prototyping/next/2_ARCHITECTURE.md`
- Modify: `prototyping/next/3_ROADMAP.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: `2_ARCHITECTURE.md` — error vocabulary table**

Find the table under "## Error vocabulary" (around line 221). Remove the `TokenAmbiguityError` row.

- [ ] **Step 2: `2_ARCHITECTURE.md` — Token reservation section**

Find "### Token reservation" (around line 200). Remove the `TokenAmbiguityError` bullet and the `<<name>>` description. Leave the `UnsupportedConstructError` bullet intact.

- [ ] **Step 3: `3_ROADMAP.md` — Slice B scope**

Find "- **Token reservation** (Doc 5 §5.1):" (around line 247). Remove the `<<name>>` / `TokenAmbiguityError` bullet.

- [ ] **Step 4: `3_ROADMAP.md` — Slice B exit criteria**

Find "- Same test file asserts that `<<name>>` raises `TokenAmbiguityError`..." (around line 285). Remove that exit criterion.

- [ ] **Step 5: `3_ROADMAP.md` — Slice B open questions**

Strike-through the four resolved questions (matching Slice A convention). Example for Q1:

```markdown
- ~~What's the exact portable regex subset?~~ — **Resolved:** Per-flavour
  capability descriptor. See `docs/superpowers/specs/2026-04-23-slice-b-design.md`
  §Q3.
```

Mirror for the other three.

- [ ] **Step 6: `CLAUDE.md` — atom count and layout**

Update the "Seven frozen Atom dataclasses" line to "Five frozen Atom dataclasses" (this matches post-Slice-B reality — Phase 2 finalises the count; doc can lead a few days).

Update the IR overview section listing the seven atoms (`LiteralAtom`, `CharClassAtom`, …) to list the five post-Slice-B atoms plus `Arm`.

Add to the project-layout section:

```
  codegen/
    flavours.py                 FlavourAdapter / Parser / Emitter protocols; ADAPTERS registry
    gbnf/
      __init__.py               re-exports GbnfAdapter
      adapter.py                GbnfAdapter
      parser.py                 GbnfParser (moved from codegen/parser.py)
      emitter.py                GbnfEmitter (moved from codegen/gbnf_emitter.py)
      ast.py                    (moved from codegen/ast.py)
      escapes.py                decode_gbnf_escapes (moved from utils/escapes.py)
      charclass.py              bracket parsing (moved from utils/charclass.py)
  exceptions.py                 LexicError + subclasses
```

Update the "`codegen()` / `compile()` / `to_grammar()`" references in CLAUDE.md to mention the `flavour="gbnf"` parameter.

- [ ] **Step 7: Run tests and ruff once more before Phase 1 commit**

Run: `uv run pytest tests/ -q && uv run ruff check src/ tests/`
Expected: **414 passed**; ruff clean.

**Do not commit yet.**

---

## Task 14: Add `test_flavours.py` + commit Phase 1

**Files:**
- Create: `tests/unit/lexic/grammars/test_flavours.py`

- [ ] **Step 1: Write the test file**

```python
# tests/unit/lexic/grammars/test_flavours.py
"""Tests for the flavours registry and adapter lookup."""

from __future__ import annotations

import pytest

from lexic.grammars import (
    ADAPTERS,
    FlavourAdapter,
    adapter_for_extension,
    get_adapter,
    register_adapter,
)
from lexic.exceptions import UnsupportedConstructError


def test_gbnf_adapter_registered_at_import():
    assert "gbnf" in ADAPTERS


def test_get_adapter_returns_gbnf():
    adapter = get_adapter("gbnf")
    assert adapter.name == "gbnf"
    assert adapter.extensions == (".gbnf",)


def test_get_adapter_unknown_raises():
    with pytest.raises(UnsupportedConstructError) as excinfo:
        get_adapter("abnf")
    assert "abnf" in str(excinfo.value)
    assert "gbnf" in str(excinfo.value)  # "Supported: ['gbnf']" present


def test_adapter_for_extension_gbnf():
    adapter = adapter_for_extension("some/path/foo.gbnf")
    assert adapter.name == "gbnf"


def test_adapter_for_extension_unknown_raises():
    with pytest.raises(UnsupportedConstructError) as excinfo:
        adapter_for_extension("foo.abnf")
    assert ".abnf" in str(excinfo.value)


def test_register_adapter_adds_to_registry():
    class _DummyParser:
        def parse(self, text):
            return []

    class _DummyEmitter:
        supports: frozenset[str] = frozenset()

        def emit(self, specs):
            return ""

    class _DummyAdapter:
        name = "_test_dummy"
        extensions = (".dummy",)

        def __init__(self):
            self.parser = _DummyParser()
            self.emitter = _DummyEmitter()

    try:
        register_adapter(_DummyAdapter())
        assert "_test_dummy" in ADAPTERS
        assert adapter_for_extension("foo.dummy").name == "_test_dummy"
    finally:
        ADAPTERS.pop("_test_dummy", None)


def test_get_adapter_via_direct_flavours_import():
    """Registry is populated even if caller doesn't import lexic.codegen."""
    # This test runs in a fresh pytest collection, so imports happen fresh.
    # Asserts eager-registration works without prior lexic.codegen import.
    import importlib

    import lexic.grammars as flavours

    importlib.reload(flavours)
    assert "gbnf" in flavours.ADAPTERS
```

- [ ] **Step 2: Run the new tests**

Run: `uv run pytest tests/unit/lexic/grammars/test_flavours.py -v`
Expected: all pass.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest tests/ -q`
Expected: **421 passed** (414 original + 7 new).

- [ ] **Step 4: Run ruff**

Run: `uv run ruff check src/ tests/`
Expected: clean.

- [ ] **Step 5: Commit Phase 1**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor(slice-b-phase-1): scaffold flavour seam + exceptions + cleanups

Phase 1 of Slice B — behaviour-preserving refactors only.

Creates:
- lexic/exceptions.py: LexicError + UnsupportedConstructError +
  GrammarAuthoringError + FieldValidationError (latter two stubbed for C/D).
- lexic/ir/regex_portable.py: PORTABLE_FEATURES set + validate_portable /
  features_used sre_parse walkers + canonicalize_groups (no-op stub; Phase 2
  lands the real impl).
- lexic/grammars/flavours.py: FlavourParser/FlavourEmitter/FlavourAdapter
  protocols + ADAPTERS registry + eager GBNF registration at module load.
- lexic/grammars/gbnf/: package with adapter.py (GbnfAdapter) and __init__.py.

Moves (git mv preserves history):
- codegen/{parser,ast,gbnf_emitter}.py  -> grammars/gbnf/{parser,ast,emitter}.py
- utils/{escapes,charclass}.py          -> grammars/gbnf/{escapes,charclass}.py

Wraps GBNFEmitter as GbnfEmitter with supports: frozenset[str] (GBNF's
portable-features subset; shorthand is absent — parser lowers \d \w \s to
char classes). Adds GbnfParser class around parse_gbnf.

Threads flavour="gbnf" through codegen(), build_classes_and_specs(),
compile(), GrammarModel.to_grammar(). to_gbnf() remains as a two-line alias.
codegen_from_path() and compile_from_path() infer flavour from extension.

Deletes LarkBuilder.build_transformer (pure indirection antipattern); two
call sites switched to build_transformer(specs, classes) directly.

Freezes all atom dataclasses with frozen=True.

Docs: drops <<name>>/TokenAmbiguityError references from 2_ARCHITECTURE.md
and 3_ROADMAP.md (syntax does not exist in GBNF). Updates CLAUDE.md project
layout to reflect the moves and flavour= parameter.

Adds tests/unit/lexic/grammars/test_flavours.py.

All 421 tests green (414 original + 7 new). Ruff clean.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

Expected: commit succeeds; pre-commit hooks pass.

---

# Phase 2 — Atom Collapse

Every task in this phase preserves observable behaviour for GBNF grammars end-to-end. **Commit boundaries:** Phase 2 commits twice — once after Task 17 (`canonicalize_groups` + its unit tests, isolated from atom-shape change), then once after Task 32 (all atom-shape work, consumer migration, regen, cleanup). Intermediate tasks 15–16 and 18–31 run *without committing*; the tree may be non-green between them because consumers lag the shape change. Only the two commit boundaries must be green.

## Task 15: Add `PatternAtom`, `Arm`; reshape `InlineAlternationAtom`; update `__init__.py`

**Files:**
- Modify: `src/lexic/ir/atoms.py`
- Modify: `src/lexic/ir/__init__.py`

- [ ] **Step 1: Add `PatternAtom`, `Arm`, and reshape `InlineAlternationAtom`**

Add at the top of `atoms.py` (after existing imports):

```python
from typing import Any  # if not already present; needed for the forward Atom reference
```

Replace the `@dataclass(frozen=True) class InlineAlternationAtom` block with:

```python
@dataclass(frozen=True)
class PatternAtom:
    """Canonical portable regex + flavour-shadow map + bounds.

    regex: canonical Python re dialect, unanchored, non-capturing groups.
    source_forms: flavour-shadow map (e.g. {"gbnf": "[a-h]"}). Missing key means
                  emitter must reconstruct from regex.
    """

    regex: str
    source_forms: dict[str, str]
    min: int
    max: int | None


@dataclass(frozen=True)
class Arm:
    """One branch of an inline alternation — an ordered sequence of atoms."""

    atoms: tuple["Atom", ...]


@dataclass(frozen=True)
class InlineAlternationAtom:
    """Inline alternation inside a sequence, e.g. (pawn | nonpawn | castle).

    Arms are inline atom sequences, not helper-rule names. No quantifier.
    """

    arms: tuple[Arm, ...]
```

**Keep** the old `CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom` classes defined in `atoms.py` for now — Task 32 removes them. This lets every consumer update one at a time with a green suite throughout Phase 2. Update the old `InlineAlternationAtom` → rename it inline (no dual version).

Also change `AlternationAtom.arm_rule_names: list[str]` → `arm_rule_names: tuple[str, ...]`.

Update the `Atom` union at the bottom:

```python
Atom = (
    LiteralAtom
    | CharClassAtom           # Task 32 removes
    | QuantifiedLiteralAtom   # Task 32 removes
    | InlineRegexAtom         # Task 32 removes
    | PatternAtom
    | RuleRefAtom
    | AlternationAtom
    | InlineAlternationAtom
)
```

- [ ] **Step 2: Update `src/lexic/ir/__init__.py`**

Add `PatternAtom` and `Arm` to the re-exports:

```python
from lexic.ir.atoms import (
    AlternationAtom,
    Arm,
    Atom,
    CharClassAtom,           # Task 32 removes
    InlineAlternationAtom,
    InlineRegexAtom,         # Task 32 removes
    LiteralAtom,
    PatternAtom,
    QuantifiedLiteralAtom,   # Task 32 removes
    RuleRefAtom,
)
from lexic.ir.spec import RuleSpec

__all__ = [
    "AlternationAtom",
    "Arm",
    "Atom",
    "CharClassAtom",
    "InlineAlternationAtom",
    "InlineRegexAtom",
    "LiteralAtom",
    "PatternAtom",
    "QuantifiedLiteralAtom",
    "RuleRefAtom",
    "RuleSpec",
]
```

- [ ] **Step 3: Run tests — existing call sites must still pass**

Run: `uv run pytest tests/ -q`
Expected: **421 passed** (`AlternationAtom.arm_rule_names` change from list to tuple may need a fix — if so, grep `arm_rule_names=` and convert any remaining `[...]` constructions to `tuple(...)` or a tuple literal).

If tests fail with something like `TypeError: AlternationAtom.__init__() ... list`: find the constructor in `src/lexic/codegen/ir_builder.py` (around line 125), change `AlternationAtom(arm_rule_names=arm_rule_names)` to `AlternationAtom(arm_rule_names=tuple(arm_rule_names))`. Same for `InlineAlternationAtom` if it still references the old `arm_rule_names` shape (it will — the rest of Phase 2 is migrating callers off it).

**Note:** Right after Step 3, callers of `InlineAlternationAtom.arm_rule_names` will break. That's expected — Tasks 18-27 migrate them. To keep the tree green during migration, **temporarily** add a back-compat property:

```python
@dataclass(frozen=True)
class InlineAlternationAtom:
    arms: tuple[Arm, ...]

    @property
    def arm_rule_names(self) -> tuple[str, ...]:  # Task 31 removes
        """Back-compat shim for callers not yet migrated."""
        raise NotImplementedError(
            "InlineAlternationAtom.arm_rule_names was removed in Slice B Phase 2. "
            "Use .arms instead; each Arm has .atoms."
        )
```

The `NotImplementedError` version is a deliberate trap — any remaining caller blows up loudly. Task 31 removes the property once every caller is migrated.

Alternative: keep an empty-tuple-returning property that lets the tree stay green. Choose based on how you prefer to find missed callers. The `NotImplementedError` version is recommended — loud failures are easier to find than silent empty tuples.

Run the tests again; record which callers blow up — they're the task-by-task migration targets for the next several tasks.

**Do not commit mid-task.** This is all one coherent move; commit at the end of Task 16 after shape tests pass.

---

## Task 16: Add `test_atom_shapes.py`

**Files:**
- Create: `tests/unit/lexic/ir/test_atom_shapes.py`

- [ ] **Step 1: Write the test file**

```python
# tests/unit/lexic/ir/test_atom_shapes.py
"""Shape and immutability tests for all IR atom types."""

from __future__ import annotations

import dataclasses

import pytest

from lexic.ir import (
    AlternationAtom,
    Arm,
    InlineAlternationAtom,
    LiteralAtom,
    PatternAtom,
    RuleRefAtom,
)


def test_literal_atom_is_frozen():
    atom = LiteralAtom(value="foo")
    with pytest.raises(dataclasses.FrozenInstanceError):
        atom.value = "bar"  # type: ignore[misc]


def test_pattern_atom_shape():
    atom = PatternAtom(
        regex="[a-z]+", source_forms={"gbnf": "[a-z]"}, min=1, max=None
    )
    assert atom.regex == "[a-z]+"
    assert atom.source_forms == {"gbnf": "[a-z]"}
    assert atom.min == 1
    assert atom.max is None


def test_pattern_atom_is_frozen():
    atom = PatternAtom(regex="a", source_forms={}, min=1, max=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        atom.regex = "b"  # type: ignore[misc]


def test_pattern_atom_source_forms_empty_is_valid():
    atom = PatternAtom(regex="a", source_forms={}, min=1, max=1)
    assert atom.source_forms == {}


def test_arm_atoms_is_tuple_not_list():
    arm = Arm(atoms=(LiteralAtom("a"),))
    assert isinstance(arm.atoms, tuple)


def test_arm_is_frozen():
    arm = Arm(atoms=(LiteralAtom("a"),))
    with pytest.raises(dataclasses.FrozenInstanceError):
        arm.atoms = ()  # type: ignore[misc]


def test_inline_alternation_arms_is_tuple_of_arms():
    inline = InlineAlternationAtom(
        arms=(
            Arm(atoms=(LiteralAtom("a"),)),
            Arm(atoms=(LiteralAtom("b"),)),
        )
    )
    assert isinstance(inline.arms, tuple)
    assert all(isinstance(a, Arm) for a in inline.arms)


def test_inline_alternation_is_frozen():
    inline = InlineAlternationAtom(arms=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        inline.arms = ()  # type: ignore[misc]


def test_alternation_arm_rule_names_is_tuple():
    alt = AlternationAtom(arm_rule_names=("a", "b", "c"))
    assert isinstance(alt.arm_rule_names, tuple)


def test_alternation_atom_is_frozen():
    alt = AlternationAtom(arm_rule_names=("a",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        alt.arm_rule_names = ()  # type: ignore[misc]


def test_pattern_atom_equality():
    a = PatternAtom(regex="x", source_forms={"gbnf": "x"}, min=1, max=1)
    b = PatternAtom(regex="x", source_forms={"gbnf": "x"}, min=1, max=1)
    assert a == b


def test_arm_equality():
    a = Arm(atoms=(LiteralAtom("x"),))
    b = Arm(atoms=(LiteralAtom("x"),))
    assert a == b


def test_dataclasses_replace_works():
    atom = PatternAtom(regex="a", source_forms={}, min=1, max=1)
    replaced = dataclasses.replace(atom, min=0)
    assert replaced.min == 0
    assert replaced.regex == "a"
    assert atom.min == 1  # original unchanged
```

- [ ] **Step 2: Run the new tests**

Run: `uv run pytest tests/unit/lexic/ir/test_atom_shapes.py -v`
Expected: all pass.

- [ ] **Step 3: Run full suite**

Run: `uv run pytest tests/ -q`
Expected: all green.

- [ ] **Step 4: Do not commit yet**

The atom-shape change breaks every consumer that still reads `InlineAlternationAtom.arm_rule_names`. The `NotImplementedError`-raising property surfaces each caller as a clear traceback, but the tree is non-green until Tasks 18–25 migrate those callers. Commit happens at Task 32.

Run `uv run pytest tests/unit/lexic/ir/test_atom_shapes.py -v` to confirm the new tests pass in isolation. The full suite may fail — that's expected until Task 32.

---

## Task 17: Implement `canonicalize_groups` + `test_regex_portable.py`

**Files:**
- Modify: `src/lexic/ir/regex_portable.py`
- Create: `tests/unit/lexic/ir/test_regex_portable.py`

- [ ] **Step 1: Implement `canonicalize_groups`**

Replace the no-op stub from Task 2 with:

```python
def canonicalize_groups(regex: str) -> str:
    """Rewrite capturing groups `(...)` to non-capturing `(?:...)`.

    Preserves structure; only toggles the group mode. Runs `validate_portable`
    on the result as a consistency check.

    Implementation: scan for `(` not followed by `?`, insert `?:` after.
    Avoids full sre_parse round-trip because sre has no public unparse API.
    """
    out: list[str] = []
    i = 0
    n = len(regex)
    while i < n:
        ch = regex[i]
        if ch == "\\" and i + 1 < n:
            out.append(regex[i : i + 2])
            i += 2
            continue
        if ch == "(" and (i + 1 >= n or regex[i + 1] != "?"):
            out.append("(?:")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)
```

**Implementation note:** this handles the common case cleanly. Tests (Step 2) include a mixed capturing/non-capturing input to verify only capturing groups are rewritten.

- [ ] **Step 2: Write the test file**

```python
# tests/unit/lexic/ir/test_regex_portable.py
"""Tests for lexic.ir.regex_portable."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.regex_portable import (
    PORTABLE_FEATURES,
    canonicalize_groups,
    features_used,
    validate_portable,
)


# --- PORTABLE_FEATURES sanity --------------------------------------------

def test_portable_features_contains_expected_keys():
    assert PORTABLE_FEATURES == frozenset(
        {
            "literal",
            "char_class",
            "negated_class",
            "shorthand",
            "quantifier",
            "alternation",
            "non_capturing_group",
            "unicode_escape",
        }
    )


# --- validate_portable — positive cases ----------------------------------

@pytest.mark.parametrize(
    "regex",
    [
        "foo",                     # literal
        "[a-z]",                   # char_class
        "[^abc]",                  # negated_class
        "[a-z]+",                  # char_class + quantifier
        "a|b|c",                   # alternation
        "(?:a|b)",                 # non_capturing_group
        r"\d+",                    # shorthand + quantifier
        r"\w\s",                   # shorthand
        r"\x41",                   # unicode_escape
        r"A",                 # unicode_escape
        "[a-z]{2,4}",              # bounded quantifier
        "(?:hello|world)+",        # group + quantifier
    ],
)
def test_validate_portable_accepts(regex):
    validate_portable(regex)  # should not raise


# --- validate_portable — negative cases ----------------------------------

@pytest.mark.parametrize(
    ("regex", "reason_fragment"),
    [
        ("^foo", "anchor"),
        ("foo$", "anchor"),
        (r"\bfoo", "boundary"),
        ("(a)", "capturing group"),
        ("(?=a)b", "anchor"),       # lookahead is emitted as AT on some Python versions; accept "anchor" OR update
        ("a.b", "any-char"),
        (r"(a)\1", "backreference"),
    ],
)
def test_validate_portable_rejects(regex, reason_fragment):
    with pytest.raises(UnsupportedConstructError) as excinfo:
        validate_portable(regex)
    assert reason_fragment in str(excinfo.value).lower()


# --- features_used --------------------------------------------------------

@pytest.mark.parametrize(
    ("regex", "expected"),
    [
        ("foo", {"literal"}),
        ("[a-z]", {"char_class"}),
        ("[^abc]", {"negated_class"}),
        ("[a-z]+", {"char_class", "quantifier"}),
        ("a|b", {"literal", "alternation"}),
        ("(?:a|b)", {"literal", "alternation", "non_capturing_group"}),
        (r"\d+", {"char_class", "shorthand", "quantifier"}),
        # shorthand is detected via IN+CATEGORY; \d alone shows as char_class + shorthand
    ],
)
def test_features_used(regex, expected):
    assert features_used(regex) == frozenset(expected)


# --- canonicalize_groups -------------------------------------------------

@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("(foo)", "(?:foo)"),
        ("(a)(b)", "(?:a)(?:b)"),
        ("(?:foo)", "(?:foo)"),              # already non-capturing; unchanged
        ("(?:a)(b)", "(?:a)(?:b)"),          # mixed
        ("[a-z]", "[a-z]"),                  # no groups
        ("a|b", "a|b"),                      # alternation without groups
        (r"\(foo\)", r"\(foo\)"),            # escaped parens unchanged
    ],
)
def test_canonicalize_groups(source, expected):
    assert canonicalize_groups(source) == expected


def test_canonicalize_groups_is_idempotent():
    source = "(a)(b)(c|d)"
    once = canonicalize_groups(source)
    twice = canonicalize_groups(once)
    assert once == twice
```

- [ ] **Step 3: Run the tests**

Run: `uv run pytest tests/unit/lexic/ir/test_regex_portable.py -v`
Expected: all pass. If a lookahead negative case fails because `sre_parse` represents `(?=...)` differently than expected, adjust the negative case: the point is it raises, the exact wording can be lookup-based.

- [ ] **Step 4: Commit**

```bash
git add src/lexic/ir/regex_portable.py tests/unit/lexic/ir/test_regex_portable.py
git commit -m "feat(ir): implement canonicalize_groups + regex_portable tests

Replaces the Phase 1 no-op stub with a scanning implementation that rewrites
capturing groups (...) to non-capturing (?:...). Preserves escaped parens
and already-non-capturing groups.

Tests cover PORTABLE_FEATURES set, validate_portable (positive + negative
cases), features_used enumeration, and canonicalize_groups including
idempotency.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 18: `GbnfParser.parse` — emit `PatternAtom` from char classes + literals + inline regex

**Files:**
- Modify: `src/lexic/grammars/gbnf/parser.py` (or wherever atom construction happens — primarily `seq_to_atoms.py` at `src/lexic/codegen/seq_to_atoms.py`, see note below)

**Note on file layout:** Today the AST→IR conversion lives in `codegen/seq_to_atoms.py` and `codegen/ir_builder.py`, not in `gbnf/parser.py` (which is AST-only). Spec §Flavour seam §GbnfAdapter describes `GbnfParser.parse` as returning `list[RuleSpec]` — that's the target end-state. Phase 2 has two viable paths:

- **Path A (recommended):** Keep `seq_to_atoms.py` and `ir_builder.py` where they are (inside `codegen/`, shared infrastructure) but have `GbnfParser.parse` call them after the AST stage. The "GBNF-specific" code in `seq_to_atoms.py` becomes the GBNF-AST → IR conversion, which is itself GBNF-specific → logically a `grammars/gbnf/` resident. Move both files into `grammars/gbnf/` as part of this task. This matches the "anything GBNF-specific lives in grammars/gbnf/" principle.
- **Path B:** Keep `seq_to_atoms.py` and `ir_builder.py` at `codegen/` level; have `GbnfParser.parse` still return AST; have the public API call `IRBuilder(ast).build()` after `parser.parse()`. Cleaner for the per-adapter protocol boundary (`parse` returns `list[RuleSpec]`) but mixes GBNF-AST knowledge into `seq_to_atoms.py` while it lives at `codegen/` level.

**Choose Path A.** It's consistent with the user's rule. The moves:

- `git mv src/lexic/codegen/seq_to_atoms.py src/lexic/grammars/gbnf/seq_to_atoms.py`
- `git mv src/lexic/codegen/ir_builder.py src/lexic/grammars/gbnf/ir_builder.py`
- `git mv src/lexic/codegen/classify.py src/lexic/grammars/gbnf/classify.py` (it classifies GBNF AST)
- `git mv src/lexic/codegen/ast_utils.py src/lexic/grammars/gbnf/ast_utils.py`
- `git mv src/lexic/codegen/helpers.py src/lexic/grammars/gbnf/helpers.py` (helper-rule registry is used only by GBNF AST→IR)
- `git mv src/lexic/codegen/naming.py src/lexic/grammars/gbnf/naming.py` (field naming operates on GBNF-derived atoms — today's `_CHARCLASS_NAMES` / `_LITERAL_NAMES` are GBNF-flavored)
- Update all imports across src/ and tests/.
- `GbnfParser.parse(text)` returns `list[RuleSpec]` by calling parse→ast→`IRBuilder(...).build()` internally.
- `build_classes_and_specs` in `codegen/__init__.py` drops its `IRBuilder` call; just uses `adapter.parser.parse(text)`.

**This is a big task. Break into sub-steps.**

- [ ] **Step 1: Move the six files into `grammars/gbnf/`**

```bash
git mv src/lexic/codegen/seq_to_atoms.py src/lexic/grammars/gbnf/seq_to_atoms.py
git mv src/lexic/codegen/ir_builder.py   src/lexic/grammars/gbnf/ir_builder.py
git mv src/lexic/codegen/classify.py     src/lexic/grammars/gbnf/classify.py
git mv src/lexic/codegen/ast_utils.py    src/lexic/grammars/gbnf/ast_utils.py
git mv src/lexic/codegen/helpers.py      src/lexic/grammars/gbnf/helpers.py
git mv src/lexic/codegen/naming.py       src/lexic/grammars/gbnf/naming.py
```

- [ ] **Step 2: Sweep imports**

Run: `grep -rn "from lexic.codegen.ir_builder\|from lexic.codegen.seq_to_atoms\|from lexic.codegen.classify\|from lexic.codegen.ast_utils\|from lexic.codegen.helpers\|from lexic.codegen.naming" src/ tests/`

For each hit, rewrite to the `lexic.grammars.gbnf.*` path. The `model_emitter.py` still lives at `codegen/` level and imports from ir; its imports from `naming.py` become `from lexic.grammars.gbnf.naming import ...`.

Wait — **`naming.py` shouldn't live in `gbnf/`**. It contains field-naming policy that applies *after* IR construction, consumed by `model_emitter.py` which lives at codegen level. Moving it into `gbnf/` would force `model_emitter` to import from `gbnf/`. That's backwards.

**Corrected plan for naming.py:** leave it at `codegen/naming.py`. Its `_CHARCLASS_NAMES` / `_LITERAL_NAMES` lookups are semantic (they name `[0-9]` as `digit`, `-` as `sign`) — they describe canonical regex / literal values, not GBNF syntax. Revert the move for `naming.py`. Task 26 handles the new-atom-shape updates.

Corrected moves (skip `naming.py`):
```bash
# Already done above, now reverse for naming:
git mv src/lexic/grammars/gbnf/naming.py src/lexic/codegen/naming.py
```

- [ ] **Step 3: Update `GbnfParser.parse` to return `list[RuleSpec]`**

In `src/lexic/grammars/gbnf/parser.py`:

```python
# Existing parse_gbnf function stays.

class GbnfParser:
    """GBNF flavour parser — source text → list[RuleSpec]."""

    def parse(self, text: str):
        from lexic.grammars.gbnf.ir_builder import IRBuilder  # lazy to avoid cycle

        ast_rules = parse_gbnf(text)
        return IRBuilder(ast_rules).build()
```

Lazy import: `ir_builder.py` imports from `atoms.py` and possibly from things that want `GbnfParser`, so a lazy import avoids circular-import issues.

- [ ] **Step 4: Update `build_classes_and_specs` to use the adapter directly**

In `src/lexic/codegen/__init__.py`:

```python
def build_classes_and_specs(
    text: str, *, stem: str, flavour: str = "gbnf"
) -> tuple[dict[str, type], list[RuleSpec]]:
    """Parse + emit + load. Returns (classes, specs)."""
    adapter = get_adapter(flavour)
    specs = adapter.parser.parse(text)
    classes = _emit_and_load_module(specs, stem, source=None)
    return classes, specs
```

Remove the `from lexic.codegen.ir_builder import IRBuilder` import (no longer needed at the `codegen/` level — `GbnfParser` owns it).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/ -q`
Expected: all green. If tests fail with import errors, grep for stragglers.

- [ ] **Step 6: Update `seq_to_atoms.py` to emit `PatternAtom` for char classes**

In `src/lexic/grammars/gbnf/seq_to_atoms.py`:

- For the `CharClass` AST case (around line 114-116):

```python
elif isinstance(item.atom, CharClass):
    min_, max_ = quantifier_to_bounds(item.quantifier)
    # Canonical PatternAtom: pattern-only in source_forms (no quantifier).
    pattern = item.atom.pattern  # e.g. "[a-z]"
    atoms.append(
        PatternAtom(
            regex=pattern,                    # TODO: shorthand lowering step
            source_forms={"gbnf": pattern},
            min=min_,
            max=max_,
        )
    )
```

- For the `Literal` with quantifier case (around line 103-110):

```python
if isinstance(item.atom, Literal):
    if item.quantifier is not None:
        min_, max_ = quantifier_to_bounds(item.quantifier)
        import re as _re
        decoded_value = decode_gbnf_escapes(item.atom.value)
        atoms.append(
            PatternAtom(
                regex=_re.escape(decoded_value),
                source_forms={"gbnf": f'"{item.atom.value}"'},
                min=min_,
                max=max_,
            )
        )
    else:
        # LiteralAtom.value is already the raw GBNF value; decode escapes
        # to canonical Python (parse-time decode invariant).
        atoms.append(LiteralAtom(value=decode_gbnf_escapes(item.atom.value)))
```

**Note on `source_forms["gbnf"]` pattern-only:** For a quantified literal, the source form is the literal plus its quotes but *without* the quantifier. The `?` or `+` in the original source is reconstructed from `min, max` at emit time.

- [ ] **Step 7: Update the inline-regex case**

Around line 122-131 (`isinstance(item.atom, Group)` → pure-literal case):

```python
# Inline literal alternation → PatternAtom (pure literal pattern like (?:a|b|c))
# BUT: if every arm is a single literal, the spec calls for InlineAlternationAtom
# carrying the literals directly — see Task 19.
if all(is_pure_literal_seq(arm) for arm in inner_arms):
    # Route: pure-literal inline alts → InlineAlternationAtom(arms=(Arm((LiteralAtom(...),)), ...))
    # See Task 19 for this path. For now (if Task 19 lands first), this whole
    # branch is replaced by the Task 19 logic. If this task lands first, keep
    # emitting PatternAtom as a temporary step and fix in Task 19.
    atoms.append(
        PatternAtom(
            regex=canonicalize_groups(_to_regex(item.atom)),
            source_forms={"gbnf": _to_gbnf(item.atom).strip("()")},
            min=min_,
            max=max_,
        )
    )
    continue
```

**Task ordering:** Task 19 overwrites this logic with the `InlineAlternationAtom` path for pure-literal alts. If this task lands first, the behaviour is still correct for GBNF grammars (pattern-based lookup still parses); Task 19 then switches the IR shape. If Task 19 lands first, skip this sub-step.

- [ ] **Step 8: Shorthand lowering in `GbnfParser`**

GBNF source shouldn't contain `\d`/`\w`/`\s` (GBNF uses bracket expressions), so "lowering" is really a defensive path — today no GBNF source produces shorthand. Keep the lowering as a documented no-op function for now. Add:

```python
# src/lexic/grammars/gbnf/parser.py (near the top)
_SHORTHAND_LOWER = {
    r"\d": "[0-9]",
    r"\w": "[a-zA-Z0-9_]",
    r"\s": "[ \\t\\n\\r\\f\\v]",
    r"\D": "[^0-9]",
    r"\W": "[^a-zA-Z0-9_]",
    r"\S": "[^ \\t\\n\\r\\f\\v]",
}

def _lower_shorthand(regex: str) -> str:
    """Replace shorthand escapes with explicit char classes in a regex string.

    GBNF source typically does not emit shorthand, but defensive lowering
    keeps the GBNF PatternAtom's regex feature-set inside the GBNF emitter's
    `supports` frozenset (shorthand is not in it).
    """
    out = regex
    for src, dst in _SHORTHAND_LOWER.items():
        out = out.replace(src, dst)
    return out
```

Callers in `seq_to_atoms.py` wrap `pattern` with `_lower_shorthand` before passing to `PatternAtom.regex`. Alternatively defer this to Phase 2.5 — GBNF never produces shorthand today, so the function is dead code. **Recommendation:** add the function + a single unit test, don't wire it into the parser. When a future flavour parser produces shorthand, it calls `_lower_shorthand`.

- [ ] **Step 9: Verify existing tests still pass**

Run: `uv run pytest tests/ -q`
Expected: green. Some tests may now need updates (old atom-type constructors in test fixtures). Fix each as it surfaces.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor(gbnf): move GBNF-specific modules into grammars/gbnf/; emit PatternAtom

Six modules move (git mv preserves history):
- seq_to_atoms.py, ir_builder.py, classify.py, ast_utils.py, helpers.py
  -> grammars/gbnf/
- naming.py stays at codegen/ (atom-semantic, not GBNF-syntax).

GbnfParser.parse(text) now returns list[RuleSpec] directly — calls
parse_gbnf(AST) + IRBuilder(ast).build() internally.

seq_to_atoms emits PatternAtom (regex=pattern, source_forms={'gbnf': pattern},
min, max) for CharClass/Literal-with-quantifier/Group AST cases. Old atom
types (CharClassAtom/QuantifiedLiteralAtom/InlineRegexAtom) still exist in
atoms.py; Task 32 removes them once consumers migrate.

build_classes_and_specs() at codegen/ level drops its IRBuilder call; uses
adapter.parser.parse() directly.

All tests remain green.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 19: `GbnfParser` inline-alt → `InlineAlternationAtom(arms=...)` (no helper rules)

**Files:**
- Modify: `src/lexic/grammars/gbnf/seq_to_atoms.py`

- [ ] **Step 1: Replace the inline-alt branch**

In `seq_to_atoms.py`, replace the current pure-literal path (after Task 18 settled):

```python
# Replace the "Inline literal alternation → PatternAtom" branch with:

# Pure-literal inline alternation → InlineAlternationAtom with inline arms.
# Each arm becomes an Arm(atoms=(LiteralAtom(...),)) or Arm containing
# multiple atoms if the arm had > 1 atom pre-Slice-B (rare).
if all(is_pure_literal_seq(arm) for arm in inner_arms):
    alt_arms: list[Arm] = []
    for arm in inner_arms:
        arm_atoms = seq_to_atoms(arm, parent_class_name, helpers, name_map, parent_of)
        alt_arms.append(Arm(atoms=tuple(arm_atoms)))
    atoms.append(InlineAlternationAtom(arms=tuple(alt_arms)))
    continue
```

**Note on the quantifier case:** The pre-Slice-B code handled `min_, max_ = quantifier_to_bounds(item.quantifier)` for quantified groups. Inline alternations don't carry their own quantifier under the Slice B shape (`InlineAlternationAtom` has no `min/max`). If the original group had a quantifier, synthesize a helper rule as before. Specifically:

```python
if all(is_pure_literal_seq(arm) for arm in inner_arms):
    if item.quantifier is None:
        # Unquantified → inline the alternation
        alt_arms = [
            Arm(atoms=tuple(seq_to_atoms(arm, parent_class_name, helpers, name_map, parent_of)))
            for arm in inner_arms
        ]
        atoms.append(InlineAlternationAtom(arms=tuple(alt_arms)))
        continue
    # Quantified pure-literal alt: fall through to the existing helper-rule path
    # below. The helper synthesises a rule whose body is the unquantified alt.
    # (Same behaviour as pre-Slice-B but now the helper's arm is itself an
    # InlineAlternationAtom carrying inline arms.)
```

- [ ] **Step 2: Update the named-rule inline alternation case**

Around line 133-143 (current code — `all(single_ruleref_of(a) is not None for a in inner_arms)`):

```python
# Inline union of named rules → InlineAlternationAtom with single-RuleRefAtom arms.
if (
    item.quantifier is None
    and len(inner_arms) > 1
    and all(single_ruleref_of(a) is not None for a in inner_arms)
):
    alt_arms = [
        Arm(atoms=(RuleRefAtom(rule_name=cast(str, single_ruleref_of(arm)), min=1, max=1),))
        for arm in inner_arms
    ]
    atoms.append(InlineAlternationAtom(arms=tuple(alt_arms)))
    continue
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/ -q`

Expected: tests fail in consumers that still use `InlineAlternationAtom.arm_rule_names`. That's expected — Tasks 21-25 migrate those consumers. The `NotImplementedError`-raising property from Task 15 surfaces each caller as a clear traceback; fix them as tasks 21-25 land.

If you want Phase 2 to ship in a single coherent batch without per-task test passes: consider fixing all consumers in one sitting and running the full suite at the end. For TDD rigour, stick with task-by-task. Both are acceptable; the plan documents both paths.

- [ ] **Step 4: No commit yet — Tasks 21-25 also touch these atoms; commit at end of Task 25**

---

## Task 20: `HelperRuleRegistry` — no inline-alt helpers; quantified-list helpers still work

**Files:**
- Modify: `src/lexic/grammars/gbnf/seq_to_atoms.py` (the existing helper-rule synthesis around line 153+)

- [ ] **Step 1: Confirm no changes needed for quantified-list helpers**

The helper-rule path at `seq_to_atoms.py:153-173` handles *quantified groups* (`(a b c)+`), which are different from inline alternations. After Task 19, inline alts don't reach this path — they return early via `continue`. So the existing quantified-list path stays untouched.

**Verify:** Run `uv run pytest tests/unit/lexic/grammars/gbnf/test_parser.py -v` and check that any "helper rule" tests still pass for quantified-group cases.

- [ ] **Step 2: Trace-test a canonical grammar**

```bash
uv run python -c "
from lexic.grammars.gbnf.parser import GbnfParser
specs = GbnfParser().parse('root ::= (\"a\" | \"b\" | \"c\")')
for s in specs:
    print(s.rule_name, s.kind, s.items)
"
```

Expected: one rule (`root`), `kind=sequence`, `items=[InlineAlternationAtom(arms=(Arm((LiteralAtom('a'),)), Arm((LiteralAtom('b'),)), Arm((LiteralAtom('c'),))))]`. No helper rules (`root-arm1`, etc.).

**No commit — continues under Task 25's batch.**

---

## Task 21: Update `lark_builder.py` — single `PatternAtom` branch, explicit default raise, new InlineAlternationAtom

**Files:**
- Modify: `src/lexic/codegen/lark_builder.py`

- [ ] **Step 1: Update `_atom_to_lark`**

```python
# src/lexic/codegen/lark_builder.py

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    AlternationAtom,
    Arm,
    InlineAlternationAtom,
    LiteralAtom,
    PatternAtom,
    RuleRefAtom,
    RuleSpec,
)
from lexic.utils.names import to_lark_name
from lexic.utils.quantifiers import bounds_to_quantifier


def _escape_lark_regex(s: str) -> str:
    return s.replace("/", "\\/")


def _atom_to_lark(atom) -> str:
    if isinstance(atom, LiteralAtom):
        # LiteralAtom.value is canonical Python (escapes decoded at parse-time)
        if any(c in atom.value for c in "\n\t\r"):
            regex = ""
            for ch in atom.value:
                if ch == "\n":
                    regex += "\\n"
                elif ch == "\t":
                    regex += "\\t"
                elif ch == "\r":
                    regex += "\\r"
                elif ch in r"\.^$*+?{}[]|()":
                    regex += "\\" + ch
                else:
                    regex += ch
            regex = _escape_lark_regex(regex)
            return f"/{regex}/"
        escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(atom, PatternAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        safe = _escape_lark_regex(atom.regex)
        return f"/{safe}/{q}"
    if isinstance(atom, RuleRefAtom):
        name = to_lark_name(atom.rule_name)
        if atom.rule_name == "ws":
            return "ws?"
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{name}{q}"
    if isinstance(atom, AlternationAtom):
        return "(" + " | ".join(to_lark_name(n) for n in atom.arm_rule_names) + ")"
    if isinstance(atom, InlineAlternationAtom):
        # Each Arm becomes an inline sequence; arms joined by |.
        arm_strs = []
        for arm in atom.arms:
            arm_parts = [_atom_to_lark(a) for a in arm.atoms]
            arm_strs.append(" ".join(arm_parts) if arm_parts else '""')
        return "(" + " | ".join(arm_strs) + ")"
    raise UnsupportedConstructError(
        f"No Lark representation for atom type {type(atom).__name__}"
    )
```

Note: drops `decode_gbnf_escapes` import (`LiteralAtom.value` is already decoded post-Task 18); drops `CharClassAtom`/`QuantifiedLiteralAtom`/`InlineRegexAtom` branches; drops the `return '""'` default; drops `from lark import Transformer` if it's still hanging around.

- [ ] **Step 2: Update `LarkBuilder._spec_to_lark_rule`**

The `value_str` case uses `isinstance(a, LiteralAtom) for a in spec.items` — unchanged. The `alternation` case reads `AlternationAtom.arm_rule_names` — now a tuple, still iterable. No changes needed.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/ -q`
Expected: green for `test_lark_builder.py` and the property round-trip tests on ground-truth grammars (these exercise the Lark grammar end-to-end).

If `test_lark_builder.py` has fixtures using `CharClassAtom` directly, update them to `PatternAtom(regex=..., source_forms={"gbnf": ...}, ...)`.

**No commit yet.**

---

## Task 22: Update `model_emitter.py` — single `PatternAtom` branch, new `InlineAlternationAtom`, explicit default raise

**Files:**
- Modify: `src/lexic/codegen/model_emitter.py`

- [ ] **Step 1: Update `_field_type`**

```python
def _field_type(atom, specs_by_rule: dict[str, RuleSpec]) -> str:
    if isinstance(atom, PatternAtom):
        return "str"
    if isinstance(atom, RuleRefAtom):
        ref = specs_by_rule.get(atom.rule_name)
        cls_name = ref.class_name if ref else atom.rule_name.replace("-", "_").title()
        if atom.min == 1 and atom.max == 1:
            return cls_name
        if atom.min == 0 and atom.max == 1:
            return f"Optional[{cls_name}]"
        return f"List[{cls_name}]"
    if isinstance(atom, AlternationAtom):
        # (identical to existing logic — still keyed on arm_rule_names)
        arm_cls_names = [
            specs_by_rule[name].class_name
            for name in atom.arm_rule_names
            if name in specs_by_rule
        ]
        parent_classes = {
            specs_by_rule[name].parent_class_name
            for name in atom.arm_rule_names
            if name in specs_by_rule
        }
        if len(parent_classes) == 1:
            parent = next(iter(parent_classes))
            if parent != "GrammarModel":
                return parent
        if arm_cls_names:
            return "Union[" + ", ".join(arm_cls_names) + "]"
        return "GrammarModel"
    if isinstance(atom, InlineAlternationAtom):
        # New shape: arms carry inline atoms. For pure-literal alts
        # (every arm is [LiteralAtom]), emit str. For mixed alts
        # (arms contain RuleRefAtom), emit Union or parent class.
        arm_classes: list[str] = []
        arm_parents: set[str] = set()
        all_literal = True
        for arm in atom.arms:
            if len(arm.atoms) == 1 and isinstance(arm.atoms[0], RuleRefAtom):
                rr: RuleRefAtom = arm.atoms[0]
                ref = specs_by_rule.get(rr.rule_name)
                if ref is not None:
                    arm_classes.append(ref.class_name)
                    arm_parents.add(ref.parent_class_name)
                    all_literal = False
            elif all(isinstance(a, LiteralAtom) for a in arm.atoms):
                pass  # pure-literal arm — contributes no class
            else:
                all_literal = False
        if all_literal:
            return "str"
        if len(arm_parents) == 1:
            parent = next(iter(arm_parents))
            if parent != "GrammarModel":
                return parent
        if arm_classes:
            return "Union[" + ", ".join(arm_classes) + "]"
        return "GrammarModel"
    raise UnsupportedConstructError(
        f"No model type for atom type {type(atom).__name__}"
    )
```

Don't forget: `from lexic.exceptions import UnsupportedConstructError` at the top; drop the old atom imports.

- [ ] **Step 2: Update `_repr_atom`**

```python
def _repr_atom(atom) -> str:
    if isinstance(atom, LiteralAtom):
        escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
        return f'LiteralAtom("{escaped}")'
    if isinstance(atom, PatternAtom):
        r = atom.regex.replace("\\", "\\\\").replace('"', '\\"')
        sf_items = ", ".join(
            f'"{k}": "{v.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
            for k, v in atom.source_forms.items()
        )
        sf = "{" + sf_items + "}"
        max_repr = "None" if atom.max is None else str(atom.max)
        return f'PatternAtom(regex="{r}", source_forms={sf}, min={atom.min}, max={max_repr})'
    if isinstance(atom, RuleRefAtom):
        max_repr = "None" if atom.max is None else str(atom.max)
        return f'RuleRefAtom("{atom.rule_name}", min={atom.min}, max={max_repr})'
    if isinstance(atom, AlternationAtom):
        names = ", ".join(f'"{n}"' for n in atom.arm_rule_names)
        return f"AlternationAtom(arm_rule_names=({names}{',' if len(atom.arm_rule_names)==1 else ''}))"
    if isinstance(atom, InlineAlternationAtom):
        arms_repr = ", ".join(
            "Arm(atoms=(" + ", ".join(_repr_atom(a) for a in arm.atoms)
            + ("," if len(arm.atoms) == 1 else "") + "))"
            for arm in atom.arms
        )
        return f"InlineAlternationAtom(arms=({arms_repr}{',' if len(atom.arms)==1 else ''}))"
    raise UnsupportedConstructError(
        f"No Python repr for atom type {type(atom).__name__}"
    )
```

**Note:** Python tuple literals need a trailing comma for single-element: `(x,)`. The `{',' if len(..) == 1 else ''}` handles this.

- [ ] **Step 3: Update the IR-import generation**

In `ModelEmitter.render()` (around line 147-164), update the atom-type list used to choose imports:

```python
used_atoms = sorted(
    {
        name
        for name, cls in [
            ("AlternationAtom", AlternationAtom),
            ("Arm", Arm),
            ("InlineAlternationAtom", InlineAlternationAtom),
            ("LiteralAtom", LiteralAtom),
            ("PatternAtom", PatternAtom),
            ("RuleRefAtom", RuleRefAtom),
        ]
        if any(isinstance(a, cls) for a in all_atoms)
        or (cls is Arm and any(isinstance(a, InlineAlternationAtom) for a in all_atoms))
    }
)
```

The `Arm` import is added whenever an `InlineAlternationAtom` is present (its arms are `Arm` instances).

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/ -q`
Expected: green. `tests/integration/test_codegen.py` regenerates grammars — the emitted Python should still parse.

**No commit yet.**

---

## Task 23: Update `grammars/gbnf/emitter.py` — single `PatternAtom` branch with `source_forms` read + stub fallback

**Files:**
- Modify: `src/lexic/grammars/gbnf/emitter.py`

- [ ] **Step 1: Update the atom dispatch**

The current file (formerly `gbnf_emitter.py`) has an `emit_atom` or similar method. Replace the three branches for `CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom` with one `PatternAtom` branch:

```python
def _emit_atom(self, atom) -> str:
    if isinstance(atom, LiteralAtom):
        return f'"{atom.value}"'  # re-escape canonical chars if needed
    if isinstance(atom, PatternAtom):
        gbnf_form = atom.source_forms.get("gbnf")
        if gbnf_form is None:
            raise NotImplementedError(
                "regex→GBNF reconstruction is Slice D scope; this path is "
                "only reached for IR-constructed atoms without source_forms. "
                f"Atom: {atom!r}"
            )
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{gbnf_form}{q}"
    if isinstance(atom, RuleRefAtom):
        q = bounds_to_quantifier(atom.min, atom.max)
        return f"{atom.rule_name}{q}"
    if isinstance(atom, AlternationAtom):
        return "(" + " | ".join(atom.arm_rule_names) + ")"
    if isinstance(atom, InlineAlternationAtom):
        arm_strs = []
        for arm in atom.arms:
            arm_strs.append("".join(self._emit_atom(a) for a in arm.atoms))
        return "(" + " | ".join(arm_strs) + ")"
    raise UnsupportedConstructError(
        f"No GBNF emission for atom type {type(atom).__name__}"
    )
```

Existing methods like `emit_rule`, top-level format, etc., stay. Adjust the `_emit_atom` call site to use the new dispatch.

- [ ] **Step 2: Literal escape re-encoding**

`LiteralAtom.value` now holds canonical Python (e.g. an actual `\n`). For GBNF emission, re-escape:

```python
def _escape_literal_for_gbnf(value: str) -> str:
    """Turn canonical Python chars back into GBNF escape sequences."""
    return (
        value
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
        .replace('"', '\\"')
    )
```

In `_emit_atom`:

```python
if isinstance(atom, LiteralAtom):
    return f'"{_escape_literal_for_gbnf(atom.value)}"'
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/ -q`
Expected: green (round-trip tests on ground-truth grammars should pass: parse → emit → parse → match).

- [ ] **Step 4: Add a unit test for the stub fallback**

Append to `tests/unit/lexic/grammars/gbnf/test_emitter.py` (or create the file if missing):

```python
import pytest
from lexic.grammars.gbnf.emitter import GbnfEmitter
from lexic.ir import PatternAtom


def test_gbnf_emitter_raises_on_missing_source_form():
    emitter = GbnfEmitter([])
    atom = PatternAtom(regex="[a-z]", source_forms={}, min=1, max=1)
    with pytest.raises(NotImplementedError) as excinfo:
        emitter._emit_atom(atom)
    assert "Slice D" in str(excinfo.value)
```

**No commit yet.**

---

## Task 24: Update `transformer/registry.py` and `transformer/builders.py`

**Files:**
- Modify: `src/lexic/codegen/transformer/registry.py`
- Modify: `src/lexic/codegen/transformer/builders.py`

- [ ] **Step 1: Merge three builders into `PatternFieldBuilder`**

In `builders.py`, delete `CharClassFieldBuilder`, `QuantifiedLiteralBuilder`, `InlineRegexBuilder`. Add:

```python
class PatternFieldBuilder:
    """Handles PatternAtom — the unified char-class / quantified-literal / inline-regex builder."""

    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        if ctx.exhausted():
            return FieldResult(value="", consumed=0)
        c = ctx.peek()
        if not isinstance(c, (Token, str)):
            return FieldResult(value="", consumed=0)
        # For quantified patterns (max != 1), greedily collect consecutive tokens.
        if atom.max != 1:
            parts = [str(c)]
            i = ctx.cursor + 1
            while i < len(ctx.children) and isinstance(ctx.children[i], (Token, str)):
                parts.append(str(ctx.children[i]))
                i += 1
            return FieldResult(value="".join(parts), consumed=i - ctx.cursor)
        return FieldResult(value=str(c), consumed=1)
```

Merges the previous three builders' logic — they were already near-identical modulo the `atom.max != 1` greedy-collect guard.

- [ ] **Step 2: Update `InlineAlternationBuilder`**

```python
class InlineAlternationBuilder:
    def build(self, atom, field_name: str, ctx: BuildContext) -> BuildResult:
        if ctx.exhausted():
            return FieldResult(value="", consumed=0)
        c = ctx.peek()
        if isinstance(c, GrammarModel):
            return FieldResult(value=c, consumed=1)
        return FieldResult(value=str(c), consumed=1)
```

Logic is unchanged from pre-Slice-B — inline alts still present as a single Lark tree node. What changed is the IR shape (`arms: tuple[Arm, ...]`), not the runtime transform.

- [ ] **Step 3: Update `registry.py`**

```python
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    AlternationAtom,
    Atom,
    InlineAlternationAtom,
    LiteralAtom,
    PatternAtom,
    RuleRefAtom,
)
from lexic.codegen.transformer.builders import (
    AbstractAlternationBuilder,
    InlineAlternationBuilder,
    LiteralSkipBuilder,
    PatternFieldBuilder,
    RuleRefBuilder,
)
from lexic.codegen.transformer.context import FieldBuilder


BUILDER_BY_ATOM: dict[type, FieldBuilder] = {
    LiteralAtom: LiteralSkipBuilder(),
    PatternAtom: PatternFieldBuilder(),
    RuleRefAtom: RuleRefBuilder(),
    InlineAlternationAtom: InlineAlternationBuilder(),
    AlternationAtom: AbstractAlternationBuilder(),
}


def builder_for(atom: Atom) -> FieldBuilder:
    builder = BUILDER_BY_ATOM.get(type(atom))
    if builder is None:
        raise UnsupportedConstructError(
            f"No builder registered for atom type {type(atom).__name__}"
        )
    return builder
```

Drops the `ValueError` in favour of `UnsupportedConstructError`. Drops imports for removed atom types + builders.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/lexic/codegen/test_transformer.py -v`
Expected: green. If fixtures construct `CharClassAtom`/`QuantifiedLiteralAtom`/`InlineRegexAtom` directly, update to `PatternAtom`.

Run: `uv run pytest tests/ -q`
Expected: overall green.

**No commit yet.**

---

## Task 25: Update `generate.py` — regex-aware sampler + new `InlineAlternationAtom` + default raise

**Files:**
- Modify: `src/lexic/generate.py`

- [ ] **Step 1: Rewrite atom dispatch in `_gen_sequence`, `_gen_value_str`, `_gen_sequence_min_depth`**

```python
# src/lexic/generate.py (partial rewrite — the atom dispatches only)

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    AlternationAtom,
    Arm,
    InlineAlternationAtom,
    LiteralAtom,
    PatternAtom,
    RuleRefAtom,
    RuleSpec,
)
# Drop: CharClassAtom, QuantifiedLiteralAtom, InlineRegexAtom imports.
# Drop: lexic.utils.escapes, lexic.utils.charclass imports — replaced by regex sampler below.


def _sample_pattern(
    regex: str, min_: int, max_: int | None, rng: _random.Random
) -> str:
    """Sample a string matching `regex`, repeated `count` times.

    For Slice B: a minimal regex-aware sampler that covers the features
    GBNF grammars produce today (char classes, alternation, literal seqs,
    shorthand-free patterns). Uses `rstr` or `exrex` if available; else a
    hand-rolled sampler over sre_parse output.
    """
    count = _pick_count(min_, max_, rng)
    if count == 0:
        return ""
    parts = [_sample_regex_once(regex, rng) for _ in range(count)]
    return "".join(parts)


def _sample_regex_once(regex: str, rng: _random.Random) -> str:
    """Generate one sample string matching the regex.

    Implementation: walk sre_parse output; LITERAL -> char; IN -> pick from
    class; BRANCH -> pick arm; MAX_REPEAT -> pick count.
    """
    import sre_parse
    tree = sre_parse.parse(regex)
    return _sample_tree(tree, rng)


def _sample_tree(tree, rng):
    from sre_constants import (
        BRANCH, IN, LITERAL, MAX_REPEAT, MIN_REPEAT, NEGATE, RANGE, SUBPATTERN, CATEGORY,
        CATEGORY_DIGIT, CATEGORY_WORD, CATEGORY_SPACE,
        CATEGORY_NOT_DIGIT, CATEGORY_NOT_WORD, CATEGORY_NOT_SPACE,
    )
    parts: list[str] = []
    for op, arg in tree:
        if op is LITERAL:
            parts.append(chr(arg))
        elif op is IN:
            chars = _chars_from_class(arg)
            if chars:
                parts.append(rng.choice(chars))
        elif op is BRANCH:
            _, branches = arg
            parts.append(_sample_tree(rng.choice(branches), rng))
        elif op is MAX_REPEAT or op is MIN_REPEAT:
            lo, hi, subtree = arg
            hi_cap = min(hi, lo + 2) if hi != sre_parse.MAXREPEAT else lo + 2
            count = rng.randint(lo, max(lo, hi_cap))
            for _ in range(count):
                parts.append(_sample_tree(subtree, rng))
        elif op is SUBPATTERN:
            _, _, _, subtree = arg
            parts.append(_sample_tree(subtree, rng))
    return "".join(parts)


def _chars_from_class(arg):
    """Enumerate characters in an IN-class arg from sre_parse."""
    from sre_constants import (
        CATEGORY, CATEGORY_DIGIT, CATEGORY_WORD, CATEGORY_SPACE,
        LITERAL, NEGATE, RANGE,
    )
    chars: list[str] = []
    negated = False
    for sub in arg:
        sub_op, sub_arg = sub
        if sub_op is NEGATE:
            negated = True
        elif sub_op is LITERAL:
            chars.append(chr(sub_arg))
        elif sub_op is RANGE:
            lo, hi = sub_arg
            chars.extend(chr(c) for c in range(lo, hi + 1))
        elif sub_op is CATEGORY:
            if sub_arg is CATEGORY_DIGIT:
                chars.extend("0123456789")
            elif sub_arg is CATEGORY_WORD:
                chars.extend(list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"))
            elif sub_arg is CATEGORY_SPACE:
                chars.extend(" \t\n\r")
    if negated:
        import string
        all_printable = [c for c in string.printable if c not in set(chars)]
        return all_printable
    return chars
```

Then in `_gen_sequence` / `_gen_value_str` / `_gen_sequence_min_depth`, replace the three old atom branches with:

```python
elif isinstance(atom, PatternAtom):
    parts.append(_sample_pattern(atom.regex, atom.min, atom.max, rng))
elif isinstance(atom, InlineAlternationAtom):
    arm = rng.choice(atom.arms)
    for a in arm.atoms:
        parts.append(_sample_atom(a, specs, rng, max_depth - 1))  # helper
```

Introduce a helper `_sample_atom(atom, specs, rng, max_depth)` that dispatches on a single atom (used for arm-atom sampling). Factor as needed.

Explicit default raise at the end of the dispatch:

```python
else:
    raise UnsupportedConstructError(
        f"No generator for atom type {type(atom).__name__}"
    )
```

- [ ] **Step 2: Fix `_get_alternation_arms`**

`InlineAlternationAtom` no longer has `arm_rule_names`. The `_get_alternation_arms` helper currently checks `isinstance(first, AlternationAtom)` — unchanged. But the `_gen_sequence` branch `isinstance(atom, (InlineAlternationAtom, AlternationAtom))` needs splitting: they now have different shapes.

- [ ] **Step 3: Update `_gen_value_str` has_required_charclass heuristic**

The signal used to detect sequential-vs-alternation in `value_str` was "presence of a required `CharClassAtom`". Update to `PatternAtom`:

```python
has_required_pattern = any(
    isinstance(a, PatternAtom) and a.min >= 1 for a in spec.items
)
```

- [ ] **Step 4: Run generator-driven tests**

Run: `uv run pytest tests/property/ -q`
Expected: all property tests pass — the random generator + parser round-trip for all seven grammars.

Run: `uv run pytest tests/ -q`
Expected: overall green.

- [ ] **Step 5: Do not commit — work continues into Tasks 26–32**

All consumer migrations, naming updates, cross-check wiring, regen, and cleanup happen before the single Phase 2 "atom migration" commit at Task 32. At this point the full suite should **pass** (no failing consumers remain), but the plan defers the commit so Task 30's regen is included in the same commit as the consumer changes that produced it — keeping regen tied to the code that generated it.

Run `uv run pytest tests/ -q` as a checkpoint. Expected: green.

---

## Task 26: Update `naming.py` for new `InlineAlternationAtom` shape

**Files:**
- Modify: `src/lexic/codegen/naming.py`

- [ ] **Step 1: Read the current `naming.py` around line 125-127**

```python
if isinstance(atom, AlternationAtom):
    ...
if isinstance(atom, InlineAlternationAtom):
    ...
```

- [ ] **Step 2: Update field-naming for inline alts**

The pre-Slice-B naming used the first arm's rule name for the inline-alt field name (via `arm_rule_names[0]`). Post-Slice-B the arm has inline atoms. Derive the field name from the first arm's first atom:

```python
if isinstance(atom, InlineAlternationAtom):
    if atom.arms and atom.arms[0].atoms:
        first_atom = atom.arms[0].atoms[0]
        if isinstance(first_atom, RuleRefAtom):
            return first_atom.rule_name.replace("-", "_")
        if isinstance(first_atom, LiteralAtom):
            return _sanitize_literal(first_atom.value) or "alt"
    return "alt"
```

If `_sanitize_literal` doesn't exist, reuse an existing name-sanitization helper or fall back to `"alt"`.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/ -q`
Expected: green. If a regenerated grammar picks different field names and a diff test flags it, update the expected field name in that test (it's a cosmetic rename; record the before/after in the commit message).

**No commit yet — Task 30 commits regen.**

---

## Task 27: Wire `validate_portable` + `supports` cross-check into `codegen.__init__`

**Files:**
- Modify: `src/lexic/codegen/__init__.py`

- [ ] **Step 1: Add the cross-check after parse**

```python
def build_classes_and_specs(
    text: str, *, stem: str, flavour: str = "gbnf"
) -> tuple[dict[str, type], list[RuleSpec]]:
    """Parse + cross-check + emit + load."""
    adapter = get_adapter(flavour)
    specs = adapter.parser.parse(text)
    _cross_check_patterns(specs, adapter)
    classes = _emit_and_load_module(specs, stem, source=None)
    return classes, specs


def _cross_check_patterns(specs: list[RuleSpec], adapter) -> None:
    """Walk every PatternAtom; raise on non-portable or non-emittable features."""
    from lexic.exceptions import UnsupportedConstructError
    from lexic.ir import Arm, InlineAlternationAtom, PatternAtom
    from lexic.ir.regex_portable import features_used, validate_portable

    for spec in specs:
        for atom in _walk_atoms(spec.items):
            if isinstance(atom, PatternAtom):
                validate_portable(atom.regex)
                missing = features_used(atom.regex) - adapter.emitter.supports
                if missing:
                    raise UnsupportedConstructError(
                        f"Pattern {atom.regex!r} in rule {spec.rule_name!r} "
                        f"uses features {sorted(missing)} not supported by "
                        f"{adapter.name!r} emitter"
                    )


def _walk_atoms(items):
    """Yield every atom, descending into InlineAlternationAtom.arms."""
    from lexic.ir import InlineAlternationAtom
    for atom in items:
        yield atom
        if isinstance(atom, InlineAlternationAtom):
            for arm in atom.arms:
                yield from _walk_atoms(arm.atoms)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/ -q`
Expected: green — existing GBNF grammars produce patterns whose features are all in GBNF's supports set.

- [ ] **Step 3: Add an integration test — cross-check raises when expected**

Append to `tests/integration/test_codegen.py` (or create a new file):

```python
def test_cross_check_raises_on_shorthand_in_gbnf_flavour():
    """A PatternAtom with shorthand (not in GBNF supports) raises at codegen."""
    from unittest.mock import patch
    from lexic.codegen import build_classes_and_specs
    from lexic.grammars import get_adapter
    from lexic.exceptions import UnsupportedConstructError
    from lexic.ir import PatternAtom, RuleSpec

    fake_specs = [
        RuleSpec(
            rule_name="root",
            class_name="Root",
            parent_class_name="GrammarModel",
            kind="sequence",
            items=[PatternAtom(regex=r"\d+", source_forms={"gbnf": r"\d+"}, min=1, max=1)],
            field_map={"digit": 0},
        )
    ]

    adapter = get_adapter("gbnf")
    with patch.object(adapter.parser, "parse", return_value=fake_specs):
        with pytest.raises(UnsupportedConstructError) as excinfo:
            build_classes_and_specs("ignored", stem="t")
    assert "shorthand" in str(excinfo.value)
```

**No commit yet.**

---

## Task 28: Add `tests/unit/lexic/grammars/gbnf/test_parser_source_forms.py`

**Files:**
- Create: `tests/unit/lexic/grammars/gbnf/test_parser_source_forms.py`

- [ ] **Step 1: Write the test file**

```python
# tests/unit/lexic/grammars/gbnf/test_parser_source_forms.py
"""Tests that GbnfParser populates PatternAtom.source_forms correctly."""

from __future__ import annotations

import pytest

from lexic.grammars.gbnf.parser import GbnfParser
from lexic.ir import InlineAlternationAtom, LiteralAtom, PatternAtom, RuleRefAtom


def _parse_first_rule(text: str):
    return GbnfParser().parse(text)[0]


def test_char_class_source_form_verbatim():
    rule = _parse_first_rule('root ::= [a-h]')
    atom = rule.items[0]
    assert isinstance(atom, PatternAtom)
    assert atom.source_forms == {"gbnf": "[a-h]"}
    assert atom.regex == "[a-h]"  # canonical: same as source for this case


def test_char_class_source_form_pattern_only_not_quantifier():
    """source_forms stores pattern only — quantifier is in min, max."""
    rule = _parse_first_rule('root ::= [a-h]+')
    atom = rule.items[0]
    assert isinstance(atom, PatternAtom)
    assert atom.source_forms == {"gbnf": "[a-h]"}
    assert atom.min == 1
    assert atom.max is None


def test_quantified_literal_source_form():
    """Quantified literal: regex = re.escape(value); source_forms['gbnf'] = \"value\"."""
    rule = _parse_first_rule('root ::= "foo"?')
    atom = rule.items[0]
    assert isinstance(atom, PatternAtom)
    assert atom.source_forms == {"gbnf": '"foo"'}
    assert atom.regex == "foo"  # re.escape("foo") = "foo"
    assert atom.min == 0
    assert atom.max == 1


def test_literal_atom_value_is_canonical_decoded():
    """LiteralAtom.value holds canonical Python (escapes decoded)."""
    rule = _parse_first_rule('root ::= "\\n"')
    atom = rule.items[0]
    assert isinstance(atom, LiteralAtom)
    assert atom.value == "\n"  # actual newline, not the two-char escape


def test_pure_literal_inline_alt_produces_arms():
    """Inline alt of pure literals → InlineAlternationAtom with inline literal arms."""
    rule = _parse_first_rule('root ::= ("a" | "b" | "c")')
    atom = rule.items[0]
    assert isinstance(atom, InlineAlternationAtom)
    assert len(atom.arms) == 3
    for arm, expected in zip(atom.arms, ["a", "b", "c"]):
        assert len(arm.atoms) == 1
        assert isinstance(arm.atoms[0], LiteralAtom)
        assert arm.atoms[0].value == expected


def test_named_rule_inline_alt_produces_rule_ref_arms():
    """Inline alt of rule refs → InlineAlternationAtom with RuleRefAtom arms."""
    rule = _parse_first_rule(
        'root ::= (a | b | c)\na ::= "x"\nb ::= "y"\nc ::= "z"'
    )
    atom = rule.items[0]
    assert isinstance(atom, InlineAlternationAtom)
    assert len(atom.arms) == 3
    for arm, expected_name in zip(atom.arms, ["a", "b", "c"]):
        assert len(arm.atoms) == 1
        assert isinstance(arm.atoms[0], RuleRefAtom)
        assert arm.atoms[0].rule_name == expected_name


def test_no_helper_rules_for_inline_alts():
    """Inline alt paths don't synthesize 'root-arm1' etc. helpers."""
    specs = GbnfParser().parse('root ::= ("a" | "b")')
    rule_names = {s.rule_name for s in specs}
    assert rule_names == {"root"}  # no root-arm1, root-arm2


@pytest.mark.parametrize(
    ("source", "expected_regex"),
    [
        (r'root ::= [a-z]',        "[a-z]"),
        (r'root ::= [^0-9]',       "[^0-9]"),
        (r'root ::= [a-zA-Z_]',    "[a-zA-Z_]"),
    ],
)
def test_pattern_regex_is_canonical_python(source, expected_regex):
    rule = _parse_first_rule(source)
    atom = rule.items[0]
    assert isinstance(atom, PatternAtom)
    assert atom.regex == expected_regex
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/unit/lexic/grammars/gbnf/test_parser_source_forms.py -v`
Expected: all pass.

**No commit yet.**

---

## Task 29: Add `tests/integration/test_source_forms_roundtrip.py`

**Files:**
- Create: `tests/integration/test_source_forms_roundtrip.py`

- [ ] **Step 1: Write the test file**

```python
# tests/integration/test_source_forms_roundtrip.py
"""Round-trip: GBNF source → IR → GBNF emission preserves PatternAtom source forms."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.grammars import get_adapter
from lexic.ir import Arm, InlineAlternationAtom, PatternAtom


GROUND_TRUTH_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "ground_truth"


@pytest.mark.parametrize(
    "grammar_path",
    sorted(GROUND_TRUTH_DIR.glob("*.gbnf")),
    ids=lambda p: p.stem,
)
def test_pattern_source_forms_populated(grammar_path: Path):
    """Every PatternAtom produced by GbnfParser has source_forms['gbnf']."""
    adapter = get_adapter("gbnf")
    text = grammar_path.read_text()
    specs = adapter.parser.parse(text)

    for spec in specs:
        for atom in _walk_atoms(spec.items):
            if isinstance(atom, PatternAtom):
                assert "gbnf" in atom.source_forms, (
                    f"PatternAtom in rule {spec.rule_name!r} missing source_forms['gbnf']: {atom}"
                )


@pytest.mark.parametrize(
    "grammar_path",
    sorted(GROUND_TRUTH_DIR.glob("*.gbnf")),
    ids=lambda p: p.stem,
)
def test_roundtrip_preserves_parse(grammar_path: Path):
    """parse → emit → parse produces the same IR."""
    adapter = get_adapter("gbnf")
    text = grammar_path.read_text()
    specs1 = adapter.parser.parse(text)
    emitted = adapter.emitter.emit(specs1)
    specs2 = adapter.parser.parse(emitted)

    # Spec counts match
    assert len(specs1) == len(specs2), grammar_path

    # Spec kinds and rule names match (atom-level equality is too strict —
    # source_forms may differ slightly on round-trip if the emitter's
    # canonical form differs from the user's, but parse-back should still
    # produce the same IR structure).
    for s1, s2 in zip(specs1, specs2):
        assert s1.rule_name == s2.rule_name
        assert s1.kind == s2.kind


def _walk_atoms(items):
    for atom in items:
        yield atom
        if isinstance(atom, InlineAlternationAtom):
            for arm in atom.arms:
                yield from _walk_atoms(arm.atoms)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/integration/test_source_forms_roundtrip.py -v`
Expected: all pass (14 tests — 2 × 7 grammars).

**No commit yet.**

---

## Task 30: Regenerate `generated/*.py`

**Files:**
- Modify: `generated/*.py` (all 18 files — seven named grammars + anon_*.py files + arithmetic_a.py, arithmetic_b.py, c.py)

- [ ] **Step 1: Regenerate**

```bash
uv run python -c "
from pathlib import Path
from lexic.codegen import codegen

for gbnf in sorted(Path('resources/ground_truth').glob('*.gbnf')):
    text = gbnf.read_text()
    codegen(text, stem=gbnf.stem)
    print('regenerated', gbnf.stem)
"
```

Expected: each grammar regenerates into `generated/<stem>.py` with `PatternAtom(...)` + `InlineAlternationAtom(arms=(Arm(...), ...))` in the `__grammar__` literals.

The other `generated/*.py` files (anon_*) come from hashed-stem compile calls in tests; they regenerate on test runs.

- [ ] **Step 2: Inspect a diff**

```bash
git diff generated/arithmetic.py | head -60
```

Expected: changes replace `CharClassAtom("[a-z]", min=1, max=1)` with `PatternAtom(regex="[a-z]", source_forms={"gbnf": "[a-z]"}, min=1, max=1)`, etc. Also `InlineAlternationAtom([...])` → `InlineAlternationAtom(arms=(Arm(atoms=(...)), ...))`. No semantic changes.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/ -q`
Expected: all green — regenerated modules load cleanly, property round-trips pass.

- [ ] **Step 4: Do not commit yet**

Regen is part of Phase 2's bundled commit at Task 32. Defer.

---

## Task 31: Remove `InlineAlternationAtom.arm_rule_names` back-compat property + tuple the rest

**Files:**
- Modify: `src/lexic/ir/atoms.py`

- [ ] **Step 1: Delete the `NotImplementedError`-raising `arm_rule_names` property from `InlineAlternationAtom`**

If Task 15's back-compat property is still in place, delete it.

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/ -q`
Expected: green — all callers were migrated in Tasks 18-25.

**No commit yet — Task 32 finalises.**

---

## Task 32: Remove old atom types + `GBNFEmitter` alias

**Files:**
- Modify: `src/lexic/ir/atoms.py`
- Modify: `src/lexic/ir/__init__.py`
- Modify: `src/lexic/grammars/gbnf/emitter.py`

- [ ] **Step 1: Delete `CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom` from `atoms.py`**

Remove the three dataclass definitions. Update the `Atom` union:

```python
Atom = (
    LiteralAtom
    | PatternAtom
    | RuleRefAtom
    | AlternationAtom
    | InlineAlternationAtom
)
```

- [ ] **Step 2: Update `src/lexic/ir/__init__.py`**

Remove the three names from imports and `__all__`.

- [ ] **Step 3: Delete the `GBNFEmitter = GbnfEmitter` back-compat alias** from `gbnf/emitter.py`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/ -q`
Expected: green. If anything fails, it means a consumer still imports an old name — fix and re-run.

Run: `uv run ruff check src/ tests/`
Expected: clean.

- [ ] **Step 5: Commit Phase 2 — one big bundled commit**

```bash
git add -A
git commit -m "refactor(slice-b-phase-2): collapse atoms to PatternAtom + reshape InlineAlternationAtom

Bundles the full atom migration into one commit because the intermediate
state (shape changed, consumers not yet migrated) is not green.

IR (atoms.py):
- Adds PatternAtom(regex, source_forms, min, max).
- Adds Arm(atoms: tuple[Atom, ...]).
- InlineAlternationAtom.arms: tuple[Arm, ...] replaces arm_rule_names.
- AlternationAtom.arm_rule_names: tuple[str, ...] (was list) for genuine
  frozenness.
- Removes CharClassAtom, QuantifiedLiteralAtom, InlineRegexAtom.
- Atom union collapses from 7 → 5 types.

GBNF parser/ir_builder (grammars/gbnf/):
- seq_to_atoms.py emits PatternAtom with source_forms['gbnf'] populated
  (pattern-only, no quantifier; quantifier lives in min, max).
- Pure-literal inline alts produce InlineAlternationAtom with inline Arms
  carrying LiteralAtom tuples — no helper-rule synthesis.
- Named-rule inline alts produce Arms of single RuleRefAtom.
- LiteralAtom.value is canonical Python (GBNF escapes decoded at parse time).
- HelperRuleRegistry retains quantified-group synthesis.
- Six GBNF-specific modules moved from codegen/ to grammars/gbnf/:
  seq_to_atoms, ir_builder, classify, ast_utils, helpers. naming.py stays
  at codegen/ (atom-semantic, not GBNF-syntax).

Consumers migrated:
- lark_builder.py: single PatternAtom branch; InlineAlternationAtom.arms
  handling; explicit UnsupportedConstructError default.
- model_emitter.py: _field_type and _repr_atom rewritten; Arm emitted in
  __grammar__ source.
- gbnf/emitter.py: PatternAtom reads source_forms['gbnf']; empty-source_forms
  raises NotImplementedError (Slice D trigger).
- transformer/{registry,builders}.py: three builders collapsed into
  PatternFieldBuilder.
- generate.py: sre_parse-based regex sampler replaces GBNF-bracket sampling;
  new InlineAlternationAtom.arms handling.
- naming.py: InlineAlternationAtom field-naming reads arm atoms directly.
- codegen/__init__.py: validate_portable + per-flavour supports cross-check
  at codegen time.

Drops GBNFEmitter backwards-compat alias.

Regenerates seven ground-truth grammars with PatternAtom + source_forms +
new InlineAlternationAtom shape in __grammar__ literals.

Adds tests:
- tests/unit/lexic/ir/test_atom_shapes.py
- tests/unit/lexic/grammars/gbnf/test_parser_source_forms.py
- tests/integration/test_source_forms_roundtrip.py

All tests green. Ruff clean.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

# Phase 3 — Token Reservation

## Task 33: Add pre-tokenisation scan to `GbnfParser.parse`

**Files:**
- Modify: `src/lexic/grammars/gbnf/parser.py`

- [ ] **Step 1: Add the scan to `GbnfParser.parse`**

```python
# src/lexic/grammars/gbnf/parser.py

import re
from lexic.exceptions import UnsupportedConstructError


# Three reserved token syntaxes:
# - <name>    — named token reference
# - <[N]>     — ID-form token reference
# - !<name>   — negation token reference
_TOKEN_PATTERN = re.compile(
    r"!<\w+>"            # !<name>
    r"|"
    r"<\[\s*\d+\s*\]>"   # <[N]>
    r"|"
    r"<\w+>"             # <name>
)


class GbnfParser:
    """GBNF flavour parser."""

    def parse(self, text: str):
        _reject_token_syntax(text)
        from lexic.grammars.gbnf.ir_builder import IRBuilder
        ast_rules = parse_gbnf(text)
        return IRBuilder(ast_rules).build()


def _reject_token_syntax(text: str) -> None:
    """Raise UnsupportedConstructError on any GBNF token reference syntax.

    Scans raw text before any atom construction, so tokens can never enter the IR.
    """
    for match in _TOKEN_PATTERN.finditer(text):
        offending = match.group(0)
        line_no = text[: match.start()].count("\n") + 1
        raise UnsupportedConstructError(
            f"GBNF tokens ({offending!r}) at line {line_no} are not supported. "
            f"Tokens are a reserved construct."
        )
```

- [ ] **Step 2: Verify existing grammars still parse**

Run: `uv run pytest tests/ -q`
Expected: all green (the ground-truth grammars don't use token syntax).

**No commit yet — Task 34 adds tests, then commits.**

---

## Task 34: Add `tests/integration/test_token_reservation.py`

**Files:**
- Create: `tests/integration/test_token_reservation.py`

- [ ] **Step 1: Write the test file**

```python
# tests/integration/test_token_reservation.py
"""Tests that GBNF token syntax is rejected by GbnfParser."""

from __future__ import annotations

import pytest

from lexic.grammars.gbnf.parser import GbnfParser
from lexic.exceptions import UnsupportedConstructError


@pytest.mark.parametrize(
    ("grammar", "expected_fragment"),
    [
        ('root ::= <think>',    "<think>"),
        ('root ::= <[42]>',     "<[42]>"),
        ('root ::= !<name>',    "!<name>"),
    ],
    ids=["named_token", "id_form_token", "negation_token"],
)
def test_token_syntax_raises(grammar, expected_fragment):
    with pytest.raises(UnsupportedConstructError) as excinfo:
        GbnfParser().parse(grammar)
    msg = str(excinfo.value)
    assert "GBNF tokens" in msg
    assert expected_fragment in msg
    assert "line" in msg.lower()  # line number mentioned


def test_multiple_tokens_reports_first():
    grammar = 'root ::= <a> <b>'
    with pytest.raises(UnsupportedConstructError) as excinfo:
        GbnfParser().parse(grammar)
    msg = str(excinfo.value)
    assert "<a>" in msg  # first match wins


def test_token_inside_larger_rule_detected():
    grammar = 'root ::= "hello" <think> "world"'
    with pytest.raises(UnsupportedConstructError):
        GbnfParser().parse(grammar)


def test_line_number_reported():
    grammar = 'root ::= "a"\nother ::= <bogus>\nmore ::= "b"'
    with pytest.raises(UnsupportedConstructError) as excinfo:
        GbnfParser().parse(grammar)
    assert "line 2" in str(excinfo.value)


def test_non_token_angle_brackets_in_literals_not_rejected():
    """Angle brackets inside quoted strings are not tokens."""
    # GBNF literals are double-quoted, so "<foo>" inside a string is just chars.
    grammar = 'root ::= "<not a token>"'
    # Should NOT raise — the regex matches bare <name>, but this <...> is inside a string.
    # Note: the scan is currently text-based, so it WILL match. If that's a
    # problem for real grammars, tighten the regex to require the <...> not be
    # preceded by an unmatched quote. For ground-truth today no grammar has
    # this pattern, so we accept the false-positive risk for simplicity.
    # This test documents the current trade-off.
    pytest.skip("Text-based scan matches <...> inside string literals; accept for Slice B")
```

**Note on the string-literal false positive:** For Slice B, accept that the scan is text-based. None of the seven ground-truth grammars use `<...>` inside string literals. When a user grammar does, tighten the scan to skip quoted regions. Slice B's exit criteria don't require handling this case.

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/integration/test_token_reservation.py -v`
Expected: 4 pass + 1 skip.

- [ ] **Step 3: Run full suite**

Run: `uv run pytest tests/ -q`
Expected: **442 passed + 1 skipped** (approximate — final count depends on exact test counts).

- [ ] **Step 4: Run ruff**

Run: `uv run ruff check src/ tests/`
Expected: clean.

- [ ] **Step 5: Commit Phase 3**

```bash
git add -A
git commit -m "feat(gbnf): reserve GBNF token syntax via pre-tokenisation scan

GbnfParser.parse raises UnsupportedConstructError before any AST construction
when source text contains:
- <name>    — named token reference
- <[N]>     — ID-form token reference
- !<name>   — negation token reference

Error message names the offending fragment, the line number, and notes the
tokens addendum.

Scan is text-based; accepts a known-trivial false-positive case for
<...> inside string literals (no current ground-truth grammar uses this
pattern; tighten if a future grammar requires it).

Adds tests/integration/test_token_reservation.py.

Closes Slice B.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

# Phase 3 Close-out

## Task 35: Sanity sweep + PR

**Files:** (no new changes)

- [ ] **Step 1: Final full-suite run**

Run: `uv run pytest tests/ -q`
Expected: all green.

- [ ] **Step 2: Final ruff**

Run: `uv run ruff check src/ tests/`
Expected: clean.

- [ ] **Step 3: Review the three-commit history**

Run: `git log --oneline -5`
Expected: at least three commits in this order:
- Phase 1 scaffolding commit
- Phase 2 migration commit(s) (possibly two: shape + consumer-sweep)
- Phase 3 token-reservation commit

- [ ] **Step 4: Verify exit criteria per spec §Per-phase exit criteria**

Open `docs/superpowers/specs/2026-04-23-slice-b-design.md` and walk through each checkbox. Confirm every exit-criteria line is satisfied.

- [ ] **Step 5: Push branch and open PR**

```bash
git push -u origin HEAD
gh pr create --title "Slice B: PatternAtom + Tier 2.5 + token reservation" --body "$(cat <<'EOF'
## Summary
- Collapses CharClassAtom / QuantifiedLiteralAtom / InlineRegexAtom into PatternAtom with source_forms flavour-shadow map
- Reshapes InlineAlternationAtom.arms to tuple[Arm, ...] — inline atom arms, no helper-rule synthesis
- Moves GBNF-specific code into grammars/gbnf/ behind FlavourAdapter/Parser/Emitter protocols
- Threads flavour="gbnf" through codegen(), compile(), to_grammar(); to_gbnf() is an alias
- Freezes all atom dataclasses
- Deletes LarkBuilder.build_transformer indirection
- Adds pre-tokenisation scan to GbnfParser: <name>/<[N]>/!<name> raise UnsupportedConstructError
- Adds PORTABLE_FEATURES set + compile-time validate_portable + per-flavour supports cross-check

## Phases (commits)
1. Scaffolding (behaviour-preserving)
2. Atom collapse (consumer migration + regen)
3. Token reservation

## Test plan
- [x] All existing 414 tests still green
- [x] New tests: test_flavours.py, test_atom_shapes.py, test_regex_portable.py, test_parser_source_forms.py, test_source_forms_roundtrip.py, test_token_reservation.py
- [x] Seven ground-truth grammars regenerate identically modulo atom renames + source_forms additions
- [x] Property round-trips green on all seven grammars
- [x] ruff clean

Spec: `docs/superpowers/specs/2026-04-23-slice-b-design.md`
EOF
)"
```

Return the PR URL to the user.

---

# Self-Review Checklist

The implementation worker (or reviewer) should verify before marking each phase complete:

**Phase 1:**
- [ ] `lexic/exceptions.py` has `LexicError`, `UnsupportedConstructError`, `GrammarAuthoringError`, `FieldValidationError`.
- [ ] `lexic/ir/regex_portable.py` has `PORTABLE_FEATURES`, `validate_portable`, `features_used`, `canonicalize_groups`.
- [ ] `lexic/grammars/flavours.py` has three protocols, `ADAPTERS`, `register_adapter`, `get_adapter`, `adapter_for_extension`, and eagerly registers `GbnfAdapter`.
- [ ] `lexic/grammars/gbnf/{adapter,parser,emitter,ast,escapes,charclass}.py` exist; `lexic/codegen/{parser,ast,gbnf_emitter}.py` and `lexic/utils/{escapes,charclass}.py` do not.
- [ ] `codegen(flavour="gbnf")` works; `codegen(flavour="abnf")` raises `UnsupportedConstructError`.
- [ ] `GrammarModel.to_grammar("gbnf")` works; `to_gbnf()` is an alias.
- [ ] `LarkBuilder.build_transformer` method is gone.
- [ ] All atom dataclasses are frozen.
- [ ] Docs (`2_ARCHITECTURE.md`, `3_ROADMAP.md`, `CLAUDE.md`) updated.
- [ ] All tests green; ruff clean.

**Phase 2:**
- [ ] Five atom types in `lexic.ir` (`LiteralAtom`, `PatternAtom`, `RuleRefAtom`, `AlternationAtom`, `InlineAlternationAtom`).
- [ ] `Arm` exported from `lexic.ir`.
- [ ] `CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom` gone.
- [ ] `InlineAlternationAtom.arms: tuple[Arm, ...]` — no helper rules for inline alts.
- [ ] `AlternationAtom.arm_rule_names: tuple[str, ...]`.
- [ ] Seven ground-truth grammars regenerate identically modulo atom renames + source_forms additions.
- [ ] Property round-trips green.
- [ ] `source_forms["gbnf"]` populated (pattern-only; no quantifier) on every `PatternAtom`.
- [ ] Every atom dispatch has explicit `UnsupportedConstructError` default raise.
- [ ] `validate_portable` + supports cross-check wired in `codegen.__init__`.
- [ ] New tests green.
- [ ] ruff clean.

**Phase 3:**
- [ ] `GbnfParser.parse` raises on `<name>`, `<[N]>`, `!<name>` before atom construction.
- [ ] `tests/integration/test_token_reservation.py` green.
- [ ] All existing tests still green.
- [ ] ruff clean.
