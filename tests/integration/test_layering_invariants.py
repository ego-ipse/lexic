"""Layering invariants enforced via static grep over src/lexic/."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "lexic"


def _grep(directory: Path, needle: str) -> list[Path]:
    """Return list of .py files in directory containing needle."""
    return [p for p in directory.rglob("*.py") if needle in p.read_text()]


def test_ir_does_not_import_grammars_parsing_codegen():
    """lexic.ir should be a leaf module, not importing lexic.grammars, the
    engine (lexic.parsing), or lexic.codegen."""
    bad = (
        _grep(SRC / "ir", "from lexic.grammars")
        + _grep(SRC / "ir", "from lexic.parsing")
        + _grep(SRC / "ir", "from lexic.codegen")
    )
    assert not bad, f"lexic.ir leaks: {bad}"


def test_codegen_does_not_import_grammars_or_parsing():
    """lexic.codegen should be a leaf module, not importing lexic.grammars or the engine."""
    bad = _grep(SRC / "codegen", "from lexic.grammars") + _grep(
        SRC / "codegen", "from lexic.parsing"
    )
    assert not bad, f"lexic.codegen leaks: {bad}"


def test_engine_package_does_not_import_grammars_or_codegen():
    """The Earley engine (lexic.parsing) is a leaf w.r.t. grammars/codegen.

    It reads and writes IR only; the flavour reducers live in lexic.grammars
    and the model fold is invoked from the compile seam, never the reverse.
    """
    engine = SRC / "parsing"
    bad = (
        _grep(engine, "from lexic.grammars")
        + _grep(engine, "import lexic.grammars")
        + _grep(engine, "from lexic.codegen")
        + _grep(engine, "import lexic.codegen")
    )
    assert not bad, f"lexic.parsing leaks: {bad}"


def test_engine_fold_seam_is_plain_data():
    """The instance fold receives plain data: the engine (lexic.parsing,
    fold.py included) never imports pydantic, and never sees the RuleSpec
    shape — constructors arrive as opaque callables, modes as the
    lexic.ir.bind vocabulary (parsing → ir is a legal edge)."""
    engine = SRC / "parsing"
    bad = (
        _grep(engine, "from pydantic")
        + _grep(engine, "import pydantic")
        + _grep(engine, "from lexic.ir.spec")
        + _grep(engine, "import lexic.ir.spec")
    )
    assert not bad, f"the fold seam leaks beyond plain data: {bad}"


def test_wrapper_models_module_is_gone():
    """Sanity: parsing/models.py (the --f<idx> wrapper bridge) is deleted and
    unreferenced — parsing/fold.py is its positional successor."""
    assert not (SRC / "parsing" / "models.py").exists()
    for p in SRC.rglob("*.py"):
        assert "lexic.parsing.models" not in p.read_text(), f"{p}"


def test_engine_imported_by_runtime_only_via_compile_seam():
    """Top-level runtime modules import the engine only through compile.py.

    ``compile.py`` is the single sanctioned runtime seam onto the engine;
    base.py / parse.py / generate.py must reach parsing behaviour through it,
    not by importing lexic.parsing directly.
    """
    offenders = []
    for p in SRC.glob("*.py"):  # top-level modules only, not subpackages
        if p.name == "compile.py":
            continue
        for line in p.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("from lexic.parsing", "import lexic.parsing")):
                offenders.append(f"{p.name}: {stripped}")
    assert not offenders, f"runtime bypasses the compile.py engine seam: {offenders}"


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

    Their successors: the binding view + passes (``lexic.codegen``), flavour
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
    """charsets/analysis/pda_tables/pda_kernel (2026-07-05 hybrid-PDA effort)
    exist inside lexic.parsing and carry no grammars/codegen import.

    ``test_engine_package_does_not_import_grammars_or_codegen`` already
    greps every ``.py`` under ``lexic.parsing`` generically (``rglob``), so
    these modules are covered by accident of directory placement; this pins
    that placement (and the absence of the two forbidden imports) explicitly
    by name, so a future reshuffle can't silently drop them from scope.
    """
    engine = SRC / "parsing"
    for name in ("charsets.py", "analysis.py", "pda_tables.py", "pda_kernel.py"):
        path = engine / name
        assert path.exists(), f"{name} missing from lexic.parsing"
        content = path.read_text()
        assert "from lexic.grammars" not in content, f"{name} imports lexic.grammars"
        assert "from lexic.codegen" not in content, f"{name} imports lexic.codegen"


def test_pda_entry_points_imported_only_via_compile_seam():
    """Only compile.py imports the PDA entry points among top-level runtime modules.

    ``pda_tables``/``pda_kernel`` are sub-paths of ``lexic.parsing``, so
    ``test_engine_imported_by_runtime_only_via_compile_seam``'s ``"from
    lexic.parsing"`` prefix check already covers them generically; this pins
    that coverage explicitly for the PDA modules by name (Task 6's
    ``CompiledGrammar.pda`` + fallback chain is the one sanctioned caller).
    """
    offenders = []
    for p in SRC.glob("*.py"):  # top-level modules only, not subpackages
        if p.name == "compile.py":
            continue
        for line in p.read_text().splitlines():
            stripped = line.strip()
            if "pda_tables" not in stripped and "pda_kernel" not in stripped:
                continue
            if stripped.startswith(("from lexic.parsing", "import lexic.parsing")):
                offenders.append(f"{p.name}: {stripped}")
    assert not offenders, f"PDA entry points bypass the compile.py seam: {offenders}"


def test_single_codegen_entry_and_emit_path():
    """One way per task: exactly one codegen entry and one emit-source function."""
    codegen_init = (SRC / "codegen" / "__init__.py").read_text()
    assert "def codegen_ir(" not in codegen_init
    emitter = (SRC / "codegen" / "model_emitter.py").read_text()
    assert "emit_module_source_ir" not in emitter
    assert emitter.count("def emit_module_source(") == 1
