"""The bench's seat filter, and the artifact write that must not overreach.

``--only`` narrows grammars; ``--seats`` narrows engines. The pair exists so a
single engine can be re-measured without restating every other cell as though
it were taken the same day — which is also why the artifact write splices and
why provenance lives per ``(grammar, seat)`` cell, the exact granularity a run
is allowed to update.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from tools import render_readme
from tools.benchmark.bench import ENGINE
from tools.benchmark.cases.grammars import BENCHES
from tools.benchmark.execution.isolation import ReportRow
from tools.benchmark.measurement.contract import digest
from tools.benchmark.presentation.cli import (
    SCHEMA,
    Run,
    _dump_json,
    _row_names,
    _seats,
    _unsettled,
)
from tools.benchmark.presentation.reporting import Block
from tools.render_readme import COMPETITORS, _measured_caption, column_workers

_WARMLESS = ReportRow([0.5], None, None, None, None, 0.0)
"""A row from a seat with no warm-up at all — every Python engine here."""


def _bench(name: str):
    """One compiled bench case by name, or skip when it is not built here."""
    found = next((bench for bench in BENCHES if bench.name == name), None)
    if found is None:
        pytest.skip(f"{name} is not compiled in this process")
    return found


# ── the filter itself ─────────────────────────────────────────────────────


def test_no_filter_means_every_seat() -> None:
    """An absent flag is not an empty selection."""
    assert _seats(None) is None
    assert _seats([]) is None


def test_an_unknown_seat_is_refused_by_name() -> None:
    """A misspelt seat must not read as "that engine measured nothing here":
    the run would splice an artifact missing exactly the column it was asked
    to refresh, and every untouched cell would still look freshly measured."""
    with pytest.raises(SystemExit) as raised:
        _seats(["lexic-pda", "lexic-turbo"])
    assert "lexic-turbo" in str(raised.value)
    assert "lexic-pda" not in str(raised.value).splitlines()[0]


def test_every_known_seat_is_accepted() -> None:
    """The vocabulary is the engine legend, so a documented seat is askable."""
    assert _seats(sorted(ENGINE)) == frozenset(ENGINE)


def test_the_filter_narrows_the_roster_and_keeps_its_order() -> None:
    """A filtered roster is a subsequence of the unfiltered one."""
    bench = _bench("json")
    everything = _row_names(bench, 16, None)
    picked = _row_names(bench, 16, frozenset({"lexic-pda", "antlr", "msgspec"}))
    assert picked == [name for name in everything if name in picked]
    assert picked == ["lexic-pda", "antlr", "msgspec"]


def test_a_seat_the_grammar_does_not_offer_simply_does_not_appear() -> None:
    """A format specialist asked of another language is an empty column, not
    an error — the name is known, this grammar just has no seat for it."""
    bench = _bench("csv")
    assert _row_names(bench, 16, frozenset({"msgspec"})) == []
    assert _row_names(bench, 16, frozenset({"msgspec", "lexic-pda"})) == ["lexic-pda"]


def test_the_mt_rows_appear_only_when_cores_are_asked_for() -> None:
    """The filter narrows the roster; it does not widen it."""
    bench = _bench("csv")
    wanted = frozenset({"lexic-mt", "lexic-mt-lex-ns"})
    assert _row_names(bench, 16, wanted) == ["lexic-mt", "lexic-mt-lex-ns"]
    assert _row_names(bench, None, wanted) == []


# ── the artifact write: a splice, never a rewrite ─────────────────────────


def _block(bench, samples: dict[str, list[float]], floor: float | None = 1.25) -> Block:
    """One presentation block carrying only the given seats' samples."""
    return Block(bench, samples, {}, floor, {}, {}, {}, {})


def _seeded(path: Path, edit=None) -> dict:
    """Write the committed artifact to ``path``, optionally edited first."""
    before = json.loads(COMPETITORS.read_text(encoding="utf-8"))
    if edit is not None:
        edit(before)
    path.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    return before


def test_a_seat_filtered_write_leaves_every_other_cell_byte_identical(
    tmp_path: Path,
) -> None:
    """The whole point of the filter: refreshing one engine may not restate
    figures from another day as though they were taken together."""
    path = tmp_path / "artifact.json"
    before = _seeded(path)
    bench = _bench("csv")

    _dump_json(path, Run(7, 16, False), [_block(bench, {"lexic-pda": [0.5, 0.5, 0.5]})])

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["values"]["csv"]["lexic-pda"] == 0.5
    for grammar, cells in before["values"].items():
        for seat, value in cells.items():
            if (grammar, seat) == ("csv", "lexic-pda"):
                continue
            assert after["values"][grammar][seat] == value, f"{grammar}/{seat} moved"


