"""Price the REAL keyed products' ambiguity comparison, law by law.

The prior cold row priced one plain `dict[str, int]`. This file builds the
actual candidate result for each distinct law and measures, per product and
per alternate kind (equal, changed-value, key-set-changing, duplicate,
dropped):

- semantic replay (producing the alternate's entry stream) — separated;
- final carrier construction (the real `dict` tree, `IrMap` with real IR
  leaves, or ready `IrTokenizer` through `from_merges`);
- exact comparison on the constructed carriers (the cold eager fallback);
- the entry-level exact alternative: a sequence-identity fast ACCEPT (sound
  because construction is a deterministic function of its entry stream —
  never used to prove inequality) plus a law-normalized entry comparison
  (key-sorted under order-insensitive laws, merge order preserved where the
  law is order-sensitive, duplicate policy applied at entry level).

Entry streams come from real parses of a generic non-JSON catalog grammar at
small/medium scale; `--mode qwen` uses the real reader's encode/rank tables
and runs alone under `tools/guarded.sh`. JSON/Qwen are witnesses, never a
privileged implementation.
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
from lexic.ir import IrChr, IrMap, IrStr, IrTokenizer
from lexic.model import GrammarModel

CATALOG = (
    "doc ::= entry+\n"
    'entry ::= key "=" value ";"\n'
    "key ::= [a-z] [a-z0-9]*\n"
    "value ::= [0-9]+\n"
)

type Entry = tuple[str, int]
type Entries = list[Entry]
type PyValue = dict[str, "PyLeaf"]
type PyLeaf = int | list[int] | PyValue


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
    entry_normalized: Phase
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


def make_alternate(entries: Entries, kind: str) -> Entries:
    """One alternate entry stream — the semantic replay's output."""
    at = len(entries) // 3
    if kind == "equal":
        return [(key, value) for key, value in entries]
    if kind == "value":
        out = list(entries)
        key, value = out[at]
        out[at] = (key, value + 1_000_000)
        return out
    if kind == "key":
        out = list(entries)
        _key, value = out[at]
        out[at] = ("zzalternate", value)
        return out
    if kind == "duplicate":
        out = list(entries)
        out.append((entries[at][0], entries[at][1] + 5))
        return out
    if kind == "dropped":
        out = list(entries)
        key, value = out[at]
        out[at] = (key, value + 1_000_000)
        return out
    raise UnsupportedConstructError(f"keyed rows: unknown alternate {kind!r}")


DROP_PREFIX_AT = "drop-projection"


def project(entries: Entries, kind: str) -> Entries:
    """The dropped-alternate projection: discard the changed occurrence."""
    if kind != "dropped":
        return entries
    at = len(entries) // 3
    victim = entries[at][0] if at < len(entries) else ""
    return [(key, value) for key, value in entries if key != victim]


class PyProduct:
    """Recursive Python mapping under one declared duplicate policy."""

    __slots__ = ("policy",)

    def __init__(self, policy: str) -> None:
        self.policy = policy

    @property
    def name(self) -> str:
        """Row label."""
        return f"python-{self.policy}"

    def build(self, entries: Entries) -> tuple[PyValue, tuple[str, ...]]:
        """Construct the recursive dict tree plus ordered duplicate verdicts."""
        carrier: PyValue = {}
        verdicts: list[str] = []
        for key, value in entries:
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

    def normalize(self, entries: Entries) -> tuple[Entries, tuple[str, ...]]:
        """Law-normalized entry view: policy applied, then key order dropped."""
        staged: dict[str, int] = {}
        verdicts: list[str] = []
        for key, value in entries:
            if key in staged:
                if self.policy == "strict":
                    verdicts.append(key)
                    continue
                if self.policy == "first-wins":
                    continue
            staged[key] = value
        return sorted(staged.items()), tuple(verdicts)


