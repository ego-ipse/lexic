# Plan — `parsing` rename + flavour rework

> **SUPERSEDED (2026-07-02, user ruling).** No `parsing_legacy` — legacy Lark path is DELETED outright; the public API is re-driven by the Earley engine (requires GBNF IR self-grammar + reducer and an instance-parsing bridge); integration tests stay green; `IrFlavour` STAYS in `ir/` (D1 overridden). The Phase-1 mechanical rename checklist and file inventories below remain accurate reference material.

Date: 2026-07-02. Produced by plan-cutover agent; unreviewed by user.

Baseline before starting: `uv run pytest tests/ -q` (1188 green), `uv run ruff check src/ tests/`. **Coordination note:** the agent fixing type/lint issues inside `parsing_2/` must land first (or rebase onto Phase 1), since Phase 1 `git mv`s that whole directory. This plan depends only on module structure, not line numbers.

Every phase lands green (full suite + ruff + pylint on touched files). Never commit — leave each landing staged for the user.

---

## Decision points (recommendations up front)

**D1 — Where does IrFlavour live?** → **Move it out of `ir/` into `src/lexic/grammars/flavour.py`.**
`IrFlavour` currently sits in `src/lexic/ir/flavour.py`, but the new fields need the `Reducer` type (`parsing_2/reduce.py`), and `ir/` must stay a leaf. Options weighed:
- *Keep in `ir/`, type the reducer field as `IrDispatch`* (Reducer IS-A IrDispatch, so no import needed): rejected — `parse_reduced(grammar, text, reducer: Reducer)` would need casts at every call site, and it leaves `meta_grammar` (a Lark string) inside `ir/`, which already violates the standing ir-purity rule.
- *Move Reducer into `ir/`*: rejected — `reduce.py` imports `forest`, `kernel`, `lexruns`, `normalize`, `tables`, `trampoline`; it would drag half the engine into `ir/`.
- *Move IrFlavour to `grammars/flavour.py`*: **recommended.** This is the home CLAUDE.md already documents (the move into `ir/` was the deviation). Flavours are grammar-layer policy; `ir/` gets purer; the reducer field is honestly typed. New sanctioned arrow: **`lexic.parsing` ← `lexic.grammars`** (grammars import the engine's `Reducer` vocabulary) — the direction `abnf_2.py` already uses today.
`IrEscape` (also in `ir/flavour.py`) is pure IR action algebra (depends only on `ir.base`/`ir.escapes`) — it moves into `ir/action.py` with the other action leaves; `ir/flavour.py` is then deleted.

**D2 — Where does the legacy Lark surface live?** → **A `LarkFlavour(IrFlavour, ABC)` mixin in a new `src/lexic/parsing_legacy/flavour.py`.**
It carries exactly the Lark-era members: `meta_grammar: ClassVar[str]`, abstract `parse_quantifier` / `parse_charclass`, and the `normalize_literal` default. (`line_comment` stays on `IrFlavour` — it feeds `ir/directives.py`, not Lark.) `meta_parser.py` types against `LarkFlavour` (same-package import, killing its cross-layer `ir.flavour` import). Both concrete flavours inherit `LarkFlavour` for now since `compile.py` drives the legacy path for both. `compile_grammar` keeps its public `flavour: IrFlavour` signature and adds an `isinstance(flavour, LarkFlavour)` guard raising `UnsupportedConstructError` — the explicit-raise default the house style requires. When `parsing_legacy` dies, deleting the package deletes the whole legacy surface; concrete flavours drop one base class and three methods. Import-cycle audit done: `grammars/__init__` → `abnf.py` → `parsing_legacy.flavour` → `grammars.flavour` resolves cleanly (the last hop imports the *submodule* while the package init is mid-flight — standard, safe; `parsing_legacy/__init__.py` is docstring-only).

**D3 — GBNF has no IR grammar yet: optional fields or a class split?** → **Annotation-only ClassVars on the `IrFlavour` base; no split.**
`IrFlavour` declares `grammar: ClassVar[IrAst]` and `reducer: ClassVar[Reducer]` as the target shape; `_AbnfFlavour` assigns them; `_GbnfFlavour` simply doesn't yet — nothing reads them for GBNF (compile still runs the legacy path), and a test pins the transitional gap. When the GBNF IR grammar lands it's two assignments, zero base-class churn. The alternative (an `IrNativeFlavour` sub-ABC) forces a collapse-rename later, and the legacy-vs-native axis is already expressed by the `LarkFlavour` mixin. The future IR-native compile entry must guard access with an explicit `UnsupportedConstructError`, not let `AttributeError` leak.

**D4 — Fate of `abnf_2.py`?** → **Merge into `abnf.py`; delete `abnf_2.py`.**
The user calls the split-off sibling "the mess", and both flavour modules' docstrings already promise "bundles … in one module" with the end-goal of full auto-generation. `ABNF_GRAMMAR`, `ABNF_NOISE`, `ABNF_REDUCTIONS`, `ABNF_REDUCER` move in; `_AbnfFlavour` gains `grammar = ABNF_GRAMMAR`, `reducer = ABNF_REDUCER`. Trade-off: `abnf.py` grows to ~700 lines (it already carries a `duplicate-code` disable for exactly this bundling reason). Fallback if the user objects to size: a sibling named `grammars/abnf_grammar.py` that `abnf.py` imports — the `_2` name dies either way. Test-mirror consequence: `test_abnf_2.py` merges into `test_abnf.py` (~760 lines), **porting every test** — none targets a deleted symbol.

**D5 — Raw or normalized grammar on the flavour? Anything else the new path needs?** → **Raw `IrAst`; nothing else.**
Verified in `reduce.py`: `Reducer` bundles the complete reduce-side policy — fields `reductions: IrMap`, `noise: IrMap` (the noise table IS inside Reducer), `literal: IrSelf`. So grammar + reducer is the full IR-native surface. Store the *raw* grammar (grammar is ground truth); Earley normalization is a per-grammar compile step, and `compile_tables`/`collapsed_tables` memoise by object identity — so when the new compile path is wired it must memoise `normalize(flavour.grammar)` once per flavour (note this in the flavour docstring now). Accepted consequence of D4: importing `lexic.grammars` (hence `import lexic`) loads the Earley engine at import time — import cost only.

**Unchanged by design (verified):** `get_flavour` / `register_flavour` / `flavour_for_extension` touch only `name`/`extensions`; `base.py`'s `to_grammar()` only calls `get_flavour(...).apply(...)`. Both keep working with zero edits (only `grammars/__init__.py`'s `IrFlavour` import is repointed in Phase 2a).

