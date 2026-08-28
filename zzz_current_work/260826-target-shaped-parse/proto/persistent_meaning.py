"""Keep alternate root meanings exact without rebuilding unchanged containers."""

from __future__ import annotations

from typing import NamedTuple


class Leaf(NamedTuple):
    """One immutable semantic contribution."""

    value: int


class Branch(NamedTuple):
    """One balanced contribution join with a cached item count."""

    size: int
    left: "Meaning"
    right: "Meaning"


class Dropped(NamedTuple):
    """The shared meaning of a subtree discarded by its parent."""

    marker: int


type Meaning = Leaf | Branch | Dropped

DROP = Dropped(0)
SIZE = 65_536


class Comparison(NamedTuple):
    """One exact equality verdict and the nodes it had to inspect."""

    equal: bool
    visited: int


def _size(meaning: Meaning) -> int:
    """Return the number of semantic leaves under ``meaning``."""
    if isinstance(meaning, Branch):
        return meaning.size
    if isinstance(meaning, Leaf):
        return 1
    return 0


def build(size: int) -> Meaning:
    """Build one balanced persistent sequence of ``size`` integers."""
    level: list[Meaning] = [Leaf(value) for value in range(size)]
    while len(level) > 1:
        joined: list[Meaning] = []
        index = 0
        while index < len(level):
            if index + 1 == len(level):
                joined.append(level[index])
            else:
                left = level[index]
                right = level[index + 1]
                joined.append(Branch(_size(left) + _size(right), left, right))
            index += 2
        level = joined
    return level[0]


def replace(root: Meaning, index: int, value: int) -> Meaning:
    """Replace one leaf by copying only its root path."""
    path: list[tuple[Branch, bool]] = []
    cursor = root
    offset = index
    while isinstance(cursor, Branch):
        left_size = _size(cursor.left)
        goes_right = offset >= left_size
        path.append((cursor, goes_right))
        if goes_right:
            offset -= left_size
            cursor = cursor.right
        else:
            cursor = cursor.left
    if not isinstance(cursor, Leaf) or offset != 0:
        raise IndexError(index)
    rebuilt: Meaning = Leaf(value)
    while path:
        branch, went_right = path.pop()
        if went_right:
            rebuilt = Branch(branch.size, branch.left, rebuilt)
        else:
            rebuilt = Branch(branch.size, rebuilt, branch.right)
    return rebuilt


def same(left: Meaning, right: Meaning) -> Comparison:
    """Compare exactly, skipping every identity-shared subtree."""
    pending = [(left, right)]
    visited = 0
    while pending:
        one, other = pending.pop()
        visited += 1
        if one is other:
            continue
        if isinstance(one, Leaf) and isinstance(other, Leaf):
            if one.value != other.value:
                return Comparison(False, visited)
            continue
        if isinstance(one, Branch) and isinstance(other, Branch):
            if one.size != other.size:
                return Comparison(False, visited)
            pending.append((one.right, other.right))
            pending.append((one.left, other.left))
            continue
        if isinstance(one, Dropped) and isinstance(other, Dropped):
            if one.marker != other.marker:
                return Comparison(False, visited)
            continue
        return Comparison(False, visited)
    return Comparison(True, visited)


def materialize(root: Meaning) -> list[int]:
    """Construct the chosen eager result once, after ambiguity resolution."""
    values: list[int] = []
    pending = [root]
    while pending:
        meaning = pending.pop()
        if isinstance(meaning, Leaf):
            values.append(meaning.value)
        elif isinstance(meaning, Branch):
            pending.append(meaning.right)
            pending.append(meaning.left)
    return values


def main() -> None:
    """Exercise changed, equal, and parent-dropped alternate meanings."""
    baseline = build(SIZE)
    changed = replace(baseline, SIZE // 2, -1)
    unchanged = replace(baseline, SIZE // 2, SIZE // 2)
    different = same(baseline, changed)
    equal = same(baseline, unchanged)
    dropped = same(DROP, DROP)
    result = materialize(changed)
    assert not different.equal
    assert equal.equal
    assert dropped.equal
    assert result[SIZE // 2] == -1
    assert different.visited < 64
    assert equal.visited < 64
    print(
        "persistent",
        f"items={SIZE}",
        f"different_visits={different.visited}",
        f"equal_visits={equal.visited}",
        f"dropped_visits={dropped.visited}",
        "materializations=1",
    )


if __name__ == "__main__":
    main()
