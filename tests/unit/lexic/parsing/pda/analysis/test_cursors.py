"""Tests for lexic.parsing.pda.analysis.cursors — the analysis context records
that ride the ``nc`` channel.

Inert data records with no behaviour of their own beyond ``Scope``'s three
delegating properties; this file constructs each and pins that delegation.
"""

from __future__ import annotations

from lexic.parsing.pda.analysis.cursors import (
    ConflictCtx,
    Cont,
    FeedCtx,
    FollowPass,
    Notes,
    Scope,
    Site,
)
from lexic.parsing.pda.core.charsets import CharSet

SOFT = CharSet.from_chars("a")
HARD = CharSet.from_chars("b")
STRUCTURAL = CharSet.from_chars("c")


def test_follow_pass_carries_its_four_constants():
    """The four constructor arguments ride through unchanged."""
    tgt: dict = {}
    pass_ = FollowPass(tgt, hard=True, loopback=False, nullable_first=True)
    assert pass_.tgt is tgt
    assert pass_.hard is True
    assert pass_.loopback is False
    assert pass_.nullable_first is True


def test_feed_ctx_carries_its_effective_set_rule_and_pass():
    """The three constructor arguments ride through unchanged."""
    pass_ = FollowPass({}, hard=False, loopback=True, nullable_first=False)
    feed = FeedCtx(SOFT, "root", pass_)
    assert feed.eff is SOFT
    assert feed.rule == "root"
    assert feed.pass_ is pass_


def test_notes_starts_empty_and_uncovered():
    """A fresh Notes has no hard/soft entries, no F1 flag, no coverage."""
    notes = Notes()
    assert not notes.hard
    assert not notes.soft
    assert notes.f1 is False
    assert notes.covered == 0


def test_site_carries_its_label_key_and_follow_set():
    """The three constructor arguments ride through unchanged."""
    site = Site("root", "root", SOFT)
    assert site.label == "root"
    assert site.at == "root"
    assert site.follow is SOFT


def test_cont_carries_its_three_views_distinctly():
    """The soft/hard/structural views are kept apart, not collapsed."""
    cont = Cont(SOFT, HARD, STRUCTURAL)
    assert cont.soft is SOFT
    assert cont.hard is HARD
    assert cont.structural is STRUCTURAL


def test_scope_properties_delegate_to_its_cont():
    """Scope's tail/hard_tail/structural_tail read straight off its Cont."""
    cont = Cont(SOFT, HARD, STRUCTURAL)
    scope = Scope("root", cont, body=True)
    assert scope.tail is SOFT
    assert scope.hard_tail is HARD
    assert scope.structural_tail is STRUCTURAL
    assert scope.rule == "root"
    assert scope.body is True


def test_conflict_ctx_carries_its_notes_cont_rule_and_index():
    """The four constructor arguments ride through unchanged."""
    notes = Notes()
    cont = Cont(SOFT, HARD, STRUCTURAL)
    ctx = ConflictCtx(notes, cont, "root", 2)
    assert ctx.notes is notes
    assert ctx.cont is cont
    assert ctx.rule == "root"
    assert ctx.index == 2
