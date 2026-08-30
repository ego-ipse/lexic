"""The three open `from_indexes` validation lanes, authored from real evidence.

`keyed_product_rows.py` proved the document→verdict relation EXACT for the two
constructors as they are currently specified. It could not choose the final
contract, because three lanes are simply not constrained today:

1. the ordinal domain — negative, sparse, repeated, out-of-range;
2. merge dyads naming spellings the vocabulary does not have;
3. byte-fallback / unknown / fused-unknown / added-token / pipeline spellings
   absent from or conflicting with the vocabulary.

This module inventories all four fetched real fixtures plus the small one for
exactly those questions, then states and executes the recommended pre-alpha
contract and differentials it against a small independent constructor oracle.

**The inventory reads the fixtures with the standard-library json decoder on
purpose.** The question is what the FORMAT contains, not how lexic parses it;
building a Qwen-scale `IrMap` (or running the historical reduce path) to count
ordinals would cost minutes and answer nothing this asks. Each fixture is
scanned once, sequentially, with its own process CPU, wall, bytes and peak
retained memory reported separately.

Run with ``--fixtures`` for the inventory (one row per file, sequential) and
with no argument for the contract, its refusal order, and the oracle
differential.
"""

from __future__ import annotations

import argparse
import json
import time
import tracemalloc
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import NamedTuple

from keyed_product_rows import (
    Indexes,
    _first_duplicate_dyad,
    _first_duplicate_ordinal,
    _first_duplicate_spelling,
    _missing_special,
)

from lexic.api.pretokens import BYTE_FALLBACK, BYTE_LEVEL_REMAP
from lexic.exceptions import FieldValidationError
from lexic.ir import IrChr, IrInt, IrMap, IrStr, IrTokenizer, IrTuple
from lexic.ir.text.pipeline import IrTokenPipeline, IrUnknown
from lexic.ir.text.tokenizer import IrLongestMatch, IrRankedMerge, IrSegmenter

CONSTRUCT_TOKENIZER: Callable[..., IrTokenizer] = IrTokenizer
"""The record's own positional constructor under an honest callable type."""

ROOT = Path(__file__).resolve().parents[3]

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)
type RawMerge = str | list[JsonValue]

FIXTURES = (
    ("hf_bpe", ROOT / "tests/integration/lexic/tokens/fixtures/hf_bpe.tokenizer.json"),
    ("gpt2", ROOT / "resources/tokenizers/gpt2.tokenizer.json"),
    ("smollm2", ROOT / "resources/tokenizers/smollm2.tokenizer.json"),
    ("qwen3", ROOT / "resources/tokenizers/qwen3.tokenizer.json"),
    ("gemma4", ROOT / "resources/tokenizers/gemma4.tokenizer.json"),
)
"""Every fixture this contract must accept or deliberately refuse."""


class OrdinalFacts(NamedTuple):
    """Lane 1 — what the vocabulary's ordinals actually look like."""

    entries: int
    distinct: int
    lowest: int
    highest: int
    negative: int
    repeated: int
    dense: bool
    gaps: int
    above_entries: int
    declared_size: int


class MergeFacts(NamedTuple):
    """Lane 2 — merge dyads against the vocabulary."""

    merges: int
    array_form: int
    string_form: int
    left_absent: int
    right_absent: int
    joined_absent: int
    example: str


class PipelineFacts(NamedTuple):
    """Lane 3 — every non-vocabulary spelling the pipeline names."""

    byte_fallback: bool
    fallback_present: int
    fallback_absent: int
    unknown: str
    unknown_in_vocab: bool
    fuse_unknown: bool
    added: int
    flagged_special: int
    ordinary_added: int
    added_absent: int
    added_conflicting: int
    remap_absent: int


class FixtureFacts(NamedTuple):
    """One fixture's complete inventory plus its isolated scan cost."""

    name: str
    bytes_read: int
    cpu: float
    wall: float
    peak_bytes: int
    ordinals: OrdinalFacts
    merges: MergeFacts
    pipeline: PipelineFacts


def _ordinal_facts(vocab: dict[str, int], declared: int) -> OrdinalFacts:
    """Lane 1 over one document's ``model.vocab``."""
    ids = list(vocab.values())
    distinct = set(ids)
    lowest = min(ids, default=0)
    highest = max(ids, default=-1)
    span = set(range(0, highest + 1))
    return OrdinalFacts(
        len(ids),
        len(distinct),
        lowest,
        highest,
        sum(1 for value in ids if value < 0),
        len(ids) - len(distinct),
        len(distinct) == len(ids) and highest + 1 == len(ids) and lowest == 0,
        len(span - distinct),
        sum(1 for value in ids if value >= len(ids)),
        declared,
    )


def _dyads(merges: Iterable[RawMerge]) -> list[tuple[str, str, bool]]:
    """Each merge as ``(left, right, was_an_array)`` — both wild encodings."""
    out: list[tuple[str, str, bool]] = []
    for merge in merges:
        if isinstance(merge, list):
            out.append((str(merge[0]), str(merge[1]), True))
            continue
        left, _, right = str(merge).partition(" ")
        out.append((left, right, False))
    return out


def _merge_facts(merges: Sequence[RawMerge], vocab: dict[str, int]) -> MergeFacts:
    """Lane 2 over one document's ``model.merges``."""
    dyads = _dyads(merges)
    left_absent = [d for d in dyads if d[0] not in vocab]
    right_absent = [d for d in dyads if d[1] not in vocab]
    joined_absent = [d for d in dyads if (d[0] + d[1]) not in vocab]
    example = ""
    if joined_absent:
        example = repr(joined_absent[0][:2])
    elif left_absent:
        example = repr(left_absent[0][:2])
    return MergeFacts(
        len(dyads),
        sum(1 for d in dyads if d[2]),
        sum(1 for d in dyads if not d[2]),
        len(left_absent),
        len(right_absent),
        len(joined_absent),
        example,
    )


