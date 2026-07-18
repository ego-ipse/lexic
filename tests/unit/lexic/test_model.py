"""Unit tests for src/lexic/base.py — the GrammarModel record spine.

Model classes here declare an explicit ``__binds__`` class table — the binds
channel runtime synthesis writes and the only channel the spine reads. A
``value_str`` class carries no binds (just an implicit ``value`` field).
"""

from __future__ import annotations

from typing import ClassVar, List, Optional

import pytest

from lexic.compile import compile_from_path, compile_text
from lexic.exceptions import FieldValidationError, UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import IrNone, IrTuple
from lexic.ir.bind import IrBind
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.model import GrammarModel
from tests.paths import GROUND_TRUTH

LOWER = IrCharClass(IrRange(IrChr("a"), IrChr("z")))


def ws_rule() -> IrRule:
    """ws ::= [ \\t\\n]* — a value_str rule (implicit value field, no binds)."""
    return IrRule(
        "ws",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrCharClass(IrChr(" "), IrChr("\t"), IrChr("\n")),
                    IrQuantifier(0, IrNone),
                )
            )
        ),
    )


class Ws(GrammarModel):
    """Whitespace model — value_str shape."""

    __grammar__: ClassVar[IrRule] = ws_rule()
    value: str


def ident_rule() -> IrRule:
    """ident ::= [a-z] ws — one text field, one model field."""
    return IrRule(
        "ident",
        IrAlternation(IrSequence(IrItem(LOWER), IrItem(IrRuleRef("ws")))),
    )


class Ident(GrammarModel):
    """Identifier model — a text field and a nested model field."""

    __grammar__: ClassVar[IrRule] = ident_rule()
    first: str
    ws: Ws
    __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
        0: ("first", IrBind(0, "text")),
        1: ("ws", IrBind(1, "model")),
    }


class NoisyIdent(GrammarModel):
    """Identifier model whose ws bind is structural noise (semantic=False)."""

    __grammar__: ClassVar[IrRule] = ident_rule()
    first: str
    ws: Ws
    __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
        0: ("first", IrBind(0, "text")),
        1: ("ws", IrBind(1, "model", False)),
    }


class It(GrammarModel):
    """Item model — value_str shape over a repeated char class."""

    __grammar__: ClassVar[IrRule] = IrRule(
        "it", IrAlternation(IrSequence(IrItem(LOWER, IrQuantifier(1, IrNone))))
    )
    value: str


class Root(GrammarModel):
    """Root model — one models-mode list field."""

    __grammar__: ClassVar[IrRule] = IrRule(
        "root",
        IrAlternation(IrSequence(IrItem(IrRuleRef("it"), IrQuantifier(1, IrNone)))),
    )
    it: List[It]
    __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
        0: ("it", IrBind(0, "models")),
    }


# ── value_str ─────────────────────────────────────────────────────────────────


def test_to_text_value_str():
    """to_text() emits the raw value for value_str classes."""
    assert Ws(value="  ").to_text() == "  "
    assert Ws(value="").to_text() == ""
    assert Ws(value="\n\t").to_text() == "\n\t"


# ── sequence with literal (literal baked in) ──────────────────────────────────


