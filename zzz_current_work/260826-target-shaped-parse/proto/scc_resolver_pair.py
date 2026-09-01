"""A constructive resolver pair for an INFINITE equal-span component.

`cyclic_meaning.py` decides that a growing equal-span component under an
injective path to a requested root makes that root's meaning family infinite.
That is enough to REFUSE. It is not enough for ``resolve=``, which is handed
two derivations and must be able to see that they mean different things.

This module builds that pair, structurally:

1. take the accepting derivation the real `FastTree` already builds — the
   derivation the parse itself produced, which is the FIRST element of the
   pair, exactly as the shipped ``resolve(tree, witness)`` call sites hand over
   the derivation in hand;
2. certify the growing component and find a carrier that both lies on a growing
   closed walk of the component's own carrying edges and stands in that
   derivation;
3. select one explicit directed traversal — a CLOSED WALK through the carrier
   carrying at least one ``grow`` edge, built as prefix + grow edge + suffix
   from breadth-first shortest paths over a fixed edge order;
4. splice exactly that traversal in at that occurrence, once, path-copying only
   the spine above it;
5. read both complete meanings at the requested root and check they differ.

There is no lap count anywhere: the traversal is one closed walk over the
component's own finite edge set, built from two shortest paths and one edge, so
its length is bounded by the component and the construction terminates for a
structural reason rather than a numeric one. A *simple* cycle is deliberately
NOT required — deciding whether one exists through a given vertex carrying a
given edge is the directed two-disjoint-paths problem, and requiring it refused
a real grammar (:data:`UPSTREAM_CARRIER`) that plainly has a pair. A walk
splices exactly as well.

The trees are held against three checks: their yields equal the document, every
node instantiates a real arm of the normalized grammar (character-class
membership included), and both meanings appear in `cyclic_meaning`'s
bounded-depth enumeration oracle. That oracle is independent in its DERIVATION
ENUMERATION only — it shares ``apply_policy``, the meaning algebra — and
termination is argued from the walk, not from the ladder.
"""

from __future__ import annotations

import time
from typing import NamedTuple

import cyclic_meaning as cyclic
import island_alternate_seed as harness

from lexic.compile import canonical_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrSeq
from lexic.ir.grammar.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spine.spine import IrSelf
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel.forest.support.readout import accept_item
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.normalize import normalize

type Meaning = cyclic.Meaning


class PairRefusal(UnsupportedConstructError):
    """A component that classifies but for which no pair may be constructed."""


class Certificate(NamedTuple):
    """One growing component, its carriers, and the chart it was read from."""

    chart: cyclic.Chart
    classes: cyclic.Classes
    component: tuple[int, ...]
    carriers: frozenset[int]
    roots: tuple[int, ...]


def certify(
    kernel: Kernel, root: int, policies: dict[str, str], program: tuple[str, ...]
) -> Certificate:
    """Find the growing component whose carriers reach a root injectively.

    :param kernel: The finished real Earley kernel.
    :param root: The requested accepting handle.
    :param policies: The rule-name → operation program.
    :param program: That program lowered to completed codes.
    :returns: The certificate the construction reads.
    :raises PairRefusal: When no component is classified ``cyclic-infinite``.
    """
    del policies
    roots = cyclic.accepting_roots(kernel, root)
    chart = cyclic.build_chart(kernel, roots)
    classes = cyclic.classify_edges(kernel, chart, program, roots)
    groups = cyclic.components(chart.nodes, chart.children)
    for group, internal in zip(groups, cyclic._bucket_edges(groups, chart)):
        verdict = cyclic.component_kind(group, internal, classes)
        if verdict.kind == cyclic.CYCLIC_INFINITE:
            return Certificate(chart, classes, group, verdict.carriers, roots)
    raise PairRefusal(
        "resolver pair: no component is classified cyclic-infinite, so this"
        " chart has no growing family to carry a second complete meaning"
    )


def program_of(kernel: Kernel, policies: dict[str, str]) -> tuple[str, ...]:
    """The completed-code program the chart classification reads."""
    return harness.Folder(kernel, policies, {}, harness.Counters(), "oracle").program