def _pipeline_facts(
    doc: dict[str, JsonValue],
    model: dict[str, JsonValue],
    vocab: dict[str, int],
) -> PipelineFacts:
    """Lane 3 over one document's fallback, unknown, added and remap spellings."""
    fallback = bool(model.get("byte_fallback"))
    spellings = [str(value) for value in BYTE_FALLBACK.values()]
    present = sum(1 for spelling in spellings if spelling in vocab)
    unknown = model.get("unk_token")
    added = doc.get("added_tokens") or []
    if not isinstance(added, list):
        raise LaneRefusal("tokenizer: 'added_tokens' is not an array")
    absent = 0
    conflicting = 0
    flagged_special = 0
    for entry in added:
        if not isinstance(entry, dict):
            raise LaneRefusal("tokenizer: an added token is not a mapping")
        content = str(entry.get("content"))
        flagged_special += bool(entry.get("special"))
        found = vocab.get(content)
        if found is None:
            absent += 1
        elif _token_id(entry.get("id"), f"added-token id for {content!r}") != found:
            conflicting += 1
    remap = [str(value) for value in BYTE_LEVEL_REMAP.values()]
    return PipelineFacts(
        fallback,
        present,
        len(spellings) - present,
        "" if unknown is None else str(unknown),
        unknown is not None and str(unknown) in vocab,
        bool(model.get("fuse_unk")),
        len(added),
        flagged_special,
        len(added) - flagged_special,
        absent,
        conflicting,
        sum(1 for spelling in remap if spelling not in vocab),
    )


def inspect(name: str, path: Path) -> FixtureFacts:
    """Scan one fixture once, sequentially, with its own cost recorded."""
    raw = path.read_bytes()
    tracemalloc.start()
    cpu = time.process_time()
    wall = time.perf_counter()
    loaded: JsonValue = json.loads(raw)
    if not isinstance(loaded, dict):
        raise LaneRefusal("tokenizer: document root is not a mapping")
    doc = loaded
    model = doc.get("model") or {}
    if not isinstance(model, dict):
        raise LaneRefusal("tokenizer: 'model' is not a mapping")
    vocab = _fixture_vocab(model)
    declared = model.get("vocab_size") or 0
    ordinals = _ordinal_facts(vocab, _token_id(declared, "'model.vocab_size'"))
    merges = _merge_facts(_raw_merges(model), vocab)
    pipeline = _pipeline_facts(doc, model, vocab)
    elapsed_cpu = time.process_time() - cpu
    elapsed_wall = time.perf_counter() - wall
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return FixtureFacts(
        name,
        len(raw),
        elapsed_cpu,
        elapsed_wall,
        peak,
        ordinals,
        merges,
        pipeline,
    )


def report(facts: FixtureFacts) -> None:
    """One fixture's three lanes, with its isolated scan cost beside them."""
    print(
        "fixture",
        facts.name,
        f"bytes={facts.bytes_read}",
        f"scan_cpu={facts.cpu:.6f}",
        f"scan_wall={facts.wall:.6f}",
        f"scan_peak_bytes={facts.peak_bytes}",
        sep="\t",
    )
    ordinals = facts.ordinals
    print(
        "lane-1-ordinals",
        facts.name,
        f"entries={ordinals.entries}",
        f"distinct={ordinals.distinct}",
        f"lowest={ordinals.lowest}",
        f"highest={ordinals.highest}",
        f"negative={ordinals.negative}",
        f"repeated={ordinals.repeated}",
        f"dense_0_to_n={ordinals.dense}",
        f"gaps_below_highest={ordinals.gaps}",
        f"ids_at_or_above_entry_count={ordinals.above_entries}",
        f"declared_vocab_size={ordinals.declared_size}",
        sep="\t",
    )
    merges = facts.merges
    print(
        "lane-2-merges",
        facts.name,
        f"merges={merges.merges}",
        f"array_form={merges.array_form}",
        f"string_form={merges.string_form}",
        f"left_absent_from_vocab={merges.left_absent}",
        f"right_absent_from_vocab={merges.right_absent}",
        f"joined_absent_from_vocab={merges.joined_absent}",
        f"example={merges.example}",
        sep="\t",
    )
    pipeline = facts.pipeline
    print(
        "lane-3-pipeline",
        facts.name,
        f"byte_fallback_declared={pipeline.byte_fallback}",
        f"fallback_spellings_in_vocab={pipeline.fallback_present}/256",
        f"fallback_spellings_absent={pipeline.fallback_absent}",
        f"unknown={pipeline.unknown!r}",
        f"unknown_in_vocab={pipeline.unknown_in_vocab}",
        f"fuse_unknown={pipeline.fuse_unknown}",
        f"added_tokens={pipeline.added}",
        f"format_special_true={pipeline.flagged_special}",
        f"format_special_false={pipeline.ordinary_added}",
        f"added_absent_from_vocab={pipeline.added_absent}",
        f"added_id_conflicts_with_vocab={pipeline.added_conflicting}",
        f"byte_level_remap_chars_absent={pipeline.remap_absent}/256",
        sep="\t",
    )


# ── the recommended pre-alpha contract ────────────────────────────────────


