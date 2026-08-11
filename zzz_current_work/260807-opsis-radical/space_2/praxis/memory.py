"""What has already been worked out, kept until the question changes.

Every gesture asks for a whole frame, and a frame asks each surface what it
shows. Compiling the reader, running the predictive machine over the document
and folding the chart are answers to questions that did not change when the
hand turned a wheel — so they are worked out once and kept against the
question that produced them.

One `Memory` per kind of question, so what comes back is what went in.
"""

from __future__ import annotations

from collections.abc import Callable

__all__ = ["Memory"]


class Memory[T]:
    """Answers of one kind, newest kept, oldest dropped."""

    __slots__ = ("held", "keep")

    def __init__(self, keep: int = 6) -> None:
        self.held: dict[str, T] = {}
        self.keep = keep

    def once(self, key: str, work: Callable[[], T]) -> T:
        """The answer to this question, worked out at most once."""
        if key in self.held:
            self.held[key] = self.held.pop(key)  # newest last
            return self.held[key]
        made = work()
        self.held[key] = made
        while len(self.held) > self.keep:
            del self.held[next(iter(self.held))]
        return made

    def clear(self) -> None:
        """Everything of this kind — for when the reading itself changes."""
        self.held.clear()
