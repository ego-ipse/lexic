"""How the hand is looking at a reading — the state a frame is built from.

A record, not a bag: the composer reads these by name, and nothing has to
guess what a key might hold.
"""

from __future__ import annotations

from typing import Protocol

__all__ = ["Looking"]


class Looking(Protocol):
    """Which surface is showing, and where each plane has been scrolled."""

    surface: str
    clock: str
    graph: str
    yaw: float
    pitch: float
    reader_top: int
    doc_top: int
    rail_top: int