ORDINAL_CONTRACT = (
    "accept every NON-NEGATIVE ordinal, sparse or above the entry count;"
    " refuse a negative ordinal and a repeated one"
)
MERGE_CONTRACT = (
    "accept a dyad whose parts are absent from the vocabulary; refuse a"
    " duplicate dyad and a non-contiguous rank"
)
PIPELINE_CONTRACT = (
    "refuse a pipeline SPECIAL outside the vocabulary; accept a declared"
    " byte-fallback table and unknown spelling that the vocabulary does not"
    " cover, and accept an added token whose id agrees with the vocabulary"
    " while refusing one that contradicts it; the special-membership check"
    " runs AFTER the added-token merge, not against model.vocab"
)


class LaneRefusal(FieldValidationError):
    """A refusal produced by the candidate final constructor."""


def _token_id(value: JsonValue, what: str) -> int:
    """One JSON integer at a tokenizer-id boundary."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise LaneRefusal(f"tokenizer: {what} is not an integer")


def _fixture_vocab(model: dict[str, JsonValue]) -> dict[str, int]:
    """A checked fixture vocabulary for inventory and contract witnesses."""
    raw = model.get("vocab") or {}
    if not isinstance(raw, dict):
        raise LaneRefusal("tokenizer: 'model.vocab' is not a mapping")
    return {
        spelling: _token_id(ordinal, f"vocabulary id for {spelling!r}")
        for spelling, ordinal in raw.items()
    }


def merged_encode(
    vocab: Sequence[tuple[str, int]], added: Sequence[tuple[str, int]]
) -> tuple[tuple[str, int], ...]:
    """``model.vocab`` extended by the added tokens it does not already carry.

    Lane 3's load-bearing case: Qwen lists all 26 of its specials only under
    ``added_tokens``, so an index built from ``model.vocab`` alone cannot spell
    them and every special-membership check would refuse the file. An added
    token that IS in the vocabulary must agree with it; a contradiction is two
    ids for one spelling and cannot be resolved by preferring either.

    :param vocab: The model's own ``spelling -> id`` entries, in document order.
    :param added: The added-token entries, in document order.
    :returns: The merged encode index.
    :raises LaneRefusal: When an added token contradicts the vocabulary.
    """
    table = dict(vocab)
    out = list(vocab)
    for spelling, ordinal in added:
        found = table.get(spelling)
        if found is None:
            table[spelling] = ordinal
            out.append((spelling, ordinal))
            continue
        if found != ordinal:
            raise LaneRefusal(
                f"tokenizer: added token {spelling!r} claims id {ordinal!r} but"
                f" the vocabulary spells it {found!r}"
            )
    return tuple(out)


def _negative_ordinal(ordinals: Iterable[int]) -> int | None:
    """The smallest negative ordinal, or ``None`` when every one is a token id."""
    found = [value for value in ordinals if value < 0]
    return min(found) if found else None


def from_indexes_final(name: str, indexes: Indexes) -> IrTokenizer:
    """The CANDIDATE final tail — the three lanes decided, in refusal order.

    Ordered validation, each refusal naming its own lane. Every lane decidable
    during STREAMING accumulation comes first, then the root cross-field
    checks — the failure order ``TODO.md`` pins for the tokenizer target:

    1. duplicate spelling in the encode index — streaming;
    2. **negative ordinal** in the encode index — streaming (open lane 1);
    3. duplicate ordinal in the encode index — streaming;
    4. duplicate ordinal in the decode index — streaming;
    5. duplicate merge dyad in the rank index — streaming (open lane 2);
    6. encode/decode bijection — root cross-field;
    7. contiguous ranks, exactly ``0 .. n-1`` — root cross-field (open lane 2);
    8. pipeline references, every special a vocabulary spelling — root
       cross-field (open lane 3);
    9. segmenter consistency — a non-empty rank index requires ranked merge —
       root cross-field.

    Sparse and above-count ordinals, dyad parts outside the vocabulary, and an
    uncovered byte-fallback or unknown spelling are ACCEPTED: every real
    fixture exercises them and none of them can make segmentation ambiguous.

    :param name: The registry name.
    :param indexes: The three built indexes plus pipeline and segmenter.
    :returns: The ready tokenizer.
    :raises LaneRefusal: On any validation above, in that order.
    """
    duplicate = _first_duplicate_spelling(indexes.encode)
    if duplicate is not None:
        raise LaneRefusal(f"tokenizer: duplicate spelling {duplicate!r}")
    negative = _negative_ordinal(ordinal for _s, ordinal in indexes.encode)
    if negative is not None:
        raise LaneRefusal(f"tokenizer: ordinal {negative!r} is not a token id")
    repeated = _first_duplicate_ordinal(ordinal for _s, ordinal in indexes.encode)
    if repeated is not None:
        raise LaneRefusal(
            f"tokenizer: duplicate ordinal {repeated!r} in the encode index"
        )
    decoded = _first_duplicate_ordinal(ordinal for ordinal, _s in indexes.decode)
    if decoded is not None:
        raise LaneRefusal(
            f"tokenizer: duplicate ordinal {decoded!r} in the decode index"
        )
    dyad = _first_duplicate_dyad(tuple(pair for pair, _rank in indexes.ranks))
    if dyad is not None:
        raise LaneRefusal(f"tokenizer: duplicate merge dyad {dyad!r}")
    forward = dict(indexes.encode)
    inverse = dict(indexes.decode)
    if len(forward) != len(inverse) or any(
        inverse.get(ordinal) != spelling for spelling, ordinal in forward.items()
    ):
        raise LaneRefusal("tokenizer: encode and decode are not inverse")
    ranks = sorted(rank for _dyad, rank in indexes.ranks)
    if ranks != list(range(len(ranks))):
        raise LaneRefusal("tokenizer: merge ranks are not contiguous from 0")
    special = _missing_special(indexes.pipeline, forward)
    if special is not None:
        raise LaneRefusal(f"tokenizer: special {special!r} is not in the vocab")
    if indexes.ranks and not isinstance(indexes.segmenter, IrRankedMerge):
        raise LaneRefusal("tokenizer: segmenter disagrees with the ranks")
    return _construct(name, indexes)


def _construct(name: str, indexes: Indexes) -> IrTokenizer:
    """Freeze the validated indexes into the record, without re-deriving."""
    return CONSTRUCT_TOKENIZER(
        IrStr(name),
        IrMap.from_table((IrStr(s), IrChr(i)) for s, i in indexes.encode),
        IrMap.from_table((IrChr(i), IrStr(s)) for i, s in indexes.decode),
        IrMap.from_table(
            (IrTuple(IrStr(d[0]), IrStr(d[1])), IrInt(r)) for d, r in indexes.ranks
        ),
        indexes.pipeline,
        indexes.segmenter,
    )


def final_verdict(indexes: Indexes) -> str | None:
    """The first refusal :func:`from_indexes_final` would produce, or ``None``.

    The document-level twin: the same ordered decision without constructing
    the tokenizer that is about to be discarded.
    """
    duplicate = _first_duplicate_spelling(indexes.encode)
    if duplicate is not None:
        return f"tokenizer: duplicate spelling {duplicate!r}"
    negative = _negative_ordinal(ordinal for _s, ordinal in indexes.encode)
    if negative is not None:
        return f"tokenizer: ordinal {negative!r} is not a token id"
    repeated = _first_duplicate_ordinal(ordinal for _s, ordinal in indexes.encode)
    if repeated is not None:
        return f"tokenizer: duplicate ordinal {repeated!r} in the encode index"
    decoded = _first_duplicate_ordinal(ordinal for ordinal, _s in indexes.decode)
    if decoded is not None:
        return f"tokenizer: duplicate ordinal {decoded!r} in the decode index"
    dyad = _first_duplicate_dyad(tuple(pair for pair, _rank in indexes.ranks))
    if dyad is not None:
        return f"tokenizer: duplicate merge dyad {dyad!r}"
    forward = dict(indexes.encode)
    inverse = dict(indexes.decode)
    if len(forward) != len(inverse) or any(
        inverse.get(ordinal) != spelling for spelling, ordinal in forward.items()
    ):
        return "tokenizer: encode and decode are not inverse"
    ranks = sorted(rank for _dyad, rank in indexes.ranks)
    if ranks != list(range(len(ranks))):
        return "tokenizer: merge ranks are not contiguous from 0"
    special = _missing_special(indexes.pipeline, forward)
    if special is not None:
        return f"tokenizer: special {special!r} is not in the vocab"
    if indexes.ranks and not isinstance(indexes.segmenter, IrRankedMerge):
        return "tokenizer: segmenter disagrees with the ranks"
    return None


# ── the independent constructor oracle ────────────────────────────────────


def oracle_verdict(indexes: Indexes) -> str | None:
    """An independent re-derivation of the same contract, written differently.

    Deliberately NOT a refactor of :func:`final_verdict`: it rebuilds each lane
    from primitive counts and carries its own missing-special search, so a
    shared helper cannot make the two agree on the lane being checked. Only the
    ORDER is shared, because the order IS the contract — which is why
    :data:`WITNESSES` pins every adjacent lane boundary separately.

    Each lane's message is built only when that lane fires: the duplicate
    searches are quadratic, and computing them eagerly made a real 268 000-entry
    fixture take longer than the whole rest of this module.
    """
    spellings = [spelling for spelling, _o in indexes.encode]
    ordinals = [ordinal for _s, ordinal in indexes.encode]
    if len(set(spellings)) != len(spellings):
        return f"tokenizer: duplicate spelling {_repr_min_spelling(spellings)!r}"
    if any(value < 0 for value in ordinals):
        return f"tokenizer: ordinal {min(ordinals)!r} is not a token id"
    if len(set(ordinals)) != len(ordinals):
        return (
            f"tokenizer: duplicate ordinal {_repr_min_ordinal(ordinals)!r}"
            " in the encode index"
        )
    decoded = [ordinal for ordinal, _s in indexes.decode]
    if len(set(decoded)) != len(decoded):
        return (
            f"tokenizer: duplicate ordinal {_repr_min_ordinal(decoded)!r}"
            " in the decode index"
        )
    dyads = [dyad for dyad, _r in indexes.ranks]
    if len(set(dyads)) != len(dyads):
        return f"tokenizer: duplicate merge dyad {_repr_min_dyad(dyads)!r}"
    if sorted(indexes.encode) != sorted((s, o) for o, s in indexes.decode):
        return "tokenizer: encode and decode are not inverse"
    if sorted(r for _d, r in indexes.ranks) != list(range(len(indexes.ranks))):
        return "tokenizer: merge ranks are not contiguous from 0"
    known = set(spellings)
    if any(str(s) not in known for s in indexes.pipeline.specials):
        return f"tokenizer: special {_absent_special(indexes, spellings)!r} is not in the vocab"
    if indexes.ranks and not isinstance(indexes.segmenter, IrRankedMerge):
        return "tokenizer: segmenter disagrees with the ranks"
    return None


def _absent_special(indexes: Indexes, spellings: Sequence[str]) -> str:
    """The first special the encode index does not spell — the oracle's own.

    Deliberately not `keyed_product_rows._missing_special`, which
    :func:`final_verdict` uses: sharing that helper would make the two lanes
    agree by construction on exactly the lane this differential is checking.
    """
    known = set(spellings)
    absent = [str(s) for s in indexes.pipeline.specials if str(s) not in known]
    return absent[0] if absent else ""


def _repr_min_spelling(spellings: Sequence[str]) -> str:
    """The repr-smallest repeated spelling."""
    repeated = {s for s in spellings if spellings.count(s) > 1}
    return min(repeated, key=lambda s: repr(IrStr(s)), default="")


def _repr_min_ordinal(ordinals: Sequence[int]) -> int:
    """The repr-smallest repeated ordinal."""
    repeated = {o for o in ordinals if ordinals.count(o) > 1}
    return min(repeated, key=lambda o: repr(IrChr(o)), default=0)


def _repr_min_dyad(dyads: Sequence[tuple[str, str]]) -> tuple[str, str]:
    """The repr-smallest repeated dyad."""
    repeated = {d for d in dyads if dyads.count(d) > 1}
    return min(
        repeated,
        key=lambda d: repr(IrTuple(IrStr(d[0]), IrStr(d[1]))),
        default=("", ""),
    )


# ── the candidate's own witness family ────────────────────────────────────


def _indexes(
    encode: Sequence[tuple[str, int]],
    ranks: Sequence[tuple[tuple[str, str], int]] = (),
    specials: Sequence[str] = (),
    segmenter: IrSegmenter = IrRankedMerge(),
    decode: Sequence[tuple[int, str]] | None = None,
) -> Indexes:
    """One index triple, decode derived from encode unless given explicitly."""
    return Indexes(
        tuple(encode),
        tuple(decode if decode is not None else ((o, s) for s, o in encode)),
        tuple(ranks),
        IrTokenPipeline(
            IrTuple(*(IrStr(s) for s in specials)),
            IrMap(),
            IrTuple(),
            IrTuple(),
            IrMap(),
            IrUnknown(),
        ),
        segmenter,
    )


BASE = (("a", 0), ("b", 1), ("ab", 2))

WITNESSES = (
    ("dense-accepted", _indexes(BASE), None),
    ("sparse-accepted", _indexes((("a", 0), ("b", 7), ("ab", 90))), None),
    ("above-count-accepted", _indexes((("a", 151643), ("b", 1))), None),
    (
        "negative-refused",
        _indexes((("a", 0), ("b", -1))),
        "tokenizer: ordinal -1 is not a token id",
    ),
    (
        "repeated-ordinal-refused",
        _indexes((("a", 3), ("b", 3))),
        "tokenizer: duplicate ordinal 3 in the encode index",
    ),
    (
        "duplicate-spelling-refused",
        _indexes((("a", 0), ("a", 1))),
        "tokenizer: duplicate spelling 'a'",
    ),
    (
        "merge-parts-outside-vocab-accepted",
        _indexes(BASE, ((("zz", "yy"), 0),)),
        None,
    ),
    (
        "duplicate-dyad-refused",
        _indexes(BASE, ((("a", "b"), 0), (("a", "b"), 1))),
        "tokenizer: duplicate merge dyad ('a', 'b')",
    ),
    (
        "non-contiguous-rank-refused",
        _indexes(BASE, ((("a", "b"), 0), (("b", "a"), 2))),
        "tokenizer: merge ranks are not contiguous from 0",
    ),
    (
        "special-outside-vocab-refused",
        _indexes(BASE, (), ("<|end|>",)),
        "tokenizer: special '<|end|>' is not in the vocab",
    ),
    ("special-in-vocab-accepted", _indexes(BASE, (), ("ab",)), None),
    (
        "broken-bijection-refused",
        _indexes(BASE, decode=((0, "a"), (1, "b"), (2, "ba"))),
        "tokenizer: encode and decode are not inverse",
    ),
    (
        "segmenter-disagrees-refused",
        _indexes(BASE, ((("a", "b"), 0),), segmenter=IrLongestMatch()),
        "tokenizer: segmenter disagrees with the ranks",
    ),
    (
        "lane-1-before-lane-2",
        _indexes((("a", 0), ("a", -1))),
        "tokenizer: duplicate spelling 'a'",
    ),
    (
        "lane-2-before-lane-3",
        _indexes((("a", -1), ("b", 3), ("c", 3))),
        "tokenizer: ordinal -1 is not a token id",
    ),
    (
        "lane-3-before-lane-4",
        _indexes((("a", 3), ("b", 3)), decode=((7, "a"), (7, "b"))),
        "tokenizer: duplicate ordinal 3 in the encode index",
    ),
    (
        "lane-4-before-lane-5",
        _indexes(
            (("a", 0), ("b", 1)),
            ((("a", "b"), 0), (("a", "b"), 1)),
            decode=((0, "a"), (0, "b")),
        ),
        "tokenizer: duplicate ordinal 0 in the decode index",
    ),
    (
        "lane-5-before-lane-6",
        _indexes(
            (("a", 0), ("b", 1)),
            ((("a", "b"), 0), (("a", "b"), 1)),
            decode=((0, "a"), (1, "z")),
        ),
        "tokenizer: duplicate merge dyad ('a', 'b')",
    ),
    (
        "lane-6-before-lane-7",
        _indexes(BASE, ((("a", "b"), 1),), decode=((0, "a"), (1, "b"), (2, "ba"))),
        "tokenizer: encode and decode are not inverse",
    ),
    (
        "lane-7-before-lane-8",
        _indexes(BASE, ((("a", "b"), 1),), ("<|end|>",)),
        "tokenizer: merge ranks are not contiguous from 0",
    ),
    (
        "lane-8-before-lane-9",
        _indexes(BASE, ((("a", "b"), 0),), ("<|end|>",), segmenter=IrLongestMatch()),
        "tokenizer: special '<|end|>' is not in the vocab",
    ),
)
"""Every accepted shape, every refused shape, and every ADJACENT lane boundary.

