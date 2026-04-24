"""Flavour protocols and adapter registry for lexic."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import RuleSpec


class FlavourParser(Protocol):
    # Phase 1: returns list[Any] because GbnfParser returns list[Rule] (AST).
    # Task 18 (Phase 2) changes GbnfParser.parse to return list[RuleSpec] directly;
    # at that point this becomes -> list[RuleSpec].
    def parse(self, text: str) -> list[Any]: ...


class FlavourEmitter(Protocol):
    supports: frozenset[str]

    def emit(self, specs: list[RuleSpec]) -> str: ...


class FlavourAdapter(Protocol):
    name: str
    extensions: tuple[str, ...]
    parser: FlavourParser
    emitter: FlavourEmitter


ADAPTERS: dict[str, FlavourAdapter] = {}


def register_adapter(adapter: FlavourAdapter) -> None:
    ADAPTERS[adapter.name] = adapter


def get_adapter(flavour: str) -> FlavourAdapter:
    try:
        return ADAPTERS[flavour]
    except KeyError:
        raise UnsupportedConstructError(
            f"Unknown flavour: {flavour!r}. Supported: {sorted(ADAPTERS)}"
        ) from None


def adapter_for_extension(path: str | Path) -> FlavourAdapter:
    suffix = Path(path).suffix
    for adapter in ADAPTERS.values():
        if suffix in adapter.extensions:
            return adapter
    known = sorted({ext for a in ADAPTERS.values() for ext in a.extensions})
    raise UnsupportedConstructError(
        f"No flavour adapter registered for extension {suffix!r}. Supported: {known}"
    )
