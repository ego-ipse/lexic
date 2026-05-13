# Step 18 cutover — revised plan

**Supersedes** Task 18 of `2026-05-08-parallel-track-ir-cutover.md`.

The previous Task 18 was a single sed-and-delete commit followed by surgical
edits inside legacy modules. An attempted execution (`failed_chat.txt`)
revealed the ordering was wrong: deleting legacy code before the runtime
modules that import it are rewritten produces cascading import errors that
prevent pytest from collecting, leaving every subsequent edit unverifiable.

This plan reverses the order. State is mapped first; decisions are made;
phasing follows the dependency graph that already exists in the source tree;
each phase ends green.

---

## State assessment

### Two pipelines coexist in the tree

The repo has both pipelines live side-by-side; the cutover's job is to
collapse to the new one and rename `new_*` directories to their target names.

| Concern               | Legacy                                          | New                                                     |
|-----------------------|-------------------------------------------------|---------------------------------------------------------|
| IR shape              | `Atom` dataclasses (`ir/atoms.py`)              | `IrItem(atom: IrAtom, quantifier: Quantifier)`          |
| Spec                  | `RuleSpec.items: list[Atom]`                    | `NewRuleSpec.items: list[IrItem \| IrAlternation]`      |
| Spec module           | `ir/spec.py::RuleSpec`                          | `ir/spec.py::NewRuleSpec` (same file, separate class)   |
| Grammar→IR            | `codegen/ir_builder.py::IRBuilder`              | `parsing/meta_parser.py::MetaGrammarParser` + `ir/derive.py::derive_specs` |
| GBNF flavour          | `grammars/gbnf/` (adapter, parser, ast, emitter, flavour) | `grammars/new_gbnf/` (flavour, emitter, escapes, meta_grammar) |
| ABNF flavour          | (none — new pipeline only)                      | `grammars/abnf/`                                        |
| Flavour registry      | `grammars/flavours.py::ADAPTERS`, `register_adapter`, `get_adapter`, `adapter_for_extension` | (none — to be added in Phase 1B) |
| Model emitter         | `codegen/model_emitter.py::ModelEmitter`        | `new_codegen/model_emitter.py::ModuleEmitter`           |
| Codegen entry         | `codegen/__init__.py::codegen(text, *, stem, flavour)`; `build_classes_and_specs(text, *, stem, flavour)`; `codegen_from_path(path)` | `new_codegen/__init__.py::codegen(specs, stem)` |
| Lark builder          | `codegen/lark_builder.py::LarkBuilder(specs).build_grammar()/build_transformer(classes)` | `parsing/lark_builder.py::LarkBuilder(specs, start_rule=...)` + `build_lark(specs, classes, start_rule)` |
| Transformer builder   | `codegen/transformer/build_transformer.py`     | `parsing/transformer/build_transformer.py`              |
| Compile entry         | `compile.py::compile_text` / `compile_from_path` driving `_compile_core` → old pipeline; top-level package re-exports `codegen` and `codegen_from_path`. | `compile.py::compile_grammar(text, flavour: type[Flavour]) -> (start, list[NewRuleSpec])`; parse + derive only (no classes/parser/transformer). Callers pass the **Flavour class**, not its name. Pattern: `tests/integration/test_compile_grammar_gbnf.py`. Cutover replaces the top-level re-exports with `compile_text` / `compile_from_path` (Decision 8 — public-API change). |
| Runtime               | `base.py`, `generate.py` dispatch on Atom types and call `decode_gbnf_escapes` on every literal | (to be rewritten — IrItem/IrAtom dispatch; literals are canonical from `MetaGrammarParser`, no decode needed) |

### Three emitter-shape mismatches that bite

1. `grammars/new_gbnf/flavour.py::GbnfFlavour.emitter = GbnfEmitter` — **class reference**.
2. `grammars/abnf/flavour.py::AbnfFlavour.emitter = AbnfEmitter(escapes=ABNF_ESCAPES)` — **instance**.
3. `grammars/gbnf/flavour.py::GbnfFlavour.emitter: GbnfEmitter = GbnfEmitter([])` — **instance**, with a transitional `# type: ignore[assignment] REMOVE IN PHASE D` directive on the line.

Old-pipeline call sites do `adapter.emitter.emit(specs)`. New-pipeline call
sites in tests (`AbnfFlavour.emitter.emit_ast(ast)` in
`tests/integration/test_cross_flavour.py:83`) also assume instance.

**Decision: `Flavour.emitter` is a class object.** Call sites instantiate via
`flavour_cls.emitter(escapes=flavour_cls.escapes)`. This matches the new
GbnfFlavour shape and `Flavour.emitter` typing (`ClassVar[type[FlavourEmitter]]`
post-cutover). `AbnfFlavour` is renormalised; the old `gbnf/flavour.py` is
deleted in the same commit that renames `new_gbnf/` → `gbnf/`.

### Two latent `parsing/lark_builder.py::_atom_to_lark` bugs

End-to-end round-trip through real grammars exposes both.

