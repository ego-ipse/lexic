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

Interleaved, because a loaded machine moves every column together and only
alternating rounds make that visible. A noise floor is measured first — the same
engine timed twice — so the reader knows what a difference must beat.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import random
import re
import sys
import time
from collections.abc import Callable, Sequence
from math import log10
from typing import NamedTuple

import lark
import msgspec
import parsimonious
import parsimonious.expressions

from lexic.compile import Directives, compile_text
from lexic.exceptions import LexicError
from lexic.parsing.parallel import AUTO, available_workers, split_model
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import _model_product, earley_model, parse_model
from lexic.parsing.trace import watch
from tools.benchmark.antlr_build import antlr_parser
from tools.benchmark.antlr_java import java_antlr_parser
from tools.benchmark.emit import (
    NO_MARKS,
    lark_grammar,
    peg_grammar,
    pyparsing_parser,
)
from tools.benchmark.grammars import BENCHES, Bench, variant_marks
from tools.benchmark.refusals import REFUSALS, accepts, refusal

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
    "pyparsing": "combinator tree on the cheapest alternation that stays faithful",
    "antlr": "ANTLR's ALL(*) parser on a warmed JVM — tool AND runtime, not Python",
    "antlr-py": "the same generated parser on the pure-Python ATN simulator",
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
    "pyparsing": "ParseResults",
    "antlr": "ParserRuleContext · JAVA",
    "antlr-py": "ParserRuleContext",
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
dedicating compiled code to a single fixed language buys. The same
:func:`unfaithful` differential gates them, which is what proves their
hard-coded language and the row's grammar agree on the fixture set.
"""

Parse = Callable[[str], object]


def _antlr_name(bench: str) -> str:
    """An identifier grammar name for ANTLR's generated code."""
    return "B" + "".join(part.title() for part in bench.replace("-", "_").split("_"))


def _lexic(bench: Bench, cores: int | None) -> dict[str, Parse]:
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
    fold = bench.fold
    product = _model_product(bench.compiled.codegen_grammar, fold)
    sequential = bench.compiled.parse
    engines: dict[str, Parse] = {
        # the production seam, like every competitor's own entry API — the
        # raw-kernel arm measured +1.3% apart from it, which was enough to
        # fake a persistent @lexical "regression" on arithmetic when variant
        # rows ran the seam and this row ran the kernel (t11_arith probe)
        "lexic-pda": lambda text: sequential(text, cores=1),
        "lexic-earley": lambda text: earley_model(
            product.instance_grammar, text, fold, product.tables
        ),
    }
    if cores is not None:
        engines["lexic-mt"] = lambda text: sequential(text, cores=cores)
    # The declared-variant engines: the SAME source under the directives a
    # lexic author could write — @lexical (maximal, mechanically derived) and
    # + @non-semantic (the fixture set's authored noise vocabulary). Both are
    # language-preserving, so both rows face the same unfaithful gate as
    # every other engine; what they measure is what the declarations buy.
    lex_marks, ns_marks = variant_marks(bench.ast)
    lex_marks = _licensed_marks(bench, lex_marks)
    for label, directives in (
        ("lexic-lex", Directives(lexical=lex_marks)),
        ("lexic-lex-ns", Directives(lexical=lex_marks, non_semantic=ns_marks)),
    ):
        variant = compile_text(
            bench.source,
            cache_key=f"bench-{bench.name}-{label}-{len(lex_marks)}",
            flavour=bench.flavour,
            directives=directives,
        )
        # the PRODUCTION seam: an author who declares directives runs
        # CompiledGrammar.parse, composition included.
        engines[label] = lambda text, parse=variant.parse: parse(text, cores=1)
        if label == "lexic-lex-ns" and cores is not None:
            engines["lexic-mt-lex-ns"] = lambda text, parse=variant.parse: parse(
                text, cores=cores
            )
    return engines


def _decision_cost(compiled, corpus: str) -> int | None:
    """Watched decision work (probes, gates, rollbacks) on the raw PDA; None = incapable."""
    fold = compiled.fold
    product = _model_product(compiled.codegen_grammar, fold)
    try:
        pda_model(product.pda, corpus, fold)
    except LexicError, PdaFail:
        return None
    run = watch(product.pda, corpus, fold, cap=1_000_000)
    return sum(
        1 for event in run.events if str(event.kind) in ("rollback", "probe", "gate")
    )


