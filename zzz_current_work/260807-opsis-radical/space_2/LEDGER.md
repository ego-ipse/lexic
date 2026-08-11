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

## What is NOT here, and is next

space_1's `gate.py` — 44 census facts, driven, exit 0 or not done. space_2
has no equivalent, which means everything above is verified by having been
DRIVEN once, not by anything that would notice if it broke tomorrow.

## Not ported yet

The dock · the ladder · pins and the pin chip · the rail chip · pop-as-window
· strata · places · verdict badges · the routes strip · Earley's column and
CAN COME NEXT in the spine · the gate.
