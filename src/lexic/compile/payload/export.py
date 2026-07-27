"""``export_value`` — a projected value as an importable module.

The artefact is the payload's four literals, the symbols it names, and an import
of the **reader emitted beside it**. Emitted rather than imported from ``lexic.``
because importing anything under that root costs the package root and a ``plain``
payload must pay for nothing — but emitted *once per directory*, not copied into
every artefact, which is 330 lines of identical machinery per file and one place
to forget when the reader changes.

The sidecar's name carries the digest of its own source, so ``payload_reader_x``
IS a particular reader: an artefact cannot bind to a newer one, and two lexic
versions writing into one directory leave two sidecars rather than one that
silently changed under the older artefact. Version skew is impossible by
construction, which is why nothing checks for it.

There is **no target flag**. Which of the three targets you get is decided by the
codomain of the reduction that produced the value — by the product the caller
already chose — and the exporter reads it off the symbols. ``module`` is required
exactly when the value names a symbol whose own module does not import.
"""

from __future__ import annotations

import ast as _pyast
import sys
from hashlib import blake2b
from importlib import import_module
from keyword import iskeyword
from pathlib import Path

from lexic import ir
from lexic.compile.payload import reader
from lexic.compile.payload.encode import Payload, project_checked
from lexic.compile.writer import literal, write_module
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
    """The reader's source as the sidecar spells it — verbatim but for a banner.

    :returns: The sidecar's source.
    :raises UnsupportedConstructError: When the reader owns an aliased name.
    """
    source = Path(reader.__file__).read_text(encoding="utf-8")
    tree = _pyast.parse(source)
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
    banner = (
        "# Emitted beside the artefacts that import it, from\n"
        "# lexic.compile.payload.reader, so an artefact reads with no lexic\n"
        "# installed. The digest in this module's NAME is of this source: a\n"
        "# newer reader is a different module, never a changed one.\n"
    )
    return banner + source


def _sidecar(directory: Path) -> str:
    """Emit the reader beside the artefacts, named for the digest of its source.

    :param directory: Where the artefact is being written.
    :returns: The module name the artefact should import the reader from.
    """
    source = _reader_source()
    tag = blake2b(source.encode("utf-8"), digest_size=6).hexdigest()
    path = directory / f"payload_reader_{tag}.py"
    # Written every time, never "only if absent". The name is DERIVED from the
    # source, so a file already sitting there under that name is either this
    # exact reader or something else wearing its name — and skipping the write
    # let a pre-placed `decode` read every artefact in the directory, silently.
    # Rewriting also refreshes a `.pyc` that a hand-edit or a crash left stale.
    write_module(path, source)
    return path.stem


def _provides(origin: str, name: str, owner: object) -> bool:
    """Does ``origin`` name a live module exporting exactly ``owner`` as ``name``?

    Identity, not presence. ``lexic.ir.base`` merely IMPORTS ``Sequence``, so a
    symbol called ``Sequence`` would find something there and the artefact would
    import a class the value was never built from.

    :param origin: The module recorded for the symbol.
    :param name: The symbol's name.
    :param owner: The class the encoder actually saw.
    :returns: Whether the artefact may import ``name`` from ``origin``.
    """
    found = sys.modules.get(origin)
    return found is not None and getattr(found, name, None) is owner


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
            # Ahead of the origin: `module=` is the caller SAYING where the
            # reader will find their symbols, and an inferred home that quietly
            # overrode it would export something they did not ask for.
            homes[name] = module
        elif _provides(origin, name, payload.owners.get(name)):
            # The origin is a real module that really exports this class, so it
            # needs no `module=`: only a SYNTHESIZED class is homeless, and the
            # question is whether the recorded module can supply it, not whether
            # lexic happens to re-export it from the spine's public surface.
            homes[name] = origin
        else:
            homeless.append(f"{name} (from {origin})")
    if homeless:
        raise UnsupportedConstructError(
            f"payload: {sorted(homeless)} name no importable module — a "
            "synthesized class reports a `generated.…` module that does not "
            "import, so pass `module=` naming where the reader will find them"
        )
    return homes


