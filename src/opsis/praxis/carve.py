"""Templating — extracting the parts of a document you named.

A template says which paths of a document to keep and throws the rest
away without building it. That takes two things the grammar cannot
supply on its own: which of its rules make a mapping level, and which
paths to keep. Both are stated here, and both are read from text rather
than typed in Python.

The shape is not guessed. A grammar that maps has rules that do it, and
only someone who knows the grammar knows which — so the window asks,
tries what it was told, and shows the refusal when the answer is wrong.
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.compile import CompiledGrammar
from lexic.compile.templating import KEEP, MapShape, template
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir import IrMap, IrTuple
from lexic.model import GrammarModel

__all__ = [
    "BENCHES",
    "Bench",
    "Carve",
    "Shape",
    "bench",
    "carve",
    "read_shape",
    "read_spec",
    "run_bench",
]


class Shape(NamedTuple):
    """The four rule names a mapping level is made of."""

    section: str = ""
    entry: str = ""
    key: str = ""
    value: str = ""

    @property
    def stated(self) -> bool:
        """Whether all four are given — three of four extracts nothing."""
        return all(self)


class Carve(NamedTuple):
    """One extraction: what came out, and what it cost."""

    paths: tuple[tuple[str, str], ...]
    note: str


class Bench(NamedTuple):
    """What a reading was last told to carve — held per reading."""

    shape: str = ""
    spec: str = ""
    result: Carve = Carve((), "name a shape and some paths, then extract")


def read_shape(text: str) -> Shape:
    """A shape from four comma-separated names.

    :param text: ``section, entry, key, value``.
    :returns: The shape, with whatever was left out left empty.
    """
    parts = [p.strip() for p in text.split(",")]
    return Shape(*(parts + ["", "", "", ""])[:4])


def read_spec(text: str) -> IrMap:
    """A keep-spec from one path per line.

    Dotted paths, because a spec IS a tree and a line is a branch of it:
    ``b.c`` keeps the ``c`` inside the ``b`` section. Nothing here is
    Python — a spec typed into a window is text like everything else.

    :param text: One dotted path per line; blanks and ``#`` lines ignored.
    :returns: The lifted spec, ready for :func:`template`.
    """
    tree: dict[str, object] = {}
    for line in text.splitlines():
        path = line.split("#", 1)[0].strip()
        if path:
            _graft(tree, [p for p in path.split(".") if p])
    return _lift(tree)


def _graft(tree: dict[str, object], path: list[str]) -> None:
    """Put one path into the spec tree, deepening as it goes."""
    if not path:
        return
    head, rest = path[0], path[1:]
    if not rest:
        tree[head] = KEEP
        return
    below = tree.get(head)
    if not isinstance(below, dict):
        below = {}
        tree[head] = below
    _graft(below, rest)


def _lift(tree: dict[str, object]) -> IrMap:
    """A spec tree as the map templating takes."""
    return IrMap(
        *(
            IrTuple(name, _lift(sub) if isinstance(sub, dict) else KEEP)
            for name, sub in tree.items()
        )
    )


def carve(compiled: CompiledGrammar, shape: Shape, spec: str, text: str) -> Carve:
    """Extract the spec'd paths of ``text`` and say what came out.

    :raises UnsupportedConstructError: When the shape does not match the
        grammar, the spec names a level the shape cannot reach, or the
        document does not parse — each of which is a real answer about
        what was asked, not a failure to try.
    """
    if not shape.stated:
        raise UnsupportedConstructError(
            "a shape needs all four names: section, entry, key, value"
        )
    keep = read_spec(spec)
    if not len(keep):
        raise UnsupportedConstructError("nothing to keep — name a path")
    built = template(compiled, MapShape(*shape), keep)
    out = built.run(text)
    paths = tuple(
        (".".join(str(p) for p in path), _shown(value)) for path, value in out.items()
    )
    asked = _leaves(keep)
    missing = asked - len(paths)
    note = f"{len(paths)} of {asked} paths kept"
    return Carve(
        paths, note + (f" · {missing} absent from the document" if missing else "")
    )


def _leaves(spec: IrMap) -> int:
    """How many paths a spec asks for — its leaves, not its top level."""
    return sum(
        _leaves(value) if isinstance(value, IrMap) else 1
        for _key, value in spec.items()
    )


def _shown(value: object) -> str:
    """One extracted value as its own text.

    A kept value is a model, so it can spell itself; anything else says
    what it is rather than being made to pretend.
    """
    if isinstance(value, GrammarModel):
        return value.to_text()
    return str(value)


BENCHES: dict[str, Bench] = {}
"""What each reading's template window has been told, by reading ident.

Held beside the session rather than in it: a template is a question
asked OF a reading, not a fact about it, and a session file that carried
one would be recording somebody's last experiment as part of the work.
"""


def bench(ident: str) -> Bench:
    """This reading's template bench, empty until it is used."""
    return BENCHES.setdefault(ident, Bench())


def run_bench(
    ident: str, compiled: CompiledGrammar, shape: str, spec: str, text: str
) -> Bench:
    """Carve with what the window says, and hold the answer.

    A refusal is held exactly like a result: the window's job is to say
    what happened, and "the shape does not match this grammar" is the
    most useful thing it can say.
    """
    try:
        result = carve(compiled, read_shape(shape), spec, text)
    except (UnsupportedConstructError, LexicError) as exc:
        result = Carve((), f"{type(exc).__name__}: {exc}")
    BENCHES[ident] = Bench(shape, spec, result)
    return BENCHES[ident]
