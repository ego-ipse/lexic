"""The spectacle — the scene substrate and its renderers.

The substrate (:mod:`.scene`) is the load-bearing floor: the scene IS
IR, so everything here renders frozen spine citizens and holds no state
of its own.
"""

from opsis.opsis.scene import (
    OPSIS_SYMBOLS,
    Rail,
    Ring,
    Space,
    VisualNode,
    Window,
    visual,
)
from opsis.opsis.space import RENDER, page, render_scene

__all__ = [
    "OPSIS_SYMBOLS",
    "RENDER",
    "Rail",
    "Ring",
    "Space",
    "VisualNode",
    "Window",
    "page",
    "render_scene",
    "visual",
]
