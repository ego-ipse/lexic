"""What the folded source will and will not locate, and why each refusal fires.

The source's whole value is that it DECLINES correctly. A wrong plan here does
not raise — it cuts a spine at an offset that was never a separator, and the
pieces still parse, so the only thing standing between a wrong model and the
caller is the boundary proof. Every case below therefore names the reason it
expects, and no case is satisfied by ``None`` alone: a plan that declined for
the wrong reason would pass a bare absence check while proving nothing.

The refusal ladder is ordered by what it kills. ``"+a"`` is the sharp one — its
FIRST character is excluded and its second is not — so a proof that asked only
the leading character would serve a mark whose occurrences are not aligned.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.parallel.discovery.regions import nearest_mark
from lexic.parsing.parallel.plan.folded import (
    FoldedPlan,
    _chosen_marks,
    _marks_in,
    divide,
    folded_plan,
    locate,
    mark_at,
)
from lexic.parsing.parallel.stitch.safety import owner_excludes
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.leftrec.shape import foldable

SERVED = (
    "root ::= expr nl\n"
    "expr ::= expr addop term | term\n"
    "term ::= [a-z] [a-z0-9]*\n"
    'addop ::= " + " | " - "\n'
    'nl ::= "\\n"\n'
)
"""The shape the source exists for: a spine under a REQUIRED tail.

The tail is why a plain separated plan cannot reach it — `_wrapper_chain`
follows only tails that can vanish — and holding it out is the source's job.
"""

BARE = 'root ::= expr\nexpr ::= expr op term | term\nterm ::= [a-z]+\nop ::= "+"\n'
"""The same spine with no tail at all — the shell is empty both sides."""


def compiled(source: str, key: str):
    """The artefact, cached per case so each grammar compiles once."""
    return compile_text(source, cache_key=f"folded-unit-{key}")


def plan_for(source: str, key: str) -> FoldedPlan | None:
    """The folded plan the source derives for one grammar."""
    return folded_plan(compiled(source, key).codegen_grammar)


def takes_the_fold(source: str, key: str) -> bool:
    """Whether the FOLD itself takes any rule — the pre-test every case owes.

    A grammar the fold refuses declines here for a reason that has nothing to
    do with the boundary proof, so a refusal case that quietly stopped being
    left-recursive would assert the wrong thing while still passing.
    """
    grammar = compiled(source, key).codegen_grammar
    rules = {str(rule.name): rule for rule in grammar.rules}
    nullable = GrammarAnalysis(grammar).item_nullable
    return any(
        foldable(name, rule, rules, nullable) is not None
        for name, rule in rules.items()
    )


# ── the served shape ──────────────────────────────────────────────────────


def test_the_served_shape_yields_a_plan() -> None:
    """The plan names the rule, the step class's rule, and both marks."""
    plan = plan_for(SERVED, "served")
    assert plan is not None
    assert plan.rule == "expr"
    assert plan.step == "expr-arm1"
    assert plan.lead == "addop"
    assert plan.marks == (" + ", " - ")
    assert plan.owners == ("term",)


def test_the_required_tail_is_held_out_of_the_extent() -> None:
    """``before`` and ``after`` are the shell, and the chain reaches the spine."""
    plan = plan_for(SERVED, "served")
    assert plan is not None
    assert (plan.before, plan.after) == ("", "\n")
    assert [(step.rule, step.item) for step in plan.chain] == [("root", 0)]


def test_a_bare_start_rule_leaves_an_empty_shell() -> None:
    """With nothing either side the extent is the whole document."""
    plan = plan_for(BARE, "bare")
    assert plan is not None
    assert (plan.before, plan.after) == ("", "")


