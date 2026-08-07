# 0/3 — What is the tech stack for opsis?

Per the standing instruction, this starts from nothing: no prior stack
investigation was consulted, and none of its findings are reconstructed here.

The question is not "which framework". It is four separable commitments, and
they should be judged separately, because they fail separately.

## Answer, before building (2026-08-07)

**1. Process: in-process with lexic.** Opsis's subjects ARE `IrSelf` objects
and its configuration IS IR. In-process, deixis is object identity, `read` is a
function call, a refusal arrives as an exception carrying its own words, and a
`Vis`-like value can hold a live `CompiledGrammar` without a wire spelling.
Every out-of-process stack must invent an encoding for `IrSelf` — that is a
serialization layer, and three formulations died establishing that opsis does
not get one. This commitment is the load-bearing one.

**2. Language: Python** — it follows from 1, since lexic is Python. It also
closes a failure class structurally: one language means no JS-in-strings, no
CSS-in-strings, no foreign blob channel at all. A prototype was shelved over
exactly that; in-process Python makes the offence inexpressible rather than
discouraged.

**3. Rendering model: immediate mode — `frame = render(session)`.** "Opsis is
configuration being instantiated" is the immediate-mode contract, verbatim. IR
is immutable tuples, so modification is reconstruction, and an immediate
renderer makes reconstruction free: the next frame simply reads the new value.
Retained trees (the DOM above all) were the standing impedance mismatch — the
fragments protocol, the camera snapshot/restore dance, innerHTML swaps killing
scripts — machinery whose whole job was simulating "the frame is a function of
the state" on a substrate that refuses it.

**4. Pixel backend: a commodity, deliberately swappable.** The renderer leaf
draws text, lines, boxes; it names nothing of lexic. Which library supplies the
pixels is the LEAST binding choice and should stay revisable: tkinter for this
demonstrator (stdlib, zero pyproject impact), a GPU-backed canvas later if the
register demands it — the walk, the table, and the records all survive that
swap unchanged. The browser is demoted, not banished: it is an *export target*
(a frozen artifact that travels), produced by the same walk with an HTML
backend, never the living instrument.

Open questions carried, not hidden:

- **Text editing** is the native path's biggest unpaid cost; the browser gets a
  text engine free. The demonstrator's retype-a-leaf is honest but minimal.
- **Layout**: lexic ships its own width-aware layout algebra (`ir/text/layout`).
  The radical endpoint is that opsis's layout engine is *lexic* — "lexic does
  everything" includes arranging. The demonstrator hand-places; unresolved.
- **The register ceiling**: whether stdlib-canvas flatness can carry the
  aesthetic, or the pixel leaf must be GPU-backed sooner than later.

## Answer, after building (same day)

The position survived contact, and sharpened in three places:

- **In-process paid immediately.** Every fact on screen (`is IrNone`,
  `rec.lo is rec[0]`, the census walk) is measured on the live object at draw
  time. The reflective panel cost *zero* mechanism: the instrument's `Style` is
  just another record in the tree, drawn by the same table entry — there was
  nothing to build. Self-modification fell out of `set_at` + rebuild in ~15
  lines. None of that is expressible across a seam without inventing protocol.
- **Immediate mode paid immediately.** "Edit pad → the whole page re-spaces"
  required no invalidation logic, no diffing, no camera dance: delete-all,
  render the new value. Hover/selection are frame inputs, not stored widgets.
- **The pixel leaf bit back, on schedule.** Tcl 9 renders a `str` subclass as
  an opaque object handle — an `IrStr` drew as a pointer number until coerced
  at the one text seam. The lesson is the architecture's point: backend
  quirks were absorbed at a single choke point (`Frame.text`), which is what
  "the leaf is swappable" means in practice.
- **Cost check**: the full frame is ~90 canvas items; census 26 regions;
  redraw-on-hover is imperceptible. No evidence yet that tk is the ceiling at
  demonstrator scale; the register question (glow, depth, motion) is real and
  deliberately not answered by this demonstrator.

Third look belongs to the user, after driving it.

## Amendment, after the user drove it (2026-08-07)

**The litmus that tkinter failed: text could not be selected.** A surface where
text cannot be selected, copied, or caret-edited is a *picture* of a tool — the
user's comparison was exact: vscode or obsidian without selection is not
imaginable. Canvas glyphs are pictures of text. This is not a polish gap; it is
the scalar tier's presentation problem, and it is disqualifying for the tool
half of opsis.

What it changes, precisely:

- Layers 1–3 (in-process, Python-hosted subjects, immediate mode over IR)
  are untouched — the wolf runs on them at 12K spans without strain.
- Layer 4 splits. The **structure plane** (span lanes, overview density,
  topology, spine) tolerates any canvas. The **text plane** (documents,
  grammar sources, every scalar leaf) requires a genuine text engine:
  selection, caret, IME, clipboard, reflow. tkinter does not credibly supply
  one, and hand-building one is the mistake the JS world's `pretext` exists
  to spare people — a library class Python simply does not have.
- The browser's text engine is today the only supplier of real text AND GPU
  spectacle in one surface. That is a serious, recorded update toward a
  hybrid leaf for the living instrument — a real text plane with the drawn
  structure plane above/behind it, one deixis across both — with the walk,
  the table, and the records unchanged on the Python side.

The census gates could never have caught this: scripted checks verify what is
drawn, not what can be grasped. The user's live hand is the gate — again.

## Candidate third leaf (2026-08-07, evening): the terminal, via ghostty

The pixel-leaf layer was built swappable; a TUI leaf is the strongest third
candidate, aimed at the terminal-dwelling audience (developers, agents). For:
the cell grid IS the weld (exact geometry by construction — the problem
pretext solves in the browser does not exist); GPU + shaders carry the
register natively; keyboard-first; and the wire is already terminal-speech —
a TUI leaf speaks the same /scene //cursor /edit protocol against the
unchanged server. Against, and deciding: the tk litmus half-applies — mouse
reporting forfeits emulator selection, so selection is app-implemented
(tractable on a grid + OSC 52 clipboard, unlike canvas — but not free), IME
is rough, and the mono/sans register channel dies in a grid. Verdict by
hostile slice, not argument: the document facet as a TUI over the existing
wire, then look. libghostty EMBEDDING is premature (API untagged; render/view
layers longest-term) — watch, don't build on. Immediate cheap win regardless:
kitty-graphics inline rendering of shots and frozen artifacts.