1. **Raw newlines emitted into Lark source.** Current code does
   `escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')`. A literal
   containing a real `\n` (e.g. `arithmetic.gbnf`'s line terminator) is placed
   verbatim inside `"..."`; Lark's grammar parser rejects it.
2. **`/` inside char-class patterns terminates the regex early.** Current
   code does `f"/{_bracket(atom.pattern, atom.negated)}/{q}"`. Pattern
   `[-+*/]` in `arithmetic.gbnf` becomes `/[-+*/]/` — Lark reads `/[-+*` as
   the regex, then `/` as terminator.

Both fixes are 1–2 line edits and ride in the cutover commit because the
file is otherwise stable; round-trip doesn't exercise it until `_compile_core`
is rerouted.

### `non_semantic_fields` provenance

- New pipeline populates `NewRuleSpec.non_semantic_fields` inside
  `derive._apply_non_semantic` from the `@non-semantic` directive set.
- Old pipeline leaves `RuleSpec.non_semantic_fields = frozenset()` and uses a
  hardcoded `RuleRefAtom('ws')` check in `base.py::semantic_dump`.

After cutover `semantic_dump` is one line:
`return self.model_dump(exclude=self.__grammar__.non_semantic_fields)`. No
old-pipeline patch needed — the old pipeline is deleted.

### Source files touched in Phase 2

Survive the cutover; legacy importers must all be rewritten:

| File                                              | Legacy names touched |
|--------------------------------------------------|-------------------------|
| `src/lexic/__init__.py`                           | `codegen_from_path` (gone) |
| `src/lexic/base.py`                               | `LiteralAtom`, `RuleRefAtom`, `get_adapter`, `decode_gbnf_escapes` |
| `src/lexic/generate.py`                           | All 6 Atom types + `decode_gbnf_escapes` (8 call sites: lines 90, 113, 117, 124, 154, 159, 183, 187) |
| `src/lexic/compile.py`                            | `build_classes_and_specs`, `LarkBuilder` (old), `adapter_for_extension` |
| `src/lexic/grammars/__init__.py`                  | `flavours.ADAPTERS`, `register_adapter`, `get_adapter`, `adapter_for_extension`, `FlavourAdapter`, `gbnf.adapter.GbnfAdapter` |
| `src/lexic/ir/__init__.py`                        | All 8 Atom re-exports, `builder.IRBuilder`, `classify.classify_rule`, `RuleClassifier`, `SequenceConverter` |
| `src/lexic/ir/spec.py`                            | `from lexic.ir.atoms import Atom` |
| `src/lexic/ir/naming.py`                          | All 8 Atom types (`assign_field_names` + helpers) |
| `src/lexic/ir/emit.py`                            | All 8 Atom types (`DEFAULT_HANDLERS`, `render_atom`, legacy `_emit_body`) |
| `src/lexic/grammars/abnf/flavour.py`              | `AbnfFlavour.emitter = AbnfEmitter(escapes=...)` (instance form — fixed in Phase 1A) |

Deleted entirely in Phase 2:

```
src/lexic/codegen/                                  (entire dir, 11 files)
src/lexic/grammars/gbnf/                            (entire dir, 7 files)
src/lexic/grammars/flavours.py
src/lexic/ir/atoms.py
src/lexic/ir/builder.py
src/lexic/ir/classify.py
src/lexic/ir/convert.py
src/lexic/ir/protocols.py
```

Renamed in Phase 2:

```
src/lexic/new_codegen/                                       →  src/lexic/codegen/
src/lexic/grammars/new_gbnf/                                 →  src/lexic/grammars/gbnf/
tests/unit/lexic/new_codegen/                                →  tests/unit/lexic/codegen/
tests/unit/lexic/grammars/new_gbnf/                          →  tests/unit/lexic/grammars/gbnf/
tests/unit/lexic/codegen/test_init_new_codegen.py            →  tests/unit/lexic/codegen/test_init_codegen.py
tests/unit/lexic/grammars/gbnf/test_init_new_gbnf.py         →  tests/unit/lexic/grammars/gbnf/test_init_gbnf.py
```

(The two file-level renames are necessary because `git mv` of a directory
preserves inner filenames; project memory rule `test_init_<package>.py`
requires the `new_` prefix be dropped.)

### Test inventory

**Delete** (subject is deleted):
```
tests/unit/lexic/ir/test_atoms.py
tests/unit/lexic/ir/test_builder.py
tests/unit/lexic/ir/test_classify.py
tests/unit/lexic/ir/test_convert.py
tests/unit/lexic/ir/test_protocols.py
tests/unit/lexic/codegen/                            (entire dir, 9 files — LEGACY)
tests/unit/lexic/grammars/gbnf/                      (entire dir, 6 files — LEGACY)
tests/unit/lexic/grammars/test_flavours.py
tests/integration/test_codegen.py                    (drives old codegen entry)
tests/integration/test_gbnf_roundtrip.py             (drives IRBuilder + GBNFEmitter + parse_gbnf)
```

**Rewrite** (subject survives, fixtures use legacy Atoms):
```
tests/unit/lexic/test_base.py                        (LiteralAtom/RuleRefAtom/CharClassAtom fixtures)
tests/unit/lexic/test_generate.py                    (uses IRBuilder + parse_gbnf)
tests/unit/lexic/ir/test_emit.py                     (DEFAULT_HANDLERS tests + atom dispatch)
tests/unit/lexic/ir/test_naming.py                   (assign_field_names + atom-shape helpers)
tests/unit/lexic/ir/test_spec.py                     (RuleSpec with Atom items)
tests/unit/lexic/ir/test_topo.py                     (Atom fixtures)
tests/unit/lexic/ir/test_helpers.py                  (verify; rewrite if Atom-shaped)
tests/unit/lexic/grammars/abnf/test_emitter.py       (render_atom on Atoms)
tests/integration/test_cross_flavour.py              (`AbnfFlavour.emitter.emit_ast(...)` — handled in Phase 1A)
tests/integration/test_full_round_trip.py            (drops old compile_text assertions)
tests/property/conftest.py                           (builds specs via IRBuilder + parse_gbnf)
```

**Already correct** (test the new pipeline; rename with their subject in 2.6):
```
tests/unit/lexic/grammars/new_gbnf/                  → tests/unit/lexic/grammars/gbnf/
tests/unit/lexic/new_codegen/                        → tests/unit/lexic/codegen/
tests/unit/lexic/parsing/test_lark_builder.py
tests/unit/lexic/parsing/test_meta_parser.py
tests/unit/lexic/parsing/transformer/test_build_transformer.py
tests/unit/lexic/ir/test_derive.py
tests/unit/lexic/ir/test_directives.py
tests/unit/lexic/ir/test_nodes.py
tests/unit/lexic/ir/test_walk.py
tests/unit/lexic/ir/test_charclass.py
tests/unit/lexic/ir/test_escapes.py
tests/unit/lexic/test_compile.py
tests/unit/lexic/test_parse.py
tests/integration/test_compile_grammar_gbnf.py
tests/integration/test_compile_grammar_abnf.py
tests/integration/test_parse.py
tests/property/test_roundtrip.py                     (driven by conftest fixture)
```

---

## Decisions

These resolve ambiguities found in state inspection. Applied uniformly.

1. **`Flavour.emitter` is a class object.** Call sites instantiate via
   `flavour_cls.emitter(escapes=flavour_cls.escapes)`. `GbnfEmitter` and
   `AbnfEmitter` constructors both accept `escapes=<EscapeCodec>`.

2. **`base.py::to_text` dispatches on position-in-field_map, not atom type.**
   For non-value_str rules:
   - `i in field_map` → emit `getattr(self, field_name)`
   - `isinstance(item.atom, IrLiteral)` → emit `item.atom.value`
   - else → skip (structural / non-emitting)
   Literals that *are* in field_map (quantified literals get a field via the
   Tier-2 cascade in `ir/derive.py::_field_map`) emit via the field; literals
   that aren't are baked into the rule text.

3. **`semantic_dump` consumes `non_semantic_fields`:**
   `self.model_dump(exclude=self.__grammar__.non_semantic_fields)`.

4. **`decode_gbnf_escapes` is gone from runtime.** `MetaGrammarParser`'s
   `ir_literal` builder (`parsing/meta_parser.py:67`) already does
   `f.escapes.decode(str(c[0])[1:-1])` and stores canonical text in
   `IrLiteral.value`. `decode_gbnf_escapes` survives only as an internal
   helper inside `grammars/gbnf/adapter.py`, which is deleted.

5. **`NewRuleSpec` collapses into `RuleSpec`.** Items typed
   `list[IrItem | IrAlternation]`. The sed in 2.7 rewrites references; the
   duplicate class definition the sed creates is reduced to one by deleting
   the older (legacy-shape) declaration in 2.8.

6. **`compile.py::compile_grammar` already exists and is correct.** No
   change to its body. `_compile_core` is replaced; public `compile_text` /
   `compile_from_path` keep their signatures.

7. **Module-top imports in `_compile_core`.** Per CLAUDE.md §Layering rules,
   `compile.py → lexic.codegen` is one of the two deliberate runtime→codegen
   seams; the established convention is module-top. The cutover preserves
   that pattern, repointed at the new modules.

8. **`lexic/__init__.py` re-exports `compile_from_path`, `compile_text`,
   `parse`, `generate`.** `codegen` and `codegen_from_path` removed — the
   new codegen surface `codegen(specs, stem)` is not a useful top-level
   convenience; callers wanting classes use `compile_from_path(path).classes`.

9. **`src/lexic/ir/protocols.py` is deleted.** Post-cutover grep confirms
   `RuleClassifier`, `SequenceConverter`, `FlavourAdapter`, the Protocol
   `FlavourParser`, and `AtomEmitHandler` have zero remaining importers,
   and the placeholder type aliases (`FieldHandler`, `LarkHandler`,
   `TransformHandler`, `ToTextHandler`) were never wired up. File and its
   test go.

10. **Two `parsing/lark_builder.py` bugs fixed in cutover** with targeted
    regression tests appended to `tests/unit/lexic/parsing/test_lark_builder.py`.

11. **Cutover commit also updates documentation.** `CLAUDE.md`,
    `prototyping/next/2_ARCHITECTURE.md`, `prototyping/next/3_ROADMAP.md`,
    `.wiki/index.md`, and `.wiki/log.md` describe the parallel-track state;
    they're synced to post-cutover reality in the same commit.

12. **No `# type: ignore`, `# noqa`, `# pylint: disable` anywhere in cutover
    output.** The existing directive on `grammars/gbnf/flavour.py:23` goes
    with its file in 2.5.

13. **Phase 1 splits into two small commits** (1A: AbnfFlavour
    normalisation; 1B: Flavour registry add) for clean rollback. **Phase 2
    is one atomic commit** — splitting risks intermediate states where
    `import lexic` fails.

---

## Phase 1A — normalise `AbnfFlavour.emitter` to a class

Goal: every emitter consumer can treat `Flavour.emitter` uniformly as a
class. Suite stays fully green.

### 1A.1 Edit `src/lexic/grammars/abnf/flavour.py`

Line 22 currently:
```python
emitter = AbnfEmitter(escapes=ABNF_ESCAPES)
```
Becomes:
```python
emitter = AbnfEmitter
```

### 1A.2 Update the only `AbnfFlavour.emitter.<method>` consumer

`tests/integration/test_cross_flavour.py:83`:
```python
abnf_text = AbnfFlavour.emitter.emit_ast(ast_g)
```
Becomes:
```python
abnf_text = AbnfFlavour.emitter(escapes=AbnfFlavour.escapes).emit_ast(ast_g)
```

Audit for other instance-call patterns:
```bash
grep -rn "AbnfFlavour\.emitter\.\|GbnfFlavour\.emitter\." src/ tests/
```
Any further hit: apply the same rewrite.

### 1A.3 Verify and commit

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/abnf/flavour.py tests/integration/test_cross_flavour.py
git commit -m "refactor(abnf): normalise AbnfFlavour.emitter to class attribute"
```

---

## Phase 1B — add the Flavour-based registry

Goal: `lexic.grammars` exposes both the legacy `ADAPTERS` registry and a
new `_FLAVOURS` registry. Phase 2's final-form swap becomes a pure delete.

### 1B.1 Edit `src/lexic/grammars/__init__.py`

Preserve the existing imports and registrations. Add the new registry
alongside:

```python
"""Grammar-flavour layer — public endpoint.

During the parallel-track cutover this module exposes both registries: the
legacy ADAPTERS dict driven by FlavourAdapter, and the new _FLAVOURS dict
driven by Flavour subclasses. The legacy half is removed in Phase 2.
"""

from __future__ import annotations

from pathlib import Path

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf.flavour import AbnfFlavour
from lexic.grammars.flavour import Flavour
from lexic.grammars.flavours import (
    ADAPTERS,
    FlavourAdapter,
    FlavourEmitter,
    FlavourParser,
    adapter_for_extension,
    get_adapter,
    register_adapter,
)
from lexic.grammars.gbnf.adapter import GbnfAdapter
from lexic.grammars.new_gbnf.flavour import GbnfFlavour as _NewGbnfFlavour

register_adapter(GbnfAdapter())

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


register_flavour(_NewGbnfFlavour)
register_flavour(AbnfFlavour)


__all__ = [
    "ADAPTERS",
    "Flavour",
    "FlavourAdapter",
    "FlavourEmitter",
    "FlavourParser",
    "adapter_for_extension",
    "flavour_for_extension",
    "get_adapter",
    "get_flavour",
    "register_adapter",
    "register_flavour",
]
```

### 1B.2 Verify and commit

```bash
uv run pytest tests/ -q
uv run ruff check src/ tests/
git add src/lexic/grammars/__init__.py
git commit -m "refactor(grammars): add Flavour registry alongside legacy ADAPTERS"
```

---

## Phase 2 — the cutover (single atomic commit)

Every step lands in one commit. Sub-step order matters: 2.5's legacy-test
removals must precede 2.6's renames; everything else follows the order
below. Final verification runs at the end.

### 2.1 Reroute `_compile_core` in `src/lexic/compile.py`

Module-top imports change (per CLAUDE.md "module-top is the seam"):

```python
# remove:
from lexic.codegen import build_classes_and_specs
from lexic.codegen.lark_builder import LarkBuilder
from lexic.grammars import adapter_for_extension

# add:
from lexic.codegen import codegen
from lexic.grammars import flavour_for_extension, get_flavour
from lexic.parsing.lark_builder import build_lark
```

Replace `_compile_core`:

```python
def _compile_core(text: str, *, stem: str, flavour: str = "gbnf") -> CompiledGrammar:
    flavour_cls = get_flavour(flavour)
    start_rule, specs_list = compile_grammar(text, flavour_cls)
    classes = codegen(specs_list, stem)
    _, parser, transformer = build_lark(specs_list, classes, start_rule)
    return CompiledGrammar(
        classes=classes,
        specs={s.rule_name: s for s in specs_list},
        parser=parser,
        transformer=transformer,
    )
```

In `compile_from_path`, replace
`flavour = adapter_for_extension(path).name` with
`flavour = flavour_for_extension(path).name`.

Update the module docstring: remove the "Runtime→codegen seam" paragraph
referencing `build_classes_and_specs` / `LarkBuilder`; replace with one line:
"Runtime entry: `compile_text` and `compile_from_path` build via
`compile_grammar` + `codegen` + `build_lark`."

### 2.2 `grammars/__init__.py` final form

Replace the Phase 1B shim with the legacy-free form:

```python
"""Grammar-flavour layer — public endpoint."""

from __future__ import annotations

from pathlib import Path

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf.flavour import AbnfFlavour
from lexic.grammars.flavour import Flavour
from lexic.grammars.gbnf.flavour import GbnfFlavour

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


__all__ = ["Flavour", "flavour_for_extension", "get_flavour", "register_flavour"]
```

`from lexic.grammars.gbnf.flavour import GbnfFlavour` resolves to the new
flavour module after the 2.6 rename.

### 2.3 Rewrite `src/lexic/base.py`

```python
"""GrammarModel: base class for all generated Pydantic models."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from lexic.ir.nodes import IrItem, IrLiteral
from lexic.ir.spec import RuleSpec


class GrammarModel(BaseModel):
    """Abstract base for all generated grammar model classes.

    Each subclass defines ``__grammar__: ClassVar[RuleSpec]``.

    ``to_text()`` walks ``__grammar__.items`` in order:
      - item index in field_map → emit getattr(self, field_name)
      - else IrItem with IrLiteral atom → emit the literal value
      - else → skip (structural / non-emitting)
    """

    __grammar__: ClassVar[RuleSpec]

    def to_text(self) -> str:
        spec = self.__grammar__
        if spec.kind == "alternation":
            raise NotImplementedError(
                f"to_text() is undefined on abstract alternation class "
                f"{type(self).__name__}; call it on a concrete arm instance."
            )
        if spec.kind == "value_str":
            return str(getattr(self, "value", ""))
        inv: dict[int, str] = {idx: name for name, idx in spec.field_map.items()}
        parts: list[str] = []
        for i, item in enumerate(spec.items):
            if not isinstance(item, IrItem):
                continue
            if i in inv:
                val = getattr(self, inv[i], None)
                if val is None:
                    continue
                if isinstance(val, list):
                    parts.append(
                        "".join(
                            v.to_text() if isinstance(v, GrammarModel) else str(v)
                            for v in val
                        )
                    )
                elif isinstance(val, GrammarModel):
                    parts.append(val.to_text())
                else:
                    parts.append(str(val))
            elif isinstance(item.atom, IrLiteral):
                parts.append(item.atom.value)
        return "".join(parts)

    def to_grammar(self, flavour: str = "gbnf") -> str:
        from lexic.grammars import get_flavour

        flavour_cls = get_flavour(flavour)
        emitter = flavour_cls.emitter(escapes=flavour_cls.escapes)
        return emitter.emit([self.__grammar__]).rstrip("\n")

    def semantic_dump(self) -> dict[str, Any]:
        return self.model_dump(exclude=self.__grammar__.non_semantic_fields)
```

The intra-function import of `get_flavour` inside `to_grammar` is the
deliberate runtime→codegen seam (CLAUDE.md §Layering rules, exception #1).

### 2.4 Rewrite `src/lexic/generate.py`

```python
"""Grammar-agnostic string generator from RuleSpec IR."""

from __future__ import annotations

import random as _random

from lexic.ir.charclass import parse_charclass_chars
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec

_ASCII_PRINTABLE = [chr(c) for c in range(32, 127)]


def _pick_count(q: Quantifier, rng: _random.Random) -> int:
    if q.min == 0:
        return 0
    if q.max == q.min:
        return q.min
    hi = min(q.max, q.min + 2) if q.max is not None else q.min + 2
    if rng.random() < 0.7:
        return q.min
    return rng.randint(q.min + 1, hi)


def _gen_charclass(atom: IrCharClass, q: Quantifier, rng: _random.Random) -> str:
    count = _pick_count(q, rng)
    if count == 0:
        return ""
    chars = parse_charclass_chars(atom.pattern)
    if atom.negated:
        excluded = set(chars)
        chars = [c for c in _ASCII_PRINTABLE if c not in excluded]
    if not chars:
        return ""
    return "".join(rng.choice(chars) for _ in range(count))


def _gen_group(
    atom: IrGroup,
    q: Quantifier,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    count = _pick_count(q, rng)
    if count == 0:
        return ""
    out: list[str] = []
    for _ in range(count):
        arm = rng.choice(atom.body.arms)
        out.append(_gen_sequence(arm, specs, rng, max_depth))
    return "".join(out)


def _gen_atom(
    item: IrItem,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    atom, q = item.atom, item.quantifier
    if isinstance(atom, IrLiteral):
        return atom.value * _pick_count(q, rng) if q != Quantifier(1, 1) else atom.value
    if isinstance(atom, IrCharClass):
        return _gen_charclass(atom, q, rng)
    if isinstance(atom, IrRuleRef):
        count = _pick_count(q, rng)
        return "".join(
            generate(atom.name, specs, rng=rng, max_depth=max_depth - 1)
            for _ in range(count)
        )
    if isinstance(atom, IrGroup):
        return _gen_group(atom, q, specs, rng, max_depth)
    return ""


def _gen_sequence(
    seq: IrSequence,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    return "".join(_gen_atom(it, specs, rng, max_depth) for it in seq.items)


def _gen_alternation(
    alt: IrAlternation,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    if not alt.arms:
        return ""
    arm = rng.choice(alt.arms)
    return _gen_sequence(arm, specs, rng, max_depth)


def _gen_alternation_kind(
    spec: RuleSpec,
    specs: dict[str, RuleSpec],
    rng: _random.Random,
    max_depth: int,
) -> str:
    arm_names = [
        it.atom.name
        for it in spec.items
        if isinstance(it, IrItem) and isinstance(it.atom, IrRuleRef)
    ]
    if not arm_names:
        return ""
    arm = rng.choice(arm_names)
    return generate(arm, specs, rng=rng, max_depth=max_depth - 1)


def generate(
    rule_name: str,
    specs: dict[str, RuleSpec],
    *,
    rng: _random.Random | None = None,
    max_depth: int = 5,
) -> str:
    if rng is None:
        rng = _random.Random()
    spec = specs.get(rule_name)
    if spec is None:
        return ""
    if spec.kind == "alternation":
        return _gen_alternation_kind(spec, specs, rng, max_depth)
    if spec.kind == "value_str":
        if spec.items and isinstance(spec.items[0], IrAlternation):
            return _gen_alternation(spec.items[0], specs, rng, max_depth)
        return "".join(
            _gen_atom(it, specs, rng, max_depth)
            for it in spec.items
            if isinstance(it, IrItem)
        )
    return "".join(
        _gen_atom(it, specs, rng, max_depth)
        for it in spec.items
        if isinstance(it, IrItem)
    )
```

The legacy `_gen_sequence_min_depth` recursion-cap branch is dropped. Property
tests in `tests/property/test_roundtrip.py:22` skip empty generator output,
so depth-0 returning `""` is handled. **Mandatory verification before
commit:** `uv run pytest tests/property/ -q` must pass against all seven
ground-truth grammars at the default `max_examples=30`.

### 2.5 Delete legacy source modules **and legacy test directories** (before 2.6 renames)

Legacy test dirs must go before renames because `git mv` targets the same
paths.

```bash
# Source deletions
git rm -r src/lexic/codegen
git rm -r src/lexic/grammars/gbnf
git rm src/lexic/grammars/flavours.py
git rm src/lexic/ir/atoms.py src/lexic/ir/builder.py
git rm src/lexic/ir/classify.py src/lexic/ir/convert.py
git rm src/lexic/ir/protocols.py

# Legacy-test deletions (clears the way for 2.6 renames)
git rm tests/unit/lexic/ir/test_atoms.py
git rm tests/unit/lexic/ir/test_builder.py
git rm tests/unit/lexic/ir/test_classify.py
git rm tests/unit/lexic/ir/test_convert.py
git rm tests/unit/lexic/ir/test_protocols.py
git rm -r tests/unit/lexic/codegen
git rm -r tests/unit/lexic/grammars/gbnf
git rm tests/unit/lexic/grammars/test_flavours.py
git rm tests/integration/test_codegen.py
git rm tests/integration/test_gbnf_roundtrip.py
```

### 2.6 Rename `new_*` directories and their inner `test_init_*` files

```bash
git mv src/lexic/new_codegen src/lexic/codegen
git mv src/lexic/grammars/new_gbnf src/lexic/grammars/gbnf
git mv tests/unit/lexic/new_codegen tests/unit/lexic/codegen
git mv tests/unit/lexic/grammars/new_gbnf tests/unit/lexic/grammars/gbnf

# Project-memory rule: test_init_<package>.py — drop the "new_" prefix.
git mv tests/unit/lexic/codegen/test_init_new_codegen.py \
       tests/unit/lexic/codegen/test_init_codegen.py
git mv tests/unit/lexic/grammars/gbnf/test_init_new_gbnf.py \
       tests/unit/lexic/grammars/gbnf/test_init_gbnf.py
```

### 2.7 Sed import paths

```bash
find src tests -name '*.py' -print0 | xargs -0 sed -i \
    -e 's|lexic\.grammars\.new_gbnf|lexic.grammars.gbnf|g' \
    -e 's|lexic\.new_codegen|lexic.codegen|g' \
    -e 's|\bNewRuleSpec\b|RuleSpec|g'
```

GNU sed `\b` word boundary; host is Linux per system info.

### 2.8 Collapse `src/lexic/ir/spec.py`

Step 2.7 produces two `class RuleSpec:` definitions (the second was
`NewRuleSpec`). Delete the older one. Final file:

```python
"""RuleSpec — canonical representation of one grammar rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from lexic.ir.nodes import IrAlternation, IrItem


@dataclass
class RuleSpec:
    """Complete specification of one grammar rule.

    Downstream emitters (ModuleEmitter, GbnfEmitter, AbnfEmitter, LarkBuilder)
    consume this instead of the raw flavour-AST.

    field_map: Pydantic field name → index in items list.
      - Structural IrLiteral items (quantifier (1,1)) are NEVER in field_map.
      - kind='alternation' items have field_map={}.
      - IrCharClass, IrRuleRef, IrGroup, and quantified IrLiteral items each
        have exactly one field_map entry.

    kind='value_str': single ``value: str`` field. Multi-arm form:
      items=[IrAlternation(...)]; emitters dispatch on isinstance.
    kind='alternation': abstract class; items=[IrItem(IrRuleRef(arm))...];
      field_map={}.
    kind='sequence': concrete class; items lists IrItems in grammar order;
      field_map populated.
    """

    rule_name: str
    class_name: str
    parent_class_name: str
    kind: Literal["sequence", "alternation", "value_str"]
    items: list[IrItem | IrAlternation] = field(default_factory=list)
    field_map: dict[str, int] = field(default_factory=dict)
    non_semantic_fields: frozenset[str] = field(default_factory=frozenset)
```

### 2.9 `src/lexic/ir/__init__.py` final form

```python
"""Lexic IR public surface."""

from lexic.ir.charclass import parse_charclass_chars
from lexic.ir.derive import (
    classify_kind,
    compute_parents,
    derive_specs,
    has_ruleref,
    hoist_helpers,
)
from lexic.ir.directives import Directives, parse_directives
from lexic.ir.emit import FlavourEmitter
from lexic.ir.escapes import CANONICAL_ESCAPES, EscapeCodec
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
    Quantifier,
)
from lexic.ir.spec import RuleSpec
from lexic.ir.topo import topo_sort
from lexic.ir.walk import IrTransformer, IrVisitor

