# opsis — VISION

The position the general instrument is built on, distilled from the whole
2026-08-07 → 2026-08-14 thread: the space_1/2 demonstrators, the space_3
probe round (`probes/probe_space3_design.py`, 10/10), the adversarial round
(`probes/ADVERSARIAL_ROUND1.md`), and the transpilation resolution that
ended with lexic itself growing `transpile()`. Present tense. Claims here
are either **built and measured** or **probe-ruled** (attacked and
surviving); nothing is aspiration dressed as fact.

## 1. What opsis is

**Opsis is lexic's screen-flavour.** A flavour is metadata + grammar +
reducer + emit actions; GBNF's emit actions spell a canonical value as text —
opsis's presentation tables spell a value as addressed regions. Same dispatch
discipline (open tables, MRO, raising default), same neutrality rule (the
subject stays untouched). The parse-back half of the flavour is the gesture
layer: a click reads an address out of the spelled surface; an edit
round-trips through reconstruction or re-reading. Opsis does not compute;
lexic computes; opsis spells and points.

**There is no opsis without spectacle — and the spectacle is the computation
made visible.** Ornament dies; motion of truth lives. A parse watched along
the text axis, a derivation stack glowing under a cursor, a refusal marking
the exact character where derivation died, a grammar re-spelling itself
through another flavour, a document crossing into another language while its
gates are watched: spectacle with zero decoration, because the motion IS the
event. The register rules protect legibility, not modesty: nothing breathes
while idle; motion communicates traversal, recomputation, or a changed
arrangement; a third axis is earned only when a third independent meaning
exists after x and y are spent.

**The doctrine runs both directions.** Opsis teaches lexic's rules at the
screen — and when opsis finds a gap in lexic, lexic is fixed, never designed
around. This is not a slogan; it is the transpilation story (§7): the
instrument's design pressure produced `IrMapping.children()`, `IrEach` over
mappings, the model-layer walk, and `lexic.compile.transpile` — engine
surface that now ships to everyone.

## 2. The node answer

**IrSelf is not a node — it is a value**: kind, payload, children, rebuild,
and deliberately nothing else. No name (names live in the parent), no
position (paths do), no identity beyond content (IrNone is one singleton in
ten thousand slots). The drawable unit is the **occurrence**: a value
standing in a relation to a context — field-of-record, element-of-sequence,
subject-of-reading, attachment-of-port, product-of-invocation.

What IrSelf guarantees is a **uniform protocol** — ask its kind, walk it,
rebuild it, dispatch it — and what each kind deserves is a **particular
shape**, authored as a table row that makes a claim about what the thing IS.
Uniform protocol, particular shape, connected by dispatch. Limit Theory made
the shape uniform and died of genericity; the opsis-4 ladder privileged one
structure and could not say "transpile"; both failures are the two halves
trying to do each other's job. An unauthored kind draws the raising default's
own words — coverage refusal is visible, never mush, never blank.

## 3. The session is a graph

**Storage is a typed graph; every earlier shape is a projection of it.**
Nodes are SUBJECTS (text, grammar-value, compiled artefact, model value,
reduced value, tokenizer, reducer, flavour, template, policy record),
content-addressed — a subject's identity is its content digest, which gives
equality for free and kills a measured class of duplicate-node bugs. Edges
are RELATION INSTANCES (read, reduced, compiled, transpiled, bound,
projected, loaded-from), each carrying its compile parameters (directives,
vocabulary) and its **verdict + cost + witness**. The strata/ladder is one
derived linear path through this graph, not the storage — the adversarial
round showed the list-as-storage producing concretely wrong answers (ring
growth, re-rooted climbs, reused window ids), and every repair is the graph.

The graph is the minimum, not a luxury: two documents under one grammar, one
document under two grammars, a grammar under two metagrammars — today these
are unreachable or unrepresentable; under the graph they are just edges, and
the lane (not the graph) is what makes them *read* right: a peer drawn
beside, a hierarchy above.

**Facets are projections of one subject**, each with its own coordinate
system, none detachable, all re-derivable — regions with hairline seams,
never windows. **Cursors live on the subject** — time, selection, hover —
and every facet renders them in its own coordinates. Native text selection
is a cursor source like any other: select characters and the smallest
covering occurrence co-selects across every facet, including across the
reader/read boundary. Windows exist only as the pinned exception, for
simultaneity a tiling cannot express. A facet under pressure degrades by
deriving less, never by clipping.

**Travel is five moves and BACK is a history stack, never a graph edge**:
cast-up, cast-down, enter-room, back, map. In a graph you can arrive at one
room two ways; "the edge I crossed" and "where I just was" are different
questions and only the second is what a hand means by back. Docking an
attachment is not travel — you are standing in the reading and a product
facet appears; entering its room is an explicit cast.

## 4. Rooms and the map

