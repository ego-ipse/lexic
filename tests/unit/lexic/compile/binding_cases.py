"""Shared test bodies for the ``lexic.compile.binding`` view.

The test bodies live here as module-level functions taking the module under
test as their sole parameter; ``tests/unit/lexic/compile/test_binding.py``
imports its target module and calls :func:`make_binding_tests` to populate
its globals. The parameterization is a vestige of a strangler window when a
byte-identical twin module existed; only the compile view remains.
"""

from __future__ import annotations

from functools import partial
from types import ModuleType
from typing import Callable

import pytest

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
from lexic.model import GrammarModel

DIGIT = IrCharClass(IrRange(IrChr("0"), IrChr("9")))
RANGE_AC = IrCharClass(IrRange(IrChr("a"), IrChr("c")))
OPT = IrQuantifier(0, 1)
STAR = IrQuantifier(0, IrNone)


def small_ast() -> IrAst:
    """start → choice ws?; choice → a | b; a/b value rules; ws noise."""
    return IrAst(
        IrSeq(
            IrRule(
                "start",
                IrSequence(IrItem(IrRuleRef("choice")), IrItem(IrRuleRef("ws"), OPT)),
            ),
            IrRule("choice", IrAlternation(IrRuleRef("a"), IrRuleRef("b"))),
            IrRule("a", IrLiteral("a")),
            IrRule("b", IrLiteral("b")),
            IrRule("ws", IrItem(IrLiteral(" "), STAR), semantic=False),
        ),
        "start",
    )


def multi_membership_ast() -> IrAst:
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


def self_arm_ast() -> IrAst:
    """s → s | lit_a: a rule that is a unit-ref arm of itself."""
    return IrAst(
        IrSeq(
            IrRule("s", IrAlternation(IrRuleRef("s"), IrRuleRef("lit_a"))),
            IrRule("lit_a", IrLiteral("a")),
        ),
        "s",
    )


def mutual_arm_ast() -> IrAst:
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


# ── naming lookup tables (re-homed from ir/naming.py) ─────────────────


def case_charclass_names_keyed_by_canonical_normal_form(binding: ModuleType) -> None:
    """The pattern library is keyed by canonical (post-canonicalize) forms.

    The binding view reads the codegen grammar, which is post-canonicalize —
    char classes are members-deduped, ranges coalesced and sorted by codepoint.
    The pre-canonical spellings (``[0-9a-fA-F]``/``[a-fA-F0-9]`` for hex, the
    mixed-case ``[a-zA-Z]``/``[a-zA-Z_0-9]``) folded to one normal-form key each
    when derive's non-canonical gate was removed in Task 6.
    """
    assert binding.CHARCLASS_NAMES["[0-9]"] == "digit"
    assert binding.CHARCLASS_NAMES["[a-z]"] == "lower"
    assert binding.CHARCLASS_NAMES["[A-Z]"] == "upper"
    assert binding.CHARCLASS_NAMES["[0-9A-Fa-f]"] == "hex"
    assert binding.CHARCLASS_NAMES["[A-Za-z]"] == "letter"
    assert binding.CHARCLASS_NAMES["[0-9A-Z_a-z]"] == "alnum"
    # The pre-canonical spellings are gone — nothing keys off them now.
    assert "[0-9a-fA-F]" not in binding.CHARCLASS_NAMES
    assert "[a-zA-Z]" not in binding.CHARCLASS_NAMES


def case_literal_names_table_content(binding: ModuleType) -> None:
    """The literal library still maps the punctuation set to stable field names."""
    assert binding.LITERAL_NAMES["-"] == "sign"
    assert binding.LITERAL_NAMES["+"] == "sign"
    assert binding.LITERAL_NAMES["."] == "dot"
    assert binding.LITERAL_NAMES[","] == "comma"
    assert binding.LITERAL_NAMES["="] == "eq"


# ── class naming ──────────────────────────────────────────────────────


