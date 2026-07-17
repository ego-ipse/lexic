"""Shared test bodies for the codegen/compile ``binding`` mirrors.

``lexic.codegen.binding`` and ``lexic.compile.binding`` are byte-identical
modules (``compile.binding`` supersedes ``codegen.binding`` — see
``zzz_current_work/260716-ir-native/PLAN_v4.md`` Task 2; codegen stays until
a later task deletes it). Maintaining two verbatim copies of the same test
suite trips pylint's whole-tree duplicate-code check (R0801), so the actual
test bodies live here ONCE as module-level functions taking the module under
test as their sole parameter. ``tests/unit/lexic/codegen/test_binding.py``
and ``tests/unit/lexic/compile/test_binding.py`` each import their own
target module and call :func:`make_binding_tests` to populate their globals
— two real, independently collected test modules, one source of truth for
the bodies. ``CANONICAL_IMPORTS`` (from ``lexic.codegen.model_emitter``) and
``GrammarModel`` are the same for both mirrors and stay module-level
constants here, unparameterized.
"""

from __future__ import annotations

import ast as pyast
from functools import partial
from types import ModuleType
from typing import Callable

import pytest

from lexic.base import GrammarModel
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

# The record spine's inherited IrSelf/tuple protocol surface (R2-4). Task 3
# re-pinned `lexic.compile.binding`'s `_RESERVED_FIELD_NAMES` to the full
# GrammarModel surface, so these eight names are now reserved there and the
# window is CLOSED (`public <= _RESERVED_FIELD_NAMES`). The read-only
# `lexic.codegen.binding` mirror still keeps the pre-Task-3 `dir(BaseModel)`
# set (its Task-8 deletion retires it), so the eight names stay unreserved
# there — the codegen branch below still pins the window exactly, so any
# FURTHER surface drift still fails.
_SPINE_PROTOCOL_NAMES = frozenset(
    {"bind", "bound", "bound_type", "children", "count", "eval", "index", "rebuild"}
)


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


def _chain_rules(depth: int) -> list[IrRule]:
    """r0 → r1 → … → r<depth>, each a unit-ref wrapper, leaf a literal."""
    rules = [
        IrRule(f"r{i}", IrSequence(IrItem(IrRuleRef(f"r{i + 1}"))))
        for i in range(depth)
    ]
    rules.append(IrRule(f"r{depth}", IrSequence(IrItem(IrLiteral("0")))))
    return rules


# ── naming lookup tables (re-homed from ir/naming.py) ─────────────────


def _case_charclass_names_keyed_by_canonical_normal_form(binding: ModuleType) -> None:
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


def _case_literal_names_table_content(binding: ModuleType) -> None:
    """The literal library still maps the punctuation set to stable field names."""
    assert binding.LITERAL_NAMES["-"] == "sign"
    assert binding.LITERAL_NAMES["+"] == "sign"
    assert binding.LITERAL_NAMES["."] == "dot"
    assert binding.LITERAL_NAMES[","] == "comma"
    assert binding.LITERAL_NAMES["="] == "eq"


# ── class naming ──────────────────────────────────────────────────────


def _case_class_name_pascalcases_hyphens_and_underscores(binding: ModuleType) -> None:
    """Both canonical hyphens and legacy underscores split words."""
    assert binding.class_name_for("jp-char") == "JpChar"
    assert binding.class_name_for("json_ws") == "JsonWs"


def _case_class_name_suffixes_python_keywords(binding: ModuleType) -> None:
    """A rule named after a keyword still yields a legal class name."""
    assert binding.class_name_for("true") == "True_"


# ── kind classification ───────────────────────────────────────────────


def _case_classify_value_str_without_rulerefs(binding: ModuleType) -> None:
    """A body with no IrRuleRef anywhere is value_str, even multi-arm."""
    rule = IrRule("v", IrAlternation(IrLiteral("a"), IrLiteral("b")))
    assert binding.classify_rule(rule) == "value_str"


def _case_classify_alternation_needs_two_non_empty_arms(binding: ModuleType) -> None:
    """Multiple ref-bearing arms classify as alternation."""
    rule = IrRule("a", IrAlternation(IrRuleRef("x"), IrRuleRef("y")))
    assert binding.classify_rule(rule) == "alternation"


