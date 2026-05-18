# Slice B — deferred work (scope B+)

**Date:** 2026-05-17
**Companion to:** `2026-05-14-slice-b-closure-and-dispatch-unification-design.md` (fresh plan in progress).
**Status:** Authoritative scope-exclusion list for the fresh Slice B plan being written 2026-05-17.

## What this document is

The fresh Slice B plan adopts **scope B + cleanup**: substrate (IrAction/IrOp + unbounded-T IrDispatch + IrNode-as-minimal-protocol), migration of existing IR-internal passes onto that substrate, IrQuantifier rename, and migration of `GbnfFlavour` / `AbnfFlavour` onto the substrate (Flavour-as-IrEmitter) — plus whatever opportunistic cleanup becomes obvious once the substrate is in.

This document is the explicit inventory of what is **left out** of that fresh plan. Any item here is a future slice. None of it is permitted to creep back in during execution.

If a task in the fresh plan would require any item below to be live, the task must either:
- be removed from the fresh plan, or
- be rescoped to stub / no-op the dependency, or
- promote the item into scope explicitly via a spec amendment.

No silent inclusion. No "while we're here." No "it's small."

---

## In scope of the fresh plan (for contrast)

A reader of this document should be able to identify what is NOT in this list — those items are in the fresh plan:

- New `ir/action.py` with `IrAction` and the `IrOp` algebra (`IrText`, `IrField`, `IrRecurse`, `IrSeq`, `IrJoin`, `IrCond`, `IrCallable`).
- `IrDispatch` rewritten in `ir/walk.py` to be unbounded-T, action-driven, no `visit_<TypeName>` getattr, no `_CHILDREN`/`_REBUILD`/`_DUMP`, no top-level `dump()`.
- `IrTransformer` and `IrVisitor` reduced to thin presets over the new `IrDispatch`.
- `_HoistTransformer` and `_RuleRefFinder` cease to be closed subclasses; they become factory functions returning loaded `IrTransformer` / `IrVisitor` instances.
- `Quantifier` renamed to `IrQuantifier` and made an `IrLeaf` participant.
- `Flavour` becomes an `IrEmitter`. `GbnfFlavour` and `AbnfFlavour` populate `actions` tables of IrOp trees (with `IrCallable` only where genuinely required).
- `FlavourEmitter`, `GbnfEmitter`, `AbnfEmitter`, `utils/quantifiers.py` deleted.
- Consumers (`base.py`, codegen, `parsing/lark_builder.py`) migrated to call `flavour.visit(node)` / `render_specs(specs, flavour)`.
- Wiki updates for the substrate, IrQuantifier, IrNode-minimal-protocol, Flavour-as-emitter. No `pre_parse_check` documentation (the hook does not exist in this slice).
- Whatever opportunistic cleanup falls out of the above (e.g. `ir/helpers.py` deletion if it becomes obvious).

Everything else is deferred. The rest of this document enumerates what "everything else" is.

---

## Deferred — explicitly out of scope

### 1. LarkFlavour promotion

Everything related to elevating Lark to a peer Flavour stays deferred.

- No `src/lexic/grammars/lark/` directory. No `LarkFlavour`, `LarkEscapes`, `lark_meta_grammar.py`.
- `.lark` is **not** a user-facing grammar extension. No registration in `grammars/__init__.py` for `.lark`.
- `parsing/lark_builder.py` keeps its current shape: it stays the internal codegen target. It may be shrunk in the fresh plan to call `render_specs(specs, <internal LarkEmitter>)` only if doing so is forced by the Flavour-as-IrEmitter migration of GBNF/ABNF — but the LarkEmitter used internally is **not** a registered Flavour and has no parse side. No bespoke meta-grammar. No user-facing path.
- Existing helpers in `parsing/lark_builder.py` (`_regex_terminal`, `_bracket`, per-atom helpers) stay where they are. They do not migrate into a `LarkFlavour.action` table.
- No `tests/unit/lexic/grammars/lark/`. No `tests/integration/test_compile_grammar_lark.py`. No `.lark` arms added to `test_cross_flavour.py` or `test_full_round_trip.py`.
- The `LarkFlavour.action[IrItem]` regex-terminal-vs-rule-token distinction (the "sharp edge" called out in the 2026-05-14 spec) does **not** need to be solved by the fresh plan. It is a problem for the future LarkFlavour slice.

Re-entry: a future "Slice X — LarkFlavour as full peer" plan that consumes the substrate landed by this slice.

### 2. Token reservation

Everything related to GBNF positional / indexed / negation token-reference syntax stays deferred.

