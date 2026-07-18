# Generated Modules — the importable twins

**When to load:** exporting a compiled grammar to a `.py` file; touching `compile/export.py`, `bind_module`, `ir/layout.py`, or the notation emit half; reasoning about twin-vs-runtime class identity.

See also: [[architecture]], [[ir-shapes]], [[field-naming]], [[public-api]]

## What an export is

`export_module(compiled, path, *, stem=None, inline_tables=False)` (re-exported from `lexic.compile`; `export_source` is the string-taker it wraps) writes an **importable twin module** of a `CompiledGrammar`. Files are written ONLY on this explicit call (ruling 2 of 260718-generated-files) — `compile_text`/`compile_from_path` never touch disk.

The module shape (the approved showcase):

- module docstring naming the stem + source flavour, stating the twin boundary;
- a complete import block **derived from the emitted content** (`from lexic.ir import (...)` covers exactly the constructor names used; `Literal` only when a `Literal[...]` value_str renders; `ClassVar` only under `inline_tables`);
- one `GrammarModel` subclass per rule: docstring = the rule rendered in the source flavour's syntax; typed fields in the binding view's **defaults-last declaration order** (required first, `= None` optionals after — see [[field-naming]]); NO dunders in the default mode;
- `GRAMMAR: IrAst = ...` — the canonical AST in IR-constructor notation;
- `bind_module(GRAMMAR, globals())` — the module-end call that recomputes `build_codegen_grammar` + `compute_binding` (deterministic) and attaches `__grammar__`/`__binds__` to each class. It validates class presence, `GrammarModel` ancestry, and field-shape agreement (`UnsupportedConstructError` otherwise) and deliberately does NOT touch `_child_attrs` (the class-body annotations already derived the runtime-identical value at class creation).

`inline_tables=True` instead writes `__grammar__`/`__binds__` as ClassVars per class (no bind call, self-contained, ~2× faster first import, busier classes). Same classes either way.

## Twins, not the same objects

Ruling 1: `compile_*` keeps returning in-memory `type()` classes; the written module's classes are equivalent-but-distinct **twins** — proven attribute-identical (`__grammar__`, `__binds__`, `_fields`, `_child_attrs`, `_field_defaults`) and behavior-identical on `to_text`/`to_grammar`/`dump`. Twins do NOT parse — parsing stays on `CompiledGrammar` (the fold lives there). Pickle identity is NOT unified (parked).

Measured (2026-07-18): twin import 3.6–10.6 ms vs 16–79 ms cold compile; the default mode's bind recompute is 2–6 ms of that, once per process.

## Formatting is IR-native

No ruff, no subprocess anywhere in `lexic.compile`:

- **`ir/layout.py`** — Wadler-style doc combinators on the record spine (`IrText`/`IrLine(flat, pre)`/`IrCat`/`IrNest`/`IrGroup` + the mutable `Sheet` cursor). Behavior is intrinsic per node (`layout()` render step, `scan()` fit-lookahead); `render(width)` drives an explicit stack. The group fit-check scans the **line continuation** (the sheet's pending stack) so trailing separators count against the line they land on.
- **the notation emit half** — `emit_ir(node, width)` in `compile/notation.py`: a per-TIER `IrTypeMap` step table (scalar leaf / record via `IrNamedTuple.repr_args` — one elision truth shared with `__repr__` / variadic / mapping-as-dyads / interned singletons / `IrSelf`-repr long tail; `IrLambda` refused eagerly) building layout docs, black-call shape. The exact inverse of `load_ir`: `load_ir(emit_ir(x)) == x` strictly for grammar ASTs; the **repr fixpoint** (`repr(load_ir(emit_ir(x))) == repr(x)`) is the contract for payloads carrying identity-eq leaves (`IrGlyph()` etc.). Broken calls carry black-style trailing commas and strings render double-quote-preferring (`black_quoted`) — **a fresh export is an isort+ruff-format FIXPOINT** (verified over the whole GT corpus, both table modes), so format-on-save never fights regeneration. Trailing commas PARSE via the gateable `arg-tail` shape (`arglist ::= value arg-tail*`, `arg-tail ::= comma arg-val?` — the comma is consumed first, so the loop stays FIRST-disjoint and nothing islands); a bare comma anywhere but last position refuses at fold time (`_arglist` strictness, the unknown-symbol precedent). The exporter's header imports are emitted in sorted (isort-stable) order.

## Always-on export gates

Every `export_source` call validates in-process: the module `ast.parse`s, and the rendered `GRAMMAR` text `load_ir`s back to an AST **equal** to `compiled.grammar`. `tools/check_generated.py` is the corpus gate: all GT grammars × both modes must be pyright-clean and pylint-clean under DEFAULT configs, with exactly three accepted exception classes (C0103 on keyword-mangled class names `True_`/`False_`; C0302 module length on large grammars; R0801 gbnf↔abnf twin duplication — same canonical AST by design).

## Reserved class names

`_RESERVED_CLASS_NAMES` (`compile/binding.py`) = `{GrammarModel, ClassVar, Literal}` ∪ the `Ir*` constructor names the notation emits — exactly the header's PascalCase bindings (lowercase `bind_module` and UPPERCASE `GRAMMAR` can never collide with a PascalCase class name). The pydantic/typing-era names (`StringConstraints`, `Annotated`, `List`, `Optional`, `Union`) were trimmed 2026-07-18 — parity-neutral on the whole GT corpus. Drift-pinned against a real export.
