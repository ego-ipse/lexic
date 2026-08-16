# T4 — verdict record, identity walk, alignment

All three sub-tasks landed as specified. One finding argues against 4b's
stated child definition rather than against the task; it is implemented as
specified, gated, and argued below with numbers.

**Gates: `tools/run_checks.sh` EXIT=0 · `pytest tests/ -q -n auto` 4006 passed,
8 skipped · property under `tools/guarded.sh 8G 600` EXIT=0 (20 passed) ·
`tools/run_examples.sh` EXIT=0 · `tools/check_generated.py` CLEAN ·
`space_3/gate.py` 24 gestures · 13 keys · 0 failures.**

**Test count delta: +56** (3950 → 4006): 8 verdict, 18 identity, 15 alignment
(unit), 11 rename-alignment (corpus), 3 alignment property, 1 census gate added
beside the addressed-emission sharing gates (and one of those PORTED to the
census — see the last section).

---

## Placement, argued

**4a → `src/lexic/compile/verdict.py`, class `Verdict`.** A verdict is not a
fact about IR; it is a fact about a RUN — an attempt made through the seam,
which for lexic is `lexic.compile` (the artefact's `parse`, the compile
entries). Its constructor reads the error hierarchy, and its consumer is
whoever made the attempt, which reaches lexic through that same root. Placing
it in `ir/` would say attempts are IR.

The name carries no `Ir` prefix on purpose: `compile/` already holds spine
records named plainly (`SpanEntry`, `SpanLevel`, `SpanPair`, `MapShape`), and
in this repo `Ir*` reads as "defined in `lexic.ir`". Exported from
`lexic.compile.__all__` and documented in `public-api.md` under a heading the
seam-drift test parses, so it is gated by T1's invariant rather than merely
listed.

**4b → `src/lexic/ir/spine/identity.py`.** The walk's ONE child definition is
a statement about the spine's tiers — *a record IS its field tuple*, read as a
traversal — so it belongs in the group that defines them. Putting it in
`ir/action/` would have implied the dispatcher's definition (`children()`,
which honours `_child_attrs`), and that is precisely the other definition M4
warns about; putting it at `ir/`'s top level would have put a reader of the
substrate beside `flavour.py`, which is a config bundle.

**4c → `src/lexic/ir/grammar/alignment.py`.** Beside `canonical.py`, whose job
it completes: `canonicalize` folds spelling and never quotients names, and
this is the comparison that abstracts what canonicalisation deliberately
leaves alone. `ir/grammar/` is "the grammar AST and the passes over it", and
the witness (`IrRenaming.renamed`) IS such a pass.

