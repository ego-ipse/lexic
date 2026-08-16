# Adversarial review — `ASKS.md`, `VISION.md`'s engine claims, `QUESTIONS.md`

Attacking the eight named lexic asks and every engine-facing claim behind
them. Every finding cites the file/line or the probe output it was checked
against. Counter-probe: `probes/adv_asks.py` (run
`uv run python zzz_current_work/260816-opsis-meta/probes/adv_asks.py`); its
lines are cited as `adv A<n>`. `probe_asks.py` re-run and confirmed at 16
facts / exit 0 — the attack is on what those facts MEAN, not on whether they
print.

**Counts: 3 blockers · 11 majors · 8 minors.**

⊨-marked rulings are attacked only through their stated implementations and
consequences, per the charge.

---

## BLOCKERS

### B1 — the occurrence address has no carrier: the spine SHARES equal nodes, by identity *(axes A, B)*

**Claim under attack.** ASKS #1's probed fact "relative addresses assigned by
the PARENT … compose bottom-up and resolve back to their occurrence by plain
spine reads", and VISION §4 "Every drawn part is an address. The drawable unit
is the **occurrence**" / §7.1 "The capsule — a value standing somewhere (an
occurrence)".

**Evidence.**

- A parsed model does not have one object per occurrence. In
  `{"a": 1, "b": 1}` under `json.gbnf`, `Ws ''` is **one object reached 7
  times** and `QuotationMark '"'` **one object reached twice** (adv, shared-object
  run: `unique node objects 14`, `shared re-reaches 7`).
- Every walk driver splices that share. `ir/action/walk.py:161`: "A shared
  subtree (one object reachable twice) transforms once and splices everywhere
  it appeared"; `IrBottomUp._run` memoises `done[id(node)]` and skips
  (`walk.py:217-219`). The probe's own `_fold_regions` does the same thing
  (`probe_asks.py:107-109`: `if id(n) in out: continue`).
- The probe's parent-names-children step resolves a child's region by
  `ir_children.index(child)` (`probe_asks.py:85`) — `list.index` is **value
  equality**, and on this spine a node IS its payload. On `[1, 1]` that
  aliases three sibling slots (adv A6b): `JsonText` child 2 (`Ws`) → slot 1,
  `EndArray` child 1 → slot 0, `BeginArray` child 1 → slot 0.
- The probe's passing fact was never exposed to either problem: its resolution
  loop takes `tuple(deep.parts)[0]` at every level (`probe_asks.py:133-136`),
  so it walked a first-child chain only.

**Why it matters.** The address is the ONLY thing distinguishing two equal
occurrences, and the vision's entire co-selection story ("selection moves the
shared cursor", §4; the cursor's singularity, §7.5) rests on it. A region
family built the way the probe demonstrates hands one region to N occurrences
and, where it does not, hands the wrong one. This is not an implementation
slip — it is the spine invariant (`CLAUDE.md`: "A node IS its payload") meeting
a requirement the spine deliberately does not serve.

