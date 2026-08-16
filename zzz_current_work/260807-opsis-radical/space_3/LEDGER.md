# space_3 — the ledger

space_3 began as an exact code copy of space_2. Every entry records what
changed, which space_2 behavior it intentionally departs from, and the gate
that keeps the working reading room intact.

## 2026-08-14 — graph foundation and map budget

### Ownership ruling

No Lexic source changed in this slice. The failures were owned by the
instrument:

- graph topology, travel history, room state, window identity, and frame
  budgets are opsis session/presentation semantics;
- `turn()` silently chooses because opsis returns from its own first-match
  loop; `compile_text(..., flavour=...)` already answers the explicit engine
  question correctly;
- Lexic already provides the strong twin contract through
  `verify_module()`; opsis had weakened it to `ast.parse()`;
- model-plane transpilation was a genuine Lexic gap and remains fixed in
  Lexic by `a4ec6fe`.

If later wiring exposes a missing engine primitive, it belongs in
`src/lexic` with repository tests. There is no application workaround
licensed by this ruling.

### Graph as storage

Added `praxis/graph.py`:

- text subjects are SHA-256 content-addressed with length-delimited parts;
- reading and policy relations cast subjects into reader/document roles;
- equal relations deduplicate to one live reading;
- lineage is stored as graph edges rooted at the initial reading;
- `Graph.walked()` derives the old ladder shape for the unchanged strata
  wire;
- successful edits re-address their relation and preserve graph edges.

`Reading.identity` and `Reading.__eq__` now use ordered reader/document
content. Reading remains deliberately unhashable: it is mutable during a
re-reading, so caches use `(identity, generation)` instead.

`Session.climbed` is now a property over `Graph.walked()`, not storage.
The policy relation enters the graph without becoming a lineage edge.
Consequences measured by the adversarial probe:

- repeated ring entry leaves the ladder at one rooted rung;
- `ring → rung 2` climbs the original JSON lineage, never `policy.gbnf`;
- two initial subjects and one reading relation are held explicitly.

### Session-lifetime windows

Removed the `self.windows = 0` reset from `Session.enter()`. Opening two
windows, travelling, then opening another now produces `w0 w1 w2`; no box
or per-window camera is inherited through an ID collision.

### Two-tier artefact licences

The map no longer runs an artefact witness. It asks the cheap
`licences(compiled)` predicate and says “witness on room entry”.

The artefact room runs the expensive tier through `keep(compiled,
generation)`, cached by compiled identity and generation with a bounded
64-entry derived cache. The twin witness now calls Lexic's
`verify_module(compiled, source)`: Lexic's self-grammar parses the module
and cross-checks its grammar, classes, fields, bindings, and shapes. Merely
being valid Python is no longer called a witness.

Still open: the full artefact family, digest-named explicit runtime imports,
and drawing a cold room witness as pending rather than blocking.

### Map derivations and gate

Depth bands are cached by `(Reading.identity, buckets)`, bounded to 64
entries. Dock facet caching was moved off the mutable Reading object onto
`(Reading.identity, generation)`.

The executable gate now covers:

- content equality and inequality after content changes;
- explicit graph subject/relation storage;
- session-lifetime window IDs across travel;
- ring deduplication and lineage isolation;
- rooted climbing after ring entry;
- cheap map licences versus room witnesses;
- the complete composed map at 20 content-distinct subjects.

Measured on this run:

- normal frame: 3.7 ms;
- map frame, 20 subjects: 2.0 ms;
- selected-rule document scrolling: 4.4 ms;
- 3D rotation during playback: 4.3 ms.

All remain below the 20 ms hot-frame budget.

### Verification

```bash
uv run ruff check <all changed Python files>  # all checks passed
uv run python -B zzz_current_work/260807-opsis-radical/space_3/gate.py
# 24 gestures · 13 keys · 0 failures
```

The adversarial session and map-cost probes also run against space_3. Their
measurements now show unique window IDs, a policy-free lineage, rooted
post-ring climbs, and sub-millisecond hot `strata()` construction.

### Next migration step

Steps 1–3 of VISION §5 are landed. Next is step 4: de-globalize `Held` into
a server instance and key room presentation/caches by relation ID. Only then
should multi-reader ingress and pending subject workers attach to the graph.

## 2026-08-14 — popup fidelity and relation-owned rooms

### Popup windows are copies again

Pin, rail, cloned facets and popped facets were rebuilt against space_1:

