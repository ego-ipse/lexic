"""IR AST node dataclasses — primitive node model.

Nodes *are* their payload:

- str-leaves subclass :class:`str` (``IrStr`` tier);
- variadic collections subclass :class:`tuple` (``IrSeq`` tier);
- fixed-arity records are :class:`IrNamedTuple` named tuples.

The abstract spine — :class:`IrSelf`, :class:`IrNode`, :class:`IrLeaf`,
:class:`IrAtom`, the primitive bases :class:`IrScalar`/:class:`IrStr`/
:class:`IrInt`/:class:`IrTuple`/:class:`IrNamedTuple`, and the absence sentinel
:data:`IrNone` — lives in :mod:`lexic.ir.base` and is re-exported here so that
``from lexic.ir.grammar.nodes import IrSelf`` keeps working. This module defines the
*concrete* grammar-AST nodes built on those bases.

Every IR node implements the structural protocol from :class:`IrSelf`:

- ``__call__(d, n, nc) -> Self``       identity evaluation
- ``eval(d, n, nc) -> Ir_co``          action-body protocol
- ``children() -> Sequence[Ir_co]``    children in traversal order
- ``rebuild(new_children) -> Self``    reconstruct under transformation

``__repr__`` is codegen: every node reproduces its own constructor call.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar, Self, cast

from lexic.ir.spine.records import IrNamedTuple, IrSeq
from lexic.ir.spine.scalars import IrChr, IrStr
from lexic.ir.spine.spine import IrAtom, IrLeaf, IrNone, IrNoneType

__all__ = [
    # Concrete grammar-AST nodes (defined here)
    "IrLiteral",
    "IrChr",
    "IrRuleRef",
    "IrSequence",
    "IrAlternation",
    "IrBounds",
    "IrQuantifier",
    "IrItem",
    "IrAlphabet",
    "IrRule",
    "IrAst",
]

# ── Concrete str-leaf atoms ───────────────────────────────────────────


class IrLiteral(IrStr, IrAtom):
    """Literal string. The string itself is the payload (escapes already decoded).

    Carries a dual role in the IR:

    - As a grammar AST leaf: the literal characters that must appear verbatim.
    - As an action-language constant: a baked-in string an action body returns.

    The two roles are distinguished at eval time by the ``nc`` parameter — see
    the IR-shapes wiki entry.  Both roles produce the same ``str`` value, so
    the same node class serves both.
    """


class IrRuleRef(IrStr, IrAtom):
    """Reference to another rule. The string is the rule name.

    Used in rule bodies to denote a non-terminal; the name matches the
    ``IrRule.name`` of the referenced rule.
    """


# ── Concrete tuple-tier collections ───────────────────────────────────


class IrSequence(IrSeq["IrItem"]):
    """Concatenation (sequence) of ``IrItem`` nodes.

    Represents an ordered sequence of grammar items that must all match in
    order.  Corresponds to the ``items`` tuple in a single alternation arm.
    A homogeneous :class:`IrSeq` of ``IrItem``.

    Authoring coercion: accepts ``IrItem | IrAtom`` per element — a bare
    :class:`IrAtom` (``IrLiteral``, ``IrRuleRef``, an inline ``IrAlternation``
    group…) wraps to ``IrItem(atom)`` with the unit quantifier. Unknown types
    pass through unchanged, so transformer rebuilds (elements mapped to
    ``IrStr`` mid-emit) are undisturbed. Idempotent on canonical input.
    """

    def __new__(cls, *items: IrItem | IrAtom) -> Self:
        """Construct a sequence, wrapping bare atoms to unit ``IrItem`` nodes.

        :param items: Elements — each an ``IrItem`` (kept), an ``IrAtom``
            (wrapped to ``IrItem(atom)``), or an unknown value (passed through).
        :returns: The sequence with atoms lifted to items.
        """
        coerced = tuple(
            item
            if isinstance(item, IrItem)
            else IrItem(item)
            if isinstance(item, IrAtom)
            else item
            for item in items
        )
        return super().__new__(cls, *cast("tuple[IrItem, ...]", coerced))

    def sole_ref(self) -> IrRuleRef | IrNoneType:
        """The rule this arm consists of, when it is one unit reference."""
        return self[0].unit_ref() if len(self) == 1 else IrNone


class IrAlternation(IrSeq[IrSequence], IrAtom):
    """Ordered choice (alternation) between ``IrSequence`` arms.

    Represents the ``|``-separated alternatives in a grammar rule body.
    Each arm is an ``IrSequence``; the first matching arm wins.
    A homogeneous :class:`IrSeq` of ``IrSequence``.

    Authoring coercion: accepts ``IrSequence | IrItem | IrAtom`` per arm — a
    non-sequence known type wraps via ``IrSequence(arm)`` (whose own coercion
    lifts an atom to an item), so a single-atom or single-item arm need not be
    spelled ``IrSequence(IrItem(...))``. Unknown types pass through unchanged.
    Idempotent on canonical input.
    """

    def __new__(cls, *arms: IrSequence | IrItem | IrAtom) -> Self:
        """Construct an alternation, wrapping bare arms to single-item sequences.

        :param arms: Arms — each an ``IrSequence`` (kept), an ``IrItem`` or
            ``IrAtom`` (wrapped via ``IrSequence``), or an unknown value
            (passed through).
        :returns: The alternation with arms lifted to sequences.
        """
        coerced = tuple(
            arm
            if isinstance(arm, IrSequence)
            else IrSequence(arm)
            if isinstance(arm, (IrItem, IrAtom))
            else arm
            for arm in arms
        )
        return super().__new__(cls, *cast("tuple[IrSequence, ...]", coerced))


# ── Concrete composite records ────────────────────────────────────────


class IrBounds(IrLeaf, IrNamedTuple[int, int | IrNoneType]):
    """Shared ``(lo, hi)`` bounds — type-aware equality plus in-bounds membership.

    Abstract base for :class:`IrQuantifier` (int counts) and :class:`IrRange`
    (code-point spans). The two are siblings, not a chain — neither is
    substitutable for the other. ``lo``/``hi`` are scalar payload, not IR-node
    children, so ``_child_attrs`` is empty.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int
    hi: int | IrNoneType

    def __contains__(self, value: object) -> bool:
        """``lo <= value <= hi``; ``hi=IrNone`` means unbounded above."""
        if not isinstance(value, int):
            return False
        hi = self.hi
        if isinstance(hi, IrNoneType):
            return self.lo <= value
        return self.lo <= value <= hi