def test_to_text_sequence_emits_literal():
    """to_text() concatenates unbound literal items between field values."""

    class EqExpr(GrammarModel):
        """Equality expression."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "eq-expr",
            IrAlternation(
                IrSequence(
                    IrItem(LOWER),
                    IrItem(IrLiteral("=")),
                    IrItem(IrCharClass(IrRange(IrChr("0"), IrChr("9")))),
                )
            ),
        )
        __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
            0: ("first", IrBind(0, "text")),
            2: ("second", IrBind(2, "text")),
        }
        first: str
        second: str

    assert EqExpr(first="x", second="1").to_text() == "x=1"


# ── sequence with nested GrammarModel ─────────────────────────────────────────


def test_to_text_nested_grammar_model():
    """Nested GrammarModel fields are emitted recursively."""
    inst = Ident(first="x", ws=Ws(value=" "))
    assert inst.to_text() == "x "


# ── sequence with List field ──────────────────────────────────────────────────


def test_to_text_list_of_grammar_model():
    """models-mode fields emit each element in order (list or tuple storage)."""
    inst = Root(it=[It(value="a"), It(value="b"), It(value="c")])
    assert inst.to_text() == "abc"


# ── Optional field absent ─────────────────────────────────────────────────────


def test_to_text_optional_absent():
    """Optional-typed fields that are None are omitted from output."""

    class R(GrammarModel):
        """R model with optional whitespace."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "r",
            IrAlternation(
                IrSequence(IrItem(LOWER), IrItem(IrRuleRef("ws"), IrQuantifier(0, 1)))
            ),
        )
        __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
            0: ("first", IrBind(0, "text")),
            1: ("ws", IrBind(1, "model")),
        }
        first: str
        ws: Optional[Ws] = None

    assert R(first="x", ws=None).to_text() == "x"
    assert R(first="x", ws=Ws(value=" ")).to_text() == "x "


# ── alternation (abstract) raises ─────────────────────────────────────────────


def test_to_text_alternation_raises():
    """Calling to_text() on an abstract alternation class raises NotImplementedError."""

    class Base(GrammarModel):
        """Abstract base model."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "base",
            IrAlternation(
                IrSequence(IrItem(IrRuleRef("a"))),
                IrSequence(IrItem(IrRuleRef("b"))),
            ),
        )

    with pytest.raises(NotImplementedError):
        Base().to_text()


# ── empty alternate arm ───────────────────────────────────────────────────────


def test_to_text_empty_arm_all_fields_absent_is_empty():
    """A rule with an empty alternate arm emits '' when every field is None."""

    class Pair(GrammarModel):
        """pair ::= "<" x ">" | — all fields Optional."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "pair",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("<")),
                    IrItem(IrRuleRef("ws")),
                    IrItem(IrLiteral(">")),
                ),
                IrSequence(),
            ),
        )
        __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
            1: ("ws", IrBind(1, "model")),
        }
        ws: Optional[Ws] = None

    assert Pair().to_text() == ""
    assert Pair(ws=Ws(value=" ")).to_text() == "< >"


# ── semantic_dump excludes ws fields ─────────────────────────────────────────


def test_semantic_dump_excludes_ws():
    """semantic_dump() omits fields whose bind carries semantic=False."""
    inst = NoisyIdent(first="x", ws=Ws(value=" "))
    d = inst.semantic_dump()
    assert "first" in d
    assert "ws" not in d


# ── bound_fields ──────────────────────────────────────────────────────────────


def test_bound_fields_maps_item_slot_to_name_and_bind():
    """bound_fields() maps each bound item slot to its (field name, bind)."""
    bound = NoisyIdent.bound_fields()
    assert set(bound) == {0, 1}
    name0, bind0 = bound[0]
    assert name0 == "first"
    assert bind0.item == 0
    name1, bind1 = bound[1]
    assert name1 == "ws"
    assert bind1.semantic is False


def test_bound_fields_empty_for_value_str_class():
    """A value_str class (no IrBind fields) has an empty bound_fields() map."""
    assert not Ws.bound_fields()


def test_bound_fields_is_a_classmethod_not_instance_dependent():
    """bound_fields() reads class-level metadata, callable on the class."""
    inst = Ident(first="x", ws=Ws(value=" "))
    assert inst.bound_fields() == Ident.bound_fields()


def test_bound_fields_explicit_binds_table_wins():
    """A class-declared __binds__ is used as-is — no annotation resolution."""

    class Declared(GrammarModel):
        """Model with an explicit binds table beside unannotated fields."""

        __grammar__: ClassVar[IrRule] = ident_rule()
        __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
            0: ("first", IrBind(0, "text")),
        }
        first: str
        ws: Optional[Ws] = None

    assert set(Declared.bound_fields()) == {0}


