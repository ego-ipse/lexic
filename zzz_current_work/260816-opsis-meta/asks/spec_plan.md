# asks/spec_plan.md — implementing the lexic asks

The contract for the src/lexic work. Tasks are ordered; each ends at the
done-gate and a commit. The parent documents are the authority:
`../VISION.md` (the position), `../ASKS.md` (revision 2, all rulings
folded), `../QUESTIONS.md` (settled list), `../probes/ADVERSARIAL_ASKS.md`
(the findings each design answers).

## Grants and roadmap (recorded 2026-08-16)

- **Commit grant**: the user granted commits at meaningful points for this
  effort, on this branch (`opsis_proto`). Commits carry NO Co-Authored-By.
  No pushes. A "meaningful point" is a completed task with the done-gate
  green.
- **Roadmap after the asks**: untrack `zzz_current_work/` from the index
  (409 files currently tracked; `git rm --cached`, working tree kept),
  merge the lexic changes to `main`, then start opsis itself on a fresh
  branch. **Ruled 2026-08-16: src/opsis is built ANEW**, room by room, on
  the shell contract — space_3 is frozen as the reference and the quarry
  (its behavior is the bar, its gate facts port as each room's acceptance,
  its leaf and the wire carry over; its derivations, placards and mode
  machine stay behind). A room is done when it looks like the thing it
  replaces and its ported facts pass.
- **Stop conditions**: a blocker requiring a user ruling (with all other
  points solved or blocked), or all tasks done.

## Ground rules (repo law, restated for the implementer)

- `tools/run_checks.sh` exits 0 = done; check `$?`, never grep output.
  `tools/auto_fix.sh` before hand-fixing lint. Full suite via
  `uv run pytest tests/ -q -n auto`.
- No `# type: ignore` / `# noqa` / suppressions. `pyproject.toml`
  untouched. No `exec`/`eval`. Flat code per `docs/STYLE.md` (≤4 indent
  levels, flat helpers, Sphinx docstrings, concise).
- Layering arrows hold; new public surface is reachable through the
  package roots only. Every new module gets its one-line entry in
  `CLAUDE.md`'s layout block (drift-gated) and its wiki row in the same
  change; significant wiki edits get a `log.md` entry.
- Tests are part of each task, written against THIS spec. Port, never
  delete: an existing test whose assertion still holds gets its
  construction updated, not removed.
- No grammar-specific hardcoding; every mechanism works over any
  formulation through the standard pipeline.

## Plan-time decisions (made, not open — flag disagreement in the report)

- **D1 (Q3)**: offsets are CODE UNITS (`len` of the emitted string) — the
  string's own truth. Columns/pixels are consumer projections. Whether
  `layout.py`'s width solve needs a column-aware measure is investigated
  in T3 and reported, not silently fixed.
- **D2 (placement)**: the address/span record family lands in
  `ir/text/spans.py` — spans are facts about documents, and `ir/text/`'s
  annotation ("How characters and documents are spelled") grows one word
  if needed ("…and where"). If implementation shows a better home, argue
  it in the report before moving.
- **D3 (M7 ruling, binding)**: the record family is designed to serve as
  kernel-trace event LEAVES later — shared leaves, separate products. No
  trace protocol is built now.

## T1 — the public-seam family (ask #4)

**Spec.** `export_value` becomes importable from `lexic.compile` and joins
`__all__`. Audit every attribute reachable on `lexic.compile` but absent
from `__all__` (`compile_ast`, `canonicalize`, `concretize`,
`compute_binding`, `synthesize`, `encoding_registry`,
`segmentation_tokenizer`, `rule_closure`, `RuleBinding`,
`build_codegen_grammar`, …): each is either promoted (added to `__all__` +
wiki `public-api.md` row) or ruled internal in the report with one line of
why. `compile_ast` is promoted (its module docstring already calls it a
primary entry). Fix `.wiki/lexic/public-api.md:79`, which names
`compile/payload/__init__.py` as `export_value`'s public home against the
layering rule.

**Tests.** A seam invariant: every symbol the wiki's public-api page
documents under `lexic.compile` is in `lexic.compile.__all__` (extend the
existing invariants family if one fits). Existing suite green.

**Done.** Gate green; commit `Export the compile seam family`.

## T2 — generate refuses with words (ask #7)

