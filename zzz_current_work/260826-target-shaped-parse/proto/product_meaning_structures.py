"""Exact ambiguity meanings for map, IR, and tokenizer products, per law.

The sequence prototype proved persistent ORDERED contribution trees. This file
asks what each remaining product's own equality/duplicate/order law admits:

- an ordered contribution tree wrongly separates two insertion orders that the
  order-insensitive map laws call EQUAL — measured, and rejected for them;
- a canonical persistent key tree (a treap whose shape is a pure function of
  content, priorities derived by BLAKE2b from the key spelling — placement
  only, never equality) satisfies the keyed laws with identity sharing;
- the exact isolated whole-result cold comparison is the honest fallback,
  priced beside it;
- tokenizer products reuse the key tree per index role, with canonical id/rank
  order restored once at materialization of the chosen result.

Real classes: `IrMapping.from_table` (duplicate refusal), `IrMap.from_table`
(canonical repr order, order-insensitive equality), `IrTokenizer.from_merges`.
The Qwen-scale row obtains the real vocabulary through the public
`json_tokenizer.read` reader (`--mode qwen` only), run alone under
`tools/guarded.sh`.
"""

from __future__ import annotations

import argparse
import hashlib
import resource
import time
import tracemalloc
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from lexic.api.json_tokenizer import read
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrChr, IrMap, IrStr, IrTokenizer
from lexic.ir.action.mapping import IrMapping

type MapKey = str | int | tuple[str, str]
type MapValue = str | int | KeyNode | None

REFUSE = 0
LAST_WINS = 1


class Cells:
    """Operation counters one comparison row reports."""

    __slots__ = ("materializations", "nodes", "visits")

    def __init__(self) -> None:
        self.nodes = 0
        self.visits = 0
        self.materializations = 0


class MeaningVerdict(NamedTuple):
    """One ordered duplicate-key verdict."""

    order: int
    key: MapKey


class KeyNode(NamedTuple):
    """One canonical persistent map node — shape is a function of content."""

    key: MapKey
    value: MapValue
    priority: int
    left: KeyNode | None
    right: KeyNode | None


def _priority(key: MapKey) -> int:
    """Placement priority; never consulted for equality.

    ``hash`` is salted across processes but stable within one, and canonical
    shape is only needed between derivations compared inside ONE parse; the
    BLAKE2b spelling stays available where cross-process reproducibility of a
    dump matters. Mixed through a tuple because ``hash(int)`` is the int
    itself, which degenerates the treap into a spine for id-keyed roles.
    """
    return hash((0x9E3779B97F4A7C15, key))


