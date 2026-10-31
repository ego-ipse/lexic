"""The rule-reference graph — what a node names, what a rule reaches, what lies on a cycle.

A grammar's rules point at one another through their ``IrRuleRef``
occurrences, and every question about that graph is asked of the one walk
:func:`references`: whether a body names any rule at all, which rules it names
and in what order, which rules a root reaches, and which rules reach an entry.
A rule lies on a reference cycle exactly when its :func:`reach` holds itself.

:func:`callees` takes that walk once per rule, for a caller that asks the graph
again and again; :func:`components` reads it for the order a fixpoint over the
rules wants — each strongly connected component after every one it references.

Cycle membership is not left recursion. ``r ::= "a" r | "b"`` is on a cycle and
is not left-recursive; the nullable-prefix left-corner question belongs to the
PDA analysis, which keeps it.
"""

from __future__ import annotations

from collections.abc import Container, Iterable, Iterator, Mapping, Sequence

from lexic.ir.grammar.nodes import IrRule, IrRuleRef
from lexic.ir.spine.spine import IrSelf


def references(node: IrSelf) -> Iterator[IrRuleRef]:
    """Every rule reference under ``node``, in pre-order, every occurrence.

    :param node: Any grammar node — a rule body, an arm, an item, an atom.
    :returns: The references, as the body spells them.
    """
    stack = [node]
    while stack:
        here = stack.pop()
        if isinstance(here, IrRuleRef):
            yield here
            continue
        stack.extend(reversed(here.children()))


def has_reference(node: IrSelf) -> bool:
    """Whether ``node`` names any rule — stopping at the first reference."""
    return next(references(node), None) is not None


def refs_in_order(node: IrSelf, out: list[str]) -> None:
    """Append each rule ``node`` names to ``out``, first occurrence order.

    :param node: Subtree root to scan.
    :param out: Accumulator; a name already in it is not appended again.
    """
    for ref in references(node):
        name = str(ref)
        if name not in out:
            out.append(name)


def reach(rules: Mapping[str, IrRule]) -> dict[str, frozenset[str]]:
    """Each rule's transitive reference closure — every name it reaches in one
    step or more, an undefined name included and never followed.

    :param rules: The rule table.
    :returns: Rule name → the names it reaches.
    """
    direct = {
        name: frozenset(map(str, references(rule.body))) for name, rule in rules.items()
    }
    out: dict[str, frozenset[str]] = {}
    for name, first in direct.items():
        seen: set[str] = set()
        pending = list(first)
        while pending:
            target = pending.pop()
            if target not in seen:
                seen.add(target)
                pending.extend(direct.get(target, ()))
        out[name] = frozenset(seen)
    return out


def reachable(rules: Mapping[str, IrRule], roots: Iterable[str]) -> frozenset[str]:
    """The defined rules reachable from ``roots``, the roots themselves included.

    :param rules: The rule table.
    :param roots: Where to start; a name the table does not define is dropped.
    :returns: The reachable rule names.
    """
    found: set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        rule = rules.get(name)
        if rule is not None and name not in found:
            found.add(name)
            pending.extend(map(str, references(rule.body)))
    return frozenset(found)


def reaching(rules: Mapping[str, IrRule], entry: str) -> frozenset[str]:
    """The rules from which ``entry`` is reachable, ``entry`` itself included.

    :param rules: The rule table.
    :param entry: The rule to reach.
    :returns: Every rule with a reference path to ``entry``.
    """
    referrers: dict[str, set[str]] = {}
    for name, rule in rules.items():
        for target in references(rule.body):
            referrers.setdefault(str(target), set()).add(name)
    found = {entry}
    pending = [entry]
    while pending:
        for source in referrers.get(pending.pop(), ()):
            if source not in found:
                found.add(source)
                pending.append(source)
    return frozenset(found)


def callees(rules: Mapping[str, IrRule]) -> dict[str, tuple[str, ...]]:
    """Each rule → the defined rules its body names, in first-occurrence order.

    :param rules: The rule table.
    :returns: Rule name → its callees; an undefined name is dropped.
    """
    out: dict[str, tuple[str, ...]] = {}
    for name, rule in rules.items():
        named: list[str] = []
        refs_in_order(rule.body, named)
        out[name] = tuple(target for target in named if target in rules)
    return out


def components(
    graph: Mapping[str, Sequence[str]], root: str, done: Container[str] = ()
) -> list[tuple[str, ...]]:
    """The strongly connected components of the rules ``root`` reaches, callees
    first — every component after each one it references.

    Tarjan's walk on an explicit stack, so a long chain costs no Python frames.

    :param graph: Rule name → its callees (:func:`callees`).
    :param root: Where to start; a rule in ``done`` yields nothing.
    :param done: Rules already settled — neither walked into nor yielded.
    :returns: The components, each sorted by name.
    """
    if root in done:
        return []
    index = {root: 0}
    low = {root: 0}
    stack = [root]
    held = {root}
    out: list[tuple[str, ...]] = []
    work: list[tuple[str, Iterator[str]]] = [(root, iter(graph[root]))]
    while work:
        name, targets = work[-1]
        target = next(targets, None)
        if target is None:
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[name])
            if low[name] == index[name]:
                out.append(_close(stack, held, name))
        elif target in done:
            continue
        elif target not in index:
            index[target] = low[target] = len(index)
            stack.append(target)
            held.add(target)
            work.append((target, iter(graph[target])))
        elif target in held:
            low[name] = min(low[name], index[target])
    return out


def _close(stack: list[str], held: set[str], root: str) -> tuple[str, ...]:
    """Pop the component ``root`` roots off the walk's stack."""
    component: list[str] = []
    while not component or component[-1] != root:
        component.append(stack.pop())
        held.discard(component[-1])
    return tuple(sorted(component))


def cyclic(graph: Mapping[str, Sequence[str]], component: Sequence[str]) -> bool:
    """Whether a component is a cycle — more than one rule, or one naming itself.

    :param graph: Rule name → its callees (:func:`callees`).
    :param component: One of :func:`components`' components.
    """
    return len(component) > 1 or component[0] in graph[component[0]]
