"""The frame — what leaves for the leaf, and everything that decides it.

Marks and tones are the vocabulary, panels are where things go, and the
composer fills them. Nothing downstream of here makes a decision.
"""

from opsis.frame.compose import compose
from opsis.frame.marks import CELL, ROW, Frame

__all__ = ["CELL", "ROW", "Frame", "compose"]
