"""Time every engine on the same grammar and the same input.

    uv run python -m tools.benchmark.bench            # default rounds
    uv run python -m tools.benchmark.bench --rounds 1 # quick pass
    uv run python -m tools.benchmark.bench --only json arithmetic
    uv run python -m tools.benchmark.bench --cores 8  # lexic-mt over 8 threads

On a free-threaded interpreter two more rows appear BY DEFAULT — `lexic-mt`
and `lexic-mt-lex-ns`: ONE parse of the FULL corpus (`Bench.full`, ~32 KB —
a split needs several chunks above the policy floor to be visible),
`cores=N` (auto N = the cpu count; `--cores N` overrides), timed as wall
clock through the same machinery as every other row. No copies, no
division — whether splitting one document across workers pays is exactly
what the cell reads, and until it pays the cell honestly reads no better
than its sequential twin. A GIL build gets no such rows and refuses an
explicit `--cores` with the reason: threaded parsing under the GIL
measured 0.82-0.92x, a net loss a row must not launder into a number.

Every OTHER row times the small corpus by default — the slow engines pay
seconds per pass at document scale, a price the default run should not
charge per round. `--full` puts every row on the full corpus; that is the
same-document run, and the one where mt and its sequential twin share an
axis exactly rather than per-char-normalised across two documents.

Every column is the SAME grammar, translated by :mod:`tools.benchmark.emit` from
the one `IrAst` lexic compiles, and every translation is checked in both
directions before it earns a row — so a cell cannot quietly report a number for
a grammar we mistranslated.

**What a row does not tell you.** The engines do not build the same thing: lexic
returns a typed model the source is recoverable from, Lark a generic `Tree`,
parsimonious a `Node` tree, pyparsing a `ParseResults`, ANTLR a
`ParserRuleContext`. Nobody gets semantic actions. That difference is real work
inside every number, so each row names what it built.

Each row is built, validated, and timed in a fresh interpreter process. Adding
an ANTLR or Lark seat therefore cannot change Lexic's heap, cache distance, or
absolute number. Worker order is deterministically shuffled, and a same-engine
noise floor says what difference must be beaten.
"""

from __future__ import annotations

import gc
from collections.abc import Sequence
from importlib import import_module
from typing import NamedTuple

from lexic.compile import CompiledGrammar, Directives, compile_text
from lexic.model import GrammarModel
from lexic.parsing.products import _model_product, earley_model
from tools.benchmark.cases.grammars import Bench
from tools.benchmark.engines.refusals import LEXIC_REFUSALS, refusals
from tools.benchmark.engines.seats import SPECIALISTS, candidates
from tools.benchmark.measurement.contract import (
    CLOCKS,
    PROTOCOL,
    RowContract,
    digest,
    shape,
)
from tools.benchmark.measurement.language import unfaithful
from tools.benchmark.measurement.occupancy import declined_reason
from tools.benchmark.measurement.sampling import Parse, Pass, prime, timed

SUMMARY = "Time every engine on the same grammar and the same input."
"""The CLI description. Named, because `__doc__` is `str | None`."""

DEFAULT_ROUNDS = 7
"""Timed rounds per engine when none is asked for."""

