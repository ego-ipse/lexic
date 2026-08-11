# space_1 — the instrument

Run it:

```bash
uv run python zzz_current_work/260807-opsis-radical/space_1/serve.py \
    resources/ground_truth/json.gbnf \
    zzz_current_work/260807-opsis-radical/tk/fixtures_long.json 8917
uv run python zzz_current_work/260807-opsis-radical/space_1/gate.py   # 40 facts, exit 0
```

## The one idea

**A surface declares the room it needs; the arrangement answers — and the
arrangement is decided here, not there.** The leaf receives a tree and
applies it. It computes no layout, resolves no name, and knows nothing about
lexic; when it drew its own pictures it drew them from state nothing could
check, and every failure this build has fixed was of that shape.

## The packages

Named for opsis' own architecture, because the names are the responsibilities.

| package | what it owns |
|---|---|
| `opsis/` | the spectacle — the scene a reading becomes, the space that arranges it, the rooms, the grammar's own pictures |
| `deixis/` | pointing — what is open at a cursor, what just closed, and what that lights, resolved once for every surface |
| `eidolon/` | shape — which rule refers to which, how far each stands from the start, where each one SITS, and any value as the value it IS |
| `kairos/` | time — the pipeline's four moments, the machine each compiles to, both engines' clocks, and the artefacts a reader can be written as |
| `praxis/` | doing — a reading, the ladder above it, an edit as a re-reading, the instrument's own record, the socket |

`serve.py` routes and serves files. `gate.py` prints what must hold.

## What the leaf is given

Not a picture — a state, and the configuration for drawing it.

```
#FACETS 5                     name kind needs W H in <column> <relation> <title>
arrange.tree (h 0.49 (t 0 grammar graph) (h 0.416 document (v 0.667 chart spine)))
#PLACES 32 flat               x y z <rule>          ← positions, derived server-side
#OPEN 15 / #CLOSED 8 / #LIT 5  ← the cursor's answer: the spine, and what is lit
form codegen · forms source canonical codegen lifted
```

Which tab is showing, which shares the hand dragged, and any arrangement the
hand MADE all live in the same state — so a form change or a re-read does not
throw them away.

## The pipeline is a property of the reader

Four moments — **source · canonical · codegen · lifted** — and the reader
displays the one you choose, spelled by its own flavour. Every name
downstream is read off that text, which is why a choice the machine makes now
lights on the graph: in the codegen form `xs ::= xs-arm1 | xs-arm2` is a rule,
and the PDA's clones are named after it.

The pipeline room says what each step did, checked rather than asserted:
`codegen — 39 rules · +7: array-item, array-item2, char-arm2`.

## Both engines, one text

`/routes` runs the road not taken: the engine's own composition at 0.05s,
explicit Earley at 0.86s, compared by VALUE — equal objects *and* identical
re-emission.

## Why each fact exists

Every line in the gate defends something this project got wrong:

- the layout was a shape, not a measurement
- the scene never carried `#EDGES`/`#DEPTHS`, so every graph drew rules as
  unrelated dots — the relationships were never on the wire
- the strata pinned one stats line to card 0, so the rung you had just
  climbed to had none, and the renderer threw mid-draw
- the automaton's edges indexed a clone list it did not send
- an edit moved the model and nothing else: the generation was a literal `1`
- the readout followed the selection while the pointer was elsewhere
- 1,403 of 12,230 spans cover no text and were drawn as boxes
- every PDA frame was named for its rule, so five clones read as one word
- DECISIONS said "none" on a grammar of nothing but decisions
- rotating the graph rescaled it, because the fit was recomputed per angle

## Where the time goes (measured, not guessed)

```
read total 581ms · of which parse 53ms · facets 1.7ms
scene build 81ms → 0.00ms per poll after (rebuilt when the text moves)
```

The previous build is `../FUCKUP/`.
