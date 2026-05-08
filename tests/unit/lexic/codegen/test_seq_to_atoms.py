from lexic.codegen.seq_to_atoms import seq_to_atoms
from lexic.grammars.gbnf.ast import (
    Alternation,
    CharClass,
    Group,
    Item,
    Literal,
    RuleRef,
    Sequence,
)
from lexic.ir import (
    CharClassAtom,
    InlineAlternationAtom,
    InlineRegexAtom,
    LiteralAtom,
    QuantifiedLiteralAtom,
    RuleRefAtom,
)
from lexic.ir.helpers import HelperRuleRegistry


def _item(atom, q=None):
    return Item(atom=atom, quantifier=q)


def _seq(*items):
    return Sequence(items=list(items))


def test_literal_and_ruleref_passthrough():
    seq = _seq(_item(Literal(value="=")), _item(RuleRef(name="expr")))
    atoms = seq_to_atoms(seq, "Root", HelperRuleRegistry(), {"expr": "Expr"}, {})
    assert atoms == [
        LiteralAtom(value="="),
        RuleRefAtom(rule_name="expr", min=1, max=1),
    ]


def test_quantified_literal_becomes_quantified_literal_atom():
    seq = _seq(_item(Literal(value="-"), q="?"))
    atoms = seq_to_atoms(seq, "Root", HelperRuleRegistry(), {}, {})
    assert atoms == [QuantifiedLiteralAtom(value="-", min=0, max=1)]


def test_charclass_with_quantifier():
    seq = _seq(_item(CharClass(pattern="[0-9]"), q="+"))
    atoms = seq_to_atoms(seq, "Root", HelperRuleRegistry(), {}, {})
    assert atoms == [CharClassAtom(pattern="[0-9]", min=1, max=None)]


def test_inline_literal_alternation_becomes_inline_regex():
    inner = Alternation(
        seqs=[_seq(_item(Literal(value="true"))), _seq(_item(Literal(value="false")))]
    )
    seq = _seq(_item(Group(alt=inner)))
    atoms = seq_to_atoms(seq, "Root", HelperRuleRegistry(), {}, {})
    assert len(atoms) == 1
    assert isinstance(atoms[0], InlineRegexAtom)


def test_inline_named_alternation_becomes_inline_alt():
    inner = Alternation(
        seqs=[_seq(_item(RuleRef(name="pawn"))), _seq(_item(RuleRef(name="king")))]
    )
    seq = _seq(_item(Group(alt=inner)))
    atoms = seq_to_atoms(
        seq, "Move", HelperRuleRegistry(), {"pawn": "Pawn", "king": "King"}, {}
    )
    assert atoms == [InlineAlternationAtom(arm_rule_names=["pawn", "king"])]


def test_single_arm_unquantified_group_inlines_contents():
    inner = Alternation(
        seqs=[_seq(_item(Literal(value="x")), _item(RuleRef(name="expr")))]
    )
    seq = _seq(_item(Group(alt=inner)))
    atoms = seq_to_atoms(seq, "Root", HelperRuleRegistry(), {"expr": "Expr"}, {})
    assert atoms == [
        LiteralAtom(value="x"),
        RuleRefAtom(rule_name="expr", min=1, max=1),
    ]


def test_quantified_group_creates_helper_ruleref():
    inner = Alternation(
        seqs=[_seq(_item(Literal(value="a")), _item(RuleRef(name="expr")))]
    )
    seq = _seq(_item(Group(alt=inner), q="*"))
    helpers = HelperRuleRegistry()
    atoms = seq_to_atoms(seq, "Root", helpers, {"expr": "Expr"}, {})
    assert len(atoms) == 1
    assert isinstance(atoms[0], RuleRefAtom)
    assert atoms[0].rule_name == "root-item"
    assert atoms[0].min == 0
    assert atoms[0].max is None
    assert [s.rule_name for s in helpers.all_specs()] == ["root-item"]


def test_quantified_group_dedup_across_calls():
    inner = Alternation(
        seqs=[_seq(_item(Literal(value="a")), _item(RuleRef(name="expr")))]
    )
    seq1 = _seq(_item(Group(alt=inner), q="*"))
    seq2 = _seq(_item(Group(alt=inner), q="+"))
    helpers = HelperRuleRegistry()
    seq_to_atoms(seq1, "Root", helpers, {"expr": "Expr"}, {})
    seq_to_atoms(seq2, "Root", helpers, {"expr": "Expr"}, {})
    assert [s.rule_name for s in helpers.all_specs()] == ["root-item", "root-item2"]
