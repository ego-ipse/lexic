"""The benchmark's translations must describe the language lexic compiles.

`tools/benchmark/emit.py` derives every competitor's grammar from the one
`IrAst` lexic itself parses, so that a row compares one question rather than
several. That claim is only worth anything if it is CHECKED: a mistranslated
grammar still parses, still produces a number, and the number is a lie.

`tools.benchmark.bench` applies the differential in both directions before any
engine earns a row. Accepting the corpus proves almost nothing on its own — a
grammar that accepts everything passes it — and neither does refusing the
rejects, since a translation that refuses everything passes that half. Both
halves have caught real bugs: a Lark regex terminated by its own `/` member, a
PEG string broken by a literal newline, a pyparsing parser that silently skipped
whitespace, and an ANTLR lexer that could not put the word `true` inside a json
string because the parser's own literal token outranked the character class.

What this file adds is what that gate cannot see: which engines are SUPPOSED to
survive each grammar, that lexic is not being asked an easier question than the
competitors, and that the lexical layer handed out is the one lexic derives.
"""

from __future__ import annotations

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.lexruns import run_candidates
from lexic.parsing.earley.normalize import normalize
from tools.benchmark.bench import SPECIALISTS, _competitors, unfaithful
from tools.benchmark.cases.grammars import BENCHES, Bench, declared_marks
from tools.benchmark.emitters.charsets import of_points
from tools.benchmark.emitters.emit import lexical_layer, peg_grammar
from tools.benchmark.emitters.structured import antlr_grammar
from tools.benchmark.engines.refusals import LEXIC_REFUSALS, accepts
from tools.benchmark.measurement import sampling
from tools.benchmark.measurement.sampling import Parse, interleaved
from tools.benchmark.presentation.reporting import _warmup_note

_ALL = frozenset(
    {
        "lark-earley",
        "lark-lalr",
        "lark-earley-lex",
        "lark-lalr-lex",
        "parsimonious",
        "parsimonious-lex",
        "pyparsing",
        "antlr",
        "antlr-lex",
        "antlr-py",
        "antlr-py-lex",
    }
)

_DIRECTIVE_MATCHED = frozenset(
    {
        "lark-earley-lex",
        "lark-lalr-lex",
        "parsimonious-lex",
        "antlr-lex",
        "antlr-py-lex",
    }
)
"""The seats built with the grammar's own directives translated. Folding a rule
into a TERMINAL moves a decision from the parser to the lexer, and a lexer has
neither the parser state nor the backtracking to make it — so the fold is worth
3x where it lands and costs a row outright where it does not. Both outcomes are
pinned, because a fold that silently stopped applying would otherwise read as
the competitor merely getting slower."""