def case_class_name_pascalcases_hyphens_and_underscores(binding: ModuleType) -> None:
    """Both canonical hyphens and legacy underscores split words."""
    assert binding.class_name_for("jp-char") == "JpChar"
    assert binding.class_name_for("json_ws") == "JsonWs"


def case_class_name_suffixes_python_keywords(binding: ModuleType) -> None:
    """A rule named after a keyword still yields a legal class name."""
    assert binding.class_name_for("true") == "True_"


# ── kind classification ───────────────────────────────────────────────


def case_classify_value_str_without_rulerefs(binding: ModuleType) -> None:
    """A body with no IrRuleRef anywhere is value_str, even multi-arm."""
    rule = IrRule("v", IrAlternation(IrLiteral("a"), IrLiteral("b")))
    assert binding.classify_rule(rule) == "value_str"


def case_classify_alternation_needs_two_non_empty_arms(binding: ModuleType) -> None:
    """Multiple ref-bearing arms classify as alternation."""
    rule = IrRule("a", IrAlternation(IrRuleRef("x"), IrRuleRef("y")))
    assert binding.classify_rule(rule) == "alternation"


def case_classify_sequence_when_one_arm_is_empty(binding: ModuleType) -> None:
    """An empty alternate arm does not promote a sequence to alternation."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrRuleRef("x"))), IrSequence()))
    assert binding.classify_rule(rule) == "sequence"


# ── field naming cascade ──────────────────────────────────────────────


def case_fields_tier1_ruleref_uses_rule_name_underscored(binding: ModuleType) -> None:
    """A ref field is named after its rule, hyphens to underscores."""
    fields = binding.bind_fields(IrSequence(IrItem(IrRuleRef("jp-char"))), frozenset())
    assert fields == {"jp_char": IrBind(0, "model")}


def case_fields_tier2_charclass_library_hit(binding: ModuleType) -> None:
    """[0-9] hits the pattern library as ``digit``."""
    fields = binding.bind_fields(IrSequence(IrItem(DIGIT, STAR)), frozenset())
    assert fields == {"digit": IrBind(0, "text")}


def case_fields_tier3_positional_head_then_part_n(binding: ModuleType) -> None:
    """Unmatched pattern fields fall through to head / part_2."""
    novel = IrCharClass(IrChr("!"), IrChr("?"))
    fields = binding.bind_fields(
        IrSequence(IrItem(novel, STAR), IrItem(novel, STAR)), frozenset()
    )
    assert list(fields) == ["head", "part_2"]


def case_fields_structural_literal_produces_no_field(binding: ModuleType) -> None:
    """A unit-quantified literal is matched text, never a field."""
    fields = binding.bind_fields(
        IrSequence(IrItem(IrLiteral("=")), IrItem(IrRuleRef("x"))), frozenset()
    )
    assert fields == {"x": IrBind(1, "model")}


def case_fields_quantified_literal_names_from_the_library(binding: ModuleType) -> None:
    """A quantified literal DOES bind, named by the literal table."""
    fields = binding.bind_fields(IrSequence(IrItem(IrLiteral("-"), OPT)), frozenset())
    assert fields == {"sign": IrBind(0, "text")}


def case_fields_collisions_get_numeric_suffixes(binding: ModuleType) -> None:
    """Repeated base names count up: ws, ws2."""
    ws = IrItem(IrRuleRef("ws"))
    fields = binding.bind_fields(
        IrSequence(ws, IrItem(IrLiteral(",")), ws), frozenset()
    )
    assert list(fields) == ["ws", "ws2"]


def case_fields_collisions_count_up_a_third_time(binding: ModuleType) -> None:
    """A third occurrence of the same base name continues the suffix run."""
    ws = IrItem(IrRuleRef("ws"))
    fields = binding.bind_fields(
        IrSequence(ws, IrItem(IrLiteral(",")), ws, IrItem(IrLiteral(";")), ws),
        frozenset(),
    )
    assert list(fields) == ["ws", "ws2", "ws3"]


def case_fields_non_semantic_ref_flags_the_bind(binding: ModuleType) -> None:
    """A ref to a noise rule binds with semantic=False."""
    fields = binding.bind_fields(IrSequence(IrItem(IrRuleRef("ws"))), frozenset({"ws"}))
    assert fields == {"ws": IrBind(0, "model", False)}


def case_fields_declaration_order_is_required_first(binding: ModuleType) -> None:
    """Optional fields (non-``models``, ``lo == 0``) sort after required ones,
    each group in item order, item slots untouched (defaults-last ruling)."""
    arm = IrSequence(
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
        IrItem(IrRuleRef("value")),
        IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)),
    )
    fields = binding.bind_fields(arm, frozenset({"ws"}))
    assert list(fields) == ["value", "ws", "ws2"]
    assert fields["value"] == IrBind(1, "model")
    assert fields["ws"] == IrBind(0, "model", False)
    assert fields["ws2"] == IrBind(2, "model", False)


def case_fields_models_mode_stays_required_ahead_of_optionals(
    binding: ModuleType,
) -> None:
    """A ``models`` field (star-quantified ref) is a required list — it keeps
    its place ahead of ``None``-defaulted fields even at ``lo == 0``."""
    arm = IrSequence(
        IrItem(IrLiteral("-"), OPT),
        IrItem(IrRuleRef("item"), STAR),
    )
    fields = binding.bind_fields(arm, frozenset())
    assert list(fields) == ["item", "sign"]
    assert fields["item"] == IrBind(1, "models")
    assert fields["sign"] == IrBind(0, "text")


def case_fields_unknown_atom_type_raises(binding: ModuleType) -> None:
    """The tier-2 table refuses an atom type it does not know.

    ``IrNot`` cannot occur in a canonical grammar (rewrite 4 eliminates it),
    so the binding tables deliberately omit it — the dispatch default must
    refuse it loudly rather than drop the field.
    """
    with pytest.raises(UnsupportedConstructError):
        binding.bind_fields(IrSequence(IrItem(IrNot(IrLiteral("a")))), frozenset())


# ── group naming ──────────────────────────────────────────────────────


def case_fields_ref_bearing_group_is_named_kind(binding: ModuleType) -> None:
    """A group containing rulerefs binds the structural slot name ``kind``."""
    group = IrAlternation(IrRuleRef("a"), IrRuleRef("b"))
    fields = binding.bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"kind": IrBind(0, "model")}


def case_fields_literal_group_named_from_first_atom(binding: ModuleType) -> None:
    """A literal-only group names itself from its first arm's first atom."""
    group = IrAlternation(IrSequence(IrItem(IrLiteral("+"))), IrLiteral("*"))
    fields = binding.bind_fields(IrSequence(IrItem(group, OPT)), frozenset())
    assert fields == {"sign": IrBind(0, "gtext")}


