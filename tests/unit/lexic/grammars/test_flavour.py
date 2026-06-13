# tests/unit/lexic/grammars/test_flavour.py
"""IrFlavour ABC contract tests — using a minimal fake flavour."""

from __future__ import annotations

from abc import ABC

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.flavour import IrEscape, IrFlavour
from lexic.grammars.gbnf.flavour import GBNF_ESCAPES, GBNF_FLAVOUR
from lexic.ir.base import IrNone, IrStr
from lexic.ir.escapes import CANONICAL_ESCAPES
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrSequence,
)
from lexic.ir.walk import IrEmitter


def test_flavour_is_abstract_cannot_instantiate_directly():
    """Direct instantiation of the ABC raises TypeError."""
    cls: type = IrFlavour
    with pytest.raises(TypeError):
        cls()  # pylint: disable=abstract-class-instantiated


def test_concrete_flavour_with_required_attrs_works():
    """A fully-specified concrete subclass can be defined and used."""

    class _Fake(IrFlavour):
        name = "fake"
        extensions = (".fake",)
        meta_grammar = "start: NAME\nNAME: /[a-z]+/\n"
        escapes = CANONICAL_ESCAPES
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

    class _Bad(IrFlavour):
        name = "bad"
        extensions = (".bad",)
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES
        # Missing parse_quantifier and parse_charclass

    cls: type = _Bad
    with pytest.raises(TypeError):
        cls()  # pylint: disable=abstract-class-instantiated


def test_normalize_literal_default_is_identity():
    """Default normalize_literal returns IrLiteral wrapping the decoded string."""

    class _F(IrFlavour):
        name = "f"
        extensions = ()
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES

        @staticmethod
        def parse_quantifier(text: str) -> IrQuantifier:
            return IrQuantifier()

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

    assert _F.normalize_literal("hello") == IrLiteral("hello")


def test_normalize_literal_can_be_overridden_to_return_group():
    """ABNF-style: case-insensitive 'abc' expands to a char-class group."""

    class _F(IrFlavour):
        name = "f"
        extensions = ()
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES

        @staticmethod
        def parse_quantifier(text: str) -> IrQuantifier:
            return IrQuantifier()

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

        @classmethod
        def normalize_literal(cls, decoded: str) -> IrAlternation:
            seq = IrSequence(
                *(
                    IrItem(IrCharClass(IrStr(f"{c.lower()}{c.upper()}")))
                    for c in decoded
                )
            )
            return IrAlternation(seq)

    out = _F.normalize_literal("ab")
    assert isinstance(out, IrAlternation)
    arm = out[0]
    assert arm[0].atom == IrCharClass(IrStr("aA"))
    assert arm[1].atom == IrCharClass(IrStr("bB"))


def test_default_line_comment_is_empty_string():
    """line_comment defaults to empty string when not set by a subclass."""

    class _F(IrFlavour):
        name = "f"
        extensions = ()
        meta_grammar = ""
        escapes = CANONICAL_ESCAPES

        @staticmethod
        def parse_quantifier(text: str) -> IrQuantifier:
            return IrQuantifier()

        @staticmethod
        def parse_charclass(text: str) -> tuple[str, bool]:
            return text, False

    assert _F.line_comment == ""


def test_irflavour_is_subclass_of_iremitter():
    """IrFlavour inherits from IrEmitter."""
    assert issubclass(IrFlavour, IrEmitter)


def test_irflavour_requires_parse_quantifier_and_parse_charclass():
    """IrFlavour declares both parse_quantifier and parse_charclass as abstract."""
    assert issubclass(IrFlavour, ABC)
    abstract = IrFlavour.__abstractmethods__
    assert "parse_quantifier" in abstract
    assert "parse_charclass" in abstract


# ── IrEscape ──────────────────────────────────────────────────────────


def test_irescape_encodes_via_gbnf_flavour_codec():
    """IrEscape.eval under GBNF_FLAVOUR encodes a str-leaf via GBNF_ESCAPES."""
    node = IrLiteral('a"b\n')
    result = IrEscape().eval(GBNF_FLAVOUR, node, ())
    assert result == GBNF_ESCAPES.encode('a"b\n')
    assert isinstance(result, IrStr)


def test_irescape_result_is_irstr():
    """IrEscape.eval returns an IrStr (not just str)."""
    result = IrEscape().eval(GBNF_FLAVOUR, IrLiteral("abc"), ())
    assert isinstance(result, IrStr)


def test_irescape_dispatcher_without_escapes_raises():
    """IrEscape.eval raises UnsupportedConstructError when the dispatcher has no escapes."""
    with pytest.raises(UnsupportedConstructError):
        IrEscape().eval(IrNone, IrLiteral("a"), ())


def test_irescape_non_string_node_raises():
    """IrEscape.eval raises UnsupportedConstructError for a non-str-leaf node."""
    with pytest.raises(UnsupportedConstructError):
        IrEscape().eval(GBNF_FLAVOUR, IrQuantifier(1, 1), ())


def test_irescape_repr_is_codegen():
    """IrEscape repr is 'IrEscape()' — fieldless leaf."""
    assert repr(IrEscape()) == "IrEscape()"
