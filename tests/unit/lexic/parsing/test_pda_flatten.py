"""Tests for lexic.parsing.pda_flatten — the flat int-coded runtime program.

:mod:`lexic.parsing.pda_flatten` is the leaf half of the PDA compiler: it
defines the flat runtime shapes (:class:`~lexic.parsing.pda_flatten._FlatArm`,
:class:`~lexic.parsing.pda_flatten._FlatClone`,
:class:`~lexic.parsing.pda_flatten.PdaProgram`) and the post-flatten
optimizer passes (:func:`~lexic.parsing.pda_flatten._optimize_program` and its
five sub-passes) that :func:`~lexic.parsing.pda_tables._flatten_program`
drives once per :func:`~lexic.parsing.pda_tables.compile_pda`.

Every case here is built through the public compile path — small
hand-authored GBNF snippets compiled to a real :class:`PdaTables` and
inspected via ``.program`` — following ``test_pda_tables.py``'s idiom. Every
name below (the module's own internals) is imported directly rather than
reached through ``module._name`` attribute access, matching
``test_lexruns.py``'s precedent; ``_pda_from_text``/``_pda_for`` come from
``test_pda_tables`` rather than duplicated (pylint R0801).
"""

from __future__ import annotations

from lexic.ir.bind import BIND_MODES
from lexic.parsing.pda_flatten import (
    _BUILD_ALT,
    _BUILD_DISPATCH,
    _BUILD_SEQ,
    _BUILD_TRANSPARENT,
    _BUILD_VALUE_STR,
    _DISPATCH_EMPTY,
    _GATE_PAIR,
    _GATE_STOP,
    _HI_UNBOUNDED,
    _M_GTEXT,
    _M_MODEL,
    _M_MODELS,
    _M_TEXT,
    _MODE_CODE,
    _OP_CC,
    _OP_CC1,
    _OP_FAIL,
    _OP_GRP,
    _OP_ISLAND,
    _OP_LIT,
    _OP_LIT1,
    _OP_REF,
    _OP_REF1,
    _OP_VSTR,
    _TERMINAL_OPS,
    PdaProgram,
    _FlatArm,
    _FlatClone,
)
from lexic.parsing.pda_tables import IslandRef
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.test_pda_tables import _pda_for, _pda_from_text

# ── helpers ───────────────────────────────────────────────────────────────


def _only_arm(clone: _FlatClone) -> _FlatArm:
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
        _OP_LIT,
        _OP_CC,
        _OP_REF,
        _OP_GRP,
        _OP_ISLAND,
        _OP_FAIL,
        _OP_LIT1,
        _OP_CC1,
        _OP_VSTR,
        _OP_REF1,
    ]
    assert len(ops) == len(set(ops))


def test_terminal_ops_are_the_four_terminal_op_codes():
    """_TERMINAL_OPS is exactly the base + specialised literal/charclass codes."""
    assert _TERMINAL_OPS == {_OP_LIT, _OP_CC, _OP_LIT1, _OP_CC1}


def test_gate_codes_are_distinct():
    """The stop-set and LL(2) pair gate codes are distinct."""
    assert _GATE_STOP != _GATE_PAIR


def test_build_mode_codes_are_pairwise_distinct():
    """Every clone build-mode (including dispatch) is a distinct int."""
    modes = [
        _BUILD_TRANSPARENT,
        _BUILD_VALUE_STR,
        _BUILD_ALT,
        _BUILD_SEQ,
        _BUILD_DISPATCH,
    ]
    assert len(modes) == len(set(modes))


def test_mode_code_matches_bind_modes_order():
    """_MODE_CODE maps BIND_MODES, in order, to the _M_* int codes."""
    assert [_MODE_CODE[mode] for mode in BIND_MODES] == [
        _M_TEXT,
        _M_GTEXT,
        _M_MODEL,
        _M_MODELS,
    ]


def test_hi_unbounded_is_the_negative_sentinel():
    """The flat ``his`` sentinel for an unbounded upper bound is -1."""
    assert _HI_UNBOUNDED == -1


def test_dispatch_empty_sentinel_is_distinguishable_from_none():
    """_DISPATCH_EMPTY is a real object, distinct from None and a target clone."""
    assert isinstance(_DISPATCH_EMPTY, object)
    assert _DISPATCH_EMPTY is not None


# ── flat class shapes ───────────────────────────────────────────────────────


def test_flatarm_declares_exactly_the_parallel_per_item_arrays():
    """_FlatArm carries exactly the seven parallel per-item arrays, no extras."""
    expected = {"n", "kinds", "payloads", "los", "his", "gate_kinds", "gate_data"}
    assert set(_FlatArm.__slots__) == expected


