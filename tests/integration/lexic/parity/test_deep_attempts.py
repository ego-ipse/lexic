"""A right recursion through an attempt, as deep as the document: the
predictive engine against Earley.

``root ::= x root | x`` cannot choose its arm at ``x``: both admit the same
text, so the attempt runs the recursive arm as a sub-run — whose ``root`` is
the same attempt again, one level down, all the way to the document's end.
Up to the parse's in-place depth each sub-run is driven where its caller
stands; past it the sub-runs suspend and the one at the depth settles them at
their floors, so the Python stack stops growing: these documents run ten times
the recursion limit deep, in each spelling.
"""

from __future__ import annotations

import gc
import inspect
import sys

import pytest

from lexic.compile import compile_text
from lexic.parsing import trace
from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.pda.core.errors import Suspended
from lexic.parsing.pda.runtime.kernel import decisions
from lexic.parsing.pda.runtime.kernel.kernel import NestingKernel, PdaKernel, pda_model
from lexic.parsing.pda.runtime.kernel.verdicts.floors import Floors
from lexic.parsing.pda.runtime.kernel.verdicts.verdicts import Verdicts
from tests import parity_helpers

_X = 'x ::= "a" [b-z]+ ";"\n'
_ENTRY = 'entry ::= e ";" tail*\ntail ::= "," e\ne ::= [a-z]+\n'
SPELLINGS = {
    "recursive-first": ("root ::= x root | x\n" + _X, "abc;"),
    "recursive-last": ("root ::= x | x root\n" + _X, "abc;"),
    "entries": ("root ::= entry root | entry\n" + _ENTRY, "abc;,de,fgh"),
    "audited": ('doc ::= root+\nroot ::= x | x root\nx ::= "a" [b-z]* ";"\n', "ab;"),
}
"""The two witnesses, the recursion on either arm, and one whose recursion
runs through the AUDIT: ``root+`` lets the short arm compose mid-document, so
it wins and the recursive arm is the audited one."""

_NOISE = (
    "n ::= nunit+\nm ::= nunit+\n"
    'nunit ::= " " | cl\ncl ::= "#" [a-z]* "\\n"\nitem ::= "x"\n'
)
FORKING = (
    "# @non-semantic n m\n"
    'root ::= unit root | unit "!"\nunit ::= a | b\n'
    'a ::= item n? m? item ";"\nb ::= item n? m? item "."\n' + _NOISE
)
"""Each unit's attempt runs inside the one before it, and inside each a noise
run's end is a boundary both ways of which are viable: a live set's sides are
forked under every sub-run the document has opened so far. Both of ``root``'s
arms hold a frame, so the stack names every sub-run's caller."""


def _forking_text(units: int) -> str:
    """``units`` units of :data:`FORKING`, then the closing ``!``."""
    return "x #a\nx;" * units + "!"


