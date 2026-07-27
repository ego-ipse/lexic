"""The shared module writer — every ``.py`` lexic emits goes out through here.

Lexic writes two kinds of importable module: a grammar's **twin** (one class per
rule, its ``GRAMMAR`` in notation) and a value's **payload** (three flat tables
and the reader that reads them). They are the same job at the last step — render
a value into bounded lines, check it is Python, put it on disk, byte-compile it —
and having that step twice is how the two ended up with five gratuitous
differences between them, only one of which anybody chose.

Two rules live here rather than in either caller:

**Whoever writes the ``.py`` writes the ``.pyc``.** ``UNCHECKED_HASH`` makes a
byte-compiled module outrank its source unconditionally, so leaving the ``.pyc``
to the first importer is how a reader gets yesterday's value.

**Nothing lands until it compiles.** A previous module and its ``.pyc`` are a
matched pair; a failed rewrite that left a broken source behind would be imported
as the OLD value, with no error anywhere.
"""

from __future__ import annotations

import ast as _pyast
import importlib.util
import os
import py_compile
from math import isfinite
from pathlib import Path
from tempfile import mkstemp

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.layout import IrCat, IrDoc, IrGroup, IrLine, IrNest, IrText, render

WIDTH = 88
"""The line budget every emitted module is rendered against."""

_INDENT = 4


def _item(value: object, width: int) -> IrDoc:
    """One element of a literal tuple, chunked if it is a long string.

    Wrapping *between* elements is not enough: one document's whole text is a
    single ``STRS`` entry, so an artefact for a 10 KB grammar had a 10 KB line
    however carefully the tuple around it was laid out. Adjacent string literals
    concatenate in Python, which is how a long string wraps at all.

    :param value: The element.
    :param width: The line budget the chunks are cut to.
    :returns: A document for the element.
    """
    if isinstance(value, float) and not isfinite(value):
        raise UnsupportedConstructError(
            f"export: {value!r} has no literal spelling — `nan` and `inf` repr "
            "as bare NAMES, which parse as valid Python and raise at import"
        )
    text = repr(value)
    # Against the same budget the chunks are cut to, not against `width`: an
    # unchunked element still lands one nest in and still carries a comma, so
    # measuring it against the raw width leaves the line up to five over.
    budget = width - 2 * _INDENT - 4
    if len(text) <= budget:
        return IrText(text)
    if not isinstance(value, str):
        # An integer literal cannot be split — adjacent-literal concatenation is
        # a string thing — and NODES holds arbitrary-width ints, so a big one is
        # a 276-character line. `int(...)` of a chunked string is the spelling
        # that fits, and it costs the artefact nothing at import.
        return IrGroup(IrCat(IrText("int("), _chunked(text, budget), IrText(")")))
    return _chunked(value, budget)


def _chunked(value: str, budget: int) -> IrDoc:
    """A string as adjacent literals, each cut to fit ``budget``."""
    chunks: list[IrDoc] = []
    start = 0
    while start < len(value):
        # By repr width, not by character count: a chunk of characters that all
        # escape to `\uXXXX` is six times its own length once written down.
        step = max(1, budget - 2)
        while step > 1 and len(repr(value[start : start + step])) > budget:
            step -= max(1, step // 4)
        piece = IrText(repr(value[start : start + step]))
        chunks.extend((IrLine(" "), piece) if chunks else (piece,))
        start += step
    return IrGroup(IrNest(_INDENT, IrCat(*chunks)))


def literal(prefix: str, value: object, *, width: int = WIDTH) -> str:
    """``prefix`` plus a Python literal, wrapped to the line budget.

    A big tuple written with ``repr`` is one unbounded line — 370 characters for
    a small grammar, and megabytes for a vocabulary. The layout algebra is what
    the rest of lexic uses to avoid that, so the payload's tables use it too.

    :param prefix: The assignment's left-hand side, e.g. ``"NODES = "``.
    :param value: A tuple, or any value whose ``repr`` is a literal.
    :param width: The line budget.
    :returns: The rendered assignment, no trailing newline.
    """
    if not isinstance(value, tuple) or not value:
        return f"{prefix}{value!r}"
    parts: list[IrDoc] = [_item(value[0], width)]
    for item in value[1:]:
        parts.extend((IrText(","), IrLine(" "), _item(item, width)))
    tail = IrCat(IrText(","), IrLine("")) if len(value) == 1 else IrLine("", ",")
    doc = IrGroup(
        IrCat(
            IrText(f"{prefix}("),
            IrNest(_INDENT, IrCat(IrLine(), *parts)),
            tail,
            IrText(")"),
        )
    )
    return render(doc, width)


def write_module(path: str | Path, source: str) -> Path:
    """Validate ``source``, put it on disk, and byte-compile it.

    The ``.pyc`` is written under ``UNCHECKED_HASH``, so it outranks its source
    unconditionally: any moment when the two disagree is a moment when the module
    reads as the wrong value, and a crash must not be able to leave one. So the
    stale cache is removed FIRST and the fresh one lands LAST, which makes every
    window consistent — old source with no cache reads the old value, new source
    with no cache reads the new one, and neither reads a mixture.

    :param path: The output ``.py`` path; parent directories are created.
    :param source: The module source.
    :returns: The written path.
    :raises UnsupportedConstructError: When the source is not valid Python or
        will not compile — in which case nothing on disk is touched.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _pyast.parse(source)
    except SyntaxError as exc:
        raise UnsupportedConstructError(
            f"export: the rendered module is not valid Python: {exc}"
        ) from exc
    # A unique staged name, not `<target>.staged`: two processes exporting into
    # one directory otherwise share it, and each one's cleanup deletes the
    # other's file mid-write.
    handle, staged_name = mkstemp(
        dir=target.parent, prefix=target.name, suffix=".staged"
    )
    os.close(handle)
    staged = Path(staged_name)
    cache = Path(importlib.util.cache_from_source(str(target)))
    try:
        staged.write_text(source, encoding="utf-8")
        py_compile.compile(
            str(staged),
            cfile=str(staged) + "c",
            dfile=str(target),
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.unlink(missing_ok=True)
        os.replace(staged, target)
        os.replace(str(staged) + "c", cache)
    except py_compile.PyCompileError as exc:
        raise UnsupportedConstructError(
            f"export: the rendered module does not compile: {exc}"
        ) from exc
    finally:
        staged.unlink(missing_ok=True)
        Path(str(staged) + "c").unlink(missing_ok=True)
    return target