class IrQuantifier(IrBounds):
    """Repetition bounds for an ``IrItem`` — int counts; ``hi`` may be ``IrNone``.

    - ``IrQuantifier(1, 1)`` — exactly once (the default; no postfix operator).
    - ``IrQuantifier(0, 1)`` — optional (``?``).
    - ``IrQuantifier(0, IrNone)`` — zero-or-more (``*``).
    - ``IrQuantifier(1, IrNone)`` — one-or-more (``+``).
    - ``IrQuantifier(m, n)`` — between ``m`` and ``n`` times.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: int = 1
    hi: int | IrNoneType = 1

    def __new__(cls, lo: int = 1, hi: int | IrNoneType = 1) -> Self:
        """Store endpoints as plain ``int`` — ``hi`` alone may stay ``IrNone``.

        Reductions build bounds from :class:`~lexic.ir.action.IrUnradix`, which
        yields :class:`~lexic.ir.base.IrInt`. The canonical quantifier shape is
        plain ``int`` counts (repr-is-codegen emits the endpoints verbatim), so
        an int-like endpoint is narrowed to ``int`` here at construction.

        :param lo: Lower bound (any int-like value).
        :param hi: Upper bound (any int-like value) or :data:`IrNone`.
        :returns: The quantifier with plain-int endpoints.
        """
        hi_val = hi if isinstance(hi, IrNoneType) else int(hi)
        return super().__new__(cls, int(lo), hi_val)

    def once(self) -> bool:
        """Whether the item occurs exactly once — no postfix operator."""
        return self.lo == 1 and self.hi == 1

    def optional(self) -> bool:
        """Whether the item occurs at most once and may be absent — ``?``."""
        return self.lo == 0 and self.hi == 1

    def unbounded(self) -> bool:
        """Whether the item may repeat without an upper bound."""
        return isinstance(self.hi, IrNoneType)

    def repeats(self) -> bool:
        """Whether the item may occur more than once, beside itself."""
        hi = self.upper()
        return hi is None or hi > 1

    def fixed(self) -> bool:
        """Whether the item occurs a fixed number of times."""
        return self.upper() == self.lo

    def upper(self) -> int | None:
        """The upper bound, or ``None`` when there is none."""
        hi = self.hi
        return None if isinstance(hi, IrNoneType) else int(hi)


class IrItem(IrNamedTuple[IrAtom, IrQuantifier], init=False):
    """An atom paired with a quantifier — the universal wrapper node.

    ``IrItem`` is the fundamental unit of a grammar sequence.  Every element
    in an ``IrSequence`` is an ``IrItem``.  The ``atom`` field accepts any
    ``IrAtom`` subclass (``IrLiteral``, ``IrCharClass``, ``IrRuleRef``,
    ``IrNot``).

    Authoring coercion: ``atom`` also accepts a bare :class:`IrSequence` inline
    group, wrapped to ``IrAlternation(seq)`` — so a quantified group need not be
    spelled ``IrItem(IrAlternation(IrSequence(...)), q)``. Any other value
    (a real ``IrAtom``, or an unknown mid-transform value) passes through.

    Children: ``atom``, ``quantifier`` (both IR nodes — the whole tuple).
    """

    atom: IrAtom
    quantifier: IrQuantifier = IrQuantifier()

    def __new__(
        cls, atom: IrAtom | IrSequence, quantifier: IrQuantifier = IrQuantifier()
    ) -> Self:
        """Construct an item, wrapping a bare sequence group to an alternation.

        :param atom: The atom, an ``IrSequence`` inline group (wrapped to
            ``IrAlternation``), or an unknown value (passed through).
        :param quantifier: Repetition bounds (defaults to the unit quantifier).
        :returns: The item with any inline-group sequence lifted to an atom.
        """
        wrapped = IrAlternation(atom) if isinstance(atom, IrSequence) else atom
        return cast(Callable[..., Self], super().__new__)(cls, wrapped, quantifier)

    def unit_ref(self) -> IrRuleRef | IrNoneType:
        """The rule this item references exactly once.

        :returns: The reference, or ``IrNone`` for any other atom or quantifier.
        """
        atom = self.atom
        if isinstance(atom, IrRuleRef) and self.quantifier.once():
            return atom
        return IrNone

    def unit_literal(self) -> IrLiteral | IrNoneType:
        """The literal this item spells exactly once, or ``IrNone``."""
        atom = self.atom
        if isinstance(atom, IrLiteral) and self.quantifier.once():
            return atom
        return IrNone


class IrAlphabet(IrNamedTuple[IrStr, IrAtom], IrAtom, init=False):
    """An atom read under a named encoding — the alphabet binding.

    Scopes a pure inner atom to an encoding: ``IrAlphabet("tokens", IrLiteral(
    "<think>"))`` is the token whose text is ``<think>``; ``IrAlphabet("tokens",
    IrCharClass(IrChr(1000)))`` is token id ``1000``; ``IrAlphabet("tokens",
    IrNot(...))`` a negated token. The wrapper is what distinguishes a literal
    read as token text from a literal read as characters — the inner node types
    are the ordinary ones (:class:`IrLiteral`, :class:`IrCharClass`,
    :class:`~lexic.ir.grammar.operators.IrNot`), so no token-specific leaf exists.

    ``encoding`` is a **name reference** (an ``IrStr`` — the :class:`IrRuleRef`
    precedent), resolved against an encoding registry, so the codec is shared,
    the canonical form stays flavour-neutral, and many encodings coexist. The
    node carries no codec and no universe: the complement / ``.`` algebra lives
    on the encoding (which owns the universe). Being an :class:`IrAtom` it rides
    :class:`IrItem` unchanged.

    Children: the single ``inner`` atom.
    Non-child payload: ``encoding`` (the registry name reference).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("inner",)
    encoding: IrStr
    inner: IrAtom

    def __new__(cls, encoding: str, inner: IrAtom) -> Self:
        """Wrap the encoding name to :class:`IrStr`; keep ``inner`` as given.

        :param encoding: The registry name of the governing encoding.
        :param inner: The pure inner atom (literal / char class / negation).
        :returns: The alphabet-bound atom.
        """
        return cast(Callable[..., Self], super().__new__)(cls, IrStr(encoding), inner)