__all__ = [
    "CANONICAL_ESCAPES",
    "Directives",
    "EscapeCodec",
    "FlavourEmitter",
    "HelperRuleRegistry",
    "IrAlternation",
    "IrAst",
    "IrCharClass",
    "IrGroup",
    "IrItem",
    "IrLiteral",
    "IrRule",
    "IrRuleRef",
    "IrSequence",
    "IrTransformer",
    "IrVisitor",
    "Quantifier",
    "RuleSpec",
    "classify_kind",
    "compute_parents",
    "derive_specs",
    "has_ruleref",
    "hoist_helpers",
    "parse_charclass_chars",
    "parse_directives",
    "topo_sort",
]
```

### 2.10 Slim `src/lexic/ir/naming.py` and move `_sanitize_pattern`

Final `naming.py`:

```python
"""IR field-naming lookup tables.

CHARCLASS_NAMES and LITERAL_NAMES are the Tier-1 / Tier-2 lookup tables used
by ir/derive.py::_field_map and codegen/aliases.py::collect_aliases.
"""

from __future__ import annotations

CHARCLASS_NAMES: dict[str, str] = {
    "[0-9]": "digit",
    "[0-9a-fA-F]": "hex",
    "[a-fA-F0-9]": "hex",
    "[a-f]": "hex_lower",
    "[A-F]": "hex_upper",
    "[a-z]": "lower",
    "[A-Z]": "upper",
    "[a-zA-Z]": "letter",
    "[a-zA-Z_0-9]": "alnum",
}

