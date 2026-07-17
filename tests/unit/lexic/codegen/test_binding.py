"""Tests for codegen/binding.py — the per-rule binding view."""

from __future__ import annotations

import ast as pyast

import pytest

from lexic.base import GrammarModel
from lexic.codegen.binding import (
    _RESERVED_CLASS_NAMES,
    _RESERVED_FIELD_NAMES,
    _SCHEMA_JOINT_STRIDE,
    CHARCLASS_NAMES,
    LITERAL_NAMES,
    _schema_depths,
    _schema_joints,
    bind_fields,
    class_name_for,
    classify_rule,
    compute_binding,
    mode_for,
)
from lexic.codegen.model_emitter import CANONICAL_IMPORTS
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrChr, IrNone, IrSeq
from lexic.ir.bind import IrBind
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot

_DIGIT = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
_RANGE_AC = IrCharClass(IrRange(IrChr("a"), IrChr("c")))
_OPT = IrQuantifier(0, 1)
_STAR = IrQuantifier(0, IrNone)


# ── naming lookup tables (re-homed from ir/naming.py) ─────────────────


def test_charclass_names_keyed_by_canonical_normal_form():
    """The pattern library is keyed by canonical (post-canonicalize) forms.

    The binding view reads the codegen grammar, which is post-canonicalize —
    char classes are members-deduped, ranges coalesced and sorted by codepoint.
    The pre-canonical spellings (``[0-9a-fA-F]``/``[a-fA-F0-9]`` for hex, the
    mixed-case ``[a-zA-Z]``/``[a-zA-Z_0-9]``) folded to one normal-form key each
    when derive's non-canonical gate was removed in Task 6.
    """
    assert CHARCLASS_NAMES["[0-9]"] == "digit"
    assert CHARCLASS_NAMES["[a-z]"] == "lower"
    assert CHARCLASS_NAMES["[A-Z]"] == "upper"
    assert CHARCLASS_NAMES["[0-9A-Fa-f]"] == "hex"
    assert CHARCLASS_NAMES["[A-Za-z]"] == "letter"
    assert CHARCLASS_NAMES["[0-9A-Z_a-z]"] == "alnum"
    # The pre-canonical spellings are gone — nothing keys off them now.
    assert "[0-9a-fA-F]" not in CHARCLASS_NAMES
    assert "[a-zA-Z]" not in CHARCLASS_NAMES


def test_literal_names_table_content():
    """The literal library still maps the punctuation set to stable field names."""
    assert LITERAL_NAMES["-"] == "sign"
    assert LITERAL_NAMES["+"] == "sign"
    assert LITERAL_NAMES["."] == "dot"
    assert LITERAL_NAMES[","] == "comma"
    assert LITERAL_NAMES["="] == "eq"


# ── class naming ──────────────────────────────────────────────────────


def test_class_name_pascalcases_hyphens_and_underscores():
    """Both canonical hyphens and legacy underscores split words."""
    assert class_name_for("jp-char") == "JpChar"
    assert class_name_for("json_ws") == "JsonWs"


def test_class_name_suffixes_python_keywords():
    """A rule named after a keyword still yields a legal class name."""
    assert class_name_for("true") == "True_"


# ── kind classification ───────────────────────────────────────────────


def test_classify_value_str_without_rulerefs():
    """A body with no IrRuleRef anywhere is value_str, even multi-arm."""
    rule = IrRule("v", IrAlternation(IrLiteral("a"), IrLiteral("b")))
    assert classify_rule(rule) == "value_str"


def test_classify_alternation_needs_two_non_empty_arms():
    """Multiple ref-bearing arms classify as alternation."""
    rule = IrRule("a", IrAlternation(IrRuleRef("x"), IrRuleRef("y")))
    assert classify_rule(rule) == "alternation"