def test_the_extent_ends_past_the_last_mark_not_at_it() -> None:
    """The final term is INSIDE the extent — the sibling source's trap.

    ``_whole_region`` takes a terminated interior's end from
    ``rfind(plan.mark)``. On a separated spine that offset is the last
    OPERATOR, so an extent read that way stops before the final term and the
    stitch rebuilds a document one term short. This is the assertion that
    would fail if the two arithmetics were ever shared.
    """
    plan = plan_for(SERVED, "served")
    assert plan is not None
    text = "a + b + zzz\n"
    region = locate(text, plan)
    assert region is not None
    assert text[region.opener : region.closer] == "a + b + zzz"
    assert region.closer > text.rfind(" + ")


def test_every_mark_inside_the_extent_is_found_in_order() -> None:
    """Both spellings, at their own offsets, and none from the shell."""
    plan = plan_for(SERVED, "served")
    assert plan is not None
    text = "a + b - c + d\n"
    region = locate(text, plan)
    assert region is not None
    assert region.marks == (1, 5, 9)
    assert [mark_at(text, at, plan.marks) for at in region.marks] == [
        " + ",
        " - ",
        " + ",
    ]


def test_a_document_without_the_shell_declines() -> None:
    """The extent is certified, not assumed — a missing tail is a decline."""
    plan = plan_for(SERVED, "served")
    assert plan is not None
    assert locate("a + b", plan) is None


# ── the division ──────────────────────────────────────────────────────────


def test_the_division_consumes_its_marks() -> None:
    """Each piece wears the shell; the removed marks come back as leads."""
    plan = plan_for(SERVED, "served")
    assert plan is not None
    text = " + ".join("abcd" for _ in range(3000)) + "\n"
    region = locate(text, plan)
    assert region is not None
    pieces = divide(text, region, 4, plan)
    assert pieces is not None
    assert len(pieces.parts) == 4
    assert len(pieces.leads) == 3
    assert all(lead in (" + ", " - ") for lead in pieces.leads)
    assert all(part.endswith("\n") for part in pieces.parts)
    # The pieces and the marks they are separated by ARE the document again:
    # a cut that kept or dropped a character would show up here and nowhere
    # else until the models were compared.
    rejoined = pieces.parts[0][:-1]
    for lead, part in zip(pieces.leads, pieces.parts[1:], strict=True):
        rejoined += lead + part[:-1]
    assert rejoined + "\n" == text


def test_a_document_under_the_floor_declines_to_divide() -> None:
    """The 2 KiB per worker floor caps the division, as every source's does."""
    plan = plan_for(SERVED, "served")
    assert plan is not None
    text = "a + b + c\n"
    region = locate(text, plan)
    assert region is not None
    assert divide(text, region, 4, plan) is None


# ── the refusal ladder, each by its own reason ────────────────────────────

REFUSALS = {
    "later-character": (
        'root ::= expr\nexpr ::= expr op term | term\nterm ::= [a-z]+\nop ::= "+a"\n',
        "+a",
        "a",
    ),
    "first-character": (
        'root ::= expr\nexpr ::= expr op term | term\nterm ::= "ab"\nop ::= "aba"\n',
        "aba",
        "a",
    ),
    "no-excludable-core": (
        'root ::= expr\nexpr ::= expr op term | term\nterm ::= [a-z]+\nop ::= "and"\n',
        "and",
        "a",
    ),
}
"""Each refusing mark, and the character its owner can emit.

``later-character`` is the one that matters most: ``"+"`` IS excluded, so a
first-character-only proof would license it — and ``"a+ab"`` holds ``"+a"`` at
offset 1, which is not a separator.
"""


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_a_mark_the_owner_can_spell_is_refused(case: str) -> None:
    """The plan declines, and the named character is why."""
    source, mark, emitted = REFUSALS[case]
    assert takes_the_fold(source, case), "the case stopped being left-recursive"
    grammar = compiled(source, case).codegen_grammar
    assert emitted in mark
    assert not owner_excludes(grammar, "term", emitted), (
        f"{case}: the owner no longer emits {emitted!r}, so the refusal under "
        "test is not the one this case exists for"
    )
    assert folded_plan(grammar) is None


