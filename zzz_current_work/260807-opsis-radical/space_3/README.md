# space_3 — the instrument, served as one frame

```bash
uv run python zzz_current_work/260807-opsis-radical/space_3/serve.py --direct \
    resources/ground_truth/json.gbnf \
    zzz_current_work/260807-opsis-radical/tk/fixtures_long.json 8918
```

## What this is

A reading — a document read under a reader — drawn whole by the server. The
leaf is a canvas that paints the marks it is sent and real text planes the
browser draws, and between them there is exactly one geometry, which is the
server's. The leaf holds no tones, no fonts, no layout, no camera, no hit
geometry and no idea what a grammar is.

## The whole protocol

One route.

```
POST /frame     size <w> <h>
                only <facet>          ← a window is one facet
                win <id>              ← ...looking through its own layer
                <gesture>             ← at · set · sel · text · scroll · spin
                <payload>             ← a plane's whole text, when it was typed in

#FONT / #TONES  the register: fills, edges, faces, tracking, measured advances
#FRAME w h gen n playing
box · line · curve · bez · arc · ring · text     ← final pixels, named tones
#HITS n         x y w h kind address [run cell]  ← what to post when landed on
#OVER n         what is drawn ABOVE the text planes
#PICKS n        real browser controls — selects and sliders — placed by the frame
#PLANES n / #TEXT   real editable text, welded onto the frame's glyph geometry
```

## Facets

Five: **THE READER** (the grammar, in whichever pipeline form it is showing)
· **THE RELATIONS** (depth 3d, flat, arcs, rails, automaton — one facet, its
own selector, `◉ focus`) · **THE DOCUMENT** (real editable text) · **THE
DERIVATION** (the overview band, the lanes, and which clock they tell —
model, PDA, or Earley) · **THE SPINE** (open at the cursor, according to the
clock). The masthead carries the ladder and the dock; the arrangement is a
measured split tree; a minimized facet merges out of it.

## Windows

A facet's head carries `⧉` (pop it out of the grid) and `⧉+` (a second view);
a selection raises `⌖ pin`; a chosen rule raises `▤ rail`. Each window looks
through its OWN layer over the session's policy — its view, its camera, its
scroll — while the cursor stays shared, because a cursor lives on the subject.

## Editing

Typing goes to the browser's own text engine. An edit is a RE-READING:
`Ctrl+Enter` reads what you wrote — in EITHER plane; grammar is the ground
truth — `Ctrl+S` saves and compiles, `Esc` reverts. A refused read keeps the
typed text, draws the frontier where derivation died — measured off the
kernel's own cursor, never scraped out of prose — and carries the engine's
words verbatim.

## Where the reading sits

`⌗` in the masthead pulls the session back to THE STRATA: every rung climbed,
the one above it, and the doors each rung holds — the rules, the machine, the
artefacts, any value as the value it IS. Entering a rung builds it. `◌ ring`
opens the instrument's own state as a reading of `fixtures/policy.gbnf`, and
saving that record APPLIES it.

## The gates

```bash
uv run python zzz_current_work/260807-opsis-radical/space_3/gate.py    # exit 0, or it is not done
zzz_current_work/260807-opsis-radical/space_3/probe.sh                 # exit 0, or it is not done
```

The gate drives the real composer over four pairings — including a reader
that refuses its document — and reads the frames as data. The probe is the
leaf standing in a browser, at 1× and 2×, checking what only a browser can:
that a canvas is sized to its box, that a plane sits on the geometry it was
sent, that a character is the width the frame believes, that a control is a
real control.

## Where it came from

space_2, cloned whole. [LEDGER.md](LEDGER.md) starts empty; what space_3
changes is written there.
