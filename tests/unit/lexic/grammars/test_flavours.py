"""Tests for the flavour adapter registry (lexic.grammars)."""

from __future__ import annotations

from pathlib import Path

import pytest

from typing import cast

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import (
    ADAPTERS,
    FlavourAdapter,
    adapter_for_extension,
    get_adapter,
    register_adapter,
)


def test_adapters_contains_gbnf_after_import() -> None:
    assert "gbnf" in ADAPTERS


def test_get_adapter_gbnf_returns_correct_name() -> None:
    assert get_adapter("gbnf").name == "gbnf"


def test_get_adapter_gbnf_returns_correct_extensions() -> None:
    assert get_adapter("gbnf").extensions == (".gbnf",)


def test_get_adapter_unknown_raises_with_known_flavours_in_message() -> None:
    with pytest.raises(UnsupportedConstructError) as exc_info:
        get_adapter("abnf")
    assert "gbnf" in str(exc_info.value)


def test_adapter_for_extension_string_path() -> None:
    assert adapter_for_extension("grammar.gbnf").name == "gbnf"


def test_adapter_for_extension_path_object() -> None:
    assert adapter_for_extension(Path("grammar.gbnf")).name == "gbnf"


def test_adapter_for_extension_unknown_raises_with_known_extensions_in_message() -> (
    None
):
    with pytest.raises(UnsupportedConstructError) as exc_info:
        adapter_for_extension("grammar.abnf")
    assert ".gbnf" in str(exc_info.value)


def test_register_adapter_adds_to_registry() -> None:
    class _StubAdapter:
        name: str = "stub"
        extensions: tuple[str, ...] = (".stub",)
        parser = None
        emitter = None

    register_adapter(cast(FlavourAdapter, _StubAdapter()))
    try:
        assert "stub" in ADAPTERS
    finally:
        ADAPTERS.pop("stub", None)


def test_register_adapter_retrievable_by_get_adapter() -> None:
    class _StubAdapter:
        name: str = "stub2"
        extensions: tuple[str, ...] = (".stub2",)
        parser = None
        emitter = None

    stub = cast(FlavourAdapter, _StubAdapter())
    register_adapter(stub)
    try:
        assert get_adapter("stub2") is stub
    finally:
        ADAPTERS.pop("stub2", None)