def internal_carrying(
    chart: cyclic.Chart, classes: cyclic.Classes, group: tuple[int, ...]
) -> tuple[cyclic.Edge, ...]:
    """The component's own ``ident``/``grow`` edges, in a deterministic order.

    Sorted by the packed parent handle, then the packed child handle, then the
    kid slot — raw integers, nothing decoded — so the traversal a run selects
    does not depend on chart discovery order.
    """
    members = set(group)
    found = [
        edge
        for edge in chart.edges
        if edge.parent in members
        and edge.child in members
        and classes.edge_class[edge] in (cyclic.IDENT, cyclic.GROW)
    ]
    return tuple(sorted(set(found), key=lambda e: (e.parent, e.child, e.slot)))


def _outgoing(edges: tuple[cyclic.Edge, ...]) -> dict[int, list[cyclic.Edge]]:
    """Each node's outgoing carrying edges, preserving the given order."""
    out: dict[int, list[cyclic.Edge]] = {}
    for edge in edges:
        out.setdefault(edge.parent, []).append(edge)
    return out


def _unwind(
    came: dict[int, cyclic.Edge], source: int, target: int
) -> tuple[cyclic.Edge, ...]:
    """The edge path recorded by :func:`_shortest`, source-first."""
    path: list[cyclic.Edge] = []
    node = target
    while node != source:
        edge = came[node]
        path.append(edge)
        node = edge.parent
    path.reverse()
    return tuple(path)


def _shortest(
    outgoing: dict[int, list[cyclic.Edge]], source: int, target: int
) -> tuple[cyclic.Edge, ...] | None:
    """A shortest edge path ``source -> target``, or ``None`` when unreachable.

    Breadth-first over a fixed edge order, so the path is a function of the
    edge set alone. An empty tuple means ``source`` IS ``target``.
    """
    if source == target:
        return ()
    came: dict[int, cyclic.Edge] = {}
    seen = {source}
    frontier = [source]
    while frontier:
        following: list[int] = []
        for node in frontier:
            for edge in outgoing.get(node, ()):
                if edge.child in seen:
                    continue
                seen.add(edge.child)
                came[edge.child] = edge
                if edge.child == target:
                    return _unwind(came, source, target)
                following.append(edge.child)
        frontier = following
    return None


def growing_walk(
    edges: tuple[cyclic.Edge, ...], start: int, classes: cyclic.Classes
) -> tuple[cyclic.Edge, ...]:
    """One closed directed walk through ``start`` carrying a ``grow`` edge.

    Built as ``shortest(start -> u) + (u, v) + shortest(v -> start)`` for the
    first ``grow`` edge ``(u, v)`` whose two halves both exist, taking the
    component's carrying edges in their fixed order. Cost is two breadth-first
    searches per candidate grow edge — ``O(E x (V + E))`` — and the result is a
    function of the edge set alone.

    A closed WALK, not a simple cycle: a walk splices exactly as well, and
    deciding whether a simple cycle through a given vertex carries a given edge
    is the directed two-disjoint-paths problem.

    :param edges: The component's carrying edges, deterministically ordered.
    :param start: The carrier the walk must pass through.
    :param classes: Edge classes, for the ``grow``-edge requirement.
    :returns: The walk, leaving and re-entering ``start``.
    :raises PairRefusal: When no such walk exists through ``start``.
    """
    outgoing = _outgoing(edges)
    for edge in edges:
        if classes.edge_class[edge] != cyclic.GROW:
            continue
        prefix = _shortest(outgoing, start, edge.parent)
        if prefix is None:
            continue
        suffix = _shortest(outgoing, edge.child, start)
        if suffix is None:
            continue
        return prefix + (edge,) + suffix
    raise PairRefusal(
        "resolver pair: no closed carrying walk through this carrier reaches a"
        " grow edge and returns, so this carrier cannot be extended"
    )


class Occurrence(NamedTuple):
    """One addressed position of a subtree inside one derivation."""

    path: tuple[int, ...]
    node: ParseTree


def _leaf_width(node: IrSelf) -> int:
    """How many characters one non-derivation kid consumes."""
    if isinstance(node, PayloadLeaf):
        return len(node.text)
    if isinstance(node, IrLiteral):
        return len(str(node))
    return 0


