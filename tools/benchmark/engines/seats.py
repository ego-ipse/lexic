"""Every competitor seat, and the one way to build it from a bench.

A seat is a name and a constructor: given the case's one `IrAst`, produce the
parse entry that engine would be used through. Building is not the whole
question — a parser that builds and then describes a different language is the
failure a benchmark cannot see from its own numbers — so :func:`competitors`
puts every candidate through the language gate and reports the reason for the
ones that do not survive, in the tool's own words.

Kept apart from the roster and the timing protocol because this is where a new
engine lands: adding one is a row in :data:`_CANDIDATES` and a constructor
beside the others, and it touches nothing that decides what a row MEANS.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from importlib import import_module

from tools.benchmark.cases.grammars import Bench, declared_marks
from tools.benchmark.emitters.directives import NO_MARKS
from tools.benchmark.engines.refusals import refusals
from tools.benchmark.measurement.language import unfaithful
from tools.benchmark.measurement.sampling import Parse


def _antlr_name(bench: str) -> str:
    """An identifier grammar name for ANTLR's generated code."""
    return "B" + "".join(part.title() for part in bench.replace("-", "_").split("_"))


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
        :data:`~tools.benchmark.bench.PRODUCT` for why that is a seat rather
        than a correction.
    """
    lark = import_module("lark")
    lark_grammar = import_module("tools.benchmark.emitters.emit").lark_grammar
    marks = declared_marks(bench) if marked else NO_MARKS
    text = lark_grammar(bench.ast, refine=parser == "lalr", marks=marks)
    return lark.Lark(text, parser=parser).parse


def _peg_parse(bench: Bench, marked: bool = False) -> Parse:
    """parsimonious over the emitted PEG, compiled on stdlib ``re``.

    parsimonious prefers the third-party ``regex`` module when installed and
    ships it as a dependency, but stdlib ``re`` measured 9-19% faster on the
    bench's patterns. The row measures the PEG scheme, not the dependency's
    regex engine, so the grammar is compiled under the faster module — a
    construction-time swap only; matching runs on the compiled patterns.
    """
    parsimonious = import_module("parsimonious")
    expressions = import_module("parsimonious.expressions")
    peg_grammar = import_module("tools.benchmark.emitters.emit").peg_grammar
    preferred = getattr(expressions, "re")
    setattr(expressions, "re", re)
    try:
        marks = declared_marks(bench) if marked else NO_MARKS
        return parsimonious.Grammar(peg_grammar(bench.ast, marks)).parse
    finally:
        setattr(expressions, "re", preferred)


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

    The built element carries its own end-of-input anchor, so no row passes
    `parse_all` — see `structured.pyparsing_parser` for the language that flag
    silently widened.
    """
    pyparsing_parser = import_module(
        "tools.benchmark.emitters.structured"
    ).pyparsing_parser
    cheap = pyparsing_parser(bench.ast, longest=False).parse_string
    if unfaithful(cheap, bench) is None:
        return cheap
    return pyparsing_parser(bench.ast, longest=True).parse_string


def _java_parse(bench: Bench, marked: bool = False) -> Parse:
    """Build one Java ANTLR row without importing ANTLR for Lexic workers."""
    java_antlr_parser = import_module(
        "tools.benchmark.engines.antlr_java"
    ).java_antlr_parser
    marks = declared_marks(bench) if marked else NO_MARKS
    suffix = "-lex" if marked else ""
    return java_antlr_parser(bench.ast, _antlr_name(bench.name + suffix), marks)


def _antlr_parse(bench: Bench, marked: bool = False) -> Parse:
    """Build one Python ANTLR row without importing ANTLR for Lexic workers."""
    antlr_parser = import_module("tools.benchmark.engines.antlr_build").antlr_parser
    marks = declared_marks(bench) if marked else NO_MARKS
    suffix = "-lex" if marked else ""
    return antlr_parser(bench.ast, _antlr_name(bench.name + suffix), marks)


