"""Time every engine on the same grammar and the same input.

    uv run python -m tools.benchmark.bench            # default rounds
    uv run python -m tools.benchmark.bench --rounds 1 # quick pass
    uv run python -m tools.benchmark.bench --only json arithmetic

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
import os
import sys
import time
from collections.abc import Callable, Sequence
from math import log10

import lark
import parsimonious

from lexic.parsing.pda.runtime.reduce_runtime import pda_model
from lexic.parsing.products import _model_product, earley_model
from tools.benchmark.antlr_build import antlr_parser
from tools.benchmark.antlr_java import java_antlr_parser
from tools.benchmark.emit import lark_grammar, peg_grammar, pyparsing_parser
from tools.benchmark.grammars import BENCHES, Bench
from tools.benchmark.refusals import REFUSALS, accepts, refusal

SUMMARY = "Time every engine on the same grammar and the same input."
"""The CLI description. Named, because `__doc__` is `str | None`."""

DEFAULT_ROUNDS = 7
"""Timed rounds per engine when none is asked for."""

PRODUCT: dict[str, str] = {
    "lexic-pda": "typed model",
    "lexic-earley": "typed model",
    "lark-earley": "Tree",
    "lark-lalr": "Tree",
    "parsimonious": "Node tree",
    "pyparsing": "ParseResults",
    "antlr": "ParserRuleContext · JAVA",
    "antlr-py": "ParserRuleContext",
}
"""What each engine BUILDS — the part a bare µs/char number hides.

`antlr` is ANTLR's Java target in a live JVM; every other row is Python. That
makes its cell a tool+runtime answer rather than an algorithm one — which is a
real question ("what parses this grammar fastest") and the one it is reported
for. `antlr-py` is the same generated parser on `antlr4-python3-runtime`, a
pure-Python ATN simulator and a different animal.
"""

Parse = Callable[[str], object]


def _antlr_name(bench: str) -> str:
    """An identifier grammar name for ANTLR's generated code."""
    return "B" + "".join(part.title() for part in bench.replace("-", "_").split("_"))


def _lexic(bench: Bench) -> dict[str, Parse]:
    """Both lexic engines over one compiled product — the PDA and Earley.

    Same grammar, same fold, same model: the only difference is which engine
    walks the input, which is the comparison these two columns exist for.

    The engine gets `codegen_grammar`, which is what `CompiledGrammar.parse`
    hands it and what the fold was BUILT against — the canonical grammar the
    competitors are given is the same language, but its arms and groups are not
    hoisted, so folding against it raises a missing-field error that looks like
    a synthesis bug in lexic and is really a mismatched pair here.
    """
    fold = bench.fold
    product = _model_product(bench.compiled.codegen_grammar, fold)
    return {
        "lexic-pda": lambda text: pda_model(product.pda, text, fold),
        "lexic-earley": lambda text: earley_model(
            product.instance_grammar, text, fold, product.tables
        ),
    }


def unfaithful(parse: Parse, bench: Bench) -> str | None:
    """The first way ``parse`` disagrees with lexic about the language, or None.

    The single place a translation is judged, in BOTH directions. An
    over-permissive one describes a larger language and passes any accept-only
    check; an over-restrictive one passes the corpus and then refuses a sentence
    nobody sampled — which is what a context-free lexer does to a grammar whose
    character classes overlap. Either way the engine gets no number, because a
    number for a different language is not a faster answer to the question, it
    is an answer to a different one.
    """
    why = refusal(parse, bench.corpus)
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


def _lark_parse(bench: Bench, parser: str) -> Parse:
    """Lark on one of its two algorithms, each given the token set it needs.

    The two backends carry different lexers and want different grammars, which
    is a distinction Lark's own documentation makes. `earley` runs a `dynamic`
    lexer that offers every matching terminal to the parser, so it settles an
    overlap itself and keeps the run terminals. `lalr` runs a `contextual` lexer
    that must commit to one terminal per position, so it gets the partitioned
    alphabet — without it a single space between `ws` and `chars` goes to the
    wrong slot, which is a token-set problem rather than a limit of LALR.
    """
    text = lark_grammar(bench.ast, refine=parser == "lalr")
    return lark.Lark(text, parser=parser).parse


def _peg_parse(bench: Bench) -> Parse:
    """parsimonious over the emitted PEG."""
    return parsimonious.Grammar(peg_grammar(bench.ast)).parse


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
    ("parsimonious", _peg_parse),
    # ANTLR builds a parser before anything runs — the Java tool, then javac for
    # the Java row. That is part of using ANTLR, as `Lark(...)` construction is,
    # so it happens here and never inside a timed round.
    ("antlr", lambda bench: java_antlr_parser(bench.ast, _antlr_name(bench.name))),
    ("antlr-py", lambda bench: antlr_parser(bench.ast, _antlr_name(bench.name))),
    ("pyparsing", _pp_parse),
)
"""Every competitor, as a name and the one way to build it from a bench."""


