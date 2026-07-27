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

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # `atoms` imports this module, so the link type flows one way
    from lexic.parsing.earley.kernel.tables.atoms import KLink

    _Level = dict[int, list[tuple[int, int, KLink]]]
    """One dot position: key → ``(predecessor_key, family_index, link)`` edges."""


def leftmost_chain(
    links: dict[int, list[KLink]],
    handle: int,
    base: int,
    bits: int,
    choices: dict[int, int],
) -> list[KLink] | None:
    """The chain whose split vector is lexicographically maximal from the left.

    :param links: The parse's SPPF family table.
    :param handle: The packed ``(item << bits) | end`` to resolve.
    :param base: The arm's dot-0 code — the descent stops here.
    :param bits: The tables' packing tier.
    :param choices: Keys pinned to one family; an entry overrides the policy at
        that key, which is how the ambiguity check flips a single point.
    :returns: The chain's links in source order, or ``None`` when a key is
        missing or a level has no surviving edge.
    """
    levels = _descend(links, handle, base, bits, choices)
    if levels is None:
        return None
    return _choose(levels)


def _descend(
    links: dict[int, list[KLink]],
    handle: int,
    base: int,
    bits: int,
    choices: dict[int, int],
) -> list[_Level] | None:
    """The level DAG from ``handle`` down to dot 0, one level per dot position."""
    levels: list[_Level] = []
    current = [handle]
    while (current[0] >> bits >> bits) != base:
        level: _Level = {}
        below: dict[int, None] = {}
        for key in current:
            bucket = links.get(key)
            if bucket is None:
                return None
            edges = []
            for index, link in _candidates(bucket, choices.get(key), bits):
                predecessor = (link[0] << bits) | link[1]
                edges.append((predecessor, index, link))
                below[predecessor] = None
            if not edges:
                return None
            level[key] = edges
        levels.append(level)
        current = list(below)
    return levels


def _candidates(
    bucket: list[KLink], pinned: int | None, bits: int
) -> list[tuple[int, KLink]]:
    """The families this policy may choose between at one key.

    A pinned key contributes only what it was pinned to. Families naming more
    than one child arm are a structural choice, not a split, and keep today's
    selection.
    """
    if pinned is not None:
        return [(pinned, bucket[pinned])]
    if len({_arm_of(link[2], bits) for link in bucket}) > 1:
        return [(0, bucket[0])]
    return list(enumerate(bucket))


def _arm_of(child: object, bits: int) -> object:
    """A family child's arm code — a scanned char and a payload are their own."""
    if isinstance(child, int) and not isinstance(child, bool):
        return child >> bits >> bits
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
