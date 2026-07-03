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


def test_rulespec_items_typed_for_iritem():
    """RuleSpec.items is typed for IrItem, not the old union of IrItem and IrAlternation."""
    content = (SRC / "ir" / "spec.py").read_text()
    assert "list[IrItem | IrAlternation]" in content
    assert "from lexic.ir.atoms" not in content
    assert "NewRuleSpec" not in content