- occurrence pins now carry the rule/address/depth header, exact snippet,
  field/generation facts, definition, stale treatment and reference cascade;
- rail pins fit one rule's track, expose parent navigation and back history,
  and keep their rule doors inside that rail window;
- graph clones carry the RULE GRAPH view selector, including the real reader
  text view; true popped Relations facets retain their facet header and full
  slider set;
- ordinary clones carry their facet body and “a second view”; true popped
  facets carry the real nested facet head and controls.

The root failure was identity, not drawing. Browser planes and controls were
keyed only by semantic names such as `document` and `graph.levelstep`, so a
second copy displaced the first. Frame addresses now carry a window scope,
gestures return through that window's layer, and each popup has its own
visual canvas in stacking order. A higher popup therefore covers the lower
popup's real text and controls instead of letting them bleed through.

Live comparison on ports 8931/8932 (8917/8918 left untouched) verified:
independent document scrolling; a 327-character Relations text copy; four
depth-3D sliders in a popped Relations facet; popup-local slider mutation;
rail parent navigation and back; and pin/rail reference content.

### Migration step 4

`Held` is gone. `Server` owns one explicit `Instrument`; its watched rows,
alternate route and window overlays live in `RoomWork` keyed by graph
relation ID. Session presentation is a relation-keyed room over session-wide
policy. Travel restores each room, successful edits migrate its state to the
new content address, and opening the ring casts the effective instrument
into policy so its relation remains a fixpoint.

The gate now proves server instances share no session/window state, relation
travel restores distinct rooms, popup planes/controls have distinct scoped
addresses, each popup is a separate visual stack, and popped Relations keeps
all four sliders.

### Verification

```bash
uv run ruff check <all changed Python files>  # all checks passed
uv run pyright space_3/praxis/session.py space_3/serve.py  # 0 errors
node --check space_3/leaf/leaf.js
uv run python -B space_3/gate.py
# 24 gestures · 13 keys · 0 failures
```

Hot measurements remain inside budget: normal frame 3.6 ms, 20-subject map
2.0 ms, selected-rule scroll 4.4 ms, and playing 3D turn 4.3 ms.

No Lexic source changed: popup identity/stacking and server/room ownership
are opsis presentation/session semantics. The next dependency-ordered
blocker is OPEN-2, all-reader ingress without a silent first match.

## 2026-08-14 — compact popup geometry, spine hover, and all-reader probes

### Exact compact windows

The compact pin and rail were measured directly against space_1 at a
1400×900 viewport. The `true` occurrence pin is now 280×97 in both spaces;
the `member` rail is 376×91 in both. Pin width follows registered 12 px copy
under the reference's 62% viewport cap, while rail geometry is its track plus
52×58 under 72% caps. The 27/29 px chrome, 12 px body, 11 px facts/address,
baselines, and trailing-newline treatment now come from frame metrics. The
result fixes both the excess height and the missing/misaligned copy.

### Spine hand

Hovering a model-spine row now paints that exact row with `liveline`, while
continuing to publish the shared span hover used by the other facets. A real
pointer move over the reference-matched row produced `:span 4:15768` and a
393×19 row wash.

### Pure all-reader ingress

`ReaderProbe` records every GBNF, ABNF, and EBNF attempt as either a compiled
machine or the engine's refusal words. `turn()` no longer chooses a first
match: ambiguity returns no reading unless a flavour is explicit. Holding an
ambiguous subject creates one unparsed `offer` relation per accepting
flavour; the frame shows all outcomes and `cast` performs the chosen read.
The leaf now reserves cast hits so the underlying text plane cannot intercept
the chooser.

The fixture `root = "x" ;` is deliberately accepted by ABNF and EBNF and
rejected by GBNF. The gate proves both offers remain distinct, preserves the
GBNF refusal verbatim, and proves an explicit EBNF cast parses faithfully and
roots the graph.

### Ownership

No Lexic source changed. Lexic already owns and exposes explicit
`compile_text(..., flavour=...)`; the silent first-match policy existed in
opsis's ingress orchestration, so the proper fix belongs here. Lexic checks
and coverage therefore remain unaffected.

### Verification

```bash
uv run ruff check <all changed Python files>
uv run pyright space_3/praxis/reading.py space_3/praxis/graph.py \
  space_3/praxis/session.py space_3/opsis/frame/compose.py
node --check space_3/leaf/leaf.js
uv run python -B space_3/gate.py
./space_3/probe.sh
```