- No `_check_no_positional_token_syntax` implementation.
- No `Flavour.pre_parse_check` hook on the `Flavour` ABC. The slot is not carved in this slice; the future token-reservation slice defines its own shape when it knows what it needs.
- No `tests/integration/test_token_reservation.py`.
- Positional `<identifier>` syntax stays accepted (it'll parse as whatever the current grammar parser produces — i.e. a parse error from Lark, not a `UnsupportedConstructError`).
- Indexed (`<[N]>`) and negation (`!<name>`) refs were already deferred in the 2026-05-14 spec; they remain deferred.

Re-entry: a future "Slice X — token reservation" plan, possibly bundled with the negation-design work.

### 3. Codegen-side pass migration

`_PatternAliasVisitor` in `codegen/aliases.py` and any other closed-subclass `IrVisitor` / `IrTransformer` living **inside `codegen/`** stays as-is.

- They keep their `visit_<TypeName>` methods.
- They are not rewritten as `IrVisitor` / `IrTransformer` instances loaded with `actions` tables.
- The `_combine` / `generic_visit` machinery the new `IrDispatch` exposes is API-compatible enough that these closed subclasses continue to work; no behavioural change.
- Exception: if the substrate rewrite forces a signature change that breaks these consumers, the **minimum mechanical fix** is applied to keep them compiling and tests green — not a full migration to the action-table style.

Re-entry: a future "Slice X — codegen pass migration" plan, possibly bundled with broader codegen rework.

### 4. IR-pass migrations beyond hoist + ruleref-finder

Only `_HoistTransformer` and `_RuleRefFinder` (both in `ir/derive.py`) migrate to the action-table style in this slice. Any other closed-subclass walk-style consumer of `IrDispatch` discovered during execution is left alone unless it sits in `ir/derive.py` next to these two.

Specifically:
- If there's a closed-subclass visitor inside `parsing/transformer/build_transformer.py`, it stays closed.
- If there's a closed-subclass visitor inside `codegen/model_emitter.py`, it stays closed (covered by §3 too).
- The `IrAst.children()` / `IrRule.children()` chain is not extended with new participants in this slice.

Re-entry: opportunistic during future slices that touch the relevant files.

### 5. Pure IrOp expression of stateful passes

`_HoistTransformer` migrates to an `IrTransformer` instance loaded with `actions = {IrItem: IrAction(IrItem, IrCallable(_hoist_item))}`. The body is `IrCallable`. Replacing the `IrCallable` with a pure IrOp tree (introducing new IrOp variants for "allocate name", "side-effect helper-list append", "construct helper rule") is **not in scope**.

Same applies to `_RuleRefFinder`: it migrates to an action table, but the body may be `IrCallable`. A pure-predicate IrOp form (if one is even meaningful for a side-effect visitor) is deferred.

The `IrCallable` escape hatch exists precisely so this deferral is clean: future slices can replace specific `IrCallable` bodies with pure IrOp trees without re-doing the surrounding plumbing.

Re-entry: a future "Slice X — IrOp algebra completion" plan, only when there's concrete pressure to make these passes self-describable.

### 6. Self-description bonus features

The fresh plan establishes that `IrAction`, every `IrOp` variant, `IrDispatch`, `IrTransformer`, `IrVisitor`, and `Flavour` are all `IrNode` subclasses (they inherit `children()` / `rebuild()` / `__str__` / `__repr__` mechanically). That is in scope.

The following bonus features that flow from self-description are **deferred**:

- **`PyFlavourCodegenRenderer`**: a future renderer that emits Python source for a `Flavour` subclass from an in-memory `Flavour` IR tree. The architecture supports it; the renderer is not built.
- **`IrFlavour` (canonical IR-self-notation Flavour)**: a future Flavour whose surface syntax IS the IR notation produced by `__str__`. The placeholder strings emitted by the new `__str__` (e.g. `LITERAL('a')`, `SEQ(...)`) are deliberately not a parseable grammar in this slice — they're debug output, not a Flavour.
- **Parsing a `Flavour` from a text-format `IrFlavour` grammar** — not built; depends on `IrFlavour` existing.
- **A `repr(GbnfFlavour())` smoke test that asserts the dump looks structurally sensible**: nice-to-have. May or may not be added in this slice. If it gets in the way of execution, it's dropped without further amendment.

Re-entry: a future "Slice X — Flavour-as-source" plan.

### 7. Already-deferred items from prior specs (restated for completeness)

The following are already out of scope per the 2026-05-14 spec (`§ Out of scope`) and stay deferred. Restated here so the fresh plan can reference one document:

- Indexed token refs (`<[N]>`) and negation refs (`!<name>`).
- Wiring `validate_portable` / `PORTABLE_FEATURES` / `canonicalize_groups` into the emit path. `ir/regex_portable.py` stays half-live (the `literal_to_regex_pattern` half remains used; the validator half stays unused, with its existing `# type: ignore` / `# pylint: disable` directives preserved as-is — those are the only such directives in the codebase and they stay).
- `IrPredicate` / `IrEnum` quantifier extension types. Flat `IrQuantifier(min, max)` is sufficient.
- Quantifier extensions beyond `(min, max)` bounds.
- `FlavourEmitter` decorator helpers (`quote`, `wrap_group`, `render_charclass`, `render_inline_regex`) as standalone reusable utilities. They get inlined into per-type IrOp/lambda bodies; nothing reusable survives.

### 8. Wiki + docs related to deferred work

Wiki and CLAUDE.md updates in the fresh plan cover ONLY the in-scope items (substrate, IrQuantifier, IrNode minimal protocol, Flavour-as-emitter). The following wiki edits are explicitly deferred:

- Any mention of `LarkFlavour` as a peer Flavour in `architecture.md` / `flavour-system.md`.
- Any `.lark` extension documentation.
- Any `pre_parse_check` documentation beyond the no-op stub (the hook is real, but its only future caller — `_check_no_positional_token_syntax` — is deferred).
- Any decision entries about token reservation or LarkFlavour.

Re-entry: paired with each deferred feature's eventual slice.

### 9. `ir/helpers.py` — fate decided opportunistically

`ir/helpers.py` (HelperRuleRegistry — zero production callers) is a deletion candidate already identified in the 2026-05-14 spec. The fresh plan **may** delete it under "cleanup," but if doing so isn't trivially safe at that point, it stays. This is the one item in this document that may flip from deferred to in-scope mid-execution without a spec amendment, because deletion of zero-caller dead code does not introduce design risk.

If deleted: also delete `tests/unit/lexic/ir/test_helpers.py` and remove `HelperRuleRegistry` from `ir/__init__.py` exports.

### 10. `LarkBuilder.build_transformer` inline-vs-keep

Already-resolved decision from the 2026-05-14 spec: **inlined into `build_lark`**. That decision stays. The fresh plan executes it as part of the consumer-migration work, not as a separate task.

### 11. Hoist elimination — `_HoistTransformer` deletion + inline-group codegen

`_HoistTransformer` (in `ir/derive.py`) synthesizes helper `<parent>-item[N]` rules for quantified `IrGroup`s containing rulerefs. It exists because `RuleSpec.kind` classification doesn't represent an inline quantified ruleref-group, and `codegen/model_emitter.py` therefore can't emit a Pydantic field for that shape.

In this slice, `_HoistTransformer` migrates to the new substrate (action-table form, `extract_body_under` recognition method on `IrAtom`/`IrGroup`). The pass itself stays.

Eliminating the pass entirely is deferred. The full re-entry covers:

- Delete `hoist_helpers` and `_HoistTransformer` from `ir/derive.py`.
- `derive_specs` stops synthesizing helper rules; `RuleSpec.items` now legitimately carries `IrItem(atom=IrGroup(…), quantifier=non-trivial)` post-derive.
- `codegen/model_emitter.py` learns to emit a nested Pydantic class for the inline group, with the parent field typed as `list[Group]` / `Group | None` / `Group` per quantifier.
- Class naming for the inline group (no more `<parent>-item[N]` rule name to base it on).
- `codegen/aliases.py` `_PatternAliasVisitor` audit — the ruleref-frame stack exists to detect pure-literal groups (the complement of what hoist catches). Without hoist, this machinery may simplify or disappear.
- Ground-truth tests that pin the helper-rule shape need regenerating; round-trip behaviour for `(foo bar)+` shifts (today's emit can render synthesized helpers; without hoist, the inline group renders directly).

Re-entry: a future "Slice X — eliminate hoist + codegen for inline groups" plan. Depends on this slice's substrate landing first.

---

## Anti-creep rules

1. **No task in the fresh plan may name `LarkFlavour`**, `.lark`, `LarkEscapes`, `lark_meta_grammar.py`, or `grammars/lark/`. Internal use of `parsing/lark_builder.py`'s existing helpers is permitted; promotion of any of them to a Flavour is not.

2. **No task in the fresh plan may implement positional-token scanning.** The `pre_parse_check` hook may be added; its body must remain a no-op for every flavour.

3. **No task in the fresh plan may migrate a closed-subclass `IrVisitor` / `IrTransformer` other than `_HoistTransformer` and `_RuleRefFinder`** to the action-table style. Mechanical signature-compatibility fixes are permitted; behavioural rewrites are not.

4. **No task in the fresh plan may replace an `IrCallable` body with a pure IrOp tree** for `_HoistTransformer` or `_RuleRefFinder`. `IrCallable` is the explicit body for both in this slice.

5. **No task in the fresh plan may introduce a new IrOp variant beyond** the canonical set: `IrText`, `IrField`, `IrRecurse`, `IrSeq`, `IrJoin`, `IrCond`, `IrCallable`. If a flavour action needs something else, the action body uses `IrCallable` until a future slice expands the algebra.

6. **No task may add wiki / docs content for any deferred feature.** Updates are limited to documenting what landed.

If execution surfaces pressure to violate any of these rules, the response is: stop, surface the pressure to the user, decide whether to amend this document or live with the gap. Do not creep silently.
