"""Real flat records, built the way the compiler builds them.

``FlatArm`` and ``FlatClone`` are ``IrLeaf`` records the compiler fills slot by
slot, so they take no constructor arguments and a test builds one the same way.
Using the real type rather than a look-alike is what keeps a frame test honest:
the frame's lanes are typed now, and a stub that merely quacks would prove the
test compiles rather than that the runtime's own record fits.
"""

from __future__ import annotations

from lexic.parsing.pda.compiler.program.flatten import FlatArm, FlatClone


def flat_arm(n: int, **lanes: object) -> FlatArm:
    """A real :class:`FlatArm` of ``n`` items, with only the lanes named filled.

    :param n: The arm's item count.
    :param lanes: Any further slot to fill, by name.
    """
    arm = FlatArm()
    arm.n = n
    for name, value in lanes.items():
        setattr(arm, name, value)
    return arm


def flat_clone[Carry](
    mode: int = 0, of: list[Carry] | None = None, **lanes: object
) -> FlatClone[Carry]:
    """A real :class:`FlatClone` in ``mode``, with only the lanes named filled.

    ``needs_ends`` defaults to ``True`` because a frame reads it at
    construction: a clone that binds a field to an item span keeps boundaries,
    so a test that says nothing about spans gets the shape that has them. Pass
    ``needs_ends=False`` for the boundary-free clone.

    :param mode: The clone's build mode.
    :param of: A sink whose model type the clone carries, so the caller's frame
        and its clone agree without either being asserted into place.
    :param lanes: Any further slot to fill, by name.
    """
    del of
    clone: FlatClone[Carry] = FlatClone()
    clone.mode = mode
    clone.needs_ends = True
    for name, value in lanes.items():
        setattr(clone, name, value)
    return clone
