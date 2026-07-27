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

import random
from collections.abc import Callable, Iterable
from typing import ClassVar, Self, cast

from lexic.ir.spine.spine import IrAtom, IrLeaf, IrNoneType
from lexic.ir.spine.records import IrNamedTuple, IrSeq
from lexic.ir.spine.scalars import IrChr, IrStr

__all__ = [
    # Concrete grammar-AST nodes (defined here)
    "IrLiteral",
    "IrCharClass",
    "IrChr",
    "IrRuleRef",
    "IrSequence",
    "IrAlternation",
    "IrBounds",
    "IrRange",
    "IrQuantifier",
    "IrItem",
    "IrAlphabet",
    "IrRule",
    "IrAst",
    "MAX_CODEPOINT",
]

MAX_CODEPOINT = 0x10FFFF
"""Highest Unicode code point — the upper bound of a char-class complement."""

_SURROGATE_LO = 0xD800
_SURROGATE_HI = 0xDFFF
"""The UTF-16 surrogate block — excised from :meth:`IrCharClass.sample`'s
interval choices (a lone surrogate has no valid UTF-8 encoding)."""

_CLASS_METACHARS = frozenset("[]^-")
"""Regex-class metacharacters that need a backslash inside ``[...]``.

``-`` is positional in Python ``re`` (literal only at class start/end), and a
bare ``--`` reads as set difference in some regex engines — a range whose LOW
BOUND is ``-`` (e.g. ``[!&--.]``) silently corrupts the class there. Escaping
the dash unconditionally is valid everywhere and position-independent."""


