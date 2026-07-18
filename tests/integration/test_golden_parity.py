"""Golden-check replay: the record spine against the Task-0 parity oracle.

Replays every ``(grammar, input)`` pair recorded in ``tests/goldens/*.json``
against the LIVE implementation and asserts equality on the ORACLE keys
(PLAN_v4 ruling 12, 2026-07-16): ``runtime_dump``, ``runtime_semantic_dump``
and ``to_text`` — recorded via the prior ``model_dump(serialize_as_any=True)``
at Task 0, reproduced natively by the record spine's
``model_dump()``/``semantic_dump()`` since Task 1. The files'
``model_dump``/``semantic_dump`` keys (declared-schema, F-DUMP-1's erasure
warts included) characterized the retired prior serializer; they remain
in the byte-pinned files as the historical record and are not asserted.

The comparison here replays each golden through ``json.loads(json.dumps(...))``
(the settled-12 byte form) rather than comparing live Python objects
directly — this is the medium that is blind to tuple-vs-list and
``IrInt``-vs-``int`` distinctions (C12). The stricter in-process medium
(``model_dump()`` dict equality between two independent parses of the same
text, without a JSON round trip) is pinned separately in
``tests/unit/lexic/test_base_surface_freeze.py``.
"""

from __future__ import annotations

import json

import pytest

from lexic.compile import compile_from_path
from tests.golden_fixtures import (
    CORPUS,
    GOLDEN_DIR,
    all_stems,
    compute_record,
    golden_path,
    load_golden,
)
from tests.paths import GROUND_TRUTH


def _stem_cases() -> list[tuple[str, int]]:
    """``(stem, record index)`` for every golden record, for parametrize ids."""
    return [(stem, i) for stem in all_stems() for i in range(len(CORPUS[stem]))]


def test_every_corpus_stem_has_a_golden_file():
    """Every grammar in CORPUS has a persisted golden JSON file."""
    for stem in all_stems():
        assert golden_path(stem).is_file(), f"missing golden file for {stem}"


def test_every_golden_file_has_a_corpus_entry():
    """No stray golden file outside tests/goldens/ lacks a CORPUS entry."""
    on_disk = {p.stem for p in GOLDEN_DIR.glob("*.json")}
    assert on_disk == set(all_stems())


@pytest.mark.parametrize("stem, index", _stem_cases())
def test_golden_record_matches_live_implementation(stem: str, index: int) -> None:
    """A golden record's oracle outputs match a fresh live parse (ruling 12)."""
    golden_records = load_golden(stem)
    sample = CORPUS[stem][index]
    golden = golden_records[index]
    assert golden["input"] == sample, (
        f"{stem}[{index}]: golden input drifted from CORPUS — "
        "regenerate via `uv run python -m tests.golden_fixtures`"
    )

    cg = compile_from_path(GROUND_TRUTH / stem)
    live = compute_record(cg, sample)
    # Round-trip the live record through the pinned byte form (settled 12)
    # before comparing, so this gate exercises the same medium the golden
    # files themselves are written in.
    live_via_json = json.loads(json.dumps(live, ensure_ascii=False))

    assert live_via_json["to_text"] == golden["to_text"]
    assert live_via_json["runtime_dump"] == golden["runtime_dump"]
    assert live_via_json["runtime_semantic_dump"] == golden["runtime_semantic_dump"]


@pytest.mark.parametrize("stem", all_stems())
def test_golden_round_trip_fidelity(stem: str) -> None:
    """Every golden input's to_text() reproduces the input verbatim.

    Not a parity check (that's the test above) — a sanity check that the
    corpus itself is round-trip-valid, so a future ir-native regression that
    breaks round-tripping is caught here even if it happens to preserve the
    (now-wrong) dump shape.
    """
    for record in load_golden(stem):
        assert record["to_text"] == record["input"], (
            f"{stem}: to_text() does not reproduce input {record['input']!r}"
        )
