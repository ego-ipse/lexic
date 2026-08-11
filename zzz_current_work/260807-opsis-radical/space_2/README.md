# space_2 — space_1, with the leaf reduced to a painter

```bash
uv run python zzz_current_work/260807-opsis-radical/space_2/serve.py \
    resources/ground_truth/json.gbnf \
    zzz_current_work/260807-opsis-radical/tk/fixtures_long.json 8918
```

## What this is, and what the earlier attempts were not

This is **space_1's whole server** — every package, every derivation, every
drawing emitter — with one composer that puts those drawings into the
measured arrangement, and a 125-line leaf that paints marks and posts
gestures. Two earlier attempts copied four modules and rebuilt a three-column
sketch; both were rightly deleted. The emitters already existed
(`opsis/paint.py` has drawn the railroad, the automaton, the relations, the
derivation, the band and both clocks since space_1). What was missing was
somewhere to put them that was not the leaf.

## Why the leaf holds nothing

space_1 kept a model there: it owned the window, the cursor and the tint.
Two geometries that must agree, and every late failure was them disagreeing —
a hover a lane deep, a picture identical at every cursor position, a band
painted in a colour the leaf did not know, a canvas stretched instead of
re-fit. None of those are expressible here.

## The whole protocol

```
POST /frame     size <w> <h>
                <gesture>    at surface railroad · at span 4858:5000 ·
                             at rule string · at line 240 ·
                             scroll reader 1 · step 1 · go end · play · tick

#FRAME <w> <h> <generation> <marks>
box   x y w h tone [label]      ← final pixels, named tones
line  x1 y1 x2 y2 tone
text  x y tone words…           ← already clipped to its column
#HITS <n>
x y w h <kind> <address>        ← what the pointer can land on, and what to
                                  post when it does
```

## Surfaces

Six, switched by clicking a tab, all composed here: **derivation**,
**relations**, **railroad**, **machine**, **pda** and **earley**. The reader
lights the lines of every rule open at the cursor; the stack under it names
them; the status line says where the cursor stands.

## The measure

| | space_1 | space_2 |
|---|---|---|
| leaf, shipped | 4,268 lines | **125** |
| leaf files | 17 | 2 |
| wire routes | 12 | 1 |
| geometry in the leaf | window, tint, lanes, hit tests, layout, camera | none |
| server | 4,377 lines | 3,692 (the same derivations, one composer) |

## Known

A curve is drawn as its chord: the frame's vocabulary is box, line and text,
so the railroad's bezier branches arrive straight. Adding `curve` to the
protocol is four lines on each side, and is stated here rather than hidden.
Rooms, strata, pins and pop-outs are not composed yet.
