# T1 + T2 — implementation report

Tasks T1 (the public-seam family, ask #4) and T2 (`generate` refuses with
words, ask #7). T3 not started.

**Gates: `tools/run_checks.sh` EXIT=0 · `pytest tests/ -q -n auto` 3835
passed, 8 skipped · `tools/run_examples.sh` EXIT=0 ·
`tools/check_generated.py` EXIT=0.**

**Test count delta: +10** (3825 → 3835). `tests/unit/lexic/test_generate.py`
22 → 28; new `tests/integration/lexic/invariants/test_public_api_drift.py`
with 4.

---

## T1 — the public-seam family

### What changed

| File | Change |
|---|---|
| `src/lexic/compile/__init__.py` | `from lexic.compile.payload.export import export_value`; six names into `__all__`; module docstring's stale `lexic.compile.passes` path corrected to `lexic.compile.pipeline.passes` and the root named as the only route to them |
| `.wiki/lexic/public-api.md` | Five headings re-homed to `compile/__init__.py`; implementing module moved into each body; a new "The seam is this page" paragraph stating the rule and naming the gate |
| `.wiki/lexic/generated-modules.md` | The `export_value` line no longer names `compile/payload/` as its home |
| `.wiki/log.md` | Entry for both tasks |
| `CLAUDE.md` | `invariants/` annotation grows "public-api seam" |
| `tests/integration/lexic/invariants/test_public_api_drift.py` | New — the seam invariant, 4 tests |

No `src/lexic/` module was added or removed, so the `CLAUDE.md` layout block
needed no file line; `test_doc_drift.py` stays green.

### The audit — every reachable-but-unlisted attribute, ruled

Before: 42 attributes reachable on `lexic.compile` and absent from `__all__`.
After: 36, every one ruled internal below.

**Promoted (6).**

| Symbol | Why |
|---|---|
| `export_value` | The ask's origin: documented as public API, absent from the module entirely, deep import the only route (m1/m2). |
| `compile_ast` | Its own module docstring calls it "the IR-born twin of `compile_text`" and the wiki gives it a full entry-point section — a primary entry that was never listed. |
| `build_codegen_grammar` | Wiki-documented with a signature block; the fused codegen grammar is what every generated class's `__grammar__` is computed against, so a caller inspecting an artefact needs it. |
| `compute_binding` | Wiki-documented with a signature block; the binding view is the artefact's own vocabulary (`templating.py` and `transpile.py` both read it). |
| `synthesize` | Wiki-documented with a signature block; the third of the three pipeline entries the page already treats as public. |
| `RuleBinding` | `compute_binding` returns `list[RuleBinding]`; a caller cannot type or destructure the result without it. Promoted with its function, not on its own. |

**Ruled internal — stdlib / typing imports (6).** `Hashable`, `Mapping`,
`NamedTuple`, `Path`, `Sequence`, `annotations`. Import machinery, not
surface.

**Ruled internal — symbols whose own package already exports them (26).**
`GrammarModel`; `UnsupportedConstructError`; `IrAlphabet`, `IrAst`,
`IrFlavour`, `IrItem`, `IrLambda`, `IrMap`, `IrNone`, `IrRule`, `IrRuleRef`,
`IrSelf`, `IrSeq`, `IrTokenizer`, `IrTuple`, `canonicalize`, `concretize`,
`fold_name`, `refs_in_order`, `rule_closure`; `get_flavour`,
`flavour_for_extension`; `FastCtor`, `FieldFold`, `ModelBody`, `ModelFold`.
Verified: every one is in `lexic.ir.__all__` / `lexic.grammars.__all__` /
`lexic.parsing.__all__` / is `lexic.model`'s or `lexic.exceptions`' own name.
Re-exporting them from `lexic.compile` would be a second import route for one
symbol — "one way per task" — and none of them is compile's to publish.

**Ruled internal — compile-package internals (4).**

- `encoding_registry` / `segmentation_tokenizer` — the vocabulary
  resolution `_assemble_core` runs; `Vocabulary(tokenizer, registry)` is the
  caller-facing form of exactly this composition, and it is already exported.
  Used nowhere outside `compile/__init__.py`.
- `check_supplied_class` / `field_kwargs` — the supplied-class contract
  `_fold_config` enforces for the open binding table; parameters of an
  internal seam, not an entry point.

### Decisions taken inside the spec's latitude

1. **Five headings re-homed, not one.** The spec named
   `public-api.md:79` (`export_value`). Running the invariant surfaced the
   same defect on `transpile` (`compile/transpile.py`),
   `build_codegen_grammar`, `compute_binding` and `synthesize` — all four
   already public, all four documented with a submodule as their home. Fixing
   one and leaving four would have left the gate red or the rule unstated, so
   the heading tail is now uniformly the import route and the implementing
   module moved one line down into the body. `transpile` needed no `__all__`
   change; it was only the heading.
2. **The invariant is a new file, not an extension of `test_doc_drift.py`.**
   That file's docstring and parser are specific to CLAUDE.md's layout block;
   a wiki-vs-`__all__` check shares the family (`invariants/`, "the repo's own
   rules") but not the parser. Four tests: the parser's own guard against a
   vacuous zero, the `__all__` membership half, a stale-`__all__` check, and
   the heading-names-the-root half.
3. **Import site.** `from lexic.compile.payload.export import export_value`,
   matching the file's existing style (`from lexic.compile.module.export
   import export_module`) rather than going through `payload/__init__.py`.
   No cycle; `payload/reader.py`'s zero-lexic-imports property is untouched
   and its test still passes.
4. **One stale path corrected in passing.** The `compile/__init__.py`
   docstring named `lexic.compile.passes` / `.binding` / `.synthesis`; the
   modules have lived under `pipeline/` for some time. Corrected in the same
   sentence that now states the root is the only route.

---

## T2 — `generate` refuses with words

### What changed

`src/lexic/generate.py`:

- `_Generator.run` raises `UnsupportedConstructError` for an undefined rule
  name, naming the rule and what the grammar does define — the shape
  `transpile.py`'s own refusals already use ("names no rule … it defines
  {sorted}").
- `_Generator.alternation` raises for an arm-less alternation, taking a new
  `where: str` parameter so the refusal names its subject. `run` passes
  `f"rule {name!r}"`; `_gen_group` passes `"an inline group"` — an inline
  group has no rule name to give, and inventing one would be worse than
  saying what it is.
- Module docstring, `run`/`alternation`/`generate` docstrings updated;
  `generate`'s `:returns:` no longer promises `""` for an unknown rule.

`UnsupportedConstructError` is the class the error vocabulary assigns: the
wiki's table lists "atom dispatch tables (unknown atom type)" under it, and
the module's existing raising default (`IrRaise` on `_GEN_ATOM`) already
raises it for the same class of defect one step away. No competing candidate
in `.wiki/lexic/error-vocabulary.md`.

No signature change to `generate()`; the injected-`rng` determinism is
untouched (`test_generate_deterministic_with_same_seed` unchanged and green).

### Tests

Six added to `tests/unit/lexic/test_generate.py`, none removed or weakened:

- undefined rule raises; its message names the rule AND the grammar's rules;
- a **dangling ref** raises from inside an expansion (the case that mattered
  — a top-level bad name is a caller error, a dangling ref is a grammar
  defect the old code swallowed mid-generation);
- an arm-less rule body raises with the rule named;
- an arm-less **inline group** raises (`match="inline group"`);
- **the boundary**: a rule with ONE EMPTY arm still yields `""`. This is the
  test that keeps the fix from over-reaching — the empty string is a real
  derivation and must stay one.

The existing 22 pass unchanged. None of them relied on the `""` fallback, so
nothing needed porting.

---

## Things that argued against the spec, or are worth the reviewer's eye

1. **`max_depth` is threaded but never read.** `generate.py` decrements
   `max_depth` on each ref expansion (`_gen_ruleref:87`) and no code path ever
   tests it — `grep -n max_depth src/lexic/generate.py` returns only the
   docstrings, the field, the decrement and the constructor. So
   `max_depth` currently bounds nothing, and
   `test_generate_max_depth_zero_picks_non_recursive_arm` passes because
   `arithmetic.gbnf`'s `term` happens to terminate, not because a budget was
   enforced. **Not fixed** — out of T2's stated scope, and a real fix changes
   generation output (arm filtering at the budget), which is a behaviour
   change needing its own gate and its own ruling. Recommend it as a small
   named ask beside #7; it is the same class of defect (a stated guarantee
   the code does not make).

2. **`tools/auto_fix.sh` reformats `zzz_current_work/`.** It rewrote 45
   tracked files under `zzz_current_work/260807-opsis-radical/` on its first
   run here. I restored them (`git checkout -- zzz_current_work/`) and the
   tree is clean, but any implementer running `auto_fix.sh` under the "don't
   touch zzz" instruction will hit this every time. Worth either excluding
   the directory from the tool or doing the planned untrack sooner.

3. **`Reducer` and `parse_reduced` are `lexic.parsing` names sitting in
   `lexic.compile.__all__`.** They predate this task and are therefore
   outside the audit's scope (which covers symbols *absent* from `__all__`),
   but they are the mirror image of the rule I applied to 26 other
   re-exports: two import routes for one symbol. Removing a name from a
   public `__all__` is a subtraction I did not make unasked. Flagging for a
   ruling.

4. **The seam invariant is one-directional by design.** It gates "documented
   ⇒ exported", not "exported ⇒ documented". The reverse would demand a wiki
   section for every one of the 43 names now in `__all__` (including
   `KEEP`, `Is`, `Flat`, `Split`…), which the page deliberately covers by
   topic instead. Stated in the test's docstring so the omission is not
   mistaken for an oversight.

---

## Gate output tail

```
sanity: OK
All checks passed!
359 files already formatted
lint: OK
0 errors, 0 warnings, 0 informations
typecheck: OK
Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)
pylint: OK
EXIT=0
```

```
3835 passed, 8 skipped, 3 warnings in 34.02s
```

```
exported 49 modules
CLEAN: 0 pyright errors, 0 unaccepted pylint findings
```

## Working tree

```
 M .wiki/lexic/generated-modules.md
 M .wiki/lexic/public-api.md
 M .wiki/log.md
 M CLAUDE.md
 M src/lexic/compile/__init__.py
 M src/lexic/generate.py
 M tests/unit/lexic/test_generate.py
?? tests/integration/lexic/invariants/test_public_api_drift.py
```

No commit made (reviewer commits). No stray files.
