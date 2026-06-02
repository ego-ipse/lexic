from abc import ABC


# Spine: generic, covariant-ish (PEP 695 is covariant-by-inference for return-only)
# Spine: generic, covariant-ish (PEP 695 is covariant-by-inference for return-only)
class IrSelf[Ir_co]:
    __slots__ = ()

    def eval(self, d, n, nc, /) -> "Ir_co": ...  # type: ignore


class IrNode[Ir_co](IrSelf[Ir_co]):
    __slots__ = ()


class IrLeaf[Ir_co](IrNode[Ir_co]):
    __slots__ = ()


# C-type primitive
class IrStr(IrLeaf[str], str):
    __slots__ = ()

    def __new__(cls, v: str = "") -> "IrStr":
        return str.__new__(cls, v)


# --- Candidate A: IrAtom as a PLAIN non-generic marker ABC ---
class IrAtom(IrNode):  # no new type param
    __slots__ = ()


class IrLiteral(IrStr, IrAtom):  # str + marker
    __slots__ = ()


lit = IrLiteral("x")
print("A: literal value      =", repr(str(lit)))
print("A: isinstance IrAtom   =", isinstance(lit, IrAtom))
print("A: isinstance IrStr    =", isinstance(lit, IrStr))
print("A: isinstance str      =", isinstance(lit, str))
print("A: MRO                 =", [c.__name__ for c in IrLiteral.__mro__])
print("A: hash works          =", hash(lit) == hash("x"))


# --- Candidate B: virtual registration (no inheritance) ---
class IrAtomReg(ABC):
    __slots__ = ()


class IrRuleRef(IrStr):
    __slots__ = ()


IrAtomReg.register(IrRuleRef)
print(
    "B: register isinstance =",
    isinstance(IrRuleRef("y"), IrAtomReg),
    "(pyright would NOT see this)",
)

foob: IrAtom = IrLiteral("lol")