**Repair.** The ask must state the address contract as three lines, not one:
(a) an address is a PATH built top-down by the driver, each child's slot
supplied positionally by the parent — never recovered from the node, never
looked up by equality; (b) a region emission may not run on an id-memoising
driver (`IrBottomUp`, or the probe's fold) unless the share-splice is disabled
for it, because equal-and-shared is the normal case, not a corner; (c) a
repository test on a document with equal siblings and on one whose noise nodes
are shared (`{"a": 1, "b": 1}` is already sufficient) is part of the ask.

---

### B2 — the rule-keyed ceiling is formulation-SPECIFIC, and Q4's recommendation asserts the opposite *(axis C — "no privileged formulation")*

**Claim under attack.** VISION §4's ceiling ("Authored rows keyed by a
grammar's RULE NAMES, shaped like transpile tables … travelling as notation")
together with §1 ("JSON under **any** JSON formulation"), §9.6 ("each an
ordinary formulation through the standard pipeline, none privileged"), and
QUESTIONS Q4's recommendation: "free-standing plugs first (they compose with
**ANY formulation** of the language via rule-name keying + gates, like
transpile tables)".

**Evidence.**

- Rule names survive canonicalisation. `ir/grammar/canonical.py` rewrite 7
  folds case and `_`→`-` only; nothing renames. Renaming `value`→`val`
  throughout `json.gbnf` — a pure rename, same language — makes the two
  grammars canonically **unequal** (adv A1b: `canonical equal = False`; A1a
  confirms only the case fold is absorbed).
- Transpile tables are the cited precedent, and they refuse across
  formulations by construction: `compile/transpile.py:500-505` raises
  "row {name!r} names no rule of the source grammar" and
  `transpile.py:396-401` raises the same for a `Make` naming no target rule.
  Rule-name keying is precisely what makes a table formulation-BOUND.
- Worse, the ask never says WHICH names. The classes a ceiling addresses are
  synthesized from the CODEGEN grammar, and `_by_rule` keys
  `cls.__grammar__.name` (`transpile.py:353-355`). For `json.gbnf` that is 39
  rules, not the canonical 32, and includes `array-item`, `array-item2`,
  `char-arm2`, `exp-item`, `int-arm2`, `object-item`, `object-item2` — names
  minted by `passes.py`'s `_reserve_helper_name` / `_hoist_rule_arms`, which
  are not a stable public contract.

**Why it matters.** VISION §9.6 buys three simultaneous ceilings (md, JSON,
ABNF) specifically so no single-format renderer can be written by accident.
Rule-name keying reintroduces the same failure one level down: a ceiling is
written against one *formulation*, and a second formulation of the same
language — which §1 promises — gets nothing, or gets a refusal. Q4's stated
justification for the recommendation is the reverse of the fact.

**Repair.** Two parts. (1) State the key domain explicitly — canonical rule
name, codegen rule name, or a derived key — and if codegen, say that the
ceiling is coupled to `passes.py` naming and gate it. (2) Prefer the repo's own
precedent for not making an author restate what the grammar says:
`MapShape.for_entry(compiled, entry)` (`compile/templating.py:122-163`) takes
ONE name and DERIVES the other three from the binding, on the stated ground
that "asking for them is asking the caller to restate what the grammar already
says — and a restatement can disagree". A ceiling built the same way (a small
declaration, the rest derived) is the version that survives a re-formulation.

---

### B3 — ask #1 moves the one thing VISION §2 reserves for opsis into the engine *(axis C)*

**Claim under attack.** ASKS #1: "region-valued combinators whose render
**solves geometry** instead of line breaks". VISION §2 (⊨): "Only
**arrangement**, register, camera, cursor mechanics, session, and history are
natively opsis's."

**Evidence.** Solving geometry is arrangement, by any reading of the word. The
ownership line is a ruling; the keystone ask is ranked #1 and contradicts it in
its second paragraph. The contradiction is not cosmetic: it decides whether
`ir/` grows a screen-layout solver. `ir/text/layout.py`'s existing solver is
one-dimensional and text-only (`render(doc, width) -> str`, `Sheet` carrying
`width`/`col`/`parts`/`stack` — `layout.py:45-59, 318-331`); a geometry solver
is a different object with a different codomain, and it is the thing §2 says
opsis owns.

**Why it matters.** This is the first ask, the one VISION §9.1 says must land
before any room is built. If it is scoped wrong, the whole v1 order is wrong,
and the repo takes a screen solver into its strict tier.

**Repair.** Split at the line the vision already drew. The ENGINE half is the
**addressed emission** — an emit half whose parts carry their field/slot
address and their text extent. That is "sayable": it is a fact about the value
and its spelling, it is testable in the repo, and it is the same primitive asks
#6 and M2 need. The OPSIS half is the solve — where regions land, in what
coordinate system, at what width. Ranked that way, the keystone shrinks to
something fundable and stops colliding with §2.

---

## MAJORS

### M1 — probe #1 proves an addressed structural fold, not a region family; every design question the ask defers is the substance *(axis B)*

