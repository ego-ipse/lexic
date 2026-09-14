"""The split-greedy certifier: what it licences, and what it refuses.

Seven conditions, and a licence is only issued when every one holds. Each test
below takes a grammar that satisfies the others and breaks exactly ONE, so a
refusal names its reason: if a later change made some condition vacuous, the
grammar written for it would start passing and the test would say so.

The baseline `CERTIFIED` grammar is the shape the licence exists for — a unit
of nullable-bodied items closed by a tail of terminators — and every variant
below is it with a single thing changed.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.analysis.gates.greedy import greedy_loop_gate

CERTIFIED = 'doc ::= u+\nu ::= i+ tl\ni ::= [ab]* t\ntl ::= t\nt ::= ";"\n'
"""The class: `u ::= i+ tl`, item `i ::= [ab]* t`, tail one terminator."""


def _gate(source: str, unit: str = "u", key: str | None = None):
    """The licence the certifier issues for ``unit``'s loop, or ``None``."""
    compiled = compile_text(source, cache_key=key or f"greedy-{hash(source)}")
    analysis = GrammarAnalysis(compiled.codegen_grammar)
    analysis.eval(analysis, compiled.codegen_grammar, ())
    items = list(analysis.rules[unit].body[0])
    return greedy_loop_gate(analysis.rules, analysis.start, unit, items, 0)


def test_the_baseline_shape_is_licensed() -> None:
    """Without this, every refusal below could be refusing for another reason.

    The control: the grammar the seven conditions are written for gets a gate,
    and the gate says what the runtime will look for — one terminator of tail,
    nothing after it, and the end of the input.
    """
    gate = _gate(CERTIFIED, key="greedy-certified")

    assert gate == (";", "", None)


# ── (a) the item repetition must be unbounded ──────────────────────────


def test_a_bounded_item_repetition_is_refused() -> None:
    """The exchange has no ceiling to respect, so it needs none to exist.

    Absorption works by giving a unit MORE items than it had. A bound on the
    repetition makes that illegal at some count, and the certifier cannot know
    which documents reach it.
    """
    assert (
        _gate(
            'doc ::= u+\nu ::= i{1,4} tl\ni ::= [ab]* t\ntl ::= t\nt ::= ";"\n',
            key="greedy-bounded",
        )
        is None
    )


# ── (b) the terminator, a single character no body character can be ────


def test_a_terminator_the_body_can_also_hold_is_refused() -> None:
    """``[ab;]*`` can consume the terminator, so a run of them is not a run of
    empty items — the re-reading the exchange depends on stops being unique."""
    assert (
        _gate(
            'doc ::= u+\nu ::= i+ tl\ni ::= [ab;]* t\ntl ::= t\nt ::= ";"\n',
            key="greedy-body-holds-t",
        )
        is None
    )


def test_a_multi_character_terminator_is_refused() -> None:
    """A longer delimiter can overlap itself or straddle a boundary.

    (b) is stated for ONE character, and the certifier refuses rather than
    reason about a two-character terminator it has never been shown to handle.
    """
    assert (
        _gate(
            'doc ::= u+\nu ::= i+ tl\ni ::= [ab]* t\ntl ::= t\nt ::= ";;"\n',
            key="greedy-long-t",
        )
        is None
    )


# ── (c) the body nullable ──────────────────────────────────────────────


def test_a_non_nullable_body_is_refused() -> None:
    """``[ab]+`` cannot be empty, so a terminator cannot be re-read as an item.

    This is also the shape the PDA already takes — the non-nullable twin the
    effort's reports contrast the class against — so a licence here would be
    both wrong and pointless.
    """
    assert (
        _gate(
            'doc ::= u+\nu ::= i+ tl\ni ::= [ab]+ t\ntl ::= t\nt ::= ";"\n',
            key="greedy-non-nullable",
        )
        is None
    )


# ── (d) the tail, exactly m copies of the terminator ───────────────────