ENGINE: dict[str, str] = {
    "lexic-pda": "lexic's predictive PDA, one pass, no directives — as authored",
    "lexic-earley": "lexic's Earley/SPPF fallback; ambiguity refused, not resolved",
    "lexic-lex": "lexic-pda, `@lexical` rules folded to their matched TEXT",
    "lexic-lex-ns": "lexic-lex, `@non-semantic` rules dropped from the model",
    "lexic-mt": "lexic-pda over the FULL corpus, one parse, cores=N — wall clock",
    "lexic-mt-lex-ns": "lexic-lex-ns, the same full-corpus cores=N wall clock",
    "lark-earley": "Lark's Earley backend, dynamic lexer, grammar as authored",
    "lark-lalr": "Lark's LALR backend, contextual lexer, partitioned alphabet",
    "lark-earley-lex": "lark-earley with the grammar's own directives translated",
    "lark-lalr-lex": "lark-lalr with the grammar's own directives translated",
    "parsimonious": "PEG: scannerless, ordered choice, possessive repetition",
    "parsimonious-lex": "parsimonious with the grammar's directives inlined",
    "pyparsing": "combinator tree on the cheapest alternation that stays faithful",
    "antlr": "ANTLR's ALL(*) parser on a warmed JVM — tool AND runtime, not Python",
    "antlr-lex": "ANTLR Java with the grammar's own directives translated",
    "antlr-py": "the same generated parser on the pure-Python ATN simulator",
    "antlr-py-lex": "ANTLR Python with the grammar's own directives translated",
    "stdlib-json": "the stdlib's hand-written C parser for the format",
    "msgspec": "a hand-written C parser for the format, the specialist floor",
}
"""One line per engine, printed ONCE above the rows.

Naming an engine is not describing it: `lark-lalr` and `lark-lalr-lex` differ
only in what the emitter hands them, and a reader who cannot see that reads the
pair as one tool being inconsistent. Printed once at the top rather than per
row, because a legend repeated ten times stops being read.
"""

PRODUCT: dict[str, str] = {
    "lexic-pda": "typed model",
    "lexic-earley": "typed model",
    "lexic-lex": "typed model · @lexical",
    "lexic-lex-ns": "typed model · @lexical @non-semantic",
    "lexic-mt": "typed model · one doc, N workers",
    "lexic-mt-lex-ns": "typed model · one doc, N workers · @lexical @non-semantic",
    "lark-earley": "Tree",
    "lark-lalr": "Tree",
    "lark-earley-lex": "Tree · @lexical @non-semantic",
    "lark-lalr-lex": "Tree · @lexical @non-semantic",
    "parsimonious": "Node tree",
    "parsimonious-lex": "Node tree · @lexical @non-semantic",
    "pyparsing": "ParseResults",
    "antlr": "ParserRuleContext · JAVA",
    "antlr-lex": "ParserRuleContext · JAVA · @lexical @non-semantic",
    "antlr-py": "ParserRuleContext",
    "antlr-py-lex": "ParserRuleContext · @lexical @non-semantic",
    "stdlib-json": "dict · C parser for the FORMAT, takes no grammar",
    "msgspec": "dict · C parser for the FORMAT, takes no grammar",
}
"""What each engine BUILDS — the part a bare µs/char number hides.

The `-lex` rows are the DIRECTIVE-MATCHED seats. lexic's headline rows are its
variants — `@lexical` folds a rule to its matched text, `@non-semantic` drops
structural rules from the model — and a translation that withholds both hands
the competitor a grammar with a rule, and a tree node, per whitespace run.
`tools.benchmark.emit._folded` spells the same two marks in Lark, so `-lex`
faces `lexic-lex`/`lexic-lex-ns` and the unmarked row faces `lexic-pda`. Both
are timed because the fold is not free to take: it costs `abnf-meta` its Earley
row outright and `markdown` its LALR one, and a row that only reported the
better of the two would hide that.

`antlr` is ANTLR's Java target in a live JVM; every other row is Python. That
makes its cell a tool+runtime answer rather than an algorithm one — which is a
real question ("what parses this grammar fastest") and the one it is reported
for. `antlr-py` is the same generated parser on `antlr4-python3-runtime`, a
pure-Python ATN simulator and a different animal.

`stdlib-json` and `msgspec` are FORMAT SPECIALISTS: hand-written C parsers for
the one format their row's grammar happens to describe. They take no grammar
and answer no capability question — their cells are the specialist floor, what
dedicating compiled code to a single fixed language buys. Their language is the
FORMAT and it is strictly larger than the row's grammar, so they are held to the
accepting half of :func:`unfaithful` and not the refusing one; :data:`SPECIALISTS`
says why that is a declaration rather than an exemption.
"""


LEXIC_ROWS = frozenset(
    {
        "lexic-pda",
        "lexic-earley",
        "lexic-lex",
        "lexic-lex-ns",
        "lexic-mt",
        "lexic-mt-lex-ns",
    }
)
"""Every Lexic row, shared by the report and regression guard."""


