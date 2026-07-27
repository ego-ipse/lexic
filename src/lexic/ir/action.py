"""Action-algebra IrNodes — primitive-node model.

Every class here is a plain :class:`IrNode` (via :class:`IrNamedTuple`,
:class:`IrSeq`, or an :class:`IrLeaf`/:class:`IrNode` leaf) that overrides
``eval`` to do work other than identity. The action algebra adds operations the
grammar AST nodes don't cover: attribute reads, sibling lookup, joining,
branching, short-circuit, and a procedural escape hatch.

All nodes inherit ``__call__ -> Self`` from :class:`IrSelf` (identity).
The value-producing protocol is ``eval(d, n, nc) -> Ir_co`` — every class
here overrides ``eval`` to produce its typed result. Pass :data:`IrNone`
to a slot that has no relevant value.

**``nc`` is the argument channel.** Operands for :class:`~lexic.ir.operators.IrOp`,
operand-fold inputs for procedural bodies, render-marks for emitter
actions (handed over by :class:`IrApply`, read by :class:`IrArgs`). It is NOT
a children channel: the child readers (:class:`IrChild`, :class:`IrIndex`,
:class:`IrChildren`) always resolve children from ``n`` itself and ignore
``nc``. ``IrConcat``/``IrJoin`` forward ``nc`` to their parts, which is how
``IrArgs`` receives arguments deep inside an action body.

**Node shapes:** the record-style actions (``IrField``, ``IrCompare``,
``IrAt``, ``IrArgs``, ``IrApply``, ``IrChildren``, ``IrConcat``, ``IrJoin``,
``IrCond``, ``IrRaise``, ``IrAction``) are :class:`IrNamedTuple` records; ``IrReturn`` is an
:class:`IrNode` leaf that also IS-A ``BaseException`` (object-based bases, unlike
a tuple, coexist with its layout).
The default bodies (``IrPass``, ``IrWalk``, ``IrEmit``, ``IrRebuild``) are plain
``__slots__`` leaves. The procedural escape hatch
:class:`~lexic.ir.base.IrLambda` lives in the spine so lower layers
(e.g. :mod:`lexic.ir.operators`) can use it too.
"""

from __future__ import annotations

from typing import ClassVar, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import IrAlternation, IrAst, IrLiteral, IrRule
from lexic.ir.operators import IrOp
from lexic.ir.records import IrNamedTuple, IrSeq, IrTuple
from lexic.ir.scalars import IrInt, IrScalar, IrStr
from lexic.ir.spine import IrLeaf, IrNode, IrNone, IrSelf

# ── Control-flow exception ────────────────────────────────────────────


class _Return(BaseException):
    """Control-flow exception raised by :class:`IrReturn`.

    Inherits :class:`BaseException` (not :class:`Exception`) so
    procedural bodies that wrap their work in
    ``except Exception:`` cannot swallow it.
    """

    def __init__(self, value: object) -> None:
        """Initialise with the value to surface to the dispatcher.

        :param value: The value carried out to the catching dispatcher.
        """
        super().__init__()
        self.value = value


# ── Attribute reader ──────────────────────────────────────────────────


