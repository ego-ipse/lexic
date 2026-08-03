"""The visual substrate — the scene is IR.

:class:`VisualNode` marks the visual role over the spine (the ``IrDoc``
idiom, one tier up): a visual node IS an IR node, so every existing
dispatch table fires the payload's action on it by plain MRO resolution.
The scene vocabulary — :class:`Ring`, :class:`Rail`, :class:`Window`,
:class:`Space` — is a family of frozen records on that marker carrying
real lexic payloads. ``repr(scene)`` is the session file and
``load_ir(text, symbols=OPSIS_SYMBOLS)`` is its reader.

The scene is immutable (the spine refuses per-instance mutable state);
the camera is the DOM; session-mutable state is a praxis cursor.
"""

from __future__ import annotations

from typing import ClassVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrNamedTuple, IrNode, IrNone, IrSelf, IrSeq

__all__ = [
    "OPSIS_SYMBOLS",
    "Rail",
    "Ring",
    "Space",
    "VisualNode",
    "Window",
    "visual",
]


class VisualNode(IrNode[IrSelf, IrSelf]):
    """Role marker — being visual is a role over the spine, not a wrapper."""


_VISUAL: dict[type, type] = {}


def visual[T: IrSelf](t: type[T]) -> type[T]:
    """The payload-typed visual class for ``t``, synthesized once.

    The result subclasses BOTH :class:`VisualNode` and ``t``, so every
    existing dispatch table fires the payload's action on it — MRO
    resolution is the whole mechanism. The ``issubclass`` guards are what
    make the ``type[T]`` claim checkable rather than asserted.

    :param t: The payload type to mark visual.
    :returns: The memoised ``Visual<name>`` subclass of ``t``.
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


class Ring(VisualNode, IrNamedTuple[str, IrSelf, str, int, int]):
    """A ring: a named, hued, placed carrier of a real IR payload.

    ``x``/``y`` are the DERIVED initial position (an eidolon product);
    the live position is the camera's business, never written back.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("payload",)

    name: str
    payload: IrSelf = IrNone
    hue: str = "cyan"
    x: int = 0
    y: int = 0


class Rail(VisualNode, IrNamedTuple[str, str, str, str]):
    """A rail: a drawn relation between rings, by NAME — geometry is the
    camera's business, not the scene's."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()

    src: str = ""
    dst: str = ""
    hue: str = "line"
    label: str = ""


class Window(VisualNode, IrNamedTuple[str, IrSelf, int, int, int, int]):
    """A window: a named opening onto a body — containment, never a
    decomposition onto the shared canvas."""

    _child_attrs: ClassVar[tuple[str, ...]] = ("body",)

    name: str
    body: IrSelf = IrNone
    x: int = 0
    y: int = 0
    w: int = 460
    h: int = 250


class Space(VisualNode, IrSeq[VisualNode]):
    """A space IS its children tuple — containment on the record spine."""


OPSIS_SYMBOLS: dict[str, type] = {
    "Rail": Rail,
    "Ring": Ring,
    "Space": Space,
    "Window": Window,
}
"""The scene's notation vocabulary — what makes ``repr`` a session file."""
