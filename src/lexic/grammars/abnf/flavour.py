"""AbnfFlavour — minimal-ABNF subset binding."""

from __future__ import annotations

from lexic.grammars.abnf.emitter import AbnfEmitter
from lexic.grammars.abnf.escapes import ABNF_ESCAPES
from lexic.grammars.abnf.meta_grammar import META_GRAMMAR
from lexic.grammars.flavour import Flavour
from lexic.ir.nodes import (
    IrAlternation,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrSequence,
    Quantifier,
)


class AbnfFlavour(Flavour):
    """Flavour for the minimal ABNF subset. See `AbnfEmitter` and `AbnfEscapes`."""

    name = "abnf"
    extensions = (".abnf",)
    meta_grammar = META_GRAMMAR
    escapes = ABNF_ESCAPES
    emitter = AbnfEmitter
    line_comment = ";"

    @staticmethod
    def parse_quantifier(text: str) -> Quantifier:
        # Forms: '*', '*N', 'N*', 'N*M', 'N'
        if text == "*":
            return Quantifier(0, None)
        if text.startswith("*"):
            return Quantifier(0, int(text[1:]))
        if "*" in text:
            lo_str, hi_str = text.split("*", 1)
            lo = int(lo_str)
            hi = int(hi_str) if hi_str else None
            return Quantifier(lo, hi)
        n = int(text)
        return Quantifier(n, n)

    @staticmethod
    def parse_charclass(text: str) -> tuple[str, bool]:
        # text is `%xNN` or `%xNN-MM`. Return canonical POSIX pattern + negated=False.
        body = text[2:]  # drop leading '%x'
        if "-" in body:
            lo_hex, hi_hex = body.split("-", 1)
            return f"{chr(int(lo_hex, 16))}-{chr(int(hi_hex, 16))}", False
        return chr(int(body, 16)), False

    @classmethod
    def normalize_literal(cls, decoded: str) -> IrLiteral | IrGroup:
        """Case-insensitive expansion: 'abc' → ([aA][bB][cC]); leave non-alpha as-is."""
        if not any(c.isalpha() for c in decoded):
            return IrLiteral(decoded)
        items: list[IrItem] = []
        for c in decoded:
            if c.isalpha():
                items.append(IrItem(atom=IrCharClass(f"{c.lower()}{c.upper()}")))
            else:
                items.append(IrItem(atom=IrLiteral(c)))
        return IrGroup(body=IrAlternation((IrSequence(tuple(items)),)))
