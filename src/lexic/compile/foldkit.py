"""Shared authored-fold vocabulary — the build-path unification seed.

Every hand-authored grammar+fold pair in the compile package (the notation and
the module self-grammar today, future authored surfaces tomorrow) repeats the
same idioms. This module is their single home, so a fifth authored surface
never copies a fourth variant.

Two tiers live here:

- **the pass-throughs** — :data:`ALT` (the alternation identity fold) and
  :func:`passthrough` (a single-field sequence's identity ctor);
- **the shared idioms** — the first+rest list collector (:func:`first_rest`,
  as the IR body :data:`FIRST_REST`), the int decode (the builtin ``int``, as
  :data:`DECODE_INT`), and the absent-default tail (:func:`absent_tail` + its
  :data:`ABSENT` sentinel).

The first two return non-IR values (``int``, ``tuple``) that no action-algebra
node can honestly build, so each is a :class:`IrNamed` leaf — a
registry-resolved symbol (the ``notation`` SYMBOLS whitelist precedent), the IR
form of a non-algebraic ctor read via the argument channel. The absent-default
tail stays a KEYWORD ctor (reused via :class:`~lexic.ir.base.IrLambda`): a
channel body cannot express it, since its absence fill (``IrNone``) is a
legitimate argument value in the notation. Surface-specific transforms that are
NOT shared stay honest :class:`~lexic.ir.base.IrLambda` citizens on their own
surface.
"""

from __future__ import annotations

from typing import Callable, ClassVar, Mapping, Self, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLambda, IrMap, IrNode, IrRuleRef, IrSelf, IrTuple
from lexic.parsing import ModelBody, ModelFold, RuleFold

__all__ = [
    "ABSENT",
    "ALT",
    "ALT_BODY",
    "DECODE_INT",
    "FIRST_REST",
    "FOLD_SYMBOLS",
    "IrNamed",
    "absent_tail",
    "first_rest",
    "model_fold",
    "passthrough",
    "seq",
]


# ── pass-throughs ─────────────────────────────────────────────────────────


def _none() -> None:
    """The unused alternation ctor slot (``kind == "alternation"`` ignores it)."""
    return None


ALT = RuleFold("alternation", _none, 0, ())
"""The shared alternation pass-through — the matched arm's model IS the result."""


def passthrough(v: object) -> object:
    """A single-field sequence rule's identity ctor.

    :param v: The one bound child.
    :returns: ``v`` unchanged.
    """
    return v


# ── the shared idioms (non-IR-valued ctors) ───────────────────────────────


ABSENT: object = object()
"""The shared "no value supplied" marker for an omitted trailing group.

An optional tail that matched empty folds to this (via :func:`absent_tail`);
a surface's strictness pass filters or rejects it (``notation``'s ``_arglist``
refuses a bare comma anywhere but last)."""


def first_rest(first: object, rest: Sequence[object] | None = None) -> tuple:
    """Head element prepended to the repeated tail — the list collector.

    :param first: The head element.
    :param rest: The repeated tail (``None``/empty ⇒ just the head).
    :returns: ``(first, *rest)`` as a tuple.
    """
    return (first, *(rest or ()))


def absent_tail(**kwargs: object) -> object:
    """An optional trailing group: its value, or :data:`ABSENT` when omitted.

    A kwargs ctor (not a channel body): the single optional field arrives BY
    KEYWORD when the tail matched — any value, **including
    :data:`~lexic.ir.base.IrNone`** as a legitimate argument — and an empty call
    means the tail matched nothing. The keyword mechanism is load-bearing here:
    the channel adapter fills an omitted optional with ``IrNone``, which would
    be indistinguishable from a real ``IrNone`` value, so this idiom stays a
    keyword ctor (reused via :class:`~lexic.ir.base.IrLambda`, field-name-generic
    through ``**kwargs``).

    :returns: The tail's folded value when present, else :data:`ABSENT`.
    """
    for value in kwargs.values():
        return value
    return ABSENT


FOLD_SYMBOLS: dict[str, Callable[..., object]] = {
    "int": int,
    "first_rest": first_rest,
    "passthrough": passthrough,
}
"""The curated fold-ctor registry — the no-exec boundary :class:`IrNamed`
resolves through. Every reachable name is a shared idiom callable; a surface
adds a symbol here to make it manifest-expressible."""