class IrField(IrNamedTuple[str, type[IrScalar]]):
    """Read a typed attribute from the dispatched node ``n`` and wrap it.

    The read value is wrapped via the **runtime** constructor ``out`` — a
    value-leaf type such as :class:`~lexic.ir.nodes.IrStr` / :class:`IrInt`
    (default ``IrStr``). Read an int with ``IrField("lo", IrInt)``; the default
    ``out=IrStr`` keeps every existing ``IrField("name")`` caller unchanged.

    Cast-free and open: ``out`` is any ``type[IrScalar]`` — callable with the
    payload thanks to :meth:`IrScalar.__new__`, so ``self.out(value)``
    type-checks without a cast and a new ``IrScalar`` subtype needs no change
    here (no enumerated leaf-type union).

    A record-leaf: ``name`` and the class-valued ``out`` are scalar payload
    (``_child_attrs = ()``); the class-aware repr renders ``out`` as a bare name.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    name: str
    out: type[IrScalar] = IrStr

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrScalar:
        """Read ``getattr(n, self.name)`` and wrap via ``self.out(value)``.

        :param _d: Dispatcher (unused — no recursion).
        :param n: Node whose attribute to read.
        :param _nc: Pre-walked children (unused).
        :returns: The attribute value wrapped in ``self.out`` (an ``IrScalar``).
        """
        return self.out(getattr(n, self.name))


# ── Radix decoder ─────────────────────────────────────────────────────


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


# ── Comparison ────────────────────────────────────────────────────────


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


# ── Attribute type test ───────────────────────────────────────────────


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


# ── Sibling lookup ────────────────────────────────────────────────────


class IrChild(IrStr):
    """Single dispatched child by name — the node IS the child's field name.

    Resolves the name through ``type(n)._child_attrs`` (record nodes) and
    yields the *dispatched* child. For tuple-shaped nodes whose children
    carry no names, :class:`IrIndex` is the positional primitive this
    resolves to.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve the named child and dispatch it via ``d``.

        :param d: Dispatcher for the sub-dispatch.
        :param n: Node whose child to resolve.
        :param _nc: Arguments (unused — children come from ``n``, never ``nc``).
        :returns: The dispatched child.
        :raises ValueError: if the name is not in ``type(n)._child_attrs``.
        """
        attrs = getattr(type(n), "_child_attrs", ())
        try:
            idx = attrs.index(self)
        except ValueError as exc:
            raise ValueError(
                f"{self!r}: {type(n).__name__} has no such child (known: {attrs})"
            ) from exc
        return d.eval(d, n.children()[idx], IrTuple())


class IrIndex(IrInt):
    """Single dispatched child by position — the node IS the index.

    The positional primitive: tuple-shaped nodes (operator monads,
    collections) have unnamed children, and ``IrIndex(0)`` addresses the
    first directly — the 0th key of a monad like ``IrNot``. Negative
    positions index from the end, as native tuples do.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve the child at this position and dispatch it via ``d``.

        :param d: Dispatcher for the sub-dispatch.
        :param n: Node whose child to resolve.
        :param _nc: Arguments (unused — children come from ``n``, never ``nc``).
        :returns: The dispatched child.
        :raises IndexError: if the position is out of range.
        """
        return d.eval(d, n.children()[self], IrTuple())


class IrAt[Ir_co: IrSelf](IrNamedTuple[int, IrSelf]):
    """Binder — rebind the dispatch focus to a raw child, then evaluate ``body``.

    The algebra's first context-shifting node: every other node evaluates
    against the ``n`` it was dispatched with, but inside an ``IrAt`` body
    ``n`` IS the selected child — ``n.children()[selector]``, raw and
    undispatched, with a fresh empty argument channel. Where :class:`IrIndex`
    yields the *dispatched* child, ``IrAt`` exposes the *raw* child to its
    body — e.g. ``IrAt(0, IrTypeMap(...))`` resolves a guard table against
    an operand's own type.

    ``selector`` is positional scalar payload (negatives index from the end,
    as native tuples do).

    :param Ir_co: the body's result type.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    selector: int
    body: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Evaluate ``body`` with ``n`` rebound to the selected raw child.

        :param d: Dispatcher, forwarded unchanged for sub-dispatch.
        :param n: Node whose raw child becomes the body's focus.
        :param _nc: Arguments (not forwarded — a focus shift starts clean).
        :returns: The body's result against the rebound focus.
        :raises IndexError: If ``selector`` is out of range for ``n.children()``.
        """
        return self.body.eval(d, n.children()[self.selector], IrTuple())


class IrEach[Ir_co: IrSelf](IrNamedTuple[IrSelf]):
    """Map ``body`` over the focus's elements — an ``IrTuple`` of the results.

    The variadic sibling of :class:`IrAt`: ``n`` is rebound to each element in
    turn (a tuple-shaped node's elements; a str-leaf's characters, each lifted
    to :class:`~lexic.ir.base.IrStr`), and like every focus shift the body
    starts with a clean argument channel.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    body: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrTuple:
        """Evaluate ``body`` once per element of the focus.

        :param d: Dispatcher, forwarded unchanged for sub-dispatch.
        :param n: The tuple-shaped or str-leaf focus to iterate.
        :param _nc: Arguments (not forwarded — a focus shift starts clean).
        :returns: The per-element results as an :class:`IrTuple`.
        :raises UnsupportedConstructError: If the focus has no elements to map.
        """
        if isinstance(n, tuple):
            elements: tuple[IrSelf, ...] = tuple(n)
        elif isinstance(n, str):
            elements = tuple(IrStr(c) for c in str(n))
        else:
            raise UnsupportedConstructError(
                f"IrEach: focus {type(n).__name__!r} has no elements"
            )
        return IrTuple(*(self.body.eval(d, e, IrTuple()) for e in elements))


