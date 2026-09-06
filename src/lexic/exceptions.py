"""Custom exceptions for Lexic."""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple


class Refusal(NamedTuple):
    """Where a refused parse stopped, and what it could have accepted there.

    The readout a caller needs to *draw* a refusal: a caret, the rule that was
    being matched, and the characters that would have continued. Deliberately
    made of primitives — this is a boundary record on the public error surface,
    and :mod:`lexic.exceptions` imports nothing from lexic (everything else
    imports IT), so a ``CharSet`` cannot live here. ``negated`` preserves the
    engine's polarity rather than enumerating a co-finite set.

    :ivar pos: The offset the parse stopped at, or ``-1`` when unknown. This is
        where the failing construct was attempted FROM — see
        :class:`~lexic.parsing.pda.core.errors.PdaFail`, which it is built from.
    :ivar rule: The grammar rule being matched there, or ``""`` when the stop
        was not inside a named rule.
    :ivar expected: The characters that would have been accepted; empty when
        the engine could not say.
    :ivar negated: ``True`` when :attr:`expected` is an EXCLUSION set — every
        character *except* these.
    :ivar undecidable: ``True`` when the predictive route did not fail but
        BAILED — it found the position genuinely undecidable and handed the
        question to the gated engine. A refusal carrying this is about
        ambiguity, not about a character the grammar could not derive.
    """

    pos: int = -1
    rule: str = ""
    expected: tuple[str, ...] = ()
    negated: bool = False
    undecidable: bool = False


class SemanticVerdict(NamedTuple):
    """One target-semantic refusal, held as a value rather than raised.

    A target's semantic contract is settled AFTER its lower syntax has been
    recognized, so a refusal has to survive as data until then: an exception
    thrown mid-parse would report a semantic failure over text that turns out
    not to parse at all, and syntax wins. Like :class:`Refusal`, this is a
    boundary record on the public error surface, so it is made of primitives —
    :mod:`lexic.exceptions` imports nothing from lexic.

    ``(pos, order)`` is a stable total key: it orders the verdicts of one
    document, and it orders the verdicts a parallel split's fragments each
    recorded independently, without either side consulting the other.

    :ivar sort: The declared verdict sort — which of the target's checks
        refused (an unsupported knob, a repeated decoded key, a missing
        required field, a target-shape mismatch, a root cross-field failure).
    :ivar words: Why it refused, in the target's own words.
    :ivar pos: The offset the refused occurrence began at, or ``-1`` when the
        check belongs to root finalization rather than to a position.
    :ivar order: Which check refused first among those sharing ``pos`` — the
        target's own declaration order.
    """

    sort: str
    words: str
    pos: int = -1
    order: int = 0


class LexicError(Exception):
    """Base class for all lexic errors."""


class UnsupportedConstructError(LexicError):
    """A grammar construct is not supported by the current flavour or IR shape.

    Raised by:
    - GBNF parser (token syntax, unknown flavour)
    - Atom dispatch tables (unknown atom type — internal consistency)
    - Codegen cross-check (pattern uses features the target emitter cannot emit)
    - The parse products, when an input does not derive (or derives two ways)

    :ivar readout: On a refused *parse*, the :class:`Refusal` describing where
        it stopped; ``None`` on every other use. Additive by construction —
        the message is unchanged and every existing raise site still passes a
        message alone.
    """

    __slots__ = ("readout",)

    def __init__(self, message: str, readout: Refusal | None = None) -> None:
        """Bind the human-readable reason and, for a parse, its readout."""
        super().__init__(message)
        self.readout = readout


class IrKeyError(UnsupportedConstructError, KeyError):
    """A key miss in an :class:`~lexic.ir.action.mapping.IrMap` lookup.

    Doubly typed: library code catching :exc:`UnsupportedConstructError` and
    ``Mapping`` protocol machinery catching :exc:`KeyError` (e.g.
    ``Mapping.get``) both work.
    """


class TargetRefusalError(LexicError):
    """A document parses, and the target it was reduced INTO refuses its meaning.

    The division of labour with :exc:`UnsupportedConstructError` is the point:
    that one says a construct cannot run here — a grammar shape, a binding
    mismatch, a defective compiled artefact, a text that does not derive.
    This one says the text derived, the compiled product ran, and the target's
    own semantic contract rejected the result.

    :ivar verdicts: Every :class:`SemanticVerdict` the run recorded, in
        ``(pos, order)`` order. The earliest is the one the message states;
        the rest are kept because a caller fixing a document wants all of
        them, not one per re-run.
    """

    __slots__ = ("verdicts",)

    def __init__(self, message: str, verdicts: Sequence[SemanticVerdict] = ()) -> None:
        """Bind the human-readable reason and the ordered verdicts behind it."""
        super().__init__(message)
        self.verdicts = tuple(verdicts)


class FieldValidationError(LexicError):
    """A hand-constructed model field violates its grammar-intrinsic contract.

    Raised by :meth:`lexic.model.GrammarModel.__new__` on the hand-construction
    path when a field's value fails its IR-intrinsic per-field check — a
    char-class field with an out-of-class character or wrong length, a
    ``Literal[...]`` value outside its arm set, a model/models field holding a
    non-model, or a missing required field. The trusted parse paths
    (``_from_values``/``fast_construct``) bypass ``__new__`` and are unchecked.
    """
