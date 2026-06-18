# Handover — `flavour_2` and the Lark cutover

**Date:** 2026-06-18
**Status:** design settled; implementation not started. Builds on the completed
`parsing_2` engine (see `prototyping/next/draft/parsing_2-handover.md`).
**Revised** after an adversarial review of the first draft — phase order corrected
(container before grammars), Phase 1 expanded (selection algebra), Seam 2 promoted to
its own phase, and a feature-parity checklist added.

This document lists the steps to finish dropping Lark: replace both Lark seams in
`compile.py` with the IR-native parser, behind a new **`flavour_2`** that is *pure IR
data* (only `IrSelf` instances — no Python methods).

---

## 1. Where we are (done, committed)

The IR-native Earley pipeline in `src/lexic/parsing_2/` is complete and tested:

- `normalize.py` — `flatten_groups`, `desugar_quantifiers`, `split_literals`
  (`_Rewriter`), `is_synthetic_name`. **No `normalize()` composer yet** — callers chain
  the three by hand; the synthetic-prefix precondition is documented, not enforced.
- `engine.py` — Earley recognizer/parser with the **nullable completer**
  (Aycock-Horspool) and `_ParseInputs` bundle.
- `ops.py` / `chart.py` / `item.py` / `forest.py` — dispatch ops, chart,
  `EarleyItem`, `ParseTree` + `build_tree`. **Single-link provenance only**
  (`chart.py` `Link` is single-valued) — unambiguous grammars.
- `reduce.py` — `Reducer` with synthetic-node splicing.
- `src/lexic/grammars/abnf_2.py` — `ABNF_GRAMMAR` (RFC 5234 subset) + `ABNF_REDUCTIONS`;
  the **ABNF self-hosting fixpoint closes**, idempotent, CRLF-robust. 18 `IrCallable`
  reductions; `_num_val`/`_repeat` still call `ABNF_FLAVOUR.parse_charclass`/
  `parse_quantifier`.
- 977 tests pass; pylint/pyright/ruff clean.

`parsing_2` is still **fully standalone**. `compile.py` uses Lark at two seams:

- **Seam 1 (meta-grammar):** `MetaGrammarParser.for_flavour(flavour).parse(text)`
  → `IrAst` (`compile.py:176`). Unambiguous notation grammars.
- **Seam 2 (runtime input):** `build_lark(...)` → Lark parser + `build_transformer`
  that turns user input into `GrammarModel` instances (`compile.py:86,126`). User
  grammars **may be ambiguous**.

---

## 2. Decisions (settled — do not relitigate)

1. **Ambiguous grammars are supported.** The engine must produce a **shared packed
   parse forest (SPPF)**. Single-link provenance is a placeholder. SPPF is a hard
   prerequisite for Seam 2 (user grammars); it is *not* needed for Seam 1 or the
   grammars-of-grammars (those are unambiguous).
2. **A flavour contains ONLY `IrSelf` instances.** No Python methods, no callbacks.
   `parse_quantifier`, `parse_charclass`, `normalize_literal`, and the `EscapeCodec`
   class are **deleted**. The goal stands; achieving it requires *both* a construction
   algebra **and** a selection/filter algebra (see Phase 1).
3. **Grammar-of-grammar rules are canonical-tagged** with the IR node they produce (as
   the Lark meta-grammars do with `-> ir_*`), so reductions can be shared across
   flavours. NB: `IrRule` has no tag slot today (`nodes.py`) — the mechanism is an open
   design point (Phase 3).
4. **A construction/numeric algebra + a selection algebra make the fold pure `IrSelf`**
   and retire every `IrCallable` in both `actions` and `reductions`.
5. `IrChr` / `IrRadix` are **value-carrying** (not `n`-reading); spelling is emit-time,
   per-flavour, on neutral `IrInt` codepoints.

### A flavour, end to end

```
grammar    : IrAst          # concrete syntax, rules canonical-tagged with target IR node
nodes      : IrDispatch     # per-node {emit, build} bodies — all IrSelf
escapes    : IrMap          # was EscapeCodec
name / extensions / line_comment : IrStr / IrTuple[IrStr]
```

Nothing but `IrSelf`. The parser, SPPF forest, reducer engine, and the shared reductions
live in `parsing_2`, not on the flavour.

> **Key-space caveat (Phase 2 must resolve):** emit `actions` key on IR node **type**;
> reductions are fundamentally **per grammar rule** (one rule name → possibly several IR
> types across arms; one IR type produced by several rules — `abnf_2` has 26 reductions
> for ~11 types). "One bidirectional `nodes` table" is not a free unification; decide the
> real shape before authoring grammars.