class IrLen(IrLeaf[IrSelf, IrInt]):
    """Element count of the focus — ``IrInt(len(n))``.

    Counts a tuple-shaped node's elements or a str-leaf's characters; the
    natural :class:`IrCompare` operand for arity-branching bodies.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrInt:
        """Return the focus's length.

        :raises UnsupportedConstructError: If the focus is unsized.
        """
        if not isinstance(n, (tuple, str)):
            raise UnsupportedConstructError(
                f"IrLen: focus {type(n).__name__!r} has no length"
            )
        return IrInt(len(n))


class IrPipe(IrNamedTuple[IrSelf, IrSelf]):
    """Rebind the focus to a computed value, then evaluate ``body``.

    Evaluates ``source``, then evaluates ``body`` with that result as ``n`` (the
    argument channel carries through). The focus-shift onto a *computed* node —
    where :class:`IrAt` shifts onto a raw child by index. ``IrPipe(IrArg(0),
    IrField("name"))`` reads ``name`` off the first argument.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("source", "body")
    source: IrSelf
    body: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Evaluate ``body`` with ``n`` rebound to ``source``'s result."""
        return self.body.eval(d, self.source.eval(d, n, nc), nc)


class IrChildren[Iri: IrSelf, Ir_co: IrSelf = IrSelf](IrNamedTuple):
    """Full tuple of dispatched children of ``n`` (reads ``n.children()``).

    ``Ir_co`` is the dispatcher's per-child result type. The result is the
    whole children sequence — distinct from :class:`IrChild` at the type
    level. ``_bound`` is derived from ``Ir_co`` so :meth:`IrSelf.bind` works.

    A fieldless record-leaf: it has no fields of its own.

    :param Ir_co: the dispatcher's per-child result type.
    """

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Resolve the children collection — dispatch each child via ``d``.

        :param d: Dispatcher for the per-child sub-dispatch.
        :param n: Node whose children to resolve.
        :param _nc: Arguments (unused — children come from ``n``, never ``nc``;
            the argument analogue is :class:`IrArgs`).
        :returns: The children sequence, type-checked against ``self.bound``.
        """
        return cast(
            Ir_co, self.bind(IrTuple(*(d.eval(d, c, IrTuple()) for c in n.children())))
        )


# ── Argument channel ──────────────────────────────────────────────────


class IrArgs(IrNamedTuple):
    """The argument channel, read whole — evaluates to the ``nc`` tuple.

    The argument analogue of :class:`IrChildren`: children come from the
    node, arguments from the caller. A renderer places
    ``IrJoin(parts=IrArgs())`` wherever received marks belong in its surface
    syntax; with no arguments passed it evaluates empty and the join's
    ``empty`` fallback applies.

    A fieldless record-leaf.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrTuple:
        """Return the arguments as a tuple node.

        :param _d: Dispatcher (unused).
        :param _n: Node (unused).
        :param nc: The argument channel.
        :returns: ``nc`` as an :class:`IrTuple`.
        """
        return IrTuple(*nc)


