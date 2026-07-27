"""Compute — turning values into other values.

Conversion and combination: radix both ways, ordinals and glyphs, comparison
and type tests, and the three that join many values into one.
"""

from __future__ import annotations

from typing import ClassVar, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.grammar.nodes import IrAlternation, IrAst, IrLiteral, IrRule
from lexic.ir.grammar.operators import IrOp
from lexic.ir.spine.records import IrNamedTuple, IrSeq, IrTuple
from lexic.ir.spine.scalars import IrInt, IrScalar, IrStr
from lexic.ir.spine.spine import IrLeaf, IrSelf


class IrUnradix(IrNamedTuple[int, type[IrScalar]]):
    """Decode the focus digit string to ``out(value)`` via ord-arithmetic.

    The inverse of the emit-side radix spelling: reads its focus ``n`` as a
    digit string and returns ``out`` (an ``IrScalar`` subtype) of the value.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    base: int
    out: type[IrScalar] = IrInt

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrScalar:
        """Decode ``str(n)`` in ``self.base`` and wrap it in ``self.out``.

        :raises UnsupportedConstructError: On an empty string or a bad digit.
        """
        s = str(n)
        if not s:
            raise UnsupportedConstructError("IrUnradix: empty digit string")
        acc = 0
        for c in s:
            v = ord(c) - 0x30 if "0" <= c <= "9" else ord(c.upper()) - 0x41 + 10
            if not 0 <= v < self.base:
                raise UnsupportedConstructError(f"bad digit {c!r} for base {self.base}")
            acc = acc * self.base + v
        return self.out(acc)


class IrGlyph(IrLeaf[IrSelf, IrStr]):
    """Render the focus code point as its character — ``IrStr(chr(int(n)))``.

    The glyph step after :class:`IrUnradix`: digits decode to a neutral code
    point, this leaf spells it as text where text is being built (reduce-side
    literal assembly). ``IrPipe(IrUnradix(16, IrInt), IrGlyph())`` reads a hex
    run as one character.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Spell the focus code point.

        :raises UnsupportedConstructError: If the focus is not an integer
            code point.
        """
        if not isinstance(n, int):
            raise UnsupportedConstructError(
                f"IrGlyph: focus must be an integer code point, got "
                f"{type(n).__name__!r}"
            )
        return IrStr(chr(n))


class IrRadix(IrNamedTuple[int, int]):
    """Spell the focus integer as digits in ``base`` — the emit-side inverse
    of :class:`IrUnradix`.

    Digits are ``0-9A-Z`` (uppercase); the result is zero-padded to ``width``.
    ``IrPipe(IrOrd(), IrRadix(16, 2))`` spells a character as its two-digit
    hex code point.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    base: int
    width: int = 0

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Spell ``int(n)`` in ``self.base``, zero-padded to ``self.width``.

        :raises UnsupportedConstructError: If the focus is not a non-negative
            integer.
        """
        if not isinstance(n, int) or int(n) < 0:
            raise UnsupportedConstructError(
                f"IrRadix: focus must be a non-negative integer, got "
                f"{type(n).__name__!r}"
            )
        value = int(n)
        digits = ""
        while value:
            digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[value % self.base] + digits
            value //= self.base
        return IrStr((digits or "0").rjust(self.width, "0"))


class IrOrd(IrLeaf[IrSelf, IrInt]):
    """Focus character → its code point — ``IrInt(ord(str(n)))``.

    The inverse of :class:`IrGlyph`: text decodes to a neutral code point
    where a spelled form is being built (emit-side num-val assembly).
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrInt:
        """Return the focus's code point.

        :raises UnsupportedConstructError: If the focus is not a single
            character.
        """
        text = str(n)
        if len(text) != 1:
            raise UnsupportedConstructError(
                f"IrOrd: focus must be a single character, got {text!r}"
            )
        return IrInt(ord(text))


class IrCompare(IrNamedTuple[IrSelf, IrOp, IrSelf]):
    """Compare two operand nodes; eval to ``IrInt(1)`` (true) or ``IrInt(0)``.

    Evaluates ``left`` and ``right`` and hands the results to ``op`` (an
    :class:`IrOp`), which applies the comparison. A truth value is an ``IrInt``
    in ``{0, 1}`` — there is no ``IrBool``. Operands are typed ``IrSelf`` (not
    ``IrNode``): ``IrNode``'s ``Ir_co`` is invariant, so a value operand like
    ``IrField`` would not be assignable to a bare ``IrNode`` slot.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("left", "right")
    left: IrSelf
    op: IrOp
    right: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrInt:
        """Evaluate both operands and apply ``self.op``.

        :param d: Dispatcher forwarded to each operand's ``eval``.
        :param n: Current node forwarded to each operand's ``eval``.
        :param nc: Pre-walked children forwarded to each operand's ``eval``.
        :returns: ``IrInt(1)`` if the comparison holds, else ``IrInt(0)``.
        """
        operands = (self.left.eval(d, n, nc), self.right.eval(d, n, nc))
        return self.op.eval(d, n, operands)


class IrIsA(IrNamedTuple[str, type[IrSelf]]):
    """Test the type of a **raw** named attribute of the dispatched node ``n``.

    Reads ``getattr(n, self.name)`` undispatched — unlike :class:`IrChild`,
    which resolves the *rendered* child — so the test sees the IR node itself
    (e.g. ``IrIsA("atom", IrAlternation)`` asks whether an item's atom needs
    parenthesising). Evals to a truth value (``IrInt`` in ``{0, 1}``), the
    natural ``test`` operand of :class:`IrCond`.

    A record-leaf: ``name`` and the class-valued ``target`` are scalar payload
    (``_child_attrs = ()``); the class-aware repr renders ``target`` bare.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: str
    target: type[IrSelf]

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrInt:
        """Read the raw attribute and apply :func:`isinstance`.

        :param _d: Dispatcher (unused — no recursion).
        :param n: Node whose attribute to test.
        :param _nc: Pre-walked children (unused).
        :returns: ``IrInt(1)`` if the attribute IS-A ``target``, else ``IrInt(0)``.
        :raises AttributeError: If ``n`` has no attribute ``self.name``.
        """
        return IrInt(isinstance(getattr(n, self.name), self.target))


