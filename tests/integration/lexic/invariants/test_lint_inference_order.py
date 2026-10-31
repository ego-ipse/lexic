"""pylint's errors on a module agree however a run orders the modules it builds.

astroid adds an attribute assignment made in another module to the class only
once it has built that module. A read that leans on such an assignment is
inferred from the class's own assignments alone in any run that reaches it
first: a parallel run's partition, or a lint of a diff touching that file only.
The whole-tree run, which happens to build the assigning modules first, stays
clean, so the two runs disagree and the error surfaces only in some of them.
Each module below is linted ALONE, which is the order that exposes it.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from tests.paths import PROJECT_ROOT

ALONE = ("src/lexic/parsing/pda/runtime/build.py",)
"""Modules whose reads once depended on assignments made elsewhere.

``build.py``: ``Frame.sinks`` is assigned ``None`` in its own ``__init__``, and
its lists in kernel.py and admission.py, so ``Frame.inherited_prefix``'s
subscript behind an ``is not None`` guard was flagged E1136 when build.py was
linted first."""


@pytest.mark.parametrize("module", ALONE)
def test_a_module_lints_clean_on_its_own(module: str) -> None:
    """pylint's error checks over the module alone report nothing."""
    done = subprocess.run(
        [sys.executable, "-m", "pylint", "--disable=all", "--enable=E", module],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout
