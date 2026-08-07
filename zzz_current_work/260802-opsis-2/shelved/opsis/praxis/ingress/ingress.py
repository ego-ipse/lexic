"""Ingress — a file becomes a reading, and what reads it is inferred.

The write side of lexic infers its target from the gesture rather than
from a flag; reads are the mirror. What a file becomes follows from
what successfully READS it, tried cheapest first:

- a grammar extension  → that flavour reads it
- a vocabulary document → a json formulation reads it into a tokenizer
- a flavour manifest   → the notation reads it, and its product reads
- a session file       → the scene notation reads it
- a compiled value     → Python reads it, by importing it
- an exported twin     → lexic's module grammar reads it
- a saved session      → it replaces the session rather than joining it
- IR notation          → the notation reads it
- anything else        → a TEXT, waiting for something to read it

Nothing here takes a "kind" argument, and nothing is refused: a file no
reader claims is a text, which is the honest answer and a real state.
What a text MEANS is whatever ends up reading it.

Reads are workspace-scoped. That is a boundary, not a shelf list: the
whole workspace is reachable and nothing outside it is.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Callable, NamedTuple

from opsis.praxis.reading import Params, Reader, _flavour_reader

from lexic import grammars
from lexic.api.json_tokenizer import tokenizer_of
from lexic.compile import compile_ast, load_ir, parse_module
from lexic.compile.module.selfgrammar import MODULE_GRAMMAR
from lexic.compile.notation.loader import load_flavour
from lexic.compile.notation.parse import NOTATION_GRAMMAR
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.grammars import flavour_for_extension
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrAst, IrMap
from lexic.parsing import Reducer, parse_reduced

__all__ = [
    "Entry",
    "Opened",
    "browse",
    "SHIPPED",
    "manifest_reader",
    "manifests",
    "open_file",
    "resolve",
    "surfaces",
    "vocabulary_reader",
]

_VALUE_MARK = "A compiled value"
"""How an exported value names itself, in its own first line."""

SHIPPED = "lexic ships "
"""How a seeded flavour records where its manifest came from."""

_VOCAB_MARK = '"added_tokens"'
"""What a ``tokenizer.json`` document says early and nothing else does."""


class Entry(NamedTuple):
    """One row of the workspace, as a picker draws it."""

    kind: str
    path: str
    name: str
    size: str


class Opened(NamedTuple):
    """What a file turned out to be, and what should read it."""

    title: str
    kind: str
    text: str
    reader: Reader | None
    note: str


def resolve(root: Path, rel: str) -> Path:
    """A workspace path, or the scope refusal.

    :raises UnsupportedConstructError: When ``rel`` leaves the
        workspace — reading beyond it would be a different decision,
        not an interpretation of this one.
    """
    path = (root / rel).resolve() if rel else root
    if not path.is_relative_to(root):
        raise UnsupportedConstructError(
            f"ingress: {rel!r} resolves outside the workspace"
        )
    return path


def browse(root: Path, rel: str = "") -> list[Entry]:
    """One directory of the workspace, directories first.

    Everything the workspace holds is reachable — a manifest beside the
    source is as openable as a grammar in a fixtures directory — and a
    file carries its size, so a thirty-megabyte read is never a
    surprise.
    """
    here = resolve(root, rel)
    if not here.is_dir():
        return []
    rows: list[Entry] = []
    if rel:
        parent = str(Path(rel).parent.as_posix())
        rows.append(Entry("dir", "" if parent == "." else parent, "..", ""))
    for path in sorted(here.iterdir(), key=lambda p: (p.is_file(), p.name)):
        if path.name.startswith(".") or path.name == "__pycache__":
            continue
        child = str(path.relative_to(root).as_posix())
        if path.is_dir():
            rows.append(Entry("dir", child, f"{path.name}/", ""))
        elif path.suffix != ".pyc":
            rows.append(Entry("file", child, path.name, _scaled(path.stat().st_size)))
    return rows


def _scaled(size: int) -> str:
    """A byte count as something a person reads."""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size // 1024} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def manifests() -> list[tuple[str, str]]:
    """Every flavour lexic ships, as the manifest text that declares it.

    Found by convention rather than named in a list: a flavour declares
    itself in a ``<name>.flavour.ir`` beside its module, so a flavour
    added to lexic shows up here without opsis learning its name. That
    is also why the shipped three are not special — they are seeded from
    their manifests exactly as one of yours would be, which is what
    makes editing one, or opening your own, the same gesture.

    :returns: ``(file name, manifest text)`` per shipped flavour.
    """
    home = Path(str(grammars.__file__)).parent
    return [
        (path.name, path.read_text(encoding="utf-8"))
        for path in sorted(home.glob("*.flavour.ir"))
    ]


def surfaces() -> list[Reader]:
    """The readers lexic ships, each carrying its own grammar.

    These are not a hard-coded menu of what opsis supports: they are
    the surfaces lexic itself exposes, and a session gains more the
    moment it opens a manifest.
    """
    return [
        Reader(
            "notation",
            "notation",
            lambda text, params: compile_ast(
                _notation_ast(text), directives=params.directives
            ),
            instance=_notation_ast,
            grammar=NOTATION_GRAMMAR,
        ),
        Reader(
            "module grammar",
            "module",
            lambda text, params: compile_ast(
                _twin_ast(text), directives=params.directives
            ),
            instance=parse_module,
            grammar=MODULE_GRAMMAR,
        ),
    ]


def _notation_ast(text: str) -> IrAst:
    """One notation read, narrowed to a grammar."""
    return IrAst.ensure(load_ir(text), "notation: a grammar expression")


def _twin_ast(text: str) -> IrAst:
    """The grammar an exported twin carries."""
    return IrAst.ensure(parse_module(text).grammar, "twin: its GRAMMAR")


def _python_reader(root: Path) -> Reader:
    """Python as a reader — a compiled value rebuilds itself on import.

    Importing IS the read for this artefact: the module decodes its own
    payload and checks its digest on the way in. Nothing else can read
    it, and pretending otherwise would mean decoding a value against
    symbols it never named. The read goes by origin because a module is
    imported by path — its source text is what a person LOOKS at, not
    what produces the value.
    """

    def read(_text: str, params: Params) -> object:
        return _import_value(root, params.origin)

    return Reader("python", "python", read)


def _import_value(root: Path, rel: str) -> object:
    """Import the module at ``rel`` and hand back the value it rebuilt."""
    name = rel.removesuffix(".py").replace("/", ".").replace("\\", ".")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        module = importlib.reload(importlib.import_module(name))
    except Exception as exc:  # foreign code fails in its own ways
        raise UnsupportedConstructError(_stale(rel, exc)) from exc
    if not hasattr(module, "VALUE"):
        raise UnsupportedConstructError(f"{rel}: imported, but it names no VALUE")
    return module.VALUE


def _stale(rel: str, exc: Exception) -> str:
    """Why a value would not come back, said so it can be acted on.

    The usual cause is an artefact older than the lexic reading it: a
    payload records where each symbol came from, and a module that has
    since moved makes the value unreadable AS RECORDED. That is the
    digest check working, so the message names the moves and the
    remedy instead of repeating a traceback.
    """
    text = str(exc)
    moves = [part for part in text.split("'") if " -> " in part]
    if not moves:
        return f"{rel} did not import — {type(exc).__name__}: {text[:200]}"
    shown = "; ".join(moves[:3])
    more = f" (and {len(moves) - 3} more)" if len(moves) > 3 else ""
    return (
        f"{rel} was exported by an older lexic: {len(moves)} of its symbols "
        f"have moved — {shown}{more}. A value cannot be decoded against "
        "symbols it did not name. Regenerate it from the grammar it came from."
    )


def vocabulary_reader(
    grammar: IrAst = JSON_GRAMMAR,
    reducer: Reducer = JSON_REDUCER,
    *,
    name: str = "vocabulary",
    of: str = "",
) -> Reader:
    """A json formulation, reading a vocabulary document into a tokenizer.

    The formulation is the parameter it always is: the shipped one is a
    default, not a privileged reader, and dropping any json grammar onto
    a vocabulary node rebuilds this reader around THAT grammar. What
    comes back is an :class:`~lexic.ir.IrTokenizer`, which is what makes
    the node bindable to a grammar — the second reading is the reduced
    document itself, so the vocabulary can also just be READ.

    :param grammar: The json formulation to read the document with.
    :param reducer: That formulation's reducer.
    :param name: What it is called on screen.
    :param of: The reading this reader came out of, if any.
    """

    def refine(doc: object, params: Params) -> object:
        return tokenizer_of(IrMap.ensure(doc, "the document"), _stem(params.origin))

    return Reader(
        name,
        "vocabulary",
        lambda text, params: refine(parse_reduced(grammar, text, reducer), params),
        instance=lambda text: parse_reduced(grammar, text, reducer),
        refine=refine,
        grammar=grammar,
        of=of,
    )


def _article(name: str) -> str:
    """``a`` or ``an``, by how the name is said."""
    return f"{'an' if name[:1].lower() in 'aeiou' else 'a'} {name}"


def _stem(rel: str) -> str:
    """A vocabulary's name — its file's stem up to the first dot."""
    return Path(rel).name.split(".", 1)[0] if rel else "vocabulary"


def open_file(root: Path, rel: str) -> Opened:
    """A file, and what turned out to read it.

    Each attempt in turn, cheapest first, so a large file is never
    parsed six ways before the answer that was obvious from its first
    line. What nothing claims is a refusal naming everything that was
    tried — a list nobody has to keep in sync, because it IS the list
    of attempts.
    """
    path = resolve(root, rel)
    text = _slurp(path, rel)
    for attempt in _ATTEMPTS:
        opened = attempt(root, path, text)
        if opened is not None:
            return opened
    return Opened(path.name, "text", text, None, _just_text(rel))


def _just_text(rel: str) -> str:
    """What a file is when no reader claimed it: a text.

    Not a refusal. Everything is text — a README, a source file, a log
    — and what it MEANS is whatever ends up reading it. Refusing to
    open one would be opsis deciding in advance that a file could not
    be a document, or a grammar for some level below.
    """
    tried = ", ".join(_TRIED[:-1]) + f", or {_TRIED[-1]}"
    return (
        f"{Path(rel).name} · a text — nothing here reads it yet. It is not "
        f"{tried}, but structure is what gives a text meaning: drop a reader "
        "on it and see."
    )


def _as_value(root: Path, path: Path, text: str) -> Opened | None:
    """A compiled value — read by importing it."""
    if path.suffix != ".py" or _VALUE_MARK not in text[:400]:
        return None
    return Opened(path.name, "value", text, _python_reader(root), "a compiled value")


def _as_twin(_root: Path, path: Path, text: str) -> Opened | None:
    """An exported twin — lexic's module grammar reads it."""
    if path.suffix != ".py" or not _reads(lambda: parse_module(text)):
        return None
    return Opened(path.name, "grammar", text, _module_surface(), "an exported twin")


