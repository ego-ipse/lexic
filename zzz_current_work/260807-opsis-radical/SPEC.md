# opsis-radical — SPEC (as built, 2026-08-07)

The concrete contract of the running system (`atlas/`). VISION.md carries the
why; this carries the what. Every claim here is census-gated or
screenshot-verified.

## 1. Processes and files

- **Instrument**: `atlas/serve.py` — Python, in-process with lexic.
  `Subject` owns: compiled grammar, reader text, document text (+ its file
  path), model, span fold, generation, cursors, background route result.
- **Leaf**: `atlas/leaf/` — versioned artifacts (`index.html`, `leaf.css`,
  `leaf.js`; `pretext.js` vendored byte-identical, md5
  `e04b8d0c6712b291f2b37088999007e0`, not yet imported — enters when a facet
  wraps or flows). The leaf is generic: it names nothing of lexic.
- **Fixtures**: `long` (json.gbnf reads `tk/fixtures_long.json`, PDA route),
  `meta` / `vyx` (the GBNF metagrammar — `compile_ast(GBNF_FLAVOUR.grammar)`
  — reads `resources/ground_truth/{json,vyx}.gbnf`; reader text =
  `GBNF_FLAVOUR.apply(GBNF_FLAVOUR.grammar)`), `abnf` (the ABNF metagrammar
  reads `json.abnf` — the second flavour through the same pipeline),
  `decide` (`atlas/fixtures/decide.gbnf` — an undecidable arm choice; the
  attempt machinery fires at every entry: the DECISION observation
  fixture) and `amb` (`atlas/fixtures/amb.gbnf` — a genuinely ambiguous
  sum, 429 derivations over 15 chars, read via the `first` resolver — the
  explicit opt-out — so ambiguity is OBSERVABLE, never silent; its PDA
  honestly has no machine: the start rule is an island). Any
  other first argument is a **file pair**: `serve.py <grammar> <doc> [port]`
  compiles the grammar file and reads the document — any grammar the
  pipeline compiles, any document it reads.

## 2. The wire (line-oriented plain text; no JSON anywhere)

- `GET /scene` — the frame: `#META` key-value lines (fixture, reader,
  seconds, resolver, faithful, generation, t) · `#RULEDEFS n` (`name a b`
  line ranges in the reader text) · `#RULENAMES n` · `#FIELDNAMES n` ·
  `#SPANS n` (`start end depth ruleIdx fieldIdx`) · `#READER <bytes>` and
  `#DOC <bytes>` (length-prefixed raw blocks).
- `GET /clock` — the two engine clocks over the document coordinate,
  rebuilt in the background after every read: `status pending|done`,
  `generation`, `pda_end` (−1 healthy; else where the fast road stops),
  `dropped n`, then the engines' own OBJECTS (counts were built first and
  ripped out — a histogram is not a machine): `#PDAFRAMES n`
  (`start end depth nameIdx` — every frame the fused kernel pushed, from
  `ClockKernel(PdaKernel)` recording in `_enter`/`_complete`/`attempt`
  before delegating; frames open at death close at the failure position),
  `#PDANAMES k`, `#EVENTS n` (`pos kind detail` — the decision
  vocabulary: attempt / loop / verdict / probe / island, recorded through
  the TraceKernel seams; capped 20k). Frames carry `ok` (6th token): a
  frame popped without completing was ROLLED BACK by the attempt
  machinery — abandoned, the same fate register as Earley's dead
  hypotheses, drawn red in the lanes and counted as probe frames in the
  spine. The overview band recontextualizes per clock: pda = stack-depth
  texture with warm decision marks; earley = hypothesis density in
  violet, red where only abandoned hypotheses touched a char.
  `#EARLEY n` (`origin last completed nameIdx` — every hypothesis
  `(rule, origin)` the explicit `Kernel` ever held, decoded from its own
  columns via `decode_item`; completed = a final-dot item appeared) and
  `#EARLEYNAMES k`. Hypotheses cap at 60k, longest/completed kept,
  `dropped` counts the rest — stated on the legend, never silent.
- `GET /verdicts` — per rule, the PDA analysis' reaction in its own
  words: `#VERDICTS n`, rows `class noteCount name` + note lines. Classes:
  attempt (ordered attempts decide) · island (windowed Earley sub-parse) ·
  hard (unresolved conflict) · gated (demoted to a stored gate) ·
  predictive (single-pass deterministic). The reader badges every
  non-predictive rule (silence IS the deterministic verdict); notes ride
  the badge title. The analysis is the oracle; this is its transcript.