def _competitors(bench: Bench) -> tuple[dict[str, Parse], dict[str, str]]:
    """Every competitor that can take this grammar, and why the others cannot.

    A tool that cannot express the grammar gets a REASON in its own words, never
    a substituted easier grammar. Building is not enough either: a parser that
    builds and then describes a different language is exactly the failure a
    benchmark cannot see, so :func:`unfaithful` gates every candidate.
    """
    built: dict[str, Parse] = {}
    refused: dict[str, str] = {}
    for label, make in _CANDIDATES:
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


def _engines(bench: Bench) -> tuple[dict[str, Parse], dict[str, str]]:
    """Every engine to time, and the ones that could not take the grammar.

    lexic's own rows pass through the SAME :func:`unfaithful` gate as every
    competitor — corpus, accepts and rejects, both directions. The gate exists
    so no engine gets a number for a different language, and an engine exempt
    from it would be exactly the sycophancy the gate is there to prevent.
    """
    lexic = _lexic(bench)
    competitors, refused = _competitors(bench)
    working: dict[str, Parse] = {}
    for label, parse in lexic.items():
        wrong = unfaithful(parse, bench)
        if wrong is None:
            working[label] = parse
        else:
            refused[label] = wrong
    return {**working, **competitors}, refused


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
    engines: dict[str, Parse], corpus: str, rounds: int
) -> dict[str, float]:
    """One pass per engine per round, so machine load moves every column alike."""
    for parse in engines.values():
        _prime(parse, corpus)
    samples: dict[str, list[float]] = {name: [] for name in engines}
    for _ in range(rounds):
        for name, parse in engines.items():
            samples[name].append(_once(parse, corpus))
    return {name: sorted(runs)[len(runs) // 2] for name, runs in samples.items()}


def _noise_floor(parse: Parse, corpus: str, rounds: int) -> float:
    """Spread between two timings of the SAME engine, as a percentage.

    Anything below this is not a result. Printing it is what stops a 2%
    difference being read as a finding.
    """
    first = _interleaved({"a": parse}, corpus, rounds)["a"]
    second = _interleaved({"a": parse}, corpus, rounds)["a"]
    return abs(first - second) / max(first, second, 1e-9) * 100


BAR_WIDTH = 40
"""Bar length. Wide enough that a 2x gap reads differently from a 4x one —
at 22 columns the log scale gave them three characters between them."""

_LEXIC_TINT: dict[str, str] = {
    "lexic-pda": "\x1b[38;5;39m",
    "lexic-earley": "\x1b[38;5;208m",
}
"""One distinct colour per lexic mode — the two rows this benchmark exists to
place are findable at a glance. Competitors keep the terminal's default
foreground: colour marks WHOSE row it is, never better or worse."""

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


def _report(
    bench: Bench,
    timings: dict[str, float],
    refused: dict[str, str],
    floor: float,
    color: bool,
) -> None:
    """One grammar's block: fastest first, with the bar and what each builds."""
    print(
        f"\n─── {bench.name} · {len(bench.corpus):,} chars · one grammar, "
        "every engine · bars log-scaled, full bar = slowest"
    )
    if not timings:
        print("    no engine could parse this grammar")
    ranked = sorted(timings.items(), key=lambda kv: kv[1])
    best = ranked[0][1] if ranked else 1.0
    worst = ranked[-1][1] if ranked else 1.0
    for name, value in ranked:
        rel = f"{value / best:6.1f}×" if value > best else "   base"
        tint = _LEXIC_TINT.get(name, "")
        label = _paint(f"{name:<13}", tint, color)
        shape = _paint(_bar(value, best, worst), tint, color)
        print(f"  {label}{value:9.3f} µs/char {rel}  {shape}  {PRODUCT.get(name, '?')}")
    for name, why in sorted(refused.items()):
        label = _paint(f"{name:<13}", _LEXIC_TINT.get(name, ""), color)
        print(f"  {label}{'—':>9}             {_paint(why[:96], _DIM, color)}")
    print(f"  {'noise floor':<13}{floor:8.2f}%    smaller differences are not results")


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
        "--only", nargs="*", metavar="NAME", help="benchmark only these grammars"
    )
    parser.add_argument(
        "--color",
        action="store_true",
        help="force ANSI colour (auto: only on a terminal, honouring NO_COLOR)",
    )
    args = parser.parse_args(argv)
    color = _use_color(args.color)
    wanted = set(args.only or ())
    benches = [b for b in BENCHES if not wanted or b.name in wanted]
    if not benches:
        raise SystemExit(f"no such grammar: {sorted(wanted)}")
    print(f"rounds={args.rounds}  grammars={', '.join(b.name for b in benches)}")
    for bench in benches:
        engines, refused = _engines(bench)
        anchor = next(iter(engines.values()), None)
        floor = _noise_floor(anchor, bench.corpus, args.rounds) if anchor else 0.0
        _report(
            bench,
            _interleaved(engines, bench.corpus, args.rounds),
            refused,
            floor,
            color,
        )
        _warmup_note(engines)
        for parse in engines.values():
            getattr(parse, "close", lambda: None)()


if __name__ == "__main__":
    main()