def _as_vocabulary(_root: Path, path: Path, text: str) -> Opened | None:
    """A vocabulary document — a json formulation reads it."""
    if path.suffix != ".json" or _VOCAB_MARK not in text[:4000]:
        return None
    return Opened(
        path.name,
        "vocabulary",
        text,
        vocabulary_reader(),
        f"a vocabulary document · {_scaled(len(text))} to read",
    )


def _as_grammar(_root: Path, path: Path, text: str) -> Opened | None:
    """A grammar — whichever flavour claims its extension."""
    try:
        flavour = flavour_for_extension(path.name)
    except UnsupportedConstructError:
        return None
    return Opened(
        path.name,
        "grammar",
        text,
        _flavour_reader(flavour),
        f"{_article(str(type(flavour).name))} grammar",
    )


def _as_session(_root: Path, path: Path, text: str) -> Opened | None:
    """A saved session — it replaces the session rather than joining it."""
    if not text.lstrip().startswith("Saved("):
        return None
    return Opened(path.name, "session", text, None, "a saved session")


def _as_manifest(_root: Path, path: Path, text: str) -> Opened | None:
    """A manifest — the notation reads it into the reader it declares."""
    if not _reads(lambda: load_flavour(text)):
        return None
    loaded = load_flavour(text)
    return Opened(
        path.name,
        "manifest",
        text,
        manifest_reader(),
        f"a manifest declaring {type(loaded).name}",
    )