`Region` is `(addr, kind, parts)` — no coordinate, no extent, no width (adv
A7). The probe's five facts are: a fold runs, a first-child chain resolves,
MRO covers model classes, a non-node refuses, and `emit_parts` exists. None
touches geometry. ASKS #1 itself defers three questions "inside the ask" —
the coordinate contract, how hit/address emission composes with width solving,
and whether the ceiling's row table is `Transpiler`-shaped — and those three
ARE the family. "The mechanism holds on the existing machinery" is a true
statement about `IrTypeMap` dispatch and nothing else. As written, two
engineers implementing ask #1 produce two incompatible artefacts; that is the
axis-B bar, met.

### M2 — the "TWO geometry sources" are one source and one missing primitive *(axis A)*

ASKS #1(b): "the geometry has TWO sources that must meet in one contract —
structural regions from the spine walk AND textual spans from `emit_parts()`'s
tagged stream … a region family that ignores `emit_parts` re-derives text
geometry the model already owns."

`emit_parts` is per-node, shallow, and carries no offsets:
`model.py:502-537` returns `list[tuple[str | None, object]]` where the part is
"a literal string or the field's **unexpanded** value (str, model, or tuple)".
The root of `{"a": [1, true], "b": null}` yields **3** items
`[('ws', Ws), ('value', Object), ('ws2', Ws)]`; the whole document is **83**
items over 27 characters (adv A5a/A5b). The model does not own text geometry —
space_3 DERIVES it, by a second full walk accumulating `at += len(text)` and
closing each `Span` (`space_3/praxis/reading.py:295-327`).

So there is one structural walk and one derived textual walk, and the
derivation is opsis-side today. The probe's headline "emit_parts is the
textual-span source (3 tagged parts)" quotes the ROOT's arity as though it
characterised the document.

**Repair.** Name the primitive instead of the meeting: an emission that carries
`(field, part, start, end)`. Then there is one source, and ask #6 is the same
ask on the parse side (M7).

### M3 — `children()` order ≠ field order, and "the PARENT names its children" does not say which *(axis B)*

`GrammarModel.children()` returns bound-field values **in item order, not field
declaration order** (`model.py:411-425`, stated in the docstring). Measured:

```
JsonText _fields    ('value', 'ws', 'ws2')      children() [Ws, Object, Ws]
Object   _fields    ('begin_object', 'end_object', 'object_item2')
Object   children() [BeginObject, ObjectItem2, EndObject]
```

Every driver feeds `nc` in `children()` order (`IrBottomUp._descend`,
`walk.py:177-198`); the probe's fold zips `_names_of(n)` (declaration order)
against `tuple(n)` (declaration order). So the probe's addresses and the
engine's argument channel disagree on order, and an implementer following
"names live in the parent" has three defensible answers (field name in
declaration order, field name in item/document order, item slot index).

Second half: `children()` only covers `_child_attrs`. The field-tuple walk
sees 923 nodes where `children()` sees 830 (probe #2). A region family driven
by `children()` cannot draw what `children()` omits, while VISION §4 makes
"field-of-record" a drawable unit.

### M4 — the interior probe's evidence measures the wrong variable *(axis A)*

Probe #2: "the children()-walk sees 830 nodes, the field-tuple walk 923 with
**203 re-reachings** — the identity walk is a genuinely distinct product, not
a rephrasing of `children()`."

Re-measured under both definitions (adv A2a–A2e):

```
children()  walk: 830 nodes, 192 re-reachings   (1022 visits without memo)
field-tuple walk: 923 nodes, 203 re-reachings   (1126 visits without memo)
```

The `children()` walk has 192 re-reachings of its own; the probe counted
re-reachings only on one side. And the 830-vs-923 delta is the **child
definition** (`_child_attrs` vs all fields), not sharing. The conclusion may
well be right — sharing is real, and B1 depends on it — but the number offered
as proof proves a different thing. **Repair.** Measure sharing under ONE child
definition, memoised vs not; that is the identity walk's actual product.

### M5 — the altitude cost is misreported by ~5×, the expensive case is unmeasured, and the cited prior art is the wrong function *(axes A, E)*

ASKS #2: "altitude is three calls of existing surface (gbnf accepts json.gbnf
in 10 ms; abnf/ebnf refuse with real `UnsupportedConstructError`s in 83/35 ms —
cheap enough for eager per-subject probing, memoised per flavour identity)."

