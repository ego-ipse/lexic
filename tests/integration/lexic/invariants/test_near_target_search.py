"""The cut search near its targets finds what a whole-document scan finds.

A plan's candidates used to be every depth-0 mark of the document, scanned and
rebased before a single cut was chosen. They are now searched for around each
target: the depth at a stretch's start is a count, and only the stretch is
walked. The claim that makes that legal is narrow and worth stating: depth is
openers minus closers before an offset, so a stretch read from its counted
depth reports exactly the depth-0 marks a whole-document walk reports inside it.

A claim of that shape is proved by disagreement, not by inspection, so every
case here reads the same document THREE ways — the search, walked nearest-first
from offset 0; the scanner's whole-document level; and a depth walk restated by
hand in this file — and requires all three to agree. Two arms would let a
mistake in the search and a matching mistake in a restatement pass together;
the third is written out longhand here precisely so it cannot drift with
either.

Vacuity is the failure mode this invites, in two ways. A grammar whose plans
all walk or cut on an envelope has no shared scanner at all, and a document
that yields no mark at depth 0 makes every arm the empty list.
`test_the_roster_reaches_the_search` and the non-empty assertions in each case
are what keep either from passing for nothing.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.parsing.parallel.discovery.scan import Scanner, spelling_offsets
from lexic.parsing.parallel.plan.cuts import (
    Level,
    after_mark,
    cut_offsets,
    reads_a_sweep,
    shared_scanner,
)
from lexic.parsing.parallel.plan.split import SplitPlan
from lexic.parsing.parallel.planner import safe_plans, split_plans
from lexic.parsing.parallel.policy import MIN_CHUNK
from lexic.parsing.parallel.roles.derive import Roles
from tests.paths import GROUND_TRUTH
from tools.benchmark.cases.grammars import BENCHES

WORKERS = (2, 4, 16)
"""Three worker counts, so no result rests on one set of targets."""

JSON_GRAMMARS = ("json.gbnf", "json.abnf")
"""Both ground-truth json formulations. Both quote their strings, so both
carry an opaque interior and are REFUSED the shared scanner — which is the
property this file pins for them, rather than an equality it could not test."""


def hand_level(scanner: Scanner, text: str) -> list[int]:
    """The depth-0 separator offsets, restated longhand — the third arm.

    Deliberately not a call into `Scanner.level`: a reading that shares no code
    with either arm is the only one that can catch both being wrong the same
    way. Every opener, closer and separator occurrence is found, ordered, and
    the depth walked one event at a time.
    """
    events: list[tuple[int, int]] = []
    for char in scanner.openers:
        events += [(at, 1) for at in spelling_offsets(text, char, 0, len(text))]
    for char in scanner.closers:
        events += [(at, -1) for at in spelling_offsets(text, char, 0, len(text))]
    starts = {
        at
        for mark in scanner.separators
        for at in spelling_offsets(text, mark, 0, len(text))
    }
    events += [(at, 0) for at in starts]
    found: list[int] = []
    depth = 0
    for at, role in sorted(events):
        depth += role
        if role == 0 and depth == 0:
            found.append(at)
    return found


def expected(plan: SplitPlan, text: str, level: list[int]) -> list[int]:
    """A one-character, unbounded plan's candidates out of a depth-0 level:
    its own spelling, never offset 0 for an opening mark, and never a
    terminated plan's last mark when nothing but skip follows it."""
    marks = [at for at in level if text[at] in plan.mark]
    if plan.opening:
        return [at for at in marks if at]
    if plan.terminated and marks and after_mark(plan, text, marks[-1]) == len(text):
        marks.pop()
    return marks


def sweeping_plans(grammar):
    """This grammar's certified plans, and the ones that read a sweep."""
    plans = safe_plans(split_plans(grammar), grammar)
    return plans, tuple(plan for plan in plans if reads_a_sweep(plan))


