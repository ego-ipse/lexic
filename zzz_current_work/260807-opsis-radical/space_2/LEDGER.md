# space_2 — a port, not a redesign

space_1's whole server, with the leaf reduced to two halves it cannot have an
opinion about: a canvas that paints marks, and real text planes the browser
draws. Every visual decision below comes from a space_1 file, named.

## Where each thing came from

| here | ported from |
|---|---|
| `opsis/frame/tones.py` | `leaf/leaf.css` `:root` — the eleven variables, the faces, the line height |
| lane tones (closed · active · pending) | `leaf/chart.js` — fill to the CURSOR, not across the span; ahead-spans carry no fill |
| `eidolon/camera.py` | `leaf/graph.js` — layout-centred orbit, focal `max(900, reach·9)`, the fit as a BOUND so the picture cannot pump as it turns |
| facet titles, tab words | `praxis/reading.py` + `eidolon/topology.py` `graph_facet` — unchanged |
| the head (`h2`), the tab strip, the selects | `leaf.css` `.facet h2` / `.tabbar` / `#gview` |
| masthead, status, the hint sentence | `leaf/index.html` |
| the arrangement tree | `opsis/space.py` + `scene.staged` — the same tree, walked here instead of in the leaf |
| editing | `praxis/history.py` `retype` — an edit is a re-reading; the frontier is the kernel's own cursor, never scraped from prose |

## What changed, and only this

`scene.py` grew `staged()`: the decisions `scene()` was already making, in a
record, so the drawn frame reads the same ones instead of making its own.
`scene()` still spells exactly what it spelled.

## Deviations redone since

- **The verdict clipped** because the frame was right-aligning by an ESTIMATE
  of the text's width. A text mark now carries its anchor and the engine that
  knows the true width does the aligning.
- **THE SPINE overran its region.** It is a `.scroll` region in `leaf.css`, so
  it scrolls: what fits is drawn from its own top, JUST CLOSED keeps its place
  at the foot, and the overflow says how much more there is.
- **Ctrl+wheel zooms** — `doc.zoom`, `chart.zoom`, `spine.zoom`, `graph.zoom`,
  the keys the policy already had. Wheel scrolls, Ctrl+wheel zooms, which is
  the pair `graph.js` uses.
- **The camera starts where `graph.js` starts it** — yaw 0.42, pitch 0.92, not
  the values I had guessed.
- **A tab switch carries the column and the index**, worked out by the frame
  that knows the arrangement, so nothing downstream reconstructs a layout.

## What a gesture costs

4 ms, measured over the whole loop. Four things are facts about a READING and
are kept against it rather than redone per frame: the staging (`scene.staged`,
keyed on what staging actually reads — turning the camera does not re-decide
which rules the reader defines), the overview band, the clock's boxes read off
once instead of re-split per frame, and the chosen rule's occurrences. Before
these, a frame cost 230 ms and typing felt like a slideshow.

## Ported since

- **The dock** — every facet as a node, lit present, dim minimized. A
  minimized facet merges out of the arrangement tree rather than being drawn
  and hidden, and keeps all its state in policy (`facet.<name> on|off`).
- **The ladder** — the lineage strip, from the `chain` the policy already
  carried. The rung you are in is warm; the rest are dim.
- **`◉ focus`** — keeps the chosen rule, everything it reaches, and its direct
  referrers; the rest fades. Measured: 32 rules → 12 kept, 20 faded, 44 edges
  → 14. With nothing chosen it fades nothing, because a focus with nothing to
  focus on would fade the whole picture.
- **`⧉ window`** — opens that facet alone, on the same session.
- **The selects are selects.** `#gform`, `#gview` and `#cclock` are single
  controls showing the value they are ON, and clicking advances them. I had
  drawn a row of every option, which is both a different instrument and too
  wide for the head it has to sit in.

## Two measurement faults, and what they were

- **A colour is not a size.** The frame derived a text mark's FACE from its
  TONE, so a chip lit `cool` had no face of its own and fell back to 12.5px —
  head chips overlapped each other. A text mark now carries its face.
- **A glyph outside ASCII is not one cell wide.** `◉`, `⧉` and `⊳` come from a
  fallback face and take about half again the room, which is the rest of that
  overlap.

## Ported since

- **The routes strip** — the road not taken, run on a thread once per reading
  and drawn while it runs. `kairos.parse.parity` was already here and unused.
  Pending is drawn, never blank: a strip that is empty while it thinks reads
  exactly like a strip with nothing to say.
- **Verdict badges** — the PDA analysis' own class per rule (`attempt`,
  `island`, `gated`, `hard`), worn on the rule's head line, on the PDA clock
  only. Silence IS the deterministic verdict, so a predictive rule wears
  nothing. `kairos.engine.verdicts` was here and unused too.

## A head under pressure derives less

THE DERIVATION cannot hold its name, its sentence and a parity verdict at
once. So a finding outranks a description — the subtitle gives way first —
and the verdict is said SHORT rather than said half: `both engines built the
same value` clipped mid-phrase still reads as a finding, and clipped earlier
reads as its opposite.

