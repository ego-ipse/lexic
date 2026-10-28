"""Tests for lexic.parsing.pda.runtime.kernel.verdicts — the boundary-decision group.

The package is a marker: the kernel is its import surface, and the host classes
live in the group's modules, where the kernel's method resolution reaches them.
"""

from __future__ import annotations

from lexic.parsing.pda.runtime.kernel import verdicts
from lexic.parsing.pda.runtime.kernel.decisions import Attempting
from lexic.parsing.pda.runtime.kernel.kernel import PdaKernel
from lexic.parsing.pda.runtime.kernel.verdicts.sides import Sides
from lexic.parsing.pda.runtime.kernel.verdicts.verdicts import Verdicts


def test_the_package_declares_no_surface_of_its_own() -> None:
    """A marker: nothing but its docstring and the modules below it."""
    own = {name for name in vars(verdicts) if not name.startswith("__")}
    assert own <= {"sides", "verdicts"}


def test_the_kernel_inherits_the_group_in_order() -> None:
    """The kernel's decision half inherits the verdict, which inherits its sides."""
    assert PdaKernel.__mro__.index(Attempting) < PdaKernel.__mro__.index(Verdicts)
    assert PdaKernel.__mro__.index(Verdicts) < PdaKernel.__mro__.index(Sides)
