"""Price the REAL keyed products' ambiguity comparison, law by law.

Per product and per alternate kind, three lanes are separated:

- semantic replay (producing the alternate's document: entry stream, merge
  stream, pipeline);
- final carrier construction (the recursive `dict` tree, `IrMap` with real IR
  leaves, or a ready `IrTokenizer`) plus exact comparison on the constructed
  carriers — the cold eager fallback;
- the exact document-level alternative: a full-input equality fast ACCEPT (an
  O(n) comparison of every constructor input — sound because construction is a
  deterministic function of ALL its inputs, never used to prove inequality)
  plus a law-normalized comparison per lane.

The tokenizer's normalized view now carries EVERY constructor input and the
COMPLETE ordered validation outcome, message for message, without constructing
the discarded tokenizer. Two constructors are exercised:

- `IrTokenizer.from_merges`, the shipped witness. Its reachable refusals are
  duplicate merge dyad, then a special outside the vocab, then duplicate token
  ordinal — a precedence measured, not assumed. Duplicate spellings cannot
  reach it: its `Vocab` is a `Mapping`, so a repeated spelling is Python
  last-wins before the constructor sees it.
- a prototype `from_indexes`, the intended final tail: three already-built
  indexes plus a pipeline, validated without deriving the inverse vocabulary
  or re-indexing merges. It refuses duplicate spellings, duplicate ordinals, a
  broken encode/decode bijection, duplicate dyads, non-contiguous ranks, a
  special outside the vocab, and a segmenter inconsistent with the rank index.

Every row asserts the document-level verdict equals the constructed-carrier
verdict, and a small exhaustive suite compares every ordered pair of generated
documents, including pairs where both sides refuse — equally, or with
different first verdicts. Entry streams come from real parses of a generic
non-JSON catalog grammar; `--mode qwen` uses the real reader's
encode/rank/pipeline and runs alone under `tools/guarded.sh`. JSON/Qwen are
witnesses, never a privileged implementation.
"""

from __future__ import annotations

import argparse
import time
import tracemalloc
from collections.abc import Callable, Iterable, Sequence
from itertools import product as cross
from pathlib import Path
from typing import NamedTuple, Protocol

from lexic.api.json_tokenizer import read
from lexic.compile import compile_text
from lexic.exceptions import FieldValidationError, UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrChr, IrInt, IrMap, IrStr, IrTokenizer, IrTuple
from lexic.ir.text.pipeline import IrTokenPipeline, IrUnknown
from lexic.ir.text.tokenizer import IrLongestMatch, IrRankedMerge, IrSegmenter
from lexic.model import GrammarModel

CATALOG = (
    "doc ::= entry+\n"
    'entry ::= key "=" value ";"\n'
    "key ::= [a-z] [a-z0-9]*\n"
    "value ::= [0-9]+\n"
)

TOKENIZER_NAME = "keyed-rows"

CONSTRUCT_TOKENIZER: Callable[..., IrTokenizer] = IrTokenizer
"""The record's own positional constructor, under its honest callable type.

`IrTokenizer` declares ``init=False``, so the class object's static signature
is the record metaclass's ParamSpec rather than the field list. Naming the
positional constructor once, with a concrete return type, keeps the call site
typed without a cast — the shipped `_build` reaches the same constructor.
"""

type Entry = tuple[str, int]
type Entries = list[Entry]
type Dyads = tuple[tuple[str, str], ...]
type PyValue = dict[str, "PyLeaf"]
type PyLeaf = int | list[int] | PyValue


class AltDoc(NamedTuple):
    """One alternate's FULL constructor input: entry, merge, and pipeline lanes."""

    entries: tuple[Entry, ...]
    merges: Dyads
    pipeline: IrTokenPipeline


class Norm(NamedTuple):
    """One product's law-normalized view of every constructor input it reads."""

    entries: tuple[Entry, ...]
    verdicts: tuple[str, ...]
    merges: Dyads
    pipeline: IrTokenPipeline


class Phase(NamedTuple):
    """One measured phase: aggregate process CPU and wall, separately."""

    cpu: float
    wall: float


class Row(NamedTuple):
    """One product × alternate-kind measurement, every lane separated."""

    product: str
    kind: str
    equal: bool
    verdict_delta: bool
    replay: Phase
    build: Phase
    compare: Phase
    fast_accept: Phase
    normalize: Phase
    document_compare: Phase
    chosen: Phase
    fast_accept_hit: bool


def _timed[Result](work: Callable[[], Result]) -> tuple[Result, Phase]:
    """Run one phase, reporting process CPU and wall separately."""
    cpu = time.process_time()
    wall = time.perf_counter()
    result = work()
    return result, Phase(time.process_time() - cpu, time.perf_counter() - wall)


def parse_entries(count: int) -> Entries:
    """Real generic-grammar entries: parse the catalog document once."""
    text = "".join(f"k{index}={index};" for index in range(count))
    compiled = compile_text(CATALOG)
    model = compiled.parse(text, cores=1)
    return _model_entries(model)