def case_fields_literal_group_named_from_charclass_slug_fallback(
    binding: ModuleType,
) -> None:
    """A literal-only group whose first atom is a non-library charclass names
    itself from the pattern slug (Tier-2 slug fallback, not the library)."""
    group = IrAlternation(IrSequence(IrItem(RANGE_AC)))
    fields = binding.bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"a_c": IrBind(0, "gtext")}


def case_fields_literal_group_with_unslugable_charclass_falls_to_tier3(
    binding: ModuleType,
) -> None:
    """A charclass whose pattern has no identifier-safe characters at all
    (its slug is empty) falls through the reserved "cc" hint to Tier-3."""
    group = IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("@")))))
    fields = binding.bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"head": IrBind(0, "gtext")}


# ── fold modes ────────────────────────────────────────────────────────


def case_mode_repeated_ref_is_models(binding: ModuleType) -> None:
    """hi > 1 (or unbounded) on a ref yields the list mode."""
    assert binding.mode_for(IrItem(IrRuleRef("x"), STAR)) == "models"


def case_mode_optional_ref_is_model(binding: ModuleType) -> None:
    """hi == 1 keeps the single-model mode even when optional."""
    assert binding.mode_for(IrItem(IrRuleRef("x"), OPT)) == "model"


def case_mode_bounded_multi_count_ref_is_models(binding: ModuleType) -> None:
    """A bounded count above one (2,5) also yields the list mode."""
    assert binding.mode_for(IrItem(IrRuleRef("x"), IrQuantifier(2, 5))) == "models"


