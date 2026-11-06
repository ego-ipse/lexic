"""Tests for lexic.parsing.earley.kernel.forest.support.ambiguity — does a span
mean more than one thing?

The split-vs-arm distinction is exercised at scale on real json input in
``tests/unit/lexic/parsing/earley/kernel/forest/test_ambiguity.py`` (the
sibling module named identically at the parent directory — a decided split is
not an ambiguity); this file targets ``same_value``'s equality semantics and
``ambiguity_points`` and the settlement path (``different_meaning`` into
``chosen_meaning``) directly, on small hand-built grammars.
"""

from __future__ import annotations

import math

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrNone, IrStr
from lexic.parsing.earley.kernel.forest.fasttree import FastTree, FirstTree, first_tree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support import ambiguity
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    DEFAULT_CONFIG,
    MeaningBuilder,
    MeaningPair,
    MeaningRun,
    ParseConfig,
    ambiguity_points,
    arm_choices,
    chosen_meaning,
    different_meaning,
    dirty_cone,
    parent_edges,
    remembered,
    same_value,
)
from lexic.parsing.earley.kernel.tables.decider import LEFTMOST_LONGEST
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice
from tests.parity_helpers import DECLINED, REFUSED, answers
from tests.unit.lexic.parsing.earley.kernel.forest.forest_helpers import (
    kernel_and_handle,
)

AMBIGUOUS_EXPR = 'e ::= e "+" e | "n"\n'
"""Every grouping is one production carved at different boundaries: a split,
which the decider settles."""

SAME_BOUNDARY = 'e ::= p | q\np ::= "n"\nq ::= "n"\n'
"""Two arms over the same text, at the same boundaries: an arm choice."""

THREE_ARMS = 'root ::= e\ne ::= p | q | r\np ::= "n"\nq ::= "n"\nr ::= "n"\n'
"""Three arms of ``e`` over one text at one predecessor: two alternates to the
base, inside the root rather than at it, so they are flips, not siblings."""


def test_same_value_is_type_aware_an_ir_leaf_and_its_bare_text_differ():
    """Bare ``==`` would call these equal (the IR wraps ``str``); type
    awareness is exactly what fixes that false positive."""
    assert not same_value(IrStr("a"), "a")


def test_same_value_treats_nan_as_equal_to_itself():
    """Two derivations always build two DISTINCT NaN objects — bare ``==``
    would call them different and wrongly flag an ambiguity."""
    assert same_value(math.nan, math.nan)


def test_same_value_compares_tuples_and_dicts_structurally():
    """Structural equality over tuples and dicts, mismatch on either shape or
    a differing value."""
    assert same_value((1, 2), (1, 2))
    assert not same_value((1, 2), (1, 3))
    assert same_value({"a": 1}, {"a": 1})
    assert not same_value({"a": 1}, {"a": 2})


def test_same_value_treats_a_type_with_no_eq_as_indistinguishable():
    """Declining to define equality is "cannot tell", which reads as no
    observable difference rather than a refusal."""
    assert same_value(object(), object())


def test_ambiguity_points_is_empty_for_an_unambiguous_grammar():
    """No key in the link table packs more than one family."""
    kernel, handle = kernel_and_handle(
        "axb", 'root ::= "a" mid "b"\nmid ::= "x" | "y"\n', "ambiguity-none"
    )
    assert ambiguity_points(kernel, handle) == []


def test_ambiguity_points_finds_a_multi_family_key_in_an_ambiguous_grammar():
    """A genuinely ambiguous expression grammar has at least one such key."""
    kernel, handle = kernel_and_handle("n+n+n", AMBIGUOUS_EXPR, "ambiguity-found")
    assert ambiguity_points(kernel, handle)


DROPPED_CARVING = (
    'root ::= x y\nx ::= "a"+\ny ::= w "!"\nw ::= w1 | w2\n'
    'w1 ::= "a"* "b"\nw2 ::= "ab"\n'
)
"""``aab!`` splits ``root`` as ``aa`` + ``b!``, the carving the decider keeps,
or ``a`` + ``ab!``, where ``w`` over ``ab`` is ``w1`` or ``w2``: an arm choice
only inside the dropped carving."""

KEPT_CARVING = (
    'root ::= x y\nx ::= "a"+\ny ::= w "!"\nw ::= w1 | w2\n'
    'w1 ::= "a"* "b"\nw2 ::= "b"\n'
)
"""As :data:`DROPPED_CARVING`, but ``w`` over the kept carving's ``b`` is
``w1`` or ``w2``: an arm choice inside the carving the decider keeps."""


def test_the_walk_enters_only_the_carving_the_decider_keeps() -> None:
    """Every family reaches ``w``'s arm choice under the dropped carving; the
    decided walk, entering the split only through its kept family, reaches
    no arm choice at all."""
    kernel, handle = kernel_and_handle("aab!", DROPPED_CARVING, "ambiguity-dropped")
    links = kernel.family_reader()
    everywhere = [
        key
        for key in ambiguity_points(kernel, handle)
        if is_arm_choice(
            links[key], kernel.tables.packing.bits, kernel.tables.code_choice
        )
    ]
    assert everywhere, "no arm choice under the dropped carving — nothing tested"
    assert arm_choices(kernel, handle, LEFTMOST_LONGEST) == []


