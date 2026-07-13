"""Tests for lexic.parsing.pda.flatten — the flat int-coded runtime program.

:mod:`lexic.parsing.pda.flatten` is the leaf half of the PDA compiler: it
defines the flat runtime shapes (:class:`~lexic.parsing.pda.flatten.FlatArm`,
:class:`~lexic.parsing.pda.flatten.FlatClone`,
:class:`~lexic.parsing.pda.flatten.PdaProgram`) and the post-flatten
optimizer passes (:func:`~lexic.parsing.pda.flatten.optimize_program` and its
five sub-passes) that :func:`~lexic.parsing.pda.clones._flatten_program`
drives once per :func:`~lexic.parsing.pda.clones.compile_pda`.

Every case here is built through the public compile path — small
hand-authored GBNF snippets compiled to a real :class:`PdaTables` and
inspected via ``.program`` — following ``test_clones.py``'s idiom. Every
name below (the module's own internals) is imported directly rather than
reached through ``module._name`` attribute access, matching
``test_lexruns.py``'s precedent; ``_pda_from_text``/``_pda_for`` come from
``test_clones`` rather than duplicated (pylint R0801).
"""

from __future__ import annotations

from lexic.ir.bind import BIND_MODES
from lexic.parsing.pda.clones import IslandRef
from lexic.parsing.pda.flatten import (
    _TERMINAL_OPS,
    BUILD_ALT,
    BUILD_DISPATCH,
    BUILD_REDUCE,
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
    R_DROP,
    R_KEEP,
    R_SPLICE,
    FlatArm,
    FlatClone,
    PdaProgram,
)
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.test_clones import _pda_for, _pda_from_text

# ── helpers ───────────────────────────────────────────────────────────────


def _only_arm(clone: FlatClone) -> FlatArm:
    """The clone's sole arm, whichever of ``selectors``/``default`` holds it.

    Every hand grammar below is small enough to compile to one FIRST-gated
    arm (or, for the dispatch-conversion negative case, one default-less
    alternation) — asserts that shape rather than silently picking one.
    """
    if clone.selectors:
        assert len(clone.selectors) == 1
        return clone.selectors[0][2]
    assert clone.default is not None
    return clone.default


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
    """_TERMINAL_OPS is exactly the base + specialised literal/charclass codes."""
    assert _TERMINAL_OPS == {OP_LIT, OP_CC, OP_LIT1, OP_CC1}


def test_gate_codes_are_distinct():
    """The stop-set and LL(2) pair gate codes are distinct."""
    assert GATE_STOP != GATE_PAIR


def test_build_mode_codes_are_pairwise_distinct():
    """Every clone build-mode (including dispatch and reduce) is a distinct int."""
    modes = [
        BUILD_TRANSPARENT,
        BUILD_VALUE_STR,
        BUILD_ALT,
        BUILD_SEQ,
        BUILD_DISPATCH,
        BUILD_REDUCE,
    ]
    assert len(modes) == len(set(modes))


def test_reduce_completion_kinds_are_pairwise_distinct():
    """The reduce completion kinds (KEEP/DROP/SPLICE) are distinct ints."""
    kinds = [R_KEEP, R_DROP, R_SPLICE]
    assert len(kinds) == len(set(kinds))