def consumed(node: IrSelf, memo: dict[int, int]) -> int:
    """How many characters one derivation node consumes, memoised by object.

    Iterative post-order: a derivation is as deep as its document, so the C
    stack is not available for this.
    """
    found = memo.get(id(node))
    if found is not None:
        return found
    if not isinstance(node, ParseTree):
        return _leaf_width(node)
    stack: list[tuple[ParseTree, bool]] = [(node, False)]
    while stack:
        current, expanded = stack.pop()
        if id(current) in memo:
            continue
        if not expanded:
            stack.append((current, True))
            stack.extend(
                (kid, False) for kid in current.kids if isinstance(kid, ParseTree)
            )
            continue
        memo[id(current)] = sum(
            memo[id(kid)] if isinstance(kid, ParseTree) else _leaf_width(kid)
            for kid in current.kids
        )
    return memo[id(node)]


def occurrences_of(
    tree: ParseTree, symbol: IrRuleRef, span: tuple[int, int]
) -> tuple[Occurrence, ...]:
    """Every position deriving ``symbol`` over exactly ``span``, addressed.

    Siblings cannot share a non-empty span, but a zero-width cycle can nest the
    same rule and span more than once. The explicit path, not ``(rule, span)``,
    is therefore the occurrence identity used by the splice.
    """
    memo: dict[int, int] = {}
    found: list[Occurrence] = []
    stack: list[tuple[ParseTree, tuple[int, ...], int]] = [(tree, (), 0)]
    while stack:
        node, path, start = stack.pop()
        end = start + consumed(node, memo)
        if node.symbol == symbol and (start, end) == span:
            found.append(Occurrence(path, node))
        offset = start
        frames: list[tuple[ParseTree, tuple[int, ...], int]] = []
        for index, kid in enumerate(node.kids):
            if isinstance(kid, ParseTree):
                frames.append((kid, path + (index,), offset))
            offset += consumed(kid, memo)
        stack.extend(reversed(frames))
    return tuple(found)


def locate_span(
    tree: ParseTree, symbol: IrRuleRef, span: tuple[int, int]
) -> Occurrence:
    """The first deterministic occurrence deriving ``symbol`` over ``span``.

    :raises PairRefusal: When the derivation holds no such occurrence.
    """
    found = occurrences_of(tree, symbol, span)
    if not found:
        raise PairRefusal(
            f"resolver pair: no occurrence of {str(symbol)!r} over {span} stands"
            " in the accepting derivation, so no position can be extended"
        )
    return found[0]


def handle_span(kernel: Kernel, handle: int) -> tuple[int, int]:
    """The document span one packed completion covers."""
    bits, mask = kernel.tables.packing.bits, kernel.tables.packing.mask
    return ((handle >> bits) & mask, handle & mask)


def _symbol(kernel: Kernel, handle: int) -> IrRuleRef:
    """The rule one completed handle derives."""
    return IrRuleRef(harness._name(kernel, handle))


def _family_for(
    kernel: Kernel, handle: int, edge: cyclic.Edge, chart: cyclic.Chart
) -> harness.Resolved:
    """The parent's own family that actually contains ``edge``."""
    for resolved in chart.resolveds[handle]:
        slots = cyclic.child_slots(resolved)
        for slot, child in zip(slots, resolved.children):
            if child == edge.child and slot == edge.slot:
                return resolved
    raise PairRefusal(
        f"resolver pair: no family of {harness._name(kernel, handle)!r} holds"
        f" the certified edge at slot {edge.slot}"
    )


def _kids(
    kernel: Kernel,
    resolved: harness.Resolved,
    replace_slot: int,
    replacement: IrSelf,
) -> IrSeq:
    """One completion's kids, with exactly one slot replaced.

    `harness.Resolved` carries child handles and delegated leaves but not
    scanned terminals, so this is only right where a carrier edge's siblings
    consume nothing. :func:`traverse_once` CHECKS that rather than trusting it:
    a dropped terminal changes the consumed width, and the width is compared
    against the carrier's own span.
    """
    width = len(resolved.children) + len(resolved.leaves)
    ints = iter(resolved.children)
    out: list[IrSelf] = []
    for index in range(width):
        if index in resolved.slots:
            out.append(resolved.leaves[resolved.slots.index(index)])
            continue
        child = next(ints)
        if index == replace_slot:
            out.append(replacement)
            continue
        built = FastTree(kernel, {}).build(child)
        if not isinstance(built, ParseTree):
            raise PairRefusal("resolver pair: a walk sibling did not build")
        out.append(built)
    return IrSeq(*out)


