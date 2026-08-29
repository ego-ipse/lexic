"""Price the REAL keyed products' ambiguity comparison, law by law.

The prior cold row priced one plain `dict[str, int]`. This file builds the
actual candidate result for each distinct law and measures, per product and
per alternate kind (equal, changed-value, key-set-changing, duplicate,
projected-away, merge-order), separating:

- semantic replay (producing the alternate's document: entry stream + merge
  stream);
- final carrier construction (the real recursive `dict` tree, `IrMap` with
  real IR leaves, or ready `IrTokenizer` through `from_merges` WITH the
  pipeline);
- exact comparison on the constructed carriers (the cold eager fallback);
- the exact document-level alternative: a full-input equality fast ACCEPT
  (an O(n) comparison of every constructor input — sound because carrier
  construction is a deterministic function of ALL its inputs; never used to
  prove inequality) plus a law-normalized comparison per lane: vocab entries
  key-sorted with the duplicate policy applied (order-insensitive lane),
  merges kept in sequence (rank = position, order-sensitive lane), the
  pipeline record compared directly — with a pipeline-differing alternate
  kind exercising that lane at every scale.

Every row asserts the document-level verdict equals the constructed-carrier
verdict. Entry streams come from real parses of a generic non-JSON catalog
grammar (128 and 8,192 entries); `--mode qwen` uses the real reader's
encode/rank/pipeline and runs alone under `tools/guarded.sh`. JSON/Qwen are
witnesses, never a privileged implementation.
"""

from __future__ import annotations

import argparse
import time
import tracemalloc
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple, Protocol

from lexic.api.json_tokenizer import read
from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrChr, IrMap, IrStr, IrTokenizer, IrTuple
from lexic.ir.text.pipeline import IrTokenPipeline
from lexic.model import GrammarModel

CATALOG = (
    "doc ::= entry+\n"
    'entry ::= key "=" value ";"\n'
    "key ::= [a-z] [a-z0-9]*\n"
    "value ::= [0-9]+\n"
)

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


class Phase(NamedTuple):
    """One measured phase: aggregate process CPU and wall, separately."""

    cpu: float
    wall: float


class Row(NamedTuple):
    """One product × alternate-kind measurement."""

    product: str
    kind: str
    equal: bool
    verdict_delta: bool
    replay: Phase
    build: Phase
    compare: Phase
    document_level: Phase
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
    """One alternate document — the semantic replay's output, both lanes."""
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
    if kind == "merges":
        if len(doc.merges) < 2:
            raise UnsupportedConstructError("keyed rows: too few merges to reorder")
        reordered = (doc.merges[1], doc.merges[0]) + doc.merges[2:]
        return AltDoc(tuple(entries), reordered, doc.pipeline)
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

    def normalized(
        self, doc: AltDoc
    ) -> tuple[Entries, tuple[str, ...], Dyads, IrTokenPipeline]:
        """The law-normalized view of EVERY constructor input this product
        consumes: (entry lane normalized, verdicts, merge lane as consumed,
        pipeline lane as consumed)."""
        ...