class IrNamed(IrNode[IrSelf, IrSelf]):
    """Named-callable fold-ctor leaf — the node IS its :data:`FOLD_SYMBOLS` key.

    The IR form of a non-algebraic ctor: on eval it resolves the key through
    :data:`FOLD_SYMBOLS` (the no-exec boundary) and applies the callable to the
    argument channel — ``FOLD_SYMBOLS[key](*nc)``. Reprable by name (unlike
    :class:`~lexic.ir.base.IrLambda`, which wraps an opaque closure), so an
    authored fold that uses only the shared vocabulary stays manifest-shaped.

    :param key: The registry key naming the shared ctor.
    """

    __slots__ = ("key",)
    _bound: ClassVar[type] = IrSelf
    key: str

    def __new__(cls, key: str, /) -> Self:
        """Wrap the registry key as an immutable leaf.

        :param key: The :data:`FOLD_SYMBOLS` key.
        :returns: The new :class:`IrNamed` leaf.
        """
        obj = object.__new__(cls)
        object.__setattr__(obj, "key", key)
        return obj

    def __repr__(self) -> str:
        """Codegen repr — ``IrNamed('<key>')``."""
        return f"IrNamed({self.key!r})"

    def __eq__(self, other: object) -> bool:
        """Structural equality over the registry key."""
        return isinstance(other, IrNamed) and other.key == self.key

    def __hash__(self) -> int:
        """Hash the registry key."""
        return hash((IrNamed, self.key))

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Resolve the key and apply its callable to the argument channel.

        The result is an opaque fold value (``int`` / ``tuple`` / the
        :data:`ABSENT` marker) the fold consumes positionally — cast to the
        ``IrSelf`` the eval protocol declares, exactly as ``load_ir`` casts its
        parse product at the fold boundary.

        :param _d: Dispatcher (unused — the callable owns its work).
        :param _n: Node (unused — arguments arrive on the channel).
        :param nc: The argument channel, in ``fields`` order.
        :returns: ``FOLD_SYMBOLS[key](*nc)``.
        :raises UnsupportedConstructError: When the key is not registered.
        """
        fn = FOLD_SYMBOLS.get(self.key)
        if fn is None:
            raise UnsupportedConstructError(
                f"foldkit: unknown fold symbol {self.key!r}"
            )
        return cast(IrSelf, fn(*nc))


FIRST_REST = IrNamed("first_rest")
"""The first+rest list collector as an IR body — see :func:`first_rest`."""

DECODE_INT = IrNamed("int")
"""The digit-run → int decode as an IR body — the builtin ``int``."""


# ── authored-fold construction ────────────────────────────────────────────


def seq(ctor: Callable[..., object] | IrSelf, n_items: int, fields: tuple) -> ModelBody:
    """A ``sequence``-kind :class:`~lexic.parsing.fold.ModelBody`.

    A plain callable is wrapped in :class:`~lexic.ir.base.IrLambda` (the
    surface-specific escape hatch); an :class:`IrSelf` (a shared idiom body) is
    carried as-is so :meth:`~lexic.parsing.fold.ModelBody.bake` maps kwargs onto
    its argument channel.

    :param ctor: The rule's model constructor — a callable or a shared IR body.
    :param n_items: Kid-slot count of the single sequence arm.
    :param fields: The bound fields, in item order.
    :returns: The sequence body.
    """
    body = ctor if isinstance(ctor, IrSelf) else IrLambda(ctor)
    return ModelBody("sequence", body, n_items, fields)


ALT_BODY = ModelBody.of(ALT)
"""The alternation pass-through as a :class:`~lexic.parsing.fold.ModelBody` —
the IrMap-authoring form of :data:`ALT` (its ctor is :data:`~lexic.ir.base.IrNone`)."""


def model_fold(bodies: Mapping[str, ModelBody]) -> ModelFold:
    """Build a :class:`~lexic.parsing.fold.ModelFold` from a name → body table.

    The single home for the "dict of :class:`~lexic.parsing.fold.ModelBody` →
    fold" construction — assembles the IR body-table (an
    :class:`~lexic.ir.mapping.IrMap`) the fold bakes on construction.

    :param bodies: Rule name → its :class:`~lexic.parsing.fold.ModelBody`.
    :returns: The configured fold.
    """
    return ModelFold(
        IrMap(*(IrTuple(IrRuleRef(name), body) for name, body in bodies.items()))
    )
