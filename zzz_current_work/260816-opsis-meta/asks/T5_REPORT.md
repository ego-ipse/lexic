# T5 — the compile moments (with the 4b census amendment)

Both landed. The amendment came first, as ordered; T5 follows it.

**Gates: `tools/run_checks.sh` EXIT=0 · `pytest tests/ -q -n auto` 4022 passed,
8 skipped · property under `tools/guarded.sh 8G 600` EXIT=0 (20 passed) ·
`tools/run_examples.sh` EXIT=0 · `tools/check_generated.py` CLEAN ·
`space_3/gate.py` 24 gestures · 13 keys · 0 failures.**

**Test count delta: +16** (4006 → 4022): +3 for the amendment, +13 for T5 (13
new moments gates and one rebind gate, less the composition case that moved
out of `passes_cases.py` with its symbol).

---

## The 4b amendment — the census opens the tables

**The definition is now: a node's children are the node-valued parts it
CARRIES — the elements of its field tuple, and, for the map family (whose
payload is a table rather than a tuple), its entries, each value under its own
key.** Still one definition, stated in the module docstring, and still
checkable through the public `field_children`.

**The module moved: `ir/spine/identity.py` → `ir/identity.py`.** This is
forced, not preference. The wider definition must know `IrMapping`, which
lives in `ir/action/` — and `ir/spine/README.md` states, as an invariant of
that folder, "Nothing here imports anything above it". A census that imported
`action/` from inside `spine/` would falsify the substrate's own rule, and a
lazy import to dodge it is exactly what the layering rule forbids. `ir/`'s top
level is where a cross-group reader belongs: `flavour.py` (which imports
`action/`, `grammar/`, `spine/` and `text/`) is the precedent. CLAUDE.md, the
two READMEs, the façade's three lists, the notation module list and the test
mirror all moved with it.

**What it bought, measured:**

| censused | before | after |
|---|---|---|
| `GBNF_FLAVOUR.reducer` | 5 nodes, 2 of them opaque tables, 0 refusals | **272 nodes**, 10 shared, 0 refusals |
| `ABNF_FLAVOUR.reducer` | 5 nodes | **843 nodes**, 11 shared |
| `compile_from_path(json.gbnf).fold.bodies` | 1 node, 0 refusals | **115 nodes, 35 refusals** |

The third row is the one that matters and it is now a gate. A compiled
grammar's fold files one `IrLambda(<class>)` per built rule; those ARE the
refusal boundary, and under the tuple-only definition the whole table censused
as a single childless node and the boundary read as an empty set on every real
artefact. The reviewer's call was right.

**One honest correction to the order.** A flavour reducer's census still
reports **zero** refusals — not because the walk cannot reach into it (it now
reaches all 272 nodes, verified against a permissive walk that also follows
lists) but because a flavour's bodies are pure IR algebra by the repo's own
rule: no `def`s in grammar reductions, so there is no `IrLambda` in a reducer
to find. The reducer gate therefore asserts the ANATOMY (>100 nodes, sharing
present) and states the zero in its docstring; the non-vacuous refusal gate
runs against the compiled fold, where the callables actually live. Reporting a
zero as a zero is the point of the boundary.

The pre-existing-flake fix is untouched, as instructed.

---

## T5 — one retaining product, and the pipeline runs through it

`src/lexic/compile/pipeline/moments.py`:

```python
GRAMMAR_MOMENTS = ("canonical", "grouped", "armed", "relaxed", "resolved")
GrammarMoments(canonical, grouped, armed, relaxed, resolved)   # five IrAst states
CompileMoments(grammar, binding, classes)                      # + binding view + classes
```

- **`_assemble_core` routes THROUGH it**, as M6 demanded: it builds one
  `CompileMoments.of(ast, resolved, identity)` and reads the artefact out of
  it. There is no route to a compiled grammar that skips a moment or computes
  one twice.
- **One composition.** `GrammarMoments.of` is the only place in `src/` where
  the three passes are chained (grep-verified). `build_codegen_grammar` MOVED
  from `passes.py` to `moments.py` and is now `GrammarMoments.of(ast).relaxed`
  — the fused form reads the retained one, so they cannot disagree. `passes.py`
  composes nothing and says so.
- **Retention costs nothing.** The moments are the locals the pipeline already
  computed; keeping them is a tuple of references. Nothing is recomputed and
  nothing re-runs — which is why the moments ride on the artefact
  (`CompiledGrammar.moments`) rather than behind a second entry that would
  re-run the pipeline to answer.

### The finding that changed the artefact's shape

Putting `moments` on `CompiledGrammar` took it to eight attributes, and pylint
said so (`R0902`). The linter was pointing at something real: `classes` and
`codegen_grammar` were now stored **twice** — once as fields, once inside the
moments. So both became properties reading `moments.classes` and
`moments.grammar.resolved`. Reads are unchanged everywhere
(`compiled.classes`, `compiled.codegen_grammar` still work, all 4022 tests
pass untouched); the two construction sites lost two arguments; and a drift
surface — an artefact whose `codegen_grammar` disagrees with its own moments —
became unrepresentable. No suppression was used or needed.

### `bind()` now demonstrates its own argument

`CompiledGrammar.bind` claims classes, binding and fold are invariant under
which vocabulary is bound. With moments retained it can be checked rather than
asserted in prose: rebinding rebuilds only the LAST grammar moment, and the
gate pins `before[:-1] == after[:-1]`, `relaxed is relaxed`, `binding is
binding`, `classes is classes`, `resolved != resolved`.

### A no-op moment is a first-class fact

`GrammarMoments.no_ops()` names the stages that RAN and changed nothing.
`canonical` is never named — it is the state the pipeline was handed, not a
stage's product. Measured over the whole GBNF corpus, and matching the
adversarial probe's numbers exactly:

```
arithmetic.gbnf  ('resolved',)                              non_semantic=['ws']
c.gbnf           ('relaxed', 'resolved')                    non_semantic=['ws']
chess.gbnf       ('armed', 'relaxed', 'resolved')           non_semantic=[]
japanese.gbnf    ('armed', 'relaxed', 'resolved')           non_semantic=[]
json.gbnf        ('resolved',)                              non_semantic=['ws']
json_arr.gbnf    ('resolved',)                              non_semantic=['ws']
json_ws.gbnf     ('resolved',)                              non_semantic=['ws']
list.gbnf        ('grouped', 'armed', 'relaxed', 'resolved') non_semantic=[]
think.gbnf       ('grouped', 'armed', 'relaxed', 'resolved') non_semantic=[]
vyx.gbnf         ('relaxed', 'resolved')                    non_semantic=[]
```

The probe's three are all gated by name: `c.gbnf` (declares `@non-semantic ws`
and relaxes nothing — its `ws` is not nullable, and relaxing there would widen
the language), `chess.gbnf` (one pass of three does anything), `vyx.gbnf`
(relax idles). Two more are gated because they are stronger cases the probe
did not name: `list.gbnf`/`think.gbnf` pass through the WHOLE pipeline
untouched — every stage a no-op — and `resolved` idles on every grammar with
no vocabulary bound, which is the conditional moment drawn honestly rather
than omitted.

### Decisions inside the latitude

1. **A record, not a list of `(name, product)` pairs.** The moments are
   heterogeneous (five grammars, a binding view, a class table), and a
   homogeneous sequence would have cost either an `object` product type (which
   `docs/STYLE.md` forbids outright) or a union every consumer re-narrows. As
   a record the tuple order IS the pipeline order, so two adjacent stages are
   `self[i]`/`self[i+1]` — which is what the compilation room's diff facet
   needs — and `GRAMMAR_MOMENTS` names them without a consumer re-deriving the
   sequence.
2. **Two records rather than one.** `build_codegen_grammar` must not
   synthesize classes, so the grammar half has to stand alone;
   `CompileMoments` holds a `GrammarMoments` rather than flattening it, which
   keeps one vocabulary and avoids an all-defaulted record with holes.
3. **`concretize` stays a moment even when no vocabulary is bound** — then
   `resolved` IS `relaxed`, and `no_ops()` says `resolved`. Omitting the field
   when unused would have made "did concretize run?" unanswerable from the
   product.
4. **Adding a pass means adding a field.** Deliberate: the moments are a named
   contract, and a new stage that did not show up in the product would be the
   drift this task exists to close.

### The one test that moved rather than being ported in place

`case_build_codegen_grammar_composes_all_three_passes` lived in
`passes_cases.py` and called `passes.build_codegen_grammar` through the
module-binding indirection. Its symbol moved to `moments.py`, so the case
moved to `tests/unit/lexic/compile/pipeline/test_moments.py` with its
assertions verbatim. Its grammar fixture is now `three_pass_ast()` in
`passes_cases.py`, imported by both files — pylint's duplicate-code found the
copy I first wrote, and sharing the builder is the right answer rather than
the linter-appeasing one.

## What changed

| File | Change |
|---|---|
| `src/lexic/ir/identity.py` | MOVED from `ir/spine/`; child definition widened to map entries |
| `src/lexic/compile/pipeline/moments.py` | NEW — `GRAMMAR_MOMENTS`, `GrammarMoments`, `CompileMoments`, `build_codegen_grammar` |
| `src/lexic/compile/pipeline/passes.py` | lost the fused function; docstring says it composes nothing |
| `src/lexic/compile/__init__.py` | `_assemble_core` routes through the product; the seam family gains three names; pipeline diagram redrawn |
| `src/lexic/compile/artifact.py` | `moments` field; `classes`/`codegen_grammar` became reads of it; `bind` moves one moment |
| `src/lexic/ir/__init__.py`, `compile/notation/parse.py` | the identity module's new home |
| `CLAUDE.md`, `ir/spine/README.md` | the two module lines |
| `.wiki/lexic/ir-shapes.md` | the amended child definition and what it opened |
| `.wiki/lexic/public-api.md` | the moments entry; `build_codegen_grammar`'s home; the artefact's field table |
| `.wiki/log.md` | two entries |
| `tests/unit/lexic/ir/test_identity.py` | MOVED; map-entry gates, the compiled-fold refusal gate, the reducer-anatomy gate |
| `tests/unit/lexic/compile/pipeline/test_moments.py` | NEW — 13 |
| `tests/unit/lexic/compile/pipeline/passes_cases.py` | the shared fixture; the composition case moved out |
| `tests/integration/lexic/tokens/test_late_binding.py` | the rebind-moves-one-moment gate |
| eleven test modules | `build_codegen_grammar`'s import path |

No suppressions, no `eval`, no `pyproject.toml`, no commit.

## Process note

`tools/auto_fix.sh` reformatted tracked `zzz_current_work/` files again (twice
this session). Restored both times by saving the pre-existing zzz diff and
re-applying it — a bare `git checkout -- zzz_current_work` would destroy T3's
uncommitted `space_3/praxis/reading.py` swap, which is still the only zzz
modification in the tree.

## Gate output tail

```
sanity: OK · lint: OK · typecheck: OK · pylint: OK   →  EXIT=0
4022 passed, 8 skipped, 3 warnings in 32.84s
guarded property  →  20 passed, EXIT=0
run_examples.sh   →  EXIT=0
check_generated   →  exported 49 modules · CLEAN
space_3/gate.py   →  24 gestures · 13 keys · 0 failures
```

T6 not started (holding, as instructed).