class PyProduct:
    """Recursive Python mapping under one declared duplicate policy.

    Its carrier consumes only the entry lane; the merge lane is not an input
    of this constructor, so the normalized view holds it empty.
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

    def normalized(
        self, doc: AltDoc
    ) -> tuple[Entries, tuple[str, ...], Dyads, IrTokenPipeline]:
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
        return sorted(staged.items()), tuple(verdicts), (), IrTokenPipeline()


class IrMapProduct:
    """The real `IrMap` law: IR leaves, canonical order, duplicate refusal."""

    name = "irmap"
    merge_sensitive = False
    pipeline_sensitive = False

    def build(self, doc: AltDoc) -> tuple[IrMap, tuple[str, ...]]:
        """Construct the canonical map; a duplicate is the ordered verdict."""
        try:
            table = IrMap.from_table(
                (IrStr(key), IrChr(value)) for key, value in doc.entries
            )
        except UnsupportedConstructError as error:
            return IrMap(), (str(error),)
        return table, ()

    def compare(
        self,
        left: tuple[IrMap, tuple[str, ...]],
        right: tuple[IrMap, tuple[str, ...]],
    ) -> bool:
        """Real order-insensitive IrMap equality plus the verdict lane."""
        return left == right

    def normalized(
        self, doc: AltDoc
    ) -> tuple[Entries, tuple[str, ...], Dyads, IrTokenPipeline]:
        """Key-sorted unique entries; the first duplicate is the verdict."""
        seen: dict[str, int] = {}
        for key, value in doc.entries:
            if key in seen:
                return (
                    sorted(seen.items()),
                    (f"duplicate key {key!r}",),
                    (),
                    IrTokenPipeline(),
                )
            seen[key] = value
        return sorted(seen.items()), (), (), IrTokenPipeline()


class TokenizerProduct:
    """The ready `IrTokenizer`: encode, decode, ranks, pipeline, segmenter,
    root construction, and validation — every constructor input compared."""

    __slots__ = ()
    name = "tokenizer"
    merge_sensitive = True
    pipeline_sensitive = True

    def build(self, doc: AltDoc) -> tuple[IrTokenizer, tuple[str, ...]]:
        """One complete ready tokenizer through the real constructor tail.

        Duplicate spellings refuse inside the real `IrMap.from_table` the
        vocab map is built from; the refusal is the ordered verdict.
        """
        try:
            encode = IrMap.from_table(
                (IrStr(key), IrChr(value)) for key, value in doc.entries
            )
        except UnsupportedConstructError as error:
            return IrTokenizer.from_vocab("refused", {}), (str(error),)
        vocab = {str(key): int(value) for key, value in encode.items()}
        return (
            IrTokenizer.from_merges(
                "keyed-rows", vocab, list(doc.merges), doc.pipeline
            ),
            (),
        )

    def compare(
        self,
        left: tuple[IrTokenizer, tuple[str, ...]],
        right: tuple[IrTokenizer, tuple[str, ...]],
    ) -> bool:
        """Whole-record equality: name/encode/decode/ranks/pipeline/segmenter."""
        return left == right

    def normalized(
        self, doc: AltDoc
    ) -> tuple[Entries, tuple[str, ...], Dyads, IrTokenPipeline]:
        """Vocab lane order-insensitive (sorted, duplicate-refused); the merge
        lane is ORDER-SENSITIVE (rank = position) and kept as-is; the pipeline
        lane is compared directly (record equality)."""
        seen: dict[str, int] = {}
        for key, value in doc.entries:
            if key in seen:
                return (
                    sorted(seen.items()),
                    (f"duplicate key {key!r}",),
                    doc.merges,
                    doc.pipeline,
                )
            seen[key] = value
        return sorted(seen.items()), (), doc.merges, doc.pipeline


KINDS = ("equal", "value", "key", "duplicate", "projected", "merges", "pipeline")


def _expect_equal(
    merge_sensitive: bool, pipeline_sensitive: bool, kind: str
) -> bool | None:
    """The expected verdict, or None where the product's policy decides."""
    if kind in ("equal", "projected"):
        return True
    if kind == "merges":
        return not merge_sensitive
    if kind == "pipeline":
        return not pipeline_sensitive
    if kind == "duplicate":
        return None
    return False


def measure[Carrier](product: KeyedProduct[Carrier], doc: AltDoc, kind: str) -> Row:
    """One product × alternate row, phases separated, totals implied."""
    alternate, replay = _timed(lambda: make_alternate(doc, kind))
    base_view = project(doc, kind)
    alt_view = project(alternate, kind)

    baseline, _base_build = _timed(lambda: product.build(base_view))
    built, build = _timed(lambda: product.build(alt_view))
    equal, compare = _timed(lambda: product.compare(baseline, built))

    def document_level() -> tuple[bool, bool]:
        if alt_view == base_view:
            return True, True
        return product.normalized(base_view) == product.normalized(alt_view), False

    (document_equal, fast_hit), document_phase = _timed(document_level)
    if document_equal != equal:
        raise UnsupportedConstructError(
            f"keyed rows: {product.name}/{kind} document-level verdict diverged"
        )
    verdict_delta = baseline[1] != built[1]
    return Row(
        product.name,
        kind,
        equal,
        verdict_delta,
        replay,
        build,
        compare,
        document_phase,
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
        f"document_level_cpu={row.document_level.cpu:.6f}",
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


def _product_rows[Carrier](
    product: KeyedProduct[Carrier], doc: AltDoc, kinds: tuple[str, ...]
) -> None:
    """Every alternate-kind row plus the retained-carrier bytes, one product."""
    for kind in kinds:
        row = measure(product, doc, kind)
        expected = _expect_equal(
            product.merge_sensitive, product.pipeline_sensitive, kind
        )
        assert expected is None or row.equal == expected, (product.name, kind)
        _print_row(row)
    print(
        product.name,
        "retained_carrier_bytes",
        _retained_bytes(product, doc),
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
    _product_rows(TokenizerProduct(), doc, KINDS)


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
    _product_rows(TokenizerProduct(), doc, KINDS)


def main(arguments: Sequence[str] | None = None) -> None:
    """Run the generic rows, or the isolated Qwen row."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="generic")
    options = parser.parse_args(arguments)
    if options.mode == "qwen":
        qwen_rows()
        return
    if options.mode != "generic":
        raise UnsupportedConstructError(f"keyed rows: unknown mode {options.mode!r}")
    generic_rows(128)
    generic_rows(8192)
    print(
        "conclusion",
        "the cold fallback must be priced per REAL product over EVERY"
        " constructor input; the document-level exact comparison covers the"
        " vocab, merge, pipeline, and verdict lanes and is asserted against the"
        " constructed carriers on every row",
        sep="\t",
    )


if __name__ == "__main__":
    main()