**Rooms are the particular shapes; the map is the uniform protocol** — the
synthesis the adversary attacked and could not fault. A relation kind gets a
ROOM (its facet set): the **reading room** (the five facets, unchanged — the
one thing that works, and the redesign costs it nothing), the **compilation
room** (the four moments, binding, machine, verdicts), the **transpile room**
(§7), the **value room** (the IR node-graph, drawn as a real graph, for any
lexic value), the **artefact room** (family + witnesses + load-back), the
**generation room** (mask/push/accepts — deferred, §9).

**The map is the landing** — the strata generalized, reached by its own
gesture and passed through, not lived in. Its rows are **roles, not kinds**:
a document lane, a reader lane, a value lane, an artefact lane, and the
instrument's own lane. Artefact families fold by default into one capsule
per subject and expand only in the artefact room — never five artefact nodes
per subject on the map. The map frame sits in the perf gate with its own
budget at the subject count the design targets; a budget nothing measures is
a wish.

**Licences are computed, in two tiers, and the screen says which.** A cheap
predicate (type/shape) runs eagerly and drives what the map OFFERS; an
expensive witness (export + load back; the measured cost is ~900 ms and
790 KB per subject) runs on entering the room, cached against
(subject, generation), drawn as pending until it lands. Every witness loads
through a digest-suffixed unique module name — lexic's own payload-sidecar
discipline — never `import_module(stem)`, which was measured returning the
wrong subject's module.

## 5. Ingress

**A file becomes a subject via its own reader; relations are offered, never
forced.** serve.py takes ANY set of files; no files → the map with doors to
fixtures and generated/. `.flavour.ir` → a live flavour; `.ir` → a typed
value; a twin `.py` → `parse_module` (a grammar parse of the source, no
import); a payload `.py` → import — **last, and only on an explicit
gesture**, with the honest words on screen: identifying a payload module
means running it.

**Probe all candidate readers; never first-match.** The measured failure: an
EBNF file with no EBNF-only construct silently read as ABNF — the instrument
doing the one thing lexic refuses to do, two derivations, one silently
chosen. When more than one reader accepts, the map draws the subject with
two offered read relations and the user casts one — which is "one document
under two grammars" arriving for free. Refusals speak per candidate, in the
engine's words verbatim, never a synthesized "could not identify this file".

**Slow ingress arrives pending.** Any subject whose ingress is not sub-100 ms
(the smallest tokenizer fixture measures 8.4 s) is built on a worker, drawn
as a pending node, promoted when it lands — the same protocol as the
background engine run. Pending is drawn, never blank.

## 6. Grammar is the ground truth

Embodied three ways, all running: the reader facet shows the grammar itself
— for the metagrammar, spelled by its own emitter; **edits are re-readings**
— text is primary, the model is only the grammar's account of what the text
says, so a commit splices text and parses again, and every facet re-derives
or nothing changes; **refusals speak the engine's words**, verbatim, with
the measured frontier where the route can measure one.

The reach this buys: opsis carries **every format lexic can parse**. The
no-privileged-formulation rule, said at the screen: generic presentation
rows give any grammar's models an instant viewable, addressable, losslessly
editable surface; authored per-domain rows are the ceiling, loaded like
flavour manifests. The grammar becomes the interface contract.

## 7. Transpilation — both planes, both real

**The grammar plane is proven and nearly free.** canonical(json.gbnf) ==
canonical(json.abnf); gbnf → abnf → back EQUAL; gbnf → ebnf → back EQUAL.
The transpile room over grammars is the room that makes "grammar is the
ground truth" visible: peer lanes, canonical-equality witness, parse-back.

**The document plane routes through MODELS, and lexic now owns it.** The
value plane was measured lossy (booleans collapse to ints, floats refuse,
duplicates refuse — a reduction is a *reading*, free to drop what it does
not need) and is demoted forever to an optional parity witness. The model
plane is the lossless account — spelling kept, distinct rule classes,
duplicates surviving — and `lexic.compile.transpile` is the mechanism:

    text_A ──A.parse──► A-models ──T──► B-models ──.to_text()──► text_B

Only T is authored, and **T is pure data**: an `IrMap` of per-rule bodies
keyed by the source grammar's RULE NAMES (`Make` / `Spelled` / `Flat` /
`Split` / `Is`), baked against the two compiled artifacts, gated on every
run — completeness, membership, fidelity — and refusing its stated domain
in words. One table serves ANY formulation of the source language (the same
table runs json.gbnf and json.abnf); the table travels through the notation
as text; the target's spelling discipline lives in the target's grammar, so
escaping and layout are the grammar's problem, not an emitter's.

For opsis this means the transpile room has a **document half**: a source
document, a target grammar, a table — itself a subject with a value-room
surface, editable as data — and the run drawn as the model-plane crossing
with its three gates as visible verdicts. The blockers the adversarial round
ranked (`IrMap` is a leaf; no escaping without a flavour; cut data
transpilation from v1) were lexic gaps, and lexic fixed them. That is §1's
doctrine, executed.

