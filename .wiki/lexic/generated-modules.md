# Generated Modules — the importable twins

**When to load:** exporting a compiled grammar or a parsed VALUE to a `.py` file; touching `compile/module/export.py`, `compile/payload/`, `compile/writer.py`, `bind_module`, `ir/layout.py`, or the notation emit half; reasoning about twin-vs-runtime class identity.

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
- **the notation emit half** — `emit_ir(node, width)` in `compile/notation/parse.py`: a per-TIER `IrTypeMap` step table (scalar leaf / record via `IrNamedTuple.repr_args` — one elision truth shared with `__repr__` / variadic / mapping-as-dyads / interned singletons / `IrSelf`-repr long tail; `IrLambda` refused eagerly) building layout docs, black-call shape. The exact inverse of `load_ir`: `load_ir(emit_ir(x)) == x` strictly for grammar ASTs; the **repr fixpoint** (`repr(load_ir(emit_ir(x))) == repr(x)`) is the contract for payloads carrying identity-eq leaves (`IrGlyph()` etc.). Broken calls carry black-style trailing commas and strings render double-quote-preferring (`black_quoted`) — **a fresh export is an isort+ruff-format FIXPOINT** (verified over the whole GT corpus, both table modes), so format-on-save never fights regeneration. Trailing commas PARSE via the gateable `arg-tail` shape (`arglist ::= value arg-tail*`, `arg-tail ::= comma arg-val?` — the comma is consumed first, so the loop stays FIRST-disjoint and nothing islands); a bare comma anywhere but last position refuses at fold time (`_arglist` strictness, the unknown-symbol precedent). The exporter's header imports are emitted in sorted (isort-stable) order.

## The module self-grammar (L2 — lexic parses its own exports)

`compile/module/selfgrammar.py` (260718-module-selfgrammar): `module_grammar()` is
an authored `IrAst` for the canonical exported layout — a strict statement
skeleton (newlines/4-space indents as REQUIRED literals; `class`/`from`/
`GRAMMAR`/`bind_module` keywords FIRST-disjoint) embedding the notation
rules wholesale for expressions plus a type-annotation mini-grammar.
`parse_module(text)` folds a file to an `MModule` model (`MClass`/`MField`
records on the spine); `verify_module(compiled, text)` cross-checks it
against `compute_binding` using the SAME public renderers the exporter used
(`export.field_type`/`value_str_type`/`docstring_lines`) — so a
disagreement means the FILE drifted. Catches: renamed/reordered fields,
annotation drift, dropped defaults, docstring drift, GRAMMAR edits, base
swaps — each with a named refusal. Runs per export inside
`tools/check_generated.py`, both table modes. Design notes: multi-arity
alternation arms split into sibling rules (the fold's one-arity-per-rule
constraint); parents capture text SPANS over unit rules (the `sq-str`
precedent) so char-level rules never fold; the field-less-class ambiguity
is killed by the `m-body` arm split; six token rules (`rparen`/`dq-str`/
`sq-str`/`name`/`neg-int`/`pos-int`) split their trailing whitespace into a
separate fold-transparent `ws-inl` rule (space/tab, no fold entry — like
`ws`) and `m-grammar-tail`/`m-grammar-stmt` spell their trailing newline
explicitly, closing the module grammar's last identifier-shaped fail-island
(a bare `name` no longer forces the Earley completion) and the
leading-indent-after-`__binds__` gap by construction. `m-imports` remains a
benign non-failing once-per-file island. `compile/foldkit.py` (ALT,
passthrough) is the build-path-unification seed shared with the notation.


## Reserved class names

`_RESERVED_CLASS_NAMES` (`compile/pipeline/binding.py`) = `{GrammarModel, ClassVar, Literal}` ∪ the `Ir*` constructor names the notation emits — exactly the header's PascalCase bindings (lowercase `bind_module` and UPPERCASE `GRAMMAR` can never collide with a PascalCase class name). The typing-era names (`StringConstraints`, `Annotated`, `List`, `Optional`, `Union`) were trimmed 2026-07-18 — parity-neutral on the whole GT corpus. Drift-pinned against a real export.

## The compiled payload — a parsed VALUE as a module

`export_module` writes a **grammar**'s twin. `export_value(value, path, *, module=None)` (`compile/payload/`) writes a **value**'s artefact: whatever lexic parsed, as an importable module.

The artefact is four flat literals and an import of the reader:

- `TYPES` — the symbols the value names, `TYPES[0]` the "names no symbol" sentinel;
- `ORIGINS` — the module each symbol was recorded as coming from, as data;
- `STRS` — every string, interned;
- `NODES` — a flat int array. Each record is `type_id, kind, payload, *child_indices`, and every child index points at an **earlier** record, so decoding is one forward pass with no recursion.

### One projection, three targets — never a flag

