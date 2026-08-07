# facets — one subject, four facets, no windows

The composition answer, built on the settled stack: a Python instrument
in-process with lexic, a browser leaf of real versioned artifacts, and a seam
that carries emitted frames one way and addresses the other. Line-oriented
plain text on the wire, both directions — no JSON anywhere.

## Run

```bash
uv run python zzz_current_work/260807-opsis-radical/facets/serve.py            # vyx, port 8901
uv run python zzz_current_work/260807-opsis-radical/facets/serve.py meta 8902
uv run python zzz_current_work/260807-opsis-radical/facets/serve.py vyx --census
```

Then open `http://127.0.0.1:8901/`. Fixtures: `vyx` (the GBNF metagrammar
reading `vyx.gbnf` — 11,692 spans), `meta` (it reading `json.gbnf`), `long`
(`json.gbnf` reading a ~16K-char JSON). For meta/vyx the reader facet's text is
the metagrammar **spelling itself** through its own emitter
(`GBNF_FLAVOUR.apply(GBNF_FLAVOUR.grammar)`).

## The facets

**THE READER** — the grammar, as text; **THE DOCUMENT** — the read text, in its
natural multiline shape, as REAL selectable DOM text with span geometry drawn
on canvases welded to it by measured monospace arithmetic; **THE DERIVATION** —
the time-axis chart (overview density + depth lanes); **THE SPINE** — the stack
open at the cursor, bounded by depth. They are regions with hairline seams, not
windows: none can be detached, closing one loses nothing, all re-derive.

The cursors live on the subject and every facet renders them: one time cursor
`t`, one selection, one hover. Native text selection in the document drives
structural co-selection — select characters and the smallest covering
occurrence is chosen, its bar halos in the chart, its rule lights up in the
reader. Click a rule in the reader and its spans outline violet in both other
directions. That cross-facet, cross-subject deixis is the point of the build.

## What to try

- Let it play (Space toggles). Double-click text to set the cursor; drag the
  chart to scrub; ←/→ steps one character.
- **Select text with the mouse** — the thing tkinter could not give. Watch the
  readout name the occurrence and the reader light its rule.
- Select a span of text and press **E** — retype it, Enter. The document is
  spliced and **re-read by lexic**: on success every facet re-derives
  (generation bumps, the banner says how long the re-reading took); on failure
  the banner carries the engine's own words and the document is untouched.
  Grammar is the ground truth: text is primary, everything else derives.
- `?t=4205&sel=4205` in the URL pins a deterministic state (used for
  screenshot verification).

## Files

- `serve.py` — the instrument: Subject (compile, read, re-read), span fold with
  authored rule names (`type(part).__grammar__.name`), the scene emitter, the
  gesture handlers, the census gate.
- `leaf/index.html` · `leaf/leaf.css` · `leaf/leaf.js` — the leaf: generic,
  nameless, versioned artifacts (not blobs). It draws addressed regions and
  reports gestures; subjects never cross the seam.
- `leaf/pretext.js` — vendored byte-identical copy of `@chenglou/pretext`
  (md5 `e04b8d0c6712b291f2b37088999007e0`). Not yet imported: this iteration's
  document facet is no-wrap monospace, where glyph geometry is arithmetic;
  pretext enters when a facet wraps or flows.
- `TALLY.md` — the context-recovery ledger, one line per step.
