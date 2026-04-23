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


class GrammarAuthoringError(LexicError):
    """A grammar is malformed in a way the author should fix.

    Stub in Slice B; wired by Slice C (discriminator ambiguity, sidecar refs
    to unknown classes/fields) and Slice D (@grammar_rule decorator misuse).
    """


class FieldValidationError(LexicError):
    """A parsed field fails the emitted Pydantic constraints.

    Stub in Slice B; wired by Slice C when Annotated[str, StringConstraints(...)]
    emission lands.
    """