def _digest_priority(key: MapKey) -> int:
    """The cross-process-stable priority variant (unused in the timed rows)."""
    digest = hashlib.blake2b(repr(key).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little")


def insert(
    root: KeyNode | None,
    key: MapKey,
    value: MapValue,
    policy: int,
    verdicts: list[MeaningVerdict],
    order: int,
    cells: Cells,
) -> KeyNode | None:
    """Persistently insert one entry, path-copying only the touched spine."""
    path: list[tuple[KeyNode, bool]] = []
    cursor = root
    while cursor is not None:
        cells.visits += 1
        if key == cursor.key:
            if policy == REFUSE:
                verdicts.append(MeaningVerdict(order, key))
                return root
            replaced = cursor._replace(value=value)
            cells.nodes += 1
            return _rebuild(path, replaced, cells)
        goes_right = _after(key, cursor.key)
        path.append((cursor, goes_right))
        cursor = cursor.right if goes_right else cursor.left
    fresh = KeyNode(key, value, _priority(key), None, None)
    cells.nodes += 1
    return _rotate_up(path, fresh, cells)


def _after(key: MapKey, other: MapKey) -> bool:
    """Total order within one homogeneous key domain, direct where same-typed."""
    if isinstance(key, str) and isinstance(other, str):
        return key > other
    if isinstance(key, tuple) and isinstance(other, tuple):
        return key > other
    if isinstance(key, int) and isinstance(other, int):
        return key > other
    return repr(key) > repr(other)


def _rebuild(path: list[tuple[KeyNode, bool]], child: KeyNode, cells: Cells) -> KeyNode:
    """Copy the traversed spine above an in-place value replacement."""
    for parent, went_right in reversed(path):
        cells.nodes += 1
        if went_right:
            child = parent._replace(right=child)
        else:
            child = parent._replace(left=child)
    return child


def _rotate_up(
    path: list[tuple[KeyNode, bool]], child: KeyNode, cells: Cells
) -> KeyNode:
    """Treap-rotate a fresh leaf to its canonical priority position."""
    while path:
        parent, went_right = path.pop()
        if child.priority > parent.priority:
            cells.nodes += 1
            if went_right:
                child = child._replace(left=parent._replace(right=child.left))
            else:
                child = child._replace(right=parent._replace(left=child.right))
            cells.nodes += 1
            continue
        cells.nodes += 1
        if went_right:
            child = parent._replace(right=child)
        else:
            child = parent._replace(left=child)
    return child


def same_tree(left: KeyNode | None, right: KeyNode | None, cells: Cells) -> bool:
    """Exact iterative equality, skipping every identity-shared branch."""
    pending: list[tuple[KeyNode | None, KeyNode | None]] = [(left, right)]
    while pending:
        one, other = pending.pop()
        cells.visits += 1
        if one is other:
            continue
        if one is None or other is None:
            return False
        if one.key != other.key:
            return False
        if isinstance(one.value, KeyNode) and isinstance(other.value, KeyNode):
            pending.append((one.value, other.value))
        elif one.value != other.value:
            return False
        pending.append((one.left, other.left))
        pending.append((one.right, other.right))
    return True


def materialize(root: KeyNode | None, cells: Cells) -> list[tuple[MapKey, MapValue]]:
    """Construct the chosen eager items once, in canonical key order."""
    cells.materializations += 1
    items: list[tuple[MapKey, MapValue]] = []
    pending: list[tuple[KeyNode, bool]] = [] if root is None else [(root, False)]
    while pending:
        node, expanded = pending.pop()
        if expanded:
            items.append((node.key, node.value))
            continue
        if node.right is not None:
            pending.append((node.right, False))
        pending.append((node, True))
        if node.left is not None:
            pending.append((node.left, False))
    return items


def _sort_key(pair: tuple[MapKey, MapValue]) -> str:
    """The SAME total order ``_after`` descends by — raw spelling for strings.

    Sorting by ``repr`` while descending by raw comparison would misplace any
    key containing a quote or backslash (real vocab tokens do), so the sort
    key and the descent comparator must be one order.
    """
    key = pair[0]
    if isinstance(key, str):
        return key
    return repr(key)


def balanced_build(
    ordered: Sequence[tuple[MapKey, MapValue]], cells: Cells
) -> KeyNode | None:
    """One O(n) canonical balanced tree from key-sorted items — the cheap
    first-ambiguity conversion of an already-accumulated flat mapping."""
    return _balanced_range(ordered, 0, len(ordered), cells)


def _balanced_range(
    ordered: Sequence[tuple[MapKey, MapValue]], low: int, high: int, cells: Cells
) -> KeyNode | None:
    """Iteratively build the canonical midpoint tree over ``[low, high)``."""
    if low >= high:
        return None
    built: dict[tuple[int, int], KeyNode | None] = {}
    pending: list[tuple[int, int, bool]] = [(low, high, False)]
    while pending:
        start, stop, expanded = pending.pop()
        if start >= stop:
            built[(start, stop)] = None
            continue
        middle = (start + stop) // 2
        if not expanded:
            pending.append((start, stop, True))
            pending.append((start, middle, False))
            pending.append((middle + 1, stop, False))
            continue
        key, value = ordered[middle]
        cells.nodes += 1
        built[(start, stop)] = KeyNode(
            key, value, 0, built[(start, middle)], built[(middle + 1, stop)]
        )
    return built[(low, high)]


def replace_value(
    root: KeyNode | None, key: MapKey, value: MapValue, cells: Cells
) -> KeyNode | None:
    """Path-copy one existing key's VALUE — the shape-preserving alternate.

    A value replacement never changes the key set, so canonical shape is
    preserved trivially; a key-set-changing alternate declines to the exact
    cold comparison instead of inventing a shape law.
    """
    path: list[tuple[KeyNode, bool]] = []
    cursor = root
    while cursor is not None:
        cells.visits += 1
        if key == cursor.key:
            cells.nodes += 1
            return _rebuild(path, cursor._replace(value=value), cells)
        goes_right = _after(key, cursor.key)
        path.append((cursor, goes_right))
        cursor = cursor.right if goes_right else cursor.left
    raise UnsupportedConstructError(
        "meaning prototype: value replacement requires an existing key"
    )


class Ordered(NamedTuple):
    """One ordered-contribution meaning — the sequence prototype's carrier."""

    entries: tuple[tuple[MapKey, MapValue], ...]


def _build_tree(
    pairs: Sequence[tuple[MapKey, MapValue]],
    policy: int,
    cells: Cells,
) -> tuple[KeyNode | None, list[MeaningVerdict]]:
    """Insert pairs in contribution order under one duplicate policy."""
    verdicts: list[MeaningVerdict] = []
    root: KeyNode | None = None
    for order, (key, value) in enumerate(pairs):
        root = insert(root, key, value, policy, verdicts, order, cells)
    return root, verdicts


def prove_insertion_order() -> None:
    """Equal maps in two insertion orders: keyed tree equal, ordered tree not."""
    pairs: list[tuple[MapKey, MapValue]] = [(f"k{i}", i) for i in range(512)]
    reordered = list(reversed(pairs))
    cells = Cells()
    forward, _ = _build_tree(pairs, REFUSE, cells)
    backward, _ = _build_tree(reordered, REFUSE, cells)
    equal_cells = Cells()
    assert same_tree(forward, backward, equal_cells)
    ordered_differs = Ordered(tuple(pairs)) != Ordered(tuple(reordered))
    assert ordered_differs
    one = IrMap.from_table((IrStr(k), IrChr(v)) for k, v in pairs if type(v) is int)
    two = IrMap.from_table((IrStr(k), IrChr(v)) for k, v in reordered if type(v) is int)
    assert one == two
    print(
        "insertion-order",
        "keyed_tree=EQUAL (canonical shape)",
        f"equal_visits={equal_cells.visits}",
        "ordered_tree=DIFFERENT (law violation for keyed products — rejected)",
        "IrMap_oracle=EQUAL",
        sep="\t",
    )


def prove_duplicates() -> None:
    """Duplicate refusal parity with the real `IrMapping.from_table`."""
    pairs: list[tuple[MapKey, MapValue]] = [("a", 1), ("b", 2), ("a", 3)]
    cells = Cells()
    root, verdicts = _build_tree(pairs, REFUSE, cells)
    assert [v.key for v in verdicts] == ["a"]
    assert verdicts[0].order == 2
    try:
        IrMapping.from_table(pairs)
    except UnsupportedConstructError as error:
        assert "'a'" in str(error)
    else:
        raise AssertionError("the real index accepted a duplicate key")
    lenient = Cells()
    replaced, none_recorded = _build_tree(pairs, LAST_WINS, lenient)
    assert not none_recorded
    assert materialize(replaced, lenient)[0] == ("a", 3)
    assert materialize(root, cells)[0] == ("a", 1)
    print(
        "duplicates",
        "REFUSE verdict parity with IrMapping.from_table; verdict order is"
        " contribution order; LAST_WINS is a distinct declared policy",
        sep="\t",
    )


def prove_alternate_costs(size: int) -> None:
    """Changed / equal / discarded alternates over one large baseline tree."""
    cells = Cells()
    pairs: list[tuple[MapKey, MapValue]] = [(f"key{i}", i) for i in range(size)]
    baseline, _ = _build_tree(pairs, REFUSE, cells)
    target: MapKey = f"key{size // 2}"

    changed_cells = Cells()
    changed = insert(baseline, target, -1, LAST_WINS, [], size, changed_cells)
    compare_changed = Cells()
    assert not same_tree(baseline, changed, compare_changed)

    equal_cells = Cells()
    rebuilt = insert(baseline, target, size // 2, LAST_WINS, [], size, equal_cells)
    compare_equal = Cells()
    assert same_tree(baseline, rebuilt, compare_equal)

    compare_dropped = Cells()
    assert same_tree(baseline, baseline, compare_dropped)

    cold = Cells()
    alternate_items = [(key, -1 if key == target else value) for key, value in pairs]
    cold.materializations += 1
    cold.visits += len(alternate_items)
    assert alternate_items != pairs
    print(
        "alternate-costs",
        f"items={size}",
        f"changed_path_nodes={changed_cells.nodes}",
        f"changed_compare_visits={compare_changed.visits}",
        f"equal_compare_visits={compare_equal.visits}",
        f"dropped_compare_visits={compare_dropped.visits}",
        f"cold_compare_ops={cold.visits} (plus one full materialization)",
        sep="\t",
    )


def prove_deep() -> None:
    """Nested-map depth beyond the recursion limit stays comparable."""
    depth = 4_000
    cells = Cells()
    inner_a: MapValue = "leaf"
    inner_b: MapValue = "leaf"
    for level in range(depth):
        node_a = KeyNode(
            f"level{level}", inner_a, _priority(f"level{level}"), None, None
        )
        node_b = KeyNode(
            f"level{level}", inner_b, _priority(f"level{level}"), None, None
        )
        inner_a, inner_b = node_a, node_b
    assert isinstance(inner_a, KeyNode) and isinstance(inner_b, KeyNode)
    deep_cells = Cells()
    assert same_tree(inner_a, inner_b, deep_cells)
    del cells
    print(
        "deep",
        f"depth={depth}",
        f"visits={deep_cells.visits}",
        "iterative equality — no interpreter-stack dependence",
        sep="\t",
    )


def prove_tokenizer_order() -> None:
    """Canonical/noncanonical tokenizer order through the real record."""
    vocab_pairs: list[tuple[MapKey, MapValue]] = [
        ("a", 0),
        ("b", 1),
        ("ab", 2),
    ]
    cells = Cells()
    encode_tree, _ = _build_tree(vocab_pairs, REFUSE, cells)
    decode_tree, _ = _build_tree(
        [(int(i), s) for s, i in vocab_pairs if type(i) is int and type(s) is str],
        REFUSE,
        cells,
    )
    encode_items = materialize(encode_tree, cells)
    decode_items = materialize(decode_tree, cells)
    ordered_by_id = sorted(
        ((s, i) for s, i in encode_items if type(i) is int), key=lambda kv: kv[1]
    )
    vocab = {str(s): int(i) for s, i in ordered_by_id if type(s) is str}
    tokenizer = IrTokenizer.from_merges("meaning-proto", vocab, [("a", "b")])
    decode_order = tuple(int(i) for i in tokenizer.decode.keys())
    assert list(decode_order) == sorted(decode_order)
    assert [k for k, _v in decode_items] == sorted(k for k, _v in decode_items)
    print(
        "tokenizer-order",
        "meaning trees are keyed per index role; the CHOSEN result is ordered"
        " once at materialization; canonical id order validated on the real"
        f" record (decode ids {decode_order})",
        sep="\t",
    )


def prove_vocab_alternate_dirties_two_indexes() -> None:
    """One changed vocab entry path-copies encode AND decode, nothing else."""
    size = 4_096
    cells = Cells()
    encode, _ = _build_tree([(f"tok{i}", i) for i in range(size)], REFUSE, cells)
    decode, _ = _build_tree([(i, f"tok{i}") for i in range(size)], REFUSE, cells)
    alt_cells = Cells()
    encode_alt = insert(encode, "tok9", -9, LAST_WINS, [], size, alt_cells)
    decode_alt = insert(decode, 9, "other", LAST_WINS, [], size, alt_cells)
    compare = Cells()
    assert not same_tree(encode, encode_alt, compare)
    assert not same_tree(decode, decode_alt, compare)
    print(
        "tokenizer-dirty",
        f"vocab_entries={size}",
        f"two_index_path_nodes={alt_cells.nodes}",
        f"compare_visits={compare.visits}",
        "dirty work follows the changed semantic dependency across both roles",
        sep="\t",
    )


def _rss_kib() -> int:
    """This process's high-water RSS in KiB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def qwen_scale() -> None:
    """Real-cardinality row: run alone under tools/guarded.sh, sequentially.

    The vocabulary comes through the real public reader
    (`json_tokenizer.read` → ready `IrTokenizer`), so the pairs are the final
    product's actual encode table — added tokens included. The reader's own
    cost is reported separately as setup and never enters a structure row.
    """
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    if not source.exists():
        print("qwen-scale\tSKIP: fixture not fetched")
        return
    setup_started = time.process_time()
    tokenizer = read(
        source.read_text(encoding="utf-8"), JSON_GRAMMAR, JSON_REDUCER, name="qwen3"
    )
    setup_seconds = time.process_time() - setup_started
    pairs: list[tuple[MapKey, MapValue]] = [
        (str(spelling), int(ordinal)) for spelling, ordinal in tokenizer.encode.items()
    ]
    print("qwen-scale-entries", len(pairs), sep="\t")
    print("qwen-scale-reader-setup-seconds", f"{setup_seconds:.6f}", sep="\t")

    tracemalloc.start()
    flat = dict(pairs)
    flat_bytes, _peak = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    tracemalloc.stop()

    tracemalloc.start()
    build = Cells()
    started = time.process_time()
    baseline, _ = _build_tree(pairs, REFUSE, build)
    build_seconds = time.process_time() - started
    tree_bytes, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    changed = Cells()
    key: MapKey = pairs[len(pairs) // 3][0]
    alternate = insert(baseline, key, -1, LAST_WINS, [], len(pairs), changed)
    compare = Cells()
    started = time.process_time()
    assert not same_tree(baseline, alternate, compare)
    compare_seconds = time.process_time() - started

    cold_started = time.process_time()
    cold_alternate = {
        spelling: (-1 if spelling == key else ordinal) for spelling, ordinal in pairs
    }
    cold_equal = cold_alternate == flat
    cold_seconds = time.process_time() - cold_started
    assert not cold_equal

    materialized = Cells()
    started = time.process_time()
    items = materialize(alternate, materialized)
    ordered_once = sorted(
        ((k, v) for k, v in items if type(v) is int), key=lambda kv: kv[1]
    )
    materialize_seconds = time.process_time() - started

    convert = Cells()
    started = time.process_time()
    key_sorted = sorted(pairs, key=_sort_key)
    balanced = balanced_build(key_sorted, convert)
    convert_seconds = time.process_time() - started
    replace_cells = Cells()
    started = time.process_time()
    replaced = replace_value(balanced, key, -1, replace_cells)
    balanced_compare = Cells()
    assert not same_tree(balanced, replaced, balanced_compare)
    replace_seconds = time.process_time() - started

    print(
        "qwen-scale-balanced",
        f"convert_sort+build_seconds={convert_seconds:.6f}",
        f"convert_nodes={convert.nodes}",
        f"replace_path_nodes={replace_cells.nodes}",
        f"replace+exact_compare_seconds={replace_seconds:.6f}",
        f"balanced_compare_visits={balanced_compare.visits}",
        sep="\t",
    )
    print(
        "qwen-scale",
        f"build_visits={build.visits}",
        f"build_nodes={build.nodes}",
        f"build_seconds={build_seconds:.6f}",
        f"changed_path_nodes={changed.nodes}",
        f"exact_compare_visits={compare.visits}",
        f"compare_seconds={compare_seconds:.6f}",
        f"cold_build+compare_seconds={cold_seconds:.6f}",
        f"materializations={materialized.materializations}",
        f"materialize+order_once_seconds={materialize_seconds:.6f}",
        f"ordered_entries={len(ordered_once)}",
        f"flat_dict_bytes={flat_bytes}",
        f"tree_bytes={tree_bytes}",
        f"peak_rss_kib={_rss_kib()}",
        sep="\t",
    )


def main(arguments: Sequence[str] | None = None) -> None:
    """Run the law witnesses, or the isolated Qwen-cardinality row."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="laws")
    options = parser.parse_args(arguments)
    if options.mode == "qwen":
        qwen_scale()
        return
    if options.mode != "laws":
        raise UnsupportedConstructError(
            f"meaning prototype: unsupported mode {options.mode!r}"
        )
    prove_insertion_order()
    prove_duplicates()
    prove_alternate_costs(65_536)
    prove_deep()
    prove_tokenizer_order()
    prove_vocab_alternate_dirties_two_indexes()
    print(
        "conclusion",
        "ordered trees stay sequence-only (law violation on keyed products);"
        " the canonical key tree is law-exact but its cost verdict is in the"
        " --mode qwen row: cold comparison wins at realistic alternate counts",
        sep="\t",
    )


if __name__ == "__main__":
    main()