def test_an_arm_choice_inside_a_dropped_carving_is_not_refused() -> None:
    """The dropped carving is a derivation this engine never produces, so the
    two meanings of ``w`` there are no ambiguity: the parse builds the kept
    carving's model, and the predictive engine, where it answers, the same."""
    for text, x in (("aab!", "aa"), ("aaab!", "aaa"), ("ab!", "a")):
        predictive, gated = answers(DROPPED_CARVING, "ambiguity-dropped", text)
        assert gated == f"Root(X('{x}'), Y(W1('b')))"
        assert predictive in (gated, DECLINED)
    assert answers(DROPPED_CARVING, "ambiguity-dropped", "ab!")[0] != DECLINED


def test_an_arm_choice_inside_the_kept_carving_is_still_refused() -> None:
    """The walk enters the kept carving, so its arm choice is found and its
    two meanings refuse the document."""
    kernel, handle = kernel_and_handle("aab!", KEPT_CARVING, "ambiguity-kept")
    assert arm_choices(kernel, handle, LEFTMOST_LONGEST)
    predictive, gated = answers(KEPT_CARVING, "ambiguity-kept", "aab!")
    assert gated == REFUSED
    assert predictive in (REFUSED, DECLINED)


STEERED_CYCLE = (
    'a ::= b c\nb ::= a | "x"\nc ::= w?\nw ::= w1 | w2\nw1 ::= "y"\nw2 ::= "y"\n'
)
"""``xy`` carves ``a`` as ``b[0,2] c[2,2]``, where ``b[0,2]`` is only the cycle
``b → a``, or as ``b[0,1] c[1,2]``. The decider keeps the first, the build
steers off it to the second, and only the second holds ``w``'s arm choice."""


def test_an_arm_choice_under_a_steered_chain_is_refused() -> None:
    """The walk enters the chains the build steered to, so the arm choice in
    the derivation the build produces is found and its two meanings refuse,
    on both engines."""
    predictive, gated = answers(STEERED_CYCLE, "ambiguity-steered", "xy")
    assert gated == REFUSED
    assert predictive in (REFUSED, DECLINED)


def _builder(build) -> MeaningBuilder:
    """One interpretation, whose replay ignores the seeded node values."""
    return MeaningBuilder(build, lambda tree, _values: build(tree))


def _settled(text: str, build, name: str, grammar: str = SAME_BOUNDARY) -> MeaningPair:
    """What the span means, under one interpretation of its derivations."""
    kernel, handle = kernel_and_handle(text, grammar, name)
    first = first_tree(kernel, (handle,), LEFTMOST_LONGEST)
    assert first is not None
    return different_meaning(kernel, first, _builder(build), LEFTMOST_LONGEST)


def test_no_witness_when_every_grouping_builds_the_same_value():
    """Every grouping of ``e ::= e "+" e | "n"`` spans the same TEXT length
    regardless of how it associates — a build function insensitive to
    grouping finds no other meaning, so nothing is refused."""

    def build_span_length(tree: ParseTree) -> int:
        """A build function insensitive to how the span is grouped."""
        del tree
        return len("n+n+n")

    pair = _settled("n+n+n", build_span_length, "meaning-none", AMBIGUOUS_EXPR)

    assert pair.witness is None
    assert chosen_meaning(pair, _builder(build_span_length), DEFAULT_CONFIG) == 5


def test_a_grouping_is_decided_not_offered_as_a_second_meaning():
    """Left- and right-associative grouping differ in where ``+`` splits the
    span, so the decider keeps one — the first slot longest — and the other is
    a carving it rejected, not a second meaning, even to a build that sees
    shape."""
    pair = _settled("n+n+n", repr, "meaning-grouping", AMBIGUOUS_EXPR)

    assert pair.witness is None
    assert chosen_meaning(pair, _builder(repr), DEFAULT_CONFIG) == pair.first.value


def test_a_differing_derivation_is_found_when_the_build_sees_shape():
    """A build function sensitive to the tree's own shape (its ``repr``) DOES
    see two arms over the same boundaries as a different meaning."""
    pair = _settled("n", repr, "meaning-found")

    assert pair.witness is not None
    assert pair.witness.value != pair.first.value
    assert repr(pair.witness.tree) != repr(pair.first.tree)


def test_every_other_arm_is_asked_not_only_the_first(monkeypatch):
    """An alternate that does not build says nothing about the next one: with
    the first alternate's replay failing, the third arm still differs from
    the base, so the span still means two things."""
    real = ambiguity.replayed
    calls: list[int] = []

    def first_fails(run, point, family, memo, parents):
        calls.append(family)
        return None if len(calls) == 1 else real(run, point, family, memo, parents)

    monkeypatch.setattr(ambiguity, "replayed", first_fails)
    pair = _settled("n", repr, "meaning-three-arms", THREE_ARMS)

    assert len(calls) == 2, calls
    assert pair.witness is not None
    assert pair.witness.value != pair.first.value


