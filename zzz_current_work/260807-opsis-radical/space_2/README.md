# space_2 — space_1, with the leaf reduced to two halves it cannot argue with

```bash
uv run python zzz_current_work/260807-opsis-radical/space_2/serve.py \
    resources/ground_truth/json.gbnf \
    zzz_current_work/260807-opsis-radical/tk/fixtures_long.json 8918
```

## What this is

space_1's whole server — every derivation, every drawing, every measurement —
with one thing changed: the leaf no longer decides anything. It is a canvas
that paints the marks it is sent and real text planes the browser draws, and
between them there is exactly one geometry, which is the server's.

That is the whole difference, and it is the point. space_1's late failures
were all two geometries disagreeing: a hover a lane deep, a picture identical
at every cursor position, a band in a colour the leaf did not know, a canvas
stretched instead of re-fit, a graph that pumped as it turned. None of those
are expressible here.

## Ported, not redesigned

Every visual decision comes from a space_1 file, named in
[LEDGER.md](LEDGER.md): `leaf.css` is the register, `chart.js` tones the
lanes, `graph.js` is the camera, `index.html` is the chrome, `reading.py` and
`topology.py` name the facets. `scene.py` grew one thing — `staged()`, the
decisions `scene()` was already making — so the drawn frame reads the same
ones instead of making its own.

## Facets

Five, as ever: **THE READER** (the grammar, in whichever form it is showing)
· **THE RELATIONS** (depth 3d, flat, arcs, rails, automaton — one facet, its
own selector, `◉ focus`) · **THE DOCUMENT** (real editable text) · **THE
DERIVATION** (the band, the lanes, and which clock they tell) · **THE SPINE**
(open at the cursor — model spans, the machine's frames, or Earley's column).

The masthead carries the ladder and the dock; a minimized facet merges out of
the arrangement rather than being drawn and hidden.

## Windows

A facet's head carries `⧉ window`; a selection raises `⌖ pin`. Both open a
window with its OWN layer over the session's policy — its view, its camera,
its scroll — while the cursor stays shared, because a cursor lives on the
subject and being visible everywhere at once is what it is for.

## Where the reading sits

`⌗ strata` in the masthead pulls the session back to the whole climb: every
rung walked, the one above it, each rung's depth band, and the doors it holds.
A door opens a ROOM — the rules by what they account for, the machine, the
artefacts, a value as the value it is — and `‹ back` returns.

## The whole protocol

```
POST /frame     size <w> <h>
                only <facet>          ← a window is one facet
                win <id>              ← ...looking through its own layer
                <gesture>             ← at · set · sel · text · scroll · spin
                <payload>             ← a plane's whole text, when it was typed in

#FONT / #TONES  the register: fills, edges, faces
#FRAME w h gen n
box · line · curve · bez · arc · ring · text     ← final pixels, named tones
#HITS n         x y w h kind address [run cell]  ← and what to post when landed on
#PLANES n       name x y w h row cell top edit chars
#TEXT           the planes' text, raw, counted in characters
```

## Editing

Typing goes to the browser's own text engine, which is why it feels like
typing. An edit is a RE-READING: `Ctrl+Enter` reads what you wrote,
`Ctrl+S` saves and compiles, `Esc` reverts. A refused read keeps your text,
draws the frontier where derivation died — measured off the kernel's own
cursor, never scraped out of prose — and the derivation says it is showing the
last good reading.

## What it costs

4 ms a gesture. Four things are facts about a READING rather than a cursor and
are kept against it: the staging, the overview band, the clock's boxes, and a
chosen rule's occurrences. The Earley clock costs ~1.5 s once, then 24 ms a
cursor move from the retained kernel.

| | space_1 | space_2 |
|---|---|---|
| leaf, shipped | 4,268 lines | **~280** |
| leaf files | 17 | 3 |
| wire routes | 12 | 1 |
| geometry in the leaf | window, tint, lanes, hit tests, layout, camera | none |