def test_the_first_character_of_the_sharp_case_is_excluded() -> None:
    """``"+a"`` is refused DESPITE its leading character being excludable.

    Without this the ``later-character`` case proves nothing a
    first-character proof would not also have caught.
    """
    grammar = compiled(
        REFUSALS["later-character"][0], "later-character"
    ).codegen_grammar
    assert owner_excludes(grammar, "term", "+")
    assert not owner_excludes(grammar, "term", "a")
    assert folded_plan(grammar) is None


def test_a_tail_the_spine_can_also_spell_is_refused() -> None:
    """An extent bounded by text the interior can emit is a guess, not a proof."""
    source = (
        "root ::= expr sep\n"
        "expr ::= expr op term | term\n"
        "term ::= [a-z;]+\n"
        'op ::= "+"\n'
        'sep ::= ";"\n'
    )
    assert takes_the_fold(source, "spelled-tail")
    assert folded_plan(compiled(source, "spelled-tail").codegen_grammar) is None


def test_a_grammar_with_no_left_recursion_has_no_folded_plan() -> None:
    """The separated formulation of the same language declines here.

    Named apart from the mark refusals because it is a different negative: the
    FOLD does not take the shape at all, so no boundary proof is ever asked.
    """
    source = (
        "root ::= expr\n"
        "expr ::= term step*\n"
        "step ::= op term\n"
        "term ::= [a-z]\n"
        'op ::= "+"\n'
    )
    assert not takes_the_fold(source, "not-recursive")
    assert folded_plan(compiled(source, "not-recursive").codegen_grammar) is None


def test_a_repetition_between_start_and_the_spine_declines() -> None:
    """A shell that is not fixed text cannot be re-worn, so the descent stops.

    ``root ::= line+`` is the dense-earley shape: the spine sits under a
    repetition, and a piece cannot wear ``line+``'s text because there is no
    one string it always derives.
    """
    source = (
        "root ::= line+\n"
        "line ::= expr nl\n"
        "expr ::= expr op term | term\n"
        "term ::= [a-z]\n"
        'op ::= "+"\n'
        'nl ::= "\\n"\n'
    )
    assert takes_the_fold(source, "under-a-repetition")
    assert folded_plan(compiled(source, "under-a-repetition").codegen_grammar) is None


def test_a_step_with_no_separator_rule_is_refused() -> None:
    """``A ::= A "a" | "a"`` folds, and still has nothing to cut on.

    A distinct negative from every mark refusal above, and the one the three
    engine-reach rows take. The fold TAKES this shape — so a test that only
    checked "no fold, no plan" would miss it — but the recursive arm's
    remainder is a bare literal, leaving no separator RULE: nothing to spell a
    mark with, and nothing to re-parse a removed one under.
    """
    source = 'root ::= expr\nexpr ::= expr "a" | "a"\n'
    assert takes_the_fold(source, "no-separator-rule")
    assert folded_plan(compiled(source, "no-separator-rule").codegen_grammar) is None


NEAREST = (10, 20, 30, 40)
"""Mark offsets for the cut selection, in document order as `locate` gives them."""


@pytest.mark.parametrize(
    ("want", "expected"),
    [
        (0.0, 10),  # before the first
        (10.0, 10),  # on a mark
        (14.0, 10),  # nearer the one below
        (15.0, 10),  # exactly between — the EARLIER, on every run
        (16.0, 20),  # nearer the one above
        (40.0, 40),  # on the last
        (99.0, 40),  # past the last
    ],
)
def test_the_cut_lands_on_the_nearest_mark(want: float, expected: int) -> None:
    """The bisect answers what a scan over every mark answered.

    Written as a table because the bisect replaced a linear ``min`` for cost,
    not for behaviour: the ends and the exact midpoint are where the two can
    disagree, and a midpoint that drifted would move a cut for reasons no
    other test would attribute.

    The subject is the sweep path's own ``nearest_mark``, which this module
    calls rather than reimplementing. It had no coverage anywhere before —
    two routes now cut with it, and the table is where its tie rule and its
    two ends are written down.
    """
    assert nearest_mark(NEAREST, want) == expected


