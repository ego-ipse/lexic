"""Tests for lexic.parsing.earley.trampoline — depth-safe trampoline driver.

:class:`Trampoline` keeps the active pull-chain on an explicit Python list so
the C stack depth stays O(1) regardless of cogen depth.  These tests cover:

- Simple single-cogen emit paths.
- Parent→child ``ADVANCE``/``EMIT`` delegation.
- Depth-safety: a 5000-deep chain at the DEFAULT recursion limit must not raise
  ``RecursionError``.

No grammar or parsing machinery is used here — every cogen is hand-written.
"""

from __future__ import annotations

import sys
from typing import Iterator

from lexic.ir.base import IrLeaf, IrSelf, IrSeq
from lexic.ir.nodes import IrLiteral
from lexic.parsing.earley.forest import IrStream
from lexic.parsing.earley.trampoline import ADVANCE, EMIT, EXHAUSTED, Trampoline

# ── Helpers ────────────────────────────────────────────────────────────


class _EmitCogen(IrLeaf[IrSelf, IrSelf]):
    """A minimal cogen that emits a fixed sequence of :class:`IrLiteral` values.

    :param values: The values to emit, in order.
    """

    __slots__ = ("_values",)

    _values: tuple[IrSelf, ...]

    def __init__(self, *values: IrSelf) -> None:
        """:param values: The values emitted in order."""
        self._values = values

    def __iter__(self) -> Iterator[tuple[object, object]]:
        """Yield ``(EMIT, v)`` for each stored value.

        :returns: A command iterator for the :class:`Trampoline`.
        """
        for v in self._values:
            yield (EMIT, v)


class _DelegateCogen(IrLeaf[IrSelf, IrSelf]):
    """A cogen that ``(ADVANCE, child)``\\s into ``child`` and re-emits each value.

    :param child: The child cogen to advance into.
    """

    __slots__ = ("_child",)

    _child: IrSelf

    def __init__(self, child: IrSelf) -> None:
        """:param child: the child cogen to advance into."""
        self._child = child

    def __iter__(self) -> Iterator[tuple[object, object]]:
        """Drive the child and re-emit each value received.

        :returns: A command iterator for the :class:`Trampoline`.
        """
        sub = iter(self._child)  # type: ignore[call-overload]
        received = yield (ADVANCE, sub)
        while received is not EXHAUSTED:
            yield (EMIT, received)
            received = yield (ADVANCE, sub)


class _ChainCogen(IrLeaf[IrSelf, IrSelf]):
    """A cogen that advances into ``next_cogen`` and re-emits exactly once.

    Used to build N-deep delegation chains.  The terminal cogen (where
    ``next_cogen is None``) emits the sentinel value directly.

    :param next_cogen: The next link in the chain, or ``None`` for the leaf.
    :param value: The value emitted by the leaf (only used when ``next_cogen`` is
        ``None``).
    """

    __slots__ = ("_next", "_value")

    _next: IrSelf | None
    _value: IrSelf | None

    def __init__(self, next_cogen: IrSelf | None, value: IrSelf | None = None) -> None:
        """:param next_cogen: the next link; :param value: leaf emit value."""
        self._next = next_cogen
        self._value = value

    def __iter__(self) -> Iterator[tuple[object, object]]:
        """Advance into the next link or emit the leaf value.

        :returns: A command iterator for the :class:`Trampoline`.
        """
        if self._next is None:
            # leaf — emit the sentinel
            yield (EMIT, self._value)
        else:
            sub = iter(self._next)  # type: ignore[call-overload]
            received = yield (ADVANCE, sub)
            while received is not EXHAUSTED:
                yield (EMIT, received)
                received = yield (ADVANCE, sub)


# ── Basic emit ─────────────────────────────────────────────────────────


def test_trampoline_yields_emit_values_in_order():
    """Trampoline over a single-cogen emitting a, b, c yields them in order."""
    a, b, c = IrLiteral("a"), IrLiteral("b"), IrLiteral("c")
    result = list(Trampoline(_EmitCogen(a, b, c)))
    assert result == [a, b, c]


def test_trampoline_empty_cogen_yields_nothing():
    """Trampoline over a cogen that emits nothing yields an empty sequence."""
    result = list(Trampoline(_EmitCogen()))
    assert not result


def test_trampoline_single_emit():
    """Trampoline over a cogen emitting one value yields exactly that value."""
    v = IrLiteral("x")
    result = list(Trampoline(_EmitCogen(v)))
    assert result == [v]
    assert result[0] is v


# ── Delegation (ADVANCE / child re-emit) ──────────────────────────────


def test_trampoline_delegate_flattens_child():
    """A parent that (ADVANCE, child)s and re-emits delivers the child's values."""
    a, b = IrLiteral("p"), IrLiteral("q")
    child = _EmitCogen(a, b)
    parent = _DelegateCogen(child)
    result = list(Trampoline(parent))
    assert result == [a, b]


def test_trampoline_two_level_delegation():
    """Two levels of delegation: grandparent → parent → child."""
    v = IrLiteral("z")
    child = _EmitCogen(v)
    parent = _DelegateCogen(child)
    grandparent = _DelegateCogen(parent)
    result = list(Trampoline(grandparent))
    assert result == [v]
    assert result[0] is v


def test_trampoline_delegate_empty_child():
    """A parent delegating into an empty child yields nothing."""
    parent = _DelegateCogen(_EmitCogen())
    result = list(Trampoline(parent))
    assert not result


# ── IrSeq used as source in IrStream ─────────────────────────────────


def test_trampoline_irseq_source():
    """Driving a plain IrSeq through IrStream yields its elements."""
    elems = [IrSeq(IrLiteral("a")), IrSeq(IrLiteral("b"))]
    src = IrSeq(*elems)
    stream: IrStream[IrSeq] = IrStream(src)
    result = list(stream)
    assert result == elems


# ── Depth-safety (the key property) ───────────────────────────────────


def test_trampoline_deep_chain_no_stack_overflow():
    """A 5000-deep delegation chain does NOT raise RecursionError.

    Each link only ``(ADVANCE, next_link)``s and re-emits; the leaf emits
    the sentinel.  The default ``sys.setrecursionlimit`` (usually 1000) would
    kill a naive recursive walk well before 5000 links — this test proves the
    trampoline keeps depth off the C stack.

    No ``sys.setrecursionlimit`` call, no threading.
    """
    depth = 5000
    assert depth > sys.getrecursionlimit(), (
        f"depth={depth} must exceed the default recursion limit "
        f"({sys.getrecursionlimit()}) for the test to be meaningful"
    )

    sentinel = IrLiteral("deep")

    # Build chain: each link advances into the next; leaf emits sentinel.
    cogen: IrSelf = _ChainCogen(None, sentinel)
    for _ in range(depth):
        cogen = _ChainCogen(cogen)

    result = list(Trampoline(cogen))
    assert result == [sentinel]
    assert result[0] is sentinel
