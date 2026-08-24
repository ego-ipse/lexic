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

from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.lexruns import run_candidates
from lexic.parsing.earley.normalize import normalize
from tools.benchmark.bench import Parse, _competitors, unfaithful
from tools.benchmark.charsets import of_points
from tools.benchmark.emit import lexical_layer
from tools.benchmark.grammars import BENCHES, Bench

_ALL = frozenset(
    {
        "lark-earley",
        "lark-lalr",
        "lark-earley-lex",
        "lark-lalr-lex",
        "parsimonious",
        "pyparsing",
        "antlr",
        "antlr-py",
    }
)

_DIRECTIVE_MATCHED = frozenset({"lark-earley-lex", "lark-lalr-lex"})
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
    "markdown": _ALL - frozenset({"parsimonious", "lark-lalr-lex"}),
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
    "abnf-meta": frozenset(
        {"lark-earley", "antlr", "antlr-py", "pyparsing", "parsimonious"}
    ),
    # vyx is authored as pure CFG with disjoint arms (ordered choice spelled by
    # charset subtraction), so the ordered-choice engines hold it whole —
    # parsimonious needed only the `"` escape inside `~r"[...]"` (a class with
    # the `!-"` range terminated the regex literal mid-class; the same
    # notation-specific-escaping family as the Lark `/` bug). lark-lalr
    # refuses at build with a reduce/reduce collision: not LALR(1).
    "vyx": frozenset(
        {
            "lark-earley",
            "lark-earley-lex",
            "antlr",
            "antlr-py",
            "pyparsing",
            "parsimonious",
        }
    ),
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
        wrong = unfaithful(parse, bench)
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
