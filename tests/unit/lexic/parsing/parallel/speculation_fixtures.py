"""The announced-section grammar, shared by the cut and speculation tests.

A section ends where the NEXT one begins: it closes at a newline and is full of
newlines, so no occurrence of its boundary character is a boundary by itself.
What forces the segmentation is the OPENING — nothing a section continues with
is ``#`` — which is the property speculation rests on, and the reason both the
precondition tests and the cut-arithmetic tests want the same fixture.
"""

from __future__ import annotations

ANNOUNCED = (
    "root ::= section+\n"
    "section ::= header line*\n"
    "header ::= hash text nl\n"
    "line ::= text nl\n"
    "text ::= [a-z ]+\n"
    'hash ::= "#"\n'
    'nl ::= "\\n"\n'
)

_WORDS = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")


def announced_doc(sections: int) -> str:
    """Sections of a header and a varying body, so cut targets land unevenly."""
    out: list[str] = []
    for n in range(sections):
        out.append(f"#{_WORDS[n % 6]} chapter opens here\n")
        out.extend(
            f"prose about {_WORDS[(n + k) % 6]} continues on\n"
            for k in range(3 + n % 4)
        )
    return "".join(out)
