# atlas — the ergonomics, thought topologically

Forked from `../facets/` (which scales; nothing was thrown away). This file is
the map the iterations follow. The governing picture: **the session is a graph
of subjects** (edges: lineage, peers, time); **facets are projections of one
subject**; **cursors live on the subject** and every facet renders them. Every
question below is answered by placing the new thing in that graph — never by
inventing a window.

## 1. Resize

The only geometry a hand should ever touch is a **seam** between facets.
Shares are session values (like everything else — editable, persisted,
reported over the gesture wire), not pixel rectangles. The load-bearing rule:

> **A facet degrades by deriving less, never by clipping.**

The spine already behaves (bounded by depth at any width). The chart drops
lanes and thins its overview. The document keeps text and sheds gutter. A
facet that cannot say anything at its current share says so — one honest line
— rather than showing a cropped lie. Iteration: draggable seams on the grid,
shares POSTed like the cursor, a `min-say` per facet.

## 2. The 3D language graph

A fifth facet over the READER subject: rules as nodes, references as edges,
**z = derivation distance from the start rule** — the axis that earned its
meaning in opsis-4's flat-vs-depth comparison, kept scoped to its region
(opsis-3 proved perspective does not leak to flat siblings, text stays
selectable). Co-selection needs zero new mechanism: a rule's *name* is already
the shared address — hover `namechar` in the graph and the reader line, the
document spans, and the chart bars light exactly as they do today. Edges come
from lexic (`IrRuleRef`s in each rule body), never re-derived by the leaf.

## 3. Attachments — reducers, templates, transpile

