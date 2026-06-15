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
- **Rendering ownership + the argument channel.** An action renders ONLY its
  own node's surface tokens — `IrNot` knows its mark (`^`), never brackets;
  brackets are strictly the `IrCharClass` action's. Cross-node marks travel
  as **arguments**: `nc` is formally the argument channel (precedent: `IrOp`
  operands, fold-mode `IrCallable`), and the *receiving* action places
  received marks wherever its syntax dictates — the IR is semantic, surface
  position is flavour data (a flavour could render negation postfix:
  `[foo]!`). Consequence: the hybrid eager-`nc` branches of
  `IrChildren`/`IrChild`/`IrIndex` are removed (children-readers read
  children; `IrArgs` reads arguments) — one channel cannot mean both once a
  node has real children.
- **Guards are type-maps, not cond-chains.** Operand validation is an
  `IrTypeMap` evaluated at the operand (`IrAt(0, IrTypeMap(...))`) with
  `IrSelf → IrRaise` as the MRO-terminal catch-all — O(1) namespace hits,
  no `IrIsSelf` node needed.
- **`IrAt` over `IrSlice` / residual `IrCallable`.** "At the operand" is a
  *structural* notion, not a textual one (no slicing brackets off rendered
  strings). `IrAt` rebinds the dispatch focus to a raw child — the gap V1
  already recorded ("`IrNot` is tuple-shaped; neither `IrIsA` nor `IrChild`
  can address its raw operand").

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

## 2. Argument channel + delegation primitives (before the charclass restructure)

Three small nodes in `action.py`, plus the channel formalization. Wire the
GBNF `IrNot`/`IrCharClass` actions immediately as the live consumer (kills
`_gbnf_not` ⇒ zero `IrCallable`s in the GBNF table, one step early):

- **`IrAt(selector, body)`** — the binder: evaluate `body` with `n` rebound
  to the **raw** child `n.children()[selector]` and fresh empty `nc`.
  Selector is index-only int payload (negatives allowed, mirroring
  `IrIndex`). The algebra's first focus-shift — document prominently.
- **`IrArgs()`** — fieldless args-reader: evaluates to the `nc` tuple. The
  argument analogue of `IrChildren`; a flavour places
  `IrJoin(parts=IrArgs())` wherever received marks belong in its syntax.
- **`IrApply(args)`** — delegation: evaluate `args` against the current
  context, then re-dispatch the current focus `n` through `d` with the
  results as `nc`. No selector — compose with `IrAt` to aim it.
- **De-hybridize the child readers**: `IrChildren`/`IrChild`/`IrIndex` lose
  their eager-`nc` branches (dead code — the dispatcher never pre-walks).
  `IrConcat`/`IrJoin` keep forwarding `nc` to parts — that is how `IrArgs`
  receives arguments deep inside a body.

GBNF wiring (works against today's str-leaf `IrCharClass`; carries over
unchanged to step 3's structured one):

```python
IrCharClass → IrConcat("[", IrJoin(parts=IrArgs()), IrThis(), "]")
IrNot       → IrAt(0, IrTypeMap(
                  IrAction(IrCharClass, IrApply(IrTuple(IrLiteral("^")))),
                  IrAction(IrSelf,      IrRaise(...)),   # MRO catch-all guard
              ))
```

## 3. IrCharClass restructure

- Tier change: str-leaf → variadic interior (`IrSeq` of `IrRange` | `IrStr`
  run) + `IrAtom`.
- `meta_parser._build_charclass`: split the `(pattern, negated)` result into
  `IrRange`s (explicit `x-y` segments only) and bare `IrStr` runs
  (consecutive single chars merged into one leaf), escape-aware — reuse the
  `_read_char` walk from `charclass.py`. Build `IrCharClass(*elements)`,
  wrap in `IrNot` when negated. `parse_charclass` survives this step; it
  dies in step 4.
- GBNF actions — end state zero `IrCallable`s (the `IrNot`/mark machinery is
  already in place from step 2; only the interior reader changes):
  ```python
  INTERIOR = IrJoin(parts=IrChildren())       # children-only reader
  MARKS    = IrJoin(parts=IrArgs())           # argument-channel reader
  IrRange     → IrConcat(<lo>, "-", <hi>)     # no degenerate cond; [a-a] round-trips
  IrStr run   → escape-aware emit             # singles inside the class
  IrCharClass → IrConcat("[", MARKS, INTERIOR, "]")
  IrNot       → unchanged from step 2 (IrAt + IrTypeMap guard + IrApply("^"))
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