def test_classify_sequence_when_one_arm_is_empty():
    """An empty alternate arm does not promote a sequence to alternation."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrRuleRef("x"))), IrSequence()))
    assert classify_rule(rule) == "sequence"


# ── field naming cascade ──────────────────────────────────────────────


def test_fields_tier1_ruleref_uses_rule_name_underscored():
    """A ref field is named after its rule, hyphens to underscores."""
    fields = bind_fields(IrSequence(IrItem(IrRuleRef("jp-char"))), frozenset())
    assert fields == {"jp_char": IrBind(0, "model")}


def test_fields_tier2_charclass_library_hit():
    """[0-9] hits the pattern library as ``digit``."""
    fields = bind_fields(IrSequence(IrItem(_DIGIT, _STAR)), frozenset())
    assert fields == {"digit": IrBind(0, "text")}


def test_fields_tier3_positional_head_then_part_n():
    """Unmatched pattern fields fall through to head / part_2."""
    novel = IrCharClass(IrChr("!"), IrChr("?"))
    fields = bind_fields(
        IrSequence(IrItem(novel, _STAR), IrItem(novel, _STAR)), frozenset()
    )
    assert list(fields) == ["head", "part_2"]


def test_fields_structural_literal_produces_no_field():
    """A unit-quantified literal is matched text, never a field."""
    fields = bind_fields(
        IrSequence(IrItem(IrLiteral("=")), IrItem(IrRuleRef("x"))), frozenset()
    )
    assert fields == {"x": IrBind(1, "model")}


def test_fields_quantified_literal_names_from_the_library():
    """A quantified literal DOES bind, named by the literal table."""
    fields = bind_fields(IrSequence(IrItem(IrLiteral("-"), _OPT)), frozenset())
    assert fields == {"sign": IrBind(0, "text")}


def test_fields_collisions_get_numeric_suffixes():
    """Repeated base names count up: ws, ws2."""
    ws = IrItem(IrRuleRef("ws"))
    fields = bind_fields(IrSequence(ws, IrItem(IrLiteral(",")), ws), frozenset())
    assert list(fields) == ["ws", "ws2"]


def test_fields_collisions_count_up_a_third_time():
    """A third occurrence of the same base name continues the suffix run."""
    ws = IrItem(IrRuleRef("ws"))
    fields = bind_fields(
        IrSequence(ws, IrItem(IrLiteral(",")), ws, IrItem(IrLiteral(";")), ws),
        frozenset(),
    )
    assert list(fields) == ["ws", "ws2", "ws3"]


def test_fields_non_semantic_ref_flags_the_bind():
    """A ref to a noise rule binds with semantic=False."""
    fields = bind_fields(IrSequence(IrItem(IrRuleRef("ws"))), frozenset({"ws"}))
    assert fields == {"ws": IrBind(0, "model", False)}


def test_fields_unknown_atom_type_raises():
    """The tier-2 table refuses an atom type it does not know.

    ``IrNot`` cannot occur in a canonical grammar (rewrite 4 eliminates it),
    so the binding tables deliberately omit it — the dispatch default must
    refuse it loudly rather than drop the field.
    """
    with pytest.raises(UnsupportedConstructError):
        bind_fields(IrSequence(IrItem(IrNot(IrLiteral("a")))), frozenset())


# ── group naming ──────────────────────────────────────────────────────


def test_fields_ref_bearing_group_is_named_kind():
    """A group containing rulerefs binds the structural slot name ``kind``."""
    group = IrAlternation(IrRuleRef("a"), IrRuleRef("b"))
    fields = bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"kind": IrBind(0, "model")}


def test_fields_literal_group_named_from_first_atom():
    """A literal-only group names itself from its first arm's first atom."""
    group = IrAlternation(IrSequence(IrItem(IrLiteral("+"))), IrLiteral("*"))
    fields = bind_fields(IrSequence(IrItem(group, _OPT)), frozenset())
    assert fields == {"sign": IrBind(0, "gtext")}


def test_fields_literal_group_named_from_charclass_slug_fallback():
    """A literal-only group whose first atom is a non-library charclass names
    itself from the pattern slug (Tier-2 slug fallback, not the library)."""
    group = IrAlternation(IrSequence(IrItem(_RANGE_AC)))
    fields = bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"a_c": IrBind(0, "gtext")}