def case_mode_unknown_atom_type_raises(binding: ModuleType) -> None:
    """The mode table refuses an atom type it does not know (IrNot cannot
    occur in a canonical grammar; the raising default keeps it loud)."""
    with pytest.raises(UnsupportedConstructError):
        binding.mode_for(IrItem(IrNot(IrLiteral("a"))))


def case_mode_ref_bearing_group_follows_quantifier(binding: ModuleType) -> None:
    """A ref-bearing group folds like a ref: model vs models by hi."""
    group = IrAlternation(IrRuleRef("a"))
    assert binding.mode_for(IrItem(group)) == "model"
    assert binding.mode_for(IrItem(group, STAR)) == "models"


def case_mode_all_unit_ref_group_is_model(binding: ModuleType) -> None:
    """Every arm a single unit ref → model (models when the group repeats)."""
    group = IrAlternation(IrRuleRef("a"), IrRuleRef("b"))
    assert binding.mode_for(IrItem(group)) == "model"
    assert binding.mode_for(IrItem(group, STAR)) == "models"


def case_mode_mixed_literal_ref_group_is_gtext(binding: ModuleType) -> None:
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
    assert binding.mode_for(IrItem(group)) == "gtext"


def case_mode_literal_only_group_is_gtext(binding: ModuleType) -> None:
    """A literal-only group folds as gtext (pinned existing behavior)."""
    group = IrAlternation(IrItem(IrLiteral("+")), IrItem(IrLiteral("-")))
    assert binding.mode_for(IrItem(group)) == "gtext"


# ── compute_binding over a small grammar ──────────────────────────────


def case_compute_binding_assigns_alternation_arm_parents(binding: ModuleType) -> None:
    """Rules named as unit-ref arms inherit the alternation's class."""
    by_name = {b.rule_name: b for b in binding.compute_binding(small_ast())}
    assert by_name["a"].parent_class_names == ("Choice",)
    assert by_name["b"].parent_class_names == ("Choice",)
    assert by_name["choice"].parent_class_names == ()


def case_compute_binding_orders_parents_before_subclasses(
    binding: ModuleType,
) -> None:
    """A binding never precedes the binding of any of its parent classes."""
    bindings = binding.compute_binding(small_ast())
    positions = {b.class_name: i for i, b in enumerate(bindings)}
    for one in bindings:
        for parent in one.parent_class_names:
            if parent in positions:
                assert positions[parent] < positions[one.class_name]


def case_compute_binding_starts_with_the_start_rule(binding: ModuleType) -> None:
    """The start rule (parentless here) leads the emission order."""
    assert binding.compute_binding(small_ast())[0].rule_name == "start"


# ── multi-membership arms (L1) ────────────────────────────────────────
#
# A rule that is a unit-ref arm of two or more alternations subclasses all of
# them (multiple inheritance). The single-parent last-writer-wins map silently
# dropped every parent but one, so a field typed with a "losing" alternation
# class rejected the instance at fold-ctor time.


def case_multi_membership_arm_lists_all_parents(binding: ModuleType) -> None:
    """A rule that is an arm of two alternations lists both parents."""
    by_name = {b.rule_name: b for b in binding.compute_binding(multi_membership_ast())}
    assert set(by_name["unquoted"].parent_class_names) == {"Value", "BareVal"}


