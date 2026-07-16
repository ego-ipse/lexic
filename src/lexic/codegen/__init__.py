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
from lexic.ir.order import order_by_refs

__all__ = [
    "RuleBinding",
    "build_codegen_grammar",
    "codegen",
    "compute_binding",
    "emit_module_source",
    "resolve_out_dir",
]


# Named (not inline) so the multi-exception clause below doesn't read as
# Python 2's `except A, e:` name-binding form — under this project's
# requires-python (>=3.14) a bare comma list IS a tuple (PEP 758), but
# `ruff format` treats that spelling as canonical and unwraps any
# parenthesised tuple written in its place.
_RUFF_SUBPROCESS_ERRORS = (OSError, subprocess.TimeoutExpired)


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
    except _RUFF_SUBPROCESS_ERRORS:
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


def resolve_out_dir(out_dir: str | Path | None) -> Path:
    """Resolve the generated-module output directory.

    ``None`` resolves to :func:`_resolve_generated_dir`'s project-default
    ``generated/`` directory; an explicit ``out_dir`` is used as given. This
    is the sole seam callers (including ``compile.py``'s memo-key
    construction) use to agree on "where does this stem land".

    :param out_dir: Caller-supplied output directory, or ``None`` for the default.
    :returns: The resolved directory (not guaranteed to exist yet).
    """
    if out_dir is not None:
        return Path(out_dir)
    return _resolve_generated_dir()


def _write_and_load(
    source: str, stem: str, class_names: list[str], out_dir: str | Path | None = None
) -> dict[str, type]:
    """Write ``<out_dir>/<stem>.py``, import it, return its named classes.

    :param source: The module source (formatted here before writing).
    :param stem: Generated-module stem.
    :param class_names: Class names to pull out of the loaded module.
    :param out_dir: Output directory; ``None`` resolves to the project's
        ``generated/`` directory (:func:`resolve_out_dir`).
    :returns: ``{class_name: class}`` for every name the module defines.
    """
    resolved_dir = resolve_out_dir(out_dir)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    out_path = resolved_dir / f"{stem}.py"
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
    canonical: IrAst,
    codegen_grammar: IrAst,
    binding: list[RuleBinding],
    stem: str,
    out_dir: str | Path | None = None,
) -> dict[str, type]:
    """Emit a Pydantic module from the codegen grammar + binding view.

    Side effect: writes ``<out_dir>/<stem>.py``.

    :param canonical: The canonical (pre-pass) grammar — the module ``GRAMMAR``.
    :param codegen_grammar: The post-pass grammar — each class's ``__grammar__``.
    :param binding: The binding view (:func:`~lexic.codegen.binding.compute_binding`).
    :param stem: Generated-module stem.
    :param out_dir: Output directory; ``None`` resolves to the project's
        ``generated/`` directory (:func:`resolve_out_dir`).
    :returns: ``{class_name: class}`` for every generated class.
    """
    source = emit_module_source(canonical, codegen_grammar, binding, stem=stem)
    classes = _write_and_load(source, stem, [b.class_name for b in binding], out_dir)
    _rebuild_leaf_first(classes, codegen_grammar, binding)
    return classes


def _rebuild_leaf_first(
    classes: dict[str, type], codegen_grammar: IrAst, binding: list[RuleBinding]
) -> None:
    """Resolve each class's deferred annotations, referenced classes first.

    ``from __future__ import annotations`` plus forward-referenced sibling
    classes leave every field's ``IrBind`` metadata unresolved until
    ``model_rebuild``. Rebuilding a class whose field types are still
    incomplete makes pydantic build the whole dependency chain in one Python
    stack, overflowing on long ref chains. Walking the ref topology
    leaf-first (reverse of the start-first ref order) so each rebuild sees
    its dependencies already complete keeps every schema build shallow;
    mutually recursive rules resolve in any order (pydantic defers the
    back-references).

    :param classes: Generated classes by class name.
    :param codegen_grammar: The post-pass grammar carrying the ref topology.
    :param binding: The binding view mapping rule names to class names.
    """
    class_for_rule = {b.rule_name: b.class_name for b in binding}
    ref_ordered = list(order_by_refs(codegen_grammar).rules)
    for rule in reversed(ref_ordered):
        cls = classes.get(class_for_rule.get(str(rule.name), ""))
        if cls is not None:
            cls.model_rebuild()
