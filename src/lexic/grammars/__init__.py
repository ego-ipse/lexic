"""Grammar-flavour layer — public endpoint."""

from __future__ import annotations

from pathlib import Path

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.grammars.ebnf import EBNF_FLAVOUR
from lexic.grammars.gbnf import GBNF_FLAVOUR
from lexic.ir import IrFlavour

_FLAVOURS: dict[str, IrFlavour] = {}


def register_flavour(flavour: IrFlavour) -> None:
    """Register a flavour singleton."""
    _FLAVOURS[type(flavour).name] = flavour


def get_flavour(name: str) -> IrFlavour:
    """Get a flavour singleton by name."""
    try:
        return _FLAVOURS[name]
    except KeyError:
        raise UnsupportedConstructError(
            f"Unknown flavour: {name!r}. Supported: {sorted(_FLAVOURS)}"
        ) from None


def flavour_for_extension(path: str | Path) -> IrFlavour:
    """Get a flavour singleton by extension."""
    suffix = Path(path).suffix
    for fl in _FLAVOURS.values():
        if suffix in type(fl).extensions:
            return fl
    known = sorted({ext for fl in _FLAVOURS.values() for ext in type(fl).extensions})
    raise UnsupportedConstructError(
        f"No flavour for extension {suffix!r}. Supported: {known}"
    )


register_flavour(GBNF_FLAVOUR)
register_flavour(ABNF_FLAVOUR)
register_flavour(EBNF_FLAVOUR)


__all__ = [
    "ABNF_FLAVOUR",
    "EBNF_FLAVOUR",
    "GBNF_FLAVOUR",
    "IrFlavour",
    "flavour_for_extension",
    "get_flavour",
    "register_flavour",
]
