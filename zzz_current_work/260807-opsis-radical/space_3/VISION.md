# space_3 — the general instrument

The vision for the general implementation: what opsis becomes when it stops
being a parsing visualization with extras and becomes the instrument for
everything lexic is. Distilled from the space_3 probe round
(`../probes/probe_space3_design.py`, 10/10; `../probes/POSITION.md`) and the
adversarial round (`../probes/ADVERSARIAL_ROUND1.md`), with blocker status as
of 2026-08-14. The foundation position (screen-flavour, occurrence, register,
the stack) is `../VISION.md` and is not restated here.

## 1. The charge

Parsing — what space_1/2 cover — is a tiny part. The general instrument
carries:

- **Compiled files as first-class input**: grammar twins, payload modules,
  values in any of the export flavours — everything under `generated/`, plus
  notation files. Any file lexic can read becomes a subject.
- **Full IR representation**: any IrSelf — grammar AST, reduced value, model,
  reducer, flavour, tokenizer — drawn as a real node graph, viewable and
  addressable, not just the grammar of the current parse.
- **Compilation itself represented**: the pipeline's moments (passes, binding,
  synthesis, tables), not just its product.
- **Transpilation**: between grammar flavours, and for documents between one
  grammar and another.
- **Pluggable attachments, including NEW ones**: tokenizers, reducers,
  deciders, templaters — docked, authored, lifted — not just the shipped set.
- **Self-representation**: opsis showing opsis, the ladder closing into a
  ring.

The standing failure mode this charge exists to break: rendering everything
as a function of what already exists. Placing a twin, an IR value, or a
compiled payload on the level of the parser IS the mistake. The parse room is
one room.

## 2. The model

**The session is a typed graph.** Nodes are SUBJECTS (text, grammar-value,
compiled artefact, model value, reduced value, tokenizer, reducer, flavour,
template, policy record). Edges are RELATION INSTANCES (read, reduced,
compiled, transpiled, bound, projected/exported, loaded-from), each carrying
its compile parameters (directives, vocabulary) and its verdict + cost +
witness. Subjects are content-addressed — identity is the content digest,
which gives equality for free. The strata/ladder of space_2 is one derived
linear path through this graph, **not the storage**.

The graph is the minimum, not a luxury. Measured today: two documents under
one grammar are unreachable by any gesture; one document under two grammars
is not representable (`turn()` discards the losers); a grammar under two
metagrammars is not representable (`read_up()` returns one). Under the graph
these are just edges.

**Rooms are the particular shapes; the map is the uniform protocol** — the
synthesis the adversary attacked and could not fault. A relation kind gets a
ROOM (its facet set); the map holds every subject under one node protocol.
Uniform node soup died (`space/`, `whole/`); the privileged ladder died
(opsis-4); each half gets the job it can do.

**Ingress is typed by what the file IS; relations are offered, never
forced.** serve.py takes ANY set of files; each becomes a subject via its own
reader; licences are computed, and the map OFFERS what they license. No
files → the map is the landing, with doors to fixtures/ and generated/.

**Attachments are ports on relation edges.** Docking a reducer on a reading
adds a product node (the reduced value) with its own facets. Attachments are
VALUES — reducer, flavour, template, tokenizer, transpile table all
probe-proven to project, travel as notation, and reload live — except the
**resolver, which is CODE**: a registry of named deciders, and a drawn
refusal for arbitrary ones. Honest boundary, said on screen.

**Opsis is in the graph.** The policy record, register, and arrangement are
subjects; the ring is an edge pointing at the instrument itself; saving the
policy record APPLIES it.

**The wire stays.** One route, frame out, gestures in. What changes is what a
session HOLDS (a graph, not one Reading) and what the map and rooms draw. The
adversarial round attacked the wire and found nothing — every finding is
server-side.

## 3. What the probes established

All ⊢ claims have passing probes in `../probes/`:

1. ⊢ A reducer is data end-to-end (notation → repr fixpoint → parses live),
   and editable in place (swap one entry, compile under the edit).
2. ⊢ A whole flavour is pure data — zero IrLambda in shipped emit actions —
   and the decoded flavour emits and compiles.
3. ⊢ Attachment values project to payloads and pass the fixpoint gate
   (Reducer, IrTokenizer).
4. ⊢ One reading yields the whole artefact family — twin, grammar payload,
   model payload, dump payload, reduced payload — written, imported back,
   witnessed.
5. ⊢ A resolver is code; everything else is a value.
6. ⊢ Grammar transpilation is real and nearly free: canonical(json.gbnf) ==
   canonical(json.abnf); gbnf→abnf→back EQUAL; gbnf→ebnf→back EQUAL.
7. ⊢ Document transpilation routes through the MODEL plane, and lexic now
   owns it (§4, RESOLVED-1).

## 4. Current blockers

Status of everything the adversarial round raised, in its severity order.

Ownership follows the general doctrine: session topology, navigation, room
state and frame budgets belong to opsis; parsing/transformation primitives
belong to lexic. A fix moves into lexic only when the engine contract is
missing, and then carries repository tests. This slice found no new engine
gap; it replaced weaker opsis behavior with lexic's existing public contract.

**RESOLVED-1 — data transpilation.** Was two blockers: the value plane is a
lossy pivot (booleans collapse, floats refuse, duplicates refuse), and a
pure-algebra data emitter was unauthorable because `IrMap` was an
`IrLeaf` the walk could not see. Both were lexic gaps and lexic fixed them
(committed `a4ec6fe`): `IrMapping.children()`/`rebuild()`, `IrEach` over
mappings, `IrBottomUp` over model trees, and `lexic.compile.transpile` —
rule-name-keyed pure-data tables, baked against the two compiled grammars,
gated per run (completeness, membership, fidelity), one table serving any
formulation of the source. The value plane is demoted to an optional parity
witness, forever. The circular-witness minor is also dead: ex16's target
grammar is authored before the transform.

**RESOLVED-2 — graph storage and session lifetimes.**
`praxis.Graph` now holds content-addressed text subjects, typed reading/policy
relations and rooted lineage edges. `Reading.__eq__` is content-derived;
`Session.climbed` is a projection; the ring is a non-lineage relation; window
ids are session-lifetime. The three measured failures are resolved and gated:
no ring growth, no post-ring re-root, no reused window id. Room presentation
is keyed per relation; the socket owns one explicit
`Instrument` holding its Session and relation-keyed watched/routes/window
work; policy is session-wide. Server instances and rooms are isolation-gated.

**RESOLVED — compact popup and spine-hand parity.** Occurrence pins use the
reference's 62%-viewport text measurement, 280×90 minimum, and
content-driven height; rail pins use track +52×58 under 72% viewport caps.
Their 27/29 px chrome and 12/11 px copy are registered frame metrics, not
leaf guesses. The model spine washes the exact hovered row. Live comparison
holds at 280×97 for `true` and 376×91 for `member`.

**RESOLVED — ingress no longer picks or executes to identify.**
`probe()` asks GBNF, ABNF, and EBNF independently, keeps every machine or
exact refusal, and ambiguity becomes explicit offered relations plus a cast.
`probe_file()` now routes by extension through the applicable pure readers:
`load_ir`, `load_flavour`, and `parse_module`. Python retains that parse answer
and an honest payload offer; only `import_payload()` executes it, under a
content-digest module name, then requires an IR value or bound model class.
All are gated. `Landing` subjects and every retained answer now occupy the
server map; payload import is a visible explicit cast. File probes run on
workers, enter as PENDING, and promote in place without blocking the
instrument.

