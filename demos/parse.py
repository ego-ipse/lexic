#!/usr/bin/env python3
"""
demos/parse.py — Parse text against a built grammar package.

Usage:
    uv run demos/parse.py [package] [start_rule]

    package     Grammar package name under built/ (default: vyx)
    start_rule  Start rule for parsing (default: packet)

Text is read from stdin. Example:

    echo '!I o:inv\\ncity=Porto\\n>' | uv run demos/parse.py
    echo 'city=Porto temp=22' | uv run demos/parse.py vyx body_line
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root / "src"))


def _load_grammar_package(name: str) -> object:
    """Load a built grammar package by path, bypassing sys.path name lookup."""
    pkg_dir = _root / "built" / name
    init = pkg_dir / "__init__.py"
    if not init.exists():
        raise ImportError(f"No built package '{name}' at {pkg_dir}")
    # Register the package so relative imports inside it work
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, init, submodule_search_locations=[str(pkg_dir)]
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def main() -> None:
    args = sys.argv[1:]
    package = args[0] if args else "vyx"
    start_rule = args[1] if len(args) > 1 else "packet"

    try:
        mod = _load_grammar_package(package)
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(
            f"Make sure you have run: uv run builder.py <grammar>.gbnf {package}",
            file=sys.stderr,
        )
        sys.exit(1)

    parse = mod.parse
    ParseError = mod.ParseError

    if sys.stdin.isatty():
        print(f"Parsing with grammar '{package}', start rule '{start_rule}'")
        print("Enter text to parse (Ctrl-D when done):")

    text = sys.stdin.read()

    try:
        result = parse(text, start=start_rule)
        print(result.model_dump_json(indent=2))
    except ParseError as e:
        print(f"Parse error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
