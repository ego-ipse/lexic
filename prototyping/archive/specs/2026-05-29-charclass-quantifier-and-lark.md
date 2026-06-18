# Charclass, Quantifier & the Lark flavour — working notes

**Status:** working notes, *not a spec.* Captures decisions reached in discussion
on 2026-05-29 plus the path toward a future LarkFlavour slice. No task here is
authorized for execution; each in-scope item still needs its own spec (and, where
noted, an amendment to the canonical-nine rule).

**Relationship to prior specs:** this builds on `2026-05-14` (closure & dispatch
unification) and `2026-05-17` (Slice B deferred work). Items those specs deferred
remain deferred unless explicitly re-opened below — and re-opening means *a new
spec*, not this note.

---

## 1. The core diagnosis

Two IR nodes are denatured — stored as a primitive while their real structure
lives in the procedural code that re-derives it on every emit:

- **`IrCharClass`** holds `value: str` — one flavour's *surface syntax*, frozen as
  a blob. GBNF emits it verbatim (accidentally lossless); ABNF must re-parse the
  blob into segments, hex-encode, re-join. The structure ABNF needs was discarded
  at parse time and is rebuilt every emit.
- **`IrQuantifier`** holds `(min, max)` with `max: int | None`. Emit re-classifies
  the pair back into surface forms (`?`/`*`/`+`/`{n}`/…) — work the parser already
  did and threw away.

