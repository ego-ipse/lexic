# TODOS

Project-level deferred work. Each entry: what, why, depends-on, where.

---

## Cleanup pass after Phase E (IR AST architecture)

**What:** Run `/simplify` (or equivalent refactor pass) over the post-Phase-E codebase to consolidate dispatch sites, tighten types, and remove transitional helpers.

**Why:** The 2026-04-29 IR AST architecture slice prioritises architectural correctness via 26 captured decisions (see plan's `## GSTACK REVIEW REPORT` block). The user-acknowledged trade-off (decision G in that report) is that some surfaces will land "correct but verbose" — the architecture-first cut.

**What to look for:**
- `derive.py` field-naming helpers (`_ir_charclass_field_name`, `_ir_literal_field_name`, `_ir_group_field_name`) duplicate the data tables in `naming.py`. Consolidate.
- `_HoistTransformer` (Task 7) state-passing pattern is OO-shaped; check if a closure-based functional form is cleaner.
- `compile.py` flavour bridge: `get_adapter(name).flavour_cls` could become a single `resolve_flavour(name_or_cls)` helper.
- `MetaGrammarParser._PARSERS` cache could be a `functools.lru_cache` if the cache invalidation story doesn't matter.
- Generated module imports always pull the full IR AST surface (decision CQ #4) — consider tightening if it causes import latency on cold paths.
- Type-tightening pass once cycles dissolve (decision Arch #3 already does this for `Flavour.emitter`; same pattern may apply elsewhere).

**Pros:** Code shrinks. Type safety tightens. Future contributors get a smaller mental model.

**Cons:** Hours of work. Risk of accidental behavioural change.

**Depends on / blocked by:** Phase E (Task 26) of the IR AST architecture plan complete; full suite green; all 9 spec success criteria passing.

**Where to start:** `docs/superpowers/plans/2026-04-29-ir-ast-architecture.md` `## GSTACK REVIEW REPORT` block lists the 26 decisions. The cleanup-pass scope is everything that those decisions raised the floor on but did not tighten further.

---

## `src/lexic/utils/quantifiers.py` — revisit when adding IrNegation

**What:** When implementing IrNegation (the deferred "negation should be applicable to anything a quantifier is" feature), revisit `quantifier_to_bounds` in `src/lexic/utils/quantifiers.py`. The empty-string edge case was patched (`"" → (1,1)`) during the parallel-track cutover. IrNegation may expose further assumptions in how quantifiers and negation compose.

**Why:** The patch (treating `""` same as `None`) was expedient. IrNegation changes the semantic space of what a quantifier applies to — worth a deliberate review pass.

**Depends on / blocked by:** IrNegation brainstorm + implementation.

**Where to start:** `src/lexic/utils/quantifiers.py`, `src/lexic/ir/nodes.py` (IrCharClass.negated is the current negation anchor).

---

## `<...>` GBNF token reservation

**What:** Implement the `<token>` syntax detection that `prototyping/next/2_ARCHITECTURE.md` §"Token reservation" describes — `UnsupportedConstructError` for any GBNF source containing `<...>` token references, with the architecture-doc's two error classes (`UnsupportedConstructError` and `TokenAmbiguityError`).

**Why:** The architecture doc commits to it as a future extension point. The new `MetaGrammarParser` does NOT add this detection; today, a GBNF source with `<token>` references either fails Lark parsing (no rule covers `<...>`) or silently parses depending on the meta-grammar's tokenization. The behaviour is undefined.

**Pros:** Closes a documented architecture gap. Establishes the dispatch entry point for a future `TokenAtom` handler.

**Cons:** Requires a meta-grammar update OR a pre-parse scan; the latter is simpler.

**Depends on / blocked by:** IR AST architecture slice complete.

**Where to start:** `prototyping/next/2_ARCHITECTURE.md` §"Token reservation" describes the contract.
