"""The spectacle — the scene substrate and its renderers.

The substrate (:mod:`._scene`) is the load-bearing floor: the scene IS
IR, so everything here renders frozen spine citizens and holds no state
of its own.
"""

from opsis.opsis._scene import (
    OPSIS_SYMBOLS,
    Rail,
    Ring,
    Space,
    VisualNode,
    Window,
    visual,
)

__all__ = [
    "OPSIS_SYMBOLS",
    "Rail",
    "Ring",
    "Space",
    "VisualNode",
    "Window",
    "visual",
]
