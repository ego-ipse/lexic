"""Tests for tools.benchmark.measurement.copy — the measurement copy's rules.

Two of them are gates on the copy itself rather than on any one revision:
every protocol module goes through the build-object rename, and no protocol
module imports a `lexic` name outside the declared shared vocabulary. Both
exist because their failure mode is a whole A/B arm dying at import, which
reads as "the run is broken" rather than "this import is new".
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from tools.benchmark.measurement.copy import (
    BUILD_OBJECT,
    PROTOCOL_MODULES,
    RETIRED_MODULES,
    SHARED_VOCABULARY,
    _rewrite,
    digest,
    materialise,
)

BENCHMARK = Path(__file__).resolve().parents[4] / "tools" / "benchmark"


def lexic_imports(source: str) -> set[str]:
    """Every ``lexic`` name one module imports, as exact dotted paths.

    Both import forms count: ``from lexic.x import y`` contributes
    ``lexic.x.y``, and a plain ``import lexic.x`` contributes ``lexic.x`` —
    the module itself is the name reached for in that case.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "lexic" or module.startswith("lexic."):
                found.update(f"{module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(
                alias.name
                for alias in node.names
                if alias.name == "lexic" or alias.name.startswith("lexic.")
            )
    return found


def module_source(module: str) -> str:
    """One protocol module's text, read from this checkout."""
    return (BENCHMARK / module).read_text(encoding="utf-8")


# ── the shared-vocabulary gate ────────────────────────────────────────────


@pytest.mark.parametrize("module", PROTOCOL_MODULES)
def test_a_protocol_module_imports_only_declared_shared_vocabulary(module: str):
    """A `lexic` name the base revision lacks kills that arm at import.

    Declared rather than derived: the base is a different checkout and this
    gate runs without one, so what it enforces is that every such import was
    written down — which is the moment somebody has to look at the other arm.
    """
    undeclared = lexic_imports(module_source(module)) - SHARED_VOCABULARY
    assert not undeclared, (
        f"{module} imports {sorted(undeclared)}, which is not declared shared "
        "with the comparison base. Confirm the base revision has it, then add "
        "it to SHARED_VOCABULARY."
    )


def test_the_gate_catches_an_undeclared_import():
    """The gate has to bite: the exact defect that broke the base arm.

    ``ModelExecutable`` postdates the base and was imported by the occupancy
    probe; reading it back out of a synthetic module proves the extractor sees
    that shape, rather than passing because it sees nothing.
    """
    source = "from lexic.parsing import ModelExecutable\nx = ModelExecutable\n"
    assert lexic_imports(source) == {"lexic.parsing.ModelExecutable"}
    assert lexic_imports(source) - SHARED_VOCABULARY


def test_the_extractor_reads_both_import_forms_and_ignores_others():
    """Only `lexic` names count, and a plain module import counts as itself."""
    source = (
        "import lexic.ir\n"
        "import threading\n"
        "from lexic.compile import CompiledGrammar, compile_text\n"
        "from pathlib import Path\n"
        "from tools.benchmark.bench import LEXIC_ROWS\n"
    )
    assert lexic_imports(source) == {
        "lexic.ir",
        "lexic.compile.CompiledGrammar",
        "lexic.compile.compile_text",
    }


def test_the_declared_vocabulary_carries_nothing_unused():
    """A name no protocol module imports is a claim about the base for nothing."""
    imported = set[str]().union(
        *(lexic_imports(module_source(module)) for module in PROTOCOL_MODULES)
    )
    assert not SHARED_VOCABULARY - imported


# ── the build-object rename ───────────────────────────────────────────────


def _copy_of(tmp_path: Path) -> Path:
    """A checkout-shaped tree holding this repo's protocol modules."""
    target = tmp_path / "tools" / "benchmark"
    target.mkdir(parents=True)
    for module in PROTOCOL_MODULES:
        destination = target / module
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(module_source(module), encoding="utf-8")
    return tmp_path


def test_the_rename_reaches_every_module_that_names_the_build_object(
    tmp_path: Path,
) -> None:
    """Not a listed subset: whichever modules name it, all of them move.

    Derived from the source rather than asserted against a fixed list, so a
    module that starts naming the build object is covered the day it does —
    the stale-list failure is silent in the other arm, at import or worse.
    """
    root = _copy_of(tmp_path)
    naming = {
        module
        for module in PROTOCOL_MODULES
        if f"compiled.{BUILD_OBJECT}" in module_source(module)
    }
    assert len(naming) > 1, "the fixture must cover more than one naming module"

    _rewrite(root, "fold")

    for module in naming:
        rewritten = (root / "tools" / "benchmark" / module).read_text(encoding="utf-8")
        assert f"compiled.{BUILD_OBJECT}" not in rewritten
        assert "compiled.fold" in rewritten