@pytest.mark.parametrize("want", [-5.0, 0.0, 9.9, 25.0, 31.0, 200.0])
def test_the_bisect_agrees_with_the_scan_it_replaced(want: float) -> None:
    """A differential against the linear reading, on the same offsets."""
    scanned = min(NEAREST, key=lambda mark: (abs(mark - want), mark))
    assert nearest_mark(NEAREST, want) == scanned


# ── the document-order precondition the bisect rests on ───────────────────

TERM = "abcdefgh"
"""A fixed-width term, so an interleaved document's mark offsets are arithmetic."""


def interleaved(terms: int) -> tuple[str, tuple[int, ...]]:
    """``(document, the mark offsets)`` for alternating ``" + "`` / ``" - "``.

    The offsets are computed from the CONSTRUCTION — term ``k`` starts at
    ``k * (len(TERM) + 3)`` and the mark follows it — rather than by searching
    the text. An expectation derived by searching would be the same operation
    :func:`_marks_in` performs, so the two could be wrong together.
    """
    width = len(TERM) + 3
    parts = [TERM]
    for index in range(1, terms):
        parts.append(" + " if index % 2 else " - ")
        parts.append(TERM)
    return "".join(parts), tuple(width * k - 3 for k in range(1, terms))


def test_the_interleaved_marks_are_found_in_document_order() -> None:
    """Both spellings alternating, at the offsets the construction puts them.

    This is what exercises the MERGE. ``_marks_in`` runs one cursor per
    spelling and picks the earliest at each step, so a single-spelling
    document never reaches :func:`_earliest` at all — and every other case in
    this file is either one spelling or a handful of marks.

    **The arithmetic equality is the load-bearing assertion, not the order.**
    A merge that took the first spelling with a mark left — the obvious bug —
    returns 200 of these 399 marks and they are still in ASCENDING ORDER, so
    the sortedness check below passes on it. Only an expectation derived from
    the construction sees the 199 that went missing.
    """
    text, expected = interleaved(400)
    plan = plan_for(SERVED, "served")
    assert plan is not None
    found = _marks_in(text, 0, len(text), plan.marks)
    assert len(found) == 399
    assert found == expected
    assert [text[at : at + 3] for at in found[:4]] == [" + ", " - ", " + ", " - "]
    assert sorted(found) == list(found), "the merge returned marks out of order"


def test_the_bisect_cuts_where_the_linear_reading_cut() -> None:
    """The differential, on the document whose order the merge produces.

    The bisect is only correct because ``_marks_in`` emits in ascending order,
    and that precondition is a fact about the MERGE of two cursors. So the
    differential runs on interleaved marks rather than on a hand-written list:
    a merge that emitted one spelling's run before the other's would leave the
    list unsorted, and the bisect would then pick a mark the scan would not.
    """
    _text, marks = interleaved(400)
    lo, hi = marks[0], marks[-1] + 3
    for workers in (2, 3, 4, 8, 16):
        target = (hi - lo) / workers
        chosen = _chosen_marks(marks, lo, hi, target, workers)
        scanned = scanned_cuts(marks, lo, hi, target, workers)
        assert chosen == scanned, f"{workers} workers: {chosen} != {scanned}"
        assert len(chosen) == workers - 1, "the document must offer every cut"


def scanned_cuts(
    marks: tuple[int, ...], lo: int, hi: int, target: float, workers: int
) -> list[int]:
    """``_chosen_marks`` as it read before the bisect — a linear ``min``.

    The reference arm of the differential, kept flat rather than closed over
    the loop variable it compares against: the point is that it is a separate,
    obviously-correct reading, and a closure would make it share state with
    the thing it is checking.
    """
    found: list[int] = []
    for step in range(1, workers):
        want = lo + step * target
        at = min(marks, key=lambda mark, w=want: (abs(mark - w), mark))
        if at not in found and lo < at < hi:
            found.append(at)
    return found
