"""Which slot owns the text — resolving a binarised chain from the left.

Where two nullable slots sit adjacent, the characters between them can go to
either and the grammar has not said which. Both engines must answer the same
way, so the answer is defined here: the FIRST slot takes as much as it can.

Stating that on the links is not obvious. A completed handle's chain is
binarised and indexed by PREDECESSOR, so it reads right to left, and the top
key's families express the RIGHTMOST split — which is why picking the family
with the largest predecessor end resolves the wrong end of the chain and tops
out well short. The vector ``s₀ ≤ s₁ ≤ … ≤ sₙ`` has to be maximised from ``s₁``,
so the chain is read twice: descend to dot 0 collecting one level per dot
position, prune the levels to keys that still reach the bottom, then choose
bottom-up, where the deepest level's end IS ``s₁``.

**Only a split is ours to answer.** Families naming the same child arm over
different spans are one production carved two ways — the grammar has not said,
so this does. Families naming DIFFERENT arms are a structural ambiguity the
grammar said two ways, and a preference about lengths has no standing over it;
those keep the existing selection and stay the ambiguity check's business.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:  # `atoms` imports this module, so the link type flows one way
    from lexic.parsing.earley.kernel.tables.atoms import KLink


class ChainSpec(NamedTuple):
    """The table constants a chain walk is cut against.

    :ivar base: The arm's dot-0 code — every descent stops here.
    :ivar bits: The tables' packing tier.
    :ivar code_choice: Completed code → authored choice identity.
    """

    base: int
    bits: int
    code_choice: tuple[int, ...]


_Level = dict[int, list[tuple[int, int, "KLink"]]]
"""One dot position: key → ``(predecessor_key, family_index, link)`` edges."""


def leftmost_chain(
    links: dict[int, list[KLink]],
    handle: int,
    spec: ChainSpec,
    choices: dict[int, int],
) -> list[KLink] | None:
    """The chain whose split vector is lexicographically maximal from the left.

    :param links: The parse's SPPF family table.
    :param handle: The packed ``(item << bits) | end`` to resolve.
    :param spec: The arm base, packing tier and choice table to cut against.
    :param choices: Keys pinned to one family; an entry overrides the policy at
        that key, which is how the ambiguity check flips a single point. A pin
        is CONSUMED at its first use (the map is mutated), so on a cyclic chart
        it names the one-lap unroll rather than a non-terminating constraint.
    :returns: The chain's links in source order, or ``None`` when a key is
        missing or a level has no surviving edge.
    """
    levels = _descend(links, handle, spec, choices)
    if levels is None:
        return None
    return _choose(levels)


def spec_for(codes, bits: int, code_choice: tuple[int, ...], key: int) -> ChainSpec:
    """The chain constants for ``key``'s own arm.

    Every family at a key shares that key's item, so its predecessors share an
    item too, and one spec cuts the key, its families and their chains alike.

    :param codes: The compiled code tables (``arm_base``/``code_arm``).
    :param bits: The tables' packing tier.
    :param code_choice: Completed code → authored choice identity.
    :param key: The packed ``(item << bits) | end`` being read.
    """
    return ChainSpec(
        codes.arm_base[codes.code_arm[key >> bits >> bits]], bits, code_choice
    )


def canonical_indices(
    links: dict[int, list[KLink]], bucket: list[KLink], spec: ChainSpec
) -> list[int]:
    """One family index per ARM — that arm's maximum, in arm-first-seen order.

    **What a consumer of an ambiguous key may be shown.** Families naming one
    arm over different spans are that arm carved two ways, and the split rule
    has already said which carving the arm HAS. A reader offered the other one
    is offered a derivation this engine would never produce — which is how a
    span comes to refuse over a carving already rejected, its real choice
    between ARMS never reached.

    So every reader of a multi-arm key sees exactly one family per arm. The
    order is the order the arms first appear, so the default reading stays the
    first arm the chart recorded.

    :param links: The parse's SPPF family table.
    :param bucket: The key's families.
    :param spec: The chain constants for that key.
    :returns: Indices into ``bucket``, one per arm, ascending.
    """
    best: dict[object, int] = {}
    for index, link in enumerate(bucket):
        arm = arm_of(link[2], spec.bits, spec.code_choice)
        held = best.get(arm)
        if held is None or dominant(links, bucket[held], link, spec) is link:
            best[arm] = index
    return sorted(best.values())


def dominant(
    links: dict[int, list[KLink]],
    first: KLink,
    second: KLink,
    spec: ChainSpec,
) -> KLink:
    """Which of two same-arm families at ONE key the split rule keeps.

    The pairwise form of the rule :func:`leftmost_chain` reads off a whole
    chain, for a caller holding two candidates rather than a level DAG: every
    family at a key shares that key's item, so two of them differ only in where
    the predecessor ends, and choosing between them is choosing between their
    predecessors' chains.

    **Exact on any forest.** Each predecessor's vector is read by
    :func:`leftmost_chain` from that predecessor as its own handle — the rule's
    own reading, whatever the buckets under it hold. A cheaper walk that
    descended both chains through family 0 would answer identically only where
    every key it stepped through held ONE family; on a forest that keeps every
    derivation, a predecessor's first-recorded family is not the one the reader
    descends into, and such a walk compares two chart-order chains and can
    crown the wrong carving.

    A dead chain loses to a live one; an exact tie goes to the larger
    predecessor key, the tie :func:`_choose` takes by maximising the key.

    :param links: The parse's SPPF family table.
    :param first: The family in hand.
    :param second: The family contesting it.
    :param spec: The chain constants for the key they both sit at.
    :returns: ``first`` or ``second`` — never a new object.
    """
    bits = spec.bits
    mask = (1 << bits) - 1
    a = (first[0] << bits) | first[1]
    b = (second[0] << bits) | second[1]
    if a == b:
        return first
    va = _vector(links, a, spec, mask)
    vb = _vector(links, b, spec, mask)
    if va is None or vb is None:
        if va is not None:
            return first
        if vb is not None:
            return second
    elif va != vb:
        return first if va > vb else second
    return first if a >= b else second


def _vector(
    links: dict[int, list[KLink]], key: int, spec: ChainSpec, mask: int
) -> tuple[int, ...] | None:
    """``V(key)`` — its chain's boundaries from dot 1 up, deepest first.

    Deepest first because the vector is maximised from the LEFT, so ordinary
    tuple comparison IS the rule. ``None`` when the chain does not reach the
    bottom: a family that derives nothing cannot be the answer.
    """
    if key >> spec.bits >> spec.bits == spec.base:
        return (key & mask,)
    chain = leftmost_chain(links, key, spec, {})
    if chain is None:
        return None
    return tuple(link[1] for link in chain[1:]) + (key & mask,)


def _descend(
    links: dict[int, list[KLink]],
    handle: int,
    spec: ChainSpec,
    choices: dict[int, int],
) -> list[_Level] | None:
    """The level DAG from ``handle`` down to dot 0, one level per dot position."""
    levels: list[_Level] = []
    current = [handle]
    while (current[0] >> spec.bits >> spec.bits) != spec.base:
        level: _Level = {}
        below: dict[int, None] = {}
        for key in current:
            edges = _edges_at(links, key, spec, choices)
            if edges is None:
                return None
            for predecessor, _index, _link in edges:
                below[predecessor] = None
            level[key] = edges
        levels.append(level)
        current = list(below)
    return levels


def _edges_at(
    links: dict[int, list[KLink]],
    key: int,
    spec: ChainSpec,
    choices: dict[int, int],
) -> list[tuple[int, int, KLink]] | None:
    """One key's outgoing edges, or ``None`` when it is missing or dead."""
    bucket = links.get(key)
    if bucket is None:
        return None
    # A pin is CONSUMED at its first use: on a cyclic chart the pinned family
    # leads back to its own key, and a pin that re-applied there would name no
    # finite derivation at all. Consumed, it names the one-lap unroll — flip
    # the point once, default policy after.
    edges = [
        ((link[0] << spec.bits) | link[1], index, link)
        for index, link in _candidates(links, bucket, choices.pop(key, None), spec)
    ]
    return edges or None


