"""Tests for lexic.grammars.gbnf — the GBNF flavour singleton.

The self-grammar's shape, the quantifier/literal emission matrices, and the
reduce-side action tables are exhaustively pinned in
``tests/unit/lexic/grammars/test_gbnf.py``; this file targets the module's
own narrow assembly not covered there: the token-encoding registry name and
the flavour singleton's declared metadata.
"""

from __future__ import annotations

from lexic.grammars.gbnf import (
    GBNF_FLAVOUR,
    GBNF_NOISE,
    GBNF_TOKEN_ENCODING,
    _GbnfFlavour,
)
from lexic.ir import IrFlavour


def test_gbnf_flavour_is_an_instance_of_its_own_private_flavour_class():
    """The singleton is a ``_GbnfFlavour`` and an ``IrFlavour``."""
    assert isinstance(GBNF_FLAVOUR, _GbnfFlavour)
    assert isinstance(GBNF_FLAVOUR, IrFlavour)


def test_gbnf_flavour_declared_metadata():
    """The flavour's name, extension and comment marker are as documented."""
    assert _GbnfFlavour.name == "gbnf"
    assert _GbnfFlavour.extensions == (".gbnf",)
    assert _GbnfFlavour.line_comment == "#"


def test_gbnf_token_encoding_names_the_registry_slot_token_terminals_bind_to():
    """The token-encoding registry name is the documented ``"tokens"``."""
    assert GBNF_TOKEN_ENCODING == "tokens"


def test_gbnf_noise_is_the_reducers_own_noise_table():
    """The flavour's reducer noise table IS the module's own GBNF_NOISE."""
    assert GBNF_FLAVOUR.reducer.noise is GBNF_NOISE