## Ported since

- **THE SPINE follows the clock**, as the contract states it. `model` = the
  open model spans with JUST CLOSED at the foot · `pda` = the kernel's own
  frames at the cursor (clone names, rolled-back ones in red) plus the
  decisions it made near here · `earley` = the cursor's column as dotted
  items with their origins, and CAN COME NEXT. `kairos.parse` already had
  `column` and `decisions`; both were unused. The recognizer kernel is
  retained, so moving the cursor on the Earley clock costs 24 ms after the
  first column rather than re-parsing the document.
- The spine's gutter is as wide as the widest thing in it: a column of
  origins clipped to `@41…` says nothing at all.

## Ported since

- **`▤ rail`** — the chip raised beside a rule when you choose it, in the
  reader, which is where the pointer was. Clicking it shows that rule as the
  track it describes and scrolls the rails TO it: the drawing already labels
  every rule's row, so the scroll can be a NAME and nobody computes a layout
  twice or holds a second copy of one.
- Co-selection reaches the lanes: a chosen rule's spans are ringed violet
  wherever they appear, which is what "click a rule → its spans outline
  violet everywhere" means.

## Ported since — windows that are their own

- **Per-window state.** A window looks through its OWN layer over the
  session's policy (`ChainMap`): its view, its camera, its scroll are its own,
  and a gesture made in it writes there. Measured: a window switched to
  `rails` leaves the main instrument on `depth 3d`, and both hold. The CURSOR
  is deliberately not in that layer — it is a cursor on the subject, and being
  visible everywhere at once is the whole point of it.
- **`⌖ pin`** — raised at the selection, because that is where the hand is.
  Clicking it opens a window on that span with its own layer. The pin says
  what the range IS: the exact occurrence if there is one, otherwise the
  smallest span covering it — the same answer selecting text gets, because it
  is the same question — and says plainly when nothing covers it any more.
- A pin wraps its text to the window rather than clipping it.

## Ported since

- **A pin knows which reading it was made against** and says `STALE · made
  against gen N` when the reading has moved on without it. It still says what
  it said; it just stops pretending that is current.
- **THE STRATA** — the session pulled back. `praxis.strata` has written this
  ladder since the first build and nothing had ever drawn it: every rung
  walked, the one above it (`not yet visited — travel builds it`), each
  rung's little depth band, and the doors it holds — its value, its machine,
  its artefacts. Reached by `⌗ strata` in the masthead, left by `✕`.

## Ported since — the rooms

`opsis/rooms.py` has written these since the first build and nothing had ever
drawn one: **the rules** by what they account for (each a door to its own
room), **one rule** with everything it is, **the machine**, **the artefacts**,
and **any value as the value it IS**. A room nobody authored says so in place,
with what this reading DOES hold. Reached through the strata's doors, left by
`‹ back`.

A section kind this frame draws no shape for prints its own name rather than
vanishing — the raising default, said on screen. Two kinds are in that state
today: `graphview` and `irvalue`.

## Noticed, not touched

The rules room lists `object` three times (299, 117, 117) and `array` twice.
That is several codegen rules spelling back to one source name, which is what
the room was asked for; making them look unique would be the frame inventing
an answer the reading did not give.

## Ported since

- **`irvalue`** — a value as the value it IS: what it HOLDS, one row per
  child, the field that names it, what it is, and its payload where it has
  one. Tier is the colour, because the tier is what the thing is. It does not
  repeat the counts the room's own section already gave.
- **The tune dials** (`#gtune`) — drawn bottom-right, where a railroad list
  and a graph both have their least content, and only for the views that
  offer them. A slider is configuration and configuration is the server's:
  the hand posts where along the track it let go, and what comes back are new
  places. `eidolon.layout.TUNE` was already the vocabulary.

Verified end to end: dragging `levelstep` moves its knob 653 → 557, and
`flatten` changes the picture's y spread 557 → 636.

**And one thing that correctly does NOT change.** Dragging `levelstep` leaves
the picture the same SIZE: the rings move apart in z and the camera's fit —
which is bounded by the cloud's radius, on purpose — takes up the slack. That
is the ported behaviour doing its job, not a dial that failed to connect; the
difference shows as perspective, not as scale.

## Ported since

- **`graphview`** — a rule's own NEIGHBOURHOOD, in columns by distance: the
  rule, what it reaches in one step, then two. `eidolon.topology.reachable`
  says a rule's neighbourhood is a different graph from the whole grammar's,
  and answering a question about one rule with a picture of everything is
  what it exists to avoid. Every node in it is a door to that rule's room.

Every deviation and every unbuilt facet named in this ledger is now built.

## The gate

```bash
uv run python zzz_current_work/260807-opsis-radical/space_2/gate.py    # 0 = done
```

35 facts over the real composer — the frame is data, so nothing is mocked and
no browser is needed: if a fact is true here, it is true of what the leaf
would be sent. It defends what was got wrong: a tone that is not in the
register, a face derived from a colour, a span ahead of the cursor drawn as
filled, a clock that changes one panel and leaves the spine talking about
another engine, a window that writes into the session, a room that draws
nothing rather than saying it is not there. It runs in 6.4 ms a frame and
asserts that.