The eight ``lane-N-before-lane-M`` rows each set two ADJACENT lanes failing at
once and pin which one is reported, so a reordering of the contract fails the
suite instead of passing it. :func:`prove_boundary_witnesses` CHECKS that,
lane by lane, rather than trusting the names: a row whose inputs make only one
of its two lanes fire is coverage in name only, and lanes 3 and 4 now name the
index they refuse so the two are distinguishable at all. That matters because the independent oracle deliberately shares the ORDER
— the order IS the contract — and so cannot catch a reordering by itself.
"""


LANE_ORDER_CONTRACT = (
    "the reported verdict is the FIRST OFFENDING LANE, not the first offending"
    " ENTRY: `_indexes((('a', -1), ('a', 0)))` reports the duplicate spelling"
    " (lane 1) even though an insertion-time validator would have refused"
    " entry 0's negative ordinal (lane 2) first",
    "that is the choice, and it is deliberate: an entry-order verdict makes"
    " the refusal depend on the order the document happens to list its"
    " vocabulary in, which is not a property of the tokenizer being described",
    "the lanes are ORDERED so that every streaming-decidable one (1-5) comes"
    " before every root cross-field one (6-9), which is the failure order"
    " TODO.md pins for the tokenizer target; an accumulator records every lane"
    " it hits and the root reports the lowest-numbered one",
)


def prove_lane_order_contract() -> None:
    """Execute the entry-order counterexample that forces the choice."""
    conflicting = _indexes((("a", -1), ("a", 0)))
    verdict = final_verdict(conflicting)
    assert verdict == "tokenizer: duplicate spelling 'a'", verdict
    for line in LANE_ORDER_CONTRACT:
        print("lane-order", line, sep="\t")
    print(
        "lane-order",
        "counterexample=_indexes((('a', -1), ('a', 0)))",
        f"reported={verdict}",
        "an insertion-time validator would report the negative ordinal at"
        " entry 0 instead; both cannot be the specification",
        sep="\t",
    )


"""Every accepted and refused shape the chosen contract has to pin."""


def lanes_fired(indexes: Indexes) -> tuple[int, ...]:
    """Which of the nine lanes a document offends, ALL of them, in order.

    A third statement of the nine conditions, used only by
    :func:`prove_boundary_witnesses`. `final_verdict` short-circuits at the
    first lane, so it cannot say whether a witness named for a boundary really
    makes BOTH of its lanes fire — and a row that does not is coverage in name
    only. That is exactly the defect this function exists to catch, twice
    missed by grepping names and counting printed rows.
    """
    spellings = [spelling for spelling, _o in indexes.encode]
    ordinals = [ordinal for _s, ordinal in indexes.encode]
    decoded = [ordinal for ordinal, _s in indexes.decode]
    dyads = [dyad for dyad, _r in indexes.ranks]
    known = set(spellings)
    conditions = (
        (1, len(set(spellings)) != len(spellings)),
        (2, any(value < 0 for value in ordinals)),
        (3, len(set(ordinals)) != len(ordinals)),
        (4, len(set(decoded)) != len(decoded)),
        (5, len(set(dyads)) != len(dyads)),
        (6, sorted(indexes.encode) != sorted((s, o) for o, s in indexes.decode)),
        (
            7,
            sorted(r for _d, r in indexes.ranks) != list(range(len(indexes.ranks))),
        ),
        (8, any(str(s) not in known for s in indexes.pipeline.specials)),
        (
            9,
            bool(indexes.ranks) and not isinstance(indexes.segmenter, IrRankedMerge),
        ),
    )
    return tuple(lane for lane, fired in conditions if fired)


def prove_boundary_witnesses() -> None:
    """Every ``lane-N-before-lane-M`` row really makes BOTH lanes fire.

    Two audits accepted a claim that the eight rows pin the eight adjacent
    boundaries; both times a row's INPUTS did not make its second lane fire, so
    swapping those two lanes would have passed the suite. Names and row counts
    cannot see that. This does, and it also checks that the reported verdict is
    the lower-numbered lane's, which is the contract.
    """
    for name, indexes, expected in WITNESSES:
        if not name.startswith("lane-"):
            continue
        parts = name.split("-")
        low, high = int(parts[1]), int(parts[4])
        assert high == low + 1, name
        fired = lanes_fired(indexes)
        assert low in fired and high in fired, (name, fired)
        assert final_verdict(indexes) == expected, name
        print(
            "boundary-witness",
            name,
            f"lanes_fired={list(fired)}",
            f"both_named_lanes_fire={low in fired and high in fired}",
            f"reported={expected}",
            sep="\t",
        )


def prove_contract() -> None:
    """Execute the candidate constructor and its document-level twin."""
    for name, indexes, expected in WITNESSES:
        verdict = final_verdict(indexes)
        oracle = oracle_verdict(indexes)
        assert verdict == expected, (name, verdict, expected)
        assert oracle == expected, (name, oracle, expected)
        built = ""
        try:
            tokenizer = from_indexes_final("candidate", indexes)
            built = str(tokenizer.name)
        except LaneRefusal as error:
            built = f"REFUSED {error}"
        constructed = built.startswith("REFUSED")
        assert constructed == (expected is not None), (name, built)
        print(
            "contract",
            name,
            f"verdict={verdict}",
            f"oracle_agrees={oracle == verdict}",
            f"constructor_agrees={constructed == (expected is not None)}",
            sep="\t",
        )


ADDED_CASES = (
    ("added-outside-model-vocab-merged", BASE, (("<|im_end|>", 151643),), ""),
    ("added-agreeing-with-vocab-accepted", BASE, (("ab", 2),), ""),
    (
        "added-contradicting-vocab-refused",
        BASE,
        (("ab", 9),),
        "tokenizer: added token 'ab' claims id 9 but the vocabulary spells it 2",
    ),
)
"""The added-token merge, which lane 3's special check runs AFTER."""


