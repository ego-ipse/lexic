"""Shared adversarial-test helpers (deep/left-recursive grammar builders)."""

from __future__ import annotations

import signal
from contextlib import contextmanager
from typing import Iterator


def ref_chain(depth: int) -> str:
    """A ``depth``+1 rule unit-ref chain bottoming out at the leaf ``0``."""
    lines = [f'r{i} ::= "[" r{i + 1} "]"' for i in range(depth)]
    lines.append(f'r{depth} ::= "0"')
    return "\n".join(lines) + "\n"


def nested(depth: int) -> str:
    """Return ``depth`` nested arrays wrapped around a single leaf ``0``."""
    return "[" * depth + "0" + "]" * depth


@contextmanager
def watchdog(seconds: int) -> Iterator[None]:
    """Raise ``TimeoutError`` if the body runs longer than ``seconds``."""

    def _trip(_signum: int, _frame: object) -> None:
        raise TimeoutError(f"parse exceeded its {seconds}s budget")

    old = signal.signal(signal.SIGALRM, _trip)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