def _as_notation(_root: Path, path: Path, text: str) -> Opened | None:
    """IR notation — a grammar written as the constructors it is."""
    if not _reads(lambda: _notation_ast(text)):
        return None
    return Opened(path.name, "grammar", text, _notation_surface(), "IR notation")


_ATTEMPTS: tuple[Callable[[Path, Path, str], Opened | None], ...] = (
    _as_value,
    _as_twin,
    _as_vocabulary,
    _as_grammar,
    _as_session,
    _as_manifest,
    _as_notation,
)
"""Every way a file can be read, in the order they are cheap to try."""

_TRIED = (
    "a compiled value",
    "an exported twin",
    "a vocabulary",
    "a grammar surface",
    "a saved session",
    "a manifest",
    "IR notation",
)
"""What :data:`_ATTEMPTS` tried, said the way a person would."""


def _slurp(path: Path, rel: str) -> str:
    """A file's text, or the refusal that says why there is none.

    A file that vanished between the picker drawing it and someone
    clicking it is an ordinary thing to happen, and a binary one is an
    ordinary mistake. Neither is allowed to be an exception nobody
    catches.
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedConstructError(
            f"{rel} is not text — every reader here reads characters"
        ) from exc
    except OSError as exc:
        raise UnsupportedConstructError(f"{rel} could not be read — {exc}") from exc


def manifest_reader() -> Reader:
    """The notation, reading a manifest into the READER it declares.

    This is what makes a session flavour ordinary: the manifest is a
    text, its product is a reader, and a reader is what any grammar can
    be dropped onto. Nothing registers it globally, so the shipped
    singleton of the same name is untouched.
    """
    return Reader(
        "manifest",
        "notation",
        lambda text, _params: load_flavour(text),
        grammar=NOTATION_GRAMMAR,
    )


def _module_surface() -> Reader:
    """Lexic's module grammar, as the reader of exported twins."""
    return surfaces()[1]


def _notation_surface() -> Reader:
    """The IR notation, as the reader of manifests and constructions."""
    return surfaces()[0]


def _reads(attempt) -> bool:
    """Whether a reading succeeds, without caring what it produced."""
    try:
        attempt()
    except LexicError, RecursionError, ValueError:
        return False
    return True
