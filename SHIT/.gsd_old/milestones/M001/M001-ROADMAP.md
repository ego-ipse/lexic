# M001: Grammar Toolkit

## Vision
A generic toolkit that takes any valid GBNF grammar and delivers: (1) Pydantic model classes with SOLID inheritance hierarchies, (2) a Lark Earley parser that turns grammar-constrained text into those typed instances, (3) round-trip serialization back to grammar text or JSON, and (4) a clean constrained LLM generation interface. Verified against all 7 ground_truth grammars.

## Slice Overview
| ID | Slice | Risk | Depends | Done | After this |
|----|-------|------|---------|------|------------|
| S01 | S01 | high | — | ✅ | python -c "from src.codegen import build; mods = build('resources/ground_truth/json_ws.gbnf'); print(mods['ObjectValue'].__bases__)" prints (<class 'src.generated.json_ws.Value'>,) |
| S02 | S02 | high | — | ✅ | python -c "from src.parser import parse; from pathlib import Path; obj = parse('{\"city\": \"Porto\"}', Path('resources/ground_truth/json_ws.gbnf')); print(type(obj).__name__)" prints ObjectValue |
| S03 | Ground Truth Gauntlet + Round-trip Verification | medium | S01, S02 | ✅ | pytest tests/test_ground_truth.py -v shows 7 grammar suites all green; JSON round-trip test passes |
| S04 | Clean Generation Interface + Integration | low | S01, S02, S03 | ✅ | MODEL_PATH=/path/to/model.gguf python -c "from src.generation import generate; result = generate('Generate JSON: ', 'resources/ground_truth/json_ws.gbnf'); print(result.to_json())" prints a JSON dict |
| S05 | S05 | high | — | ✅ | pytest tests/test_codegen.py -v — all tests pass; generated classes have correct names (no ValueAlt4), correct __bases__, and correct field types for all 6 ground_truth grammars |
| S06 | Parser Rewrite + to_text() — tests-first | high | S05 | ⬜ | pytest tests/test_parser.py -v — all tests pass; parse(text, grammar) returns a typed Root; result.to_text() reconstructs the original text exactly for all 6 ground_truth grammars |
| S07 | Cross-Grammar Printing — print_as(grammar_b) | medium | S05, S06 | ⬜ | pytest tests/test_printing.py -v — to_json() round-trips JSON exactly; print_as(grammar_b) serializes a parsed instance to any target grammar's text format |
| S08 | Generation Interface — Approach B | low | S05, S06, S07 | ⬜ | MODEL_PATH=/path/to/model.gguf python -c "from src.generation import generate; result = generate('Generate JSON: ', 'resources/ground_truth/json_ws.gbnf'); print(result.to_json())" — prints a valid JSON dict |