def _verify_module(module: str | None, homes: dict[str, str], payload: Payload) -> None:
    """If ``module`` already imports, confirm it really provides these symbols.

    A two-step export is legitimate — the twin and the payload can be written in
    either order — so a module that does not import yet is not an error. One
    that DOES import and does not provide the symbols is: ``module="json"`` for
    a twin written to ``generated/json.py`` resolves to the standard library on
    any path that does not happen to put the twin first, and the artefact then
    fails at import with a message about the wrong module entirely.

    :param module: The caller's module, or ``None``.
    :param homes: Symbol name → the module it will be imported from.
    :param payload: The projected value, for the classes it saw.
    :raises UnsupportedConstructError: When the module resolves and disagrees.
    """
    wanted = sorted(name for name, home in homes.items() if home == module)
    if module is None or not wanted:
        return
    try:
        found = import_module(module)
    except ImportError:
        return  # not written yet — the other half of a two-step export
    missing = [name for name in wanted if not hasattr(found, name)]
    if missing:
        raise UnsupportedConstructError(
            f"payload: module={module!r} imports from "
            f"{getattr(found, '__file__', '?')} and does not provide {missing} — "
            "the artefact would name symbols that module cannot supply"
        )
    # Identity only where identity is the right question — for a class that
    # claims `module` as its own home, anything else under that name is an
    # impostor. A twin's classes never claim it: a value is parsed with runtime
    # classes whose module is content-tagged, so `is` would refuse the ordinary
    # case of exporting a value beside its twin. There the question is the one
    # the reader asks at decode — do these carry the rules the payload was built
    # against — asked here, early, where the message can name the module.
    claimed = [
        name
        for name in wanted
        if getattr(payload.owners.get(name), "__module__", None) == module
        and getattr(found, name) is not payload.owners[name]
    ]
    if claimed:
        raise UnsupportedConstructError(
            f"payload: module={module!r} provides {claimed}, but not the classes "
            "this value was built from — those classes name that module as their "
            "own, so a different object under the name is a different class"
        )
    supplied = {name: getattr(found, name) for name in wanted}
    supplied.update(
        {name: getattr(ir, name) for name, home in homes.items() if home == SPINE}
    )
    if reader.shape_of(payload.types, supplied) != payload.shape():
        raise UnsupportedConstructError(
            f"payload: module={module!r} imports from "
            f"{getattr(found, '__file__', '?')}, whose classes carry different "
            "rules than this value was built from — the artefact would decode "
            "against the wrong grammar"
        )


def _reader_import(reader_module: str) -> list[str]:
    """Import the sidecar both ways round.

    Where an artefact lands is not settled when it is written: a directory can
    become a package, or stop being one, long after the export. Guessing at
    export time — reading the directory for an ``__init__.py`` — produced a file
    that imported in exactly one of the two arrangements and raised in the other.

    :param reader_module: The sidecar's module name, unqualified.
    :returns: The import lines.
    """
    return [
        "try:",
        f"    from .{reader_module} import decode",
        "except ImportError:",
        f"    from {reader_module} import decode",
    ]


def _imports(homes: dict[str, str]) -> list[str]:
    """One parenthesised ``from … import`` per home, aliased so nothing shadows.

    :param homes: Symbol name → the module it is imported from.
    :returns: The import lines, wrapped to the line budget.
    """
    lines: list[str] = []
    for home in sorted(set(homes.values())):
        names = sorted(name for name, where in homes.items() if where == home)
        lines.append(f"from {home} import (")
        lines.extend(f"    {name} as {ALIAS}{name}," for name in names)
        lines.append(")")
    return lines


