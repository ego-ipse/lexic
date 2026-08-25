"""Shared construction for tests that wrap an existing ``ReduceFold``'s
already-compiled state into a subclass instance without recompiling it.

Both ``test_fold_merge_law.py`` (``Recorder``, which observes a fold) and
``test_fold_refusals.py`` (``_Probe``, which exposes two private methods
publicly) need the same five-attribute carry; this is the one place it's
written. ``CarriesFoldState`` sets ``_scratch`` from ITS OWN method (rather
than a free function reaching into a sibling instance), which is what keeps
that one assignment inside the ``ReduceFold`` hierarchy it belongs to.

``count_pool_entries`` is the parallel-fold engagement witness every I22
step-4 pin needs: ``PoolLease.__enter__`` is a dunder, so counting it is not
a protected-access concern the way counting ``ReduceFold._fold_unit`` would
be, and ``reduce()`` only ever enters a pool when it actually partitions.
"""

from __future__ import annotations

import threading
from typing import Self

import pytest

from lexic.compile.reduce.fold import ReduceFold
from lexic.parsing.parallel.pool import PoolLease, WorkPool


class CarriesFoldState(ReduceFold):
    """A ``ReduceFold`` built by carrying an existing fold's compiled state.

    Never through ``ReduceFold.__init__``, which recompiles ``tables`` from
    ``moments`` — a cost this construction path exists specifically to skip.
    """

    @classmethod
    def carrying(cls, source: ReduceFold) -> Self:
        """A fresh ``cls`` instance carrying ``source``'s ``tables``/``plan``.

        :param source: The fold whose ``tables``/``plan``/``reducer`` to reuse.
        :returns: A ``cls`` instance with its own fresh thread-local scratch.
        """
        self = cls.__new__(cls)
        self.reducer = source.reducer
        self.plan = source.plan
        self.raw_literals = source.raw_literals
        self.tables = source.tables
        self._scratch = threading.local()
        return self


def count_pool_entries(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Patch ``PoolLease.__enter__`` with a call counter.

    :param monkeypatch: The caller's fixture (the patch is undone with it).
    :returns: A one-element mutable box (``[count]``) the caller reads
        after each call under test — a fresh call site re-reads ``box[0]``
        after zeroing it, since the patch itself stays installed for the
        whole test.
    """
    box = [0]
    original = PoolLease.__enter__

    def _counted(self: PoolLease) -> WorkPool:
        box[0] += 1
        return original(self)

    monkeypatch.setattr(PoolLease, "__enter__", _counted)
    return box