def _escape_regex_point(point: int) -> str:
    """Escape a single code point for safe use inside a regex ``[...]``.

    :param point: The code point to escape.
    :returns: The escaped single-member text (``\\\\``/``\\xNN``/glyph).
    """
    ch = chr(point)
    if ch == "\\":
        return "\\\\"
    if ch in _CLASS_METACHARS:
        return f"\\{ch}"
    if ch.isprintable():
        return ch
    if point <= 0xFF:
        return f"\\x{point:02x}"
    if point <= 0xFFFF:
        return f"\\u{point:04x}"
    return f"\\U{point:08x}"


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

    def __eq__(self, other: object) -> bool:
        """Equal only to the same bounds subtype with equal endpoints."""
        if type(self) is not type(other):
            return False
        return super().__eq__(other)

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__` (``tuple`` supplies its own ``__ne__``)."""
        return not self == other

    def __hash__(self) -> int:
        """Hash by endpoint tuple (defining ``__eq__`` nulls the inherited hash)."""
        return super().__hash__()

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


class IrRange(IrBounds):
    """Inclusive char range — ``IrChr`` code-point endpoints, always closed.

    Endpoints are required (no defaults): a range is always built from explicit
    code points, so there is no placeholder bound.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    lo: IrChr
    hi: IrChr


class IrCharClass(IrSeq[IrRange | IrChr], IrAtom):
    """Character class over code points — ``IrRange`` spans and single ``IrChr``.

    The node IS its element tuple: :class:`IrRange` entries for explicit
    ``x-y`` ranges, single :class:`~lexic.ir.base.IrChr` code points otherwise —
    ``[a0-9]`` → ``IrCharClass(IrChr("a"), IrRange(IrChr("0"), IrChr("9")))``.

    Brackets are NOT stored — the flavour renderer emits them. Negation is NOT
    stored — ``[^...]`` parses to ``IrNot(IrCharClass(...))``; the negation hands
    its mark to the class action via the argument channel. Glyph/escape spelling
    happens only at emit time, per flavour.

    Member/complement math is intrinsic: :meth:`pattern` renders the flat
    regex interior, :meth:`members` enumerates covered code points, and
    :meth:`normalized`/:meth:`complement` produce the canonical set-form and
    Unicode complement the canonicaliser relies on.
    """

    def pattern(self) -> str:
        """Flatten to a regex/source-safe interior pattern (per-member escaped).

        Each member is a code point (or a code-point range); every point is
        escaped on its own value — regex metacharacters get a backslash, a bare
        backslash doubles, non-printable points become ``\\xNN`` / ``\\uNNNN`` /
        ``\\UNNNNNNNN``.

        :returns: The flat interior pattern, members escaped for a regex class.
        """
        parts: list[str] = []
        for el in self:
            if isinstance(el, IrRange):
                parts.append(
                    f"{_escape_regex_point(int(el.lo))}-{_escape_regex_point(int(el.hi))}"
                )
            else:
                parts.append(_escape_regex_point(int(el)))
        return "".join(parts)

    def sample(self, rng: random.Random) -> int:
        """Pick one covered code point uniformly, without materialising members.

        A complement class can span the whole Unicode range; enumerating its
        members would be prohibitive, so this samples by interval instead. The
        UTF-16 surrogate block (U+D800-U+DFFF) is excluded from the intervals
        sampled from — a lone surrogate has no valid UTF-8 encoding, so
        ``chr()`` of one would fail a text round-trip.

        :param rng: The random source.
        :returns: A covered code point.
        """
        intervals = self._desurrogated_intervals()
        sizes = [hi - lo + 1 for lo, hi in intervals]
        lo, hi = rng.choices(intervals, weights=sizes)[0]
        return rng.randint(lo, hi)

    def _desurrogated_intervals(self) -> "list[tuple[int, int]]":
        """The interval cover with the UTF-16 surrogate block excised.

        An interval straddling the block splits into its two flanking pieces;
        one wholly inside the block is dropped. Falls back to the raw cover in
        the degenerate all-surrogate case, so ``sample`` never raises on an
        empty choice set. The represented set itself (:meth:`intervals`,
        :meth:`complement`, :meth:`members`, :meth:`normalized`) is unaffected —
        only sampling avoids the block.

        :returns: The interval cover, surrogate points removed.
        """
        cleaned: list[tuple[int, int]] = []
        for lo, hi in self.intervals():
            if hi < _SURROGATE_LO or lo > _SURROGATE_HI:
                cleaned.append((lo, hi))
                continue
            if lo < _SURROGATE_LO:
                cleaned.append((lo, _SURROGATE_LO - 1))
            if hi > _SURROGATE_HI:
                cleaned.append((_SURROGATE_HI + 1, hi))
        return cleaned or self.intervals()

    def members(self) -> list[int]:
        """Enumerate every code point the class covers, in element order.

        Ranges expand to all endpoints inclusive; single ``IrChr`` members
        contribute one point each.

        .. warning::
           Do **not** call on a Unicode-scale class (e.g. a ``[^...]``
           complement, which can span ~1.1M points): the returned list holds
           one entry per covered point. Set/merge math should go through
           :meth:`intervals` / :meth:`from_intervals`, which stay in the
           interval domain.

        :returns: The covered code points, ranges expanded.
        """
        points: list[int] = []
        for el in self:
            if isinstance(el, IrRange):
                points.extend(range(int(el.lo), int(el.hi) + 1))
            else:
                points.append(int(el))
        return points

    @staticmethod
    def _coalesce(raw: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Sort ``raw`` spans and merge overlapping/adjacent ones into a cover.

        The single home for the interval merge algorithm — :meth:`intervals`
        and :meth:`from_intervals` both call it, and so does the canonicaliser
        (via those). Shared so the sort+merge lives in exactly one place.

        :param raw: Unordered ``(lo, hi)`` inclusive spans (may overlap).
        :returns: The minimal sorted disjoint cover.
        """
        merged: list[tuple[int, int]] = []
        for lo, hi in sorted(raw):
            if merged and lo <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        return merged

    def intervals(self) -> list[tuple[int, int]]:
        """Return the sorted, coalesced ``(lo, hi)`` inclusive interval cover.

        Overlapping or adjacent spans merge, so the result is a minimal
        disjoint cover of the class in ascending code-point order. This is the
        Unicode-safe view of the class's membership — it never materialises
        individual points, so it is the right basis for set/merge math.

        :returns: The minimal sorted interval cover.
        """
        raw: list[tuple[int, int]] = []
        for el in self:
            if isinstance(el, IrRange):
                raw.append((int(el.lo), int(el.hi)))
            else:
                raw.append((int(el), int(el)))
        return self._coalesce(raw)

    @classmethod
    def from_intervals(cls, spans: Iterable[tuple[int, int]]) -> IrCharClass:
        """Build a normalised class from ``(lo, hi)`` intervals, coalescing first.

        Members are constructed directly (``IrChr`` for a single point, an
        ``IrRange`` for a wider span) from the coalesced cover — no per-point
        materialisation. The result is already in :meth:`normalized` form.

        :param spans: ``(lo, hi)`` inclusive intervals (may overlap/repeat).
        :returns: The canonical-form class over the union of ``spans``.
        """
        return cls(*(cls._span(lo, hi) for lo, hi in cls._coalesce(list(spans))))

    @staticmethod
    def _span(lo: int, hi: int) -> IrRange | IrChr:
        """A single code point renders as ``IrChr``; a wider span as ``IrRange``."""
        return IrChr(lo) if lo == hi else IrRange(IrChr(lo), IrChr(hi))

    def normalized(self) -> "IrCharClass":
        """Return the canonical set-form — deduped, sorted, ranges coalesced.

        Members are collapsed to their minimal disjoint interval cover; each
        run of one code point becomes an ``IrChr``, each wider run an
        ``IrRange``. Two classes describing the same set compare equal after
        this.

        :returns: The canonical-form character class.
        """
        return IrCharClass(*(self._span(lo, hi) for lo, hi in self.intervals()))

    @property
    def is_any(self) -> bool:
        """Whether this class covers the whole Unicode range — the ``.`` class.

        ``.`` (any character) canonicalises to the positive full-span class
        ``[0, MAX_CODEPOINT]`` (via ``IrNot(IrCharClass())`` → :meth:`complement`),
        indistinguishable in the IR from ``[^]`` or ``[\\x00-\\U0010ffff]``. A
        flavour whose surface has an any-char token (GBNF ``.``) reads this to
        restore that spelling on emit.

        :returns: ``True`` iff the coalesced cover is exactly ``[(0, MAX_CODEPOINT)]``.
        """
        return self.intervals() == [(0, MAX_CODEPOINT)]

    @property
    def is_empty(self) -> bool:
        """Whether this class has no members — the empty set.

        ``IrNot(IrCharClass())`` (the raw, un-canonicalised parse of ``.`` /
        ``[^]``) negates the empty class, so it denotes any character; a flavour
        with a ``.`` surface reads this on emit to restore that spelling even off
        the non-canonical ``parse_grammar`` seam (the canonical full-span form is
        :meth:`is_any`).

        :returns: ``True`` iff the class has no ``IrRange``/``IrChr`` members.
        """
        return len(self) == 0

    def complement(self) -> "IrCharClass":
        """Return the positive canonical-form class over the Unicode complement.

        The complement is taken against ``[0, MAX_CODEPOINT]`` — every code
        point NOT in this class, as coalesced ``IrRange``/``IrChr`` spans. Used
        by the canonicaliser to rewrite ``IrNot(charclass)`` to positive spans
        (ABNF cannot express negation).

        :returns: The complement class in canonical form.
        """
        spans: list[IrRange | IrChr] = []
        cursor = 0
        for lo, hi in self.intervals():
            if lo > cursor:
                spans.append(self._span(cursor, lo - 1))
            cursor = max(cursor, hi + 1)
        if cursor <= MAX_CODEPOINT:
            spans.append(self._span(cursor, MAX_CODEPOINT))
        return IrCharClass(*spans)


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
        :returns: ``True`` when ``other`` is an ``IrRule`` with equal name and body.
        """
        if not isinstance(other, IrRule):
            return False
        return self.name == other.name and self.body == other.body

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__` (``tuple`` supplies its own ``__ne__``)."""
        return not self == other

    def __hash__(self) -> int:
        """Hash by ``(name, body)`` — consistent with :meth:`__eq__`."""
        return hash((self.name, self.body))


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
