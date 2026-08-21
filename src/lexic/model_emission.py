"""Stack records and extent reservation for addressed model emission."""

from __future__ import annotations

from typing import Any, ClassVar

from lexic.ir import IrAddress, IrExtent, IrNamedTuple, IrSpan


class EmissionPart(IrNamedTuple[Any, IrAddress]):
    """A part waiting to be emitted under its parent-supplied address."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    part: Any
    address: IrAddress


class EmissionClose(IrNamedTuple[int, IrAddress, int]):
    """A container close: extent slot, address, and opening offset."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    slot: int
    address: IrAddress
    start: int


def open_emission(
    work: EmissionPart,
    parts: list[tuple[str, Any]],
    extents: list[IrExtent],
    at: int,
) -> list[object]:
    """Reserve a container extent and stack its close beneath its children."""
    reserved = len(extents)
    extents.append(IrExtent(work.address, IrSpan(at, at)))
    items: list[object] = [EmissionClose(reserved, work.address, at)]
    items.extend(
        EmissionPart(part, work.address.child(field, slot))
        for slot, (field, part) in reversed(list(enumerate(parts)))
    )
    return items
