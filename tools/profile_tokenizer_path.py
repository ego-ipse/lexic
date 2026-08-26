"""Observe the tokenizer cold path without changing production source.
Control runs install nothing; observed runs delegate replacements and restore
them. ``--source`` and ``--target`` are explicit; the target is overwritten.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import statistics
import time
from collections.abc import Callable, Hashable
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path

from lexic.api import json_tokenizer
from lexic.compile import artifact, reset_cache_for_tests
from lexic.compile import CompiledGrammar, Directives, Vocabulary
from lexic.compile.payload import Payload
from lexic.compile.payload import export as payload_export
from lexic.compile.reduce import fold as reduction_fold
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrAst, IrMap, IrSelf, IrTokenizer, Reducer
from lexic.model import GrammarModel
from lexic.parsing.earley.kernel.forest.support.ambiguity import Resolver
from lexic.parsing.parallel import AUTO, reset_pools

_ACTIVE: ContextVar[OnePathObserver | None] = ContextVar(
    "profile_tokenizer_active", default=None
)


@dataclass(frozen=True, slots=True)
class Started:
    """The two clocks at one named boundary's entry."""

    aggregate_process_cpu: float
    wall: float


@dataclass(slots=True)
class Clock:
    """Aggregate-process-CPU and wall seconds for one interval."""

    aggregate_process_cpu: float = 0.0
    wall: float = 0.0

    def add(self, elapsed: Clock) -> None:
        """Accumulate one completed interval."""
        self.aggregate_process_cpu += elapsed.aggregate_process_cpu
        self.wall += elapsed.wall

    def minus(self, other: Clock) -> Clock:
        """Return the signed difference from another interval."""
        return Clock(
            self.aggregate_process_cpu - other.aggregate_process_cpu,
            self.wall - other.wall,
        )


@dataclass(slots=True)
class ReadStages:
    """Reader-stage clocks."""

    source: Clock = field(default_factory=Clock)
    grammar_setup: Clock = field(default_factory=Clock)
    reduce_setup: Clock = field(default_factory=Clock)
    parse: Clock = field(default_factory=Clock)
    fold: Clock = field(default_factory=Clock)


@dataclass(slots=True)
class ExportStages:
    """Exporter-stage clocks."""

    build: Clock = field(default_factory=Clock)
    project: Clock = field(default_factory=Clock)
    sidecar_render: Clock = field(default_factory=Clock)
    write: Clock = field(default_factory=Clock)


@dataclass(slots=True)
class Stages:
    """Clock pairs attributed to one reader/export call pair."""

    read: ReadStages = field(default_factory=ReadStages)
    export: ExportStages = field(default_factory=ExportStages)

    source = property(lambda self: self.read.source)
    grammar_setup = property(lambda self: self.read.grammar_setup)
    reduce_setup = property(lambda self: self.read.reduce_setup)
    parse = property(lambda self: self.read.parse)
    fold = property(lambda self: self.read.fold)
    build = property(lambda self: self.export.build)
    project = property(lambda self: self.export.project)
    sidecar_render = property(lambda self: self.export.sidecar_render)
    write = property(lambda self: self.export.write)

    def total(self) -> Clock:
        """Return the sum of the non-overlapping named stages."""
        total = Clock()
        for stage in (
            self.source,
            self.grammar_setup,
            self.reduce_setup,
            self.parse,
            self.fold,
            self.build,
            self.project,
            self.sidecar_render,
            self.write,
        ):
            total.add(stage)
        return total


@dataclass(frozen=True, slots=True)
class Witness:
    """The semantic value and exact emitted bytes produced by one arm."""

    tokenizer_count: int
    merge_count: int
    probe_digest: str
    export_digest: str
    export_size: int


@dataclass(frozen=True, slots=True)
class Run:
    """One control or observed product call and its external observations."""

    label: str
    total: Clock
    stages: Stages
    witness: Witness


@dataclass(frozen=True, slots=True)
class Pair:
    """One adjacent control/observed comparison, in execution order."""

    control: Run
    observed: Run

    def delta(self) -> Clock:
        """Return observed minus control total time."""
        return self.observed.total.minus(self.control.total)


