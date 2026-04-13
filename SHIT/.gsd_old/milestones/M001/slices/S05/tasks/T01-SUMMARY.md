---
id: T01
parent: S05
milestone: M001
key_files:
  - tests/test_codegen.py
  - tests/test_grammar_toolkit.py
key_decisions:
  - Naming contract for all 6 grammars locked in tests: ValueLiteral for arm-4 literal group, TermExpr for arm-2 of arithmetic term, StatementIdentifier2 for collision dedup, camelCase splitting for SingleLineCommentStatement/MultiLineCommentStatement/ForInitDataType/ForInitIdentifier
  - Deleted test_grammar_toolkit.py — it mixed parse()/to_text()/to_json() concerns that belong to S06/S07 and is not a valid codegen contract
duration: 
verification_result: passed
completed_at: 2026-04-13T18:56:08.366Z
blocker_discovered: false
---

# T01: Write tests/test_codegen.py (27 tests, all fail on current code) and delete test_grammar_toolkit.py

**Write tests/test_codegen.py (27 tests, all fail on current code) and delete test_grammar_toolkit.py**

## What Happened

Read all 6 ground_truth grammars (json_ws.gbnf, arithmetic.gbnf, c.gbnf, chess.gbnf, japanese.gbnf, list.gbnf) and the current codegen.py to understand the AST structure and existing naming behaviour. Confirmed the current code fails at build() call time with ModuleNotFoundError (generated code string imports `from src.base import GrammarNode` which has no module yet).

Wrote tests/test_codegen.py with 27 contract tests covering all 6 grammars. Tests only exercise the public `build(grammar_path) -> dict[str, type]` API — no parse(), to_text(), or to_json(). Key assertion groups:

1. `test_no_alt_n_names` (parametrized × 6): asserts no class name matches r'.+Alt\\d+$' — fails currently because the code produces ValueAlt4, TermAlt2, StatementAlt0..6, etc.
2. `test_root_present` (parametrized × 6): asserts Root is always generated.
3. json_ws exact name checks: ObjectValue, ArrayValue, StringValue, NumberValue, ValueLiteral (arm 4 is a SequenceNode with first node being an AlternativeNode of literals → Literal suffix).
4. json_ws SOLID hierarchy: Value is abstract base (no required fields), all arm classes subclass Value.
5. json_ws field type: ObjectValue must have a field typed as the Object class (not Union).
6. json_ws root: Root subclasses Object (root ::= object).
7. arithmetic: IdentTerm, NumTerm, TermExpr — Term is abstract base.
8. c.gbnf statement: 9 semantic names including collision dedup (StatementIdentifier2) and camelCase splitting (SingleLineCommentStatement, MultiLineCommentStatement). Statement is abstract base.
9. c.gbnf for_init: ForInitDataType, ForInitIdentifier — ForInit is abstract base.
10. chess / japanese: identical value structure → same 5 arm names as json_ws, Value is abstract base.
11. list.gbnf: Root present, no AltN names.

Deleted tests/test_grammar_toolkit.py as instructed (it conflated codegen/parser/serialization concerns and imported parse() which is out of scope for S05).

All 27 tests fail with ModuleNotFoundError on the current pre-rewrite code. Zero tests pass, satisfying the tests-first gate.

## Verification

pytest tests/test_codegen.py -v 2>&1 | grep -E '(FAILED|ERROR|passed|failed)' — all 27 tests FAILED with ModuleNotFoundError. Zero-passed assertion also confirmed: python -c assert zero passed returned 'ASSERTION OK: 0 tests passed, as required for tests-first gate'.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `pytest tests/test_codegen.py -v 2>&1 | grep -E '(FAILED|ERROR|passed|failed)' | wc -l` | 0 | ✅ pass — 27 FAILED lines, 0 passed | 150ms |
| 2 | `python -c "import re,subprocess; r=subprocess.run(['pytest','tests/test_codegen.py','--tb=no','-q'],capture_output=True,text=True); assert 'passed' not in r.stdout or int(re.search(r'(\d+) passed',r.stdout).group(1))==0"` | 0 | ✅ pass — zero-passed assertion satisfied | 140ms |

## Deviations

none

## Known Issues

none

## Files Created/Modified

- `tests/test_codegen.py`
- `tests/test_grammar_toolkit.py`