**RESOLVED — the full artefact family is retained and witnessed.**
The map computes only cheap offered forms. The artefact room runs `keep()`
against (compiled identity, subject, generation), bounded and cached on a
worker. Its twin is read through lexic's existing `verify_module()`
self-grammar cross-check, not merely `ast.parse()`. Twin, IR notation, grammar
payload, model payload, and dump payload are written, loaded back through
digest-suffixed unique runtime module names, and witnessed; those temporary
module names are removed after use. The reduced slot is retained honestly as
`not licensed` when no reducer is docked. Cold work is drawn PENDING and
promoted in the same room when complete.

**RESOLVED-4 — the map has a measured budget.** The map no longer runs
`keep()`; it offers cheap licences and defers witnesses to the room. Depth
bands are content-cached, derived caches are bounded, and the composed map
frame is gated at 20 content-distinct subjects. Measured this run: 2.0 ms
against the 20 ms budget (the former hot `strata()` cost was ~55 ms).

**RESOLVED-5 — slow ingress does not freeze the instrument.** File ingress
runs outside the render/request path. Every file subject arrives PENDING,
retains a stable content address, and is promoted when its worker completes;
the server map refreshes while pending without giving play state to the leaf.
The gate uses a deliberately slow reader to prove the pending frame is
visible before promotion. The generation room remains deferred because its
fixtures are fetched and therefore cannot be gated on a fresh clone.

**RESOLVED — praxis is on the spine without corrupting its lifetimes.**
Reading, Facet, Session and Rung remain application owners where mutation is
real. `praxis.value.snapshot()` projects their complete current topology —
including subjects, relation instances and policy — into immutable
`IrNamedTuple` records. The strata has an instrument-value door, and the same
generic value room that draws every other `IrSelf` draws this snapshot. The
gate proves an old snapshot does not mutate when its Session advances.

**OPEN-7 — remaining unfunded surfaces** a general implementation must cover:
`.bind(tokenizer)` (a new artefact = a second subject, no relation kind
exists); directives/vocabulary on the relation instance
(without it, two readings of one pair are indistinguishable nodes); the
template room's actual surface (`Spec`/`Keep`/`SpanPair`);
duplicate-key refusals explained on screen; resolver chips named for what the engine promises
(the PDA's "first" and Earley's "first" are not the same first).

`lexic.generate` is now funded: a strata door generates a deterministic
sample, requires the same reader to accept and byte-identically re-emit it,
shows otherwise-invisible whitespace explicitly, and offers the next seed.
`bind_module` and twin ≠ runtime-class witnessing are closed by the complete
artefact-family load-back gate.

## 5. The vision for the code

**Three objects, three lifetimes.** `Graph` — subjects and relation
instances, content-addressed, session-lifetime. `Room state` — per-relation-
instance presentation (camera, selector positions, watched frames), keyed by
relation id. `Policy` — session-wide, what survives travel. The server-owned
`Instrument` now holds the session plus relation-keyed watched routes and
window overlays; derived caches follow the same relation address.

**Migration order that keeps the gate green** (ruled in the adversarial
round, C8): (1) content-address subjects and give `Reading` an `__eq__` —
pure addition, kills ring growth; (2) lift the window counter out of
`enter()` — one line; (3) introduce `Graph` with `climbed` as a derived
projection — the strata gate assertions are unchanged because the wire is
unchanged; (4) de-globalize `Held`; (5) split `facets.py` per room LAST,
when a second room exists to split against — carving earlier is speculative
generality and the project's own history says so.

As of 2026-08-14, steps 1–4 are landed and gated. Pure grammar candidates now
become explicit offered relations, and the generalized file router retains
pure notation, flavour, and module-selfgrammar answers without execution.
The server-owned Landing map presents those subjects and offers; payload
import is digest-named, provenance-checked, and reachable only through a
visible cast. File ingress and artefact witnesses are pending worker work,
never render-path stalls. Praxis is now an immutable value projection reached
through the strata, and the first OPEN-7 surface (`lexic.generate`) is live and
read-back-gated. The remaining work is the reduced OPEN-7 list. Facet
splitting remains last.