def test_fields_literal_group_with_unslugable_charclass_falls_to_tier3():
    """A charclass whose pattern has no identifier-safe characters at all
    (its slug is empty) falls through the reserved "cc" hint to Tier-3."""
    group = IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("@")))))
    fields = bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"head": IrBind(0, "gtext")}


# ── fold modes ────────────────────────────────────────────────────────


def test_mode_repeated_ref_is_models():
    """hi > 1 (or unbounded) on a ref yields the list mode."""
    assert mode_for(IrItem(IrRuleRef("x"), _STAR)) == "models"


def test_mode_optional_ref_is_model():
    """hi == 1 keeps the single-model mode even when optional."""
    assert mode_for(IrItem(IrRuleRef("x"), _OPT)) == "model"


def test_mode_bounded_multi_count_ref_is_models():
    """A bounded count above one (2,5) also yields the list mode."""
    assert mode_for(IrItem(IrRuleRef("x"), IrQuantifier(2, 5))) == "models"


def test_mode_unknown_atom_type_raises():
    """The mode table refuses an atom type it does not know (IrNot cannot
    occur in a canonical grammar; the raising default keeps it loud)."""
    with pytest.raises(UnsupportedConstructError):
        mode_for(IrItem(IrNot(IrLiteral("a"))))


def test_mode_ref_bearing_group_follows_quantifier():
    """A ref-bearing group folds like a ref: model vs models by hi."""
    group = IrAlternation(IrRuleRef("a"))
    assert mode_for(IrItem(group)) == "model"
    assert mode_for(IrItem(group, _STAR)) == "models"


def test_mode_all_unit_ref_group_is_model():
    """Every arm a single unit ref → model (models when the group repeats)."""
    group = IrAlternation(IrRuleRef("a"), IrRuleRef("b"))
    assert mode_for(IrItem(group)) == "model"
    assert mode_for(IrItem(group, _STAR)) == "models"


def test_mode_mixed_literal_ref_group_is_gtext():
    """A group mixing literal arms with a multi-item ref arm folds as gtext.

    The char-arm2 shape (``"\\"" | ... | "u" hexdig{4}``): a literal arm yields
    no sub-model and the ``"u" hexdig{4}`` arm is multi-item, so a model union
    is impossible — the group's matched text folds verbatim instead.
    """
    group = IrAlternation(
        IrSequence(IrItem(IrLiteral("n"))),
        IrSequence(
            IrItem(IrLiteral("u")), IrItem(IrRuleRef("hexdig"), IrQuantifier(4, 4))
        ),
    )
    assert mode_for(IrItem(group)) == "gtext"


def test_mode_literal_only_group_is_gtext():
    """A literal-only group folds as gtext (pinned existing behavior)."""
    group = IrAlternation(IrItem(IrLiteral("+")), IrItem(IrLiteral("-")))
    assert mode_for(IrItem(group)) == "gtext"


# ── compute_binding over a small grammar ──────────────────────────────


def _small_ast() -> IrAst:
    """start → choice ws?; choice → a | b; a/b value rules; ws noise."""
    return IrAst(
        IrSeq(
            IrRule(
                "start",
                IrSequence(IrItem(IrRuleRef("choice")), IrItem(IrRuleRef("ws"), _OPT)),
            ),
            IrRule("choice", IrAlternation(IrRuleRef("a"), IrRuleRef("b"))),
            IrRule("a", IrLiteral("a")),
            IrRule("b", IrLiteral("b")),
            IrRule("ws", IrItem(IrLiteral(" "), _STAR), semantic=False),
        ),
        "start",
    )


def test_compute_binding_assigns_alternation_arm_parents():
    """Rules named as unit-ref arms inherit the alternation's class."""
    by_name = {b.rule_name: b for b in compute_binding(_small_ast())}
    assert by_name["a"].parent_class_names == ("Choice",)
    assert by_name["b"].parent_class_names == ("Choice",)
    assert by_name["choice"].parent_class_names == ()


