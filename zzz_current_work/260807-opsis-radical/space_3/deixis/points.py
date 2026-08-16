"""Pointing — what is open where you are standing, and what that lights.

A cursor is a point in the document. Three questions follow from it, and all
three were being answered in the leaf by scanning twelve thousand spans on
every frame:

- **what is OPEN here** — the derivation's own stack at this offset, which is
  the spine;
- **what just CLOSED** — the last few things finished before it, which is how
  you see the reading move;
- **what is LIT** — the rules those spans name, so the grammar, the relations
  and the railroad can all show the same thing at once.

Deixis is the resolution: one point, one set of names, every surface in
agreement. A surface that computed its own answer could disagree with its
neighbour, and did.
"""

from __future__ import annotations

from praxis.reading import Reading, Span

__all__ = ["closed_before", "lit_at", "open_at", "wire"]

# how many just-closed rows are worth keeping: enough to see the reading
# move, few enough that the list is read rather than scrolled
RECENT = 8


def open_at(reading: Reading, at: float) -> list[Span]:
    """The spans containing this point, outermost first — the live stack."""
    return sorted(
        (span for span in reading.spans if span.start <= at < span.end),
        key=lambda span: span.depth,
    )


def closed_before(reading: Reading, at: float, keep: int = RECENT) -> list[Span]:
    """The last spans to finish before this point, most recent last."""
    done = [span for span in reading.spans if span.end <= at]
    done.sort(key=lambda span: (span.end, span.depth))
    return done[-keep:]


def lit_at(reading: Reading, at: float, said: dict[str, str]) -> list[str]:
    """The rule names the live stack points at, spelled as the reading spells them."""
    seen: list[str] = []
    for span in open_at(reading, at):
        name = said.get(span.rule, span.rule)
        if name not in seen:
            seen.append(name)
    return seen


def _row(span: Span, reading: Reading, said: dict[str, str]) -> str:
    """One row: depth, the rule as named, its extent, and what it covers."""
    text = reading.text[span.start : min(span.end, span.start + 40)]
    return (
        f"{span.depth} {said.get(span.rule, span.rule)} {span.start} {span.end} "
        f"{text!r}"
    )


def wire(reading: Reading, at: float, said: dict[str, str]) -> str:
    """The point, spelled: what is open, what just closed, what is lit."""
    live = open_at(reading, at)
    done = closed_before(reading, at)
    names = lit_at(reading, at, said)
    return "\n".join(
        [
            f"#OPEN {len(live)}",
            *(_row(span, reading, said) for span in live),
            f"#CLOSED {len(done)}",
            *(_row(span, reading, said) for span in reversed(done)),
            f"#LIT {len(names)}",
            *names,
            "",
        ]
    )