# ── equality / hashing (settled 4) ────────────────────────────────────────────


class PairA(GrammarModel):
    """a ::= "x" — single-field value_str shape, for cross-class eq tests."""

    __grammar__: ClassVar[IrRule] = IrRule(
        "a", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    )
    value: str


class PairB(GrammarModel):
    """b ::= "x" — identical shape to PairA, distinct class."""

    __grammar__: ClassVar[IrRule] = IrRule(
        "b", IrAlternation(IrSequence(IrItem(IrLiteral("x"))))
    )
    value: str


def test_same_class_equal_payload_compares_equal():
    """Two instances of the same class with equal fields compare equal."""
    assert PairA(value="x") == PairA(value="x")


def test_cross_class_equal_payload_compares_unequal():
    """Type-aware equality: distinct classes never compare equal (settled 4;
    plain tuple equality would say A('x') == B('x'))."""
    assert PairA(value="x") != PairB(value="x")


def test_hash_is_consistent_with_equality():
    """Equal models hash equal; models are usable as dict/set keys."""
    one, two = PairA(value="x"), PairA(value="x")
    assert hash(one) == hash(two)
    assert len({one, two}) == 1


# ── list→tuple ctor coercion (settled 11) ─────────────────────────────────────


def test_ctor_coerces_models_lists_to_tuples():
    """A live list handed by the fold/PDA is stored as a tuple."""
    inst = Root(it=[It(value="a"), It(value="b")])
    assert isinstance(inst.it, tuple)


def test_ctor_coerces_positional_lists_too():
    """The coercion applies to positional construction as well."""
    inst = Root([It(value="a")])
    assert isinstance(inst.it, tuple)


def test_coerced_models_field_keeps_hashability():
    """A model holding a coerced models field is hashable."""
    inst = Root(it=[It(value="a")])
    assert hash(inst) == hash(Root(it=[It(value="a")]))


# ── the tuple surface (ruling 9, accepted) ────────────────────────────────────


def test_models_are_tuples():
    """A model IS its field tuple: iterable, sized, indexable."""
    inst = Ident(first="x", ws=Ws(value=" "))
    assert isinstance(inst, tuple)
    assert len(inst) == 2
    assert inst[0] == "x"
    assert inst.first is inst[0]


# ── children / rebuild / _child_attrs (settled 13) ───────────────────────────


def test_children_are_bound_field_values_in_item_order():
    """children() yields the bound fields' values, in item-slot order."""
    ws = Ws(value=" ")
    inst = Ident(first="x", ws=ws)
    kids = inst.children()
    assert kids == ("x", ws)
    assert kids[1] is ws


def test_children_follow_item_order_not_declaration_order():
    """children() follows the binds table's ITEM order (settled 13), even
    when field declaration order differs from item-slot order."""

    class Swapped(GrammarModel):
        """Fields declared in the reverse of their item-slot order."""

        __grammar__: ClassVar[IrRule] = ident_rule()
        __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
            0: ("first", IrBind(0, "text")),
            1: ("ws", IrBind(1, "model")),
        }
        ws: Optional[Ws] = None
        first: str = ""

    inst = Swapped(ws=Ws(value=" "), first="x")
    assert inst.children() == ("x", Ws(value=" "))


def test_value_str_class_has_no_children():
    """A value_str class has no binds, hence no IR children."""
    assert not Ws(value=" ").children()


def test_rebuild_splices_bound_fields_in_item_order():
    """rebuild() replaces the bound fields with new children, keeping type."""
    inst = Ident(first="x", ws=Ws(value=" "))
    donor = Ident(first="y", ws=Ws(value="\t"))
    rebuilt = inst.rebuild(donor.children())
    assert type(rebuilt) is type(inst)
    assert rebuilt.first == "y"
    assert rebuilt.ws == Ws(value="\t")