EXPECTED: dict[str, frozenset[str]] = {
    "arithmetic": _ALL,
    "csv": _ALL,
    "json": _ALL,
    # PEG and pyparsing both have POSSESSIVE repetition and cannot back out of a
    # committed one: `seq-rest ::= n item` swallows the NEXT rule's name and
    # there is no way back, so they stop at char 244 of `json.gbnf`. That is a
    # property of those formalisms, not of the emitters. The ABNF self-grammar
    # has no such shape: once the emitters order an EMPTY arm last — the order
    # any ordered-choice author writes, see `emit._choice_arms` — parsimonious
    # holds the whole grammar. lark-lalr builds gbnf-meta and then answers a
    # shift/reduce resolution wrong at parse time: the token partition is
    # proven adequate (lark-earley parses the corpus over the SAME refined
    # grammar), so the grammar is simply not LALR(1). On abnf-meta it refuses
    # at build with a reduce/reduce collision — same verdict, said earlier.
    # lexic's own PDA declines both self-grammars (island start rule) and the
    # benchmark reports that rather than hiding it; the Earley rows answer.
    # PEG commits to `document`'s first matching block and cannot back out, so
    # it stops partway; every other tool holds the whole subset. ANTLR escalates
    # to full-context prediction here, which is why the harness's error listener
    # must implement the prediction hooks rather than only the verdict ones.
    # markdown loses lark-lalr-lex: folding `fenceline` into a terminal makes it
    # munch the newline that closes the fence, which the contextual lexer cannot
    # take back. The unfolded lark-lalr seat still holds the row.
    "markdown": _ALL - frozenset({"parsimonious", "parsimonious-lex", "lark-lalr-lex"}),
    # 200 nested levels: pyparsing recurses per level and exhausts the
    # interpreter stack. A depth limit of the tool, not of the translation.
    "nested": _ALL - frozenset({"pyparsing"}),
    # Long terminals, trivial decisions — nothing here is hard for anyone.
    "lexruns": _ALL,
    # An unbounded shared prefix: PEG and pyparsing backtrack through it,
    # ANTLR predicts it, lark-lalr survives because the divergence is a single
    # token once lexed. Everyone holds it; what differs is what it costs.
    "backtrack": _ALL,
    # Three record kinds decided by their first character and closed by their
    # own delimiter: nothing here is hard for any formalism. What the row
    # prices is lexic's SPLIT declining, not any engine struggling.
    "mixedends": _ALL,
    # A header line then body lines until the next header — one token of
    # lookahead for everyone. Same as above: the row prices the split, and
    # every engine holds the grammar.
    "announced": _ALL,
    "gbnf-meta": frozenset({"lark-earley", "lark-earley-lex", "antlr", "antlr-py"}),
    # abnf-meta loses BOTH directive-matched seats: `c-wsp` folds to a nullable
    # terminal, which Lark's dynamic Earley refuses outright ("zero-width
    # regexps") and its contextual lexer collides on. The unfolded rows answer.
    # parsimonious goes too, on a derived probe rather than on the corpus: an
    # `alternation` whose arms are separated by `c-wsp*` needs a shorter reading
    # of the preceding run, and PEG's repetition is possessive.
    "abnf-meta": frozenset({"lark-earley", "antlr", "antlr-py", "pyparsing"}),
    # vyx is authored as pure CFG with disjoint arms (ordered choice spelled by
    # charset subtraction), so it survives everywhere its formalism can back out
    # of a committed choice. lark-lalr refuses at build with a reduce/reduce
    # collision: not LALR(1). The two ordered-choice seats go on a derived probe
    # — `!X:P L2< D:{ } >` needs the optional `body` to be re-tried after its
    # first arm fails deep inside, which neither PEG's possessive `?` nor
    # pyparsing's `Or` (longest match per decision, not a context-free parse)
    # can do. Both held the corpus and every authored sentence.
    "vyx": frozenset({"lark-earley", "lark-earley-lex", "antlr", "antlr-py"}),
}
"""Which competitors must survive each grammar, pinned.

The gate drops an unfaithful engine silently — right for a report, useless as a
regression signal, because an emitter that starts producing broken Lark looks
exactly like Lark declining the grammar. Pinning the floor turns a silent drop
into a red test. Every name missing from a set here is a limit argued out above,
never a shrug.
"""


_BUILT: dict[str, dict[str, Parse]] = {}
"""Memo for :func:`_built`, keyed by bench NAME.

A `Bench` carries lexic's `CompiledGrammar`, which holds a dict of synthesised
classes and is therefore unhashable — so this is a plain dict rather than
`functools.cache`.
"""


def _built(bench: Bench) -> dict[str, Parse]:
    """Every competitor the benchmark would report for ``bench``.

    Memoised: ANTLR shells out to a Java tool per grammar and then to `javac`,
    and the tests over four grammars would otherwise pay for that many times.
    """
    if bench.name not in _BUILT:
        _BUILT[bench.name] = _competitors(bench)[0]
    return _BUILT[bench.name]


@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_every_reported_engine_agrees_with_lexic(bench: Bench) -> None:
    """No row is printed for a grammar we mistranslated, in either direction."""
    for name, parse in _built(bench).items():
        wrong = unfaithful(parse, bench, fixed_language=name in SPECIALISTS)
        assert wrong is None, (
            f"{bench.name}: the {name} translation {wrong} — the benchmark would "
            "print a number for a language that is not the grammar's"
        )