It found two things on its first run that were not gate bugs:

- **the "edited — unread" mark was missing from the rebuilt plane.** I wrote
  it before the second deletion and never re-added it in the port, so a
  document could be typed in with nothing saying the derivation beside it was
  of the last reading.
- **`value` has no spans of its own** — it is spelled by whichever arm it
  took — so a check written against it was testing nothing.

## The bug the probe could not see

space_1 rendered its rule graph with the labels detached from the lines, on
the user's screen and not on mine. The cause: **a canvas is a replaced
element.** It has an intrinsic size from its `width`/`height` attributes, so
`position: absolute; inset: 0` does NOT stretch it — its layout size becomes
its BITMAP size. The bitmap is set to `w × devicePixelRatio`, so at 1× the
two numbers coincide and everything looks right, and at 2× the canvas lays
out at twice the box it sits in: the drawing goes with it, and the chips —
DOM elements positioned in CSS pixels — stay where they belong.

Measured, before and after:

```
before  dpr=1  wrap=587x603  cv.css=587x603     ← coincidence
        dpr=2  wrap=587x604  cv.css=1174x1208   ← twice its box
after   dpr=2  wrap=587x604  cv.css=587x604     bitmap 1174x1208
```

space_2 never had it — its canvases say `width: 100%; height: 100%` — but
the probe could not have told me so, because it only ever ran at 1×. **It
runs at 1× and 2× now**, and asserts each canvas lays out in the room it was
put in, measured against the WINDOW rather than against the canvas's own
numbers, since those numbers are exactly what is wrong when this breaks.

### And a canvas that keeps yesterday's bitmap

Measuring space_1's other canvases turned up a second one of the family: its
chart sits in a **431px box holding a 503px bitmap** — the picture squashed
14% — because only its PINNED windows observe their size. Nothing redraws the
main grid's canvases when a facet's box changes, so the bitmap is whatever it
was when something last happened to draw.

space_2 cannot have that fault, and the reason is structural rather than
careful: the server owns the layout, so every layout change ARRIVES AS A
FRAME, and the size is re-measured on the way in. The probe now proves it by
shrinking the canvas's box and checking the bitmap follows — `box 520 ·
bitmap 520 @1`, `box 520 · bitmap 1040 @2`.

The lesson is about the harness, not the CSS: a check that cannot distinguish
two values which happen to be equal in the only environment it runs in is not
a check. Every screenshot I took of the "broken" render was at 1×, where
there was nothing to see.

## The probe

```bash
zzz_current_work/260807-opsis-radical/space_2/probe.sh    # 0 = done
```

Seven facts the gate cannot reach, checked by the leaf standing in the
browser looking at the result: the canvas is sized to its element rather than
stretched into it · every text plane sits on the geometry it was sent · a
character is the width the frame believes · a line is the height it believes
· a box paints where the frame put it, in the tone it named · landing on a
tab changes which facet is shown · the leaf paints without waiting for an
animation frame.

Two of those are there because of specific failures:

- **`requestAnimationFrame`.** An earlier harness scheduled through it, and
  headless Chrome does not fire it under `--virtual-time-budget`, so every
  "verified" measurement read a canvas that had not been drawn. The probe
  awaits `ask()` and asserts the leaf schedules nothing.
- **The glyph geometry.** Every highlight drawn under the text is placed with
  `CELL` and `ROW`, which were my estimates. The browser now says: 7.526
  against a believed 7.5, and 19 against 19. Guessed widths are what clipped
  the parity verdict, the graph chips and the strata's doors; this is the
  measurement that stops it being a guess.

## Popping and cloning were the same thing

Both opened a window and left the grid alone, so `⧉` and `⊞` differed only in
their glyph. They mean different things: **⧉ takes the facet OUT of the grid**
— it is somewhere else now — and **⊞ leaves the grid the one it has** and
opens a second view beside it.

The meaning is the SESSION's, not the leaf's. The leaf opens the window,
because only a browser can, and then says what happened; what popping means
is a gesture the session answers, which is why it can be gated at all. And
the dock is where a popped facet comes back from, so closing its window
leaves a dim chip rather than a facet nobody can find — which is exactly what
made a popped-out facet feel broken in space_1.

## A window is not something only the graph can be

`⧉ window` was written on the graph's head alone, which made popping out a
property of that picture rather than of facets. Every facet's head carries
`⧉` and `⊞` now: pop it out, or open a SECOND one. Two clones of THE
DERIVATION keep their own clocks — one on `pda`, the other on `model` —
because each window looks through its own layer.

The gate caught the new `clone` hit immediately, which is the check doing its
job: a hit must be answered by something. It also showed the check was a flat
allowlist hiding a real distinction, so it now says which kinds the SESSION
answers and which the LEAF does — and the leaf's list is exactly `pop` and
`clone`, the two things a browser must do itself.

## Two answers to "is it playing"

The leaf kept its own flag to decide whether to send ticks; the session kept
one to decide whether a tick advances. Two copies of one truth, and they
disagreed the moment playback started from anywhere the leaf could not see:
clicking ▶ in the transport set the session running and the leaf, knowing
nothing about it, sent no ticks. The reading sat still while the instrument
believed it was moving.

The frame's own head says it now — `#FRAME w h gen marks playing` — and the
leaf ticks while the frame says so. It holds no answer of its own, and the
probe asserts that it does not.