LITERAL_NAMES: dict[str, str] = {
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

__all__ = ["CHARCLASS_NAMES", "LITERAL_NAMES"]
```

The underscore on `_LITERAL_NAMES` is dropped — it's a public constant.

Move `_sanitize_pattern` to `src/lexic/ir/derive.py` as a private function
inserted before `_ATOM_HINT`. The import in `derive.py` (line 11) changes
from
```python
from lexic.ir.naming import _LITERAL_NAMES, CHARCLASS_NAMES, _sanitize_pattern
```
to
```python
from lexic.ir.naming import CHARCLASS_NAMES, LITERAL_NAMES
```
References inside `derive.py` from `_LITERAL_NAMES` → `LITERAL_NAMES`
(occurrences in `_ATOM_HINT` and `_FIELD_BASE` dicts).

### 2.11 Slim `src/lexic/ir/emit.py`

Drop:
- `from lexic.ir.atoms import ...` block (lines 18–27)
- `TypeVar A` and `Atom` references
- Static `handler` and `make_handlers` helpers
- `DEFAULT_HANDLERS` class attribute
- The `handlers` parameter on `__init__`
- The `render_atom` method
- The `from lexic.ir.protocols import AtomEmitHandler, EscapeCodec` block

Import `EscapeCodec` directly:
```python
if TYPE_CHECKING:
    from lexic.ir.escapes import EscapeCodec
```

`__init__` becomes:
```python
def __init__(self, escapes: EscapeCodec) -> None:
    self._escapes = escapes
```

Rewrite `_emit_body` for the new RuleSpec shape:
```python
def _emit_body(self, spec: RuleSpec) -> str:
    if not spec.items:
        return self.empty_body
    if spec.kind == "alternation":
        return self.alt_separator.join(
            self._emit_item(it)
            for it in spec.items
            if isinstance(it, IrItem)
        )
    first = spec.items[0]
    if isinstance(first, IrAlternation):
        return self._emit_alternation(first)
    parts = [self._emit_item(it) for it in spec.items if isinstance(it, IrItem)]
    return " ".join(p for p in parts if p) or self.empty_body
```

In `_emit_ir_atom`, replace `NotImplementedError` with
`UnsupportedConstructError`:
```python
raise UnsupportedConstructError(
    f"No IR-atom handler for {type(atom).__name__!r}"
)
```

`GbnfEmitter` already overrides `emit` / `emit_rule` / `_emit_body`;
`AbnfEmitter` relies on the parent `_emit_body` and works with the rewrite
through its overridden `place_quantifier` / `format_quantifier`.

### 2.12 Tighten `src/lexic/grammars/flavour.py`

```python
"""Flavour ABC — the contract every grammar flavour fulfils."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import IrGroup, IrLiteral, Quantifier

if TYPE_CHECKING:
    from lexic.ir.emit import FlavourEmitter


class Flavour(ABC):
    """Per-flavour configuration. Subclass and fill in class attributes."""

    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    meta_grammar: ClassVar[str]
    escapes: ClassVar[EscapeCodec]
    emitter: ClassVar[type["FlavourEmitter"]]
    line_comment: ClassVar[str] = ""

    @staticmethod
    @abstractmethod
    def parse_quantifier(text: str) -> Quantifier:
        """Parse a flavour-specific quantifier token text into canonical bounds."""

    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse a bracket-expression token. Return (canonical_pattern, negated)."""

    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrGroup:
        """Optional sugar-expansion hook. Default: identity (return IrLiteral)."""
        return IrLiteral(decoded)
```

### 2.13 Fix `src/lexic/parsing/lark_builder.py` two bugs

Add to the imports section:
```python
from lexic.ir.escapes import EscapeCodec
```

Add after the imports:
```python
class _LarkLiteralEscapes(EscapeCodec):
    SHORT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}


