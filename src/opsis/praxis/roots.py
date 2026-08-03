"""Ingress — files become roots; the read side of the session.

The write side is scoped and inferred (exports land under
``generated/``, the target read off the gesture); ingress is its
mirror: reads are WORKSPACE-scoped, and what a chosen file becomes is
inferred from what is READ, never from a kind parameter — grammar text
by its extension's flavour, a flavour manifest by loading it, a session
file by thawing it, a notation grammar by reading it. A file none of
those readings accept is a drawn refusal, not a blank.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from lexic.compile import load_ir
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.grammars import flavour_for_extension
from opsis.opsis.scene import OPSIS_SYMBOLS, Space
from opsis.praxis.state import (
    Ladder,
    _notation_ast,
    root_flavour,
    root_manifest,
    root_notation,
)

__all__ = ["Opened", "Workspace", "open_path", "thaw"]

SHELVES = ("resources/ground_truth", "generated")
"""The default shelves a listing sweeps, workspace-relative."""

_SESSION_SUFFIXES = (".ir", ".scene")


class Workspace:
    """The session's file scope — praxis carries the root explicitly."""

    __slots__ = ("root",)

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, rel: str) -> Path:
        """A workspace path, or the scope refusal.

        :raises UnsupportedConstructError: When ``rel`` escapes the
            workspace root — broader reads are a policy change, not an
            interpretation of this one.
        """
        path = (self.root / rel).resolve()
        if not path.is_relative_to(self.root):
            raise UnsupportedConstructError(
                f"ingress: {rel!r} resolves outside the workspace root"
            )
        return path

    def listing(self) -> list[str]:
        """The shelf files, workspace-relative, sorted — the picker's rows.

        Bytecode and dunder infrastructure are not artefacts and never
        list; everything else on a shelf does.
        """
        out: list[str] = []
        for shelf in SHELVES:
            base = self.root / shelf
            if base.is_dir():
                out.extend(
                    str(p.relative_to(self.root).as_posix())
                    for p in base.rglob("*")
                    if p.is_file() and _listable(p)
                )
        out.extend(
            p.name
            for p in self.root.iterdir()
            if p.is_file() and p.suffix in _SESSION_SUFFIXES
        )
        return sorted(out)


def _listable(path: Path) -> bool:
    """Whether a shelf file is an artefact rather than infrastructure."""
    if "__pycache__" in path.parts or path.suffix == ".pyc":
        return False
    return not (path.name.startswith("__") and path.name.endswith("__.py"))


class Opened(NamedTuple):
    """What one ingress read produced — a root's ladder, a scene, or a refusal.

    :ivar kind: ``grammar`` / ``manifest`` / ``notation`` / ``scene`` /
        ``refused``.
    :ivar ladder: The new root's ladder, for the three root kinds.
    :ivar scene: The thawed scene, for a session file.
    :ivar note: What was read (a label), or the refusal's real message.
    """

    kind: str
    ladder: Ladder | None
    scene: Space | None
    note: str


def thaw(text: str) -> Space:
    """Freeze's read half — a saved ``repr(scene)`` back to the scene.

    :raises UnsupportedConstructError: When the text is not a scene.
    """
    return Space.ensure(load_ir(text, symbols=OPSIS_SYMBOLS), "thaw: a session file")


def open_path(workspace: Workspace, rel: str) -> Opened:
    """One file becomes a root — the kind inferred from what is read.

    Tried in order: the extension's flavour (grammar text → a flavour
    root with the file as rung 0), a flavour manifest (→ a manifest
    root), a scene (→ thaw), a notation grammar (→ a notation root with
    the file as rung 0). What nothing accepts is ``refused`` with the
    last reading's real message.
    """
    text = workspace.resolve(rel).read_text(encoding="utf-8")
    try:
        flavour = flavour_for_extension(rel)
    except UnsupportedConstructError:
        flavour = None
    if flavour is not None:
        ladder = Ladder(root_flavour(str(type(flavour).name)))
        ladder.edit(0, text)
        return Opened("grammar", ladder, None, f"{rel} · {type(flavour).name} grammar")
    try:
        root = root_manifest(text)
    except LexicError:
        root = None
    if root is not None:
        return Opened("manifest", Ladder(root), None, f"{rel} · flavour manifest")
    try:
        return Opened("scene", None, thaw(text), f"{rel} · session file")
    except LexicError:
        pass
    try:
        _notation_ast(text)
    except LexicError as exc:
        return Opened("refused", None, None, f"{type(exc).__name__}: {exc}")
    ladder = Ladder(root_notation())
    ladder.edit(0, text)
    return Opened("notation", ladder, None, f"{rel} · notation grammar")