def _lexic(
    bench: Bench, cores: int | None, only: frozenset[str] | None = None
) -> tuple[dict[str, Parse], dict[str, CompiledGrammar]]:
    """Both lexic engines over one compiled product — the PDA and Earley.

    Same grammar, same fold, same model: the only difference is which engine
    walks the input, which is the comparison these two columns exist for.

    The engine gets `codegen_grammar`, which is what `CompiledGrammar.parse`
    hands it and what the fold was BUILT against — the canonical grammar the
    competitors are given is the same language, but its arms and groups are not
    hoisted, so folding against it raises a missing-field error that looks like
    a synthesis bug in lexic and is really a mismatched pair here.

    Every sequential row pins ``cores=1``: the seam's default is auto, and on
    a free-threaded build a row legended "one pass" must not silently split.
    The mt rows are the SAME seam with ``cores`` — one document, one parse,
    however many workers the split can occupy.

    :param cores: The mt rows' worker count, or ``None`` for no mt rows.
    """
    wanted = LEXIC_ROWS if only is None else only
    unknown = wanted - LEXIC_ROWS
    if unknown:
        raise ValueError(f"unknown Lexic benchmark rows: {sorted(unknown)}")
    binding = bench.compiled.product
    sequential = bench.compiled.parse
    engines: dict[str, Parse] = {}
    # The production seam, like every competitor's own entry API — the
    # raw-kernel arm measured +1.3% apart from it, which was enough to fake a
    # persistent @lexical "regression" on arithmetic when variant rows ran the
    # seam and this row ran the kernel (t11_arith probe).
    if "lexic-pda" in wanted:
        engines["lexic-pda"] = lambda text: sequential(text, cores=1)
    if "lexic-earley" in wanted:
        product = _model_product(bench.compiled.codegen_grammar, bench.compiled.product)
        engines["lexic-earley"] = lambda text: earley_model(
            product.instance_grammar, text, binding, product.tables
        )
    mt_artifacts: dict[str, CompiledGrammar] = {}
    if cores is not None and "lexic-mt" in wanted:
        engines["lexic-mt"] = lambda text: sequential(text, cores=cores)
        mt_artifacts["lexic-mt"] = bench.compiled
    # The declared-variant engines: the SAME source under the directives a
    # lexic author could write — @lexical (maximal, mechanically derived) and
    # + @non-semantic (the fixture set's authored noise vocabulary). Both are
    # language-preserving, so both rows face the same unfaithful gate as
    # every other engine; what they measure is what the declarations buy.
    variant_rows = wanted & {"lexic-lex", "lexic-lex-ns", "lexic-mt-lex-ns"}
    if not variant_rows:
        return engines, mt_artifacts
    variants, variant_artifacts = _variant_engines(bench, wanted, cores)
    engines.update(variants)
    mt_artifacts.update(variant_artifacts)
    return engines, mt_artifacts


def _variant_engines(
    bench: Bench, wanted: frozenset[str], cores: int | None
) -> tuple[dict[str, Parse], dict[str, CompiledGrammar]]:
    """Compile only the requested directive-bearing Lexic variants.

    The directives are the case's DECLARED sets. They are not derived from the
    grammar by heuristic and not trimmed by what this engine finds eligible or
    fast: a row label must denote the same workload in every revision, and a
    licence that removes marks until the row stops regressing hides exactly the
    regression the row exists to expose.
    """
    lex_marks = frozenset(bench.lexical)
    ns_marks = frozenset(bench.non_semantic)
    engines: dict[str, Parse] = {}
    artifacts: dict[str, CompiledGrammar] = {}
    for label, directives in (
        ("lexic-lex", Directives(lexical=lex_marks)),
        ("lexic-lex-ns", Directives(lexical=lex_marks, non_semantic=ns_marks)),
    ):
        needed = label in wanted or (
            label == "lexic-lex-ns" and "lexic-mt-lex-ns" in wanted
        )
        if not needed:
            continue
        variant = compile_text(
            bench.source,
            cache_key=f"bench-{bench.name}-{label}-{len(lex_marks)}",
            flavour=bench.flavour,
            directives=directives,
        )
        # the PRODUCTION seam: an author who declares directives runs
        # CompiledGrammar.parse, composition included.
        if label in wanted:
            engines[label] = lambda text, parse=variant.parse: parse(text, cores=1)
        if (
            label == "lexic-lex-ns"
            and cores is not None
            and "lexic-mt-lex-ns" in wanted
        ):
            engines["lexic-mt-lex-ns"] = lambda text, parse=variant.parse: parse(
                text, cores=cores
            )
            artifacts["lexic-mt-lex-ns"] = variant
    return engines, artifacts


