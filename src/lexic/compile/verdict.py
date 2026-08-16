"""Verdict — one attempt's outcome as a value, refusal included.

An attempt through this seam ends one of two ways: a product, or a raised
:class:`~lexic.exceptions.LexicError`. An exception is not a value. It cannot
be held beside three others, compared, kept, or drawn, so a caller weighing
several candidate readers over one text has a product for the accepts and
nothing at all for the refusals — which is most of what it wanted to know.

A :class:`Verdict` is that missing half: accepted or refused, the engine's own
words verbatim, the readout the refusal carried, and what the attempt cost.

Deliberately absent: which candidates to try, in what order, memoised how,
re-run when — and the attempt itself. That is policy, it belongs to whoever
owns the session, and it is the reason no reader registry lands here: a
registry of "the readers we happen to ship" privileges the formulations lexic
happens to carry, which every mechanism in this package refuses to do.
"""

from __future__ import annotations

from typing import ClassVar, Self

from lexic.exceptions import LexicError, Refusal, UnsupportedConstructError
from lexic.ir import IrNamedTuple


class Verdict(IrNamedTuple[bool, str, Refusal, float]):
    """What one attempt said, as a value.

    :ivar accepted: ``True`` when the attempt produced its product.
    :ivar words: The engine's message, verbatim — empty on an accept. Never
        re-worded: a caller drawing two refusals side by side is comparing what
        the engine said, and a paraphrase compares the paraphraser.
    :ivar readout: The refusal's :class:`~lexic.exceptions.Refusal` — where it
        stopped and what would have continued. The default ``Refusal()``
        (``pos == -1``) is the honest empty: the engine said nothing about
        position, which every accept and some refusals do.
    :ivar seconds: What the attempt cost, as its caller measured it. Comparable
        across attempts of the same run, and meaningless across machines —
        which is why nothing here measures it for you.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    accepted: bool
    words: str
    readout: Refusal = Refusal()
    seconds: float = 0.0

    @classmethod
    def accept(cls, seconds: float) -> Self:
        """The verdict of an attempt that produced its product.

        :param seconds: What the attempt cost.
        :returns: An accepted verdict, with no words and no readout.
        """
        return cls(True, "", Refusal(), seconds)

    @classmethod
    def refuse(cls, error: LexicError, seconds: float) -> Self:
        """The verdict of an attempt that raised — the error kept as a value.

        :param error: The exception the attempt raised.
        :param seconds: What the attempt cost before it raised.
        :returns: A refused verdict carrying the error's own message and, when
            it is a parse refusal, its readout.
        """
        if isinstance(error, UnsupportedConstructError) and error.readout is not None:
            return cls(False, str(error), error.readout, seconds)
        return cls(False, str(error), Refusal(), seconds)