def test_flatclone_declares_exactly_the_selector_and_fold_build_fields():
    """_FlatClone carries exactly the arm-selector + fold/build fields, no extras."""
    expected = {"selectors", "default", "mode", "fold", "fields"}
    expected |= {"fast", "defaults", "leaf", "needs_ends"}
    assert set(_FlatClone.__slots__) == expected


def test_pdaprogram_declares_a_single_start_slot():
    """PdaProgram carries only the entry clone (or island opt-out marker)."""
    assert PdaProgram.__slots__ == ("start",)


def test_pdaprogram_init_binds_start_verbatim():
    """PdaProgram.__init__ is a plain wrap — no processing of its argument."""
    sentinel = object()
    program = PdaProgram(sentinel)
    assert program.start is sentinel


# ── _specialize_terminals + _inline_value_strs + _mark_leaves ──────────────


def test_exactly_once_ref_and_literal_inline_and_specialise_to_a_leaf():
    """A ref to a terminal-only value_str clone inlines to _OP_VSTR, the
    trailing exactly-once literal specialises to _OP_LIT1, and the whole
    sequence clone earns the frame-less leaf licence.
    """
    pda = _pda_from_text('root ::= lit "x"\nlit ::= "a" | "b"\n')
    root = pda.program.start
    assert root.mode == _BUILD_SEQ
    assert root.needs_ends is False
    assert root.leaf is True
    arm = _only_arm(root)
    assert arm.n == 2
    assert arm.kinds == (_OP_VSTR, _OP_LIT1)
    assert arm.los == (1, 1)
    assert arm.his == (1, 1)
    lit_clone = arm.payloads[0]
    assert isinstance(lit_clone, _FlatClone)
    assert lit_clone.mode == _BUILD_VALUE_STR
    assert arm.payloads[1] == "x"


def test_value_str_literal_run_specialises_but_never_earns_the_leaf_flag():
    """A merged literal-run value_str clone specialises its sole item to
    _OP_LIT1, but the leaf licence is granted only to _BUILD_SEQ clones.
    """
    pda = _pda_from_text('root ::= "a" "b"\n')
    root = pda.program.start
    assert root.mode == _BUILD_VALUE_STR
    assert root.leaf is False
    arm = _only_arm(root)
    assert arm.kinds == (_OP_LIT1,)
    assert arm.payloads == ("ab",)


def test_exactly_once_charclass_specialises_to_cc1_with_a_resolved_charset():
    """An exactly-once char-class item flattens its (chars, negated) pair and
    specialises to _OP_CC1; a following ref to a terminal-only value_str
    clone still inlines to _OP_VSTR alongside it.
    """
    pda = _pda_from_text('root ::= [a-c] x\nx ::= "z"\n')
    root = pda.program.start
    arm = _only_arm(root)
    assert arm.kinds == (_OP_CC1, _OP_VSTR)
    chars, negated = arm.payloads[0]
    assert chars == frozenset("abc")
    assert negated is False


def test_unbounded_terminal_is_never_specialised_to_its_exactly_once_code():
    """A quantified (non-exactly-once) literal keeps the plain _OP_LIT code —
    _specialize_terminals only rewrites lo == hi == 1 items.
    """
    pda = _pda_from_text('root ::= "a"+ x\nx ::= y "q"\ny ::= "p"\n')
    root = pda.program.start
    arm = _only_arm(root)
    assert arm.kinds[0] == _OP_LIT
    assert arm.los[0] == 1
    assert arm.his[0] == _HI_UNBOUNDED


# ── _convert_dispatch ────────────────────────────────────────────────────


def test_qualifying_alternation_converts_to_a_frameless_dispatch_clone():
    """An alternation whose every arm is a single unit ref to a non-inlined
    clone converts to _BUILD_DISPATCH, carrying the target clones directly
    as selector payloads with no default.
    """
    text = (
        'root ::= alt\nalt ::= a | b\na ::= x "1"\nb ::= y "2"\nx ::= "q"\ny ::= "r"\n'
    )
    pda = _pda_from_text(text)
    root = pda.program.start
    arm = _only_arm(root)
    assert arm.kinds == (_OP_REF1,)  # needs_ends False: the call specialises too
    alt_clone = arm.payloads[0]
    assert alt_clone.mode == _BUILD_DISPATCH
    assert alt_clone.default is None
    targets = {chars: target for chars, _negated, target in alt_clone.selectors}
    assert targets[frozenset({"q"})].mode == _BUILD_SEQ
    assert targets[frozenset({"r"})].mode == _BUILD_SEQ