def test_compute_binding_orders_parents_before_subclasses():
    """A binding never precedes the binding of any of its parent classes."""
    bindings = compute_binding(_small_ast())
    positions = {b.class_name: i for i, b in enumerate(bindings)}
    for binding in bindings:
        for parent in binding.parent_class_names:
            if parent in positions:
                assert positions[parent] < positions[binding.class_name]


def test_compute_binding_starts_with_the_start_rule():
    """The start rule (parentless here) leads the emission order."""
    assert compute_binding(_small_ast())[0].rule_name == "start"


# ── multi-membership arms (L1) ────────────────────────────────────────
#
# A rule that is a unit-ref arm of two or more alternations subclasses all of
# them (multiple inheritance). The single-parent last-writer-wins map silently
# dropped every parent but one, so a field typed with a "losing" alternation
# class rejected the instance at fold-ctor time.


def _multi_membership_ast() -> IrAst:
    """value → bare_val | unquoted; bare_val → unquoted | num.

    ``unquoted`` is a unit-ref arm of BOTH ``value`` and ``bare_val`` (multi
    membership), and ``bare_val`` is itself an arm of ``value`` — so ``BareVal``
    is a subclass of ``Value`` and must precede it in ``Unquoted``'s bases for
    the MRO to linearize.
    """
    return IrAst(
        IrSeq(
            IrRule(
                "value", IrAlternation(IrRuleRef("bare_val"), IrRuleRef("unquoted"))
            ),
            IrRule("bare_val", IrAlternation(IrRuleRef("unquoted"), IrRuleRef("num"))),
            IrRule("unquoted", IrLiteral("u")),
            IrRule("num", IrLiteral("0")),
        ),
        "value",
    )


def test_multi_membership_arm_lists_all_parents():
    """A rule that is an arm of two alternations lists both parents."""
    by_name = {b.rule_name: b for b in compute_binding(_multi_membership_ast())}
    assert set(by_name["unquoted"].parent_class_names) == {"Value", "BareVal"}


def test_multi_membership_bases_ordered_most_derived_first():
    """A base that subclasses another base precedes it (MRO-linearizable order).

    ``BareVal`` is itself an arm of ``Value`` (so ``BareVal`` subclasses
    ``Value``); Python's C3 linearization rejects ``(Value, BareVal)``, so the
    bases must be ordered ``(BareVal, Value)``.
    """
    by_name = {b.rule_name: b for b in compute_binding(_multi_membership_ast())}
    assert by_name["unquoted"].parent_class_names == ("BareVal", "Value")


# ── unit-arm cycles (L5) ──────────────────────────────────────────────
#
# A rule that is a unit-ref arm of itself, or rules that are unit-ref arms of
# each other, would emit self-/circularly-inheriting classes (`class S(S):`)
# and die at module exec. Cycle members all derive the same language, so the
# parent graph drops intra-cycle edges (members become siblings) and widens an
# edge to an outside member to that member's whole cycle — concrete arms then
# carry every member, keeping isinstance for fields typed with any of them.


def _self_arm_ast() -> IrAst:
    """s → s | lit_a: a rule that is a unit-ref arm of itself."""
    return IrAst(
        IrSeq(
            IrRule("s", IrAlternation(IrRuleRef("s"), IrRuleRef("lit_a"))),
            IrRule("lit_a", IrLiteral("a")),
        ),
        "s",
    )


def _mutual_arm_ast() -> IrAst:
    """a → b | x ; b → a | y: mutually unit-ref-arm alternations."""
    return IrAst(
        IrSeq(
            IrRule("a", IrAlternation(IrRuleRef("b"), IrRuleRef("x"))),
            IrRule("b", IrAlternation(IrRuleRef("a"), IrRuleRef("y"))),
            IrRule("x", IrLiteral("x")),
            IrRule("y", IrLiteral("y")),
        ),
        "a",
    )


def test_self_arm_drops_the_self_parent():
    """The self unit arm contributes no parent edge; other arms keep theirs."""
    by_name = {b.rule_name: b for b in compute_binding(_self_arm_ast())}
    assert by_name["s"].parent_class_names == ()
    assert by_name["lit_a"].parent_class_names == ("S",)


