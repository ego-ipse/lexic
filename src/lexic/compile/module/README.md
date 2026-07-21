# `compile/module` — the twin-module surface

A compiled grammar's **importable twin**: the emit half writes it, the
parse-back half re-reads it and cross-checks it against the compiler's own
binding view — so drift between compiler and artifact is a test failure, not
a surprise.

## `export.py` — the emit half

`export_source(compiled)` renders the twin module text; `export_module(
compiled, path, *, inline_tables=False)` is the **sole file-write seam**.
The layout: docstring = the rule in the source flavour (flat emission — the
docstring fill-wrap on the layout algebra owns the line breaks); typed
defaults-last fields; `GRAMMAR` in the notation via `emit_ir`; a module-end
`bind_module(GRAMMAR, globals())` call, or inline `__grammar__`/`__binds__`
ClassVars under `inline_tables=True`. Always-on gates: `ast.parse` +
`load_ir(GRAMMAR) == compiled.grammar`. Formatting is `lexic.ir.layout` —
no `ruff`, no subprocess — and a fresh export is an isort + ruff-format
**fixpoint**. `docstring_lines` / `field_type` / `value_str_type` are public
because `selfgrammar` recomputes with exactly these renderers.

## `selfgrammar.py` — the parse-back half

`module_grammar()` is the grammar of generated modules: a STRICT statement
skeleton (required newline/indent literals) with the notation rules embedded
wholesale and a type-annotation mini-grammar. The skeleton is authored so
every decision is predictive — body lines split on their FIRST char
(indented vs the `__binds__` keyword; past the indent, a field name is never
underscore-led while `__grammar__` is), no rule ends on a loop (a trailing
loop with empty soft FOLLOW islands), and each inline-binds entry consumes
the next line's leading indent so the loop exit peeks `}`. One documented
gap: a line that can only follow an embedded expression starts at its
keyword — the expression's trailing noise swallows the leading indent.

`parse_module(text)` folds a twin into `MModule`/`MClass`/`MField` records;
`verify_module(compiled, text)` is the L2 cross-check — the expected
docstrings, fields, bases and inline tables are recomputed with the SAME
renderers the exporter used, so any disagreement means the file drifted. It
runs per export inside `tools/check_generated.py`.