Three problems.

**The 10 ms is warm.** `probe_asks.main()` runs `probe_region_floor()` — which
calls `compile_text` on `json.gbnf` — before `probe_altitude()`, so GBNF's
self-grammar is already compiled. In a clean process, in flavour order:

```
cold abnf: refuses  79ms
cold ebnf: refuses  30ms
cold gbnf: accepts 486ms      total first subject: 595ms
warm abnf/ebnf/gbnf: 1 / 1 / 10ms
```

Warm probing is cheap, as claimed; the FIRST subject in a session costs ~0.6 s,
and the figure the ask publishes is neither the cold nor the warm number.

**One accept, two fast refusals.** Both refusals fail early (adv A3d: abnf on
`c.gbnf` refuses in 2 ms). The set contains exactly one accepting reader, so
"probe all candidate readers, keep every verdict" is priced on its cheapest
possible shape. The case the no-silent-pick rule exists for — several readers
ACCEPTING — is never measured, and at the DOCUMENT level (two grammars reading
one document) each accept is a full parse, not an early refusal.

**Wrong prior art.** The ask says "Today `praxis/reading.upward()` hand-probes
the three metagrammars." `upward()` probes nothing: it returns a declared pair
off an already-resolved flavour and says so — "Returns the pair, never a parse"
(`space_3/praxis/reading.py:370-380`). The probing lives at
`reading.py:123-128` ("Ask every pure grammar flavour; preserve every engine
answer") and it uses **`compile_text`**, not `parse_grammar` — a strictly
larger operation than the one timed.

### M6 — ask #4 names 3 of at least 6 moments, its distinctness fact is grammar-contingent, and its own "one way per task" line is the risk it leaves open *(axes A, C)*

**The composition fact is a source identity, not a discovery.**
`passes.py:255` literally reads
`return relax_non_semantic(hoist_arms(hoist_groups(ast)))`. Probe #4 asserts
output equality of the same expression.

**The moments are incomplete.** What the compilation room draws is
`_assemble_core` (`compile/__init__.py:590-628`): canonical AST →
`build_codegen_grammar` → **`concretize`** (conditional, vocabulary-dependent)
→ `compute_binding` → `synthesize` → `_fold_config`/`ModelFold`. The ask names
the three grammar→grammar passes and nothing after. A four-moment product
cannot draw binding or synthesis — which is where "structurally — classes
synthesized apart" (VISION §8's own truthful-claims example) lives.

**"There is something to draw" is per-grammar** (adv A4):

```
json.gbnf : m1!=ast True · m2!=m1 True  · m3!=m2 True   non_semantic=['ws']
vyx.gbnf  : m1!=ast True · m2!=m1 True  · m3!=m2 False  non_semantic=[]
c.gbnf    : m1!=ast True · m2!=m1 True  · m3!=m2 False  non_semantic=['ws']
chess.gbnf: m1!=ast True · m2!=m1 False · m3!=m2 False  non_semantic=[]
```

`chess.gbnf` has exactly ONE pass of three that changes anything; `c.gbnf`
declares `@non-semantic ws` and still relaxes nothing (its `ws` is not
nullable, so `relax_non_semantic` returns `ast` unchanged — `passes.py:230-232`).
The probe only asserted `m1 != ast or m2 != m1`; it never checked m3. So the
room must draw a no-op moment honestly, and the ask should say so rather than
claim distinctness.

**The doctrine risk.** "either export the passes or, better, a pipeline-trace
product that runs the standard pipeline and retains each moment. No second
pipeline: one way per task." A trace product that *re-runs* the passes is a
second composition of them, and it will drift from `_assemble_core` the first
time a pass is added. The ask permits that version. The only "one way"
formulation is: `_assemble_core` itself routes through the retaining product.
Say that, or the sentence disclaims a risk it then allows.

### M7 — #5, #6, #7 (and M2) are one ask, and splitting them costs the thing they are bought for *(axis D)*

All four are the same shape: a fold or a run held a correspondence and the
product dropped it.

- `Transpiler.apply` returns only the product (`transpile.py:273-285`); the
  walk is `IrBottomUp`, which has source node and transformed children in hand
  at every step (`walk.py:216-245`).
- `SpanEntry` is `key: str`, `value: str` — text, not offsets
  (`templating.py:166-172`), built by a fold whose fields are
  `FieldFold(bind.item, "text", name, …)` (`templating.py:516-526`), i.e. spans
  captured from positions the engine knew.
- `PdaKernel` runs the steps and keeps none; `__slots__` is closed
  (`parsing/pda/runtime/kernel/kernel.py:158`).
- Emission drops offsets (M2).

Four separate asks produce four record shapes. The cursor then has to wash
across them — which is exactly the co-selection VISION §5 calls "what makes the
4-D object legible" — and four independently-designed provenance records will
not compose. **Repair.** One ask: *products carry provenance — a fold or run
that knew a correspondence hands it back*, with one record vocabulary, one
gate, and TWO explicitly named directions (parse-side offsets for #5/#6,
emit-side offsets for M2; they are different walks and must both be in scope).
Rank it where #5 currently sits; it then subsumes three entries.

### M8 — the orbit is defined by an equality that is neither language equality nor defined for values *(axis A)*

VISION §5 (⊨ section, attackable implementation): "the ring is the
**equivalence class under lexic's canonical equality**, each membership
carrying its witness". ASKS #2 repeats it and probe #2 reports "orbit
membership IS canonical equality (json.gbnf == json.abnf)".

- `canonicalize(ast: IrAst) -> IrAst` (`ir/grammar/canonical.py:316`) is
  grammar-only. There is no canonical form for a VALUE, so a value's orbit
  (§5's own example: "its notation, its payloads, its dump, its document
  spelling under a grammar") has no such equivalence at all — and the document
  spelling is a `str`, whose relation to the value is not an equality in any
  case.
- For grammars the equality is name-sensitive (B2's adv A1b) and factoring-
  sensitive: `json.gbnf` is canonically unequal to `json_arr.gbnf` and to
  `json_ws.gbnf` (adv A1d/A1e).
- The one positive result is fixture co-authorship, not computation: both
  `json.gbnf` and `json.ebnf`/`json.abnf` define the same 32 rule names, listed
  identically (adv A1c prints both sets).

**Repair.** State the membership relation per subject kind — grammar: canonical
equality, with the name-sensitivity written down; value: spine equality plus a
per-form witness; text: "reads to the same value under the same reader" — and
stop presenting one relation as covering all three. The ring is still
computable; it is just three computations.

### M9 — ask #2 is four asks running on two mechanisms, and the policy half is opsis's by the vision's own line *(axes D, E)*

Reduce the four queries to their mechanisms: **altitude** (probe every reader,
keep every verdict), **orbit's grouping** (attempt each of the four export
forms, keep the witness), and **laterality's** "which flavours can spell an
AST" / "whether a reducer's domain covers a grammar's rules" are all
attempt-and-record. **Interior** is walk-and-count. So: one verdict-keeping
prober and one walk, not four surfaces.

And the prober's *policy* — which candidates, in what order, memoised how,
what a kept verdict record contains, when it is re-run — is session concern,
which VISION §2 assigns to opsis ("session" is in the opsis list). The strongest
opsis-side case: `space_3/praxis/reading.py:123-128` is ten lines, already
correct, already keeps every verdict, and moving it into the engine buys a
name rather than a computation. What the engine genuinely lacks is a **verdict
record type** so that verdicts from different attempts are comparable and
drawable — today each attempt yields either a product or an exception, and an
exception is not a value the graph can carry.

**Repair.** Name the engine half as the record, leave the candidate policy
opsis-side. If the engine is to own a candidate list, that list is a registry,
and a registry of "the readers we happen to ship" is the privileged-formulation
hazard in a new costume — argue it explicitly or drop it.

### M10 — Q3's recommendation regresses the measure the precedent it cites actually landed on *(axis B)*

Q3 recommends "character units in the algebra, pixels only at the leaf weld —
same discipline the space_1 railroad landed on."

The railroad's unit is not characters. `space_3/praxis/reading.py:331-333`:
`columns(line)` — "How many terminal columns this line occupies, **wide glyphs
counted twice**", summing 2 for East-Asian `W`/`F` — and `space_3/opsis/measure.py`
imports exactly that function, with its module docstring arguing the point
("Every other surface here is measured in columns and rows"). Meanwhile
`ir/text/layout.py:61-67` measures with `self.col += len(text)` — code units,
wide-glyph-blind. A region family landing "beside `IrDoc`" inherits the blind
measure, and `resources/ground_truth/japanese.gbnf` is already in the corpus.

Also `measure.py` uses fractional units (`VGAP = 0.25`, `REACH = 1.1`), so the
prior art's "characters and rows" is not an integer cell grid either.

**Repair.** The coordinate contract must name the measure FUNCTION and say
whether it is integral, not just the unit word. "Characters" resolves to two
incompatible things inside this thread already.

### M11 — Q6's "make it real when the second reading first occurs" is contradicted by the engine's own identity function *(axis C)*

Q6 recommends funding relation-instance directives/vocabulary "in the graph
schema from day one … make it real when the second reading first occurs".

The engine already treats them as part of an artefact's identity, and says so
in a comment: `compile_text`'s memo key is
`(content stem, flavour key, vocabulary, directives)` with "The directives are
part of WHAT WAS COMPILED, so they key the memo too: without them one source
compiled two ways would hand back the first" (`compile/__init__.py:673-681`);
`compile_from_path` keys the same tuple (`:855-862`); and
`CompiledGrammar.bind(tokenizer)` returns "a **NEW** artefact"
(`artifact.py:204-216`).

So a graph that content-addresses a reading without them will merge two
distinct artefacts into one node the first time anyone passes `Directives(...)`
or binds a vocabulary — which VISION §3 makes routine, since a tokenizer plug
is listed as "a new artefact — a second subject". The recommendation should be
*fund it now*, on the ground that the engine already did.

---

## MINORS

1. **Ask #3 is right, and applies a standard ask #4 does not.** `export_value`
   is genuinely absent from `lexic.compile` (verified: never imported there;
   it lives in `compile/payload/__init__.__all__:20-27`). But ask #4's premise
   "only the fused `build_codegen_grammar` is importable at the root"
   understates the seam: `build_codegen_grammar`, `compile_ast`, `canonicalize`,
   `concretize`, `compute_binding`, `synthesize`, `encoding_registry`,
   `segmentation_tokenizer`, `rule_closure`, `RuleBinding` are all reachable as
   `lexic.compile` attributes and none is in `__all__`. `compile_ast` in
   particular is a primary documented entry (its own module docstring calls it
   "the IR-born twin of `compile_text`"). If ask #3 is "export it", say the
   sentence covers the family, or the seam gets repaired one symbol per effort.

2. **The wiki's own citation breaches the layering rule.**
   `.wiki/lexic/public-api.md:79` documents `export_value` as public API with
   `compile/payload/__init__.py` as its home — a module `CLAUDE.md` says is not
   importable from outside the package. Ask #3's repair should include the wiki
   line, not just the `__init__`.

3. **Ask #2 cites `encoding_registry` as an existing surface**; it is
   importable from `lexic.compile` but not exported — finding 1's family.

4. **Ask #2 attributes altitude probing to the wrong function** — see M5's
   third part. `upward()` promises "never a parse".

5. **Probe fact "#1 a non-node … refuses" is too loose to be a refusal test.**
   `probe_asks.py:150` catches `(LexicError, TypeError, AttributeError)`, so a
   bare `TypeError` would have printed `ok`. The actual raise is `IrKeyError`
   (an `UnsupportedConstructError` subclass) from `IrTypeMap.resolve`. Narrow
   the except to `LexicError` or the fact does not test what it says.

6. **The raising default is unreachable for nodes, and the register promises
   otherwise.** Every synthesized class subclasses `IrNamedTuple`, so the MRO
   floor always answers — the default fires only for a non-`IrSelf`. That is
   ADVERSARIAL_MOCK M15's repair landed correctly, but VISION §4's "an
   unauthored kind draws the refusal's own words" is then true only for
   non-nodes. Say which, so the register does not draw a refusal that cannot
   occur.

7. **Ask #8 calls `lexic.generate` "already funded and gated", and it has a
   silent fallback.** `_Generator.run` returns `""` for an unknown rule name
   (`generate.py:126-131`) and `alternation` returns `""` for an empty body
   (`:133-138`) — no refusal, no words. A strata door built on it draws an
   empty sample indistinguishably from a generated one. (The seed half of the
   claim holds: `generate(..., rng=...)` takes an injected `random.Random`,
   `generate.py:145-163`.) This is arguably its own small ask.

8. **Every ask that adds a module owes a `CLAUDE.md` line in the same change.**
   The project-layout block is exhaustive and drift-checked by
   `tests/integration/lexic/invariants/test_doc_drift.py`. Ask #1's region
   family and any trace module land under that gate; the asks do not note the
   cost, and "beside `IrDoc`" would put a non-text family under `ir/text/`,
   whose annotation reads "How characters and documents are spelled".

---

## What survived

Attacked and could not fault:

- **Ask #3's core fact.** `export_value` really is absent from the public seam:
  not imported in `compile/__init__.py`, not in its `__all__`, not an attribute
  of `lexic.compile`. The deep import is the only route. Checked expecting the
  usual "it's reachable, just unlisted" and it is genuinely not there.
- **Ask #6's fact.** `SpanEntry` really carries text, not offsets — two `str`
  fields, `templating.py:166-172`, docstring "both as raw document spans".
- **Ask #4's composition fact, at source strength.** `passes.py:255` IS
  `relax_non_semantic(hoist_arms(hoist_groups(ast)))` — stronger than the
  output equality the probe asserts. (Its consequences are M6.)
- **The `IrDoc` precedent, exactly as stated.** Doc nodes really do double as
  action-body templates: `IrGroup.eval`/`IrNest.eval` rebuild around the
  evaluated interior (`layout.py:221-252`), `IrLine.eval` is identity data
  (`:186-190`), `IrDocConcat`/`IrDocJoin` are the doc-tier sums
  (`:264-315`), behaviour is intrinsic (`layout`/`scan`), and the driver is a
  flat explicit-stack loop (`render`, `:318-331`). `IrFlavour.apply` really does
  render a doc-valued emission width-aware (`flavour.py:156-169`). The
  analogy's premise holds; only what is inferred from it (B3, M1) does not.
- **Ask #7's grounding.** `PdaKernel` is a public export
  (`lexic.parsing.__all__`, `parsing/__init__.py:164, 278`) with closed
  `__slots__` (`kernel.py:158`) and no public step hook — the ask is real, and
  deferring the machine room to clone frames until it lands is the honest call.
- **The MRO floor over model classes.** Every synthesized class lands on the
  `IrNamedTuple` row; unknown model classes need no registration. Verified
  independently of the probe.
- **"The spectacle already folds spans from `emit_parts`".** True:
  `space_3/praxis/reading.py:295-327` opens a `Span` per model, accumulates
  `at += len(text)`, and closes it on the way out. (What it does NOT show is
  that the engine owns those offsets — M2.)
- **`compile_text`'s by-value memo keys.** Attacked looking for an identity
  hazard the graph would inherit; the keys are by value with the `id()`
  unsoundness argued in-place (`compile/__init__.py:670-681`). It is the graph
  side that has the gap (M11), not the engine.