def prove_added_merge() -> None:
    """Added tokens outside ``model.vocab`` are merged, contradictions refused."""
    for name, vocab, added, expected in ADDED_CASES:
        try:
            merged = merged_encode(vocab, added)
            message = ""
        except LaneRefusal as error:
            merged = ()
            message = str(error)
        assert message == expected, (name, message, expected)
        special = "" if not merged else merged[-1][0]
        verdict = ""
        if merged:
            verdict = final_verdict(_indexes(merged, (), (special,))) or ""
        print(
            "added-merge",
            name,
            f"merged_entries={len(merged)}",
            f"refusal={message}",
            f"special_check_after_merge={verdict or 'accepted'}",
            sep="\t",
        )


def constructed_verdict(indexes: Indexes) -> str | None:
    """What the CONSTRUCTOR really decided — ``None``, or its refusal message.

    The eager reference the document-level twin must reproduce. A successful
    build carries no verdict; two successful builds may still be different
    tokenizers, which is a difference in the RESULT, not in the contract.
    """
    try:
        from_indexes_final("candidate", indexes)
    except LaneRefusal as error:
        return str(error)
    return None


def prove_lane_pairs() -> None:
    """Every ordered pair: twin, oracle and EAGER CONSTRUCTION agree.

    Comparing the twin against the oracle alone would be near-tautological
    once both are pinned to the same expected verdict. The load-bearing
    comparison is against what the constructor really built: two documents are
    interchangeable iff their constructed outcomes are identical, refusals
    included.
    """
    checked = 0
    eager = {name: constructed_verdict(indexes) for name, indexes, _e in WITNESSES}
    for name, indexes, _expected in WITNESSES:
        assert final_verdict(indexes) == eager[name], name
        assert oracle_verdict(indexes) == eager[name], name
    for left_name, left, _le in WITNESSES:
        for right_name, right, _re in WITNESSES:
            checked += 1
            same_twin = final_verdict(left) == final_verdict(right)
            same_oracle = oracle_verdict(left) == oracle_verdict(right)
            same_eager = eager[left_name] == eager[right_name]
            assert same_twin == same_oracle, (left_name, right_name)
            assert same_twin == same_eager, (left_name, right_name)
    print(
        "contract",
        "exhaustive-pairs",
        f"ordered_pairs={checked}",
        f"twin_equals_eager_construction_per_witness={len(WITNESSES)}",
        f"distinct_verdicts={len(set(map(str, eager.values())))}",
        "the document-level twin, the independently written oracle and the"
        " eager construction agree on every ordered pair, refusing pairs"
        " included",
        sep="\t",
    )


