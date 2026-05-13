"""Layering invariants enforced via static grep over src/lexic/."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "lexic"


def _grep(directory: Path, needle: str) -> list[Path]:
    """Return list of .py files in directory containing needle."""
    return [p for p in directory.rglob("*.py") if needle in p.read_text()]


def test_ir_does_not_import_grammars_parsing_codegen():
    """lexic.ir should be a leaf module, not importing lexic.grammars or lexic.parsing."""
    bad = (
        _grep(SRC / "ir", "from lexic.grammars")
        + _grep(SRC / "ir", "from lexic.parsing")
        + _grep(SRC / "ir", "from lexic.codegen")
    )
    assert not bad, f"lexic.ir leaks: {bad}"


def test_codegen_does_not_import_grammars_or_parsing():
    """lexic.codegen should be a leaf module, not importing lexic.grammars or lexic.parsing."""
    bad = _grep(SRC / "codegen", "from lexic.grammars") + _grep(
        SRC / "codegen", "from lexic.parsing"
    )
    assert not bad, f"lexic.codegen leaks: {bad}"


def test_parsing_imports_grammars_only_via_flavour_abc():
    """Currently vacuous — parsing/* doesn't import lexic.grammars at all.
    Kept as a guardrail against future regression.
    """
    parsing = SRC / "parsing"
    for p in parsing.rglob("*.py"):
        for line in p.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("from lexic.grammars", "import lexic.grammars")):
                assert "lexic.grammars.flavour" in stripped, (
                    f"{p}: imports lexic.grammars beyond the Flavour ABC: {stripped}"
                )


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