class Options(argparse.Namespace):
    """The observer's parsed command-line values."""

    source: Path
    target: Path
    rounds: int

    def validate(self) -> None:
        """Validate command-line values."""
        if self.rounds < 1:
            raise ValueError("--rounds must be positive")

    def resolved_paths(self) -> tuple[Path, Path]:
        """Resolve input/output paths."""
        return self.source.resolve(), self.target.resolve()


@dataclass(slots=True)
class ReaderOriginals:
    """Original reader and reduction callables."""

    path_read_text: Callable[..., str]
    compile_ast: Callable[..., CompiledGrammar]
    reduce_entry: Callable[..., artifact._ReduceEntry]
    parse: Callable[..., GrammarModel]
    reduce: Callable[..., IrSelf]
    tokenizer_of: Callable[..., IrTokenizer]


@dataclass(slots=True)
class ExportOriginals:
    """Original payload-export callables."""

    project_checked: Callable[..., Payload]
    sidecar: Callable[..., str]
    render: Callable[..., str]
    write_module: Callable[..., Path]


@dataclass(slots=True)
class Originals:
    """Runtime references restored after one observed product call."""

    reader: ReaderOriginals
    exporter: ExportOriginals

    path_read_text = property(lambda self: self.reader.path_read_text)
    compile_ast = property(lambda self: self.reader.compile_ast)
    reduce_entry = property(lambda self: self.reader.reduce_entry)
    parse = property(lambda self: self.reader.parse)
    reduce = property(lambda self: self.reader.reduce)
    tokenizer_of = property(lambda self: self.reader.tokenizer_of)
    project_checked = property(lambda self: self.exporter.project_checked)
    sidecar = property(lambda self: self.exporter.sidecar)
    render = property(lambda self: self.exporter.render)
    write_module = property(lambda self: self.exporter.write_module)

    def reader_originals(self) -> ReaderOriginals:
        """Return the reader callables."""
        return self.reader

    def exporter_originals(self) -> ExportOriginals:
        """Return the exporter callables."""
        return self.exporter


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Optional arguments accepted by the payload renderer."""

    module: str | None = None
    reduction: None = None
    ambiguous: bool = False


class OnePathObserver:
    """Runtime-only probes around named boundaries of the existing one path."""

    def __init__(self, source: Path, target: Path) -> None:
        self.source = source
        self.target = target
        self.stages = Stages()
        self.variant: CompiledGrammar | None = None
        self.fold: reduction_fold.ReduceFold | None = None
        self.originals = Originals(
            ReaderOriginals(
                Path.read_text,
                json_tokenizer.compile_ast,
                artifact._reduce_entry,
                artifact.CompiledGrammar.parse,
                reduction_fold.ReduceFold.reduce,
                json_tokenizer.tokenizer_of,
            ),
            ExportOriginals(
                payload_export.project_checked,
                payload_export._sidecar,
                payload_export.render,
                payload_export.write_module,
            ),
        )

    def activate(self) -> None:
        """Install the probes for one synchronous product call."""
        if _ACTIVE.get() is not None:
            raise RuntimeError("one-path observer is already active")
        _ACTIVE.set(self)
        setattr(Path, "read_text", _read_text)
        setattr(json_tokenizer, "compile_ast", _compile_ast)
        setattr(artifact, "_reduce_entry", _reduce_entry)
        setattr(artifact.CompiledGrammar, "parse", _parse)
        setattr(reduction_fold.ReduceFold, "reduce", _reduce)
        setattr(json_tokenizer, "tokenizer_of", _tokenizer_of)
        setattr(payload_export, "project_checked", _project_checked)
        setattr(payload_export, "_sidecar", _sidecar)
        setattr(payload_export, "render", _render)
        setattr(payload_export, "write_module", _write_module)

    def deactivate(self) -> None:
        """Restore every runtime reference after the product call."""
        if _ACTIVE.get() is not self:
            raise RuntimeError("one-path observer is not active")
        setattr(Path, "read_text", self.originals.path_read_text)
        setattr(json_tokenizer, "compile_ast", self.originals.compile_ast)
        setattr(artifact, "_reduce_entry", self.originals.reduce_entry)
        setattr(artifact.CompiledGrammar, "parse", self.originals.parse)
        setattr(reduction_fold.ReduceFold, "reduce", self.originals.reduce)
        setattr(json_tokenizer, "tokenizer_of", self.originals.tokenizer_of)
        setattr(payload_export, "project_checked", self.originals.project_checked)
        setattr(payload_export, "_sidecar", self.originals.sidecar)
        setattr(payload_export, "render", self.originals.render)
        setattr(payload_export, "write_module", self.originals.write_module)
        _ACTIVE.set(None)

    def read_text(
        self,
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> str:
        """Time only the configured tokenizer source read."""
        if path != self.source:
            return self.originals.path_read_text(path, encoding, errors, newline)
        started = _started()
        try:
            return self.originals.path_read_text(path, encoding, errors, newline)
        finally:
            self.stages.source.add(_elapsed(started))

    def compile(
        self,
        grammar: IrAst,
        *,
        cache_key: Hashable | None = None,
        vocabulary: Vocabulary = Vocabulary(),
        directives: Directives = Directives(),
    ) -> CompiledGrammar:
        """Time JSON grammar assembly at the reader's existing call site."""
        started = _started()
        try:
            compiled = self.originals.compile_ast(
                grammar,
                cache_key=cache_key,
                vocabulary=vocabulary,
                directives=directives,
            )
        finally:
            self.stages.grammar_setup.add(_elapsed(started))
        self.variant = compiled
        return compiled

    def entry(
        self, compiled: CompiledGrammar, reducer: Reducer
    ) -> artifact._ReduceEntry:
        """Time derived reduction setup and retain its exact boundaries."""
        if compiled is not self.variant:
            return self.originals.reduce_entry(compiled, reducer)
        started = _started()
        try:
            entry = self.originals.reduce_entry(compiled, reducer)
        finally:
            self.stages.reduce_setup.add(_elapsed(started))
        self.variant = entry.variant
        self.fold = entry.fold
        return entry

    def parse_model(
        self,
        compiled: CompiledGrammar,
        text: str,
        resolve: Resolver | None = None,
        cores: int = AUTO,
    ) -> GrammarModel:
        """Time only the reduction variant's top-level parse."""
        if compiled is not self.variant:
            return self.originals.parse(compiled, text, resolve, cores)
        started = _started()
        try:
            return self.originals.parse(compiled, text, resolve, cores)
        finally:
            self.stages.parse.add(_elapsed(started))

    def fold_model(
        self,
        fold: reduction_fold.ReduceFold,
        model: GrammarModel,
        *,
        cores: int = AUTO,
    ) -> IrSelf:
        """Time only the reduction entry's outer fold."""
        if fold is not self.fold:
            return self.originals.reduce(fold, model, cores=cores)
        started = _started()
        try:
            return self.originals.reduce(fold, model, cores=cores)
        finally:
            self.stages.fold.add(_elapsed(started))

    def build_tokenizer(self, document: IrMap, name: str) -> IrTokenizer:
        """Time the existing reduced-document to tokenizer construction."""
        started = _started()
        try:
            return self.originals.tokenizer_of(document, name)
        finally:
            self.stages.build.add(_elapsed(started))

    def project_payload(self, value: IrTokenizer) -> Payload:
        """Time the existing checked payload projection."""
        started = _started()
        try:
            return self.originals.project_checked(value)
        finally:
            self.stages.project.add(_elapsed(started))

    def prepare_sidecar(self, directory: Path) -> str:
        """Accumulate sidecar generation into the export render stage."""
        started = _started()
        try:
            return self.originals.sidecar(directory)
        finally:
            self.stages.sidecar_render.add(_elapsed(started))

    def render_payload(
        self,
        payload: Payload,
        reader_module: str,
        options: RenderOptions,
    ) -> str:
        """Accumulate value rendering into the same export render stage."""
        started = _started()
        try:
            return self.originals.render(
                payload,
                reader_module,
                module=options.module,
                reduction=options.reduction,
                ambiguous=options.ambiguous,
            )
        finally:
            self.stages.sidecar_render.add(_elapsed(started))

    def write_payload(self, path: Path, source: str) -> Path:
        """Time only the requested value module's validation/write/compile."""
        if path != self.target:
            return self.originals.write_module(path, source)
        started = _started()
        try:
            return self.originals.write_module(path, source)
        finally:
            self.stages.write.add(_elapsed(started))