def _added_entries(
    doc: dict[str, JsonValue],
) -> tuple[tuple[str, int, bool], ...]:
    """Added-token spelling, ordinal, and format ``special`` flag."""
    raw = doc.get("added_tokens") or []
    if not isinstance(raw, list):
        raise LaneRefusal("tokenizer: 'added_tokens' is not an array")
    out: list[tuple[str, int, bool]] = []
    for value in raw:
        if not isinstance(value, dict):
            raise LaneRefusal("tokenizer: an added token is not a mapping")
        spelling = value.get("content")
        ordinal = value.get("id")
        if not isinstance(spelling, str):
            raise LaneRefusal("tokenizer: an added token has no spelling")
        out.append(
            (
                spelling,
                _token_id(ordinal, f"added-token id for {spelling!r}"),
                bool(value.get("special")),
            )
        )
    return tuple(out)


def _raw_merges(model: dict[str, JsonValue]) -> tuple[RawMerge, ...]:
    """The two admitted raw merge encodings, checked at the JSON boundary."""
    raw = model.get("merges") or []
    if not isinstance(raw, list):
        raise LaneRefusal("tokenizer: 'model.merges' is not an array")
    out: list[RawMerge] = []
    for value in raw:
        if isinstance(value, str) or isinstance(value, list):
            out.append(value)
            continue
        raise LaneRefusal("tokenizer: a merge is neither text nor an array")
    return tuple(out)


