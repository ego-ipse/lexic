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

## Deviations still to redo

- The tune dials (`#gtune`) are not drawn.
- `⌖ pin` is NOT built. Pins are windows carrying their own camera, view and
  history — per-window state, where a popped window today shares the one
  session. Half a pin (a window that silently steers the main instrument)
  would be worse than none, so it is stated here instead.

## Not ported yet

The dock · the ladder · pins and the pin chip · the rail chip · pop-as-window
· strata · places · verdict badges · the routes strip · Earley's column and
CAN COME NEXT in the spine · the gate.
