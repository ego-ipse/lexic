"""The scene — what a session looks like, as IR.

A reading is praxis's; a ring is the spectacle's picture of one. The
records here are frozen spine citizens carrying real lexic payloads, so
``repr(scene)`` IS the session's drawn form and
``load_ir(text, symbols=SYMBOLS)`` reads it back. There is no
serializer, because the picture is already something lexic can read.

:class:`VisualNode` is the role marker (the ``IrDoc`` idiom): a visual
node IS an IR node, so every table lexic already has fires the
payload's action on it by MRO. The scene is immutable — the record tier
refuses per-instance state — so the camera lives in the DOM and nothing
drawn can quietly become stateful.
"""

from __future__ import annotations

from typing import ClassVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrNamedTuple, IrNode, IrNone, IrSelf, IrSeq

__all__ = ["SYMBOLS", "Moon", "Rail", "Ring", "Space", "VisualNode", "visual"]


class VisualNode(IrNode[IrSelf, IrSelf]):
    """Role marker — being visual is a role over the spine, not a wrapper."""


_VISUAL: dict[type, type] = {}


def visual[T: IrSelf](t: type[T]) -> type[T]:
    """The payload-typed visual class for ``t``, synthesized once.

    The result subclasses BOTH the marker and ``t``, so a table that
    dispatches on ``t`` fires unchanged. The ``issubclass`` guards make
    the ``type[T]`` return checked rather than asserted — Python has no
    intersection type, so the claim is verified instead of promised.
    """
    got = _VISUAL.get(t)
    if got is not None and issubclass(got, t):
        return got
    made = type(f"Visual{t.__name__}", (VisualNode, t), {})
    if not issubclass(made, t):
        raise UnsupportedConstructError(
            f"visual: synthesis for {t.__name__!r} lost its payload base"
        )
    _VISUAL[t] = made
    return made


class Moon(VisualNode, IrNamedTuple[str, str, str, IrSeq]):
    """A reading of its ring, in orbit around it — and its own moons.

    A moon is carried rather than placed: it rides at a fixed offset, so
    a fan keeps its shape however the ring is dragged. Lines are for
    relations between rings; a reading of a ring belongs to it.

    A moon that carries moons is a GROUP: clicking it opens its own
    orbit in place instead of a window. That is the same recursion the
    ladder has, applied to the fan, and it is what keeps a node from
    wearing twenty readings at once.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("moons",)

    name: str
    label: str = ""
    kind: str = ""
    moons: IrSeq = IrSeq()


class Ring(
    VisualNode, IrNamedTuple[str, IrSelf, str, int, int, str, str, IrSeq, str, str]
):
    """One reading, drawn.

    :ivar name: What rails and gestures address it by.
    :ivar payload: The lexic node it is ABOUT — the node itself, not a
        copy, which is what makes the scene inspectable as IR.
    :ivar x: Where eidolon put it; the live position is the camera's and
        is never written back.
    :ivar tag: What a gesture needs — ``reading:r3``.
    :ivar state: ``reads`` when its product can read others, else
        ``idle``. A fact about the product, not a mode someone set.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("payload", "moons")

    name: str
    payload: IrSelf = IrNone
    hue: str = "cyan"
    x: int = 0
    y: int = 0
    label: str = ""
    sub: str = ""
    moons: IrSeq = IrSeq()
    tag: str = ""
    state: str = ""


class Rail(VisualNode, IrNamedTuple[str, str, str, str, str, int]):
    """A reading drawn between two rings, addressed by name.

    ``label``/``sub`` are what the reading CLAIMS; ``bow`` swings the
    curve off the straight line so two relations over one pair stay
    legible. Where the ends sit is the camera's business.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()

    src: str = ""
    dst: str = ""
    hue: str = "cyan"
    label: str = ""
    sub: str = ""
    bow: int = 0


class Space(VisualNode, IrSeq[VisualNode]):
    """A space IS its children tuple — containment on the record spine."""


SYMBOLS: dict[str, type] = {
    "Moon": Moon,
    "Rail": Rail,
    "Ring": Ring,
    "Space": Space,
}
"""The scene's notation vocabulary — what makes ``repr`` readable back."""