def test_a_refreshed_seat_keeps_its_column_and_a_new_one_is_appended(
    tmp_path: Path,
) -> None:
    """Order is the artifact's own, so a re-measure does not reshuffle the file."""
    path = tmp_path / "artifact.json"
    before = _seeded(path)
    bench = _bench("csv")
    order = list(before["values"]["csv"])

    _dump_json(path, Run(7, 16, False), [_block(bench, {"lexic-pda": [0.5]})])

    after = json.loads(path.read_text(encoding="utf-8"))
    assert list(after["values"]["csv"]) == order


def _dated(payload: dict) -> None:
    """Date every recorded cell in the past, so today's write stands out."""
    for cells in payload["provenance"].values():
        for record in cells.values():
            record["measured"] = "2019-01-01"


def test_only_the_written_cells_take_todays_date(tmp_path: Path) -> None:
    """Provenance is per cell because a run refreshes some and not others.

    The fixture is dated by the test rather than read off the committed file:
    a seat this repository happened to measure today would otherwise make the
    written and unwritten dates agree, and the assertion pass for no reason.
    """
    path = tmp_path / "artifact.json"
    before = _seeded(path, _dated)
    bench = _bench("csv")

    _dump_json(path, Run(3, 8, False), [_block(bench, {"lexic-pda": [0.5]})])

    after = json.loads(path.read_text(encoding="utf-8"))
    written = after["provenance"]["csv"]["lexic-pda"]
    assert written["rounds"] == 3
    assert written["measured"] == datetime.date.today().isoformat()
    assert after["provenance"]["csv"]["lexic-earley"]["measured"] == "2019-01-01"
    assert (
        after["provenance"]["csv"]["lexic-earley"]
        == before["provenance"]["csv"]["lexic-earley"]
    ), "an unmeasured seat's record must not move"


def test_an_untouched_grammar_keeps_its_value_and_its_provenance(
    tmp_path: Path,
) -> None:
    """The defect this granularity exists for.

    ``--only csv --seats lexic-mt --cores 2`` refreshes one cell of one column.
    Stored per column, that restated every other grammar's threaded figure as a
    two-worker measurement taken today with three rounds — the numbers stayed
    put and the record under them did not.
    """
    path = tmp_path / "artifact.json"
    before = _seeded(path, _dated)
    kept = before["provenance"]["json"]["lexic-mt"]
    assert kept["cores"] == 16 and kept["rounds"] != 3, "the fixture must differ"

    _dump_json(path, Run(3, 2, False), [_block(_bench("csv"), {"lexic-mt": [0.5]})])

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["values"]["json"]["lexic-mt"] == before["values"]["json"]["lexic-mt"]
    assert after["provenance"]["json"]["lexic-mt"] == kept
    refreshed = after["provenance"]["csv"]["lexic-mt"]
    assert (refreshed["rounds"], refreshed["cores"]) == (3, 2)
    assert refreshed["measured"] == datetime.date.today().isoformat()


def test_a_non_threaded_seat_records_no_worker_request(tmp_path: Path) -> None:
    """``cores`` is the mt rows' request; every other seat is single-threaded."""
    path = tmp_path / "artifact.json"
    bench = _bench("csv")
    _dump_json(
        path,
        Run(7, 16, False),
        [_block(bench, {"lexic-pda": [0.5], "lexic-mt": [0.2]})],
    )

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["provenance"]["csv"]["lexic-pda"]["cores"] is None
    assert after["provenance"]["csv"]["lexic-mt"]["cores"] == 16


def test_the_record_says_which_document_the_seat_read(tmp_path: Path) -> None:
    """``--full`` changes the work, so it changes the cell, not only its value."""
    path = tmp_path / "artifact.json"
    bench = _bench("csv")

    _dump_json(path, Run(7, 16, False), [_block(bench, {"lexic-pda": [0.5]})])
    corpus = json.loads(path.read_text(encoding="utf-8"))["provenance"]["csv"]
    _dump_json(path, Run(7, 16, True), [_block(bench, {"lexic-pda": [0.5]})])
    full = json.loads(path.read_text(encoding="utf-8"))["provenance"]["csv"]

    assert (corpus["lexic-pda"]["scale"], full["lexic-pda"]["scale"]) == (
        "corpus",
        "full",
    )
    assert corpus["lexic-pda"]["chars"] == len(bench.corpus)
    assert full["lexic-pda"]["chars"] == len(bench.full)


