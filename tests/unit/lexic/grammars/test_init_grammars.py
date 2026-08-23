"""Tests for lexic.grammars — the flavour registry public endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import (
    ABNF_FLAVOUR,
    EBNF_FLAVOUR,
    GBNF_FLAVOUR,
    flavour_for_extension,
    get_flavour,
    register_flavour,
)


def test_get_flavour_resolves_each_built_in_flavour_by_name():
    """Every built-in flavour name resolves to its own singleton."""
    assert get_flavour("gbnf") is GBNF_FLAVOUR
    assert get_flavour("abnf") is ABNF_FLAVOUR
    assert get_flavour("ebnf") is EBNF_FLAVOUR


def test_get_flavour_refuses_an_unknown_name_naming_the_known_ones():
    """An unknown flavour name refuses, listing the ones that ARE known."""
    with pytest.raises(UnsupportedConstructError, match="Unknown flavour.*gbnf"):
        get_flavour("nonexistent")


def test_flavour_for_extension_resolves_by_suffix():
    """A path's suffix resolves to the flavour that declares it."""
    assert flavour_for_extension("grammar.gbnf") is GBNF_FLAVOUR
    assert flavour_for_extension("grammar.abnf") is ABNF_FLAVOUR


def test_flavour_for_extension_accepts_a_path_object():
    """A ``Path`` works the same as a plain string."""
    assert flavour_for_extension(Path("g.gbnf")) is GBNF_FLAVOUR


def test_flavour_for_extension_refuses_an_unknown_suffix():
    """An unregistered suffix refuses, naming the suffix it saw."""
    with pytest.raises(UnsupportedConstructError, match=r"\.xyz"):
        flavour_for_extension("g.xyz")


def test_register_flavour_makes_a_flavour_reachable_by_its_type_name():
    """A registered flavour is looked up by ``type(flavour).name`` — the
    registry keys on the CLASS, so re-registering the same singleton twice
    just overwrites its own slot."""
    register_flavour(GBNF_FLAVOUR)
    assert get_flavour("gbnf") is GBNF_FLAVOUR
