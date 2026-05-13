"""Grammar-flavour layer — public endpoint.

During the parallel-track cutover this module exposes both registries: the
legacy ADAPTERS dict driven by FlavourAdapter, and the new _FLAVOURS dict
driven by Flavour subclasses. The legacy half is removed in Phase 2.
"""

from __future__ import annotations

from pathlib import Path

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf.flavour import AbnfFlavour
from lexic.grammars.flavour import Flavour
from lexic.grammars.flavours import (
    ADAPTERS,
    FlavourAdapter,
    FlavourEmitter,
    FlavourParser,
    adapter_for_extension,
    get_adapter,
    register_adapter,
)
from lexic.grammars.gbnf.adapter import GbnfAdapter
from lexic.grammars.new_gbnf.flavour import GbnfFlavour as _NewGbnfFlavour

register_adapter(GbnfAdapter())

_FLAVOURS: dict[str, type[Flavour]] = {}


def register_flavour(flavour_cls: type[Flavour]) -> None:
    """Register a flavour."""
    _FLAVOURS[flavour_cls.name] = flavour_cls


def get_flavour(name: str) -> type[Flavour]:
    """Get a flavour by name."""
    try:
        return _FLAVOURS[name]
    except KeyError:
        raise UnsupportedConstructError(
            f"Unknown flavour: {name!r}. Supported: {sorted(_FLAVOURS)}"
        ) from None


def flavour_for_extension(path: str | Path) -> type[Flavour]:
    """Get a flavour by extension."""
    suffix = Path(path).suffix
    for fc in _FLAVOURS.values():
        if suffix in fc.extensions:
            return fc
    known = sorted({ext for fc in _FLAVOURS.values() for ext in fc.extensions})
    raise UnsupportedConstructError(
        f"No flavour for extension {suffix!r}. Supported: {known}"
    )


register_flavour(_NewGbnfFlavour)
register_flavour(AbnfFlavour)


__all__ = [
    "ADAPTERS",
    "Flavour",
    "FlavourAdapter",
    "FlavourEmitter",
    "FlavourParser",
    "adapter_for_extension",
    "flavour_for_extension",
    "get_adapter",
    "get_flavour",
    "register_adapter",
    "register_flavour",
]
