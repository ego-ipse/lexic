"""Flavour manifests — one notation expression → a live :class:`IrFlavour`.

A manifest is a single IR-constructor notation expression (``compile/notation``)
whose root is an :class:`~lexic.ir.action.mapping.IrMap` of seven named sections::

    IrMap(
        IrTuple(IrStr('name'),        IrStr('gbnf')),
        IrTuple(IrStr('extensions'),  IrTuple(IrStr('.gbnf'))),
        IrTuple(IrStr('line-comment'),IrStr('#')),
        IrTuple(IrStr('escapes'),     IrMap( ... five IR-dyad tables ... )),
        IrTuple(IrStr('grammar'),     IrAst( ... the self-grammar ... )),
        IrTuple(IrStr('reduction'),   Reducer( ... the whole reduction ... )),
        IrTuple(IrStr('actions'),     IrTypeMap( ... the emit half ... )),
    )

:func:`load_flavour` folds that into an :class:`IrFlavour`: it lowers the escape
IR dyads to an :class:`~lexic.ir.text.codec.escapes.EscapeCodec` and synthesizes the flavour
class by a bare :func:`type` call.

The reduction is **carried, not derived**. A :class:`~lexic.ir.Reducer` is a
plain IR record — actions, default, noise, literal — so the manifest spells the
whole thing and the loader reads it. Deriving the noise map from the grammar's
own ``semantic=False`` flags made one reading of a grammar the only reading it
could have; a reduction is a reading, and one grammar must support several.

The root shape is strict: exactly the seven section
names, each of the declared type — any deviation is an
:class:`~lexic.exceptions.UnsupportedConstructError` (never ``TypeError`` /
``KeyError``). Registration stays the caller's business.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from lexic.compile.notation.parse import load_ir
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import EscapeCodec, IrAst, IrFlavour, IrMap, IrTuple, IrTypeMap, Reducer

__all__ = ["load_flavour", "load_flavour_from_path"]

_SECTIONS: tuple[str, ...] = (
    "name",
    "extensions",
    "line-comment",
    "escapes",
    "grammar",
    "reduction",
    "actions",
)
"""The exact, required section names of a manifest root — strict both ways."""

_ESCAPE_TABLES: tuple[str, ...] = (
    "short",
    "hex",
    "class-short",
    "class-meta",
    "quote-safe",
)
"""The five escape sub-tables the ``escapes`` section spells (all required)."""


# ── entry ────────────────────────────────────────────────────────────────


def load_flavour(text: str) -> IrFlavour:
    """Parse a manifest expression and fold it into an :class:`IrFlavour`.

    :param text: A manifest — one IR-constructor notation expression whose root
        is the section :class:`~lexic.ir.action.mapping.IrMap`.
    :returns: The synthesized flavour (unregistered).
    :raises UnsupportedConstructError: On any parse error, unknown symbol, or a
        root/section/escape shape violation.
    """
    sections = _load_sections(text)
    grammar = _section(sections, "grammar", IrAst)
    reducer = _section(sections, "reduction", Reducer)
    actions = _section(sections, "actions", IrTypeMap)
    escapes = _lower_escapes(_section(sections, "escapes", IrMap))
    return _synthesize_flavour(sections, grammar, actions, escapes, reducer)


def load_flavour_from_path(path: str | Path) -> IrFlavour:
    """Load a manifest from a UTF-8 file.

    :param path: Path to a ``.flavour.ir`` manifest.
    :returns: The synthesized flavour (unregistered).
    """
    return load_flavour(Path(path).read_text(encoding="utf-8"))


# ── root shape ───────────────────────────────────────────────────────────


def _load_sections(text: str) -> IrMap:
    """Parse ``text`` and validate the strict seven-section root shape.

    :param text: The manifest source.
    :returns: The section map, keyed by the seven names.
    :raises UnsupportedConstructError: If the root is not an ``IrMap`` or its
        keys are not exactly the seven section names.
    """
    root = load_ir(text)
    if not isinstance(root, IrMap):
        raise UnsupportedConstructError(
            f"manifest: root must be an IrMap of sections, got {type(root).__name__}"
        )
    keys = {str(key) for key in root.keys()}
    unknown = sorted(keys - set(_SECTIONS))
    if unknown:
        raise UnsupportedConstructError(_unknown_section_message(unknown[0]))
    missing = sorted(set(_SECTIONS) - keys)
    if missing:
        raise UnsupportedConstructError(
            f"manifest: missing required section(s) {missing}; "
            f"every manifest carries exactly {list(_SECTIONS)}"
        )
    return root


def _unknown_section_message(name: str) -> str:
    """The rejection message for an unknown root section (settled 8 for ``noise``).

    :param name: The offending section name.
    :returns: The error text.
    """
    if name == "noise":
        return (
            "manifest: no 'noise' section — reducer policy is derived from the "
            "self-grammar's semantic flags; manifests carry no noise section"
        )
    return (
        f"manifest: unknown section {name!r}; the seven sections are {list(_SECTIONS)}"
    )


def _section[T](sections: IrMap, name: str, expected: type[T]) -> T:
    """Read a present section and narrow it to its declared type.

    :param sections: The validated section map (every name present).
    :param name: The section name.
    :param expected: The type the section value must be.
    :returns: The section value, typed.
    :raises UnsupportedConstructError: If the value is not ``expected``.
    """
    value = sections[name]
    if not isinstance(value, expected):
        raise UnsupportedConstructError(
            f"manifest: section {name!r} must be an {expected.__name__}, "
            f"got {type(value).__name__}"
        )
    return value


# ── reducer policy (settled 8) ───────────────────────────────────────────


# ── escapes (ruling D1) ──────────────────────────────────────────────────


def _lower_escapes(tables: IrMap) -> EscapeCodec:
    """Lower the five escape IR-dyad tables to an ``EscapeCodec`` record.

    :param tables: The ``escapes`` section — an ``IrMap`` of the five tables.
    :returns: The ``EscapeCodec`` record carrying the five tables.
    :raises UnsupportedConstructError: On a missing/unknown table or a malformed
        dyad shape.
    """
    _validate_escape_keys(tables)
    class_meta = "".join(
        str(char) for char in _require(tables["class-meta"], IrTuple, "class-meta")
    )
    return EscapeCodec.from_tables(
        short=_short_map(tables["short"]),
        hexes=_hex_tuple(tables["hex"]),
        class_short=_class_short_map(tables["class-short"]),
        class_meta=class_meta,
        quote_safe=_range_tuple(tables["quote-safe"], "quote-safe"),
    )


def _validate_escape_keys(tables: IrMap) -> None:
    """Enforce the strict five-table escape shape.

    :param tables: The ``escapes`` section map.
    :raises UnsupportedConstructError: On a missing or unknown table key.
    """
    keys = {str(key) for key in tables.keys()}
    unknown = sorted(keys - set(_ESCAPE_TABLES))
    if unknown:
        raise UnsupportedConstructError(
            f"manifest: escapes has unknown table(s) {unknown}; "
            f"the five are {list(_ESCAPE_TABLES)}"
        )
    missing = sorted(set(_ESCAPE_TABLES) - keys)
    if missing:
        raise UnsupportedConstructError(
            f"manifest: escapes missing table(s) {missing}; "
            f"the five are {list(_ESCAPE_TABLES)}"
        )


def _short_map(table: object) -> dict[str, str]:
    """``short`` table (``IrMap[IrStr → IrStr]``) → ``SHORT_ESCAPES``."""
    entries = _require(table, IrMap, "escapes.short")
    return {str(key): str(value) for key, value in entries.items()}


def _class_short_map(table: object) -> dict[int, str]:
    """``class-short`` table (``IrMap[IrInt → IrStr]``) → ``CLASS_SHORT``."""
    entries = _require(table, IrMap, "escapes.class-short")
    return {
        _as_int(key, "escapes.class-short key"): str(value)
        for key, value in entries.items()
    }


def _hex_tuple(table: object) -> tuple[tuple[str, int], ...]:
    """``hex`` table (``IrTuple`` of ``(tag, width)``) → ``HEX_ESCAPES`` (ordered)."""
    rows = _require(table, IrTuple, "escapes.hex")
    return tuple(_hex_row(row) for row in rows)


def _hex_row(row: object) -> tuple[str, int]:
    """One ``hex`` entry — a ``(tag, width)`` dyad."""
    tag, width = _dyad(row, "escapes.hex entry")
    return str(tag), _as_int(width, "escapes.hex width")


def _range_tuple(table: object, ctx: str) -> tuple[tuple[int, int], ...]:
    """A ``(lo, hi)`` code-point range tuple — the ``quote-safe`` shape."""
    rows = _require(table, IrTuple, f"escapes.{ctx}")
    return tuple(_range_row(row, ctx) for row in rows)


def _range_row(row: object, ctx: str) -> tuple[int, int]:
    """One ``(lo, hi)`` code-point range dyad."""
    lo, hi = _dyad(row, f"escapes.{ctx} entry")
    return _as_int(lo, f"escapes.{ctx} lo"), _as_int(hi, f"escapes.{ctx} hi")


def _dyad(row: object, ctx: str) -> list[object]:
    """Narrow a two-element ``IrTuple`` dyad to its pair of elements.

    :param row: The candidate dyad.
    :param ctx: A locating prefix for the error message.
    :returns: The two elements, as a list.
    :raises UnsupportedConstructError: If ``row`` is not a 2-element ``IrTuple``.
    """
    items = list(_require(row, IrTuple, ctx))
    if len(items) != 2:
        raise UnsupportedConstructError(
            f"manifest: {ctx} must be a pair, got {len(items)} items"
        )
    return items


# ── flavour synthesis ────────────────────────────────────────────────────


def _synthesize_flavour(
    sections: IrMap,
    grammar: IrAst,
    actions: IrTypeMap,
    escapes: EscapeCodec,
    reducer: Reducer,
) -> IrFlavour:
    """Build the flavour class by a bare ``type()`` call and return its instance.

    ``actions`` rides as a class-level default plus its annotation — the proven
    :class:`IrFlavour` field wiring (never ``init=False``, which suppresses the
    generated ``__init__`` and silently resolves ``actions`` to the empty
    dispatcher default). The remaining metadata are plain class attributes over
    the base's ClassVars.

    :param sections: The validated section map (identity fields read here).
    :param grammar: The self-grammar.
    :param actions: The emit-half type map.
    :param escapes: The lowered escape codec.
    :param reducer: The derived reducer.
    :returns: The synthesized flavour instance.
    """
    name = str(_section(sections, "name", str))
    class_name = f"Loaded{name.capitalize()}Flavour"
    namespace = {
        "__annotations__": {"actions": IrTypeMap},
        "actions": actions,
        "name": name,
        "extensions": tuple(
            str(ext) for ext in _section(sections, "extensions", IrTuple)
        ),
        "escapes": escapes,
        "line_comment": str(_section(sections, "line-comment", str)),
        "grammar": grammar,
        "reducer": reducer,
        "__module__": __name__,
        "__qualname__": class_name,
    }
    flavour_cls = type(class_name, (IrFlavour,), namespace)
    return cast(IrFlavour, flavour_cls())


# ── shared coercions ─────────────────────────────────────────────────────


def _require[T](value: object, expected: type[T], ctx: str) -> T:
    """Narrow ``value`` to ``expected`` or reject with a located message."""
    if not isinstance(value, expected):
        raise UnsupportedConstructError(
            f"manifest: {ctx} must be an {expected.__name__}, "
            f"got {type(value).__name__}"
        )
    return value


def _as_int(value: object, ctx: str) -> int:
    """Narrow an ``IrInt``/``int`` value or reject with a located message."""
    if not isinstance(value, int):
        raise UnsupportedConstructError(
            f"manifest: {ctx} must be an integer, got {type(value).__name__}"
        )
    return int(value)
