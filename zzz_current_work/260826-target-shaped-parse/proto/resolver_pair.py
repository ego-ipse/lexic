"""Resolver handoff with REAL trees: island-local versus complete-document.

This file constructs both complete-document `ParseTree`s corresponding to a
differing island seed, associates each with its replayed root meaning, invokes
real deterministic resolvers on both pair scopes, and verifies the selected
target meaning corresponds to the returned derivation. It also:

- shows the exact information the delegated chart is missing (the island
  interior exists only as an opaque `PayloadLeaf`; no interior family is in
  the outer link table), rather than asserting it;
- demonstrates with the real public `CompiledGrammar.parse` that today's
  island resolver receives the ISLAND-LOCAL pair;
- shows a context-sensitive resolver choosing differently between the two
  scopes — the parity argument: PDA and Earley expose one ambiguity opt-out
  only if both engines hand the resolver the same pair scope;
- proves the refusal and equal-root paths perform no complete-document
  reparse, and prices recognition and tree construction separately.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import NamedTuple

import island_alternate_seed as harness
from lexic.compile import compile_text
from lexic.ir import IrSelf, IrSeq
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.grammar.nodes import IrLiteral
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    ambiguity_points,
)
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice
from lexic.parsing.pda.runtime.islands import island_run

type Meaning = harness.Meaning

PUBLIC_ISLAND = (
    'root ::= "(" t ")" "z"\n'
    't ::= t "!" | pair\n'
    "pair ::= one two | onetwo\n"
    'one ::= "x"\ntwo ::= "y"\nonetwo ::= "xy"\n'
)


class Phase(NamedTuple):
    """One measured phase, process CPU and wall separately."""

    cpu: float
    wall: float


def _timed[Result](work: Callable[[], Result]) -> tuple[Result, Phase]:
    """Time one phase."""
    cpu = time.process_time()
    wall = time.perf_counter()
    result = work()
    return result, Phase(time.process_time() - cpu, time.perf_counter() - wall)


def tree_meaning(tree: ParseTree, policies: dict[str, str]) -> Meaning:
    """Fold a real ParseTree with the same meaning algebra the charts use."""
    name = str(tree.symbol)
    policy = policies.get(name, "")
    if policy == "atom":
        return ("atom", _tree_text(tree))
    if policy == "drop":
        return (name,)
    kids = tuple(
        tree_meaning(kid, policies) for kid in tree.kids if isinstance(kid, ParseTree)
    )
    if policy == "swap":
        return (name,) + tuple(reversed(kids))
    if policy == "wrap":
        return (name, ("layer",) + kids)
    return (name,) + kids


def _tree_text(tree: ParseTree) -> str:
    """The consumed span text under one derivation node."""
    parts: list[str] = []
    pending: list[ParseTree] = [tree]
    while pending:
        node = pending.pop(0)
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                pending.append(kid)
            elif isinstance(kid, IrLiteral):
                parts.append(str(kid))
    return "".join(parts)


class SeedCase(NamedTuple):
    """One differing island seed inside a delegated outer run."""

    run: harness.OuterRun
    baseline_root: Meaning
    alternate_root: Meaning
    island_kernel: Kernel
    island_root: int
    island_point: int


def build_case(counters: harness.Counters) -> SeedCase:
    """One kept-difference delegated run with its replayed root meanings."""
    text = "[(xy)]"
    outer = harness._tables(harness.OUTER_ONE, len(text))
    island = harness._tables(harness.ISLAND, len(text))
    run = harness.outer_run(outer, island, text, "t", {}, counters)
    verdict = harness.cone_verdict(run, {}, counters)
    assert verdict.differs
    (leaf_id, seed), *_rest = run.seeds.items()
    graph = harness._graph(run.kernel, run.root)
    replay = harness.Folder(run.kernel, {}, run.occurrences, counters, "replay")
    overlay = harness.Overlay({})
    baseline = harness.Folder(
        run.kernel, {}, run.occurrences, counters, "baseline"
    ).apply(run.root, overlay, set(), None, {})
    alternate = replay.apply(
        run.root,
        harness.Overlay(dict(overlay.changed)),
        harness._dirty(graph, leaf_id),
        None,
        {leaf_id: seed.alternates[0]},
    )
    kern, best = island_run(island, text[2 : 2 + 256])
    if best is None:
        raise UnsupportedConstructError("resolver pair: island did not match")
    item, end = best
    island_root = (item << kern.tables.packing.bits) | end
    points = [
        key
        for key in ambiguity_points(kern, island_root)
        if is_arm_choice(
            kern.st.links[key], kern.tables.packing.bits, kern.tables.code_choice
        )
    ]
    return SeedCase(run, baseline, alternate, kern, island_root, points[0])


def prove_missing_information(case: SeedCase) -> None:
    """The delegated chart cannot reconstruct a complete pair — shown, not
    asserted: the island child in the outer derivation IS an opaque leaf, and
    no interior rule of the island grammar has a completion in the outer link
    table."""
    kernel = case.run.kernel
    tree = FastTree(kernel, {}).build(case.run.root)
    assert isinstance(tree, ParseTree)
    leaves = _payload_leaves(tree)
    assert leaves, "resolver pair: outer tree lost its delegated leaf"
    interior_rules = {"pair", "one", "two", "onetwo"}
    bits = kernel.tables.packing.bits
    interior_completions = 0
    for handle in kernel.st.links:
        code = handle >> (2 * bits)
        if code >= len(kernel.tables.codes.code_arm):
            continue
        rule = kernel.tables.codes.arm_rule[kernel.tables.codes.code_arm[code]]
        if str(kernel.tables.decode.rule_refs[rule]) in interior_rules:
            interior_completions += 1
    print(
        "missing-information",
        f"outer_tree_island_child=PayloadLeaf(text={leaves[0].text!r})",
        f"island_interior_completions_in_outer_chart={interior_completions}",
        "a complete pair therefore needs either a splice of the retained"
        " island derivation or one un-delegated recognition",
        sep="\t",
    )
    assert interior_completions == 0


def _payload_leaves(tree: ParseTree) -> list[PayloadLeaf]:
    """Every delegated leaf below one derivation node."""
    found: list[PayloadLeaf] = []
    pending: list[ParseTree] = [tree]
    while pending:
        node = pending.pop()
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                pending.append(kid)
            elif isinstance(kid, PayloadLeaf):
                found.append(kid)
    return found


class CompletePair(NamedTuple):
    """Both complete-document derivations, associated by root meaning."""

    baseline_tree: ParseTree
    alternate_tree: ParseTree
    recognition: Phase
    construction: Phase


def build_complete_pair(case: SeedCase, counters: harness.Counters) -> CompletePair:
    """One un-delegated recognition; two complete trees; exact association."""
    text = case.run.kernel.text
    tables = harness._tables(harness.OUTER_ONE, len(text))

    def recognize() -> Kernel:
        counters.full_document_parses += 1
        return Kernel(tables, text, True).run()

    kernel, recognition = _timed(recognize)
    if accept_item(kernel) < 0:
        raise UnsupportedConstructError("resolver pair: full parse failed")
    root = accept_handle(kernel)
    points = [
        key
        for key in ambiguity_points(kernel, root)
        if is_arm_choice(
            kernel.st.links[key], kernel.tables.packing.bits, kernel.tables.code_choice
        )
    ]
    assert len(points) == 1

    def construct() -> tuple[ParseTree, ParseTree]:
        first = FastTree(kernel, {}).build(root)
        second = FastTree(kernel, {points[0]: 1}).build(root)
        if not isinstance(first, ParseTree) or not isinstance(second, ParseTree):
            raise UnsupportedConstructError("resolver pair: tree did not build")
        return first, second

    (first, second), construction = _timed(construct)
    meanings = {tree_meaning(first, {}): first, tree_meaning(second, {}): second}
    if set(meanings) != {case.baseline_root, case.alternate_root}:
        raise UnsupportedConstructError(
            "resolver pair: complete meanings do not match the replayed roots"
        )
    return CompletePair(
        meanings[case.baseline_root],
        meanings[case.alternate_root],
        recognition,
        construction,
    )


def island_local_pair(case: SeedCase) -> tuple[ParseTree, ParseTree, Phase]:
    """Both island-local derivations — free from the island kernel in hand."""

    def construct() -> tuple[ParseTree, ParseTree]:
        first = FastTree(case.island_kernel, {}).build(case.island_root)
        second = FastTree(case.island_kernel, {case.island_point: 1}).build(
            case.island_root
        )
        if not isinstance(first, ParseTree) or not isinstance(second, ParseTree):
            raise UnsupportedConstructError("resolver pair: island tree missing")
        return first, second

    (first, second), construction = _timed(construct)
    return first, second, construction


def context_sensitive(first: ParseTree, other: ParseTree) -> ParseTree:
    """A deterministic resolver whose choice depends on the pair's SCOPE.

    Complete-document pairs are rooted at `root`; island-local pairs at `t`.
    It prefers the marker-free derivation when it can see the whole document
    and the marker-bearing one when it can only see the island. Deterministic
    for any fixed pair — exactly the contract `Resolver` declares.
    """
    scope = str(first.symbol)
    first_marked = "onetwo" not in repr(tree_meaning(first, {}))
    if scope == "root":
        return first if first_marked else other
    return other if first_marked else first


def prove_scope_divergence(case: SeedCase, pair: CompletePair) -> None:
    """The SAME resolver picks different target meanings per pair scope."""
    local_first, local_second, local_cost = island_local_pair(case)
    local_choice = context_sensitive(local_first, local_second)
    complete_choice = context_sensitive(pair.baseline_tree, pair.alternate_tree)
    local_meaning = tree_meaning(local_choice, {})
    complete_meaning = tree_meaning(complete_choice, {})
    complete_island_part = _island_subtree_meaning(complete_choice)
    print(
        "scope-divergence",
        f"island_local_choice={local_meaning}",
        f"complete_choice_island_part={complete_island_part}",
        f"diverges={local_meaning != complete_island_part}",
        f"local_pair_construction_cpu={local_cost.cpu:.6f}",
        sep="\t",
    )
    assert local_meaning != complete_island_part
    assert complete_meaning in (case.baseline_root, case.alternate_root)


def _island_subtree_meaning(tree: ParseTree) -> Meaning:
    """The island rule's meaning inside one complete derivation."""
    pending: list[ParseTree] = [tree]
    while pending:
        node = pending.pop()
        if str(node.symbol) == "t":
            return tree_meaning(node, {})
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                pending.append(kid)
    raise UnsupportedConstructError("resolver pair: complete tree lost the island")


