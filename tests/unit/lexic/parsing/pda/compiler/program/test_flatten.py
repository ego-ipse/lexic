"""Tests for lexic.parsing.pda.compiler.program.flatten — the flat int-coded runtime program.

:mod:`lexic.parsing.pda.compiler.program.flatten` is the leaf half of the PDA compiler: it
defines the flat runtime shapes (:class:`~lexic.parsing.pda.compiler.program.flatten.FlatArm`,
:class:`~lexic.parsing.pda.compiler.program.flatten.FlatClone`,
:class:`~lexic.parsing.pda.compiler.program.flatten.PdaProgram`) and the post-flatten
optimizer passes (:func:`~lexic.parsing.pda.compiler.program.flatten.optimize_program` and its
five sub-passes) that :func:`~lexic.parsing.pda.compiler.clones.flatten_program`
drives once per :func:`~lexic.parsing.pda.compiler.clones.compile_pda`.

Every case here is built through the public compile path — small
hand-authored GBNF snippets compiled to a real :class:`PdaTables` and
inspected via ``.program`` — following ``test_clones.py``'s idiom. Every
name below (the module's own internals) is imported directly rather than
reached through ``module._name`` attribute access, matching
``test_lexruns.py``'s precedent; ``pda_from_text``/``pda_for`` come from
``test_clones`` rather than duplicated (pylint R0801).
"""

from __future__ import annotations

import pytest

from lexic.ir import BIND_MODES
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
    PdaProgram,
    gate_take,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_ALT,
    BUILD_DISPATCH,
    BUILD_SEQ,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    DISPATCH_EMPTY,
    GATE_ATTEMPT,
    GATE_GREEDY,
    GATE_KWIN,
    GATE_STOP,
    HI_UNBOUNDED,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_SPAN,
    M_TEXT,
    MODE_CODE,
    OP_CC,
    OP_CC1,
    OP_FAIL,
    OP_GRP,
    OP_ISLAND,
    OP_LIT,
    OP_LIT1,
    OP_REF,
    OP_REF1,
    OP_VSTR,
    TERMINAL_OPS,
)
from tests.unit.lexic.parsing.pda.compiler.test_clones import only_arm, pda_from_text

# ── helpers ───────────────────────────────────────────────────────────────


# ── op-code / build-mode / gate constant tables ────────────────────────────


def test_op_codes_are_pairwise_distinct():
    """Every base + specialised op-code is a distinct int."""
    ops = [
        OP_LIT,
        OP_CC,
        OP_REF,
        OP_GRP,
        OP_ISLAND,
        OP_FAIL,
        OP_LIT1,
        OP_CC1,
        OP_VSTR,
        OP_REF1,
    ]
    assert len(ops) == len(set(ops))


def test_terminal_ops_are_the_four_terminal_op_codes():
    """TERMINAL_OPS is exactly the base + specialised literal/charclass codes."""
    assert TERMINAL_OPS == {OP_LIT, OP_CC, OP_LIT1, OP_CC1}


def test_gate_codes_are_distinct():
    """The stop-set and window gate codes are distinct."""
    assert GATE_STOP != GATE_KWIN


def test_build_mode_codes_are_pairwise_distinct():
    """Every model clone build-mode is a distinct int."""
    modes = [
        BUILD_TRANSPARENT,
        BUILD_VALUE_STR,
        BUILD_ALT,
        BUILD_SEQ,
        BUILD_DISPATCH,
    ]
    assert len(modes) == len(set(modes))


def test_mode_code_matches_bind_modes_order():
    """MODE_CODE maps BIND_MODES, in order, to the _M_* int codes."""
    assert [MODE_CODE[mode] for mode in BIND_MODES] == [
        M_TEXT,
        M_GTEXT,
        M_MODEL,
        M_MODELS,
        M_SPAN,
    ]


def test_hi_unbounded_is_the_negative_sentinel():
    """The flat ``his`` sentinel for an unbounded upper bound is -1."""
    assert HI_UNBOUNDED == -1