def test_mutual_arm_cycle_members_become_siblings():
    """Neither cycle member subclasses the other — the hierarchy loads."""
    by_name = {b.rule_name: b for b in compute_binding(_mutual_arm_ast())}
    assert by_name["a"].parent_class_names == ()
    assert by_name["b"].parent_class_names == ()


def test_mutual_arm_concrete_arms_carry_every_cycle_member():
    """An arm of either member subclasses BOTH (the widened cross-cycle edge)."""
    by_name = {b.rule_name: b for b in compute_binding(_mutual_arm_ast())}
    assert by_name["x"].parent_class_names == ("A", "B")
    assert by_name["y"].parent_class_names == ("A", "B")


def test_cycle_member_keeps_its_outside_parent():
    """z → a | q over the a↔b cycle: ``a`` keeps ``Z``; arms still reach ``Z``.

    ``x``/``y`` subclass ``(A, B)`` and ``A`` subclasses ``Z``, so instances
    of either arm satisfy a field typed ``Z`` transitively.
    """
    ast = IrAst(
        IrSeq(
            IrRule("z", IrAlternation(IrRuleRef("a"), IrRuleRef("q"))),
            IrRule("a", IrAlternation(IrRuleRef("b"), IrRuleRef("x"))),
            IrRule("b", IrAlternation(IrRuleRef("a"), IrRuleRef("y"))),
            IrRule("x", IrLiteral("x")),
            IrRule("y", IrLiteral("y")),
            IrRule("q", IrLiteral("q")),
        ),
        "z",
    )
    by_name = {b.rule_name: b for b in compute_binding(ast)}
    assert by_name["a"].parent_class_names == ("Z",)
    assert by_name["b"].parent_class_names == ()
    assert by_name["x"].parent_class_names == ("A", "B")
    assert by_name["q"].parent_class_names == ("Z",)


# ── reserved names (L6) ───────────────────────────────────────────────


def test_class_name_mangles_keywords_and_header_bindings():
    """Keywords and emitted-header names get the ``_`` suffix; others don't."""
    assert class_name_for("true") == "True_"
    assert class_name_for("annotated") == "Annotated_"
    assert class_name_for("grammar-model") == "GrammarModel_"
    assert class_name_for("jp-char") == "JpChar"


def test_reserved_class_names_cover_the_emitted_header():
    """Every name the emitter's header binds is in the reserved-class set."""
    bound = {
        alias.asname or alias.name
        for node in pyast.walk(pyast.parse(CANONICAL_IMPORTS))
        if isinstance(node, pyast.ImportFrom)
        for alias in node.names
    }
    # ``annotations`` (the __future__ import) can never PascalCase-collide.
    assert bound - {"annotations"} <= _RESERVED_CLASS_NAMES


# The record spine's inherited IrSelf/tuple protocol surface (R2-4). NOT in
# the read-only `_RESERVED_FIELD_NAMES` yet: a rule named after one of these
# generates an unmangled field that shadows the protocol on that class — a
# KNOWN, user-accepted window (FABLE_T1_REVIEW.md T1-1) until Task 3 re-pins
# the reserved sets in the ported compile/binding.py. Pinned exactly so any
# FURTHER surface drift still fails here.
_SPINE_PROTOCOL_NAMES = frozenset(
    {"bind", "bound", "bound_type", "children", "count", "eval", "index", "rebuild"}
)


def test_reserved_field_names_cover_grammar_model():
    """Every public GrammarModel attribute outside the known Task-3 window
    is a reserved field name — and the window is exactly the pinned set."""
    public = {n for n in dir(GrammarModel) if not n.startswith("_")}
    assert public - _SPINE_PROTOCOL_NAMES <= _RESERVED_FIELD_NAMES
    assert public & _SPINE_PROTOCOL_NAMES == _SPINE_PROTOCOL_NAMES