def test_rebuild_of_children_is_identity_shaped():
    """rebuild(children()) reproduces an equal model."""
    inst = Ident(first="x", ws=Ws(value=" "))
    assert inst.rebuild(inst.children()) == inst


# ── dispatch admission (settled 13): models reach IrTuple catch-alls ─────────


def test_ir_type_map_irtuple_entry_admits_models():
    """An IrTypeMap's IrTuple entry resolves for a model instance (MRO) —
    the emit actions' IrAction(IrTuple, ...) catch-all is reachable by
    models, as intended dispatch openness."""
    marker = IrLiteral("caught")
    table = IrTypeMap(IrAction(IrTuple, marker))
    assert table.resolve(Ident(first="x", ws=Ws(value=" "))) is marker


# ── native dump ───────────────────────────────────────────────────────────────


def test_dump_is_field_ordered_and_runtime_complete():
    """dump() emits every field in declaration order, nested models
    as dicts, models-mode tuples as lists."""
    inst = Root(it=[It(value="a"), It(value="b")])
    assert inst.dump() == {"it": [{"value": "a"}, {"value": "b"}]}
    assert list(Ident(first="x", ws=Ws(value=" ")).dump()) == ["first", "ws"]


def test_dump_reemits_tuples_as_lists():
    """The dump's models-mode value is a plain list (in-process dump parity)."""
    dumped = Root(it=[It(value="a")]).dump()
    assert isinstance(dumped["it"], list)


# ── to_grammar ────────────────────────────────────────────────────────────────


def test_to_grammar_returns_string_no_trailing_newline():
    """to_grammar() returns a string with no trailing newline."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    result = inst.to_grammar()
    assert isinstance(result, str)
    assert not result.endswith("\n")


def test_to_grammar_default_flavour_is_gbnf():
    """Default flavour for to_grammar() is gbnf."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    assert inst.to_grammar() == inst.to_grammar("gbnf")


def test_to_grammar_contains_rule_name():
    """to_grammar() output contains the rule name."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    result = inst.to_grammar()
    assert str(inst.__grammar__.name) in result


def test_to_grammar_unknown_flavour_raises():
    """Unknown flavour raises UnsupportedConstructError."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    with pytest.raises(UnsupportedConstructError):
        inst.to_grammar("xyz_unknown_flavour")


def _wide_root_instance():
    """A compiled instance whose start rule's own body is wide enough to
    overflow width 88 flat — ten long rule-ref items in one sequence."""
    names = [f"item-name-number-{i:02d}" for i in range(10)]
    text = "root ::= " + " ".join(names) + "\n"
    for name in names:
        text += f'{name} ::= "{name}"\n'
    cg = compile_text(text)
    return cg.parse("".join(names))


def test_to_grammar_width_none_is_flat_single_line():
    """to_grammar(width=None) renders the rule flat — no line breaks."""
    inst = _wide_root_instance()
    result = inst.to_grammar(width=None)
    assert "\n" not in result
    assert not result.endswith("\n")


def test_to_grammar_default_width_wraps_a_long_rule():
    """to_grammar()'s default width (88) wraps a rule too wide to fit flat."""
    inst = _wide_root_instance()
    result = inst.to_grammar()
    assert "\n" in result
    assert not result.endswith("\n")


def test_to_grammar_wrapped_and_flat_differ():
    """The wrapped and flat renderings of the same wide rule are not equal."""
    inst = _wide_root_instance()
    assert inst.to_grammar() != inst.to_grammar(width=None)


# ── fast_construct licence (trivially granted on the spine) ───────────────────


def test_fast_construct_is_always_granted():
    """Every record class earns the licence — there is no validation to skip."""
    ctor, defaults = Ident.fast_construct()
    assert callable(ctor)
    assert not defaults


def test_fast_construct_reports_field_defaults():
    """The licence's defaults dict carries the class's optional defaults."""

    class WithDefault(GrammarModel):
        """Model with a None-defaulted optional field."""

        __grammar__: ClassVar[IrRule] = ident_rule()
        __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
            0: ("first", IrBind(0, "text")),
            1: ("ws", IrBind(1, "model")),
        }
        first: str
        ws: Optional[Ws] = None

    _ctor, defaults = WithDefault.fast_construct()
    assert defaults == {"ws": None}


