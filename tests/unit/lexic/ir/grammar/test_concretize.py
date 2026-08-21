"""concretize — resolving an IrAlphabet's spelling to an encoding ordinal."""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action.mapping import IrMap
from lexic.ir.grammar.concretize import concretize, concretize_atom
from lexic.ir.grammar.nodes import (
    IrAlphabet,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrRule,
    IrSequence,
)
from lexic.ir.grammar.operators import IrNot
from lexic.ir.spine.records import IrSeq, IrTuple
from lexic.ir.spine.scalars import IrStr
from lexic.ir.text.codec.encodings import IrUnicode
from lexic.ir.text.tokenizer import IrTokenizer


def _registry() -> IrMap:
    tok = IrTokenizer.from_vocab(
        "gpt2",
        IrMap(
            IrTuple(IrStr("<think>"), IrChr(0)),
            IrTuple(IrStr("</think>"), IrChr(1)),
        ),
    )
    return IrMap(
        IrTuple(IrStr("unicode"), IrUnicode()),
        IrTuple(IrStr("gpt2"), tok),
    )


def _ast(*items: IrItem) -> IrAst:
    return IrAst(IrSeq(IrRule("r", IrSequence(*items))), "r")


def _atom(ast: IrAst) -> object:
    return ast.rules[0].body[0][0].atom


# ── text-form → id ─────────────────────────────────────────────────────


def test_concretize_resolves_text_form_literal_to_an_id() -> None:
    """A text-form token literal becomes an id-form char class."""
    out = concretize(
        _ast(IrItem(IrAlphabet("gpt2", IrLiteral("<think>")))), _registry()
    )
    assert _atom(out) == IrAlphabet("gpt2", IrCharClass(IrChr(0)))


def test_concretize_resolves_negated_text_form() -> None:
    """A negated text-form token resolves under its ``IrNot``."""
    out = concretize(
        _ast(IrItem(IrAlphabet("gpt2", IrNot(IrLiteral("</think>"))))), _registry()
    )
    assert _atom(out) == IrAlphabet("gpt2", IrNot(IrCharClass(IrChr(1))))


def test_concretize_passes_id_form_through() -> None:
    """An already-id-form alphabet is left intact (in-universe)."""
    out = concretize(
        _ast(IrItem(IrAlphabet("gpt2", IrCharClass(IrChr(1))))), _registry()
    )
    assert _atom(out) == IrAlphabet("gpt2", IrCharClass(IrChr(1)))


def test_concretize_leaves_unicode_atoms_untouched() -> None:
    """A bare (Unicode) char class is not an alphabet — unchanged."""
    out = concretize(_ast(IrItem(IrCharClass(IrChr(97)))), _registry())
    assert _atom(out) == IrCharClass(IrChr(97))


# ── refusals ───────────────────────────────────────────────────────────


def test_concretize_refuses_unbound_encoding() -> None:
    """An alphabet naming an unregistered encoding refuses."""
    reg = IrMap(IrTuple(IrStr("unicode"), IrUnicode()))
    with pytest.raises(UnsupportedConstructError, match="no encoding bound"):
        concretize(_ast(IrItem(IrAlphabet("gpt2", IrLiteral("<think>")))), reg)


def test_concretize_refuses_unmapped_spelling() -> None:
    """A spelling that is not one vocab token refuses."""
    with pytest.raises(UnsupportedConstructError, match="not one token"):
        concretize(_ast(IrItem(IrAlphabet("gpt2", IrLiteral("<nope>")))), _registry())


def test_concretize_refuses_out_of_universe_id() -> None:
    """An id-form token id beyond the vocab universe refuses."""
    with pytest.raises(UnsupportedConstructError, match="outside the encoding"):
        concretize(
            _ast(IrItem(IrAlphabet("gpt2", IrCharClass(IrChr(999))))), _registry()
        )


# ── per-atom seam ──────────────────────────────────────────────────────


def test_concretize_atom_resolves_a_single_alphabet() -> None:
    """The per-atom seam resolves one alphabet in isolation."""
    resolved = concretize_atom(IrAlphabet("gpt2", IrLiteral("<think>")), _registry())
    assert resolved == IrAlphabet("gpt2", IrCharClass(IrChr(0)))