All three are reachable through their package roots only (`lexic.compile`,
`lexic.ir`), and the two IR families joined the notation vocabulary
(`compile/notation/parse.py`'s `_IR_MODULES`), so `load_ir(repr(x)) == x`
holds for a census and for an alignment — checked in the drift pin's module
list, which gained both.

## 4a — the verdict record

`Verdict(accepted, words, readout, seconds)`, with `Verdict.accept(seconds)`
and `Verdict.refuse(error, seconds)`. The refusing constructor lifts
`UnsupportedConstructError.readout` when the error carries one and otherwise
uses the empty `Refusal()` (`pos == -1`) rather than `None`, which keeps the
field union-free.

Decisions inside the latitude:

1. **Cost is `seconds: float`, measured by the caller.** The record does not
   time anything. Timing means running the attempt, and running attempts is
   the prober the spec (and M9) rules out. The docstring says the number is
   comparable within a run and meaningless across machines.
2. **No `attempt()` method anywhere**, though I considered one on
   `CompiledGrammar`. It would have made the ACCEPTED case throw the product
   away — the caller then parses a second time — and choosing between "keep
   the product" and "keep only the verdict" is exactly the policy the ask
   assigns to opsis. Every caller writing its own three-line try/except is the
   correct cost here.
3. **One record with `accepted: bool`, not two types.** The Liskov rule in
   `docs/STYLE.md` argues for splitting variants with structurally different
   contracts; I did not, because the point of the record is that verdicts of
   BOTH kinds sit in one list and compare. `Refusal` next door carries
   `negated`/`undecidable` booleans on the same reasoning.
4. **The type of the error is not kept**, only `str(error)`. The engine's
   messages are already self-identifying ("parsing: input does not derive from
   'grammar'"). Flagging this as the one place a reviewer might want more.

Nothing in the tree constructs a `Verdict` yet, which is by design — the
producer is the caller. The tests build them from REAL raised errors (a
genuine refused parse, and a `FieldValidationError`), not from hand-made
strings.

## 4b — the identity walk

`census(root) -> IrCensus`, a sequence of `IrIdentity(node, reached,
unspellable)` in first-reach order, with `shared()` and `refusals()` sub-census
views. `field_children` and `unspellable` are exported too, so the definition
the census reports under is checkable by a consumer rather than only stated.

- **`reached` counts arrivals** — one per edge pointing at the node, plus one
  for the root — so `sum(reached) == edges + 1` is a conservation law, and it
  is how the corpus test checks the census against its own definition instead
  of against a second traversal that would only agree with itself.
- **Distinctness is identity**, and the walk is iterative (a 10,000-deep chain
  is gated). The id→index table is safe because the census holds every node,
  so no id can be recycled mid-walk — the prototype had the same latent
  hazard and no comment about it.
- **The refusal boundary** is `IrLambda` plus any node carrying a bare
  callable that is neither a node nor a class. `spine.py` already names
  `IrLambda` as "the one node whose payload is a callable and therefore the
  one the notation refuses"; the second clause catches a raw function riding
  in a record field, which I could not find anywhere in the tree but which the
  prototype's rule anticipated.

### The one thing that argues against the spec

The spec fixes the child definition as the field-tuple walk. I implemented
that. **Its consequence is that a map is a LEAF** — `IrMapping` carries a dict
in a slot, not a tuple — and that is worth the reviewer's eye, because it is
what the refusal boundary is mostly made of. Measured this session:

```
                        definition     nodes  shared  arrivals  maps  lambdas
gbnf json.gbnf AST      field-tuple      470       1       476     0        0
                        children()       424       0       424     0        0
JSON_GRAMMAR            field-tuple      335       2       409     0        0
                        children()       316       1       384     0        0
GBNF_FLAVOUR.reducer    field-tuple        5       0         5     2        0
                        children()         1       0         1     0        0
```

The field-tuple definition is strictly the better of the two (it sees
`IrRule.name`, which `_child_attrs` excludes and which is a real shared node),
and the 470-vs-424 gap is exactly M4's "the delta was the child definition".
But a flavour's reducer censuses as **five nodes, two of them tables**, and the
`IrLambda`s inside those tables — the only unspellable things in the repo — are
never reached. So on a reducer the census reports `refused 0`, honestly under
its own definition and misleadingly if read as "this value round-trips".

I did not widen the definition, because a two-clause child relation (tuple
elements, plus a map's entries) is the isinstance cascade the doctrine
forbids, and because "ONE stated child definition" is the ask's actual
deliverable. The module docstring states the exclusion, `test_a_map_is_a_
leaf_under_this_definition` pins it, and the honest fix — if a consumer ever
needs table interiors — is for `IrMapping` to answer for its own children on
the spine, not for the census to special-case it.

The corpus fixture cross-check is worth recording: `{"a": 1, "b": 1}` under
`json.gbnf` censuses as **14 distinct nodes with a maximum share count of 7**,
against **67 emitted occurrences** from `emit_addressed()`. That gap is why
addresses exist, and it is now gated as two numbers from two products rather
than asserted in prose.

## 4c — equality up to renaming

`align_names(left, right) -> IrAlignment(renamings, capped)`. Both sides are
canonicalised, the rules are coloured by refinement over the rule graph — a
rule's colour is its own colour plus its body with every in-grammar ref
replaced by that ref's target's colour, refined to a fixpoint over BOTH
grammars at once — and every candidate bijection consistent with the final
colouring is verified by applying it and comparing rule SETS.

Decisions inside the latitude:

1. **The comparison is over the rule set, not the rule list.** A renaming can
   reorder the canonical order (unreferenced rules sort alphabetically by
   their NEW names), and two orderings of one rule set are one grammar. The
   `semantic` flag participates, so a noise rule aligns only with a noise rule.
2. **Refusal is the empty `renamings`, not a raise.** "Are these the same
   grammar?" is a question whose honest answer can be no; a raise would make
   an ordinary answer an exception. The canonicaliser's own refusals (a
   name-fold collision) still propagate as words, and that is gated.
3. **A cap, and it is a drawn fact.** *k* mutually interchangeable rules admit
   *k!* bijections; `CANDIDATE_CAP = 256` bounds the enumeration and
   `capped: bool` says when it was hit. The alternative — returning a
   truncated list silently — is the same defect as picking one.
4. **The witness is a transport, not a certificate.** `IrRenaming.renamed(ast)`
   carries a grammar (and, by `dict(renaming)`, any rule-keyed table) across
   the renaming. It is the same function the verifier uses, so a witness that
   verified cannot fail to transport. This is what T7 will consume.
5. **The colouring seeds the start rule apart**, and a rule's own colour leads
   its signature so a round can only split a class. Without that, a round
   could MERGE the start rule with a body-identical twin, which cost nothing
   in correctness (the final check pins `start`) but could burn the cap.

Gates, all three the spec named plus two it did not:

- `json.gbnf` vs a hand-written pure rename of it (fixture in the test module,
  same rule order, same bodies, same directive): one bijection, uncapped, and
  it is exactly the expected name map. The fixture is asserted to BE a rename
  first — disjoint name sets, unequal ASTs — so the gate cannot go vacuous.
- `json.gbnf` vs `json_arr.gbnf`: refuses.
- a grammar with two identical rule bodies: both alignments, and every offered
  one is asserted to really carry the grammar across.
- **`json.gbnf` vs `json.abnf` aligns with the IDENTITY witness** — one
  grammar, two flavours, names surviving the crossing. Not asked for, and the
  strongest single statement in the file.
- a property suite (30/30/20 examples over four corpus grammars × random
  relabellings): the search recovers a bijection it was never told, every
  offered bijection is valid, and alignment is symmetric.

**Out of scope and said so**, in the module docstring, the function docstring
and the wiki: language equality. An empty alignment claims only that no
renaming relates the two grammars, never that their languages differ.

## Found in passing, and fixed

`tests/integration/lexic/roundtrip/test_addressed_emission.py::test_shared_
nodes_get_one_address_each_not_one_between_them` was **failing at HEAD** before
any of my changes (confirmed by stashing my edit to that file — the failure
reproduces on the committed version). It read `id(model.occurrence(...))`
without holding the occurrence, so a resolved part that is built on the way out
is freed the moment its id is taken and CPython hands the same address to the
next one; two unrelated parts then read back as one shared object. It passed in
isolation and failed when the file ran whole, which is why it survived T3's
run. The occurrences are now held while their ids are read; the assertions are
unchanged.

The neighbouring `test_the_b1_fixture_really_does_share_nodes` hand-rolled an
id-keyed walk to assert the premise; it is now written against `census`, which
is the point of 4b replacing the prototype's core with engine truth. Its
assertion is unchanged.

## What changed

| File | Change |
|---|---|
| `src/lexic/compile/verdict.py` | NEW — `Verdict` + its two constructors |
| `src/lexic/ir/spine/identity.py` | NEW — `field_children`, `unspellable`, `IrIdentity`, `IrCensus`, `census` |
| `src/lexic/ir/grammar/alignment.py` | NEW — `IrRename`/`IrRenaming`/`IrRenamings`/`IrAlignment`, `align_names`, `CANDIDATE_CAP` |
| `src/lexic/compile/__init__.py` | `Verdict` imported and in `__all__` |
| `src/lexic/ir/__init__.py` | eleven names across the three façade lists (TYPE_CHECKING, `__all__`, `_HOMES`) |
| `src/lexic/compile/notation/parse.py` | `identity` + `alignment` in `_IR_MODULES` |
| `CLAUDE.md`, `ir/spine/README.md`, `ir/grammar/README.md` | the three module lines |
| `.wiki/lexic/ir-shapes.md` | the identity walk and the alignment family |
| `.wiki/lexic/public-api.md` | the `Verdict` entry (heading shaped so the seam-drift test gates it) |
| `.wiki/log.md` | the entry |
| `tests/unit/lexic/compile/test_verdict.py` | NEW — 8 |
| `tests/unit/lexic/ir/spine/test_identity.py` | NEW — 18 |
| `tests/unit/lexic/ir/grammar/test_alignment.py` | NEW — 15 |
| `tests/integration/lexic/roundtrip/test_rename_alignment.py` | NEW — 11 |
| `tests/property/lexic/test_alignment.py` | NEW — 3 |
| `tests/integration/lexic/roundtrip/test_addressed_emission.py` | the id-recycling fix, the ported premise gate, one new census gate |
| `tests/unit/lexic/compile/notation/test_parse.py` | the drift pin's module list |

No suppressions, no `eval`, no `pyproject.toml`, no commit.

## Process note, fourth occurrence

`tools/auto_fix.sh` reformatted tracked `zzz_current_work/` files again. The
lane's restore instruction (`git checkout -- zzz_current_work`) would have
destroyed T3's uncommitted `space_3/praxis/reading.py` swap, so the diff was
saved first and re-applied after: the tree still carries exactly that one zzz
modification and nothing else.

## Gate output tail

```
sanity: OK · lint: OK · typecheck: OK · pylint: OK   →  EXIT=0
4006 passed, 8 skipped, 3 warnings in 34.54s
guarded property  →  20 passed, EXIT=0
run_examples.sh   →  EXIT=0
check_generated   →  exported 49 modules · CLEAN, EXIT=0
space_3/gate.py   →  24 gestures · 13 keys · 0 failures
```

T5 not started (holding, per the lane's instruction).
