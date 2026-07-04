# Getting started

Runnable examples covering the public surface of Lexic. Each script is
self-contained — `uv run python getting_started/<file>.py`.

| Script | What it shows |
|---|---|
| [`ex01_hello_grammar.py`](ex01_hello_grammar.py) | Inline GBNF → `compile_text` → parse → round-trip. The core invariant. |
| [`ex02_compile_from_file.py`](ex02_compile_from_file.py) | `compile_from_path` on a bundled ground-truth `.gbnf` (`list.gbnf`). |
| [`ex03_parse_json.py`](ex03_parse_json.py) | Parsing nested JSON via `json_ws.gbnf`; `to_text()` and `semantic_dump()`. |
| [`ex04_transpile_flavours.py`](ex04_transpile_flavours.py) | GBNF → IR AST → ABNF via `parse_grammar` + flavour singleton. |
| [`ex05_inspect_ir.py`](ex05_inspect_ir.py) | Walking `compiled.grammar` / `model.__grammar__` (`IrRule`) + emitting via either flavour. |

## What you'll learn

- **Compilation**: `compile_text(text)` and `compile_from_path(path)` both
  return a `CompiledGrammar` whose `.parse(text)` yields a `GrammarModel`
  instance for the start rule.
- **Round-trip**: every model has `to_text()` (re-emit source) and
  `to_grammar(flavour)` (re-emit the underlying grammar in any registered
  flavour).
- **Flavours**: `GBNF_FLAVOUR` and `ABNF_FLAVOUR` are singleton instances
  (`from lexic.grammars import ...`). They're `IrEmitter`s — call
  `flavour.apply(ir_node)` to render any IR node as flavour text.
- **IR**: `compiled.grammar` is the canonical `IrAst` for the whole grammar;
  `model.__grammar__` is the generated class's own `IrRule` (from the codegen
  grammar) — the shape `to_text()`/`to_grammar()` walk. See
  [.wiki/lexic/ir-shapes.md](../.wiki/lexic/ir-shapes.md).

## Further reading

- [.wiki/lexic/architecture.md](../.wiki/lexic/architecture.md) — pipeline
  walk-through.
- [.wiki/lexic/flavour-system.md](../.wiki/lexic/flavour-system.md) — how
  flavours are wired, action tuples, adding a new one.
- [resources/ground_truth/](../resources/ground_truth/) — bundled grammars
  used as fixtures.
