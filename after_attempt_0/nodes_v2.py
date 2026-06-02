from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Self, Sequence, final


# 1. THE ROOT (Pure Protocol/ABC, no instance state)
class IrSelf:
    __slots__ = ()
    # ... __call__, eval, children, rebuild ...


# 2. THE SUPERSETS (Pure ABCs, no instance state)
class IrNode(IrSelf):
    __slots__ = ()
    _str_name: ClassVar[str]


class IrLeaf(IrNode):
    __slots__ = ()

    def children(self) -> Sequence[IrSelf]:
        return ()

    def rebuild(self, _nc: Sequence[IrSelf]) -> Self:
        return self


# 3. THE C-TYPE PRIMITIVES (Zero-overhead, native hashing)
class IrStr(IrLeaf, str):
    __slots__ = ()

    def __new__(cls, val: str = "") -> Self:
        return str.__new__(cls, val)


class IrInt(IrLeaf, int):
    __slots__ = ()

    def __new__(cls, val: int = 0) -> Self:
        return int.__new__(cls, val)


class IrTuple(IrNode, tuple):
    __slots__ = ()

    def __new__(cls, *items: IrSelf) -> Self:
        return tuple.__new__(cls, items)

    def children(self) -> Sequence[IrSelf]:
        return self


class IrFrozenSet(IrNode, frozenset):
    __slots__ = ()

    def __new__(cls, *items: IrSelf) -> Self:
        return frozenset.__new__(cls, items)

    def children(self) -> Sequence[IrSelf]:
        return tuple(self)


# 4. THE COMPOSITES (Slotted Dataclasses)
@dataclass(frozen=True, slots=True)
class IrComposite(IrNode):
    # Inherits __slots__ from dataclass, safe because it doesn't mix with C-types
    pass


# 5. THE VARIADIC NODES (Direct tuple subclasses)
class IrAlternation(IrTuple):
    __slots__ = ()
    _str_name: ClassVar[str] = "ALT"
    # Native tuple equality and hashing apply automatically!


@final
class IrNone(IrSelf):
    __slots__ = ()
    _instance: ClassVar[Self | None] = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init_subclass__(cls, **kwargs) -> None:
        # Hard runtime block against subclassing
        raise TypeError(f"{cls.__name__} is @final and cannot be subclassed")
