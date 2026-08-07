"""The constraint cursor — what a grammar admits next, at a prefix.

Generation is id-space, so this is its own surface and not a second
parse. A mask is a fact about a PREFIX, which is why it cannot be a
static window: there is no mask until someone has pushed something, and
pushing is the whole interaction.

The cursor is per-reading and per-read: editing the grammar or its
vocabulary throws the prefix away, because a prefix admitted by the old
grammar means nothing under the new one.
"""

from __future__ import annotations

from opsis.praxis.reading import Reading
from opsis.praxis.session import Session

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrTokenizer

__all__ = ["Cursors", "Prefix"]

SHOWN = 24
"""How many admissible tokens a mask shows before it states the rest."""


class Prefix:
    """One reading's constraint cursor, and the tokens pushed into it."""

    __slots__ = ("compiled", "cursor", "pushed", "vocabulary")

    def __init__(self, reading: Reading) -> None:
        compiled = reading.compiled
        if compiled is None:
            raise UnsupportedConstructError("constrain: nothing compiled here")
        self.compiled = compiled
        self.cursor = compiled.constrain()
        self.vocabulary = compiled.tokens.tokenizer
        self.pushed: list[int] = []

    @property
    def text(self) -> str:
        """What the pushed tokens spell."""
        return "".join(self._spelling(i) for i in self.pushed)

    def _spelling(self, ident: int) -> str:
        """One token id, as the characters it stands for."""
        vocab = self.vocabulary
        if vocab is None:
            return f"<{ident}>"
        return str(vocab.decode.get(ident, f"<{ident}>"))

    def mask(self) -> set[int]:
        """The admissible next-token ids at this prefix."""
        return self.cursor.mask()

    def push(self, ident: int) -> None:
        """Advance by one token, refusing one the mask does not admit.

        The refusal is the point: a cursor that accepted an inadmissible
        token would be answering a question about a string the grammar
        does not have.
        """
        admitted = self.mask()
        if ident not in admitted:
            raise UnsupportedConstructError(
                f"token {ident} ({self._spelling(ident)!r}) is not admitted here — "
                f"{len(admitted):,} others are"
            )
        self.cursor.push(ident)
        self.pushed.append(ident)

    def push_text(self, text: str) -> int:
        """Push whichever admitted token spells ``text``.

        :returns: The token id pushed.
        :raises UnsupportedConstructError: When no admitted token spells
            it — which names the nearest ones rather than just refusing.
        """
        want = {i for i in self.mask() if self._spelling(i) == text}
        if not want:
            raise UnsupportedConstructError(
                f"nothing admitted here spells {text!r} — "
                f"{sample(self.mask(), self.vocabulary)}"
            )
        ident = min(want)
        self.push(ident)
        return ident

    def back(self) -> None:
        """Undo the last push by replaying the prefix without it.

        A cursor advances; it does not rewind. Replaying is what undo
        HONESTLY is here, and it is cheap because a prefix is short.
        """
        if not self.pushed:
            raise UnsupportedConstructError("nothing pushed yet")
        keep = self.pushed[:-1]
        self.cursor = self.compiled.constrain()
        self.pushed = []
        for ident in keep:
            self.push(ident)

    def accepts(self) -> bool:
        """Whether the prefix pushed so far is a whole string."""
        return self.cursor.accepts()


class Cursors:
    """Every reading's cursor, thrown away whenever that reading re-reads."""

    __slots__ = ("held", "stamp")

    def __init__(self) -> None:
        self.held: dict[str, Prefix] = {}
        self.stamp: dict[str, int] = {}

    def of(self, session: Session, ident: str) -> Prefix:
        """This reading's cursor, fresh if the reading has changed."""
        reading = session.readings.get(ident)
        if reading is None:
            raise UnsupportedConstructError("that reading is no longer here")
        now = id(reading.product)
        if self.stamp.get(ident) != now or ident not in self.held:
            self.held[ident] = Prefix(reading)
            self.stamp[ident] = now
        return self.held[ident]

    def reset(self, session: Session, ident: str) -> Prefix:
        """Throw this reading's prefix away and start again."""
        self.held.pop(ident, None)
        self.stamp.pop(ident, None)
        return self.of(session, ident)


def sample(mask: set[int], vocabulary: IrTokenizer | None) -> str:
    """A mask as something a person reads — a look, and the honest count."""
    if not mask:
        return "nothing is admitted — only the end of input"
    shown = sorted(mask)[:SHOWN]
    spell = [
        repr(str(vocabulary.decode.get(i, f"<{i}>"))) if vocabulary else str(i)
        for i in shown
    ]
    rest = f" (of {len(mask):,})" if len(mask) > SHOWN else ""
    return ", ".join(spell) + rest