Which target you get is decided by **the codomain of the reduction that produced the value**, and read off the symbols:

| target | the value | symbols | what only it can do |
|---|---|---|---|
| `classes` | a model, parsed against a grammar | that grammar's classes | `to_text()` reproduces the source |
| `ir` | a reduced value on the spine | `lexic.ir` and its submodules | the reduction, structurally |
| `plain` | builtins only | none | reads with **0 lexic modules** |

There is no target parameter and no channel per target — the projection is one function over one symbol table. A symbol is homed at the spine when the public surface exports it, else at its recorded origin when that module supplies *exactly that class* (identity, not presence — `lexic.ir.base` merely imports `Sequence`), else at an explicit `module=`, which always wins over an inferred home because it is the caller saying where the reader will look. A synthesized class reports a content-tagged module that does not import, which is exactly when `module=` is required.

### The reader is emitted, not imported and not inlined

`compile/payload/reader.py` imports no lexic, by design and by test. Importing *anything* under `lexic.` costs the package root, so a `plain` payload that reached for the installed reader would lose the property that defines it.

It is emitted **once per directory** as `payload_reader_<tag>.py`, and artefacts import `decode` from it. The tag is the digest of the sidecar's own source, so that module name IS a particular reader: an artefact cannot bind to a newer one, and two lexic versions writing into one directory leave two sidecars rather than one that silently changed underneath. Skew is impossible by construction, which is why nothing checks for it. The artefact spells the import both relatively and absolutely under a `try`/`except ImportError`, because whether it lands inside a package is not settled when it is written.

The kind space is closed by construction: `compile/payload/codec.py` declares one row per kind carrying **both** directions, so lexic cannot emit a kind the reader does not read. Rows resolve by **unique most-derived type with a tie refusing** — first-hit MRO is not safe, because the spine puts `IrSelf` ahead of a builtin base and a catch-all row would turn every string leaf into a childless unit.

### What the artefact checks when it is read

- **the digest**, over all four tables — length vector, joined text and the node ints under `blake2b`. Catches an altered table.
- **the shape**, a digest of the RULES the named symbols carry. Catches a payload read against a different compilation of its grammar, which no table check can see: the tables are intact, the names resolve, and every record decodes to a wrong value. Rules rather than modules, because a generated class's module legitimately MOVES — parsed with runtime classes tagged by content, read back against the twin, which reports its own file.
- **the origins**, for a symbol carrying no rule. Shape reads 0 for a class the caller wrote, and its module *does* survive the cycle, so a name rebound to another module's class of the same name is refused rather than decoded into the wrong class.
- **structural checks** in `decode` — a forward-only child index, a symbol id in range.

A collision is impossible by construction rather than by a reserved-name list: every imported symbol is bound under a `_sym_` alias and `SYMBOLS` maps the payload's name to it, so a rule called `decode` cannot shadow the machinery that reads it.

## One writer for every emitted module

`compile/writer.py` is the last step for both exporters.

`literal(prefix, value)` renders a table through the layout algebra, chunking a long string into adjacent literals (cut by **repr** width — a run that escapes to `\uXXXX` is six times its own length written down) and a long int as `int('…')`, since an integer literal cannot be split.

`write_module(path, source)` validates, byte-compiles and lands the module. Two rules live there rather than in either caller:

- **Whoever writes the `.py` writes the `.pyc`.** `UNCHECKED_HASH` makes bytecode outrank its source unconditionally, so leaving the `.pyc` to the first importer is how a reader gets yesterday's value.
- **Source and cache are never allowed to disagree.** The stale cache is removed first and the fresh one lands last, so every crash window is consistent: old source with no cache reads the old value, new source with no cache reads the new one, and neither reads a mixture. The staged path is unique per call, so two processes exporting into one directory cannot delete each other's scratch.

## Always-on export gates

Every `export_source` call validates in-process: the module `ast.parse`s, and its `GRAMMAR` assignment — located **structurally**, by walking the parsed module, never by splitting the source text — `load_ir`s back to an AST **equal** to `compiled.grammar`. Every `export_value` call runs the **fixpoint gate** first: `project(decode(project(v))) == project(v)`, so an artefact that cannot be read back is never written. Its limit travels with it — a wrong value is a perfectly good fixpoint of a wrong encoder — which is why the `classes` target is gated on `to_text()` instead. `tools/check_generated.py` is the corpus gate: all GT grammars × both modes must be pyright-clean and pylint-clean under DEFAULT configs, with exactly three accepted exception classes (C0103 on keyword-mangled class names `True_`/`False_`; C0302 module length on large grammars; R0801 gbnf↔abnf twin duplication — same canonical AST by design). It gates **every** emitted module: twins in both table modes, payload artefacts in their `ir` and `plain` targets, and the reader sidecar they import.
