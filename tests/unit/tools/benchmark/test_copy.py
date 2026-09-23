"""Tests for tools.benchmark.measurement.copy — the measurement copy's rules.

Two of them are gates on the copy itself rather than on any one revision:
every protocol module goes through the build-object rename, and no protocol
module imports a `lexic` name outside the declared shared vocabulary. Both
exist because their failure mode is a whole A/B arm dying at import, which
reads as "the run is broken" rather than "this import is new".
"""

from __future__ import annotations

import ast
import io
import subprocess
import tokenize
from pathlib import Path

import pytest

from tools.benchmark.measurement.copy import (
    ARM_SPELLED,
    BUILD_OBJECT,
    PARSE_CONFIG,
    PROTOCOL_MODULES,
    RETIRED_MODULES,
    SHARED_VOCABULARY,
    _rewrite,
    _unwrap_config,
    digest,
    exports_config,
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
    undeclared = lexic_imports(module_source(module)) - SHARED_VOCABULARY - ARM_SPELLED
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
    assert not ARM_SPELLED - imported


# ── the build-object rename ───────────────────────────────────────────────


def _revision(root: Path, exports: bool) -> Path:
    """Give ``root`` a ``lexic.parsing`` package root that does, or does not,
    export the parse configuration."""
    package = root / "src" / "lexic" / "parsing"
    package.mkdir(parents=True)
    names = ["Resolver", PARSE_CONFIG] if exports else ["Resolver"]
    (package / "__init__.py").write_text(f"__all__ = {names!r}\n".replace("'", '"'))
    return root


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
    target = _revision(tmp_path, exports=True) / "tools" / "benchmark"
    target.mkdir(parents=True)
    for retired in RETIRED_MODULES:
        (target / retired).parent.mkdir(parents=True, exist_ok=True)
        (target / retired).write_text("stale\n", encoding="utf-8")

    materialise(tmp_path, BUILD_OBJECT, BENCHMARK.parents[1])

    for module in PROTOCOL_MODULES:
        assert (target / module).read_text(encoding="utf-8") == module_source(module)
    for retired in RETIRED_MODULES:
        assert not (target / retired).exists()


def _materialised_split_ab(root: Path, exports: bool) -> str:
    """``diagnostics/split_ab.py`` as :func:`materialise` leaves it in a
    checkout that does, or does not, export the parse configuration."""
    (_revision(root, exports) / "tools" / "benchmark").mkdir(parents=True)
    materialise(root, BUILD_OBJECT, BENCHMARK.parents[1])
    return (root / "tools" / "benchmark" / "diagnostics" / "split_ab.py").read_text(
        encoding="utf-8"
    )


def test_a_base_without_the_parse_config_takes_the_resolver_bare(
    tmp_path: Path,
) -> None:
    """Its ``earley_model`` takes the resolver positionally, and it has no
    ``ParseConfig`` to import: the copy must name neither."""
    copied = _materialised_split_ab(tmp_path, exports=False)
    assert PARSE_CONFIG not in copied
    assert "            _take_first,\n" in copied
    assert "lexic.parsing.ParseConfig" not in lexic_imports(copied)


def test_a_base_with_the_parse_config_keeps_the_config_form(tmp_path: Path) -> None:
    """A revision that exports it gets the module byte for byte."""
    copied = _materialised_split_ab(tmp_path, exports=True)
    assert copied == module_source("diagnostics/split_ab.py")
    assert "ParseConfig(resolve=_take_first)" in copied


def test_no_parse_config_survives_a_copy_into_a_base_without_it(
    tmp_path: Path,
) -> None:
    """The gate: after materialising into a base that does not export it, no
    protocol module names ``ParseConfig`` in code, and every module parses."""
    (_revision(tmp_path, exports=False) / "tools" / "benchmark").mkdir(parents=True)
    materialise(tmp_path, BUILD_OBJECT, BENCHMARK.parents[1])
    for module in PROTOCOL_MODULES:
        text = (tmp_path / "tools" / "benchmark" / module).read_text(encoding="utf-8")
        ast.parse(text)
        names = {
            token.string
            for token in tokenize.generate_tokens(io.StringIO(text).readline)
            if token.type == tokenize.NAME
        }
        assert PARSE_CONFIG not in names, module


@pytest.mark.parametrize(
    ("init", "exports"),
    [
        ('"""ParseConfig is only mentioned here."""\n__all__ = ["Resolver"]\n', False),
        ("__all__ = ['Resolver', 'ParseConfig']\n", True),
        ("from lexic.parsing.x import ParseConfig\n", True),
    ],
)
def test_the_export_is_read_from_the_code_not_the_text(
    tmp_path: Path, init: str, exports: bool
) -> None:
    """A docstring mention is not an export; single quotes and an import are."""
    package = tmp_path / "src" / "lexic" / "parsing"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(init, encoding="utf-8")
    assert exports_config(tmp_path) is exports


def _unwrapped(tmp_path: Path, text: str) -> str:
    """``text`` as one protocol module, after the unwrap."""
    root = _copy_of(tmp_path)
    module = root / "tools" / "benchmark" / "diagnostics" / "split_ab.py"
    module.write_text(text, encoding="utf-8")
    _unwrap_config(root)
    return module.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("call", "bare"),
    [
        ("ParseConfig(take)", "take"),
        ("ParseConfig(resolve = take)", "take"),
        ("lexic.parsing.ParseConfig(resolve=self.take)", "self.take"),
        (
            "ParseConfig(\n    resolve=lambda one, _other: one,\n)",
            "lambda one, _other: one",
        ),
    ],
)
def test_every_call_form_unwraps_to_its_resolver(
    tmp_path: Path, call: str, bare: str
) -> None:
    """Positional, spaced, dotted and multi-line calls all lose the wrapper."""
    text = f"from lexic.parsing import DEFAULT_CONFIG, ParseConfig\nrun(x, {call})\n"
    assert _unwrapped(tmp_path, text) == (
        f"from lexic.parsing import DEFAULT_CONFIG\nrun(x, {bare})\n"
    )


@pytest.mark.parametrize(
    "use",
    ["run(ParseConfig(resolve=take, decide=d))", "kind = ParseConfig"],
)
def test_a_use_with_no_bare_spelling_refuses_locally(tmp_path: Path, use: str) -> None:
    """A decider, or a use that is not a call, has no form a base without the
    record can take: materialise refuses it here, not the runner at import."""
    with pytest.raises(ValueError, match=PARSE_CONFIG):
        _unwrapped(tmp_path, f"from lexic.parsing import ParseConfig\n{use}\n")


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
