# space_2 — the thin leaf

```bash
uv run python zzz_current_work/260807-opsis-radical/space_2/serve.py \
    resources/ground_truth/json.gbnf \
    zzz_current_work/260807-opsis-radical/tk/fixtures_long.json 8918
```

## What is different

space_1 moved *drawing* to the server and kept a *model* in the leaf — it
owned the window, the cursor and the tint. That is two geometries which must
agree, and every late failure in that build was them disagreeing:

- lane height computed on both sides → hovering reported the span nested
  one level inside the one under the pointer;
- coordinates from the server, window maths in the leaf → the same picture
  at every cursor position, deaf to zoom, invisible while playing;
- tone names from the server, colour register in the leaf → a whole band
  painted in near-black;
- canvas bitmap tracking width only → pictures stretched instead of re-fit.

None of those are expressible here, because the leaf holds no geometry at
all.

## The whole protocol

One route. The leaf says how big it is and what the hand did; the answer is
the instrument, drawn:

```
POST /frame          size <w> <h>
                     <gesture>            point x y · at span 4858:5000 ·
                                          at line 240 · step 1 · go end ·
                                          play · tick · resized

#FRAME <w> <h> <generation> <marks>
box   x y w h tone [label]     ← final pixels, named tones
line  x1 y1 x2 y2 tone
text  x y tone words…
#HITS <n>
x y w h <kind> <address>        ← what the pointer can land on, and what to
                                  post when it does
```

The leaf's entire job: paint five mark kinds, hit-test rectangles, post the
address. It converts no pixels to offsets, decides no colour, computes no
lane, and knows nothing of grammars, spans or clocks.

## The measure

| | space_1 | space_2 |
|---|---|---|
| leaf, shipped | 4,268 lines | **124 lines** |
| leaf files | 17 | 2 |
| wire routes | 12 | 1 |
| geometry in the leaf | window, tint, lanes, hit tests, layout | none |

## What it does not do yet

The frame carries the reader, the document, the derivation, the stack at the
cursor and the status line. space_1's other surfaces — the relations graph,
the railroad, the automaton, both engine clocks, the rooms, the strata, pins,
pop-outs — are not in it. They are all the same shape of work: derive on this
side, emit marks and hits, and the leaf needs no new code to show them, which
is the point of the protocol.