def _contains_type(value: JsonValue, expected: str) -> bool:
    """Whether a nested tokenizer section declares ``type == expected``."""
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            if current.get("type") == expected:
                return True
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return False


def _validation_pipeline(
    doc: dict[str, JsonValue],
    model: dict[str, JsonValue],
    added: Sequence[tuple[str, int, bool]],
) -> IrTokenPipeline:
    """The pipeline fields that participate in the three validation lanes."""
    unknown = model.get("unk_token")
    unknown_spec = (
        IrUnknown(unknown, bool(model.get("fuse_unk")))
        if isinstance(unknown, str)
        else IrUnknown()
    )
    remap = (
        BYTE_LEVEL_REMAP
        if _contains_type(doc.get("pre_tokenizer"), "ByteLevel")
        else IrMap()
    )
    fallback = BYTE_FALLBACK if bool(model.get("byte_fallback")) else IrMap()
    return IrTokenPipeline(
        IrTuple(*(IrStr(spelling) for spelling, _ordinal, _special in added)),
        remap,
        IrTuple(),
        IrTuple(),
        fallback,
        unknown_spec,
    )


def fixture_indexes(path: Path) -> Indexes:
    """One real fixture streamed into the three indexes the contract validates.

    `model.vocab` merged with `added_tokens` — the load-bearing Qwen step, run
    here on 151 669 real entries rather than a three-entry toy — then decode
    derived, ranks numbered by position, and the pipeline's specials taken from
    the added tokens exactly as the shipped reader takes them.
    """
    loaded: JsonValue = json.loads(path.read_bytes())
    if not isinstance(loaded, dict):
        raise LaneRefusal("tokenizer: document root is not a mapping")
    doc = loaded
    model = doc.get("model") or {}
    if not isinstance(model, dict):
        raise LaneRefusal("tokenizer: 'model' is not a mapping")
    vocab = tuple(_fixture_vocab(model).items())
    added = _added_entries(doc)
    encode = merged_encode(vocab, tuple((s, i) for s, i, _special in added))
    dyads = _dyads(_raw_merges(model))
    return Indexes(
        encode,
        tuple((ordinal, spelling) for spelling, ordinal in encode),
        tuple(((left, right), rank) for rank, (left, right, _a) in enumerate(dyads)),
        _validation_pipeline(doc, model, added),
        IrRankedMerge(),
    )


