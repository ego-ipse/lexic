"""Witness the fold walk's interleaving-dependent execution over shared subtrees."""

from __future__ import annotations

from typing import NamedTuple

from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize


class Witness(NamedTuple):
    """One grammar/input whose built derivation shares a subtree object.

    :ivar name: The shape's label.
    :ivar grammar: GBNF source whose fast-path derivation is a DAG.
    :ivar text: The input.
    :ivar shared_rule: The rule whose derivation object is shared.
    :ivar occurrences: Distinct kid slots referencing the shared object.
    :ivar unguarded_folds: Fold-body executions the current walk performs.
    """

    name: str
    grammar: str
    text: str
    shared_rule: str
    occurrences: int
    unguarded_folds: int


WITNESSES = (
    Witness(
        "duplicate-slot",
        'root ::= a "x" a\na ::= "y"?\n',
        "x",
        "a",
        2,
        2,
    ),
    Witness(
        "pending-frame",
        'root ::= a b\nb ::= a "z"\na ::= "y"?\n',
        "z",
        "a",
        2,
        2,
    ),
    Witness(
        "sibling-memo",
        'root ::= b c\nb ::= a "u"\nc ::= a "w"\na ::= "y"?\n',
        "uw",
        "a",
        2,
        1,
    ),
)
"""Three DAG shapes; the shared node's fold count differs BY TRAVERSAL ORDER."""


def _tree(grammar: str, text: str) -> ParseTree:
    """Parse ``text`` and build the single derivation via the fast path."""
    ast = normalize(canonical_grammar(grammar, GBNF_FLAVOUR))
    kernel = Kernel(compile_tables(ast, tier_for(len(text))), text, True).run()
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("shared forest prototype: no parse")
    built = FastTree(kernel).build(accept_handle(kernel))
    if not isinstance(built, ParseTree):
        raise UnsupportedConstructError("shared forest prototype: the fast path missed")
    return built


def _slot_counts(root: ParseTree) -> dict[int, int]:
    """How many kid slots reference each subtree object, by identity."""
    counts: dict[int, int] = {}
    stack: list[ParseTree] = [root]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        _count_kids(node, counts, stack)
    return counts


def _count_kids(
    node: ParseTree, counts: dict[int, int], stack: list[ParseTree]
) -> None:
    """Record one node's subtree kid slots and queue them for expansion."""
    for kid in node.kids:
        if not isinstance(kid, ParseTree):
            continue
        counts[id(kid)] = counts.get(id(kid), 0) + 1
        stack.append(kid)


def _shared_node(root: ParseTree, rule: str) -> int:
    """The identity of the witness rule's one shared subtree object."""
    found: set[int] = set()
    stack: list[ParseTree] = [root]
    while stack:
        node = stack.pop()
        if str(node.symbol) == rule:
            found.add(id(node))
        stack.extend(kid for kid in node.kids if isinstance(kid, ParseTree))
    if len(found) != 1:
        raise AssertionError(
            f"witness rule {rule!r} is not one shared object: {len(found)}"
        )
    return found.pop()


def _push_unfolded(
    stack: list[tuple[ParseTree, bool]], node: ParseTree, results: set[int]
) -> None:
    """The current walk's push guard: skip only kids whose fold FINISHED.

    This mirrors ``src/lexic/parsing/fold.py`` (the ``id(k) not in results``
    membership test): a shared object still pending on the stack passes the
    guard and is pushed again.
    """
    for kid in node.kids:
        if isinstance(kid, ParseTree) and id(kid) not in results:
            stack.append((kid, False))


def _walk_folds(root: ParseTree, guard_fold: bool) -> dict[int, int]:
    """Replicate the parse-fold walk and count fold-body executions per node.

    With ``guard_fold`` False this is the current discipline. With it True, a
    node whose result already exists is not folded again — the exactly-once
    value contract the plan requires; occurrence effects then belong to the
    parent's slot consumption, not the child's fold body.
    """
    executed: dict[int, int] = {}
    results: set[int] = set()
    stack: list[tuple[ParseTree, bool]] = [(root, False)]
    while stack:
        node, expanded = stack.pop()
        if not expanded:
            stack.append((node, True))
            _push_unfolded(stack, node, results)
            continue
        if guard_fold and id(node) in results:
            continue
        executed[id(node)] = executed.get(id(node), 0) + 1
        results.add(id(node))
    return executed


def _exercise(witness: Witness) -> None:
    """Prove the sharing shape and pin both walks' execution counts."""
    tree = _tree(witness.grammar, witness.text)
    shared = _shared_node(tree, witness.shared_rule)
    slots = _slot_counts(tree)
    if slots.get(shared, 0) != witness.occurrences:
        raise AssertionError(
            f"{witness.name}: expected {witness.occurrences} slots,"
            f" saw {slots.get(shared, 0)}"
        )
    unguarded = _walk_folds(tree, False)
    guarded = _walk_folds(tree, True)
    if unguarded.get(shared, 0) != witness.unguarded_folds:
        raise AssertionError(
            f"{witness.name}: expected {witness.unguarded_folds} unguarded"
            f" folds, saw {unguarded.get(shared, 0)}"
        )
    if guarded.get(shared, 0) != 1:
        raise AssertionError(
            f"{witness.name}: guarded fold ran {guarded.get(shared, 0)} times"
        )
    print(
        witness.name,
        f"occurrences={witness.occurrences}",
        f"unguarded_folds={unguarded[shared]}",
        f"guarded_folds={guarded[shared]}",
        sep="\t",
    )


def main() -> None:
    """Run every witness; the walk must show both over- and under-execution."""
    for witness in WITNESSES:
        _exercise(witness)
    counts = {witness.unguarded_folds for witness in WITNESSES}
    if counts != {1, 2}:
        raise AssertionError("the witnesses no longer span both miscounts")
    print(
        "conclusion",
        "fold-body executions per shared node depend on traversal order:"
        " 2 for duplicate-slot/pending-frame, 1 for sibling-memo —"
        " neither per-node-once nor per-occurrence semantics holds",
        sep="\t",
    )


if __name__ == "__main__":
    main()
