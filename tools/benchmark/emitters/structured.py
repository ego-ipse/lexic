"""Pyparsing and ANTLR projections of the canonical benchmark grammar."""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

import pyparsing as pp

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSelf,
    IrSequence,
)
from tools.benchmark.emitters.charsets import (
    CharSet,
    complement,
    of_points,
    overlap,
    partition,
)
from tools.benchmark.emitters.directives import NO_MARKS, Marks, inlined_marks
from tools.benchmark.emitters.emit import (
    Lex,
    Runs,
    _ANTLR_SPECIALS,
    _UNIT,
    _antlr_escaped,
    _bounds,
    _choice_arms,
    _live,
    _members,
    _negated_class,
    _names,
    _known_ref,
    _quantified,
    _ranges,
    _rule_map,
    _term_for,
    charset_of,
    lexical_layer,
)


def pyparsing_parser(ast: IrAst, longest: bool = True) -> pp.ParserElement:
    """``ast`` as a live pyparsing element.

    pyparsing has no grammar notation to emit into — it is combinators — so the
    translation builds objects instead of text. Forward references are declared
    up front so recursion resolves, which is the only structural difference from
    the text emitters.

    :param longest: Spell alternation as `Or` (try every arm, keep the longest)
        rather than `MatchFirst` (commit to the first that matches). `Or` is the
        faithful reading of a context-free `|`; `MatchFirst` silently imposes
        PEG's ordered choice, and a grammar whose arms share a prefix then
        describes a different language — which is what dropped a meta row and
        got written down as a pyparsing limitation.
    """
    if longest:
        # `Or` re-tries every arm at every position and is exponential without
        # memoisation — 2s for 200 characters of `arithmetic`. It is switched on
        # only for the parsers that need it, because turning it on globally
        # would charge every other pyparsing row for a feature it never used.
        pp.ParserElement.enable_packrat()
    rules, start = _rule_map(ast)
    # pyparsing SKIPS WHITESPACE BY DEFAULT, and a parser that quietly ignores
    # spaces is not the grammar it was given — it accepted `1 + 2` for a grammar
    # with no space in it. Leaving it off per leaf is not enough: every
    # composite re-enables it, so the default is cleared for the whole build.
    previous = pp.ParserElement.DEFAULT_WHITE_CHARS
    pp.ParserElement.set_default_whitespace_chars("")
    try:
        forwards = {name: pp.Forward() for name in rules}
        choice = pp.Or if longest else pp.MatchFirst
        for name, body in rules.items():
            forwards[name] <<= _pp(body, forwards, choice)
        return forwards[start]
    finally:
        pp.ParserElement.set_default_whitespace_chars(previous)


def _pp_alternation(node: IrAlternation, fwd: dict[str, pp.Forward], choice):
    """Whichever alternation `pyparsing_parser` was asked for — see it for why.

    Arms in :func:`_choice_arms` order: `Or` keeps the longest whatever the
    order, and `MatchFirst` needs the empty arm last for the same reason PEG
    does.
    """
    return choice([_pp(arm, fwd, choice) for arm in _choice_arms(node)])


def _pp_sequence(node: IrSequence, fwd: dict[str, pp.Forward], choice):
    parts = [_pp(item, fwd, choice) for item in node]
    return pp.And(parts) if parts else pp.Empty()


def _pp_item(node: IrItem, fwd: dict[str, pp.Forward], choice):
    atom = _pp(node.atom, fwd, choice)
    lo, hi = _bounds(node.quantifier)
    if node.quantifier == _UNIT:
        return atom
    if (lo, hi) == (0, 1):
        return pp.Opt(atom)
    if (lo, hi) == (0, -1):
        return pp.ZeroOrMore(atom)
    if (lo, hi) == (1, -1):
        return pp.OneOrMore(atom)
    return atom * (lo, None if hi < 0 else hi)


def _pp_literal(node: IrLiteral | IrChr, _fwd: dict[str, pp.Forward], _choice):
    return pp.Literal(str(node))


def _pp_charclass(node: IrCharClass, _fwd: dict[str, pp.Forward], _choice):
    return pp.Regex(f"[{_members(node)}]")


def _pp_ruleref(node: IrRuleRef, fwd: dict[str, pp.Forward], _choice):
    key = str(node)
    if key not in fwd:
        raise UnsupportedConstructError(f"benchmark: reference to unknown {key!r}")
    return fwd[key]


def _pp_not(node: IrNot, _fwd: dict[str, pp.Forward], _choice):
    inner = node[0]
    if not isinstance(inner, IrCharClass):
        raise UnsupportedConstructError(
            f"benchmark: pyparsing cannot express IrNot over {type(inner).__name__}"
        )
    return pp.Regex(f"[^{_members(inner)}]")


_PP: dict[type, Callable[..., pp.ParserElement]] = {
    IrAlternation: _pp_alternation,
    IrSequence: _pp_sequence,
    IrItem: _pp_item,
    IrLiteral: _pp_literal,
    IrChr: _pp_literal,
    IrCharClass: _pp_charclass,
    IrRuleRef: _pp_ruleref,
    IrNot: _pp_not,
}
"""Node type → its pyparsing element."""