def test_two_meanings_refuse_without_a_resolver():
    """The default answer to a span that means two things is a refusal."""
    pair = _settled("n", repr, "meaning-refused")

    with pytest.raises(UnsupportedConstructError, match="ambiguous input"):
        chosen_meaning(pair, _builder(repr), DEFAULT_CONFIG)


def test_a_resolver_settles_which_meaning_is_kept():
    """The opt-out is the caller's deterministic choice between the two."""
    pair = _settled("n", repr, "meaning-resolved")
    assert pair.witness is not None

    keep_first = ParseConfig(resolve=lambda one, _other: one)
    keep_other = ParseConfig(resolve=lambda _one, other: other)
    first = chosen_meaning(pair, _builder(repr), keep_first)
    other = chosen_meaning(pair, _builder(repr), keep_other)

    assert first == pair.first.value
    assert other == pair.witness.value
    assert first != other


def test_the_default_config_refuses_and_keeps_the_leftmost_longest_carving():
    """No resolver means refusal, spelled ``IrNone``; the decider defaults to
    the one configuration, and a config naming only a resolver keeps it."""
    assert DEFAULT_CONFIG.resolve is IrNone
    assert DEFAULT_CONFIG.decide is LEFTMOST_LONGEST
    assert ParseConfig(resolve=lambda one, _other: one).decide is LEFTMOST_LONGEST
    assert DEFAULT_CONFIG == ParseConfig()


def _refuse_builds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any fast build during the test an error."""

    def no_build(_self: FastTree, _handle: int) -> ParseTree:
        raise AssertionError("remembered built a derivation")

    monkeypatch.setattr(FastTree, "build", no_build)


def test_remembered_folds_the_first_build_and_builds_nothing(monkeypatch):
    """The baseline is the derivation the caller built, its memo that build's:
    remembering it costs no second build."""
    kernel, handle = kernel_and_handle("n", SAME_BOUNDARY, "remembered-memo")
    first = first_tree(kernel, (handle,), LEFTMOST_LONGEST)
    assert first is not None
    run = MeaningRun(kernel, handle, _builder(repr), LEFTMOST_LONGEST)
    _refuse_builds(monkeypatch)
    base, memo = remembered(run, first)
    assert base.tree is first.tree
    assert base.value == repr(first.tree)
    assert memo.nodes == first.memo
    assert memo.nodes is not first.memo


def test_remembered_folds_a_streamed_tree_fresh_with_an_empty_memo(monkeypatch):
    """A derivation read off the chart keeps no handles, so there is nothing to
    seed from: it folds fresh and the memo stays empty."""
    kernel, handle = kernel_and_handle("n", SAME_BOUNDARY, "remembered-stream")
    built = first_tree(kernel, (handle,), LEFTMOST_LONGEST)
    assert built is not None
    streamed = FirstTree(handle, built.tree, {})
    run = MeaningRun(kernel, handle, _builder(repr), LEFTMOST_LONGEST)
    _refuse_builds(monkeypatch)
    base, memo = remembered(run, streamed)
    assert (base.tree, base.value) == (built.tree, repr(built.tree))
    assert (memo.nodes, memo.values) == ({}, {})


def test_dirty_cone_is_the_flipped_point_and_every_handle_above_it():
    """Read backwards over the parent index: the point, its parents, theirs."""
    parents = {3: [2], 2: [1], 4: [1]}
    assert dirty_cone(parents, 1, 3) == frozenset({3, 2, 1})
    assert dirty_cone(parents, 1, 4) == frozenset({4, 1})


def test_dirty_cone_is_empty_for_a_point_outside_the_root():
    """Nothing about this root changes when a point it never reaches flips."""
    assert dirty_cone({3: [2]}, 1, 9) == frozenset()


def test_parent_edges_put_every_ambiguity_point_under_the_root():
    """Each point of an ambiguous span is reached from its root, so its cone
    climbs back to it."""
    kernel, handle = kernel_and_handle("n+n+n", AMBIGUOUS_EXPR, "parents-expr")
    parents = parent_edges(kernel, handle)
    points = ambiguity_points(kernel, handle)
    assert points
    for point in points:
        assert handle in dirty_cone(parents, handle, point)


def test_a_span_walks_its_parent_index_once_however_many_points_it_flips(
    monkeypatch,
):
    """Every flip of one span reads its cone off one walk of the link table —
    a walk per flip was the cost the shared index removes."""
    walks: list[int] = []
    real = ambiguity.parent_edges

    def counted(kernel, root):
        walks.append(root)
        return real(kernel, root)

    flips: list[int] = []
    replay = ambiguity.replayed

    def counted_replay(run, point, family, memo, parents):
        flips.append(point)
        return replay(run, point, family, memo, parents)

    monkeypatch.setattr(ambiguity, "parent_edges", counted)
    monkeypatch.setattr(ambiguity, "replayed", counted_replay)
    _settled("n", lambda tree: "same", "parents-once", THREE_ARMS)
    assert len(flips) == 2
    assert len(walks) == 1
