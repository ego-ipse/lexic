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


def missing_mirrors() -> list[str]:
    """Modules with no mirrored unit-test file, as ``src`` -> ``test`` lines."""
    gaps = []
    for module in source_modules():
        relative = str(module.relative_to(SOURCE_ROOT))
        if relative in ALLOWED:
            continue
        expected = _expected_test(module)
        if not expected.is_file():
            gaps.append(f"{module.relative_to(ROOT)} -> {expected.relative_to(ROOT)}")
    return gaps


@pytest.mark.xfail(
    strict=True,
    reason=(
        "75 of 170 source modules have no mirrored unit-test file — 34 package "
        "__init__.py markers and 41 real modules. The list is the work order "
        "and it lives in this test's own failure message, so it cannot go "
        "stale the way a copy in a document would. Strict, so the day the last "
        "gap closes this fails and the marker must come off. Deliberately NOT "
        "seeded into ALLOWED: that list means 'cannot be tested alone', and 75 "
        "unjustified entries would turn a record of decisions into a place to "
        "hide work — a green gate proving nothing."
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
