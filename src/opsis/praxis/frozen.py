"""The session file — a session as IR, and back.

Freezing writes what a session IS: readings that name each other. It is
not a screenshot and not a dump, it is the same records the instrument
runs on, spelled in lexic's own notation and read back by lexic's own
reader. There is no opsis format and no opsis parser.

That is the point of holding a binding as an ident rather than as a
tokenizer: a session with a ten-megabyte vocabulary bound to it saves
as the sentence that says so.
"""

from __future__ import annotations

from lexic.compile import Directives, load_ir
from lexic.compile.notation.emit import emit_ir
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrNamedTuple, IrSeq, IrStr
from opsis.praxis.ingress import SHIPPED, manifests
from opsis.praxis.reading import Reading
from opsis.praxis.session import Session

__all__ = ["SESSION_SYMBOLS", "Held", "Saved", "freeze", "thaw"]


class Held(IrNamedTuple[str, str, str, str, str, str, str, str, str]):
    """One reading, as the nine facts that reproduce it.

    Not its product: a product is what reading produces, and a session
    file that carried one would be asserting a result rather than
    recording an input. Thawing reads everything again.
    """

    ident: IrStr
    title: IrStr
    kind: IrStr
    reader: IrStr
    origin: IrStr
    vocabulary: IrStr
    start: IrStr
    non_semantic: IrStr
    text: IrStr


class Saved(IrSeq[Held]):
    """A whole session — its readings, in the order they were opened."""


SESSION_SYMBOLS: dict[str, type] = {"Held": Held, "Saved": Saved}
"""What :func:`thaw` reads a session file's constructors as."""


def freeze(session: Session) -> str:
    """A session as notation text — what :func:`thaw` reads back."""
    return emit_ir(Saved(*(_held(r) for r in session.readings.values())))


def _held(reading: Reading) -> Held:
    """One reading's facts, spelled flat so the file stays readable.

    A text that came from a file is not copied into the session file:
    the file is where it lives, and duplicating it would mean a saved
    session could disagree with the workspace it names. A typed text has
    nowhere else to be, so it is carried.
    """
    names = reading.params.directives.non_semantic or ()
    return Held(
        IrStr(reading.ident),
        IrStr(reading.title),
        IrStr(reading.kind),
        IrStr(reading.reader),
        IrStr(reading.params.origin),
        IrStr(reading.params.bound),
        IrStr(reading.params.directives.start or ""),
        IrStr(",".join(sorted(str(n) for n in names))),
        IrStr("" if reading.params.origin else reading.text),
    )


def thaw(session: Session, text: str) -> int:
    """Replace a session's readings with the ones a file records.

    Read in file order and then read again: a reading whose reader is
    another reading cannot resolve until that one exists, so the second
    pass is what makes naming order-free. Surfaces are untouched — the
    flavours lexic ships are seeded, not saved.

    :param session: The session to refill.
    :param text: A session file, as :func:`freeze` wrote it.
    :returns: How many readings came back.
    :raises UnsupportedConstructError: If the text is not a session.
    """
    try:
        saved = load_ir(text, symbols=SESSION_SYMBOLS)
    except (TypeError, ValueError) as exc:
        # A well-formed expression can still be a malformed record —
        # the notation reads it, the constructor refuses it.
        raise UnsupportedConstructError(f"thaw: {exc}") from exc
    if not isinstance(saved, Saved):
        raise UnsupportedConstructError(
            f"thaw: that is a {type(saved).__name__}, not a saved session"
        )
    session.readings.clear()
    for held in saved:
        _restore(session, Held.ensure(held, "thaw: a reading"))
    for ident in list(session.readings):
        session.read(ident)
    return len(saved)


def _restore(session: Session, held: Held) -> None:
    """One reading back, with its text re-read from where it came from.

    A reading that came from a file gets its text from that file again,
    so a session reopened after the file changed shows the file rather
    than what the file used to say.
    """
    reading = Reading(
        str(held.ident),
        str(held.title),
        str(held.kind),
        str(held.reader),
        _text(session, held),
        str(held.origin),
    )
    reading.params.bound = str(held.vocabulary)
    reading.params.directives = _directives(held)
    session.readings[reading.ident] = reading
    session.claim(reading.ident)


def _text(session: Session, held: Held) -> str:
    """A reading's text — from wherever it came from, read again now."""
    origin = str(held.origin)
    if not origin:
        return str(held.text)
    if origin.startswith(SHIPPED):
        return dict(manifests()).get(origin.removeprefix(SHIPPED), "")
    try:
        return session.root.joinpath(origin).read_text(encoding="utf-8")
    except OSError:
        return ""


def _directives(held: Held) -> Directives:
    """The chips a saved reading carried."""
    names = str(held.non_semantic)
    return Directives(
        start=str(held.start) or None,
        non_semantic=frozenset(names.split(",")) if names else None,
    )
