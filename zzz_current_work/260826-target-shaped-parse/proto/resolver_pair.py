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
from functools import partial
from typing import NamedTuple

import island_alternate_seed as harness

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrSelf, IrSeq
from lexic.ir.grammar.nodes import IrLiteral
from lexic.model import GrammarModel
from lexic.parsing import ModelFold, earley_model, pda_tables
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel.forest.support.ambiguity import (
    Resolver,
    ambiguity_points,
    same_value,
)
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.fold import collapsed_fold_tables, lift_optional_nullables
from lexic.parsing.pda.runtime.islands import island_run
from lexic.parsing.pda.runtime.kernel.kernel import pda_model

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


def _take_first(first: ParseTree, _other: ParseTree) -> ParseTree:
    """Deterministic first-derivation resolver."""
    return first


def _take_second(_first: ParseTree, other: ParseTree) -> ParseTree:
    """Deterministic second-derivation resolver."""
    return other


def _record_first(
    seen: list[tuple[ParseTree, ParseTree]], first: ParseTree, other: ParseTree
) -> ParseTree:
    """Record one resolver pair and keep its first derivation."""
    seen.append((first, other))
    return first


def _record_symbol(
    observed: list[str], first: ParseTree, other: ParseTree
) -> ParseTree:
    """Record both resolver roots and keep the first derivation."""
    observed.extend((str(first.symbol), str(other.symbol)))
    return first


def _record_order(order: list[str], first: ParseTree, _other: ParseTree) -> ParseTree:
    """Record when a resolver runs relative to document construction."""
    order.append(f"resolver({first.symbol})")
    return first


def _count_call(calls: list[int], first: ParseTree, _other: ParseTree) -> ParseTree:
    """Count a resolver invocation and keep the first derivation."""
    calls.append(1)
    return first


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
        "a complete pair therefore needs either a splice of the island's own"
        " derivation or one un-delegated recognition. That derivation is NOT"
        " simply retained — see island-refusal-inline, where the island"
        " decides and discards before the document root exists — so the splice"
        " route also needs a deferred decision and per-occurrence state",
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


def _recognize_document(
    tables: ParserTables, text: str, counters: harness.Counters
) -> Kernel:
    """Run and count the cold complete-document recognition."""
    counters.full_document_parses += 1
    return Kernel(tables, text, True).run()


def _tree_pair(kernel: Kernel, root: int, point: int) -> tuple[ParseTree, ParseTree]:
    """Baseline and one-point alternate trees from one finished kernel."""
    first = FastTree(kernel, {}).build(root)
    second = FastTree(kernel, {point: 1}).build(root)
    if not isinstance(first, ParseTree) or not isinstance(second, ParseTree):
        raise UnsupportedConstructError("resolver pair: tree did not build")
    return first, second


def _spliced_pair(
    outer: ParseTree, first: ParseTree, second: ParseTree
) -> tuple[ParseTree, ParseTree]:
    """Two complete trees made by replacing one delegated occurrence."""
    return _splice(outer, first), _splice(outer, second)


def build_complete_pair(case: SeedCase, counters: harness.Counters) -> CompletePair:
    """One un-delegated recognition; two complete trees; exact association."""
    text = case.run.kernel.text
    tables = harness._tables(harness.OUTER_ONE, len(text))

    kernel, recognition = _timed(partial(_recognize_document, tables, text, counters))
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

    (first, second), construction = _timed(partial(_tree_pair, kernel, root, points[0]))
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
    (first, second), construction = _timed(
        partial(_tree_pair, case.island_kernel, case.island_root, case.island_point)
    )
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

    (spliced_a, spliced_b), cost = _timed(
        partial(_spliced_pair, outer_tree, local_first, local_second)
    )
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

    model = compiled.parse("(xy)z", cores=1, resolve=partial(_record_symbol, observed))
    assert model.to_text() == "(xy)z"
    assert observed and set(observed) == {"t"}
    print(
        "public-scope-today",
        f"resolver saw pair roots {sorted(set(observed))} — island-local, not"
        " the document root",
        sep="\t",
    )


# ── occurrence-addressed splicing ─────────────────────────────────────────


def payload_leaves(tree: ParseTree) -> list[PayloadLeaf]:
    """Every delegated leaf below one derivation, in document order."""
    order: list[PayloadLeaf] = []
    pending: list[IrSelf] = [tree]
    while pending:
        node = pending.pop()
        if isinstance(node, PayloadLeaf):
            order.append(node)
        elif isinstance(node, ParseTree):
            pending.extend(reversed(tuple(node.kids)))
    return order


