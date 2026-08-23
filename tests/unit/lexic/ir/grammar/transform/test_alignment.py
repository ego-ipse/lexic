"""Tests for lexic.ir.grammar.transform.alignment: equality up to renaming."""

from __future__ import annotations

import pytest

from lexic.compile import parse_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import (
    CANDIDATE_CAP,
    IrAlignment,
    IrAst,
    IrLiteral,
    IrMap,
    IrRename,
    IrRenaming,
    IrRenamings,
    IrStr,
    IrTuple,
    align_names,
    canonicalize,
)

PAIR = 'root ::= head tail\nhead ::= "a"\ntail ::= "b"\n'
RENAMED_PAIR = 'start ::= first second\nfirst ::= "a"\nsecond ::= "b"\n'
REORDERED = 'root ::= tail head\nhead ::= "a"\ntail ::= "b"\n'
TWINS = 'root ::= "x"\nalpha ::= "y"\nbeta ::= "y"\n'


def grammar(text: str) -> IrAst:
    """Parse a GBNF source into its AST."""
    return parse_grammar(text, GBNF_FLAVOUR)


def table(alignment: IrAlignment, at: int = 0) -> dict[str, str]:
    """One of the alignment's bijections, as a plain name table."""
    return dict(alignment.renamings[at])


# ── the answer ────────────────────────────────────────────────────────


def test_a_pure_rename_aligns_with_the_bijection_as_witness() -> None:
    """Renaming every rule changes nothing the alignment can see."""
    alignment = align_names(grammar(PAIR), grammar(RENAMED_PAIR))
    assert len(alignment.renamings) == 1
    assert table(alignment) == {"root": "start", "head": "first", "tail": "second"}
    assert not alignment.capped


def test_a_grammar_aligns_with_itself_by_the_identity() -> None:
    """The reflexive case, and the bijection says so."""
    alignment = align_names(grammar(PAIR), grammar(PAIR))
    assert [table(alignment)] == [{"root": "root", "head": "head", "tail": "tail"}]


def test_a_different_factoring_refuses() -> None:
    """Structure the renaming cannot reach: no bijection, empty alignment."""
    reshaped = grammar('root ::= head\nhead ::= "a" "b"\ntail ::= "b"\n')
    assert align_names(grammar(PAIR), reshaped).renamings == IrRenamings()


def test_a_reordered_body_refuses() -> None:
    """Two refs swapped in a sequence is a different grammar, not a rename."""
    assert len(align_names(grammar(PAIR), grammar(REORDERED)).renamings) == 0


def test_a_different_rule_count_refuses() -> None:
    """No bijection exists between sets of different size."""
    assert len(align_names(grammar(PAIR), grammar('root ::= "a"\n')).renamings) == 0


def test_rule_order_is_not_a_difference() -> None:
    """A renaming may reorder the canonical rule list; the rule SET decides."""
    tail_first = 'root ::= head tail\ntail ::= "b"\nhead ::= "a"\n'
    assert len(align_names(grammar(PAIR), grammar(tail_first)).renamings) == 1


def test_the_start_rule_must_map_to_the_start_rule() -> None:
    """Two grammars with one rule set but different starts do not align."""
    left = grammar('root ::= alt\nalt ::= "a"\n')
    right = canonicalize(left)
    restarted = IrAst(right.rules, "alt")
    assert len(align_names(left, restarted).renamings) == 0


# ── ambiguity is offered, never picked ────────────────────────────────


def test_identical_bodies_yield_every_alignment() -> None:
    """Two interchangeable rules admit two bijections, and both come back."""
    alignment = align_names(grammar(TWINS), grammar(TWINS))
    assert len(alignment.renamings) == 2
    assert [dict(renaming) for renaming in alignment.renamings] == [
        {"alpha": "alpha", "beta": "beta", "root": "root"},
        {"alpha": "beta", "beta": "alpha", "root": "root"},
    ]