class IrRule(IrNamedTuple[IrStr, IrAlternation, bool], init=False):
    """A named grammar rule, with a ``semantic`` flag.

    The ``body`` is always an ``IrAlternation``, even for single-arm rules
    (a single arm is an ``IrAlternation`` containing one ``IrSequence``).

    Authoring coercion: ``body`` accepts ``IrAlternation | IrSequence | IrItem
    | IrAtom`` — a non-alternation known type wraps up to a single-arm
    ``IrAlternation`` (the cascade lifting atom→item→sequence→alternation), so
    ``IrRule("cr", IrCharClass(IrChr("\\r")))`` constructs exactly the canonical
    single-arm rule. The ``IrAlternation`` check runs first (it IS-A ``IrAtom``).
    Unknown types pass through unchanged.

    ``semantic`` is ``True`` for an ordinary rule and ``False`` for a
    structural-noise rule (whitespace, delimiters, comments) — the ``@non-
    semantic`` directive and each flavour's noise declarations flag rules by
    setting it. It is **compile-channel metadata**, not grammar structure —
    like a source location — so it is excluded from ``__eq__``/``__hash__``.
    Two rules with the same name and body but different ``semantic`` flags are
    equal: the self-hosting fixpoint
    ``parse_grammar(flavour.apply(GRAMMAR), flavour) == GRAMMAR`` requires it,
    because a freshly parsed rule is ``semantic=True`` while the authored
    self-grammar flags its noise rules ``semantic=False``.

    Children: the single ``body`` ``IrAlternation``.
    Non-child payload: ``name`` (rule identifier), ``semantic`` (the flag).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)
    name: str
    body: IrAlternation
    semantic: bool = True

    def __new__(
        cls,
        name: str,
        body: IrAlternation | IrSequence | IrItem | IrAtom,
        semantic: bool = True,
    ) -> Self:
        """Construct a rule, lifting a non-alternation body to a single-arm one.

        :param name: The rule identifier.
        :param body: The rule body — an ``IrAlternation`` (kept), or an
            ``IrSequence``/``IrItem``/``IrAtom`` (wrapped up to a single-arm
            ``IrAlternation``), or an unknown value (passed through).
        :param semantic: ``False`` for a structural-noise rule; ``True`` otherwise.
        :returns: The rule with its body normalised to an ``IrAlternation``.
        """
        if isinstance(body, IrAlternation):
            alt = body
        elif isinstance(body, (IrSequence, IrItem, IrAtom)):
            alt = IrAlternation(body)
        else:
            alt = body
        return cast(Callable[..., Self], super().__new__)(cls, name, alt, semantic)

    def __eq__(self, other: object) -> bool:
        """Structural equality over ``name`` and ``body`` only.

        ``semantic`` is compile-channel metadata, excluded so the self-hosting
        fixpoint holds (see the class docstring).

        :param other: The value to compare against.
        :returns: ``True`` when ``other`` is the same rule class with equal
            name and body — the record rule's kind test, ``semantic`` aside.
        """
        if type(other) is not type(self):
            return False
        return self.name == other.name and self.body == other.body

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__` (``tuple`` supplies its own ``__ne__``)."""
        return not self == other

    def __hash__(self) -> int:
        """Hash by ``(name, body)`` — consistent with :meth:`__eq__`."""
        return hash((self.name, self.body))

    def sole_arm(self) -> tuple[IrItem, ...] | IrNoneType:
        """The items of this rule's only arm.

        :returns: The items, or ``IrNone`` when the rule has several arms.
        """
        return tuple(self.body[0]) if len(self.body) == 1 else IrNone


