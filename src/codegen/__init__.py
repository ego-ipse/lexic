"""GBNF → Pydantic codegen.

codegen(grammar_path) parses a .gbnf file, builds a RuleSpec IR,
and writes an importable Python module to generated/<stem>.py.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

from .ir_builder import IRBuilder
from .model_emitter import ModelEmitter
from .parser import parse_gbnf


def codegen(grammar_path: str | Path) -> dict[str, type]:
    """Parse a GBNF file, generate Pydantic models, return dict[name, type]."""
    grammar_path = Path(grammar_path)
    rules = parse_gbnf(grammar_path.read_text())
    specs = IRBuilder(rules).build()

    out_dir = Path(__file__).resolve().parent.parent.parent / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{grammar_path.stem}.py"
    out_path.write_text(ModelEmitter(specs, str(grammar_path)).render())

    module_name = f"generated.{grammar_path.stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]
    mod = importlib.import_module(module_name)
    return {s.class_name: getattr(mod, s.class_name) for s in specs if hasattr(mod, s.class_name)}


generate_classes = codegen