## 8. Both engines, both clocks

One parse, two observations. The product always comes from the engine's own
composition — no route flag exists near the parse API. The instrument
additionally runs the road not taken, in the background: on a healthy PDA
route, an explicit Earley run yields a **drawn parity verdict**; on a
resolver route, the PDA's probe-fork position marks **where the fast road
stops** — the inversion is the content. The visualization switch enables
only when the background run has finished; pending is drawn, never blank.
Resolver chips promise only what the engine promises: the PDA's "first" and
Earley's "first" are not the same first, and a chip is named for what it is.

## 9. Attachments, and the one that is code

**Attachments are ports on relation edges.** Docking a reducer on a reading
adds a product node with its own facets. Reducers, flavours, templates,
tokenizers, transpile tables are VALUES — probe-proven to project, travel as
notation, and reload live — so they are authored in the value room
(slot-based editing of IR structures, offers from the algebra, never a
textarea), loaded from files, or lifted from a parsed document. A
**resolver is CODE** — the one attachment that is not a value; a registry of
named deciders, and a drawn refusal for arbitrary ones. Honest boundary,
said on screen.

`lexic.generate` is the cheapest, most legible gesture in the engine — "show
me a document this reader accepts" is one call — and jumps the queue if
anything else slips. The generation room proper (tokenizer mask/push/
accepts) is deferred: its smallest fixture costs 8.4 s to ingest and cannot
be gated on a fresh clone (fixtures are fetched, never committed).

## 10. The stack, settled

In-process with lexic (subjects ARE IrSelf; a data seam is the thrice-killed
thing); Python; immediate mode (frame = render(session); modification is
reconstruction); and a split leaf: a **real text plane** (the browser's text
engine — selection is the litmus a canvas can never pass) welded to a
**drawn structure plane** by one computed geometry. The wire between
instrument and leaf is a render protocol, not a serialization layer: one
route, emitted frames one way, addresses the other; subjects never cross.
Leaf code lives as leaf code (versioned artifacts); frame content is emitted
data; that line is what makes the blob offence structural. The adversarial
round attacked the wire and found nothing — every finding is server-side.

**Memory at graph scale**: `generation` is per-subject; a frame carries the
generations of the subjects it draws. Lazy: everything except the cheap
ingress predicate. Evicted: derived caches for subjects not visible in the
current room, LRU of ~3. Never evicted: the graph itself, and lexic's
compile cache (not ours to touch).

**Praxis on the spine is its own funded slice, later.** "The value room
draws opsis's own records" is narrowed until then to what is already true:
it draws any lexic value, and the instrument's policy record — which is a
text with a grammar, and whose saving APPLIES it (the ring closes).

## 11. What v1 is

Must contain, ranked: (1) the graph as storage, the ladder as projection;
(2) ingress that probes all readers and never picks; (3) the reading room,
unchanged and green; (4) the map as a role-laned landing, artefact families
folded, its frame in the perf gate; (5) the transpile room — grammar half
first, document half on `lexic.compile.transpile`; (6) the value room over
any lexic IrSelf; (7) five travel moves and a history-stack BACK; (8)
two-tier licences with digest-named witness loading.

Deferred, each with its reason recorded: the artefact room (soundness fix
first, cost second); the generation room (ingress cost, un-gateable
fixtures); praxis onto the spine (its own slice, after the graph);
directives/vocabulary on relation instances (needed before two readings of
one pair coexist, not before v1). Nothing is deferred silently: a deferral
is a drawn refusal or an absent door, never a broken one.

## 12. Implementation state — 2026-08-14

space_3 has landed all four graph migration steps without changing
the reading-room wire: content-addressed subjects and reading equality;
session-lifetime window IDs; `Graph` storage with the ladder derived from
rooted lineage; and a server-owned `Instrument` with relation-keyed room
presentation, watched routes and window layers. The ring is a policy
relation, never a ladder insertion.

Popup fidelity is gated as part of the unchanged reading room: pin and rail
carry space_1's content and controls; cloned/popped facets use scoped real
text and controls; overlapping windows have independent visual stacks; and
popped Relations retains its full selector and sliders.

The map now uses cheap artefact licences and defers strong witnesses to room
entry. Twin source is cross-checked through Lexic's existing
`verify_module()` contract. The complete composed map is in the performance
gate at 20 content-distinct subjects and measures 2.0 ms on the recorded run;
the full gate remains green.

This slice required no Lexic change. That is an ownership result, not a
constraint: graph/session/frame lifetimes belong to opsis, while the engine
already supplied the required verification primitive. The earlier
model-plane transpilation gap did belong to Lexic and remains fixed there.

Pure all-reader grammar ingress and explicit offered relations are now
landed and gated. Still open, in dependency order: generalized file-subject
ingress, with payload imports last and explicit; pending worker subjects;
then the remaining rooms and surfaces. The detailed evidence and exact gate
measurements live in `space_3/LEDGER.md`.