def three_arms(grammar, text: str, workers: int) -> tuple[int, int]:
    """Read every sweeping plan's candidates three ways and require agreement.

    :returns: ``(plans compared, candidates seen)`` — so a caller can refuse a
        case that compared nothing.
    """
    plans, sweepers = sweeping_plans(grammar)
    shared = shared_scanner(grammar, plans)
    if shared is None or not sweepers:
        return 0, 0
    whole = shared.level(text, 0, len(text), 0)
    assert whole == hand_level(shared, text), (
        "the scanner's level and a longhand depth walk disagree"
    )
    compared = seen = 0
    for plan in sweepers:
        if any(len(mark) > 1 for mark in plan.mark) or plan.bound is not None:
            continue  # thinning and bounds are the unit tests' and the probe's
        searched = list(
            cut_offsets(plan, text, workers, Level(shared, text)).marks(
                0, 0, len(text) + 1
            )
        )
        assert searched == expected(plan, text, whole), f"{plan.mark}: search moved"
        compared += 1
        seen += len(searched)
    return compared, seen


# ── the roster, every bench grammar over its own document ─────────────────


@pytest.mark.parametrize("workers", WORKERS)
@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_every_bench_grammar_searches_identically(bench, workers: int) -> None:
    """Each bench grammar, its full document, three readings, three counts."""
    three_arms(bench.compiled.codegen_grammar, bench.full, workers)


@pytest.mark.parametrize("workers", WORKERS)
@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_every_bench_grammar_cuts_identically(bench, workers: int) -> None:
    """The cuts chosen through the shared scanner are the plan's own.

    The candidates are what is searched; the cuts are the choice made from
    them. A search that preserved the candidates but shifted the choice would
    pass the test above and still split the document somewhere else.
    """
    grammar = bench.compiled.codegen_grammar
    plans, sweepers = sweeping_plans(grammar)
    shared = shared_scanner(grammar, plans)
    if shared is None or not sweepers:
        return
    for plan in sweepers:
        assert (
            cut_offsets(
                plan, bench.full, workers, Level(plan.scanner, bench.full)
            ).offsets
            == cut_offsets(plan, bench.full, workers, Level(shared, bench.full)).offsets
        ), f"{plan.mark}: the shared scanner moved a cut"


def test_the_roster_reaches_the_search() -> None:
    """The roster really exercises the search, by count rather than by name.

    Every equality above is vacuous on a grammar with no shared scanner, and
    most of the roster has none. If this stops holding, the file is comparing
    nothing with nothing and proves nothing.
    """
    reaching = {}
    for bench in BENCHES:
        plans, marks = three_arms(bench.compiled.codegen_grammar, bench.full, 4)
        if plans:
            reaching[bench.name] = (plans, marks)
    assert len(reaching) >= 4, f"only {sorted(reaching)} reach the search"
    assert sum(marks for _plans, marks in reaching.values()) >= 500, (
        f"too few candidates compared for the equality to mean anything: {reaching}"
    )
    assert any(plans >= 2 for plans, _marks in reaching.values()), (
        "no grammar asks a second sweeping plan — the shared scanner is never "
        f"read by more than one plan: {reaching}"
    )


# ── both json formulations: refused the sweep, and still answering ────────


@pytest.mark.parametrize("workers", (2, 8))
@pytest.mark.parametrize("name", JSON_GRAMMARS)
def test_a_quoted_json_grammar_takes_no_shared_scanner(name: str, workers: int) -> None:
    """Both ground-truth json grammars quote their strings, so neither reads a
    depth-counted search — and each still answers through the ordinary entry.

    Pinned rather than assumed: the refusal is asserted, so this case fails
    rather than passing vacuously if such a grammar ever becomes eligible.
    """
    grammar = compile_from_path(GROUND_TRUTH / name).codegen_grammar
    plans, sweepers = sweeping_plans(grammar)
    assert shared_scanner(grammar, plans) is None or not sweepers, (
        f"{name} now reads a shared scanner — this case no longer pins a refusal"
    )
    document = (
        "{" + ", ".join(f'"k{i}": [1, 2, {{"b": "x, y"}}]' for i in range(200)) + "}"
    )
    assert len(document) > 2 * MIN_CHUNK
    compiled = compile_from_path(GROUND_TRUTH / name)
    assert compiled.parse(document, cores=workers).to_text() == document


# ── the differential can fail ─────────────────────────────────────────────


PAIRED = 'root ::= item ("," item)*\nitem ::= "(" word ")"\nword ::= [a-z]+\n'
"""A separated repetition whose items are a REAL bracket pair — so the depth
counted at a stretch's start decides which commas stand at 0. (`item`'s
interior is a rule reference, which is what makes `(` and `)` a depth-tracked
pair; see `roles.runs.bracket_arms`' ``enclosing`` test.)"""