This is the same fault as every other one this rebuild exists to prevent,
wearing different clothes: not two GEOMETRIES disagreeing, but two copies of
one fact. The rule is the same either way — one truth, and it is the
server's.

## Two keys for one scroll

The rail chip wrote `top.rails`, the wheel wrote `top.graph`, and the drawing
read `top.rails` — so the chip worked and the wheel did nothing at all. It is
the facet's own key now, and a notch is worth what the FACET says it is
worth: a plane scrolls in lines because a plane knows what a line is, and a
stack of railroads has no lines, so it says 26px.

Seams were never verified either. They hold: dragging the first one moves
THE DOCUMENT's head 389 · 749 · 914 across a quarter, the measured rest, and
six tenths.

## Three cursors on one subject

Cursors live on the SUBJECT — time, selection, hover — and every facet
renders them in its own coordinates. Two of the three were missing.

- **Hover did not exist.** It does now: the leaf reports what the pointer is
  over ONLY when that changes, so a hand crossing a facet is one gesture and
  not a thousand, and the server decides what it means. Hovering a rule
  lights it; hovering a SPAN lights the rule that read it; letting go lets
  go. It does not move the cursor and does not choose — that is what makes it
  the lighter twin of selection rather than a second one.
- **Selection worked one way only.** Selecting in the document asked what
  value those characters are; selecting in the READER did nothing at all.
  It now asks the mirror question — which rule are these characters part of —
  and lights its every occurrence. One gesture, one meaning, whichever text
  you are standing in, which is what crossing the reader/read boundary means.

## Grammar is the ground truth — including when you type in it

Re-reading only ever looked at the DOCUMENT. Typing in THE READER and
pressing `Ctrl+Enter` did nothing at all, which makes the reader a note in
the margin rather than the thing that decides what the document says.

It reads both planes now. Rename a rule throughout the grammar and the
document re-reads under it — the same language, 12,219 spans either way, but
the spans are now CALLED `sp` where they were called `ws`, which is what
proves the new reader is the one that read. A reader that no longer compiles
is a refusal like any other: the old reader stands, the reading keeps its
spans, and what you typed stays where you typed it.

**Focus belongs to the facet, not to one view.** `◉ focus` faded the ring
graph and nothing else; a rule's neighbourhood is the same neighbourhood
whether it is drawn flat, arced or in three-space, so `graph_drawing` takes
what focus keeps.

## The ring

`praxis/roots.py` and `fixtures/policy.gbnf` were both here, unused: the
instrument's own state as a text it can read. `◌ ring` in the masthead opens
it — `policy.gbnf ⊳ the policy grammar`, whose document is the presentation
record, with spans, a spine and a verdict like any other reading.

**And saving it APPLIES it.** The parse already proved the record
well-formed, so applying is reading the lines it holds: write
`chart.clock earley` and `facet.spine off` into the instrument's own
document, save, travel back down, and the derivation is on the Earley clock
with the spine minimized. A record the grammar REFUSES — a key outside
`[a-z0-9._-]` — is not applied, and says why.

That is the ladder closing into a ring: focus moving along a lineage edge
that points at the instrument itself.

## Travel

The strata drew a rung nobody could enter: `at rung n` closed the overlay and
did nothing else. Entering one now BUILDS it — `read_up` was already here and
unused — and the ladder below stays climbed, so coming back is a rung, not a
reload. Standing somewhere new is a new generation, which is what makes a pin
taken on the rung below go stale rather than quietly describing a text that
is no longer under it.

Two faults it uncovered in `praxis/state.py`, both ported forward without
being noticed:

- **The ladder named the reader by its FILE.** `reading.py` says in as many
  words that a metagrammar is not a file and the label cannot come from a
  path without lying about the pairing — and `chain()` took the path anyway.
  After travelling, the ladder said `json.gbnf ⊳ json.gbnf` while the
  masthead beside it said the truth.
- **The fixpoint could never be found.** The test compared a file name to a
  reader name — never equal — so at the top of the ladder the rung you were
  standing on was drawn twice. It compares the PAIRING now, and the climb
  stops where a text is read by its own metagrammar.

## Every reading, not one

The gate reads FOUR pairings now — the json grammar, its ABNF spelling, a
grammar whose arms cannot be decided, and a reader that REFUSES its document.
Everything above had only ever been driven on one, and that is exactly how
long the next fault stayed invisible:

- **A refusal said only `NOT FAITHFUL`.** The engine had already said
  `parsing: input does not derive from 'root'` and the instrument was keeping
  it to itself. VISION: refusals speak the engine's words, verbatim. There is
  a banner now, and the gate reads it on the pairing that refuses.
