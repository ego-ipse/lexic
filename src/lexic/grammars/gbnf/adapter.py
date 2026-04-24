"""GbnfAdapter composes GbnfParser and GbnfEmitter into a FlavourAdapter."""

from __future__ import annotations

from lexic.grammars.flavours import FlavourAdapter
from lexic.grammars.gbnf.emitter import GbnfEmitter
from lexic.grammars.gbnf.parser import GbnfParser


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
