"""``export_value`` — a projected value as an importable, self-contained module.

The artefact is the payload's four literals, the symbols it names, and **the
reader's own source inlined**. Inlined rather than imported because importing
anything under ``lexic.`` costs the package root, and a ``plain`` payload must
pay for nothing; it also makes the artefact self-contained, so a payload cannot
skew against a newer reader.

There is **no target flag**. Which of the three targets you get is decided by the
codomain of the reduction that produced the value — by the product the caller
already chose — and the exporter reads it off the symbols. ``module`` is required
exactly when the value names a symbol whose own module does not import.
"""

from __future__ import annotations

import ast as _pyast
import importlib.util
import os
import py_compile
from keyword import iskeyword
from pathlib import Path

from lexic import ir
from lexic.compile.payload import reader
from lexic.compile.payload.encode import Payload, project_checked
from lexic.exceptions import UnsupportedConstructError

ALIAS = "_sym_"
"""Every imported symbol is bound under this prefix, and ``SYMBOLS`` maps the
payload's name to the alias.

Collision-proof **by construction** rather than by a reserved-name list: the
reader's source shares the artefact's namespace, so a grammar with a rule called
``decode`` or ``digest`` would otherwise shadow the machinery that reads it.
:func:`_reader_source` asserts the reader owns no name with this prefix, which is
the one thing that could reopen it."""

SPINE = "lexic.ir"
"""Where a spine symbol is imported from — the public surface, complete since
``IrTuple`` joined it."""


def _reader_source() -> str:
    """The reader's source, ready to inline: no docstring, no ``__future__``.

    Both have to go — a ``__future__`` import is only legal at the top of a file
    and the artefact supplies its own, and the reader's module docstring would
    read as a stray string in the middle of one. What replaces them is a line
    saying where the code came from, because a reader of the artefact should not
    have to guess.
    """
    source = Path(reader.__file__).read_text(encoding="utf-8")
    tree = _pyast.parse(source)
    drop: set[int] = set()
    for node in tree.body:
        future = isinstance(node, _pyast.ImportFrom) and node.module == "__future__"
        docstring = isinstance(node, _pyast.Expr) and isinstance(
            node.value, _pyast.Constant
        )
        if future or (docstring and node is tree.body[0]):
            drop.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    owned = {
        target.id
        for node in tree.body
        if isinstance(node, (_pyast.Assign, _pyast.AnnAssign))
        for target in (
            node.targets if isinstance(node, _pyast.Assign) else [node.target]
        )
        if isinstance(target, _pyast.Name)
    } | {node.name for node in tree.body if isinstance(node, _pyast.FunctionDef)}
    clash = sorted(name for name in owned if name.startswith(ALIAS))
    if clash:
        raise UnsupportedConstructError(
            f"payload: the reader owns {clash}, which collides with the alias "
            f"prefix {ALIAS!r} every imported symbol is bound under"
        )
    kept = [
        line for number, line in enumerate(source.splitlines(), 1) if number not in drop
    ]
    banner = (
        "# The payload reader, inlined from lexic.compile.payload.reader so this\n"
        "# artefact imports no lexic at all and cannot skew against a newer one."
    )
    return banner + "\n" + "\n".join(kept).strip() + "\n"


def _homes(payload: Payload, module: str | None) -> dict[str, str]:
    """Where each symbol is imported from, refusing one that cannot be.

    :param payload: The projected value.
    :param module: The caller's module for its own symbols.
    :returns: Symbol name → module to import it from.
    :raises UnsupportedConstructError: When a symbol has no importable home.
    """
    homes: dict[str, str] = {}
    homeless: list[str] = []
    for name, origin in zip(payload.symbols, payload.origins[1:], strict=True):
        # Routed by ORIGIN, never by name. A caller may call a class `IrLiteral`,
        # and sending it to `lexic.ir` because the NAME matches hands the reader
        # a different class with no error at all — the origin is recorded
        # precisely so this decision does not have to guess.
        if origin.split(".")[0] == "lexic" and name in set(ir.__all__):
            homes[name] = SPINE
        elif module is not None:
            homes[name] = module
        else:
            homeless.append(f"{name} (from {origin})")
    if homeless:
        raise UnsupportedConstructError(
            f"payload: {sorted(homeless)} name no importable module — a "
            "synthesized class reports a `generated.…` module that does not "
            "import, so pass `module=` naming where the reader will find them"
        )
    return homes


