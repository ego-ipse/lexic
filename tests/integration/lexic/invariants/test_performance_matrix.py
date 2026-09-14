"""The performance matrix is the roster, read at run time — never a list typed
into the workflow.

Three benchmark rows were added on the roster and never ran on the remote,
because the workflow carried its own twelve names. This pins the shape that
cannot drift: the matrix and the aggregate's expected rows both come from the
``roster`` job, and that job prints ``BENCHES`` by name.
"""

from __future__ import annotations

from pathlib import Path

from tools.benchmark.cases.grammars import BENCHES

WORKFLOW = (
    Path(__file__).resolve().parents[4] / ".github" / "workflows" / "performance.yml"
)


def test_the_matrix_and_the_expected_rows_come_from_the_roster_job() -> None:
    """No grammar name is typed into the workflow; both readers use the job."""
    text = WORKFLOW.read_text()
    assert "grammar: ${{ fromJSON(needs.roster.outputs.grammars) }}" in text
    assert "--expect ${{ join(fromJSON(needs.roster.outputs.grammars), ' ') }}" in text
    assert "from tools.benchmark.cases.grammars import BENCHES" in text
    for bench in BENCHES:
        assert f"- {bench.name}\n" not in text, (
            f"{bench.name} is typed into the workflow"
        )


def test_the_aggregate_waits_for_the_roster_and_every_row() -> None:
    """The aggregate needs both jobs, or a roster change could outrun it."""
    text = WORKFLOW.read_text()
    assert "needs: [roster, lexic]" in text
