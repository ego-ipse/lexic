"""IrDispatch, IrVisitor, IrTransformer — Python-ast-style traversal for the IR AST.

``IrDispatch[_N, _T]`` is the shared parent. ``visit()`` dispatches to
``visit_<TypeName>`` methods; missing types fall to ``generic_visit`` which
walks children via ``_CHILDREN`` and delegates to ``_combine`` (subclass
override). The two canonical instantiations are:

  IrVisitor[_N]      = IrDispatch[_N, None]   walks for side effects.
  IrTransformer[_N]  = IrDispatch[_N, _N]     rewrites via ``_REBUILD``.

Other folds-to-T can subclass ``IrDispatch`` directly when state is needed.
For stateless reductions to a value (e.g. pretty-print, source rendering),
prefer a top-level function with a per-type dispatch dict — see ``dump``.

Leaves (IrLiteral, IrCharClass, IrRuleRef) have no children. Unknown node
types raise TypeError.
"""

from __future__ import annotations

from typing import Callable, TypeAlias, TypeVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrGroup,
    IrItem,
    IrLeaf,
    IrNode,
    IrRule,
    IrSequence,
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


class IrDispatch[_N, _T]:
    """Type-name dispatch over IR nodes; parent of IrVisitor and IrTransformer.

    ``visit(node)`` returns whatever ``visit_<TypeName>(node)`` returns. If no
    matching method exists, ``generic_visit`` walks ``node``'s children via
    ``_CHILDREN``, recurses, and combines the visited children into a result
    of type ``_T`` via ``_combine`` (subclass override).
    """

    children: dict[type, _GetChildren] = _CHILDREN
    action: dict[type, Callable[..., _T]]

    def visit(self, node: _N) -> _T:
        """Dispatch to ``visit_<TypeName>(node)`` and return its result."""
        method = getattr(self, f"visit_{type(node).__name__}", self.generic_visit)
        return method(node)

    def generic_visit(self, node: _N) -> _T:
        """Walk children via _CHILDREN, recurse, and delegate to ``_combine``."""
        getter = self.children.get(type(node))
        if getter is None and not isinstance(node, IrLeaf):
            raise UnsupportedConstructError(
                f"generic_visit: unknown node type {type(node).__name__!r}"
            )
        old_children = getter(node) if getter else ()
        new_children = tuple(self.visit(c) for c in old_children)
        return self._combine(node, old_children, new_children)

    def _combine(self, node: _N, old_children: tuple, new_children: tuple) -> _T:
        """Combine visited children into a result for ``node``. Subclass overrides."""
        try:
            return self.action[type(node)](node, old_children, new_children)
        except KeyError as exc:
            raise UnsupportedConstructError(
                f"no action handler for node type {type(node).__name__!r}"
            ) from exc


class IrVisitor[_N](IrDispatch[_N, None]):
    """Walks the IR for side effects. Subclass + define ``visit_<TypeName>`` methods."""

    def _combine(self, node: _N, old_children: tuple, new_children: tuple) -> None:
        return None


class IrTransformer[_N](IrDispatch[_N, _N]):
    """Rewrites the IR. Each ``visit_<TypeName>`` returns a (possibly new) node."""

    action: dict[type, _Rebuilder] = _REBUILD

    def _combine(self, node: _N, old_children: tuple, new_children: tuple) -> _N:
        if not old_children:
            return node
        if all(nc is oc for nc, oc in zip(new_children, old_children)):
            return node
        return self.action[type(node)](node, new_children)


def dump(node: IrNode, *, indent: int = 0) -> str:
    """Pretty-print an IR AST node for debugging."""
    dumper = _DUMP.get(type(node))
    return dumper(node, indent) if dumper else repr(node)