def _model_entries(model: GrammarModel) -> Entries:
    """Read (key, value) pairs out of the real parsed model."""
    rows = getattr(model, "entry")
    entries: Entries = []
    for row in rows:
        key = getattr(row, "key").to_text()
        value = getattr(row, "value").to_text()
        entries.append((key, int(value)))
    return entries


def make_alternate(doc: AltDoc, kind: str) -> AltDoc:
    """One alternate document — the semantic replay's output, every lane."""
    entries = list(doc.entries)
    at = len(entries) // 3
    if kind == "equal":
        return AltDoc(tuple(entries), doc.merges, doc.pipeline)
    if kind in ("value", "projected"):
        key, value = entries[at]
        entries[at] = (key, value + 1_000_000)
        return AltDoc(tuple(entries), doc.merges, doc.pipeline)
    if kind == "key":
        _key, value = entries[at]
        entries[at] = ("zzalternate", value)
        return AltDoc(tuple(entries), doc.merges, doc.pipeline)
    if kind == "duplicate":
        entries.append((entries[at][0], entries[at][1] + 5))
        return AltDoc(tuple(entries), doc.merges, doc.pipeline)
    if kind == "ordinal":
        entries[at] = (entries[at][0], entries[0][1])
        return AltDoc(tuple(entries), doc.merges, doc.pipeline)
    if kind == "merges":
        if len(doc.merges) < 2:
            raise UnsupportedConstructError("keyed rows: too few merges to reorder")
        reordered = (doc.merges[1], doc.merges[0]) + doc.merges[2:]
        return AltDoc(tuple(entries), reordered, doc.pipeline)
    if kind == "merge-dup":
        if not doc.merges:
            raise UnsupportedConstructError("keyed rows: no merge to duplicate")
        return AltDoc(tuple(entries), doc.merges + (doc.merges[0],), doc.pipeline)
    if kind == "special":
        return AltDoc(
            tuple(entries),
            doc.merges,
            IrTokenPipeline(specials=IrTuple(IrStr("zz-not-a-token"))),
        )
    if kind == "pipeline":
        if len(doc.pipeline.specials):
            return AltDoc(tuple(entries), doc.merges, IrTokenPipeline())
        return AltDoc(
            tuple(entries),
            doc.merges,
            IrTokenPipeline(specials=IrTuple(IrStr(entries[0][0]))),
        )
    raise UnsupportedConstructError(f"keyed rows: unknown alternate {kind!r}")


def project(doc: AltDoc, kind: str) -> AltDoc:
    """The projected-away alternate: discard the changed entry occurrence."""
    if kind != "projected":
        return doc
    at = len(doc.entries) // 3
    victim = doc.entries[at][0] if at < len(doc.entries) else ""
    return AltDoc(
        tuple((key, value) for key, value in doc.entries if key != victim),
        doc.merges,
        doc.pipeline,
    )


class KeyedProduct[Carrier](Protocol):
    """What one keyed product must provide to be measured."""

    @property
    def name(self) -> str:
        """Row label."""
        ...

    @property
    def merge_sensitive(self) -> bool:
        """Whether the product's law consumes the merge lane."""
        ...

    @property
    def pipeline_sensitive(self) -> bool:
        """Whether the product's law consumes the pipeline lane."""
        ...

    def build(self, doc: AltDoc) -> tuple[Carrier, tuple[str, ...]]:
        """Construct the carrier plus its ordered verdict lane."""
        ...

    def compare(
        self,
        left: tuple[Carrier, tuple[str, ...]],
        right: tuple[Carrier, tuple[str, ...]],
    ) -> bool:
        """Exact equality under the product's law."""
        ...

    def normalized(self, doc: AltDoc) -> Norm:
        """The law-normalized view of EVERY constructor input this product
        consumes, including the ordered verdict lane."""
        ...


class PyProduct:
    """Recursive Python mapping under one declared duplicate policy.

    Its carrier consumes only the entry lane; the merge and pipeline lanes are
    not inputs of this constructor, so the normalized view holds them empty.
    """

    __slots__ = ("policy",)
    merge_sensitive = False
    pipeline_sensitive = False

    def __init__(self, policy: str) -> None:
        self.policy = policy

    @property
    def name(self) -> str:
        """Row label."""
        return f"python-{self.policy}"

    def build(self, doc: AltDoc) -> tuple[PyValue, tuple[str, ...]]:
        """Construct the recursive dict tree plus ordered duplicate verdicts."""
        carrier: PyValue = {}
        verdicts: list[str] = []
        for key, value in doc.entries:
            if key in carrier:
                if self.policy == "strict":
                    verdicts.append(key)
                    continue
                if self.policy == "first-wins":
                    continue
            carrier[key] = {"value": value, "meta": [value % 10]}
        return carrier, tuple(verdicts)

    def compare(
        self,
        left: tuple[PyValue, tuple[str, ...]],
        right: tuple[PyValue, tuple[str, ...]],
    ) -> bool:
        """Exact recursive equality including the ordered verdict lane."""
        return left == right

    def normalized(self, doc: AltDoc) -> Norm:
        """Policy applied, then key order dropped; no merge/pipeline input."""
        staged: dict[str, int] = {}
        verdicts: list[str] = []
        for key, value in doc.entries:
            if key in staged:
                if self.policy == "strict":
                    verdicts.append(key)
                    continue
                if self.policy == "first-wins":
                    continue
            staged[key] = value
        return Norm(
            tuple(sorted(staged.items())), tuple(verdicts), (), IrTokenPipeline()
        )


