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

## What it says on the wire

```
needs    grammar:70x46  document:25x986  chart:80x20  spine:48x20  graph:132x5  machine:756x10
offered  grammar:63  document:32  chart:72  spine:43
wants.window  graph,machine
```

The instrument publishes its reasoning, so every verdict is checkable rather
than trusted. `machine:756x10` is why the automaton can never live in a
column: 126 clones need 756 characters of width. On screen the shortfall is
said where the problem is — `⧉ graph needs a window` on the reader's own
head, clickable, opening the view where it fits.

**Tolerance belongs to the KIND.** A plane wraps and scrolls, so half its
width still reads; a graph cannot wrap — below its ask the names collide.
Judging both by one number is why four rounds of layout work never fixed the
graphs while the arrangement kept reporting them fine.

## Where the time goes (measured, not guessed)

```
read total 581ms · of which parse 53ms · facets 1.7ms   # the rest is the
scene build 81ms → 0.00ms per poll after                # engine compiling
```

Startup is dominated by compiling the grammar — the engine's work, memoised
by content — not by anything the instrument does. The scene used to be
rebuilt on every poll (a quarter-megabyte of spans and text); it is now built
once per state of the text, with facts for both the speed and the
invalidation, because a cache that never invalidates is worse than none.

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
