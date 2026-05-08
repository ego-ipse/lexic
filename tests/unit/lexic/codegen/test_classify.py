from lexic.codegen.classify import (
    Classifier,
    NamedAlt,
    PureLiteralAlt,
    SequenceKind,
    ValueStr,
)
from lexic.grammars.gbnf.ast import (
    Alternation,
    CharClass,
    Group,
    Item,
    Literal,
    Rule,
    RuleRef,
    Sequence,
)


def _rule(name: str, body: Alternation) -> Rule:
    return Rule(name=name, body=body)


def _seq(*items: Item) -> Sequence:
    return Sequence(items=list(items))


def _alt(*seqs: Sequence) -> Alternation:
    return Alternation(seqs=list(seqs))


def _lit(v: str, q: str | None = None) -> Item:
    return Item(atom=Literal(value=v), quantifier=q)


def _cc(pat: str, q: str | None = None) -> Item:
    return Item(atom=CharClass(pattern=pat), quantifier=q)


def _ref(name: str, q: str | None = None) -> Item:
    return Item(atom=RuleRef(name=name), quantifier=q)


def test_pure_literal_alternation_carries_alt():
    body = _alt(_seq(_lit("+")), _seq(_lit("-")), _seq(_lit("*")))
    result = Classifier().classify(_rule("op", body))
    assert isinstance(result, PureLiteralAlt)
    assert len(result.alt.seqs) == 3


def test_named_alternation_returns_stripped_arm_sequences():
    body = _alt(_seq(_ref("a")), _seq(_ref("b")), _seq(_ref("c")))
    result = Classifier().classify(_rule("u", body))
    assert isinstance(result, NamedAlt)
    assert len(result.arms) == 3
    assert all(len(a.items) > 0 for a in result.arms)


def test_sequence_returns_non_stripped_first_arm():
    body = _alt(_seq(_ref("expr"), _lit("="), _ref("expr")))
    result = Classifier().classify(_rule("assign", body))
    assert isinstance(result, SequenceKind)
    assert result.body.items == body.seqs[0].items


def test_value_str_single_arm_carries_unwrapped_alt():
    body = _alt(_seq(_cc("[0-9]", "+")))
    result = Classifier().classify(_rule("num", body))
    assert isinstance(result, ValueStr)
    assert len(result.alt.seqs) == 1


def test_structurally_complex_returns_value_str():
    inner = _alt(_seq(_lit("a")), _seq(_lit("b")))
    body = _alt(_seq(Item(atom=Group(alt=inner), quantifier=None)))
    result = Classifier().classify(_rule("choice", body))
    assert isinstance(result, ValueStr)
    assert result.alt is not None


def test_empty_arms_returns_value_str():
    body = _alt()
    result = Classifier().classify(_rule("empty", body))
    assert isinstance(result, ValueStr)
    assert result.alt is not None
