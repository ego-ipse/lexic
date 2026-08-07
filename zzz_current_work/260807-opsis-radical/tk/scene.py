"""The value half — the instrument as one immutable record tree, plus IR surgery.

The whole demonstrator is a single ``Session`` value on the lexic spine. A frame
renders it; a modification reconstructs it. There is no other state worth the name.
"""

from collections.abc import Iterator

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrInt,
    IrNamedTuple,
    IrNone,
    IrQuantifier,
    IrSelf,
    IrSeq,
    IrStr,
)

Path = tuple[int, ...]


class Style(IrNamedTuple):
    """The instrument's look — colours and metrics, editable like any subject."""

    field: IrStr
    ink: IrStr
    dim: IrStr
    cool: IrStr
    warm: IrStr
    violet: IrStr
    red: IrStr
    green: IrStr
    pad: IrInt
    text: IrInt


class Exhibit(IrNamedTuple):
    """One drawn claim — a title, the claim, and the live subject it is made about."""

    title: IrStr
    claim: IrStr
    subject: IrSelf


class Exhibits(IrSeq[Exhibit]):
    """The ordered exhibit run."""


class Session(IrNamedTuple):
    """Everything the instrument is, as one value — every frame renders this."""

    style: Style
    exhibits: Exhibits
    generation: IrInt


def initial_session() -> Session:
    """The demonstrator's whole starting state, constructed and returned."""
    style = Style(
        IrStr("#0b0e14"),
        IrStr("#e8e2d6"),
        IrStr("#66707f"),
        IrStr("#6fc3c9"),
        IrStr("#e2a65c"),
        IrStr("#d98cf5"),
        IrStr("#e06060"),
        IrStr("#79c99a"),
        IrInt(14),
        IrInt(13),
    )
    exhibits = Exhibits(
        Exhibit(
            IrStr("IrStr"),
            IrStr("the node IS the string — no wrapper, no .value; retyping it rebuilds it"),
            IrStr("value ::= object | array | string"),
        ),
        Exhibit(
            IrStr("IrNone"),
            IrStr("absence is a singleton value — a drawn socket, never a blank, never Python None"),
            IrNone,
        ),
        Exhibit(
            IrStr("IrNamedTuple"),
            IrStr("a record IS its field tuple — read by name or by index; a live IrQuantifier"),
            IrQuantifier(1, IrNone),
        ),
        Exhibit(
            IrStr("an unregistered node"),
            IrStr("the draw table is open with a raising default — no entry refuses, in words"),
            IrAlternation(),
        ),
    )
    return Session(style, exhibits, IrInt(0))


def node_at(root: IrSelf, path: Path) -> IrSelf | int | str:
    """The element at ``path`` — index steps into nested tuples."""
    node: IrSelf | int | str = root
    for step in path:
        if not isinstance(node, tuple):
            raise UnsupportedConstructError(f"path {path} steps into a leaf at {step}")
        node = node[step]
    return node


def set_at(root: IrSelf | int | str, path: Path, value: IrSelf | int | str) -> IrSelf | int | str:
    """A copy of ``root`` with ``value`` at ``path`` — modification is reconstruction."""
    if not path:
        return value
    if not isinstance(root, tuple):
        raise UnsupportedConstructError(f"path {path} steps into a leaf")
    elements: list[IrSelf | int | str] = list(root)
    elements[path[0]] = set_at(elements[path[0]], path[1:], value)
    return type(root)(*elements)


def spell_path(root: IrSelf, path: Path) -> str:
    """The path spelled for a person — field names where the tuple has them."""
    parts = ["session"]
    node: IrSelf | int | str = root
    for step in path:
        fields = getattr(type(node), "_fields", ())
        parts.append(fields[step] if step < len(fields) else f"[{step}]")
        node = node[step] if isinstance(node, tuple) else node
    return " · ".join(parts)


def walk(node: IrSelf) -> Iterator[IrSelf]:
    """Every node reachable through ``children()``, root first."""
    yield node
    for child in node.children():
        yield from walk(child)
