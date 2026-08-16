# opsis — the interfaces

Design exploration, 2026-08-16, written while the keystone lands. This
concretizes VISION.md's elements into three contracts — the wire, the
shell, the hand — plus the leaf's requirements and the src package shape.
Status: proposal for iteration, not ruled. Grounded in space_3's actual
wire (one route, `at · set · sel · text · scroll · spin`, `#FONT/#TONES/
#FRAME/#HITS/#OVER/#PICKS/#PLANES` blocks) — everything here grows that
protocol, nothing replaces it.

## 1. The wire, grown to speak the six elements

The wire today speaks PIXELS (box/line/text in named tones) plus HITS
(what to post when landed on). The six-element language wants the wire to
say what a drawn thing IS, so the leaf stays derivation-free while the
gate can still assert element-level facts ("this frame draws 12 capsules,
3 offered edges, 1 stale verdict") without scraping pixel coordinates.

Proposal — element blocks between the pixel display list and `#HITS`:

```
#CAPS n      id kind-glyph name address x y w h        ← capsules drawn
#EDGES n     id kind from-cap to-cap verdict-tone      ← realized relations
#DOORS n     id label casts x y w h                    ← offered edges
#VERDICTS n  edge-id state words…                      ← PENDING/STALE/words
#CURSOR      subject-address [span]                    ← the one cursor
```

The pixel words still paint; the element blocks say what the paint means.
Three consequences: (a) the gate's assertions move up an altitude — "no
room without gestures" becomes countable per frame; (b) co-selection is
checkable (every facet showing subject S must wash the `#CURSOR`
address); (c) T3's address records become the wire's address spelling —
one vocabulary from engine to leaf, no translation shim (the same
shared-leaves rule that settled M7).

Gesture verbs stay the six; the rule "every verb names the element it
acts on" resolves apparent collisions: `spin` on a camera control is a
camera; `spin` on an orbit ring's element id is the orbit gesture (§3).

## 2. The shell contract

The shell is what WAYFORWARD §3.2 extracts; this is its signature. A room
is a DECLARATION, not a class hierarchy:

```
Room  = (focus-kind,          # subject kind or relation kind it opens on
         facets,              # ordered facet set, each a Facet
         dock)                # the relation's ports, drawn in the masthead
Facet = (name,                # its head
         wants,               # measured columns×rows it needs (space_1's law:
                              #   a surface declares, the arrangement answers)
         draw,                # (frame, subject, camera, cursor) -> marks+elements
         gestures)            # the verbs it accepts, per element kind
```

The shell owns: the measured split tree, facet heads (`⧉`/`⧉+`/minimize),
the masthead (trail · dock · travel), window layers, the register, the
cursor, and ONE gesture router. A facet owns: its coordinate system, its
camera, its drawing. A facet never sees the graph — it sees its subject
and the shared cursor. The reading room becomes five such declarations;
the map becomes three (§4); a placard is illegal by construction because
a `Room` with zero gesturing facets fails the gate.

## 3. Travel, made visual (Q1 concretized)

- **enter** (absorbs dive): every capsule is enterable; entering a part
  IS interior descent. One gesture, two directions of the same geometry.
  No sixth move — the ruling bar ("a move that can only be a button is
  not a move") is met by the capsule being the button-that-isn't: it is
  the thing itself.
- **spin**: the orbit ring (§4) drags/scrolls; variants rotate through
  the focus position; releasing on a variant makes it the drawn spelling.
  Wire: `spin <ring-id> <delta>`. Earned only when the ring is drawn —
  until then the artefact room's list is the classical projection and
  suffices.
- **shift**: clicking a drawn EDGE (not its far capsule) crosses it —
  the trail records the edge kind (`⊳` read, `⇒` transpiled, `＋` port),
  and BACK undoes the crossing. Clicking the far capsule is focus, not
  travel — the B1-repaired cursor rule keeps these distinct.
- **cast-up / cast-down / back / map**: unchanged.

The distinction that makes shift a real move: focus moves the cursor
WITHIN the room; shift changes which relation the room is OF. The hand
learns it from the chrome: edges highlight whole-length on hover,
capsules halo.

## 4. The map's simultaneous projections (the tesseract rule, drawn)

Ruled: side by side, never xor. The map room is three facets over the one
graph, each a low-dimensional projection, welded by the cursor:

- **THE LANES** (classical): role lanes — documents · readers · values ·
  artefacts · the instrument. Fold rules and density gates as ruled.
  This is the projection that survives 30 subjects.
- **THE ORBIT** (geometric, focus-local): the focused subject at center;
  its representation ring around it (variants as capsules, witness edges
  as verdict-toned arcs); altitude drawn as a vertical rail through the
  center (what reads it above, what it reads below); lateral peers to the
  sides. Radiating-from-a-center is the Limit Theory picture at the only
  scale it survives: ONE subject's neighbourhood, never the whole graph.
- **THE TRAIL** (temporal): the history stack as a breadcrumb of capsule
  ⊳ edge ⊳ capsule — the projection BACK operates on, drawn rather than
  implied.

Selecting in any facet washes the other two. The strata remains the
altitude projection opened by the ladder chip — same room family, deeper
on one axis. Nothing ever attempts the whole 4-D drawing.

## 5. The viewing, at the dock

The plug stack gets one home: the masthead DOCK shows the focused
relation's ports as offered edges (`＋ reducer` `＋ tokenizer` `＋ rows`
`＋ template` `＋ resolver`), each either empty (dim), docked (the
attachment's capsule, enterable), or refused (verdict with words —
"resolver: code, from the registry only"). Docking = casting an offer:
pick a subject from the map, or author one in the value room, or generate
one from the algebra's offers. The dock is the SAME element vocabulary as
everything else — ports are edges, attachments are capsules, licences are
verdicts — so the viewing model costs zero new UI concepts.

## 5b. Settings — the ring, not a dialog

How a user accesses, views and edits the instrument's settings: **there is
no settings dialog, because settings are a subject like every other.** The
policy record is a DOCUMENT in the settings language (`policy.gbnf` — an
ordinary grammar through the standard pipeline; opsis's own config gets no
privileged format), the instrument is its reader, and `◌ ring` in the
masthead — present in every room — opens that reading. Save APPLIES: the
next frame is a render of the new value (the tk demonstrator proved the
loop: retype `warm`, the whole instrument changes; retype `pad` to 999, a
refusal in words and the session value untouched).

Three tiers, one subject, no fourth mechanism:

1. **Direct** — the controls themselves (register toggles, clock, seam
   drags, facet minimize) post `set` gestures that PATCH the policy
   record. Dragging a seam IS editing settings; the record is the truth
   the drag lands in.
2. **Structural** — the policy opens in the value room like any value:
   SLOTS with typed offers (a tone slot offers colours, a share slot
   numbers in range), the floor for parts nobody authored.
3. **Textual** — the record as a real text plane; commit is a re-reading;
   an invalid record refuses with the engine's words and the running
   policy stays untouched.

Content addressing makes settings history free: an applied edit is a new
policy subject, the ring edge repoints, and prior policy subjects remain
in the graph — revert is re-reading an old subject, and "what changed"
is a diff of two values in the value room. Scope stays the ruled
three-lifetime split: policy is session-wide; room state (cameras,
selectors) is per-relation and NOT in the policy record; the boundary is
drawn, not blurred. Persistence: the record is a file; a session boots by
reading it — settings travel as text, like everything lexic touches.

## 5c. How rendering is DETERMINED — licences and casts, never heuristics

The chain from bytes to a drawn surface, every step either a computed
licence or an explicit cast — no guess anywhere:

1. **Extension routes to pure readers** (`.flavour.ir` → flavour, `.ir` →
   value, `.py` → twin-parse plus an offered payload cast — execution is
   never part of identification).
2. **The reader is probed, never picked.** All candidate readers run;
   every verdict is kept; one accept auto-offers, several accepts draw as
   offered relations and the hand CASTS. A refused-by-all subject keeps
   its honest room.
3. **Row tables apply by GRAMMAR IDENTITY, not file type.** A table is
   applicable iff it BAKES against this reading's compiled grammar and
   its gates pass (completeness, membership) — extended across pure
   renames by the alignment witness. "Which rows fit" is a computed
   licence like "which readers accept"; nothing keys off `.md`.
4. **Precedence among applicable tables**: docked on this reading (the
   relation instance) → bound in the policy record (the ring holds
   default row-bindings per grammar identity — settings, so tier-3
   editable like everything else) → shipped with the instrument (the
   grammar languages' reader-facet forms ARE shipped rows) → none.
5. **The floor is the guaranteed else.** No applicable ceiling → the
   spine-protocol floor, addressable and editable; the dock OFFERS
   authoring or loading rows. A table failing its gate is a refused
   offer with the gate's words — never a partially-applied ceiling:
   applicability is all-or-nothing per table, hole-free by construction.
6. **Within a drawing**: rule-keyed row → kind-keyed floor by MRO →
   raising default for non-nodes. The same dispatch discipline as the
   engine, ending in words.

## 6. What the leaf must be (the client's requirements)

Unchanged and non-negotiable (space_2/3 settled): real text planes for
anything selectable/editable (canvas text is disqualified — the wolf
finding); one geometry, computed server-side; controls are real browser
controls; the leaf derives nothing; deterministic probe drivability
(`?probe=1`); censusable frames.

Grown by this design: (a) the leaf renders element blocks it does not
interpret — capsule chrome and edge tones are still just paint plus hit
ids; (b) the cursor wash must land in ONE frame across every facet
showing the subject (co-selection is the product; a laggy wash breaks the
tesseract rule's legibility); (c) cameras stay in the leaf per facet
(a camera is the hand's), but the orbit ring's rotation posts `spin` and
receives new placement — the leaf never re-derives orbit positions; (d)
windows keep their own layers; the element blocks repeat per window.

## 7. The src shape (post-merge, the opsis branch)

The five modes survive with sharpened charges — the 2607xx naming closes
its circle:

```
src/opsis/
  opsis/     the spectacle — frame, tones, marks, the facet shell (§2)
  deixis/    pointing — the cursor, co-selection, address↔region maps
             (consumes lexic's T3 records; owns NO address derivation)
  eidolon/   shape — the geometry SOLVE (B3's opsis half): lanes, orbit,
             split tree, cameras' laws; measures in the named measure
  kairos/    time — clocks, scrubbing, watched runs, trace consumption
  praxis/    doing — the graph, sessions, ingress workers, travel,
             policy; invokes lexic, never transforms
```

Boundary law, restated once: praxis invokes, eidolon arranges, opsis
paints, deixis points, kairos schedules — and anything SAYABLE about a
subject comes from lexic (VISION §2). The wire module sits in opsis; the
gate drives rooms as data; the browser probe stays.

## 8. Questions this raises (for QUESTIONS.md when ruled)

1. Element blocks vs pixel blocks: does the leaf draw capsules FROM
   `#CAPS` (leaf owns capsule chrome, ~40 lines) or keep pure pixels with
   `#CAPS` as gate-metadata only? Recommendation: metadata-only first —
   zero leaf change, full gate benefit; promote to drawn-by-leaf only if
   chrome duplication across facets measures as real cost.
2. Does the trail facet subsume the masthead trail, or draw only in the
   map room? Recommendation: masthead trail everywhere (one line), trail
   facet only on the map.
3. Where the shell's `Room`/`Facet` declarations live: records on the
   spine (praxis snapshot draws them in the value room — self-portrait
   for free) vs plain classes. Recommendation: spine records; the ring
   closing over the instrument's own room declarations is the
   self-representation proof at zero extra cost.