def leaf_occurrences(tree: ParseTree, leaf: PayloadLeaf) -> int:
    """How many positions in ``tree`` hold exactly this leaf OBJECT."""
    return sum(1 for found in payload_leaves(tree) if found is leaf)


def splice_leaf(
    tree: ParseTree, leaf: PayloadLeaf, replacement: ParseTree
) -> ParseTree:
    """The derivation with exactly THIS delegated leaf object replaced.

    Occurrence identity comes from the leaf itself: the kernel injects one
    :class:`PayloadLeaf` per delegated occurrence, so the object names a
    position and an object-addressed splice cannot disturb a sibling island.
    Iterative, path-copying only the spine above the hit.
    """
    spine = _spine_to(tree, leaf)
    current: IrSelf = replacement
    for node, index in reversed(spine):
        kids = list(node.kids)
        kids[index] = current
        current = ParseTree(node.symbol, IrSeq(*kids))
    if not isinstance(current, ParseTree):
        raise UnsupportedConstructError("resolver pair: splice produced no tree")
    return current


def _spine_to(tree: ParseTree, leaf: PayloadLeaf) -> list[tuple[ParseTree, int]]:
    """The ``(node, kid index)`` route from the root down to ``leaf``."""
    stack: list[tuple[ParseTree, list[tuple[ParseTree, int]]]] = [(tree, [])]
    while stack:
        node, route = stack.pop()
        for index, kid in enumerate(node.kids):
            if kid is leaf:
                return route + [(node, index)]
            if isinstance(kid, ParseTree):
                stack.append((kid, route + [(node, index)]))
    raise UnsupportedConstructError("resolver pair: that leaf is not in the tree")


TWO_ISLAND_TEXT = "(xy)(xy)z"
"""Two delegated occurrences of the same island rule in one document."""


def prove_multi_island_occurrence() -> None:
    """Two islands: each occurrence owns its own leaf, and a splice is local."""
    counters = harness.Counters()
    outer = harness._tables(harness.OUTER_TWO, len(TWO_ISLAND_TEXT))
    island = harness._tables(harness.ISLAND, len(TWO_ISLAND_TEXT))
    run = harness.outer_run(outer, island, TWO_ISLAND_TEXT, "t", {}, counters)
    tree = FastTree(run.kernel, {}).build(run.root)
    assert isinstance(tree, ParseTree)
    leaves = payload_leaves(tree)
    assert len(leaves) == 2 and leaves[0] is not leaves[1]
    assert all(leaf_occurrences(tree, leaf) == 1 for leaf in leaves)
    spliced: list[ParseTree] = []
    for position, leaf in zip((1, 5), leaves):
        kern, best = island_run(island, TWO_ISLAND_TEXT[position : position + 256])
        if best is None:
            raise UnsupportedConstructError("resolver pair: island did not match")
        item, end = best
        root = (item << kern.tables.packing.bits) | end
        key = [
            k
            for k in ambiguity_points(kern, root)
            if is_arm_choice(
                kern.st.links[k], kern.tables.packing.bits, kern.tables.code_choice
            )
        ][0]
        alternate = FastTree(kern, {key: 1}).build(root)
        assert isinstance(alternate, ParseTree)
        spliced.append(splice_leaf(tree, leaf, alternate))
    left, right = spliced
    assert left != right
    assert leaf_occurrences(left, leaves[1]) == 1
    assert leaf_occurrences(right, leaves[0]) == 1
    assert leaf_occurrences(left, leaves[0]) == 0
    print(
        "multi-island-occurrence",
        f"seeds={len(run.seeds)}",
        f"delegated_leaves={len(leaves)}",
        f"distinct_leaf_objects={leaves[0] is not leaves[1]}",
        f"occurrences_per_leaf={[leaf_occurrences(tree, leaf) for leaf in leaves]}",
        f"splice_left_keeps_right_leaf={leaf_occurrences(left, leaves[1]) == 1}",
        f"splice_right_keeps_left_leaf={leaf_occurrences(right, leaves[0]) == 1}",
        f"document_reparses={counters.full_document_parses}",
        "occurrence identity is the leaf OBJECT: one per delegated occurrence,"
        " standing at exactly one position",
        sep="\t",
    )