def test_every_offered_alignment_really_aligns() -> None:
    """Offered means valid — each bijection carries one grammar onto the other.

    Re-canonicalised after the move, because a renaming may reorder the rule
    list (the swap sends the last rule to the second-last slot) and the rule
    SET is what alignment is about.
    """
    left, right = grammar(TWINS), grammar(TWINS)
    canonical = canonicalize(right)
    for renaming in align_names(left, right).renamings:
        assert canonicalize(renaming.renamed(canonicalize(left))) == canonical


def test_the_cap_is_a_drawn_fact() -> None:
    """More bijections than the cap admits: the product says so, not less."""
    many = 'root ::= "x"\n' + "".join(f'r{i} ::= "y"\n' for i in range(6))
    alignment = align_names(grammar(many), grammar(many))
    assert alignment.capped
    assert len(alignment.renamings) == CANDIDATE_CAP


def test_an_uncapped_alignment_says_so() -> None:
    """The honest negative: nothing was left unexamined."""
    assert not align_names(grammar(PAIR), grammar(RENAMED_PAIR)).capped


# ── the witness as transport ──────────────────────────────────────────


def test_a_renaming_is_its_pairs() -> None:
    """A spine record read as a table — ``dict`` of it, no accessor."""
    renaming = IrRenaming(IrRename("a", "b"), IrRename("c", "d"))
    assert dict(renaming) == {"a": "b", "c": "d"}


def test_renamed_carries_a_grammar_across() -> None:
    """The transport: the source grammar, re-keyed by the witness."""
    alignment = align_names(grammar(PAIR), grammar(RENAMED_PAIR))
    moved = alignment.renamings[0].renamed(canonicalize(grammar(PAIR)))
    assert [str(rule.name) for rule in moved.rules] == ["start", "first", "second"]
    assert str(moved.start) == "start"


def test_renamed_leaves_an_unmentioned_name_alone() -> None:
    """A partial table is applied as given — no invented targets."""
    moved = IrRenaming(IrRename("head", "first")).renamed(canonicalize(grammar(PAIR)))
    assert [str(rule.name) for rule in moved.rules] == ["root", "first", "tail"]


def test_the_witness_rekeys_a_rule_keyed_table() -> None:
    """The other half of the transport: a table crosses the renaming too."""
    renaming = IrRenaming(IrRename("head", "first"), IrRename("tail", "second"))
    rows = IrMap(
        IrTuple(IrStr("head"), IrLiteral("H")),
        IrTuple(IrStr("tail"), IrLiteral("T")),
    )
    moved = renaming.rekeyed(rows)
    assert {str(key): str(body) for key, body in moved.items()} == {
        "first": "H",
        "second": "T",
    }


def test_rekeying_leaves_an_unmentioned_key_alone() -> None:
    """A partial renaming moves what it names and nothing else."""
    moved = IrRenaming(IrRename("head", "first")).rekeyed(
        IrMap(
            IrTuple(IrStr("head"), IrLiteral("H")), IrTuple(IrStr("x"), IrLiteral("X"))
        )
    )
    assert {str(key) for key in moved.keys()} == {"first", "x"}


def test_rekeying_onto_one_name_refuses() -> None:
    """Two rows landing on one key would silently drop one of them."""
    collide = IrRenaming(IrRename("a", "z"), IrRename("b", "z"))
    with pytest.raises(UnsupportedConstructError, match="duplicate key"):
        collide.rekeyed(
            IrMap(
                IrTuple(IrStr("a"), IrLiteral("A")), IrTuple(IrStr("b"), IrLiteral("B"))
            )
        )


def test_an_alignment_of_uncanonicalisable_grammars_refuses_with_words() -> None:
    """A name-fold collision is the canonicaliser's refusal, not a silent no."""
    clash = grammar('root ::= a_b\na_b ::= "x"\nA-B ::= "y"\n')
    with pytest.raises(UnsupportedConstructError, match="name folding collision"):
        align_names(clash, clash)
