"""AbnfEscapes — minimal ABNF escape codec.

ABNF string literals don't carry C-style escape sequences; they are
pure characters. Hex values appear OUTSIDE literals as %xNN tokens
parsed by `AbnfFlavour.parse_charclass`. So the codec is identity.
"""

from __future__ import annotations

from typing import ClassVar

from lexic.ir.escapes import EscapeCodec


class AbnfEscapes(EscapeCodec):
    """Identity codec — ABNF literals are canonical Python."""

    SHORT_ESCAPES: ClassVar[dict[str, str]] = {}
    HEX_ESCAPES: ClassVar[tuple[tuple[str, int], ...]] = ()


ABNF_ESCAPES: EscapeCodec = AbnfEscapes()