def test_a_threaded_seat_always_records_the_full_input(tmp_path: Path) -> None:
    """The mt rows read the full corpus whether or not ``--full`` was asked."""
    path = tmp_path / "artifact.json"
    bench = _bench("csv")

    _dump_json(path, Run(7, 16, False), [_block(bench, {"lexic-mt": [0.2]})])

    record = json.loads(path.read_text(encoding="utf-8"))["provenance"]["csv"]
    assert record["lexic-mt"] == {
        "measured": datetime.date.today().isoformat(),
        "rounds": 7,
        "cores": 16,
        "scale": "full",
        "chars": len(bench.full),
        "grammar_digest": digest(bench.source),
        "document_digest": digest(bench.full),
        "warmed": None,
    }


def test_the_noise_floor_is_recorded_per_grammar(tmp_path: Path) -> None:
    """A run that measured four grammars says nothing about the other eight."""
    path = tmp_path / "artifact.json"
    bench = _bench("csv")
    _dump_json(path, Run(7, 16, False), [_block(bench, {"lexic-pda": [0.5]})])

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["noise_floor_percent"] == {"csv": 1.25}


def test_a_foreign_schema_is_refused_rather_than_spliced_into(tmp_path: Path) -> None:
    """A layout that records provenance differently cannot be updated in part.

    Reading one as another leaves cells nobody measured carrying this run's
    date — the precise failure per-cell records exist to prevent.
    """
    path = tmp_path / "artifact.json"
    _seeded(path, lambda payload: payload.update(schema=SCHEMA - 1))

    with pytest.raises(SystemExit, match="schema"):
        _dump_json(
            path, Run(7, 16, False), [_block(_bench("csv"), {"lexic-pda": [0.5]})]
        )


# ── the caption and the column labels read what the artifact says ─────────


def test_one_date_reads_as_one_date() -> None:
    """Agreement is the common case and reads plainly."""
    assert _measured_caption(["2026-09-06", "2026-09-06"]) == "measured 2026-09-06"


def test_cells_taken_apart_are_captioned_as_a_span() -> None:
    """One date over cells taken weeks apart claims a run that never
    happened."""
    assert (
        _measured_caption(["2026-09-06", "2026-09-01"])
        == "measured 2026-09-01 to 2026-09-06, per cell"
    )


def test_a_column_measured_at_one_worker_count_states_it() -> None:
    """The committed artifact's threaded column is a single request."""
    assert column_workers("lexic-mt") == 16
    assert column_workers("lexic-pda") is None


def test_a_column_measured_at_two_worker_counts_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A header states one count, so two is a refusal, not an average.

    Silently printing either would relabel half the column; printing the
    artifact's own disagreement is the only truthful move left.
    """
    records = json.loads(COMPETITORS.read_text(encoding="utf-8"))["provenance"]
    records["csv"]["lexic-mt"] = dict(records["csv"]["lexic-mt"], cores=2)
    monkeypatch.setattr(render_readme, "cell_records", lambda: records)

    with pytest.raises(SystemExit, match="lexic-mt was measured at 16, 2 workers"):
        column_workers("lexic-mt")


def test_the_committed_artifact_carries_provenance_for_every_measured_cell() -> None:
    """The file the README renders from must be able to answer the question."""
    data = json.loads(COMPETITORS.read_text(encoding="utf-8"))
    assert data["schema"] == SCHEMA
    missing = sorted(
        f"{grammar}/{seat}"
        for grammar, cells in data["values"].items()
        for seat in cells
        if seat not in data["provenance"].get(grammar, {})
    )
    assert missing == [], missing


# ── what a cell says it measured, and what it may not publish ─────────────


def test_a_cell_names_the_grammar_and_the_document_it_was_measured_on(
    tmp_path: Path,
) -> None:
    """A length says a fixture was resized; only a digest says it was EDITED.

    An edited grammar with one seat refreshed leaves every other cell in the
    file reading as a measurement of the current language, and the date, the
    round count and the character count all agree with that reading.
    """
    path = tmp_path / "artifact.json"
    bench = _bench("csv")

    _dump_json(path, Run(7, 16, False), [_block(bench, {"lexic-pda": [0.5]})])

    record = json.loads(path.read_text(encoding="utf-8"))["provenance"]["csv"]
    assert record["lexic-pda"]["grammar_digest"] == digest(bench.source)
    assert record["lexic-pda"]["document_digest"] == digest(bench.corpus)
    assert digest(bench.source) != digest(bench.source + "\n"), "digest must move"


def test_the_committed_cells_were_measured_on_this_trees_grammars() -> None:
    """The published numbers and the fixtures in the tree must be one pair."""
    data = json.loads(COMPETITORS.read_text(encoding="utf-8"))
    by_name = {bench.name: bench for bench in BENCHES}
    for grammar, cells in data["provenance"].items():
        bench = by_name.get(grammar)
        if bench is None:
            pytest.skip(f"{grammar} is not compiled in this process")
        for seat, record in cells.items():
            document = bench.full if record["scale"] == "full" else bench.corpus
            assert record["grammar_digest"] == digest(bench.source), f"{grammar}/{seat}"
            assert record["document_digest"] == digest(document), f"{grammar}/{seat}"


def test_a_row_whose_displayed_cells_disagree_on_the_grammar_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A table row is a comparison, so its cells must share a grammar."""
    records = json.loads(COMPETITORS.read_text(encoding="utf-8"))["provenance"]
    records["csv"]["lexic-pda"] = dict(
        records["csv"]["lexic-pda"], grammar_digest="0000000000000000"
    )
    monkeypatch.setattr(render_readme, "cell_records", lambda: records)

    with pytest.raises(SystemExit, match="different grammars"):
        render_readme.row_grammar("csv", ["lexic-pda", "lexic-earley"])