def is_arm_choice(bucket: list[KLink], bits: int, code_choice: tuple[int, ...]) -> bool:
    """Do this key's families name more than one child ARM?

    The line between the two classes of ambiguity, and the same test the split
    policy uses to decide what it may answer. Families naming ONE arm over
    different spans are a split — the grammar has not said which slot owns the
    text, so the policy does, and a decided split is not an ambiguity. Families
    naming DIFFERENT arms are a structural choice the grammar stated two ways,
    which nothing about lengths can settle: that is what the refusal is for.
    """
    return len({arm_of(link[2], bits, code_choice) for link in bucket}) > 1


def _candidates(
    links: dict[int, list[KLink]],
    bucket: list[KLink],
    pinned: int | None,
    spec: ChainSpec,
) -> list[tuple[int, KLink]]:
    """The families this policy may choose between at one key.

    A pinned key contributes only what it was pinned to. Families naming more
    than one child arm are a structural choice, not a split, so the policy does
    not choose between them — but WHICH carving stands for the default arm is
    still a split, and :func:`canonical_indices` answers it, so what is read is
    that arm's own carving rather than the first one the chart recorded.
    """
    if pinned is not None:
        return [(pinned, bucket[pinned])]
    if is_arm_choice(bucket, spec.bits, spec.code_choice):
        index = canonical_indices(links, bucket, spec)[0]
        return [(index, bucket[index])]
    return list(enumerate(bucket))


def arm_of(child: object, bits: int, code_choice: tuple[int, ...]) -> object:
    """A family child's authored choice — scans and payloads are their own.

    The one reading of what arm a family names: :func:`is_arm_choice`, the
    canonical selection and every consumer that asks the question read it here.
    """
    if isinstance(child, int) and not isinstance(child, bool):
        return code_choice[child >> bits >> bits]
    return type(child)


def _choose(levels: list[_Level]) -> list[KLink]:
    """Choose bottom-up: the deepest level's end is ``s₁``, then feed it upward.

    Keys within one level share item code and origin, so the packed key is
    monotone in the end column and ``max`` on the key IS ``max`` on the end.
    """
    if not levels:
        return []
    _prune(levels)
    # Every dot-0 predecessor is the same key — the origin is chain-invariant.
    below = max(pkey for edges in levels[-1].values() for pkey, _, _ in edges)
    chain: list[KLink] = []
    for level in reversed(levels):  # deepest first, so this is already source order
        key = max(
            k for k, edges in level.items() if any(p == below for p, _, _ in edges)
        )
        chain.append(next(link for p, _, link in level[key] if p == below))
        below = key
    return chain


def _prune(levels: list[_Level]) -> None:
    """Drop keys that no longer reach the bottom — a dead branch of the DAG."""
    for depth in range(len(levels) - 2, -1, -1):
        alive = set(levels[depth + 1])
        for key, edges in list(levels[depth].items()):
            kept = [edge for edge in edges if edge[0] in alive]
            if kept:
                levels[depth][key] = kept
            else:
                del levels[depth][key]
