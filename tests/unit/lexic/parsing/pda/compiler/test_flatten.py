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

from lexic.ir import BIND_MODES
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
    PdaProgram,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_ALT,
    BUILD_DISPATCH,
    BUILD_SEQ,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    DISPATCH_EMPTY,
    GATE_PAIR,
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
    """The stop-set and LL(2) pair gate codes are distinct."""
    assert GATE_STOP != GATE_PAIR


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


def test_flatclone_declares_exactly_the_selector_and_fold_build_fields():
    """FlatClone carries exactly the arm-selector + fold/build fields, no extras."""
    expected = {"name", "selectors", "kwin_selectors", "pn_selectors", "default"}
    expected |= {"struct_arm", "attempt"}
    expected |= {"mode", "fold", "fields", "plan"}
    expected |= {"fast", "defaults", "leaf", "chartable", "chartotal"}
    expected |= {"runarm", "needs_ends"}
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
