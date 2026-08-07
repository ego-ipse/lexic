# opsis-radical — HANDOVER (2026-08-07, end of day)

State: everything committed on `opsis_proto` (`80ede43`…`b8053f5`), including
this gitignored folder (added with `-f`; the user granted `--no-verify` for
zzz-only commits). Cold start needs three files: this one, `atlas/TALLY.md`
(the live ledger), `atlas/THINKING.md` (the map the iterations follow).

## What exists, oldest to newest

| where | what | state |
|---|---|---|
| `tk/` | in-process tkinter probes: `demonstrator.py` (the four spine kinds + the instrument editing its own Style), `spectacle.py` (a parse watched, 50 chars), `wolf.py` (same at hostile scale, 3 fixtures) | done; superseded as a medium (canvas text is not selectable — the litmus); each has `--census` and `--shot` |
| `facets/` | the composition answer: Python instrument ⇄ browser leaf, four facets of one reading, subject-level cursors, native selection → co-selection, edits as re-readings | done as built; ledger closed with a pointer to atlas |
| `atlas/` | the ergonomics fork — the live line | iteration 1 of 6 done (refusal frontier) |
| `STACK.md` | the stack position: answered before building, after building, amended after the selection litmus | current |

## Run

```bash
uv run python zzz_current_work/260807-opsis-radical/atlas/serve.py             # vyx on :8901 (slow route, ~5s boot)
uv run python zzz_current_work/260807-opsis-radical/atlas/serve.py long 8903   # json.gbnf route, fast, frontier-capable
uv run python zzz_current_work/260807-opsis-radical/atlas/serve.py meta 8902   # metagrammar reading json.gbnf
uv run python zzz_current_work/260807-opsis-radical/atlas/serve.py long --census   # the gate, exit 0
```

Then open the printed URL. **The server does not hot-reload** — after any
change to `serve.py` or `leaf/`, restart it (leaf files are re-read per
request, but the subject/scene state is built at boot).

## How to trigger the refusal

Three ways, all leaving the document untouched (generation does not bump):

1. **By hand (the real flow):** run the `long` fixture → select some
   characters in THE DOCUMENT with the mouse → press **E** → replace the text
   with something the grammar cannot derive (e.g. `§§§`) → Enter. The banner
   carries the engine's words plus the measured frontier; a red caret marks
   the deepest verified position; the cursor jumps there; the spine shows what
   was open in the last good reading. Esc clears the mark.
2. **Deterministically (for screenshots):** open
   `http://127.0.0.1:8903/?break=5000` — the leaf POSTs a one-char corruption
   at offset 5000 on boot and renders the refusal state.
3. **Scripted:** `serve.py long --census` splices garbage mid-document and
   asserts the frontier equals the exact corruption offset.

Route caveat: the frontier is measured only on the PDA route (`long`). On the
resolver fixtures (`meta`/`vyx`) the refusal honestly reports *frontier
unmeasured* — see lexic asks below.

## TODO — the iteration ladder (atlas/THINKING.md owns the detail)

1. ~~**Refusal frontier**~~ — DONE (`2e3c5aa`). Red caret at the PDA's deepest
   verified position, read from the kernel's own failure words.
2. **Both engines** (§6b, ruled by the user): background Earley run beside the
   PDA product; alternate route drawn as pending until finished; switch
   enables on completion; inversion on PDA failure (probe-fork point and
   island hand-offs as first-class marks); parity as a drawn verdict.
   Surfaces exist: `earley_model`, `PdaKernel`, `pda_tables`;
   `TraceKernel(PdaKernel)` is the proven observation pattern.
3. **Seam resize** — shares as session values; facets degrade by deriving
   less, never by clipping.
4. **Rule graph facet** — flat first (IrRuleRef edges + name-addressed
   co-selection), then z = derivation distance.
5. **Ports bay** — reducer docking (adds a product; products multiply
   facets), then transpile as a peer lane.
6. **The ring** — focus opsis's own configuration as a subject.

One iteration per session; update `atlas/TALLY.md` each time; census before
screenshots.

## Lexic asks (rulings wanted, both measured this effort)

- **Refusal position on the record.** `PdaFail` spells its position only in
  prose ("no arm at N"); the public parse surface discards even that
  (`UnsupportedConstructError`, words only, no attrs). Wanted: a readout-shaped,
  additive surface carrying frontier position (and eventually expected-next).
  Until then atlas regex-reads the kernel's words — honest but fragile.
- **De-ambiguate the GBNF self-grammar's model product** (noise attribution on
  comment/ws). Measured: PDA route 313,593 chars/s vs metagrammar
  Earley+resolver route 1,974 chars/s (159×), resolver invoked once — the
  cost is the route. Fixing this puts grammar-reading-grammar on the fast road
  and makes the meta/vyx frontier measurable.

## Traps (each cost time today)

- The browse daemon's chromium cannot sandbox here (AppArmor userns);
  `firefox --headless` hangs. Screenshots: drive playwright's shell directly —
  `~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell
  --no-sandbox --headless --window-size=1720,1000 --virtual-time-budget=8000
  --screenshot=out.png URL`.
- Repeated path slip: after `cd` into the effort folder, repo-rooted
  `zzz_current_work/...` paths double up. Run git from the repo root.
- `pkill`'s nonzero exit aborts `&&` chains — it ate a tally append once.
  Verify a server is down by curl on its port, not by pkill's exit code.
- Ledger discipline (user-corrected): **the tally lives where the work lives.**
  atlas work goes in `atlas/TALLY.md`, nowhere else.
