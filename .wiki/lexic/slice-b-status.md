---
name: Slice B status — what remains and what no longer applies
description: Audit of Slice B (PatternAtom collapse, Tier 2.5 scaffolding, token reservation) against post-cutover codebase. Reference before picking up any Slice B work.
type: project
---

**When to load:** before resuming any Slice B work; when deciding what to do next after the IrItem cutover.

Source plan: `docs/superpowers/plans/2026-04-23-slice-b-pattern-atom-tier-2-5-tokens.md`

---

## TL;DR

Phase 1 (scaffolding) is largely done via the IrItem cutover path, though
through a different architecture than Slice B planned. Phase 2 (atom
collapse) is entirely obsolete — the old `Atom` shape is gone and the
IrItem shape is the only shape. Phase 3 (token reservation) is the one
remaining concrete deliverable.

---

## Phase 1 — Scaffolding (Tasks 1–14)

### Done through the IrItem cutover

| Task | Description | Status |
|------|-------------|--------|
| 1 | `lexic/exceptions.py` — `LexicError`, `UnsupportedConstructError`, `GrammarAuthoringError`, `FieldValidationError` | ✓ Done |
| 2 | `lexic/ir/regex_portable.py` — `PORTABLE_FEATURES`, `validate_portable`, `features_used` | ✓ Done (see caveat below) |
| 3 | Move GBNF modules into `grammars/gbnf/` | ✓ Done — differently (see below) |
| 5 | Import-path sweep across `src/` and `tests/` | ✓ Done as part of cutover |
| 8 | `flavour=` parameter on `codegen()` | ✓ Done |
| 9 | `flavour=` on `compile_text()` and `compile_from_path()` | ✓ Done |
| 10 | `GrammarModel.to_grammar(flavour)` | ✓ Done — `base.py:61` |
| 14 | `test_flavours.py` exists | ✓ Done — `tests/unit/lexic/grammars/test_flavour.py` |

### Obsolete — replaced by a different architecture

| Task | Original plan | Why obsolete |
|------|--------------|--------------|
| 4 | Wrap `GbnfParser` and `GbnfEmitter` as classes behind `FlavourAdapter` protocol | Replaced by `Flavour` ABC (`grammars/flavour.py`). `GbnfFlavour(Flavour)` is the class. `MetaGrammarParser` handles parsing generically. |
| 6 | Create `GbnfAdapter` implementing `FlavourAdapter` protocol | Same — `GbnfFlavour` is the adapter. No separate protocol layer. |
| 7 | Create `grammars/flavours.py` with `FlavourAdapter`/`Parser`/`Emitter` protocols + `ADAPTERS` registry | `flavours.py` was created then deleted. Registry is now `register_flavour`/`get_flavour` in `grammars/__init__.py` keyed on `Flavour` subclasses. `flavours.py` must stay gone — `test_layering_invariants.py` enforces this. |
| 12 | Freeze old atom dataclasses | Old atoms (`CharClassAtom`, `QuantifiedLiteralAtom`, `InlineRegexAtom`, etc.) are fully deleted. Nothing to freeze. |
| 13 | Doc cleanup — drop `<<name>>` / `TokenAmbiguityError` | `TokenAmbiguityError` was never added. The `<<name>>` grammar form was never implemented. Nothing to remove. |

### Done but with a caveat

**Task 2 — `regex_portable.py`:** `canonicalize_groups()` is a no-op stub
with a `TODO(slice-b-phase-2)`. Phase 2 is obsolete, so this TODO is stale.
The function should either be implemented (rewrite capturing groups as
non-capturing) or removed if no consumer needs it. The `type: ignore` and
`pylint: disable` directives on the private `re._constants` / `re._parser`
imports need explicit permission per project coding standards.

**Task 3 — Module layout:** The plan moved `codegen/parser.py` →
`grammars/gbnf/parser.py`. Superseded twice over since: the 2026-05-13
cutover moved to a `grammars/gbnf/` subpackage (`emitter.py`, `escapes.py`,
`flavour.py`, `meta_grammar.py`), and the 2026-07-02/03 Lark→Earley cutover
flattened it again to a single `grammars/gbnf.py` module carrying emit
`actions` + a native self-grammar/reducer (no `meta_grammar.py`, no separate
`parsing/meta_parser.py` — see [[architecture]]). `parser.py`/`ast.py` never
came back in any form. Layout question is moot; nothing to action here.

**Task 11 — Delete `LarkBuilder.build_transformer`:** Resolved by deletion,
not by the planned inlining. `parsing/lark_builder.py` (and
`build_transformer` with it) no longer exists — the entire Lark path was
removed in the 2026-07-02/03 cutover. Its replacement, `ModelFold`
(`lexic.parsing.models`), is the current instance-parsing fold. This Slice B
commitment is closed.