---

## 3. Implementation steps (ordered — revised)

Ordering principle: **build the algebra → fix the flavour container and its
representations → author the grammars → SPPF → wire Seam 1 → wire Seam 2 → cut over.**
Container precedes grammars because GBNF forces representation decisions (escapes,
`[...]`+`^` negation, postfix/`{n,m}` quantifiers) that ABNF dodged.

### Phase 1 — IR algebra (generic, in `ir/`; the enabling layer)

1. **Numeric / construction:** `IrRadix` (digit-run → `IrInt`, base read structurally),
   `IrChr` (codepoint-carrying char leaf; emit-time spelling), and an `IrMake`-family to
   construct typed IR (`IrQuantifier`, `IrRange`, `IrCharClass`, `IrItem`, `IrSequence`,
   `IrAlternation`, `IrRule`, `IrAst`) from reduced children.
2. **Selection / filter:** `IrSelect` / `IrFilter` / `IrCollect` (working names) — the
   reductions don't just *construct*, they *filter children by type* and *positionally
   select* (`next(c for c in nc if isinstance(c, X))`, `nc[1:-1]`). Without these the
   `IrCallable`s cannot be removed. **This is the half the first draft omitted.**
3. Unit-test each node's `eval` contract. **Do not touch `ABNF_REDUCTIONS` yet** — the
   `parse_*`-deletion is one atomic edit, and it belongs in Phase 3 (see below), not
   smeared here.
4. **Layering watch:** type-filtering is *consumer policy*; landing it in `ir/` risks
   cementing the closed-set ladder the open-classes direction wants to dissolve
   (`MEMORY.md`: open-set-consumer rework). Keep these nodes open/dispatch-driven, not a
   new hardcoded ladder.

### Phase 2 — `flavour_2` container + representations (was Phase 4 — moved up)

5. Define the `flavour_2` ABC with the pure-`IrSelf` shape in §2.
6. **Decide the table shape** given the key-space caveat: one bidirectional table, or
   two (emit keyed by type, reduce keyed by canonical rule-tag). This decision gates
   Phase 3.
7. Migrate `escapes`: `EscapeCodec` → `IrMap`/`IrSelf` data; escaping via the existing
   `IrEscape` action node. Needed before any escaped-literal grammar (GBNF).
8. **Resolve char-class-with-escapes and `IrNot`** in *both* directions. ABNF `%x`-only
   never exercised `[...]` escapes or negation; GBNF does (`[^"\\\x00-\x1F]`). There is
   **no `IrNot` reduction anywhere yet**.
9. **Resolve quantifier construction** for prefix (ABNF `*`, `1*`) *and* postfix +
   counted (GBNF `*`/`+`/`?`/`{n,m}`).
10. **Resolve case-insensitive literals** (`normalize_literal`: `"abc"` → match `aA bB cC`)
    — a genuine semantic rewrite, the one open question that isn't leaf-lexing. (Note:
    `ABNF_GRAMMAR` was authored to dodge it; real ABNF input triggers it.)

### Phase 3 — canonical-tagged grammars + shared reductions (was Phase 3)

11. Decide the **canonical-tag mechanism** (a field on `IrRule`, or a rule-name→IR-node
    side table). `IrRule` has no slot today.
12. Rewrite `ABNF_GRAMMAR` with canonical tags; migrate `ABNF_REDUCTIONS` onto the
    table — **dropping every `IrCallable` and every `parse_*` call atomically** (the
    three-way edit F2). Re-close the ABNF fixpoint. Delete the emit-side
    `_abnf_charclass` `IrCallable` (incl. its parenthesize-iff-multiple branch).
13. Author the **GBNF grammar-of-grammar** (`gbnf_2.py`) on the same tags + shared
    reductions; it now has the escape/negation/quantifier machinery from Phase 2. Close
    its self-hosting fixpoint. Reproduce **`CORE_RULES` injection** (undefined
    `ALPHA`/`DIGIT`/`CRLF` …) here or in Phase 5.

### Phase 4 — SPPF / ambiguity (was Phase 2 — moved down; gates Seam 2)

14. Make `chart.py` `links` multi-valued; `build_tree`/`forest.py` produce **packed
    nodes**; `ParseTree.kids` admits them.
15. **`Reducer._reduced_children` must handle packed nodes** + a disambiguation policy
    (this *does* ripple into `reduce.py`, contra the first draft). Add an
    ambiguity-detection path (today the chart silently keeps the first completion).
16. Decide where disambiguation policy lives (engine default / flavour / grammar-author).
17. Tests with a deliberately ambiguous grammar.

