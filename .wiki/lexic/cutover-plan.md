# Parallel-Track IR Cutover Plan

**When to load:** understanding what was done at cutover; checking Slice B remaining work.

Source: `docs/superpowers/plans/2026-05-08-parallel-track-ir-cutover.md`

See also: [[architecture]], [[ir-shapes]], [[slice-b-status]]

## Status — Cutover complete (2026-05-13)

All 18 tasks are done. The IrItem-based pipeline is the only pipeline. The old Atom shape (`atoms.py`), old `codegen/` (ir_builder, old lark_builder, old transformer), `new_gbnf/`, `new_codegen/`, and `flavours.py` are all gone.

### What replaced what

| Old | New |
|---|---|
| `grammars/new_gbnf/` | `grammars/gbnf/` |
| `new_codegen/` | `codegen/` |
| `ir/atoms.py` | deleted — `IrItem`-based nodes only |
| `RuleSpec.items: list[Atom]` | `RuleSpec.items: list[IrItem \| IrAlternation]` |
| `NewRuleSpec` | `RuleSpec` (unified) |
| `compile_text → _stem_for_text` hash | `compile_from_path → path.stem` |
| `codegen/lark_builder.py` + `codegen/transformer/` | `parsing/lark_builder.py` + `parsing/transformer/` |
| `grammars/__init__.py` ADAPTERS registry | `get_flavour` / `register_flavour` / `flavour_for_extension` |

> **Superseded further (2026-07-02/03):** the `parsing/lark_builder.py` +
> `parsing/transformer/` destination in the row above is itself gone — a
> second cutover (Lark→Earley, `PLAN_cutover_parsing_v2.md`) deleted the
> entire Lark path and replaced it with a native Earley engine at
> `src/lexic/parsing/` (both for grammar-text parsing and generated-instance
> parsing). See [[architecture]] and the 2026-07-02/03 [[log]] entry for the
> current shape; this page's table is a record of the 2026-05-13 cutover only.

### Still pending (Slice B)

See [[slice-b-status]] for the full breakdown. The one remaining concrete deliverable from Slice B is token reservation (Phase 3, Tasks 33–34): pre-tokenisation scan in the GBNF parser for `<name>`, `<[N]>`, `!<name>` syntax.