def case_multi_membership_bases_ordered_most_derived_first(
    binding: ModuleType,
) -> None:
    """A base that subclasses another base precedes it (MRO-linearizable order).

    ``BareVal`` is itself an arm of ``Value`` (so ``BareVal`` subclasses
    ``Value``); Python's C3 linearization rejects ``(Value, BareVal)``, so the
    bases must be ordered ``(BareVal, Value)``.
    """
    by_name = {b.rule_name: b for b in binding.compute_binding(multi_membership_ast())}
    assert by_name["unquoted"].parent_class_names == ("BareVal", "Value")


# ── unit-arm cycles (L5) ──────────────────────────────────────────────
#
# A rule that is a unit-ref arm of itself, or rules that are unit-ref arms of
# each other, would emit self-/circularly-inheriting classes (`class S(S):`)
# and die at module exec. Cycle members all derive the same language, so the
# parent graph drops intra-cycle edges (members become siblings) and widens an
# edge to an outside member to that member's whole cycle — concrete arms then
# carry every member, keeping isinstance for fields typed with any of them.


def case_self_arm_drops_the_self_parent(binding: ModuleType) -> None:
    """The self unit arm contributes no parent edge; other arms keep theirs."""
    by_name = {b.rule_name: b for b in binding.compute_binding(self_arm_ast())}
    assert by_name["s"].parent_class_names == ()
    assert by_name["lit_a"].parent_class_names == ("S",)


def case_mutual_arm_cycle_members_become_siblings(binding: ModuleType) -> None:
    """Neither cycle member subclasses the other — the hierarchy loads."""
    by_name = {b.rule_name: b for b in binding.compute_binding(mutual_arm_ast())}
    assert by_name["a"].parent_class_names == ()
    assert by_name["b"].parent_class_names == ()


def case_mutual_arm_concrete_arms_carry_every_cycle_member(
    binding: ModuleType,
) -> None:
    """An arm of either member subclasses BOTH (the widened cross-cycle edge)."""
    by_name = {b.rule_name: b for b in binding.compute_binding(mutual_arm_ast())}
    assert by_name["x"].parent_class_names == ("A", "B")
    assert by_name["y"].parent_class_names == ("A", "B")


def case_cycle_member_keeps_its_outside_parent(binding: ModuleType) -> None:
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
    by_name = {b.rule_name: b for b in binding.compute_binding(ast)}
    assert by_name["a"].parent_class_names == ("Z",)
    assert by_name["b"].parent_class_names == ()
    assert by_name["x"].parent_class_names == ("A", "B")
    assert by_name["q"].parent_class_names == ("Z",)


# ── reserved names (L6) ───────────────────────────────────────────────


def case_class_name_mangles_keywords_and_header_bindings(
    binding: ModuleType,
) -> None:
    """Keywords and emitted-header names get the ``_`` suffix; others don't.

    The pydantic/typing-era reservations (``Annotated``, ``Optional``, …)
    were trimmed with the twin-module header (260718): ``annotated`` now
    unmangles; the emitted IR constructor names still mangle.
    """
    assert binding.class_name_for("true") == "True_"
    assert binding.class_name_for("annotated") == "Annotated"
    assert binding.class_name_for("literal") == "Literal_"
    assert binding.class_name_for("ir-rule") == "IrRule_"
    assert binding.class_name_for("grammar-model") == "GrammarModel_"
    assert binding.class_name_for("jp-char") == "JpChar"


def case_reserved_field_names_cover_grammar_model(binding: ModuleType) -> None:
    """Every public GrammarModel attribute is a reserved field name."""
    public = {n for n in dir(GrammarModel) if not n.startswith("_")}
    reserved = getattr(binding, "_RESERVED_FIELD_NAMES")
    assert public <= reserved


