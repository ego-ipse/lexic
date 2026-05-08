"""Codegen public surface.

- build_classes_and_specs(text, *, stem, flavour="gbnf") → (classes, specs)
- codegen(text, *, stem, flavour="gbnf") → classes
- codegen_from_path(path, *, flavour=None) → classes  (infers flavour from ext)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from lexic.codegen.ir_builder import IRBuilder
from lexic.codegen.model_emitter import ModelEmitter
from lexic.grammars import adapter_for_extension, get_adapter
from lexic.ir import RuleSpec


def _emit_and_load_module(
    specs: list[RuleSpec], stem: str, *, source: str | None
) -> dict[str, type]:
    out_dir = Path(__file__).resolve().parent.parent.parent.parent / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.py"
    out_path.write_text(ModelEmitter(specs, source or f"<string:{stem}>").render())

    module_name = f"generated.{stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, out_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return {
        s.class_name: getattr(mod, s.class_name)
        for s in specs
        if hasattr(mod, s.class_name)
    }


def build_classes_and_specs(
    text: str, *, stem: str, flavour: str = "gbnf"
) -> tuple[dict[str, type], list[RuleSpec]]:
    """Parse + IR-build + emit + load. Returns (classes, specs)."""
    adapter = get_adapter(flavour)
    # Phase 1: adapter.parser.parse returns AST; pass through IRBuilder.
    # Phase 2: adapter.parser.parse returns list[RuleSpec] directly.
    ast_rules = adapter.parser.parse(text)
    specs = IRBuilder(ast_rules).build()
    classes = _emit_and_load_module(specs, stem, source=None)
    return classes, specs


def codegen(text: str, *, stem: str, flavour: str = "gbnf") -> dict[str, type]:
    """Classes-only wrapper."""
    classes, _ = build_classes_and_specs(text, stem=stem, flavour=flavour)
    return classes


def codegen_from_path(
    grammar_path: str | Path, *, flavour: str | None = None
) -> dict[str, type]:
    """Read-file wrapper; infers flavour from extension if flavour=None."""
    path = Path(grammar_path)
    if flavour is None:
        flavour = adapter_for_extension(path).name
    return codegen(path.read_text(), stem=path.stem, flavour=flavour)
