# Handover — `flavour_2` reduce side (`IrCallable` removal)

**Date:** 2026-06-18
**Scope:** the *reduce* direction only (parse tree → IR).

**Where the rest lives (not blessed as authoritative — that's the user's call):** the
seven-phase structure was drafted in `plans/flavour-2-lark-cutover/flavour_2-handover.md`
and the visual plan `plan.mdx` beside it. Treat them as prior drafts, not a fixed plan:
parts have already moved (e.g. the handover still frames the canonical tag as an open
question, which this session resolved to "tag = rule name", and it predates all of the
reduce thinking below). A brainstorming spec was also drafted and **deleted** this
session because it hard-coded a wrong algebra — see "don'ts" below. This document covers
only the reduce side.

**Goal:** make every reduction body pure `IrSelf` — delete the 18 `IrCallable`s in
`ABNF_REDUCTIONS` (`grammars/abnf_2.py`) and the emit-side `_abnf_charclass`
`IrCallable`, with nothing relocated to a Python callback.

---

## STATUS — 2026-06-20 (authoritative; everything below is the original pre-implementation plan)

**The reduce cutover is wired and green.** Self-hosting fixpoint + CRLF + idempotent
all hold; pyright clean; ruff clean; **1004/1012 tests pass** — the 8 failures are all
in `test_abnf_2.py`, pending the mechanical port in *What's left → A*.

### Implemented

**New IR nodes**
- `IrArg(IrInt)` (`ir/action.py`) — positional `nc` reader (`nc[self]`, undispatched);
  the argument-channel analogue of `IrIndex`.
- `IrBuild(IrNamedTuple[type[IrSelf], IrSelf])` (`ir/action.py`) —
  `target(*(nc if args is IrNone else args.eval(...)))`. Default `args=IrNone` splats
  the channel; an `args` body reshapes it (wrap-as-leaf, collect-into-`IrSeq`).
- `IrPipe(IrNamedTuple[IrSelf, IrSelf])` (`ir/action.py`) — focus-shift onto a *computed*
  value: `body.eval(d, source.eval(d, n, nc), nc)`. (Resolves Issue 1.)
- `IrLambda(IrNode)` (`ir/base.py`) — minimal procedural escape hatch; the closure IS
  the `eval` slot (≈6.7× faster than `IrCallable`; `repr` is codegen via AST source
  extraction). All four exported in `ir/__init__.py`; all pyright/ruff clean.

**Reducer cleaning machinery** (`parsing_2/reduce.py`) — the clean-`nc` "option B":
- Contribution bodies `DROP` / `KEEP_RAW` / `KEEP_REDUCED` (each returns an `IrTuple`:
  0 / 1 / 1 elements — the flat-map model; splice = many).
- `ResolveChildren` is **policy-driven**: synthetic → splice; leaf → `Reducer.literal`;
  rule → `Reducer.noise.resolve(symbol)`. Defaults (`literal=KEEP_RAW`,
  `noise → KEEP_REDUCED`) reproduce a plain reduce, so the generic `test_reduce.py`
  "leaves pass through" contract is untouched; a flavour *opts into* cleaning.
- `Yield` / `YIELD` — subtree source text, skipping non-semantic sub-rule spans
  (`noise.resolve(symbol) is DROP`). The text-rule mirror of building from `nc`;
  subsumes the old `_YIELD`, char-val quote-stripping, and the numeric tokens.
- `Reducer` gains `noise: IrMap` + `literal: IrSelf`; `eval` uses
  `reductions.resolve(symbol)` (honours `IR_DEFAULT`).

**ABNF reduce flavour** (`grammars/abnf_2.py`)
- `ABNF_NOISE` — `IrMap` marking `{wsp, SP, HTAB, c-nl, CR, LF, DQUOTE} → DROP`,
  `IR_DEFAULT → KEEP_REDUCED`.
- `ABNF_REDUCTIONS` — structural rules pure (`IrBuild(IrRule/IrSequence/IrAlternation)`,
  `IrArg(0)` for the four forwards, `IrBuild(IrAst, IrTuple(IrBuild(IrSeq),
  IrPipe(IrArg(0), IrField("name"))))` for `rulelist`); text rules
  `IrBuild(IrRuleRef/IrLiteral, IrTuple(YIELD))`; **`IR_DEFAULT → YIELD`** covers every
  char/terminal rule with no explicit entry.
- `ABNF_REDUCER = Reducer(reductions=ABNF_REDUCTIONS, noise=ABNF_NOISE, literal=DROP)`.
- `repetition` stays `IrLambda(_repetition)`: its `repeat? element` is optional +
  reordered, so it type-selects atom/quant from clean `nc` — doesn't fit `IrBuild`'s
  positional splat.