Ruff passed; Pyright reported 0 errors and 0 warnings; the gate reported
24 gestures, 13 keys, 0 failures; and the browser probe passed at both 1×
and 2× scale. Hot frames remain below the 20 ms budget: normal 3.6 ms,
20-subject map 2.0 ms, prolific selected-rule scroll 4.5 ms, and playing 3D
turn 4.3 ms.

### Remaining boundary

OPEN-2 is only half closed. The next blocker is the generalized file-subject
router, including explicit-last payload imports. Pending worker subjects
follow it; they are still required before slow ingress can stop blocking the
instrument.

## 2026-08-14 — extension-first file ingress

### Pure readers retain every applicable answer

`praxis.ingress.probe_file()` turns each path into one content-addressed
`FileSubject`. Extension narrows the candidate set; it never selects a winner.
An `.ir` file runs `load_ir`; a `.flavour.ir` file retains both the notation
value and the validated live flavour; a `.py` file runs `parse_module`, which
parses the source with Lexic's module self-grammar and does not import it.
Every accepted value and every engine refusal remains on its own `FileProbe`.
Grammar source suffixes still run all three metagrammars through the existing
all-reader probe.

An empty `land()` retains its fixture/generated doors rather than inventing a
reading. This is the data seam the server map will consume next.

### Python stays explicit

A Python subject carries an offered payload relation whose words are honest:
identifying a payload module means running it. Probing never crosses that
boundary. `import_payload()` is the explicit operation: it executes through
`spec_from_file_location` under a content-digest-suffixed module name, then
promotes only modules exporting an `IrSelf` value or a bound `GrammarModel`
class. A module with no such provenance is a refusal, not an untyped subject.

The gate writes a payload whose first action creates a marker. `probe_file()`
leaves the marker absent; only `import_payload()` creates it. The returned
module name contains the subject digest and its only accepted export is the
fixture's `VALUE`. A generated twin is independently accepted by
`parse_module` while payload execution remains merely offered.

### Verification and boundary

```bash
uv run ruff check space_3/praxis/ingress.py space_3/gate.py
uv run pyright space_3/praxis/ingress.py space_3/gate.py
uv run python -u space_3/gate.py
```

Ruff passed, Pyright reported 0 errors and 0 warnings, and the full executable
gate again reported 24 gestures, 13 keys, 0 failures.

No Lexic source changed. The pure loaders and explicit compile APIs already
belonged there; ordering their use, withholding Python execution, naming
runtime modules, and retaining offers are Opsis ingress policy.

OPEN-2 is not yet closed on screen. `Landing` subjects and their answers must
still enter the server-owned graph/map, and payload execution must be reached
through a visible explicit cast. OPEN-5 then moves slow readers to pending
worker subjects.

## 2026-08-14 — Landing promotion, pending work, and complete artefact witnesses

### The ingress boundary is now visible

The server map owns every `Landing`: file subjects enter on their role lane,
all pure answers and exact refusals remain visible, and Python payload
execution is reachable only through an explicit cast. File probing runs in
the server-owned ingress worker. A subject is drawn PENDING immediately and
is promoted at the same content address when its result arrives; the leaf
continues to own neither play nor pending state.

The gate injects a deliberately slow probe and proves the pending node is
drawn before completion. This closes the render-path freeze without guessing
at a duration threshold: all file ingress is worker work, so a new slow
reader cannot silently reintroduce the stall.

### One reading retains the complete family

`keep()` now retains six named slots: twin, IR notation, grammar payload,
model payload, dump payload, and reduced payload. The first five are written,
loaded back, and witnessed. The twin passes Lexic's module self-grammar check;
payloads load through `spec_from_file_location`, bind through Lexic's public
contract, and keep runtime model classes distinct from the twin. Runtime
module names include the subject's content digest, do not collide across
subjects, and are removed from `sys.modules` after the witness.

Reduced is not fabricated from an unrelated transformation. Without a docked
reducer its family slot says `not licensed`; a reducer can fund that witness
later without changing the family shape.

The artefact room asks for this family lazily. A cold request is drawn PENDING
while a bounded worker builds it, then promotes to the six completed rows in
place. The map continues to compute only cheap licences.

### Ownership and regression

No Lexic source changed. Lexic already supplies `verify_module`,
`bind_module`, notation and payload loaders, and the value/model distinctions;
worker lifetime, room promotion, and retained-family presentation are Opsis
responsibilities.

