"""IrFlavour ABC — config bundle every grammar flavour subclasses.

An IrFlavour:
- Carries per-flavour metadata as ClassVars (name, extensions, etc.).
- Inherits IrEmitter — its ``actions`` tuple holds the per-IR-type
  rendering rules.
- Declares ``parse_quantifier`` / ``parse_charclass`` as abstract
  staticmethods consumed by the meta-parser.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import IrAlternation, IrLiteral, IrQuantifier
from lexic.ir.walk import IrEmitter


class IrFlavour(IrEmitter, ABC):
    """Base for every grammar flavour.

    :cvar name: Short flavour identifier (e.g. ``"gbnf"``).
    :cvar extensions: Tuple of file extensions handled.
    :cvar meta_grammar: Lark meta-grammar string for parsing source.
    :cvar escapes: EscapeCodec subclass for literal escape handling.
    :cvar line_comment: Line-comment prefix; empty disables @directive parsing.
    """

    __slots__ = ()
    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    meta_grammar: ClassVar[str]
    escapes: ClassVar[EscapeCodec]
    line_comment: ClassVar[str] = ""

    @staticmethod
    @abstractmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        """Parse a quantifier symbol into an IrQuantifier.

        :param text: Flavour-specific quantifier token.
        :returns: Canonical ``IrQuantifier(min, max)``.
        """

    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse a char class into ``(pattern, negated)``.

        :param text: Bracket-expression token text.
        :returns: Tuple of canonical pattern and negation flag.
        """

    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrAlternation:
        """Optional sugar-expansion hook. Default: identity (return IrLiteral).

        :param decoded: Decoded literal string.
        :returns: ``IrLiteral`` wrapping the decoded string.
        """
        return IrLiteral(decoded)
