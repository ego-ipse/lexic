"""new_codegen — IR → Pydantic Python source.

Renamed to lexic.codegen at cutover (Slice 4).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from lexic.ir.spec import NewRuleSpec
from lexic.new_codegen.model_emitter import emit_module_source

__all__ = ["codegen", "emit_module_source"]


def _resolve_generated_dir() -> Path:
    """Locate the project's generated/ directory.

    Searches up from this file's location to the repo root, then drops down
    into generated/. Falls back to a cwd-relative `generated/` (created on
    demand) if the repo-root layout isn't found.
    """
    here = Path(__file__).resolve()
    # src/lexic/new_codegen/__init__.py → repo root four levels up
    candidate = here.parent.parent.parent.parent / "generated"
    if candidate.exists():
        return candidate
    # Fallback: cwd-relative
    cwd_candidate = Path.cwd() / "generated"
    cwd_candidate.mkdir(parents=True, exist_ok=True)
    return cwd_candidate


def codegen(specs: list[NewRuleSpec], stem: str) -> dict[str, type]:
    """Emit a Pydantic module from specs; return the dict of generated classes.

    Side effect: writes `generated/<stem>.py`. The file is regenerated on
    every call.
    """
    out_dir = _resolve_generated_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.py"
    out_path.write_text(emit_module_source(specs, stem=stem))

    module_name = f"generated.{stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, out_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load generated module from {out_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)

    return {
        s.class_name: getattr(mod, s.class_name)
        for s in specs
        if hasattr(mod, s.class_name)
    }
