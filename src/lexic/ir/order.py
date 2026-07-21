"""RuleOrder — deterministic start-first ordering of grammar rules.

Reborn from the old ``topo_sort`` skeleton (which orders :class:`RuleSpec`s for
codegen) as an IR-side ordering class: given a rule set, a start rule, and an
edge relation over rule names, :class:`RuleOrder` produces a stable order —
start first, then breadth-first over the edges (first-reference order), then any
rule the walk never reaches, alphabetically.

The edge relation is a policy: :func:`order_by_refs` supplies **ref-edges**
(the ``IrRuleRef`` occurrences in each rule body, in body order), the ordering
the canonicaliser's rule-order rewrite uses. The codegen binding view supplies
**parent-edges** (each rule pointing at its inheritance parent) and walks them
via :meth:`RuleOrder.ordered_parents_first`, so parent classes are emitted
before their subclasses — the successor of the old ``topo_sort``.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable

from lexic.ir.base import IrSelf, IrSeq
from lexic.ir.nodes import IrAst, IrRuleRef


class RuleOrder:
    """Start-first breadth-first ordering over a supplied edge relation.

    :param names: The rule names to order.
    :param start: The start rule name — placed first when present.
    :param edges: Maps a rule name to the names it points at, in significant
        order; only names in ``names`` participate.
    """

    def __init__(
        self, names: Iterable[str], start: str, edges: Callable[[str], list[str]]
    ) -> None:
        self._names = list(names)
        self._known = set(self._names)
        self._start = start
        self._edges = edges

    def ordered(self) -> list[str]:
        """Return the rule names in canonical order.

        :returns: Start first, then breadth-first over the edges, then the
            unreached rules alphabetically.
        """
        order: list[str] = []
        seen: set[str] = set()
        queue: deque[str] = deque([self._start] if self._start in self._known else [])
        while queue:
            name = queue.popleft()
            if name in seen:
                continue
            seen.add(name)
            order.append(name)
            for ref in self._edges(name):
                if ref in self._known and ref not in seen:
                    queue.append(ref)
        order.extend(sorted(n for n in self._names if n not in seen))
        return order

    def ordered_parents_first(self) -> list[str]:
        """Return the rule names with every name after its edge targets.

        The parent-edge policy: ``edges`` points each name at the name(s) that
        must precede it (its inheritance parents). Seeds are the start rule,
        then the names in input order; each seed emits its ancestor chain
        first, so a parent always lands before its subclasses while the rest
        keeps input order.

        :returns: The names, ancestors-first, start's chain leading.
        """
        order: list[str] = []
        seen: set[str] = set()

        def visit(name: str) -> None:
            if name in seen or name not in self._known:
                return
            seen.add(name)  # before the ancestor walk — terminates on a cycle
            for ancestor in self._edges(name):
                visit(ancestor)
            order.append(name)

        if self._start in self._known:
            visit(self._start)
        for name in self._names:
            visit(name)
        return order

    @classmethod
    def by_refs(cls, ast: IrAst) -> IrAst:
        """Reorder ``ast``'s rules start-first by ref-edges (the canonical order).

        The edge relation is each rule's ``IrRuleRef`` occurrences, in body
        order — the ordering the canonicaliser's rule-order rewrite uses.

        :param ast: The grammar AST to reorder.
        :returns: The AST with rules in canonical ref-edge order; start unchanged.
        """
        by_name = {r.name: r for r in ast.rules}
        edges: dict[str, list[str]] = {}
        for rule in ast.rules:
            refs: list[str] = []
            refs_in_order(rule.body, refs)
            edges[rule.name] = refs
        order = cls(by_name, ast.start, lambda n: edges.get(n, [])).ordered()
        return IrAst(IrSeq(*(by_name[name] for name in order)), ast.start)


def refs_in_order(node: IrSelf, out: list[str]) -> None:
    """Collect ``IrRuleRef`` names in pre-order (body) traversal order.

    :param node: Subtree root to scan.
    :param out: Accumulator receiving each ref name in first-seen order.
    """
    if isinstance(node, IrRuleRef):
        name = str(node)
        if name not in out:
            out.append(name)
        return
    for child in node.children():
        refs_in_order(child, out)


def order_by_refs(ast: IrAst) -> IrAst:
    """Module-level alias for :meth:`RuleOrder.by_refs`.

    :param ast: The grammar AST to reorder.
    :returns: The AST with rules in canonical ref-edge order; start unchanged.
    """
    return RuleOrder.by_refs(ast)