def _pp(node: IrSelf, fwd: dict[str, pp.Forward], choice) -> pp.ParserElement:
    build = _PP.get(type(node))
    if build is None:
        raise UnsupportedConstructError(
            f"benchmark: no pyparsing element for {type(node).__name__}"
        )
    return build(node, fwd, choice)


# ── ANTLR (.g4 text, then a Java codegen step) ─────────────────────────────


_ANTLR_KEYWORDS = frozenset(
    {
        "grammar", "lexer", "parser", "options", "tokens", "import", "fragment",
        "returns", "locals", "throws", "catch", "finally", "mode", "channels",
        "header", "members", "init", "after", "rule",
    }
)  # fmt: skip
"""ANTLR's own reserved words.

The GBNF self-grammar's start rule is called `grammar`, which is the keyword
that opens an ANTLR file — so emitting it produced a build error that read as
"ANTLR cannot express GBNF" when the only problem was a name.
"""


def _antlr_safe(name: str) -> str:
    """A rule name ANTLR will not read as one of its own keywords."""
    return f"{name}_" if name in _ANTLR_KEYWORDS else name


class Blocks(NamedTuple):
    """The partitioned lexer alphabet — one token per disjoint block.

    :ivar sets: Block index → the code points it holds.
    :ivar of_class: A character class → the blocks whose union it is.
    :ivar of_char: A literal's character → the single block holding it.
    """

    sets: list[CharSet]
    of_class: dict[CharSet, tuple[int, ...]]
    of_char: dict[str, int]


def _alphabet(rules: dict[str, IrSelf], runs: Runs) -> tuple[list[CharSet], set[str]]:
    """Every character class and literal character the emission still needs.

    Anything under a kept run is skipped: the run terminal consumes it, and
    declaring its class again would put a second token over the same code points.
    """
    classes: list[CharSet] = []
    chars: set[str] = set()

    def visit(node: IrSelf) -> None:
        if isinstance(node, IrItem) and node in runs:
            return
        if isinstance(node, IrCharClass):
            classes.append(charset_of(node))
        elif isinstance(node, IrNot):
            inner = node[0]
            if not isinstance(inner, IrCharClass):
                raise UnsupportedConstructError(
                    f"benchmark: ANTLR cannot express IrNot over {type(inner).__name__}"
                )
            classes.append(complement(charset_of(inner)))
        elif isinstance(node, (IrLiteral, IrChr)):
            chars.update(str(node))
        elif isinstance(node, tuple):
            for child in node:
                visit(child)

    for body in rules.values():
        visit(body)
    return classes, chars


def safe_runs(rules: dict[str, IrSelf], runs: Runs) -> Runs:
    """The runs that survive ANTLR's lexer having to decide without context.

    A run terminal is maximal-munch, so it is safe only where its code points
    appear NOWHERE else in the grammar. Otherwise the lexer munches a run across
    a position where the parser needed a single character, and no declaration
    order fixes it. An unsafe run is dropped and its characters rejoin the
    partition, one token per block — slower, and correct, which is the trade the
    two-tier design actually offers.
    """
    kept = dict(runs)
    while kept:
        classes, chars = _alphabet(rules, kept)
        plain = classes + [of_points(c) for c in chars]
        entries = list(kept.items())
        unsafe = [
            item
            for index, (item, run) in enumerate(entries)
            if any(overlap(run.chars, other) for other in plain)
            or any(
                overlap(run.chars, o.chars)
                for j, (_, o) in enumerate(entries)
                if j != index
            )
        ]
        if not unsafe:
            break
        for item in unsafe:
            kept.pop(item)
    return kept


def partition_blocks(rules: dict[str, IrSelf], runs: Runs) -> Blocks:
    """Refine every class and literal character into disjoint lexer blocks."""
    classes, chars = _alphabet(rules, runs)
    unique: list[CharSet] = list(dict.fromkeys(classes))
    letters = sorted(chars)
    blocks, members = partition(unique + [of_points(c) for c in letters])
    return Blocks(
        sets=blocks,
        of_class={c: tuple(members[i]) for i, c in enumerate(unique)},
        of_char={c: members[len(unique) + i][0] for i, c in enumerate(letters)},
    )