def _case_classify_sequence_when_one_arm_is_empty(binding: ModuleType) -> None:
    """An empty alternate arm does not promote a sequence to alternation."""
    rule = IrRule("s", IrAlternation(IrSequence(IrItem(IrRuleRef("x"))), IrSequence()))
    assert binding.classify_rule(rule) == "sequence"


# ── field naming cascade ──────────────────────────────────────────────


def _case_fields_tier1_ruleref_uses_rule_name_underscored(binding: ModuleType) -> None:
    """A ref field is named after its rule, hyphens to underscores."""
    fields = binding.bind_fields(IrSequence(IrItem(IrRuleRef("jp-char"))), frozenset())
    assert fields == {"jp_char": IrBind(0, "model")}


def _case_fields_tier2_charclass_library_hit(binding: ModuleType) -> None:
    """[0-9] hits the pattern library as ``digit``."""
    fields = binding.bind_fields(IrSequence(IrItem(_DIGIT, _STAR)), frozenset())
    assert fields == {"digit": IrBind(0, "text")}


def _case_fields_tier3_positional_head_then_part_n(binding: ModuleType) -> None:
    """Unmatched pattern fields fall through to head / part_2."""
    novel = IrCharClass(IrChr("!"), IrChr("?"))
    fields = binding.bind_fields(
        IrSequence(IrItem(novel, _STAR), IrItem(novel, _STAR)), frozenset()
    )
    assert list(fields) == ["head", "part_2"]


def _case_fields_structural_literal_produces_no_field(binding: ModuleType) -> None:
    """A unit-quantified literal is matched text, never a field."""
    fields = binding.bind_fields(
        IrSequence(IrItem(IrLiteral("=")), IrItem(IrRuleRef("x"))), frozenset()
    )
    assert fields == {"x": IrBind(1, "model")}


def _case_fields_quantified_literal_names_from_the_library(binding: ModuleType) -> None:
    """A quantified literal DOES bind, named by the literal table."""
    fields = binding.bind_fields(IrSequence(IrItem(IrLiteral("-"), _OPT)), frozenset())
    assert fields == {"sign": IrBind(0, "text")}


def _case_fields_collisions_get_numeric_suffixes(binding: ModuleType) -> None:
    """Repeated base names count up: ws, ws2."""
    ws = IrItem(IrRuleRef("ws"))
    fields = binding.bind_fields(
        IrSequence(ws, IrItem(IrLiteral(",")), ws), frozenset()
    )
    assert list(fields) == ["ws", "ws2"]


def _case_fields_collisions_count_up_a_third_time(binding: ModuleType) -> None:
    """A third occurrence of the same base name continues the suffix run."""
    ws = IrItem(IrRuleRef("ws"))
    fields = binding.bind_fields(
        IrSequence(ws, IrItem(IrLiteral(",")), ws, IrItem(IrLiteral(";")), ws),
        frozenset(),
    )
    assert list(fields) == ["ws", "ws2", "ws3"]


def _case_fields_non_semantic_ref_flags_the_bind(binding: ModuleType) -> None:
    """A ref to a noise rule binds with semantic=False."""
    fields = binding.bind_fields(IrSequence(IrItem(IrRuleRef("ws"))), frozenset({"ws"}))
    assert fields == {"ws": IrBind(0, "model", False)}


def _case_fields_unknown_atom_type_raises(binding: ModuleType) -> None:
    """The tier-2 table refuses an atom type it does not know.

    ``IrNot`` cannot occur in a canonical grammar (rewrite 4 eliminates it),
    so the binding tables deliberately omit it — the dispatch default must
    refuse it loudly rather than drop the field.
    """
    with pytest.raises(UnsupportedConstructError):
        binding.bind_fields(IrSequence(IrItem(IrNot(IrLiteral("a")))), frozenset())


# ── group naming ──────────────────────────────────────────────────────


def _case_fields_ref_bearing_group_is_named_kind(binding: ModuleType) -> None:
    """A group containing rulerefs binds the structural slot name ``kind``."""
    group = IrAlternation(IrRuleRef("a"), IrRuleRef("b"))
    fields = binding.bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"kind": IrBind(0, "model")}