def traverse_once(
    kernel: Kernel, chart: cyclic.Chart, walk: tuple[cyclic.Edge, ...], base: ParseTree
) -> ParseTree:
    """Wrap ``base`` in exactly one traversal of the selected closed walk.

    Built from the deepest edge upwards, so a long walk costs one pass and no
    Python recursion. The result must consume exactly what ``base`` consumed —
    every node of an equal-span component covers the same span — and a walk
    node that pulled in a scanned terminal `harness.Resolved` cannot represent
    would break that.

    :raises PairRefusal: When the traversal changed the consumed width.
    """
    memo: dict[int, int] = {}
    expected = consumed(base, memo)
    current: IrSelf = base
    for edge in reversed(walk):
        resolved = _family_for(kernel, edge.parent, edge, chart)
        current = ParseTree(
            _symbol(kernel, edge.parent), _kids(kernel, resolved, edge.slot, current)
        )
    if not isinstance(current, ParseTree):
        raise PairRefusal("resolver pair: the traversal produced no derivation")
    if consumed(current, memo) != expected:
        raise PairRefusal(
            "resolver pair: the traversal changed the consumed width, so a walk"
            " node carries a child this construction cannot represent"
        )
    return current


def splice_at(
    tree: ParseTree, path: tuple[int, ...], replacement: ParseTree
) -> ParseTree:
    """The derivation with exactly the node at ``path`` replaced.

    Path-copies the spine above the occurrence and shares everything else,
    iteratively — a document-deep derivation must not need the C stack.
    """
    spine: list[ParseTree] = [tree]
    for index in path:
        kid = spine[-1].kids[index]
        if not isinstance(kid, ParseTree):
            raise PairRefusal("resolver pair: the occurrence path left the tree")
        spine.append(kid)
    current: IrSelf = replacement
    for depth in range(len(path) - 1, -1, -1):
        parent = spine[depth]
        kids = list(parent.kids)
        kids[path[depth]] = current
        current = ParseTree(parent.symbol, IrSeq(*kids))
    if not isinstance(current, ParseTree):
        raise PairRefusal("resolver pair: the splice produced no derivation")
    return current


class Pair(NamedTuple):
    """Two complete derivations of one document and their target meanings."""

    first: ParseTree
    other: ParseTree
    first_meaning: Meaning
    other_meaning: Meaning
    walk: tuple[cyclic.Edge, ...]
    path: tuple[int, ...]
    carrier: str
    carriers_tried: int
    baseline_occurrences: int


def construct_pair(
    kernel: Kernel,
    root: int,
    policies: dict[str, str],
    overrides: dict[int, Meaning],
) -> Pair:
    """Build the two complete derivations ``resolve=`` needs, structurally.

    ``first`` IS the derivation the parse produced — what the shipped
    ``resolve(tree, witness)`` call sites pass as their first argument — and
    ``other`` is that derivation with one traversal of the growing walk spliced
    in at one addressed occurrence.

    :param kernel: The finished real Earley kernel.
    :param root: The requested accepting handle.
    :param policies: The rule-name → operation program.
    :param overrides: Delegated-leaf meanings, by leaf id.
    :returns: Both derivations and both complete requested-root meanings.
    :raises PairRefusal: When the chart carries no constructible pair.
    """
    program = program_of(kernel, policies)
    certificate = certify(kernel, root, policies, program)
    outer = FastTree(kernel, {}).build(root)
    if not isinstance(outer, ParseTree):
        raise PairRefusal("resolver pair: the accepting derivation did not build")
    carrier, walk, occurrence, tried, seen = _pick_carrier(kernel, certificate, outer)
    traversed = traverse_once(kernel, certificate.chart, walk, occurrence.node)
    other = splice_at(outer, occurrence.path, traversed)
    first_meaning = cyclic.tree_meaning(outer, policies, overrides)
    other_meaning = cyclic.tree_meaning(other, policies, overrides)
    if first_meaning == other_meaning:
        # The certificate says the component's family is infinite under an
        # injective path, and the splice sends the difference up the same
        # carrying edges that closure was built from. If the two complete
        # meanings still compare equal, that argument did not hold on THIS
        # chart, and the honest answer is a named refusal — not a pair whose
        # two elements mean the same thing, and not an assertion in a caller.
        raise PairRefusal(
            "resolver pair: the spliced traversal did not change the requested"
            f" root's meaning at {harness._name(kernel, carrier)!r}; the"
            " component certifies infinite but this carrier's difference does"
            " not reach the requested root"
        )
    return Pair(
        outer,
        other,
        first_meaning,
        other_meaning,
        walk,
        occurrence.path,
        harness._name(kernel, carrier),
        tried,
        seen,
    )