_LARK_ESCAPES = _LarkLiteralEscapes()
```

`HEX_ESCAPES` is intentionally omitted — Lark accepts literal Unicode
codepoints in quoted strings, and the seven ground-truth grammars are ASCII.
If a future grammar requires `\xNN`-style escape preservation in Lark
output, add the tuple to `_LarkLiteralEscapes` alongside `SHORT_ESCAPES`.

In `_atom_to_lark`:

- `IrLiteral` branch — replace
  ```python
  escaped = atom.value.replace("\\", "\\\\").replace('"', '\\"')
  return f'"{escaped}"{q}'
  ```
  with
  ```python
  return f'"{_LARK_ESCAPES.encode(atom.value)}"{q}'
  ```

- `IrCharClass` branch — replace
  ```python
  return f"/{_bracket(atom.pattern, atom.negated)}/{q}"
  ```
  with
  ```python
  return f"/{_bracket(atom.pattern.replace('/', '\\/'), atom.negated)}/{q}"
  ```
  (Python literal `'\\/'` is the 2-char string `\/` — the Lark-source-level
  forward-slash escape.)

### 2.14 Regression tests for both `lark_builder` bugs

Append to `tests/unit/lexic/parsing/test_lark_builder.py`. The new tests
use the `item` and `spec` helpers from `tests/_ir_fixtures.py` (created in
2.16). Ensure the file's import block includes:

```python
import lark