Same error, twice. The fix is the same shape both times: **parse classifies once
(its job); emit dispatches on the preserved structure (the dispatcher's job).**

## 2. Decisions

### 2.1 The make-it-a-type vs keep-it-data rule

The distinguishing test for whether a distinction belongs in the *type system* or
stays *data*:

> Promote to a node **type** when the distinction is flavour-**neutral semantics**.
> Keep it as **data** when the distinction is one flavour's **surface sugar**.

Consequences:

- **CharClass → composite, by type.** `Char` / `Range` / `NamedSet` are
  flavour-neutral semantic kinds (a range is not a char in *any* notation). So a
  char class is structural: optional `IrNot` wrapping an `IrAlternation` of typed
  members. Emit becomes `IrJoin` over members, each member dispatched by its type
  through the existing action table. `_split_charclass_segments` and the hex-range
  walker **evaporate** — they reconstruct structure that is now real nodes.
- **Quantifier → stays data (two ints).** `+` vs `1*` are two flavours' renderings
  of the same fact `(1, ∞)`. Lifting `IrPlus`/`IrStar`/… into the type system would
  bake GBNF's surface vocabulary into the shared IR and force every *other* flavour
  to un-categorize on transpile. Rejected. The ground truth is the bounds.

### 2.2 Quantifier representation

- `max: int | None` is replaced. **Arity encodes unboundedness** (mirrors the
  `IrNone`-instead-of-`None` discipline already used elsewhere): a quantifier is a
  tuple of ints, max arity 2.
  - `(0,)` → `*`   (zero or more)
  - `(1,)` → `+`   (one or more)
  - `(0,1)` → `?`
  - `(n,)` → `{n,}` (at least n)
  - `(n,m)` → `{n,m}`
  - `(n,n)` → `{n}` (exactly)
- **Convention to pin:** `(n,)` means *at least n* (open). "Exactly n" is `(n,n)`.
  Without this, `(3,)` is ambiguous.
- **`IrInt`** is added as a value-type sibling of `IrStr` (`class IrInt(IrType,
  int)`, `_bound = int`). Justification is *not* symmetry — it's that `IrInt` is the
  honest operand type for the comparison op below. `IrStr` carries string content
  for `IrConcat`/`IrField`; `IrInt` carries numeric content for comparisons/guards.
  Comparing raw Python ints smuggled through `getattr` would re-introduce the
  stringly escape we are removing.
- Sketch (illustrative, not final): `IrQuantifier(IrTuple[IrInt])`, arity ≤ 2, with
  `min`/`max` accessors over elements `[0]`/`[1]`.

### 2.3 The missing primitive — value-aware branching

The thing that made every prior attempt fall one short. Today `IrCond` branches on
the **truthiness of `getattr(n, field)`** — it can test "is this field zero/empty"
and nothing else. It cannot ask `min == max`, `min > max`, or "is max absent." So:

- Predicate **properties on the node** (`is_star`, `is_exact`, …) are rejected: they
  are branching logic smuggled onto the data, read by a stringly `getattr`, justified
  by no node protocol. The node would accrete one boolean per surface distinction of
  *every* flavour.
- A **stringly DSL** (`IrCond("min>max", …)`) is rejected: unsafe, unwalkable, a
  turing-tarpit.

**Decision — generalize `IrCond`, add `IrCompare` (Shape A).** Replace `IrCond`'s
`field: str` with `test: IrNode` (any op whose `eval` is truthy/falsy). Add a dumb,
composable predicate op:

```
IrCompare(left: IrNode, op: Cmp, right: IrNode)   # Cmp = closed enum EQ|LT|GT
```

Rationale over folding compare-and-branch into one node (Shape B):

1. Separation of concerns — `IrCond` branches, `IrCompare` predicates. Folding them
   repeats the original `getattr`-welded mistake.
2. Today's `IrCond(field=...)` is *already* a degenerate Shape-A (test hardwired to
   one field's truthiness). Generalizing is the implied form, not a new concept.
3. Composition is free: `IrNot(test)`, and later `IrAnd`/`IrOr`, slot into the same
   hole. `?` = `IrAnd(IrCompare(min,EQ,0), IrCompare(max,EQ,1))`.
4. The construction **guard** reuses the predicate verbatim:
   `IrCompare(IrField("min"), GT, IrField("max")) → IrRaise / IrPass`.
5. Back-compat: `IrCond` keeps accepting a bare `str` (auto-wrapped as field-read
   truthiness), so existing call sites do not churn.

Open sub-decisions (fix before any spec):
- **(a)** `IrCompare` compares operands via their bound builtins (`IrInt` is-a `int`,
  so `left.eval() < right.eval()` works with no unwrapping — same way `IrStr`'s
  str-ness makes `.join` work). Leaning yes.
- **(b)** Scalar `Cmp` + `IrAnd` to start; promote a tuple-equality form only if the
  conjunction nesting proves ugly in practice. Let the pain justify it.

> ⚠️ **Canonical-nine collision.** `IrInt`, `IrCompare`, and any `IrAnd`/`IrOr`
> exceed the canonical nine ops (`IrReturn, IrChild, IrChildren, IrConcat, IrText,
> IrField, IrCond, IrJoin, IrCallable`) frozen by the 2026-05-18 spec and re-asserted
> in 2026-05-17 §Anti-creep rule 5. Generalizing `IrCond` likewise changes a canonical
> op's shape. **This is exactly the "IrOp algebra completion" that 2026-05-17 §6
> deferred.** Pursuing it = a spec amendment opening that deferred slice, not a quiet
> edit. Until then, the `IrCallable` escape hatch remains the sanctioned tool.

### 2.4 Validation as a concern, not necessarily as algebra

The `min ≤ max` invariant is real but is *not emit's business*. Build `IrCompare`
**for emit** (sugar selection genuinely needs it); the guard then reuses it for free.
Do not build the comparison op speculatively just to make the guard algebraic — if
emit didn't need it, a plain construction-time check would suffice.

## 3. Proposed sequence (concept-sized, each step left *coherent*, not merely green)

Not authorized; ordering only. "Coherent" = no denatured half-states / adapters
left bridging two truths.

1. **`IrInt`** — value-type sibling of `IrStr`. Ships alone, no consumer. *(Algebra
   expansion — needs the amendment of §2.3.)*
2. **Generalize `IrCond` + add `IrCompare`** — value-aware branching; back-compat
   coercion for existing `IrCond(str)` sites. *(Algebra expansion — amendment.)*
3. **Quantifier honest end-to-end** (the rehearsal — simple, mistakes obvious):
   tuple-of-`IrInt` repr; guard via `IrCompare`; flavour emit selects sugar from
   bounds; delete `_gbnf_quantifier`, `_abnf_quantifier`, `_abnf_format_quantifier`,
   `GBNF_QUANT_SYMBOLS`; re-prove the 7 ground-truth round-trips **and** add brace
   cases (`{2,5}`) that currently parse-but-fail-to-emit (latent GBNF bug).
4. **CharClass honest end-to-end** (the uncomfortable one — round-trip must be
   *re-earned*, member order preserved, no normalization): `IrNot?` over
   `IrAlternation` of `Char`/`Range`/`NamedSet`; structured `parse_charclass`; emit
   = `IrJoin` over members dispatched by type; delete the segment/hex walkers.
5. **Closure check** — confirm the only surviving `IrCallable` in either flavour is
   literal-escaping (a codec call). If so, the tables are codegen-able.

Dependency logic: 1→2 (`IrCompare` operates on `IrInt`); 2→3,4 (both need
value-aware sugar selection); 3 before 4 deliberately (quantifier rehearses the
parse-classifies / emit-dispatches pattern before charclass's round-trip risk).

## 4. The Lark flavour (forward look — still deferred)

Per 2026-05-17 §1, **LarkFlavour-as-peer remains deferred** and is a future
"Slice X — LarkFlavour as full peer" that *consumes* the substrate above. Nothing
here authorizes starting it. What the work above changes about its eventual shape:

- LarkFlavour becomes a third action **table** (mirroring `gbnf/` and `abnf/`
  layout: `flavour.py`, `meta_grammar`, `escapes.py`) rather than a third pile of
  helpers — *if and only if* steps 3–4 land, because only structured CharClass /
  Quantifier let the three flavours share node shapes and differ only in tables.
- The **regex-terminal-vs-rule-token "sharp edge"** (2026-05-14; restated
  2026-05-17 §1) — rendering a quantifier as `/pattern/` with `{n,m}` *embedded in
  the regex* when bounds aren't expressible as `?`/`*`/`+` — is still the trickiest
  renderer and **still deferred**. Structured members + value-aware branching make
  it tractable, not solved.
- **Parser-class commitment is unresolved** and is the decision that determines
  whether the user-facing `.lark` path is clean or a fork: Lark's internal codegen
  use assumes LALR; real-world `.lark` files assume Earley (ambiguity, broader
  grammar class). Committing to LALR quietly defines a Lark *subset* (needs saying,
  like the ABNF-subset framing); committing to Earley diverges internal vs user
  parser config even while sharing one Flavour. **Open; belongs in the LarkFlavour
  spec.**
- **`~n` / `~n..m` round-trip fidelity** — Lark's richer quantifier vocabulary maps
  cleanly *into* `(min, max)`, but a Lark `~3` (exact) round-tripping *through* a
  flavour with no exact-count syntax is the cross-flavour fidelity question the
  property tests will surface. Tracked, not designed.
- **Native Earley-over-`IrSelf`** is *not on any deferred list* — it is further out
  than LarkFlavour. It is only reachable after the meta-grammar itself becomes IR
  (see §5). Treat as aspiration, not roadmap, until there is concrete pressure.

## 5. The longer arc (vision — explicitly not scheduled)

The same denaturing exists one level up: the meta-grammar collapses `repeat` /
`num-val` into Lark **terminal blobs**, then `parse_quantifier` / `parse_charclass`
rebuild the structure procedurally. The end state is the meta-grammar parsing to
structure directly — at which point those parse helpers are *deleted, not rewritten*
— and ultimately a flavour describing itself in lexic's own IR (Lark demoted to a
parsing engine). This is the bootstrap that would make the Earley question an engine
choice behind an IR-shaped seam rather than an architecture commitment.

This arc subsumes the already-deferred `PyFlavourCodegenRenderer` and `IrFlavour`
(2026-05-17 §6). It is recorded as direction only; **no step here is scheduled.**

---

## 6. Deferred-work ledger (carried from 2026-05-14 and 2026-05-17)

Restated so this note references one place. **All remain deferred** unless a row
says otherwise.

| # | Item | Source | Status after these notes |
|---|------|--------|--------------------------|
| 1 | LarkFlavour as full peer | 14 §promotion / 17 §1 | **Deferred.** §4 above refines its eventual shape; does not start it. |
| 2 | Regex-terminal-vs-rule-token "sharp edge" | 14 / 17 §1 | **Deferred.** Made tractable by §2–3, not solved. |
| 3 | Indexed (`<[N]>`) & negation (`!<name>`) token refs | 14 §out-of-scope / 17 §2 | **Deferred.** Untouched. |
| 4 | `Flavour.pre_parse_check` hook | 17 §2 | **Deferred.** No slot carved. |
| 5 | Wiring `validate_portable` / `PORTABLE_FEATURES` | 14 §out-of-scope / 17 §5 | **Deferred.** `regex_portable.py` stays as-is. |
| 6 | Codegen-pass migration to action tables | 17 §3 | **Deferred.** Untouched. |
| 7 | Pure-IrOp form for `_HoistTransformer` / `_RuleRefFinder` (replace `IrCallable` bodies) | 17 §4 | **Deferred.** Escape hatch stays. |
| 8 | **IrOp algebra completion** (new ops beyond the nine; new quantifier extension types `IrPredicate`/`IrEnum`) | 14 §out-of-scope / 17 §4,§6, rule 5 | **Re-opened in principle** by §2.3 (`IrInt`/`IrCompare`/`IrCond` generalization). **Requires a spec amendment to proceed** — not authorized by this note. |
| 9 | `PyFlavourCodegenRenderer` | 17 §6 | **Deferred.** §5 records it as the arc's payoff; §3 step 5 only *checks* codegen-ability, does not build the renderer. |
| 10 | `IrFlavour` (IR-self-notation Flavour) | 17 §6 | **Deferred.** §5 vision only. |
| 11 | Eliminate hoist pass + codegen for inline groups | 17 §appendix | **Deferred.** Untouched. |
| 12 | Wiki / CLAUDE.md docs for any deferred feature | 17 §8, rule 6 | **Deferred.** This note is working notes, not wiki/spec content. |
| 13 | Delete `ir/helpers.py` (zero-caller dead code) | 14 / 17 §appendix | **Deferred** (may flip to in-scope opportunistically per 17; no design risk). |

**Net new vs prior specs:** the only genuinely new proposal is the §2.3 algebra
expansion (`IrInt`, `IrCompare`, generalized `IrCond`), which is ledger item #8
moving from "deferred" toward "needs a spec." Everything else either refines the
shape of an already-deferred item (Lark, sharp edge) or stays put.
