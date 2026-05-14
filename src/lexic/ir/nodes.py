"""IR AST node dataclasses — canonical, frozen, hashable.

Every IR node implements the structural protocol from IrNode:
  - children() -> tuple[IrNode, ...]   children in traversal order
  - rebuild(new_children) -> IrNode    reconstruct under transformation
  - emit(indent=0) -> str              default string rendering (debug)

Flavour-specific rendering bypasses `emit()` via the per-flavour action
dispatch table on `Flavour` (an IrEmitter subclass).
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import TypeAlias


class IrNode(ABC):
    """Structural protocol every IR node implements."""

    def children(self) -> tuple[IrNode, ...]:
        """Children in traversal order. Default: leaf — no children.

        :returns: A tuple of the node's children.
        """
        return ()

    def rebuild(self, new_children: tuple[IrNode, ...]) -> IrNode:  # pylint: disable=unused-argument
        """Reconstruct with new children. Default: identity (leaves).

        Leaves inherit identity rebuild.
        Structural nodes must override to reconstruct with new children.
        Unused argument is accepted to satisfy the protocol.

        :param new_children: Tuple of new child nodes to rebuild with.
        :returns: A new IrNode instance with the new children, or self if unchanged.
        """
        return self

    def emit(self, indent: int = 0) -> str:  # pylint: disable=unused-argument
        """Default string rendering used by IrMetaEmitter.

        Leaves return repr(self).
        Branches override to render themselves at indent indent + 1
        Flavour emitters bypass this via their action dispatch table.

        :param indent: Indentation depth (number of two-space levels). Ignored by leaves.
        :returns: String representation of the node.
        """
        return repr(self)


# ── Leaves ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrLiteral(IrNode):
    """Literal string. `value` is canonical Python (escapes decoded)."""

    value: str


@dataclass(frozen=True, slots=True)
class IrCharClass(IrNode):
    """Character class. `pattern` is canonical POSIX-style interior."""

    pattern: str
    negated: bool = False


@dataclass(frozen=True, slots=True)
class IrRuleRef(IrNode):
    """Reference to another rule by name."""

    name: str


# ── Quantifier (also a leaf IrNode) ──────────────────────────────────


@dataclass(frozen=True, slots=True)
class Quantifier(IrNode):
    """Repetition bounds. `max=None` means unbounded.

    Will be renamed to IrQuantifier in Task 2.1; staying as Quantifier
    in Task 1.x to keep step 1 a pure protocol-introduction change.
    """

    min: int = 1
    max: int | None = 1


# ── Structure ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IrSequence(IrNode):
    """Concatenation of items."""

    items: tuple[IrItem, ...] = ()


@dataclass(frozen=True, slots=True)
class IrAlternation(IrNode):
    """Choice between sequences. Always >= 1 arm."""

    arms: tuple[IrSequence, ...] = ()


@dataclass(frozen=True, slots=True)
class IrGroup(IrNode):
    """Parenthesised group. Body is always an IrAlternation."""

    body: IrAlternation


@dataclass(frozen=True, slots=True)
class IrItem(IrNode):
    """An atom (leaf or group) with a quantifier."""

    atom: IrAtom
    quantifier: Quantifier = field(default_factory=Quantifier)


@dataclass(frozen=True, slots=True)
class IrRule(IrNode):
    """A named rule. Body is always an IrAlternation, even single-arm."""

    name: str
    body: IrAlternation


@dataclass(frozen=True, slots=True)
class IrAst(IrNode):
    """Full grammar: rules + start-rule name."""

    rules: tuple[IrRule, ...] = ()
    start: str = ""


# ── Type aliases (structural unions) ─────────────────────────────────

IrLeaf: TypeAlias = IrLiteral | IrCharClass | IrRuleRef
IrAtom: TypeAlias = IrLeaf | IrGroup