def test_dispatch_conversion_skipped_once_value_str_inlining_eats_the_refs():
    """When every arm's target is itself a terminal-only value_str clone,
    _inline_value_strs rewrites the unit refs to _OP_VSTR *before*
    _convert_dispatch runs — the alternation no longer has the unit-ref
    shape the dispatch rewrite requires, so it stays _BUILD_ALT.
    """
    pda = _pda_from_text('root ::= alt\nalt ::= a | b\na ::= "1"\nb ::= "2"\n')
    root = pda.program.start
    arm = _only_arm(root)
    alt_clone = arm.payloads[0]
    assert alt_clone.mode == _BUILD_ALT
    for _chars, _negated, sub_arm in alt_clone.selectors:
        assert sub_arm.kinds == (_OP_VSTR,)


# ── _specialize_calls ────────────────────────────────────────────────────


def test_specialize_calls_is_blocked_by_a_needs_ends_sequence_clone():
    """An exactly-once ref stays _OP_REF (never promoted to _OP_REF1) when
    its own clone keeps item ends for some other bound field's text span.
    """
    pda = _pda_from_text('root ::= "a"+ x\nx ::= y "q"\ny ::= "p"\n')
    root = pda.program.start
    assert root.needs_ends is True
    arm = _only_arm(root)
    assert arm.kinds[1] == _OP_REF
    x_clone = arm.payloads[1]
    assert x_clone.mode == _BUILD_SEQ  # not vstr-inlinable: it holds a ruleref


# ── inline group flatten (_flatten_group / _BUILD_TRANSPARENT) ────────────


def test_inline_group_flattens_transparent_with_no_fold_and_no_fast_ctor():
    """A ref-bearing inline group (too small to be hoisted to a named rule)
    flattens to a frame-less _BUILD_TRANSPARENT clone: no RuleFold, no
    fields, no fast constructor, never leaf-licenced.
    """
    pda = _pda_from_text('root ::= (x "1" | y "2")\nx ::= "a"\ny ::= "b"\n')
    root = pda.program.start
    assert root.needs_ends is True
    arm = _only_arm(root)
    assert arm.kinds == (_OP_GRP,)
    group = arm.payloads[0]
    assert group.mode == _BUILD_TRANSPARENT
    assert group.fold is None
    assert group.fields == ()
    assert group.fast is None
    assert group.defaults is None
    assert group.leaf is False
    assert len(group.selectors) == 2
    assert group.default is None


# ── island / fail-island flattening ─────────────────────────────────────


def test_island_ref_flattens_to_op_island_carrying_the_rule_name():
    """A ref to a genuine (non-fail) island flattens to _OP_ISLAND with the
    island's rule name as payload — the runtime's splice-in marker.
    """
    pda = _pda_from_text('root ::= x\nx ::= "a"? "a"\n')
    assert "x" in pda.islands
    arm = _only_arm(pda.program.start)
    assert arm.kinds == (_OP_ISLAND,)
    assert arm.payloads == ("x",)


def test_fail_island_ref_flattens_to_op_fail_carrying_the_rule_name():
    """A ref to a fail-island (the F1 soft-follower-escape shape) flattens
    to _OP_FAIL, never spliced by the pure-PDA runtime.
    """
    pda = _pda_from_text('root ::= x "ab"?\nx ::= [a-c]*\n')
    arm = _only_arm(pda.program.start)
    assert arm.kinds[0] == _OP_FAIL
    assert arm.payloads[0] == "x"


def test_start_rule_itself_an_island_flattens_the_program_to_a_bare_islandref():
    """When the start rule is itself an island, PdaProgram.start is the
    IslandRef marker directly — no _FlatClone entry point at all.
    """
    pda = _pda_from_text('root ::= "a"? "a"\n')
    assert pda.islands == frozenset({"root"})
    assert pda.program.start == IslandRef("root", fail=False)


# ── ground-truth sweep (optimizer invariants hold on real grammars) ────────


def test_every_exactly_once_terminal_is_specialised_across_ground_truth():
    """No reachable arm keeps a bare _OP_LIT/_OP_CC on an exactly-once item —
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
        if clone.mode == _BUILD_DISPATCH:
            for _chars, _negated, target in clone.selectors:
                stack.append(target)
            continue
        arms = [arm for _chars, _negated, arm in clone.selectors]
        if clone.default is not None:
            arms.append(clone.default)
        for arm in arms:
            for i, kind in enumerate(arm.kinds):
                if kind in (_OP_LIT, _OP_CC):
                    assert not (arm.los[i] == 1 and arm.his[i] == 1)
                payload = arm.payloads[i]
                if kind in (_OP_GRP, _OP_REF, _OP_REF1, _OP_VSTR):
                    stack.append(payload)
