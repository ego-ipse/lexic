from typing import NamedTuple, Protocol, Self, Sequence, runtime_checkable


# ---- 1. typing.NamedTuple + extra base (inheritance) ----
class IrNodeABC:
    __slots__ = ()

    def children(self):
        return ()


try:

    class IrItemA(NamedTuple, IrNodeABC):
        atom: str
        quantifier: int

    print("1. NamedTuple + base       : WORKS")
except TypeError as e:
    print("1. NamedTuple + base       : FAILS —", e)


# ---- 2. NamedTuple satisfying a structural Protocol (no inheritance) ----
@runtime_checkable
class IrNodeProto(Protocol):
    def children(self) -> Sequence["IrNodeProto"]: ...
    def eval(self, d, n, nc, /) -> "IrNodeProto": ...


class IrItemB(NamedTuple):
    atom: str
    quantifier: int

    def children(self):
        return self

    def eval(self, d, n, nc, /) -> Self:
        return self


it = IrItemB("a", 3)
print("2. proto isinstance        :", isinstance(it, IrNodeProto))
print("2. named fields            :", it.atom, it.quantifier, "| tuple:", tuple(it))
v: IrNodeProto = IrItemB("x", 1)  # static assignability check


# ---- 3. can a NamedTuple carry a marker role (IrAtom) structurally? ----
@runtime_checkable
class IrAtomProto(Protocol):
    def children(self) -> Sequence["IrNodeProto"]: ...
    def eval(self, d, n, nc, /) -> "IrNodeProto": ...


# NOTE: structurally identical to IrNodeProto -> every node is an "atom". Marker lost.
print(
    "3. atom-marker distinct?   :",
    isinstance(it, IrAtomProto),
    "(but so is every node — marker is meaningless structurally)",
)
