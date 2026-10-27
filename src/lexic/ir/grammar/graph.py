"""The rule-reference graph — what a node names, what a rule reaches, what lies on a cycle.

A grammar's rules point at one another through their ``IrRuleRef``
occurrences, and every question about that graph is asked of the one walk
:func:`references`: whether a body names any rule at all, which rules it names
and in what order, which rules a root reaches, and which rules reach an entry.
A rule lies on a reference cycle exactly when its :func:`reach` holds itself.

Cycle membership is not left recursion. ``r ::= "a" r | "b"`` is on a cycle and
is not left-recursive; the nullable-prefix left-corner question belongs to the
PDA analysis, which keeps it.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping

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
