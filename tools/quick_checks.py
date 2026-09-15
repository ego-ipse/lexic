"""The gate for ONE diff — the checks this change can actually have broken.

`tools/run_checks.sh` is the done-gate and runs over the whole tree; the remote
runs it on every push. That is the wrong instrument mid-change: a tree-wide
sweep costs minutes, reports failures nobody in this diff caused, and is slow
enough that it stops being run at all.

This selects instead. Given the paths a diff touches it emits the commands that
CAN see those paths, prints each one before running it, and exits on the first
failure. Nothing here is a new rule — every command is one `tools/checks/*.sh`
or `tools/auto_fix.sh` already runs, narrowed to files.

**It FIXES before it checks.** `ruff format`, `isort` and `ruff check --fix` run
on the changed files first, then the verifying pass. `tools/auto_fix.sh` does
the same three things over the whole tree, so reaching for it mid-diff is the
sweep this tool exists to replace; a gate that only reported left the fixable
half to be done by hand, which meant doing it tree-wide. This tool therefore
WRITES to the files it was given — nothing else, and nothing it was not.

**Nothing here is ever tree-wide.** A cross-file check — `pylint`'s duplicate
blocks, an annotation that no longer matches a caller elsewhere — is real, and
it is the REMOTE's to run. Answering it by sweeping a directory would make this
tool the thing it exists to replace, and a gate that costs minutes is a gate
nobody runs. The only directory any command ever receives is a changed
`conftest.py`'s own, and only as a pytest target.

Selection is a pure function of the changed paths (:func:`plan`), so what this
tool decides to run is testable without running anything.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]

SRC = "src/lexic/"
TESTS = "tests/"
PAID_PATH = "src/lexic/parsing/"
WITNESS = "tests/integration/lexic/invariants/test_paid_path_witness.py"
"""Pinned bytecode for the per-character loops — run whenever `parsing/` moves.

The pin exists because that loop and the code around it are edited in the same
efforts. A diff that touches `parsing/` at all is exactly the case it was
written for.
"""

COUPLED: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "tools/benchmark/cases/",
        (
            "tests/integration/lexic/invariants/test_readme_render.py",
            "tests/integration/lexic/invariants/test_performance_matrix.py",
        ),
    ),
)
"""Directory prefix → tests coupled to it by something no import expresses.

The import graph is how this tool finds what a change can break, and it misses
a real dependency whenever the coupling is by CONTENT rather than by reference.
The benchmark roster is the case that caught it out: adding a row adds a
parametrised instance to every test that reads `BENCHES`, which moves the
rendered tests badge, which `test_readme_render` re-renders and compares — and
nothing in the render path imports the roster, so nothing in the graph says so.
`test_performance_matrix` reads the roster at run time for the same reason.

Every row here is a coupling somebody was bitten by, named with its reason. A
row without one is a tree-wide sweep wearing a prefix.
"""


class Command(NamedTuple):
    """One command to run, and what to call it when it fails.

    :ivar label: The short name printed and reported.
    :ivar argv: The exact argument vector.
    """

    label: str
    argv: tuple[str, ...]


def module_of(path: str) -> str | None:
    """The dotted module a source path defines, or ``None`` if it is not one."""
    if not path.startswith(SRC) or not path.endswith(".py"):
        return None
    dotted = path[len("src/") : -len(".py")].replace("/", ".")
    return dotted.removesuffix(".__init__") if dotted.endswith("__init__") else dotted


def mirror_of(path: str) -> str | None:
    """The unit test that mirrors one source path, by this repo's convention.

    ``src/lexic/a/b.py`` is mirrored by ``tests/unit/lexic/a/test_b.py``, and a
    package's ``__init__.py`` by ``tests/unit/lexic/a/test_init_a.py`` — named
    for the package, because ``test___init__.py`` collides across packages.
    """
    if not path.startswith(SRC) or not path.endswith(".py"):
        return None
    parts = path[len("src/") : -len(".py")].split("/")
    if parts[-1] == "__init__":
        parts = [*parts[:-1], f"test_init_{parts[-2]}"]
    else:
        parts = [*parts[:-1], f"test_{parts[-1]}"]
    return "tests/unit/" + "/".join(parts) + ".py"


def helper_of(path: str) -> str | None:
    """The dotted name of a tests-tree HELPER, or ``None`` if it is not one.

    A `.py` under `tests/` that pytest does not collect — a shared builder, a
    fixture module — is imported by real test files under a dotted path
    (`tests.unit....forest_helpers`). Handing it to pytest selects nothing, so
    what it earns is the tests that import IT.
    """
    if not path.startswith(TESTS) or not path.endswith(".py"):
        return None
    name = path.rsplit("/", 1)[-1]
    if name.startswith("test_") or name == "conftest.py":
        return None
    return path[: -len(".py")].replace("/", ".")


def importing_tests(modules: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Test files that import each dotted module, by `git grep`.

    Matched on the import statement rather than on the bare name, so a module
    merely MENTIONED in a docstring does not drag its tests in.
    """
    found: dict[str, tuple[str, ...]] = {}
    for dotted in modules:
        pattern = rf"^\s*(from|import) {re.escape(dotted)}\b"
        result = subprocess.run(
            ["git", "grep", "-lE", pattern, "--", TESTS],
            capture_output=True,
            text=True,
            check=False,
            cwd=ROOT,
        )
        found[dotted] = tuple(sorted(filter(None, result.stdout.splitlines())))
    return found