def test_dispatch_empty_sentinel_is_distinguishable_from_none():
    """DISPATCH_EMPTY is a real object, distinct from None and a target clone."""
    assert isinstance(DISPATCH_EMPTY, object)
    assert DISPATCH_EMPTY is not None


# ── flat class shapes ───────────────────────────────────────────────────────


def test_flatarm_declares_exactly_the_parallel_per_item_arrays():
    """FlatArm carries exactly the seven parallel per-item arrays, no extras."""
    expected = {"n", "kinds", "payloads", "los", "his", "gate_kinds", "gate_data"}
    assert set(FlatArm.__slots__) == expected


def test_flatclone_declares_exactly_the_selector_and_build_fields():
    """FlatClone carries exactly the arm-selector + build fields, no extras."""
    expected = {"name", "selectors", "kwin_selectors", "pn_selectors", "default"}
    expected |= {"struct_arm", "attempt"}
    expected |= {"mode", "ctor", "matched", "n_items", "fields", "plan"}
    expected |= {"fast", "build", "defaults", "leaf", "chartable", "chartotal"}
    expected |= {"runarm", "needs_ends", "completion", "fold"}
    assert set(FlatClone.__slots__) == expected


def test_a_clone_carries_the_rule_name_it_stands_for():
    """The flat artifact names itself — no reaching back into the binding view."""
    pda = pda_from_text('root ::= lit "x"\nlit ::= "a" | "b"\n')
    root = pda.program.start
    assert root.name == "root"
    assert only_arm(root).payloads[0].name == "lit"


def test_an_inline_group_clone_has_an_empty_name():
    """A group stands for no rule the grammar named, and says so."""
    pda = pda_from_text('root ::= (a "y" | b) "c"\na ::= "x"\nb ::= "z"\n')
    group = only_arm(pda.program.start).payloads[0]
    assert isinstance(group, FlatClone)
    assert group.name == ""


def test_pdaprogram_declares_start_and_delegates_slots():
    """PdaProgram carries the entry clone (or island opt-out) + delegate source."""
    assert PdaProgram.__slots__ == ("start", "delegates")


def test_pdaprogram_init_binds_start_verbatim():
    """PdaProgram.__init__ is a plain wrap — no processing of its argument."""
    sentinel = object()
    program = PdaProgram(sentinel)
    assert program.start is sentinel
    assert program.delegates is None  # default; the artifact attaches the source


# ── specialize_terminals + _inline_value_strs + _mark_leaves ──────────────


# ── the split-greedy gate ──────────────────────────────────────────────


EOF_GATE = (";", "", None)
"""One terminator of tail, then the end of the input."""

TWO_GATE = (";;", "", None)
"""``m = 2``: the tail is two terminators."""

STARTER_GATE = (";", "", frozenset({"#"}))
"""The continuation begins with ``#``, which cannot begin an item."""

LITERAL_GATE = (";", "a", None)
"""astra's case: the continuation is ``a``, which CAN begin a body."""


@pytest.mark.parametrize(
    ("label", "text", "pos", "takes"),
    [
        ("the tail and nothing else stops it", "a;;", 2, False),
        ("a tail with more after it does not", "a;;a;;", 2, True),
        ("mid-document, on a terminator", "a;;a;;", 5, False),
        ("a body character is not the tail", "a;ab;", 2, True),
        ("past the end takes nothing", "a;;", 3, True),
    ],
)
def test_the_end_of_input_case(label: str, text: str, pos: int, takes: bool) -> None:
    """Exit exactly where the remainder IS the tail — nowhere earlier, nowhere later.

    The last row is the one worth stating: at a position past the tail the
    remainder is empty, which is not the tail, so the gate says "take" — and
    says nothing about whether an item is there. Ordinary recognition decides
    that, which is the whole of what this gate claims.
    """
    assert gate_take(text, pos, GATE_GREEDY, EOF_GATE) is takes, label


