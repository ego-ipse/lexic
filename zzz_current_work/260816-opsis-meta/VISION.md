# opsis — the wrapping vision

The position at the meta level. Everything here is either settled by ruling
(marked ⊨), carried from the probe-ruled foundation of 260807-opsis-radical
(marked ⊢ — attacked and surviving, or built and measured), or this
document's own synthesis awaiting attack (unmarked). Present tense; status
lives in LEDGER.md.

## 1. The claim

⊨ **Opsis is the universal surface for grammar-defined content.** Give it a
string of content and the grammar that reads it — plus whatever plugs the
reading requires — and it renders a viewable, addressable, losslessly
editable surface. Markdown under a markdown grammar, JSON under any JSON
formulation, a config format, vyx traffic, lexic's own notation and twins:
one mechanism, no privileged formulation, ever. The way a browser renders
HTML, but with the language *declared* rather than baked in.

Lexic self-inspection — the parsing room, the compile pipeline, the
instrument reading its own policy — is not the definition; it is the two
proofs. First proof of depth: the engine's own artefacts are the hardest
content to render honestly. Second proof of universality: the instrument
renders *itself* through the same pipeline, so nothing is privileged, and
the ladder closes into a ring.

⊢ Opsis is lexic's screen-flavour. A flavour is metadata + grammar +
reducer + emit actions, where emit actions spell a value as text. A
screen-rendering of a language is the same triple with the emit half's
codomain changed: **presentation is an emit half whose target is addressed
regions instead of text**, and the gesture layer is its parse-back half.
Opsis does not compute; lexic computes; opsis spells and points.

## 2. The ownership line

⊨ **Lexic owns everything sayable; opsis owns only where things stand and
what the hand does.** Any work found to be required in lexic is in scope —
opsis reveals, and by revealing shows ways to improve lexic. The
presumption is reversed from the space_3 slices: if opsis computes a *fact*
about a subject — structure, identity, sharing, correspondence, trace,
licence, chirality — that computation is an engine surface waiting to be
named (ASKS.md ranks them). Only arrangement, register, camera, cursor
mechanics, session, and history are natively opsis's.

The precedent is executed, not aspirational: the transpilation round's
design pressure produced `IrMapping.children()`, `IrEach` over mappings,
the model-layer walk, and `lexic.compile.transpile` — engine surface that
ships to everyone. Every ask lands in `src/lexic` with repository tests;
nothing is painted around.

## 3. The viewing — what a rendering is made of

A **viewing** is a stack: text ⊳ grammar, plus the plugs the language
requires —

- a **tokenizer** where the language has a token layer (`.bind(tokenizer)`,
  a new artefact — a second subject);