def _licensed_marks(bench: Bench, marks: frozenset[str]) -> frozenset[str]:
    """Marks licensed by ENGINE EVIDENCE, dropped one by one until sound.

    lexruns collapses a run only after PROVING charset, uniqueness and
    FOLLOW-disjointness; a benchmark heuristic proving none of them was
    measured making three grammars slower and one PDA-incapable. The licence
    here holds marks to the same standard, empirically: a mark set survives
    only if the raw PDA still takes the corpus AND the watched decision trace
    shows no more rollbacks than the plain compile — otherwise marks drop
    (alphabetically last first) until the remainder is sound, possibly none.
    The honest declaration for that grammar is then NOTHING, and the variant
    row equals plain rather than regressing it.
    """
    if not marks:
        return marks
    baseline = _decision_cost(bench.compiled, bench.corpus)
    candidates = sorted(marks)
    while candidates:
        trial = compile_text(
            bench.source,
            cache_key=f"bench-{bench.name}-lic-{len(candidates)}-{candidates[0]}",
            flavour=bench.flavour,
            directives=Directives(lexical=frozenset(candidates)),
        )
        cost = _decision_cost(trial, bench.corpus)
        if cost is not None and (baseline is None or cost <= baseline):
            return frozenset(candidates)
        candidates.pop()
    return frozenset()


def unfaithful(parse: Parse, bench: Bench, document: str | None = None) -> str | None:
    """The first way ``parse`` disagrees with lexic about the language, or None.

    The single place a translation is judged, in BOTH directions. An
    over-permissive one describes a larger language and passes any accept-only
    check; an over-restrictive one passes the corpus and then refuses a sentence
    nobody sampled — which is what a context-free lexer does to a grammar whose
    character classes overlap. Either way the engine gets no number, because a
    number for a different language is not a faster answer to the question, it
    is an answer to a different one.

    :param document: The text this engine will be timed on — the acceptance
        half is checked against exactly that (default: the small corpus).
    """
    why = refusal(parse, document if document is not None else bench.corpus)
    if why is not None:
        return f"refuses the corpus — {why}"
    for text in bench.accepts:
        why = refusal(parse, text)
        if why is not None:
            return f"refuses {text!r} — {why}"
    for text in bench.rejects:
        if accepts(parse, text):
            return f"accepts {text[:18]!r}, which lexic refuses"
    return None


def _lark_parse(bench: Bench, parser: str, marked: bool = False) -> Parse:
    """Lark on one of its two algorithms, each given the token set it needs.

    The two backends carry different lexers and want different grammars, which
    is a distinction Lark's own documentation makes. `earley` runs a `dynamic`
    lexer that offers every matching terminal to the parser, so it settles an
    overlap itself and keeps the run terminals. `lalr` runs a `contextual` lexer
    that must commit to one terminal per position, so it gets the partitioned
    alphabet — without it a single space between `ws` and `chars` goes to the
    wrong slot, which is a token-set problem rather than a limit of LALR.
    :param marked: Translate the grammar's own directives too — see
        :data:`PRODUCT` for why that is a seat rather than a correction.
    """
    marks = variant_marks(bench.ast) if marked else NO_MARKS
    text = lark_grammar(bench.ast, refine=parser == "lalr", marks=marks)
    return lark.Lark(text, parser=parser).parse


def _peg_parse(bench: Bench) -> Parse:
    """parsimonious over the emitted PEG, compiled on stdlib ``re``.

    parsimonious prefers the third-party ``regex`` module when installed and
    ships it as a dependency, but stdlib ``re`` measured 9-19% faster on the
    bench's patterns. The row measures the PEG scheme, not the dependency's
    regex engine, so the grammar is compiled under the faster module — a
    construction-time swap only; matching runs on the compiled patterns.
    """
    preferred = getattr(parsimonious.expressions, "re")
    setattr(parsimonious.expressions, "re", re)
    try:
        return parsimonious.Grammar(peg_grammar(bench.ast)).parse
    finally:
        setattr(parsimonious.expressions, "re", preferred)