def case_bind_fields_mangles_reserved_names(binding: ModuleType) -> None:
    """Rule refs named after keywords or model attributes get a ``_`` suffix."""
    items = [
        IrItem(IrRuleRef("class")),
        IrItem(IrRuleRef("to-text")),
        IrItem(IrRuleRef("value")),
    ]
    fields = binding.bind_fields(items, frozenset())
    assert list(fields) == ["class_", "to_text_", "value"]


def case_multi_membership_parents_all_emitted_before_child(
    binding: ModuleType,
) -> None:
    """Every parent alternation is emitted before the multi-membership subclass."""
    bindings = binding.compute_binding(multi_membership_ast())
    positions = {b.class_name: i for i, b in enumerate(bindings)}
    for parent in bindings[
        next(i for i, b in enumerate(bindings) if b.rule_name == "unquoted")
    ].parent_class_names:
        assert positions[parent] < positions["Unquoted"]


def case_multi_membership_parent_order_is_deterministic(
    binding: ModuleType,
) -> None:
    """The parent tuple is stable across repeated bindings of the same grammar."""
    ast = multi_membership_ast()
    first = {b.rule_name: b.parent_class_names for b in binding.compute_binding(ast)}
    second = {b.rule_name: b.parent_class_names for b in binding.compute_binding(ast)}
    assert first == second


def case_compute_binding_flags_noise_fields_from_the_ast(
    binding: ModuleType,
) -> None:
    """ast.non_semantic drives the per-field semantic flag."""
    by_name = {b.rule_name: b for b in binding.compute_binding(small_ast())}
    assert by_name["start"].fields["ws"].semantic is False
    assert by_name["start"].fields["choice"].semantic is True


def case_compute_binding_alternation_and_value_str_have_no_fields(
    binding: ModuleType,
) -> None:
    """Only sequence-kind rules carry field bindings."""
    by_name = {b.rule_name: b for b in binding.compute_binding(small_ast())}
    assert by_name["choice"].fields == {}
    assert by_name["a"].fields == {}