- `GET /automaton` — the compiled machine itself: `#ACLONES n`
  (`nameIdx mode flags depth` — every reachable clone; modes
  alt/seq/dispatch/value_str/group; flags a=attempt l=leaf k/p/s=gates;
  BFS depth from the start clone), `#ANAMES k`, `#AEDGES n`. Nodes are
  CLONES, not rules — the same rule as several context clones IS the
  machine. Static per session.
- `GET /column?i=N` — Earley column N on demand, from the retained
  recognizer kernel: `#COLUMN i n` (`origin role rule ::= done ● todo`)
  + `#EXPECT n` (the terminals that can come next). The leaf fetches the
  cursor's column as t moves; whole-document item sets never ship.
- `GET /rails` — every rule's structural lines in one frame, sections
  headed `#RAIL <rule> <n>` in AST order — the all-rules rails view reads
  this once and caches it (the reader grammar never changes across document
  re-reads).
- `GET /rail?rule=<name>` — one rule's body as indented structural lines:
  `#RAIL <rule> <n>`, then `<depth> <kind> [payload]` per node (children one
  depth deeper). Kinds: `alt`/`seq` (containers, single-child collapsed
  server-side), `many lo hi` (a real quantifier; hi −1 unbounded),
  `ref`/`lit`/`class` (leaves; lit escaped `\n\t\r\\`), `not`/`alpha`
  (one-child wrappers), `nil` (empty sequence), `other <Type>` (undrawable,
  named). Unknown rule → `no such rule <name>`. The leaf owns all geometry —
  the railroad renderer draws these lines as track.
- `GET /routes` — `primary …`, `primary_seconds …`, then the background
  result: `status pending|done|failed`, `name`, `seconds`, `parity`, `pos`,
  `words`.
