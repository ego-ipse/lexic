"""Tests for lexic.parsing.pda.compiler.flatten — the flat int-coded runtime program.

:mod:`lexic.parsing.pda.compiler.flatten` is the leaf half of the PDA compiler: it
defines the flat runtime shapes (:class:`~lexic.parsing.pda.compiler.flatten.FlatArm`,
:class:`~lexic.parsing.pda.compiler.flatten.FlatClone`,
:class:`~lexic.parsing.pda.compiler.flatten.PdaProgram`) and the post-flatten
optimizer passes (:func:`~lexic.parsing.pda.compiler.flatten.optimize_program` and its
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
from lexic.parsing.pda.compiler.clones import IslandRef
from lexic.parsing.pda.compiler.flatten import (
    _TERMINAL_OPS,
    BUILD_ALT,
    BUILD_DISPATCH,
    BUILD_REDUCE,
    BUILD_SEQ,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    CHARTABLE_CAP,
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
    R_DROP,
    R_KEEP,
    R_SPLICE,
    FlatArm,
    FlatClone,
    PdaProgram,
    vstr_model,
)
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.pda.compiler.test_clones import pda_for, pda_from_text

# ── helpers ───────────────────────────────────────────────────────────────


def only_arm(clone: FlatClone) -> FlatArm:
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
    expected |= {"fast", "defaults", "leaf", "chartable", "needs_ends"}
    expected |= {"reduce_kind", "reduce_body", "reduce_is_yield"}
    expected |= {"reduce_span", "reduce_can_drop"}
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


# ── _specialize_terminals + _inline_value_strs + _mark_leaves ──────────────


def test_exactly_once_ref_and_literal_inline_and_specialise_to_a_leaf():
    """A ref to a terminal-only value_str clone inlines to OP_VSTR, the
    trailing exactly-once literal specialises to OP_LIT1, and the whole
    sequence clone earns the frame-less leaf licence.
    """
    pda = pda_from_text('root ::= lit "x"\nlit ::= "a" | "b"\n')
    root = pda.program.start
    assert root.mode == BUILD_SEQ
    assert root.needs_ends is False
    assert root.leaf is True
    arm = only_arm(root)
    assert arm.n == 2
    assert arm.kinds == (OP_VSTR, OP_LIT1)
    assert arm.los == (1, 1)
    assert arm.his == (1, 1)
    lit_clone = arm.payloads[0]
    assert isinstance(lit_clone, FlatClone)
    assert lit_clone.mode == BUILD_VALUE_STR
    assert arm.payloads[1] == "x"


def test_a_terminal_only_value_str_clone_earns_the_leaf_flag():
    """A merged literal-run value_str clone specialises its sole item to
    OP_LIT1 and earns the frame-less licence.

    It earns it on exactly the terms that let a REFERENCE to such a clone
    become ``OP_VSTR``: no arm can descend, so an ENTRY has nothing to keep a
    frame for either.
    """
    pda = pda_from_text('root ::= "a" "b"\n')
    root = pda.program.start
    assert root.mode == BUILD_VALUE_STR
    assert root.leaf is True
    arm = only_arm(root)
    assert arm.kinds == (OP_LIT1,)
    assert arm.payloads == ("ab",)


def test_a_value_str_clone_that_can_descend_is_not_frame_less():
    """The licence is about descent, not about the build mode.

    ``@lexical`` is what makes a ref-bearing rule a ``value_str``; its body can
    still hold a group, and then a frame is exactly what the entry needs.
    """
    text = '# @lexical pair\nroot ::= pair\npair ::= ("a" | "bb")+\n'
    pair = only_arm(pda_from_text(text).program.start).payloads[0]
    assert isinstance(pair, FlatClone)
    assert pair.mode == BUILD_VALUE_STR
    assert OP_GRP in only_arm(pair).kinds  # the descent the frame is there for
    assert pair.leaf is False


# ── chartable_for: the reconstruction licence ──────────────────────────────


def test_a_one_char_value_str_clone_carries_a_model_per_character():
    """``digit ::= [0-9]`` accepts ten strings, so all ten models are baked.

    The reconstruction licence: every string the clone accepts is one character
    wide, so its model is known from the character alone.
    """
    pda = pda_from_text('root ::= digit+ "!"\ndigit ::= [0-9]\n')
    digit = only_arm(pda.program.start).payloads[0]
    assert digit.mode == BUILD_VALUE_STR
    assert sorted(digit.chartable) == sorted("0123456789")
    assert [model.to_text() for model in digit.chartable.values()] == list(
        digit.chartable
    )


def test_a_dispatching_one_char_alternation_tables_every_arm():
    """A ``value_str`` rule of one-char arms tables the union of its arms."""
    pda = pda_from_text('root ::= sign+\nsign ::= "+" | "-" | [0-9]\n')
    sign = only_arm(pda.program.start).payloads[0]
    assert sorted(sign.chartable) == sorted("+-0123456789")


def test_a_run_valued_value_str_clone_earns_no_table():
    """``digits ::= [0-9]+`` accepts spans of any width — nothing to key on."""
    pda = pda_from_text('root ::= digits "!"\ndigits ::= [0-9]+\n')
    digits = only_arm(pda.program.start).payloads[0]
    assert digits.mode == BUILD_VALUE_STR
    assert digits.chartable is None


def test_a_negated_class_value_str_earns_no_table():
    """A co-finite class has no finite key set, so it keeps the per-span build."""
    pda = pda_from_text('root ::= other+ "!"\nother ::= [^!]\n')
    other = only_arm(pda.program.start).payloads[0]
    assert other.mode == BUILD_VALUE_STR
    assert other.chartable is None


def test_a_multi_character_literal_value_str_earns_no_table():
    """A two-char literal is not answerable from one lookahead character."""
    pda = pda_from_text('root ::= word+ "!"\nword ::= "ab" | "c"\n')
    word = only_arm(pda.program.start).payloads[0]
    assert word.mode == BUILD_VALUE_STR
    assert word.chartable is None


def test_a_class_wider_than_the_cap_earns_no_table():
    """The cap bounds compile-time work; a wide class keeps the built model."""
    wide = "".join(chr(code) for code in range(0x100, 0x100 + CHARTABLE_CAP + 8))
    pda = pda_from_text(f'root ::= glyph+ "!"\nglyph ::= [{wide}]\n')
    glyph = only_arm(pda.program.start).payloads[0]
    assert glyph.mode == BUILD_VALUE_STR
    assert glyph.chartable is None


def test_a_tabled_model_is_the_one_the_per_span_build_constructs():
    """The table caches :func:`vstr_model` — same class, same value, same hash.

    What makes a reconstructed interior model indistinguishable from a
    parse-built one, at the construction site itself.
    """
    pda = pda_from_text('root ::= digit+ "!"\ndigit ::= [0-9]\n')
    digit = only_arm(pda.program.start).payloads[0]
    for char, tabled in digit.chartable.items():
        built = vstr_model(digit, char)
        assert type(tabled) is type(built)
        assert tabled == built
        assert hash(tabled) == hash(built)


def test_exactly_once_charclass_specialises_to_cc1_with_a_resolved_charset():
    """An exactly-once char-class item flattens its (chars, negated) pair and
    specialises to OP_CC1; a following ref to a terminal-only value_str
    clone still inlines to OP_VSTR alongside it.
    """
    pda = pda_from_text('root ::= [a-c] x\nx ::= "z"\n')
    root = pda.program.start
    arm = only_arm(root)
    assert arm.kinds == (OP_CC1, OP_VSTR)
    chars, negated = arm.payloads[0]
    assert chars == frozenset("abc")
    assert negated is False


def test_unbounded_terminal_is_never_specialised_to_its_exactly_once_code():
    """A quantified (non-exactly-once) literal keeps the plain OP_LIT code —
    _specialize_terminals only rewrites lo == hi == 1 items.
    """
    pda = pda_from_text('root ::= "a"+ x\nx ::= y "q"\ny ::= "p"\n')
    root = pda.program.start
    arm = only_arm(root)
    assert arm.kinds[0] == OP_LIT
    assert arm.los[0] == 1
    assert arm.his[0] == HI_UNBOUNDED


# ── convert_dispatch ────────────────────────────────────────────────────


def test_qualifying_alternation_converts_to_a_frameless_dispatch_clone():
    """An alternation whose every arm is a single unit ref to a non-inlined
    clone converts to BUILD_DISPATCH, carrying the target clones directly
    as selector payloads with no default.
    """
    text = (
        'root ::= alt\nalt ::= a | b\na ::= x "1"\nb ::= y "2"\nx ::= "q"\ny ::= "r"\n'
    )
    pda = pda_from_text(text)
    root = pda.program.start
    arm = only_arm(root)
    assert arm.kinds == (OP_REF1,)  # needs_ends False: the call specialises too
    alt_clone = arm.payloads[0]
    assert alt_clone.mode == BUILD_DISPATCH
    assert alt_clone.default is None
    targets = {chars: target for chars, _negated, target in alt_clone.selectors}
    assert targets[frozenset({"q"})].mode == BUILD_SEQ
    assert targets[frozenset({"r"})].mode == BUILD_SEQ


def test_dispatch_conversion_survives_value_str_inlinable_arms():
    """An alternation whose arms target terminal-only value_str clones still
    dispatches: convert_dispatch runs BEFORE _inline_value_strs, so the unit
    refs it reads are still OP_REF.

    The two specialisations compete for one arm and both remove exactly one
    frame from it — but only dispatch also removes the pass-through frame the
    arms BESIDE it would otherwise pay. Running the inliner first made one
    inlinable arm disqualify its whole alternation.
    """
    pda = pda_from_text('root ::= alt\nalt ::= a | b\na ::= "1"\nb ::= "2"\n')
    root = pda.program.start
    alt_clone = only_arm(root).payloads[0]
    assert alt_clone.mode == BUILD_DISPATCH
    targets = {chars: target for chars, _negated, target in alt_clone.selectors}
    assert targets[frozenset({"1"})].mode == BUILD_VALUE_STR
    assert targets[frozenset({"2"})].mode == BUILD_VALUE_STR


def test_a_mixed_alternation_no_longer_pays_a_frame_for_its_other_arms():
    """One value_str arm beside a sequence arm: the clone still dispatches.

    This is the shape the ordering used to cost — the sequence arm gained
    nothing from the inliner and lost the frame-less dispatch to it.
    """
    pda = pda_from_text(
        'root ::= alt\nalt ::= a | b\na ::= "1"\nb ::= x "2"\nx ::= "q"\n'
    )
    alt_clone = only_arm(pda.program.start).payloads[0]
    assert alt_clone.mode == BUILD_DISPATCH
    modes = {target.mode for _chars, _negated, target in alt_clone.selectors}
    assert modes == {BUILD_VALUE_STR, BUILD_SEQ}


def test_a_lexical_rule_flattens_to_one_terminal_item():
    """``@lexical`` on ``number ::= digit+`` reaches the runtime as one
    quantified char-class op — no group clone to enter per character.

    The directive's whole point is that the rule keeps its matched TEXT; a
    redundant group in its body put a frame back in front of every character.
    """
    text = "# @lexical number\nroot ::= number\nnumber ::= digit+\ndigit ::= [0-9]\n"
    number = only_arm(pda_from_text(text).program.start).payloads[0]
    assert number.mode == BUILD_VALUE_STR
    arm = only_arm(number)
    assert arm.n == 1
    assert arm.kinds[0] in _TERMINAL_OPS
    assert arm.his[0] == HI_UNBOUNDED


# ── _specialize_calls ────────────────────────────────────────────────────


def test_specialize_calls_is_blocked_by_a_needs_ends_sequence_clone():
    """An exactly-once ref stays OP_REF (never promoted to OP_REF1) when
    its own clone keeps item ends for some other bound field's text span.
    """
    pda = pda_from_text('root ::= "a"+ x\nx ::= y "q"\ny ::= "p"\n')
    root = pda.program.start
    assert root.needs_ends is True
    arm = only_arm(root)
    assert arm.kinds[1] == OP_REF
    x_clone = arm.payloads[1]
    assert x_clone.mode == BUILD_SEQ  # not vstr-inlinable: it holds a ruleref


# ── inline group flatten (_flatten_group / BUILD_TRANSPARENT) ────────────


def test_inline_group_flattens_transparent_with_no_fold_and_no_fast_ctor():
    """A ref-bearing inline group (too small to be hoisted to a named rule)
    flattens to a frame-less BUILD_TRANSPARENT clone: no RuleFold, no
    fields, no fast constructor, never leaf-licenced.
    """
    pda = pda_from_text('root ::= (x "1" | y "2")\nx ::= "a"\ny ::= "b"\n')
    root = pda.program.start
    assert root.needs_ends is True
    arm = only_arm(root)
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
    island's rule name as payload — the runtime's splice-in marker. The
    fixture islands by LEFT RECURSION — the class no attempt can settle.
    """
    pda = pda_from_text('root ::= x\nx ::= x "a" | "b"\n')
    assert "x" in pda.islands
    arm = only_arm(pda.program.start)
    assert arm.kinds == (OP_ISLAND,)
    assert arm.payloads == ("x",)


