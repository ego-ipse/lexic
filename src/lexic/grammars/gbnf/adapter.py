"""GbnfAdapter composes GbnfParser and GbnfEmitter into a FlavourAdapter.

Also declares the GBNF escape codec — `GbnfEscapes(EscapeCodec)` — at module
level, alongside `GBNF_ESCAPES` and the convenience aliases
`decode_gbnf_escapes` / `encode_gbnf_escapes`.  This is the single home for
all GBNF flavour declarations.
"""

from __future__ import annotations

from lexic.grammars.flavours import FlavourAdapter
from lexic.grammars.gbnf.emitter import GbnfEmitter
from lexic.grammars.gbnf.parser import GbnfParser
from lexic.ir.escapes import EscapeCodec


class GbnfEscapes(EscapeCodec):
    """GBNF escape tables for quoted string literals.  Algorithm is inherited from EscapeCodec."""

    SHORT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}
    HEX_ESCAPES = (("x", 2), ("u", 4), ("U", 8))


GBNF_ESCAPES = GbnfEscapes()
decode_gbnf_escapes = GBNF_ESCAPES.decode
encode_gbnf_escapes = GBNF_ESCAPES.encode


class GbnfAdapter(FlavourAdapter):
    """GBNF flavour adapter.

    Implements FlavourAdapter (duck-typed against grammars.FlavourAdapter).
    """

    name = "gbnf"
    extensions: tuple[str, ...] = (".gbnf",)

    def __init__(self) -> None:
        self.parser = GbnfParser()
        # TODO(slice-b-phase-2): GbnfEmitter() becomes no-arg when emit(specs)
        # is the primary API and emit_rule(spec) takes an explicit spec arg.
        self.emitter = GbnfEmitter([])