class IrArg(IrInt):
    """Single argument by position — the node IS the index into ``nc``.

    The argument-channel analogue of :class:`IrIndex` (which indexes ``n``'s
    children): ``IrArg(0)`` returns the first element of the channel **as-is**,
    undispatched — the arguments are already resolved values (a reducer hands a
    body its reduced children on ``nc``). Negative positions index from the end,
    as native tuples do.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Return the argument at this position, undispatched.

        :param _d: Dispatcher (unused — arguments are already resolved).
        :param _n: Node (unused — the value comes from ``nc``, never ``n``).
        :param nc: The argument channel.
        :returns: ``nc[self]``.
        :raises IndexError: If the position is out of range.
        """
        return nc[self]


class IrApply[Ir_co: IrSelf](IrNamedTuple[IrTuple]):
    """Delegation — re-dispatch the current focus ``n`` with arguments.

    Evaluates each element of ``args`` against the current context, then
    dispatches ``n`` itself through ``d`` with the results as the argument
    channel. The node's own action runs and decides what the received
    arguments mean — e.g. a negation mark spliced into a class's brackets
    via :class:`IrArgs`. Carries no selector: compose with :class:`IrAt`
    to aim the delegation at an operand.

    :param Ir_co: the dispatched action's result type.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("args",)
    args: IrTuple = IrTuple()

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Dispatch ``n`` via ``d`` with the evaluated ``args`` as the channel.

        :param d: Dispatcher resolving ``n``'s own action.
        :param n: The focus to re-dispatch.
        :param nc: Current arguments, forwarded while evaluating ``args``.
        :returns: The dispatched action's result.
        """
        evaluated = IrTuple(*(a.eval(d, n, nc) for a in self.args))
        return d.eval(d, n, evaluated)


# ── Construction ──────────────────────────────────────────────────────


class IrBuild(IrNamedTuple[type[IrSelf], IrSelf]):
    """Construct ``target`` from the argument channel.

    ``args=IrNone`` (default) splats the raw channel — ``target(*nc)``; an
    ``args`` body reshapes it first — ``target(*args.eval(...))``.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("args",)
    target: type[IrSelf]
    args: IrSelf = IrNone

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Construct ``target`` from raw ``nc`` or the evaluated ``args``."""
        return self.target(*(nc if self.args is IrNone else self.args.eval(d, n, nc)))