def test_mode_code_matches_bind_modes_order():
    """MODE_CODE maps BIND_MODES, in order, to the _M_* int codes."""
    assert [MODE_CODE[mode] for mode in BIND_MODES] == [
        M_TEXT,
        M_GTEXT,
        M_MODEL,
        M_MODELS,
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
    expected = {"selectors", "kwin_selectors", "pn_selectors", "default"}
    expected |= {"struct_arm"}
    expected |= {"mode", "fold", "fields"}
    expected |= {"fast", "defaults", "leaf", "needs_ends"}
    expected |= {"reduce_kind", "reduce_body", "reduce_is_yield"}
    expected |= {"reduce_span", "reduce_can_drop"}
    assert set(FlatClone.__slots__) == expected


def test_pdaprogram_declares_start_and_delegates_slots():
    """PdaProgram carries the entry clone (or island opt-out) + delegate source."""
    assert PdaProgram.__slots__ == ("start", "delegates")


def test_pdaprogram_init_binds_start_verbatim():
    """PdaProgram.__init__ is a plain wrap — no processing of its argument."""
    sentinel = object()
    program = PdaProgram(sentinel)
    assert program.start is sentinel
    assert program.delegates is None  # default; the artifact attaches the source


# ── _specialize_terminals + _inline_value_strs + _mark_leaves ──────────────


def test_exactly_once_ref_and_literal_inline_and_specialise_to_a_leaf():
    """A ref to a terminal-only value_str clone inlines to OP_VSTR, the
    trailing exactly-once literal specialises to OP_LIT1, and the whole
    sequence clone earns the frame-less leaf licence.
    """
    pda = _pda_from_text('root ::= lit "x"\nlit ::= "a" | "b"\n')
    root = pda.program.start
    assert root.mode == BUILD_SEQ
    assert root.needs_ends is False
    assert root.leaf is True
    arm = _only_arm(root)
    assert arm.n == 2
    assert arm.kinds == (OP_VSTR, OP_LIT1)
    assert arm.los == (1, 1)
    assert arm.his == (1, 1)
    lit_clone = arm.payloads[0]
    assert isinstance(lit_clone, FlatClone)
    assert lit_clone.mode == BUILD_VALUE_STR
    assert arm.payloads[1] == "x"


def test_value_str_literal_run_specialises_but_never_earns_the_leaf_flag():
    """A merged literal-run value_str clone specialises its sole item to
    OP_LIT1, but the leaf licence is granted only to BUILD_SEQ clones.
    """
    pda = _pda_from_text('root ::= "a" "b"\n')
    root = pda.program.start
    assert root.mode == BUILD_VALUE_STR
    assert root.leaf is False
    arm = _only_arm(root)
    assert arm.kinds == (OP_LIT1,)
    assert arm.payloads == ("ab",)


def test_exactly_once_charclass_specialises_to_cc1_with_a_resolved_charset():
    """An exactly-once char-class item flattens its (chars, negated) pair and
    specialises to OP_CC1; a following ref to a terminal-only value_str
    clone still inlines to OP_VSTR alongside it.
    """
    pda = _pda_from_text('root ::= [a-c] x\nx ::= "z"\n')
    root = pda.program.start
    arm = _only_arm(root)
    assert arm.kinds == (OP_CC1, OP_VSTR)
    chars, negated = arm.payloads[0]
    assert chars == frozenset("abc")
    assert negated is False


def test_unbounded_terminal_is_never_specialised_to_its_exactly_once_code():
    """A quantified (non-exactly-once) literal keeps the plain OP_LIT code —
    _specialize_terminals only rewrites lo == hi == 1 items.
    """
    pda = _pda_from_text('root ::= "a"+ x\nx ::= y "q"\ny ::= "p"\n')
    root = pda.program.start
    arm = _only_arm(root)
    assert arm.kinds[0] == OP_LIT
    assert arm.los[0] == 1
    assert arm.his[0] == HI_UNBOUNDED


# ── _convert_dispatch ────────────────────────────────────────────────────


def test_qualifying_alternation_converts_to_a_frameless_dispatch_clone():
    """An alternation whose every arm is a single unit ref to a non-inlined
    clone converts to BUILD_DISPATCH, carrying the target clones directly
    as selector payloads with no default.
    """
    text = (
        'root ::= alt\nalt ::= a | b\na ::= x "1"\nb ::= y "2"\nx ::= "q"\ny ::= "r"\n'
    )
    pda = _pda_from_text(text)
    root = pda.program.start
    arm = _only_arm(root)
    assert arm.kinds == (OP_REF1,)  # needs_ends False: the call specialises too
    alt_clone = arm.payloads[0]
    assert alt_clone.mode == BUILD_DISPATCH
    assert alt_clone.default is None
    targets = {chars: target for chars, _negated, target in alt_clone.selectors}
    assert targets[frozenset({"q"})].mode == BUILD_SEQ
    assert targets[frozenset({"r"})].mode == BUILD_SEQ


def test_dispatch_conversion_skipped_once_value_str_inlining_eats_the_refs():
    """When every arm's target is itself a terminal-only value_str clone,
    _inline_value_strs rewrites the unit refs to OP_VSTR *before*
    _convert_dispatch runs — the alternation no longer has the unit-ref
    shape the dispatch rewrite requires, so it stays BUILD_ALT.
    """
    pda = _pda_from_text('root ::= alt\nalt ::= a | b\na ::= "1"\nb ::= "2"\n')
    root = pda.program.start
    arm = _only_arm(root)
    alt_clone = arm.payloads[0]
    assert alt_clone.mode == BUILD_ALT
    for _chars, _negated, sub_arm in alt_clone.selectors:
        assert sub_arm.kinds == (OP_VSTR,)


# ── _specialize_calls ────────────────────────────────────────────────────


def test_specialize_calls_is_blocked_by_a_needs_ends_sequence_clone():
    """An exactly-once ref stays OP_REF (never promoted to OP_REF1) when
    its own clone keeps item ends for some other bound field's text span.
    """
    pda = _pda_from_text('root ::= "a"+ x\nx ::= y "q"\ny ::= "p"\n')
    root = pda.program.start
    assert root.needs_ends is True
    arm = _only_arm(root)
    assert arm.kinds[1] == OP_REF
    x_clone = arm.payloads[1]
    assert x_clone.mode == BUILD_SEQ  # not vstr-inlinable: it holds a ruleref


# ── inline group flatten (_flatten_group / BUILD_TRANSPARENT) ────────────


def test_inline_group_flattens_transparent_with_no_fold_and_no_fast_ctor():
    """A ref-bearing inline group (too small to be hoisted to a named rule)
    flattens to a frame-less BUILD_TRANSPARENT clone: no RuleFold, no
    fields, no fast constructor, never leaf-licenced.
    """
    pda = _pda_from_text('root ::= (x "1" | y "2")\nx ::= "a"\ny ::= "b"\n')
    root = pda.program.start
    assert root.needs_ends is True
    arm = _only_arm(root)
    assert arm.kinds == (OP_GRP,)
    group = arm.payloads[0]
    assert group.mode == BUILD_TRANSPARENT
    assert group.fold is None
    assert group.fields == ()
    assert group.fast is None
    assert group.defaults is None
    assert group.leaf is False
    assert len(group.selectors) == 2
    assert group.default is None


# ── island / fail-island flattening ─────────────────────────────────────


def test_island_ref_flattens_to_op_island_carrying_the_rule_name():
    """A ref to a genuine (non-fail) island flattens to OP_ISLAND with the
    island's rule name as payload — the runtime's splice-in marker.
    """
    pda = _pda_from_text('root ::= x\nx ::= n "x" | n "y"\nn ::= [0-9]+\n')
    assert "x" in pda.islands
    arm = _only_arm(pda.program.start)
    assert arm.kinds == (OP_ISLAND,)
    assert arm.payloads == ("x",)


def test_fail_island_ref_flattens_to_op_fail_carrying_the_rule_name():
    """A ref to a fail-island (the F1 soft-follower-escape shape) flattens
    to OP_FAIL, never spliced by the pure-PDA runtime.
    """
    pda = _pda_from_text('root ::= x "ab"?\nx ::= [a-c]*\n')
    arm = _only_arm(pda.program.start)
    assert arm.kinds[0] == OP_FAIL
    assert arm.payloads[0] == "x"


def test_start_rule_itself_an_island_flattens_the_program_to_a_bare_islandref():
    """When the start rule is itself an island, PdaProgram.start is the
    IslandRef marker directly — no FlatClone entry point at all. The fixture
    shares an unbounded digit prefix across arms, ungatable at any ``k ≤ 3``
    (the old ``"a"? "a"`` shape now legitimately demotes under P2).
    """
    pda = _pda_from_text('root ::= n "x" | n "y"\nn ::= [0-9]+\n')
    assert pda.islands == frozenset({"root"})
    assert pda.program.start == IslandRef("root", fail=False)


# ── ground-truth sweep (optimizer invariants hold on real grammars) ────────


def test_every_exactly_once_terminal_is_specialised_across_ground_truth():
    """No reachable arm keeps a bare OP_LIT/OP_CC on an exactly-once item —
    _specialize_terminals is exhaustive, not just true on hand fixtures.
    """
    pda = _pda_for(GROUND_TRUTH / "arithmetic.gbnf")
    stack = [pda.program.start] if hasattr(pda.program.start, "mode") else []
    seen: set[int] = set()
    while stack:
        clone = stack.pop()
        if id(clone) in seen:
            continue
        seen.add(id(clone))
        if clone.mode == BUILD_DISPATCH:
            for _chars, _negated, target in clone.selectors:
                stack.append(target)
            continue
        arms = [arm for _chars, _negated, arm in clone.selectors]
        if clone.default is not None:
            arms.append(clone.default)
        for arm in arms:
            for i, kind in enumerate(arm.kinds):
                if kind in (OP_LIT, OP_CC):
                    assert not (arm.los[i] == 1 and arm.his[i] == 1)
                payload = arm.payloads[i]
                if kind in (OP_GRP, OP_REF, OP_REF1, OP_VSTR):
                    stack.append(payload)
