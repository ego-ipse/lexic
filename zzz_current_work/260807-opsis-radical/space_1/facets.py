"""What a relation shows — projections, each with its own coordinates.

A facet spells itself and answers its own asks, so nothing above it branches
on what it holds: the socket knows no kinds, the session knows no renderers,
and a new projection is a new class rather than an edit in four places.

The wire is line-oriented text::

    #FACET <name> <kind> <title>
    #NOTE <what looking at this tells you>
    ... whatever the kind means ...
    #END
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

__all__ = ["Facet", "Offers", "Plane", "Rows"]

Ask = Mapping[str, str]


class Facet:
    """One projection of one relation."""

    kind: str = "facet"

    def __init__(self, name: str, title: str, note: str = "") -> None:
        self.name = name
        self.title = title
        self.note = note

    def body(self) -> Sequence[str]:
        """The payload lines this kind means; empty when it is all asked for."""
        return ()

    def ask(self, query: Ask) -> str | None:
        """Answer one ask, or ``None`` when it is not this facet's question."""
        return None

    def wire(self) -> list[str]:
        """This facet, spelled. The emitter never inspects the payload."""
        out = [f"#FACET {self.name} {self.kind} {self.title}"]
        if self.note:
            out.append(f"#NOTE {self.note}")
        out.extend(self.body())
        out.append("#END")
        return out


class Plane(Facet):
    """Real text, so the browser's own selection works over it."""

    kind = "plane"

    def __init__(self, name: str, title: str, note: str, text: str) -> None:
        super().__init__(name, title, note)
        self.text = text

    def body(self) -> Sequence[str]:
        lines = self.text.split("\n")
        return [f"#TEXT {len(lines)}", *(f"|{line}" for line in lines)]


class Rows(Facet):
    """Pairs the relation already knows — measured, never implied."""

    kind = "rows"

    def __init__(
        self, name: str, title: str, note: str, pairs: Sequence[tuple[str, str]]
    ) -> None:
        super().__init__(name, title, note)
        self.pairs = list(pairs)

    def body(self) -> Sequence[str]:
        return [f"#ROW {key}\t{value}" for key, value in self.pairs]


class Offers(Facet):
    """Where you can go from here — computed by asking, never a menu.

    Every line is a licensed cast: a thing you can see, a relation kind, and
    the role it would take there. Nothing lists these; they are checked.
    """

    kind = "offers"

    def __init__(
        self,
        name: str,
        title: str,
        note: str,
        offers: Sequence[tuple[str, str, str, str]],
    ) -> None:
        super().__init__(name, title, note)
        self.offers = list(offers)

    def body(self) -> Sequence[str]:
        return [
            f"#CAST {tid} {kind} {role} {label}"
            for tid, kind, role, label in self.offers
        ]
