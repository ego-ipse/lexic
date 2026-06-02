import sys
import timeit
from dataclasses import dataclass
from typing import Self, Sequence


class IrSelf[Ir_co]:
    __slots__ = ()

    def eval(self, d, n, nc, /):
        return self

    def children(self) -> Sequence["IrSelf"]:
        return ()


class IrNode[Ir_co](IrSelf[Ir_co]):
    __slots__ = ()


class IrAtom(IrNode):
    __slots__ = ()


# tuple primitive base
class IrTuple(IrNode, tuple):
    __slots__ = ()

    def __new__(cls, *items) -> Self:
        return tuple.__new__(cls, items)

    def children(self):
        return self


class IrQuantifier(IrNode, tuple):  # named-tuple node, NOT an atom
    __slots__ = ()

    def __new__(cls, lo: int = 1, hi: int | None = 1) -> Self:
        return tuple.__new__(cls, (lo, hi))

    @property
    def min(self) -> int:
        return self[0]

    @property
    def max(self) -> int | None:
        return self[1]


class IrGroup(IrTuple, IrAtom):  # named-tuple node that IS an atom
    __slots__ = ()

    @property
    def body(self):
        return self[0]


# dataclass equivalents
@dataclass(frozen=True, slots=True)
class DQuant(IrNode):
    min: int = 1
    max: int | None = 1


q_tup = IrQuantifier(2, 5)
q_dc = DQuant(2, 5)
g = IrGroup("BODY")

print("tuple node min/max     :", q_tup.min, q_tup.max)
print("tuple isinstance IrNode :", isinstance(q_tup, IrNode))
print(
    "group isinstance IrAtom :",
    isinstance(g, IrAtom),
    "| IrNode:",
    isinstance(g, IrNode),
)
print("group MRO               :", [c.__name__ for c in IrGroup.__mro__])
print(
    "tuple eq/hash native    :",
    IrQuantifier(2, 5) == IrQuantifier(2, 5),
    hash(IrQuantifier(2, 5)) == hash((2, 5)),
)
print()
print("sizeof tuple-node       :", sys.getsizeof(q_tup), "bytes")
print("sizeof dataclass-node   :", sys.getsizeof(q_dc), "bytes")
print(
    "eq  tuple   (1e6)       : %.4fs"
    % timeit.timeit(lambda: q_tup == IrQuantifier(2, 5), number=1_000_000)
)
print(
    "eq  dataclass(1e6)      : %.4fs"
    % timeit.timeit(lambda: q_dc == DQuant(2, 5), number=1_000_000)
)
print(
    "hash tuple  (1e6)       : %.4fs"
    % timeit.timeit(lambda: hash(q_tup), number=1_000_000)
)
print(
    "hash dataclass(1e6)     : %.4fs"
    % timeit.timeit(lambda: hash(q_dc), number=1_000_000)
)