def test_a_module_naming_nothing_is_left_byte_identical(tmp_path: Path) -> None:
    """The rewrite is a rename, not a pass: untouched modules must not change."""
    root = _copy_of(tmp_path)
    quiet = [
        module
        for module in PROTOCOL_MODULES
        if f"compiled.{BUILD_OBJECT}" not in module_source(module)
    ]
    before = {module: module_source(module) for module in quiet}

    _rewrite(root, "fold")

    for module, text in before.items():
        assert (root / "tools" / "benchmark" / module).read_text(
            encoding="utf-8"
        ) == text


# ── materialise ───────────────────────────────────────────────────────────


def test_materialise_installs_the_protocol_and_deletes_the_retired(
    tmp_path: Path,
) -> None:
    """The copy is the protocol plus the absence of what the correction dropped."""
    target = tmp_path / "tools" / "benchmark"
    target.mkdir(parents=True)
    for retired in RETIRED_MODULES:
        (target / retired).parent.mkdir(parents=True, exist_ok=True)
        (target / retired).write_text("stale\n", encoding="utf-8")

    materialise(tmp_path, BUILD_OBJECT, BENCHMARK.parents[1])

    for module in PROTOCOL_MODULES:
        assert (target / module).read_text(encoding="utf-8") == module_source(module)
    for retired in RETIRED_MODULES:
        assert not (target / retired).exists()


def test_materialise_refuses_a_root_with_no_benchmark(tmp_path: Path) -> None:
    """Correcting a tree that has no benchmark would silently create one."""
    with pytest.raises(ValueError, match="no tools/benchmark"):
        materialise(tmp_path, BUILD_OBJECT, BENCHMARK.parents[1])


def test_the_digest_moves_with_the_renamed_copy(tmp_path: Path) -> None:
    """The report's digest identifies the text that ran, rename included."""
    root = _copy_of(tmp_path)
    before = digest(root)

    _rewrite(root, "fold")

    assert digest(root) != before


def _merge_base(root: Path) -> str | None:
    """The comparison base's sha, or ``None`` when this checkout cannot name it.

    A runner clones one branch, so ``main`` is often not a local ref; the
    remote-tracking name is tried next. When neither resolves there is no base
    to check against and the caller skips rather than failing on the clone's
    shape.
    """
    for ref in ("main", "origin/main"):
        found = subprocess.run(
            ["git", "merge-base", ref, "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
        )
        if found.returncode == 0:
            return found.stdout.strip()
    return None


def test_a_copied_module_imports_nothing_the_base_checkout_lacks() -> None:
    """A copied module may import an uncopied one only if the BASE has it too.

    The base arm is a checkout of the base revision with the protocol modules
    copied over it, so an uncopied module resolves to the base's own — which is
    fine for a module both revisions have, and a `ModuleNotFoundError` on the
    runner for one this branch introduced. The local tree has every file, so no
    other gate can see the difference.
    """
    root = BENCHMARK.parent.parent
    base = _merge_base(root)
    if base is None:
        pytest.skip("no merge base resolvable in this checkout")
    carried = {
        f"tools.benchmark.{name[:-3].replace('/', '.')}" for name in PROTOCOL_MODULES
    }
    missing: dict[str, set[str]] = {}
    for module in PROTOCOL_MODULES:
        wanted = {
            line.split()[1]
            for line in (one.strip() for one in module_source(module).splitlines())
            if line.startswith(("from tools.benchmark.", "import tools.benchmark."))
        }
        absent = set()
        for name in wanted - carried:
            path = name.replace(".", "/") + ".py"
            found = subprocess.run(
                ["git", "cat-file", "-e", f"{base}:{path}"],
                capture_output=True,
                check=False,
                cwd=root,
            )
            if found.returncode != 0:
                absent.add(name)
        if absent:
            missing[module] = absent
    assert not missing, (
        "a copied module imports a module this branch introduced and does not "
        f"copy — the base arm cannot import it: {missing}"
    )
