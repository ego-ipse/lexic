"""Shared construction for tests that wrap an existing ``ReduceFold``'s
already-compiled state into a subclass instance without recompiling it.

Both ``test_fold_merge_law.py`` (``Recorder``, which observes a fold) and
``test_fold_refusals.py`` (``_Probe``, which exposes two private methods
publicly) need the same five-attribute carry; this is the one place it's
written. ``CarriesFoldState`` sets ``_scratch`` from ITS OWN method (rather
than a free function reaching into a sibling instance), which is what keeps
that one assignment inside the ``ReduceFold`` hierarchy it belongs to.
"""

from __future__ import annotations

import threading
from typing import Self

from lexic.compile.reduce.fold import ReduceFold


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