def test_bind_fields_mangles_reserved_names():
    """Rule refs named after keywords or model attributes get a ``_`` suffix."""
    items = [
        IrItem(IrRuleRef("class")),
        IrItem(IrRuleRef("to-text")),
        IrItem(IrRuleRef("value")),
    ]
    fields = bind_fields(items, frozenset())
    assert list(fields) == ["class_", "to_text_", "value"]


def test_multi_membership_parents_all_emitted_before_child():
    """Every parent alternation is emitted before the multi-membership subclass."""
    bindings = compute_binding(_multi_membership_ast())
    positions = {b.class_name: i for i, b in enumerate(bindings)}
    for parent in bindings[
        next(i for i, b in enumerate(bindings) if b.rule_name == "unquoted")
    ].parent_class_names:
        assert positions[parent] < positions["Unquoted"]


def test_multi_membership_parent_order_is_deterministic():
    """The parent tuple is stable across repeated bindings of the same grammar."""
    ast = _multi_membership_ast()
    first = {b.rule_name: b.parent_class_names for b in compute_binding(ast)}
    second = {b.rule_name: b.parent_class_names for b in compute_binding(ast)}
    assert first == second


def test_compute_binding_flags_noise_fields_from_the_ast():
    """ast.non_semantic drives the per-field semantic flag."""
    by_name = {b.rule_name: b for b in compute_binding(_small_ast())}
    assert by_name["start"].fields["ws"].semantic is False
    assert by_name["start"].fields["choice"].semantic is True


def test_compute_binding_alternation_and_value_str_have_no_fields():
    """Only sequence-kind rules carry field bindings."""
    by_name = {b.rule_name: b for b in compute_binding(_small_ast())}
    assert by_name["choice"].fields == {}
    assert by_name["a"].fields == {}


# ── schema expansion joints (deep ref chains) ─────────────────────────


def _chain_rules(depth: int) -> list[IrRule]:
    """r0 → r1 → … → r<depth>, each a unit-ref wrapper, leaf a literal."""
    rules = [
        IrRule(f"r{i}", IrSequence(IrItem(IrRuleRef(f"r{i + 1}"))))
        for i in range(depth)
    ]
    rules.append(IrRule(f"r{depth}", IrSequence(IrItem(IrLiteral("0")))))
    return rules


def test_schema_depths_count_acyclic_chains():
    """Depth is the inlined-schema nesting: leaf 1, each referrer +1."""
    edges = {"a": ["b"], "b": ["c"], "c": []}
    assert _schema_depths(edges) == {"a": 3, "b": 2, "c": 1}


def test_schema_depths_cycle_edges_add_no_depth():
    """Cycle members keep depth from OUTSIDE refs only (pydantic def-refs)."""
    edges = {"v": ["a", "leaf"], "a": ["v"], "leaf": []}
    depths = _schema_depths(edges)
    assert depths["leaf"] == 1
    assert depths["v"] == 2  # leaf inlines; the v↔a cycle edge does not
    assert depths["a"] == 1  # a's only ref is intra-cycle — def-ref'd, shallow


def test_schema_joints_flag_every_stride_multiple():
    """A chain longer than one stride gets a joint at each stride multiple."""
    depth = 2 * _SCHEMA_JOINT_STRIDE + 10
    joints = _schema_joints(_chain_rules(depth))
    assert len(joints) == 2
    depths_of_joints = {depth + 1 - int(name[1:]) for name in joints}
    assert depths_of_joints == {_SCHEMA_JOINT_STRIDE, 2 * _SCHEMA_JOINT_STRIDE}


def test_shallow_grammars_get_no_joints():
    """Every grammar under one stride deep is untouched (all ground truths)."""
    assert not _schema_joints(_chain_rules(30))
    bindings = compute_binding(_multi_membership_ast())
    assert not any(b.schema_joint for b in bindings)


def test_compute_binding_threads_joint_flags():
    """RuleBinding.schema_joint mirrors the joint set."""
    depth = _SCHEMA_JOINT_STRIDE + 5
    rules = _chain_rules(depth)
    ast = IrAst(IrSeq(*rules), "r0")
    flagged = {b.rule_name for b in compute_binding(ast) if b.schema_joint}
    assert len(flagged) == 1