- `#POLICY n` in the scene, plus `GET /policy` and `POST /policy` (changed
  keys as `key value` lines; value `-` deletes) — the presentation policy as
  session state, rung 5. Keys: `speed`, `doc.zoom`, `chart.zoom`, `chart.clock model|pda|earley`
  (which clock THE DERIVATION's lanes tell — rung 8; pending is drawn as a
  sentence, never a blank),
  `spine.zoom`, `reader.mode text|graph`, `graph.view depth3d|flat|arcs|rails`,
  `graph.levelstep|ringscale|flatten|labelscale`, `graph.camera "yaw pitch
  zoom panx pany"`, `arrange.reader|right|top` (grid shares; the seams write
  these), `pin.<id> span s e d rule x y w h gen` (gen is the reading the
  pin was made against — staleness survives a reload; legacy 9-token
  values read as current) / `pin.<id> graph x y w h yaw
  pitch zoom panx pany view` (`view` ∈ text|depth3d|flat|arcs|rails — every graph
  window carries its own, independent of `graph.view`; shorter legacy values
  parse) / `pin.<id> rail <rule> x y w h` (a railroad window; refs inside it
  are clickable and open that rule's railroad — `?rail=a,b` deep-links).
  The rail gesture is the chip: clicking a rule in the reader text, or a
  rule chip in any graph view, raises `▤ rail` beside the pointer — the
  same gesture shape as the text pin chip. The tune panel is per-view
  (depth3d: depth/ring/flat/label · flat: cols/rows/label · arcs:
  pitch/lift/label · rails: gap/label · automaton: depth/spread/label).
  The reader's view set gained `automaton` — the machine drawn walk-lit:
  when `chart.clock` is `pda`, the frames open at the cursor light their
  exact clones warm (frames carry clone ids), visited clones tint by
  mode, attempt clones wear the warm ring, gated clones the violet box.
  THE SPINE follows the clock: `model` = the open model spans (as ever);
  `pda` = the kernel's own stack at t plus the decision events near t
  (or the honest none-sentence pointing at the automaton view);
  `earley` = the cursor's column as dotted items (@origin, role) with
  CAN COME NEXT — fetched per cursor move, cached per generation.
  Railroads are navigable spaces:
  the rails view scrolls on wheel (Ctrl+wheel zooms, like the text
  planes) and clicking a ref scrolls to that rule; in a rail window a
  ref click re-targets the window in place (`↩` walks back, `▲ n`
  ascends to a chosen parent — a rule may be referenced many times, so
  ascent is a choice, not a jump). A NEW window is only ever the chip.
  Hovering any ref co-selects its rule — the same light as its chip,
  reader line and spans; rail windows join the per-frame render for it.
  Leaves are interpreters: the browser applies policy at boot and
  posts every presentation gesture back; the TUI obeys speed, shares, and
  reader.mode — its flat rule graph IS `graph.view` in cells. Both leaves
  POLL `/policy` (browser ~2s with a 2.5s quiet window after local
  gestures — the hand on the wheel wins; TUI on its 2.5s tick) and apply
  the delta: scalars re-apply, pins reconcile in place (add/remove/nudge —
  a window's element, camera, tree and history survive a remote move).
  Cross-leaf sync is live: a gesture in one leaf lands in the other within
  a tick. The TUI renders pins as PANES (rung 7): a column between
  document and spine (≥176 cols) — span pins show their text, rail pins
  their structural lines in the rail registers, graph pins name
  themselves. Policy dies with the server process — accepted for now.
- `POST /cursor` — `t <float> sel <int>` (fire-and-forget, throttled).
- `POST /edit` — `<start> <end>\n<replacement>` → re-read WITHOUT saving.
  Reply `ok <secs>` or `refuse <pos>\n<engine words>` (`pos` −1 when
  unmeasurable).
- `POST /save` — same body → re-read AND persist to the document's own file.
  Reply `ok <secs> saved` | `ok <secs> held <reason>` (ground-truth corpus is
  never overwritten; the hold states why) | `refuse <pos>\n<words>`.

Spans are folded from the model's own tagged `emit_parts()` stream — the
stream `to_text()` consumes — so the chart cannot drift from the text; rule
names come from `type(part).__grammar__.name`.

## 3. Facets and cursors

READER (grammar text; rule lines addressable) · DOCUMENT (editable plaintext
plane over welded under/over canvases; glyph geometry is monospace
arithmetic) · DERIVATION (canvas: overview density + depth lanes + route
strip) · SPINE (stack open at the cursor; bounded by depth). Cursors on the
subject: `t`, selection, hover. Co-selection: hover/click a span ⇄ its rule
lights in the reader; click a rule → its spans outline violet everywhere;
native text selection → smallest covering occurrence co-selects; gutter click
sets `t` to that line; chart scrubs; Space plays; ←/→ steps.

## 4. Editing contract

Typing in the document marks the session **dirty**: derived facets go stale
(dimmed, labelled "last good reading"), span/hover queries suspend, status
reads `edited — unread`. **Ctrl+Enter re-reads without saving. Ctrl+S saves,
and saving compiles.** Esc reverts to the last good reading. A refused
re-read keeps the typed text, draws the **frontier** (red caret + underline)
inside it at the deepest verified position, scrolls there, and carries the
engine's words in the banner. Generation bumps only on a successful read.

## 5. Engine routes (rung 2, first half)

After every successful read, a daemon thread runs the road not taken
(results discarded if the generation moved):

- PDA-routed subjects → explicit Earley:
  `earley_model(normalize(lift_optional_nullables(cg.codegen_grammar)),
  doc, cg.fold)` — **this pass pair is the instance-grammar recipe**; without
  it the tables refuse (unnormalised quantifiers) or the parse reports
  spurious ambiguity. Parity verdict = structural `==` plus `to_text`
  equality. Measured: 1.9s vs 0.05s on 15.7K chars, parity holds.
- Resolver-routed subjects → `PdaKernel(cg.pda_tables(), doc, cg.fold)`,
  expected to probe-fork; the position is read from its words ("attempt loop
  at N") and drawn as where-the-fast-road-stops (meta: 202, vyx: 3,306).

The leaf polls `/routes` (1.2s) and renders the strip in the derivation
header: running… → timings + verdict (green on holds) or the inversion
position. **Rung 8 (rung 2's second half) is built**: THE DERIVATION's lanes
switch between the model view, the PDA's decision clock (frame entries per
char, log-scaled; warm ticks where the real attempt machinery fired; a red
line where the fast road stops on a refused route) and Earley's chart clock
(items per column, log-scaled) — both rebuilt in the background per read,
census-gated on every fixture.

## 6. Known reads of engine prose (fragile, by declared necessity)

`re: "\bat (\d+)\b"` over `PdaFail` / `ProbeFork` words. Both are lexic asks
(HANDOVER): put the position on the record; de-ambiguate the self-grammar's
model product.

## 7. Gates and verification

`serve.py <fixture> --census` (exit 0) asserts: round-trip fidelity, scene
integrity, identity retype ok, garbage retype refused with the document
untouched (corruption placed per route — a mid-document control char is
LEGAL in metagrammar comments; measured), frontier position exact on the PDA
route / −1 on resolver routes, save `saved` vs `held` per route, background
route result as expected. Leaf syntax: `node --check`. Visuals: playwright's
chrome-headless-shell with `--no-sandbox` + `?t=`/`?sel=`/`?rule=`/`?break=`
deterministic states.
