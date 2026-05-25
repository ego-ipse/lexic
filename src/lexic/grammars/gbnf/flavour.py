"""GBNF flavour for Lexic."""

from lexic.grammars.flavour import Flavour
from lexic.grammars.gbnf.emitter import GbnfEmitter
from lexic.grammars.gbnf.escapes import GBNF_ESCAPES
from lexic.grammars.gbnf.meta_grammar import META_GRAMMAR
from lexic.ir.nodes import IrQuantifier
from lexic.utils.quantifiers import quantifier_to_bounds


class GbnfFlavour(Flavour):
    """GBNF flavour"""

    name = "gbnf"
    extensions = (".gbnf",)
    meta_grammar = META_GRAMMAR
    escapes = GBNF_ESCAPES
    emitter = GbnfEmitter
    line_comment = "#"

    @staticmethod
    def parse_quantifier(text: str) -> IrQuantifier:
        """GBNF quantifier parser."""
        lo, hi = quantifier_to_bounds(text)
        return IrQuantifier(min=lo, max=hi)

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        """GBNF charclass parser."""
        # text includes the brackets: [pattern] or [^pattern]
        inner = text[1:-1]
        if inner.startswith("^"):
            return inner[1:], True
        return inner, False