@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_the_expected_engines_survive_every_grammar(bench: Bench) -> None:
    """The pinned floor, so an emitter regression cannot hide as a tool limit."""
    missing = EXPECTED[bench.name] - set(_built(bench))
    assert not missing, (
        f"{bench.name}: {sorted(missing)} no longer survive this grammar — "
        "suspect the emitters before believing the tools changed their minds"
    )


@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_lexic_is_not_asked_an_easier_question(bench: Bench) -> None:
    """No bench may carry `@non-semantic`, because lexic would relax it.

    `@non-semantic` marks rules skippable noise, and lexic's codegen pass gives
    every top-level reference to one `min=0`. A grammar carrying one is a
    grammar lexic parses MORE LOOSELY than the text every competitor is handed —
    whitespace and comments optional for lexic, mandatory for everyone else.
    That asymmetry is why five tools were once recorded as unable to express a
    grammar lexic reads without trouble.

    Keeping the set empty is what makes `grammar` and `codegen_grammar` describe
    the same language, so the translation needs no per-tool compensation.
    """
    flagged = sorted(bench.ast.non_semantic or ())
    assert not flagged, (
        f"{bench.name}: {flagged} are marked non-semantic, so lexic relaxes "
        "references to them and parses a looser language than the competitors "
        "are given — either drop the directive or give every tool its own "
        "ignore mechanism (`%ignore`, `-> skip`, default whitespace)"
    )


@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_the_emitted_lexical_layer_is_the_one_lexic_derives(bench: Bench) -> None:
    """Competitors get lexic's run terminals — and never one it declined.

    lexic collapses proved-safe character repetitions into single maximal-munch
    run terminals, so it reads csv as ~1,400 units. An emitter that dissolves
    that layer hands every lexer-based competitor 12,539 single-character tokens
    and the row measures the missing lexer rather than the engines. One that
    invents a run lexic declined hands them a munch lexic itself refused:
    `run_candidates` drops any run whose FOLLOW set meets its charset, and
    collapsing it anyway silently changes the language.
    """
    licensed = {
        of_points(chars)
        for chars, _empty, _unit in run_candidates(
            compile_tables(normalize(bench.ast))
        ).values()
    }
    given = {run.chars for run in lexical_layer(bench.ast).values()}
    assert given <= licensed, (
        f"{bench.name}: a run terminal was emitted that lexic never licensed — "
        "the competitors are being handed a maximal munch lexic itself refused"
    )
    assert given, (
        f"{bench.name}: lexic derives {len(licensed)} run terminals here and the "
        "emitters handed out none — the lexical layer is being dissolved"
    )


def test_each_timed_benchmark_sample_is_preconditioned_by_its_own_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each isolated worker measures hot executions of its one engine.

    The initial parse is the ordinary one-time prime. Each timed sample then
    gets one untimed pass of the SAME engine immediately before it, keeping the
    reported value a median of individual timed parses. Public workers contain
    no other engine; this pins the low-level sampling protocol itself.
    """
    events: list[str] = []

    def parse(_text: str) -> object:
        events.append("parse")
        return object()

    def timed(_parse: Parse, _text: str) -> float:
        events.append("timed")
        return 1.0

    monkeypatch.setattr(sampling, "once", timed)
    monkeypatch.setattr(sampling.gc, "collect", lambda: None)

    assert interleaved({"row": parse}, {"row": "x"}, 2) == {"row": [1.0, 1.0]}
    assert events == ["parse", "parse", "timed", "parse", "timed"]


def test_peg_and_antlr_can_translate_the_directive_matched_variant() -> None:
    """The new seats receive the same authored marks as Lark's ``-lex`` rows."""
    bench = next(candidate for candidate in BENCHES if candidate.name == "json")
    marks = declared_marks(bench)

    assert peg_grammar(bench.ast, marks) != peg_grammar(bench.ast)
    assert antlr_grammar(bench.ast, "MarkedJson", marks) != antlr_grammar(
        bench.ast, "MarkedJson"
    )


