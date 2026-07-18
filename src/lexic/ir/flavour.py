"""IrFlavour ABC — config bundle every grammar flavour subclasses.

An IrFlavour:
- Carries per-flavour metadata as ClassVars (name, extensions, etc.).
- Inherits IrEmitter — its ``actions`` tuple holds the per-IR-type
  rendering rules (the IR→text half).
- Carries its self-grammar (``grammar``) and parse reducer (``reducer``) —
  the text→IR half driven by :mod:`lexic.parsing`.

Zero methods beyond the emitter protocol: everything a flavour needs is
metadata, emit ``actions``, ``grammar``, and ``reducer``. The one protocol
refinement here is width — ``apply(root, width=88)`` renders a doc-valued
emission against the layout algebra (``width=None`` = flat).
"""

from __future__ import annotations

from abc import ABC
from typing import ClassVar, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrInt, IrLeaf, IrNode, IrNone, IrSelf, IrStr
from lexic.ir.escapes import EscapeCodec
from lexic.ir.layout import IrDoc, render
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import IrAst, IrRule
from lexic.ir.walk import IrDispatch, IrEmitter


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


class IrEscapePoint(IrLeaf[IrSelf, IrStr]):
    """Spell the focus code point through the **dispatcher's** codec,
    bracket-class context.

    The class-member sibling of :class:`IrEscape`: same fieldless shape, same
    codec-via-``d`` flow, but the focus is an integer code point (an
    ``IrChr``/``IrInt`` leaf) and the spelling rules are the codec's
    class-context tables (``CLASS_SHORT``/``CLASS_META`` + hex fallback).
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Return ``IrStr(d.escapes.encode_point(int(n)))``.

        :param d: Dispatcher; must carry an ``escapes`` :class:`EscapeCodec`.
        :param n: The code-point leaf to spell.
        :param _nc: Pre-walked children (unused).
        :returns: The class-safe member text as an :class:`IrStr`.
        :raises UnsupportedConstructError: If ``d`` carries no escape codec or
            ``n`` is not an integer code point.
        """
        codec = getattr(d, "escapes", IrNone)
        if not isinstance(codec, EscapeCodec):
            raise UnsupportedConstructError(
                f"IrEscapePoint: dispatcher {type(d).__name__} carries no codec"
            )
        if not isinstance(n, int):
            raise UnsupportedConstructError(
                f"IrEscapePoint: focus must be a code point, got {type(n).__name__!r}"
            )
        return IrStr(codec.encode_point(int(n)))


class IrSpellable(IrLeaf[IrSelf, IrInt]):
    """Truth test — does the focus str-leaf fit the **dispatcher's** quoted
    literal form?

    Reads the codec via ``d`` like :class:`IrEscape` and applies its
    ``QUOTE_SAFE`` ranges; the natural :class:`~lexic.ir.action.IrCond` test
    for a quoted-form-vs-numeric-fallback emit branch.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrInt:
        """Return ``IrInt(d.escapes.spellable(str(n)))``.

        :param d: Dispatcher; must carry an ``escapes`` :class:`EscapeCodec`.
        :param n: The str-leaf whose text to test.
        :param _nc: Pre-walked children (unused).
        :returns: ``IrInt(1)`` when every character is spellable, else ``IrInt(0)``.
        :raises UnsupportedConstructError: If ``d`` carries no escape codec or
            ``n`` is not a str-leaf.
        """
        codec = getattr(d, "escapes", IrNone)
        if not isinstance(codec, EscapeCodec):
            raise UnsupportedConstructError(
                f"IrSpellable: dispatcher {type(d).__name__} carries no codec"
            )
        if not isinstance(n, str):
            raise UnsupportedConstructError(
                f"IrSpellable: focus must be a str-leaf, got {type(n).__name__!r}"
            )
        return IrInt(codec.spellable(n))


class IrFlavour(IrEmitter, ABC):
    """Base for every grammar flavour.

    :cvar name: Short flavour identifier (e.g. ``"gbnf"``).
    :cvar extensions: Tuple of file extensions handled.
    :cvar escapes: EscapeCodec subclass for literal escape handling.
    :cvar line_comment: Line-comment prefix; empty disables @directive parsing.
    :cvar grammar: The flavour's self-grammar (raw, un-normalised) — ground truth.
    :cvar reducer: Parse-tree → IrAst policy (a parsing Reducer at runtime).
    :cvar core_rules: The flavour's std-namespace prelude (name-ref → rule) —
        e.g. RFC 5234 B.1 core rules. Consumed as dangling-ref resolution
        ONLY: a parsed grammar referencing a prelude name without defining it
        gets the rule appended; unmentioned prelude rules are never added.
    """

    name: ClassVar[str]
    extensions: ClassVar[tuple[str, ...]]
    escapes: ClassVar[EscapeCodec]
    line_comment: ClassVar[str] = ""
    grammar: ClassVar[IrAst]
    reducer: ClassVar[IrDispatch]
    core_rules: ClassVar[IrMap[IrStr, IrRule]] = IrMap()

    def apply(self, root: IrNode, width: int | None = 88) -> IrStr:
        """Emit ``root`` as flavour text, width-aware.

        The emitter protocol unchanged for str-tier results; a doc result
        (the structure-level actions build layout docs) renders against
        ``width`` — ``None`` renders flat (today's single-line rules).

        :param root: Root IR node to emit.
        :param width: Target maximum line width, or ``None`` for flat.
        :returns: The emitted text.
        """
        result = super().apply(root)
        if isinstance(result, IrDoc):
            return IrStr(render(result, width))
        return result
