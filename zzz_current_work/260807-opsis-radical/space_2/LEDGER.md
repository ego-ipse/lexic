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

## Not ported yet

The dock · the ladder · pins and the pin chip · the rail chip · pop-as-window
· strata · places · verdict badges · the routes strip · Earley's column and
CAN COME NEXT in the spine · the gate.