These are **not facets and not rungs — they are ports on the reading** (the
codex-mock's capability bay, now with a substrate under it). Topologically:

- **Docking a reducer** adds a *product* to the reading (the reduced value).
  A new product brings ITS facets (a value tree beside the model view). The
  facet set multiplies by products, never by windows.
- **A template** is an attachment that selects paths — its facet is the
  document with the selected paths lit, which is co-selection we already have,
  driven by a value instead of a hand.
- **Transpile** adds a **peer edge** in the session graph: a second READER
  facet beside the first (`json.gbnf ≅ json.abnf`), same canonical subject
  underneath, co-selection crossing via the canonical value. The peer is a
  sibling of the reader, not a child of the parse.

Empty ports are drawn with an explanation and a way to supply the object —
a missing attachment is visible capability, not absent UI.

## 4. Changing the meta level

Opsis's own configuration is a subject like any other — the tk demonstrator
proved the mechanism (its Style record drawn and retyped by the same table).
So "going meta" is not a mode: it is **moving focus along a lineage edge that
happens to point at yourself**. The session graph contains opsis's own session
as a node; its document is the configuration text; its reader is the config
grammar; its facets are the same four. The ladder closes into a ring (the
opsis-4 conjecture) and the ring is just an edge in the graph. Ergonomically:
one gesture — focus a subject — covers grammars, documents, and the
instrument itself, uniformly.

## 5. What a stacktrace looks like on a badly formatted file

A refusal is a *reading product*, so it gets facets like any product:

- the DOCUMENT with the **failure frontier** marked — the deepest position the
  engine verified before refusing;
- the SPINE **at the frontier** — what was open when derivation died (the
  honest analogue of stack frames);
- the **expected-next** set, from the grammar, in the reader's own spellings —
  which co-selects the rules that could have continued (the reader facet
  lights the alternatives);
- the engine's words, verbatim, as the title line.

**Measured gap (2026-08-07): lexic's public parse surface carries none of
this.** A refusal is `UnsupportedConstructError` with words only — no
position, no expected set (`args` is the whole payload). The engine knows the
frontier internally (the PDA's failure state, Earley's last live column); the
public surface discards it. This is lexic work worth a ruling, the same class
as opsis-3's §6 findings — a readout surface, additive, shaped like
`readout.py`'s existing seam. Until it lands, the refusal facet draws the
words and marks the frontier **unmeasured**, honestly.

## 6. Performance truth (measured, same day)

`json.gbnf` on the PDA fused route: **313,593 chars/s**. The metagrammar on
the Earley+resolver route: **1,974 chars/s** — 159×. The resolver fires ONCE
on all of vyx.gbnf, so the cost is the route, not the resolution: the GBNF
self-grammar's model product is ambiguous, the PDA probe-forks, and the whole
document pays for Earley + the ambiguity audit. Lexic-side fix: make the
self-grammar's model product unambiguous (noise attribution) so it rides the
PDA. Opsis's obligation meanwhile: state the route in the masthead (it does).

## 6b. Both engines, both clocks (ruled 2026-08-07)

The user's ruling on §6: **give both routes as observation.** The parse API
keeps no route flag — the "no PDA opt-out" ruling stands untouched; the
product is still the engine's own composition. But the instrument runs BOTH
engines over the document and draws each as its own time facet on the shared
document coordinate: the PDA's decision sequence, Earley's chart columns —
neither a renamed version of the other. Protocol: default to the road actually
taken (PDA when healthy); run the other in the background; the switch enables
only when it finishes — until then the alternate route is a drawn pending
state, never a blank. When the PDA fails, the inversion is content: the
probe-fork point and island hand-off intervals are first-class marks. With
both runs in hand, parity is a drawable measured fact: *both engines built the
same value — holds*. Surface exists: engine-floor exports (`earley_model`,
`PdaKernel`, `pda_tables`) from the opsis-2 batch; `TraceKernel(PdaKernel)`
is the proven zero-hook observation pattern.

## 7. The ruled direction — one instrument, one policy, many surfaces

User-blessed ("the fair compromise for now") after TUI slice 3.

- **The browser leaf is the flagship** — the one medium carrying all four at
  once: real text, scoped 3D, overlapping windows, GPU spectacle. The living,
  full opsis is the browser one.
- **Windows are pinned facets, only.** Created by an explicit pin gesture,
  never by navigation; movable, resizable, uncapped (the cap was overruled —
  "let the people have fun"; "pin only for simultaneity" survives as advice,
  not enforcement); carrying their subject's address so co-selection reaches
  inside. The instances: simultaneity a
  tiling cannot express, comparison of exactly two, persistent reference.
  The load-bearing line stands: a pane cannot overlap; a window can.
- **3D is the rule-graph facet** — z = derivation distance from the start
  rule, scoped perspective, name-addressed co-selection — browser only. The
  TUI renders the same facet flat; a cell grid has no z and pretending
  otherwise is medium dishonesty. The forest stays flat everywhere (settled
  by looking).
- **The TUI is the field instrument**, not a parity race: read side + honest
  editing where developers and agents already stand. Its pins land as panes;
  same meaning, the medium's geometry.
- **Presentation policy moves from leaf code into the wire** — the
  resolution of the two-renderings divergence: the scene grows a policy
  section (facet inventory, arrangement shares, pins, register, co-selection
  vocabulary); leaves thin into interpreters of one policy. Extracted AFTER
  pinning and the 3D graph exist concretely — build twice, then the rule.
  Seam-resize (§1) folds into this rung: shares ARE arrangement-as-value.
- **The native/GPU endgame stays the watched option** (libghostty when it
  stabilises); nothing above the leaf changes if taken later.

## 8. Rung 5 — policy into the wire (scope, ruled with the user)

One instrument, one policy, many surfaces — presentation moves from leaf code
into session state; the leaves become interpreters. In scope, explicitly:

1. **The policy record** on the session, line-oriented like the whole wire
   (no JSON): dotted keys — `arrange.reader`, `doc.zoom`, `chart.zoom`,
   `spine.zoom`, `speed`, `reader.mode`, `graph.*`, `pin.<id> …`. Cursors
   (t, sel) already live on the subject; policy is the third session state.
   NOT IR-notation yet — configuration-as-IR is the ring's business.
2. **Wire**: `#POLICY` in `/scene`; `POST /policy` (changed keys as lines);
   `GET /policy` polled ~2s — which gives cross-leaf sync free: two leaves
   on one server stay in step.
3. **Browser re-base**: boot applies policy (pins survive reload — the felt
   gap); every presentation gesture posts its delta.
4. **Seam resize lands here** — draggable hairlines writing `arrange.*`;
   it always was arrangement-as-value.
5. **THE GRAPH ASKS, moved into this rung by ruling**:
   - Obsidian-style layout tunables as policy values with a slider panel:
     `graph.levelstep` (z separation), `graph.ringscale`, `graph.flatten`,
     `graph.labelscale`.
   - `graph.view` switchable: `depth3d` (current) · `flat` (levels as
     columns, no camera — the same view the TUI renders in cells) · `arcs`
     (rules in SOURCE ORDER on a line, reference arcs above/below —
     recursion, forward/backward refs and clustering become visible shapes,
     and source order is preserved where the rings destroy it).
6. **TUI re-base — the acceptance test**: the TUI obeys `#POLICY` (shares,
   speed, reader.mode) including rung 4's remaining half — the FLAT rule
   graph in cells is just the TUI's interpretation of `graph.view`. Pins
   render as a minimal occurrence-list pane (full panes stay rung 6).
7. **Gates**: policy round-trip census (POST → GET → boot applies, asserted
   in DOM and TUI text screenshots); SPEC §2 wire update; ledger.

Out of scope, named: IR-native policy spelling (the ring), the engine
clocks (rung 2b), per-colour register editing, policy persistence across
server restarts (session state dies with the process — accepted for now).

**POST-5, its own iteration by ruling: the railroad.** Per-rule railroad
diagrams opened as pin windows (mark a rule → pop its railroad) — a real
renderer with lineage (opsis-1's graphic.py was a railroad flavour as an
open dispatch table); its facet kind is reserved in the policy schema now.

## Iteration ladder

1. ~~Refusal facet~~ — DONE (browser + TUI, frontier in both media).
2. ~~Both engines, first half~~ — DONE (background run, parity verdict,
   inversion). The clocks-switch remains, folded after the policy rung.
3. ~~Pinning in the browser~~ — DONE (uncapped by ruling; chip gesture;
   measured birth width; reconciled rendering).
4. ~~The 3D rule-graph facet, browser half~~ — DONE (+ focus mode, orbit,
   zoom, pop-out, camera clamp; the TUI flat half moves into rung 5).
5. **Policy into the wire** (§8) — INCLUDES the graph asks (tunables +
   switchable views flat/arcs) and the TUI re-base with the flat graph;
   seam-resize lands here.
6. ~~The railroad~~ — DONE (`/rail` structural wire; canvas renderer with
   bypass/loop arches, split/join curves, class/literal/ref/negation
   registers; `▤ rail` on the marked rule; refs click through to their own
   railroad; `pin.<id> rail` policy + `?rail=` deep link).
7. ~~TUI panes-for-pins~~ — DONE (the PANES column from the same policy
   record; span text, rail structure in registers, graph pins named; live
   `/policy` tick in both leaves closed rung 5's polling leftover).
8. ~~Engine clocks~~ — DONE (`/clock` wire; `ClockKernel(PdaKernel)`
   zero-hook counts + the explicit Earley `Kernel.cols` readout; the
   derivation facet's `chart.clock` switch, policy-persisted; pending
   drawn as a sentence).
9. **Ports bay** — reducer docking; transpile peer lane.
10. **The ring** — focus opsis's own configuration as a subject.

One iteration per session, tally updated each time, census before screenshots.

## 9. Facet management (ruled 2026-08-08) — the facet set is itself a node-space

The user's ruling at the rung-8 stable point: complexity is growing and no
single facet can host what comes next; facets need move, minimize, reopen,
clone, and pop-as-window. **This is not making facets windows** — a pane
still cannot overlap; a window still can. It is the node philosophy applied
one level up: the SESSION's facet set drawn and handled as nodes.

- **The dock** — the place to close to and reopen from. A slim node rail in
  the masthead: every facet is a chip (lit = present, dim = minimized).
  Clicking toggles presence. The dock is a registry drawn as nodes, not a
  menu; a minimized facet keeps ALL its state (policy holds it — shares,
  views, clocks, cameras survive minimize/reopen and cross-leaf sync).
- **Presence is policy**: `facet.<name> on|off`. The grid REFLOWS —
  neighbours take the freed share; reopening restores from `arrange.*`.
- **Move** = reordering panes in the grid (`arrange.order`), never overlap.
- **Clone** = a second projection of the same kind with its own presentation
  state (`facet.<id> <kind> …`) — two readers (text beside automaton) is the
  motivating case. Clones are nodes in the dock like any facet.
- **Pop as window** = the existing pinned-window machinery, generalized: any
  facet can pop a pinned twin (the reader already does — graph and rail
  pins). Windows stay the ruled exception. Closed windows should MINIMIZE
  to the dock rather than delete, so they reopen.

Build order: dock + minimize/reopen + reflow (this round) → move → clone →
pop for the remaining facet kinds → pin-minimize into the dock.

### 9b. The layout is a split tree (ruled 2026-08-08, second pass)

The user's findings on the dock+slots round: a dozen facets explodes the
complexity, and the whole thing PRESUPPOSES the layout — nothing imposes
three columns with one split in half, nor that only the center can fill
the screen. Correct: slots were the old grid wearing a new name.

**The arrangement is a tree.** Internal nodes are H/V splits carrying a
share; leaves are facets. The grid CSS is gone — the leaf walks the
visible tree and places facets absolutely. Consequences, each a fix to a
named flaw: any facet anywhere (movement = leaf swaps, later subtree
moves); any facet fullscreen (minimize the rest — the tree merges to one
leaf); N facets = a deeper tree (clone-ready); every internal edge IS a
seam (resize generalizes); one policy line (`arrange.tree`, an
s-expression: `(h 0.24 grammar (h 0.61 document (v 0.58 chart spine)))`).

**Order ruling (mine, stated):** layout tree → clone → pop. Clone cannot
exist without a place for a fifth facet; pop's re-dock needs an insertion
point. The dock's scale redesign follows clone, when instance counts are
real. Legacy `arrange.reader|right|top` stay honored while the tree is
default-shaped (the TUI still reads them); the tree supersedes them
otherwise.

## 10. Focus and travel — the session becomes a ladder (built 2026-08-08)

The user's redirect, after two wrong answers (a popup map, a facet map):
"how does opsis represent itself" is not furniture — it is the LADDER.
A facet is (subject, projection, presentation); atlas had hardwired the
first coordinate. The clone problem and the layout problem were both
fragments of that: clone tried to multiply presentation with the subject
pinned; the map drew the third coordinate only.

**Built: Session = the ladder of readings a fixture implies.** Every
reader is also a text; every text may also be a reader. long climbs:
long.json ⊳ json.gbnf → json.gbnf ⊳ metagrammar → the metagrammar ⟲ its
own spelling (the self-hosting fixpoint — reader and document the SAME
TEXT, census-gated). Subjects build lazily on first focus; one policy
record spans the session, so the arrangement survives travel. The wire:
`#LADDER` in the scene, `POST /focus i`. The leaf: the lineage strip in
the masthead — readings as chips, focus lit warm, click travels; every
subject-scoped cache resets and the WHOLE instrument re-derives (spans,
spine, clocks, verdicts, automaton, rails — all of it, against the new
reading). The travel moment is the duality made kinesthetic: json.gbnf
flips from reader to document in one click.

Not yet: anchored facets (clone = a facet pinned to an off-focus rung —
now DEFINABLE in this model, deferred); the constellation view (the
graph drawn whole, opsis-2's picture) when the session goes non-linear
(peers, the opsis node); the IR rung (the notation as a readable text);
the opsis node itself (the policy record as a subject — the ring).

### 10b. The IR floor and the ring (built 2026-08-08)

The user's two challenges on §10: where does opsis-representing-itself
FIT, and the "fixpoint" wasn't one — the IR was untouched. Both answered
structurally:

**The IR rung.** The ladder now descends below the spelling rung to
`metagrammar.export.py ⊳ the module self-grammar` — the metagrammar AS
ITS GENERATED TWIN MODULE (IR constructors: `class Grammar(GrammarModel)`,
`IrRule(...)`) read by `MODULE_GRAMMAR`, lexic's own "parses its own
exports" surface. 34,740 chars, PDA route, 0.07s, faithful; census-gated
per fixture. The old ⟲ label was honestly demoted to "reads its own
spelling" — text-level self-hosting, not the fixpoint.

**The absolute fixpoint is BLOCKED, and that is a finding:** the module
self-grammar's own rule names (`esc-u` / `esc-U`) collide under name
folding, so no flavour can spell it and `export_source` cannot export it —
the self-grammar cannot yet enter its own language. Atlas reads it via a
language-identical rename (esc-U → esc-u-cap). ENGINE ASK: exportability
for IR-authored grammars (or fold-safe self-grammar names) would close
`module-grammar ⟲ its own export` — the true fixpoint.

**Where opsis fits: as a reading.** The session policy record — already
a line-oriented text on the wire — got a grammar (atlas/fixtures/
policy.gbnf) and became the ⚙ rung, violet in the strip, refreshed on
focus. The document facet IS the instrument's state; spans, spine and
verdicts work over it like any subject. And the ring closes: **saving a
valid record APPLIES it** — Handler.retype's persist path pours the
parsed record back into session.policy; the leaves poll; the instrument
rearranges. Census-gated ("the ring applies"); screenshot-proven: a
saved `arrange.tree (v 0.55 document grammar)` line REARRANGED the
screen that displayed it, with the policy grammar's own railroads in
the reader. No special machinery anywhere: opsis is one more subject of
the standard pipeline.