def test_a_tail_that_is_not_copies_of_the_terminator_is_refused() -> None:
    """A ``.`` tail against a ``;`` terminator: the exchange's re-reading has
    nothing to re-read, because the tail is not made of items' terminators.

    Measured to be SUFFICIENT and not necessary — the greedy rule still
    describes this grammar — so the refusal is the proof's reach, not the
    rule's, and the test says so rather than implying the shape is broken.
    """
    assert (
        _gate(
            'doc ::= u+\nu ::= i+ tl\ni ::= [ab]* t\ntl ::= "."\nt ::= ";"\n',
            key="greedy-other-tail",
        )
        is None
    )


# ── (e) the continuation's boundary ────────────────────────────────────


def test_a_continuation_whose_starters_cannot_begin_an_item_is_licensed() -> None:
    """``#`` can start neither a body nor a terminator, so it locates the end."""
    gate = _gate(
        'doc ::= u+ end\nu ::= i+ tl\ni ::= [ab]* t\ntl ::= t\nt ::= ";"\n'
        'end ::= "#"\n',
        key="greedy-disjoint-close",
    )

    assert gate == (";", "", frozenset({"#"}))


def test_a_continuation_that_can_begin_a_body_is_charged_its_spelling() -> None:
    """astra's counterexample, as a licence rather than as a conflict pair.

    ``c ::= "a"`` differs from the terminator and still begins a BODY, so after
    the tail an ``a`` may be the continuation or the next item. A starter test
    cannot tell; matching the literal to the end of the input can, and its
    length is charged — which is why this grammar needs three characters of
    lookahead where the others need two.
    """
    gate = _gate(
        'doc ::= u+ c\nu ::= i+ tl\ni ::= [a]* t\ntl ::= t\nt ::= ";"\nc ::= "a"\n',
        key="greedy-astra",
    )

    assert gate == (";", "a", None)


def test_a_continuation_with_no_fixed_spelling_is_refused() -> None:
    """Its starters meet an item's and it cannot be matched in full either.

    ``c ::= [ab]+`` begins where a body does, so no starter separates it, and
    it spells infinitely many strings, so there is nothing to match to the end
    of the input. Neither branch of (e) applies and the certifier declines.
    """
    assert (
        _gate(
            'doc ::= u+ c\nu ::= i+ tl\ni ::= [ab]* t\ntl ::= t\nt ::= ";"\n'
            "c ::= [ab]+\n",
            key="greedy-open-close",
        )
        is None
    )


# ── (f) the outer occurrence ───────────────────────────────────────────


def test_a_bounded_outer_repetition_is_refused() -> None:
    """``u{2}`` cannot collapse to one unit, so absorption has no destination."""
    assert (
        _gate(
            'doc ::= u{2}\nu ::= i+ tl\ni ::= [ab]* t\ntl ::= t\nt ::= ";"\n',
            key="greedy-bounded-outer",
        )
        is None
    )


def test_a_unit_that_is_not_the_first_item_of_the_start_rule_is_refused() -> None:
    """``doc ::= open u+`` — the licence reasons about the whole input, and a
    unit behind a required prefix is not what it reasoned about."""
    assert (
        _gate(
            'doc ::= open u+\nopen ::= "<"\nu ::= i+ tl\ni ::= [ab]* t\n'
            'tl ::= t\nt ::= ";"\n',
            key="greedy-prefixed",
        )
        is None
    )


# ── (g) the body's ε, exactly one derivation ───────────────────────────


def test_a_body_nullable_through_a_nested_repetition_is_refused() -> None:
    """``w*`` with ``w ::= [ab]*`` derives ε as zero ``w``, one empty ``w``, two…

    No arm choice anywhere, and still not unique. Nullability gives EXISTENCE;
    the exchange introduces empty-bodied items and needs them to carry no
    choice, which is uniqueness. The greedy rule happens to describe this
    grammar anyway — the licence refuses it regardless, because the proof does
    not reach it.
    """
    assert (
        _gate(
            'doc ::= u+\nu ::= i+ tl\ni ::= w* t\nw ::= [ab]*\ntl ::= t\nt ::= ";"\n',
            key="greedy-nested-nullable",
        )
        is None
    )


