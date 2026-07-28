"""Value leaves — a scalar node IS its payload.

``IrScalar`` and the three concrete leaves: ``IrStr`` subclasses ``str``,
``IrInt`` subclasses ``int``, and ``IrChr`` is an ``IrInt`` that reads as the
character it numbers. There is no ``.value`` — ``leaf == \"x\"`` works because
the leaf is the string.
"""

from __future__ import annotations

from typing import Any, ClassVar, Self, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.spine.spine import IrLeaf, IrSelf


class IrScalar(IrLeaf):
    """Abstract base for value-carrying leaves (:class:`IrStr`, :class:`IrInt`).

    Hosts the behaviour shared by all value leaves: self-evaluating ``eval``,
    type-aware equality/hash (distinct leaf kinds never compare equal), and
    codegen ``__repr__``. Each subclass sets ``_bound`` to its primitive base,
    which drives payload comparison, hashing and rendering.

    Abstract **by convention**: instantiate a concrete leaf (``IrStr``/``IrInt``),
    never ``IrScalar`` itself — it has no primitive base to hold a payload, so
    ``IrScalar("x")`` fails. (Not an ``@abstractmethod`` ABC: the concrete leaves
    override no method to mark abstract, and an abstract ``IrScalar`` would make
    ``type[IrScalar]`` — e.g. :attr:`~lexic.ir.action.IrField.out` — un-callable
    for the type checker.)
    """

    def __new__(cls, *args: object) -> Self:
        """Forward construction to the primitive base.

        Exists so ``type[IrScalar]`` is callable with a payload (e.g. for
        :attr:`~lexic.ir.action.IrField.out`); subclasses carry no ``__new__``.
        No args ⇒ the primitive's own default (``""`` / ``0``).

        :param args: The payload, forwarded to the primitive ``__new__``.
        :returns: A new value-leaf instance.
        """
        return super().__new__(cls, *args)

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Return ``self`` — the node IS the value.

        Annotated ``IrSelf`` (not ``Self``) so action-leaves built on the
        scalar tier (``IrOp``, ``IrChild``, ``IrIndex``) can override with
        their own result types — they ARE their payload but do not
        self-evaluate.

        :returns: ``self``.
        """
        return self

    def __eq__(self, other: object) -> bool:
        """Type-aware equality: distinct leaf kinds never compare equal.

        ``IrLiteral('x') != IrRuleRef('x')`` even though each equals plain
        ``'x'`` — otherwise same-payload leaves of different kinds would collide
        in structural equality/hashing. Falls back to the primitive's equality
        (so a leaf still matches its plain-``str``/``int`` value).

        :param other: The value to compare against.
        :returns: ``True`` when equal under the rules above.
        """
        if type(self) is type(other):  # hot path: same leaf kind, skip isinstance
            return super().__eq__(other)
        if isinstance(other, IrScalar):  # distinct leaf kinds never compare equal
            return False
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__`, kept consistent with it.

        ``str``/``int`` supply their own ``__ne__`` (which ignores the
        leaf-kind check), so without this override ``a != b`` would disagree
        with ``not (a == b)`` for distinct same-payload leaves.

        :param other: The value to compare against.
        :returns: ``True`` when not equal under :meth:`__eq__`.
        """
        return not self == other

    def __hash__(self) -> int:
        """Hash by primitive payload, so a leaf matches its plain value as a key.

        :returns: The native ``str``/``int`` hash of the payload.
        """
        return super().__hash__()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Install the bound primitive's C-level ``__hash__`` slot on the subclass.

        A leaf is keyed in dicts/sets constantly; the inherited Python
        :meth:`__hash__` wrapper costs a frame per probe. Binding the bare
        ``str``/``int`` hash slot here (rather than in the class body) gives the
        zero-frame C hash without the bare-slot assignment tripping the override
        type-checker — mirroring how :class:`IrNamedTuple` installs accessors in
        ``__init_subclass__``. Consistent with :meth:`__eq__`: equal leaves share
        the payload hash; distinct leaf kinds may collide (harmless).

        :param kwargs: Forwarded to ``super().__init_subclass__``.
        """
        super().__init_subclass__(**kwargs)
        if cls._bound in (str, int):
            setattr(cls, "__hash__", cls._bound.__hash__)

    def __repr__(self) -> str:
        """Codegen repr: ``ClassName(payload)`` via the primitive's ``repr``.

        ``self._bound(self)`` strips the subclass to a plain ``str``/``int`` so
        ``!r`` renders the bare payload (quoted string / bare int), not a
        recursive node repr.

        :returns: Constructor call reproducing this node.
        """
        return f"{type(self).__name__}({self._bound(self)!r})"


class IrStr(IrScalar, str):
    """``IrSelf + str`` value leaf — the node IS the string.

    Multi-inherits :class:`IrScalar` and ``str`` so instances are both IR nodes
    and native strings. ``_bound`` is set explicitly (no PEP 695 type params).

    **Design note:** do **not** write ``IrLeaf[str]`` — ``str`` violates the
    ``Ir_co: IrSelf`` bound and triggers "mutually incompatible bases".
    """

    _bound: ClassVar[type[str]] = str


class IrInt(IrScalar, int):
    """Int-typed value leaf — the node IS the integer. Sibling of :class:`IrStr`.

    ``_bound`` is set explicitly (no PEP 695 type params).
    """

    _bound: ClassVar[type[int]] = int

    def __str__(self) -> str:
        """The decimal digits of this value.

        ``int`` renders through ``__repr__``, which :class:`IrScalar` repurposes
        for codegen, so without this an ``IrInt`` would stringify to its
        constructor form. Mirrors :meth:`IrChr.__str__`.

        :returns: ``str(int(self))``.
        """
        return str(int(self))


def glyph(ordinal: int) -> str:
    """``chr(ordinal)``, refusing a value past Unicode by name.

    An ordinal only has to be a code point where it becomes a character; an
    encoding is free to give a larger one meaning of its own, so the check
    belongs here and not on the leaf's constructor.
    """
    if not 0 <= ordinal <= 0x10FFFF:
        raise UnsupportedConstructError(
            f"ir: code point {ordinal} (0x{ordinal:X}) is past the top of the "
            "Unicode range (0x10FFFF) — it spells no character"
        )
    return chr(ordinal)


class IrChr(IrInt):
    """A code point — build from a 1-char glyph or an int; stores the ordinal."""

    def __new__(cls, value: int | str = 0) -> Self:
        """Build from a 1-char glyph or an int.

        :raises UnsupportedConstructError: If a string of length != 1 is given.
        """
        if isinstance(value, str):
            if len(value) != 1:
                msg = f"IrChr expects one glyph, got {value!r}"
                raise UnsupportedConstructError(msg)
            value = ord(value)
        return super().__new__(cls, value)

    def __str__(self) -> str:
        """The raw glyph for this code point — the neutral ``IrUnicode.spell``.

        This ``chr`` is the neutral, canonical spelling (``IrUnicode`` is the
        default encoding); per-flavour *escaping* is applied at emit by the
        flavour's ``EscapeCodec``, never by the leaf, so the canonical IR stays
        flavour-neutral.

        :raises UnsupportedConstructError: When the ordinal is past the top of
            the Unicode range. This is the single point where an ordinal
            becomes a CHARACTER, so it is where the range is a real
            constraint — a bare ``chr()`` here handed callers of
            ``parse_grammar`` and ``compile_text`` a ``ValueError`` naming
            neither the value nor where it came from.
        """
        return glyph(int(self))

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Evaluate to the raw glyph (the neutral ``IrUnicode.spell``; see
        :meth:`__str__`) as an ``IrStr`` — emit-side use."""
        return IrStr(glyph(int(self)))


# ── Primitive tuple tier ──────────────────────────────────────────────