def changed_paths(ref: str) -> tuple[str, ...]:
    """Every path this working tree changes against ``ref``, untracked included.

    An untracked file is part of the diff a reviewer will see, and leaving new
    files out would mean a new test never runs under the gate that exists to
    run it.
    """
    diff = subprocess.run(
        ["git", "diff", "--name-only", ref],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    names = diff.stdout.splitlines() + untracked.stdout.splitlines()
    return tuple(sorted({name for name in names if name.strip()}))


def _collected(path: str) -> bool:
    """Whether pytest would collect tests from this path."""
    return path.rsplit("/", 1)[-1].startswith("test_")


def _test_targets(
    paths: Sequence[str],
    exists: Callable[[str], bool],
    importers: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Every test path this diff can have broken."""
    targets: set[str] = set()
    for path in paths:
        if path.startswith(TESTS) and _collected(path) and exists(path):
            targets.add(path)
        if path.endswith("/conftest.py") and exists(path):
            # A conftest's fixtures reach its whole subtree, and no import
            # names it — the directory is what it can have broken.
            targets.add(path.rsplit("/", 1)[0])
        mirror = mirror_of(path)
        if mirror is not None and exists(mirror):
            targets.add(mirror)
        for dotted in (module_of(path), helper_of(path)):
            if dotted is not None:
                targets.update(one for one in importers.get(dotted, ()) if exists(one))
        if path.startswith(PAID_PATH) and exists(WITNESS):
            targets.add(WITNESS)
        for prefix, coupled in COUPLED:
            if path.startswith(prefix):
                targets.update(one for one in coupled if exists(one))
    return tuple(sorted(targets))


def plan(
    paths: Sequence[str],
    exists: Callable[[str], bool],
    importers: Mapping[str, tuple[str, ...]],
) -> tuple[Command, ...]:
    """The commands one diff earns — a pure function of what it touched.

    :param paths: Repo-relative changed paths.
    :param exists: Whether a path is a file in the tree. A DELETED file is a
        changed path that no linter can open, and a mirror test that was never
        written is not a failure to report.
    :param importers: Dotted module → the test files importing it.
    :returns: The commands, in the order they should run.
    """
    python = [one for one in paths if one.endswith(".py") and exists(one)]
    commands: list[Command] = []
    if python:
        commands += [
            # FIX first, on the changed files only. `tools/auto_fix.sh` does
            # the same three things over the WHOLE tree, so reaching for it
            # mid-diff is the sweep this tool exists to replace — and a gate
            # that only reported left the fixable half to be done by hand,
            # which meant doing it tree-wide.
            Command("ruff format", ("uv", "run", "ruff", "format", *python)),
            Command("isort", ("uv", "run", "isort", *python)),
            Command(
                "ruff check --fix", ("uv", "run", "ruff", "check", "--fix", *python)
            ),
            # Then verify. `ruff check` runs again because `--fix` leaves what
            # it cannot fix, and its exit code is the one that matters.
            Command("ruff check", ("uv", "run", "ruff", "check", *python)),
            Command("pyright", ("uv", "run", "pyright", *python)),
            Command("pylint", ("uv", "run", "pylint", *python)),
        ]
    targets = _test_targets(paths, exists, importers)
    if targets:
        commands.append(Command("pytest", ("uv", "run", "pytest", *targets, "-q")))
    return tuple(commands)


def run(commands: Sequence[Command]) -> int:
    """Run each command in order, stopping at the first failure.

    :returns: 0 when every command passed, else the first failure's code.
    """
    for command in commands:
        print(f"\n$ {' '.join(command.argv)}", flush=True)
        code = subprocess.run(command.argv, check=False, cwd=ROOT).returncode
        if code:
            print(f"\nquick checks: {command.label} FAILED", file=sys.stderr)
            return code
    print(f"\nquick checks: {len(commands)} command(s) OK")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Select and run this diff's checks.

    :param argv: ``[ref]`` — what to diff against, defaulting to ``HEAD``.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    ref = args[0] if args else "HEAD"
    paths = changed_paths(ref)
    if not paths:
        print(f"quick checks: nothing changed against {ref}")
        return 0
    print(f"quick checks: {len(paths)} changed path(s) against {ref}")
    for path in paths:
        print(f"  {path}")
    named = {module_of(path) for path in paths} | {helper_of(path) for path in paths}
    commands = plan(
        paths,
        lambda path: (ROOT / path).is_file(),
        importing_tests(sorted(one for one in named if one is not None)),
    )
    if not commands:
        print("quick checks: nothing to run for these paths")
        return 0
    return run(commands)


if __name__ == "__main__":
    raise SystemExit(main())
