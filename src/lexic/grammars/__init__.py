"""Grammar-flavour layer — public endpoint."""

from __future__ import annotations

from pathlib import Path

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf.flavour import AbnfFlavour
from lexic.grammars.flavour import IrFlavour
from lexic.grammars.gbnf.flavour import GbnfFlavour

_FLAVOURS: dict[str, type[IrFlavour]] = {}


def register_flavour(flavour_cls: type[IrFlavour]) -> None:
    """Register a flavour."""
    _FLAVOURS[flavour_cls.name] = flavour_cls


def get_flavour(name: str) -> type[IrFlavour]:
    """Get a flavour by name."""
    try:
        return _FLAVOURS[name]
    except KeyError:
        raise UnsupportedConstructError(
            f"Unknown flavour: {name!r}. Supported: {sorted(_FLAVOURS)}"
        ) from None


def flavour_for_extension(path: str | Path) -> type[IrFlavour]:
    """Get a flavour by extension."""
    suffix = Path(path).suffix
    for fc in _FLAVOURS.values():
        if suffix in fc.extensions:
            return fc
    known = sorted({ext for fc in _FLAVOURS.values() for ext in fc.extensions})
    raise UnsupportedConstructError(
        f"No flavour for extension {suffix!r}. Supported: {known}"
    )


register_flavour(GbnfFlavour)
register_flavour(AbnfFlavour)


__all__ = ["IrFlavour", "flavour_for_extension", "get_flavour", "register_flavour"]
