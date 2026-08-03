"""Kairos — the time axis: a parse held open, and a prefix advancing.

Most of this instrument answers about a whole text at once. These two
do not. A resumable chart is held open while text ARRIVES, marked at
points worth returning to and wound back to any of them — so its marks
are moments in a session's history rather than offsets in a document.
A constraint cursor is the same shape from the other end: a prefix that
grows one token at a time, each step narrowing what may come next.

Both are stateful in a way nothing else here is, and both are about
WHEN rather than what. That is why they are together, and why they are
not in praxis with the readings they belong to.
"""
