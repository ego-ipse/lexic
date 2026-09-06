"""The bench's seat filter, and the artifact write that must not overreach.

``--only`` narrows grammars; ``--seats`` narrows engines. The pair exists so a
single engine can be re-measured without restating every other cell as though
it were taken the same day — which is also why the artifact write splices and
why provenance lives per seat.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from tools.benchmark.bench import ENGINE
from tools.benchmark.cases.grammars import BENCHES
from tools.benchmark.presentation.cli import (
    _dump_json,
    _row_names,
    _seats,
)
from tools.benchmark.presentation.reporting import Block
from tools.render_readme import COMPETITORS, _measured_caption


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


def _block(bench, samples: dict[str, list[float]]) -> Block:
    """One presentation block carrying only the given seats' samples."""
    return Block(bench, samples, {}, 1.25, {}, {}, {})


def test_a_seat_filtered_write_leaves_every_other_cell_byte_identical(
    tmp_path: Path,
) -> None:
    """The whole point of the filter: refreshing one engine may not restate
    figures from another day as though they were taken together."""
    before = json.loads(COMPETITORS.read_text(encoding="utf-8"))
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    bench = _bench("csv")

    _dump_json(path, 7, 16, [_block(bench, {"lexic-pda": [0.5, 0.5, 0.5]})])

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
    before = json.loads(COMPETITORS.read_text(encoding="utf-8"))
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    bench = _bench("csv")
    order = list(before["values"]["csv"])

    _dump_json(path, 7, 16, [_block(bench, {"lexic-pda": [0.5]})])

    after = json.loads(path.read_text(encoding="utf-8"))
    assert list(after["values"]["csv"]) == order


def test_only_the_written_seats_take_todays_date(tmp_path: Path) -> None:
    """Provenance is per seat because a run refreshes some and not others.

    The fixture is dated by the test rather than read off the committed file:
    a seat this repository happened to measure today would otherwise make the
    written and unwritten dates agree, and the assertion pass for no reason.
    """
    before = json.loads(COMPETITORS.read_text(encoding="utf-8"))
    for seat in before["engines"].values():
        seat["measured"] = "2019-01-01"
    path = tmp_path / "artifact.json"
    path.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    bench = _bench("csv")

    _dump_json(path, 3, 8, [_block(bench, {"lexic-pda": [0.5]})])

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["engines"]["lexic-pda"]["rounds"] == 3
    assert (
        after["engines"]["lexic-pda"]["measured"] == datetime.date.today().isoformat()
    )
    assert after["engines"]["lexic-earley"]["measured"] == "2019-01-01"
    assert after["engines"]["lexic-earley"] == before["engines"]["lexic-earley"], (
        "an unmeasured seat's provenance must not move"
    )


def test_a_non_threaded_seat_records_no_worker_request(tmp_path: Path) -> None:
    """``cores`` is the mt rows' request; every other seat is single-threaded."""
    path = tmp_path / "artifact.json"
    bench = _bench("csv")
    _dump_json(path, 7, 16, [_block(bench, {"lexic-pda": [0.5], "lexic-mt": [0.2]})])

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["engines"]["lexic-pda"]["cores"] is None
    assert after["engines"]["lexic-mt"]["cores"] == 16


def test_the_noise_floor_is_recorded_per_grammar(tmp_path: Path) -> None:
    """A run that measured four grammars says nothing about the other eight."""
    path = tmp_path / "artifact.json"
    bench = _bench("csv")
    _dump_json(path, 7, 16, [_block(bench, {"lexic-pda": [0.5]})])

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["noise_floor_percent"] == {"csv": 1.25}


# ── the caption reads what the artifact says ──────────────────────────────


def test_one_date_reads_as_one_date() -> None:
    """Agreement is the common case and reads plainly."""
    engines = {"a": {"measured": "2026-09-06"}, "b": {"measured": "2026-09-06"}}
    assert _measured_caption(engines) == "measured 2026-09-06"


def test_seats_taken_apart_are_captioned_as_a_span() -> None:
    """One date over columns taken weeks apart claims a run that never
    happened."""
    engines = {"a": {"measured": "2026-09-01"}, "b": {"measured": "2026-09-06"}}
    assert _measured_caption(engines) == "measured 2026-09-01 to 2026-09-06, per seat"


def test_the_committed_artifact_carries_provenance_for_every_seat() -> None:
    """The file the README renders from must be able to answer the question."""
    data = json.loads(COMPETITORS.read_text(encoding="utf-8"))
    assert data["schema"] == 2
    missing = sorted(
        name for name, meta in data["engines"].items() if "measured" not in meta
    )
    assert missing == [], missing