---

## Phase 1 — the rename (one green landing)

### 1.1 Directory moves (`git mv`, history-preserving)

```bash
git mv src/lexic/parsing src/lexic/parsing_legacy
git mv src/lexic/parsing_2 src/lexic/parsing        # includes README.md
git mv tests/unit/lexic/parsing tests/unit/lexic/parsing_legacy
git mv tests/unit/lexic/parsing_2 tests/unit/lexic/parsing
git mv tests/unit/lexic/parsing/test_init_parsing_2.py tests/unit/lexic/parsing/test_init_parsing.py
```

### 1.2 Reference rewrite — **order is load-bearing**

**Pass 1 (legacy first)** — rewrite old-package references before touching `parsing_2`, or pass 2 corrupts them:
- `lexic.parsing.meta_parser` → `lexic.parsing_legacy.meta_parser`
- `lexic.parsing.lark_builder` → `lexic.parsing_legacy.lark_builder`
- `lexic.parsing.transformer` → `lexic.parsing_legacy.transformer`
- `tests.unit.lexic.parsing.conftest` → `tests.unit.lexic.parsing_legacy.conftest` (in `test_build_transformer.py`, `test_lark_builder.py`)
- Literal *path strings* `"tests/unit/lexic/parsing/test_lark_builder.py"` and `"src/lexic/parsing/lark_builder.py"` at `test_lark_builder.py:75-76` → `parsing_legacy` variants.

