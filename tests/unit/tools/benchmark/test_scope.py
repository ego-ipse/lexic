"""Tests for the benchmark scope — which rows a change can reach.

Two questions, and the tests are about the DIRECTION each one errs in. The
table over-approximates, because measuring too many rows costs minutes and
measuring too few costs a regression nobody saw. The diff reader refuses what
it cannot answer, because an unknown row set must stop a run rather than
select the empty one.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.benchmark import bench
from tools.benchmark.compare import MT_ROWS
from tools.benchmark.scope import diff, paths

# --------------------------------------------- the rows a change can reach


def test_a_change_under_the_pda_reaches_every_pda_seat_and_not_the_gated_one() -> None:
    """The PDA's own seats, and the folding variants that are also the PDA.

    ``lexic-lex`` and ``lexic-lex-ns`` are the predictive parser with directives
    applied, so a change to the predictive runtime reaches them; the Earley seat
    is the route that does NOT take the PDA, and measuring it would be spending
    the budget to prove something the change cannot have touched.
    """
    reached = paths.seats_for(["src/lexic/parsing/pda/runtime/admission.py"])
    assert reached == frozenset(paths.PDA_SEATS)
    assert "lexic-earley" not in reached


def test_a_change_under_the_gated_engine_reaches_only_its_own_seat() -> None:
    """The Earley kernel is one seat's paid path and nothing else's."""
    assert paths.seats_for(["src/lexic/parsing/earley/kernel/loop/kernel.py"]) == (
        frozenset(paths.EARLEY_SEATS)
    )


def test_a_change_to_the_document_split_reaches_only_the_threaded_seats() -> None:
    """A split is only ever exercised by a row that asks for workers."""
    assert paths.seats_for(["src/lexic/parsing/parallel/plan/cuts.py"]) == frozenset(
        paths.MT_SEATS
    )


def test_a_source_path_the_table_does_not_name_reaches_every_seat() -> None:
    """The stated over-approximation, and the direction it errs in.

    An unrecognised module under the package is one nobody has placed on a
    paid path yet. Measuring too many rows costs minutes; measuring too few
    costs a regression nobody saw, so the unplaced case takes the whole roster.
    """
    for path in (
        "src/lexic/generate.py",
        "src/lexic/parsing/products.py",
        "src/lexic/somewhere/nobody/has/mapped.py",
    ):
        assert paths.seats_for([path]) == paths.EVERY_SEAT, path


def test_a_change_off_every_paid_path_selects_no_seat_at_all() -> None:
    """A test, a document or the harness itself measures nothing.

    Not an oversight — a run over such a diff has no row to report and says so.
    The harness is deliberately in this set: editing it makes the two arms
    incomparable rather than slower, which the printed digests already surface.
    """
    assert not paths.seats_for(
        [
            "tests/unit/lexic/parsing/pda/runtime/test_admission.py",
            "docs/STYLE.md",
            ".wiki/log.md",
            "tools/benchmark/quick.py",
            "pyproject.toml",
            "README.md",
        ]
    )


def test_several_changed_paths_union_the_seats_they_reach() -> None:
    """A diff is a set of paths and its scope is their union, never the first."""
    assert paths.seats_for(
        [
            "src/lexic/parsing/earley/engine.py",
            "src/lexic/parsing/parallel/policy.py",
        ]
    ) == frozenset(paths.EARLEY_SEATS) | frozenset(paths.MT_SEATS)


def test_the_table_is_read_most_specific_first() -> None:
    """A deep path takes its own row, not the broader one above it.

    ``parsing/pda/`` sits under ``parsing/``, which the table does not name and
    which therefore reaches every seat. If the table were read in any other
    order, or unconditionally, a PDA change would select the whole roster and
    the tier would have no scope at all.
    """
    assert paths.seats_for(["src/lexic/parsing/pda/compiler/clones.py"]) != (
        paths.EVERY_SEAT
    )
    assert paths.seats_for(["src/lexic/parsing/lift.py"]) == paths.EVERY_SEAT


def test_the_tables_every_seat_is_exactly_the_roster_s_seats() -> None:
    """The drift tripwire: a seat added to the roster must join a family.

    ``EVERY_SEAT`` is spelled as the union of the families rather than as its
    own list, so a new seat that nobody placed would be missing from BOTH — and
    a change that reaches everything would quietly stop reaching it. Checked
    against the benchmark's own row set, not a fixture: a fixture would drift
    with the table it is meant to catch drifting.
    """
    assert paths.EVERY_SEAT == bench.LEXIC_ROWS


def test_no_family_claims_a_seat_the_roster_does_not_carry() -> None:
    """A misspelt seat in the table would select nothing, silently."""
    for family in (paths.PDA_SEATS, paths.EARLEY_SEATS, paths.MT_SEATS):
        assert set(family) <= bench.LEXIC_ROWS, family


def test_every_threaded_seat_is_reachable_from_the_split_and_the_pda() -> None:
    """Both threaded seats run the PDA over a split document, so both families
    claim them — and a change to either half must select them."""
    assert set(paths.MT_SEATS) <= set(paths.PDA_SEATS)
    assert set(paths.MT_SEATS) == set(MT_ROWS)


# ------------------------------------------------ the diff the rows come from


def _repo(tmp_path: Path) -> Path:
    """A throwaway work tree with one commit, for asking git real questions."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "kept.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=tmp_path, check=True)
    return tmp_path


def test_the_diff_reader_sees_a_tracked_file_that_changed(tmp_path: Path) -> None:
    """The ordinary case — an edit to a file the base already had."""
    repo = _repo(tmp_path)
    (repo / "kept.txt").write_text("two\n", encoding="utf-8")
    assert diff.changed_paths("HEAD", repo) == ("kept.txt",)


def test_the_diff_reader_sees_a_file_that_was_never_added(tmp_path: Path) -> None:
    """The failure this reader exists to avoid.

    ``git diff`` cannot see an untracked file, and a NEW module under the
    predictive runtime is exactly the change that most needs its seats
    measured. Missing it would not read as an error — it would read as a clean
    run over a change nobody measured, which is the worst answer this tool has.
    """
    repo = _repo(tmp_path)
    (repo / "brand_new.py").write_text("x = 1\n", encoding="utf-8")
    assert diff.changed_paths("HEAD", repo) == ("brand_new.py",)


def test_the_diff_reader_reports_each_path_once(tmp_path: Path) -> None:
    """A staged-and-modified file is one path, not two."""
    repo = _repo(tmp_path)
    (repo / "kept.txt").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    (repo / "kept.txt").write_text("three\n", encoding="utf-8")
    assert diff.changed_paths("HEAD", repo) == ("kept.txt",)


def test_an_unchanged_tree_yields_no_paths(tmp_path: Path) -> None:
    """Nothing changed is a real answer, and it is empty rather than absent."""
    assert not diff.changed_paths("HEAD", _repo(tmp_path))


def test_a_revision_git_cannot_resolve_is_refused(tmp_path: Path) -> None:
    """A typo'd base must not read as "nothing changed" and select no rows."""
    with pytest.raises(RuntimeError):
        diff.changed_paths("no-such-revision", _repo(tmp_path))


def test_a_directory_that_is_not_a_work_tree_is_refused(tmp_path: Path) -> None:
    """Asking the wrong place is an error, not an empty diff."""
    with pytest.raises(RuntimeError):
        diff.changed_paths("HEAD", tmp_path / "nowhere")
