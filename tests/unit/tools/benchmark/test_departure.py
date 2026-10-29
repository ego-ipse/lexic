"""Where a split's model departs from its own sequential one, the job that asks,
and the gate rule that reads the answer.

The gate asks this of a base whose head stopped splitting: a head that gave up
a WRONG split corrected it, one that gave up a right split lost work. The
witness is the ambiguous pair list, where ``(0),(1)`` is one long pair or two
short ones and the decider keeps the long — so a carving can spell the
document back exactly and still read it wrong.
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import pytest

from lexic.compile import compile_text
from lexic.model import GrammarModel
from tests.unit.tools.benchmark.benchmark_helpers import BASE, CONTRACT, HEAD, OBSERVED
from tools.benchmark import compare
from tools.benchmark.cases.grammars import BENCHES
from tools.benchmark.execution import isolation, worker
from tools.benchmark.execution.isolation import Job, RowRequest
from tools.benchmark.judging import arithmetic
from tools.benchmark.measurement import occupancy
from tools.benchmark.measurement.contract import RowResult
from tools.benchmark.measurement.occupancy import departure, split_departure

PAIRS = (
    'root ::= arr\narr ::= "[" pair ("," pair)* "]"\n'
    'pair ::= "(" num ")" "," "(" num ")" | "(" num ")"\nnum ::= [0-9]+\n'
)
DOCUMENT = "[(0),(1),(2),(3),(4)]"
COMPILED = compile_text(PAIRS, cache_key="departure-pairs")
"""One artefact for every model here: equality is class-aware, and two compiles
synthesise two sets of classes."""


def _sequential() -> GrammarModel:
    """The decider's reading of :data:`DOCUMENT`: long, long, short."""
    return COMPILED.parse(DOCUMENT, cores=1)


def _short_from_two(sequential: GrammarModel) -> GrammarModel:
    """The same text read with the second pair broken into two short ones.

    Built from the sequential model's own classes, so it differs in carving
    and in nothing else.
    """
    arr = sequential[0]
    item, short, num = arr[1][0], arr[1][1][0], arr[0][0]
    rest = tuple(_like(item, _like(short, _like(num, digit))) for digit in "234")
    return _like(sequential, _like(arr, arr[0], rest))


def _like(model: GrammarModel, *values: object) -> GrammarModel:
    """A model of ``model``'s class over ``values``, through its own licence."""
    build, _defaults, _fields = type(model).fast_construct()
    return build(list(values))


def test_equal_models_do_not_depart() -> None:
    """A split that built the sequential model has nothing to report."""
    assert departure(_sequential(), _sequential()) is None


def test_a_carving_departs_at_the_item_it_reads_differently() -> None:
    """Same text, different carving from the second pair on: the offset is that
    item's start — its separator — not the root that merely contains it."""
    sequential = _sequential()
    wrong = _short_from_two(sequential)
    assert wrong.to_text() == DOCUMENT, "the witness must spell the same text"
    assert wrong != sequential

    assert departure(wrong, sequential) == DOCUMENT.index(",(2)")
    assert departure(sequential, wrong) == DOCUMENT.index(",(2)")


def test_two_texts_depart_at_their_first_differing_character() -> None:
    """Models spelling different texts part where the texts do."""
    compiled = compile_text(PAIRS, cache_key="departure-texts")
    one, other = (
        compiled.parse("[(0),(1)]", cores=1),
        compiled.parse("[(0),(7)]", cores=1),
    )

    assert departure(one, other) == "[(0),(1)]".index("1")


def test_the_probe_reports_where_a_wrong_split_departs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A split handing back a wrong carving is caught against the sequential
    parse the probe runs itself; a declined split reports nothing."""
    wrong = _short_from_two(_sequential())

    monkeypatch.setattr(occupancy, "split_model", lambda *_args, **_kw: wrong)
    assert split_departure(COMPILED, DOCUMENT, 2) == DOCUMENT.index(",(2)")

    monkeypatch.setattr(occupancy, "split_model", lambda *_args, **_kw: None)
    assert split_departure(COMPILED, DOCUMENT, 2) is None


LINES = 'root ::= line+\nline ::= [a-z0-9]* nl\nnl ::= "\\n"\n'


def test_a_right_split_does_not_depart() -> None:
    """A split that engages and builds the sequential model reports nothing."""
    compiled = compile_text(LINES, cache_key="departure-lines")
    document = "".join(f"line{at}\n" for at in range(2000))
    assert occupancy.declined_reason(compiled, document, 4).declined is None

    assert split_departure(compiled, document, 4) is None


def _answering(payload: dict[str, object], seen: list[list[str]]):
    """A ``subprocess.run`` stand-in writing ``payload`` as the worker's line."""

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    return run


