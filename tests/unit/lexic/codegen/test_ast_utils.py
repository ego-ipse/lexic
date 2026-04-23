from lexic.grammars.gbnf.ast import (
    Alternation,
    Group,
    Item,
    Literal,
    RuleRef,
    Sequence,
)
from lexic.codegen.ast_utils import (
    is_ws_item,
    single_ruleref_of,
    strip_ws,
    unwrap_group_alt,
)


def _item(atom, q=None):
    return Item(atom=atom, quantifier=q)


def test_strip_ws_drops_ws_rulerefs():
    seq = Sequence(
        items=[
            _item(Literal(value="a")),
            _item(RuleRef(name="ws")),
            _item(Literal(value="b")),
        ]
    )
    assert [it.atom for it in strip_ws(seq).items] == [
        Literal(value="a"),
        Literal(value="b"),
    ]


def test_is_ws_item_true_only_for_ws_ruleref():
    assert is_ws_item(_item(RuleRef(name="ws"))) is True
    assert is_ws_item(_item(RuleRef(name="other"))) is False
    assert is_ws_item(_item(Literal(value="ws"))) is False


def test_single_ruleref_direct():
    seq = Sequence(items=[_item(RuleRef(name="expr"))])
    assert single_ruleref_of(seq) == "expr"


def test_single_ruleref_through_group():
    inner = Alternation(seqs=[Sequence(items=[_item(RuleRef(name="inner"))])])
    seq = Sequence(items=[_item(Group(alt=inner))])
    assert single_ruleref_of(seq) == "inner"


def test_single_ruleref_rejects_quantified():
    seq = Sequence(items=[_item(RuleRef(name="expr"), q="+")])
    assert single_ruleref_of(seq) is None


def test_unwrap_group_alt_peels_single_arm_wrapper():
    inner = Alternation(
        seqs=[
            Sequence(items=[_item(Literal(value="a"))]),
            Sequence(items=[_item(Literal(value="b"))]),
        ]
    )
    outer = Alternation(seqs=[Sequence(items=[_item(Group(alt=inner))])])
    assert unwrap_group_alt(outer) is inner


def test_unwrap_group_alt_passes_through_multi_arm():
    alt = Alternation(
        seqs=[
            Sequence(items=[_item(Literal(value="a"))]),
            Sequence(items=[_item(Literal(value="b"))]),
        ]
    )
    assert unwrap_group_alt(alt) is alt