class IrMapProduct:
    """The real `IrMap` law: IR leaves, canonical order, duplicate refusal."""

    __slots__ = ()
    name = "irmap"
    merge_sensitive = False
    pipeline_sensitive = False

    def build(self, doc: AltDoc) -> tuple[IrMap | None, tuple[str, ...]]:
        """Construct the canonical map; a duplicate is the ordered verdict."""
        try:
            table = IrMap.from_table(
                (IrStr(key), IrChr(value)) for key, value in doc.entries
            )
        except UnsupportedConstructError as error:
            return None, (str(error),)
        return table, ()

    def compare(
        self,
        left: tuple[IrMap | None, tuple[str, ...]],
        right: tuple[IrMap | None, tuple[str, ...]],
    ) -> bool:
        """Real order-insensitive IrMap equality plus the verdict lane."""
        return left == right

    def normalized(self, doc: AltDoc) -> Norm:
        """Key-sorted unique entries; the repr-first duplicate is the verdict."""
        duplicate = _first_duplicate_spelling(doc.entries)
        if duplicate is not None:
            return Norm(
                (),
                (f"IrMap: duplicate key {IrStr(duplicate)!r}",),
                (),
                IrTokenPipeline(),
            )
        return Norm(tuple(sorted(doc.entries)), (), (), IrTokenPipeline())


def _first_duplicate_spelling(entries: Sequence[Entry]) -> str | None:
    """The repr-smallest repeated spelling, or ``None`` when all are distinct.

    `IrMap.from_table` sorts by ``repr(key)`` before indexing, so the key it
    names on a refusal is the repr-smallest duplicated one — not the first in
    document order. The O(n) membership scan runs first so the repr pass is
    paid only when a duplicate actually exists.
    """
    seen: set[str] = set()
    repeated: set[str] = set()
    for key, _value in entries:
        if key in seen:
            repeated.add(key)
        seen.add(key)
    if not repeated:
        return None
    return min(repeated, key=lambda key: repr(IrStr(key)))


def _first_duplicate_dyad(merges: Dyads) -> tuple[str, str] | None:
    """The repr-smallest repeated merge dyad, or ``None``."""
    seen: set[tuple[str, str]] = set()
    repeated: set[tuple[str, str]] = set()
    for dyad in merges:
        if dyad in seen:
            repeated.add(dyad)
        seen.add(dyad)
    if not repeated:
        return None
    return min(repeated, key=lambda dyad: repr(_ir_dyad(dyad)))


def _ir_dyad(dyad: tuple[str, str]) -> IrTuple:
    """One merge dyad as the spine record the rank index keys on."""
    return IrTuple(IrStr(dyad[0]), IrStr(dyad[1]))


def _first_duplicate_ordinal(ordinals: Iterable[int]) -> int | None:
    """The repr-smallest repeated token ordinal, or ``None``."""
    seen: set[int] = set()
    repeated: set[int] = set()
    for ordinal in ordinals:
        if ordinal in seen:
            repeated.add(ordinal)
        seen.add(ordinal)
    if not repeated:
        return None
    return min(repeated, key=lambda ordinal: repr(IrChr(ordinal)))


def _missing_special(pipeline: IrTokenPipeline, vocab: dict[str, int]) -> str | None:
    """The first pipeline special absent from the vocabulary, in order."""
    for spelling in pipeline.specials:
        if str(spelling) not in vocab:
            return str(spelling)
    return None


class MergesTokenizerProduct:
    """The shipped `IrTokenizer.from_merges` tail, verdict order included.

    Reachable refusals, in the order the constructor evaluates them:

    1. duplicate merge dyad, inside ``_rank_map``'s ``IrMap.from_table``;
    2. a pipeline special outside the vocabulary, inside ``_build``;
    3. duplicate token ordinal, when ``_build`` derives the inverse map.

    A repeated SPELLING never reaches the constructor: ``Vocab`` is a
    ``Mapping``, so Python's own last-wins already resolved it. That is a real
    divergence from the intended `from_indexes` tail, which refuses it.
    """

    __slots__ = ()
    name = "tokenizer-merges"
    merge_sensitive = True
    pipeline_sensitive = True

    def build(self, doc: AltDoc) -> tuple[IrTokenizer | None, tuple[str, ...]]:
        """One complete ready tokenizer through the real constructor tail."""
        vocab = dict(doc.entries)
        try:
            built = IrTokenizer.from_merges(
                TOKENIZER_NAME, vocab, list(doc.merges), doc.pipeline
            )
        except UnsupportedConstructError as error:
            return None, (str(error),)
        return built, ()

    def compare(
        self,
        left: tuple[IrTokenizer | None, tuple[str, ...]],
        right: tuple[IrTokenizer | None, tuple[str, ...]],
    ) -> bool:
        """Whole-record equality: name/encode/decode/ranks/pipeline/segmenter."""
        return left == right

    def normalized(self, doc: AltDoc) -> Norm:
        """Every constructor input, plus the first verdict in constructor order."""
        vocab = dict(doc.entries)
        verdict = _merges_verdict(doc, vocab)
        if verdict is not None:
            return Norm((), (verdict,), (), IrTokenPipeline())
        return Norm(tuple(sorted(vocab.items())), (), doc.merges, doc.pipeline)


