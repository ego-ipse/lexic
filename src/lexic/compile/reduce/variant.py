"""Recognition-only grammar variants for dropped reduction subtrees."""

from __future__ import annotations

from collections.abc import Mapping

from lexic.compile.pipeline.passes import retargeter, skip_rules
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrRule, IrSeq, reachable

_SKIP = "-sk"


def elide_subtrees(
    grammar: IrAst, roots: frozenset[str]
) -> tuple[IrAst, Mapping[str, str]]:
    """Redirect dropped rule occurrences into recognition-only rule twins.

    Every rule reachable below a dropped root receives a recursively retargeted
    twin. Original rules remain available to semantic occurrences elsewhere;
    only references to a dropped root enter the twin graph. The returned names
    seed the post-pass reachability walk whose fold entries are omitted.

    :param grammar: The canonical reducer-derived grammar.
    :param roots: Non-semantic DROP rules whose subtrees need no model.
    :returns: The expanded grammar and twin-name → source-name aliases.
    :raises UnsupportedConstructError: If a generated twin name already exists.
    """
    if not roots:
        return grammar, {}
    names = {str(rule.name) for rule in grammar.rules}
    closure = reachable({str(rule.name): rule for rule in grammar.rules}, roots)
    collisions = sorted(name for name in closure if f"{name}{_SKIP}" in names)
    if collisions:
        targets = ", ".join(repr(f"{name}{_SKIP}") for name in collisions)
        raise UnsupportedConstructError(
            f"reduce: recognition-only rule name collision: {targets}"
        )

    twins = {name: f"{name}{_SKIP}" for name in closure}
    redirect = retargeter({root: twins[root] for root in roots if root in twins})
    originals = tuple(
        IrRule(rule.name, redirect.apply(rule.body), rule.semantic)
        for rule in grammar.rules
    )
    shared = frozenset(names - closure)
    expanded = IrAst(
        IrSeq(*originals, *skip_rules(grammar, shared, _SKIP)), grammar.start
    )
    return expanded, {twin: source for source, twin in twins.items()}