**Resolved this session**
- **Issue 1** (`IrAst.start`) — `IrPipe(IrArg(0), IrField("name"))`.
- **char-val / DQUOTE delimiter** — `DQUOTE` is non-semantic, so `YIELD` skips the quotes.

**Known wart:** `_REDUCTIONS` (the annotated intermediate tuple in `abnf_2.py`) exists
only because `IrTuple`/`IrMap` are invariant in their value type and the dyad values are
heterogeneous; the tuple annotation widens each to `IrSelf`. Removable only via per-dyad
`IrTuple[IrRuleRef, IrSelf](...)` subscripts (more verbose). `ABNF_NOISE` uses bare
`IrMap` (its values are homogeneous).

### What's left

**A. flavour2 / ABNF2 — finish this cutover (small, mechanical).** Port the 8
`test_abnf_2.py` failures: (1) swap `Reducer(reductions=ABNF_REDUCTIONS)` → `ABNF_REDUCER`
(6 sites); (2) `test_char_val_reduction` — rebuild the quotes as `DQUOTE` sub-trees
(`ParseTree(IrRuleRef("DQUOTE"), IrSeq(IrLiteral('"')))`), keep `== IrLiteral("ab")`;
(3) `test_abnf_reductions_covers_terminal_rules` — terminals now resolve via
`IR_DEFAULT → YIELD`, so assert `.resolve(IrRuleRef("ALPHA")) is YIELD`, not the explicit
`[...]` entry. (Tests → Sonnet subagent per standing workflow.)

**B. "Point 2" — the numeric reductions (Issue 2, partially done).** `num-val`/`repeat`
are no longer `IrCallable` over dirty `nc`; they're `IrLambda` over `YIELD`'s raw subtree
text. **But they still call `ABNF_FLAVOUR.parse_charclass` / `parse_quantifier`** — the
procedural radix/range parse. The deferred work is the **pure radix / multiply-accumulate
algebra** replacing those calls (and retiring the reduce-side `EscapeCodec` use). The
numeric set is open, so a finite `IrMap` can't enumerate it — it needs an `IR_DEFAULT`
arithmetic body. This is the original "drop `parse_quantifier`/`parse_charclass`" back-half.