from lexic.ir.nodes import IrCharClass, IrLiteral
from lexic.parsing.lark_builder import LarkBuilder
from tests._ir_fixtures import item, spec
```

(Most are likely already present from existing tests in the file; add only
what's missing.)

Append the tests:

```python
def test_literal_with_newline_escapes_to_n() -> None:
    """Raw \\n must round-trip through Lark as the escape sequence \\n."""
    s = spec("line", "sequence", items=[item(IrLiteral("\n"))], field_map={"lit": 0})
    grammar, start = LarkBuilder([s]).build_grammar()
    assert '"\\n"' in grammar
    lark.Lark(grammar, parser="earley", start=start)  # must not raise


def test_charclass_with_slash_escapes_in_regex() -> None:
    """`/` inside a char class must be backslash-escaped in the Lark regex."""
    s = spec("op", "sequence", items=[item(IrCharClass("-+*/"))], field_map={"head": 0})
    grammar, start = LarkBuilder([s]).build_grammar()
    assert "/[-+*\\/]/" in grammar
    lark.Lark(grammar, parser="earley", start=start)  # must not raise
```

### 2.15 Update `src/lexic/__init__.py`

```python
"""Lexic — grammar engine."""

from lexic.compile import compile_from_path, compile_text
from lexic.generate import generate
from lexic.parse import parse