def test_a_row_read_through_seats_that_agree_is_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal is about the DISPLAYED cells, not every cell in the file."""
    records = json.loads(COMPETITORS.read_text(encoding="utf-8"))["provenance"]
    records["csv"]["lexic-pda"] = dict(
        records["csv"]["lexic-pda"], grammar_digest="0000000000000000"
    )
    monkeypatch.setattr(render_readme, "cell_records", lambda: records)

    assert render_readme.row_grammar("csv", ["lexic-earley"]) != "0000000000000000"


def test_display_seats_all_name_a_seat_the_artifact_holds() -> None:
    """A misspelt display seat is dropped in silence and the caption still adds up.

    The list once carried `antlr-java`, which no seat answers to, so the table
    rendered one column short of what the list asks for and nothing said so.
    """
    engines = json.loads(COMPETITORS.read_text(encoding="utf-8"))["engines"]
    unknown = [name for name in render_readme.DISPLAY_SEATS if name not in engines]
    assert unknown == [], unknown


def test_an_unknown_display_seat_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The renderer applies to its own list the rule ``--seats`` applies to the CLI's."""
    monkeypatch.setattr(
        render_readme, "DISPLAY_SEATS", (*render_readme.DISPLAY_SEATS, "antlr-java")
    )

    with pytest.raises(SystemExit, match="antlr-java"):
        render_readme.competitor_data()


def test_a_warm_up_that_never_settled_publishes_no_cell() -> None:
    """A JIT mid-descent reads 2-3x above the level the process actually holds.

    That verdict used to reach the console and nowhere else, so a refresh
    spliced a soft number into the artifact indistinguishably from a settled
    one. It is a refusal now, with the parses spent in the words.
    """
    settled = ReportRow([0.5], None, None, (2400, True), None, 0.0)
    moving = ReportRow([0.5], None, None, (2400, False), None, 0.0)
    samples = {"antlr": [0.5], "antlr-lex": [0.5], "lexic-pda": [0.5]}

    refused = _unsettled(
        {"antlr": settled, "antlr-lex": moving, "lexic-pda": _WARMLESS}, samples
    )

    assert sorted(refused) == ["antlr-lex"]
    assert "2400" in refused["antlr-lex"]


def test_a_settled_seat_records_the_budget_its_number_stands_on(
    tmp_path: Path,
) -> None:
    """2,400 warm parses and 24 are not the same claim; the cell used to say neither."""
    path = tmp_path / "artifact.json"
    bench = _bench("csv")
    block = _block(bench, {"antlr": [0.5], "lexic-pda": [0.5]})._replace(
        warmed={"antlr": 2400}
    )

    _dump_json(path, Run(7, 16, False), [block])

    record = json.loads(path.read_text(encoding="utf-8"))["provenance"]["csv"]
    assert record["antlr"]["warmed"] == 2400
    assert record["lexic-pda"]["warmed"] is None


def test_a_filtered_run_that_missed_the_anchor_leaves_the_floor_alone(
    tmp_path: Path,
) -> None:
    """The floor is one number per grammar with no record of the engine behind it.

    Anchored on whichever row measured first, ``--seats antlr`` replaced csv's
    floor with a JVM-measured control and ``--seats lark-earley`` replaced it
    again — three numbers for one cell, each written without a word.
    """
    path = tmp_path / "artifact.json"
    before = _seeded(path)
    bench = _bench("csv")

    _dump_json(path, Run(7, 16, False), [_block(bench, {"antlr": [0.5]}, floor=None)])

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["noise_floor_percent"] == before["noise_floor_percent"]
    assert after["values"]["csv"]["antlr"] == 0.5, "the cell itself is still written"