def prove_fixture_pipeline_payload() -> None:
    """Accepted fallback/unknown data survives the candidate construction."""
    for name, path in FIXTURES:
        if not path.exists():
            continue
        indexes = fixture_indexes(path)
        tokenizer = from_indexes_final(name, indexes)
        assert tokenizer.pipeline == indexes.pipeline, name
        print(
            "fixture-pipeline",
            name,
            f"atomic_added_tokens={len(indexes.pipeline.specials)}",
            f"byte_fallback_entries={len(indexes.pipeline.byte_fallback)}",
            f"unknown={indexes.pipeline.unknown.spelling!r}",
            f"fuse_unknown={indexes.pipeline.unknown.fuse}",
            f"remap_entries={len(indexes.pipeline.remap)}",
            "candidate construction retained every lane-relevant field",
            sep="\t",
        )


def prove_fixture_contract() -> None:
    """Run ALL NINE lanes over each real fixture's merged indexes.

    The admission row below reads three of the nine from the inventory; this
    one runs the constructor itself, so the ``admitted`` claim is the
    contract's own verdict rather than a proxy for it.
    """
    for name, path in FIXTURES:
        if not path.exists():
            print("fixture-contract", name, "absent", sep="\t")
            continue
        indexes = fixture_indexes(path)
        started = time.process_time()
        verdict = final_verdict(indexes)
        oracle = oracle_verdict(indexes)
        eager = constructed_verdict(indexes)
        elapsed = time.process_time() - started
        assert verdict == oracle == eager, (name, verdict, oracle, eager)
        print(
            "fixture-contract",
            name,
            f"merged_entries={len(indexes.encode)}",
            f"merge_dyads={len(indexes.ranks)}",
            f"specials={len(indexes.pipeline.specials)}",
            f"all_nine_lanes_verdict={verdict}",
            f"twin_oracle_eager_agree={verdict == oracle == eager}",
            f"cpu={elapsed:.6f}",
            sep="\t",
        )


def prove_fixture_admission() -> None:
    """State, per fixture, whether the chosen contract admits it — from facts."""
    for name, path in FIXTURES:
        if not path.exists():
            print("admission", name, "fixture absent — fetch with ext.API.hf", sep="\t")
            continue
        facts = inspect(name, path)
        admits = (
            facts.ordinals.negative == 0
            and facts.ordinals.repeated == 0
            and facts.pipeline.added_conflicting == 0
        )
        print(
            "admission",
            name,
            f"admitted={admits}",
            f"needs_sparse_ordinals={not facts.ordinals.dense}",
            f"needs_merge_parts_outside_vocab={facts.merges.joined_absent > 0}",
            f"needs_uncovered_fallback="
            f"{facts.pipeline.byte_fallback and facts.pipeline.fallback_absent > 0}",
            f"needs_uncovered_remap={facts.pipeline.remap_absent > 0}",
            f"needs_added_tokens_outside_model_vocab={facts.pipeline.added_absent > 0}",
            f"needs_unknown_outside_vocab="
            f"{bool(facts.pipeline.unknown) and not facts.pipeline.unknown_in_vocab}",
            sep="\t",
        )


def main(arguments: Sequence[str] | None = None) -> None:
    """Inventory the fixtures, or execute the chosen contract."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", action="store_true")
    parsed = parser.parse_args(arguments)
    if parsed.fixtures:
        for name, path in FIXTURES:
            if not path.exists():
                print("fixture", name, "absent — fetch with ext.API.hf", sep="\t")
                continue
            report(inspect(name, path))
        prove_fixture_contract()
        prove_fixture_pipeline_payload()
        return
    prove_contract()
    prove_boundary_witnesses()
    prove_lane_order_contract()
    prove_added_merge()
    prove_lane_pairs()
    prove_fixture_admission()
    prove_fixture_pipeline_payload()
    print(
        "recommendation",
        f"lane_1={ORDINAL_CONTRACT}",
        f"lane_2={MERGE_CONTRACT}",
        f"lane_3={PIPELINE_CONTRACT}",
        "streaming accumulation DECIDES lanes 1 through 5 — each needs only"
        " the entries seen so far — and lanes 6 through 9 read two indexes and"
        " can only run at the root, which is the failure order TODO.md pins"
        " for this target; the reported verdict is the lowest-numbered lane"
        " hit, not the first entry to offend, so an accumulator records its"
        " hits and the root reports",
        sep="\t",
    )


if __name__ == "__main__":
    main()
