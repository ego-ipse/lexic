"""A legible, witnessed `lexic.generate` gesture for one compiled reader."""

from __future__ import annotations

import random
from dataclasses import dataclass

from lexic.compile import CompiledGrammar
from lexic.exceptions import LexicError
from lexic.generate import generate

__all__ = ["Generated", "make"]


@dataclass(frozen=True, slots=True)
class Generated:
    """One deterministic sample and its read-back verdict."""

    root: str
    seed: int
    text: str
    faithful: bool
    words: str


def make(machine: CompiledGrammar, seed: int, max_depth: int = 5) -> Generated:
    """Generate once and require the same reader to accept and re-emit it."""
    root = str(machine.grammar.start)
    rules = {str(rule.name): rule for rule in machine.grammar.rules}
    try:
        text = generate(root, rules, rng=random.Random(seed), max_depth=max_depth)
        back = machine.parse(text)
        faithful = back.to_text() == text
        words = (
            "the same reader accepts and re-emits it"
            if faithful
            else "read-back changed its spelling"
        )
    except (LexicError, RecursionError, RuntimeError, ValueError) as refusal:
        return Generated(root, seed, "", False, str(refusal))
    return Generated(root, seed, text, faithful, words)
