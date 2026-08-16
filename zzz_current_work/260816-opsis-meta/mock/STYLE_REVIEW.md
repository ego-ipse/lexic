# Mock style review — coherence pass

Scope: the mock set in `zzz_current_work/260816-opsis-meta/mock/*.html`, against
each other and against the parsing room's register
(`zzz_current_work/260807-opsis-radical/space_3/leaf/leaf.css` + `index.html`,
and `space_3/opsis/frame/tones.py`, the server-side source of truth).

**The set is nine files, not ten**: `artefact_room`, `compilation_room`,
`generation_strata`, `machine_room`, `navigation`, `rendered`, `ring`,
`transpile_room`, `value_room`. If a tenth was expected, it was never written.

## How this was measured

Every page was **rendered**, not read. Headless Chromium (the
`ms-playwright/chromium-1208` build already on the box, driven through an
ephemeral `playwright` env, `--no-sandbox`) loaded each file at a 1600×1000
viewport, and every screenshot taken was opened and looked at. On top of the
pixels, four programmatic passes ran in-page:

- computed style for the shared chrome selectors (`body`, `h1`, `.note`,
  `.screen`, `.mast`, `.fhead`, `.facet`, `.row`, `.cap-note`, `.legend`);
- a CSS-source diff of every selector appearing in more than one file;
- a register audit walking every element and recording each one whose computed
  text colour, border colour, outline colour or SVG stroke is `--green`,
  `--red` or `--warm`, together with its text;
- a mass probe measuring, per facet, the box height against the bottom edge of
  its lowest text-bearing leaf ("fill %"), plus a leaf count.

**One measurement is tokens, not pixels.** The parsing room is a canvas drawn
from a server wire; it cannot be rendered standalone without the space_3 server,
so its register was read from `leaf.css` and `tones.py` rather than screenshotted.
Also: neither *JetBrains Mono* nor *Inter* is installed on this machine
(`fc-list`: 0 matches each), so the font findings below are about the **declared
stacks**, which is where the divergence actually lives — not about glyph shapes,
which fell back to the same DejaVu on both sides here.

Counts: **17 findings** — 3 critical, 5 high, 6 medium, 3 low.

---

## Applied

The findings below were then applied to the nine mocks in place, and all nine were
re-rendered and re-measured with the same four passes. **Every measured value in
the Findings section records the state before that pass** — read it as the
diagnosis, not the current state.

### What changed

**The register (C1).** Every file's `:root` now carries `tones.py`'s eleven
values verbatim, plus `--token` (`#8fa3b8`, needed by C2/H3), `--mono` and
`--sans`. Re-measured: **cross-file drift ZERO, and 0/11 tones mismatching
`tones.py`** — the drift table now reads zero in both directions, which is what
it could not do before, since agreeing with each other and agreeing with the
room were previously different things.

**Verdict tones (C2, C3, H3).** All fourteen decorative green literals now carry
`--token`: `.s` in `artefact_room`, `.lit` in `value_room`, `.r-code` and
`.fl .s` in `rendered`. `compilation_room`'s diff polarity is now `--dim`
(was) against `--cool` (minted), and its legend says so — *"dim = the arm as it
stood, cool = the rule the pass minted (a pass is work, not a verdict — neither
side is red or green)"*. `machine_room`'s `.k.scan` is `--token` and its caption
was reworded to match. Two decorative greens the first pass had only seen in
pixels were caught on re-inspection and also fixed: `generation_strata`'s depth
band (`#26522f` → `#1d3143`) and `artefact_room`'s payload mass strip
(`#26522f` → `#33414f`, keeping its three-way categorical against the existing
blue and violet bands).