def _started() -> Started:
    return Started(time.process_time(), time.perf_counter())


def _elapsed(started: Started) -> Clock:
    return Clock(
        time.process_time() - started.aggregate_process_cpu,
        time.perf_counter() - started.wall,
    )


def _observer() -> OnePathObserver:
    observer = _ACTIVE.get()
    if observer is None:
        raise RuntimeError("one-path observer replacement ran while inactive")
    return observer


def _read_text(
    path: Path,
    encoding: str | None = None,
    errors: str | None = None,
    newline: str | None = None,
) -> str:
    return _observer().read_text(path, encoding, errors, newline)


def _compile_ast(
    grammar: IrAst,
    *,
    cache_key: Hashable | None = None,
    vocabulary: Vocabulary = Vocabulary(),
    directives: Directives = Directives(),
) -> CompiledGrammar:
    return _observer().compile(
        grammar,
        cache_key=cache_key,
        vocabulary=vocabulary,
        directives=directives,
    )


def _reduce_entry(compiled: CompiledGrammar, reducer: Reducer) -> artifact._ReduceEntry:
    return _observer().entry(compiled, reducer)


def _parse(
    compiled: CompiledGrammar,
    text: str,
    resolve: Resolver | None = None,
    cores: int = AUTO,
) -> GrammarModel:
    return _observer().parse_model(compiled, text, resolve, cores)


