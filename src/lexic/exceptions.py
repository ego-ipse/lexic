"""Custom exceptions for Lexic."""

from __future__ import annotations


class LexicError(Exception):
    """Base class for all lexic errors."""


class UnsupportedConstructError(LexicError):
    """A grammar construct is not supported by the current flavour or IR shape.

    Raised by:
    - GBNF parser (token syntax, unknown flavour)
    - Atom dispatch tables (unknown atom type — internal consistency)
    - Codegen cross-check (pattern uses features the target emitter cannot emit)
    """


class IrKeyError(UnsupportedConstructError, KeyError):
    """A key miss in an :class:`~lexic.ir.mapping.IrMap` lookup.

    Doubly typed: library code catching :exc:`UnsupportedConstructError` and
    ``Mapping`` protocol machinery catching :exc:`KeyError` (e.g.
    ``Mapping.get``) both work.
    """


class FieldValidationError(LexicError):
    """A hand-constructed model field violates its grammar-intrinsic contract.

    Raised by :meth:`lexic.model.GrammarModel.__new__` on the hand-construction
    path when a field's value fails its IR-intrinsic per-field check — a
    char-class field with an out-of-class character or wrong length, a
    ``Literal[...]`` value outside its arm set, a model/models field holding a
    non-model, or a missing required field. The trusted parse paths
    (``_from_parts``/``fast_construct``) bypass ``__new__`` and are unchecked.
    """
