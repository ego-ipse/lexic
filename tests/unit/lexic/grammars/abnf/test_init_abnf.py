"""Tests for lexic.grammars.abnf — the ABNF flavour singleton.

The self-grammar's structure, the quantifier/literal emission matrices and
the reduce-side action tables are exhaustively pinned in
``tests/unit/lexic/grammars/test_abnf.py``; this file targets the module's
own narrow assembly: the singleton's identity and the escape codec's
boundary.
"""

from __future__ import annotations

from lexic.grammars.abnf import (
    ABNF_ESCAPES,
    ABNF_FLAVOUR,
    ABNF_NOISE,
    ABNF_REDUCER,
    _AbnfFlavour,
)
from lexic.ir import DROP, IrFlavour, IrRuleRef


def test_abnf_flavour_is_an_instance_of_its_own_private_flavour_class():
    """The singleton is an ``_AbnfFlavour`` and an ``IrFlavour``."""
    assert isinstance(ABNF_FLAVOUR, _AbnfFlavour)
    assert isinstance(ABNF_FLAVOUR, IrFlavour)


def test_abnf_flavour_declared_metadata():
    """The flavour's name, extension and comment marker are as documented."""
    assert _AbnfFlavour.name == "abnf"
    assert _AbnfFlavour.extensions == (".abnf",)
    assert _AbnfFlavour.line_comment == ";"


def test_abnf_escapes_quote_safe_covers_printable_ascii_but_not_the_quote():
    """RFC 7405's char-val body excludes the double quote — everything else
    printable ASCII is spellable."""
    assert ABNF_ESCAPES.spellable("hello world!")
    assert not ABNF_ESCAPES.spellable('has"quote')
    assert not ABNF_ESCAPES.spellable("\x01control")


def test_abnf_noise_drops_a_non_semantic_rule_and_keeps_everything_else():
    """A non-semantic rule's DROP mapping round-trips through the table."""
    dropped_rule = next(
        key
        for key, value in ABNF_NOISE.items()
        if value is DROP and isinstance(key, IrRuleRef)
    )
    assert ABNF_NOISE.get(dropped_rule) is DROP


def test_abnf_reducer_wraps_the_flavours_own_actions_and_noise():
    """The reducer's noise table IS the flavour's own ``ABNF_NOISE``."""
    assert ABNF_REDUCER.noise == ABNF_NOISE
