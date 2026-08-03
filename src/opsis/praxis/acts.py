"""What a reading can DO — the deeds beside the read.

Reading is the relation; these are the other things lexic can do with
what a reading produced, and each one is offered only where its input
exists. A grammar that compiled can generate and can be written out; a
grammar with no vocabulary bound cannot be constrained, and says so by
not offering it.

Every deed that writes ends by OPENING what it wrote. That is not
politeness: a twin that will not read back is a broken twin, and the
only way to know is to read it back.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import NamedTuple

from lexic.compile import CompiledGrammar
from lexic.compile.module.export import export_module
from lexic.compile.payload.export import export_value
from lexic.exceptions import UnsupportedConstructError
from lexic.generate import generate
from lexic.ir import IrSelf, IrTokenizer
from lexic.model import GrammarModel
from opsis.praxis.ingress import open_file
from opsis.praxis.reading import Reading, Source
from opsis.praxis.session import Session

__all__ = ["Deed", "deeds", "perform"]

SHELF = "generated"
"""Where written artefacts land — lexic's own shelf, inside the workspace."""

_SAMPLES = 8
"""How many strings one generate deed produces."""


class Deed(NamedTuple):
    """One thing a reading can do, and what it says it will do."""

    name: str
    label: str
    why: str


def deeds(reading: Reading) -> list[Deed]:
    """What this reading can do — from what it HAS, never from its kind."""
    out: list[Deed] = []
    compiled = reading.compiled
    if compiled is not None:
        out.append(
            Deed(
                "generate",
                "generate",
                f"{_SAMPLES} random strings in this grammar's language, "
                "each opened as a text it reads",
            )
        )
        out.append(
            Deed(
                "twin",
                "write twin",
                f"the importable module, into {SHELF}/ — then read back",
            )
        )
        if compiled.tokens.tokenizer is not None:
            out.append(
                Deed(
                    "constrain",
                    "constrain",
                    "the admissible next tokens at every prefix",
                )
            )
    if isinstance(reading.product, IrSelf) and compiled is None:
        out.append(
            Deed(
                "value",
                "write value",
                f"this product as a self-contained module in {SHELF}/",
            )
        )
    return out


def perform(session: Session, reading: Reading, name: str) -> str:
    """Do one of a reading's deeds and say what happened.

    :raises UnsupportedConstructError: When the deed is not one this
        reading offers — which is a real refusal, since the fan draws
        only the deeds it has.
    """
    if name not in {deed.name for deed in deeds(reading)}:
        raise UnsupportedConstructError(
            f"{reading.title} cannot {name!r} — it offers "
            f"{[d.name for d in deeds(reading)] or 'nothing'}"
        )
    return _DO[name](session, reading)


def _artefact(reading: Reading) -> CompiledGrammar:
    """The grammar this reading IS, or the refusal saying it is not one.

    Never an assert: a deed offered on a reading that turns out not to
    have one is something the person doing it should be TOLD, and an
    assertion error is not a sentence anybody can act on.
    """
    held = reading.compiled
    if held is None:
        raise UnsupportedConstructError(f"{reading.title} is not a compiled grammar")
    return held


def _generate(session: Session, reading: Reading) -> str:
    """Random strings in the grammar's language, each opened under it."""
    compiled = _artefact(reading)
    rules = {str(rule.name): rule for rule in compiled.grammar.rules}
    start = str(compiled.grammar.start) or next(iter(rules), "")
    rng = random.Random(len(reading.text))
    made = [generate(start, rules, rng=rng) for _ in range(_SAMPLES)]
    for i, text in enumerate(sorted(set(made), key=len)):
        session.add(f"generated {i + 1}", "text", reading.ident, Source(text))
    return f"generated {len(set(made))} distinct strings from {start!r}"


def _twin(session: Session, reading: Reading) -> str:
    """The importable module, written and then read back as a reading."""
    compiled = _artefact(reading)
    stem = _stem(reading)
    path = export_module(compiled, session.root / SHELF / f"{stem}.py", stem=stem)
    return _reopen(session, path, f"wrote {stem}.py")


def _value(session: Session, reading: Reading) -> str:
    """This reading's product as a module, written and read back.

    A model's classes were synthesized, so they have no importable home
    until one is written: the twin of the grammar that read this text IS
    that home, and it is written first rather than demanded of whoever
    clicked. A product built only from spine classes needs none, and
    gets none.
    """
    stem = f"{_stem(reading)}_value"
    home = _home(session, reading)
    path = export_value(
        reading.product, session.root / SHELF / f"{stem}.py", module=home
    )
    wrote = f"wrote {stem}.py" if home is None else f"wrote {stem}.py beside its twin"
    return _reopen(session, path, wrote)


def _home(session: Session, reading: Reading) -> str | None:
    """Where a product's classes will be importable from, written if need be.

    :returns: The dotted module name, or ``None`` when the product names
        only spine classes and no twin is involved.
    """
    if not isinstance(reading.product, GrammarModel):
        return None
    above = session.readings.get(reading.reader)
    compiled = above.compiled if above is not None else None
    if above is None or compiled is None:
        raise UnsupportedConstructError(
            "this model's classes came from a grammar that is no longer here, "
            "so there is nowhere to import them from"
        )
    stem = _stem(above)
    export_module(compiled, session.root / SHELF / f"{stem}.py", stem=stem)
    return f"{SHELF}.{stem}"


def _constrain(_session: Session, reading: Reading) -> str:
    """State the binding a constraint cursor would run over.

    The cursor itself is driven from its window, one token at a time,
    because a mask is a fact about a PREFIX and there is no prefix until
    someone has pushed one.
    """
    compiled = _artefact(reading)
    vocab = IrTokenizer.ensure(compiled.tokens.tokenizer, "a bound vocabulary")
    return f"constrained by {vocab.name} · {len(vocab.encode):,} entries"


def _reopen(session: Session, path: Path, note: str) -> str:
    """Open what was just written, so the write is proved by a read."""
    rel = str(path.relative_to(session.root).as_posix())
    opened = open_file(session.root, rel)
    if opened.reader is None:
        return f"{note} · but nothing reads it back — {opened.note}"
    session.add(
        opened.title,
        opened.kind,
        session.surface(opened.reader),
        Source(opened.text, rel),
    )
    return f"{note} · {opened.note}, read back"


def _stem(reading: Reading) -> str:
    """A filename stem from a reading's whole title.

    The whole title, extension included: ``json.gbnf`` and ``json.abnf``
    are two formulations of one language and would otherwise write over
    each other, and a bare ``json.py`` on the shelf is a name real
    modules already use.
    """
    keep = [c if c.isalnum() else "_" for c in reading.title.lower()]
    return "".join(keep).strip("_").removesuffix("_py") or "grammar"


_DO = {
    "generate": _generate,
    "twin": _twin,
    "value": _value,
    "constrain": _constrain,
}
"""Deed name → what doing it does."""