def _header(homes: dict[str, str]) -> list[str]:
    """The import block and the symbol map, aliased so nothing can shadow."""
    lines = ["from __future__ import annotations", ""]
    for home in sorted(set(homes.values())):
        names = sorted(name for name, where in homes.items() if where == home)
        joined = ", ".join(f"{name} as {ALIAS}{name}" for name in names)
        lines.append(f"from {home} import {joined}")
    lines.append("")
    lines.append("SYMBOLS = {")
    lines.extend(f'    "{name}": {ALIAS}{name},' for name in sorted(homes))
    lines.append("}")
    return lines


def render(payload: Payload, *, module: str | None = None) -> str:
    """The artefact's source: header, inlined reader, tables, and the value.

    :param payload: The projected value.
    :param module: Where a non-spine symbol is imported from.
    :returns: The module source.
    :raises UnsupportedConstructError: When a symbol has no importable home.
    """
    if module is not None and not all(
        part.isidentifier() and not iskeyword(part) for part in module.split(".")
    ):
        raise UnsupportedConstructError(
            f"payload: module={module!r} is not a dotted Python name, so the "
            "header it would write cannot be imported"
        )
    homes = _homes(payload, module)
    doc = (
        '"""A compiled value — the payload, its symbols, and the reader inlined.\n\n'
        "Regenerate rather than edit: the tables carry a digest, checked on the\n"
        "way in, so an edit here is refused rather than read as a wrong value.\n"
        '"""'
    )
    parts = [doc, "\n".join(_header(homes)) if homes else _HEADER_PLAIN]
    parts.append(_reader_source())
    parts.append(
        f"TYPES = {payload.types!r}\n"
        f"ORIGINS = {payload.origins!r}\n"
        f"STRS = {payload.strs!r}\n"
        f"NODES = {payload.nodes!r}\n"
        f"DIGEST = {payload.digest()!r}\n\n"
        f"VALUE = decode(TYPES, STRS, NODES, {'SYMBOLS' if homes else '{}'}, DIGEST)"
    )
    return "\n\n\n".join(parts) + "\n"


_HEADER_PLAIN = "from __future__ import annotations"
"""A ``plain`` payload names no symbol, so it has no imports to write — which is
the whole reason its reader is inlined."""


def export_value(value: object, path: str | Path, *, module: str | None = None) -> Path:
    """Write ``value`` as an importable module, and byte-compile it.

    The value is projected under the always-on fixpoint gate first, so an
    artefact that cannot be read back is never written.

    Whoever writes the ``.py`` writes the ``.pyc``: ``UNCHECKED_HASH`` makes a
    stale ``.pyc`` outrank a fresh source, silently, so leaving it to the first
    importer is how a reader gets yesterday's value.

    :param value: Anything lexic parsed — a model, reduced IR, or plain data.
    :param path: Where to write.
    :param module: Where a non-spine symbol is imported from.
    :returns: The written path.
    :raises UnsupportedConstructError: On a value outside the vocabulary, a
        symbol with no importable home, or a failed gate.
    """
    target = Path(path)
    source = render(project_checked(value), module=module)
    try:
        _pyast.parse(source)
    except SyntaxError as exc:
        raise UnsupportedConstructError(
            f"payload: the rendered artefact is not valid Python: {exc}"
        ) from exc
    # Written through a temporary and moved into place. A previous artefact and
    # its `.pyc` are a matched pair, and `UNCHECKED_HASH` means the `.pyc` wins:
    # a failed re-export that left a broken source behind would be imported as
    # the OLD value, with no error anywhere.
    staged = target.with_name(target.name + ".staged")
    staged.write_text(source, encoding="utf-8")
    try:
        py_compile.compile(
            str(staged),
            cfile=str(staged) + "c",
            dfile=str(target),
            doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
        )
        cache = Path(importlib.util.cache_from_source(str(target)))
        cache.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(staged) + "c", cache)
        os.replace(staged, target)
    finally:
        staged.unlink(missing_ok=True)
        Path(str(staged) + "c").unlink(missing_ok=True)
    return target