Affected: `src/lexic/compile.py:47-48`, `src/lexic/parsing_legacy/lark_builder.py:27`, `zzz_current_work/bench_parsing.py:57`, `tests/unit/lexic/parsing_legacy/*` (self-imports), `tests/unit/lexic/grammars/test_abnf.py:32`, `tests/integration/test_full_round_trip.py:14`, `tests/integration/test_cross_flavour.py:14`. (No bare `from lexic.parsing import …` exists anywhere — verified.)

**Pass 2:** `parsing_2` → `parsing` everywhere: imports, `:mod:`/`:class:` docstring refs, README self-references, the `"parsing_2: …"` error-message prefixes in `engine.py`/`normalize.py`/`tables.py`/`kernel.py`/`forest.py`, and `pyproject.toml:41`'s performance-marker text. No test asserts on a `"parsing_2:"` message string (verified by grep), so the prefix rename is safe. Scope: `src/lexic/parsing/**` (former parsing_2), `src/lexic/grammars/abnf_2.py:77` (`from lexic.parsing_2.reduce` → `from lexic.parsing.reduce`), `tests/unit/lexic/parsing/**`, `tests/unit/lexic/grammars/test_abnf_2.py`, `tests/performance/test_lazy_forest_perf.py`, `zzz_current_work/bench_parsing.py`, `zzz_current_work/spike_iterative_forest.py`.

Leave `zzz_current_work/postleo/*` and `HANDOVER_beat_lark.md` untouched — historical records; renaming inside them falsifies history.

### 1.3 Layering-invariant test updates (`tests/integration/test_layering_invariants.py`)

- `test_ir_does_not_import_grammars_parsing_codegen` — no change needed: the `"from lexic.parsing"` substring grep covers both `lexic.parsing` and `lexic.parsing_legacy`. Docstring update only.
- `test_parsing_imports_grammars_only_via_flavour_abc` — split in two: a **new, stronger** guard that `src/lexic/parsing/` (the engine) imports neither `lexic.grammars` nor `lexic.codegen` (it is ir-only today — pin that), and a `parsing_legacy` variant keeping the existing `lexic.grammars.flavour` allowance (vacuous until Phase 2a makes it real).

### 1.4 Docs in the same landing

- `src/lexic/parsing/README.md` (pass 2 covers tokens; re-read for prose).
- Wiki: `.wiki/lexic/architecture.md` (lines 16, 21, 115, 126, 152 — module table gets both `parsing` = IR-native Earley engine and `parsing_legacy` = Lark path kept until GBNF has an IR grammar), `.wiki/lexic/flavour-system.md:128`, `.wiki/lexic/public-api.md` (CompiledGrammar still Lark-backed — say so), plus a `log.md` entry. (`.wiki/pipeline-map.canvas` has no parsing_2 refs — checked.)

### 1.5 Gate

`tools/auto_fix.sh` → `uv run pytest tests/ -q` (1188 green) → `uv run ruff check src/ tests/` → pylint on touched src files → `grep -rn "parsing_2" src tests pyproject.toml` returns nothing → optional: `uv run python zzz_current_work/bench_parsing.py`.

---

## Phase 2 — flavour rework (three green landings)

### 2a — Move `IrFlavour` to `grammars/flavour.py`; `IrEscape` to `ir/action.py`

1. Create `src/lexic/grammars/flavour.py` with the `IrFlavour` ABC moved **verbatim** (surface split is 2b).
2. Move `IrEscape` into `src/lexic/ir/action.py` (needs only `ir.base`, `ir.escapes`, `exceptions`).
3. Delete `src/lexic/ir/flavour.py`.
4. Repoint importers: `src/lexic/compile.py:45`, `src/lexic/parsing_legacy/meta_parser.py:46` (→ `lexic.grammars.flavour` — the layering-test allowance becomes non-vacuous), `src/lexic/grammars/__init__.py:10`, `src/lexic/grammars/gbnf.py:35`, `src/lexic/grammars/abnf.py:37` (IrEscape now from `lexic.ir.action`), tests `test_gbnf.py:15`, `test_abnf.py:20`, `test_meta_parser.py:15`.
5. Tests (mirror rule): `git mv tests/unit/lexic/ir/test_flavour.py tests/unit/lexic/grammars/test_flavour.py`; then move the IrEscape block (old `test_flavour.py:158-189`) into `tests/unit/lexic/ir/test_action.py`. Port everything.
6. Gate: full suite + lint. The intra-package `from lexic.grammars.flavour import …` inside `abnf.py`/`gbnf.py` during package init is the standard mid-init submodule import — safe, and it's the pre-move shape CLAUDE.md documents.