def _pick_carrier(
    kernel: Kernel, certificate: Certificate, outer: ParseTree
) -> tuple[int, tuple[cyclic.Edge, ...], Occurrence, int, int]:
    """A carrier that both lies on a growing walk and stands in the derivation.

    EVERY carrier is tried, in packed-handle order, and the first satisfying
    both conditions wins. Committing to one carrier is what refused
    :data:`UPSTREAM_CARRIER`: `cyclic_meaning._carriers` returns the
    ``ident``/``grow`` upward closure of the growing sub-cycle, and a member of
    that closure need not lie on a closed carrying walk at all.

    Injective visibility is NOT re-checked here. It is a property of the
    COMPONENT, already established by :func:`certify`, and it holds of some
    carrier in that upward closure. Splicing at any node of the growing
    sub-cycle sends the difference up to that carrier along the same carrying
    edges the closure was built from, and from there injectively to a requested
    root. That argument is prose, so :func:`construct_pair` CHECKS its
    conclusion and refuses by name if the two complete meanings come out equal
    — the residual class this construction does not prove away.
    """
    carrying = internal_carrying(
        certificate.chart, certificate.classes, certificate.component
    )
    tried = 0
    for carrier in sorted(certificate.carriers):
        tried += 1
        try:
            walk = growing_walk(carrying, carrier, certificate.classes)
        except PairRefusal:
            continue
        found = occurrences_of(
            outer, _symbol(kernel, carrier), handle_span(kernel, carrier)
        )
        if not found:
            continue
        return carrier, walk, found[0], tried, len(found)
    raise PairRefusal(
        "resolver pair: no carrier of the growing component both lies on a"
        " closed carrying walk and stands in the accepting derivation"
    )


# ── independent structural validation ─────────────────────────────────────


def yield_text(tree: ParseTree) -> str:
    """The characters one derivation consumes, left to right."""
    out: list[str] = []
    stack: list[IrSelf] = [tree]
    while stack:
        node = stack.pop()
        if isinstance(node, ParseTree):
            stack.extend(reversed(tuple(node.kids)))
        elif isinstance(node, PayloadLeaf):
            out.append(node.text)
        elif isinstance(node, IrLiteral):
            out.append(str(node))
    return "".join(out)


def _arms(ast: IrAst) -> dict[str, tuple[IrSequence, ...]]:
    """Each normalized rule's alternative sequences."""
    out: dict[str, tuple[IrSequence, ...]] = {}
    for rule in ast[0]:
        if not isinstance(rule, IrRule):
            continue
        body = rule.body
        if isinstance(body, IrAlternation):
            out[str(rule.name)] = tuple(
                arm for arm in body if isinstance(arm, IrSequence)
            )
        elif isinstance(body, IrSequence):
            out[str(rule.name)] = (body,)
    return out


def _in_class(atom: IrCharClass, text: str) -> bool:
    """Whether a one-character string is a MEMBER of this character class."""
    if len(text) != 1:
        return False
    point = ord(text)
    for element in atom:
        if isinstance(element, IrRange) and _in_range(element, point):
            return True
        if isinstance(element, IrChr) and int(element) == point:
            return True
    return False


def _in_range(span: IrRange, point: int) -> bool:
    """Whether one code point falls inside an inclusive range.

    An open upper bound is `IrNone` on the record, so the bound is read only
    when it is an integer — an open range admits everything above its low end.
    """
    low, high = span[0], span[1]
    if not isinstance(low, int) or point < int(low):
        return False
    return not isinstance(high, int) or point <= int(high)


def _matches(item: IrSelf, kid: IrSelf) -> bool:
    """Whether one normalized grammar item admits one derivation kid."""
    if not isinstance(item, IrItem):
        return False
    atom = item[0]
    if isinstance(atom, IrRuleRef):
        if isinstance(kid, PayloadLeaf):
            return True
        return isinstance(kid, ParseTree) and str(kid.symbol) == str(atom)
    if isinstance(atom, IrLiteral):
        return isinstance(kid, IrLiteral) and str(kid) == str(atom)
    if isinstance(atom, IrCharClass):
        return isinstance(kid, IrLiteral) and _in_class(atom, str(kid))
    return False


