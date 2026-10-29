"""The run's summary over every grammar's artefact — an untimed row included."""

from __future__ import annotations

import json
from pathlib import Path

from tools.benchmark import aggregate
from tools.benchmark.judging.arithmetic import UNSOUND_BASE, Verdict, untimed

UNSOUND = untimed(
    "reopening/lexic-mt", f"{UNSOUND_BASE} (at 2 workers, from offset 8)", "wall"
)
TIMED = Verdict("json/lexic-pda", "ok", 1.01, 0.98, 1.03, 1.04, 6, "cpu")


def _gathered(tmp_path: Path) -> aggregate.Gathered:
    """Both rows through the artefact files the matrix jobs write."""
    for grammar, verdict in (("reopening", UNSOUND), ("json", TIMED)):
        payload = {"verdicts": [verdict._asdict()]}
        (tmp_path / f"ab-{grammar}.json").write_text(json.dumps(payload))
    return aggregate.gather(tmp_path, ("reopening", "json"))


def test_an_unsound_base_row_survives_the_artefact_and_does_not_fail(
    tmp_path: Path,
) -> None:
    """Untimed is not slower: the run passes, and the line says the row is there."""
    gathered = _gathered(tmp_path)

    assert aggregate.status(gathered) == 0
    line = aggregate.verdict_line(gathered)
    assert line.startswith("**PASS**")
    assert f"1 untimed, {UNSOUND_BASE}" in line


def test_every_table_lists_the_unsound_row_after_the_timed_ones(
    tmp_path: Path,
) -> None:
    """Not hidden: the row and its words are in both renderings, last."""
    gathered = _gathered(tmp_path)

    for text in (
        aggregate.markdown(gathered, ("reopening", "json")),
        aggregate.plain(gathered),
    ):
        assert UNSOUND.status in text
        assert text.index("json/lexic-pda") < text.index("reopening/lexic-mt")
