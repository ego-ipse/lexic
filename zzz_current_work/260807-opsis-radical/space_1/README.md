# space_1 — the instrument, rebuilt around what it measured

Run it:

```bash
uv run python zzz_current_work/260807-opsis-radical/space_1/serve.py \
    resources/ground_truth/json.gbnf \
    zzz_current_work/260807-opsis-radical/tk/fixtures_long.json 8917
uv run python zzz_current_work/260807-opsis-radical/space_1/gate.py   # 18 facts, exit 0
```

## The one idea

**A surface declares the room it needs; the arrangement answers.** Every
layout before this was a shape someone chose — reader narrow, document wide
— and every picture that failed, failed because it was living somewhere it
does not fit. Measuring says that shape was backwards: reading
`fixtures_long.json`, the grammar needs 70 columns and the document 25.
Reading `json.gbnf` under `json.abnf` the shares invert. Same instrument,
different reading, different shape — and the grammar reads whole in both,
which it never did before.

A surface that cannot be honoured is NAMED (`wants.window graph,machine`)
rather than crushed into a column and redrawn until someone gives up.

## The files

| file | what it owns |
|---|---|
| `read.py` | a reading, its spans, and what each surface needs |
| `place.py` | the arrangement, computed from those needs |
| `chain.py` | the rungs this reading implies — named, not parsed |
| `watch.py` | the predictive kernel, reporting what it did |
| `machine.py` | the compiled machine: clones, not rules |
| `draw.py` | the rule graph, and the room it would need |
| `keep.py` | artefacts — none counts until it loads back |
| `retype.py` | an edit is a re-reading; a refusal measures where it died |
| `ring.py` | the instrument's own state, read and applied |
| `serve.py` | the socket, and the scene the leaf reads |
| `gate.py` | what must hold, printed as facts |

## Why each fact exists

Every line in the gate defends something this project got wrong:

- the layout was a shape, not a measurement
- a surface was crushed instead of asking for a window
- a facet was named something the leaf could not recognise
- the engine's folded name met the grammar's spelling, so nothing lit
- a subset of hypotheses drew structure that was not in the parse
- a clone id indexed a table it was not measured against
- an artefact existed without anyone reading it back
- a refusal was scraped from prose instead of measured
- a stratum was a column's position rather than a depth
- the automaton showed the clones a run entered and called that the machine

The previous build is `../FUCKUP/`.