def _reduce(
    fold: reduction_fold.ReduceFold,
    model: GrammarModel,
    *,
    cores: int = AUTO,
) -> IrSelf:
    return _observer().fold_model(fold, model, cores=cores)


def _tokenizer_of(document: IrMap, name: str) -> IrTokenizer:
    return _observer().build_tokenizer(document, name)


def _project_checked(value: IrTokenizer) -> Payload:
    return _observer().project_payload(value)


def _sidecar(directory: Path) -> str:
    return _observer().prepare_sidecar(directory)


def _render(
    payload: Payload,
    reader_module: str,
    *,
    module: str | None = None,
    reduction: None = None,
    ambiguous: bool = False,
) -> str:
    return _observer().render_payload(
        payload,
        reader_module,
        RenderOptions(module, reduction, ambiguous),
    )


def _write_module(path: Path, source: str) -> Path:
    return _observer().write_payload(path, source)


def _product(source: Path, target: Path) -> IrTokenizer:
    tokenizer = json_tokenizer.read_from_path(source, JSON_GRAMMAR, JSON_REDUCER)
    payload_export.export_value(tokenizer, target)
    return tokenizer


def _witness(tokenizer: IrTokenizer, target: Path) -> Witness:
    data = target.read_bytes()
    probe = ",".join(str(token) for token in tokenizer.tokenize("hello"))
    return Witness(
        len(tokenizer.encode),
        len(tokenizer.ranks),
        hashlib.blake2b(probe.encode("utf-8")).hexdigest(),
        hashlib.blake2b(data).hexdigest(),
        len(data),
    )


def _run(label: str, source: Path, target: Path, observed: bool) -> Run:
    """Run one cache-reset control or observed product without concurrency."""
    reset_pools()
    reset_cache_for_tests()
    observer = OnePathObserver(source, target) if observed else None
    if observer is not None:
        observer.activate()
    try:
        started = _started()
        try:
            tokenizer = _product(source, target)
        finally:
            total = _elapsed(started)
            if observer is not None:
                observer.deactivate()
        stages = observer.stages if observer is not None else Stages()
        witness = _witness(tokenizer, target)
        del tokenizer
        del observer
        return Run(label, total, stages, witness)
    finally:
        reset_pools()
        gc.collect()


def _assert_same(pair: Pair) -> None:
    if pair.control.witness != pair.observed.witness:
        raise AssertionError("control and observed arms produced different witnesses")


def _unclassified(run: Run) -> Clock:
    return run.total.minus(run.stages.total())


def _percentage(delta: Clock, baseline: Clock) -> Clock:
    if baseline.aggregate_process_cpu == 0.0 or baseline.wall == 0.0:
        raise AssertionError("a zero control clock cannot quantify perturbation")
    return Clock(
        100 * delta.aggregate_process_cpu / baseline.aggregate_process_cpu,
        100 * delta.wall / baseline.wall,
    )