def _arm_admits(arm: IrSequence, kids: tuple[IrSelf, ...]) -> bool:
    """Whether one arm's items line up one-to-one with a node's kids."""
    items = tuple(part for part in arm if isinstance(part, IrItem))
    if len(items) != len(kids):
        return False
    return all(_matches(item, kid) for item, kid in zip(items, kids))


def valid_derivation(tree: ParseTree, ast: IrAst) -> str:
    """The first node that instantiates no arm, or the empty string.

    A structural oracle over the normalized grammar and the tree only, never
    the chart the tree came from. A ``PayloadLeaf`` satisfies any rule
    reference by design — a delegated interior is opaque to the outer grammar —
    and that is the one place this oracle is deliberately weak.
    """
    arms = _arms(ast)
    stack: list[ParseTree] = [tree]
    while stack:
        node = stack.pop()
        name = str(node.symbol)
        kids = tuple(node.kids)
        options = arms.get(name)
        if options is None:
            return f"{name}: no such rule"
        if not any(_arm_admits(arm, kids) for arm in options):
            return f"{name}: no arm admits {len(kids)} kids"
        stack.extend(kid for kid in kids if isinstance(kid, ParseTree))
    return ""


def difference_count(first: ParseTree, other: ParseTree) -> int:
    """How many addressed positions two derivations actually disagree at.

    Structural equality short-circuits, so a path-copied node that came out
    equal is not counted — otherwise the splice's own spine would read as a
    difference at every level.
    """
    stack: list[tuple[IrSelf, IrSelf]] = [(first, other)]
    differences = 0
    while stack:
        left, right = stack.pop()
        if left is right or left == right:
            continue
        if not isinstance(left, ParseTree) or not isinstance(right, ParseTree):
            differences += 1
            continue
        if left.symbol != right.symbol or len(left.kids) != len(right.kids):
            differences += 1
            continue
        stack.extend(zip(left.kids, right.kids))
    return differences


# ── the witnesses ─────────────────────────────────────────────────────────


UPSTREAM_CARRIER = 'root ::= x\nx ::= a\na ::= b | "s"\nb ::= a | c\nc ::= x\n'
"""A component whose carrier closure reaches a node OFF the growing cycle.

``x`` is in `cyclic_meaning._carriers`' upward closure (``x -> a`` carries) but
every path back to it runs through ``c``, whose operation is constant. The
first-carrier-plus-simple-cycle constructor refused this grammar outright; it
is retained as the regression witness for both fixes.
"""

SIDE_CYCLE = 'root ::= x\nx ::= y | "s"\ny ::= x | z\nz ::= y\n'
"""A component whose only ``grow`` edge sits on a side cycle."""


class Case(NamedTuple):
    """One infinite-component witness and what the pair must satisfy."""

    name: str
    grammar: str
    text: str
    policies: dict[str, str]
    oracle_ceiling: int


CASES = (
    Case("unary-unit-cycle", cyclic.UNIT, "x", {}, 5),
    Case("two-key-multi-node-cycle", cyclic.TWO_KEY, "x", {}, 4),
    Case("sibling-accepting-roots", cyclic.SIBLING_CYCLE, "x", {}, 4),
    Case(
        "upstream-carrier-off-cycle",
        UPSTREAM_CARRIER,
        "s",
        {"x": "pass", "a": "pass", "c": "drop"},
        4,
    ),
    Case(
        "grow-edge-on-side-cycle",
        SIDE_CYCLE,
        "s",
        {"root": "pass", "x": "pass", "y": "pass"},
        4,
    ),
)

DECLINED = (
    Case("dropping-root-opaque", cyclic.UNIT, "x", {"root": "drop"}, 5),
    Case("identity-cycle-bounded", cyclic.UNIT, "x", {"a": "pass", "b": "pass"}, 5),
    Case("acyclic-twin", cyclic.ACYCLIC_TWIN, "x", {"root": "atmost1"}, 5),
)
"""Charts that classify but for which no pair is requested — the boundary."""


def _kernel(grammar: str, text: str) -> tuple[Kernel, int]:
    """One finished real kernel and its requested accepting handle."""
    kernel = Kernel(cyclic.tables_for(grammar, len(text)), text, True).run()
    if accept_item(kernel) < 0:
        raise PairRefusal("resolver pair: the witness did not parse")
    return kernel, harness.accept_handle(kernel)