def prove_selection_correspondence(case: SeedCase, pair: CompletePair) -> None:
    """Deterministic resolvers: the materialized meaning IS the returned
    derivation's meaning, for both take-first and take-second."""
    for name, resolver in (
        ("take-first", lambda first, other: first),
        ("take-second", lambda first, other: other),
    ):
        chosen = resolver(pair.baseline_tree, pair.alternate_tree)
        materialized = tree_meaning(chosen, {})
        expected = (
            case.baseline_root if chosen is pair.baseline_tree else case.alternate_root
        )
        assert materialized == expected, name
    print(
        "selection-correspondence",
        "take-first/take-second materialize exactly their returned"
        " derivation's replayed root meaning",
        sep="\t",
    )


def _splice(tree: ParseTree, replacement: ParseTree) -> ParseTree:
    """The outer derivation with its delegated leaf replaced by a real island
    derivation — path-copying only the spine above the leaf."""
    new_kids: list[IrSelf] = []
    changed = False
    for kid in tree.kids:
        if isinstance(kid, PayloadLeaf) and not changed:
            new_kids.append(replacement)
            changed = True
        elif isinstance(kid, ParseTree):
            spliced = _splice(kid, replacement)
            if spliced is not kid:
                changed = True
            new_kids.append(spliced)
        else:
            new_kids.append(kid)
    if not changed:
        return tree
    return ParseTree(tree.symbol, IrSeq(*new_kids))


