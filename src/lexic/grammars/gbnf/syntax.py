"""GBNF flavour syntax — escape tables + bracket canonicalisation.

GbnfEscapes subclasses EscapeCodec (lexic.ir.escapes); the GBNF flavour
declares only its escape tables.  encode/decode/read_escape are inherited
from the ABC.  Module-level `decode_gbnf_escapes`/`encode_gbnf_escapes` are
bound to a canonical instance — convenient for module-level functional
callers; behaviour is identical to `GBNF_ESCAPES.decode`/`.encode`.
"""

from __future__ import annotations

from lexic.ir.escapes import EscapeCodec


class GbnfEscapes(EscapeCodec):
    """GBNF escape tables.  Algorithm is inherited."""

    SHORT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
    HEX_ESCAPES = (("x", 2), ("u", 4), ("U", 8))


GBNF_ESCAPES = GbnfEscapes()
decode_gbnf_escapes = GBNF_ESCAPES.decode
encode_gbnf_escapes = GBNF_ESCAPES.encode


def gbnf_bracket_to_canonical(pattern: str) -> str:
    """Convert a GBNF bracket expression to canonical POSIX form.

    Today GBNF brackets are already POSIX-compatible for ASCII patterns;
    this is identity. Future Unicode-property classes (\\p{...}) would be
    expanded here.
    """
    return pattern


def canonical_to_gbnf_bracket(pattern: str) -> str:
    """Inverse of gbnf_bracket_to_canonical."""
    return pattern
