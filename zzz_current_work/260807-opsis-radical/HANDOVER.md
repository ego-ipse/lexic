# opsis-radical — HANDOVER (2026-08-08, end of day 3)

## NEXT SESSION — start here

**The user's parting corrections, verbatim intent — they define tomorrow:**

1. **The inward readers are a NONISSUE.** I had framed "the notation isn't
   readable" as an engine ask. Wrong: lexic already reads its own compiled
   and notation forms — `compile/notation/parse.py` (notation text → real
   lexic.ir objects), the module self-grammar (exports), the manifest
   loader (`*.flavour.ir` → a live IrFlavour). The inward axis is readable
   TODAY through existing surfaces. **Start with this tomorrow.**
2. **IrFlavour is an IrSelf and an IrNamedTuple.** Not magic — topology
   already defined. Flavour components (reducers, emit actions, escapes,
   tokenizers) are IR values on the record spine; they enter the layers
   graph as nodes through the SAME machinery as everything else. The
   `*.flavour.ir` files in `src/lexic/grammars/` are literally their
   notation spellings.

So the first build of tomorrow: **the layers compass over existing
surfaces** — inward readings via the notation surfaces, outward via the
module self-grammar (already a rung), flavour nodes as IR values, no new
engine work. THINKING §10c holds the corrected axes model (vertical /
inward / outward / lateral+intersections — the export module is OUTWARD,
the merge-find-set axis; my "IR floor" labeling was a type error the user
corrected).

## Where the instrument stands (all committed, `opsis_proto` through `91f653f`)

Cold start reads, in order: VISION.md · SPEC.md · this file ·
`atlas/TALLY.md` (the live ledger — every round, including both reverts) ·
`atlas/THINKING.md` (§9 facet management · §9b split-tree · §10 the
ladder · §10b IR floor + the ring · §10c the corrected axes).

**Day 3 delivered, in order:**
- **Layout**: the arrangement is a split TREE (`arrange.tree`, one
  s-expression; h/v splits + `t` tab groups); every internal edge a seam;
  topology by gesture (edge-split / centre-tab drops; chip, header and
  tab all drag as the node's aliases); the dock (presence nodes, grouped).
  THE ARRANGEMENT map was built twice and REVERTED twice (popup, then
  facet) — the real answer became §10.
- **The ladder** (§10): `Session` = readings per fixture, lazily built;
  focus + travel (`POST /focus`, `#LADDER` on the wire, the lineage strip
  in the masthead); one policy record spans the session. Travel is the
  duality made kinesthetic: json.gbnf flips reader→document in one click.
- **The outward rung + the ring** (§10b, retyped by §10c): the
  metagrammar's export module read by the module self-grammar (34.7K
  chars, PDA, 0.07s, faithful — census-gated), now correctly typed as an
  OUTWARD move (`x` kind, dashed chip). **The ring**: the session policy
  record is a reading (`atlas/fixtures/policy.gbnf`, the ⚙ rung, violet);
  travel to it, edit it as text, **save APPLIES it** — census-gated and
  screenshot-proven (a saved `arrange.tree` line rearranged the screen
  that displayed it). The engine finding that stands: the module
  self-grammar's own names (`esc-u`/`esc-U`) collide under name folding →
  no flavour can spell it → `export_source` cannot export it → the true
  fixpoint (`module-grammar ⟲ its own export`) is blocked; atlas reads it
  via a language-identical rename.
- **Earlier day 3**: engine clocks rebuilt as the machines (PDA frame
  trace with rollback fates, Earley hypothesis field), the automaton view
  (walk-lit clone graph), verdict badges (the analysis' per-rule
  reaction), the `decide` (738 attempt events) and `amb` (429
  derivations, resolver `first`) observation fixtures, `/column`
  on-demand Earley items, the spine following the clock, live cross-leaf
  policy sync, TUI panes-for-pins.

**Both reverts, ledgered honestly:** the §9b clone/pin-minimize/re-dock
bundle (clone dodged the singleton-renderer truth) and the map rounds
(furniture instead of the ladder). Root causes in TALLY + §10c.

## Run

```bash
# fixtures: vyx | meta | long | abnf | decide | amb — or <grammar> <doc> [port]
uv run python zzz_current_work/260807-opsis-radical/atlas/serve.py long 8901
uv run python zzz_current_work/260807-opsis-radical/atlas/serve.py meta --census   # every fixture gates
uv run python zzz_current_work/260807-opsis-radical/atlas/tui.py meta --census
```

Deterministic states: `?t= ?sel= ?rule= ?break= ?graph ?gpin ?rail=a,b ?map
?focus`; travel via `POST /focus i`; policy over `POST /policy`. The
census asserts the ladder (export rung faithful, opsis rung reads the
record, THE RING APPLIES) on every gbnf fixture.

## Open threads, ranked for tomorrow

1. **The layers compass on existing surfaces** (the user's directive):
   inward readings (notation parse / manifests), flavour nodes as
   IrNamedTuple values, the compass facet showing position + moves
   (↑ abstraction · ⊙ inward · ⧉ outward · ↔ lateral). Existing rungs
   become edges of this graph; the strip is its 1-D projection.
2. **Anchored facets** (clone, correctly defined): a facet pinned to an
   off-focus node — needs per-facet subject pointers; defined in §10,
   costed but not started.
3. **The SPPF view over amb** (429 derivations, N families — "any Earley
   conversation without the SPPF is dead on start"); the forest surfaces
   (`to_chart`, Links families) are proven reachable.
4. Engine asks parked: exportability for IR-authored grammars (the true
   fixpoint); the other agent's PROPOSAL was GO'd and they were
   implementing — expect src/ commits from their lane; do not touch src/.
5. Dock scale pass · pop for non-reader facets · TUI parity for
   travel/ladder (TUI ignores them today, censuses green).

## Traps (cumulative; day-3 additions first)

- Patch scripts: assert every anchor, END WITH THE WRITE — two more
  crash-before-write incidents today; one anchor probe CLOBBERED its
  target (repaired). `grep -c` the disk after every batch.
- `[hidden]` loses to any authored `display` — third occurrence; the rule:
  every hidden-toggling element gets `[hidden]{display:none}` in the same
  breath.
- Shell `$()` strips trailing newlines — the policy grammar refused a
  record over it (honestly). Use heredocs for record bodies.
- The masthead must stay one line (desc ellipsizes, strip scrolls) — it
  ate half the screen once.
- The census drives a bare Handler through the `subject` property SETTER
  shim (wraps a solo session) — keep it in mind when touching Handler.
- chrome-headless screenshots capture at LOAD; polling/gesture behavior
  is code-verified + user-verified only. The browse daemon's chromium
  cannot sandbox (AppArmor); drive playwright's shell directly with
  `--no-sandbox`.
- `pkill` exit 144 aborts `&&` chains — verify ports by curl. Run git
  from the repo root (cd path-doubling). The tally lives where the work
  lives: `atlas/TALLY.md`, nowhere else.