The browser probe's ownership assertion had matched the old literal
`frame && frame.running`. Pending refresh correctly widened that expression
to running-or-pending, so the probe now checks for server-frame running state
without prescribing the exact expression. It still rejects leaf-owned
`playing` state.

### Verification

```bash
uv run ruff check <all changed Python files>
uv run pyright <all changed Python files>
node --check space_3/leaf/leaf.js
node --check space_3/leaf/probe.js
uv run python -B space_3/gate.py
./space_3/probe.sh
```

Ruff passed; Pyright reported 0 errors and 0 warnings; the executable gate
reported 24 gestures, 13 keys, 0 failures. The browser probe reported zero
failures at both 1× and 2× scale, including native graph sliders, pin and rail
popups, popup-local navigation, and leaf play-state ownership. Ports 8917 and
8918 were not touched.

The ingress, artefact-family, and OPEN-5 slow-ingress blockers are closed. The
next dependency-ordered work is OPEN-6 (praxis on the spine) and the
separately funded OPEN-7 surfaces.

## 2026-08-14 — Praxis on the value spine and a witnessed generate gesture

### Mutable owners, immutable value

`praxis.value.snapshot()` projects the live Session into a `PraxisSession`
`IrNamedTuple`. Its children retain the Reading, every Facet and climbed Rung,
content-addressed Subjects, relation instances, effective policy, focus,
generation and cursor as nested Lexic values. The mutable Session remains the
owner; advancing it produces a new snapshot and cannot alter the old one.

The instrument lane now has an `ir:instrument` door. It opens the snapshot in
the existing generic value room, which draws its named record edges without a
Praxis-specific renderer. This resolves OPEN-6 while preserving the graph,
session and engine-value lifetimes rather than forcing one to impersonate
another.

### Generate, then believe

The reading's strata and room index now expose `generate:0`. The gesture calls
Lexic's existing public `generate()` with a deterministic seed, then requires
the same compiled reader to accept the result and re-emit identical text
before anything is shown. The room names the root, seed and read-back verdict,
spells invisible whitespace, and offers the next seed as “generate another.”
A refusal stays a refusal in the room.

The gate pins equal seeds to equal documents, distinct tested seeds to
distinct documents, both read-back verdicts, the visible spelling, the next
gesture, and both strata doors.

### Ownership and verification

No Lexic source changed. Immutable IR records and `lexic.generate` already
exist there; projecting application state and exposing a witnessed gesture are
Opsis topology and presentation.

Ruff passed, Pyright reported 0 errors and 0 warnings, and the full executable
gate reported 24 gestures, 13 keys, 0 failures. The remaining OPEN-7 surfaces
are tokenizer attachment, relation directives/vocabulary, the template room,
duplicate-key explanations, and resolver-specific promises. Runtime module
binding and twin/runtime-class distinction were already closed by the full
artefact-family gate.

## 2026-08-15 — THE STRATA and THE MAP are distinct travel

The landing-map slice had intercepted the reading room's existing
`at strata on` gesture in the server and sent it to THE MAP. That made the
space_2 ladder appear replaced even though `praxis.strata`, its visited and
unvisited rung cards, `Session._rung()`, and the metagrammar reading were all
still present. The gate encoded the interception, while its strata and rung
checks called the composer and session directly and therefore missed the dead
visible route.

The server no longer consumes a strata gesture. The ladder chip retains its
verbatim pairing and again opens THE STRATA; its unvisited metagrammar card
builds and enters the metagrammar reading on demand, and rung zero returns to
the original reading. A separate adjacent `⌗ map` control emits
`at ingress map`; BACK restores the exact reading room from the server-owned
history stack.

The executable gate now rejects a server-consumed strata gesture and requires
distinct visible `strata/on` and `ingress/map` hits. The browser probe follows
the actual hit rectangles through reading → strata → metagrammar → strata →
original reading, then enters THE MAP separately and comes BACK. This closes
the route the earlier component-level assertions could not see. No Lexic
source changed: the fault and its fix are Opsis navigation topology.

### Verification

Ruff passed, Pyright reported 0 errors and 0 warnings, and the executable gate
reported 24 gestures, 13 keys, 0 failures. The browser probe reported zero
failures at both 1× and 2×, including the complete visible metagrammar and map
round-trips. The probe used ports 8928 and 8929; ports 8917 and 8918 were not
touched.
