# Getting started

Runnable examples covering the public surface of Lexic. Run each **from the
repository root, as a module** — `uv run python -m getting_started.<name>`.

| Script | What it shows |
|---|---|
| [`ex01_hello_grammar.py`](ex01_hello_grammar.py) | Inline GBNF → `compile_text` → parse → round-trip. The core invariant. |
| [`ex02_compile_from_file.py`](ex02_compile_from_file.py) | `compile_from_path` on a bundled ground-truth `.gbnf` (`list.gbnf`). |
| [`ex03_parse_json.py`](ex03_parse_json.py) | Parsing nested JSON via `json_ws.gbnf`; `to_text()` and `semantic_dump()`. |
| [`ex04_transpile_flavours.py`](ex04_transpile_flavours.py) | GBNF → IR AST → ABNF and EBNF via `parse_grammar` + the flavour singletons. |
| [`ex05_inspect_ir.py`](ex05_inspect_ir.py) | Walking `compiled.grammar` / `model.__grammar__` (`IrRule`) + emitting via either flavour. |
| [`ex06_token_grammar.py`](ex06_token_grammar.py) | Token grammars: an `IrTokenizer` + `<think>…</think>` GBNF → parse token-granular, round-trip, and the `constrain()` next-token mask (capabilities A/B/C). |
| [`ex07_constrained_generation.py`](ex07_constrained_generation.py) | A full generation loop: mask → pick → `push` on one live chart until the grammar `accepts()`. Any vocab drives any char grammar. |
| [`ex08_twin_module.py`](ex08_twin_module.py) | `export_module`/`export_source` → an importable twin; lexic parses its own export (`parse_module`/`verify_module`); checked construction from the imported classes. |
| [`ex09_json_reducer.py`](ex09_json_reducer.py) | `parse_reduced` + the json reducer kit: a document folds to typed IR values (`IrMap`/`IrTuple`/`IrInt`/`IrNone`) — no model classes. |
| [`ex10_templating.py`](ex10_templating.py) | `template(compiled, MapShape, spec)`: extract two paths from a document, skip the rest as raw spans. Grammar-native — the same shape fits json.gbnf and json.abnf. |
| [`ex11_hf_tokenizer.py`](ex11_hf_tokenizer.py) | The HF `tokenizer.json` story end to end: reduce with lexic's own json, lift vocab/merges/specials, `IrTokenizer.from_merges`, exact BPE `tokenize()`. |
| [`ex12_real_think_flow.py`](ex12_real_think_flow.py) | The `<think>` flow against a REAL 151k model vocabulary: `ext.API.hf` fetches, `lexic.api.json_tokenizer` reads, `think.gbnf` parses and constrains. Skips cleanly when the fixture is absent. |

## What you'll learn

- **Compilation**: `compile_text(text)` and `compile_from_path(path)` both
  return a `CompiledGrammar` whose `.parse(text)` yields a `GrammarModel`
  instance for the start rule.
- **Round-trip**: every model has `to_text()` (re-emit source) and
  `to_grammar(flavour)` (re-emit the underlying grammar in any registered
  flavour).
- **Flavours**: `GBNF_FLAVOUR`, `ABNF_FLAVOUR` and `EBNF_FLAVOUR` are singleton instances
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