class IrMerge(IrLeaf[IrSelf, IrSelf]):
    """Fold the argument channel's rules into an :class:`~lexic.ir.nodes.IrAst`,
    merging same-named rules.

    Incremental definition (ABNF ``=/``): a rule whose name was already seen
    has its alternation arms appended to the earlier rule, in source order.
    The start rule is the first name defined.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Merge the channel's :class:`~lexic.ir.nodes.IrRule` args into an AST.

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


# ── String concatenation ──────────────────────────────────────────────


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


# ── Variable-arity join with separator ────────────────────────────────


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


# ── Conditional branch ────────────────────────────────────────────────


class IrCond[Ir_co: IrSelf](IrNamedTuple[IrSelf, IrSelf, IrSelf]):
    """If ``test`` evaluates truthy, evaluate ``then_op``; else ``else_op``.

    ``test`` is any node whose ``eval`` yields a truthy/falsy value (e.g.
    :class:`IrCompare`, :class:`IrAnd`). Typed ``IrSelf`` (not ``IrNode``) for
    the same reason as :class:`IrCompare`'s operands — ``IrNode``'s ``Ir_co`` is
    invariant, which rejects value operands like ``IrField``. Both branches
    share ``Ir_co``.

    :param Ir_co: the shared result type of both branches.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("test", "then_op", "else_op")
    test: IrSelf
    then_op: IrSelf
    else_op: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Branch on the truthiness of ``self.test.eval(d, n, nc)``.

        :param d: Dispatcher forwarded to the test and the chosen branch.
        :param n: Current node forwarded to the test and the chosen branch.
        :param nc: Pre-walked children forwarded onward.
        :returns: The chosen branch's result.
        """
        branch = self.then_op if self.test.eval(d, n, nc) else self.else_op
        return branch.eval(d, n, nc)


# ── Default bodies ────────────────────────────────────────────────────


class IrThis(IrLeaf[IrSelf, IrSelf]):
    """Identity body — evaluates to the dispatched node ``n`` as-is.

    Use when an action matches and the dispatcher's return-shape contract
    is satisfied by the dispatched node itself. Equivalent to Python's
    ``lambda d, n, nc: n``.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Return the dispatched node ``n``.

        :param _d: Dispatcher (unused).
        :param n: Node to return as-is.
        :param _nc: Pre-walked children (unused).
        :returns: The dispatched node ``n``.
        """
        return n


class IrPass(IrLeaf[IrSelf, IrSelf]):
    """No-op body — evaluates to :data:`IrNone` without recursing.

    Use when an action matches but neither a value nor a child walk is
    desired. Equivalent to Python's ``pass``. Not the default for
    :class:`~lexic.ir.walk.IrVisitor` — that role belongs to
    :class:`IrWalk`.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Return :data:`IrNone`.

        :param _d: Dispatcher (unused).
        :param _n: Node (unused).
        :param _nc: Pre-walked children (unused).
        :returns: :data:`IrNone`.
        """
        return IrNone


class IrWalk(IrLeaf[IrSelf, IrSelf]):
    """Walk ``n``'s children via ``d``; return :data:`IrNone`.

    Canonical body for visitor defaults — the visitor analogue of
    :class:`IrRebuild`. Side-effect-only: child results are dispatched
    for their effects and discarded. Honours ``nc``: if the caller has
    already dispatched children, no re-walk happens.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Walk children unless they were pre-dispatched; return :data:`IrNone`.

        :param d: Dispatcher driving child recursion.
        :param n: Node whose children to walk. Runtime contract: ``IrNode``.
        :param nc: Pre-dispatched children, if any — skips the walk when truthy.
        :returns: :data:`IrNone`.
        """
        if not nc:
            for c in n.children():
                d.eval(d, c, ())
        return IrNone


class IrEmit[Iri: IrSelf, Ir_co: IrLiteral](IrLeaf[Iri, Ir_co]):
    """Body that emits ``IrLiteral(str(n))`` for the dispatched node.

    Default body for :class:`~lexic.ir.walk.IrEmitter`. Stringifies
    ``n`` via its ``__str__`` (str-leaves ARE their value; other nodes fall
    back to their str form) and wraps the result as an :class:`IrLiteral`.
    Override an emitter's ``default`` with :class:`IrRaise` to refuse
    unmatched types instead.

    A plain ``__slots__`` leaf with an explicit ``_bound`` (no PEP 695 type
    parameter carries the bound at construction here, so it is declared).

    :param Ir_co: the :class:`IrLiteral`-typed result type.
    """

    _bound: ClassVar[type] = IrLiteral

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Return ``IrLiteral(str(n))``.

        :param _d: Dispatcher (unused).
        :param n: The dispatched node.
        :param _nc: Pre-walked children (unused).
        :returns: ``IrLiteral`` wrapping the node's string form.
        """
        return self.bound(str(n))


class IrRebuild(IrLeaf[IrSelf, IrNode]):
    """Walk ``n``'s children via ``d``, then rebuild ``n`` with the result.

    Canonical body for transformer defaults. Always rebuilds — change
    detection lives in callers if they want it.

    A plain ``__slots__`` leaf. ``n`` is
    narrowed with an explicit :func:`isinstance` guard that raises
    :exc:`~lexic.exceptions.UnsupportedConstructError` — no suppression
    (matches the codebase's "explicit raise in every dispatch path" rule).

    :raises UnsupportedConstructError: if ``n`` is not an :class:`IrNode`.
    """

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrNode:
        """Walk ``n.children()`` via ``d`` (or accept ``nc``), then rebuild.

        :param d: Dispatcher driving child recursion.
        :param n: Node to rebuild. Must be an :class:`IrNode`.
        :param nc: Pre-dispatched children, if any.
        :returns: ``n.rebuild(new_children)``.
        :raises UnsupportedConstructError: if ``n`` is not an :class:`IrNode`.
        """
        if not isinstance(n, IrNode):  # narrow: only IrNodes can be rebuilt
            raise UnsupportedConstructError(
                f"IrRebuild: cannot rebuild {type(n).__name__}"
            )
        new_children = nc or IrTuple(*(d.eval(d, c, ()) for c in n.children()))
        return n.rebuild(new_children)


