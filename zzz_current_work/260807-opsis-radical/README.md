# opsis-radical — the demonstrator

A brand-new thread, deliberately not a continuation of any prior opsis effort.
One question is answered on screen, three ways:

1. **How does opsis represent `IrSelf`, `IrNone`, `IrStr`, `IrNamedTuple`?**
   Four exhibits, each a *drawn claim* about what that kind of thing IS, each
   made about a **live lexic object** with its facts measured on the spot and
   stamped `— holds` / `— fails`. A fifth exhibit shows the open-table refusal:
   a node kind with no presentation entry draws the raising default's own words
   in red, never a blank.
2. **How does opsis represent itself and modify itself?**
   The violet panel is the instrument's own `Style` record — part of the same
   `Session` value everything else lives in — drawn by the *same* table entry
   that draws the `IrQuantifier` exhibit, and retyped the same way. A commit
   reconstructs the whole `Session` (records are tuples; modification is
   rebuild), bumps `generation`, and the next frame is a render of the new
   value. Retype `warm`, `pad`, or `text` and the entire instrument changes.
0. **The tech stack** is answered in [STACK.md](STACK.md), once before this was
   built and once after.

## Run

```bash
uv run python zzz_current_work/260807-opsis-radical/tk/demonstrator.py            # live
uv run python zzz_current_work/260807-opsis-radical/tk/demonstrator.py --census   # gate, exit 0
uv run python zzz_current_work/260807-opsis-radical/tk/demonstrator.py --shot out.png

uv run python zzz_current_work/260807-opsis-radical/tk/spectacle.py               # a parse, watched
uv run python zzz_current_work/260807-opsis-radical/tk/spectacle.py --census      # gate, exit 0
uv run python zzz_current_work/260807-opsis-radical/tk/spectacle.py --shot 33 out.png
```

`spectacle.py` is the white whale: `json.gbnf` compiled by lexic, a real document
parsed to a typed model, and the derivation animated on the settled clock —
**text is the time axis**. Every span is folded from the model's own tagged
`emit_parts()` stream (the same stream `to_text()` consumes), so the chart
cannot drift from the text by construction. It plays once and rests; hover the
text or lanes to scrub time, Space replays, hover a span to read it.

```bash
uv run python zzz_current_work/260807-opsis-radical/tk/wolf.py [long|meta|vyx]
uv run python zzz_current_work/260807-opsis-radical/tk/wolf.py vyx --census
uv run python zzz_current_work/260807-opsis-radical/tk/wolf.py long --shot 8000 out.png
```

`wolf.py` is the big bad wolf test — the watched parse at hostile scale, after
the small spectacle's litmus failure. Fixtures: `long` (a generated ~16K-char
JSON — 12,219 spans, depth 19, parsed in 0.05s), `meta` (the 90-rule GBNF
metagrammar reading `json.gbnf` as a document), `vyx` (the metagrammar reading
`vyx.gbnf` — 12,610 spans; ambiguity settled by an explicitly supplied
first-derivation resolver, and said so in the header). The scale answers: the
text axis gets a viewport (overview band = the whole document as span-density;
detail stage = a window at fixed readable pitch), the right pane is the SPINE —
the stack open at the cursor, bounded by depth, never by document size — and
every count is stated (`in view N of M spans`). The window resizes; readouts
are integers. See `STACK.md`'s amendment for what the wolf did NOT fix: canvas
text cannot be selected, and that finding is recorded as disqualifying for the
tool half.

## What to try

- Hover anything monospace — a dim halo previews its address. Click — a warm
  halo selects it, and the inspector answers the same questions whatever it is
  (that uniformity is `IrSelf`'s portrait; it has no card of its own).
- In the record exhibit, hover the `lo` value and watch the `[0]` cell halo
  too — one path, two readings; the record IS its field tuple.
- Click the `IrNone` socket and try to type — the refusal states why absence
  has one spelling.
- Click `warm`'s hex in the violet panel, retype `#4fd1ff`, Enter — selection
  halos, the hint line, and every warm mark on screen change in the same frame.
- Retype `pad` to `22` — the whole page re-spaces. Retype it to `999` — a red
  refusal in words, and the session value is untouched.
- Watch `generation` and `regions` in the bottom-right census while you do.

## Truth boundary

- Every subject is a live in-process lexic value; every fact line is computed
  from it at draw time (`is`, `isinstance`, `==`, `len`, a `children()` walk).
  Nothing is baked.
- The refusal card's words are a real `UnsupportedConstructError` raised by the
  presentation table's default.
- This is a demonstrator, not the product: three files, one fixed layout, no
  windows, no lexic *parsing* on screen — the subjects here are the spine's
  four kinds, as asked, nothing more.

## Files

- `scene.py` — the value half: the `Style`/`Exhibit`/`Session` records (on
  `IrNamedTuple`), path surgery (`node_at`/`set_at` — modification is
  reconstruction), and the census walk.
- `present.py` — the presentation half: an open per-type draw table with MRO
  resolution and a raising default, over tkinter canvas primitives.
- `demonstrator.py` — the instrument: the frame (`render(session)`), the hand
  (hover/select/retype/commit), census and shot modes.