__all__ = ["compile_from_path", "compile_text", "generate", "parse"]
```

Public surface changes — `codegen` and `codegen_from_path` are no longer
top-level re-exports.

### 2.16 Shared test-fixture helper + per-file rewrites

Create `tests/_ir_fixtures.py` (top-level test util — importable from any
test package as `from tests._ir_fixtures import item, spec`; placed there
deliberately to avoid cross-package imports between `tests/unit/lexic/ir/`,
`tests/unit/lexic/parsing/`, and the top-level `tests/unit/lexic/`):

```python
"""Shared IrItem-based fixture helpers for the unit test suite."""

from __future__ import annotations

from typing import Iterable, Literal

from lexic.ir.nodes import IrItem, Quantifier
from lexic.ir.spec import RuleSpec

REQ = Quantifier(1, 1)
OPT = Quantifier(0, 1)
PLUS = Quantifier(1, None)

Kind = Literal["sequence", "alternation", "value_str"]


def item(atom, q: Quantifier = REQ) -> IrItem:
    return IrItem(atom=atom, quantifier=q)


def spec(
    rule_name: str,
    kind: Kind,
    items: Iterable,
    *,
    field_map: dict[str, int] | None = None,
    non_semantic_fields: frozenset[str] = frozenset(),
) -> RuleSpec:
    return RuleSpec(
        rule_name=rule_name,
        class_name=rule_name.title().replace("-", ""),
        parent_class_name="GrammarModel",
        kind=kind,
        items=list(items),
        field_map=field_map or {},
        non_semantic_fields=non_semantic_fields,
    )
```

Importers use `from tests._ir_fixtures import item, spec, REQ, OPT, PLUS`.

Per-file rewrites — each replaces legacy fixtures with IrItem equivalents,
exercising the same behaviour:

- **`tests/unit/lexic/test_base.py`** — value_str, sequence with literal
  baked in, sequence with nested GrammarModel, sequence with `List[...]`
  field, optional field absent, alternation raises, `semantic_dump`
  excludes `non_semantic_fields=frozenset({"ws"})`, `to_grammar` resolves
  flavour.
- **`tests/unit/lexic/test_generate.py`** — simple value_str literal,
  multi-arm value_str via `IrAlternation`, sequence with rule refs, optional
  rule ref (count 0), recursive grammar (max_depth boundary), negated
  charclass, group with quantifier.
- **`tests/unit/lexic/ir/test_emit.py`** — keep IR-AST chain tests; drop
  DEFAULT_HANDLERS tests. Add `_emit_body` tests for each kind; assert
  `_emit_ir_atom` on unknown type → `UnsupportedConstructError`.
- **`tests/unit/lexic/ir/test_naming.py`** — keep `CHARCLASS_NAMES` /
  `LITERAL_NAMES` content assertions only. If the file reduces to
  trivialities, fold into `test_derive.py` and `git rm` the file in the same
  commit.
- **`tests/unit/lexic/ir/test_spec.py`** — assert
  `RuleSpec.items: list[IrItem | IrAlternation]`, `non_semantic_fields`
  default = `frozenset()`.
- **`tests/unit/lexic/ir/test_topo.py`** — IrItem fixtures.
- **`tests/unit/lexic/ir/test_helpers.py`** — verify; rewrite if Atom-shaped.
- **`tests/unit/lexic/grammars/abnf/test_emitter.py`** — replace
  `render_atom(...)` tests with `emit_rule(...)` tests on single-IrItem
  rules. Working drafts exist in `failed_chat.txt`; lift but drop any ignore
  directives.
- **`tests/property/conftest.py`** — replace the fixture body:
  ```python
  from lexic.compile import compile_grammar
  from lexic.grammars.gbnf.flavour import GbnfFlavour

  @pytest.fixture(scope="session")
  def all_grammar_specs() -> dict[str, dict]:
      result = {}
      for name in ALL_GRAMMARS:
          text = (GROUND_TRUTH / f"{name}.gbnf").read_text()
          _, specs = compile_grammar(text, GbnfFlavour)
          result[name] = {s.rule_name: s for s in specs}
      return result
  ```
- **`tests/integration/test_full_round_trip.py`** — `compile_text` (the
  function) survives the cutover and drives the new pipeline post-2.1.
  Drop only the assertions whose purpose was the parallel-track side-by-side
  comparison between old `_compile_core` output and new `compile_grammar`
  output. Keep the single-pipeline assertions of the form
  `compile_text(text).parse(text).to_text() == text`. If nothing meaningful
  survives the cut, `git rm` it.

### 2.17 Layering-invariant integration test

Create `tests/integration/test_layering_invariants.py`:

```python
"""Layering invariants enforced via static grep over src/lexic/."""

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