CASES: dict[str, Callable[[ModuleType], None]] = {
    "test_charclass_names_keyed_by_canonical_normal_form": (
        case_charclass_names_keyed_by_canonical_normal_form
    ),
    "test_literal_names_table_content": case_literal_names_table_content,
    "test_class_name_pascalcases_hyphens_and_underscores": (
        case_class_name_pascalcases_hyphens_and_underscores
    ),
    "test_class_name_suffixes_python_keywords": (
        case_class_name_suffixes_python_keywords
    ),
    "test_classify_value_str_without_rulerefs": (
        case_classify_value_str_without_rulerefs
    ),
    "test_classify_alternation_needs_two_non_empty_arms": (
        case_classify_alternation_needs_two_non_empty_arms
    ),
    "test_classify_sequence_when_one_arm_is_empty": (
        case_classify_sequence_when_one_arm_is_empty
    ),
    "test_fields_tier1_ruleref_uses_rule_name_underscored": (
        case_fields_tier1_ruleref_uses_rule_name_underscored
    ),
    "test_fields_tier2_charclass_library_hit": (
        case_fields_tier2_charclass_library_hit
    ),
    "test_fields_tier3_positional_head_then_part_n": (
        case_fields_tier3_positional_head_then_part_n
    ),
    "test_fields_structural_literal_produces_no_field": (
        case_fields_structural_literal_produces_no_field
    ),
    "test_fields_quantified_literal_names_from_the_library": (
        case_fields_quantified_literal_names_from_the_library
    ),
    "test_fields_collisions_get_numeric_suffixes": (
        case_fields_collisions_get_numeric_suffixes
    ),
    "test_fields_collisions_count_up_a_third_time": (
        case_fields_collisions_count_up_a_third_time
    ),
    "test_fields_non_semantic_ref_flags_the_bind": (
        case_fields_non_semantic_ref_flags_the_bind
    ),
    "test_fields_unknown_atom_type_raises": case_fields_unknown_atom_type_raises,
    "test_fields_ref_bearing_group_is_named_kind": (
        case_fields_ref_bearing_group_is_named_kind
    ),
    "test_fields_literal_group_named_from_first_atom": (
        case_fields_literal_group_named_from_first_atom
    ),
    "test_fields_literal_group_named_from_charclass_slug_fallback": (
        case_fields_literal_group_named_from_charclass_slug_fallback
    ),
    "test_fields_literal_group_with_unslugable_charclass_falls_to_tier3": (
        case_fields_literal_group_with_unslugable_charclass_falls_to_tier3
    ),
    "test_mode_repeated_ref_is_models": case_mode_repeated_ref_is_models,
    "test_mode_optional_ref_is_model": case_mode_optional_ref_is_model,
    "test_mode_bounded_multi_count_ref_is_models": (
        case_mode_bounded_multi_count_ref_is_models
    ),
    "test_mode_unknown_atom_type_raises": case_mode_unknown_atom_type_raises,
    "test_mode_ref_bearing_group_follows_quantifier": (
        case_mode_ref_bearing_group_follows_quantifier
    ),
    "test_mode_all_unit_ref_group_is_model": case_mode_all_unit_ref_group_is_model,
    "test_mode_mixed_literal_ref_group_is_gtext": (
        case_mode_mixed_literal_ref_group_is_gtext
    ),
    "test_mode_literal_only_group_is_gtext": case_mode_literal_only_group_is_gtext,
    "test_compute_binding_assigns_alternation_arm_parents": (
        case_compute_binding_assigns_alternation_arm_parents
    ),
    "test_compute_binding_orders_parents_before_subclasses": (
        case_compute_binding_orders_parents_before_subclasses
    ),
    "test_compute_binding_starts_with_the_start_rule": (
        case_compute_binding_starts_with_the_start_rule
    ),
    "test_multi_membership_arm_lists_all_parents": (
        case_multi_membership_arm_lists_all_parents
    ),
    "test_multi_membership_bases_ordered_most_derived_first": (
        case_multi_membership_bases_ordered_most_derived_first
    ),
    "test_self_arm_drops_the_self_parent": case_self_arm_drops_the_self_parent,
    "test_mutual_arm_cycle_members_become_siblings": (
        case_mutual_arm_cycle_members_become_siblings
    ),
    "test_mutual_arm_concrete_arms_carry_every_cycle_member": (
        case_mutual_arm_concrete_arms_carry_every_cycle_member
    ),
    "test_cycle_member_keeps_its_outside_parent": (
        case_cycle_member_keeps_its_outside_parent
    ),
    "test_class_name_mangles_keywords_and_header_bindings": (
        case_class_name_mangles_keywords_and_header_bindings
    ),
    "test_reserved_field_names_cover_grammar_model": (
        case_reserved_field_names_cover_grammar_model
    ),
    "test_bind_fields_mangles_reserved_names": (
        case_bind_fields_mangles_reserved_names
    ),
    "test_multi_membership_parents_all_emitted_before_child": (
        case_multi_membership_parents_all_emitted_before_child
    ),
    "test_multi_membership_parent_order_is_deterministic": (
        case_multi_membership_parent_order_is_deterministic
    ),
    "test_compute_binding_flags_noise_fields_from_the_ast": (
        case_compute_binding_flags_noise_fields_from_the_ast
    ),
    "test_compute_binding_alternation_and_value_str_have_no_fields": (
        case_compute_binding_alternation_and_value_str_have_no_fields
    ),
}


def make_binding_tests(binding: ModuleType) -> dict[str, Callable[[], None]]:
    """Bind the shared binding-suite bodies to ``binding``.

    :param binding: ``lexic.compile.binding`` — the module under test.
    :returns: ``{test function name: zero-arg callable}``, ready for
        ``globals().update(...)`` in a mirror test module.
    """
    return {name: partial(case, binding) for name, case in CASES.items()}
