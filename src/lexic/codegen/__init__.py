"""codegen — IR → Pydantic Python source.

Renamed to lexic.codegen at cutover (Slice 4).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from ruff import find_ruff_bin

from lexic.codegen.binding import RuleBinding, compute_binding
from lexic.codegen.model_emitter import emit_module_source
from lexic.codegen.passes import build_codegen_grammar
from lexic.ir.nodes import IrAst

__all__ = [
    "RuleBinding",
    "build_codegen_grammar",
    "codegen",
    "compute_binding",
    "emit_module_source",
]


def _ruff_format(source: str) -> str:
    ruff = find_ruff_bin()
    try:
        fixed = subprocess.run(
            [ruff, "check", "--fix", "-"],
            input=source,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if fixed.returncode in (0, 1):
            source = fixed.stdout or source
        result = subprocess.run(
            [ruff, "format", "-"],
            input=source,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
    except OSError, subprocess.TimeoutExpired:
        pass
    return source


def _resolve_generated_dir() -> Path:
    """Locate the project's generated/ directory.

    Searches up from this file's location to the repo root, then drops down
    into generated/. Falls back to a cwd-relative `generated/` (created on
    demand) if the repo-root layout isn't found.
    """
    here = Path(__file__).resolve()
    # src/lexic/codegen/__init__.py → repo root four levels up
    candidate = here.parent.parent.parent.parent / "generated"
    if candidate.exists():
        return candidate
    # Fallback: cwd-relative
    cwd_candidate = Path.cwd() / "generated"
    cwd_candidate.mkdir(parents=True, exist_ok=True)
    return cwd_candidate


def _write_and_load(source: str, stem: str, class_names: list[str]) -> dict[str, type]:
    """Write ``generated/<stem>.py``, import it, return its named classes.

    :param source: The module source (formatted here before writing).
    :param stem: Generated-module stem.
    :param class_names: Class names to pull out of the loaded module.
    :returns: ``{class_name: class}`` for every name the module defines.
    """
    out_dir = _resolve_generated_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.py"
    out_path.write_text(_ruff_format(source))

    module_name = f"generated.{stem}"
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, out_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load generated module from {out_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)

    return {name: getattr(mod, name) for name in class_names if hasattr(mod, name)}


def codegen(
    canonical: IrAst, codegen_grammar: IrAst, binding: list[RuleBinding], stem: str
) -> dict[str, type]:
    """Emit a Pydantic module from the codegen grammar + binding view.

    Side effect: writes ``generated/<stem>.py``.

    :param canonical: The canonical (pre-pass) grammar — the module ``GRAMMAR``.
    :param codegen_grammar: The post-pass grammar — each class's ``__grammar__``.
    :param binding: The binding view (:func:`~lexic.codegen.binding.compute_binding`).
    :param stem: Generated-module stem.
    :returns: ``{class_name: class}`` for every generated class.
    """
    source = emit_module_source(canonical, codegen_grammar, binding, stem=stem)
    classes = _write_and_load(source, stem, [b.class_name for b in binding])
    # Resolve deferred annotations (``from __future__ import annotations`` plus
    # forward-referenced sibling classes) so each field's ``IrBind`` metadata is
    # readable — base.py drives ``to_text``/``semantic_dump`` off it.
    for cls in classes.values():
        cls.model_rebuild()
    return classes