def prove_splice_alternative(case: SeedCase, pair: CompletePair) -> None:
    """The zero-recognition alternative REVIEW asked about: splice the island
    kernel's own derivations into the delegated outer tree, and prove the
    result is STRUCTURALLY IDENTICAL to the un-delegated complete pair."""
    outer_tree = FastTree(case.run.kernel, {}).build(case.run.root)
    assert isinstance(outer_tree, ParseTree)
    local_first, local_second, _cost = island_local_pair(case)

    def construct() -> tuple[ParseTree, ParseTree]:
        return _splice(outer_tree, local_first), _splice(outer_tree, local_second)

    (spliced_a, spliced_b), cost = _timed(construct)
    spliced = {
        tree_meaning(spliced_a, {}): spliced_a,
        tree_meaning(spliced_b, {}): spliced_b,
    }
    assert set(spliced) == {case.baseline_root, case.alternate_root}
    identical = (
        spliced[case.baseline_root] == pair.baseline_tree
        and spliced[case.alternate_root] == pair.alternate_tree
    )
    print(
        "splice-alternative",
        "recognitions=0",
        f"construction_cpu={cost.cpu:.6f}",
        f"construction_wall={cost.wall:.6f}",
        f"structurally_identical_to_undelegated_pair={identical}",
        "NOTE: available on the Earley-delegated path only — the fused PDA"
        " runtime builds models with no document-level ParseTree, so the PDA"
        " path still requires one recognition to produce a complete pair",
        sep="\t",
    )
    assert identical