def prove_case(case: Case) -> None:
    """Construct, validate and differential one infinite-component pair."""
    kernel, root = _kernel(case.grammar, case.text)
    engine = FastTree(kernel, {}).build(root)
    assert isinstance(engine, ParseTree)
    started = time.process_time()
    pair = construct_pair(kernel, root, case.policies, {})
    elapsed = time.process_time() - started
    ast = normalize(canonical_grammar(case.grammar, GBNF_FLAVOUR))
    assert pair.first == engine, case.name
    assert yield_text(pair.first) == case.text, case.name
    assert yield_text(pair.other) == case.text, case.name
    assert valid_derivation(pair.first, ast) == "", case.name
    assert valid_derivation(pair.other, ast) == "", case.name
    assert pair.first_meaning != pair.other_meaning, case.name
    assert pair.baseline_occurrences >= 1, (case.name, pair.baseline_occurrences)
    span = (0, len(case.text))
    other_occurrences = len(occurrences_of(pair.other, IrRuleRef(pair.carrier), span))
    differences = difference_count(pair.first, pair.other)
    oracle = cyclic.bounded_depth_meanings(
        kernel, root, case.policies, {}, {}, case.oracle_ceiling
    )
    assert pair.first_meaning in oracle.meanings, (case.name, pair.first_meaning)
    assert pair.other_meaning in oracle.meanings, (case.name, pair.other_meaning)
    repeat = construct_pair(*_kernel(case.grammar, case.text), case.policies, {})
    assert repeat.walk == pair.walk and repeat.path == pair.path, case.name
    print(
        "pair",
        case.name,
        f"carrier={pair.carrier}",
        f"carriers_tried={pair.carriers_tried}",
        f"walk_edges={len(pair.walk)}",
        f"walk={[_edge_label(kernel, e) for e in pair.walk]}",
        f"occurrence_path={list(pair.path)}",
        f"baseline_occurrences_of_rule_and_span={pair.baseline_occurrences}",
        f"spliced_occurrences_of_rule_and_span={other_occurrences}",
        "the addressed path, not rule/span uniqueness, identifies the splice",
        f"first_is_engine_derivation={pair.first == engine}",
        f"changed_positions={differences}",
        f"meanings_differ={pair.first_meaning != pair.other_meaning}",
        f"both_in_oracle=True oracle_set={len(oracle.meanings)}",
        f"deterministic_repeat={repeat.walk == pair.walk}",
        f"cpu={elapsed:.6f}",
        sep="\t",
    )


def _edge_label(kernel: Kernel, edge: cyclic.Edge) -> str:
    """One traversal edge as ``parent -> child @ slot`` for the printed record."""
    parent = harness._name(kernel, edge.parent)
    return f"{parent}->{harness._name(kernel, edge.child)}@{edge.slot}"


def prove_declines() -> None:
    """Charts with no infinite component refuse to produce a pair, by name."""
    for case in DECLINED:
        kernel, root = _kernel(case.grammar, case.text)
        try:
            construct_pair(kernel, root, case.policies, {})
        except PairRefusal as error:
            message = str(error)
        else:
            raise AssertionError(f"{case.name}: a pair was constructed anyway")
        outcome = cyclic.exact_meanings(
            kernel, root, case.policies, {}, {}, cyclic.Metrics()
        )
        assert not outcome.differs, case.name
        print(
            "decline",
            case.name,
            f"classification={outcome.kind}",
            f"root_meanings={len(outcome.meanings)}",
            f"refusal={message.split(';')[0]}",
            sep="\t",
        )


def prove_refusal_boundary() -> None:
    """The construction's OWN refusals, exercised directly.

    The three :data:`DECLINED` rows all stop at :func:`certify`. These are the
    others — a carrier with no growing closed walk, and a rule/span the
    accepting derivation does not hold. The first is exactly what
    :data:`UPSTREAM_CARRIER` produced before the walk fix, so both are
    reachable and both get a witness rather than a claim. The third,
    equal-complete-meanings, has no witness among these grammars and is
    recorded as an open obligation instead of manufactured.
    """
    kernel, root = _kernel(cyclic.UNIT, "x")
    certificate = certify(kernel, root, {}, program_of(kernel, {}))
    carrying = internal_carrying(
        certificate.chart, certificate.classes, certificate.component
    )
    identity_only = cyclic.Classes(
        {edge: cyclic.IDENT for edge in carrying},
        certificate.classes.visible,
        certificate.classes.injective,
    )
    try:
        growing_walk(carrying, sorted(certificate.carriers)[0], identity_only)
    except PairRefusal as error:
        walk_refusal = str(error)
    else:
        raise AssertionError("a grow-free edge set produced a walk")
    outer = FastTree(kernel, {}).build(root)
    assert isinstance(outer, ParseTree)
    try:
        locate_span(outer, IrRuleRef("nowhere"), (0, 1))
    except PairRefusal as error:
        locate_refusal = str(error)
    else:
        raise AssertionError("an absent rule was located anyway")
    print(
        "refusal-boundary",
        f"no_growing_walk={walk_refusal}",
        f"no_occurrence={locate_refusal}",
        "third refusal — equal complete meanings after the splice — is"
        " checked in construct_pair and has no witness among these grammars;"
        " it is an open obligation, not a proved-empty class",
        sep="\t",
    )