def test_fail_island_ref_flattens_to_op_fail_carrying_the_rule_name():
    """A ref to a fail-island (the F1 soft-follower-escape shape) flattens
    to OP_FAIL, never spliced by the pure-PDA runtime.
    """
    pda = pda_from_text('root ::= x "ab"?\nx ::= [a-c]*\n')
    arm = only_arm(pda.program.start)
    assert arm.kinds[0] == OP_FAIL
    assert arm.payloads[0] == "x"


def test_start_rule_itself_an_island_flattens_the_program_to_a_bare_islandref():
    """When the start rule is itself an island, PdaProgram.start is the
    IslandRef marker directly — no FlatClone entry point at all. The fixture
    islands by LEFT RECURSION (the ungatable digit-prefix overlap shape now
    legitimately attempts, as the ``"a"? "a"`` shape before it demoted).
    """
    pda = pda_from_text('root ::= root "a" | "b"\n')
    assert pda.islands == frozenset({"root", "root-arm1"})  # the hoisted arm too
    assert pda.program.start == IslandRef("root", fail=False)


# ── ground-truth sweep (optimizer invariants hold on real grammars) ────────


def test_every_exactly_once_terminal_is_specialised_across_ground_truth():
    """No reachable arm keeps a bare OP_LIT/OP_CC on an exactly-once item —
    _specialize_terminals is exhaustive, not just true on hand fixtures.
    """
    pda = pda_for(GROUND_TRUTH / "arithmetic.gbnf")
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