def _merges_verdict(doc: AltDoc, vocab: dict[str, int]) -> str | None:
    """The first `from_merges` refusal message, or ``None`` when it succeeds."""
    dyad = _first_duplicate_dyad(doc.merges)
    if dyad is not None:
        return f"IrMap: duplicate key {_ir_dyad(dyad)!r}"
    special = _missing_special(doc.pipeline, vocab)
    if special is not None:
        return f"tokenizer: special {special!r} is not in the vocab"
    ordinal = _first_duplicate_ordinal(vocab.values())
    if ordinal is not None:
        return f"IrMap: duplicate key {IrChr(ordinal)!r}"
    return None


class Indexes(NamedTuple):
    """The three already-built tokenizer indexes plus the pipeline.

    What the intended `from_indexes` tail receives: no inverse derivation, no
    rank re-indexing, no dyad materialization.
    """

    encode: tuple[Entry, ...]
    decode: tuple[tuple[int, str], ...]
    ranks: tuple[tuple[tuple[str, str], int], ...]
    pipeline: IrTokenPipeline
    segmenter: IrSegmenter


def indexes_of(doc: AltDoc) -> Indexes:
    """Stream one document into the three index builders, in document order."""
    return Indexes(
        doc.entries,
        tuple((ordinal, spelling) for spelling, ordinal in doc.entries),
        tuple((dyad, rank) for rank, dyad in enumerate(doc.merges)),
        doc.pipeline,
        # The segmenter is a DECLARED builder input, not derived from the rank
        # index: `from_merges` means the ranked merge even with zero merges.
        IrRankedMerge(),
    )


def from_indexes(name: str, indexes: Indexes) -> IrTokenizer:
    """The intended final tail — validate three built indexes and construct.

    Ordered validation, each refusal naming its own lane:

    1. duplicate spelling in the encode index;
    2. duplicate ordinal in the decode index;
    3. encode/decode bijection (equal cardinality, mutually inverse);
    4. duplicate dyad in the rank index;
    5. contiguous ranks — exactly ``0 .. n-1``;
    6. pipeline references — every special is a vocabulary spelling;
    7. segmenter consistency — a non-empty rank index requires the ranked
       merge. The converse is NOT checked: `from_merges` declares the ranked
       merge for an empty merge list, so an empty rank index says nothing
       about the model.

    :param name: The registry name.
    :param indexes: The three built indexes plus pipeline and segmenter.
    :returns: The ready tokenizer.
    :raises FieldValidationError: On any validation above, in that order.
    """
    duplicate = _first_duplicate_spelling(indexes.encode)
    if duplicate is not None:
        raise FieldValidationError(f"tokenizer: duplicate spelling {duplicate!r}")
    repeated = _first_duplicate_ordinal(ordinal for ordinal, _s in indexes.decode)
    if repeated is not None:
        raise FieldValidationError(f"tokenizer: duplicate ordinal {repeated!r}")
    forward = dict(indexes.encode)
    inverse = dict(indexes.decode)
    if len(forward) != len(inverse) or any(
        inverse.get(ordinal) != spelling for spelling, ordinal in forward.items()
    ):
        raise FieldValidationError("tokenizer: encode and decode are not inverse")
    dyad = _first_duplicate_dyad(tuple(pair for pair, _rank in indexes.ranks))
    if dyad is not None:
        raise FieldValidationError(f"tokenizer: duplicate merge dyad {dyad!r}")
    ranks = sorted(rank for _dyad, rank in indexes.ranks)
    if ranks != list(range(len(ranks))):
        raise FieldValidationError("tokenizer: merge ranks are not contiguous from 0")
    special = _missing_special(indexes.pipeline, forward)
    if special is not None:
        raise FieldValidationError(
            f"tokenizer: special {special!r} is not in the vocab"
        )
    if indexes.ranks and not isinstance(indexes.segmenter, IrRankedMerge):
        raise FieldValidationError("tokenizer: segmenter disagrees with the ranks")
    return CONSTRUCT_TOKENIZER(
        IrStr(name),
        IrMap.from_table((IrStr(s), IrChr(i)) for s, i in indexes.encode),
        IrMap.from_table((IrChr(i), IrStr(s)) for i, s in indexes.decode),
        IrMap.from_table((_ir_dyad(d), IrInt(r)) for d, r in indexes.ranks),
        indexes.pipeline,
        indexes.segmenter,
    )