def prove_nested_island_occurrence() -> None:
    """A nested delegated region needs the SAME splice, one level down."""
    text = "[(xy)]"
    counters = harness.Counters()
    outer = harness._tables(harness.OUTER_ONE, len(text))
    island = harness._tables(harness.ISLAND_NESTED, len(text))
    nested = harness._tables(harness.INNER, len(text))
    run = harness.outer_run(outer, island, text, "t", {}, counters, nested, "inner")
    outer_tree = FastTree(run.kernel, {}).build(run.root)
    assert isinstance(outer_tree, ParseTree)
    inner_delegates = harness._delegates(island, nested, "inner", {}, counters)
    outcome = harness.island_product(island, text, 2, {}, counters, inner_delegates)
    assert outcome is not None
    island_tree = FastTree(outcome.kernel, {}).build(outcome.root)
    assert isinstance(island_tree, ParseTree)
    nested_leaves = payload_leaves(island_tree)
    assert len(nested_leaves) == 1
    inner_kern, inner_best = island_run(nested, text[3:])
    assert inner_best is not None
    inner_item, inner_end = inner_best
    inner_root = (inner_item << inner_kern.tables.packing.bits) | inner_end
    inner_tree = FastTree(inner_kern, {}).build(inner_root)
    assert isinstance(inner_tree, ParseTree)
    filled_island = splice_leaf(island_tree, nested_leaves[0], inner_tree)
    outer_leaves = payload_leaves(outer_tree)
    complete = splice_leaf(outer_tree, outer_leaves[0], filled_island)
    assert payload_leaves(complete) == []
    print(
        "nested-island-occurrence",
        f"outer_leaves={len(outer_leaves)}",
        f"island_leaves={len(nested_leaves)}",
        f"opaque_leaves_after_two_splices={len(payload_leaves(complete))}",
        f"document_reparses={counters.full_document_parses}",
        "a complete-document pair over nested delegation is one addressed"
        " splice per delegation LEVEL, innermost first; each level's leaf"
        " object names its own occurrence",
        sep="\t",
    )


# ── what each engine actually hands the resolver ──────────────────────────


class RouteObservation(NamedTuple):
    """What one forced engine route showed its resolver, and what came back."""

    route: str
    called: bool
    first_symbol: str
    other_symbol: str
    kept_first: bool
    kept_other: bool
    crossed: bool


def _observe(
    route: str, run: Callable[[Resolver], GrammarModel], fold: ModelFold
) -> RouteObservation:
    """Run one route twice — take-first and take-second — and MEASURE which
    derivation the returned model corresponds to.

    The ordering claim is that the first argument is the derivation the engine
    already had in hand. Nothing about the pair's roots shows that, so it is
    read off the result: the take-first run's model must fold from the first
    element, and the take-second run's from the second.
    """
    seen: list[tuple[ParseTree, ParseTree]] = []

    kept_first_model = run(partial(_record_first, seen))
    if not seen:
        return RouteObservation(route, False, "", "", False, False, False)
    first, other = seen[0]
    kept_other_model = run(_take_second)
    return RouteObservation(
        route,
        True,
        str(first.symbol),
        str(other.symbol),
        _same_model(kept_first_model, fold, first),
        _same_model(kept_other_model, fold, other),
        # The negative controls the containment test needs to discriminate:
        # neither returned model may match the derivation it did NOT keep.
        _same_model(kept_first_model, fold, other)
        or _same_model(kept_other_model, fold, first),
    )


def _same_model(model: GrammarModel, fold: ModelFold, tree: ParseTree) -> bool:
    """Whether a returned model is the one that derivation folds to.

    An island-scoped pair folds to a SUBTREE's model, which is not the
    document model the route returns, so the containment test is the honest
    one: the derivation's own model must appear inside the returned one.
    """
    built = fold.apply(tree)
    if same_value(model, built):
        return True
    return repr(built) in repr(model)


