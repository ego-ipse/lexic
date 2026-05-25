# tests/unit/lexic/grammars/test_flavour.py
"""Flavour ABC contract tests — using a minimal fake flavour."""

from __future__ import annotations

from typing import ClassVar

import pytest

from lexic.grammars.flavour import Flavour
from lexic.ir.emit import FlavourEmitter
from lexic.ir.escapes import CANONICAL_ESCAPES
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrSequence,
)


def test_flavour_is_abstract_cannot_instantiate_directly():
    """Direct instantiation of the ABC raises TypeError."""
    cls: type = Flavour
    with pytest.raises(TypeError):
        cls()  # pylint: disable=abstract-class-instantiated


def test_concrete_flavour_with_required_attrs_works():
    """A fully-specified concrete subclass can be defined and used."""

    class _Fake(Flavour):
        name = "fake"
        extensions = (".fake",)
        meta_grammar = "start: NAME\nNAME: /[a-z]+/\n"
        escapes = CANONICAL_ESCAPES
        emitter: ClassVar[type[FlavourEmitter]] = FlavourEmitter
        line_comment = "#"

        @staticmethod
        def parse_quantifier(text: str) -> IrQuantifier:
            return IrQuantifier(1, 1)

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

    assert _Fake.name == "fake"
    assert _Fake.parse_quantifier("?") == IrQuantifier(1, 1)


def test_concrete_flavour_missing_abstract_methods_fails():
    """A subclass that omits the abstract methods cannot be instantiated."""

    class _Bad(Flavour):
        name = "bad"
        extensions = (".bad",)
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES
        emitter: ClassVar[type[FlavourEmitter]] = FlavourEmitter
        # Missing parse_quantifier and parse_charclass

    cls: type = _Bad
    with pytest.raises(TypeError):
        cls()  # pylint: disable=abstract-class-instantiated


def test_normalize_literal_default_is_identity():
    """Default normalize_literal returns IrLiteral wrapping the decoded string."""

    class _F(Flavour):
        name = "f"
        extensions = ()
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES
        emitter: ClassVar[type[FlavourEmitter]] = FlavourEmitter

        @staticmethod
        def parse_quantifier(text: str) -> IrQuantifier:
            return IrQuantifier()

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

    assert _F.normalize_literal("hello") == IrLiteral("hello")


def test_normalize_literal_can_be_overridden_to_return_group():
    """ABNF-style: case-insensitive 'abc' expands to a char-class group."""

    class _F(Flavour):
        name = "f"
        extensions = ()
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES
        emitter: ClassVar[type[FlavourEmitter]] = FlavourEmitter

        @staticmethod
        def parse_quantifier(text: str) -> IrQuantifier:
            return IrQuantifier()

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

        @classmethod
        def normalize_literal(cls, decoded: str) -> IrGroup:
            seq = IrSequence(
                tuple(IrItem(IrCharClass(f"{c.lower()}{c.upper()}")) for c in decoded)
            )
            return IrGroup(IrAlternation((seq,)))

    out = _F.normalize_literal("ab")
    assert isinstance(out, IrGroup)
    items = out.body.arms[0].items
    assert items[0].atom == IrCharClass("aA")
    assert items[1].atom == IrCharClass("bB")


def test_default_line_comment_is_empty_string():
    """line_comment defaults to empty string when not set by a subclass."""

    class _F(Flavour):
        name = "f"
        extensions = ()
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES
        emitter: ClassVar[type[FlavourEmitter]] = FlavourEmitter

        @staticmethod
        def parse_quantifier(text: str) -> IrQuantifier:
            return IrQuantifier()

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

    assert _F.line_comment == ""