def antlr_grammar(ast: IrAst, name: str, marks: Marks = NO_MARKS) -> str:
    """``ast`` as an ANTLR 4 grammar named ``name``.

    ANTLR splits a grammar into two TIERS and the lexer runs FIRST, with no view
    of what the parser wants. A character class is legal only in a lexer rule, so
    every class must become a token — and the moment two classes overlap, one
    token owns that character everywhere and the other class can never match
    again. GBNF has `cmchar = [^\\n]` and `namehead = [A-Za-z_]`; minting a token
    each leaves one of them dead, which is exactly how ANTLR came to be recorded
    as unable to express grammars it handles perfectly well.

    So the code-point space is PARTITIONED first (:mod:`tools.benchmark.charsets`)
    into blocks no class splits, one token per block, and a class becomes the
    alternation of its blocks. Literals go the same way, spelled as the sequence
    of blocks holding their characters, because an implicit literal token
    outranks every lexer rule on a length tie — that is what stopped the word
    `true` from appearing inside a json string. Every character then has exactly
    one token type, the lexer is deterministic, and the parser decides
    everything a parser should.

    Where lexic's derived run terminals survive that test (:func:`_safe_runs`)
    they are kept and declared first, so ANTLR gets the same lexical layer lexic
    gave itself rather than one token per character.

    ANTLR is also the one competitor that does not take a grammar at runtime —
    the Java tool runs over this text before anything parses, outside the timed
    region, as `Lark(...)` construction is.
    """
    ast = inlined_marks(ast, marks)
    candidates = lexical_layer(ast)
    runs = safe_runs(_live(ast, candidates)[0], candidates)
    rules, start = _live(ast, runs)
    names = {n: _antlr_safe(v) for n, v in _names(rules).items()}
    lex = Lex(runs, {})
    partitioned = partition_blocks(rules, runs)
    bodies = [
        (names[n], _antlr(body, names, lex, partitioned)) for n, body in rules.items()
    ]
    lines = [f"grammar {name};"]
    lines += [f"{rule} : {body} ;" for rule, body in bodies]
    lines.append(f"entry_ : {names[start]} EOF ;")
    lines += [f"{term} : {body} ;" for body, term in lex.terms.items()]
    lines += [
        f"B{i} : [{_ranges(s, _antlr_escaped, _ANTLR_SPECIALS)}] ;"
        for i, s in enumerate(partitioned.sets)
    ]
    return "\n".join(lines) + "\n"


def _named(indices: tuple[int, ...]) -> str:
    """One block, or a parenthesised alternation of several."""
    if len(indices) == 1:
        return f"B{indices[0]}"
    return "(" + " | ".join(f"B{i}" for i in indices) + ")"


def _antlr_alternation(node, names, lex, blocks):
    return " | ".join(_antlr(arm, names, lex, blocks) for arm in node)


def _antlr_sequence(node, names, lex, blocks):
    """Juxtaposition; an EMPTY arm emits nothing, which is ANTLR's empty alt."""
    return " ".join(_antlr(item, names, lex, blocks) for item in node)


def _antlr_counted(atom: str, lo: int, hi: int) -> str:
    """A repeat count ANTLR has no syntax for, spelled out.

    ANTLR has no `{n,m}`: the mandatory copies are written in full, then the
    optional tail — a `*` when unbounded, one `?` per allowed extra otherwise.
    """
    fixed = " ".join([atom] * lo)
    tail = f"{atom}*" if hi < 0 else " ".join([f"{atom}?"] * (hi - lo))
    return f"{fixed} {tail}".strip()


def _antlr_item(node, names, lex, blocks):
    run = lex.runs.get(node)
    if run is not None:
        body = f"[{_ranges(run.chars, _antlr_escaped, _ANTLR_SPECIALS)}]+"
        term = _term_for(body, lex, "RUN")
        return f"{term}?" if run.optional else term
    atom = _antlr(node.atom, names, lex, blocks)
    if isinstance(node.atom, (IrAlternation, IrSequence)):
        atom = f"({atom})"
    return _quantified(atom, node.quantifier, _antlr_counted)


def _antlr_literal(node, _names, _lex, blocks):
    """A literal as the SEQUENCE of blocks holding its characters.

    Never ANTLR's own `'true'`: an implicit literal token outranks every lexer
    rule on a length tie, so the word `true` could not appear inside a json
    string. Spelling it in blocks keeps one token type per character and leaves
    the decision where it belongs.
    """
    parts = [f"B{blocks.of_char[c]}" for c in str(node)]
    return parts[0] if len(parts) == 1 else "(" + " ".join(parts) + ")"


def _antlr_charclass(node, _names, _lex, blocks):
    """The blocks this class is the union of."""
    return _named(blocks.of_class[charset_of(node)])


def _antlr_ruleref(node, names, _lex, _blocks):
    return _known_ref(node, names)


def _antlr_not(node, _names, _lex, blocks):
    inner = _negated_class(node, "ANTLR")
    return _named(blocks.of_class[complement(charset_of(inner))])


_ANTLR: dict[type, Callable[..., str]] = {
    IrAlternation: _antlr_alternation,
    IrSequence: _antlr_sequence,
    IrItem: _antlr_item,
    IrLiteral: _antlr_literal,
    IrChr: _antlr_literal,
    IrCharClass: _antlr_charclass,
    IrRuleRef: _antlr_ruleref,
    IrNot: _antlr_not,
}
"""Node type → its ANTLR spelling."""


def _antlr(node: IrSelf, names: dict[str, str], lex: Lex, blocks: Blocks) -> str:
    emit = _ANTLR.get(type(node))
    if emit is None:
        raise UnsupportedConstructError(
            f"benchmark: no ANTLR spelling for {type(node).__name__}"
        )
    return emit(node, names, lex, blocks)
