# Slice B — confirmed decisions only

What the user has explicitly agreed to. Nothing inferred, nothing I drifted into.

## Scope

- Scope is **B + cleanup**: IrAction/IrOp substrate, migration of IR-internal closed-subclass passes onto the substrate, rename `Quantifier` → `IrQuantifier`, migration of `GbnfFlavour` / `AbnfFlavour` onto the substrate (Flavour-as-IrEmitter), and opportunistic cleanup once the substrate is in.
- The authoritative scope-exclusion contract is `docs/superpowers/specs/2026-05-17-slice-b-deferred-work.md`. Anti-creep rules in that document apply.

## Edits to the deferred-work doc the user approved

- `Flavour.pre_parse_check` hook is NOT carved in this slice. The future token-reservation slice defines its own shape when it knows what it needs.
- The soft qualifier on `parsing/lark_builder.py` (section §1) stays as written. The user rejected tightening it.
- `IrDispatch` / `IrTransformer` / `IrVisitor` / `Flavour` are `IrNode` subclasses. The user rejected narrowing this to "only `IrAction` + `IrOp` are IrNodes."

## Confirmed substrate shape

- `class IrDispatch(IrCollection["IrAction"], Generic[_T]):` — the dispatcher is generic over `_T`; the IrNode-ness comes from `IrCollection["IrAction"]`. **Verbatim from the user.**
- `IrDispatch` is **not** an ABC.
- `IrDispatch` **has** a `default` mechanism. The user's words: *"By default IrDispatch uses the table, if any is set, otherwise it uses the default."*
- `IrOp` is generic over `_T` the same way `IrDispatch` is. The user's words: *"IrDispatch is generic on _T, IrOp should as well."*
- Op variants are typed by what they natively produce; composition across `_T` is duck-typed in the Python sense. The user's words: *"Strings can be truthy or falsy."* So a string-producing op is composable in a bool-folding dispatcher; the generic parameterization expresses intent and dispatch matching, not a runtime straightjacket.
- Skip-recursion / fallthrough behaviour CAN be expressed via IrOp variants (the user gestured at `IrReturn`). This is direction, not a fully designed mechanism.

## Confirmed correctness constraint

- `has_ruleref` short-circuit MUST work. Accepting a perf regression here is **not** acceptable.

## Workflow

- Ask before each task whether to dispatch a subagent or implement manually.
- Never launch a subagent without asking first.
- No worktrees.
- Commits belong entirely to the user (no `Co-Authored-By`).
- No `# type: ignore` / `# pylint: disable` / `# noqa` without explicit permission.

---

## Explicitly OPEN (not confirmed; do not assume)

The user has NOT agreed to any of the following. Treat them as unanswered design questions, not as latent decisions waiting to be uncovered.

- **Dispatch entry point.** Whether `IrDispatch` is invoked via `__call__(node)`, a named method (`visit` / `dispatch` / `run` / `emit`), a free function taking `(dispatcher, node)`, or something else. I unilaterally assumed `__call__`; the user has not endorsed it.
- **Auto-recursion behavior.** Whether the dispatcher walks `node.children()` automatically before evaluating a matched action body, or whether action bodies drive recursion explicitly via op variants. The user has not picked.
- **`new_children` in action-body signatures.** Whether action bodies receive `(dispatch, node, new_children)` or just `(dispatch, node)`. Tied to the auto-recursion question.
- **Whether `IrDispatch` is a frozen-slotted dataclass.** `IrCollection.rebuild` uses `dataclasses.replace`, so concrete IrCollection subclasses must be dataclasses — but the exact decoration (`frozen=True, slots=True`, `repr=False`) on `IrDispatch` is not user-confirmed for this iteration.
- **How `default` actually fires.** Whether it is a method on `IrDispatch`, an `IrAction` keyed on the `IrNode` ABC (universal MRO catch-all), or both. The user has confirmed there IS a default; not where it lives.
- **Whether `IrReturn` is recognised specially by the dispatcher** (e.g. inspected before recursing to enable real skip-recursion) or just produces a value like any other op. Tied to the short-circuit requirement.
- **The exact IrOp variant inventory.** Earlier iterations canonicalised seven variants (`IrText`, `IrField`, `IrRecurse`, `IrSeq`, `IrJoin`, `IrCond`, `IrCallable`) plus `IrAction`. With `IrOp[_T]` generic and `IrReturn` added, the inventory may differ. Not confirmed.
- **Whether IR-internal passes (`_HoistTransformer`, `_RuleRefFinder`, `_PatternAliasVisitor`) migrate to the substrate at all** — and if so, in what form. The user rejected my proposal to fall back to plain recursive functions. They also said the previous IrCallable-based migrations were terrible. The right shape has not been settled.
- **The `_PatternAliasVisitor` bracketing-recursion mechanism.** Not user-confirmed in any form. Earlier `_pre_recurse` hook proposals were abandoned along with the deleted spec.
- **Test-green-after-each-step packaging.** Whether Flavour migration (and any other tightly-coupled multi-task work) is presented as an atomic group with intermediate commits, or repackaged as a single step. The user told me to decide; I should not commit to a packaging without revisiting.

## State of the repo

- Tasks 1.1–1.3 of `docs/superpowers/plans/2026-05-14-slice-b-closure-and-dispatch-unification.md` have landed: the rich IR node hierarchy (`IrNode → IrLeaf / IrStructure → IrCollection / IrComposite`), `children()` / `rebuild()` defaults on the bases, and `__str__` / `__repr__` are in place.
- `walk.py` still carries the legacy `IrDispatch` / `IrVisitor` / `IrTransformer` with `_CHILDREN` / `_REBUILD` / `_DUMP` / `dump()` / `visit_<TypeName>` machinery. Task 1.4 was never executed.
- The 2026-05-14 spec is partially superseded by intent (the 2026-05-15 revision section) but no clean replacement exists. The two 2026-05-17 documents that did exist (substrate-and-flavour-as-emitter spec + plan) were deleted at the user's instruction.
- `docs/superpowers/specs/2026-05-17-slice-b-deferred-work.md` remains. It is the only 2026-05-17 doc still in tree.