# ── _from_parts equivalence ────────────────────────────────────────────────


def test_from_parts_equivalent_to_the_keyword_constructor():
    """_from_parts built via the licence matches the keyword constructor's
    dump()/semantic_dump()/equality/to_text()."""
    validated = Ident(first="x", ws=Ws(value=" "))
    ctor, defaults = Ident.fast_construct()
    parts = dict(defaults)
    parts.update(first="x", ws=Ws(value=" "))
    fast = ctor(parts, {"first", "ws"})

    assert fast == validated
    assert fast.dump() == validated.dump()
    assert fast.semantic_dump() == validated.semantic_dump()
    assert fast.to_text() == validated.to_text()


def test_from_parts_fills_defaults_for_unset_optional_fields():
    """_from_parts, seeded from fast_construct's defaults, matches the
    keyword constructor when an optional field is left unset."""

    class Eq(GrammarModel):
        """Model with an optional field left at its default."""

        __grammar__: ClassVar[IrRule] = ident_rule()
        __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
            0: ("first", IrBind(0, "text")),
            1: ("ws", IrBind(1, "model")),
        }
        first: str
        ws: Optional[Ws] = None

    validated = Eq(first="x")
    ctor, defaults = Eq.fast_construct()
    parts = dict(defaults)
    parts.update(first="x")
    fast = ctor(parts, {"first"})

    assert fast == validated
    assert fast.dump() == validated.dump()


def test_from_parts_coerces_models_lists():
    """The fast build coerces a live models-mode list exactly like __new__."""
    ctor, defaults = Root.fast_construct()
    parts = dict(defaults)
    parts["it"] = [It(value="a")]
    fast = ctor(parts, {"it"})
    assert isinstance(fast, Root)
    assert isinstance(fast.it, tuple)
    assert fast == Root(it=[It(value="a")])


# ── checked construction ────────────────────────────────────────────────────


def test_missing_required_field_raises_field_validation_error():
    """A missing required field raises FieldValidationError — checked
    construction rewires the record build's interim TypeError."""
    with pytest.raises(FieldValidationError):
        Ident(first="x")  # type: ignore[reportCallIssue]  # intentional misuse under test


def op_rule() -> IrRule:
    """op ::= "+" | "-" — a multi-arm pure-literal value_str rule."""
    return IrRule(
        "op",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("+"))),
            IrSequence(IrItem(IrLiteral("-"))),
        ),
    )


class Op(GrammarModel):
    """Multi-arm literal value_str model — Literal[...]-checked."""

    __grammar__: ClassVar[IrRule] = op_rule()
    value: str


def repeated_eq_rule() -> IrRule:
    """req ::= "="+ — a bound (quantified) literal field."""
    return IrRule(
        "req",
        IrAlternation(IrSequence(IrItem(IrLiteral("="), IrQuantifier(1, IrNone)))),
    )


class RepeatedEq(GrammarModel):
    """Model whose bound field's atom is a quantified IrLiteral (R7 hole)."""

    __grammar__: ClassVar[IrRule] = repeated_eq_rule()
    __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
        0: ("eqs", IrBind(0, "text")),
    }
    eqs: str


def gtext_rule() -> IrRule:
    """gtxt ::= ("a" | "b") — literal-only inline group, gtext mode."""
    return IrRule(
        "gtxt",
        IrAlternation(
            IrSequence(
                IrItem(
                    IrAlternation(
                        IrSequence(IrItem(IrLiteral("a"))),
                        IrSequence(IrItem(IrLiteral("b"))),
                    )
                )
            )
        ),
    )


class GtextGroup(GrammarModel):
    """Model with a literal-only inline group bound in gtext mode (R7 hole)."""

    __grammar__: ClassVar[IrRule] = gtext_rule()
    __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
        0: ("group", IrBind(0, "gtext")),
    }
    group: str


