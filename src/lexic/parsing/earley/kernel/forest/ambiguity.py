"""Does this span mean more than one thing? — the forest's own answer.

Ambiguity is a property of the FOREST, and the forest already records it: a key
packing more than one family IS an ambiguity point (Scott 2008). So the question
is answered by a walk, not by enumerating derivations and hoping the interesting
one comes early.

What counts as an ambiguity is a question about VALUES, not about derivations. A
grammar routinely derives one text several ways without meaning anything by it —
an inline group carves a digit two ways and folds the same both times, and two
adjacent nullable slots split a gap two ways to the same end. Refusing those
refuses valid input for a difference no consumer can observe.

Shared by both consumers that must answer it — the island sub-parse and the
reduce path — so that "two derivations, one meaning" is decided once and the
same way, whichever engine is asking.
"""

from __future__ import annotations

from collections.abc import Callable
from operator import ne
from typing import TYPE_CHECKING

from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.readout import accept_items
from lexic.parsing.earley.kernel.tables.splits import is_arm_choice

if TYPE_CHECKING:  # `kernel` is what hands us a finished parse to read
    from lexic.parsing.earley.kernel.loop.kernel import Kernel

__all__ = ["ambiguity_points", "means_two_things", "same_value"]


def ambiguity_points(kernel: Kernel, root: int) -> list[int]:
    """Every key reachable from ``root`` that packs more than one family.

    :param kernel: The finished kernel whose links to walk.
    :param root: The packed accepting handle.
    :returns: The ambiguity points, ascending. Empty means the span derives
        exactly one way — proven, not sampled.
    """
    bits, mask = kernel.tables.packing.bits, kernel.tables.packing.mask
    codes, links = kernel.tables.codes, kernel.st.links
    found: set[int] = set()
    seen: set[int] = set()
    stack = [root]
    while stack:
        handle = stack.pop()
        if handle in seen:
            continue
        seen.add(handle)
        item = handle >> bits
        if (item >> bits) == codes.arm_base[codes.code_arm[item >> bits]]:
            continue
        bucket = links.get(handle)
        if bucket is None:
            continue
        if len(bucket) > 1:
            found.add(handle)
        stack.extend(_reachable(bucket, bits, mask))
    return sorted(found)


def _reachable(bucket: list, bits: int, mask: int) -> list[int]:
    """The handles a packed family bucket leads to — predecessors and kids.

    Every family, not merely the first: a walk down one spine finds only the
    ambiguity points ON that spine.
    """
    out: list[int] = []
    for pitem, pend, child in bucket:
        out.append((pitem << bits) | pend)
        if isinstance(child, int) and not isinstance(child, bool):
            out.append(((child >> bits) << bits) | (child & mask))
    return out


def _sibling_roots(kernel: Kernel, handle: int) -> list[int]:
    """The OTHER whole-input completions of the start symbol, if any.

    A many-production root is not an ambiguity point in the link table: the
    sibling productions live in other accepting ITEMS, which a walk down from
    one of them never reaches. `s ::= s s | "a"` over `"aaa"` is exactly that
    shape, and reading only the links calls it unambiguous.
    """
    bits, mask = kernel.tables.packing.bits, kernel.tables.packing.mask
    if (handle & mask) != len(kernel.text):
        return []
    return [
        (item << bits) | len(kernel.text)
        for item in accept_items(kernel)
        if ((item << bits) | len(kernel.text)) != handle
    ]


def same_value(one: object, other: object) -> bool:
    """Do two built values differ in anything a consumer could observe?

    Type-aware and structural, because bare ``==`` answers the wrong question in
    both directions. It calls two values equal when one is ``IrStr("a")`` and the
    other bare ``"a"`` — the IR wraps ``str`` and ``int``, so a leaf and its text
    compare equal while a consumer reading the field sees two different things.
    And it calls them different for a float NaN, which is never equal to itself,
    or for any authored class that never defined ``__eq__``, since two
    derivations always build two objects.

    A type that declined to define equality has declined to answer, and the
    conservative reading of "cannot tell" is no observable difference, hence no
    refusal.
    """
    if type(one) is not type(other):
        return False
    if isinstance(one, (tuple, list)) and isinstance(other, (tuple, list)):
        return len(one) == len(other) and all(map(same_value, one, other))
    if isinstance(one, dict) and isinstance(other, dict):
        return one.keys() == other.keys() and all(
            same_value(one[k], other[k]) for k in one
        )
    if type(one).__eq__ is object.__eq__:
        return True
    # `x != x` is true only of a value that is not equal to itself — NaN.
    # Spelled through `operator` because it is a deliberate self-comparison.
    return bool(one == other) or (ne(one, one) and ne(other, other))


def means_two_things(
    kernel: Kernel,
    handle: int,
    build: Callable[[ParseTree], object],
    first: ParseTree,
) -> bool:
    """Does any other derivation of ``handle`` build a different value?

    Flips one ambiguity point at a time rather than trying every combination: a
    fold is compositional, so if no single alternative changes the value, no
    combination of them does. That is linear in ambiguity points, where
    enumerating derivations is exponential in them.

    A predicate rather than a builder, because "means two things" and "nothing
    built" are different answers and a caller that cannot tell them apart will
    report one as the other.

    :param kernel: The finished kernel.
    :param handle: The packed accepting handle.
    :param build: Turns a derivation into the value it means — a fold's or a
        reducer's ``apply``.
    :param first: The derivation already in hand, to compare the rest against.
    :returns: ``True`` when two derivations build values that differ.
    """
    base = build(first)
    for alternate in _sibling_roots(kernel, handle):
        other = FastTree(kernel, {}).build(alternate)
        if isinstance(other, ParseTree) and not same_value(base, build(other)):
            return True
    bits = kernel.tables.packing.bits
    for key in ambiguity_points(kernel, handle):
        bucket = kernel.st.links[key]
        # A SPLIT has a defined answer — the first slot owns the text — so it is
        # not an ambiguity and must not be refused or fallen back for. Only a
        # choice between different ARMS is a question the grammar left open.
        if not is_arm_choice(bucket, bits):
            continue
        for index in range(1, len(bucket)):
            other = FastTree(kernel, {key: index}).build(handle)
            if isinstance(other, ParseTree) and not same_value(base, build(other)):
                return True
    return False