def _case_fields_literal_group_named_from_first_atom(binding: ModuleType) -> None:
    """A literal-only group names itself from its first arm's first atom."""
    group = IrAlternation(IrSequence(IrItem(IrLiteral("+"))), IrLiteral("*"))
    fields = binding.bind_fields(IrSequence(IrItem(group, _OPT)), frozenset())
    assert fields == {"sign": IrBind(0, "gtext")}


def _case_fields_literal_group_named_from_charclass_slug_fallback(
    binding: ModuleType,
) -> None:
    """A literal-only group whose first atom is a non-library charclass names
    itself from the pattern slug (Tier-2 slug fallback, not the library)."""
    group = IrAlternation(IrSequence(IrItem(_RANGE_AC)))
    fields = binding.bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"a_c": IrBind(0, "gtext")}


def _case_fields_literal_group_with_unslugable_charclass_falls_to_tier3(
    binding: ModuleType,
) -> None:
    """A charclass whose pattern has no identifier-safe characters at all
    (its slug is empty) falls through the reserved "cc" hint to Tier-3."""
    group = IrAlternation(IrSequence(IrItem(IrCharClass(IrChr("@")))))
    fields = binding.bind_fields(IrSequence(IrItem(group)), frozenset())
    assert fields == {"head": IrBind(0, "gtext")}


# ── fold modes ────────────────────────────────────────────────────────


def _case_mode_repeated_ref_is_models(binding: ModuleType) -> None:
    """hi > 1 (or unbounded) on a ref yields the list mode."""
    assert binding.mode_for(IrItem(IrRuleRef("x"), _STAR)) == "models"


def _case_mode_optional_ref_is_model(binding: ModuleType) -> None:
    """hi == 1 keeps the single-model mode even when optional."""
    assert binding.mode_for(IrItem(IrRuleRef("x"), _OPT)) == "model"


def _case_mode_bounded_multi_count_ref_is_models(binding: ModuleType) -> None:
    """A bounded count above one (2,5) also yields the list mode."""
    assert binding.mode_for(IrItem(IrRuleRef("x"), IrQuantifier(2, 5))) == "models"


def _case_mode_unknown_atom_type_raises(binding: ModuleType) -> None:
    """The mode table refuses an atom type it does not know (IrNot cannot
    occur in a canonical grammar; the raising default keeps it loud)."""
    with pytest.raises(UnsupportedConstructError):
        binding.mode_for(IrItem(IrNot(IrLiteral("a"))))


def _case_mode_ref_bearing_group_follows_quantifier(binding: ModuleType) -> None:
    """A ref-bearing group folds like a ref: model vs models by hi."""
    group = IrAlternation(IrRuleRef("a"))
    assert binding.mode_for(IrItem(group)) == "model"
    assert binding.mode_for(IrItem(group, _STAR)) == "models"


def _case_mode_all_unit_ref_group_is_model(binding: ModuleType) -> None:
    """Every arm a single unit ref → model (models when the group repeats)."""
    group = IrAlternation(IrRuleRef("a"), IrRuleRef("b"))
    assert binding.mode_for(IrItem(group)) == "model"
    assert binding.mode_for(IrItem(group, _STAR)) == "models"


def _case_mode_mixed_literal_ref_group_is_gtext(binding: ModuleType) -> None:
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


def _case_mode_literal_only_group_is_gtext(binding: ModuleType) -> None:
    """A literal-only group folds as gtext (pinned existing behavior)."""
    group = IrAlternation(IrItem(IrLiteral("+")), IrItem(IrLiteral("-")))
    assert binding.mode_for(IrItem(group)) == "gtext"


# ── compute_binding over a small grammar ──────────────────────────────


def _case_compute_binding_assigns_alternation_arm_parents(binding: ModuleType) -> None:
    """Rules named as unit-ref arms inherit the alternation's class."""
    by_name = {b.rule_name: b for b in binding.compute_binding(_small_ast())}
    assert by_name["a"].parent_class_names == ("Choice",)
    assert by_name["b"].parent_class_names == ("Choice",)
    assert by_name["choice"].parent_class_names == ()


