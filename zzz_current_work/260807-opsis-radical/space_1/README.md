# space_1 — the instrument, rebuilt around what it measured

Run it:

```bash
uv run python zzz_current_work/260807-opsis-radical/space_1/serve.py \
    resources/ground_truth/json.gbnf \
    zzz_current_work/260807-opsis-radical/tk/fixtures_long.json 8917
uv run python zzz_current_work/260807-opsis-radical/space_1/gate.py   # 36 facts, exit 0
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
rather than crushed into a column and redrawn until someone gives up — and
the mark it puts on itself opens it at the address it named, which is not
the same address for every surface.

The relations are a **facet**, not a mode of the reader. Living inside the
reader, the graph could only appear by hiding the grammar it is a picture
of, and it inherited a column measured for text. It is now laid out in the
room it actually has: levels are bands across the width, a level too crowded
for one column wraps into as many as a rule name's width allows, and the fit
frames the LABELS rather than the dots. Nothing is scaled down afterwards,
so nothing collides that did not have to, and nothing hangs off the edge —
which the probe measures rather than assumes (`flatClipped=0`).

## The files

| file | what it owns |
|---|---|
| `read.py` | a reading, its spans, and what each surface needs |
| `irvalue.py` | a value as the value it IS — identity, tier, absence, refusal |
| `place.py` | the arrangement, computed from those needs |
| `chain.py` | the rungs this reading implies — named, not parsed |
| `watch.py` | the predictive kernel, reporting what it did |
| `machine.py` | the compiled machine: clones, not rules |
| `draw.py` | the rule graph, and the room it would need |
| `keep.py` | artefacts — none counts until it loads back |
| `retype.py` | an edit is a re-reading; a refusal measures where it died |
| `ring.py` | the instrument's own state, read and applied |
| `serve.py` | the socket, and the scene the leaf reads |
| `track.py` | one rule's body as track — the grammar's own spelling |
| `wire_machine.py` | the automaton and the verdicts, as the leaf reads them |
| `gate.py` | what must hold, printed as facts |

The leaf is one program living in fifteen files (`leaf/`), carved along its
own section boundaries — order is load order, and every top-level binding
stays in the global lexical environment, because splitting a program is not
the same as making it several programs.

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

## The rooms

A surface too big for a column is not the only thing that needs somewhere to
live. Four rooms answer at `/place`, each reached by a door that says what is
behind it:

| room | what it holds |
|---|---|
| `rules` | every rule this document used, ordered by what it accounts for |
| `rule:<name>` | one rule: its neighbourhood, its clones, its occurrences, its IR |
| `machine` / `artefacts` | what the grammar compiles to, and what it writes out |
| `ir:grammar` `ir:codegen` `ir:reducer` | the value surface, on each subject |

The value surface is the one the instrument exists for: a grammar drawn as
what it IS once loaded — one object reached from twelve places is ONE node
with twelve edges arriving (`IrNone ↩ 14×`), a record's edges are its FIELD
NAMES, absence is a value with a place, and a node carrying a Python function
is marked refused because the notation cannot spell it. Reading `json.gbnf`:
392 unique nodes, 408 edges, 2 shared reached 19 times, nothing refused.

## Both engines, one text

`/routes` runs the road not taken: the engine's own composition parses in
0.05s, explicit Earley in 0.86s, and the two are compared by VALUE — equal
objects *and* identical re-emission. Two engines building different things
from one text is the finding, not a detail to smooth over.

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
- a ⧉ mark sent every surface to the graph, whatever had asked
- a room's graph parsed a wire nothing has ever sent, and drew empty
- a value's payload contained a newline, and the line-oriented wire tore
- `<class 'lexic.ir.spine.scalars.IrChr'>` appeared where `IrChr` is the fact
- a route answered with a stub while the leaf drew the empty result
- the scene never carried `#EDGES`/`#DEPTHS`, so every graph drew rules as
  unrelated dots — the relationships were never on the wire at all
- the strata sent one stats line pinned to card 0, so the rung you had just
  climbed to was marked visited with no numbers, and the leaf's card renderer
  threw mid-draw: everything after the first stratum simply never appeared
- the readout followed the SELECTION while the pointer was somewhere else
- 1,403 of 12,230 spans occupy no text (a rule derived ε) and were drawn as
  boxes two characters wide — model structure the document does not contain
- every PDA frame was named for its RULE, so five clones of `object` read as
  one word repeated five times: the machine's whole shape, hidden as noise

The previous build is `../FUCKUP/`.
