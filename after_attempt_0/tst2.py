from typing import Self, cast


class IrSelf[Ir_co]:
    __slots__ = ()


class IrNode[Ir_co](IrSelf[Ir_co]):
    __slots__ = ()


class IrLeaf[Ir_co](IrNode[Ir_co]):
    __slots__ = ()


class IrAtom(IrNode):
    __slots__ = ()


# --- Variant 1: no __new__ override at all (inherit str.__new__) ---
class IrStr1(IrLeaf[str], str):
    __slots__ = ()


class IrLiteral1(IrStr1, IrAtom):
    __slots__ = ()


v1: IrAtom = IrLiteral1("x")  # check 1


# --- Variant 2: __new__ -> Self via cast ---
class IrStr2(IrLeaf[str], str):
    __slots__ = ()

    def __new__(cls, v: str = "") -> Self:
        return cast(Self, str.__new__(cls, v))


class IrLiteral2(IrStr2, IrAtom):
    __slots__ = ()


v2: IrAtom = IrLiteral2("x")  # check 2


# --- Variant 3: __new__ -> Self via super() ---
class IrStr3(IrLeaf[str], str):
    __slots__ = ()

    def __new__(cls, v: str = "") -> Self:
        return super().__new__(cls, v)


class IrLiteral3(IrStr3, IrAtom):
    __slots__ = ()


v3: IrAtom = IrLiteral3("x")  # check 3


# --- Variant 4: __new__ -> Self via str.__new__ direct (the form said to fail) ---
class IrStr4(IrLeaf[str], str):
    __slots__ = ()

    def __new__(cls, v: str = "") -> Self:
        return str.__new__(cls, v)


class IrLiteral4(IrStr4, IrAtom):
    __slots__ = ()


v4: IrAtom = IrLiteral4("x")  # check 4