def _pp_parse(bench: Bench) -> Parse:
    """pyparsing's combinator tree, on the CHEAPEST faithful alternation.

    pyparsing spells two alternations and they are not interchangeable:
    `MatchFirst` commits to the first arm that matches (PEG's ordered choice),
    `Or` keeps the longest (what a context-free `|` means). `MatchFirst` is what
    a pyparsing author writes and it is far faster — but where arms share a
    prefix it parses a different language. So build the cheap one, ask whether
    it is faithful, and pay for `Or` only where it is not. That is the iteration
    a person hitting the bug would do, and it gives pyparsing its best HONEST
    number per grammar rather than its fastest wrong one.
    """
    quick = pyparsing_parser(bench.ast, longest=False)

    def cheap(body: str) -> object:
        return quick.parse_string(body, parse_all=True)

    if unfaithful(cheap, bench) is None:
        return cheap
    exact = pyparsing_parser(bench.ast, longest=True)
    return lambda body: exact.parse_string(body, parse_all=True)


_CANDIDATES: tuple[tuple[str, Callable[[Bench], Parse]], ...] = (
    ("lark-earley", lambda bench: _lark_parse(bench, "earley")),
    ("lark-lalr", lambda bench: _lark_parse(bench, "lalr")),
    ("lark-earley-lex", lambda bench: _lark_parse(bench, "earley", marked=True)),
    ("lark-lalr-lex", lambda bench: _lark_parse(bench, "lalr", marked=True)),
    ("parsimonious", _peg_parse),
    # ANTLR builds a parser before anything runs — the Java tool, then javac for
    # the Java row. That is part of using ANTLR, as `Lark(...)` construction is,
    # so it happens here and never inside a timed round.
    ("antlr", lambda bench: java_antlr_parser(bench.ast, _antlr_name(bench.name))),
    ("antlr-py", lambda bench: antlr_parser(bench.ast, _antlr_name(bench.name))),
    ("pyparsing", _pp_parse),
)
"""Every competitor, as a name and the one way to build it from a bench."""


_JSON_SPECIALISTS: tuple[tuple[str, Callable[[Bench], Parse]], ...] = (
    ("stdlib-json", lambda bench: json.loads),
    ("msgspec", lambda bench: msgspec.json.decode),
)
"""The json row's format specialists (see :data:`PRODUCT`)."""


def _candidates(bench: Bench) -> tuple[tuple[str, Callable[[Bench], Parse]], ...]:
    """The candidate rows for one bench: every engine, plus its specialists.

    A specialist parses one fixed FORMAT, so it is a candidate only for the
    bench whose language it hard-codes — offering `json.loads` a csv corpus
    would print a refusal row that answers no question anyone asked.
    """
    if bench.name != "json":
        return _CANDIDATES
    return _CANDIDATES + _JSON_SPECIALISTS


def _competitors(bench: Bench) -> tuple[dict[str, Parse], dict[str, str]]:
    """Every competitor that can take this grammar, and why the others cannot.

    A tool that cannot express the grammar gets a REASON in its own words, never
    a substituted easier grammar. Building is not enough either: a parser that
    builds and then describes a different language is exactly the failure a
    benchmark cannot see, so :func:`unfaithful` gates every candidate.
    """
    built: dict[str, Parse] = {}
    refused: dict[str, str] = {}
    for label, make in _candidates(bench):
        try:
            parse = make(bench)
        except REFUSALS as exc:
            refused[label] = f"{type(exc).__name__}: {' '.join(str(exc).split())}"
            continue
        wrong = unfaithful(parse, bench)
        if wrong is None:
            built[label] = parse
        else:
            refused[label] = wrong
            getattr(parse, "close", lambda: None)()
    return built, refused


MT_ROWS = frozenset({"lexic-mt", "lexic-mt-lex-ns"})
"""The rows that always read the full corpus — a split needs the scale."""