- **The banner was drawn UNDER the document's text.** The planes are real
  elements, so anything the one canvas painted in their rectangle was behind
  them — the refusal, the `⌖ pin` chip, the `▤ rail` chip, all of them. The
  instrument has always welded an under and an over canvas around its text;
  the frame carries an `#OVER` block now and the leaf paints it above. Found
  by looking at a screenshot, which is what screenshots are for.

The probe also caught its own weak fact on the first run — it clicked the tab
that was already showing, so "landing on a tab changes what is shown" could
not fail. A fact that cannot fail is worse than no fact.

## Read the reference. Every one of these was a guess that cost a session

A list of defects came back from real use. Each one below was fixed by
opening the space_1 file that already answered it, and several had been
"fixed" once before from memory, which is why they came back.

- **The PDA clock was the model's clock with other numbers in it.**
  `leaf/chart.js` does not draw them the same way at all: a frame's row is
  its STACK DEPTH, its colour is the kind of clone that pushed it
  (`AUTO_INK`: dispatch cool, alt warm, seq token, value_str violet, group
  dim), a frame the attempt machinery rolled back is red — the same fate
  register as Earley's abandoned hypotheses — and a frame wide enough to
  read says WHAT IT IS inside its own box. Boxes alone made the two clocks
  look like the same picture twice. Hovering one names it in the readout.
- **The reader badged only the rules that gave the machine trouble.**
  `_badges` dropped every `predictive` verdict, so a grammar of 39
  classified rules looked like a grammar of one — and it hid the thing the
  badges are FOR: that the other 38 are settled without a decision at
  runtime. `leaf.css` styles all five classes and `automaton.js` badges
  every rule it has a verdict for.
- **The status bar had been paraphrased.** `index.html` spells `#pos`,
  `#transport`, `#hint` and `#readout`; `frame.js` spells what each says.
  It says them again, including the readout on the right edge — what is
  under the hand, in the words of the thing it is on.
- **The clocks were not slow; the CLOCK was.** Playback advanced a fixed
  fraction of the document per tick and the leaf ticked every 110ms, so the
  cursor lurched nine times a second. The session now advances by real
  elapsed time and the leaf asks as fast as the socket allows. Measured at
  1500x850 over a 15,769-char document: 132 frames/s on the model clock, 133
  on the PDA, 43 on Earley — and all three cross the document in the same
  ten seconds, which is the point.
- **Choosing a rule highlighted nothing.** `planes.js` draws four things
  under the document's real text, in an order that matters because they
  overlap: what the cursor stands inside, every span of the chosen rule
  outlined violet, what is under the hand, and the selection.
- **A window was a browser window.** `window.open` for popping, cloning and
  pinning — a different document, which cannot overlap the thing it was torn
  from, and overlapping is the entire reason to tear one off. space_1's are
  in-page `.pin` divs. Here a window is a rectangle over the arrangement:
  the session says which exist, where each sits and what it is about; the
  frame draws them last, over the text.
- **`▤ rail` showed the whole railway scrolled to a rule.** `paint.py` has
  carried `rail_drawing` — "one rule's track, alone — what a pinned railroad
  window shows" — beside `rails_drawing` the entire time.
- **The graphs could not be panned and only the railroad zoomed.**
  `graph.js`: a drag pans every view but the three-space one, where it
  turns; the wheel zooms, except on the railroads where it scrolls and
  Ctrl+wheel zooms. The zoom is anchored at the pointer.
- **A picture drew straight over the facet beside it.** In the leaf each
  view had its own element and CSS clipped it. One canvas has no layout to
  clip with, so the frame says it as a mark: `clip`/`unclip` around every
  region and every window.

- **The masthead carried buttons the reference had dropped.** `boot.js`
  says it in as many words — *"The strip is dead: the masthead carries ONE
  chip — where you are"* — and clicking it opens the strata. A row of rungs
  with separators, plus a `⌗ strata` chip, plus a `◌ ring` chip, was a map of
  the climb drawn in the one place with no room for a map and two more
  buttons for a door that already had one. One chip now, `#pincount` beside
  the dock where `index.html` puts it, and the instrument's own state is a
  door in the strata — in its own column, tagged *the instrument*, which is
  what `rooms.js` does with a lane outside the chain.

- **Resizing was finnicky for two reasons, both arithmetic.** A share was
  measured against the WHOLE WINDOW when a split divides only its own
  subtree, so a nested seam jumped away from the hand by the ratio between
  the two — `wire.js` carries `base` and `size` on every seam edge for
  exactly this, and the hit carries them here. And the share list was padded
  with `0` up to the seam being dragged, so moving the second seam set the
  first split to zero width, changed the shape of the tree, and renumbered
  the seams mid-drag. The placeholder is negative now: a share is a fraction,
  so no real one can be, and "the hand has not said" is a thing the layout
  can be told.

