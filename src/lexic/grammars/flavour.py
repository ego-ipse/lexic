"""Flavour ABC — the contract every grammar flavour fulfils.

A flavour module is configuration: a Lark meta-grammar string with
canonical-tagged productions, an EscapeCodec subclass, a FlavourEmitter
subclass, and two staticmethods that parse quantifier and char-class
token strings. No imperative pipeline code per flavour.

The optional `normalize_literal` hook allows flavour-specific sugar
expansion (e.g. ABNF case-insensitive literals) without leaking flavour
concepts into the IR AST itself: the hook returns canonical IR AST nodes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import IrGroup, IrLiteral, Quantifier


class Flavour(ABC):
    """Per-flavour configuration. Subclass and fill in class attributes."""

    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    meta_grammar: ClassVar[str]
    escapes: ClassVar[EscapeCodec]
    emitter: ClassVar[Any]  # FlavourEmitter — typed loosely to avoid import cycle
    line_comment: ClassVar[str] = ""

    @staticmethod
    @abstractmethod
    def parse_quantifier(text: str) -> Quantifier:
        """Parse a flavour-specific quantifier token text into canonical bounds."""

    @staticmethod
    @abstractmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """Parse a bracket-expression token. Return (canonical_pattern, negated)."""

    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrGroup:
        """Optional sugar-expansion hook. Default: identity (return IrLiteral)."""
        return IrLiteral(decoded)