def paired_document(units: int) -> str:
    """A PAIRED document long enough to clear the chunk floor."""
    return ",".join(f"(unit{chr(97 + i % 26)})" for i in range(units))


class _Shifted(Scanner):
    """A scanner whose depth count is off by one past ``at`` — the sabotage."""

    def __init__(self, scanner: Scanner, at: int) -> None:
        """Copy ``scanner``'s roles; count one opener too many past ``at``."""
        super().__init__(Roles((), ()))
        self.__dict__.update(vars(scanner))
        self.at = at

    def drift(self, text: str, lo: int, hi: int) -> int:
        """The honest count, plus one when the stretch crosses ``at``."""
        return super().drift(text, lo, hi) + (lo <= self.at < hi)


def test_a_perturbed_depth_is_caught() -> None:
    """A wrong count at a stretch's start must NOT pass.

    Every case above compares the search against whole-document walks. If the
    counted depth were ignored — every stretch read from 0, say — all of them
    could still agree on a document whose marks all stand at depth 0. Counting
    one opener too many must change the answer.
    """
    grammar = compile_text(PAIRED, cache_key="near-target-paired").codegen_grammar
    text = paired_document(1200)
    assert len(text) > 4 * MIN_CHUNK
    plans, sweepers = sweeping_plans(grammar)
    shared = shared_scanner(grammar, plans)
    assert shared is not None and sweepers, "the fixture must read a shared scanner"
    assert shared.openers and shared.closers, "the fixture must count a depth"
    for plan in sweepers:
        end = len(text) + 1
        truthful = list(
            cut_offsets(plan, text, 4, Level(shared, text)).marks(0, 0, end)
        )
        assert len(truthful) > 2, "the plan selected too little to perturb"
        sabotaged = _Shifted(shared, len(text) // 2)
        wrong = list(
            cut_offsets(plan, text, 4, Level(sabotaged, text)).marks(0, 0, end)
        )
        assert wrong != truthful


# ── a document that genuinely carries no mark at depth 0 ───────────────────


NO_DEPTH_ZERO = 'root ::= item ("," item)*\nitem ::= "(" word ")"\nword ::= [a-z]+\n'
"""A separated repetition whose separator sits inside a REAL bracket pair.

`item`'s interior is a rule reference (`word`), which is what qualifies `(`
and `)` as a genuine depth-tracked pair — an inline character class in the
same spot would not (see `roles.runs.bracket_arms`' ``enclosing`` test). A document
that opens one such pair and never closes it holds every comma at depth 1
forever: real separator occurrences, at a depth the plan never keys on. That
is distinct from `test_empty_sweep_gate.py`'s witness, whose separator SET is
itself empty — here the vocabulary is fine and the DOCUMENT is what empties.
"""


def unclosed_document(commas: int) -> str:
    """A `NO_DEPTH_ZERO` document with every comma inside one open paren."""
    return "(" + "," * commas


def no_depth_zero_plan() -> SplitPlan:
    """`NO_DEPTH_ZERO`'s one sweeping plan."""
    grammar = compile_text(NO_DEPTH_ZERO, cache_key="no-depth-zero").codegen_grammar
    _plans, sweepers = sweeping_plans(grammar)
    assert len(sweepers) == 1, "the fixture must read exactly one shared scanner"
    return sweepers[0]


@pytest.mark.parametrize("workers", WORKERS)
def test_a_document_with_no_depth_zero_mark_has_no_candidate(workers: int) -> None:
    """No mark stands at depth 0, and the search says so.

    Here the scanner is really asked, finds real separator occurrences (every
    comma), and the counted depth genuinely leaves none at 0 — so the search
    counts the whole document for the few candidates the ceiling needs, finds
    none, and cuts nowhere.
    """
    plan = no_depth_zero_plan()
    text = unclosed_document(20 * MIN_CHUNK)
    assert len(spelling_offsets(text, ",", 0, len(text))) == len(text) - 1
    assert plan.scanner.level(text, 0, len(text), 0) == []
    chosen = cut_offsets(plan, text, workers, Level(plan.scanner, text))
    assert chosen.offsets == []
    assert not list(chosen.marks(0, 0, len(text) + 1))