MT_ROWS = frozenset({"lexic-mt", "lexic-mt-lex-ns"})
"""The rows that always read the full corpus — a split needs the scale."""

LEXICAL_ROWS = frozenset(
    {
        "lexic-lex",
        "lexic-lex-ns",
        "lexic-mt-lex-ns",
        "lark-earley-lex",
        "lark-lalr-lex",
        "parsimonious-lex",
        "antlr-lex",
        "antlr-py-lex",
    }
)
"""Every seat built with the case's declared `@lexical` set.

Declared rather than derived from the name, for the same reason
:data:`~tools.benchmark.cases.directives.DIRECTIVES` is declared: a row label
must denote the same work in every revision. The naming convention is pinned
beside it by test, so a new `-lex` seat cannot be added without landing here.
"""

NON_SEMANTIC_ROWS = LEXICAL_ROWS - {"lexic-lex"}
"""Every seat that ALSO carries the case's `@non-semantic` set.

`lexic-lex` is the one seat that takes the fold without the noise drop — it
exists precisely to price the two declarations apart, and `PRODUCT` labels it
that way. Every other marked seat faces both, because a translation handed one
and not the other is not the grammar lexic's variant rows compile.
"""

NOISE_ANCHOR = "lexic-pda"
"""The one seat a grammar's noise floor is ever measured on.

The floor is one number per grammar and nothing beside it records which engine
produced it, so it must not depend on which engines a run was ASKED for.
Anchored on the first row that happened to measure, `--seats antlr` replaced a
grammar's floor with a JVM-measured control and `--seats lark-earley` replaced
it again — three numbers for one cell, each written without a word. A fixed
anchor makes the cell mean one thing, and a run that did not measure this seat
leaves the committed floor alone rather than restating it.
"""