**C. Auto-layout + non-semantic marking on the grammar (#4 — experiment-proven, NOT
committed).** Experiment confirmed: stripping the decorative between-items `wsp` from
`rule`/`group` round-trips (`reduce(parse(layout-grammar, emit(clean))) == clean`). To
commit: an `insert_layout` normalizer pass (insert optional `wsp` between items of the
syntactic rules), clean `rule`/`group` in `ABNF_GRAMMAR`, and run `insert_layout` before
`normalize` in the parse pipeline (the grammar expands layout before parsing itself).
*Limits:* `altrest`/`catrest` keep explicit `wsp` — the separator sits inside a repeated
unit (boundary-sensitive: between-items layout can't supply the space *before* each `/`)
and `catrest`'s is a **required** separator (`foo bar` vs `foobar`), load-bearing.
*Tie-in:* the non-semantic marking should live on the grammar (a directive / flag on the
`IrRule`s) and feed **both** `ABNF_NOISE` *and* the layout insertion — one source of truth
instead of the hand-maintained `ABNF_NOISE`/`_NON_SEMANTIC` list. That is the real #4.

**D. emit-side `_abnf_charclass` `IrCallable`** (`grammars/abnf.py`) — still an
`IrCallable`; this session was reduce-only. Named in the original goal for removal; a
separate emit-side task.

**E. The larger Lark cutover** (`plans/flavour-2-lark-cutover/flavour_2-handover.md`,
seven phases). The reduce side is one slice; the reduce machinery runs on the already-
hardened `parsing_2` Earley engine (the cutover's target substrate). Still outstanding:
the pure-data `flavour_2` container; tagged grammars; SPPF generalisation (ambiguous
forests); Seam 1 / Seam 2 (the Lark → IR-native parser seams); the **GBNF** flavour ported
to this same reduce shape; and finally **removing the Lark metagrammars** entirely.

---

## Parked issues — DO NOT FORGET

> **Issue 1 is RESOLVED and Issue 2 is partially done — see STATUS above.** Kept here for
> the original framing.

Two items deliberately set aside; the design below proceeds without resolving them.

### Issue 1 — `IrAst.start` derivation (decision pending)

`_rulelist` should set `start` to the first rule's name. The blocker: `IrField`
reads `getattr(n, name)` off the *current focus* `n`, but the first reduced rule
lives on `nc[0]`, not on `n`. Two ways forward:

- **Derive it purely** — add a focus-shift-to-computed-value node `IrPipe(source,
  body)` (eval `source`, rebind its result as the focus, eval `body`). Then
  `start = IrPipe(IrArg(0), IrField("name"))`. `rulelist = 1*rule` ⇒ `nc` never
  empty ⇒ no empty-guard. Costs a **3rd new node** beyond `IrArg`/`IrBuild`.
  `IrPipe` is the general "focus onto something you computed" primitive (`IrAt`
  only does raw-child indices).
- **Drop it from the reduction** — build `IrAst(IrSeq(*nc))` with `start=""` and
  let `compile_grammar`'s existing start-resolution (`@start` directive →
  positional first-rule fallback in `directives.py`) fill it. `start` is already
  a grammar-level concern with a home.

### Issue 2 — `_repeat` → `IrQuantifier` and `_num_val` → `IrCharClass` (parked, "hold that thought")

These map *string → structured value* over an **open** numeric set (any digit
run, any hex range). A finite `IrMap` cannot enumerate it, so the `IR_DEFAULT`
branch would need radix / multiply-accumulate arithmetic expressed in pure
algebra — a separate, bigger design than the structural builders. **Keep their
`IrCallable`s for this pass; design the numeric algebra separately.** This is the
"wiring / drop `parse_quantifier`,`parse_charclass`" back-half the handover
already marks speculative.

### Approved this turn (design to implement)

- **`IrArg(IrInt)`** — positional argument reader, the `nc`-analogue of `IrIndex`.
- **`IrBuild(target, args=IrNone)`** — target constructor. Default `args=IrNone`
  splats the channel (`target(*nc)`); an arg-spec body reshapes it
  (`target(*args.eval(...))`). Absorbs the join→leaf wrap and the `IrAst`
  collection. (See body sketch in the design notes.)

---

## Decisions still standing (from the earlier, now-deleted spec)

These were confirmed in conversation and are *not* the part that went wrong:

- **Two tables**, mirrored: emit `IrTypeMap[type → body]`, reduce `IrMap[IrRuleRef → body]`.
- **The canonical tag IS the rule name** (`IrRuleRef`). No new slot on `IrRule`, no side table.
- **A flavour is pure `IrSelf` data**; the emitter and reducer are generic engines.
- **All seven cutover phases in scope**, back half speculative.

## Decided this session

- **Clean `nc` upstream (option "B").** Today a reduction sees a *dirty* `nc`: for
  `rule = rulename "=" alternation c-nl` it gets `(rulename, "=", alternation, c-nl)`
  and copes by type-selecting (`next(c for c in nc if isinstance(c, IrRuleRef))`). The
  cleaning — dropping **non-semantic rules** and **inline-literal terminals** — moves
  into the reducer's child resolution, so a body receives the *conceptual* children in
  order. This is what removes the need for any per-body filtering.
- **The reduce table already maps rule name → body.** The job is only to make the
  bodies pure `IrSelf`. There is no new "assembler" abstraction; assembly is `rebuild`.

---

## How the machinery actually works (so the next session doesn't re-read it)

**Reducer** (`parsing_2/reduce.py`): `class Reducer(IrDispatch)`. It *is* a dispatch but
ignores most of it — it hand-rolls `reduce(tree)` and `_reduced_children(tree)` with a
**mutable list**, recurses by calling `self.reduce(child)` itself, splices synthetic
rules inline, and finally does `body.eval(self, tree, reduced)`. So the body gets the
already-flattened children on **`nc`** (the argument channel) and never drives its own
child recursion. Dispatch key is `tree.symbol` (a *value*, `IrRuleRef`) via the
`IrMap` `reductions` — correct, because every node is the same type (`ParseTree`), and
it's why this can't just become a plain `IrTransformer`.

**ParseTree** (`parsing_2/forest.py`): `IrNamedTuple[IrRuleRef, IrSeq]` —
`symbol: IrRuleRef` (scalar payload, the table key) + `kids: IrSeq`
(`_child_attrs = ("kids",)`). It walks and rebuilds like any IR node.

**`rebuild`** (`ir/base.py`): `IrNamedTuple.rebuild` splices children into the
`_child_attrs` slots in order and **preserves scalar payload**; `IrTuple.rebuild` is
variadic `type(self)(*children)`. `IrTransformer`'s default body `IrRebuild` is exactly
"dispatch each child via `d`, then `n.rebuild(results)`".

**Action vocabulary already available** (`ir/action.py`): `IrField` (read+wrap a typed
attr), `IrChild`/`IrIndex`/`IrChildren` (dispatched children of `n`), `IrArgs` (the
whole `nc`), `IrConcat`/`IrJoin` (string build), `IrCond`/`IrIsA`/`IrCompare`
(branch/test), `IrApply`/`IrAt` (delegation/focus-shift). Value-keyed dispatch with a
default is `IrMap` + `IR_DEFAULT`; the emit side already uses this for the open
quantifier set — see `ABNF_PREFIX_QUANTIFIER` (`grammars/abnf.py:139`), an
`IrMap(IrQuantifier(1,1) → IrLiteral(""), …, IR_DEFAULT → nested IrCond)`. Mirror that
shape for the numeric reduce bodies.

**Defaults that matter:** `IrQuantifier()` is `(1,1)`; `IrItem.quantifier` defaults to
`IrQuantifier()`. So an absent `repeat` needs no fill — the slot's own default covers
it. `IrRuleRef` IS-A `IrStr`, so it lands cleanly in an `IrStr` `name` slot.

---

## Per-reduction breakdown (the 13 structural reductions in `ABNF_REDUCTIONS`)

With clean `nc`, classify each by what its pure-`IrSelf` body becomes:

| Reduction | Today | Becomes |
|---|---|---|
| `_concatenation` → `IrSequence` | collect `IrItem` | reconstruct from children (`rebuild`, variadic) |
| `_alternation` → `IrAlternation` | collect `IrSequence` | `rebuild`, variadic |
| `_repetition` → `IrItem` | pick atom + quant | `rebuild` into `(atom, quantifier)`; quant defaults |
| `_rule_reduce` → `IrRule` | pick ref + alt | `rebuild` into `(name, body)` |
| `_rulelist` → `IrAst` | collect rules + start | `rebuild` rules (variadic) + derive `start` (first rule name) |
| `_element`/`_group`/`_altrest`/`_catrest` | pick one child | forward the single cleaned child |
| `_rulename` → `IrRuleRef` | join chars | `IrConcat` of text → wrap as `IrRuleRef` |
| `_char_val` → `IrLiteral` | join, strip quotes | `IrConcat` → wrap as `IrLiteral` (delimiters dropped by cleaning) |
| `_repeat` → `IrQuantifier` | `parse_quantifier` | value-keyed `IrMap` + `IR_DEFAULT` (numeric) |
| `_num_val` → `IrCharClass` | `parse_charclass` | value-keyed `IrMap` + `IR_DEFAULT` (numeric) |

So: ~5 are straight `rebuild`, 4 are "forward single child", 2 are join→leaf, 2 are the
numeric `IrMap`s. The type each body produces is owned by the body — exactly as an emit
body owns its output. No tag map, no construct node.

---

## The one genuinely-open mechanism

`rebuild` reconstructs `type(self)` — but in reduce, `n` is a `ParseTree`, so
`n.rebuild(...)` yields a `ParseTree`, not the target IR type. **Sourcing `rebuild`'s
placement logic from a target type (rather than `type(self)`) is the thing to settle
next, against the actual code** — likely by factoring the placement out of
`IrNamedTuple.rebuild`/`IrTuple.rebuild` so a reduce body can call it with the type it
produces. Settle it concretely; do not design it in the abstract (the deleted spec did,
and invented `IrPick`/`IrMake`/a tag map — all rejected).

## Other open items

- **Cleaning rule for delimiter *rules*.** Inline literals (`"="`, `"("`) are obviously
  droppable; non-semantic rules are flagged. But ABNF `DQUOTE` is a *rule*, so
  `char-val = DQUOTE *vchar-nq DQUOTE` still arrives delimited unless `DQUOTE` is marked
  non-semantic or a residual slice survives. Decide which.
- **Wiring.** Once bodies are pure `IrSelf`, the `parse_quantifier`/`parse_charclass`
  calls in `_repeat`/`_num_val` and the `EscapeCodec` go away (the broader cutover goal).
  Re-close the ABNF self-hosting fixpoint after the change.

## Hard-won don'ts (do not resurrect)

- No `IrPick`/`IrMake` with mode flags or list accumulators.
- No separate "generic assembler" node — it's `rebuild`.
- No `rule → type` tag map + generic default — the body owns its target type.
- `IrInt`/`IrStr` ARE their primitives — never `IrInt(int(x))` or `chr(int(codepoint))`.