class IndexTokenizerProduct:
    """The intended `from_indexes` tail and its document-level twin."""

    __slots__ = ()
    name = "tokenizer-indexes"
    merge_sensitive = True
    pipeline_sensitive = True

    def build(self, doc: AltDoc) -> tuple[IrTokenizer | None, tuple[str, ...]]:
        """Stream the indexes and construct through the validating tail."""
        try:
            built = from_indexes(TOKENIZER_NAME, indexes_of(doc))
        except FieldValidationError as error:
            return None, (str(error),)
        return built, ()

    def compare(
        self,
        left: tuple[IrTokenizer | None, tuple[str, ...]],
        right: tuple[IrTokenizer | None, tuple[str, ...]],
    ) -> bool:
        """Whole-record equality plus the ordered verdict lane."""
        return left == right

    def normalized(self, doc: AltDoc) -> Norm:
        """Every constructor input, plus the first verdict in declared order."""
        verdict = _indexes_verdict(doc)
        if verdict is not None:
            return Norm((), (verdict,), (), IrTokenPipeline())
        return Norm(tuple(sorted(doc.entries)), (), doc.merges, doc.pipeline)


def _indexes_verdict(doc: AltDoc) -> str | None:
    """The first `from_indexes` refusal message, without constructing.

    The bijection, contiguity, and segmenter lanes are unreachable from a
    DOCUMENT — `indexes_of` derives decode from encode, numbers ranks by
    position, and picks the segmenter from the rank index — so they carry no
    document-level twin. `prove_index_lane_coverage` exercises them directly
    against the constructor, which is where independently supplied indexes can
    break them.
    """
    duplicate = _first_duplicate_spelling(doc.entries)
    if duplicate is not None:
        return f"tokenizer: duplicate spelling {duplicate!r}"
    ordinal = _first_duplicate_ordinal(value for _key, value in doc.entries)
    if ordinal is not None:
        return f"tokenizer: duplicate ordinal {ordinal!r}"
    dyad = _first_duplicate_dyad(doc.merges)
    if dyad is not None:
        return f"tokenizer: duplicate merge dyad {dyad!r}"
    special = _missing_special(doc.pipeline, dict(doc.entries))
    if special is not None:
        return f"tokenizer: special {special!r} is not in the vocab"
    return None


KINDS = (
    "equal",
    "value",
    "key",
    "duplicate",
    "ordinal",
    "projected",
    "merges",
    "merge-dup",
    "special",
    "pipeline",
)


def _expect_equal(
    merge_sensitive: bool, pipeline_sensitive: bool, kind: str
) -> bool | None:
    """The expected verdict, or None where the product's policy decides."""
    if kind in ("equal", "projected"):
        return True
    if kind in ("merges", "merge-dup"):
        return not merge_sensitive
    if kind in ("pipeline", "special"):
        return not pipeline_sensitive
    if kind in ("duplicate", "ordinal"):
        return None
    return False


def measure[Carrier](product: KeyedProduct[Carrier], doc: AltDoc, kind: str) -> Row:
    """One product × alternate row, every lane separated."""
    alternate, replay = _timed(lambda: make_alternate(doc, kind))
    base_view = project(doc, kind)
    alt_view = project(alternate, kind)

    baseline, _base_build = _timed(lambda: product.build(base_view))
    built, build = _timed(lambda: product.build(alt_view))
    equal, compare = _timed(lambda: product.compare(baseline, built))

    # The fast accept IS part of the document lane and is timed as such: at
    # Qwen scale it walks every entry, merge, and pipeline field.
    fast_hit, fast_accept = _timed(lambda: alt_view == base_view)
    (base_norm, alt_norm), normalize = _timed(
        lambda: (
            ((), ())
            if fast_hit
            else (product.normalized(base_view), product.normalized(alt_view))
        )
    )
    document_equal, document_compare = _timed(
        lambda: True if fast_hit else base_norm == alt_norm
    )
    if document_equal != equal:
        raise UnsupportedConstructError(
            f"keyed rows: {product.name}/{kind} document-level verdict diverged"
        )
    chosen_input = base_view if document_equal else alt_view
    _chosen, chosen = _timed(lambda: product.build(chosen_input))
    verdict_delta = baseline[1] != built[1]
    return Row(
        product.name,
        kind,
        equal,
        verdict_delta,
        replay,
        build,
        compare,
        fast_accept,
        normalize,
        document_compare,
        chosen,
        fast_hit,
    )


def _print_row(row: Row) -> None:
    """One aligned output row."""
    print(
        row.product,
        row.kind,
        f"equal={row.equal}",
        f"verdict_delta={row.verdict_delta}",
        f"replay_cpu={row.replay.cpu:.6f}",
        f"build_cpu={row.build.cpu:.6f}",
        f"compare_cpu={row.compare.cpu:.6f}",
        f"cold_total_cpu={row.build.cpu + row.compare.cpu:.6f}",
        f"fast_accept_cpu={row.fast_accept.cpu:.6f}",
        f"normalize_cpu={row.normalize.cpu:.6f}",
        f"document_compare_cpu={row.document_compare.cpu:.6f}",
        "document_total_cpu="
        + f"{row.fast_accept.cpu + row.normalize.cpu + row.document_compare.cpu:.6f}",
        f"chosen_construction_cpu={row.chosen.cpu:.6f}",
        f"fast_accept={row.fast_accept_hit}",
        f"build_wall={row.build.wall:.6f}",
        sep="\t",
    )


