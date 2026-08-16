# T3 — addressed emission and provenance

Stages **3a, 3b and 3e landed**. **3c and 3d did not**, and the reason is one
finding common to both, argued below with evidence: the engine's fold and
transform walks are *position-free* and *share-splicing* by design, so neither
"carries what it computed" in the sense the stage assumes. Nothing was
searched, guessed, or forked to get around it.

**Gates: `tools/run_checks.sh` EXIT=0 · `pytest tests/ -q -n auto` 3914
passed, 8 skipped · property suite under `tools/guarded.sh 8G 600` EXIT=0 ·
`tools/run_examples.sh` EXIT=0 · `tools/check_generated.py` EXIT=0 ·
`space_3/gate.py` 24 gestures · 13 keys · 0 failures.**

**Test count delta: +74** (3840 → 3914): 19 unit (`ir/text/test_spans.py`),
49 corpus (`roundtrip/test_addressed_emission.py`), 6 property
(`property/lexic/test_addressed_emission.py`).

---

## 3a — the record vocabulary (`src/lexic/ir/text/spans.py`)

Eight records, all spine, all notation-spellable:

| Record | What it is |
|---|---|
| `IrStep(field, slot)` | one address step — the parent's name for a part, and its ordinal in the parent's emission |
| `IrAddress(IrSeq[IrStep])` | the path from the root; `.child(field, slot)` is the only builder |
| `IrSpan(start, end)` | half-open, code units; `.of(text)` slices it back |
| `IrExtent(address, span)` | the emit-side correspondence |
| `IrExtents(IrSeq[IrExtent])` | one emission's, document order |
| `IrEmission(text, extents)` | what `emit_addressed()` returns |
| `IrOrigin(address, source)` | the transform-side correspondence |
| `IrOrigins(IrSeq[IrOrigin])` | its container |

Decisions taken inside the spec's latitude:

1. **`slot`, not `index`.** The field started as `index` and pyright caught it:
   `IrStep` is a tuple, and `index` overrides `tuple.index` with an
   incompatible type. Renamed rather than suppressed — and the repo already
   treats `index` as a shadowing name (it is in `RESERVED_FIELD_NAMES` for
   exactly this reason).
2. **Both halves on every step, not "name where one exists, index where it
   does not"** (the spec's wording). A repeated field's elements all carry the
   SAME field name, so a name-or-index scheme cannot tell them apart; the slot
   is always present and always identifying, and the field name is what the
   grammar calls it. This is the shape B1 needs.
3. **`IrEmission` and the two containers exist** — beyond the "five records"
   brief. `IrEmission` because text and spans are only meaningful together
   (spans measured against one emission mean nothing against another
   rendering), and the containers because a bare `IrSeq` loses the element
   bound and reprs as `IrSeq(...)`. `SpanLevel(IrSeq[SpanEntry])` is the
   in-repo precedent for naming a sequence product.
4. **`ir/text/spans.py` (D2) survived contact.** No argument against it: a
   span is a fact about a document's spelling, and `escapes`/`layout` are
   already the "spelling" half of that package rather than the "characters"
   half. `CLAUDE.md`'s annotation grew D2's word ("…— and where"), and the
   package README says why the last three modules sit together.
5. **Registered in the notation vocabulary** (`compile/notation/parse.py`'s
   `_IR_MODULES`), so the repr-is-codegen pin is `load_ir(repr(x)) == x` —
   the repo's own no-exec boundary — rather than `eval`, which is a hard
   constraint. The drift-pin test's module list gained `spans` too.

## 3b — the addressed emission (`GrammarModel.emit_addressed` / `.occurrence`)