def _case_compute_binding_orders_parents_before_subclasses(
    binding: ModuleType,
) -> None:
    """A binding never precedes the binding of any of its parent classes."""
    bindings = binding.compute_binding(_small_ast())
    positions = {b.class_name: i for i, b in enumerate(bindings)}
    for one in bindings:
        for parent in one.parent_class_names:
            if parent in positions:
                assert positions[parent] < positions[one.class_name]


def _case_compute_binding_starts_with_the_start_rule(binding: ModuleType) -> None:
    """The start rule (parentless here) leads the emission order."""
    assert binding.compute_binding(_small_ast())[0].rule_name == "start"


# ── multi-membership arms (L1) ────────────────────────────────────────
#
# A rule that is a unit-ref arm of two or more alternations subclasses all of
# them (multiple inheritance). The single-parent last-writer-wins map silently
# dropped every parent but one, so a field typed with a "losing" alternation
# class rejected the instance at fold-ctor time.


def _case_multi_membership_arm_lists_all_parents(binding: ModuleType) -> None:
    """A rule that is an arm of two alternations lists both parents."""
    by_name = {b.rule_name: b for b in binding.compute_binding(_multi_membership_ast())}
    assert set(by_name["unquoted"].parent_class_names) == {"Value", "BareVal"}


def _case_multi_membership_bases_ordered_most_derived_first(
    binding: ModuleType,
) -> None:
    """A base that subclasses another base precedes it (MRO-linearizable order).

    ``BareVal`` is itself an arm of ``Value`` (so ``BareVal`` subclasses
    ``Value``); Python's C3 linearization rejects ``(Value, BareVal)``, so the
    bases must be ordered ``(BareVal, Value)``.
    """
    by_name = {b.rule_name: b for b in binding.compute_binding(_multi_membership_ast())}
    assert by_name["unquoted"].parent_class_names == ("BareVal", "Value")


# ── unit-arm cycles (L5) ──────────────────────────────────────────────
#
# A rule that is a unit-ref arm of itself, or rules that are unit-ref arms of
# each other, would emit self-/circularly-inheriting classes (`class S(S):`)
# and die at module exec. Cycle members all derive the same language, so the
# parent graph drops intra-cycle edges (members become siblings) and widens an
# edge to an outside member to that member's whole cycle — concrete arms then
# carry every member, keeping isinstance for fields typed with any of them.


def _case_self_arm_drops_the_self_parent(binding: ModuleType) -> None:
    """The self unit arm contributes no parent edge; other arms keep theirs."""
    by_name = {b.rule_name: b for b in binding.compute_binding(_self_arm_ast())}
    assert by_name["s"].parent_class_names == ()
    assert by_name["lit_a"].parent_class_names == ("S",)


def _case_mutual_arm_cycle_members_become_siblings(binding: ModuleType) -> None:
    """Neither cycle member subclasses the other — the hierarchy loads."""
    by_name = {b.rule_name: b for b in binding.compute_binding(_mutual_arm_ast())}
    assert by_name["a"].parent_class_names == ()
    assert by_name["b"].parent_class_names == ()


def _case_mutual_arm_concrete_arms_carry_every_cycle_member(
    binding: ModuleType,
) -> None:
    """An arm of either member subclasses BOTH (the widened cross-cycle edge)."""
    by_name = {b.rule_name: b for b in binding.compute_binding(_mutual_arm_ast())}
    assert by_name["x"].parent_class_names == ("A", "B")
    assert by_name["y"].parent_class_names == ("A", "B")


def _case_cycle_member_keeps_its_outside_parent(binding: ModuleType) -> None:
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


def _case_class_name_mangles_keywords_and_header_bindings(
    binding: ModuleType,
) -> None:
    """Keywords and emitted-header names get the ``_`` suffix; others don't."""
    assert binding.class_name_for("true") == "True_"
    assert binding.class_name_for("annotated") == "Annotated_"
    assert binding.class_name_for("grammar-model") == "GrammarModel_"
    assert binding.class_name_for("jp-char") == "JpChar"