def _retained_bytes[Carrier](product: KeyedProduct[Carrier], doc: AltDoc) -> int:
    """tracemalloc-attributed bytes of one constructed carrier."""
    tracemalloc.start()
    built = product.build(doc)
    size, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert built is not None
    return size


def _normalized_bytes[Carrier](product: KeyedProduct[Carrier], doc: AltDoc) -> int:
    """tracemalloc-attributed bytes of one normalized document view."""
    tracemalloc.start()
    view = product.normalized(doc)
    size, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert view is not None
    return size


def _product_rows[Carrier](
    product: KeyedProduct[Carrier], doc: AltDoc, kinds: tuple[str, ...]
) -> None:
    """Every alternate-kind row plus retained bytes, one product."""
    for kind in kinds:
        row = measure(product, doc, kind)
        expected = _expect_equal(
            product.merge_sensitive, product.pipeline_sensitive, kind
        )
        assert expected is None or row.equal == expected, (product.name, kind)
        _print_row(row)
    print(
        product.name,
        "retained_bytes",
        f"carrier={_retained_bytes(product, doc)}",
        f"normalized_view={_normalized_bytes(product, doc)}",
        sep="\t",
    )


def _tiny_documents() -> tuple[tuple[str, AltDoc], ...]:
    """A small exhaustive family: valid, and one defect per constructor lane."""
    base = (("a", 0), ("b", 1), ("c", 2))
    dyads: Dyads = (("a", "b"), ("b", "c"))
    plain = IrTokenPipeline()
    bad_one = IrTokenPipeline(specials=IrTuple(IrStr("zz")))
    bad_two = IrTokenPipeline(specials=IrTuple(IrStr("yy")))
    good = IrTokenPipeline(specials=IrTuple(IrStr("a")))
    dup_ord_low = (("a", 0), ("b", 0), ("c", 2))
    dup_ord_high = (("a", 0), ("b", 1), ("c", 1))
    dup_spelling = (("a", 0), ("b", 1), ("a", 3))
    dup_dyad_ab = dyads + (("a", "b"),)
    dup_dyad_bc = dyads + (("b", "c"),)
    return (
        ("valid", AltDoc(base, dyads, plain)),
        ("valid-specials", AltDoc(base, dyads, good)),
        ("valid-no-merges", AltDoc(base, (), plain)),
        ("valid-reordered-merges", AltDoc(base, dyads[::-1], plain)),
        ("valid-other-value", AltDoc((("a", 0), ("b", 7), ("c", 2)), dyads, plain)),
        ("dup-ordinal-low", AltDoc(dup_ord_low, dyads, plain)),
        ("dup-ordinal-high", AltDoc(dup_ord_high, dyads, plain)),
        ("dup-spelling", AltDoc(dup_spelling, dyads, plain)),
        ("dup-dyad-ab", AltDoc(base, dup_dyad_ab, plain)),
        ("dup-dyad-bc", AltDoc(base, dup_dyad_bc, plain)),
        ("bad-special-zz", AltDoc(base, dyads, bad_one)),
        ("bad-special-yy", AltDoc(base, dyads, bad_two)),
        ("dup-dyad-and-bad-special", AltDoc(base, dup_dyad_ab, bad_one)),
        ("dup-dyad-and-other-special", AltDoc(base, dup_dyad_ab, bad_two)),
        ("bad-special-and-dup-ordinal-low", AltDoc(dup_ord_low, dyads, bad_one)),
        ("bad-special-and-dup-ordinal-high", AltDoc(dup_ord_high, dyads, bad_one)),
        ("dup-spelling-and-bad-special", AltDoc(dup_spelling, dyads, bad_one)),
        ("dup-spelling-and-dup-dyad", AltDoc(dup_spelling, dup_dyad_ab, plain)),
        # A merge dyad naming spellings absent from the vocabulary: neither
        # tail validates it, so both accept — the pair still has to agree.
        ("dangling-merge-reference", AltDoc(base, ((("q", "z"),)), plain)),
        (
            "dangling-merge-reference-other",
            AltDoc(base, ((("q", "w"),)), plain),
        ),
    )