def prove_engine_pair_scope() -> None:
    """The two engines do not present the same pair TODAY — shown, not claimed."""
    compiled = compile_text(PUBLIC_ISLAND)
    text = "(xy)z"
    grammar = normalize(lift_optional_nullables(compiled.codegen_grammar))
    tables = collapsed_fold_tables(grammar, compiled.fold, tier_for(len(text)))
    predictive = _observe(
        "pda",
        lambda resolve: pda_model(
            pda_tables(compiled.codegen_grammar, compiled.fold),
            text,
            compiled.fold,
            resolve=resolve,
        ),
        compiled.fold,
    )
    general = _observe(
        "earley",
        lambda resolve: earley_model(grammar, text, compiled.fold, tables, resolve),
        compiled.fold,
    )
    assert predictive.called and general.called
    assert predictive.first_symbol != general.first_symbol
    assert predictive.kept_first and predictive.kept_other
    assert general.kept_first and general.kept_other
    assert not predictive.crossed and not general.crossed
    for observation in (predictive, general):
        print(
            "engine-pair-scope",
            observation.route,
            f"resolver_called={observation.called}",
            f"pair_root={observation.first_symbol}",
            f"other_root={observation.other_symbol}",
            f"take_first_returned_the_first_element={observation.kept_first}",
            f"take_second_returned_the_second_element={observation.kept_other}",
            f"crossed_match={observation.crossed}",
            sep="\t",
        )
    print(
        "engine-pair-scope",
        "verdict",
        f"pda_root={predictive.first_symbol}",
        f"earley_root={general.first_symbol}",
        "the ORDERING rule already matches — both hand over (the derivation"
        " in hand, the first differing one) — but the SCOPES differ today:"
        " the PDA's island gate is rooted at the island rule and Earley's"
        " document gate at the start rule, so a context-sensitive resolver"
        " can already observe which engine ran",
        sep="\t",
    )


THIRD_DEFECT_BASELINE = {
    "pda_pair_root": "t",
    "earley_pair_root": "root",
    "pda_refusal": (
        "parsing: island 't' derives the same text two ways that mean"
        " different things — supply a resolver to choose between them"
    ),
    "earley_refusal": (
        "parsing: ambiguous input — two derivations that mean different"
        " things; supply a resolver to choose between them"
    ),
}
"""The UNCONTAMINATED pre-fix behaviour of a THIRD shipped defect.

`Resolver`'s own contract says "both engines given the same pair answer the
same way". On one grammar and one document the two engines hand over pairs
rooted at DIFFERENT rules and refuse with DIFFERENT messages, so a
context-sensitive resolver — and a caller reading the refusal — can already
tell which engine ran. `CURRENT_BUG_REPORT.md` records two defects and not
this one; it is pinned here so the source phase has a reference, and the
coordinator folds it into that document.
"""


def prove_third_defect_baseline() -> None:
    """Pin the engine pair-scope and refusal-message divergence, as found."""
    compiled = compile_text(PUBLIC_ISLAND)
    text = "(xy)z"
    grammar = normalize(lift_optional_nullables(compiled.codegen_grammar))
    tables = collapsed_fold_tables(grammar, compiled.fold, tier_for(len(text)))
    messages: dict[str, str] = {}
    routes = (
        (
            "pda",
            lambda: pda_model(
                pda_tables(compiled.codegen_grammar, compiled.fold),
                text,
                compiled.fold,
            ),
        ),
        ("earley", lambda: earley_model(grammar, text, compiled.fold, tables)),
    )
    for name, run in routes:
        try:
            run()
        except UnsupportedConstructError as error:
            messages[name] = str(error)
        else:
            raise AssertionError(f"{name}: an ambiguous document did not refuse")
    assert messages["pda"] == THIRD_DEFECT_BASELINE["pda_refusal"], messages
    assert messages["earley"] == THIRD_DEFECT_BASELINE["earley_refusal"], messages
    print(
        "third-defect-baseline",
        f"pda_refusal={messages['pda']!r}",
        f"earley_refusal={messages['earley']!r}",
        f"messages_differ={messages['pda'] != messages['earley']}",
        f"pair_roots=pda={THIRD_DEFECT_BASELINE['pda_pair_root']}"
        f" earley={THIRD_DEFECT_BASELINE['earley_pair_root']}",
        "Resolver declares that both engines given the same pair answer the"
        " same way; they are not given the same pair, and they do not refuse"
        " with the same words — a THIRD shipped defect, not in"
        " CURRENT_BUG_REPORT.md",
        sep="\t",
    )


def prove_island_refusal_is_inline() -> None:
    """The island decides — and can REFUSE — before the document root exists.

    `islands.island_parse` calls `another_meaning` and then either
    `policy.resolve` or a refusal, inline, and returns only ``(tree, end)``;
    the island kernel dies with the call. A document-rooted pair therefore
    cannot be assembled from state the parse already holds: the decision has to
    be DEFERRED and per-occurrence state carried to the root. This corrects the
    earlier claim that both derivations are "already retained".
    """
    compiled = compile_text(PUBLIC_ISLAND)
    order: list[str] = []

    model = compiled.parse("(xy)z", cores=1, resolve=partial(_record_order, order))
    order.append(f"document_model({type(model).__name__})")
    refusal = ""
    try:
        compiled.parse("(xy)z", cores=1)
    except UnsupportedConstructError as error:
        refusal = str(error)
    print(
        "island-refusal-inline",
        f"call_order={order}",
        f"resolver_ran_before_the_document_model={order[0].startswith('resolver')}",
        f"refusal_without_a_resolver={refusal}",
        "so a document-rooted pair must DEFER this decision and retain"
        " per-occurrence state; it is not assembled from state already held",
        sep="\t",
    )


