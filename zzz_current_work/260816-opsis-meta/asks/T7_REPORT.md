# T7 — the presentation table mechanism

Landed. The last ask: a ceiling is a rule-keyed table, baked and gated in the
transpile tradition, drawing rows over T3's records with no geometry anywhere.

**Gates: `tools/run_checks.sh` EXIT=0 · `pytest tests/ -q -n auto` 4148 passed,
8 skipped · property under `tools/guarded.sh 8G 600` EXIT=0 (20 passed) ·
`tools/run_examples.sh` EXIT=0 · `tools/check_generated.py` CLEAN ·
`space_3/gate.py` 24 gestures · 13 keys · 0 failures.**

**Test count delta: +69** (4079 → 4148): 23 integration (the three
demonstrations and the gates), 13 unit (the mechanism itself), 3 unit for
`rekeyed`, and 30 the new corpus grammar contributes to the existing
corpus-wide suites.

---

## The shape

```python
Row(role, address, span, parts)      # what stands where — and NOTHING else
Rows(IrSeq[Row])
Draw(role)                           # the one row-building body; role may be algebra
present(compiled, rows) -> Presentation
Presentation.apply(model) -> Rows
IrRenaming.rekeyed(table) -> IrMap   # the witness, re-keying any rule-keyed table
```

`compile/presentation.py`, exported from `lexic.compile` — beside
`transpile.py`, whose tradition it follows exactly: rows are DATA keyed by rule
names, baked once against an artifact, gated always-on, and spellable through
the notation with the authored vocabulary supplied per call
(`load_ir(repr(table), symbols={"Draw": Draw})`, the `Make`/`Spelled`
precedent).

**The walk is the emission's own.** `apply` iterates
`model.emit_addressed().extents` — document order, parents first, address and
span already computed — and nests rows by address prefix on an explicit stack.
A ceiling therefore has no traversal of its own and cannot disagree with the
addresses a consumer co-selects through. That is T3 paying for itself a second
time.

## Decisions inside the latitude

1. **Completeness is over DRAWABLE rules, not all semantic ones.** A rule is
   drawable when it is semantic (noise draws nothing) and its binding kind is
   not `alternation` (a pass-through never stands anywhere — the arm's model is
   the value, and the arms have rows of their own). Both facts are read off the
   compilation's own binding view rather than asked of the author. This is what
   keeps an honest ceiling small: markdown 11 rows, arithmetic 6, JSON 28.
2. **Helper routing is derived from the two grammars, not from names.** A
   helper is whatever the codegen grammar has and the canonical grammar does
   not — a set difference T5's `moments` makes free — and its owner is the
   canonical rule whose body reaches it through helpers alone. No name parsing,
   no `-item`/`-arm` convention read anywhere. A helper reachable from two
   canonical rules would have no single row to route to, and refuses in words
   (it cannot happen today; the refusal is there because the derivation should
   say so rather than pick).
3. **`Draw` is the only body constructor.** The address, span and nested rows
   come from the occurrence, never from the author: they are facts about the
   document, and a body able to state them could state them wrongly. What the
   author supplies is the role — a constant, or any algebra producing one. The
   unit suite draws one rule as two roles through an `IrCond` to keep that a
   real capability rather than a claim.
4. **The cursor is a per-run leaf.** `_Focus` carries the address and span for
   the occurrence being drawn and is mutated as the walk moves — per-run state,
   like every other cursor here, because the artifact is shared.
5. **`rekeyed` landed on `IrRenaming`, beside `renamed`.** The ask calls the
   alignment "the artifact that transports every rule-keyed table"; that is one
   method, and it belongs on the witness rather than on the ceiling, since a
   transpile table crosses a renaming the same way.

## The three demonstrations

All in `tests/integration/lexic/codegen/test_presentation.py`, none privileged,
each a table of rule → role and a structural assertion of what it draws.

- **markdown** — `resources/ground_truth/markdown.gbnf`, authored for this
  task. `"# Title\nsome *bold* text\n- one\n"` draws as
  `page → heading(depth, text(words)) → paragraph → item`, with emphasis and
  code reaching their own roles inside a line.
- **JSON** — `json.gbnf` unchanged, 28 rows, `{"a": 1}` drawing as
  `document → map → entry`.
- **ABNF** — `arithmetic.abnf`, 6 rows, `12+3` drawing as
  `formula → expression → term → number → digit`, with the hoisted `expr-item`
  occurrences drawing under `expression` through the routing.

### The markdown grammar, and what it cost to make honest

It is a real fixture, not a sketch: 14 rules, both engines, round-trip clean,
and **unambiguous** — which took two restrictions, both stated in the file's
own comment because a reader will otherwise think them arbitrary:

- a paragraph cannot open with `#` or `-` (else `"# x"` derives two ways, and
  two derivations that mean different things are refused by both engines);
- a line interleaves plain runs with styled ones (`plain? (styled plain?)*`)
  rather than repeating a chunk, because two adjacent plain runs carve one run
  of text two ways. The first formulation I wrote did exactly that and Earley
  refused it — caught before it shipped, by running the fixture through BOTH
  engines rather than the PDA alone, which takes the greedy path and would
  never have noticed.

It joined `tests/paths.GBNF_GRAMMARS` — a full corpus citizen, not a special
case — so it now also runs the round-trip, addressed-emission, watched-run,
cross-flavour and property suites. Those +30 tests all pass, and the corpus
drift pin (`test_gbnf_ir_equivalence`) gained its golden fingerprint, which is
that gate doing its job.

## The gates the spec named

| Gate | Where |
|---|---|
| Three demonstrations | the three tests above, plus span-slicing and nesting parametrised over all three |
| Completeness refusal in words | `present` with 3 of 6 rows: "the table has 3 hole(s) — ['op', 'num', 'digit'] have no row"; a second test asserts every missing rule is named |
| Membership refusal | a row named `paragraph` against arithmetic: "name no drawable rule of the grammar — it draws [...]" |
| Alignment transport | `arithmetic.abnf` vs a renamed GBNF twin: one witness, `rekeyed`, and the two drawings are IDENTICAL tuple-for-tuple |
| Notation round-trip | all three tables, `load_ir(repr(table), symbols={"Draw": Draw}) == table` |

Plus the ones I would not ship without: every span slices back inside the
document; a row's span nests inside its parent's; a row carries no geometry
(the field set is pinned against `{x, y, width, height, column, pixels}`); a
noise rule needs no row; a helper needs no row AND still draws; a table does
not transport to `json_arr.gbnf` (a different factoring — the alignment refuses
first, and `present` refuses after).

## What changed

| File | Change |
|---|---|
| `src/lexic/compile/presentation.py` | NEW — `Row`, `Rows`, `Draw`, `Presentation`, `present` |
| `src/lexic/ir/grammar/alignment.py` | `IrRenaming.rekeyed` — the witness as a table transport |
| `src/lexic/compile/__init__.py` | five names on the seam |
| `resources/ground_truth/markdown.gbnf` | NEW — the third demonstrator language |
| `tests/paths.py` | markdown joins the GBNF corpus |
| `tests/integration/lexic/roundtrip/test_gbnf_ir_equivalence.py` | its golden fingerprint |
| `CLAUDE.md` | the module's line |
| `.wiki/lexic/public-api.md`, `.wiki/log.md` | the entry and the log |
| `tests/integration/lexic/codegen/test_presentation.py` | NEW — 23 |
| `tests/unit/lexic/compile/test_presentation.py` | NEW — 13 |
| `tests/unit/lexic/ir/grammar/test_alignment.py` | 3 for `rekeyed` |

No suppressions, no `eval`, no `pyproject.toml`, no commit.

## Boundaries, stated

- **A ceiling is bound to its grammar's rule names**, and a renaming is the
  only difference it crosses. A differently-factored grammar of the same
  language refuses — which is the honest position B2 forced and the ask
  adopted, not a limitation to be worked around later.
- **A row's `role` is unconstrained.** Nothing validates that two ceilings use
  the same words; a vocabulary of roles is a consumer's contract, not lexic's,
  and inventing one here would be the privileged formulation in a new costume.
- **Nesting is by address prefix**, so a ceiling's tree follows the model's.
  A ceiling cannot re-parent a row (draw a heading's text under the page rather
  than the heading) — that is a solver's job, and giving a table the power
  would have meant giving it geometry.

## Process note

`tools/auto_fix.sh` reformatted tracked `zzz_current_work/` files twice more;
restored both times from the saved pre-existing diff, so the tree still carries
only T3's licensed `space_3/praxis/reading.py` swap.

## Gate output tail

```
sanity: OK · lint: OK · typecheck: OK · pylint: OK   →  EXIT=0
4148 passed, 8 skipped, 3 warnings in 37.72s
guarded property  →  20 passed, EXIT=0
run_examples.sh   →  EXIT=0
check_generated   →  CLEAN: 0 pyright errors, 0 unaccepted pylint findings
space_3/gate.py   →  24 gestures · 13 keys · 0 failures
```

The asks are done: T1–T7 all landed. Holding — the untrack and the merge are
the user's explicit go, not mine.
