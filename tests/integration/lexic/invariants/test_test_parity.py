"""Every source module has its mirrored unit-test file.

`testing.md` states the mirror rule and `STYLE.md` §11 repeats it, but nothing
enforced it, so the tree drifted quietly: a module added without its test file
looks exactly like a module whose tests live somewhere else. This gate makes
the difference visible.

The mapping is the documented one::

    src/lexic/foo/bar.py       ->  tests/unit/lexic/foo/test_bar.py
    src/lexic/foo/__init__.py  ->  tests/unit/lexic/foo/test_init_foo.py

**What this gate does NOT claim.** A mirrored file existing says a module has
somewhere obvious to test it, not that it is well tested. This is a placement
invariant; coverage is a different question and a different instrument.

`ALLOWED` is for modules that genuinely cannot be tested alone. Every entry
carries its reason inline, because an allowlist without reasons becomes a
place to hide work rather than a record of a decision.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = ROOT / "src" / "lexic"
UNIT_ROOT = ROOT / "tests" / "unit" / "lexic"

ALLOWED: dict[str, str] = {}
"""Module path (relative to ``src/lexic``) -> why it has no mirrored file.

Empty by design. An entry here is a claim that the module cannot be exercised
on its own, and that claim belongs in review, not in a bulk edit.
"""


def is_pure_marker(module: Path) -> bool:
    """Whether a package ``__init__.py`` declares no surface of its own.

    A pure marker is a docstring, imports, and at most a literal ``__all__``.
    It has nothing to test that testing its package does not already cover, so
    demanding a ``test_init_<pkg>.py`` for it would buy a file rather than a
    check.

    The predicate lives in the gate rather than in an allowlist ON PURPOSE:
    exemption is then a property of the file, re-derived every run. An
    ``__init__`` that grows a ``__getattr__``, a computed ``__all__`` or any
    other logic stops being pure the moment it does, and rejoins the gap list
    with nobody having to notice.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # the module docstring
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if _is_literal_all(node):
            continue
        return False
    return True


def _is_literal_all(node: ast.stmt) -> bool:
    """Whether ``node`` is ``__all__ = [...]`` with a literal on the right.

    A COMPUTED ``__all__`` is surface — it is the façade deciding what it
    exports — so only a literal counts as declarative.
    """
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return False
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    named_all = any(
        isinstance(target, ast.Name) and target.id == "__all__" for target in targets
    )
    return named_all and isinstance(node.value, (ast.List, ast.Tuple, ast.Set))


def _expected_test(module: Path) -> Path:
    """The unit-test file the mirror rule requires for ``module``."""
    relative = module.relative_to(SOURCE_ROOT)
    if module.name == "__init__.py":
        package = relative.parent.name or "lexic"
        return UNIT_ROOT / relative.parent / f"test_init_{package}.py"
    return UNIT_ROOT / relative.parent / f"test_{module.stem}.py"


def source_modules() -> list[Path]:
    """Every Python module under ``src/lexic``, cache artefacts excluded."""
    return sorted(
        path for path in SOURCE_ROOT.rglob("*.py") if "__pycache__" not in path.parts
    )


def exempt_markers() -> list[Path]:
    """Package inits exempt as pure markers — the gate holds them to it."""
    return [
        module
        for module in source_modules()
        if module.name == "__init__.py" and is_pure_marker(module)
    ]


def missing_mirrors() -> list[str]:
    """Modules with no mirrored unit-test file, as ``src`` -> ``test`` lines.

    Pure-marker package inits are not gaps: they declare no surface, so the
    debt they would represent is imaginary. Everything else — every real
    module, and every ``__init__`` that DOES something — is owed its file.
    """
    exempt = set(exempt_markers())
    gaps = []
    for module in source_modules():
        relative = str(module.relative_to(SOURCE_ROOT))
        if relative in ALLOWED or module in exempt:
            continue
        expected = _expected_test(module)
        if not expected.is_file():
            gaps.append(f"{module.relative_to(ROOT)} -> {expected.relative_to(ROOT)}")
    return gaps


def test_exempt_package_inits_declare_no_surface() -> None:
    """The other half of the exemption: a marker must STAY a marker.

    Without this the predicate would be a way out rather than a statement of
    fact. An ``__init__`` that gains logic simply stops matching, so it leaves
    this test and joins the gap list above — which is the behaviour that makes
    exempting it safe in the first place.
    """
    exempt = exempt_markers()
    assert exempt, "no pure-marker inits found — the predicate is not matching"
    impure = [
        str(module.relative_to(ROOT)) for module in exempt if not is_pure_marker(module)
    ]
    assert not impure, f"exempt inits that grew a surface: {impure}"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "44 of 170 source modules are owed a mirrored unit-test file: 41 real "
        "modules plus 3 package inits that declare a surface of their own "
        "(grammars, grammars/abnf, grammars/gbnf). A further 32 package inits "
        "are exempt as pure markers, held to that by "
        "test_exempt_package_inits_declare_no_surface — so the exemption is a "
        "property re-derived each run, not a list someone maintains. The gap "
        "list is the work order and lives in this test's own failure message, "
        "so it cannot go stale the way a copy in a document would. Strict, so "
        "the day the last gap closes this fails and the marker must come off. "
        "Deliberately NOT seeded into ALLOWED: that list means 'cannot be "
        "tested alone', and bulk entries would turn a record of decisions into "
        "a place to hide work — a green gate proving nothing."
    ),
)
def test_every_source_module_has_a_mirrored_unit_test_file() -> None:
    """The mirror rule, enforced rather than merely documented."""
    gaps = missing_mirrors()
    assert not gaps, (
        f"{len(gaps)} source modules have no mirrored unit-test file.\n"
        "Add the file (see testing.md for the naming rule), or add an ALLOWED\n"
        "entry with the reason it cannot be tested alone:\n  " + "\n  ".join(gaps)
    )


def test_the_allowlist_names_only_modules_that_exist() -> None:
    """A stale allowlist entry silently excuses a module that was renamed."""
    present = {str(path.relative_to(SOURCE_ROOT)) for path in source_modules()}
    stale = sorted(set(ALLOWED) - present)
    assert not stale, f"ALLOWED names modules that no longer exist: {stale}"
