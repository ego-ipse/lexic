"""Tests for ``lexic.parsing.parallel.plan.cuts`` — where a document is cut.

The plan says which spellings bound a unit; this says which of their
occurrences a given document is actually cut at. The floor is absolute in both
directions, and an OPENING mark belongs to the piece after it rather than the
piece before — the one arithmetic difference between a proposal and a proof.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.parallel import policy as policy_module
from lexic.parsing.parallel.discovery.scan import Scanner
from lexic.parsing.parallel.plan.cuts import (
    FlatLevel,
    Level,
    PlanMarks,
    after_mark,
    cut_offsets,
    cut_spans,
    level_of,
    sole_mark,
)
from lexic.parsing.parallel.plan.split import SplitPlan, matched, spellings
from lexic.parsing.parallel.planner import safe_plans, split_plans
from lexic.parsing.parallel.policy import MIN_CHUNK
from lexic.parsing.parallel.pool import WorkPool
from tests.unit.lexic.parsing.parallel.envelope_fixtures import ENVELOPE_SOURCE
from tests.unit.lexic.parsing.parallel.speculation_fixtures import (
    ANNOUNCED,
    announced_doc,
)

LINES = 'root ::= line+\nline ::= [a-z0-9]* nl\nnl ::= "\\n"\n'


def _lines(size: int) -> str:
    """A LINES document of at least ``size`` characters."""
    out: list[str] = []
    total = 0
    while total < size:
        out.append(f"line{len(out)}\n")
        total += len(out[-1])
    return "".join(out)


def _safe(source: str, key: str) -> tuple[SplitPlan, ...]:
    """Every plan ``source`` certifies."""
    compiled = compile_text(source, cache_key=key)
    grammar = compiled.codegen_grammar
    safe = safe_plans(split_plans(grammar), compiled.split_analysis or compiled.grammar)
    assert safe, "the fixture must certify a plan"
    return safe


def _plan(source: str, key: str) -> SplitPlan:
    return _safe(source, key)[0]


# ── sole_mark ─────────────────────────────────────────────────────────────


def test_a_one_spelling_plan_names_its_mark_and_a_set_declines() -> None:
    """The proofs stated over a single mark have no reading over a set, and
    say so by declining rather than picking one of its members."""
    plan = _plan(LINES, "cuts-lines")
    assert sole_mark(plan) == "\n"
    assert sole_mark(plan._replace(mark=frozenset({"\n", ";"}))) == ""


# ── closing vs opening arithmetic ─────────────────────────────────────────


def test_a_closing_mark_belongs_to_the_piece_before_it() -> None:
    """A terminated unit OWNS its terminator, so the piece keeps it and the
    next one starts past it."""
    plan = _plan(LINES, "cuts-lines")
    text = "one\ntwo\n"
    assert after_mark(plan, text, 3) == 4


def test_an_opening_mark_belongs_to_the_piece_after_it() -> None:
    """A proposal marks where the NEXT unit begins, so the piece before it
    ends there and the mark itself is the next piece's first character."""
    plan = _plan(ANNOUNCED, "cuts-announced")
    assert plan.opening
    text = announced_doc(4)
    at = text.index("#", 1)
    assert after_mark(plan, text, at) == at


def test_opening_spans_hand_the_mark_forward_and_lose_nothing() -> None:
    """The spans a proposal produces tile the document exactly: no character
    is dropped at a cut and none is counted twice."""
    plan = _plan(ANNOUNCED, "cuts-announced")
    text = announced_doc(60)
    cuts = [text.index("#", 1), text.rindex("#")]
    spans, leads = cut_spans(plan, text, cuts)
    assert not any(leads)
    assert "".join(text[lo:hi] for lo, hi in spans) == text


# ── the floor, in both directions ─────────────────────────────────────────


def test_every_chosen_cut_clears_the_floor_on_both_sides() -> None:
    """The 2 KiB floor is absolute, and a proposal is not exempt from it."""
    plan = _plan(ANNOUNCED, "cuts-announced")
    text = announced_doc(300)
    assert len(text) > 4 * MIN_CHUNK
    cuts = cut_offsets(plan, text, 8, Level(plan.scanner, text)).offsets
    assert cuts
    bounds = [0, *cuts, len(text)]
    assert all(hi - lo >= MIN_CHUNK for lo, hi in zip(bounds, bounds[1:])), (
        "a cut left a piece under the floor"
    )


