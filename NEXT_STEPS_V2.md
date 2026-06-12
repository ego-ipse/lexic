# Next steps V2 — IrRange / class-expression rework (branch `more_nodes`)

Supersedes `NEXT_STEPS.md` (V1). State as of 2026-06-12: 693 tests green,
pyright/ruff/pylint clean. V1 steps 1–3 are redesigned around two decisions
from review: the **IrRange unification** (quantifiers and char ranges are one
shape) and **negation-outside** (`IrNot` wraps the class; it never sits in the
interior). V1's ABNF port and housekeeping carry over.

## Decisions (settled, do not relitigate)

Carried from V1 unchanged:

- **No `IrNegCharClass`.** `IrNot` is *generic* negation; negation never lives
  in a node type.
- Lark consumers (`derive`, `naming`, `lark_builder`, `aliases`, `generate`,
  `charclass.py`, `model_emitter`) are condemned — adapt them mechanically to
  keep the suite green, design nothing around them.
- Action leaves are value-leaves, not records: the node IS its payload.

New / revised:

- **REVERSED from V1: negation sits OUTSIDE the class.**
  `[^a-z]` → `IrNot(IrCharClass(...))`, never `IrCharClass(IrNot(...))`.
  V1 read the surface position of `^` (inside the brackets) as structure. It
  is not: `^` is the complement operator's surface syntax, the same way `(?!`
  puts negation inside the lookahead's parens. The decider: inside-nesting
  cannot represent class intersection — `[a-z1-9&&[^b2]]` nests a negated
  class inside a positive one, and an interior-bound negation has no slot for
  that. Operator-shaped negation composes for free.
- **`IrRange(lo, hi)`** — one node for "inclusive range". Quantifier bounds
  are int ranges; char ranges are single-char str ranges (a char range IS an
  int range via ord/chr). The degenerate convention `n` → `(n, n)` applies to
  the **quantifier side only** (`{3}`). Single chars in a class interior are
  NOT degenerate ranges: a run of consecutive single chars is one bare
  `IrStr` leaf (`[abc]` → `IrCharClass(IrStr("abc"))`) — fewer nodes, and
  `IrRange` then only ever arises from an explicit `x-y` in source, so
  emission needs no degenerate cond and `[a-a]` round-trips verbatim.
  `lo`/`hi` are **scalar payload**
  (`_child_attrs = ()`) — walkers never descend into bounds; actions read
  them via `IrField("lo", ...)`. The open upper bound is **`IrNone`**, which
  kills the last `int | None` union in the IR.
- **`IrQuantifier(IrRange)` stays a distinct subclass** (int-flavoured).
  Type-keyed action tables stay precise: concrete-first MRO means the
  `IrQuantifier` action (the `GBNF_QUANTIFIERS` data map) wins for
  quantifiers while a base `IrRange` action serves char ranges.
- **`IrCharClass` is the variadic union** — `IrSeq[IrRange]` + `IrAtom`; the
  node IS its ranges tuple. NOT monadic, NOT a str-leaf.
- **Predicate reading.** A class is a membership predicate: union =
  `IrCharClass`, intersection = `IrAnd`, complement = `IrNot`. `IrOpNode`
  IS-A `IrAtom`, so class expressions already compose as atoms with zero new
  marker types, and the boolean `_OPS` folds (`&`/`|`/`!`) are literally
  correct for membership. Complement needs a universe only at enumeration
  time (`generate`), never in the IR.
