"""GBNF → Pydantic codegen.

codegen(grammar_path) parses a .gbnf file, classifies each rule,
and writes an importable Python module to generated/<stem>.py.

No exec() anywhere. eval() only for resolving type-annotation strings.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from .parser import parse_gbnf
from .emitter import build_specs, topo_sort, render_source


def codegen(grammar_path: str | Path) -> dict[str, type]:
    """Parse a GBNF file, generate Pydantic models, return dict[name, type]."""
    grammar_path = Path(grammar_path)
    rules = parse_gbnf(grammar_path.read_text())

    specs = topo_sort(build_specs(rules))

    # Write source file.
    out_dir = Path(__file__).resolve().parent.parent.parent / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = grammar_path.stem
    out_path = out_dir / f"{stem}.py"
    out_path.write_text(render_source(specs, str(grammar_path)))

    # Import the generated module and collect the classes.
    module_name = f"generated.{stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]

    mod = importlib.import_module(module_name)
    return {s.name: getattr(mod, s.name) for s in specs if hasattr(mod, s.name)}


# Keep the old name as an alias.
generate_classes = codegen