def prove_exhaustive_pairs() -> None:
    """Every ordered pair of the tiny family, both tokenizer constructors.

    The reference is the COMPLETE result relation: two documents agree exactly
    when their constructed results agree AND their ordered verdicts agree, so
    equal refusals count as agreement and differing first verdicts do not.
    """
    documents = _tiny_documents()
    for product in (MergesTokenizerProduct(), IndexTokenizerProduct()):
        refusals = 0
        both_refuse_equal = 0
        both_refuse_different = 0
        for (left_name, left), (right_name, right) in cross(documents, documents):
            built_left = product.build(left)
            built_right = product.build(right)
            constructed = product.compare(built_left, built_right)
            document = product.normalized(left) == product.normalized(right)
            assert constructed == document, (
                product.name,
                left_name,
                right_name,
                built_left[1],
                built_right[1],
            )
            if built_left[1] and built_right[1]:
                refusals += 1
                if built_left[1] == built_right[1]:
                    both_refuse_equal += 1
                else:
                    both_refuse_different += 1
        print(
            "exhaustive-pairs",
            product.name,
            f"documents={len(documents)}",
            f"pairs={len(documents) ** 2}",
            f"both_refuse={refusals}",
            f"both_refuse_equal={both_refuse_equal}",
            f"both_refuse_different_first_verdict={both_refuse_different}",
            "document-level verdict == constructed-result verdict on every pair",
            sep="\t",
        )


def prove_index_lane_coverage() -> None:
    """Every `from_indexes` validation refuses, including the document-free ones."""
    entries = (("a", 0), ("b", 1))
    decode = ((0, "a"), (1, "b"))
    ranks = ((("a", "b"), 0),)
    plain = IrTokenPipeline()
    good = Indexes(entries, decode, ranks, plain, IrRankedMerge())
    assert from_indexes("cover", good) is not None
    broken = (
        (
            "duplicate spelling",
            Indexes((("a", 0), ("a", 1)), decode, ranks, plain, IrRankedMerge()),
        ),
        (
            "duplicate ordinal",
            Indexes(entries, ((0, "a"), (0, "b")), ranks, plain, IrRankedMerge()),
        ),
        (
            "encode and decode are not inverse",
            Indexes(entries, ((0, "a"), (1, "z")), ranks, plain, IrRankedMerge()),
        ),
        (
            "duplicate merge dyad",
            Indexes(
                entries,
                decode,
                ((("a", "b"), 0), (("a", "b"), 1)),
                plain,
                IrRankedMerge(),
            ),
        ),
        (
            "merge ranks are not contiguous",
            Indexes(entries, decode, ((("a", "b"), 3),), plain, IrRankedMerge()),
        ),
        (
            "is not in the vocab",
            Indexes(
                entries,
                decode,
                ranks,
                IrTokenPipeline(specials=IrTuple(IrStr("zz"))),
                IrRankedMerge(),
            ),
        ),
        (
            "segmenter disagrees",
            Indexes(entries, decode, ranks, plain, IrLongestMatch()),
        ),
    )
    for expected, indexes in broken:
        try:
            from_indexes("cover", indexes)
        except FieldValidationError as error:
            assert expected in str(error), (expected, str(error))
            continue
        raise AssertionError(f"from_indexes accepted a broken index: {expected}")
    print(
        "index-lane-coverage",
        f"validations={len(broken)}",
        "duplicate spelling, duplicate ordinal, bijection, duplicate dyad,"
        " rank contiguity, special membership, segmenter consistency — all"
        " refuse; the bijection, contiguity, and segmenter lanes are"
        " unreachable from a document and therefore carry no document-level"
        " twin",
        sep="\t",
    )


def prove_constructor_parity() -> None:
    """The `from_indexes` candidate builds the SAME record as `from_merges`.

    Where the two tails disagree the divergence is declared, not accidental:
    a repeated spelling is Python last-wins before `from_merges` sees it and a
    refusal for `from_indexes`, which also reports it ahead of a later lane.
    """
    agreed = 0
    acceptance: list[str] = []
    verdict: list[str] = []
    for name, doc in _tiny_documents():
        merges_built = MergesTokenizerProduct().build(doc)
        index_built = IndexTokenizerProduct().build(doc)
        if (merges_built[0] is None) != (index_built[0] is None):
            acceptance.append(name)
            continue
        if merges_built[0] is not None and index_built[0] is not None:
            assert merges_built[0] == index_built[0], name
            agreed += 1
            continue
        if merges_built[1] != index_built[1]:
            verdict.append(name)
    assert acceptance == ["dup-spelling"], acceptance
    assert verdict == [
        "dup-ordinal-low",
        "dup-ordinal-high",
        "dup-dyad-ab",
        "dup-dyad-bc",
        "dup-dyad-and-bad-special",
        "dup-dyad-and-other-special",
        "bad-special-and-dup-ordinal-low",
        "bad-special-and-dup-ordinal-high",
        "dup-spelling-and-bad-special",
        "dup-spelling-and-dup-dyad",
    ], verdict
    print(
        "constructor-parity",
        f"identical_records={agreed}",
        f"acceptance_divergences={acceptance}",
        f"verdict_message_divergences={len(verdict)}",
        "from_merges takes a Mapping, so a repeated spelling is resolved by"
        " Python last-wins before it; from_indexes streams pairs, refuses it,"
        " and orders the vocabulary lanes ahead of the merge lane — both"
        " divergences are declared contract, not accident",
        sep="\t",
    )


