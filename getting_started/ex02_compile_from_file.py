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
    """Compile ``list.gbnf``, parse a sample document, round-trip its items."""
    compiled = compile_from_path(GRAMMAR_PATH)

    model = compiled.parse(SAMPLE)
    # A bound field IS an attribute on the model, and a repeated one is a
    # tuple of sub-models — dump() is for serialization, not for reading
    # structure. The classes are synthesized at RUNTIME, though, so a type
    # checker cannot see their fields; getattr says that out loud. For
    # statically-typed field access, export the twin module (ex08).
    items = getattr(model, "item")
    print(f"Parsed {len(items)} items from {GRAMMAR_PATH.name}:")
    # Round-trip lines back through the grammar to show each item is itself a model.
    for line in model.to_text().splitlines():
        print("  •", line.lstrip("- "))

    assert model.to_text() == SAMPLE


if __name__ == "__main__":
    main()
