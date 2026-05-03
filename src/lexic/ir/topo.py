"""Generic topological sort over RuleSpecs."""

from __future__ import annotations

from typing import Callable, Protocol, TypeVar


class _SpecLike(Protocol):
    class_name: str
    parent_class_name: str
    rule_name: str


_S = TypeVar("_S", bound=_SpecLike)


def topo_sort(
    specs: list[_S],
    *,
    is_start_rule: Callable[[_S], bool],
) -> list[_S]:
    """Order specs so parent classes appear before subclasses, with the start rule first.

    `is_start_rule` is a flavour-supplied predicate. When it matches multiple
    specs, the first one in input order wins.
    """
    by_cls = {s.class_name: s for s in specs}
    ordered: list[_S] = []
    visited: set[str] = set()

    def visit(cls_name: str) -> None:
        if cls_name in visited:
            return
        visited.add(cls_name)
        spec = by_cls.get(cls_name)
        if spec and spec.parent_class_name not in ("GrammarModel", "BaseModel"):
            visit(spec.parent_class_name)
        if spec:
            ordered.append(spec)

    start_spec = next((s for s in specs if is_start_rule(s)), None)
    if start_spec is not None:
        visit(start_spec.class_name)
    for s in specs:
        visit(s.class_name)

    return ordered