# ── Strict default ────────────────────────────────────────────────────


class IrRaise[Ir_co: IrSelf](IrNamedTuple[type[BaseException], str]):
    """Body that raises a configured exception on dispatch.

    Strict-default body for :class:`~lexic.ir.walk.IrDispatch`. When
    no action in the dispatcher's table matches ``type(n).__mro__``,
    the dispatcher falls through to ``self.default`` — when that is
    :class:`IrRaise`, this body raises ``exc_type`` with a formatted
    message. The default ``exc_type`` is
    :exc:`~lexic.exceptions.UnsupportedConstructError`.

    :param Ir_co: the (never-produced) result type.
    :param exc_type: Exception class to raise.
    :param message: ``str.format``-style template. Substitutions:
        ``{dispatcher}`` → ``type(d).__name__``; ``{node_type}`` →
        ``type(n).__name__``.
    """

    exc_type: type[BaseException] = UnsupportedConstructError
    message: str = "{dispatcher}: no action for {node_type!r}"

    def eval(self, d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> Ir_co:
        """Raise ``self.exc_type`` with the formatted message.

        :param d: Dispatcher driving the walk.
        :param n: Node whose type had no matching action.
        :param _nc: Pre-walked children (unused).
        :returns: Never returns normally.
        :raises BaseException: Always — an instance of ``self.exc_type``.
        """
        raise self.exc_type(
            self.message.format(
                dispatcher=type(d).__name__,
                node_type=type(n).__name__,
            )
        )


# ── Short-circuit return ──────────────────────────────────────────────


class IrReturn[Ir_co: IrSelf](IrNode[IrSelf, Ir_co], _Return):
    """Short-circuit IR node that IS-A control-flow exception.

    ``IrReturn`` mixes :class:`IrNode` (structural IR contract) with
    :class:`_Return` (BaseException machinery). Both are object-based — unlike a
    tuple, they coexist with ``BaseException``'s instance layout — so it is a
    plain :class:`IrNode` leaf, not an :class:`IrNamedTuple`. ``eval`` raises
    ``self``; the dispatcher catches the instance and surfaces ``self.value`` or
    the instance itself. Equality is by identity (``BaseException`` semantics).

    :param Ir_co: the type of the carried value.
    """

    lazy_eval: bool

    def __init__(self, value: object = IrThis(), lazy_eval: bool = True) -> None:
        """Carry ``value`` and initialise the ``BaseException`` machinery.

        :param value: Value to surface — defaults to the dispatched node (via
            :class:`IrThis`) when none is given.
        :param lazy_eval: When ``True``, an ``IrSelf`` value is ``eval``\\ ed
            before the exception unwinds.
        """
        _Return.__init__(self, value)
        self.lazy_eval = lazy_eval

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Raise ``self`` — unwinds to the dispatcher's catch.

        :param _d: Dispatcher (unused).
        :param _n: Node (unused).
        :param _nc: Pre-walked children (unused).
        :returns: Never returns normally.
        :raises IrReturn: Always — raises ``self``.
        """

        if self.lazy_eval and isinstance(self.value, IrSelf):
            raise self.__class__(self.value.eval(d, n, nc))
        raise self


# ── Action binding ────────────────────────────────────────────────────


class IrAction[Ir_co: IrSelf](IrNamedTuple[type[IrSelf], IrSelf]):
    """Bind a target IR node type to a callable IrNode body.

    ``target_type`` is metadata (a concrete IR-node type, scalar payload
    excluded from ``children()`` via ``_child_attrs``); the class-aware repr
    renders it as a bare name. ``body`` is the single IrNode child invoked
    under dispatch.

    :param Ir_co: the result type the body produces.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    target_type: type[IrSelf]
    body: IrSelf

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> Ir_co:
        """Delegate to the body.

        :param d: Dispatcher forwarded to the body's ``eval``.
        :param n: Current node forwarded to the body's ``eval``.
        :param nc: Pre-walked children forwarded to the body's ``eval``.
        :returns: The body's result.
        """
        return self.body.eval(d, n, nc)
