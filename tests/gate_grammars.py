"""Shared grammars for the FOLLOW-window loop gate's two test layers.

The gate's unit test asks what the certifier returns; its parity test asks
whether the two engines still agree once it fires. Both need the SAME language,
because a gate proved on one grammar and exercised on another proves nothing
about either — and two copies would drift the moment one file's terminator
changed.

One copy, therefore, with the property that makes it the class written down
beside it rather than left to be re-derived by whoever reads the next file.
"""

from __future__ import annotations

ARM_FINAL_LOOP = (
    "root ::= run sep\n"
    "run ::= word+\n"
    "word ::= [a-z]+ sp\n"
    'sep ::= "e." nl\n'
    'sp ::= " "\n'
    'nl ::= "\\n"\n'
)
"""The gate's class, as small as it goes.

`run ::= word+` is the arm's LAST item, `run` is referenced exactly once, and
the terminator's first character `e` is also a legal word character. So no
single-character stop set decides the loop, and FOLLOW\\ :sub:`2` does, because
no word's second character can be `.`.
"""

REPEATED_ARM_FINAL_LOOP = ARM_FINAL_LOOP.replace(
    "root ::= run sep\n", "root ::= entry+\nentry ::= run sep\n"
)
"""The same class under an outer repetition — many documents in one text, so a
gate that is wrong by one iteration compounds instead of cancelling."""

NULL_ARM = ARM_FINAL_LOOP.replace('"e."', '"%."')
"""The same language shape with a terminator no word can begin with.

`%` is outside `[a-z]`, so the cheapest tier settles the loop at k = 1 and the
FOLLOW-window gate is never reached. Both layers use it to prove they are not
passing because nothing was gated.
"""

REPEATED_NULL_ARM = REPEATED_ARM_FINAL_LOOP.replace('"e."', '"%."')
"""`NULL_ARM` under the same outer repetition as `REPEATED_ARM_FINAL_LOOP`."""
