from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Self, TypeVar, cast


class IrSelf[Ir_co: "IrSelf"]:
    __slots__ = ()
    _bound: ClassVar[type]

    def eval(self, d, n, nc, /) -> Ir_co:
        return cast(Ir_co, self)

    # derive _bound from the class's OWN type params only (no MRO walk)
    def __init_subclass__(cls, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        if "_bound" in cls.__dict__:
            return
        params = cls.__dict__.get("__type_params__", ())
        if params and isinstance(params[0], TypeVar) and params[0].__bound__:
            cls._bound = params[0].__bound__

    @property
    def bound(self) -> type[Ir_co]:
        return type(self)._bound


class IrNode[Ir_co: IrSelf = IrSelf](IrSelf[Ir_co]):
    __slots__ = ()


class IrLeaf[Ir_co: IrSelf](IrNode[Ir_co]):
    __slots__ = ()


class IrStr(IrLeaf[str], str):
    __slots__ = ()
    _bound: ClassVar[type[str]] = str

    def __new__(cls, v: str = "") -> Self:
        return super().__new__(cls, v)

    def eval(self, d, n, nc, /) -> Self:
        return self


class IrTuple[T: IrSelf](IrNode, tuple):
    __slots__ = ()
    _bound: ClassVar[type[tuple]] = tuple

    def __new__(cls, *items: T) -> Self:
        return super().__new__(cls, items)

    def eval(self, d, n, nc, /) -> Self:
        return type(self)(*(p.eval(d, n, nc) for p in self))


class IrSequence(IrTuple[IrStr]):  # no own type params
    __slots__ = ()


class IrComposite[Ir_co: IrSelf = IrSelf](IrNode[Ir_co]):
    __slots__ = ()


@dataclass(frozen=True, slots=True)
class IrField[Ir_co: IrStr = IrStr](IrComposite[Ir_co]):
    name: str

    def eval(self, d, n, nc, /) -> Ir_co:
        return self.bound(getattr(n, self.name))


class IrConcat[Ir_co: IrStr = IrStr](IrTuple[IrSelf]):  # generic + tuple subclass
    __slots__ = ()

    def eval(self, d, n, nc, /) -> Ir_co:
        return self.bound(self.bound().join(p.eval(d, n, nc) for p in self))


# runtime _bound checks
print("IrSequence._bound :", IrSequence._bound.__name__, "(want tuple)")
print("IrConcat._bound   :", IrConcat._bound.__name__, "(want IrStr)")
print("IrField._bound    :", IrField._bound.__name__, "(want IrStr)")
print("IrStr._bound      :", IrStr._bound.__name__, "(want str)")
c = IrConcat(IrStr("a"), IrStr("b"))
out = c.eval(IrStr(), IrStr(), ())
print("IrConcat eval     :", repr(out), "| isinstance IrStr:", isinstance(out, IrStr))