- a **reducer** where meaning is wanted beyond structure (text → the
  reducer's value);
- a **resolver** where ambiguity must be settled — ⊢ the one plug that is
  CODE, a registry of named deciders with a drawn refusal for arbitrary
  ones; every other plug is a VALUE;
- **presentation rows** where the language has an authored ceiling (§4);
- **templates** where extraction is wanted (`Spec`/`KEEP`/`SpanPair` — the
  surface exists in `lexic.compile.templating`, generic over any compiled
  grammar).

⊢ Every value-plug projects, travels as notation, and reloads live
(probe-ruled for Reducer and IrTokenizer; flavours are pure data with zero
IrLambda). So plugs are authored in the value room (slot-based editing,
offers from the algebra, never a textarea), loaded from files, or lifted
from a parsed document. Each plug is a subject; the stack is a relation
instance with ports; **renderability is a computed licence** that ingress
offers — never a declaration (the space_3 review's M4 is doctrine now).

This is what scopes the attachment story: attachments are not features
beside the rooms, they are the constituents of a viewing.

## 4. Presentation — the emit half, in two tiers

⊨ (provisionally — "sounds fair for now") The presentation contract:

- **The kind-keyed floor, on the spine.** Any `IrSelf` renders honestly
  from the guaranteed protocol alone: a record as its named fields, a
  sequence as its indexed elements, a leaf as its payload, absence as
  `IrNone`'s one spelling. MRO-walked, raising default — an unauthored
  kind draws the refusal's own words, never mush, never blank, and never
  anonymous circles.
- **The rule-keyed ceiling, per language.** Authored rows keyed by a
  grammar's CANONICAL rule names — never codegen helper names — shaped
  like transpile tables: pure data, baked against the compiled artifact,
  gated for completeness, travelling as notation, loadable like flavour
  manifests, declared minimally with the rest derived from the binding
  (the `MapShape` precedent: a restatement can disagree). A ceiling is
  authored against a grammar and is honestly formulation-BOUND: the
  mechanism is generic, a given table is not, and a second formulation of
  the language gets the floor plus the gate's refusal, never silence
  (adversarial B2). A markdown table draws headings large and code shaded;
  a reducer draws as its rule→action rows; a tokenizer as vocabulary and
  segmenters. Each row is a claim about what the thing IS.

Rendering a language is transpiling it into screen-space — with the
ownership split kept (adversarial B3): lexic owns the **addressed
emission** (parts carrying address, field, and text extent in a named
measure — ASKS.md #1, the keystone), because what regions exist and what
they say is a fact about the value and its spelling; opsis owns the
**solve** — where regions land, in what screen coordinates — because that
is arrangement (§2). Row and region node types are lexic vocabulary on the
`IrDoc` dual-role precedent; the solver never enters `ir/`. Until the
keystone lands, rows are opsis-side open dispatch tables and the ceiling
is stated as that.

**Every drawn part is an address.** The drawable unit is the occurrence —
field-of-record, element-of-sequence, rule-of-grammar, span-of-document.
An occurrence IS a node — of the drawn graph: the pair (path, value), a
value standing somewhere, which is what a capsule holds. What it is not
is the value object alone: the spine shares equal values by identity (one
`Ws` object, seven reachings), so one value has many occurrences, and the
address — a path assigned top-down by the driver, positionally, never
recovered from the value object (adversarial B1) — is what makes each
occurrence its own capsule. Everything drawn is a hit; selection moves
the shared cursor; entering travels. No dead regions. The floor's raising default
fires for non-nodes; genuine `IrSelf` kinds always land on a floor row via
MRO — the refusal that CAN occur is the one the register promises.

**Editing is a re-reading, everywhere.** Text is primary; the model is the
grammar's account of what the text says; a commit splices text and parses
again, and every projection re-derives or nothing changes. Under universal
rendering this quietly makes opsis a *structural editor* for any language
with a grammar. Refusals keep the typed text, draw the measured frontier,
and speak the engine's words verbatim.

## 5. The geometry — the cycle made navigable

⊨ The pipeline is a cycle, not a line: every compiled form is
simultaneously an output (artefact, witnessed) and an input (subject,
probed). The cycle has a geometry with four motions, and navigation happens
in it:

- **The orbit** — the ring of a subject's representations. A grammar's
  orbit: its flavour texts, its twin, its notation, its grammar-payload. A
  value's orbit: its notation, its payloads, its dump, its document
  spelling under a grammar. The orbit is COMPUTED, never declared: each
  variant is its own content-addressed text subject, and membership is
  computed per subject kind (adversarial M8): a grammar's ring by
  canonical equality (name- and factoring-sensitive — a fact stated on
  screen, not hidden), a value's ring by spine equality plus a per-form
  load-back witness, a text's ring by reading to the same value under the
  same reader. The three compiled manners —
  twin/module, payload, notation — exist for values AND for grammars;
  designing any surface around the twin alone is the named trap.
- **Altitude** — value → document → grammar → metagrammar → the fixpoint.
  The climb, and the descent: a grammar's documents, its generated
  samples.
- **Interior** — descent into a part: from a compiled value to an `IrMap`
  inside it, from a grammar to one rule, from a reducer to one action. The
  spine protocol (fields, indices, keys) defines this completely.
- **Laterality** — crossing to a connected peer: grammar → its tokenizer,
  reading → its docked reducer, document → its transpiled twin lane,
  rule → the reducer entry that reads it, type → the emit action that
  spells it.

**Projections, not destinations — the tesseract rule.** ⊨ Four axes do
not fit one drawing: rendering the whole geometry at once would be
projecting a tesseract, and a single clever 3-D picture is exactly the
kind of heroic view that dies of its own density. The instrument's answer
is the one it already has: multiple simultaneous LOW-dimensional
projections, each an axis restriction with its own coordinate system,
welded by the shared cursor — the way a tesseract is understood through
its shadows and nets, never through one image. The strata is the geometry
restricted to altitude. The artefact room is one subject's orbit. The
value room is an interior. The map is the widest projection on screen —
never "the whole." Co-selection across projections is what makes the 4-D
object legible, and it is why the cursor's singularity (§7.5) is
load-bearing rather than aesthetic. None of them is storage: ⊢ storage is the one typed graph — subjects content-addressed,
relations carrying compile parameters and verdict + cost + witness — with
ONE digest scheme and ONE store (the space_3 two-worlds split is the
counterexample, not a precedent).

The engine answers four queries uniformly — what spellings does this have,
what reads it and what does it read, what is inside it, what stands beside
it — as computations (ASKS.md #2). Opsis draws the answers.

## 6. Travel and the hand

⊢ The settled moves: cast-up, cast-down, enter-room, back, map. BACK is a
history stack, never a graph edge. Docking is not travel.

⊨ The geometry's candidate moves — **spin** (around the orbit), **dive**
(into the interior), **shift** (lateral) — become named moves *iff they
justify themselves*, and the justification is VISUAL: each must exist as a
gesture on the drawn geometry — spinning the ring, entering a capsule,
crossing a drawn edge — never as a stale button. A move that can only be a
button is not a move.

⊨ **Visual and classical representations coexist, side by side.** The
parsing room is the model: the overview band beside the real text plane,
the spine beside the derivation, each a projection of the same subject
with its own coordinate system, none forcing the others out. The same
both/and holds at every scale — the map holds the geometric drawing
(orbits, altitude, laterals — the Limit Theory node picture, drawn with
authored shapes, never soup) AND a lane/list projection at once, composed
like facets, both under the perf gate. Only a sith thinks in xor gates.

## 7. The language — six elements, repaired

Carried from WAYFORWARD §3.0 with the adversarial repairs binding:

1. **The capsule** — a value standing somewhere (an occurrence). One
   chrome: kind glyph · name · address. Click = focus; enter = travel.
2. **The edge** — a relation, realized (verdict in its tone, words on
   hover) or offered (a door chip; clicking CASTS). Ports are offered
   edges; docked attachments are realized ones with a product capsule.
3. **The verdict** — a relation's drawn judgement: tone, gates, verbatim
   refusal, PENDING, STALE, ABSENT. Verdicts belong to relations, never
   float free, never sit on controls.
4. **The facet** — a projection of the focused subject with its own
   coordinate system, hairline-seamed. Rooms differ ONLY in which facets
   they compose. A placard is not a facet; a section renderer may serve
   *inside* a facet, never as a screen.
5. **The cursor** — owned by the subject, drawn by every projection that
   shows it. Repair (ADVERSARIAL_MOCK B1): the singularity must hold — the
   focus facet always shows the cursor's subject; if a second channel
   exists (hover, lane-selection) it gets its own chrome and is counted in
   the language.
6. **The control** — chrome acting on the INSTRUMENT: travel, windows,
   clock, register. Controls never masquerade as subjects.

Granularity honesty is part of the language (ADVERSARIAL_MOCK B2): a facet
draws only at the granularity the engine exposes — clone frames until a
kernel trace protocol exists, model spans because `emit_parts` is real. A
facet drawn at an invented granularity is a fake facet, and a room with
nothing to do is a gate failure, not a placeholder.

## 8. The register — spectacle without ornament

⊢ Unchanged from the foundation: there is no opsis without spectacle, and
the spectacle is the computation made visible. Nothing breathes idle;
motion means traversal, recomputation, or a changed arrangement; a third
axis is earned only when a third independent meaning exists. Refusals
speak the engine's words; pending is drawn, never blank; no silent caps —
a bounded drawing says what it dropped. Truthful-claims chrome down to the
wording (visual_4's standard: "structurally — classes synthesized apart"
rather than a fake ✓).

## 9. What v1 of the wrap is, ranked

1. ⊨ The lexic keystones first (ASKS.md #1–#2), so the rooms are built
   once on real engine surface — not a third generation of bespoke
   renderers ported later. The asks are probed, adversarially attacked,
   and only then written.
2. One graph, one digest scheme, one store; ingress files results into it
   as pending→promoted subjects.
3. The shell extracted; the reading room re-hosted as its first client,
   behavior-identical, gates carried whole.
4. The map as the geometry's whole-view (both projections, §6), in the
   perf gate at the target subject count.
5. The value room on the two-tier presentation contract — any IrSelf, its
   particular authored shape, the floor beneath, the raising default on
   screen.
6. The viewing as the unit: plugs dockable at ports, authored in the value
   room, renderability a computed licence. ⊨ Three authored ceilings
   demonstrated together — markdown, JSON, and ABNF — so no single-format
   renderer can be written by accident: the mechanism must stay generic
   across all three, each an ordinary formulation through the standard
   pipeline, none privileged.
7. The orbit drawn: one subject's full representation ring with witnesses,
   spin as a gesture if it earns itself.
8. Travel completed over the geometry; one history; every gesture through
   one router.

Deferred with recorded reasons, nothing silent: the tokenizer generation
room (fetched fixtures cannot gate on a fresh clone); instruction-level
machine drawing (waits on the kernel trace ask); directives/vocabulary on
relation instances (needed before two readings of one pair coexist).

## 10. The quality bar

The repo's own: flat code, open dispatch, refusals with words, no silent
picks, no suppressions, `run_checks.sh` exits 0. Frames as data in the
gate; the leaf probed in a real browser; every stage of migration leaves
the gate green and adds the assertions that would have caught the mess it
fixes. Vision documents carry position; ledgers carry status; the two
never mix again.
