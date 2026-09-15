"""Tests for tools.quick_checks — WHICH checks one diff earns.

The selection is the whole tool: if it drops a command, a red that this repo's
gate would have caught ships instead. So the expectations here are written out
by hand from the rule, not read back from what the function happens to return,
and every case names the failure it exists to prevent.

Nothing here runs a check. `plan` is pure — changed paths in, commands out —
and that is exactly what makes the tool's own decisions testable.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from tools.quick_checks import (
    COUPLED,
    PAID_PATH,
    ROOT,
    TESTS,
    WITNESS,
    Command,
    helper_of,
    mirror_of,
    module_of,
    plan,
)

STATE = "src/lexic/parsing/earley/kernel/loop/state.py"
STATE_MIRROR = "tests/unit/lexic/parsing/earley/kernel/loop/test_state.py"
STATE_MODULE = "lexic.parsing.earley.kernel.loop.state"
IMPORTER = "tests/integration/lexic/invariants/test_layering_invariants.py"


def _everything(_path: str) -> bool:
    """An ``exists`` predicate for a tree where every named path is a file."""
    return True


def _only(*present: str):
    """An ``exists`` predicate for a tree holding exactly ``present``."""
    return lambda path: path in present


def _labels(commands: Sequence[Command]) -> list[str]:
    """Just the labels, for asserting WHICH commands were selected."""
    return [command.label for command in commands]


def _argv(commands: Sequence[Command], label: str) -> tuple[str, ...]:
    """One selected command's argument vector."""
    return next(command.argv for command in commands if command.label == label)


# ── the mapping between a module and its test ──────────────────────────


def test_a_module_maps_to_its_dotted_name() -> None:
    """The dotted name is what an import statement is grepped for."""
    assert module_of(STATE) == STATE_MODULE
    assert module_of("src/lexic/model.py") == "lexic.model"


def test_a_packages_init_maps_to_the_package_itself() -> None:
    """`lexic.parsing`, not `lexic.parsing.__init__` — nobody imports the latter."""
    assert module_of("src/lexic/parsing/__init__.py") == "lexic.parsing"


def test_a_non_source_path_has_no_module_or_mirror() -> None:
    """A README, a yaml and a test file are not modules under test."""
    for path in ("README.md", ".github/workflows/performance.yml", "tests/x.py"):
        assert module_of(path) is None, path
        assert mirror_of(path) is None, path


def test_a_module_mirrors_to_its_unit_test() -> None:
    """The repo's convention, which the selection depends on being right."""
    assert mirror_of(STATE) == STATE_MIRROR
    assert mirror_of("src/lexic/model.py") == "tests/unit/lexic/test_model.py"


def test_a_packages_init_mirrors_to_the_package_named_test() -> None:
    """`test_init_<pkg>.py` — `test___init__.py` would collide across packages."""
    assert (
        mirror_of("src/lexic/parsing/__init__.py")
        == "tests/unit/lexic/parsing/test_init_parsing.py"
    )


# ── what a source change earns ─────────────────────────────────────────


def test_a_source_change_lints_the_file_and_runs_its_mirror() -> None:
    """The four file-scoped checks, then the one test file that mirrors it."""
    commands = plan([STATE], _only(STATE, STATE_MIRROR), {})

    assert _labels(commands) == [
        "ruff check",
        "ruff format",
        "pyright",
        "pylint",
        "pytest",
    ]
    assert _argv(commands, "ruff check") == ("uv", "run", "ruff", "check", STATE)
    # The witness is not in this tree, so it is correctly absent; the case
    # where it exists is `test_a_change_under_parsing_always_runs_the_witness`.
    assert _argv(commands, "pytest") == ("uv", "run", "pytest", STATE_MIRROR, "-q")


def test_a_source_change_also_runs_the_tests_that_import_it() -> None:
    """A mirror test is not the only test that can see a module.

    A mirror covers the module's own surface; an integration test covers what
    the module is FOR. A selection that ran only mirrors would leave every
    cross-module consequence of a change unrun.
    """
    commands = plan(
        [STATE],
        _only(STATE, STATE_MIRROR, IMPORTER, WITNESS),
        {STATE_MODULE: (IMPORTER,)},
    )

    assert IMPORTER in _argv(commands, "pytest")
    assert STATE_MIRROR in _argv(commands, "pytest")