- **The arrangement could not be RESHAPED, only resized.** `wire.js` makes a
  facet's head an alias of its node: drag it onto another surface and where
  you let go decides what happens — the outer quarters split, the middle
  tabs, and `#dropzone` says which before the hand lets go. Here the head is
  a hit nobody clicks, the leaf reports where in the target the pointer is as
  a FRACTION, and one function decides what a fraction means. The shape is
  written as a shape, because a shape recomputed from measurement on the next
  frame is a hand's work thrown away. A tab group is one region, so dropping
  beside a tabbed surface splits the region it shows in — there is only one
  box there.

- **A graph's nodes were words floating in space.** `.gchip` is a name in a
  BOX: field2, a hairline, 10px mono, centred on the node — and four things
  it can be, each with its own edge and colour. `.near` is cool and ink,
  `.start` is warm, `.marked` is violet, and `.hot` fills warm and reads the
  name out of it. Distance is in the SIZE: the projection scales the chip
  between 0.55 and 1.2, so three faces stand in for that here, because a
  registered face is a thing and a scale is not something a mark can carry.

- **A popped facet could not come home.** `popout.js` keeps the tree the
  facet left from and `dockFacet` restores it — *"back into the arrangement
  it left, exactly where it was"*. Closing the window here just deleted the
  window and left a dim chip you had to find and click, which put the surface
  back wherever the measurement felt like. The window remembers its home now.

- **The spine had one panel where the reference has two.** `spine.js` gives
  every clock a CAPTION saying what it is showing — *open at the cursor* /
  *the PDA's stack at t* / *Earley column N — M items* — and a second panel
  under the stack: JUST CLOSED, DECISIONS, or CAN COME NEXT as warm chips.
  Only the model had a footer here, and the PDA's decisions and Earley's
  expected terminals were mixed into the stack rows as if they were frames.
  All three go through one shape now, so a clock cannot invent its own
  furniture. (`decisions()` returns nothing for `json.gbnf` — the walk really
  is deterministic descent, and the footer says so in the reference's own
  words. The `decide.gbnf` fixture yields 96, so the panel is not empty
  because it is broken.)

- **The overview band stayed the model's on every clock.** `chart.js`
  chooses: `clock !== 'model'` draws the RUN's own texture instead — the
  PDA's stack depth in cool with a warm mark wherever it decided, Earley's
  live hypotheses in violet, red where they died, blended where both
  happened in one bucket. A band that says the same thing about three
  different runs is furniture. The alpha ramps continuously there; a tone is
  a name, so these are its endpoints in four steps, and the blend ramps too —
  flat, it made every bucket identical on a document where both happen
  everywhere.

- **The reader lit two states where the reference lights three.** They are
  three different questions: `.live` is the rules the derivation is inside
  RIGHT NOW — so playing walks the grammar itself rather than only the
  picture of it — `.lit` is what has been chosen, and `.hot` is what the hand
  is on. Here everything that lit at all was washed the same, and the chosen
  rule wore `.hot`, which belongs to the pointer. Drawn weakest first, so the
  hand always wins the line it is over. One gate fact had encoded the wrong
  mapping and was corrected against the CSS rather than around it.

- **Choosing a rule did not SHOW it.** `litRules` ends by scrolling the
  reader to whichever rule is selected, hot or chosen —
  `scrollIntoView({block: "nearest"})`. A rule chosen from the graph or the
  lanes is usually not the one on screen, and a highlight you have to go
  looking for reads as a highlight that did not happen. The session says
  which line must be seen; the frame does the nearest-scrolling, because only
  it knows how many rows fit. Scrolling by hand says where you want to be and
  clears it.

- **The document did not follow the cursor.** `followCursor` keeps the
  cursor's line on the page while the reading plays, and lands it four tenths
  down when it has to move — where the eye already is, not one line inside
  the edge it just crossed. Without it, playing runs the cursor off the
  bottom and the derivation is being told about text nobody can see. The
  reader's `scrollIntoView({block: "nearest"})` and the document's 40% are
  two different behaviours in the reference, and they are two here.

- **The status bar promised keys the instrument did not have.** The hint is
  ported verbatim from `index.html` and says *g graph · [ ] speed*, and
  `gestures.js` also binds `p` to pinning what is selected. None of the four
  existed. A promise the instrument does not keep is worse than one it never
  made — the gate now counts thirteen keys where it counted eight.

## What using it found — a second list, and what each one really was

Every item here came back from real use, and every one had the same cause:
code written from a memory of a reference file that was open at the time.

- **The status bar's buttons landed on nothing.** `do` — the kind every
  transport chip carries — was not in `LANDED`. The gate's "answered" set
  NAMED it by hand instead of reading the table, so a list of what should be
  answered passed while nothing answered it. It reads `LANDED` and `SAYS`
  now.
- **The bar walked about.** `#pos` is `min-width: 30ch` and WRAPS; mine grew
  with its text and shoved the transport along. And the speed had limits I
  invented — `setSpeed` is 1/512 to 16, and `speedWord` spells anything under
  one as a fraction.
- **▤ rail did not appear at all**, because a text plane is a REAL element:
  a click in the reader never reaches the canvas, so `sel` is the only report
  that a rule was chosen there and it carried no pointer. The chip itself was
  the wrong object — `#railchip` is one floating button at the pointer, 11px
  sans, raised from the reader, the rails, the automaton and the graph alike.
