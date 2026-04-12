#!/usr/bin/env python3
"""
demos/chat.py — Interactive constrained generation chat loop.

Usage:
    MODEL_PATH=/path/to/model.gguf uv run demos/chat.py [grammar_file] [package]

    grammar_file  Path to .gbnf file (default: grammar.gbnf)
    package       Grammar package for parsing responses (default: stem of grammar_file)

Environment:
    MODEL_PATH    Path to GGUF model file (required)

Each turn: enter a prompt, the model generates a grammar-constrained response,
which is then parsed and pretty-printed as JSON.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root / "src"))
from generate import generate


def _load_grammar_package(name: str) -> object:
    """Load a built grammar package by path, bypassing sys.path name lookup."""
    pkg_dir = _root / "resources" / name
    init = pkg_dir / "__init__.py"
    if not init.exists():
        raise ImportError(f"No built package '{name}' at {pkg_dir}")
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, init, submodule_search_locations=[str(pkg_dir)]
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


def main() -> None:
    model_path = os.environ.get("MODEL_PATH")
    if not model_path:
        print("Error: set MODEL_PATH to a GGUF model file", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]
    grammar_file = Path(args[0]) if args else Path("grammar.gbnf")
    package = args[1] if len(args) > 1 else grammar_file.stem

    if not grammar_file.exists():
        print(f"Error: grammar file not found: {grammar_file}", file=sys.stderr)
        sys.exit(1)

    try:
        mod = _load_grammar_package(package)
        parse = mod.parse
        ParseError = mod.ParseError
    except ImportError as e:
        print(f"Warning: {e}", file=sys.stderr)
        print("Responses will be printed as raw text only.", file=sys.stderr)
        parse = None
        ParseError = None

    print(f"Chat — grammar: {grammar_file}, model: {Path(model_path).name}")
    print("Type a prompt and press Enter. Ctrl-C or Ctrl-D to quit.\n")

    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not prompt:
            continue

        try:
            response = generate(model_path, prompt, grammar_file)
        except Exception as e:
            print(f"Generation error: {e}", file=sys.stderr)
            continue

        print(f"Model (raw): {response!r}")

        if parse is not None:
            try:
                result = parse(response)
                print(f"Model (parsed):\n{result.model_dump_json(indent=2)}")
            except Exception:
                pass

        print()


if __name__ == "__main__":
    main()
