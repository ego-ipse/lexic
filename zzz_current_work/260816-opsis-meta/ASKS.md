# Named lexic asks — ranked by leverage

The doctrine (VISION §2): when opsis needs what the engine does not expose,
the ask is named and lands in `src/lexic` with repository tests — never
painted, never worked around. Under the 2026-08-16 ruling **any lexic work
is in scope**; this list is ranked by architectural leverage.

Revision 2, after the adversarial round (`probes/ADVERSARIAL_ASKS.md`,
3 blockers · 11 majors · 8 minors). Findings are cited as B/M/m; the
author's dissent from one finding is recorded at the bottom. Probe
evidence: `probes/probe_asks.py` (16 facts) and the adversary's
`probes/adv_asks.py`.

## 1. Addressed emission and provenance — THE KEYSTONE, re-scoped

*Products carry the correspondences they computed: a fold or run that knew
a correspondence hands it back.* One record vocabulary, two directions
(M7's merge, minus the kernel — see dissent). This absorbs the old #1's
engine half, the old #5 (transpiler trace) and #6 (span offsets), and the
adversary's M2.

- **Emit-side**: an emission whose parts carry `(address, field, start,
  end)` — today `emit_parts()` is per-node, shallow, offset-free
  (`model.py:502`), and space_3 re-derives text geometry by a second full
  walk (`praxis/reading.py:295-327`). The engine knows the offsets; the
  product should carry them.
- **Parse-side**: `SpanEntry` carries span *text*, not offsets
  (`templating.py:166-172`, confirmed twice) — the fold captured positions
  it then dropped. Same record vocabulary.
- **Transpile-side**: `Transpiler.apply` returns only the product
  (`transpile.py:273-285`) while the `IrBottomUp` walk holds source node
  and built children at every step — the trace product (source occurrence
  ↔ built occurrence) uses the same address contract.

**The address contract (B1 — the blocker this ask exists to survive).**
The spine SHARES equal nodes by identity: in `{"a": 1, "b": 1}` one `Ws`
object is reached 7 times, and every walk driver splices shares by `id()`
memo. Therefore: (a) an address is a PATH built top-down by the driver,
each child's slot supplied **positionally** by the parent — never
recovered from the node, never looked up by value equality; (b) an
addressed emission may not run on an id-memoising driver with share-splice
enabled — equal-and-shared is the normal case, not a corner; (c) the
address states its order explicitly — item-slot (document) order with the
field name attached, from the binding, because `children()` order and
`_fields` declaration order genuinely differ (M3: `JsonText` declares
`(value, ws, ws2)` and walks `[Ws, Object, Ws]`); (d) a repository test on
a document with equal siblings and shared noise nodes is part of the ask.

**The ownership split (B3).** The engine half is the *addressed emission*
— a fact about the value and its spelling, testable in-repo. The geometry
SOLVE — where regions land, in what screen coordinate system — is
arrangement, which VISION §2 reserves for opsis. Lexic does not grow a
screen-layout solver. What lexic does own is the *measure*: offsets are in
a named measure function, and the contract names it (M10 — `layout.py`
counts code units, `self.col += len(text)`, wide-glyph-blind, while the
instrument measures terminal columns with wide glyphs counted twice;
`japanese.gbnf` is already in the corpus; the discrepancy must be settled
inside this ask, not discovered later).

**Probed / verified.** The `IrDoc` dual-role precedent holds exactly as
cited (adversary's "What survived"). The dispatch floor holds: MRO lands
unknown model classes on the record row; a non-node refuses with
`IrKeyError`. What the probe did NOT prove — geometry, coordinates, width
— is exactly what this re-scope removes from lexic.

## 2. The presentation ceiling contract — formulation-bound, honestly

The two-tier dispatch stands (floor proven on existing machinery), but B2
killed the "one table serves any formulation" framing: rule names are
formulation-bound (a pure rename makes two grammars canonically unequal;
transpile tables refuse unknown names by construction — that is what the
gates are FOR). The ceiling contract is therefore:

- **Key domain: canonical rule names** — user-authored, surviving
  canonicalisation (which folds case and `_`→`-` only). Never codegen
  helper names (`array-item2`, `char-arm2` — minted by `passes.py`, not a
  public contract). Occurrences of helper classes route to their canonical
  parent's row through the binding view, MapShape-style: **declare one
  name, derive the rest** (`MapShape.for_entry` is the in-repo precedent,
  on its own stated ground — "a restatement can disagree").
- **A ceiling is authored against a grammar and gated** — completeness and
  membership gates say where it applies. The *mechanism* is
  formulation-generic; a given *table* is not, and saying otherwise was
  the error (Q4's justification is corrected accordingly). But the
  boundary is softer than B2 first drew it (user ruling 2026-08-16): a
  pure rename is no boundary at all — equality up to renaming is
  decidable, and its computed name ALIGNMENT (ask #3) transports the same
  table across renamed formulations for free. The honest refusal is
  reserved for *structurally* different formulations (different
  factoring), where it is real.
- Row/region node types are lexic vocabulary (data, notation-portable,
  ask #1's records); the solver that arranges them is opsis (B3).
- The three demonstrator ceilings (md, JSON, ABNF — ruled) are what keeps
  the mechanism honest across languages.

## 3. The verdict record and the identity walk — the relation algebra, shrunk

M9 is right that the four queries reduce to two mechanisms — a
verdict-keeping prober and a walk — and that probing *policy* (which
candidates, what order, memoised how, re-run when) is session concern,
which VISION §2 assigns to opsis. The engine half shrinks to:

- **A verdict record type.** Today an attempt yields a product or an
  exception, and an exception is not a value the graph can carry. The
  engine should hand back verdicts as values — accepted/refused, the
  engine's words, the cost — comparable and drawable across attempts.
  No reader registry lands in lexic: a registry of "the readers we happen
  to ship" is the privileged-formulation hazard in a new costume (M9).
- **The identity walk as a product**: unique nodes, share counts, refusal
  boundaries, under ONE stated child definition (M4's correction: the
  830-vs-923 delta was the child *definition*, not sharing; measured
  honestly, both walks re-reach ~200 shared nodes — sharing is real, and
  ask #1's B1 depends on it, but the number offered before proved the
  wrong thing).
- **Orbit membership is three relations, not one** (M8): a grammar's ring
  is canonical equality; a value's ring is spine equality plus a per-form
  load-back witness; a text's ring is "reads to the same value under the
  same reader". All three computable today; the grouping surface is the
  ask.
- **Equality up to renaming, with the alignment as the witness** (user
  ruling 2026-08-16: a pure rename of topologically identical grammars is
  no real difference). `canonicalize` folds spelling but never quotients
  names; the ask is a names-abstracted comparison that, on success, hands
  back the rule-name BIJECTION — the artifact that transports every
  rule-keyed table (ceilings, transpile tables) across the renaming.
  Decidable, unlike language equality in general, which stays refused.
  Rules with identical bodies admit multiple valid bijections: the
  ambiguity is surfaced as offered alignments, never silently picked —
  the no-silent-pick doctrine applied to isomorphism. (The 2607xx
  architecture sketch already named `isomorphic(a, b)`; this funds it.)
- Altitude probing stays opsis-side (ten correct lines in
  `praxis/reading.py:123-128` — the prior-art citation is corrected from
  `upward()`, which "never parses"). Honest costs (M5): warm probes are
  1–10 ms; the FIRST subject in a session costs ~0.6 s cold; the
  several-readers-ACCEPT case at document level is a full parse per accept
  and is unmeasured — the map's eager tier budgets for the cold and
  multi-accept cases, not the warm single-accept one.

## 4. `export_value` and the public-seam family — smallest, do first

`export_value` is genuinely absent from `lexic.compile` (confirmed twice —
not imported, not in `__all__`, deep import is the only route). m1 widens
it: `compile_ast`, `canonicalize`, `concretize`, `compute_binding`,
`synthesize`, `encoding_registry` and others are reachable attributes but
absent from `__all__` — audit the seam once, fix the family, and correct
`.wiki/lexic/public-api.md:79`, which documents `export_value`'s home as a
module the layering rule says is not importable (m2).

## 5. The compile moments — through the pipeline itself

M6 reshapes this ask. The passes compose to the fused function *by source
identity* (`passes.py:255` IS the composition). But the room's moments are
at least six — canonical → hoist_groups → hoist_arms → relax_non_semantic
→ `concretize` (conditional) → `compute_binding` → `synthesize` — and the
ask as previously written named three. And "one way per task" cuts
deeper than my earlier wording: a trace product that RE-RUNS the passes is
a second composition that will drift the first time a pass is added. The
only one-way formulation: **`_assemble_core` itself routes through the
retaining product**. Distinctness is grammar-contingent (chess.gbnf: one
pass of three changes anything; a declared `@non-semantic ws` on a
non-nullable rule relaxes nothing) — a no-op moment is drawn honestly as a
no-op, never suppressed.

## 6. A kernel trace protocol — kept separate (see dissent)

Unchanged in substance, confirmed in grounding: `PdaKernel` is public with
closed `__slots__` and no step hook. Instruction-level machine drawing
waits on a public trace; until then the machine room draws clone frames
and says the watch re-runs and caps.

## 7. `generate` refuses with words — elevated from the adversary's m7

`_Generator.run` returns `""` for an unknown rule name and for an empty
alternation body — a silent fallback the repo's own doctrine forbids. A
generation door built on it draws an empty sample indistinguishably from a
generated one. Fix: raise with words. Small, self-contained, and the
generation gesture is already live in space_3 — this is a real engine bug
found by the review, which is the doctrine (§2) working.

## Cross-cutting costs (m8)

Every ask that adds a module owes its `CLAUDE.md` project-layout line in
the same change (`test_doc_drift.py` gates both directions), and ask #1's
record family needs a placement ruling — `ir/text/` is annotated "How
characters and documents are spelled", and an addressed-emission record
family arguably belongs there only if the annotation grows, or elsewhere
if not.

## Non-asks, recorded so they stay dead

- A `PdaTables | None` opt-out channel or any route flag near the parse
  API — repeatedly rejected; escapes are islands; the engine owns
  composition.
- A privileged "screen grammar" formulation, a bespoke per-format module,
  or functionality living in tests/fixtures.
- Any second emit path beside the flavour/emit-action mechanism — the
  addressed emission extends the algebra; it does not fork it.
- A screen-geometry solver in `ir/` (B3) — arrangement is opsis's.
- A reader registry in lexic (M9) — candidate policy is session concern.

## The M7 disagreement — RULED 2026-08-16: the middle position

⊨ Separate products, shared leaves (user ruling; the dissent is
dissolved). The record of the positions, kept for the reasoning:

The adversary's M7 folds four dropped-data findings into ONE ask ("products
carry provenance"): emit-side offsets, templating span offsets, the
transpiler correspondence, and the kernel trace. I merged the first three
and kept the kernel trace apart (ask #6). The disagreement, precisely:

**Where we agree.** Three products are the same SHAPE — a static
correspondence, a set of (occurrence-path ↔ span-or-occurrence) pairs; the
folds that build them hold both ends and merely drop one; keeping the data
is nearly free; the consumer is co-selection (the cursor washing across
facets); and they can share one record vocabulary and one always-on gate
discipline, like the export gates.

**Where the kernel trace differs, in four ways.** (1) *Shape*: it is a
temporal EVENT STREAM — ordered steps (scan, probe, rollback, gate
consultation), each with a position and a verdict; order IS the content,
where a correspondence set has no time axis. (2) *Consumer*: the machine
room's clock and scrubber — kairos, temporal navigation — not deixis'
co-selection. The instrument's oldest architecture names these as separate
modes. (3) *Cost model*: correspondences are keep-what-you-computed on
paths that already run; a kernel trace must instrument the engine's paid
hot loop, so it is pay-to-watch — an explicitly watched, capped re-run —
and can never be always-on. (4) *Gating*: an always-on fidelity gate works
for correspondences and cannot exist for a trace.

**The risk of the full merge**: a vocabulary general enough for both is an
abstraction whose two halves share little but the name — designed before
either consumer exists, which is the speculative-generality pattern this
repo's own history warns against ("split per room LAST").

**The adversary's strongest point, conceded**: machine-room rows DO
co-select with the document and the grammar (click a frame → wash the
span it consumed). If the trace's positional references and the
correspondence records are unrelated types, that co-selection crosses two
vocabularies with a translation shim between them.

**The middle position (now the ruling).** Separate PRODUCTS, shared
LEAVES: the kernel trace remains its own ask with its own driver, cost
model, and consumer — but its events carry ask #1's address/span records
as their reference fields, so a trace event and a correspondence entry
point into a document with the same record and co-selection composes
without translation. One vocabulary where the cursor needs it (the
leaves); the trace keeps its own shape where time and cost demand it
(the product). Consequence for sequencing: ask #1's record vocabulary is
designed knowing it will serve as trace-event leaves — a constraint on
its generality, not on its schedule.