`emit_addressed() -> IrEmission` drives the SAME `emit_parts` stream `to_text`
consumes, accumulating offsets and assigning addresses top-down; every part
`emit_parts` yields gets an extent, and a part that expands (a sub-model, a
repeated field's tuple) gets one covering all of it.

`occurrence(address)` is the inverse, and it earns its place: the spec's own
gate (i) — "slicing `to_text()` by its span yields exactly that occurrence's
own `to_text()`" — presupposes resolving an address to an occurrence, and the
alternative was to put that walk in the test, which the "no functionality in
tests" rule forbids. Both directions run off one `_sub_parts` definition, so
the address contract cannot drift from itself.

Both names joined `RESERVED_FIELD_NAMES` (a public `GrammarModel` method is a
reserved field name — the field-naming cost this ask pays).

**Share-safety, concretely.** Nothing on this path memoises on `id`. The
corpus gates include `{"a": 1, "b": 1}` under `json.gbnf`, where one `Ws`
object is reached seven times and one `QuotationMark` twice; the fixture's
sharing is itself asserted (`test_the_b1_fixture_really_does_share_nodes`) so
the sharing gates cannot quietly stop testing anything.

**The M3 order fact is honoured by construction**: steps come from
`emit_parts`' own order and its own tags, never from `_fields`. No independent
derivation of order exists to disagree.

**Gates.** (i) fidelity, (ii) the B1 fixture plus `[1, 1]`'s equal siblings,
(iii) leaf extents tile the emitted text with no gap or overlap, (iv) the
property suite over six corpus grammars under `guarded.sh`. Plus two the spec
did not name and I would not ship without: the addressed text IS `to_text()`
over the whole corpus, and spans nest with the addresses.

### The one design argument worth the reviewer's eye

`to_text()` was left as its own loop rather than made a caller of the
addressed walk. Two readers of one `emit_parts` stream is not a second
emission path (the text has ONE definition), but it IS two loops that could
drift. The alternative — `to_text = self.emit_addressed().text` — makes the
hot path (every round-trip gate, `Transpiler.run`'s fidelity check,
`check_generated`'s 49 modules) build addresses nobody asked for.

I chose the two loops plus a corpus gate pinning their texts to each other,
and said so in the module comment. If the reviewer prefers one loop, the
change is three lines and the gate already exists; it is a performance
judgement, not a correctness one.

## 3e — the reference consumer (byte-identity verdict)

**IDENTICAL: 44 cases, 840 spans, all five fields.**

`space_3/praxis/reading.py`'s `fold()` — a hand-rolled second traversal
accumulating `at += len(text)` — now projects `emit_addressed()` into the five
fields the rooms read (`start`, `end`, `depth`, `rule`, `field`). The old
derivation was snapshotted first
(`probes/adv_space3_spans.py --save`, 44 documents: 7 ground-truth grammars ×
6 seeds plus space_3's own two fixtures) and the new one compared against it
(`--check`). Every span identical in every field.

`space_3/gate.py` still exits 0 with the same 24 gestures, 13 keys, 0
failures. Its output differs from the baseline only in the ordering of four
slider lines, which is pre-existing run-to-run nondeterminism in that gate (a
third run reproduced the *baseline* order under the new code); the outputs are
identical as sets.

Two projection rules the swap had to state, both consequences of
`emit_addressed` addressing more than models: `depth` counts MODEL ancestors
(a repeated field's tuple layer is not a level), and `field` is the nearest
non-empty name on the way up (a tuple's elements are emitted under the tuple's
field name). Both are in the new docstring.

---

## 3c and 3d — not landed, and why

Both stages assume a product dropped something it held. **Neither walk ever
held it.** This is the same root fact twice, and it is a genuine argument
against the stages as written rather than a difficulty in doing them.

### 3c — the fold is position-free

`ParseTree` is `(symbol, kids)` — `parsing/earley/kernel/forest/forest.py:77`.
No offsets, anywhere. `_subtree_text(node)` (`parsing/fold.py:251`)
*reconstructs* a slot's text by walking its leaves and concatenating them, and
`ModelFold.apply` folds bottom-up over an `id`-keyed results dict with no
offset in scope. So `SpanEntry`'s "raw span" text is not a span the fold
recorded and dropped — it is a string the fold rebuilt from leaves. There is
nothing to carry.

The spec anticipated this ("if the current fold genuinely does not hold them,
extend the fold to carry them"). What that costs, honestly:

- **Both engines, not one.** The ParseTree fold is the Earley path; the PDA's
  fused runtime (`pda/runtime/build.py`) never builds a ParseTree at all. A
  ParseTree-only implementation would produce offsets on one route and not the
  other — a product that silently differs by engine, which is worse than not
  having it.
- **The paid loop, under a performance gate.** Threading a start offset means
  every sequence node needs its preceding kids' lengths; done naively that is
  `_subtree_text` per kid and quadratic. Doable in one pass with a
  bottom-up length memo, but it is surgery on `tests/performance/`-gated code.
- **And it changes what a field IS.** `text` mode currently yields a `str`,
  which is the generated class's field type. Offsets have to ride *beside* the
  model rather than inside it — which is 3b's product shape again, on the
  parse side: `parse_model` returning the model, and a sibling product
  returning the model AND its source-side extents.

That last point is the real finding: **the parse side wants the same product
3b just built, not a wider `SpanEntry`.** `SpanEntry` carrying two ints is the
symptom; a parse-side addressed product is the ask. It needs the same B1
share-safety analysis (the fold's `results` dict is `id`-keyed, so the same
splice hazard exists there), and it is a task of 3b's size, not a stage of it.

**Recommendation:** re-scope 3c as "the parse-side addressed product", ranked
beside 3b rather than under it, and let `SpanEntry` take its offsets from that
when it exists. I did not implement a partial version, because the only
partial available is engine-dependent.

### 3d — `IrBottomUp` knows objects, not occurrences

Measured on the shipped `ex16` json→yaml transform (probe run, this session):

```
source model occurrences: 178   distinct objects: 71   max reuse: 27
product model occurrences:  33   distinct objects: 33   max reuse:  1
```

The source has 178 occurrences over 71 objects. `IrBottomUp` folds each object
**once** and splices the result everywhere it appeared
(`ir/action/walk.py:161`, and its `done[id(node)]` memo at `:217`). So for the
one source object reached 27 times, the walk computed one answer — it does not
know, and cannot know, which of the 27 occurrences a given built node came
from. "Keep what you computed" therefore yields a source-OBJECT → built-OBJECT
map, and `IrOrigin(address, address)` is an occurrence-level record. Filling
its `source` field would mean picking one of 27 addresses: a silent pick, which
doctrine forbids, or a set, which is not "where it came from".

The honest fix is a non-splicing driver for the transform — which changes
transpile's cost (re-folding a 27×-shared subtree 27 times) and is a design
decision with a real trade-off, not an implementation detail. That deserves its
own ruling.

Note `IrOrigin`/`IrOrigins` shipped anyway (3a): the vocabulary is right, and
having it costs nothing while the producer is settled. Nothing in the tree
constructs one yet, and no test pretends otherwise.

---

## D1 — the `layout.py` wide-glyph investigation (the spec asked for this)

**Finding: the discrepancy is real, does not bite, and `len` is the correct
measure for `layout.py`'s job. Nothing changed.**

The discrepancy reproduces trivially — `Sheet.write` does
`self.col += len(text)` (`ir/text/layout.py:61-67`), so:

```
IrGroup(IrCat(IrText("あ"*30), IrLine(" "), IrText("あ"*30)))  rendered at width 88
  → one line:  chars=61  columns=121   fits-88-by-chars=True  by-columns=False
```

It does not bite the corpus. Emitting every ground-truth grammar at width 88:
`japanese.gbnf`'s widest line is 51 chars / 51 columns, `json.gbnf` 70/70,
`c.gbnf` 86/86; **zero** lines exceed 88 by either measure. `japanese.gbnf`
does carry 8 wide glyphs in its emitted form (char-class bounds like
`hiragana ::= [ぁ-ゟ]`), so the case is exercised — those lines are just short.

The substantive point: **`layout.py`'s width budget serves linters.** What it
renders is emitted grammar text and generated `.py` twins, and those are gated
by `tools/check_generated.py` running ruff and pylint under DEFAULT configs —
which count line length in CHARACTERS. A column-aware measure would put
lexic's emitter at odds with the gate on its own output. So M10's "discrepancy"
is two correct measures for two different jobs:

- **code units** for anything that must slice a string back (spans, D1) or
  satisfy a character-counting linter (`layout.py`);
- **terminal columns** for whatever draws on a terminal — which is the
  consumer's own projection, exactly as `space_3/praxis/reading.py:331`'s
  `columns()` does it today.

Both are now written down (`ir/text/spans.py`'s module docstring and the
`ir-shapes` wiki page) rather than left to be rediscovered. **I recommend no
change to `layout.py`.**

---

## What changed

| File | Change |
|---|---|
| `src/lexic/ir/text/spans.py` | NEW — the eight records |
| `src/lexic/ir/__init__.py` | the family in the lazy façade (TYPE_CHECKING block, `__all__`, `_HOMES`) |
| `src/lexic/model.py` | `emit_addressed`, `occurrence`, the `_Part`/`_Shut`/`_emitted`/`_sub_parts`/`_open` walk leaves |
| `src/lexic/compile/notation/parse.py` | `spans` in `_IR_MODULES` — the family is spellable |
| `src/lexic/compile/pipeline/naming.py` | `emit_addressed` + `occurrence` reserved |
| `src/lexic/ir/text/README.md`, `CLAUDE.md` | the module's line and D2's annotation word |
| `.wiki/lexic/ir-shapes.md` | the family, the four rules, the two measures |
| `.wiki/lexic/public-api.md` | the two `GrammarModel` methods |
| `.wiki/log.md` | the entry |
| `tests/addressed_helpers.py` | NEW — shared reads (the two suites needed the same two, and pylint's duplicate-code found the copy) |
| `tests/unit/lexic/ir/text/test_spans.py` | NEW — 19 |
| `tests/integration/lexic/roundtrip/test_addressed_emission.py` | NEW — 49 |
| `tests/property/lexic/test_addressed_emission.py` | NEW — 6 |
| `tests/unit/lexic/compile/notation/test_parse.py` | `ir_spans` in the drift pin's module list |
| `zzz_current_work/.../space_3/praxis/reading.py` | 3e — the swap (not committed; validation only) |

No suppressions, no `eval`, no `pyproject.toml`.

## Two process notes

1. **`tools/auto_fix.sh` reformats tracked `zzz_current_work/` files** — the
   same finding as T1/T2, hit three more times this session. I restored the
   churn each time (keeping only the authorized `space_3/praxis/reading.py`
   edit), but every `auto_fix` run needs that cleanup by hand until the
   planned untrack lands.
2. The corpus gate takes its grammar list from `tests.paths.GBNF_GRAMMARS`
   minus three named exclusions rather than restating it — pylint's
   duplicate-code caught the restatement, and deriving it is better anyway.

## Gate output tail

```
sanity: OK
All checks passed!
364 files already formatted
lint: OK
0 errors, 0 warnings, 0 informations
typecheck: OK
Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)
pylint: OK
EXIT=0
```

```
3914 passed, 8 skipped, 3 warnings in 35.29s
tools/guarded.sh 8G 600 -- pytest tests/property/  →  17 passed, EXIT=0
tools/run_examples.sh                              →  EXIT=0
tools/check_generated.py  exported 49 modules      →  CLEAN, EXIT=0
space_3/gate.py           24 gestures · 13 keys    →  0 failures
adv_space3_spans.py --check  →  IDENTICAL: 44 cases, 840 spans, all five fields
```

No commit made (reviewer commits). Working tree carries only the files above.

---

# T3 continued — 3c and 3d under the reviewer's re-scopes

**Both re-scopes ACCEPTED, both stages landed.** The evidence that decided it
is below; neither needed a contest.

**Gates: `tools/run_checks.sh` EXIT=0 · `pytest tests/ -q -n auto` 3950
passed, 8 skipped · property under `tools/guarded.sh 8G 600` EXIT=0 ·
`run_examples.sh` EXIT=0 · `check_generated.py` CLEAN · `space_3/gate.py` 24
gestures · 13 keys · 0 failures · 3e byte-identity still IDENTICAL (44 cases,
840 spans).**

**Test count delta for this half: +36** (3914 → 3950): 27 templating-span
gates, 8 crossing gates, and one ported pin.

## 3c — accepted, and the re-scope was right twice over

The re-scope said accumulation is licensed where search is not. Two facts
found while implementing make it stronger than that:

1. **The PDA does not even need to accumulate — it already computes the
   offsets and throws them away.** `pda/runtime/build.py` builds a `text`
   field as `text[(start if item == 0 else ends[item - 1]) : ends[item]]`,
   where `start`/`ends` are absolute document offsets off the kernel frame.
   That is keep-what-you-computed in the most literal sense available.
2. **On the tree route the accumulation is exact for every span that
   matters,** and provably so rather than luckily: shared `ParseTree` nodes
   are always ZERO-WIDTH. Measured over three documents including ones with
   repeated non-empty content (`{"a": "xx", "b": "xx"}`): 7, 3 and 4 shared
   nodes, `shared-lengths=[0]` in every case, zero non-empty shared nodes.
   The reason is structural, not incidental — a non-empty derivation is
   chart-keyed by its span, so two occurrences at different positions are
   different items. Only zero-width nodes can intern across positions, and
   that is the one case `_tree_offsets` cannot separate (documented in its
   docstring and in the wiki).

The `-sk` skip twins were the named potential blocker; they are not one.
`skip_rules` twins each rule with `retag.apply(r.body)` — the same body, so
the same leaves — and fold bodies decide what is BUILT, never what is parsed.
Leaf text is fully present under a skipped subtree.

**How it landed.** A new fold mode, `span`, joins `BIND_MODES`. The key move
is that a field is a **(slot, mode) pair**, so the entry binds its two slots
twice — `text` and `span` — and one capture yields both halves with no second
pass and no change to what a `text` field is. `compute_binding` never emits
`span`: a generated field is what a rule MEANS, and a position is not, so no
model class grows one. `ModelFold.wants_spans` gates the tree route's offset
pass, so every ordinary grammar pays nothing.

Touched: `ir/spine/bind.py` (vocabulary), `pda/compiler/flatten.py` (int
code), `pda/runtime/build.py` (both field builders), `parsing/fold.py`
(`_tree_offsets`, `_slot_span`, threading), `compile/templating.py`
(`SpanEntry.key_at`/`value_at`, the four-field entry body).

**Gates** (`roundtrip/test_templating_spans.py`, 27): the offsets slice back
to the entry's own text over six documents × two JSON formulations; a
duplicate-spelling document pins that no search is happening (the key
`"name"` at `IrSpan(1, 7)` and a later VALUE `"name"` at `IrSpan(19, 25)` —
a `document.index` derivation would give both the first); document order and
non-overlap; the nested-level coordinate rule; and **both engine routes
produce identical entries**, which is where a divergence between the frame
read and the accumulation would show.

## 3d — accepted; the product states the set

The re-scope is exactly what the walk can honestly say, and the measurement
that motivated it reproduced: 178 source model occurrences on 71 objects,
one reached 27 times; the product 33 occurrences on 33 objects.

**One design choice inside the latitude.** Rather than two channels (unique
origins + a separate shared-set map), the crossing emits **one `IrOrigin` per
(built occurrence, source occurrence) pair the object map licenses**. A
source value standing in one place yields one entry — the unique case, an
ordinary occurrence↔occurrence correspondence; one standing in several yields
one entry each. `Crossing.sources_of(address)` returns the set, and its
multiplicity IS the answer, so a consumer wanting "the" source must confront
it. One channel, no silent pick possible, and the unique/shared distinction
falls out of `len()` rather than being a schema decision.

**`IrBottomUp._sink()`** is the seam that made this keep-what-you-computed
rather than a second walk: `_run` already fills `id(source) -> result` to do
its job and drops it, so a driver that wants it overrides one method. That
mirrors the existing `_descend` seam (whose own docstring already says
"Mirrors the overridable `_run` seam"), and `_run` changed by one line.
`compile/transpile.py`'s `_Tracked` is the override; a fresh one per call, so
no per-run state rides a shared artifact.

`run(text) -> str` keeps its signature and is now `cross(...).product.text` —
one path, two products, and `ex16`/`ex17` untouched.

**A boundary the gates state rather than hide.** 14 of 33 built model
occurrences have NO source: `Entry`, `Key`, `AvalsItem`, `FentsItem` — models
a table body builds inside itself (`Make("entry", IrTuple(Make("key", …), …))`)
or that the chain-grower mints for a hoisted list. They are the table's own
construction, not a transformed source node, and the crossing says so with an
empty set rather than attributing them to a neighbour. The gate asserts the
class names, so a future table that widened this silently would fail.

**One gate I had to weaken, correctly.** I first asserted that a shared
built occurrence's source addresses all belong to ONE source object. That is
false, and the code is right: two DISTINCT source objects can produce one
built object, because the fold interns by spelling. The honest invariant, now
gated, is the no-pick one: for every source value the set names, EVERY place
that value stands is in the set — a product that had chosen would carry a
proper subset.

## T4 — not started

Context budget. T3's two halves consumed the session; T4 (verdict record,
identity walk, rename alignment) is untouched, and nothing in the tree
anticipates it. Note for whoever takes it: `IrOrigins`/`IrOrigin` and the
`_model_addresses` grouping in `compile/transpile.py` are the shape 4b's
identity walk will want (unique nodes, share counts under ONE stated child
definition) — that grouping is already the share count, computed over the
emission's child definition, and 4b should either reuse it or state why its
definition differs.

## Process note, third occurrence

`tools/auto_fix.sh` reformatted tracked `zzz_current_work/` files on every
run this session (five times). Restored each time; the tree carries only the
licensed `space_3/praxis/reading.py` swap.

## Gate output tail

```
sanity: OK · lint: OK · typecheck: OK · pylint: OK   →  EXIT=0
3950 passed, 8 skipped, 3 warnings in 34.57s
guarded property  →  17 passed, EXIT=0
run_examples.sh   →  EXIT=0
check_generated   →  CLEAN: 0 pyright errors, 0 unaccepted pylint findings
space_3/gate.py   →  24 gestures · 13 keys · 0 failures
adv_space3_spans  →  IDENTICAL: 44 cases, 840 spans, all five fields
```
