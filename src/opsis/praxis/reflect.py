"""The reflective rung — the picture, as a text you can read and edit.

Everything on screen is drawn from records, and those records are IR:
``Ring``, ``Rail``, ``Moon``, ``Space``. So the picture has a grammar —
the same IR-constructor notation every other rung is read by — and a
session can hold the picture as an ordinary reading, whose text is the
scene and whose product is the scene.

That closes the ladder. Edit the notation and the drawing changes,
because the drawing was never anything but that notation's product. No
special case makes this work: the scene reading is read by the same
notation reader a manifest is, and refuses the same way.
"""

from __future__ import annotations

from lexic.compile import load_ir
from lexic.compile.notation.emit import emit_ir
from lexic.compile.notation.parse import NOTATION_GRAMMAR
from lexic.exceptions import UnsupportedConstructError
from opsis.opsis.scene import SYMBOLS, Space
from opsis.praxis.reading import Params, Reader
from opsis.praxis.session import Session

__all__ = ["REFLECTED", "drawn_by", "scene_reader", "scene_text"]

REFLECTED = "scene"
"""The kind a reading that IS the picture carries."""


def scene_reader() -> Reader:
    """The notation, reading scene text into the scene it describes.

    Not a second notation: the same constructor language, given the
    scene's own vocabulary. A ``Ring`` is a name in that vocabulary
    exactly as ``IrRule`` is a name in lexic's.
    """
    return Reader(
        "scene",
        "notation",
        _read,
        grammar=NOTATION_GRAMMAR,
    )


def _read(text: str, _params: Params) -> object:
    """One scene read, narrowed to a space."""
    space = load_ir(text, symbols=SYMBOLS)
    if not isinstance(space, Space):
        raise UnsupportedConstructError(
            f"a scene is a Space; that is a {type(space).__name__}"
        )
    return space


def scene_text(space: Space) -> str:
    """The scene as the notation that reconstructs it."""
    return emit_ir(space)


def drawn_by(session: Session) -> Space | None:
    """The hand-edited scene the world should draw, if there is one.

    A session normally derives its picture from its readings. Once
    somebody has written a scene down, that writing is what is drawn —
    it stops being a report of the session and becomes an instruction to
    it, which is the whole point of being able to edit it.

    The most recent one wins, so writing a new scene supersedes an older
    one without anybody having to delete it.
    """
    for reading in reversed(list(session.readings.values())):
        if reading.kind == REFLECTED and isinstance(reading.product, Space):
            return reading.product
    return None
