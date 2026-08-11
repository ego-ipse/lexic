"""The frame — what leaves for the leaf, and everything that decides it.

`scene.staged` makes the decisions; this presents them. Marks and tones are
the vocabulary, panels place the arrangement tree, and the composer fills it.
"""

from opsis.frame.compose import compose
from opsis.frame.marks import CELL, ROW, Frame

__all__ = ["CELL", "ROW", "Frame", "compose"]