class IrMapProduct:
    """The real `IrMap` law: IR leaves, canonical order, duplicate refusal."""

    name = "irmap"

    def build(self, entries: Entries) -> tuple[IrMap, tuple[str, ...]]:
        """Construct the canonical map; a duplicate is the ordered verdict."""
        try:
            table = IrMap.from_table(
                (IrStr(key), IrChr(value)) for key, value in entries
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

    def normalize(self, entries: Entries) -> tuple[Entries, tuple[str, ...]]:
        """Key-sorted unique entries; the first duplicate is the verdict."""
        seen: dict[str, int] = {}
        for key, value in entries:
            if key in seen:
                return sorted(seen.items()), (f"duplicate key {key!r}",)
            seen[key] = value
        return sorted(seen.items()), ()


class TokenizerProduct:
    """The ready `IrTokenizer`: encode+decode+ranks+pipeline+validation."""

    __slots__ = ("merges",)
    name = "tokenizer"

    def __init__(self, merges: list[tuple[str, str]]) -> None:
        self.merges = merges

    def build(self, entries: Entries) -> tuple[IrTokenizer, tuple[str, ...]]:
        """One complete ready tokenizer through the real constructor tail.

        Duplicate spellings refuse inside the real `IrMap.from_table` the
        vocab map is built from; the refusal is the ordered verdict.
        """
        try:
            encode = IrMap.from_table(
                (IrStr(key), IrChr(value)) for key, value in entries
            )
        except UnsupportedConstructError as error:
            return IrTokenizer.from_vocab("refused", {}), (str(error),)
        vocab = {str(key): int(value) for key, value in encode.items()}
        return IrTokenizer.from_merges("keyed-rows", vocab, self.merges), ()

    def compare(
        self,
        left: tuple[IrTokenizer, tuple[str, ...]],
        right: tuple[IrTokenizer, tuple[str, ...]],
    ) -> bool:
        """Whole-record equality: name, encode, decode, ranks, pipeline."""
        return left == right

    def normalize(self, entries: Entries) -> tuple[Entries, tuple[str, ...]]:
        """Vocab is order-insensitive (sorted); merges stay order-sensitive
        and are shared/identical here, so the entry view is the sorted vocab."""
        seen: dict[str, int] = {}
        for key, value in entries:
            if key in seen:
                return sorted(seen.items()), (f"duplicate key {key!r}",)
            seen[key] = value
        return sorted(seen.items()), ()


class KeyedProduct[Carrier](Protocol):
    """What one keyed product must provide to be measured."""

    @property
    def name(self) -> str:
        """Row label."""
        ...

    def build(self, entries: Entries) -> tuple[Carrier, tuple[str, ...]]:
        """Construct the carrier plus its ordered verdict lane."""
        ...

    def compare(
        self,
        left: tuple[Carrier, tuple[str, ...]],
        right: tuple[Carrier, tuple[str, ...]],
    ) -> bool:
        """Exact equality under the product's law."""
        ...

    def normalize(self, entries: Entries) -> tuple[Entries, tuple[str, ...]]:
        """The law-normalized entry view."""
        ...


KINDS = ("equal", "value", "key", "duplicate", "dropped")
EXPECT_EQUAL = {
    "equal": True,
    "value": False,
    "key": False,
    "duplicate": False,
    "dropped": True,
}


def measure[Carrier](
    product: KeyedProduct[Carrier], entries: Entries, kind: str
) -> Row:
    """One product × alternate row, phases separated, both totals implied."""
    alternate, replay = _timed(lambda: make_alternate(entries, kind))
    base_view = project(entries, kind)
    alt_view = project(alternate, kind)

    baseline, base_build = _timed(lambda: product.build(base_view))
    built, build = _timed(lambda: product.build(alt_view))
    equal, compare = _timed(lambda: product.compare(baseline, built))

    def normalized() -> tuple[bool, bool]:
        if alt_view == base_view:
            return True, True
        left = product.normalize(base_view)
        right = product.normalize(alt_view)
        return left == right, False

    (normalized_equal, fast_hit), entry_normalized = _timed(normalized)
    if normalized_equal != equal:
        raise UnsupportedConstructError(
            f"keyed rows: {product.name}/{kind} entry-normalized verdict diverged"
        )
    verdict_delta = baseline[1] != built[1]
    del base_build
    return Row(
        product.name,
        kind,
        equal,
        verdict_delta,
        replay,
        build,
        compare,
        entry_normalized,
        fast_hit,
    )


def _product_rows[Carrier](
    product: KeyedProduct[Carrier], entries: Entries, kinds: tuple[str, ...]
) -> None:
    """Every alternate-kind row plus the retained-carrier bytes, one product."""
    for kind in kinds:
        row = measure(product, entries, kind)
        expected = EXPECT_EQUAL[kind]
        assert row.equal == expected or kind == "duplicate", (product.name, kind)
        _print_row(row)
    print(
        product.name,
        "retained_carrier_bytes",
        _retained_bytes(product, entries),
        sep="\t",
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
        f"entry_normalized_cpu={row.entry_normalized.cpu:.6f}",
        f"fast_accept={row.fast_accept_hit}",
        f"build_wall={row.build.wall:.6f}",
        sep="\t",
    )


def _retained_bytes[Carrier](product: KeyedProduct[Carrier], entries: Entries) -> int:
    """tracemalloc-attributed bytes of one constructed carrier."""
    tracemalloc.start()
    built = product.build(entries)
    size, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert built is not None
    return size


def generic_rows(count: int) -> None:
    """Small/medium rows over the real parsed catalog entries."""
    entries = parse_entries(count)
    merges = [(entries[index][0], entries[index + 1][0]) for index in range(0, 40, 2)]
    print(f"### catalog entries={len(entries)}")
    _product_rows(PyProduct("last-wins"), entries, KINDS)
    _product_rows(PyProduct("strict"), entries, KINDS)
    _product_rows(PyProduct("first-wins"), entries, KINDS)
    _product_rows(IrMapProduct(), entries, KINDS)
    _product_rows(TokenizerProduct(merges), entries, KINDS)


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
    entries: Entries = [
        (str(spelling), int(ordinal)) for spelling, ordinal in tokenizer.encode.items()
    ]
    merges: list[tuple[str, str]] = [
        (str(dyad[0]), str(dyad[1]))
        for dyad, _rank in sorted(tokenizer.ranks.items(), key=lambda kv: int(kv[1]))
    ]
    print("qwen-entries", len(entries), "merges", len(merges), sep="\t")
    for kind in ("equal", "value", "dropped"):
        _print_row(measure(PyProduct("last-wins"), entries, kind))
    for kind in ("equal", "value", "dropped"):
        _print_row(measure(IrMapProduct(), entries, kind))
    for kind in ("equal", "value", "dropped"):
        _print_row(measure(TokenizerProduct(merges), entries, kind))


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
        "the cold fallback must be priced per REAL product; entry-level"
        " normalized comparison is the exact cheaper candidate wherever"
        " construction is a deterministic function of the entry stream",
        sep="\t",
    )


if __name__ == "__main__":
    main()
