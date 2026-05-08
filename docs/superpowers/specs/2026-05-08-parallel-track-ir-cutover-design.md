# Parallel-track IR cutover: replace dual-shape migration with side-by-side build

**Date:** 2026-05-08
**Status:** Approved (brainstormed)
**Supersedes (in part):** Tasks 19–25 of `docs/superpowers/plans/2026-04-29-ir-ast-architecture.md`. Tasks 0–18 of that plan are landed and stand. Task 26 (documentation supersession) is deferred to a separate brainstorm after this work lands.
**Implementation plan:** to be written.

## Background

Tasks 1–18 of the IR-AST architecture plan are landed. The new pipeline (`compile_grammar`, `MetaGrammarParser.for_flavour`, `derive_specs`) produces `NewRuleSpec`s with `items: list[IrItem | IrAlternation]` end-to-end for both GBNF and ABNF, including a passing cross-flavour transpilation integration test (commit `d87e4ad`).

The legacy pipeline (`compile_text → build_classes_and_specs → IRBuilder`) is still in place and produces the old `RuleSpec` shape with `items: list[Atom]` over the seven legacy atom dataclasses (`LiteralAtom`, `CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom`, `RuleRefAtom`, `AlternationAtom`, `InlineAlternationAtom`). Both pipelines coexist; no consumer below `compile.py` understands both shapes.

Tasks 19–25 of the original plan migrate consumers from the old shape to the new via a *dual-shape* strategy: every consumer (gbnf emitter, model_emitter, lark_builder, transformer, base, generate) is updated to handle both shapes via `isinstance` dispatch, then the legacy branches are stripped after the entry point is rerouted. Three structural problems make this strategy worse than it has to be:

1. **Every consumer file is touched twice.** Tasks 20–24b add dual-shape dispatch; Tasks 25b–25e remove the same dispatch. ~6 source files plus tests modified, then re-modified, with the only "delivery" between them being a redundant code path that exists to be deleted.
2. **The transient adapter `legacy_to_iritems` (Task 19) has no caller.** Once consumers are dual-shape, the adapter is unreachable from production code paths. It is dead on arrival.
3. **The plan was written against a pre–Task 18 mental model.** Decisions accumulated during Tasks 1–18 implementation were bolted onto the later tasks as `**Decision X applies here:**` notes (Decision H, CQ #1, CQ #2, OV #1, etc.) rather than restructuring the tasks. Several of these notes contradict the original task body (Task 21's `# FIXME` placeholder; Task 22's `name == "ws"` hack; Task 19's `_convert_inline_regex_to_group` shape-invalidity).

## Strategy

Replace the dual-shape migration with a **parallel-track** build:

- The new shape lands in fresh modules (`new_gbnf/`, `new_codegen/`) or directly in their final destinations (`parsing/lark_builder.py`, `parsing/transformer/`) where the destination is empty.
- The old shape stays untouched until cutover. No `isinstance(item, IrItem)` branches in legacy modules. No transient adapter.
- A single cutover commit reroutes `compile.py`, deletes the legacy modules in one fell swoop, renames `new_*` → final names, and tightens types.

The cutover commit has wide blast radius but is mostly mechanical (`git rm`, `git mv`, `sed` on imports). The integration suite is the safety net — if it passes, the rerouted pipeline is correct end-to-end.

## Architectural principles

Inherited from `2026-04-29-ir-ast-architecture-design.md` unchanged. This spec adds three:

**P7. No transient code in master.** Every commit between Slice 1 and the cutover ships clean code. No `# FIXME`, no "delete me in Slice 4", no `isinstance`-on-shape forks.

**P8. Codegen and parsing are flavour-blind.** `lexic.codegen` and `lexic.parsing` consume `RuleSpec`s and produce artefacts. Neither imports from `lexic.grammars.gbnf` or `lexic.grammars.abnf`. Flavour selection is resolved upstream in `compile.py`.

**P9. The flavour interface is the `Flavour` ABC alone.** `lexic.grammars.flavours` (the `FlavourAdapter` Protocol layer) is removed. `lexic.grammars.flavour.Flavour` and the registry helpers in `grammars/__init__.py` are the sole flavour surface.

## Architecture

### End state (post-cutover)

```
src/lexic/
  compile.py              orchestration: text → CompiledGrammar (sole orchestrator)
  base.py · generate.py · exceptions.py · parse.py
  ir/
    spec.py               RuleSpec.items: list[IrItem]; NewRuleSpec collapsed in
    nodes.py · walk.py · directives.py · derive.py
    emit.py               handlers dispatch on IR AST nodes only
    naming.py             slim: data + utils only
    protocols.py          drops RuleClassifier, SequenceConverter
    escapes.py · helpers.py · charclass.py · regex_portable.py · topo.py
    __init__.py           exports IR AST surface, no legacy atoms
  parsing/
    meta_parser.py        (existing)
    lark_builder.py       IrItem-only spec → lark grammar + transformer factory
    transformer/
      build_transformer.py · builders.py
  codegen/                slimmed: specs → Pydantic Python source
    __init__.py           codegen(specs, stem) → dict[name, type]
    model_emitter.py      IrItem-only
  grammars/
    flavour.py            Flavour ABC (sole flavour surface)
    __init__.py           registry: register_flavour, get_flavour, flavour_for_extension
    gbnf/                 (renamed from new_gbnf at cutover)
      adapter.py · emitter.py · escapes.py · flavour.py
      meta_grammar.py · parser.py · charclass.py · __init__.py
    abnf/                 (untouched in this work)
      escapes.py · emitter.py · flavour.py · meta_grammar.py · __init__.py
```

### Layering rules

- `lexic.ir` imports nothing from `lexic.grammars`, `lexic.parsing`, `lexic.codegen`.
- `lexic.parsing` imports from `lexic.ir` and `lexic.grammars.flavour` (the ABC only). It does not import any specific flavour module.
- `lexic.codegen` imports from `lexic.ir`. It does not import `lexic.grammars`, `lexic.parsing`, or any specific flavour module.
- `lexic.grammars.<flavour>` imports from `lexic.ir` and `lexic.grammars.flavour`. Per-flavour packages are siblings; one flavour does not import another.
- `lexic.compile` is the only orchestrator. It imports `lexic.ir`, `lexic.grammars`, `lexic.parsing`, `lexic.codegen`.
- `lexic.base` and `lexic.generate` (runtime) import from `lexic.ir` only. The single deliberate exception — `to_grammar()` calling a flavour emitter — goes through `grammars.get_flavour(name).emitter` rather than a hard-coded `lexic.grammars.gbnf` import.

### Mid-flight (between slices, before cutover)

```
src/lexic/
  compile.py              still routes through legacy pipeline
  ir/                     legacy atoms still present in atoms.py et al
  parsing/                gains lark_builder.py + transformer/
                            (parallel to codegen/lark_builder + codegen/transformer
                             which still serve the legacy compile path)
  new_codegen/            model_emitter only (IrItem-only)
  codegen/                unchanged, still legacy IRBuilder pipeline
  grammars/
    flavour.py · flavours.py    both exist
    new_gbnf/             full mirror, IrItem-only
    gbnf/                 unchanged
    abnf/                 unchanged
```

Internal imports inside `new_gbnf/` reference `lexic.grammars.new_gbnf.X`. Internal imports inside `new_codegen/` reference `lexic.new_codegen.X`. Cutover renames these via `sed`.

### Data flow (post-cutover)

```
text + flavour_name
    │
    ▼
compile.compile_text  ──► grammars.get_flavour(name) ──► Flavour subclass
    │
    ▼
compile_grammar(text, flavour_cls)
    ├── parse_directives(text, flavour.line_comment) ──► Directives(non_semantic, start)
    ├── MetaGrammarParser.for_flavour(flavour).parse(text) ──► IrAst
    └── derive_specs(ast, non_semantic_rules) ──► (start_rule, list[RuleSpec])
                                                    │
                              ┌─────────────────────┴─────────────────────┐
                              ▼                                           ▼
                  codegen.codegen(specs, stem)         parsing.lark_builder.build_lark(
                              │                            specs, classes, start_rule)
                              ▼                                           │
                  dict[name → type[GrammarModel]]                          ▼
                              │                          (lark.Lark, lark.Transformer)
                              └─────────────────────┬─────────────────────┘
                                                    ▼
                                CompiledGrammar(classes, specs, parser, transformer)
                                                    │
                                                    ▼
                                              .parse(text) → GrammarModel instance
```

The flavour parameter never reaches `codegen` or `parsing.lark_builder`. Below `derive_specs` everything is flavour-agnostic IR.

## Slices

Four ordered slices. Each leaves the tree green with the full suite passing.

### Slice 1 — `new_gbnf/` (full mirror, IrItem-only)

`src/lexic/grammars/new_gbnf/`:

| File | Content |
|---|---|
| `__init__.py` | Re-exports |
| `meta_grammar.py` | Copy of current `gbnf/meta_grammar.py` (already IR-AST shape) |
| `escapes.py` | Copy of current `gbnf/escapes.py` (already clean) |
| `flavour.py` | Copy of current `gbnf/flavour.py` (re-pointed imports to `new_gbnf` siblings) |
| `parser.py` | Thin wrapper: `MetaGrammarParser.for_flavour(GbnfFlavour).parse(text) → IrAst` |
| `emitter.py` | IrItem-only dispatch: `IrLiteral`, `IrCharClass`, `IrRuleRef`, `IrGroup`, plus bare `IrAlternation` for multi-arm `value_str`. Implements `FlavourEmitter` ABC from `lexic.ir.emit` |
| `adapter.py` | Exposes parser + emitter; sets `flavour_cls = GbnfFlavour` |

(The current `gbnf/` package has no `charclass.py`; charclass logic lives in `lexic.ir.charclass` and is consumed via that import. `new_gbnf/` does the same.)

Tests at `tests/unit/lexic/grammars/new_gbnf/` mirror the file layout.

**Exit criteria:**
- `tests/unit/lexic/grammars/new_gbnf/` passes.
- The full suite stays green (nothing else imports `new_gbnf`).
- `new_gbnf` modules import only from `lexic.ir`, `lexic.grammars.flavour`, `lexic.parsing.meta_parser`, and other `lexic.grammars.new_gbnf` siblings.

### Slice 2 — `new_codegen/` (model_emitter only)

`src/lexic/new_codegen/`:

| File | Content |
|---|---|
| `__init__.py` | Public entry: `codegen(specs: list[RuleSpec], stem: str) -> dict[str, type]`. Internally renders Python source via `model_emitter`, writes `generated/<stem>.py`, imports the module, returns the class dict. **No flavour parameter. No text-parsing. No `IRBuilder`.** |
| `model_emitter.py` | IrItem-only dispatch. Renders `RuleSpec` (with new-shape items) to Python source string. Emits the canonical `from lexic.ir.nodes import …` block per Decision CQ #4 (full IR AST surface, fixed import line, no detect-and-include). Emits real Python expressions for every IR shape including `IrGroup` per Decision CQ #1 (no `# FIXME` placeholders) |

Tests at `tests/unit/lexic/new_codegen/`.

**Exit criteria:**
- `tests/unit/lexic/new_codegen/` passes.
- The full suite stays green.
- `new_codegen` imports only from `lexic.ir`, `lexic.base`, and stdlib.
- No `# FIXME` strings in generated module source for any input shape (asserted in tests).
- Module-level recursive `_repr_atom_value` / `_repr_alternation` / `_repr_sequence` / `_repr_iritem` produce eval-stable Python (round-trip test: `exec` the generated module, `__grammar__.items[i]` reconstructs the input IR).

### Slice 3 — `parsing/lark_builder.py` + `parsing/transformer/`

Add to `src/lexic/parsing/`:

| File | Content |
|---|---|
| `lark_builder.py` | IrItem-only. `build_lark(specs, classes, start_rule) -> (lark_grammar_str, lark.Lark, lark.Transformer)`. No name-string check on `"ws"` — non-semantic optionality flows from `RuleSpec.non_semantic_fields` and `IrItem.quantifier` (Decision CQ #2) |
| `transformer/build_transformer.py` | IrItem-only. Generates the runtime `lark.Transformer` from specs |
| `transformer/builders.py` | IrItem-only field-extraction strategies. Table-driven dispatch on `IrItem.atom` types |

Tests at `tests/unit/lexic/parsing/lark_builder.py` and `tests/unit/lexic/parsing/transformer/`. The old `codegen/lark_builder.py` and `codegen/transformer/` stay untouched — they still serve the legacy compile path.

**Exit criteria:**
- New tests pass.
- The full suite stays green.
- New modules import only from `lexic.ir`, `lark`, and stdlib. No imports from `lexic.codegen`, `lexic.grammars`, or any flavour module.
- No `atom.name == "ws"` or equivalent name-string check in `lark_builder.py` (asserted in tests).

### Slice 4 — Cutover

The "one fell swoop." Single landable commit. Mostly mechanical.

**Sub-step ordering (single commit):**

1. **Reroute `compile.py::_compile_core`:**

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
       return CompiledGrammar(classes=classes, specs=specs, parser=parser, transformer=transformer)
   ```

2. **Registry consolidation in `grammars/__init__.py`:**

   ```python
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
   ```

3. **Delete legacy modules and their tests.** `git rm -r` removes the test directories that mirror deleted source directories. Explicit list:

   ```bash
   # source modules
   git rm -r src/lexic/codegen
   git rm -r src/lexic/grammars/gbnf
   git rm src/lexic/grammars/flavours.py
   git rm src/lexic/ir/atoms.py src/lexic/ir/builder.py
   git rm src/lexic/ir/classify.py src/lexic/ir/convert.py

   # test modules — cascade with src deletion (mirror principle)
   git rm -r tests/unit/lexic/codegen
   git rm -r tests/unit/lexic/grammars/gbnf
   git rm tests/unit/lexic/ir/test_atoms.py
   git rm tests/unit/lexic/ir/test_builder.py
   git rm tests/unit/lexic/ir/test_classify.py
   git rm tests/unit/lexic/ir/test_convert.py
   ```

   The `git mv` in sub-step 4 then puts the parallel-track replacements into the just-emptied `codegen/` and `grammars/gbnf/` slots.

4. **Move `new_*` into final names:**

   ```bash
   git mv src/lexic/new_codegen src/lexic/codegen
   git mv src/lexic/grammars/new_gbnf src/lexic/grammars/gbnf
   git mv tests/unit/lexic/new_codegen tests/unit/lexic/codegen
   git mv tests/unit/lexic/grammars/new_gbnf tests/unit/lexic/grammars/gbnf
   ```

5. **Sed imports:**

   ```bash
   find src tests -name '*.py' -exec sed -i \
       -e 's|lexic\.grammars\.new_gbnf|lexic.grammars.gbnf|g' \
       -e 's|lexic\.new_codegen|lexic.codegen|g' \
       {} +
   ```

6. **Tighten `lexic.ir`:**
   - `ir/spec.py`: change `RuleSpec.items: list[Atom]` → `list[IrItem]`. Collapse `NewRuleSpec` into `RuleSpec`. Drop `from lexic.ir.atoms import Atom`.
   - `ir/emit.py`: replace legacy `DEFAULT_HANDLERS` (over `LiteralAtom`/etc.) with handlers over IR AST nodes (`IrLiteral`, `IrCharClass`, `IrRuleRef`, `IrGroup`).
   - `ir/naming.py`: keep `_CHARCLASS_NAMES`, `_LITERAL_NAMES`, `_sanitize_pattern`. Drop `assign_field_names`, `_charclass_field_name`, `_quantified_literal_field_name`, `_inline_regex_field_name`.
   - `ir/protocols.py`: drop `RuleClassifier`, `SequenceConverter`. Update `__all__`.
   - `ir/__init__.py`: drop legacy atom exports. Add IR AST exports (`IrAlternation`, `IrAst`, `IrCharClass`, `IrGroup`, `IrItem`, `IrLiteral`, `IrRule`, `IrRuleRef`, `IrSequence`, `Quantifier`, `IrTransformer`, `IrVisitor`, `derive_specs`, `classify_kind`, `compute_parents`, `hoist_helpers`, `Directives`, `parse_directives`).

7. **Tighten runtime modules:**
   - `base.py::to_text`: IrItem-only dispatch. Drop legacy-atom imports. Drop `decode_gbnf_escapes` import (literals are canonical post-MetaGrammarParser). The `to_grammar(name)` edge calls `grammars.get_flavour(name).emitter`.
   - `generate.py`: IrItem-only dispatch. Drop legacy-atom imports.

8. **Tighten `Flavour.emitter` typing in `grammars/flavour.py`:** `ClassVar[Any]` → `ClassVar[FlavourEmitter]` with `TYPE_CHECKING` import.

9. **Run full suite + ruff. Iterate failures in place. Commit.**

**Exit criteria for Slice 4:**
- Full suite green; property round-trips green.
- `src/lexic/grammars/flavours.py` does not exist.
- `src/lexic/codegen/` contains only `__init__.py` and `model_emitter.py`.
- `src/lexic/grammars/gbnf/` contains the new-shape mirror (no `ast.py`, no `ast_to_ir.py`).
- `src/lexic/ir/` does not contain `atoms.py`, `builder.py`, `classify.py`, or `convert.py`.
- `RuleSpec.items` is typed `list[IrItem]`.
- `NewRuleSpec` does not exist as a separate dataclass.
- `grep -r 'from lexic\.ir\.atoms' src/ tests/` returns nothing (excluding deleted files in git history).
- `grep -r 'from lexic\.grammars\.flavours' src/ tests/` returns nothing.
- `grep -r 'lexic\.grammars\.new_gbnf\|lexic\.new_codegen' src/ tests/` returns nothing.

## Testing strategy

**Mirror principle (CLAUDE.md §"Test file structure"):** test tree mirrors src tree exactly. When a source file is created, moved, renamed, or deleted, the corresponding test file gets the same treatment in the same commit.

**During parallel-track (Slices 1–3):**
- `tests/unit/lexic/grammars/new_gbnf/` mirrors `src/lexic/grammars/new_gbnf/`.
- `tests/unit/lexic/new_codegen/` mirrors `src/lexic/new_codegen/`.
- `tests/unit/lexic/parsing/lark_builder.py` and `tests/unit/lexic/parsing/transformer/` are added under existing `tests/unit/lexic/parsing/`.
- All existing unit tests for legacy modules remain green — the legacy pipeline is untouched.

**Integration tests** (`tests/integration/test_codegen.py`, `test_gbnf_roundtrip.py`, `test_parse.py`, `test_cross_flavour_arithmetic.py`) test the public surface (`compile_text`, `compile_grammar`, `parse`, round-trips). They keep passing through Slices 1–3 because the entry point routes through the legacy pipeline. At Slice 4 cutover, they remain green by definition — they are the cutover safety net.

**Property tests** (`tests/property/test_roundtrip.py`) exercise the full pipeline with hypothesis. No changes needed; passing through Slice 4 is the strongest signal that the cutover is sound.

**At cutover:**
- `git rm` all unit tests for deleted modules (legacy IR atoms, legacy IRBuilder, legacy classifier/converter, legacy GBNF AST, legacy Adapter Protocol).
- `git mv` parallel test trees into final names; `sed` import paths.
- Add `tests/integration/test_layering_invariants.py` asserting:
  - `lexic.ir` does not import `lexic.grammars.*`, `lexic.parsing.*`, `lexic.codegen.*`.
  - `lexic.codegen` does not import `lexic.grammars.*`, `lexic.parsing.*`.
  - `lexic.parsing` does not import `lexic.codegen.*`, `lexic.grammars.gbnf.*`, `lexic.grammars.abnf.*` — only `lexic.grammars.flavour`.
  - No `lexic.grammars.flavours` references anywhere.
  - No `lexic.grammars.new_gbnf` or `lexic.new_codegen` references anywhere.

## Out of scope

- **Generalising negation across atoms.** Today `IrCharClass.negated` is the only carrier of negation. The user has flagged that negation should be applicable to anything quantifiable. This is a separate IR-shape change that needs its own brainstorm. Tracked for a follow-up cycle.
- **Documentation supersession (Task 26).** Updating `prototyping/next/2_ARCHITECTURE.md` to reflect the post-cutover layering, adding ASCII pipeline diagrams, and rotating obsolete `prototyping/curr/` documents into `prototyping/old/` is deferred to a separate brainstorm after this work lands.
- **Slice C/D/E from `prototyping/next/3_ROADMAP.md`** (type-driven IR, `@grammar_rule` decorator, error-quality pass). Unaffected by this work.
- **ABNF parallel-track.** ABNF modules are already IR-AST shape (Tasks 14–17) and need no migration. They are untouched in this work.

## Risks and mitigations

**R1. Cutover commit blast radius.** Slice 4 touches many files at once.
- Mitigation: each sub-step within Slice 4 is mechanical (git operations, sed). Local rehearsal on a scratch branch reveals breakage before commit. Integration tests are the safety net.

**R2. Mid-flight import confusion.** While `gbnf/` and `new_gbnf/` coexist, accidentally importing the wrong one is a real bug source.
- Mitigation: all internal imports inside `new_gbnf/` reference `lexic.grammars.new_gbnf.X`. Slice 1 exit criterion includes a grep assertion that no `new_gbnf` module imports from `lexic.grammars.gbnf`. Same for `new_codegen`.

**R3. Generated module backwards compat.** Existing `generated/*.py` files were emitted by the legacy `model_emitter` and import legacy atoms. After cutover, those modules will fail to import.
- Mitigation: `generated/` is git-ignored and write-once per project (per CLAUDE.md §"Project layout"). Any consumer regenerates on first use after pulling. The cutover commit itself does not need to regenerate them; consumers do so transparently via `compile()`.

**R4. Decisions from Tasks 1–18 not preserved.** Several decisions in the original plan (Decision H, CQ #1, CQ #2, CQ #4, OV #1, OV #6, OV #12, OV #20, Arch #2, Arch #3) reflect architectural commitments that this spec must honour.
- Mitigation: each decision is anchored in a slice's exit criterion or implementation note. Specifically:
  - Decision CQ #1 (no `# FIXME` in generated source) → Slice 2 exit criterion.
  - Decision CQ #2 (no `name == "ws"` hack) → Slice 3 exit criterion.
  - Decision CQ #4 (full IR AST imports in generated modules, fixed line) → Slice 2 implementation note.
  - Decision OV #1 (Task 24b: `generate.py` is a runtime consumer; cannot be skipped) → Slice 4 sub-step 7.
  - Decision OV #6/#20 (`flavour_cls` on adapter) → Slice 1 (`new_gbnf/adapter.py`).
  - Decision OV #12 (`compile_grammar` returns `(start_rule, specs_list)`) → already landed in Task 12; Slice 4 sub-step 1 honours it.
  - Decision Arch #2 (`lexic.parsing` package layering) → Slice 3 exit criterion.
  - Decision Arch #3 (`Flavour.emitter` typing tightened) → Slice 4 sub-step 8.

## Open questions

None for this brainstorm. The IRCharClass negation generalisation and Task 26 documentation work are deferred to separate sessions per user direction.

## Success criteria (whole spec)

- 312+ existing tests + new unit tests for `new_gbnf`, `new_codegen`, `parsing/lark_builder`, `parsing/transformer` all green at the end of every slice.
- Property round-trips green.
- `compile_text(text, flavour="gbnf")` and `compile_text(text, flavour="abnf")` produce byte-identical results before and after the cutover for the seven ground-truth grammars.
- `RuleSpec.items: list[IrItem]` typed strictly. `NewRuleSpec` collapsed.
- `lexic.codegen` and `lexic.parsing` import nothing from `lexic.grammars.<flavour>`.
- `lexic.grammars.flavours` does not exist.
- No `# FIXME`, no `isinstance(item, IrItem)` shape forks, no `name == "ws"` hacks anywhere in the post-cutover tree.