### Phase 5 — Seam 1 (meta-grammar parsing)

18. Add a single `normalize()` entry (composes flatten→desugar→split) and **enforce** the
    synthetic-prefix precondition.
19. Replace `MetaGrammarParser.for_flavour(flavour).parse(text)` with
    `reduce(parse(normalize(flavour.grammar), text), reductions)`.
20. Preserve pipeline-level behavior that lives *outside* the parser:
    `parse_directives`/`@start`/`@non-semantic` precedence and `non_semantic_rules`
    plumbing (`compile.py:173-184`), ABNF `=/` incremental rules, `prose-val` rejection
    diagnostics.
21. **Acceptance gate:** the new Seam 1 must emit a **byte-identical `IrAst`** to the old
    one for every ground-truth grammar (else `derive_specs`/`codegen`/`generated/`
    regress undetected).

### Phase 6 — Seam 2 (runtime input → `GrammarModel`) — its own phase

> The single largest, least-specified piece. It is **not** "reuse the Reducer with a
> different target" — it is re-deriving `build_transformer` as reduction bodies.

22. Re-express, as `IrSelf` reductions driven by `RuleSpec`: `field_map`/`kind`-driven
    field assignment, unquantified-literal skipping, **adjacent optional-ruleref type
    disambiguation** (`build_transformer.py:121-131`), unbounded→list, per-atom consumers.
23. Preserve the **round-trip invariant** (`parse(text, grammar).to_text() == text`) as a
    test gate across all ground-truth grammars (`base.py` `to_text` is the contract).
24. Requires Phase 4 (SPPF) — user grammars may be ambiguous.
25. **Error diagnostics:** replace the single flat positionless
    `UnsupportedConstructError` (`engine.py:165`) with position + expected-set context.
    Today's message is a hard DX regression vs Lark.

### Phase 7 — cutover / cleanup

26. Delete `parsing/lark_builder.py`, `parsing/meta_parser.py`, `parsing/transformer/`,
    the `META_GRAMMAR` strings, `EscapeCodec`, and the Lark dependency.
27. Redesign `CompiledGrammar` — it currently holds `lark.Lark`/`lark.Transformer` typed
    fields (`compile.py:55-61`); the shape must change, not just lose imports.
28. Rename `parsing_2 → parsing`, `flavour_2 → flavour`, `abnf_2 → abnf`, etc.; mirror the
    test tree.
29. Finish the deferred `utils/quantifiers.py` cleanup (still consumed by `lark_builder`
    and `codegen/aliases.py`).
30. Update `CLAUDE.md`, `.wiki/`, the layering rules, and `prototyping/next/3_ROADMAP.md`.

---

## 4. Feature-parity checklist (must survive the cutover — easy to lose silently)

- [ ] ABNF `=/` incremental alternatives (RFC 5234 §3.3; `meta_parser.py:112-147`).
- [ ] `prose-val` `<...>` rejection diagnostic.
- [ ] `CORE_RULES` injection for referenced-but-undefined core rules (`abnf.py:101`).
- [ ] `@start` / `@non-semantic` directives and `non_semantic_rules` plumbing.
- [ ] Parse-error diagnostics with position + expected set.
- [ ] Byte-identical `IrAst` from Seam 1 for every ground-truth grammar.
- [ ] `parse(text).to_text() == text` round-trip from Seam 2 for every ground-truth grammar.
- [ ] Performance: Earley is O(n³) and `build_tree` runs eagerly inside `Complete`
      (`ops.py`). No benchmark exists; add one before trusting large inputs (`c.gbnf`,
      `json_arr.gbnf`).

---

## 5. Open questions (resolve in-phase)

- **Table shape** (Phase 2) — one bidirectional `nodes` table vs two, given the
  type-key/rule-key mismatch (§2 caveat).
- **Canonical-tag mechanism** (Phase 3) — `IrRule` field vs side table.
- **Case-insensitive literals** (Phase 2) — algebraic per-char case-class vs a dedicated
  node expanded in a generic pass.
- **Disambiguation policy location** (Phase 4) — engine / flavour / grammar-author.
- **Theoretical end-state (out of scope):** emit actions define surface syntax, so the
  grammar-of-grammar is in principle *derivable* from `actions`. Author explicitly for
  now; revisit only after the cutover.

---

## 6. Guiding invariant

A flavour is **concrete syntax (grammar) + surface rendering + escape data**, all as
`IrSelf`. The fold back to IR is generic. If a flavour needs a Python method, the
capability it wants belongs in the shared algebra (Phase 1), not on the flavour.
