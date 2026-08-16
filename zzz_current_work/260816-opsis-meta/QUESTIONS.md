# Open rulings

Each with a recommendation. Settled rulings are recorded at the bottom and
in VISION.md; once ruled, an entry moves down, never re-opens silently.

## Q1 — The travel moves' visual gestures

Spin / dive / shift are admitted iff they justify themselves as gestures
on the drawn geometry (ruled). What remains open is the concrete gesture
per move and which earn v1:

- **spin** — candidate: drag/scroll around the drawn orbit ring; the
  variants rotate through the focus position. Earned only when the orbit
  is drawn (VISION §9.7).
- **dive** — candidate: enter on a capsule that is a part (the interior IS
  the value room's descent); arguably this is enter-room wearing the
  geometry, not a sixth move. Recommendation: fold dive into enter.
- **shift** — candidate: crossing a drawn lateral edge (click the edge,
  not the peer capsule). Distinct from enter because you stay at the same
  altitude and the trail records the edge kind.

Recommendation: rule per-move at the moment its geometry is first drawn,
against the "a move that can only be a button is not a move" bar.

## Q3 — The measure function for addressed offsets

Revised after adversarial M10: "character units" names two incompatible
measures already in this thread — `ir/text/layout.py` counts code units
(`len(text)`, wide-glyph-blind) while the instrument's `columns()` counts
terminal columns with East-Asian wide glyphs as 2 (and `measure.py` uses
fractional units besides). The contract must name the measure FUNCTION
and whether it is integral, not a unit word. Recommendation: the
addressed emission (ASKS #1) carries offsets in code units — the string's
own truth, stable across renderers — and any column/pixel measure is a
projection applied by the consumer; whether `layout.py`'s width solving
also needs a column-aware measure (`japanese.gbnf` is in the corpus) is
investigated inside ask #1.

## Q4 — Where the presentation ceiling's rows live

Per-grammar row tables travel as notation (ruled provisionally). Open:
are they part of a flavour-like bundle ("screen flavour" = grammar ref +
reducer ref + rows, one manifest), or free-standing tables docked as
plugs? Recommendation: free-standing plugs first; bundle later if
manifests want it. (Justification corrected by adversarial B2: a table is
formulation-BOUND by its rule-name keys and gated where it does not
apply — the earlier "composes with any formulation" claim was wrong; what
free-standing buys is docking the same table onto any *reading that
compiles the grammar it was baked against* — extended across pure
renamings by the alignment witness (ASKS #3) — and minimal declaration
with binding-derived routing keeps the coupling small.)

## Q6 — Relation-instance directives/vocabulary

Carried from space_3 OPEN-7: without directives/vocabulary on the relation
instance, two readings of one (reader, document) pair are
indistinguishable nodes. Recommendation strengthened by adversarial M11:
**fund it now, fully** — the engine already treats directives and
vocabulary as part of what-was-compiled (`compile_text`'s memo keys on
`(stem, flavour, vocabulary, directives)`, with the reasoning written in
place; `bind(tokenizer)` returns a NEW artefact). A graph that
content-addresses a reading without them merges two distinct artefacts
into one node the first time anyone passes `Directives(...)` — and the
viewing model makes tokenizer plugs routine. Deferring this repeats
engine-known identity semantics as a graph bug.

---

## Settled (2026-08-16)

- **M7: separate products, shared leaves.** The kernel trace is its own
  ask; its events reference ask #1's address/span records, so
  co-selection composes across products without translation.
- **A pure rename is no boundary.** Names-abstracted equality with an
  alignment witness (ASKS #3) transports rule-keyed tables across
  renamings; refusals are reserved for structural difference.
- **An occurrence IS a node** — (path, value), the drawn graph's unit;
  it is the value object alone that it is not.

- **Src sequencing: src/lexic first.** The asks are refined by probing,
  attacked by an adversarial round, then written. Opsis rooms follow the
  keystones. (Former Q7.)
- **The map draws both projections side by side** — geometric and
  classical at once, the parsing room's precedent (its facets never force
  one or the other). Not a toggle; a composition, under the perf gate.
  (Former Q2.)
- **The first authored ceilings are md, JSON, and ABNF together** — three
  languages so no md renderer gets written by accident: any solution must
  stay honest and generic across all three through the standard pipeline.
  (Former Q5.)

- **Any lexic work is in scope.** Opsis reveals; revealing improves lexic.
- **The cycle is geometric and navigated** — orbit, altitude, interior,
  laterality.
- **Universal rendering is the claim** — any text under its declared
  grammar plus required plugs; vyx is an instance.
- **Named moves iff visually justified** — a gesture on the drawn
  geometry, never a stale button.
- **Visual and classical representations coexist** — the parsing room is
  the model; only a sith thinks in xor gates.
- **Presentation contract** (two tiers, transpile-table-shaped ceiling) —
  accepted provisionally.
- **Opsis lives in src** in this repo, possibly a submodule later for
  maintainability.
- **No sacred cows** — the reading room's behavior is the bar; its code is
  a quarry.