### 2b — Split the legacy surface into `LarkFlavour`

1. New `src/lexic/parsing_legacy/flavour.py`:
   ```python
   class LarkFlavour(IrFlavour, ABC):
       """Lark-era flavour surface — dies with parsing_legacy."""
       meta_grammar: ClassVar[str]
       @staticmethod @abstractmethod def parse_quantifier(text: str) -> IrQuantifier: ...
       @staticmethod @abstractmethod def parse_charclass(text: str) -> tuple[str, bool]: ...
       @classmethod def normalize_literal(cls, decoded: str) -> IrLiteral | IrAlternation: ...  # identity default
   ```
2. Strip `meta_grammar`, `parse_quantifier`, `parse_charclass`, `normalize_literal` from `IrFlavour` (keeps `name`, `extensions`, `escapes`, `line_comment`, inherited `actions`).
3. `_GbnfFlavour(LarkFlavour)`, `_AbnfFlavour(LarkFlavour)` — bodies unchanged, one import added.
4. `meta_parser.py` types `flavour: LarkFlavour` (same-package import).
5. `compile.py::compile_grammar`: keep `flavour: IrFlavour`; add `isinstance(flavour, LarkFlavour)` guard → `UnsupportedConstructError("flavour {name} has no Lark meta-grammar surface")`. `compile.py` importing `parsing_legacy` is the already-sanctioned runtime seam.
6. Tests: new `tests/unit/lexic/parsing_legacy/test_flavour.py` — receives the legacy-surface tests (abstractness of parse_quantifier/parse_charclass, meta_grammar) moved out of `grammars/test_flavour.py`, which keeps the metadata/emitter/registration tests. Add a guard test for the non-LarkFlavour `compile_grammar` raise.
7. Gate: full suite + lint.

### 2c — IR-native fields + fold `abnf_2.py` into `abnf.py`

1. `grammars/flavour.py`: add to `IrFlavour`
   ```python
   grammar: ClassVar[IrAst]   # the flavour's self-grammar (raw, un-normalised — ground truth)
   reducer: ClassVar[Reducer] # parse-tree → IrAst policy (reductions + noise + literal)
   ```
   with `from lexic.parsing.reduce import Reducer`. Docstring: GBNF transitionally omits both (nothing reads them until its IR grammar lands); future consumers must raise `UnsupportedConstructError` on absence and memoise `normalize(flavour.grammar)` per flavour.
2. Move the entire contents of `abnf_2.py` (`ABNF_GRAMMAR`, `_NON_SEMANTIC`, `ABNF_NOISE`, `_cp0`/`_cp1`/`_dec`, `ABNF_REDUCTIONS`, `ABNF_REDUCER` + docstring content) into `abnf.py`; `git rm src/lexic/grammars/abnf_2.py`. On `_AbnfFlavour`: `grammar: ClassVar[IrAst] = ABNF_GRAMMAR`, `reducer: ClassVar[Reducer] = ABNF_REDUCER`.
3. Repoint remaining `abnf_2` importers: `tests/unit/lexic/parsing/test_normalize.py:28`, `zzz_current_work/bench_parsing.py:46`, and the "forthcoming `abnf_2.py`" prose in `src/lexic/parsing/__init__.py:5` and `README.md` (→ `grammars/abnf.py`).
4. Tests: merge `tests/unit/lexic/grammars/test_abnf_2.py` into `test_abnf.py` under a section banner — **every test ported** (incl. the self-hosting fixpoint suite), imports repointed to `lexic.grammars.abnf`; delete `test_abnf_2.py` only after the port. Add three new tests: `ABNF_FLAVOUR.grammar is ABNF_GRAMMAR`, `ABNF_FLAVOUR.reducer is ABNF_REDUCER`, `not hasattr(GBNF_FLAVOUR, "grammar")` (pins the transitional gap).
5. Gate: full suite + lint + fixpoint tests green in their new home + bench sanity run.