---

## Phase 2 — Atom collapse (Tasks 15–32) — **Entirely obsolete**

Tasks 15–32 collapsed `CharClassAtom`, `QuantifiedLiteralAtom`,
`InlineRegexAtom` into `PatternAtom` and reshaped `InlineAlternationAtom`.
None of this work applies:

- The old `Atom` shape (`ir/atoms.py`) was deleted at cutover.
- The new shape is `IrItem`-based (`ir/nodes.py`): `IrLiteral`, `IrCharClass`,
  `IrRuleRef`, `IrGroup`, `IrItem(atom, quantifier)`.
- `InlineAlternationAtom` does not exist; inline alternations are represented
  as `IrGroup(IrAlternation(...))`.
- `PatternAtom` was never created; char-class patterns live in `IrCharClass`.
- `source_forms` (flavour-shadow map) was never implemented; emitters read the
  flavour-specific syntax directly from `IrCharClass.pattern`.

Consumer migrations (Tasks 21–26), `HelperRuleRegistry` changes (Task 20),
and the regeneration step (Task 30) are all irrelevant — there is no old atom
shape to migrate from.

`validate_portable` / `PORTABLE_FEATURES` / `features_used` from Task 27 were
built and exist in `regex_portable.py` but are not wired into the pipeline.
The Slice B wiring point (`codegen/__init__` cross-check) no longer exists in
the same form. Decide separately whether to wire these into the new emit path.

---

## Phase 3 — Token reservation (Tasks 33–34) — **Still required**

This is the one piece of Slice B that is both concrete and unimplemented.

**What it is:** The GBNF meta-grammar should reject the `<name>`,
`<[N]>`, and `!<name>` token-reference syntax with a clear
`UnsupportedConstructError` rather than a cryptic Lark parse error.

**Current state (updated 2026-07-02/03 — Lark→Earley cutover):** `MetaGrammarParser`
and `grammars/gbnf/meta_grammar.py` no longer exist. GBNF grammar text now
parses via `canonical_grammar` (which calls `parse_grammar` →
`parse_reduced(normalize(GBNF_GRAMMAR), text, GBNF_REDUCER)`) (the native Earley engine, `lexic.parsing` — see
[[architecture]]). A grammar containing `<think>` or `!<output>` will fail
either at the engine level (`UnsupportedConstructError`, "no parse" — `<`/`>`
are not accepted anywhere in `GBNF_GRAMMAR`) or, if some other rule happens
to consume the characters, produce a confusing but *not* GBNF-token-related
parse. Either way there is still no diagnostic naming tokens as the
unsupported feature — the pre-tokenisation scan (Task 33) is equally
applicable and equally still-needed on the new engine.

**What to implement:**

1. In `canonical_grammar` (or a helper called before `parse_grammar`), scan the
   source text for the token-reference patterns:
   - `<identifier>` and `<[integer]>` — positional / indexed token refs
   - `!<identifier>` — negation token ref
   Raise `UnsupportedConstructError` naming "GBNF token-reference syntax
   (`<name>`, `<[N]>`, `!<name>`)" as the unsupported feature.

2. Add `tests/integration/test_token_reservation.py` asserting:
   - Grammar with `root ::= <think>` raises `UnsupportedConstructError`.
   - Grammar with `root ::= !<output>` raises `UnsupportedConstructError`.
   - Grammar with `root ::= <[0]>` raises `UnsupportedConstructError`.
   - The error message names "token" in a human-readable way.

The `TokenAmbiguityError` for `<<name>>` was explicitly dropped (Task 13
decision). Do not add it.

**Where to add the scan:** The scan belongs in `canonical_grammar` (`compile.py`)
before the `parse_grammar` call, or as a standalone `_check_no_token_syntax(text)`
helper called from there. The check is flavour-specific to GBNF — `canonical_grammar`
is flavour-agnostic, so gate the scan on `flavour.name == "gbnf"` (or move it
into `GBNF_REDUCER`'s reduction bodies) rather than adding it unconditionally.

---

## Summary table

| Phase | Tasks | Status |
|-------|-------|--------|
| 1 — Scaffolding | 1, 2, 8, 9, 10, 14 | Done |
| 1 — Scaffolding | 4, 6, 7, 12, 13 | Obsolete |
| 1 — Scaffolding | 11 | Done — resolved by deletion (2026-07 Lark cutover) |
| 1 — Scaffolding | 2 (`canonicalize_groups`) | Stub to resolve |
| 2 — Atom collapse | 15–32 | Obsolete (IrItem shape supersedes) |
| 3 — Token reservation | 33–34 | Pending (concrete, required) |