def _print(run: Run) -> None:
    """Print one tab-separated aggregate-process-CPU/wall arm row."""
    stages = (
        run.stages.source,
        run.stages.grammar_setup,
        run.stages.reduce_setup,
        run.stages.parse,
        run.stages.fold,
        run.stages.build,
        run.stages.project,
        run.stages.sidecar_render,
        run.stages.write,
        _unclassified(run),
    )
    values = (run.total, *stages)
    print(
        run.label,
        *(f"{value.aggregate_process_cpu:.6f}" for value in values),
        *(f"{value.wall:.6f}" for value in values),
        sep="\t",
    )


def _print_perturbation(pair: Pair) -> None:
    """Print the paired observer cost before phase values are considered."""
    delta = pair.delta()
    ratio = _percentage(delta, pair.control.total)
    print(
        "observer_delta",
        f"{delta.aggregate_process_cpu:.6f}",
        f"{delta.wall:.6f}",
        f"{ratio.aggregate_process_cpu:.2f}%",
        f"{ratio.wall:.2f}%",
        sep="\t",
    )


def _median(values: list[float]) -> float:
    return statistics.median(values)


def _print_summary(pairs: list[Pair]) -> None:
    """Print medians over every paired sample, never a favourable sample."""
    control = Clock(
        _median([pair.control.total.aggregate_process_cpu for pair in pairs]),
        _median([pair.control.total.wall for pair in pairs]),
    )
    observed = Clock(
        _median([pair.observed.total.aggregate_process_cpu for pair in pairs]),
        _median([pair.observed.total.wall for pair in pairs]),
    )
    delta = Clock(
        _median([pair.delta().aggregate_process_cpu for pair in pairs]),
        _median([pair.delta().wall for pair in pairs]),
    )
    ratio = _percentage(delta, control)
    print(
        "median_all_pairs",
        f"{control.aggregate_process_cpu:.6f}",
        f"{control.wall:.6f}",
        f"{observed.aggregate_process_cpu:.6f}",
        f"{observed.wall:.6f}",
        f"{delta.aggregate_process_cpu:.6f}",
        f"{delta.wall:.6f}",
        f"{ratio.aggregate_process_cpu:.2f}%",
        f"{ratio.wall:.2f}%",
        sep="\t",
    )


def main() -> None:
    """Alternate cache-reset control and observed arms without concurrency."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=1)
    options: Options = Options()
    parser.parse_args(namespace=options)
    options.validate()
    source, target = options.resolved_paths()
    if source == target:
        parser.error("--source and --target must name different files")
    print(
        "# aggregate_process_cpu is process_time: aggregate CPU seconds"
        " across all threads/cores; wall is elapsed seconds",
    )
    print(
        "arm\taggregate_process_cpu_total\taggregate_process_cpu_source"
        "\taggregate_process_cpu_grammar_setup"
        "\taggregate_process_cpu_reduce_setup\taggregate_process_cpu_parse"
        "\taggregate_process_cpu_fold\taggregate_process_cpu_build"
        "\taggregate_process_cpu_project"
        "\taggregate_process_cpu_sidecar_render\taggregate_process_cpu_write"
        "\taggregate_process_cpu_unclassified\twall_total\twall_source"
        "\twall_grammar_setup\twall_reduce_setup\twall_parse\twall_fold"
        "\twall_build\twall_project\twall_sidecar_render\twall_write"
        "\twall_unclassified"
    )
    pairs: list[Pair] = []
    for round_number in range(options.rounds):
        number = round_number + 1
        if round_number % 2:
            observed = _run(f"observed-{number}", source, target, True)
            _print(observed)
            control = _run(f"control-{number}", source, target, False)
            _print(control)
        else:
            control = _run(f"control-{number}", source, target, False)
            _print(control)
            observed = _run(f"observed-{number}", source, target, True)
            _print(observed)
        pair = Pair(control, observed)
        _assert_same(pair)
        pairs.append(pair)
        _print_perturbation(pair)
    _print_summary(pairs)


if __name__ == "__main__":
    main()