Note: `reduce.py`'s `_PLANS`/`_COLLAPSED` memos key on `id(reducer)`/`id(grammar)` with strong refs — module-level singletons keep this correct after the fold; no change needed.

---

## Test-migration table (complete)

| Old path | New path | How |
|---|---|---|
| `tests/unit/lexic/parsing/__init__.py` | `tests/unit/lexic/parsing_legacy/__init__.py` | git mv (P1) |
| `tests/unit/lexic/parsing/conftest.py` | `tests/unit/lexic/parsing_legacy/conftest.py` | git mv (P1) |
| `tests/unit/lexic/parsing/test_meta_parser.py` | `tests/unit/lexic/parsing_legacy/test_meta_parser.py` | git mv (P1) |
| `tests/unit/lexic/parsing/test_lark_builder.py` | `tests/unit/lexic/parsing_legacy/test_lark_builder.py` | git mv (P1; fix path strings L75-76) |
| `tests/unit/lexic/parsing/transformer/{__init__,test_build_transformer}.py` | `tests/unit/lexic/parsing_legacy/transformer/…` | git mv (P1) |
| `tests/unit/lexic/parsing_2/{__init__,conftest}.py` | `tests/unit/lexic/parsing/…` | git mv (P1) |
| `tests/unit/lexic/parsing_2/test_{chart,engine,forest,item,kernel,normalize,reduce,tables,trampoline}.py` | `tests/unit/lexic/parsing/test_*.py` | git mv (P1) |
| `tests/unit/lexic/parsing_2/test_init_parsing_2.py` | `tests/unit/lexic/parsing/test_init_parsing.py` | git mv + rename (P1, `test_init_<pkg>` rule) |
| `tests/unit/lexic/ir/test_flavour.py` (IrFlavour part) | `tests/unit/lexic/grammars/test_flavour.py` | git mv (2a) |
| `tests/unit/lexic/ir/test_flavour.py:158-189` (IrEscape part) | `tests/unit/lexic/ir/test_action.py` | port (2a) |
| — (new src `parsing_legacy/flavour.py`) | `tests/unit/lexic/parsing_legacy/test_flavour.py` | new file (2b); receives legacy-surface tests from `grammars/test_flavour.py` |
| `tests/unit/lexic/grammars/test_abnf_2.py` | merged into `tests/unit/lexic/grammars/test_abnf.py` | port all, then delete (2c) |

No test is deleted whose target symbol survives. Pre-existing gap (being fixed in parallel by the fixer agent): `parsing_2/lexruns.py` test mirror.

## Final docs sweep (with 2c landing)

- Wiki: `flavour-system.md` rewritten around the new surface (IrFlavour = metadata + emitter actions + grammar + reducer; LarkFlavour = transitional Lark surface in `parsing_legacy`); `architecture.md` arrows updated (`parsing ← grammars` sanctioned; `ir/flavour.py` gone); `log.md` entries for both phases.
- CLAUDE.md is materially stale (still shows `grammars/gbnf/` packages, no `parsing_2`, IrFlavour location wrong). Recommend refreshing §Project layout, §Flavour system, §Layering rules with the 2c landing — offer the user the diff rather than rewriting wholesale unprompted.

## Risks

- **Sed ordering** (Phase 1 pass 1 before pass 2) — the easiest way to corrupt the rename; verify with the `grep -rn "parsing_2"` gate.
- **Concurrent lint agent** in `parsing_2/` — sequence Phase 1 after their landing.
- **Import-time weight**: after 2c, `import lexic` loads the Earley engine (`grammars` → `abnf.py` → `parsing.reduce`). Accepted consequence of "the flavour carries its grammar"; call it out to the user.
