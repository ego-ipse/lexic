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

## Parked issues — DO NOT FORGET

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
