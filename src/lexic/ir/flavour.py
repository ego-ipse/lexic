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
from typing import ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrLeaf, IrNone, IrSelf, IrStr
from lexic.ir.escapes import EscapeCodec
from lexic.ir.nodes import IrAlternation, IrLiteral, IrQuantifier
from lexic.ir.walk import IrEmitter


class IrEscape(IrLeaf[IrSelf, IrStr]):
    """Encode the dispatched node through the **dispatcher's** escape codec.

    A fieldless leaf: the codec is not payload — it flows in as context via
    ``d``, which under emission is the flavour singleton carrying its
    ``escapes`` ClassVar. The same body therefore renders correctly under
    every flavour (``IrConcat(IrLiteral('"'), IrEscape(), IrLiteral('"'))``
    is flavour-agnostic), and repr-is-codegen holds (``IrEscape()``).
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Return ``IrStr(d.escapes.encode(n))``.

        :param d: Dispatcher; must carry an ``escapes`` :class:`EscapeCodec`.
        :param n: The node whose payload to encode (a str-leaf).
        :param _nc: Pre-walked children (unused).
        :returns: The encoded payload as an :class:`IrStr`.
        :raises UnsupportedConstructError: If ``d`` carries no escape codec or
            ``n`` is not a str-leaf.
        """
        codec = getattr(d, "escapes", IrNone)
        if not isinstance(codec, EscapeCodec):
            raise UnsupportedConstructError(
                f"IrEscape: dispatcher {type(d).__name__} carries no escape codec"
            )
        if not isinstance(n, str):
            raise UnsupportedConstructError(
                f"IrEscape: cannot encode non-string node {type(n).__name__}"
            )
        return IrStr(codec.encode(n))


class IrFlavour(IrEmitter, ABC):
    """Base for every grammar flavour.

    :cvar name: Short flavour identifier (e.g. ``"gbnf"``).
    :cvar extensions: Tuple of file extensions handled.
    :cvar meta_grammar: Lark meta-grammar string for parsing source.
    :cvar escapes: EscapeCodec subclass for literal escape handling.
    :cvar line_comment: Line-comment prefix; empty disables @directive parsing.
    """

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
        :returns: Canonical ``IrQuantifier(lo, hi)``.
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
