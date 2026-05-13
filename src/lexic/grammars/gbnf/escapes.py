"""GbnfEscapes —  GBNF escape codec.

Also declares the GBNF escape codec — `GbnfEscapes(EscapeCodec)` — at module
level, alongside `GBNF_ESCAPES` and the convenience aliases
`decode_gbnf_escapes` / `encode_gbnf_escapes`.  This is the single home for
all GBNF flavour declarations.
"""

from __future__ import annotations

from lexic.ir.escapes import EscapeCodec


class GbnfEscapes(EscapeCodec):
    """GBNF escape tables for quoted string literals.  Algorithm is inherited from EscapeCodec."""

    SHORT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
    HEX_ESCAPES = (("x", 2), ("u", 4), ("U", 8))


GBNF_ESCAPES = GbnfEscapes()
