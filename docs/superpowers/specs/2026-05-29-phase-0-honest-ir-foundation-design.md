# Phase 0 — honest-IR foundation (algebra, quantifier, charclass)

**Status:** implementation design. Covers Phase 0 of the Lark full-coverage
program (`2026-05-29-lark-full-coverage-umbrella-design.md`). Specs **0a–0c** in
detail; **0d** (`IrNonSemantic`) is a tracked forward-pointer that becomes its
own spec. This document **opens** the canonical-op slice deferred by the
`2026-05-17`/`-18` specs (ledger #8) — see §0a.4.

**Relationship to prior notes.** Supersedes the working notes
`2026-05-29-charclass-quantifier-and-lark.md` §2–§3 with concrete decisions
reached 2026-05-29. Two corrections to those notes, both code-verified:
- `IrCond` has **zero callers** in `src/`, so its generalization needs **no**
  back-compat shim.
- `IrText` **does not exist** — it was deleted in the Slice-B step-1 revision and
  `IrLiteral` absorbed the string-constant role. The frozen "canonical nine" list
  in prior specs is misnamed.

## Internal dependency order

```
0a  algebra expansion + canonical-op amendment   (no consumer; governance-gated)
 ├─► 0b  honest quantifier            (consumes IrInt/IrCompare/IrAnd/IrCond, widened IrField)
 └─► 0c  structured charclass         (consumes the same)
0d  IrNonSemantic                     (independent; forward-pointer only)
```

0b and 0c are independent of each other. 0d is independent of all.

---

## The Cure pattern (governs 0b and 0c)

Both `IrQuantifier` and `IrCharClass` are **denatured**: stored as a primitive
(`min/max` ints, a `value:str` blob) while their real structure lives in
procedural code that re-derives surface on every emit (`bounds_to_quantifier`,
`_split_charclass_segments`, the hex walker). The fix is identical in both:

> **Cure:** one **canonical algebraic renderer** lives in `ir/` (flavour-neutral,
> built from the action algebra), produces the *shared* surface (regex / internal-
> Lark / GBNF all agree). The one deviating flavour (**ABNF**) **overrides** with
> its own algebraic action. All other consumers — `parsing/lark_builder` (Layer 1),
> `codegen/aliases`, naming, `generate` — call the canonical renderer. The
> procedural re-derivation is **deleted**.

This deliberately reaches past the umbrella's "Layer 1 untouched" boundary
(into `lark_builder` and `codegen`) — a sanctioned scope expansion, because the
goal is to *delete* the denatured procedural code, not wrap it.

New canonical renderers live in **`ir/canonical.py`** (`IrEmitter` singletons
built from the algebra). Layering holds: `ir ← grammars`, `ir ← parsing`,
`ir ← codegen` are all permitted edges; the renderer imports nothing from
`grammars`.

---

## 0a — Algebra expansion + canonical-op amendment

### 0a.1 New ops

- **`IrInt(IrType, int)`** — exact sibling of `IrStr`. `_bound = int`, neutral
  `0`, single-arg `coerce`. Exists to be the **honest operand** for comparison,
  so no raw Python int is smuggled through `getattr` (the stringly-escape §2.3
  forbids).
- **`IrCompare(left: IrNode, op: Cmp, right: IrNode)`** — `Cmp` a closed enum,
  **`EQ | LT | GT`** only. `eval` evaluates both sides via `.eval` and compares
  with native builtins (`IrInt` *is-a* `int`). **Returns `IrInt(0)`/`IrInt(1)`**;
  `IrCond` tests it by native truthiness (`bool(IrInt(0))` is `False`).
- **`IrAnd(parts: IrTuple[IrNode])`** — conjunction; `eval` is AND over the
  truthiness of evaluated parts, yielding `IrInt(0/1)`. `IrOr` and boolean-`NOT`
  are **not** built (no Phase-0 consumer; see §0a.5).

### 0a.2 Generalized `IrCond`

`field: str` → **`test: IrNode`**; `_child_attrs = ("test", "then_op",
"else_op")`; branch on `bool(self.test.eval(d, n, nc))`. **No bare-`str`
coercion** (zero callers). This is the only shape change to an existing
canonical op besides §0a.3.

### 0a.3 `IrField` bound widening

`IrField[Ir_co: IrStr = IrStr]` → **`IrField[Ir_co: IrType = IrStr]`** so it can
read `IrInt`-typed attributes (`IrField[IrInt]("min")`). Required by 0b's
algebraic quantifier emit (comparing bounds without `getattr`-int smuggling).
Default stays `IrStr` — existing string field-reads are unaffected.

### 0a.4 Booleans, with no `IrBool` node (decision X)

`bool` is not subclassable in Python, *and* a boolean is an `int` in `{0,1}`.
So a truth value is **`IrInt` whose domain is `IrQuantifier(0,1)`** — no `IrBool`
primitive. `IrCompare`/`IrAnd` return `IrInt(0/1)`; the `[0,1]` domain is a
**type-level** fact (documented), not a runtime carrier. This rests on 0b's
reframing of `IrQuantifier` as a general integer **interval** (§0b.4).

**Recorded, not built (decision Y → deferred):** a runtime refinement node
`IrRanged(value: IrInt, bound: IrQuantifier)` is the named future home for two
things only — (1) *unified complement-based negation* (boolean `NOT` =
`bound.max − v`, the same shape as charclass complement) and (2) *Slice-C
Pydantic-constraint codegen* (`Field(ge=, le=)`). Neither is a Phase-0/Lark
consumer; `X → Y` is a lossless later upgrade (wrapping a bare `IrInt` is
non-breaking). The `IrNot`/boolean relationship is recorded here as its eventual
home; **`IrNot` stays grammar-only** in Phase 0.

### 0a.5 Canonical-op amendment (governance)

This section **formally amends** the op freeze of `2026-05-17` §rule-5 / `2026-05-18`:

- **Name correction:** the canonical body ops are
  `IrReturn, IrChild, IrChildren, IrConcat, IrField, IrCond, IrJoin, IrCallable,
  IrLiteral` — **not** `IrText` (which does not exist).
- **Additions:** `IrInt`, `IrCompare`, `IrAnd`; `IrCond` reshaped (§0a.2);
  `IrField` bound widened (§0a.3).
- **Unchanged rules:** `IrCallable` remains the sanctioned procedural escape
  hatch; any op beyond this amended set requires a further amendment.

### 0a.6 Tests

`tests/unit/lexic/ir/test_action.py`: `IrInt` value/neutral/coerce; `IrCompare`
each `Cmp` over `IrInt` operands; `IrAnd` truthiness; generalized `IrCond` with an
`IrCompare` test; `IrField[IrInt]` reading an int attribute.

---

## 0b — Honest quantifier (general interval) + Cure

### 0b.1 Representation

`IrQuantifier` becomes an **arity-encoded tuple of `IrInt`**; **arity encodes
unboundedness** (no stored `None`):
- arity 2 = closed interval `[lo, hi]`; arity 1 = half-open `[lo, ∞)`.
- `(0,)`→`*`, `(1,)`→`+`, `(0,1)`→`?`, `(n,n)`→`{n}`, `(n,)`→`{n,}`,
  `(n,m)`→`{n,m}`. Pinned convention: `(n,)` is *at least n*; *exactly n* is
  `(n,n)`. Default stays `(1,1)`.
- Exposes `min`, `max` (`IrInt`) and **`arity` (`IrInt`)** so "unbounded" is
  `arity == 1`, testable with the same `IrCompare` machinery — no special
  predicate, no boolean-`NOT`.

### 0b.2 Forward migration — no compat facade

No `max=None` survives anywhere; we move forward, not bridge backward.
Unboundedness is **arity**: an open quantifier is constructed as a 1-arity
interval, never `(n, None)`. Construction is arity-honest — the default
`IrQuantifier()` stays `(1,1)`; a clean interval constructor builds a 1- or
2-arity `IrTuple[IrInt]` (exact ergonomics settled in the plan; `IrInt` coercion
of raw `int` args is normal `IrNode` behavior). Accessors do **not** reintroduce
`None`: `.min`→`IrInt`, `.arity`→`int`; the upper bound is read arity-guarded
(`max` is meaningful only when `arity == 2` — exactly where the canonical
action's `IrField("max")` runs). Consumers migrate forward:
- **`parse_quantifier`** (both flavours) constructs arity-1 for `*`/`+`/`{n,}`
  instead of `(…, None)`.
- **`derive._relax_item`** is rewritten arity-aware (rebuild `min`→0 preserving
  the upper bound / arity), replacing `IrQuantifier(0, item.quantifier.max)`.
- The ~20 construction sites move to the arity-honest form.

### 0b.3 The Cure

A **single canonical algebraic quantifier action** in `ir/canonical.py` — a
nested `IrCond` tree gated on `arity`, then `min`/`max` equality, built from
`IrCompare(EQ)` + `IrAnd` — produces the canonical `?*+{n,m}` surface.
- **GBNF** uses the canonical action (its surface == canonical).
- **ABNF** overrides with its own algebraic action (prefix `*n`/`n*m`).
- **`lark_builder`** and **`aliases`** render suffixes by `apply`-ing the
  canonical emitter instead of `bounds_to_quantifier`.

**Deletions:** `_gbnf_quantifier`, `_abnf_quantifier`,
`_abnf_format_quantifier`, `GBNF_QUANT_SYMBOLS`, and **`utils/quantifiers.py`**
(`bounds_to_quantifier`) entirely. This **fixes the latent GBNF `{n,m}` bug**
(`gbnf/flavour.py:117` raised on brace forms).

### 0b.4 Interval reframe

`IrQuantifier` is documented as a **general integer interval** — repetition
bounds are one use, value domains another (the `[0,1]` bool domain from §0a.4
rests on this). No new node; docstring + shared abstraction.

### 0b.5 Not in 0b

**Greed** (lazy/possessive). It is an orthogonal match-strategy variant, not an
interval property; "greed-ready" means nothing blocks adding it later, not that
scaffolding is built now. Greed is Phase 4.

### 0b.6 Tests

Re-prove the 7 ground-truth round-trips; **add** `{2}`/`{2,}`/`{2,5}` brace
cases (currently parse-but-fail-to-emit); cross-flavour quantifier property
tests; canonical-action unit tests in `tests/unit/lexic/ir/test_canonical.py`.
Remove `tests/unit/lexic/utils/test_quantifiers.py`.

---

## 0c — Structured charclass + Cure-mirror

### 0c.1 Node shape

`IrCharClass` stops being a `value:str` leaf and becomes an **`IrCollection` of
typed members**, retaining `IrAtom` by multi-inheritance (as `IrGroup` does):
- `IrChar(value: str)` — one decoded, canonical character.
- `IrRange(lo: IrChar, hi: IrChar)` — inclusive range (a codepoint interval; a
  second future customer for `IrRanged`/Y, recorded not forced).
- A member base marker (`IrCharClassMember`).
- **`NamedSet` (`\d`/`\w`/`\s`/POSIX) is defined in the hierarchy but not built**
  — no GBNF/ABNF or ground-truth consumer; it arrives with Lark/regex in Phase 1
  and slots in with zero rework.
- **Negation stays external** via `IrNot(IrCharClass(...))` → `[^…]`.
  `IrCharClass` holds only positive members.

### 0c.2 Order preserved, no normalization

`[a-z0-9]` → `(Range(a,z), Range(0,9))` in that order, emitted byte-identical. No
sorting, dedup, or range-merging. Round-trip is **re-earned**, not assumed.

### 0c.3 The Cure-mirror

A **single canonical algebraic charclass renderer** in `ir/canonical.py` —
bracket form `[…]`, an `IrJoin` over members dispatched by member-type
(`IrChar`→escaped char, `IrRange`→`lo-hi`) — consumed by **GBNF + `lark_builder`
+ `aliases` + naming**. **ABNF overrides** with the hex form (`%xNN` /
`%xNN-MM`, per-member dispatch).

**Deletions:** `_split_charclass_segments`, `_hex_range_segment`, and
`_gbnf_charclass`'s string interpolation. Per-member hex/escape encoding is a
codec call via `IrCallable` — the *sanctioned* escape hatch, satisfying the
closure check (the only surviving `IrCallable` in either flavour is
literal/charclass escaping).

### 0c.4 `parse_charclass` contract change (Layer 3)

The `IrFlavour` ABC and both flavours move from
`parse_charclass(text) -> (pattern: str, negated: bool)` to
**`-> (members: tuple[IrCharClassMember, ...], negated: bool)`**.
`meta_parser._build_charclass` wraps members in `IrCharClass` (+ `IrNot` if
negated). Each flavour segments its own surface (`[a-z0-9]` → ranges;
`%x41-5A` → range).

### 0c.5 Consumer migration

Every `.value` reader (~15) moves to members or the canonical renderer:
- **naming** (`derive._bracketed`, `CHARCLASS_NAMES` keys,
  `aliases._name_for_charclass`) → key on the **canonical bracket form** of the
  members (intrinsic to `IrCharClass`).
- **`generate.py`** (`parse_charclass_chars(atom.value)`) → enumerate from
  members (`IrChar`→`[c]`, `IrRange`→expand). The string-parsing
  `charclass.py::parse_charclass_chars` is **replaced** by member enumeration.
- **`lark_builder`** / **`aliases`** bracket-building → canonical renderer.

### 0c.6 Tests

Re-prove the 7 ground-truth round-trips (charclass-heavy: `arithmetic`, `c`,
`json_*`); add order-preservation and negation cases; cross-flavour charclass
property tests; `generate` enumeration over structured members; canonical-action
unit tests. Update `tests/unit/lexic/ir/test_nodes.py`,
`test_charclass.py`, and the flavour tests.

---

## 0d — `IrNonSemantic` (forward-pointer; becomes its own spec)

**Not specced in detail here — tracked so we don't lose it.**

Today `@non-semantic` is parsed as a directive (`ir/directives.py`) into a
`frozenset`, threaded as a `derive_specs` parameter, and applied as a `min=0`
relaxation (`derive._apply_non_semantic`/`_relax_item`) plus
`RuleSpec.non_semantic_fields`.

**Destination (per umbrella §4.2):** a Lexic-level **`IrNonSemantic(IrDispatch)`**
— an `IrSelf` one level above the grammar that *dispatches on* it to mark its
targets. `@non-semantic` (GBNF/ABNF comment-space shim) and Lark `%ignore`
(native) both **parse into the one `IrNonSemantic`**; each flavour emits it back
to its own surface. This is the worked example of the program's Lexic-level
dispatch pattern.

It is **independent of 0a–0c** (touches `directives`, `derive`, `compile_grammar`,
`RuleSpec` — not the node algebra) and is deferred to spec **0d**.

---

## Cross-cutting

### Layering

The canonical renderers in `ir/canonical.py` are consumed across `grammars`,
`parsing`, and `codegen` — all permitted `ir ←` edges. The renderers import
nothing from `grammars`. No new runtime→codegen edge; the two sanctioned edges
are untouched.

### Invariants preserved

- **Round-trip fidelity** re-proven per flavour after each of 0a/0b/0c.
- **Grammar is canonical**; cross-flavour emit raises honestly (ABNF still has no
  negation → `IrNot` raises, unchanged).
- **One way per task**: one canonical renderer per concept; ABNF override is the
  single deviation, not an alternate API.
- **No regression**: full suite (474 tests) green after each sub-step.

### Test-file discipline

Per CLAUDE.md: new modules get mirrored test files (`ir/canonical.py` →
`tests/unit/lexic/ir/test_canonical.py`); deleted `utils/quantifiers.py` →
delete `tests/unit/lexic/utils/test_quantifiers.py`.

---

## Explicitly out of scope

- **0d `IrNonSemantic`** — forward-pointer only; its own spec.
- **Greed** (Phase 4); **`NamedSet`** population (Phase 1); **`IrRanged`/Y**
  (Slice C / unified negation); **`IrOr`/boolean-`NOT`** (no consumer).
- Any Lark flavour work — that is Phase 1.