def prove_unvalidated_lanes() -> None:
    """What neither tail validates today — reported, not silently assumed."""
    negative = IrTokenizer.from_merges("audit", {"a": -1, "b": 1}, [("a", "b")])
    sparse = IrTokenizer.from_merges("audit", {"a": 0, "b": 900}, [("a", "b")])
    assert int(negative.encode[IrStr("a")]) == -1
    assert sparse.universe == 900
    dangling = IrTokenizer.from_merges("audit", {"a": 0, "b": 1}, [("q", "z")])
    assert len(dangling.ranks) == 1
    unknown = IrTokenizer.from_merges(
        "audit",
        {"a": 0, "b": 1},
        [("a", "b")],
        IrTokenPipeline(unknown=IrUnknown(IrStr("<absent>"))),
    )
    assert unknown.encode.get(IrStr("<absent>")) is None
    indexed = from_indexes(
        "audit",
        Indexes(
            (("a", 0), ("b", 1)),
            ((0, "a"), (1, "b")),
            ((("q", "z"), 0),),
            IrTokenPipeline(unknown=IrUnknown(IrStr("<absent>"))),
            IrRankedMerge(),
        ),
    )
    assert len(indexed.ranks) == 1
    print(
        "unvalidated-lanes",
        "three lanes are unchecked by BOTH tails and are declared, not"
        " assumed: the ordinal domain (a negative id and a sparse id space"
        " both construct), merge REFERENCES (a dyad naming spellings absent"
        " from the vocabulary constructs), and the pipeline's byte-fallback"
        " table and unknown spelling (an unknown outside the vocabulary"
        " constructs); only pipeline SPECIALS are validated",
        sep="\t",
    )


def generic_rows(count: int) -> None:
    """Small/medium rows over the real parsed catalog entries."""
    entries = parse_entries(count)
    merges: Dyads = tuple(
        (entries[index][0], entries[index + 1][0]) for index in range(0, 40, 2)
    )
    doc = AltDoc(tuple(entries), merges, IrTokenPipeline())
    print(f"### catalog entries={len(entries)} merges={len(merges)}")
    _product_rows(PyProduct("last-wins"), doc, KINDS)
    _product_rows(PyProduct("strict"), doc, KINDS)
    _product_rows(PyProduct("first-wins"), doc, KINDS)
    _product_rows(IrMapProduct(), doc, KINDS)
    _product_rows(MergesTokenizerProduct(), doc, KINDS)
    _product_rows(IndexTokenizerProduct(), doc, KINDS)


def qwen_rows() -> None:
    """The real fixture's cardinalities: run alone under tools/guarded.sh."""
    source = (
        Path(__file__).resolve().parents[3]
        / "resources"
        / "tokenizers"
        / "qwen3.tokenizer.json"
    )
    if not source.exists():
        print("qwen\tSKIP: fixture not fetched")
        return
    setup_cpu = time.process_time()
    setup_wall = time.perf_counter()
    tokenizer = read(
        source.read_text(encoding="utf-8"), JSON_GRAMMAR, JSON_REDUCER, name="qwen3"
    )
    print(
        "qwen-reader-setup",
        f"cpu={time.process_time() - setup_cpu:.6f}",
        f"wall={time.perf_counter() - setup_wall:.6f}",
        sep="\t",
    )
    entries: tuple[Entry, ...] = tuple(
        (str(spelling), int(ordinal)) for spelling, ordinal in tokenizer.encode.items()
    )
    merges: Dyads = tuple(
        (str(dyad[0]), str(dyad[1]))
        for dyad, _rank in sorted(tokenizer.ranks.items(), key=lambda kv: int(kv[1]))
    )
    doc = AltDoc(entries, merges, tokenizer.pipeline)
    print(
        "qwen-doc",
        f"entries={len(entries)}",
        f"merges={len(merges)}",
        f"pipeline_specials={len(tokenizer.pipeline.specials)}",
        sep="\t",
    )
    _product_rows(PyProduct("last-wins"), doc, KINDS)
    _product_rows(IrMapProduct(), doc, KINDS)
    _product_rows(MergesTokenizerProduct(), doc, KINDS)
    _product_rows(IndexTokenizerProduct(), doc, KINDS)


def main(arguments: Sequence[str] | None = None) -> None:
    """Run the generic rows, or the isolated Qwen row."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="generic")
    options = parser.parse_args(arguments)
    if options.mode == "qwen":
        prove_exhaustive_pairs()
        qwen_rows()
        return
    if options.mode != "generic":
        raise UnsupportedConstructError(f"keyed rows: unknown mode {options.mode!r}")
    prove_exhaustive_pairs()
    prove_index_lane_coverage()
    prove_constructor_parity()
    prove_unvalidated_lanes()
    generic_rows(128)
    generic_rows(8192)
    print(
        "conclusion",
        "the cold fallback is priced per REAL product over EVERY constructor"
        " input; the tokenizer document-level view now carries the complete"
        " ordered validation relation for both the shipped from_merges tail"
        " and the intended from_indexes tail, message for message, and is"
        " asserted against the constructed results on every measured row and"
        " on every ordered pair of the exhaustive tiny family",
        sep="\t",
    )


if __name__ == "__main__":
    main()