Re-measured register audit: every remaining green is a `✓` verdict or a gate
that holds (`✓ verify_module`, `✓ fixpoint`, `✓ 923 nodes`,
`✓ read back byte-identical`, `completeness ✓`, `membership ✓`, `fidelity ✓`,
the orbit's holds-arcs, `none — fully spellable`). Every remaining red is a
worded refusal. **Zero decorative uses of either.**

**Warm (H2).** `artefact_room`'s `.v-pend` and `navigation`'s `.v-pend` are now
`--dim`; the orbit's pending arc is `--dim` dashed and its legend reads
`dim-dashed=pending`. `navigation`'s note — *"what is amber is where the cursor
is"* — is now true of the file it sits in.

**The two voices (H1).** `h1`, `.note`, `.cap-note`, `.mast`, `.fhead` and
`.legend` are set in `var(--sans)`; grammar text, documents, rosters, traces and
payload tables stay `var(--mono)`. Both stacks are the living room's, verbatim.
`navigation`'s `svg text` also moved off the hardcoded `"SF Mono"` to
`var(--mono)`. No occurrence of `SF Mono` or `Consolas` survives in the set.

**Chrome geometry (H5, L1, L2).** Body is `13px/1.5 var(--mono)` in all nine, so
the 12/13px split is gone — and because every chrome size is now declared rather
than inherited, the masthead no longer coheres by accident. Unified: `.note`
(72em, 26px), `.cap-note` (30px), `.fhead` (9px, flex), `.legend` (8px),
`.mast` (gap 12px, explicit 12px sans), `.travel` (seamed off with the
border-left variant), and `generation_strata`'s missing `h1` letter-spacing.

**Cursor and port vocabulary (H4, M6).** `rendered`'s `.port` polarity is
inverted to match `navigation` and `value_room` — `.port` is dashed/empty and
the docked one carries `.port.docked`, with the markup updated. `ring`'s `.sp`
and `.slot.open` moved to the warm treatment the other rooms use, so the cursor
is one thing in every room; its violet `.screen` border is kept, being
deliberate and captioned.

**One content follow-on.** `ring` draws the instrument's policy record, and that
record *names the register*. Its values were still the old palette's, so the
room contradicted the register it was rendered in; `warm` and `cool` now read
`#e2a65c` and `#6fc3c9`, and the offer list's `#d66a5a` reads `#e06060`. The
off-palette offer `#4fd1ff` is left alone — it is honestly a value you could
set warm to, not a register tone.

### Re-measured verdict

| pass | before | after |
|---|---|---|
| `:root` cross-file drift | zero | **zero** (held) |
| `:root` vs `tones.py` | 11/11 mismatched | **0/11 mismatched** |
| computed chrome drift | 13 properties drifting | **0** |
| decorative green uses | 18 | **0** |
| decorative red uses | 3 | **0** |
| decorative green background fills | 2 | **0** |
| warm on pending (elements, 2 files) | 4 | **0** |
| files with no sans voice | 9 | **0** |
| `SF Mono`/`Consolas` references | 9 files | **0** |
| clipped elements | 0 | **0** (held) |

The three computed values that still differ across files are all deliberate and
were left: `ring`'s violet `.screen` border, `.row` `min-height`, and the
resulting `.screen` heights.

### Deferred, and why

- **M1 (mass)** — out of scope for this pass by instruction; it is content, not
  style. The font change shifted the numbers slightly, so the M1 table is now
  stale. Refreshed fills: `rendered` THE DOCUMENT **16%**, `generation_strata`
  THE SAMPLE **35%**, `machine_room` THE GRAMMAR **35%** and THE DOCUMENT
  **35%**, `transpile_room` THE SOURCE **39%** and THE TARGET **46%**,
  `value_room` THE SPELLING **45%**, `navigation` THE TRAIL **54%**.
  `compilation_room` THE DIFF rose to 60% and is no longer under the threshold.
  Eight facets still owe mass.
- **M2, M3, M4 (hover, STALE/ABSENT, the window layer)** — these need new drawn
  states, which is content.
- **M5 (chip geometry)** — deferred deliberately. Unifying `.fam`/`.door`/
  `.port`/`.slot`/`.gate` onto one `.chip` primitive means rewriting the markup
  of all nine files, which is well past "minimally" and risks breaking rooms to
  fix a 1px padding spread. The canonical block below carries the primitive for
  whenever that rewrite happens.
- **L3 (travel set)** — the missing `⌗ map`/`▤ strata`/`◌ ring` affordances are
  markup, not style.

One new minor observation, found while applying: `value_room` puts `.cls` (the
warm class-name tone) on the quantifier `*` in two rules (lines 68 and 70), so a
grammar operator is painted as if it were a class name. Markup slip, not a
register decision — worth a line when the mass pass touches that file.

---

## Findings

*(measured before the applied pass above)*

### C1 · critical · all nine files — the mocks are a different instrument's palette

The nine mocks agree with each other perfectly and disagree with the living room
on **every one of the eleven tones**. Measured (mock `:root` vs `tones.py`
`TONES`, with rough RGB distance):

| tone | mock | living | ΔRGB | dist |
|---|---|---|---|---|
| violet | `#a78bda` | `#d98cf5` | (−50, −1, −27) | **56.8** |
| cool | `#5aa7d6` | `#6fc3c9` | (−21, −28, +13) | **37.3** |
| ink | `#cfd6e4` | `#e8e2d6` | (−25, −12, +14) | **31.1** |
| warm | `#e8b04a` | `#e2a65c` | (+6, +10, −18) | 21.4 |
| green | `#69c98f` | `#79c99a` | (−16, 0, −11) | 19.4 |
| red | `#d66a5a` | `#e06060` | (−10, +10, −6) | 15.4 |
| dim | `#6b7488` | `#66707f` | (+5, +4, +9) | 11.0 |
| field2 | `#11151d` | `#0e1219` | (+3, +3, +4) | 5.8 |
| dimmer | `#3d4454` | `#3a4250` | (+3, +2, +4) | 5.4 |
| hair | `#1e2430` | `#1a2230` | (+4, +2, 0) | 4.5 |
| field | `#0c0f14` | `#0b0e14` | (+1, +1, 0) | 1.4 |

The fields and hairlines are near-identical, so this reads at a glance as "the
same instrument" — which is exactly what makes it dangerous. The three that
carry meaning have moved a long way. `--ink` is the clearest: the mocks' body
text is a cool blue-grey, the living room's is a warm cream (`#e8e2d6`). The
mocks' violet is desaturated to a dusty lilac where the living room's is a hot
magenta-violet. `--cool` has swung from teal to sky-blue.

**Which side moves: the mocks.** `tones.py` is not a preference, it is the
register a frame ships with — `register()` puts these exact strings on the wire,
and the leaf is written to hold no colour of its own. Nothing in the mock set's
prose proposes a repalette, and VISION §8 opens "Unchanged from the foundation".

*Fix:* replace the `:root` block in all nine with the canonical block below.

### C2 · critical · `artefact_room`, `rendered`, `value_room` — green is being used as a syntax colour

`.s{color:var(--green)}` paints string literals. Measured green-texted elements
that are not verdicts:

- `value_room` — nine: `"{"`, `","`, `"}"`, `":"`, `"["`, `"]"`, `"\""`,
  `IrInt 3`, `IrNone — absence is a value`
- `rendered` — four: `gate.py exits 0` (the whole fenced block, via `.r-code`),
  `"ingest"`, `allow crawlers`, `120`
- `artefact_room` — one: the whole docstring `'''object ::= "{" ws (member ("," ws member)*)? "}"'''`

In the living instrument green is spent in exactly one place. `facets.py:1714`
reads `"green" if role == "complete" else "ink"`, and `tones.py` assigns
`#79c99a` to no role name at all — it exists only as the raw `green` entry.
Green is genuinely reserved there, and the mocks spend it fourteen times on
decoration as a literal tone alone — eighteen counting C3's diff outlines and
H3's `scan`.

*Fix:* literals take `--ink`; if grammar text needs a second value tone, take
`--token` (`#8fa3b8`), which the living register already carries for exactly
this neutral-lexical job. Green survives only on `✓` verdicts.

### C3 · critical · `compilation_room` — the diff paints was/now in red and green

The legend states it verbatim: *"red = the arm as it stood, green = the rule the
pass minted"*. Measured outlines confirm — RED on `unescaped | escape`,
`zero | digit1-9 digit*`, `e sign? digit+`; GREEN on `char-arm2`, `int-arm2`,
`exp-item`.

Neither side of a diff is a verdict. A hoisted arm is not a failure and a minted
rule is not a pass; the room's own caption says these passes are all no-op-or-
work, never wrong. This is the most legible violation in the set because a
reader learns the wrong rule from the legend itself.

*Fix:* was/now as `--dim` → `--ink` (the pass moved text from background to
foreground), or `--cool` for the minted side — cool is already the structural
`ref`/`rail` tone in `tones.py`. The cursor's `--warm` marks the selected rule
in both moments. Red and green leave this facet entirely.

### H1 · high · all nine files — the sans voice is missing entirely

`grep -c sans` returns **0 in all nine files**. Every text-bearing element in
every mock computes to `"SF Mono", Consolas, monospace`.

The living register is explicitly two-voiced — `tones.py`'s module docstring:
*"Monospace is lexic's output; sans-serif is opsis speaking."* `FONTS` assigns
`SANS` to `title`, `ftitle`, `fsub`, `hsub`, `railchip`, `winhead` and `fpop`.
So facet heads, mastheads, sub-labels, rail chips and window heads are all sans
in the room being built, and all mono in the photographs of it.

This one compounds: a room built to these photographs draws its own chrome in
lexic's voice, and the distinction between *the instrument speaking* and *the
subject speaking* — which is most of what makes the parsing room readable —
disappears. It is also the finding most likely to be implemented wrong silently,
because mono chrome does not look broken.

Separately, the declared mono stack diverges: mocks say `"SF Mono", Consolas,
monospace` (an Apple/Microsoft pair), the living room says `"JetBrains Mono",
"DejaVu Sans Mono", ui-monospace, monospace`.

*Fix:* `h1`, `.note`, `.cap-note`, `.mast`, `.fhead`, `.legend` and window heads
take the sans stack; grammar text, documents, rosters, traces, payload tables —
lexic's output — stay mono. Adopt the living room's stacks verbatim.

### H2 · high · `artefact_room`, `navigation` — warm is spent on PENDING

`artefact_room` defines `.v-pend{color:var(--warm)}`; measured warm text
includes `… loading back` and `PENDING — worker, cached`. `navigation`'s orbit
legend reads *"amber-dashed=pending"*, and the audit finds WARM SVG strokes on
the orbit lines.

In the living register warm is `caret`, `cursor`, `name`, `winhead`, `hot`,
`live`, `pdadecided` — every one of them a thing that is **live or identity**.
Pending is the precise opposite: not yet live. And `navigation` contradicts
itself inside one file: its own `.cap.pending{border-style:dashed;color:var(--dim)}`
gets it right for lanes while its orbit gets it wrong, and its `<p class="note">`
states the law — *"what is amber is where the cursor is"* — two paragraphs above
the amber-dashed pending arcs.

*Fix:* `navigation`'s `.cap.pending` treatment (dashed, `--dim`) becomes the one
pending treatment everywhere, including the orbit's arcs and
`artefact_room`'s `.v-pend`.

### H3 · high · `machine_room` — event kinds are painted with verdict tones

Caption, verbatim: *"Event kinds carry their register: scans green, probes cool,
rollbacks red."* Measured: `scan` = GREEN, `rollback` = RED.

An event kind is a taxonomy, not a judgement — a scan that consumed a character
has not passed anything. `rollback` in red is defensible and should stay
(`tones.py` spends `#e06060` on `lost`, and a rollback is a died-hypothesis).
Green on `scan` is not.

*Fix:* `scan` → `--token` (`#8fa3b8`, the living register's neutral lexical
tone). Keep probe cool, gate warm-worded, rollback red.

### H4 · high · six of nine — the `.port` chip teaches two contradictory vocabularies

Measured CSS:

| file | `.port` base | modifier |
|---|---|---|
| `navigation` | `1px dashed var(--dimmer)`, `--dim` | `.docked` → solid violet; `.refused` → solid red |
| `value_room` | `1px dashed var(--dimmer)` | — |
| `rendered` | `1px solid var(--violet)`, `--violet` | `.off` → dashed dimmer |

`rendered` inverts the polarity: there, the *unmodified* `.port` already wears
the treatment that means "docked" in `navigation`, and the empty state needs a
modifier. Two mocks in one set define the same class name with opposite defaults,
and both are meant to be built from.

*Fix:* one vocabulary — `.port` = dashed `--dimmer` (offered, empty),
`.port.docked` = solid `--violet`, `.port.refused` = solid `--red`. `rendered`'s
`◆ rows · md-rows.ir` becomes `.port.docked`.

### H5 · high · three files — body font-size drifts, and the masthead coheres only by accident

Measured computed `body`:

| files | font-size | line-height |
|---|---|---|
| `artefact_room`, `compilation_room` | **12px** | 17.4px |
| `generation_strata` | **12px** | 18px |
| the other six | 13px | 19.5px |

The two mocks carrying the mass correction render 8% smaller than the rest of
the set, which flatters their density.

The dangerous half is second-order: `.mast` computes to **12px in all nine** —
but only six declare `font-size:12px`; the other three inherit it from a 12px
body. Likewise `.note` computes 13px in all nine, three by declaration and six by
inheritance. Fix the body to 13px in those three files and the mastheads
silently grow to 13px, and every masthead in the set drifts apart. The current
coherence is a coincidence of two errors, not a design.

*Fix:* body `13px/1.5` in all nine, and every chrome size declared absolutely in
the canonical block rather than inherited.

### M1 · medium · eight of nine — the mass law is not met in nine facets

Fill % = the bottom edge of a facet's lowest text-bearing leaf, over its box
height. Below 60% a facet has visible dead air.

| file · facet | fill | leaves |
|---|---|---|
| `rendered` · THE DOCUMENT | **18%** | 2 |
| `generation_strata` · THE SAMPLE | **36%** | 8 |
| `machine_room` · THE GRAMMAR | **39%** | 5 |
| `transpile_room` · THE SOURCE | **42%** | 3 |
| `machine_room` · THE DOCUMENT | **43%** | 3 |
| `transpile_room` · THE TARGET | **46%** | 4 |
| `value_room` · THE SPELLING | **49%** | 3 |
| `navigation` · THE TRAIL | **55%** | 11 |
| `compilation_room` · THE DIFF | **58%** | 13 |

For contrast, the facets that meet it: `value_room` THE IDENTITY 98%,
`artefact_room` THE FAMILY 98%, `transpile_room` THE CROSSING 97%,
`value_room` THE FLOOR 96%, `navigation` THE LANES 95%.

`artefact_room`'s own closing note anticipates part of this — *"the value-room
and transpile mocks are due a density pass"* — but the measurement says
`rendered` and `machine_room` are worse than either, and neither is on that list.
`rendered`'s THE DOCUMENT is the extreme: a five-line `notes.md` standing in for
"a real text plane", in a room whose whole claim is that a file arrives at the
screen. Per-file remedies are in the ranked list below.

### M2 · medium · all nine — no hover state anywhere, though the mocks promise one

`grep -c ':hover'` returns **0 in all nine files**. Yet `navigation`'s own
captions assert the behaviour twice: *"capsules HALO on hover"* and *"edges
highlight WHOLE-LENGTH on hover"*, and its S2 caption calls hover part of "the
whole law" the chrome carries.

A build photograph that states a state in prose but never draws it hands the
implementer a decision the mock was supposed to make.

*Fix:* `navigation` gains a fourth chrome-state panel beside FOCUS/SHIFT/SPIN
showing HOVER on a capsule and on an edge; every file gains the `:hover` rules
for `.cap`, `.port`, `.door`, `.slot`.

### M3 · medium · all nine — STALE and ABSENT are never drawn

ROOMS.md law 3: *"PENDING/STALE/ABSENT are drawn states with words, never
blanks."* Measured occurrences across the set: PENDING is drawn twice
(`navigation`'s `tokenizer.json PENDING`, `artefact_room`'s model payload) —
good. **STALE** appears once, as a word in `navigation`'s prose, never as a
drawn state. **ABSENT** appears zero times in all nine files, though ROOMS.md's
generation room owes *"ABSENT fixtures draw their fetch door"*.

*Fix:* `generation_strata` draws the ABSENT tokenizer fixture with its fetch
door (it is the room that owes it); `artefact_room` or `navigation` draws one
STALE witness — a verdict whose subject moved under it — since staleness is
what makes the two-tier witness licence legible.

### M4 · medium · all nine — the window/pin layer is never drawn

`machine_room` says *"The automaton facet (clone graph lit at t) joins as ⧉
window, elided here"*; `value_room`, `navigation` and `ring` carry the `⧉`
affordance in facet heads. No mock draws what opens.

The living register already carries a full window face family — `winhead`
(11px sans, warm), `pinbody` (12px mono), `pinfact` and `pinaddr` (11px mono),
and `cast` (`rgba(0,0,0,0.55)`, the box-shadow). All of it is unphotographed, so
a builder will invent it.

*Fix:* one mock — `machine_room` is the natural host, since it names the elision —
draws the automaton as a real raised window over the facets, using the
`winhead`/`pinbody`/`pinfact`/`cast` faces.

### M5 · medium · four chip primitives with incompatible geometry

Measured:

| class · file | padding | border | radius |
|---|---|---|---|
| `.fam` · `artefact_room` | `3px 6px` | `border-left: 2px` | none |
| `.door` · `generation_strata` | `1px 8px` | `border-left: 2px solid cool` | none |
| `.door` · `navigation` | `1px 7px` | `1px solid hair` | 3px |
| `.port` · `navigation`,`rendered`,`value_room` | `1px 7px` | 1px | 3px |
| `.slot` · `ring`, `value_room` | `1px 6px` | `1px solid dimmer` | 3px |
| `.gate` · `transpile_room` | `1px 8px` | `1px solid hair` | 3px |

`.door` alone is two different shapes in two files. Three paddings
(`1px 6px`/`1px 7px`/`1px 8px`) do the same job.

*Fix:* one `.chip` primitive — `padding: 1px 7px; border: 1px solid var(--dimmer);
border-radius: 3px` — with `.chip.door`, `.chip.port`, `.chip.slot`, `.chip.gate`
as tone-only modifiers. `.fam`'s left-rule row treatment is a different object
(a list row, not a chip) and should keep its own name.

### M6 · medium · `ring`, `value_room` — the cursor changes colour between rooms

`.slot.open` is `border-color: var(--violet); background:#171322` in `ring` and
`border-color: var(--warm); background:#151a24` in `value_room`. Same for the
span wash: `.sp` is `#241a2e` + violet outline in `ring`, `#2a2410` + warm
outline in the other four files that define it.

`ring`'s violet is partly deliberate and works — its caption earns it: *"The
violet ring border is the room saying whose state this is."* But that argument
covers the **screen border**, not the cursor. Cross-room law 1 is one cursor;
if the open slot and the span wash change tone when you walk into the ring, the
cursor is not one thing.

*Fix:* keep `ring`'s violet `.screen` border (documented, effective). Move
`.slot.open` and `.sp` in `ring` to the warm treatment the other rooms use.

### L1 · low · masthead height drifts 32.4px → 37px

Measured `.mast` box heights: `artefact_room`/`compilation_room` 32.4,
`generation_strata`/`machine_room`/`ring` 33, `transpile_room` 35.5,
`navigation`/`rendered`/`value_room` 37. Five distinct values.

Two causes, both fixable in the canonical block: the 12/13px body drift (H5),
and two different `.travel` implementations — `margin-left:auto` in six files
versus `border-left:1px solid var(--hair); padding-left:12px` in `navigation`
and `value_room`. The bordered variant is the better one (it seams the travel
group off the masthead the way facets are seamed) and should win.

### L2 · low · vertical rhythm drifts across four properties

Measured, with the number of distinct values in the set:

- `.row` `min-height` — **eight** distinct: 200, 300, 300, 330, 330, 340, 360,
  390, 400px. This is arbitrary, and it is partly what produces M1's void
  percentages: a facet is not sparse in the abstract, it is sparse against a
  box height nobody chose.
- `.cap-note` `margin-bottom` — four: 8, 28, 30, 34px
- `.note` `margin-bottom` — two: 22, 26px
- `.fhead` `margin-bottom` — three: 8, 9, 10px
- `.legend` `margin-top` — two: 6, 8px
- `.mast` `gap` — two: 12, 14px
- `.note` `max-width` — 962px vs 936px (a `74em`/`72em` declaration crossed with
  the 12/13px body drift)

*Fix:* single values in the canonical block; `.row` min-height 360px.

### L3 · low · the travel set varies, so three affordances are unreachable from most rooms

Measured masthead travel groups:

- `‹ back ⌗ map` — seven files
- `‹ back ▤ strata ◌ ring` — `navigation`
- `‹ back ▤ strata ⌗ map` — `value_room`
- `‹ back ⌗ map ◌ ring` — `generation_strata`, screen 2

ROOMS.md has the strata *"opened by the ladder chip"* and the ring reachable
*"from any masthead"*. As drawn, six of nine rooms offer neither.

*Fix:* the standing travel set is `‹ back · ⌗ map · ▤ strata · ◌ ring`, minus
whichever room you are standing in. `generation_strata` also omits `h1`'s
`letter-spacing:.06em` (computed `normal` where all eight others compute 0.9px)
— the same copy-paste slip.

---

## The canonical register block

One block, to replace the per-file `<style>` preamble in all nine. Tones and
faces are `tones.py`'s, verbatim; the geometry is the set's own majority value,
except where a finding above named a better one (`.row` 360px from L2, the
bordered `.travel` from L1, the unified `.chip` from M5).

```html
<style>
:root{
  /* tones — tones.py TONES, verbatim. Do not re-spell. */
  --field:#0b0e14; --field2:#0e1219; --ink:#e8e2d6;
  --dim:#66707f;   --dimmer:#3a4250; --hair:#1a2230;
  --warm:#e2a65c;  --cool:#6fc3c9;   --violet:#d98cf5;
  --green:#79c99a; --red:#e06060;    --token:#8fa3b8;
  /* washes — the cursor's span, and the ring's own screen edge */
  --span:#2a3140; --spanfill:rgba(226,166,92,.12); --cast:rgba(0,0,0,.55);
  /* the two voices: mono is lexic's output, sans is opsis speaking */
  --mono:"JetBrains Mono","DejaVu Sans Mono",ui-monospace,monospace;
  --sans:"Inter","DejaVu Sans",system-ui,sans-serif;
}
body{background:var(--field);color:var(--ink);font:13px/1.5 var(--mono);margin:0;padding:28px}

/* opsis speaking — sans */
h1{font:600 15px var(--sans);letter-spacing:.06em;margin:0 0 6px;color:var(--ink)}
.note{font:13px var(--sans);color:var(--dim);max-width:72em;margin:0 0 26px}
.cap-note{font:12px var(--sans);color:var(--dim);max-width:80em;margin:8px 0 30px}
.cap-note b{color:var(--ink);font-weight:600}
.legend{font:10px var(--sans);color:var(--dimmer);margin-top:8px}
.fhead{font:11px var(--sans);letter-spacing:.12em;color:var(--dim);margin-bottom:9px;display:flex;gap:8px;align-items:center}
.mast{font:12px var(--sans)}

/* the room */
.screen{border:1px solid var(--hair);background:var(--field2);max-width:1180px;margin:0 0 14px}
.screen.instrument{border-color:var(--violet)}   /* the ring: whose state this is */
.mast{display:flex;gap:12px;align-items:center;border-bottom:1px solid var(--hair);padding:7px 14px}
.op{color:var(--dim)}
.travel{margin-left:auto;display:flex;gap:10px;color:var(--cool);
        border-left:1px solid var(--hair);padding-left:12px}
.row{display:flex;min-height:360px}
.facet{flex:1;border-right:1px solid var(--hair);padding:10px 12px;min-width:0;position:relative}
.facet:last-child{border-right:none}

/* one chip primitive; modifiers are tone only */
.chip{display:inline-block;font:11px var(--mono);padding:1px 7px;
      border:1px solid var(--dimmer);border-radius:3px;color:var(--dim)}
.chip.door{color:var(--cool);border-color:var(--hair)}
.chip.port{border-style:dashed}                                  /* offered, empty */
.chip.port.docked{border-style:solid;border-color:var(--violet);color:var(--violet)}
.chip.port.refused{border-style:solid;border-color:var(--red);color:var(--red)}
.chip.slot.open{border-color:var(--warm);background:#1a1610}     /* the cursor, in every room */
.chip.gate.holds{border-color:var(--green);color:var(--green)}   /* a verdict — earns green */
.chip.pending{border-style:dashed;color:var(--dim)}              /* NOT warm */
.chip.stale{border-style:dotted;color:var(--dim)}
.chip.absent{border-style:dashed;color:var(--dimmer)}
.chip:hover{border-color:var(--cool);color:var(--cool)}

/* lexic's output — mono */
pre,.plane,.roster,.trace{font:13px/1.5 var(--mono)}
.kw{color:var(--violet)} .lit{color:var(--ink)} .tok{color:var(--token)} .dimt{color:var(--dim)}

/* the cursor: warm, and only warm */
.sp{background:var(--spanfill);outline:1px solid var(--warm)}
.sel{border-left-color:var(--warm);background:#1a1610}

/* verdicts: green passes, red refuses with words. Nothing else. */
.v-ok{color:var(--green)} .v-no{color:var(--red)} .v-un{color:var(--dim)}
.v-pend{color:var(--dim)}   /* pending is dim + dashed, never warm */

/* raised window layer — winhead/pinbody/pinfact/cast, from tones.py FONTS */
.win{position:absolute;background:var(--field2);border:1px solid var(--hair);
     box-shadow:0 6px 24px var(--cast)}
.win header{font:11px var(--sans);color:var(--warm);padding:4px 8px;border-bottom:1px solid var(--hair)}
.win .body{font:12px var(--mono);color:var(--ink);padding:6px 8px}
.win .fact{font:11px var(--mono);color:var(--dim)}
</style>
```

Two notes on the block. `--token` is added because C2 and H3 both need a neutral
value tone that is not green — it is already in `tones.py`, just unused by the
mocks. And the chip modifiers are written so that **green and red appear only on
`.gate.holds` and `.v-no`** — if a future mock needs a verdict tone it has to
reach for a class whose name says "verdict", which is the cheapest way to keep
§8 enforced by construction rather than by review.

---

## Ranked improvements, per file

1. **`rendered`** — worst mass gap in the set (THE DOCUMENT at 18% fill, 2
   leaves). Give it a real `notes.md`: 40+ lines with nested lists, a table, a
   fenced block, inline code, a link — enough that the rendered half has to make
   real layout decisions. Then fix `.port` polarity (H4). This mock currently
   claims universal rendering from a five-line file.
2. **`machine_room`** — THE GRAMMAR 39%, THE DOCUMENT 43%. A 738-event trace
   deserves more than a 3-rule grammar and a 3-line document; show `decide.gbnf`
   whole and a document long enough that scrubbing moves the span visibly. Also
   the natural host for the window layer (M4) and the `scan`-green fix (H3).
3. **`compilation_room`** — repaint the diff (C3), then fill THE DIFF (58%): the
   *"29 unchanged rules folded"* line is the right idea but the fold should show
   more of the mass above it, and the strip's five moments leave the lower half
   of the room empty.
4. **`transpile_room`** — THE SOURCE 42% / THE TARGET 46%. The caption already
   claims *"178 source occurrences over 71 objects → 33 built"*; draw a
   `doc.json` big enough to hold 71 objects instead of a 5-line one. THE CROSSING
   at 97% shows the room knows how.
5. **`value_room`** — THE SPELLING at 49% with 3 leaves, next to THE SHAPE at
   93% and THE IDENTITY at 98%. The spelling facet should carry the whole gbnf
   text, folded, not six rules. Also fix nine green literals (C2).
6. **`navigation`** — fix the amber-dashed pending arcs (H2, and it contradicts
   its own note); add the HOVER chrome-state panel (M2); THE TRAIL at 55% could
   carry a deeper history stack, which is also what makes BACK legible.
7. **`generation_strata`** — THE SAMPLE at 36%. Draw several witnessed samples
   with their seeds, not one; add the ABSENT tokenizer fixture with its fetch
   door (M3); restore `h1{letter-spacing:.06em}` (L3).
8. **`artefact_room`** — closest to right on mass (98/77/68%). Fix `.v-pend`
   warm (H2) and the one green docstring (C2), and raise the body to 13px (H5),
   which will cost it some of its apparent density.
9. **`ring`** — cleanest register discipline in the set, and the only room with
   no verdict-tone misuse at all. Only change: `.slot.open` and `.sp` to warm
   (M6), keeping the violet screen border.

---

## What already coheres

Worth stating plainly, because the drift list is long and most of the set is
disciplined:

- **The eleven `:root` tones are byte-identical across all nine files.** Despite
  being copy-pasted nine times, not one hex has rotted. The palette's problem is
  which palette it is (C1), not internal drift.
- **The facet head is one face everywhere** — 11px, `letter-spacing` computed
  1.32px (`.12em`), `--dim`, no `text-transform`, in all nine. It is the single
  most-repeated element in the set and it did not drift at all.
- **The hairline is one hairline** — `1px rgb(30,36,48)` on `.screen`, on
  `.mast`'s bottom edge and on `.facet`'s right edge, identical in all nine.
  `ring`'s violet screen border is the one exception, and it is deliberate,
  captioned, and effective.
- **The room's box metrics agree** — `.facet` padding `10px 12px`, `.mast`
  padding `7px 14px`, `.screen` max-width 1180px and background `#11151d`,
  `body` padding 28px, `h1` 15px/600, `.legend` 10px `--dimmer`, `.cap-note`
  12px `--dim`: every one identical across all nine.
- **Nothing breathes idle.** Zero `@keyframes`, `animation`, `transition` or
  `blink` in all nine files. VISION §8's first clause is honoured without
  exception — no mock reaches for motion as decoration.
- **Refusals speak the engine's words.** Measured red text is, in every case,
  real engine vocabulary rather than a synthesized message or a bare ✗:
  `FieldValidationError: pad: 999 outside [0, 64] · not applied`,
  `UnsupportedConstructError: IrTypeMap: no action for 'int'`,
  `rule 'loop' cannot terminate — every arm loops forever (max_depth, by heights)`,
  `generate: rule 'gone' is not defined — the grammar defines ['root', 'sub']`,
  `✕ resolver · code, registry only`, `free text — not offered; a slot takes values`.
  This is the hardest part of §8 to hold and the set holds it everywhere.
- **Bounded counts say what they dropped** — `… 24 more rules ▸ show all 32`,
  `… 29 unchanged rules folded`, `… 8 more ▸ all 15`, `… 12 more shared`,
  `… 4 more subjects — derive less, never clip`, `… 36 more classes`. Law 4 is
  met in every room that bounds anything.