@pytest.mark.parametrize(
    ("text", "pos", "takes"),
    [
        ("a;;;", 2, False),  # two terminators remain: the tail
        ("a;;;;", 2, True),  # three remain: one more item fits before the tail
        ("a;;", 2, True),  # only one remains — not this tail
    ],
)
def test_a_two_terminator_tail_reads_both(text: str, pos: int, takes: bool) -> None:
    """``m`` is not a constant: a longer tail moves where the loop may stop."""
    assert gate_take(text, pos, GATE_GREEDY, TWO_GATE) is takes


@pytest.mark.parametrize(
    ("text", "pos", "takes"),
    [
        ("a;;#", 2, False),  # the tail, then the continuation's first character
        ("a;;", 2, False),  # the tail, then the end — also a stop
        ("a;;a;;#", 2, True),  # the tail, then a body character: not the end
        ("a;ab;#", 2, True),  # not even the tail here
    ],
)
def test_the_disjoint_starter_case(text: str, pos: int, takes: bool) -> None:
    """A starter that cannot begin an item LOCATES the continuation.

    It does not parse it: the second row stops at the end of input too, because
    a starter set says where the continuation may begin, never that one must.
    """
    assert gate_take(text, pos, GATE_GREEDY, STARTER_GATE) is takes


@pytest.mark.parametrize(
    ("text", "pos", "takes"),
    [
        ("a;;a", 2, False),  # tail then the literal then the end
        ("a;;a;;a", 2, True),  # the same two characters, and MORE after them
        ("a;;", 2, True),  # the tail, but the continuation is missing
        ("a;;ab", 2, True),  # the literal's character, then more
    ],
)
def test_the_literal_to_end_of_input_case(text: str, pos: int, takes: bool) -> None:
    """astra's counterexample, at the predicate that answers it.

    Rows one and two are the conflict pair: identical next two characters
    (``;a``), opposite answers. A two-character window cannot separate them and
    this gate does not try — it matches the tail AND the literal AND the end of
    the input, which is why the licence charges the literal's length.
    """
    assert gate_take(text, pos, GATE_GREEDY, LITERAL_GATE) is takes


def test_every_gate_kind_still_answers_through_the_one_entry_point() -> None:
    """`gate_take` splits after three kinds; all six must still route.

    The three one- and two-character kinds are answered in `gate_take` itself so
    a hot loop pays nothing to reach them; the wider kinds go on to
    `_wide_gate_take`. A split like that is exactly where a kind can fall
    through a crack and start answering ``False`` for the wrong reason, so this
    drives one input of each kind through the single entry point and checks the
    answer against what that kind's own rule says.

    A smaller `gate_take` is not evidence of no regression — the kinds behind
    the split now cost a call, and only the remote's matrix rows on those paths
    decide that. This test defends correctness, not cost.
    """
    semi = (frozenset({";"}), False)
    table = [
        ("STOP takes a char in its set", GATE_STOP, semi, "a;", 1, True),
        ("STOP refuses one outside it", GATE_STOP, semi, "ab", 1, False),
        (
            "ATTEMPT takes a FIRST-only char",
            GATE_ATTEMPT,
            (semi, (frozenset({"#"}), False)),
            "a;",
            1,
            True,
        ),
        (
            "KWIN takes a matching window",
            GATE_KWIN,
            (((frozenset({";"}), False), (frozenset({"a"}), False)),),
            "x;a",
            1,
            True,
        ),
        (
            "KWIN refuses a window it does not hold",
            GATE_KWIN,
            (((frozenset({";"}), False), (frozenset({"a"}), False)),),
            "x;b",
            1,
            False,
        ),
        ("GREEDY stops on the tail", GATE_GREEDY, EOF_GATE, "a;", 1, False),
        ("GREEDY takes anything else", GATE_GREEDY, EOF_GATE, "a;;", 1, True),
    ]
    for label, kind, gate, text, pos, expected in table:
        assert gate_take(text, pos, kind, gate) is expected, label