- **The space bar did nothing** because both planes were editable. Only
  `#docText` is: `#grammarBody` takes no letters, which is what lets Space,
  `g` and `[` `]` work while the reader has the hand.
- **Clicking the derivation landed on the wrong character.** The facet had
  three left edges — 0, 6 and 10. `chart.js` has one: `pad = 10`.
- **The lanes slid out from under the hand**, because the window was
  recomputed from the cursor every frame. `chart.js` keeps `view0` and moves
  it only when the cursor leaves. Only the frame knows the width, so the
  frame reports what it worked out and the session remembers it.
- **Playback ran at twice the pace.** `tick` crosses the document in 22
  seconds; mine did 10.
- **A window could be seen and not touched.** The planes are real elements,
  so a canvas drawn over one still passes every click into the textarea
  underneath — which is also why closing a window did nothing. Each window
  carries a pane of glass now.
- **Every graph was the wrong size**: `graph.js` auto-fits each view to the
  facet, capped at 2.4, and every view here was placed at scale 1.
- **A drawing's box is an OUTLINE** in `paint.js` and a FILL in
  `drawChartBand` — the consumer decides. Filling every box in its edge tone
  turned every graph node into a solid slab; then stroking them all flattened
  the overview band to a row of empty rectangles.

## The slop, counted

Thirteen places drew a rectangle as four `said.line` calls over four corner
tuples — a hundred lines doing what `said.ring` already does. Converting them
found two bugs that had been hiding in the duplication: the transport's
buttons were forty pixels tall instead of sixteen and clipped to two strips,
and a verdict badge was drawn at a negative width. `facets.py` is still 1,570
lines and still holds the planes, five graph views, three clocks, three spine
stacks, the pin and seven module-level caches. It wants splitting — but not
before the rest of the duplication in it is gone, or the split just moves the
slop into four files.

## The derivation — and two wrong diagnoses, kept as a warning

I said the lanes were 20px against the reference's 11, then that the two
instruments were folding the document to different depths. Both were wrong,
and both were "measured" by eye off a screenshot crop.

MEASURED PROPERLY:

- both readings are the same: **12,219 spans, max depth 19**
- the reference's chart canvas is **476x467**, so its lane is
  `(467 - 48 - 8 - 24) / 20` = **19.35px**, and mine is **20**

The lane heights agree. `chart_drawing` is byte-identical on both sides and
neither scales the drawing when it paints it.

Traced to the end: both sides emit `lane - 2` for a box's height and both
compute `lane = max(6, min(22, (tall - 24) / deep))`. Mine reaches the 22px
CAP — box height 20 — because my chart facet is about 508px inside, where the
reference's canvas is 467. At the same size both draw 19.35.

So the derivation's geometry is right and its tones are right. And the room
is not a code difference either: `praxis/reading.py` is BYTE-IDENTICAL on both
sides and `opsis/space.py` differs only by this port's own additions, so the
appetites and the arrangement maths are the same. The 508 I measured came
from a session whose seams I had been dragging all afternoon.

MEASURE A FRESH SESSION BEFORE CHASING THIS. Every number in a served
instrument is a number about that session's policy as much as about the
code.

DO NOT MEASURE A PICTURE BY LOOKING AT IT. Every real finding this session
came from dumping the numbers — the frame's marks, the canvas's own width and
height, a policy value — and every wrong one came from squinting at a crop.

## The spine — done, and seen

`gestures.js` binds click to the selection and mousemove to the hover on both
spine panels; `frame.js` reads `focus = hover >= 0 ? hover : sel`, so the warm
readout says `under the hand · …` or `selected · …` and THE HAND WINS while
the pointer is on a row.

Every row here emitted a hit of ZERO WIDTH, so nothing could be hovered or
clicked and the readout could never change from the spine at all. A row
carries its address now and is a real rectangle. Only the model spine's rows
carry one — `drawPdaSpine` and `drawEarleySpine` build rows without
`dataset.i`, and clicking those does nothing in the reference either.

And `chart.js` draws THREE outlines over a model lane, not one: ink for the
span under the hand, warm for the selected one, violet for every span of the
chosen rule, each 1.5px outside the box. Only the violet was here, so the
derivation said nothing about what the spine was pointing at.

Seen, not just measured: hovering `member 4..1,263` — the spine's d3 — draws
a bright outline around that exact lane.

## The spine, as it was

`gestures.js` binds both spine panels the same way:

    click     → cur.sel = +row.dataset.i        (SELECT that span)
    mousemove → cur.hover = +row.dataset.i      (hover it)

and `frame.js` reads `focus = cur.hover >= 0 ? cur.hover : cur.sel`, so the
warm readout says `under the hand · <span words>` or `selected · <span
words>`. THE HAND WINS: a hover outranks a selection while the pointer is
there.

Here every spine row emits `said.hit(x, y, 0, 0, ...)` — zero width — so no
row can be hovered or clicked and the readout never changes from the spine at
all. `_rows` needs to emit a real rectangle per row carrying that row's
address, and a `Row` needs a fifth field to hold one.