- **`IrAt` over `IrSlice` / residual `IrCallable`.** "Interior of a class" is
  a *structural* notion (the join of its ranges), not a textual one (slicing
  brackets off a rendered child). `IrAt` is the binder primitive that lets an
  action body evaluate against a raw operand — the gap V1 already recorded
  ("`IrNot` is tuple-shaped; neither `IrIsA` nor `IrChild` can address its
  raw operand").

## Target tree shapes

```
[a-z]            → IrCharClass(IrRange("a","z"))
[abc]            → IrCharClass(IrStr("abc"))     # run of singles = one str leaf
[a-z_0-9]        → IrCharClass(IrRange("a","z"), IrStr("_"), IrRange("0","9"))
[^a-z]           → IrNot(IrCharClass(IrRange("a","z")))
?                → IrQuantifier(0, 1)            # IS-A IrRange
*                → IrQuantifier(0, IrNone)       # open bound = IrNone, not None
[a-z1-9&&[^b2]]  → IrAnd(IrCharClass(IrRange("a","z"), IrRange("1","9")),
                         IrNot(IrCharClass(IrStr("b2"))))
                   # future-proofing target; intersection is not parsed yet
```

## 1. IrRange + IrQuantifier retier

- `IrRange` record in `nodes.py`: `IrNamedTuple`, fields `lo`/`hi`,
  `_child_attrs = ()`. `IrQuantifier` subclasses it; `min`/`max` rename to
  `lo`/`hi`; `max=None` → `IrNone` everywhere (`GBNF_QUANTIFIERS` keys,
  `parse_quantifier`, `derive`, `lark_builder`, `aliases`,
  `utils/quantifiers.py` — mechanical).
- Pin with a test: records are tuple-equal across types
  (`IrQuantifier(1, 1) == IrRange(1, 1)`). Acceptable — int vs str payload
  keeps the quantifier and char-range domains disjoint — but it must be a
  *recorded* fact, not a surprise.

## 2. IrAt primitive (standalone, before the charclass restructure)

`IrAt(selector, body)` in `action.py`: resolve the **raw** (undispatched)
child `n.children()[selector]`, then evaluate `body` with `n` rebound to it
and a fresh empty `nc`:

```python
def eval(self, d, n, nc, /):
    return self.body.eval(d, n.children()[self.selector], ())
```

Design items to settle while writing it:

- Selector is index-only int payload (matches `IrIndex`; negatives allowed).
  Named/chained selectors only when a consumer demands them.
- It is the algebra's **first binder** — every other node evaluates against
  the `n` it was dispatched with. Document the focus-shift prominently.
- Guard story: `IrNot`'s GBNF action must raise on non-class operands, which
  needs a type test of the *rebound* node itself. Either extend `IrIsA` with
  a self form or add a small `IrIsSelf(target)` leaf — decide here, with
  tests.

## 3. IrCharClass restructure

- Tier change: str-leaf → variadic interior (`IrSeq` of `IrRange` | `IrStr`
  run) + `IrAtom`.
- `meta_parser._build_charclass`: split the `(pattern, negated)` result into
  `IrRange`s (explicit `x-y` segments only) and bare `IrStr` runs
  (consecutive single chars merged into one leaf), escape-aware — reuse the
  `_read_char` walk from `charclass.py`. Build `IrCharClass(*elements)`,
  wrap in `IrNot` when negated. `parse_charclass` survives this step; it
  dies in step 4.
- GBNF actions — end state zero `IrCallable`s:
  ```python
  INTERIOR = IrJoin(parts=IrChildren())
  IrRange     → IrConcat(<lo>, "-", <hi>)     # no degenerate cond; [a-a] round-trips
  IrStr run   → escape-aware emit             # singles inside the class
  IrCharClass → IrConcat("[",  INTERIOR, "]")
  IrNot       → IrConcat("[^", IrAt(0, INTERIOR), "]")   # + guard; kills _gbnf_not
  ```
  NOTE: class-interior escaping (`]`, `\`, `^`, `-`) is not literal escaping —
  the range/run actions need an escape seam beside `IrEscape()`.
  NOTE: keying the run action on bare `IrStr` is a wide MRO net (`IrChild`,
  `IrOp` IS-A `IrStr`; concrete grammar leaves are shielded by their own
  actions). A thin `IrChars(IrStr)` subclass would make the table key
  precise — decide at implementation.
- ABNF actions: `IrRange` → `%xNN-MM`; `IrStr` run → per-char `%xNN` (hex
  formatting needs a fold-mode `IrCallable` — acceptable residue, or grow a
  formatting leaf later); `IrCharClass` → elements joined `" / "`,
  parenthesised when >1 (the length test is a second small residue);
  `IrNot` → `IrRaise`. Kills `_abnf_charclass`, `_split_charclass_segments`,
  `_hex_range_segment`.
- **Flattening helper** (one, canonical): `(pattern: str, negated: bool)`
  view over `IrCharClass | IrNot(IrCharClass)` — `IrRange("a","z")` →
  `"a-z"`, `IrStr` runs verbatim. Condemned consumers (`derive`, `naming`'s
  `CHARCLASS_NAMES` keys, `lark_builder`, `aliases`, `model_emitter`,
  `generate`) adapt through it only — no per-site surgery.
  `parse_charclass_chars` reimplements over the interior elements: a run
  iterates its chars; a range chains `chr(c) for c in range(ord(lo), ord(hi)+1)`.

## 4. Meta-grammar productions (V1 Q3a + Q3b, merged)

`parse_quantifier` and `parse_charclass` die together — the IrRange
unification makes them the same move. Replace the opaque `QUANTIFIER` /
`CHARCLASS` / `HEXCC` regex tokens with productions carrying lo/hi tokens
(`"[" "^"? interior "]"`, `lo "-" hi`, `lo "," hi`, ABNF `lo "*" hi`) feeding
one generic IrRange builder in `MetaGrammarParser`; the flavour contributes
only grammar text + a symbol `IrMap` (`GBNF_QUANTIFIERS` exists; ABNF needs
its prefix equivalent). Negation becomes grammar structure feeding
`IrNot(IrCharClass(...))` directly. ABNF `%xNN-MM` hex→char stays *decoding* —
one shared decoder beside `EscapeCodec`.

## 5. ABNF port (V1 step 4, unchanged)

After 1–4: `_abnf_encode_literal` → the GBNF `IrEscape` body; `_abnf_item` →
GBNF's item body with cond/quantifier order flipped (prefix); `_abnf_ast` →
identical to GBNF's. Then extend ABNF coverage (fuller quantifier forms,
literal forms) on the structured base. End state: a flavour is meta-grammar
text + action table + escape/symbol data, no methods.

## Deferred — range coalescing (opt-in, undecided)

A possible later pass: coalescing a contiguous `IrStr` run into a range
(`IrStr("abc")` → `IrRange("a","c")`). Changes emitted grammar text
(`[abc]` → `[a-c]`) — same language, different text — so it collides with
round-trip fidelity and must be a strictly opt-in compile option, shaped as
an `IrTransformer` normalization table. Decide when there is a consumer.
(The lossless half of the original idea — singles as str leaves instead of
degenerate ranges — was promoted into the canonical parse shape; see
§Decisions and step 3.)

## Housekeeping

- CLAUDE.md and `.wiki/` are stale and getting staler: the `ir/base.py`
  spine (`IrNamedTuple`/`IrCachingTuple`/`Field`), `operators.py`
  (`IrOpNode`/`MonadicOp`/`IrNot`/`IrEq`/`IrAnd`), `mapping.py`
  (`IrMap`/`IrTypeMap`), fold-mode `IrCallable`,
  `IrIsA`/`IrEscape`/`IrIndex`/`IrChild` reshape, declarative `GBNF_ACTIONS`
  — none of it is documented. Refresh once the restructure settles; add
  `IrRange`/`IrAt` and the negation-outside reversal in the same pass.
- Delete `NEXT_STEPS.md` (V1) once this document is accepted.
- `generated/` files churn in the working tree; deliberately uncommitted.
- Workflow: src by hand/Fable/sOpus, tests always via Sonnet subagents.
