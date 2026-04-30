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
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSequence,
)


_N = TypeVar("_N")
_GetChildren: TypeAlias = Callable[[_N], tuple[_N, ...]]
_LEAVES = (IrLiteral, IrCharClass, IrRuleRef)

# Maps each interior node type to a function that returns its child nodes.
_CHILDREN: dict[type, _GetChildren] = {
    IrAst: lambda n: n.rules,
    IrRule: lambda n: (n.body,),
    IrAlternation: lambda n: n.arms,
    IrSequence: lambda n: n.items,
    IrItem: lambda n: (n.atom,),
    IrGroup: lambda n: (n.body,),
}


# Maps each interior node type to a function that rebuilds it with new children.
_REBUILD: dict[type, Callable[..., object]] = {
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
        f"{'  ' * i}IrAlternation([\n"
        + ",\n".join(dump(a, indent=i + 1) for a in n.arms)
        + f"\n{'  ' * i}])"
    ),
    IrSequence: lambda n, i: (
        f"{'  ' * i}IrSequence([" + ", ".join(dump(it) for it in n.items) + "])"
    ),
    IrItem: lambda n, i: f"IrItem({dump(n.atom)}, q={n.quantifier})",
    IrGroup: lambda n, i: f"{'  ' * i}IrGroup({dump(n.body, indent=i + 1)})",
}


class IrVisitor:
    """Walks the IR AST. Subclass + define `visit_<TypeName>` methods."""

    leaves: tuple[type, ...] = _LEAVES
    children: dict[type, _GetChildren] = _CHILDREN

    def visit(self, node: object) -> None:
        """Visit a node, dispatching to the appropriate `visit_<TypeName>` method."""
        method = getattr(self, f"visit_{type(node).__name__}", self.generic_visit)
        method(node)

    def generic_visit(self, node: object) -> None:
        """Default visit implementation that walks into child nodes."""
        getter = self.children.get(type(node))
        if getter is not None:
            for child in getter(node):
                self.visit(child)
        elif isinstance(node, self.leaves):
            pass
        else:
            raise TypeError(f"generic_visit: unknown node type {type(node).__name__!r}")


class IrTransformer:
    """Rewrites the IR AST. Each visit returns a (possibly new) node.

    `generic_visit` rebuilds a node with transformed children when any child
    changed, or returns the original node otherwise (identity preservation is
    cheap and lets tests use `is` checks). Unknown node types raise TypeError.
    """

    leaves: tuple[type, ...] = _LEAVES
    rebuild: dict[type, Callable[..., object]] = _REBUILD
    children: dict[type, _GetChildren] = _CHILDREN

    def visit(self, node: object):
        """Visit a node, dispatching to the appropriate `visit_<TypeName>` method."""
        method = getattr(self, f"visit_{type(node).__name__}", self.generic_visit)
        return method(node)

    def generic_visit(self, node: object):
        """Default visit implementation that walks into child nodes and rebuilds if changed."""
        getter = self.children.get(type(node))
        if getter is None:
            if isinstance(node, self.leaves):
                return node
            raise TypeError(f"generic_visit: unknown node type {type(node).__name__!r}")
        old_children = getter(node)
        new_children = tuple(self.visit(c) for c in old_children)
        if all(nc is oc for nc, oc in zip(new_children, old_children)):
            return node
        return self.rebuild[type(node)](node, new_children)


def dump(node: object, *, indent: int = 0) -> str:
    """Pretty-print an IR AST node for debugging."""
    dumper = _DUMP.get(type(node))
    if dumper is None:
        return repr(node)
    return dumper(node, indent)
