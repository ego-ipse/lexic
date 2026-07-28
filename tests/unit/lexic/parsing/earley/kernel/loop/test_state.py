"""Tests for lexic.parsing.earley.kernel.loop.state — the per-parse index state.

``KernelState`` is the kernel's mutable-chart exception: five position-indexed
column containers plus two parse-global SPPF link tables. ``file_item`` is the
one operation it owns — filing a just-inserted item under the symbol its dot
faces, into ``waiting`` (a rule) or ``scannable`` (an atom).
"""

from __future__ import annotations

from lexic.parsing.earley.kernel.loop.state import KernelState


def test_seeds_one_container_per_column() -> None:
    """Each per-column index has exactly ``columns`` entries, all empty."""
    st = KernelState(4)
    assert [
        len(x) for x in (st.seen, st.waiting, st.scannable, st.predicted, st.leo)
    ] == [
        4,
        4,
        4,
        4,
        4,
    ]
    assert not any(st.seen) and not any(st.waiting) and not any(st.scannable)
    assert not any(st.predicted) and not any(st.leo)


def test_link_tables_are_parse_global_not_per_column() -> None:
    """``links`` / ``leo_links`` are keyed by packed handle, so one dict each."""
    st = KernelState(4)
    assert not st.links
    assert not st.leo_links


def test_columns_do_not_share_containers() -> None:
    """A write to one column's index is invisible to the others."""
    st = KernelState(3)
    st.seen[1].add(7)
    assert st.seen[0] == set() and st.seen[2] == set()


def test_file_item_positive_symbol_files_into_waiting() -> None:
    """``s > 0`` means the dot faces rule ``s - 1`` — file under ``waiting``."""
    st = KernelState(2)
    st.file_item(0, 42, 3)
    assert st.waiting[0] == {2: [42]}
    assert st.scannable[0] == {}


def test_file_item_negative_symbol_files_into_scannable() -> None:
    """``s < 0`` means the dot faces atom ``-s - 1`` — file under ``scannable``."""
    st = KernelState(2)
    st.file_item(1, 42, -3)
    assert st.scannable[1] == {2: [42]}
    assert st.waiting[1] == {}


def test_file_item_appends_to_an_existing_bucket_in_order() -> None:
    """A second item under the same symbol joins the bucket, keeping chart order."""
    st = KernelState(1)
    st.file_item(0, 10, 1)
    st.file_item(0, 20, 1)
    assert st.waiting[0] == {0: [10, 20]}


def test_file_item_keeps_symbols_in_separate_buckets() -> None:
    """Different awaited symbols never share a bucket."""
    st = KernelState(1)
    st.file_item(0, 10, 1)
    st.file_item(0, 20, 2)
    assert st.waiting[0] == {0: [10], 1: [20]}
