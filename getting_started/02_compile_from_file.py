"""Compile a grammar from a .gbnf file.

Loads one of the bundled ground-truth grammars from ``resources/ground_truth/``
and parses a sample document against it. ``compile_from_path`` caches by
``(path, mtime, size, flavour)`` so re-calling it is free.

Run::

    uv run python getting_started/02_compile_from_file.py
"""

from __future__ import annotations

from pathlib import Path

from lexic import compile_from_path

REPO_ROOT = Path(__file__).resolve().parent.parent
GRAMMAR_PATH = REPO_ROOT / "resources" / "ground_truth" / "list.gbnf"

SAMPLE = """\
- buy milk
- write more grammars
- ship slice B
"""


def main() -> None:
    compiled = compile_from_path(GRAMMAR_PATH)

    model = compiled.parse(SAMPLE)
    print(f"Parsed {len(model.item)} items from {GRAMMAR_PATH.name}:")
    for it in model.item:
        print("  •", it.to_text().rstrip("\n"))

    assert model.to_text() == SAMPLE


if __name__ == "__main__":
    main()
