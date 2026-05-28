"""Parse JSON via a GBNF grammar.

Uses the bundled ``json_ws.gbnf`` to compile a JSON parser. Demonstrates two
useful APIs on :class:`GrammarModel`:

- ``to_text()`` — lossless round-trip back to the source text.
- ``semantic_dump()`` — drops non-semantic fields (here: whitespace ``ws``)
  and returns the structural payload as a dict.

Run::

    uv run python getting_started/03_parse_json.py
"""

from __future__ import annotations

import json
from pathlib import Path
from pprint import pprint

from lexic import compile_from_path

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAMMAR_PATH = REPO_ROOT / "resources" / "ground_truth" / "json_ws.gbnf"

SAMPLE = (
    '{"project": {"name": "Lexic", "version": 0, "ships": true}, '
    '"deps": [{"name": "lark", "extras": ["regex", "standalone"]}, '
    '{"name": "pydantic", "extras": []}], '
    '"meta": {"tags": ["grammar", "ir", "transpiler"], '
    '"owners": {"primary": "mika", "backup": null}}}'
)


def main() -> None:
    compiled = compile_from_path(GRAMMAR_PATH)

    model = compiled.parse(SAMPLE)
    print("Original:")
    print(" ", SAMPLE)

    round_tripped = model.to_text()
    print("\nRound-trip:")
    print(" ", round_tripped)
    assert round_tripped == SAMPLE

    # Cross-check the parse against Python's json module — same structure,
    # same values.
    print("\njson.loads(round_tripped):")
    print(" ", json.loads(round_tripped))

    print("\nsemantic_dump (drops non-semantic 'ws' nodes):")
    pprint(model.semantic_dump(), indent=2, width=88)


if __name__ == "__main__":
    main()
