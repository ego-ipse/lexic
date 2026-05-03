"""IrVisitor and IrTransformer — Python-ast-style traversal for the IR AST.

`IrVisitor` walks; subclass and define `visit_<NodeType>` methods.
`IrTransformer` rewrites; methods return a (possibly new) node.

Both use module-level dispatch tables so the child-structure of each node type
is defined once. Leaves (IrLiteral, IrCharClass, IrRuleRef) have no children.
Unknown node types raise TypeError.
"""

from __future__ import annotations

from typing import Callable, TypeAlias, TypeVar

from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrGroup,
    IrItem,
    IrNode,
    IrRule,
    IrSequence,
    IrLeaf,
)

_N = TypeVar("_N", bound=IrNode)
_GetChildren: TypeAlias = Callable[[_N], tuple[_N, ...]]

_CHILDREN: dict[type, _GetChildren] = {
    IrAst: lambda n: n.rules,
    IrRule: lambda n: (n.body,),
    IrAlternation: lambda n: n.arms,
    IrSequence: lambda n: n.items,
    IrItem: lambda n: (n.atom,),
    IrGroup: lambda n: (n.body,),
}

_Rebuilder: TypeAlias = Callable[..., _N]
_REBUILD: dict[type, _Rebuilder] = {
    IrAst: lambda n, ch: IrAst(rules=ch, start=n.start),
    IrRule: lambda n, ch: IrRule(name=n.name, body=ch[0]),
    IrAlternation: lambda n, ch: IrAlternation(arms=ch),
    IrSequence: lambda n, ch: IrSequence(items=ch),
    IrItem: lambda n, ch: IrItem(atom=ch[0], quantifier=n.quantifier),
    IrGroup: lambda n, ch: IrGroup(body=ch[0]),
}

_DUMP: dict[type, Callable[..., str]] = {
    IrAst: lambda n, i: (
        f"{'  ' * i}IrAst(start={n.start!r}, rules=[\n"
        + "\n".join(dump(r, indent=i + 1) for r in n.rules)
        + f"\n{'  ' * i}])"
    ),
    IrRule: lambda n, i: (
        f"{'  ' * i}IrRule({n.name!r},\n{dump(n.body, indent=i + 1)}\n{'  ' * i})"
    ),
    IrAlternation: lambda n, i: (
        f"{'  ' * i}IrAlternation([])"
        if not n.arms
        else f"{'  ' * i}IrAlternation([\n"
        + ",\n".join(dump(a, indent=i + 1) for a in n.arms)
        + f"\n{'  ' * i}])"
    ),
    IrSequence: lambda n, i: (
        f"{'  ' * i}IrSequence([])"
        if not n.items
        else f"{'  ' * i}IrSequence([\n"
        + ",\n".join(dump(it, indent=i + 1) for it in n.items)
        + f"\n{'  ' * i}])"
    ),
    IrItem: lambda n, i: (
        f"{'  ' * i}IrItem({dump(n.atom, indent=i + 1)}, q={n.quantifier})"
    ),
    IrGroup: lambda n, i: f"{'  ' * i}IrGroup({dump(n.body, indent=i + 1)})",
}


class IrVisitor[_N]:
    """Walks the IR AST. Subclass + define `visit_<TypeName>` methods."""

    children: dict[type, _GetChildren] = _CHILDREN

    def visit(self, node: _N) -> None:
        """Visit a node."""
        method = getattr(self, f"visit_{type(node).__name__}", self.generic_visit)
        method(node)

    def generic_visit(self, node: _N) -> None:
        """Default visit method: visit all children."""
        getter = self.children.get(type(node))
        if getter is not None:
            for child in getter(node):
                self.visit(child)
        elif not isinstance(node, IrLeaf):
            raise TypeError(f"generic_visit: unknown node type {type(node).__name__!r}")


class IrTransformer[_N]:
    """Rewrites the IR AST. Each visit returns a (possibly new) node."""

    children: dict[type, _GetChildren] = _CHILDREN
    rebuild: dict[type, _Rebuilder] = _REBUILD

    def visit(self, node: _N) -> _N:
        """Visit a node and return a (possibly new) node of the same type."""
        visit_fn: Callable[[_N], _N] | None = getattr(
            self, f"visit_{type(node).__name__}", None
        )
        if visit_fn is not None:
            return visit_fn(node)
        return self.generic_visit(node)

    def generic_visit(self, node: _N) -> _N:
        """Default visit method: rebuild the node with visited children."""
        getter = self.children.get(type(node))
        if getter is None:
            if isinstance(node, IrLeaf):
                return node
            raise TypeError(f"generic_visit: unknown node type {type(node).__name__!r}")
        old_children = getter(node)
        new_children = tuple(self.visit(c) for c in old_children)
        if all(nc is oc for nc, oc in zip(new_children, old_children)):
            return node
        return self.rebuild[type(node)](node, new_children)


def dump(node: IrNode, *, indent: int = 0) -> str:
    """Pretty-print an IR AST node for debugging."""
    dumper = _DUMP.get(type(node))
    return dumper(node, indent) if dumper else repr(node)