@pytest.mark.parametrize("spelling", SPELLINGS, ids=SPELLINGS)
def test_past_the_recursion_limit_parses_on_the_predictive_engine(
    spelling: str,
) -> None:
    """Ten times the interpreter's recursion limit, in units — a third of it
    for the audited spelling, whose every level's audit re-runs the rest of
    the document, so that its parse stays quadratic: the predictive engine
    derives the document, and at ten units its model is Earley's."""
    grammar, unit = SPELLINGS[spelling]
    compiled = compile_text(grammar)
    limit = sys.getrecursionlimit()
    text = unit * (limit // 3 if spelling == "audited" else 10 * limit)
    assert pda_model(compiled.pda_tables(), text, compiled.executor).to_text() == text
    predictive, gated = parity_helpers.answers(grammar, f"deep-{spelling}", unit * 10)
    assert predictive == gated != parity_helpers.REFUSED


def test_two_models_deeper_than_the_recursion_limit_compare() -> None:
    """``same_value`` compares two models a right recursion built ten times
    the recursion limit deep, as an audit compares a winner and a rival:
    equal ones are the same value, and one whose innermost unit differs is
    not."""
    grammar, unit = SPELLINGS["recursive-last"]
    compiled = compile_text(grammar)
    units = 10 * sys.getrecursionlimit()
    tables, executor = compiled.pda_tables(), compiled.executor
    one = pda_model(tables, unit * units, executor)
    two = pda_model(tables, unit * units, executor)
    other = pda_model(tables, unit * (units - 1) + "abd;", executor)
    assert one is not two
    assert same_value(one, two)
    assert not same_value(one, other)


def _deepest_drive(grammar: str, text: str, monkeypatch) -> int:
    """The deepest Python stack any drive of one predictive parse ran at."""
    compiled = compile_text(grammar)
    drive = vars(PdaKernel)["_drive"]
    deepest = [0]

    def measured(self, floor=0, limit=-1):
        depth, frame = 0, inspect.currentframe()
        while frame is not None:
            depth, frame = depth + 1, frame.f_back
        deepest[0] = max(deepest[0], depth)
        return drive(self, floor, limit)

    monkeypatch.setattr(PdaKernel, "_drive", measured)
    try:
        pda_model(compiled.pda_tables(), text, compiled.executor)
    finally:
        monkeypatch.undo()
    return deepest[0]


@pytest.mark.parametrize("spelling", SPELLINGS, ids=SPELLINGS)
def test_the_python_stack_stops_growing_past_the_in_place_depth(
    spelling: str, monkeypatch
) -> None:
    """Twice and five times the in-place depth, in units: the deepest drive
    stands at the same Python depth — past the depth a unit costs no frame."""
    grammar, unit = SPELLINGS[spelling]
    bound = decisions.in_place_depth()
    shallow = _deepest_drive(grammar, unit * (2 * bound), monkeypatch)
    deep = _deepest_drive(grammar, unit * (5 * bound), monkeypatch)
    assert deep == shallow


SHALLOW = 'r ::= (x ";")+ | (x ";")+ "."\n' + 'x ::= "a" [b-z]+\n'
"""An attempt whose sub-runs cannot nest: one entry deep at any length, each
driven on a frame of its own."""


def _drives(grammar: str, text: str, monkeypatch) -> tuple[int, int]:
    """How many sub-runs one predictive parse of ``text`` drove plainly, and
    how many counted."""
    plain, counted = vars(PdaKernel)["_sub_drive"], vars(NestingKernel)["_sub_drive"]
    drives = [0, 0]

    def plainly(self, floor, limit=-1):
        drives[0] += 1
        return plain(self, floor, limit)

    def counting(self, floor):
        drives[1] += 1
        return counted(self, floor)

    compiled = compile_text(grammar)
    monkeypatch.setattr(PdaKernel, "_sub_drive", plainly)
    monkeypatch.setattr(NestingKernel, "_sub_drive", counting)
    try:
        assert (
            pda_model(compiled.pda_tables(), text, compiled.executor).to_text() == text
        )
    finally:
        monkeypatch.undo()
    return drives[0], drives[1]


@pytest.mark.parametrize(
    ("grammar", "text", "nests"),
    [(SPELLINGS["recursive-last"][0], "abc;" * 30, True), (SHALLOW, "ab;ac;.", False)],
    ids=["nesting", "shallow"],
)
def test_the_program_chooses_its_sub_runs_drive(
    grammar: str, text: str, nests: bool, monkeypatch
) -> None:
    """A program whose sub-runs can nest past the in-place depth drives every
    one counted; one whose sub-runs cannot drives every one plainly, on the
    kernel the count is not part of."""
    assert compile_text(grammar).pda_tables().program.nests is nests
    plain, counted = _drives(grammar, text, monkeypatch)
    assert (counted if nests else plain) > 0
    assert (plain if nests else counted) == 0


@pytest.mark.parametrize(
    ("grammar", "units", "watched"),
    [
        (SPELLINGS["recursive-last"][0], 10, trace.WatchedNestingKernel),
        (SHALLOW, 0, trace.WatchedKernel),
    ],
    ids=["nesting", "shallow"],
)
def test_a_watched_run_chooses_the_kernel_its_program_does(
    grammar: str, units: int, watched: type, monkeypatch
) -> None:
    """A watched run parses on the watched twin of the kernel its program
    chooses: one that can nest derives a right recursion ten times the
    recursion limit deep, as the unwatched parse does; one that cannot runs
    the plain watched kernel."""
    text = "abc;" * (units * sys.getrecursionlimit()) if units else "ab;ac;."
    chosen = []
    real = trace.kernel_for

    def choosing(tables, plain, nesting):
        chosen.append(real(tables, plain, nesting))
        return chosen[-1]

    compiled = compile_text(grammar)
    monkeypatch.setattr(trace, "kernel_for", choosing)
    run = trace.watch(compiled.pda_tables(), text, compiled.executor, cap=16)
    assert chosen == [watched]
    assert run[3]


def _nesting(grammar: str, text: str, monkeypatch) -> int:
    """How many sub-runs deep ``text`` nests on the Python stack, unbounded."""
    real = vars(decisions.Attempting)["_attempt_run"]
    deepest, live = [0], [0]

    def counted(self, sub, pos, mark):
        live[0] += 1
        deepest[0] = max(deepest[0], live[0])
        try:
            return real(self, sub, pos, mark)
        finally:
            live[0] -= 1

    compiled = compile_text(grammar)
    monkeypatch.setattr(decisions, "SYNC_DEPTH", sys.maxsize)
    monkeypatch.setattr(decisions.Attempting, "_attempt_run", counted)
    try:
        pda_model(compiled.pda_tables(), text, compiled.executor)
    finally:
        monkeypatch.undo()
    return deepest[0]


def _suspensions(grammar: str, text: str, bound: int, monkeypatch) -> tuple[int, str]:
    """How many sub-runs suspend parsing ``text`` at in-place depth
    ``bound``, and the parse's ``to_text``."""
    real = vars(decisions.Attempting)["_attempt_run"]
    count = [0]

    def counted(self, sub, pos, mark):
        try:
            return real(self, sub, pos, mark)
        except Suspended:
            count[0] += 1
            raise

    compiled = compile_text(grammar)
    monkeypatch.setattr(decisions, "SYNC_DEPTH", bound)
    monkeypatch.setattr(decisions.Attempting, "_attempt_run", counted)
    try:
        model = pda_model(compiled.pda_tables(), text, compiled.executor)
    finally:
        monkeypatch.undo()
    return count[0], model.to_text()


@pytest.mark.parametrize("past", [-1, 0, 1], ids=["under", "at", "over"])
def test_a_document_across_the_in_place_depth(past: int, monkeypatch) -> None:
    """A document whose sub-runs nest one fewer, as many and one more deep
    than the in-place depth: under and at it none suspends — the one at the
    depth drives, with nothing past it — and over it the innermost does."""
    grammar, unit = SPELLINGS["recursive-first"]
    text = unit * 12
    nesting = _nesting(grammar, text, monkeypatch)
    suspended, back = _suspensions(grammar, text, nesting - past, monkeypatch)
    assert back == text
    assert bool(suspended) == (past > 0), (nesting, suspended)


@pytest.mark.parametrize("spelling", SPELLINGS, ids=SPELLINGS)
def test_every_sub_run_suspended_builds_the_model_driven_in_place(
    spelling: str, monkeypatch
) -> None:
    """An in-place depth of nothing — every sub-run past the first suspends
    and is settled at its floor, attempts and audits resumed there — builds
    the model a depth past the document's builds."""
    grammar, unit = SPELLINGS[spelling]
    compiled = compile_text(grammar)
    text = unit * 30
    models = []
    for bound in (0, sys.maxsize):
        monkeypatch.setattr(decisions, "SYNC_DEPTH", bound)
        models.append(pda_model(compiled.pda_tables(), text, compiled.executor).dump())
    assert _suspensions(grammar, text, 0, monkeypatch)[0] > 0
    assert models[0] == models[1]


@pytest.mark.parametrize("bound", [0, 1, 3])
def test_a_side_forked_inside_suspended_sub_runs_gives_earleys_model(
    bound: int, monkeypatch
) -> None:
    """A forking document whose sub-runs suspend: its sides are forked above
    floors no Python call waits on, read them off the stack and settle them
    as the live drive does — and the parse builds Earley's model."""
    text = _forking_text(12)
    assert _suspensions(FORKING, text, bound, monkeypatch)[0] > 0
    monkeypatch.setattr(decisions, "SYNC_DEPTH", bound)
    predictive, gated = parity_helpers.answers(FORKING, f"deep-forking-{bound}", text)
    assert predictive == gated != parity_helpers.DECLINED


def _nested(grammar: str) -> str:
    """``grammar`` inside a right recursion through an attempt, so that every
    sub-run its start rule's parse runs is nested inside another one."""
    start = grammar.split("::=")[0].strip()
    return f'wrap ::= {start} "%" wrap | {start} "%"\n' + grammar


STEALING = 'x ::= t* rest\nt ::= "ab" | ("a" | "aa")+ "a"\nrest ::= [a]*\n'
"""``t``'s second arm runs framed and takes the ``a`` it ends on, so its sub-run
misses item by item and the rule's island is asked; at ``aaa`` that island
ends after two characters or three, and ``rest`` can follow either."""

RIVALLED = (
    "doc ::= root+\nroot ::= x | x y | x y y\n"
    'x ::= "a" [b-z]* ";"\ny ::= "a" [b-z]* "!"\n'
)
"""``x`` wins ``root``'s attempt, ``x y`` is a rival ending elsewhere that could
compose, and ``x y y`` is audited after it: the audit settles on both."""


def _settled_on(
    grammar: str, text: str, monkeypatch, method: str, path
) -> tuple[int, tuple[str, str]]:
    """How many floors a depth-0 parse of ``text`` settles through ``path`` —
    a predicate on ``Floors.<method>``'s kernel and floor — and its answers."""
    real = vars(Floors)[method]
    hits = [0]

    def spied(self, floor, outcome):
        hits[0] += path(self, floor, outcome)
        return real(self, floor, outcome)

    monkeypatch.setattr(decisions, "SYNC_DEPTH", 0)
    monkeypatch.setattr(Floors, method, spied)
    try:
        answers = parity_helpers.answers(_nested(grammar), "deep-live", text)
    finally:
        monkeypatch.undo()
    return hits[0], answers


def _within_misses(
    grammar: str, text: str, monkeypatch, owner: type, name: str
) -> tuple[int, tuple[str, str]]:
    """How many times a depth-0 parse of ``text`` calls ``owner.<name>`` while
    settling a sub-run that missed above its floor, and its answers."""
    missed, real = vars(Floors)["_missed_at"], vars(owner)[name]
    inside, calls = [0], [0]

    def settling(self, floor, failure, live):
        inside[0] += 1
        try:
            return missed(self, floor, failure, live)
        finally:
            inside[0] -= 1

    def counted(self, *args):
        calls[0] += inside[0] > 0
        return real(self, *args)

    monkeypatch.setattr(decisions, "SYNC_DEPTH", 0)
    monkeypatch.setattr(Floors, "_missed_at", settling)
    monkeypatch.setattr(owner, name, counted)
    try:
        answers = parity_helpers.answers(_nested(grammar), "deep-live", text)
    finally:
        monkeypatch.undo()
    return calls[0], answers


def test_a_suspended_sub_run_that_misses_by_stealing_asks_the_island(
    monkeypatch,
) -> None:
    """A miss above a live floor asks the rule's island, as the sub-run's call
    does: settled as a miss, the parse declines a document Earley derives."""
    asked, (predictive, gated) = _within_misses(
        STEALING, "aaa%aaa%", monkeypatch, decisions.Attempting, "_stolen_back"
    )
    assert asked > 0
    assert predictive == gated != parity_helpers.DECLINED


SIDE_MISSES = {"shrunk": "aaab%%", "generated": "a%aa%%%aa%%abababaaabaaa%%"}
"""Documents a side's miss inside ``t`` must leave a miss: the second is a
generated sample of :data:`STEALING` nested, the first what it shrinks to."""


@pytest.mark.parametrize("bound", [None, 0], ids=["default", "depth-0"])
@pytest.mark.parametrize("text", SIDE_MISSES.values(), ids=SIDE_MISSES)
def test_a_miss_above_a_sides_floor_asks_no_island(
    text: str, bound: int | None, monkeypatch
) -> None:
    """A miss above a side's floor is that reading's death, not its sub-run's
    outcome: asked there, the rule's island answers for the sub-run beside the
    reading that took the other way, and the two meet where the decider cannot
    separate them, on documents the predictive engine answers without it."""
    if bound is not None:
        monkeypatch.setattr(decisions, "SYNC_DEPTH", bound)
    predictive, gated = parity_helpers.answers(_nested(STEALING), "deep-side", text)
    assert predictive == gated != parity_helpers.DECLINED


def test_an_islands_ends_from_a_suspended_sub_run_are_its_iteration(
    monkeypatch,
) -> None:
    """Ends the stolen island raises for a suspended sub-run are claimed for
    it, as its call claims them, and the iteration they are the whole outcome
    of ranks them: unclaimed, they decline the document."""
    ranked, (predictive, gated) = _within_misses(
        STEALING, "aaa%aaa%", monkeypatch, Verdicts, "_iteration_ends"
    )
    assert ranked > 0
    assert predictive == gated != parity_helpers.DECLINED


def test_an_audit_resumed_at_a_floor_keeps_the_rivals_found_before(
    monkeypatch,
) -> None:
    """An audited entry suspended after a rival was found settles with that
    rival, so the decider ranks it: restarted with none, the winner commits
    and the document fails."""

    def with_rivals(_kernel, floor, _got) -> bool:
        entry = floor[5]
        return entry is not None and entry[3] is not None and entry[4] is not None

    hits, (predictive, gated) = _settled_on(
        RIVALLED, "ab;ac!%ab;ac!%", monkeypatch, "_settle_floor", with_rivals
    )
    assert hits > 0
    assert predictive == gated != parity_helpers.DECLINED


def test_a_failure_held_above_a_floor_leaves_no_cycle(monkeypatch) -> None:
    """A sub-run that fails above its floor — the last unit's recursive arm,
    at the end of the document — is settled from a held failure, held
    without the traceback that would hold the drive's frame: the parse leaves
    nothing for the collector."""
    grammar, unit = SPELLINGS["recursive-first"]
    compiled = compile_text(grammar)
    tables = compiled.pda_tables()
    monkeypatch.setattr(decisions, "SYNC_DEPTH", 0)
    gc.collect()
    gc.disable()
    try:
        pda_model(tables, unit * 40, compiled.executor)
        assert gc.collect() == 0
    finally:
        gc.enable()
