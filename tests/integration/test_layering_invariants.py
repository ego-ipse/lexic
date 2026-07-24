"""Layering invariants enforced via static grep / AST over src/lexic/."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "lexic"


def grep(directory: Path, needle: str) -> list[Path]:
    """Return list of .py files in directory containing needle."""
    return [p for p in directory.rglob("*.py") if needle in p.read_text()]


def module_name(path: Path) -> str:
    """The dotted module name of a file under ``src/`` (``src/lexic/a/b.py`` →
    ``lexic.a.b``)."""
    return ".".join(path.relative_to(SRC.parent).with_suffix("").parts)


COMPILE_PKG = SRC / "compile"
COMPILE_SEAM = COMPILE_PKG / "__init__.py"


def runtime_module_files() -> list[Path]:
    """The runtime seam-scope: top-level runtime modules plus the compile package.

    ``compile.py`` became the ``lexic.compile`` package; the package (its
    ``__init__``) is now the sole runtime seam onto the engine, so the seam
    invariants scan the top-level modules together with every module inside
    ``compile/``.
    """
    return sorted(SRC.glob("*.py")) + sorted(COMPILE_PKG.rglob("*.py"))


def from_imports(tree: ast.AST) -> "list[tuple[str, str]]":
    """Every absolute ``from <module> import <name>`` as ``(module, name)``."""
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.extend((node.module, alias.name) for alias in node.names)
    return out


def test_no_cross_module_private_imports_in_src():
    """No ``from <module> import _name`` crosses a module boundary in ``src/``.

    A name two modules share is that module's public surface — it is renamed
    public at its defining module (the underscore dropped), never imported
    across the boundary. Permanent enforcement of directive 4.
    """
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        mod = module_name(path)
        for module, name in from_imports(ast.parse(path.read_text())):
            if module != mod and name.startswith("_"):
                offenders.append(f"{mod}: from {module} import {name}")
    assert not offenders, f"cross-module private imports: {offenders}"


LICENSED_PARSING = frozenset({"lexic.parsing", "lexic.parsing.earley.reduce"})
"""The engine imports a ``lexic.compile`` module may make: the package root
(the product entries + fold toolkit) and the one licensed submodule
``lexic.parsing.earley.reduce`` — the reduce channel (``Reducer`` sentinels,
``Yield``/``YIELD``) the notation and loader need. Every other
``lexic.parsing`` submodule (``.fold``/``.pda``/``.products``/``.earley.*``)
stays off-limits."""

GRAMMARS_PARSING = frozenset({"lexic.parsing.earley.reduce"})
"""The one engine import a ``lexic.grammars`` module may make — the reduce
channel its flavour reducers are built from. The package root (product
entries, fold toolkit) is compile-only."""


def _engine_imports(path: Path) -> list[str]:
    """Every ``lexic.parsing`` module ``path`` imports, in either import form."""
    tree = ast.parse(path.read_text())
    mods = [m for m, _ in from_imports(tree)]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.extend(alias.name for alias in node.names)
    return [m for m in mods if m == "lexic.parsing" or m.startswith("lexic.parsing.")]


def _engine_licence(path: Path) -> frozenset[str]:
    """The engine imports ``path`` is licensed to make (empty = none at all)."""
    if path.is_relative_to(COMPILE_PKG):
        return LICENSED_PARSING
    if path.is_relative_to(SRC / "grammars"):
        return GRAMMARS_PARSING
    return frozenset()


def test_runtime_imports_parsing_are_compile_only_and_licensed():
    """Every module under ``src/lexic`` honors its engine-import licence.

    The scan rglobs the WHOLE tree (future packages are covered by
    construction, not by remembering to extend a glob): the engine imports
    itself freely; ``lexic.compile`` modules may import
    :data:`LICENSED_PARSING`; ``lexic.grammars`` modules may import the
    :data:`GRAMMARS_PARSING` reduce channel; every other module may not
    import ``lexic.parsing`` at all. Enforcement of directive 1.
    """
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path.is_relative_to(SRC / "parsing"):
            continue
        licence = _engine_licence(path)
        for module in _engine_imports(path):
            if module in licence:
                continue
            rel = path.relative_to(SRC)
            allowed = f"may import only {sorted(licence)}" if licence else "may not"
            offenders.append(f"{rel}: imports {module} ({allowed})")
    assert not offenders, f"parsing import-layering violations: {offenders}"


def test_ir_does_not_import_grammars_or_parsing():
    """lexic.ir should be a leaf module, not importing lexic.grammars or the
    engine (lexic.parsing)."""
    bad = grep(SRC / "ir", "from lexic.grammars") + grep(
        SRC / "ir", "from lexic.parsing"
    )
    assert not bad, f"lexic.ir leaks: {bad}"


def test_no_src_module_imports_pydantic():
    """No module anywhere in ``src/`` imports pydantic.

    Models live on the IrNamedTuple record spine, not pydantic; the dependency
    is gone from the runtime entirely.
    """
    bad = grep(SRC, "from pydantic") + grep(SRC, "import pydantic")
    assert not bad, f"pydantic imported in src: {bad}"


def test_engine_package_does_not_import_grammars():
    """The Earley engine (lexic.parsing) is a leaf w.r.t. grammars.

    It reads and writes IR only; the flavour reducers live in lexic.grammars
    and the model fold is invoked from the compile seam, never the reverse.
    """
    engine = SRC / "parsing"
    bad = grep(engine, "from lexic.grammars") + grep(engine, "import lexic.grammars")
    assert not bad, f"lexic.parsing leaks: {bad}"


def test_engine_fold_seam_is_plain_data():
    """The instance fold receives plain data: the engine (lexic.parsing,
    fold.py included) never imports pydantic, and never sees the RuleSpec
    shape — constructors arrive as opaque callables, modes as the
    lexic.ir.bind vocabulary (parsing → ir is a legal edge)."""
    engine = SRC / "parsing"
    bad = (
        grep(engine, "from pydantic")
        + grep(engine, "import pydantic")
        + grep(engine, "from lexic.ir.spec")
        + grep(engine, "import lexic.ir.spec")
    )
    assert not bad, f"the fold seam leaks beyond plain data: {bad}"


def test_wrapper_models_module_is_gone():
    """Sanity: parsing/models.py (the --f<idx> wrapper bridge) is deleted and
    unreferenced — parsing/fold.py is its positional successor."""
    assert not (SRC / "parsing" / "models.py").exists()
    for p in SRC.rglob("*.py"):
        assert "lexic.parsing.models" not in p.read_text(), f"{p}"


def test_engine_imported_by_runtime_only_via_compile_seam():
    """Runtime modules outside the compile package never import the engine.

    The compile package is the single sanctioned runtime consumer of the engine
    (its own modules' engine imports are governed by
    :func:`test_runtime_imports_parsing_are_compile_only_and_licensed`);
    base.py / parse.py / generate.py must reach parsing behaviour through the
    package, not by importing lexic.parsing directly.
    """
    offenders = []
    for p in runtime_module_files():
        if p.is_relative_to(COMPILE_PKG):
            continue
        for line in p.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("from lexic.parsing", "import lexic.parsing")):
                offenders.append(f"{p.relative_to(SRC)}: {stripped}")
    assert not offenders, (
        f"runtime bypasses the compile package engine seam: {offenders}"
    )


def test_compile_package_seam_is_init_only():
    """Outside the compile package, only ``lexic.compile`` (the ``__init__``) is imported.

    The compile package is the sole runtime seam (settled 1): every other
    ``src/`` module reaches it via ``from lexic.compile import ...`` (the
    package root), never a submodule (``lexic.compile.passes`` / ``.binding`` /
    ``.synthesis``). Intra-package imports are unrestricted.
    """
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if path.is_relative_to(COMPILE_PKG):
            continue
        tree = ast.parse(path.read_text())
        mods = [m for m, _ in from_imports(tree)]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.extend(alias.name for alias in node.names)
        for module in mods:
            if module.startswith("lexic.compile."):
                offenders.append(f"{module_name(path)}: {module}")
    assert not offenders, f"compile subpackage imported outside the seam: {offenders}"


def test_flavours_module_is_gone():
    """Sanity: the old flavours module has been deleted and is not imported."""
    assert not (SRC / "grammars" / "flavours.py").exists()
    for p in SRC.rglob("*.py"):
        content = p.read_text()
        assert "from lexic.grammars.flavours" not in content, f"{p}"
        assert "import lexic.grammars.flavours" not in content, f"{p}"


def test_legacy_atom_modules_are_gone():
    """Sanity: the old atom modules have been deleted and are not imported."""
    for name in ("atoms.py", "builder.py", "classify.py", "convert.py", "protocols.py"):
        assert not (SRC / "ir" / name).exists(), f"ir/{name} still present"


def test_no_new_gbnf_or_new_codegen_residual():
    """Sanity: no residual imports of the retired new_gbnf or new_codegen packages."""
    this_file = Path(__file__).resolve()
    for p in list(SRC.rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
        if p == this_file:
            continue
        content = p.read_text()
        assert "lexic.grammars.new_gbnf" not in content, f"{p}: residual new_gbnf"
        assert "lexic.new_codegen" not in content, f"{p}: residual new_codegen"


def test_utils_package_is_gone():
    """The whole lexic.utils package died in Task 6, unreferenced anywhere."""
    assert not (SRC / "utils").exists()
    this_file = Path(__file__).resolve()
    for p in list(SRC.rglob("*.py")) + list((ROOT / "tests").rglob("*.py")):
        if p == this_file:
            continue
        content = p.read_text()
        assert "from lexic.utils" not in content, f"{p}: residual lexic.utils import"
        assert "import lexic.utils" not in content, f"{p}: residual lexic.utils import"


def test_retired_ir_modules_are_gone():
    """The RuleSpec/derive/emit/naming/topo modules died in Task 6.

    Their successors: the binding view + passes (``lexic.compile``), flavour
    ``apply`` (emission), and ``lexic.ir.order`` (rule ordering).
    """
    for name in ("derive.py", "spec.py", "emit.py", "naming.py", "topo.py"):
        assert not (SRC / "ir" / name).exists(), f"ir/{name} still present"
    for p in SRC.rglob("*.py"):
        content = p.read_text()
        for module in (
            "lexic.ir.derive",
            "lexic.ir.spec",
            "lexic.ir.emit",
            "lexic.ir.naming",
            "lexic.ir.topo",
        ):
            assert module not in content, f"{p}: residual {module} reference"


def test_hybrid_pda_modules_are_swept_by_the_leaf_invariant():
    """The core substrate, analysis, clone compiler and runtime modules exist
    inside lexic.parsing.pda and carry no grammars import.

    ``test_engine_package_does_not_import_grammars`` already greps every
    ``.py`` under ``lexic.parsing`` generically (``rglob``), so these modules
    are covered by accident of directory placement; this pins that placement
    (and the absence of the forbidden import) explicitly by name, so a future
    reshuffle can't silently drop them from scope.
    """
    pda = SRC / "parsing" / "pda"
    for rel in (
        "core/charsets.py",
        "analysis/analysis.py",
        "compiler/clones.py",
        "runtime/runtime.py",
    ):
        path = pda / rel
        assert path.exists(), f"{rel} missing from lexic.parsing.pda"
        content = path.read_text()
        assert "from lexic.grammars" not in content, f"{rel} imports lexic.grammars"


def test_earley_never_imports_pda():
    """The Earley engine (``parsing/earley``) never imports the PDA package.

    The intra-``parsing`` arrow runs one way — ``pda → earley`` only. Island-
    interior delegation (Task 6.2) is threaded through this seam without
    reversing it: the delegate table is an opaque-callable slot the kernel
    invokes (``Kernel.delegates`` / :data:`~lexic.parsing.earley.kernel.Delegate`),
    populated by ``pda`` and passed in through :mod:`lexic.parsing.pda.runtime.islands`;
    the kernel itself imports nothing from ``pda`` and stays PDA-agnostic.
    """
    earley = SRC / "parsing" / "earley"
    bad = grep(earley, "from lexic.parsing.pda") + grep(
        earley, "import lexic.parsing.pda"
    )
    assert not bad, f"earley imports pda (delegation must stay opaque): {bad}"


def test_pda_entry_points_imported_only_via_compile_seam():
    """Only the compile seam imports the PDA entry points among runtime modules.

    ``pda.clones``/``pda.runtime`` are sub-paths of ``lexic.parsing``, so
    ``test_engine_imported_by_runtime_only_via_compile_seam``'s ``"from
    lexic.parsing"`` prefix check already covers them generically; this pins
    that coverage explicitly for the PDA modules by name. Post-Task-2 no runtime
    module imports them at all — the products own the PDA behind the root API.
    """
    offenders = []
    for p in runtime_module_files():
        if p == COMPILE_SEAM:
            continue
        for line in p.read_text().splitlines():
            stripped = line.strip()
            if not any(
                mod in stripped
                for mod in ("pda.clones", "pda.runtime", "pda.reduce_runtime")
            ):
                continue
            if stripped.startswith(("from lexic.parsing", "import lexic.parsing")):
                offenders.append(f"{p.name}: {stripped}")
    assert not offenders, f"PDA entry points bypass the compile.py seam: {offenders}"


def test_codegen_package_is_gone():
    """Sanity: the codegen package is deleted and imported nowhere in src.

    Its jobs live on the ``lexic.compile`` package (binding view + passes +
    runtime synthesis).
    """
    assert not (SRC / "codegen").exists()
    for p in SRC.rglob("*.py"):
        content = p.read_text()
        assert "lexic.codegen" not in content, f"{p}: residual lexic.codegen"
