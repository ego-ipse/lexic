"""Scene contract — the notation round-trip, and visual-class synthesis."""

from __future__ import annotations

from lexic.compile.notation.emit import emit_ir
from lexic.compile.notation.parse import load_ir
from lexic.ir import IrSeq, IrStr
from opsis.opsis.draw.scene import SYMBOLS, Moon, Ring, Space, VisualNode, visual


def _sample_space() -> Space:
    """A small space of two rings, one carrying a moon."""
    return Space(
        Ring("r1", moons=IrSeq(Moon("m-r1-text", "text", "text"))),
        Ring("r2", hue="amber", x=30, y=40),
    )


def test_space_of_rings_round_trips_through_the_notation() -> None:
    """``load_ir(emit_ir(space))`` reconstructs a structurally equal space."""
    space = _sample_space()
    text = emit_ir(space)
    back = load_ir(text, symbols=SYMBOLS)
    assert back == space
    assert isinstance(back, Space)


def test_visual_is_memoised_for_the_same_type() -> None:
    """Asking for the visual class of the same type twice gives one object."""
    first = visual(IrStr)
    second = visual(IrStr)
    assert first is second


def test_visual_subclasses_both_visualnode_and_the_payload_type() -> None:
    """The synthesized class fires on both the visual role and its payload type."""
    made = visual(IrStr)
    assert issubclass(made, VisualNode)
    assert issubclass(made, IrStr)