class IrAst(IrNamedTuple[IrSeq[IrRule], IrStr]):
    """Full grammar AST: a collection of rules plus the start-rule name.

    ``rules`` is an ``IrTuple`` of ``IrRule`` nodes (wrapped so a single
    child attribute can hold the whole collection and be replaced atomically
    by tree transformations).  ``start`` is the plain string name of the
    start rule.

    The set of structural-noise rules is **not** a field: it is derived from
    the rules' own ``semantic`` flags via the :attr:`non_semantic` property.
    Because the flag lives on :class:`IrRule` (and is excluded from its
    equality), ``IrAst`` needs no equality override — plain tuple equality over
    ``(rules, start)`` composes ``IrRule.__eq__`` element-wise, and the
    self-hosting fixpoint holds for free.

    Children: the single ``rules`` ``IrTuple``.
    Non-child payload: ``start`` (start-rule name).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("rules",)

    rules: IrSeq = IrSeq()
    start: str = ""

    @property
    def non_semantic(self) -> frozenset[str]:
        """Names of the structural-noise rules (those with ``semantic=False``).

        Derived from the rules' own flags — the single source feeding the
        codegen passes (quantifier relaxation), the binding view's
        ``semantic_dump`` filter and, for a flavour's self-grammar, its
        ``Reducer`` noise map. Keeps the
        ``@non-semantic`` directive vocabulary even though the flag's polarity
        is positive (``semantic``) on the rule.

        :returns: The frozenset of non-semantic rule names.
        """
        return frozenset(r.name for r in self.rules if not r.semantic)