class IrMerge(IrLeaf[IrSelf, IrSelf]):
    """Fold the argument channel's rules into an :class:`~lexic.ir.grammar.nodes.IrAst`,
    merging same-named rules.

    Incremental definition (ABNF ``=/``): a rule whose name was already seen
    has its alternation arms appended to the earlier rule, in source order.
    The start rule is the first name defined.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Merge the channel's :class:`~lexic.ir.grammar.nodes.IrRule` args into an AST.

        :param _d: Dispatcher (unused).
        :param _n: Node (unused — the rules arrive on the channel).
        :param nc: The reduced rules, in source order.
        :returns: The assembled ``IrAst``.
        :raises UnsupportedConstructError: If a channel arg is not an ``IrRule``.
        """
        merged: list[IrRule] = []
        position: dict[str, int] = {}
        for rule in nc:
            if not isinstance(rule, IrRule):
                raise UnsupportedConstructError(
                    f"IrMerge: expected IrRule args, got {type(rule).__name__!r}"
                )
            if rule.name in position:
                base = merged[position[rule.name]]
                merged[position[rule.name]] = IrRule(
                    base.name, IrAlternation(*base.body, *rule.body)
                )
            else:
                position[rule.name] = len(merged)
                merged.append(rule)
        return IrAst(IrSeq(*merged), merged[0].name if merged else IrStr(""))


class IrConcat[Ir_co: IrStr = IrStr](IrNamedTuple[IrTuple]):
    """Evaluate ``parts`` in order; return ``bound().join(...)`` of results.

    Generic in ``Ir_co`` (bounded by :class:`IrStr`, defaulting to
    :class:`IrStr`). ``_bound`` is derived from ``Ir_co``, so at runtime the
    bound's neutral element (``IrStr()`` → ``""``) is the join base. As an
    :class:`IrNamedTuple` the ``bound`` property statically reports the base's
    ``IrSelf`` (no ``.join``), so ``eval`` casts ``self.bound`` to
    ``type[Ir_co]`` — the runtime value already satisfies it.

    :param Ir_co: the str-typed result type (defaults to :class:`IrStr`).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("parts",)
    parts: IrTuple = IrTuple()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Concatenate evaluated parts via the bound's neutral element.

        :param d: Dispatcher forwarded to each part's ``eval``.
        :param n: Current node forwarded to each part's ``eval``.
        :param nc: Pre-walked children forwarded to each part's ``eval``.
        :returns: The concatenation of all parts wrapped in ``self.bound``.
        """
        bound = cast(type[Ir_co], self.bound)
        return bound(bound().join(p.eval(d, n, nc) for p in self.parts))


class IrJoin[Ir_co: IrStr = IrStr](IrNamedTuple[IrSelf, IrSelf, IrSelf]):
    r"""Evaluate ``parts``; join results with ``separator``, fall back to
    ``empty`` when ``parts`` evaluates empty.

    All three children are :class:`IrNode`\\ s and participate in tree
    walks / rebuilds. ``parts`` is typically an :class:`IrTuple` (itself an
    IrNode); ``separator`` and ``empty`` are arbitrary IrNodes computed at
    eval time.

    :param Ir_co: the str-typed result type (defaults to :class:`IrStr`).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("parts", "separator", "empty")
    parts: IrSelf = IrTuple()
    separator: IrSelf = IrLiteral("")
    empty: IrSelf = IrLiteral("")

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Evaluate ``parts``; join or return the empty fallback.

        :param d: Dispatcher forwarded to each child's ``eval``.
        :param n: Current node forwarded to each child's ``eval``.
        :param nc: Pre-walked children forwarded to each child's ``eval``.
        :returns: The separator-joined parts, or ``empty`` when parts is empty.
        """
        rendered = self.parts.eval(d, n, nc)
        if not rendered:
            return cast("Ir_co", self.empty.eval(d, n, nc))
        sep = self.separator.eval(d, n, nc)
        bound = cast("type[Ir_co]", self.bound)
        return bound(bound(sep).join(rendered))