def _symbol_map(homes: dict[str, str]) -> list[str]:
    """``SYMBOLS`` — the payload's name for a class, mapped to its alias."""
    return (
        ["SYMBOLS = {"]
        + [f'    "{name}": {ALIAS}{name},' for name in sorted(homes)]
        + ["}"]
    )


def render(
    payload: Payload,
    reader_module: str,
    *,
    module: str | None = None,
    reduction: object = None,
) -> str:
    """The artefact's source: imports, tables, and the value.

    :param payload: The projected value.
    :param reader_module: The emitted reader to import ``decode`` from.
    :param module: Where a non-spine symbol is imported from.
    :param reduction: The reduction the value was produced by, recorded so a
        holder of a live one can ask whether the artefact is still current.
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
    _verify_module(module, homes, payload)
    doc = (
        '"""A compiled value — the payload, the symbols it names, and the value.\n\n'
        "Regenerate rather than edit: the tables carry a digest, checked on the\n"
        "way in, so an edit here is refused rather than read as a wrong value.\n"
        '"""'
    )
    tables = "\n".join(
        literal(f"{name} = ", table)
        for name, table in (
            ("TYPES", payload.types),
            ("ORIGINS", payload.origins),
            ("STRS", payload.strs),
            ("NODES", payload.nodes),
        )
    )
    return (
        "\n\n\n".join(
            [
                doc,
                "\n".join(_reader_import(reader_module) + _imports(homes)),
                "\n".join(_symbol_map(homes)) if homes else "SYMBOLS = {}",
                f"{tables}\n"
                f"DIGEST = {payload.digest()!r}\n"
                f"SHAPE = {payload.shape()!r}\n"
                f"REDUCTION = {reader.reduction_digest(reduction)!r}\n\n"
                "TABLES = (TYPES, ORIGINS, STRS, NODES)\n"
                "VALUE = decode(TABLES, SYMBOLS, (DIGEST, SHAPE))",
            ]
        )
        + "\n"
    )


def export_value(
    value: object,
    path: str | Path,
    *,
    module: str | None = None,
    reduction: object = None,
) -> Path:
    """Write ``value`` as an importable module, and byte-compile it.

    The value is projected under the always-on fixpoint gate first, so an
    artefact that cannot be read back is never written.

    Whoever writes the ``.py`` writes the ``.pyc``: ``UNCHECKED_HASH`` makes a
    stale ``.pyc`` outrank a fresh source, silently, so leaving it to the first
    importer is how a reader gets yesterday's value.

    :param value: Anything lexic parsed — a model, reduced IR, or plain data.
    :param path: Where to write.
    :param module: Where a non-spine symbol is imported from.
    :param reduction: The reduction that produced ``value``. Recorded, not
        checked at import: an ``ir`` or ``plain`` artefact names spine classes
        or nothing, so nothing at read time could disagree with it. Ask with
        :func:`built_under`, which is the only party that can.
    :returns: The written path.
    :raises UnsupportedConstructError: On a value outside the vocabulary, a
        symbol with no importable home, or a failed gate.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = project_checked(value)
    source = render(
        payload, _sidecar(target.parent), module=module, reduction=reduction
    )
    return write_module(target, source)


def built_under(artefact: object, reduction: object) -> bool:
    """Was ``artefact`` produced by ``reduction``?

    The producer-side half of provenance. The grammar half is checked at decode,
    because a class carries its rules; a reduction cannot be, because the
    symbols an ``ir`` or ``plain`` artefact names are the same under every
    reduction there is. So the question is asked here, by whoever holds a live
    reduction — which is exactly the party deciding whether a cached artefact
    needs rebuilding.

    :param artefact: An imported payload module.
    :param reduction: The reduction to compare against.
    :returns: Whether the artefact records this reduction. ``False`` when the
        artefact recorded none — an unknown provenance is not a match.
    """
    recorded = getattr(artefact, "REDUCTION", 0)
    return bool(recorded) and recorded == reader.reduction_digest(reduction)