def prove_scope_changes_the_question() -> None:
    """Document scope changes WHETHER to refuse, not only the pair's root.

    A dropping parent makes the island-local question and the document-root
    question disagree: the island has a second meaning, the document does not.
    Whichever scope is chosen therefore also decides what the engines refuse,
    which the decision table has to say out loud.

    Harness output under a TOY policy, and the row says so itself: the whole
    run goes through `island_alternate_seed`'s re-implementation, and
    ``{"mid": "drop"}`` stands in for a reducer's ``DROP``. What it shows is
    that a dropping parent CAN make the two questions disagree — a property of
    the two scopes — not how often a shipped grammar does it.
    """
    text = "[(xy)]"
    for label, policies in (("kept", {}), ("dropping-parent", {"mid": "drop"})):
        counters = harness.Counters()
        outer = harness._tables(harness.OUTER_ONE, len(text))
        island = harness._tables(harness.ISLAND, len(text))
        run = harness.outer_run(outer, island, text, "t", {}, counters)
        verdict = harness.cone_verdict(run, policies, counters)
        island_alternates = sum(len(seed.alternates) for seed in run.seeds.values())
        print(
            "scope-changes-the-question",
            "PROTOTYPE-HARNESS ROW under a TOY policy",
            label,
            f"island_local_second_meanings={island_alternates}",
            f"document_root_differs={verdict.differs}",
            f"the_two_questions_agree={bool(island_alternates) == verdict.differs}",
            sep="\t",
        )


def prove_document_pair_scaling() -> None:
    """The cold recognition a document-scoped PDA pair costs, at three sizes.

    A full Earley recognition of the whole document is linear in it — the very
    cost PDA-first composition exists to avoid — so quoting it at five
    characters would understate what the user is ruling on. Sequential, one
    process, no pool.
    """
    for repeats in (1, 16, 128):
        text = "(xy)z" * repeats
        grammar = (
            'root ::= piece+\npiece ::= "(" t ")" "z"\n'
            + PUBLIC_ISLAND.split("\n", 1)[1]
        )
        tables = harness._tables(grammar, len(text))
        kernel, phase = _timed(lambda: Kernel(tables, text, True).run())
        assert accept_item(kernel) >= 0
        print(
            "document-pair-scaling",
            f"chars={len(text)}",
            f"cold_recognition_cpu={phase.cpu:.6f}",
            f"cold_recognition_wall={phase.wall:.6f}",
            "linear in the document; a five-character quote is not the price",
            sep="\t",
        )


def prove_no_shadow_on_unambiguous_path() -> None:
    """Neither scope needs a shadow model or tree on the unambiguous path."""
    counters = harness.Counters()
    text = "[(xy)]"
    outer = harness._tables(harness.OUTER_ONE, len(text))
    plain = harness._tables(harness.ISLAND_PLAIN, len(text))
    run = harness.outer_run(outer, plain, text, "t", {}, counters)
    verdict = harness.cone_verdict(run, {}, counters)
    assert not verdict.differs
    assert not run.seeds
    assert counters.full_document_parses == 0
    compiled = compile_text(PUBLIC_ISLAND)
    calls: list[int] = []

    ambiguous = compiled.parse("(xy)z", cores=1, resolve=partial(_count_call, calls))
    assert ambiguous.to_text() == "(xy)z"
    print(
        "no-shadow",
        "PROTOTYPE-HARNESS ROW: the seed and reparse counts come from"
        " island_alternate_seed's own delegated re-implementation, not from"
        " src; only the resolver-call count is from the public API",
        f"unambiguous_island_seeds={len(run.seeds)}",
        f"document_reparses={counters.full_document_parses}",
        f"resolver_calls_on_an_AMBIGUOUS_document={len(calls)}",
        "both scopes build the pair AFTER inequality is proven, so nothing is"
        " retained ahead of time and the unambiguous path carries no shadow"
        " model or tree. That is the whole of what this row shows: the island"
        " derivations are NOT free re-use — see island-refusal-inline, where"
        " the island decides and discards before the document root exists —"
        " so a document-rooted pair needs a deferred decision and"
        " per-occurrence retained state",
        sep="\t",
    )


