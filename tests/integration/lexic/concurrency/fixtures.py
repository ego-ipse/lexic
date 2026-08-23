"""Grammars and documents the concurrency lane shares.

Two grammars, and the difference between them is the point. ``SPLITTING``
engages the split path, so a parse against it starts worker threads and takes
a pool lease that does real work; ``FLAT`` declines, so it exercises the
sequential path under thread pressure. Several tests need one or the other and
none of them should carry its own copy — a grammar repeated across files is
both a drift surface and a duplicate-code finding.

Deliberately NOT the adversarial suite's escape-run grammar. The lane should
not inherit another suite's witness: if that one were retuned for its own
reasons, these tests would change meaning without anybody editing them.
"""

from __future__ import annotations

from tests.split_helpers import engages

SPLITTING = 'root ::= line+\nline ::= [a-z0-9]* nl\nnl ::= "\\n"\n'
"""Newline-terminated lines — a shape whose split genuinely engages."""

FLAT = """\
root ::= "[" row ("," row)* "]"
row ::= "{" [a-z]+ ":" [0-9]+ "}"
"""
"""A bracketed record list, which declines to split at every size."""


def split_doc(seed: int = 0, lines: int = 2600) -> str:
    """A ``SPLITTING`` document whose every line carries ``seed``.

    The seed rides in the text so a model built from another thread's document
    is detectable BY VALUE, not merely by length.
    """
    tag = "a" * (seed + 1)
    return "\n".join(f"{tag}{line:05d}" for line in range(lines)) + "\n"


def flat_doc(seed: int = 0, rows: int = 200) -> str:
    """A ``FLAT`` document whose every row carries ``seed`` twice over."""
    key = "k" + "a" * (seed + 1)
    body = ",".join(f"{{{key}:{seed:02d}{row:04d}}}" for row in range(rows))
    return "[" + body + "]"


__all__ = ["FLAT", "SPLITTING", "engages", "flat_doc", "split_doc"]
