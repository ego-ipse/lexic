"""GbnfEscapes (mirror) parity with the legacy module."""

from __future__ import annotations

from lexic.grammars.new_gbnf.escapes import GbnfEscapes as NewEscapes
from lexic.grammars.gbnf.adapter import GbnfEscapes as LegacyEscapes


def test_decode_parity():
    """Decode parity between the two modules."""
    cases = [r"\n", r"\t", r"\r", r"\\", r"\"", r"ÿ", r"\x41", "abc"]
    for s in cases:
        assert NewEscapes().decode(s) == LegacyEscapes().decode(s)


def test_encode_parity():
    """Encode parity between the two modules."""
    cases = ["\n", "\t", "\\", '"', "abc", "\x00"]
    for s in cases:
        assert NewEscapes().encode(s) == LegacyEscapes().encode(s)