def prove_pda_has_no_document_tree() -> None:
    """The fused PDA product builds models with no document `ParseTree`."""
    compiled = compile_text(PUBLIC_ISLAND)
    text = "(xy)z"
    model, cost = _timed(
        lambda: pda_model(
            pda_tables(compiled.codegen_grammar, compiled.fold),
            text,
            compiled.fold,
            resolve=lambda first, other: first,
        )
    )
    assert model.to_text() == text
    tables = harness._tables(PUBLIC_ISLAND, len(text))
    recognition, phase = _timed(lambda: Kernel(tables, text, True).run())
    assert accept_item(recognition) >= 0
    print(
        "pda-document-scope",
        f"pda_model_cpu={cost.cpu:.6f}",
        "document_parse_tree=None (the fused runtime builds models during"
        " recognition and retains no chart)",
        f"cold_earley_recognition_for_a_document_pair_cpu={phase.cpu:.6f}",
        f"cold_earley_recognition_wall={phase.wall:.6f}",
        "so a complete-document pair on the predictive path costs ONE extra"
        " recognition plus two tree builds, paid only after inequality and an"
        " actual resolve= call",
        sep="\t",
    )


def prove_scope_costs(case: SeedCase, pair: CompletePair) -> None:
    """The per-scope cold work and retained state, as one decision table."""
    local_first, local_second, local_cost = island_local_pair(case)
    assert local_first is not local_second
    outer_tree = FastTree(case.run.kernel, {}).build(case.run.root)
    assert isinstance(outer_tree, ParseTree)
    leaves = payload_leaves(outer_tree)
    (_a, _b), splice_cost = _timed(
        lambda: (
            splice_leaf(outer_tree, leaves[0], local_first),
            splice_leaf(outer_tree, leaves[0], local_second),
        )
    )
    print(
        "scope-cost",
        "island-local",
        "extra_recognitions=0",
        "extra_tree_builds=2 (island kernel already in hand)",
        f"construction_cpu={local_cost.cpu:.6f}",
        "retained=the island kernel the sub-parse already holds",
        sep="\t",
    )
    print(
        "scope-cost",
        "complete-document/earley-delegated",
        "extra_recognitions=0",
        "extra_tree_builds=2 island + 2 addressed splices",
        f"construction_cpu={splice_cost.cpu:.6f}",
        "retained=the outer chart plus, per ambiguous island occurrence, a"
        " DEFERRED decision and the derivations it needs — see"
        " island-refusal-inline; today's island decides and discards inline",
        sep="\t",
    )
    print(
        "scope-cost",
        "complete-document/fused-pda",
        "extra_recognitions=1",
        "extra_tree_builds=2",
        f"recognition_cpu={pair.recognition.cpu:.6f}",
        f"construction_cpu={pair.construction.cpu:.6f}",
        "retained=nothing before the refusal; the cold recognition is the whole cost",
        sep="\t",
    )


def prove_public_type_survives() -> None:
    """Both candidate scopes keep today's `Resolver` SIGNATURE — and only that."""
    annotation = getattr(Resolver, "__value__", Resolver)
    print(
        "public-type",
        f"Resolver={annotation}",
        "both scopes hand over two ParseTrees and take one back, so the"
        " declared type is unchanged in either; what changes under the"
        " complete-document scope is the CONTRACT — the pair's root — which a"
        " context-sensitive resolver observes (see scope-divergence), so it is"
        " a deliberate pre-alpha contract change even though no signature"
        " moves",
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
    prove_engine_pair_scope()
    prove_third_defect_baseline()
    prove_multi_island_occurrence()
    prove_nested_island_occurrence()
    prove_no_shadow_on_unambiguous_path()
    prove_pda_has_no_document_tree()
    prove_island_refusal_is_inline()
    prove_scope_changes_the_question()
    prove_document_pair_scaling()
    prove_scope_costs(case, pair)
    prove_public_type_survives()
    print(
        "conclusion",
        "complete pairs are constructible and associable after inequality is"
        " proven; the delegated chart provably lacks the interior; the two"
        " engines already present DIFFERENT pair scopes; occurrence identity"
        " rides the delegated leaf object at every delegation level; neither"
        " scope needs a shadow on the unambiguous path; the choice of scope"
        " is a USER DECISION and is not made here",
        sep="\t",
    )


if __name__ == "__main__":
    main()
