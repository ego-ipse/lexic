"""Depth-safe trampoline for the forest tree walks.

Right-recursive grammars produce arbitrarily deep derivation spines, so a walk
that recurses through the Python call stack overflows (a native nested-generator
forest walk dies at ~300 levels). The fix is to keep the
active pull-chain on an explicit Python list instead of the C stack.

A **cogen** is a generator (an IR node's ``__iter__``) that, rather than
iterating a child directly, yields commands to the :class:`Trampoline` driver:

- ``(ADVANCE, child)`` — resume child generator ``child`` to its next value; the
  driver sends back that value, or :data:`EXHAUSTED` when ``child`` is done.
- ``(EMIT, value)`` — ``value`` is one of my outputs.

Suspended cogens live as locals in their parent generator's frame, so the
driver's list holds only the live spine — depth lives in a list, never the C
stack. The behaviour stays on ``__iter__`` (an allowed dunder); the driver's
loop is :meth:`Trampoline.__iter__`.
"""

from __future__ import annotations

from typing import Generator, Iterable, Iterator, cast

from lexic.ir import IrLeaf, IrSelf

ADVANCE = object()
"""Command tag: ``(ADVANCE, child)`` — drive ``child`` to its next value."""

EMIT = object()
"""Command tag: ``(EMIT, value)`` — ``value`` is one of my outputs."""

EXHAUSTED = object()
"""Sent into a parent cogen when an advanced child cogen is exhausted."""

# A command's payload is heterogeneous — a child cogen (ADVANCE) or an emitted
# IrSelf value (EMIT) — so it is typed ``object`` and narrowed at the seam.
_Command = tuple[object, object]
_CoGen = Generator[_Command, object, None]


class Trampoline(IrLeaf[IrSelf, IrSelf]):
    """Drive a root cogen to a flat, depth-safe lazy sequence of its emits.

    Keeps the active pull-chain on an explicit Python list, so spine depth lives
    in the list rather than the C stack. A cogen that yields ``(ADVANCE, child)``
    is suspended while ``child`` runs until it ``EMIT``\\ s (the value delivered to
    the parent) or is exhausted (:data:`EXHAUSTED` delivered); a root ``EMIT`` is
    yielded out and the root re-advanced for the next value.

    :ivar _root: The root cogen node to drive (an :class:`~lexic.ir.base.IrLeaf`
        whose ``__iter__`` yields trampoline commands).
    """

    __slots__ = ("_root",)

    _root: IrSelf

    def __init__(self, root: IrSelf) -> None:
        """:param root: the root cogen node to drive."""
        self._root = root

    def __iter__(self) -> Iterator[IrSelf]:
        """Yield the root cogen's emitted values lazily, with O(1) C-stack depth.

        :returns: An iterator over the root cogen's emitted values.
        """
        stack: list[_CoGen] = [cast(_CoGen, iter(cast(Iterable[_Command], self._root)))]
        to_send: object = None
        while stack:
            top = stack[-1]
            try:
                kind, payload = top.send(to_send)
            except StopIteration:
                stack.pop()
                to_send = EXHAUSTED
                continue
            if kind is ADVANCE:
                stack.append(cast(_CoGen, payload))
                to_send = None
            else:  # EMIT
                stack.pop()
                if stack:
                    to_send = payload
                else:
                    yield cast(IrSelf, payload)
                    stack.append(top)  # re-advance the root for the next value
                    to_send = None