def test_the_antlr_warmup_note_displays_its_cold_first_parse(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Cold execution is visible beside, but separate from, the warm median."""

    class Parser:
        """A callable exposing the Java benchmark's reporting attributes."""

        warmed = (24, True)
        cold_us_per_char = 3.25

        def __call__(self, _text: str) -> object:
            """Satisfy the benchmark parser protocol."""
            return object()

        @staticmethod
        def charstream_share() -> float:
            """A representative stream-construction share."""
            return 0.2

    engines: dict[str, Parse] = {"antlr": Parser()}
    _warmup_note(engines)

    shown = capsys.readouterr().out
    assert "antlr first" in shown
    assert "3.250 µs/char" in shown
    assert "cold" in shown


def _lexic_takes(bench: Bench, text: str) -> bool:
    """Whether the row's own compiled artefact accepts ``text``."""
    return accepts(
        lambda body: bench.compiled.parse(body, cores=1), text, LEXIC_REFUSALS
    )


@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_the_derived_probes_catch_a_widening_no_authored_sentence_can(
    bench: Bench,
) -> None:
    """A seat that ignores trailing whitespace passes every authored sentence.

    That is not a hypothetical: it is what `parse_string(parse_all=True)` did to
    the pyparsing seat, whose end-of-input anchor was built outside the emitter's
    empty-whitespace window and therefore skipped whitespace. The authored
    `rejects` hold no sentence of the form "the corpus with a newline on the
    end", so the gate that existed could not see it on nine of the ten benches
    pyparsing builds on. The derived probes can.
    """
    if _lexic_takes(bench, bench.corpus + "\n"):
        pytest.skip(f"{bench.name} admits a trailing newline, so this is no widening")

    def widened(text: str) -> object:
        """lexic behind an end-of-input anchor that skips whitespace.

        The whole input is tried first, so the language is strictly larger and
        never different — what is added is exactly what the pyparsing anchor
        added: a prefix that parses, and trailing whitespace walked over.
        """
        error: BaseException = UnsupportedConstructError("widened: no reading")
        for at in range(len(text), len(text.rstrip()) - 1, -1):
            try:
                return bench.compiled.parse(text[:at], cores=1)
            except LEXIC_REFUSALS as exc:
                error = exc
        raise error

    if any(accepts(widened, text, LEXIC_REFUSALS) for text in bench.rejects):
        pytest.skip(f"{bench.name}: an authored reject already separates this")
    assert unfaithful(widened, bench, exceptions=LEXIC_REFUSALS) is not None, (
        f"{bench.name}: a parser accepting the corpus with trailing whitespace "
        "passed the faithfulness gate — the gate is back to proving nothing"
    )


@pytest.mark.parametrize("bench", BENCHES, ids=lambda b: b.name)
def test_the_pyparsing_seat_anchors_inside_its_own_whitespace_window(
    bench: Bench,
) -> None:
    """pyparsing's end-of-input must not be the one element that skips space.

    `parse_string`'s `parse_all` builds its `StringEnd()` at PARSE time, after
    :func:`pyparsing_parser` has restored `DEFAULT_WHITE_CHARS`, so that one
    element admitted whitespace the grammar has no rule for. The anchor is part
    of the returned element instead, and the same call is where tab expansion
    was turned off — `parse_string` expands a tab to eight spaces by default,
    which handed a class holding a space a tab it does not hold.
    """
    parse = _built(bench).get("pyparsing")
    if parse is None:
        pytest.skip(f"pyparsing does not survive {bench.name}")
    for suffix in ("\n", " ", "\t", "\r", "  \n"):
        text = bench.corpus + suffix
        assert accepts(parse, text) == _lexic_takes(bench, text), (
            f"{bench.name}: pyparsing and lexic disagree about {suffix!r} on the "
            "end of the corpus — the anchor is outside the whitespace window"
        )
    tabbed = bench.corpus.replace(" ", "\t", 1)
    assert accepts(parse, tabbed) == _lexic_takes(bench, tabbed), (
        f"{bench.name}: pyparsing and lexic disagree about a tab in the corpus — "
        "parse_string is expanding it to spaces before the parser sees it"
    )