def test_a_change_under_parsing_always_runs_the_paid_path_witness() -> None:
    """The pin exists for exactly this: a loop edited beside other work."""
    assert PAID_PATH in STATE
    commands = plan([STATE], _everything, {})

    assert WITNESS in _argv(commands, "pytest")


def test_a_change_outside_parsing_does_not_run_the_witness() -> None:
    """A pin that runs on every diff is a pin nobody reads."""
    commands = plan(["src/lexic/model.py"], _everything, {})

    assert WITNESS not in _argv(commands, "pytest")


def test_a_source_change_does_not_lint_the_whole_tests_tree() -> None:
    """Nothing a src change touches earns a sweep of the tests tree."""
    commands = plan([STATE], _everything, {})

    assert "pyright tests" not in _labels(commands)
    assert "pylint tests" not in _labels(commands)


def test_a_missing_mirror_is_not_a_pytest_target() -> None:
    """pytest errors on a path that does not exist, failing the gate for nothing."""
    commands = plan([STATE], _only(STATE), {})

    assert "pytest" not in _labels(commands)
    assert _labels(commands) == ["ruff check", "ruff format", "pyright", "pylint"]


def test_a_deleted_file_is_not_handed_to_a_linter() -> None:
    """A deletion is a changed path no linter can open."""
    commands = plan([STATE, "src/lexic/gone.py"], _only(STATE), {})

    assert _argv(commands, "pyright") == ("uv", "run", "pyright", STATE)


# ── what a test change earns ───────────────────────────────────────────


def test_a_test_change_lints_and_runs_only_itself() -> None:
    """The four file-scoped checks on it, and it as the one pytest target.

    No command here is tree-wide. A changed test file does NOT earn a sweep of
    `tests/`: the remote owns tree-wide, and a tool whose point is to run one
    diff's checks cannot answer a cross-file question by running everything.
    """
    commands = plan([IMPORTER], _only(IMPORTER), {})

    assert _labels(commands) == [
        "ruff check",
        "ruff format",
        "pyright",
        "pylint",
        "pytest",
    ]
    assert _argv(commands, "pytest") == ("uv", "run", "pytest", IMPORTER, "-q")


def test_a_new_test_file_is_selected_like_any_other() -> None:
    """An untracked file is part of the diff, so it is linted and run."""
    fresh = "tests/unit/tools/test_new.py"
    commands = plan([fresh], _everything, {})

    assert _argv(commands, "pytest") == ("uv", "run", "pytest", fresh, "-q")
    assert _argv(commands, "pylint") == ("uv", "run", "pylint", fresh)


def test_no_command_is_ever_given_a_whole_directory_of_source() -> None:
    """The one property that makes this tool what it is, asserted directly.

    Only a changed `conftest.py` may contribute a directory, and only to
    pytest; nothing else may hand a linter or a type checker a tree.
    """
    paths = [STATE, IMPORTER, "tools/quick_checks.py", "README.md"]

    for command in plan(paths, _everything, {}):
        if command.label == "pytest":
            continue
        # Every argument naming a PATH is a single file — stated without index
        # arithmetic, since the file list starts at a different position in
        # each of the four commands.
        named = [one for one in command.argv if "/" in one]
        assert named, command.label
        assert all(one.endswith(".py") for one in named), command.label
        assert TESTS not in command.argv, command.label


def test_a_tests_tree_helper_runs_the_tests_that_import_it() -> None:
    """A helper is not a pytest target — pytest collects nothing from it.

    `tests/.../forest_helpers.py` holds no test, so selecting it would run
    literally nothing while looking like coverage. What it earns is the test
    files that import it.
    """
    helper = "tests/unit/lexic/parsing/earley/kernel/forest/forest_helpers.py"
    dotted = "tests.unit.lexic.parsing.earley.kernel.forest.forest_helpers"
    commands = plan([helper], _only(helper, IMPORTER), {dotted: (IMPORTER,)})

    assert _argv(commands, "pytest") == ("uv", "run", "pytest", IMPORTER, "-q")