def _case_reserved_class_names_cover_the_emitted_header(binding: ModuleType) -> None:
    """Every name the emitter's header binds is in the reserved-class set."""
    bound = {
        alias.asname or alias.name
        for node in pyast.walk(pyast.parse(CANONICAL_IMPORTS))
        if isinstance(node, pyast.ImportFrom)
        for alias in node.names
    }
    # ``annotations`` (the __future__ import) can never PascalCase-collide.
    assert bound - {"annotations"} <= getattr(binding, "_RESERVED_CLASS_NAMES")


def _case_reserved_field_names_cover_grammar_model(binding: ModuleType) -> None:
    """Every public GrammarModel attribute is reserved (compile: window closed;
    codegen: the eight spine names stay in the pre-Task-3 window)."""
    public = {n for n in dir(GrammarModel) if not n.startswith("_")}
    reserved = getattr(binding, "_RESERVED_FIELD_NAMES")
    if binding.__name__.startswith("lexic.compile"):
        assert public <= reserved
    else:
        # codegen.binding is read-only until its Task-8 deletion; its
        # dir(BaseModel) set leaves the eight spine-protocol names unreserved.
        assert public - _SPINE_PROTOCOL_NAMES <= reserved
        assert public & _SPINE_PROTOCOL_NAMES == _SPINE_PROTOCOL_NAMES


def _case_bind_fields_mangles_reserved_names(binding: ModuleType) -> None:
    """Rule refs named after keywords or model attributes get a ``_`` suffix."""
    items = [
        IrItem(IrRuleRef("class")),
        IrItem(IrRuleRef("to-text")),
        IrItem(IrRuleRef("value")),
    ]
    fields = binding.bind_fields(items, frozenset())
    assert list(fields) == ["class_", "to_text_", "value"]


def _case_multi_membership_parents_all_emitted_before_child(
    binding: ModuleType,
) -> None:
    """Every parent alternation is emitted before the multi-membership subclass."""
    bindings = binding.compute_binding(_multi_membership_ast())
    positions = {b.class_name: i for i, b in enumerate(bindings)}
    for parent in bindings[
        next(i for i, b in enumerate(bindings) if b.rule_name == "unquoted")
    ].parent_class_names:
        assert positions[parent] < positions["Unquoted"]


def _case_multi_membership_parent_order_is_deterministic(
    binding: ModuleType,
) -> None:
    """The parent tuple is stable across repeated bindings of the same grammar."""
    ast = _multi_membership_ast()
    first = {b.rule_name: b.parent_class_names for b in binding.compute_binding(ast)}
    second = {b.rule_name: b.parent_class_names for b in binding.compute_binding(ast)}
    assert first == second


def _case_compute_binding_flags_noise_fields_from_the_ast(
    binding: ModuleType,
) -> None:
    """ast.non_semantic drives the per-field semantic flag."""
    by_name = {b.rule_name: b for b in binding.compute_binding(_small_ast())}
    assert by_name["start"].fields["ws"].semantic is False
    assert by_name["start"].fields["choice"].semantic is True


def _case_compute_binding_alternation_and_value_str_have_no_fields(
    binding: ModuleType,
) -> None:
    """Only sequence-kind rules carry field bindings."""
    by_name = {b.rule_name: b for b in binding.compute_binding(_small_ast())}
    assert by_name["choice"].fields == {}
    assert by_name["a"].fields == {}


# ── schema expansion joints (deep ref chains) ─────────────────────────


def _case_schema_depths_count_acyclic_chains(binding: ModuleType) -> None:
    """Depth is the inlined-schema nesting: leaf 1, each referrer +1."""
    edges = {"a": ["b"], "b": ["c"], "c": []}
    assert getattr(binding, "_schema_depths")(edges) == {"a": 3, "b": 2, "c": 1}


def _case_schema_depths_cycle_edges_add_no_depth(binding: ModuleType) -> None:
    """Cycle members keep depth from OUTSIDE refs only (pydantic def-refs)."""
    edges = {"v": ["a", "leaf"], "a": ["v"], "leaf": []}
    depths = getattr(binding, "_schema_depths")(edges)
    assert depths["leaf"] == 1
    assert depths["v"] == 2  # leaf inlines; the v↔a cycle edge does not
    assert depths["a"] == 1  # a's only ref is intra-cycle — def-ref'd, shallow