def _msgspec_parse(_bench: Bench) -> Parse:
    """Load msgspec only when its JSON specialist row is requested."""
    msgspec = import_module("msgspec")
    return msgspec.json.decode


_CANDIDATES: tuple[tuple[str, Callable[[Bench], Parse]], ...] = (
    ("lark-earley", lambda bench: _lark_parse(bench, "earley")),
    ("lark-lalr", lambda bench: _lark_parse(bench, "lalr")),
    ("lark-earley-lex", lambda bench: _lark_parse(bench, "earley", marked=True)),
    ("lark-lalr-lex", lambda bench: _lark_parse(bench, "lalr", marked=True)),
    ("parsimonious", _peg_parse),
    ("parsimonious-lex", lambda bench: _peg_parse(bench, marked=True)),
    # ANTLR builds a parser before anything runs — the Java tool, then javac for
    # the Java row. That is part of using ANTLR, as `Lark(...)` construction is,
    # so it happens here and never inside a timed round.
    ("antlr", _java_parse),
    ("antlr-lex", lambda bench: _java_parse(bench, marked=True)),
    ("antlr-py", _antlr_parse),
    ("antlr-py-lex", lambda bench: _antlr_parse(bench, marked=True)),
    ("pyparsing", _pp_parse),
)
"""Every competitor, as a name and the one way to build it from a bench."""


_JSON_SPECIALISTS: tuple[tuple[str, Callable[[Bench], Parse]], ...] = (
    ("stdlib-json", lambda bench: json.loads),
    ("msgspec", _msgspec_parse),
)
"""The json row's format specialists (see :data:`~tools.benchmark.bench.PRODUCT`)."""

SPECIALISTS = frozenset(name for name, _make in _JSON_SPECIALISTS)
"""Seats that take NO grammar, so only one direction is a claim about them.

A specialist's language is the FORMAT it hard-codes, and that format is strictly
larger than the row's grammar — the bench's json admits no comma inside a string
and no trailing whitespace after the document, and every real json parser takes
both. Asking one to refuse those is asking it to be a different program, so the
refusing half of :func:`~tools.benchmark.measurement.language.unfaithful` is not
asked of these rows at all.

What IS asked, and is the whole claim their cells make, is the accepting half:
they must take every sentence the row's grammar derives, including the derived
probes. A specialist that refused one would be answering an easier question than
the seats beside it.
"""


def candidates(bench: Bench) -> tuple[tuple[str, Callable[[Bench], Parse]], ...]:
    """The candidate rows for one bench: every engine, plus its specialists.

    A specialist parses one fixed FORMAT, so it is a candidate only for the
    bench whose language it hard-codes — offering `json.loads` a csv corpus
    would print a refusal row that answers no question anyone asked.
    """
    if bench.name != "json":
        return _CANDIDATES
    return _CANDIDATES + _JSON_SPECIALISTS


def competitors(bench: Bench) -> tuple[dict[str, Parse], dict[str, str]]:
    """Every competitor that can take this grammar, and why the others cannot.

    A tool that cannot express the grammar gets a REASON in its own words, never
    a substituted easier grammar. Building is not enough either: a parser that
    builds and then describes a different language is exactly the failure a
    benchmark cannot see, so :func:`~tools.benchmark.measurement.language.unfaithful`
    gates every candidate.
    """
    built: dict[str, Parse] = {}
    refused: dict[str, str] = {}
    for label, make in candidates(bench):
        try:
            parse = make(bench)
        except refusals() as exc:
            refused[label] = f"{type(exc).__name__}: {' '.join(str(exc).split())}"
            continue
        wrong = unfaithful(parse, bench, fixed_language=label in SPECIALISTS)
        if wrong is None:
            built[label] = parse
        else:
            refused[label] = wrong
            getattr(parse, "close", lambda: None)()
    return built, refused
