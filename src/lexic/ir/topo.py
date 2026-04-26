"""Generic topological sort over RuleSpecs."""

from __future__ import annotations

from typing import Callable

from lexic.ir.spec import RuleSpec


def topo_sort(
    specs: list[RuleSpec],
    *,
    is_start_rule: Callable[[RuleSpec], bool],
) -> list[RuleSpec]:
    """Order specs so parent classes appear before subclasses, with the start rule first.

    `is_start_rule` is a flavour-supplied predicate. When it matches multiple
    specs, the first one in input order wins.
    """
    by_cls = {s.class_name: s for s in specs}
    ordered: list[RuleSpec] = []
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
