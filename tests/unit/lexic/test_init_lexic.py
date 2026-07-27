"""Tests for ``lexic.__init__``: the package root is a LAZY façade.

The root re-exports the entry points, and importing it used to import the whole
engine — so ``import lexic.ir`` (which runs the root first, as every Python
package import does) cost 77 modules for a caller that wanted 15. Every payload
artefact naming a spine symbol paid that on every read.
"""

from __future__ import annotations

import ast as pyast
import subprocess
import sys

import lexic
from tests.paths import PROJECT_ROOT

SRC = str(PROJECT_ROOT / "src")
ROOT = PROJECT_ROOT / "src" / "lexic" / "__init__.py"


def _child(code: str) -> list[str]:
    """Run `code` in a fresh interpreter; return the lexic modules it left resident.

    In THIS process every module is already imported, so the question cannot be
    asked here at all.
    """
    got = subprocess.run(
        [
            sys.executable,
            "-c",
            code + "\nimport sys\n"
            "print(' '.join(sorted(m for m in sys.modules if m.startswith('lexic'))))",
        ],
        capture_output=True,
        text=True,
        check=True,
        env={"PYTHONPATH": SRC},
    )
    return got.stdout.strip().split()


def test_importing_the_spine_does_not_import_the_engine() -> None:
    """``import lexic.ir`` must not drag ``lexic.parsing`` or ``lexic.compile``."""
    resident = _child("import lexic.ir")
    assert not [m for m in resident if m.startswith("lexic.parsing")]
    assert not [m for m in resident if m.startswith("lexic.compile")]


def test_the_root_pulls_the_spine_at_most_never_the_engine() -> None:
    """``import lexic`` costs the spine, because one export cannot be lazy.

    ``generate`` names this export AND the submodule ``lexic.generate``, so it
    is bound eagerly — ``__getattr__`` is only called on a miss, and importing
    the module anywhere would otherwise shadow the function with it. That drags
    ``lexic.ir``; it does not drag the engine, which is the 62 modules that
    matter.
    """
    resident = _child("import lexic")
    assert not [m for m in resident if m.startswith("lexic.parsing")]
    assert not [m for m in resident if m.startswith("lexic.compile")]


def test_generate_is_the_function_even_after_the_submodule_loads() -> None:
    """The export survives its own submodule being imported.

    Import order decides this, so it passes in isolation and fails under
    ``-n auto``: whichever test first does ``import lexic.generate`` binds the
    MODULE as an attribute of the package.
    """
    code = (
        "import lexic.generate\n"
        "from lexic import generate\n"
        "assert callable(generate), type(generate)\n"
        "assert generate.__name__ == 'generate'\n"
    )
    assert _child(code)


def test_the_entry_points_still_import_from_the_root() -> None:
    """The documented beginner surface is unchanged: every ``__all__`` name works."""
    code = (
        "import lexic\n"
        "for name in lexic.__all__:\n"
        "    assert callable(getattr(lexic, name)), name\n"
        "from lexic import compile_text\n"
        "assert compile_text('root ::= [a-z]+\\n').parse('ab').to_text() == 'ab'\n"
    )
    assert _child(code)


def test_an_unexported_name_raises_attribute_error() -> None:
    """The façade refuses a name it has no home for, as a module should."""
    try:
        lexic.nonexistent  # noqa: B018 — the access IS the assertion
    except AttributeError as exc:
        assert "nonexistent" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("the façade resolved a name it does not export")


def test_dir_reports_the_exports() -> None:
    """A lazy module still answers ``dir()`` — tab-completion is a surface too."""
    assert set(lexic.__all__) <= set(dir(lexic))


def test_the_three_views_of_the_surface_agree() -> None:
    """The static declarations, ``__all__`` and the runtime lookups agree.

    The surface is stated three times because three consumers read it — a type
    checker, the export machinery, and the resolution path — and drift between
    them is the one hazard this arrangement introduces: a name declared but not
    resolvable type-checks and then raises; a name resolvable but undeclared
    works and is typed as nothing in particular. Pinning them makes the
    repetition safe.

    ``generate`` sits on the eager side of the split, so "declared" is every
    ``from lexic… import`` in the file, in or out of the ``TYPE_CHECKING``
    block, and "resolvable" is the lazy homes plus whatever is bound eagerly.
    """
    tree = pyast.parse(ROOT.read_text(encoding="utf-8"))
    declared, eager = set(), set()
    for node in pyast.walk(tree):
        if not isinstance(node, pyast.ImportFrom) or not (node.module or "").startswith(
            "lexic"
        ):
            continue
        declared |= {alias.name for alias in node.names}
        if node.col_offset == 0:  # outside the TYPE_CHECKING block
            eager |= {alias.name for alias in node.names}
    homed = {
        key.value
        for node in pyast.walk(tree)
        if isinstance(node, pyast.Assign)
        and any(isinstance(t, pyast.Name) and t.id == "_HOMES" for t in node.targets)
        and isinstance(node.value, pyast.Dict)
        for key in node.value.keys
        if isinstance(key, pyast.Constant)
    }
    assert declared == set(lexic.__all__) == homed | eager
    assert not homed & eager, "a name is both lazy and eager"
    # …and every declared name really resolves, which the AST cannot say.
    for name in declared:
        assert callable(getattr(lexic, name)), name