def prove_nested_island_pair() -> None:
    """A growing component ABOVE a delegated island still yields a pair."""
    text = "xy"
    island = cyclic.tables_for(harness.ISLAND, len(text))
    outer = cyclic.tables_for(cyclic.ISLAND_CYCLE, len(text))
    run = harness.outer_run(outer, island, text, "t", {}, harness.Counters())
    pair = construct_pair(run.kernel, run.root, {}, run.occurrences)
    ast = normalize(canonical_grammar(cyclic.ISLAND_CYCLE, GBNF_FLAVOUR))
    assert yield_text(pair.first) == text
    assert yield_text(pair.other) == text
    assert valid_derivation(pair.first, ast) == ""
    assert valid_derivation(pair.other, ast) == ""
    assert pair.first_meaning != pair.other_meaning
    assert pair.baseline_occurrences >= 1
    print(
        "pair",
        "nested-island-source",
        f"carrier={pair.carrier}",
        f"walk_edges={len(pair.walk)}",
        f"delegated_leaves={len(run.occurrences)}",
        f"occurrence_path={list(pair.path)}",
        f"baseline_occurrences_of_rule_and_span={pair.baseline_occurrences}",
        f"changed_positions={difference_count(pair.first, pair.other)}",
        f"meanings_differ={pair.first_meaning != pair.other_meaning}",
        sep="\t",
    )


def prove_deep_pair() -> None:
    """A document-deep derivation splices without the C stack."""
    for pad in (2_000, 8_000):
        text = "x" + "a" * pad
        kernel, root = _kernel(cyclic.DEEP_CYCLE, text)
        started = time.process_time()
        pair = construct_pair(kernel, root, {}, {})
        elapsed = time.process_time() - started
        ast = normalize(canonical_grammar(cyclic.DEEP_CYCLE, GBNF_FLAVOUR))
        assert yield_text(pair.first) == text
        assert yield_text(pair.other) == text
        assert valid_derivation(pair.first, ast) == ""
        assert valid_derivation(pair.other, ast) == ""
        assert pair.first_meaning != pair.other_meaning
        assert pair.baseline_occurrences >= 1
        print(
            "pair",
            "deep-stack-safe",
            f"chars={len(text)}",
            f"carrier={pair.carrier}",
            f"walk_edges={len(pair.walk)}",
            f"occurrence_path={list(pair.path)}",
            f"changed_positions={difference_count(pair.first, pair.other)}",
            f"meanings_differ={pair.first_meaning != pair.other_meaning}",
            f"cpu={elapsed:.6f}",
            sep="\t",
        )


def main() -> None:
    """Build a pair for every infinite witness; state the refusal boundary."""
    for case in CASES:
        prove_case(case)
    prove_nested_island_pair()
    prove_deep_pair()
    prove_declines()
    prove_refusal_boundary()
    print(
        "invariant",
        "an infinite equal-span component yields a complete pair whose FIRST"
        " element is the derivation the parse produced and whose second is that"
        " derivation with ONE closed carrying walk spliced at ONE addressed"
        " occurrence; every carrier is tried, and the walk is two shortest"
        " paths plus one grow edge, so the construction costs O(E x (V + E))"
        " and terminates structurally with no lap count, depth ladder or"
        " bounded search; a component that classifies bounded, opaque or"
        " acyclic carries no second requested-root meaning and is refused a"
        " pair by name, and the constructor's own two refusals have their own"
        " witnesses",
        sep="\t",
    )


if __name__ == "__main__":
    main()