**Spec.** `lexic.generate` raises instead of silently returning `""`:
an unknown rule name and an empty alternation body each raise the
exception the error vocabulary assigns (read
`.wiki/lexic/error-vocabulary.md` and choose accordingly — likely
`UnsupportedConstructError`; if the wiki argues otherwise, follow the
wiki), with the rule name in the message. No signature change; the
injected-`rng` determinism stays.

**Tests.** Both refusals unit-tested with message content asserted; the
existing generate tests stay green (if any relied on `""`, port their
assertions to the refusal per the port-never-delete rule).

**Done.** Gate green; commit `Generate refuses unknown rules with words`.

## T3 — addressed emission and provenance (ask #1, the keystone)

Staged; each stage is reviewable, the task commits as one meaningful point
(or two if 3d/3e land separately — reviewer's call at review time).

**3a — the record vocabulary** (`ir/text/spans.py`, D2). Spine records:

- the occurrence ADDRESS: a path of slots from the root, item/document
  order, each step carrying the field name where one exists (from the
  binding) and the index where one does not. Built top-down by the
  driver, supplied positionally by the parent — never recovered from a
  value object, never looked up by equality (B1).
- the SPAN: `(start, end)` in code units (D1).
- the correspondence: address ↔ span (emit-side), address ↔ address
  (transpile-side). One vocabulary, designed as future trace-event leaves
  (D3).

**3b — emit-side addressed emission.** A `GrammarModel` product that
yields the correspondence set for a model's emission: every occurrence's
address paired with the span its spelling occupies in `to_text()`'s
output. One way per task: it drives the SAME `emit_parts` stream
`to_text` consumes (no second emission path), accumulating offsets — the
engine-side version of the walk space_3 hand-rolls. The driver must be
share-safe: equal sibling values are distinct occurrences with distinct
addresses (no `id()`-memo splice on this path).

**Gates (repository tests).** (i) Fidelity: for every address, slicing
`to_text()` by its span yields exactly that occurrence's own `to_text()`.
(ii) The B1 fixture: a document with equal siblings and shared noise
(`{"a": 1, "b": 1}` under json.gbnf) — every occurrence distinct, every
span correct. (iii) Coverage: the correspondence set covers the whole
emitted text with the structural literals attributed. (iv) Property test
over the round-trip corpus grammars (run under `tools/guarded.sh`).

**3c — templating offsets.** `SpanEntry` (and the span fold behind it)
carries `(start, end)` spans from the positions the fold already knew —
never re-found by string search. `Template.run` products expose them.
Gate: the offsets slice the document to the entry's existing `key`/
`value` text, on every templating fixture.

**3d — the transpiler trace.** `Transpiler.run`'s product carries the
source-address ↔ built-address correspondence the `IrBottomUp` walk holds
(keep-what-you-computed; always-on, like the transpile gates). Gate: on
the shipped json→kv example, every built occurrence traces to a source
address and the correspondence survives the run's own fidelity gate.

**3e — acceptance: the reference consumer.** Swap
`space_3/praxis/reading.py`'s hand-rolled span walk to consume 3b and
assert byte-identical spans on the fixture corpus (space_3's own gate
still green: `space_3/gate.py`). This is the proof the record shape
serves a consumer. zzz is not committed; the swap is validation, and the
result is reported.

**Done.** Gate green; commit `Addressed emission — products carry their
correspondences` (split if reviewed so).

## T4 — verdict record, identity walk, alignment (ask #3)

**4a — the verdict record.** A spine record for an attempt's outcome:
accepted/refused, the engine's words verbatim, the cost. Constructor from
a raised `LexicError`. Minimal: no prober, no registry — candidate policy
stays caller-side (M9). Placement argued in the report (likely beside the
compile root's products).

**4b — the identity walk.** An engine product over any `IrSelf`: unique
nodes, share counts (re-reachings), refusal boundary (what the notation
cannot spell back), under ONE stated child definition — the field-tuple
walk (M4's correction: state the definition, count sharing under it
alone). This replaces `space_3/eidolon/value.py`'s core as engine truth.

**4c — equality up to renaming.** A names-abstracted canonical comparison
of two grammar ASTs; on success, the rule-name bijection(s) as the
witness. Multiple valid bijections are all returned — offered, never
picked (the ruling). Language equality beyond renaming is out of scope
and says so. Gate: json.gbnf vs a pure-rename fixture aligns with the
right bijection; json.gbnf vs `json_arr.gbnf` (different factoring)
refuses; a grammar with two identical rule bodies yields both alignments.

**Done.** Gate green; commit per sub-task or as one, reviewer's call.

## T5 — the compile moments (ask #5)

**Spec.** `_assemble_core` is restructured so the pipeline's moments —
canonical → hoist_groups → hoist_arms → relax_non_semantic →
(concretize, when vocabulary demands) → binding → classes — flow through
ONE retaining product; `compile_text`/`compile_ast` consume its final
moment, and a public entry returns the moments themselves. No second
composition anywhere (`build_codegen_grammar` remains THE fused form only
if it is itself expressed through the same product — no drift surface).
Retention costs nothing when nobody asks for the moments. A no-op moment
(chess.gbnf's, a non-nullable `@non-semantic`) is a first-class fact of
the product, not an omission.

**Gates.** The moments compose exactly to the artifact's codegen grammar
on the ground-truth corpus; the no-op cases from the adversarial probe
(chess.gbnf, c.gbnf, vyx.gbnf) are asserted as no-ops; existing pipeline
tests green untouched (their assertions are the contract that nothing
changed behaviourally).

**Done.** Gate green; commit `Compile moments retained through the one
pipeline`.

## T6 — the kernel trace protocol (ask #6)

In scope (correction 2026-08-16: the user ordered ALL asks implemented;
"its consumer arrives right after the merge" is not a deferral ground —
that consumer arriving is the point of the sequencing). After T3 and T4:
the events carry T3's `spans.py` records as their reference leaves (the
ruled middle position, D3).

**Spec.** A public watched-run product on the predictive kernel: an
ordered event stream — scan, probe, rollback, gate consultation — each
event carrying its step order, its clone/rule identity, its verdict, and
its position as a T3 span/address record. Pay-to-watch: the trace runs as
an explicitly watched re-run with a stated cap, never instruments the
unwatched hot path, and says both facts in its product (the cap reached
or not; the run re-executed). Placement: `lexic.parsing` surface, argued
in the report.

**Gates.** Determinism: two watched runs of one (grammar, text) yield
identical streams. Honesty: the cap is a drawn fact (`capped: bool` or
count), never a silent truncation. Reference fidelity: every event's span
lies within the document and its rule/clone names resolve against the
compiled tables. Perf: the unwatched parse path is measurably untouched
(in-process A/B on a corpus fixture, guarded).

**Done.** Gate green; commit `The kernel speaks — a watched trace
product`.

## T7 — the presentation table mechanism (ask #2's lexic half)

In scope, last (needs T3's records and T4's alignment). The B3 ruling
stands — no screen-geometry solver in lexic — so the lexic half is
exactly the sayable part:

**Spec.** A baked, gated, rule-keyed table mechanism in the transpile
tradition: rows keyed by CANONICAL rule names; minimal declaration with
binding-derived routing (helper classes route to their canonical parent's
row — the `MapShape` precedent); bodies are ordinary IR actions whose
products are values built over T3's record vocabulary (addresses, spans —
no pixel/geometry types anywhere); baked against a compiled artifact;
gated for completeness and membership; travelling as notation
(repr-fixpoint); transported across pure renamings by T4's alignment
witness. Demonstrated by REPOSITORY TESTS on all three ruled languages —
a md grammar, a JSON grammar, an ABNF formulation — each with a small
authored table whose product is asserted structurally, none privileged,
all through the standard pipeline.

**Gates.** The three demonstrations; a completeness refusal in words for
a table with a hole; a membership refusal for a row naming no rule; the
alignment transport asserted on a renamed formulation; notation
round-trip of an authored table.

**Done.** Gate green; commit `Presentation tables — the ceiling's engine
half`.

## Out of scope, recorded

- The pixel/geometry SOLVE and opsis's own row vocabulary — the B3
  ruling's opsis half, built with the first room.
- The zzz untrack + merge to main — after T7, on explicit go.

## Findings promoted to fixes

- `generate.py`'s `max_depth` threaded-but-never-read (T2 finding): FIXED
  by the reviewer 2026-08-16 — depth accounting made real, exhaustion
  refuses with words (bugs are fixed when found, not logged).

## Reporting

Per task, the implementer writes `asks/T<n>_REPORT.md`: what changed,
decisions taken inside the spec's latitude, anything that argued against
the spec (with the argument), gate output tail, and the test count delta.
The reviewer (main agent) reviews the diff, runs the gate independently,
and commits.