def test_parsing_imports_grammars_only_via_flavour_abc():
    """Currently vacuous — parsing/* doesn't import lexic.grammars at all.
    Kept as a guardrail against future regression.
    """
    parsing = SRC / "parsing"
    for p in parsing.rglob("*.py"):
        for line in p.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("from lexic.grammars", "import lexic.grammars")):
                assert "lexic.grammars.flavour" in stripped, (
                    f"{p}: imports lexic.grammars beyond the Flavour ABC: {stripped}"
                )


def test_flavours_module_is_gone():
    assert not (SRC / "grammars" / "flavours.py").exists()
    for p in SRC.rglob("*.py"):
        content = p.read_text()
        assert "from lexic.grammars.flavours" not in content, f"{p}"
        assert "import lexic.grammars.flavours" not in content, f"{p}"


def test_legacy_atom_modules_are_gone():
    for name in ("atoms.py", "builder.py", "classify.py", "convert.py", "protocols.py"):
        assert not (SRC / "ir" / name).exists(), f"ir/{name} still present"


def test_no_new_gbnf_or_new_codegen_residual():
    for p in list(SRC.rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
        content = p.read_text()
        assert "lexic.grammars.new_gbnf" not in content, f"{p}: residual new_gbnf"
        assert "lexic.new_codegen" not in content, f"{p}: residual new_codegen"


def test_rulespec_items_typed_for_iritem():
    content = (SRC / "ir" / "spec.py").read_text()
    assert "list[IrItem | IrAlternation]" in content
    assert "from lexic.ir.atoms" not in content
    assert "NewRuleSpec" not in content
```

### 2.18 Documentation sync (same commit)

The cutover changes structural facts described in several documents. Edit
in this commit so docs match code:

- **`CLAUDE.md`** — replace the "Current state — two pipelines in parallel"
  section and the legacy half of the "Project layout" tree with the
  post-cutover single-pipeline layout. Restate the layering-rules narrative
  in terms of the new seams (`codegen`, `build_lark`); drop references to
  `build_classes_and_specs` / `LarkBuilder`.
- **`prototyping/next/3_ROADMAP.md`** — mark the cutover slice complete.
- **`prototyping/next/2_ARCHITECTURE.md`** — drop parallel-track caveats;
  document the IR-AST canonical pipeline as the only pipeline.
- **`.wiki/index.md`** — update pages on architecture, IR shapes, field
  naming, the cutover plan, and cross-references.
- **`.wiki/log.md`** — append a single dated entry summarising the cutover:
  legacy pipeline retired, `NewRuleSpec` collapsed, `ir/protocols.py`
  removed, Flavour-based registry consolidated, lark_builder bugs fixed.

### 2.19 Clear caches, run suite, audit grep

```bash
rm -f generated/*.py
uv run pytest tests/ -q
uv run pytest tests/property/ -q              # explicit pass for property suite
uv run ruff check src/ tests/
grep -rn "from lexic.ir import.*Atom\b\|from lexic.ir.atoms\|from lexic.ir.builder\|from lexic.ir.classify\|from lexic.ir.convert\|from lexic.ir.protocols\|from lexic.grammars.flavours\|\\bget_adapter\\b\|adapter_for_extension\|FlavourAdapter\|register_adapter\|\\bADAPTERS\\b\|NewRuleSpec\|RuleClassifier\|SequenceConverter\|new_gbnf\|new_codegen\|decode_gbnf_escapes\|codegen_from_path\|build_classes_and_specs" src/ tests/
```

Acceptance:
- Full suite green; no skips beyond pre-existing xfails.
- Property suite green for all seven ground-truth grammars at
  `max_examples=30`.
- Ruff clean.
- Grep returns empty.

### 2.20 Single commit

```bash
git add -A
git commit -m "refactor(ir): cutover — IR-AST canonical pipeline replaces legacy IRBuilder

- compile._compile_core routes through compile_grammar + codegen + build_lark
- grammars.flavours removed; registry consolidated on the Flavour ABC
- new_gbnf/ -> grammars/gbnf/; new_codegen/ -> codegen/; sed updates imports
- test_init_new_*.py renamed to test_init_*.py per project memory rule
- ir/atoms.py, ir/builder.py, ir/classify.py, ir/convert.py, ir/protocols.py deleted
- RuleSpec.items typed list[IrItem | IrAlternation]; NewRuleSpec collapsed
- ir/naming.py slimmed to two lookup tables; _sanitize_pattern moved to derive
- ir/emit.py: DEFAULT_HANDLERS + legacy-atom dispatch dropped
- base.py, generate.py: IrItem-only dispatch; decode_gbnf_escapes removed
- Flavour.emitter typed ClassVar[type[FlavourEmitter]]
- parsing/lark_builder.py: literal escape codec + char-class / escape, with
  regression tests for both bugs
- lexic/__init__.py: codegen / codegen_from_path re-exports removed
- tests/integration/test_layering_invariants.py asserts spec layering rules
- Legacy unit + integration tests deleted; surviving tests rewritten with
  IrItem fixtures
- CLAUDE.md, ARCHITECTURE.md, ROADMAP.md, .wiki/ synced to post-cutover state"
```

---

## Verification rubric (both phases)

- `uv run pytest tests/ -q` fully green, no skips beyond pre-existing xfails.
- `uv run ruff check src/ tests/` clean.
- `tools/auto_fix.sh` produces no diff after the commit.
- No new `# type: ignore`, `# noqa`, `# pylint: disable` directives.
- No `Co-Authored-By` on commits.
- Property suite passes for all seven ground-truth grammars at
  `max_examples=30`.

## Executor notes

- Re-read every file mentioned in this plan before editing — file state may
  have drifted between plan-write time and execution.
- Run `tools/auto_fix.sh` before each manual fix-up to avoid burning edits
  on mechanical formatting drift.
- Do not start Phase 2 until Phase 1A and Phase 1B are green and committed.
- If a sub-step inside Phase 2 produces breakage that no earlier sub-step
  can explain, stop and re-investigate rather than patch — the cascading
  import failure that killed `failed_chat.txt` always presents as "the next
  sub-step exposes a deletion that an earlier sub-step missed".
- Ask before dispatching subagents; never use worktrees.