@pytest.mark.parametrize(("cpus", "pieces"), [(16, 15), (32, 16)])
def test_a_plan_cut_spares_a_cpu_when_its_workers_claim_them_all(
    cpus: int, pieces: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sixteen workers on sixteen CPUs cut fifteen pieces, as the region route
    does; on a host with CPUs to spare they cut sixteen."""
    monkeypatch.setattr(policy_module, "available_workers", lambda: cpus)
    plan = _plan(LINES, "cuts-lines")
    text = _lines(40 * MIN_CHUNK)
    assert (
        len(cut_offsets(plan, text, 16, Level(plan.scanner, text)).offsets)
        == pieces - 1
    )


def _candidates(plan: SplitPlan, text: str, cores: int = 8) -> list[int]:
    """Every candidate the cut search would read, listed by walking it
    nearest-first from offset 0 — which is ascending."""
    return list(
        cut_offsets(plan, text, cores, Level(plan.scanner, text)).marks(
            0, 0, len(text) + 1
        )
    )


def test_a_terminated_cut_may_stand_just_before_the_floor() -> None:
    """A terminated piece KEEPS its mark, so a mark one character short of the
    floor still leaves the piece before it a full ``MIN_PIECE`` — and, being
    the nearest to the target, it is the cut taken over a farther one."""
    plan = _plan(LINES, "cuts-lines")
    assert plan.terminated
    text = "a" * 1023 + "\n" + "b" * 2176 + "\n" + "c" * 999 + "\n" + "d" * 2098 + "\n"
    marks = [at for at, char in enumerate(text) if char == "\n"]
    assert (len(text), marks) == (6300, [1023, 3200, 4200, 6299])
    # The first target is a third of the way in: 1023 stands nearer it than 3200.
    assert abs(2100 - 1023) < abs(3200 - 2100)
    assert cut_offsets(plan, text, 3, Level(plan.scanner, text)).offsets == [1023, 4200]


def test_a_proposal_is_never_cut_at_offset_zero() -> None:
    """A cut at the document's first character leaves an empty first piece,
    which is not a document.

    The scan reports a mark there — a unit does begin there — and the
    candidates drop it, so neither a choice nor a re-selection can reach it."""
    plan = _plan(ANNOUNCED, "cuts-announced")
    text = announced_doc(300)
    assert text[0] == "#", "the fixture must open ON a proposal character"
    assert 0 in plan.scanner.level(text, 0, len(text), 0)
    assert 0 not in _candidates(plan, text)
    assert 0 not in cut_offsets(plan, text, 8, Level(plan.scanner, text)).offsets


def test_every_candidate_stands_on_a_mark_of_the_plan() -> None:
    """Candidate generation is grammar-derived, never a byte offset: each one
    is an occurrence of a spelling the plan named."""
    plan = _plan(ANNOUNCED, "cuts-announced")
    text = announced_doc(300)
    marks = _candidates(plan, text)
    assert marks
    assert all(text[at] in plan.mark for at in marks)


# ── searching near the targets, and why where it starts changes nothing ───


def test_where_a_search_starts_changes_no_candidate() -> None:
    """Candidates are found where they are asked for, so the order a search
    reads them in is a scheduling choice and never an answer: walked out from
    any target, they are the plan's depth-0 marks of the whole document."""
    plan = _plan(LINES, "cuts-lines")
    text = _lines(6 * MIN_CHUNK)
    whole = [
        at for at in plan.scanner.level(text, 0, len(text), 0) if text[at] in plan.mark
    ]
    assert len(whole) > 100, "the fixture must hold many marks, or nothing is compared"
    # The last line's terminator would leave an empty last piece: no candidate.
    assert after_mark(plan, text, whole[-1]) == len(text)
    whole.pop()
    marks = cut_offsets(plan, text, 8, Level(plan.scanner, text)).marks
    for want in (0, len(text) / 3, len(text) - 1, len(text) + 50):
        found = list(marks(want, 0, len(text) + 1))
        assert sorted(found) == whole, want
        gaps = [abs(at - want) for at in found]
        assert gaps == sorted(gaps), "a search must read its candidates nearest first"


def test_choosing_cuts_reads_only_the_text_near_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fifteen cuts in a large document read the stretches around their
    targets, not every mark in it: the depth at a stretch's start is counted,
    and only the stretch is walked."""
    monkeypatch.setattr(policy_module, "available_workers", lambda: 16)
    plan = _plan(LINES, "cuts-lines")
    text = _lines(64 * MIN_CHUNK)
    read: list[int] = []
    real = Scanner.level

    def counted(self: Scanner, doc: str, lo: int, hi: int, base: int) -> list[int]:
        read.append(hi - lo)
        return real(self, doc, lo, hi, base)

    monkeypatch.setattr(Scanner, "level", counted)
    cuts = cut_offsets(plan, text, 16, Level(plan.scanner, text)).offsets
    assert len(cuts) == 14
    assert 0 < sum(read) < len(text) // 8, f"read {sum(read)} of {len(text)}"


PAIRED = 'root ::= item ("," item)*\nitem ::= "(" word ")"\nword ::= [a-z]+\n'
"""Commas between real bracket pairs: depth decides which ones stand at 0."""


def test_a_dense_plan_never_sweeps_the_whole_level() -> None:
    """Candidates every few characters are found near the targets; the whole
    level is never listed."""
    plan = _plan(LINES, "cuts-lines")
    text = _lines(32 * MIN_CHUNK)
    level = Level(plan.scanner, text)
    assert cut_offsets(plan, text, 16, level).offsets
    assert level.listed is None


def test_a_short_document_empty_at_its_start_is_still_read_to_its_end() -> None:
    """Nothing in the first stretch says only that the plan is sparse there: a
    document too short to be swept in windows is still read whole before its
    one cut is declined — and here it has one."""
    plan = _plan(LINES, "cuts-lines")
    text = "a" * 2047 + "\n" + "b" * 2047 + "\n"
    assert len(text) == 2 * MIN_CHUNK and "\n" not in text[:1024]
    assert cut_offsets(plan, text, 2, Level(plan.scanner, text)).offsets == [2047]


def _listed_lines() -> tuple[SplitPlan, str, Level]:
    """LINES over a level already swept whole — the listed path every
    envelope, opaque walk and sparse plan reads."""
    plan = _plan(LINES, "cuts-lines")
    text = _lines(6 * MIN_CHUNK)
    level = Level(plan.scanner, text)
    level.whole()
    return plan, text, level


def test_a_listed_plan_still_drops_its_skip_only_last_mark() -> None:
    """Read from a list, a terminated plan's last mark — nothing but skip after
    it — is still no candidate, and is not counted as one."""
    plan, text, level = _listed_lines()
    marks = [at for at in level.listed or () if text[at] in plan.mark]
    assert after_mark(plan, text, marks[-1]) == len(text)
    reader = PlanMarks(plan, level, None)
    assert reader.found(10**6) == len(marks) - 1
    assert list(reader.around(0, 0, len(text) + 1)) == marks[:-1]


def test_a_listed_target_midway_between_two_candidates_takes_the_earlier() -> None:
    """Read from a list, a tie still goes to the earlier candidate."""
    plan, text, level = _listed_lines()
    marks = cut_offsets(plan, text, 8, level).marks
    whole = list(marks(0, 0, len(text) + 1))
    earlier, later = whole[100], whole[101]
    want = (earlier + later) / 2
    assert want - earlier == later - want
    assert list(marks(want, 0, len(text) + 1))[:2] == [earlier, later]


def _envelope_plan() -> SplitPlan:
    """ENVELOPE_SOURCE's envelope plan."""
    plan = next(
        (one for one in _safe(ENVELOPE_SOURCE, "cuts-envelope") if one.envelope),
        None,
    )
    assert plan is not None, "the fixture must certify an envelope plan"
    return plan


@pytest.mark.parametrize(
    ("opening", "held", "kept"),
    [
        (True, [0, 100, 200], [100, 200]),  # an opening cut at 0: no piece before it
        (True, [5, 100, 200], [5, 100, 200]),  # a first cut past 0 is a real one
        (False, [0, 100, 200], [0, 100, 200]),  # a closing mark at 0 ends a piece
    ],
)
def test_an_envelopes_cuts_are_its_candidates_bar_an_opening_zero(
    opening: bool, held: list[int], kept: list[int]
) -> None:
    """An envelope's own cuts need no plan filter: every one is a candidate,
    counted, except the empty first piece an opening cut at 0 would leave."""
    plan = _envelope_plan()._replace(opening=opening)
    text = "a = b\n" * 2000
    reader = PlanMarks(plan, Level(plan.scanner, text), held)
    assert reader.found(10**6) == len(kept)
    assert list(reader.around(0, 0, len(text) + 1)) == kept


def test_a_sparse_plan_is_answered_from_the_whole_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plan with no candidate near the start does not search the document out
    stretch by stretch: past a first stretch with nothing in it, the whole level
    is listed once, for every plan after it, and it is the level a single walk
    reads."""
    plan = _plan(PAIRED, "cuts-paired")
    nested = "(" + "x" * 3000 + ")"
    text = ",".join([nested] * 6 + ["(ab)"] * 400)
    honest = plan.scanner.level(text, 0, len(text), 0)
    read: list[int] = []
    real = Scanner.level

    def counted(self: Scanner, doc: str, lo: int, hi: int, base: int) -> list[int]:
        read.append(hi - lo)
        return real(self, doc, lo, hi, base)

    monkeypatch.setattr(Scanner, "level", counted)
    with WorkPool(4) as pool:
        level = Level(plan.scanner, text, pool)
        chosen = cut_offsets(plan, text, 4, level)
    assert level.listed == honest
    assert sum(read) - len(text) < 2 * 1024, "the search read on past a sparse start"
    assert chosen.offsets
    assert set(chosen.offsets) <= set(honest)


# ── selecting this plan's own marks out of the grammar's ──────────────────


def test_a_one_character_mark_set_selects_exactly_what_widths_would() -> None:
    """The membership test and the width match must agree, mark for mark.

    A one-character spelling cannot overlap itself, so every width is 1 and the
    run thinning is the identity — the two paths are one answer, and this is
    the check that they stay one.
    """
    plan = _plan(LINES, "cuts-lines")
    text = _lines(2 * MIN_CHUNK)
    matched_marks = [
        at
        for at in plan.scanner.level(text, 0, len(text), 0)
        if matched(text, at, spellings(plan.mark))
    ]
    assert after_mark(plan, text, matched_marks[-1]) == len(text)
    assert _candidates(plan, text, 4) == matched_marks[:-1]


PARAS = 'root ::= para ("\\n\\n" para)*\npara ::= line ("\\n" line)*\nline ::= [a-z]+\n'
"""Paragraphs separated by a spelling that is its own border."""


def _paras_plan(trailing: bool) -> SplitPlan:
    """PARAS's two-newline plan, with the overlap end the test asks for."""
    plan = next(
        one for one in _safe(PARAS, "cuts-paras") if one.mark == frozenset({"\n\n"})
    )
    return plan._replace(trailing=trailing)


def _padded(core: str) -> str:
    """``core`` placed mid-document, with enough text either side to be cut."""
    side = "\n".join(["abcdefg"] * 600)
    return side + "\n\n" + core + "\n\n" + side


@pytest.mark.parametrize(("trailing", "kept"), [(False, [1, 8]), (True, [3, 10])])
def test_overlapping_occurrences_thin_to_one_boundary_per_run(
    trailing: bool, kept: list[int]
) -> None:
    """``"\\n\\n\\n\\n"`` reads three occurrences and the grammar has ONE
    boundary in it. Which end it stands at is the plan's static answer; either
    way no two boundaries are adjacent and no piece can be empty."""
    core = "a\n\n\n\nbcd\n\n\n\ne"
    text = _padded(core)
    at = text.index(core)
    found = [
        one - at
        for one in _candidates(_paras_plan(trailing), text)
        if at <= one < at + len(core)
    ]
    assert found == kept


@pytest.mark.parametrize("trailing", [False, True])
def test_a_run_split_by_where_a_search_starts_still_thins_to_one(
    trailing: bool,
) -> None:
    """A search that starts INSIDE an overlapping run reads the run's
    neighbours past its first stretch's edge, so the run still keeps one
    boundary — the one a search from the document's start keeps."""
    plan = _paras_plan(trailing)
    core = "a\n\n\n\n\nb"
    text = _padded(core)
    run = text.index(core) + 1
    end = len(text) + 1
    whole = _candidates(plan, text)
    kept = [at for at in whole if run <= at < run + 5]
    assert kept == ([run + 3] if trailing else [run])
    marks = cut_offsets(plan, text, 8, Level(plan.scanner, text)).marks
    for want in range(run - 1, run + 6):
        assert sorted(marks(want, 0, end)) == whole, want


def test_a_target_midway_between_two_candidates_takes_the_earlier() -> None:
    """Nearest first, and the earlier on a tie — the order every divider's
    choice is read in."""
    plan = _plan(LINES, "cuts-lines")
    text = _lines(6 * MIN_CHUNK)
    marks = cut_offsets(plan, text, 8, Level(plan.scanner, text)).marks
    whole = _candidates(plan, text)
    earlier, later = whole[100], whole[101]
    want = (earlier + later) / 2
    assert want - earlier == later - want
    assert list(marks(want, 0, len(text) + 1))[:2] == [earlier, later]


ARROWS = 'root ::= item ("->" item)*\nitem ::= [a-z]+\n'
"""A two-character separator that is NOT its own border."""


@pytest.mark.parametrize("trailing", [False, True])
def test_occurrences_exactly_width_apart_are_both_kept(trailing: bool) -> None:
    """Two occurrences with nothing between them are NOT the same run — only
    occurrences closer than the mark's own width overlap."""
    plan = _plan(ARROWS, "cuts-arrows")._replace(trailing=trailing)
    side = "->".join(["abcdefg"] * 600)
    core = "x->->y"
    text = side + "->" + core + "->" + side
    at = text.index(core)
    found = [one - at for one in _candidates(plan, text) if at <= one < at + len(core)]
    assert found == [1, 3]


def test_the_widest_spelling_at_an_offset_is_the_one_that_matches() -> None:
    """Longest first, or a cut lands mid-spelling — and the ordering is the
    SET's, settled once rather than at every occurrence."""
    ordered = spellings(frozenset({"\n", "\n\n", ";"}))

    assert ordered[0] == "\n\n"
    assert matched("a\n\nb", 1, ordered) == "\n\n"
    assert matched("a\nb", 1, ordered) == "\n"
    assert matched("ab", 1, ordered) == ""


def test_a_plan_carries_its_marks_in_match_order_already_settled() -> None:
    """Order is a property of the mark SET, so the plan is what holds it.

    Deriving it where a mark is READ sorted once per candidate examined and
    once per cut accepted, on the same immutable set, every document.
    """
    plan = _plan(LINES, "cuts-lines")

    assert plan.ordered == spellings(plan.mark)
    assert plan.ordered == ("\n",)


def test_the_ordering_a_plan_carries_is_the_one_matching_uses() -> None:
    """A wider spelling at an offset still wins, through the plan's tuple."""
    plan = _plan(LINES, "cuts-lines")
    wide = plan._replace(
        mark=frozenset({"\n", "\n\n"}), ordered=spellings(frozenset({"\n", "\n\n"}))
    )
    text = "a\n\nb\n"

    assert after_mark(wide, text, 1) == 3
    assert after_mark(plan, text, 1) == 2


# ── a level under a scanner with no pair counts nothing ───────────────────


def test_a_scanner_with_no_pair_reads_a_flat_level_and_a_paired_one_counts() -> None:
    """Chosen once per document, by the scanner's own roles: a flat level for a
    scanner that opens and closes nothing, the counting level otherwise."""
    flat = _plan(LINES, "cuts-lines").scanner
    paired = _plan(PAIRED, "cuts-paired").scanner
    assert isinstance(level_of(flat, "x\n"), FlatLevel)
    assert not isinstance(level_of(paired, "(x)"), FlatLevel)


def test_a_flat_level_chooses_the_counting_levels_cuts_without_counting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every mark of a flat scanner stands at depth 0, so the flat level's
    candidates and cuts are the counting level's, with no count asked."""
    plan = _plan(LINES, "cuts-lines")
    text = _lines(32 * MIN_CHUNK)
    counted = cut_offsets(plan, text, 16, Level(plan.scanner, text))
    expected = (counted.offsets, list(counted.marks(0, 0, len(text) + 1)))

    def refused(*_args: object) -> int:
        raise AssertionError("a flat level asked for a count")

    monkeypatch.setattr(Scanner, "drift", refused)
    flat = cut_offsets(plan, text, 16, level_of(plan.scanner, text))
    assert (flat.offsets, list(flat.marks(0, 0, len(text) + 1))) == expected
    assert expected[0]


def test_a_paired_level_still_counts_its_depth() -> None:
    """Inside a bracket the counting level reads depth 1 — what a flat level
    could never say, and why a paired scanner never gets one."""
    plan = _plan(PAIRED, "cuts-paired")
    text = "(ab)," * 10 + "(" + ",".join(["(x)"] * 30) + ")"
    assert level_of(plan.scanner, text).depth(text.index("(x)")) == 1