**Memory discipline at graph scale.** `generation` is per-subject; a frame
carries the generations of the subjects it draws. Lazy: everything but the
cheap ingress predicate. Evicted: derived caches (spans, watched frames,
kernels, artefact families) for subjects not visible in the current room,
LRU ~3. Never evicted: the graph itself (nodes are small) and lexic's
compile cache (not ours; clearing it invalidates live classes).

**Every gate stays.** space_3's `gate.py` (frames as data, refusal pairing
included) and `probe.sh` (the leaf in a real browser) remain the done-gates;
the map frame joins the perf gate with its own budget. Witness loads use
digest-named modules only. The quality bar is the repo's: flat code, open
dispatch, refusals with words, no silent picks anywhere in the stack.

## 6. The vision for the interface

**The landing is the map; THE STRATA remains the climb.** Rows on the map are
ROLES, not kinds: a document lane, a reader lane, a value lane, an artefact
lane, and the instrument's own lane. Artefact families fold into one capsule
per subject, expanding only in their room. Offered relations are drawn as
doors; a subject with two accepting readers shows both and waits for the cast.
With no files given, the map is what greets you, holding doors to fixtures/
and generated/. The space_2 ladder chip continues to open THE STRATA, where
visited and unvisited rungs—including the metagrammar—are displayed and
travelled. The adjacent `⌗ map` is the distinct fifth travel move, reachable
from every reading and passed through, not lived in.

**Rooms, one per relation kind.** The **reading room** — space_2's five
facets, unchanged; it is the thing that works and the redesign costs it
nothing. The **compilation room** — the four moments, binding view, machine,
verdicts. The **transpile room** — grammar half: peer lanes,
canonical-equality witness, both re-emit directions; document half: source
document, target grammar, and the transform table — itself a subject with a
value-room surface, editable as data — with the three gates as drawn
verdicts. The **value room** — any lexic IrSelf as a real node graph
(`eidolon/value.py`'s walk), which is also where attachment values are
authored: slot-based editing of IR structures, offers from the algebra,
never a textarea. The **artefact room** — the family, its witnesses, its
load-backs, each verdict drawn from a digest-named load. The **generation
room** — mask/push/accepts over a bound tokenizer — is designed but
deferred (OPEN-5).

**Travel is five moves**: cast-up, cast-down, enter-room, back, map. BACK is
a history stack, never a graph edge — in a graph you can arrive at one room
two ways, and "where I just was" is the only question a hand is asking.
Docking an attachment is not travel: you stay in the reading, a product
facet appears, and entering its room is an explicit cast.

**Editing stays a re-reading** everywhere: text is primary, commit splices
and re-parses, every facet re-derives or nothing changes. Refusals keep the
typed text, draw the measured frontier, and speak the engine's words. A
pending computation — background engine run, expensive witness, slow
ingress — is drawn as pending, never blank, and promotes when it lands.

**The spectacle is the computation.** A document crossing the transpile
room's lanes while its gates flip to verdicts; the compilation room's
passes rewriting the grammar in steps; the generation mask narrowing as
characters are pushed; the map re-arranging when a product node arrives.
Register rules hold: nothing breathes idle, motion means traversal,
recomputation, or rearrangement.

## 7. v1, ranked

Must contain: (1) the graph as storage, the ladder as projection; (2)
ingress that probes all readers and never picks; (3) the reading room
unchanged and green; (4) the map as role-laned landing, families folded,
frame in the perf gate; (5) the transpile room — grammar half first,
document half on `lexic.compile.transpile`; (6) the value room over any
lexic IrSelf; (7) five travel moves, history-stack BACK; (8) two-tier
licences with digest-named witness loading.

Deferred, each with its recorded reason: the tokenizer generation room
(attachment topology); directives/vocabulary on relation instances (needed
before two readings of one pair coexist). Praxis-on-the-spine and the smaller
`lexic.generate` gesture are now live and gated. Nothing is deferred silently:
a deferral is a drawn refusal or an absent door, never a broken one.