def test_an_arm_choice_under_a_non_nullable_operand_is_licensed() -> None:
    """``b*`` over ``b ::= [ab] | [cd]``: the choice is NOT on the ε path.

    (g) asks whether the body's ε is unique. ``b`` consumes a character on
    either arm, so ε is zero repetitions and nothing else — the alternation is
    never entered to derive it, and the introduced empty items carry no choice.

    This test asserted a REFUSAL until astra found the reader behind it: it
    asked whether the operand's own body derived ε uniquely, which is a
    different question, and answered False for anything named. That licensed
    ``i ::= [a]* t`` while refusing an identical ``i ::= letter* t`` with
    ``letter ::= [a]``. Spelling a character class as a rule is not a change of
    language, and this row would have frozen the defect.
    """
    assert _gate(
        'doc ::= u+\nu ::= i+ tl\ni ::= b* t\nb ::= [ab] | [cd]\ntl ::= t\nt ::= ";"\n',
        key="greedy-arm-under-eps",
    ) == (";", "", None)


def test_an_arm_choice_that_can_derive_the_body_s_epsilon_is_refused() -> None:
    """``b ::= [ab]* | [cd]``: now ε CAN go through the operand, two ways.

    Zero repetitions of ``b*`` is one ε; one repetition taking ``b``'s nullable
    arm is another. Uniqueness fails and the licence is withheld.
    """
    assert (
        _gate(
            "doc ::= u+\nu ::= i+ tl\ni ::= b* t\nb ::= [ab]* | [cd]\n"
            'tl ::= t\nt ::= ";"\n',
            key="greedy-nullable-arm-under-eps",
        )
        is None
    )


def test_a_named_body_is_licensed_exactly_as_the_inline_one_is() -> None:
    """The witness astra asked for by name: spelling is not language.

    ``i ::= letter* t`` with ``letter ::= [a]`` and ``i ::= [a]* t`` are the
    same language, and the certifier must not tell them apart — it did, and
    licensed only the inline one.
    """
    inline = _gate(
        'doc ::= u+\nu ::= i+ tl\ni ::= [a]* t\ntl ::= t\nt ::= ";"\n',
        key="greedy-inline-body",
    )
    named = _gate(
        "doc ::= u+\nu ::= i+ tl\ni ::= letter* t\nletter ::= [a]\n"
        'tl ::= t\nt ::= ";"\n',
        key="greedy-named-body",
    )

    assert inline == named == (";", "", None)


# ── unknown is not absence ─────────────────────────────────────────────


def test_a_body_the_readers_cannot_resolve_is_refused_not_assumed_empty() -> None:
    """The failure that would be SILENT, so the one worth a grammar of its own.

    An alphabet reader that returned the empty set for something it could not
    read would prove (b) — the terminator is no body character — by never
    having looked. Here the body is an eleven-deep chain of references, past
    the depth any reader follows, so its alphabet comes back UNKNOWN. Verified
    directly: ``_alphabet_of`` returns ``None`` on this grammar's body rather
    than an empty set, and the licence is withheld.

    A certifier that guesses is worse than none, because it is believed.
    """
    chain = "".join(f"r{n} ::= r{n + 1}\n" for n in range(10))
    assert (
        _gate(
            "doc ::= u+\nu ::= i+ tl\ni ::= r0 t\n"
            + chain
            + 'r10 ::= [ab]*\ntl ::= t\nt ::= ";"\n',
            key="greedy-unknown-body",
        )
        is None
    )


@pytest.mark.parametrize(
    ("label", "source"),
    [
        ("two items and no tail", 'doc ::= u+\nu ::= i+\ni ::= [ab]* t\nt ::= ";"\n'),
        (
            "three items in the unit",
            'doc ::= u+\nu ::= i+ mid tl\ni ::= [ab]* t\nmid ::= "m"\n'
            'tl ::= t\nt ::= ";"\n',
        ),
    ],
)
def test_a_unit_that_is_not_i_plus_t_is_refused(label: str, source: str) -> None:
    """The licence is written for exactly ``I+ T`` and claims nothing wider.

    Both of these have a nullable-bodied item under an unbounded repetition —
    the interesting half — and neither is the shape the exchange argues about.
    """
    assert _gate(source, key=f"greedy-shape-{label.replace(' ', '-')}") is None