def _engines(
    bench: Bench, cores: int | None, full: bool
) -> tuple[dict[str, Parse], dict[str, str], dict[str, str]]:
    """Every engine to time, its document, and who could not take the grammar.

    lexic's own rows pass through the SAME :func:`unfaithful` gate as every
    competitor — accepts and rejects both directions, plus the exact document
    the row will be timed on; the mt rows included, since a split that
    changed what an input means would be the worst possible way to get a
    faster number. The gate exists so no engine gets a number for a
    different language, and an engine exempt from it would be exactly the
    sycophancy the gate is there to prevent.
    """
    lexic = _lexic(bench, cores)
    competitors, refused = _competitors(bench)
    documents = {
        name: bench.full if full or name in MT_ROWS else bench.corpus
        for name in (*lexic, *competitors)
    }
    working: dict[str, Parse] = {}
    for label, parse in lexic.items():
        wrong = unfaithful(parse, bench, documents[label])
        if wrong is None:
            working[label] = parse
        else:
            refused[label] = wrong
    if full:
        for label, parse in list(competitors.items()):
            wrong = unfaithful(parse, bench, documents[label])
            if wrong is not None:
                refused[label] = wrong
                competitors.pop(label)
                getattr(parse, "close", lambda: None)()
    return {**working, **competitors}, refused, documents


def _once(parse: Parse, corpus: str) -> float:
    """Microseconds per input character for one timed pass, GC held off.

    An engine that measured the pass ITSELF is believed over the wall clock: the
    Java row runs in a live JVM, and a `perf_counter` around it would charge
    ANTLR for the pipe carrying the input across. Every in-process engine has no
    such reading and is timed the ordinary way.
    """
    gc.disable()
    start = time.perf_counter()
    parse(corpus)
    elapsed = time.perf_counter() - start
    gc.enable()
    inner = getattr(parse, "measured_us", None)
    return (inner() if inner else elapsed * 1e6) / len(corpus)


def _prime(parse: Parse, corpus: str) -> None:
    """Bring one engine to steady state before any round counts.

    A JIT-compiled engine's first parses are not the engine — the Java row's
    first is ~20x its settled cost. `warm` parses until the median stops moving;
    an engine without one gets the single pass it always got.
    """
    warm = getattr(parse, "warm", None)
    if warm is None:
        parse(corpus)
        return
    warm(corpus)


def _interleaved(
    engines: dict[str, Parse], texts: dict[str, str], rounds: int
) -> dict[str, list[float]]:
    """One pass per engine per round, so machine load moves every column alike.

    ``texts`` names each row's document: the mt rows always read the full
    corpus, everyone else reads whatever the ``--full`` decision assigned.

    Each row's pass is followed by an UNTIMED ``gc.collect()``: the passes run
    under ``gc.disable()``, so without it a row inherits its predecessor's
    uncollected garbage — the row seated behind lexic-earley's allocation-heavy
    parse read +2-3% against a byte-identical artifact seated elsewhere. The
    collect levels the heap between rows; it is what removes that bias.

    The seats are still reshuffled every round so no row keeps one predecessor
    for effects a collect cannot level (cache warmth, frequency scaling). The
    shuffle is from a fixed seed, which makes runs REPRODUCIBLE, not unbiased:
    every process replays the identical schedule, so whatever residual seating
    effect a permutation carries is a constant across runs, never averaged
    away. The seat-check line is the display's own measurement of what's left.
    """
    for name, parse in engines.items():
        _prime(parse, texts[name])
    samples: dict[str, list[float]] = {name: [] for name in engines}
    seats = list(engines.items())
    rng = random.Random(0x5EA75)
    for _ in range(rounds):
        rng.shuffle(seats)
        for name, parse in seats:
            samples[name].append(_once(parse, texts[name]))
            gc.collect()
    return samples


