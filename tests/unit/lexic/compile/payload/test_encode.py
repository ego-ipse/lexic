"""Tests for lexic.compile.payload.encode — the projection's lexic side.

The vocabulary round-trip and the tamper matrix live in ``test_project.py``
(against the package's re-exported surface); this file targets ``encode.py``'s
own narrow pieces directly: the ``Payload`` record, the in-place-mutable
sharing rule, and ``project_checked``'s fixpoint gate.
"""

from __future__ import annotations

import pytest

from lexic.compile.payload.encode import (
    EXACT_PLAIN,
    SENTINEL,
    _in_place_mutable,
    project,
    project_checked,
)
from lexic.exceptions import UnsupportedConstructError


def test_payload_symbols_excludes_the_sentinel():
    """``symbols`` is ``types[1:]`` — the sentinel itself never counts as one."""
    payload = project({"a": 1})
    assert payload.types[0] == SENTINEL
    assert payload.symbols == payload.types[1:]


def test_payload_tables_is_the_four_literals_in_reader_order():
    """``tables`` is exactly ``(types, origins, strs, nodes)``."""
    payload = project([1, "x"])
    assert payload.tables == (
        payload.types,
        payload.origins,
        payload.strs,
        payload.nodes,
    )


def test_a_plain_value_names_only_the_sentinel():
    """An exact builtin in ``EXACT_PLAIN`` never mints a symbol of its own."""
    payload = project(42)
    assert payload.symbols == ()
    assert payload.types == (SENTINEL,)


def test_exact_plain_covers_the_documented_builtins():
    """The exact-type builtin set matches what the docstring promises."""
    assert EXACT_PLAIN == {
        str,
        int,
        bool,
        tuple,
        list,
        dict,
        float,
        bytes,
        set,
        frozenset,
        type(None),
    }


def test_two_equal_lists_at_distinct_identities_do_not_share_a_record():
    """Mutable containers are shared by identity only — two equal-but-distinct
    lists must not collapse to one node, or a later in-place edit to one would
    silently corrupt the other's decode."""
    a, b = [1, 2], [1, 2]
    payload = project({"a": a, "b": b})
    assert len(payload.nodes) > 0
    assert _in_place_mutable(a) and _in_place_mutable(b)


def test_in_place_mutable_is_true_for_list_dict_set_false_for_tuple_and_str():
    """The mutable-container predicate over the vocabulary's builtin types."""
    assert _in_place_mutable([1])
    assert _in_place_mutable({"a": 1})
    assert _in_place_mutable({1})
    assert not _in_place_mutable((1,))
    assert not _in_place_mutable("x")


def test_project_checked_passes_for_an_ordinary_value():
    """An ordinary value's fixpoint-checked projection matches the plain one."""
    payload = project_checked({"a": [1, 2], "b": "x"})
    assert payload == project({"a": [1, 2], "b": "x"})


def test_a_cycle_refuses_with_the_offending_type_named():
    """A value containing itself has no finite encoding and refuses."""
    cyclic: list = []
    cyclic.append(cyclic)
    with pytest.raises(UnsupportedConstructError, match="cycle"):
        project(cyclic)