def _case_schema_joints_flag_every_stride_multiple(binding: ModuleType) -> None:
    """A chain longer than one stride gets a joint at each stride multiple."""
    stride = getattr(binding, "_SCHEMA_JOINT_STRIDE")
    depth = 2 * stride + 10
    joints = getattr(binding, "_schema_joints")(_chain_rules(depth))
    assert len(joints) == 2
    depths_of_joints = {depth + 1 - int(name[1:]) for name in joints}
    assert depths_of_joints == {stride, 2 * stride}


def _case_shallow_grammars_get_no_joints(binding: ModuleType) -> None:
    """Every grammar under one stride deep is untouched (all ground truths)."""
    assert not getattr(binding, "_schema_joints")(_chain_rules(30))
    bindings = binding.compute_binding(_multi_membership_ast())
    assert not any(b.schema_joint for b in bindings)


def _case_compute_binding_threads_joint_flags(binding: ModuleType) -> None:
    """RuleBinding.schema_joint mirrors the joint set."""
    depth = getattr(binding, "_SCHEMA_JOINT_STRIDE") + 5
    rules = _chain_rules(depth)
    ast = IrAst(IrSeq(*rules), "r0")
    flagged = {b.rule_name for b in binding.compute_binding(ast) if b.schema_joint}
    assert len(flagged) == 1