def _medians(samples: dict[str, list[float]]) -> dict[str, float]:
    """Each row's reported figure: the median of its per-round passes."""
    return {name: sorted(runs)[len(runs) // 2] for name, runs in samples.items()}


def _noise_floor(parse: Parse, corpus: str, rounds: int) -> float:
    """Spread between two timings of the SAME engine, as a percentage.

    Anything below this is not a result. Printing it is what stops a 2%
    difference being read as a finding.
    """
    first = _medians(_interleaved({"a": parse}, {"a": corpus}, rounds))["a"]
    second = _medians(_interleaved({"a": parse}, {"a": corpus}, rounds))["a"]
    return abs(first - second) / max(first, second, 1e-9) * 100


_WARM_CONVERGED = 150
"""Warmup parses below which a JIT row has historically landed in its slow
mode. Requiring three consecutive stable batches converges the json row 4 runs
in 5 (0.118-0.148 µs/char, 192-204 parses) where one window converged 1 in 6;
a run that settles sooner than this is reported as SHORT, because the residual
bimodality is real and an unstated error bar is the thing to avoid."""

BAR_WIDTH = 40
"""Bar length. Wide enough that a 2x gap reads differently from a 4x one —
at 22 columns the log scale gave them three characters between them."""

_TINT: dict[str, str] = {
    "lexic-pda": "\x1b[38;5;39m",
    "lexic-lex": "\x1b[38;5;45m",
    "lexic-lex-ns": "\x1b[38;5;51m",
    "lexic-earley": "\x1b[38;5;208m",
    "lexic-mt": "\x1b[38;5;118m",
    "lexic-mt-lex-ns": "\x1b[38;5;84m",
    "stdlib-json": "\x1b[38;5;213m",
    "msgspec": "\x1b[38;5;213m",
    "lark-earley-lex": "\x1b[38;5;250m",
    "lark-lalr-lex": "\x1b[38;5;250m",
}
"""One distinct colour per lexic mode — the two rows this benchmark exists to
place are findable at a glance — plus one shared tint for the format
specialists, marking rows that answer a DIFFERENT question (no grammar taken).
Competitors keep the terminal's default foreground: colour marks whose row it
is and what kind, never better or worse.

The directive-matched lark seats take a DARKER tone of that default rather than
a colour of their own, because they are not a different tool — they are the
same one handed the grammar's own directives, and the pair reads as a pair."""

_DIM = "\x1b[2m"
_RESET = "\x1b[0m"


def _use_color(force: bool) -> bool:
    """Colour when forced, else only on a real terminal nobody opted out of.

    ``NO_COLOR`` (the informal cross-tool convention) wins over tty detection;
    piped output stays clean ANSI-free text either way.
    """
    return force or (sys.stdout.isatty() and "NO_COLOR" not in os.environ)


def _paint(text: str, code: str, on: bool) -> str:
    """``text`` wrapped in one ANSI colour, when colour is on and one applies."""
    return f"{code}{text}{_RESET}" if on and code else text


def _bar(value: float, best: float, worst: float) -> str:
    """A log-scaled bar, full width at the SLOWEST engine in this block.

    The scale used to be a fixed two decades, which saturated the moment one
    engine was 100x another — and with a JIT'd Java column in the table that is
    most rows. Every bar hit full width and the picture said nothing. Anchoring
    the top of the scale to the block's own worst ratio keeps the shape readable
    however far apart the engines turn out to be.
    """
    span = log10(max(worst / best, 10.0))
    ratio = max(value / best, 1.0)
    filled = min(BAR_WIDTH, round(log10(ratio) / span * BAR_WIDTH))
    return "█" * filled + "·" * (BAR_WIDTH - filled)


SPECIALISTS = frozenset(name for name, _make in _JSON_SPECIALISTS)
"""Rows that take NO grammar — hand-written C for one fixed format."""


def _amount(value: float) -> str:
    """One timing, in the unit that keeps its significant digits.

    Under a microsecond, three decimals of `µs/char` spends the whole number on
    leading zeros: the fastest rows here are tens of nanoseconds and `0.045`
    says less than `45.0` does.
    """
    return f"{value * 1000:9.1f} ns/char" if value < 1.0 else f"{value:9.3f} µs/char"


def _ranked_rows(timings: dict[str, float], color: bool) -> None:
    """The timed rows, fastest first, each with its bar and product.

    The `base` is the fastest engine that TAKES A GRAMMAR. A format specialist
    is a floor, not a competitor — anchoring the column to it would rate every
    general engine against hand-written C for one language and answer a question
    nobody asked. It still gets a ratio, below 1, which is the honest reading:
    what fraction of the specialist's cost the general engines run at.

    The BARS keep their own anchor at the block's genuine fastest row, so the
    picture is unchanged and the shift lives only in the ratio column.
    """
    ranked = sorted(timings.items(), key=lambda kv: kv[1])
    general = [v for n, v in ranked if n not in SPECIALISTS]
    fastest = ranked[0][1] if ranked else 1.0
    worst = ranked[-1][1] if ranked else 1.0
    best = general[0] if general else fastest
    for name, value in ranked:
        ratio = value / best
        rel = (
            "   base"
            if value == best
            else f"{ratio:6.3f}×"
            if ratio < 1
            else f"{ratio:6.1f}×"
        )
        tint = _TINT.get(name, "")
        label = _paint(f"{name:<17}", tint, color)
        shape = _paint(_bar(value, fastest, worst), tint, color)
        print(f"  {label}{_amount(value)} {rel}  {shape}  {PRODUCT.get(name, '?')}")


class Block(NamedTuple):
    """One grammar's finished measurements, ready to print.

    :ivar bench: The grammar and its documents.
    :ivar samples: Per-row timings, one list per round.
    :ivar refused: Rows that earned words instead of a number.
    :ivar floor: The harness's own noise, as a percentage.
    :ivar documents: What each row actually parsed.
    :ivar mt_note: Why the mt rows ran sequentially, or ``None`` when the
        split engaged (or no mt rows exist).
    """

    bench: Bench
    samples: dict[str, list[float]]
    refused: dict[str, str]
    floor: float
    documents: dict[str, str]
    mt_note: str | None


def _mt_check(bench: Bench, cores: int | None) -> str | None:
    """Why this grammar's mt rows did not thread, or ``None`` when they did.

    Asked of the split entry directly, not inferred from timings: a split
    that declines falls back to the sequential parse, so the mt cell alone
    cannot distinguish "threading bought nothing" from "nothing threaded".
    The same lesson as the seat check — a row that runs the same program as
    its twin must say so, or the spread between them reads as a result.
    """
    if cores is None:
        return None
    grammar = bench.compiled.codegen_grammar
    request = Request(bench.full, bench.fold, None)
    if (
        split_model(
            parse_model, grammar, request, cores, analysis=bench.compiled.grammar
        )
        is None
    ):
        return "the unified split seam found no eligible work on this document"
    return None


def _report(block: Block, color: bool) -> None:
    """One grammar's block: fastest first, with the bar and what each builds."""
    bench = block.bench
    sizes = {len(doc) for doc in block.documents.values()}
    note = (
        f"{len(bench.corpus):,} chars (mt rows: {len(bench.full):,})"
        if len(sizes) > 1
        else f"{max(sizes, default=len(bench.corpus)):,} chars"
    )
    print(
        f"\n─── {bench.name} · {note} · one grammar, "
        "every engine · bars log-scaled, full bar = slowest"
    )
    if not block.samples:
        print("    no engine could parse this grammar")
    _ranked_rows(_medians(block.samples), color)
    for name, why in sorted(block.refused.items()):
        label = _paint(f"{name:<17}", _TINT.get(name, ""), color)
        print(f"  {label}{'—':>9}             {_paint(why[:96], _DIM, color)}")
    print(
        f"  {'noise floor':<13}{block.floor:8.2f}%    "
        "smaller differences are not results"
    )
    if block.mt_note is not None:
        print(
            f"  {'mt check':<13}{'off':>8}     {block.mt_note} — the mt rows "
            "ran the same one-worker program as their sequential twins"
        )
    _seat_check(bench, block.samples)


def _seat_check(bench: Bench, samples: dict[str, list[float]]) -> None:
    """The harness's own error, read off two identical-by-construction rows.

    Where a grammar has NO `@non-semantic` marks, the two variant rows are
    compiled from identical `Directives` — the same program by construction —
    so any spread between them is instrument error, not a result, and the
    display says what it measured itself to be wrong by. That is the only
    identity this line claims: a non-empty mark set can change the compiled
    machine even when the codegen grammars compare equal (the noise
    declaration feeds the skip alphabet, not the grammar's shape), and no
    cheap artifact comparison certifies sameness in either direction — so a
    marked grammar gets no seat check rather than a false one. The statistic
    is PAIRED: the median of the per-round differences, so common-mode load
    cancels and its sign is readable — a signed constant is a seating bias,
    a wandering sign is noise.
    """
    if "lexic-lex" not in samples or "lexic-lex-ns" not in samples:
        return
    _, ns_marks = variant_marks(bench.ast)
    if ns_marks:
        return
    diffs = sorted(
        (ns - lex) / max(min(lex, ns), 1e-9) * 100
        for lex, ns in zip(samples["lexic-lex"], samples["lexic-lex-ns"])
    )
    spread = diffs[len(diffs) // 2]
    print(
        f"  {'seat check':<13}{spread:+8.2f}%    lexic-lex vs lexic-lex-ns run "
        "the same program — this spread is the harness's own error"
    )


def _warmup_note(engines: dict[str, Parse]) -> None:
    """What it took to make the JIT row honest, printed rather than assumed."""
    for name, parse in engines.items():
        warmed = getattr(parse, "warmed", None)
        if warmed is None:
            continue
        spent, settled = warmed
        state = "median settled" if settled else "STILL MOVING — number is soft"
        share = getattr(parse, "charstream_share", lambda: 0.0)()
        print(
            f"  {name + ' warmup':<13}{spent:6} parses   {state}; "
            f"{share * 100:.0f}% of the timed region builds the CharStream"
        )


def _legend(color: bool) -> None:
    """The engine roster, once, before any grammar's rows."""
    print(_paint("engines — what each row IS:", _DIM, color))
    for name, note in ENGINE.items():
        tint = _TINT.get(name, "")
        print(f"  {_paint(f'{name:<16}', tint, color)} {_paint(note, _DIM, color)}")


def _mark(cores: int | None) -> str:
    """The header's cores marker, empty when no MT rows were asked for."""
    return f"  cores={cores}" if cores is not None else ""


def _mt_cores(asked: int | None) -> int | None:
    """The lexic-mt thread count — the rows are ON by default when they can be.

    Reads ``cores`` the way lexic does (:mod:`lexic.parsing.parallel.policy`):
    ``--cores N`` is N; bare ``--cores`` and no flag alike are auto. Auto is
    1 on a GIL build, and that is where the rows drop out entirely — a
    "threaded" row running one thread answers a question nobody asked, and
    real threading there measured a net loss.
    """
    workers = available_workers() if asked in (None, AUTO) else asked
    return workers if workers > 1 else None


def main(argv: Sequence[str] | None = None) -> None:
    """Time every engine on every benchmark grammar."""
    parser = argparse.ArgumentParser(description=SUMMARY)
    parser.add_argument(
        "--rounds",
        type=int,
        default=DEFAULT_ROUNDS,
        help=f"timed rounds per engine (default {DEFAULT_ROUNDS}; 1 is a quick pass)",
    )
    parser.add_argument(
        "--cores",
        type=int,
        nargs="?",
        const=0,
        default=None,
        metavar="N",
        help="lexic-mt worker count: the corpus parsed as ONE document "
        "split across N workers (bare --cores = auto, the cpu count; "
        "free-threaded interpreter only — the GIL build measured a net loss)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="time every row on the full corpus (default: only the lexic-mt "
        "rows read it — the slow engines pay seconds per pass there)",
    )
    parser.add_argument(
        "--only", nargs="*", metavar="NAME", help="benchmark only these grammars"
    )
    parser.add_argument(
        "--color",
        action="store_true",
        help="force ANSI colour (auto: only on a terminal, honouring NO_COLOR)",
    )
    args = parser.parse_args(argv)
    if args.cores and available_workers() == 1:
        raise SystemExit(
            "--cores needs a free-threaded interpreter (python3.14t): "
            "threaded parsing under the GIL measured 0.82-0.92x, a net loss"
        )
    cores = _mt_cores(args.cores)
    color = _use_color(args.color)
    wanted = set(args.only or ())
    benches = [b for b in BENCHES if not wanted or b.name in wanted]
    if not benches:
        raise SystemExit(f"no such grammar: {sorted(wanted)}")
    print(
        f"rounds={args.rounds}{_mark(cores)}  grammars={', '.join(b.name for b in benches)}"
    )
    _legend(color)
    for bench in benches:
        engines, refused, documents = _engines(bench, cores, args.full)
        anchor = next(iter(engines), None)
        floor = (
            _noise_floor(engines[anchor], documents[anchor], args.rounds)
            if anchor
            else 0.0
        )
        _report(
            Block(
                bench,
                _interleaved(engines, documents, args.rounds),
                refused,
                floor,
                documents,
                _mt_check(bench, cores),
            ),
            color,
        )
        _warmup_note(engines)
        for parse in engines.values():
            getattr(parse, "close", lambda: None)()


if __name__ == "__main__":
    main()