def group_model_rule() -> IrRule:
    """grp ::= (ident) — ref-bearing inline group, model mode."""
    return IrRule(
        "grp",
        IrAlternation(
            IrSequence(IrItem(IrAlternation(IrSequence(IrItem(IrRuleRef("ident"))))))
        ),
    )


class GroupModel(GrammarModel):
    """Model with a ref-bearing inline group bound in model mode."""

    __grammar__: ClassVar[IrRule] = group_model_rule()
    __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
        0: ("group", IrBind(0, "model")),
    }
    group: Ident


# charclass field ────────────────────────────────────────────────────────────


def test_charclass_field_all_covered_chars_constructs():
    """Every char within the class and length within the item's quantifier
    constructs cleanly."""
    inst = Ident(first="x", ws=Ws(value=" "))
    assert inst.first == "x"


def test_charclass_field_out_of_class_char_raises():
    """A char outside the class raises FieldValidationError naming the char
    and the pattern."""
    with pytest.raises(FieldValidationError, match="is not in"):
        Ident(first="1", ws=Ws(value=" "))


def test_charclass_field_length_too_long_raises():
    """A value longer than the item's quantifier bounds raises
    FieldValidationError ('length ... out of bounds')."""
    with pytest.raises(FieldValidationError, match="out of bounds"):
        Ident(first="ab", ws=Ws(value=" "))


def test_charclass_field_length_too_short_raises():
    """A value shorter than a bound char-class field's quantifier lower
    bound raises FieldValidationError ('length ... out of bounds'). ``It``
    itself is a value_str class (no bind), so this needs its own bound
    fixture rather than reusing ``It``."""

    class Repeated(GrammarModel):
        """rep ::= [a-z]{2,} — bound char-class field, min length 2."""

        __grammar__: ClassVar[IrRule] = IrRule(
            "rep",
            IrAlternation(IrSequence(IrItem(LOWER, IrQuantifier(2, IrNone)))),
        )
        __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
            0: ("chars", IrBind(0, "text")),
        }
        chars: str

    with pytest.raises(FieldValidationError, match="out of bounds"):
        Repeated(chars="a")


def test_charclass_field_non_str_value_raises():
    """A non-str value on a char-class field raises FieldValidationError."""
    with pytest.raises(FieldValidationError, match="expected a str"):
        Ident(
            first=123,  # type: ignore[reportArgumentType]  # intentional misuse under test
            ws=Ws(value=" "),
        )


# bound literal field — R7 hole ───────────────────────────────────────────────


def test_bound_literal_field_wrong_value_does_not_raise():
    """A bound (quantified) literal field is the R7 hole: plain str, never
    validated — an unrelated value still constructs."""
    inst = RepeatedEq(eqs="totally-wrong-value")
    assert inst.eqs == "totally-wrong-value"


# model ref field ──────────────────────────────────────────────────────────────


def test_model_field_submodel_value_constructs():
    """A real sub-model instance on a model-mode field constructs cleanly."""
    ws = Ws(value=" ")
    inst = Ident(first="x", ws=ws)
    assert inst.ws is ws


def test_model_field_non_model_value_raises():
    """A non-model value on a model-mode field raises FieldValidationError."""
    with pytest.raises(FieldValidationError, match="expected a sub-model"):
        Ident(
            first="x",
            ws="not a model",  # type: ignore[reportArgumentType]  # intentional misuse under test
        )


# models field ─────────────────────────────────────────────────────────────────


def test_models_field_list_of_submodels_constructs():
    """A list of sub-models on a models-mode field constructs, coerced to a
    tuple."""
    inst = Root(it=[It(value="a"), It(value="b")])
    assert inst.it == (It(value="a"), It(value="b"))