def prove_no_reparse_paths() -> None:
    """Refusal and equal-root paths never run a complete-document parse."""
    text = "[(xy)]"
    for name, policies, differs in (
        ("refusal", {}, True),
        ("equal-root", {"mid": "drop"}, False),
    ):
        counters = harness.Counters()
        outer = harness._tables(harness.OUTER_ONE, len(text))
        island = harness._tables(harness.ISLAND, len(text))
        run = harness.outer_run(outer, island, text, "t", {}, counters)
        verdict = harness.cone_verdict(run, policies, counters)
        assert verdict.differs == differs, name
        assert counters.full_document_parses == 0, name
        print(
            f"no-reparse-{name}",
            f"differs={verdict.differs}",
            f"document_reparses={counters.full_document_parses}",
            sep="\t",
        )


def prove_public_scope_today() -> None:
    """The REAL public parse hands the resolver the island-local pair today."""
    compiled = compile_text(PUBLIC_ISLAND)
    observed: list[str] = []

    def resolver(first: ParseTree, other: ParseTree) -> ParseTree:
        observed.append(str(first.symbol))
        observed.append(str(other.symbol))
        return first

    model = compiled.parse("(xy)z", cores=1, resolve=resolver)
    assert model.to_text() == "(xy)z"
    assert observed and set(observed) == {"t"}
    print(
        "public-scope-today",
        f"resolver saw pair roots {sorted(set(observed))} — island-local, not"
        " the document root",
        sep="\t",
    )


def main() -> None:
    """Build the pair, prove association, scopes, and path costs."""
    counters = harness.Counters()
    case = build_case(counters)
    assert counters.full_document_parses == 0
    prove_missing_information(case)
    pair = build_complete_pair(case, counters)
    assert counters.full_document_parses == 1
    print(
        "complete-pair-cost",
        f"recognition_cpu={pair.recognition.cpu:.6f}",
        f"recognition_wall={pair.recognition.wall:.6f}",
        f"tree_construction_cpu={pair.construction.cpu:.6f}",
        f"tree_construction_wall={pair.construction.wall:.6f}",
        sep="\t",
    )
    prove_selection_correspondence(case, pair)
    prove_scope_divergence(case, pair)
    prove_splice_alternative(case, pair)
    prove_no_reparse_paths()
    prove_public_scope_today()
    print(
        "conclusion",
        "complete pairs are constructible and associable after inequality is"
        " proven; the delegated chart provably lacks the interior; one pair"
        " scope must be chosen for engine parity, and today's public island"
        " scope is local",
        sep="\t",
    )


if __name__ == "__main__":
    main()