Only the MODEL spine's rows carry an index in the reference: `drawPdaSpine`
and `drawEarleySpine` build rows with no `dataset.i`, so clicking those does
nothing there either. Do not invent behaviour for them.

Clicking a railroad chooses the rule, raises the chip and scrolls the list to
it. I reported `railsGoto` as not taking; that was wrong — `json-text` is
still the FIRST MARK in the drawing after the scroll, and I read its name
instead of its position. It is drawn at y = -1124 afterwards, which is the
list having moved 1,237px. Read the number, not the order.

## What is IDENTICAL, so nobody chases it again

Checked with `diff`, not by eye:

- `praxis/reading.py` — byte-identical
- `eidolon/layout.py` — byte-identical
- `opsis/paint.py` — differs only by the `keep` argument this port added, so
  `graph_drawing`, `rails_drawing`, `chart_drawing` and `automaton_drawing`
  all produce the same marks from the same reading
- `opsis/space.py` — differs only by this port's own additions

So every remaining visual difference in a graph, a railroad or the derivation
is in how the FRAME PLACES what those files drew — the fit, the pan, the
dots, the tones — and not in what was drawn. Diff first. Two of this
afternoon's wrong diagnoses would have died in one command.

## The graphs — where the pass got to

`graph.js` fits against the extent of the nodes it PROJECTED. Mine fitted
against `drawn.wide`, the width the layout was asked for — and a drawing laid
out to fill its room reports about that room, so the fit computed 0.96 and
did nothing at all. That is what "flat and arcs look like shit" was: the
picture wherever the layout dropped it, in a corner of an empty facet.
`_bounds` measures left and right now as well as top and bottom.

MEASURED ON A FRESH SESSION, AND RIGHT: flat's rings span y 305.5..612.6 in
a facet whose inside is y 83..876 — 307px of picture with 222 above and 264
below, centred within about twenty pixels. Width binds, because the flat
layout is wide and short and the fit preserves aspect, which is what
`min(availW/(x1-x0), availH/(y1-y0), 2.4)` does.

I first read this as "106px low" by measuring a session I had been dragging
all afternoon AND letting the status bar's own rings into the maximum. Twice
in one measurement. Filter to the facet's room and use a server nobody has
touched.

## Still wrong, reported from use — DO THESE

- **flat, arcs and the automaton are broken.** The fit now measures against
  what a drawing REACHES rather than the box it was laid out in, and flat
  measures centred on a fresh session — but the user says all three are still
  wrong, so the measurement is not the picture. `layout.py` and `paint.py`
  are byte-identical, so it is placement: compare against `graph.js`'s
  `v.frame.k`, `mx` and `my`, which fit against the PROJECTED extent with a
  per-view pad taken from the widest label, and centre on the LAYOUT's middle
  — not on the drawing's bounding box, which is what this port does.
- **The dials are drawn, and a drawn slider is not a slider.** `index.html`
  gives `#gtune` four real `<input type="range">` elements — depth 60..280
  step 10, ring 0.4..2 step 0.05, flat 0.2..1.2 step 0.05, and LABEL 0.7..1.8
  step 0.05, which this port never had at all. The same lesson as the
  dropdowns: a control the browser owns cannot be painted. They need the
  `#PICKS` treatment — placed by the frame, rendered by the browser.
- **A tab is an alias of its node**, and dragging one now moves that surface
  as dragging its head does. The drop overlay this port draws is not the
  reference's `#dropzone`; compare them.

## The masthead's last inch — and a reference bug NOT to port

The ladder's chip is forty pixels there and a hundred and ninety here, and I
was ready to shrink ours to match. Do not.

Nothing in space_1's Python ever emits a `#LADDER` block. `wire.js` parses
one, so `S.ladder` is always EMPTY, and `renderLadder` falls through its own
fallback:

    chip.textContent = (focused ? focused.label : '…') + '  ∴'

The reference's tiny chip is `…  ∴` — a placeholder for data that never
arrives. This port shows the pairing it stands on, which is what that chip
was meant to say.

MATCHING A PICTURE IS NOT THE GOAL. The reference is the authority on what
the instrument MEANS, and it can still be broken; a difference is a question,
not an instruction. This one would have been ported as a bug.

## The faces are believed, not measured — the next gap

The probe checks that a MONO character is the width the frame believes,
because a highlight sits under those characters. It has never checked the
sans faces, and the frame wraps the hint, right-aligns the verdict and packs
every head's controls from `ADVANCE`. Believed too wide, a line wraps early —
which is why the status hint breaks mid-phrase where the reference breaks a
clause later. Believed too narrow, two things overlap, which is how head
chips collided earlier.

The register now SENDS `advance <face> <px>` and the leaf reads it into
`frame.advance`, so the measurement is one fact away. Two attempts at writing
that fact made the probe exit silently — the plumbing is green on its own, so
it is the fact's own code. Write it small, run the probe after every line,
and remember that a harness which says nothing is worse than a known gap.

## Not ported yet

Strata as the landing page, and adding files from there.