def test_models_field_non_list_scalar_raises():
    """A non-list/tuple scalar on a models-mode field raises
    FieldValidationError."""
    with pytest.raises(FieldValidationError, match="expected a list of sub-models"):
        Root(it="not-a-list")  # type: ignore[reportArgumentType]  # intentional misuse under test


def test_models_field_element_non_model_raises():
    """A list containing a non-model element raises FieldValidationError."""
    bad: list = [It(value="a"), "bad"]
    with pytest.raises(FieldValidationError, match="expected a sub-model"):
        Root(it=bad)  # type: ignore[reportArgumentType]  # intentional misuse under test


# inline-group field ───────────────────────────────────────────────────────────


def test_group_model_field_submodel_value_constructs():
    """A ref-bearing inline group bound in model mode checks like a ref."""
    ident = Ident(first="x", ws=Ws(value=" "))
    inst = GroupModel(group=ident)
    assert inst.group is ident


def test_group_model_field_non_model_value_raises():
    """A ref-bearing inline group bound in model mode rejects a non-model."""
    with pytest.raises(FieldValidationError, match="expected a sub-model"):
        GroupModel(
            group="not a model"  # type: ignore[reportArgumentType]  # intentional misuse under test
        )


def test_gtext_group_field_wrong_value_does_not_raise():
    """A literal-only inline group bound in gtext mode is an R7 hole: plain
    str, never validated."""
    inst = GtextGroup(group="totally-wrong-value")
    assert inst.group == "totally-wrong-value"


# value_str Literal[...] ─────────────────────────────────────────────────────


def test_value_str_literal_arm_value_constructs():
    """A value within the multi-arm literal set constructs."""
    assert Op(value="+").value == "+"


def test_value_str_literal_out_of_arm_value_raises():
    """A value outside the multi-arm literal set raises FieldValidationError."""
    with pytest.raises(FieldValidationError, match="is not one of"):
        Op(value="*")


def test_value_str_single_arm_charclass_is_not_checked():
    """Narrowing: a single-arm char-class value_str is NOT checked via the
    value_str path (the check is bind-driven and value_str carries no bind) —
    an out-of-class value still constructs."""
    inst = It(value="ZZZ!!!")
    assert inst.value == "ZZZ!!!"


# required-presence ────────────────────────────────────────────────────────────


def test_all_required_fields_provided_constructs():
    """All required fields provided constructs cleanly."""
    inst = Root(it=[It(value="a")])
    assert inst.it == (It(value="a"),)


def test_optional_field_omitted_constructs():
    """An optional (defaulted) field left unset does not trip presence
    checking."""

    class WithOptional(GrammarModel):
        """Model with a defaulted optional ws field."""

        __grammar__: ClassVar[IrRule] = ident_rule()
        __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {
            0: ("first", IrBind(0, "text")),
            1: ("ws", IrBind(1, "model")),
        }
        first: str
        ws: Optional[Ws] = None

    inst = WithOptional(first="x")
    assert inst.ws is None


def test_required_field_omitted_raises_on_another_fixture():
    """A missing required field raises FieldValidationError on a models-mode
    fixture too (beyond the base Ident pin)."""
    with pytest.raises(FieldValidationError, match="missing required field"):
        Root()  # type: ignore[reportCallIssue]  # intentional misuse under test


def test_unexpected_field_raises_type_error_not_field_validation_error():
    """A genuine unexpected-fields misuse still surfaces as TypeError — the
    checked-construction rewire targets missing fields only, not extras."""
    with pytest.raises(TypeError):
        Ident(
            first="x",
            ws=Ws(value=" "),
            bogus="nope",  # type: ignore[reportCallIssue]  # intentional misuse under test
        )


# parse-path bypass ────────────────────────────────────────────────────────────


def test_parse_path_output_reconstructs_via_checked_construction():
    """Valid parser output passes every check with no false rejection: a
    parsed model reconstructed via checked kwargs construction is equal to
    the original."""
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    model = cg.parse("x=1\n")
    rebuilt = type(model)(**{name: getattr(model, name) for name in model._fields})
    assert rebuilt == model