_CASES: dict[str, Callable[[ModuleType], None]] = {
    "test_charclass_names_keyed_by_canonical_normal_form": (
        _case_charclass_names_keyed_by_canonical_normal_form
    ),
    "test_literal_names_table_content": _case_literal_names_table_content,
    "test_class_name_pascalcases_hyphens_and_underscores": (
        _case_class_name_pascalcases_hyphens_and_underscores
    ),
    "test_class_name_suffixes_python_keywords": (
        _case_class_name_suffixes_python_keywords
    ),
    "test_classify_value_str_without_rulerefs": (
        _case_classify_value_str_without_rulerefs
    ),
    "test_classify_alternation_needs_two_non_empty_arms": (
        _case_classify_alternation_needs_two_non_empty_arms
    ),
    "test_classify_sequence_when_one_arm_is_empty": (
        _case_classify_sequence_when_one_arm_is_empty
    ),
    "test_fields_tier1_ruleref_uses_rule_name_underscored": (
        _case_fields_tier1_ruleref_uses_rule_name_underscored
    ),
    "test_fields_tier2_charclass_library_hit": (
        _case_fields_tier2_charclass_library_hit
    ),
    "test_fields_tier3_positional_head_then_part_n": (
        _case_fields_tier3_positional_head_then_part_n
    ),
    "test_fields_structural_literal_produces_no_field": (
        _case_fields_structural_literal_produces_no_field
    ),
    "test_fields_quantified_literal_names_from_the_library": (
        _case_fields_quantified_literal_names_from_the_library
    ),
    "test_fields_collisions_get_numeric_suffixes": (
        _case_fields_collisions_get_numeric_suffixes
    ),
    "test_fields_collisions_count_up_a_third_time": (
        _case_fields_collisions_count_up_a_third_time
    ),
    "test_fields_non_semantic_ref_flags_the_bind": (
        _case_fields_non_semantic_ref_flags_the_bind
    ),
    "test_fields_unknown_atom_type_raises": _case_fields_unknown_atom_type_raises,
    "test_fields_ref_bearing_group_is_named_kind": (
        _case_fields_ref_bearing_group_is_named_kind
    ),
    "test_fields_literal_group_named_from_first_atom": (
        _case_fields_literal_group_named_from_first_atom
    ),
    "test_fields_literal_group_named_from_charclass_slug_fallback": (
        _case_fields_literal_group_named_from_charclass_slug_fallback
    ),
    "test_fields_literal_group_with_unslugable_charclass_falls_to_tier3": (
        _case_fields_literal_group_with_unslugable_charclass_falls_to_tier3
    ),
    "test_mode_repeated_ref_is_models": _case_mode_repeated_ref_is_models,
    "test_mode_optional_ref_is_model": _case_mode_optional_ref_is_model,
    "test_mode_bounded_multi_count_ref_is_models": (
        _case_mode_bounded_multi_count_ref_is_models
    ),
    "test_mode_unknown_atom_type_raises": _case_mode_unknown_atom_type_raises,
    "test_mode_ref_bearing_group_follows_quantifier": (
        _case_mode_ref_bearing_group_follows_quantifier
    ),
    "test_mode_all_unit_ref_group_is_model": _case_mode_all_unit_ref_group_is_model,
    "test_mode_mixed_literal_ref_group_is_gtext": (
        _case_mode_mixed_literal_ref_group_is_gtext
    ),
    "test_mode_literal_only_group_is_gtext": _case_mode_literal_only_group_is_gtext,
    "test_compute_binding_assigns_alternation_arm_parents": (
        _case_compute_binding_assigns_alternation_arm_parents
    ),
    "test_compute_binding_orders_parents_before_subclasses": (
        _case_compute_binding_orders_parents_before_subclasses
    ),
    "test_compute_binding_starts_with_the_start_rule": (
        _case_compute_binding_starts_with_the_start_rule
    ),
    "test_multi_membership_arm_lists_all_parents": (
        _case_multi_membership_arm_lists_all_parents
    ),
    "test_multi_membership_bases_ordered_most_derived_first": (
        _case_multi_membership_bases_ordered_most_derived_first
    ),
    "test_self_arm_drops_the_self_parent": _case_self_arm_drops_the_self_parent,
    "test_mutual_arm_cycle_members_become_siblings": (
        _case_mutual_arm_cycle_members_become_siblings
    ),
    "test_mutual_arm_concrete_arms_carry_every_cycle_member": (
        _case_mutual_arm_concrete_arms_carry_every_cycle_member
    ),
    "test_cycle_member_keeps_its_outside_parent": (
        _case_cycle_member_keeps_its_outside_parent
    ),
    "test_class_name_mangles_keywords_and_header_bindings": (
        _case_class_name_mangles_keywords_and_header_bindings
    ),
    "test_reserved_class_names_cover_the_emitted_header": (
        _case_reserved_class_names_cover_the_emitted_header
    ),
    "test_reserved_field_names_cover_grammar_model": (
        _case_reserved_field_names_cover_grammar_model
    ),
    "test_bind_fields_mangles_reserved_names": (
        _case_bind_fields_mangles_reserved_names
    ),
    "test_multi_membership_parents_all_emitted_before_child": (
        _case_multi_membership_parents_all_emitted_before_child
    ),
    "test_multi_membership_parent_order_is_deterministic": (
        _case_multi_membership_parent_order_is_deterministic
    ),
    "test_compute_binding_flags_noise_fields_from_the_ast": (
        _case_compute_binding_flags_noise_fields_from_the_ast
    ),
    "test_compute_binding_alternation_and_value_str_have_no_fields": (
        _case_compute_binding_alternation_and_value_str_have_no_fields
    ),
    "test_schema_depths_count_acyclic_chains": (
        _case_schema_depths_count_acyclic_chains
    ),
    "test_schema_depths_cycle_edges_add_no_depth": (
        _case_schema_depths_cycle_edges_add_no_depth
    ),
    "test_schema_joints_flag_every_stride_multiple": (
        _case_schema_joints_flag_every_stride_multiple
    ),
    "test_shallow_grammars_get_no_joints": _case_shallow_grammars_get_no_joints,
    "test_compute_binding_threads_joint_flags": (
        _case_compute_binding_threads_joint_flags
    ),
}


def make_binding_tests(binding: ModuleType) -> dict[str, Callable[[], None]]:
    """Bind the shared binding-suite bodies to ``binding``.

    :param binding: ``lexic.codegen.binding`` or ``lexic.compile.binding`` —
        the module under test.
    :returns: ``{test function name: zero-arg callable}``, ready for
        ``globals().update(...)`` in a mirror test module.
    """
    return {name: partial(case, binding) for name, case in _CASES.items()}