def seat_directives(bench: Bench, seat: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The EXACT directive sets one seat is built with, sorted.

    The single reading of "what did this seat compile with", shared by the row
    contract, the artifact's per-cell record and the structural gate — because
    a cell that disagrees with the contract about the declarations is exactly
    the drift the record exists to expose.

    :param bench: The case, carrying its declared sets.
    :param seat: The row name.
    :returns: ``(lexical, non_semantic)``, empty for an unmarked seat.
    """
    lexical = tuple(sorted(bench.lexical)) if seat in LEXICAL_ROWS else ()
    non_semantic = (
        tuple(sorted(bench.non_semantic)) if seat in NON_SEMANTIC_ROWS else ()
    )
    return lexical, non_semantic


def directive_digest(bench: Bench, seat: str) -> str:
    """One seat's directive sets as a digest, for the per-cell record.

    A digest rather than the names themselves: `gbnf-meta` declares fifteen
    `@lexical` rules and the artifact holds a record per (grammar, seat), so
    spelling them out would multiply the file by its longest declaration to
    answer one question — did this change since the cell was measured.
    """
    lexical, non_semantic = seat_directives(bench, seat)
    return digest("\n".join(lexical) + "\x1f" + "\n".join(non_semantic))


def build_contract(
    bench: Bench, row: str, document: str, cores: int, gc_enabled: bool
) -> RowContract:
    """The exact identity of one row over one document — the ONE constructor.

    The worker builds this from what it measured and the structural gate builds
    it from what a row WOULD be measured under, and the two must agree field for
    field or the gate is checking a shape nobody writes. `scale` is derived from
    the document rather than passed, so the record cannot disagree with what was
    actually parsed.

    :param bench: The case.
    :param row: The seat name.
    :param document: The exact input this row reads.
    :param cores: The worker request; 1 for every sequential row.
    :param gc_enabled: Whether the collector ran during the observation.
    :returns: The row's contract.
    """
    lexical, non_semantic = seat_directives(bench, row)
    return RowContract(
        PROTOCOL,
        row,
        bench.name,
        digest(bench.source),
        lexical,
        non_semantic,
        digest(document),
        len(document.encode("utf-8")),
        "full" if document == bench.full else "corpus",
        PRODUCT[row],
        cores,
        gc_enabled,
        CLOCKS,
    )


class EngineBuild(NamedTuple):
    """One isolated row's parser, input, refusal, and optional MT artifact."""

    parse: Parse | None
    document: str
    refusal: str | None
    artifact: CompiledGrammar | None


def one_engine(bench: Bench, name: str, cores: int | None, full: bool) -> EngineBuild:
    """Construct and validate exactly one requested benchmark row."""
    document = bench.full if full or name in MT_ROWS else bench.corpus
    artifact = None
    if name in LEXIC_ROWS:
        built, artifacts = _lexic(bench, cores, frozenset({name}))
        parse = built.get(name)
        artifact = artifacts.get(name)
        if parse is None:
            return EngineBuild(
                None,
                document,
                "requires free-threaded Python with at least two workers",
                None,
            )
    else:
        makers = dict(candidates(bench))
        if name not in makers:
            raise ValueError(f"unknown benchmark row {name!r} for {bench.name}")
        try:
            parse = makers[name](bench)
        except refusals() as exc:
            return EngineBuild(
                None,
                document,
                f"{type(exc).__name__}: {' '.join(str(exc).split())}",
                None,
            )
    exceptions = LEXIC_REFUSALS if name in LEXIC_ROWS else None
    wrong = unfaithful(parse, bench, document, exceptions, name in SPECIALISTS)
    if wrong is not None:
        getattr(parse, "close", lambda: None)()
        return EngineBuild(None, document, wrong, None)
    return EngineBuild(parse, document, None, artifact)


def observe(build: EngineBuild, rounds: int) -> Pass:
    """This process's ONE observation of its row, on both clocks.

    The independent unit of a comparison is the PROCESS, not the pass. Several
    inner passes are reduced here to a single answer so that a warm allocator
    or a lucky cache line inside one interpreter cannot be counted as several
    independent structural samples. The reduction is the median on each clock,
    which is what a repeated measurement of one state is worth.
    """
    parse, document = build.parse, build.document
    if parse is None:
        raise ValueError("cannot observe a refused benchmark row")
    prime(parse, document)
    passes: list[Pass] = []
    for _ in range(rounds):
        parse(document)
        passes.append(timed(parse, document))
        gc.collect()
    walls = sorted(entry.wall for entry in passes)
    cpus = sorted(entry.cpu for entry in passes)
    return Pass(walls[len(walls) // 2], cpus[len(cpus) // 2])


class Result(NamedTuple):
    """What one row BUILT, digested both ways.

    :ivar text: The product rendered back to text — the fidelity check.
    :ivar shape: Its structure — the check that says two arms built the same
        product, which the text cannot answer for a round trip.
    """

    text: str
    shape: str


def result_identity(build: EngineBuild) -> Result:
    """Parse once, and answer both questions a timing pair must pass.

    A lexic row round-trips its model; every other product answers for itself
    through ``repr``. Both digests travel in the observation — a timing pair
    whose two arms built different things is not a comparison.
    """
    parse = build.parse
    if parse is None:
        raise ValueError("cannot read a refused benchmark row's result")
    product = parse(build.document)
    rendered = product.to_text() if isinstance(product, GrammarModel) else repr(product)
    return Result(rendered, shape(product))


def _mt_check(
    artifacts: dict[str, CompiledGrammar], document: str, cores: int | None
) -> dict[str, str]:
    """Why each exact mt artifact did not thread; absent rows engaged."""
    if cores is None:
        return {}
    seen = {
        name: declined_reason(compiled, document, cores).declined
        for name, compiled in artifacts.items()
    }
    return {name: why for name, why in seen.items() if why is not None}


def main(argv: Sequence[str] | None = None) -> None:
    """Run the benchmark report without keeping report code in this module."""
    import_module("tools.benchmark.presentation.cli").main(argv)


if __name__ == "__main__":
    main()
