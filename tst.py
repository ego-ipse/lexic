"""TST"""

from typing import Generic, Self
from typing_extensions import TypeVar

_T = TypeVar("_T", default=Self)


class Box(Generic[_T]):
    """TST"""

    _value: _T

    def __init__(self, value: _T) -> None:
        """TST"""
        self._value = value

    def value(self) -> _T:
        """TST"""
        return self._value


class IntBox(Box[int]):
    """TST"""

class StrBox(Box[str]):
    """TST"""

print('runtime OK')
print(Box(4).value())
print(IntBox(5).value())
print(StrBox("lk").value())