def test_a_conftest_change_runs_its_whole_directory() -> None:
    """Fixtures reach a subtree and no import names them, so the tree is the unit."""
    conftest = "tests/integration/lexic/invariants/conftest.py"
    commands = plan([conftest], _only(conftest), {})

    assert _argv(commands, "pytest") == (
        "uv",
        "run",
        "pytest",
        "tests/integration/lexic/invariants",
        "-q",
    )


def test_a_helper_is_not_confused_with_a_test_or_a_conftest() -> None:
    """The three kinds of `.py` under `tests/` are selected differently."""
    assert helper_of("tests/unit/x/helpers.py") == "tests.unit.x.helpers"
    assert helper_of("tests/unit/x/test_a.py") is None
    assert helper_of("tests/unit/x/conftest.py") is None
    assert helper_of("src/lexic/model.py") is None


def test_a_roster_change_runs_the_tests_coupled_to_it_by_content() -> None:
    """The import graph cannot see this one, and it went unrun for a whole diff.

    Adding a benchmark row adds a parametrised instance to every test reading
    `BENCHES`, which moves the rendered tests badge that `test_readme_render`
    compares. Nothing in the render path imports the roster, so no import edge
    exists to follow — the coupling is by content and has to be declared.
    """
    grammars = "tools/benchmark/cases/grammars.py"
    render = "tests/integration/lexic/invariants/test_readme_render.py"
    matrix = "tests/integration/lexic/invariants/test_performance_matrix.py"

    targets = _argv(plan([grammars], _everything, {}), "pytest")

    assert render in targets
    assert matrix in targets


def test_a_coupled_test_that_does_not_exist_is_not_a_target() -> None:
    """A declared coupling is still checked against the tree, like every other."""
    commands = plan(["tools/benchmark/cases/grammars.py"], _only("x"), {})

    assert "pytest" not in _labels(commands)


def test_a_change_elsewhere_in_tools_is_not_coupled_to_the_roster() -> None:
    """The prefix is the cases directory, not `tools/` — a row must stay narrow."""
    commands = plan(["tools/benchmark/compare.py"], _everything, {})

    assert "pytest" not in _labels(commands)


def test_every_declared_coupling_names_real_files() -> None:
    """A stale row silently stops selecting anything, which is the failure mode.

    `exists` filters a coupled path that has been deleted or renamed, so the
    table going stale costs coverage without ever failing. This is the check
    that it has not.
    """
    for prefix, coupled in COUPLED:
        assert (ROOT / prefix).is_dir(), prefix
        for path in coupled:
            assert (ROOT / path).is_file(), path


# ── what earns nothing ─────────────────────────────────────────────────


def test_a_non_python_change_earns_no_commands() -> None:
    """A README or a workflow cannot break a linter or a test here."""
    assert not plan(["README.md", ".wiki/log.md"], _everything, {})


def test_an_empty_diff_earns_no_commands() -> None:
    """The degenerate case, stated rather than assumed."""
    assert not plan([], _everything, {})


# ── a tools change ─────────────────────────────────────────────────────


def test_a_tools_change_lints_itself_and_runs_its_mirror_if_there_is_one() -> None:
    """`tools/` has no `src/lexic` mirror rule, so only a direct test counts."""
    commands = plan(["tools/quick_checks.py"], _everything, {})

    assert _labels(commands) == ["ruff check", "ruff format", "pyright", "pylint"]


@pytest.mark.parametrize(
    "path",
    ["src/lexic/model.py", "tools/quick_checks.py", "tests/unit/tools/test_x.py"],
)
def test_every_python_change_is_linted_by_all_four(path: str) -> None:
    """No python file is exempt from the file-scoped four."""
    labels = _labels(plan([path], _everything, {}))

    assert labels[:4] == ["ruff check", "ruff format", "pyright", "pylint"]