@pytest.mark.parametrize("departs", [17, None])
def test_the_departure_job_asks_one_count_and_reads_the_offset(
    monkeypatch: pytest.MonkeyPatch, departs: int | None
) -> None:
    """One fresh worker per count, flagged, its offset read back as given."""
    seen: list[list[str]] = []
    monkeypatch.setattr(
        isolation.subprocess, "run", _answering({"departs": departs}, seen)
    )
    job = Job(
        "pairs/lexic-mt/split-3",
        RowRequest("pairs", "lexic-mt", 5, 3, False),
        Path("b"),
    )

    assert isolation.run_departure(job) == departs
    assert "--departs" in seen[0]
    assert seen[0][seen[0].index("--cores") + 1] == "3"


def test_a_refused_departure_job_stops_rather_than_reading_sound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A row that could not be built has not shown its split is right."""
    monkeypatch.setattr(
        isolation.subprocess, "run", _answering({"refusal": "no build"}, [])
    )
    job = Job(
        "pairs/lexic-mt/split-2",
        RowRequest("pairs", "lexic-mt", 5, 2, False),
        Path("b"),
    )

    with pytest.raises(RuntimeError, match="no build"):
        isolation.run_departure(job)


def test_the_worker_answers_the_departure_question_on_a_real_row() -> None:
    """The bench's own reopening row at two workers: this tree declines its
    split, so there is no departure — and the worker says so in its wire form."""
    bench = next(one for one in BENCHES if one.name == "reopening")

    assert worker.departure_payload(bench, "lexic-mt", 1, 2, False) == {"departs": None}


def _stopped_splitting(job: Job) -> RowResult:
    """A pair whose base split and whose head declined; controls split."""
    return RowResult(
        CONTRACT, (OBSERVED._replace(engaged=not job.label.endswith("/head")),), None
    )


def _departing(at: dict[int, int | None], asked: list[int]):
    """A base whose split departs from its sequential model as ``at`` says."""

    def run_departure(job: Job) -> int | None:
        assert job.label.startswith("json/lexic-mt/") and job.root == BASE
        assert job.request.cores is not None
        asked.append(job.request.cores)
        return at[job.request.cores]

    return run_departure


def test_a_head_declining_a_split_wrong_below_the_row_s_count_is_unsound_untimed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Right at the row's four workers, wrong at three: a carving right by where
    its cuts landed. The head that declines it is not failed, not timed, and
    the row says where the base's split went wrong."""
    asked: list[int] = []
    monkeypatch.setattr(compare, "run_job", _stopped_splitting)
    monkeypatch.setattr(
        compare, "run_departure", _departing({2: None, 3: 41, 4: None}, asked)
    )

    verdict, pairing = compare.grow(compare.Arms(BASE, HEAD, 4), "json", "lexic-mt")

    assert verdict.status == (
        "base split unsound: head declines a wrong split (at 3 workers, from offset 41)"
    )
    assert verdict.pairs == 0 and math.isnan(verdict.ratio)
    assert pairing.candidate == () and pairing.head_wall == ()
    assert asked == [2, 3], "the first departure ends the search"
    assert compare.status([verdict]) == 0


def test_a_head_declining_a_split_right_at_every_count_is_still_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A base whose split builds its own sequential model at every count from
    two to the row's lost real work in the head, and the refusal stands."""
    asked: list[int] = []
    monkeypatch.setattr(compare, "run_job", _stopped_splitting)
    monkeypatch.setattr(
        compare, "run_departure", _departing({2: None, 3: None, 4: None}, asked)
    )

    with pytest.raises(ValueError, match="no longer splits") as caught:
        compare.grow(compare.Arms(BASE, HEAD, 4), "json", "lexic-mt")

    assert "every count from 2 to 4" in str(caught.value)
    assert asked == [2, 3, 4]


def test_an_untimed_row_prints_after_every_timed_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Its ``nan`` cannot scramble the slowest-first order of the timed rows."""
    unsound = arithmetic.untimed("json/lexic-mt", arithmetic.UNSOUND_BASE, "wall")
    timed = [
        arithmetic.Verdict(f"json/{name}", "ok", ratio, 0.9, 1.1, 1.2, 6, "cpu")
        for name, ratio in (("a", 0.95), ("b", 1.05), ("c", 1.0))
    ]

    compare.report_table([timed[0], unsound, *timed[1:]])

    rows = [line.split()[0] for line in capsys.readouterr().out.splitlines()[1:]]
    assert rows == ["json/b", "json/c", "json/a", "json/lexic-mt"]
