"""One canonical ``IrAst`` → each competitor's own notation.

The benchmark's claim is that every engine is asked the same question, and that
only holds if nobody hand-writes a second copy of the grammar. So each
competitor's input is DERIVED from the grammar lexic itself compiles — the same
relationship ``to_grammar(flavour)`` already has with GBNF and ABNF.

Two things beyond a literal transcription have to be right, and getting either
wrong reads as a competitor failing when it is our translation that failed:

1. **The lexical layer.** lexic derives run terminals and collapses character
   repetitions into them — see :func:`lexical_layer`. Dissolving that layer
   hands a lexer-based competitor one token per character.
2. **A token set the tool can use.** ANTLR's lexer runs before its parser and
   cannot see context, so overlapping character classes must be refined into
   disjoint blocks first — see :func:`antlr_grammar`.

Dispatch is a table keyed by node type with a raising default, never an
isinstance ladder — a node nobody taught an emitter must fail loudly and by
name, because the alternative is a row measuring a grammar we mistranslated.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from functools import cache
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
    IrNone,
    IrNot,
    IrQuantifier,
    IrRange,
    IrRuleRef,
    IrSelf,
    IrSequence,
)
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.lexruns import run_candidates
from lexic.parsing.earley.normalize import normalize
from tools.benchmark.charsets import (
    CharSet,
    complement,
    normalized,
    of_points,
    overlap,
    partition,
)

_UNIT = IrQuantifier(1, 1)
_STAR = IrQuantifier(0, IrNone)
_PLUS = IrQuantifier(1, IrNone)


def _bounds(quant: IrQuantifier) -> tuple[int, int]:
    """``(lo, hi)`` with ``-1`` for unbounded — absence is ``IrNone``, not None."""
    return int(quant.lo), int(quant.hi) if isinstance(quant.hi, int) else -1


def _rule_map(ast: IrAst) -> tuple[dict[str, IrSelf], str]:
    """``{name: body}`` and the start name, refusing a start that is not defined."""
    rules = {str(rule.name): rule.body for rule in ast.rules}
    start = str(ast.start)
    if start not in rules:
        raise UnsupportedConstructError(f"benchmark: no rule named {start!r}")
    return rules, start


def _slug(name: str) -> str:
    """A lowercase identifier, keeping distinct names distinct.

    `a-b` and `a_b` both slug to `a_b`, so a bare replacement would silently
    merge two rules into one — a mistranslation no test of ONE input would
    catch. Collisions get a numeric suffix instead. A leading underscore goes:
    Lark reads `_rule` as "inline this into the parent" and ANTLR refuses it as
    a rule name outright.
    """
    base = "".join(c if c.isalnum() else "_" for c in name).lower().lstrip("_")
    return f"r_{base}" if not base or base[0].isdigit() else base


def _names(rules: dict[str, IrSelf]) -> dict[str, str]:
    """Grammar name → emitted name, with collisions broken deterministically."""
    out: dict[str, str] = {}
    taken: set[str] = set()
    for name in rules:
        slug = _slug(name)
        if slug in taken:
            n = 2
            while f"{slug}_{n}" in taken:
                n += 1
            slug = f"{slug}_{n}"
        taken.add(slug)
        out[name] = slug
    return out


def charset_of(node: IrCharClass) -> CharSet:
    """A char class as an interval set."""
    return normalized(
        (int(m.lo), int(m.hi)) if isinstance(m, IrRange) else (int(m), int(m))
        for m in node
    )


# ── the lexical layer lexic derives for itself ─────────────────────────────


class RunTerminal(NamedTuple):
    """One run terminal lexic derived, in the form an emitter can spell.

    :ivar chars: The exact code points the run accepts.
    :ivar optional: The run's rule is nullable (``*``, not ``+``). A lexer
        terminal may not match the empty string, so the repetition stays `+` and
        the emptiness moves to the REFERENCE, as `RUN?`.
    """

    chars: CharSet
    optional: bool


Runs = dict[IrItem, RunTerminal]
"""Authored item → the run terminal lexic collapses it to. The KEY is the item
as written (`digit+`), not the synthetic rule normalisation minted for it, so a
competitor keeps its own looping construct and gains only the lexical layer."""


def _unit_of(body: IrSelf) -> IrItem | None:
    """The repeated item of a normalised run rule's right-recursive body."""
    if not isinstance(body, IrAlternation):
        return None
    arms = sorted(body, key=len)
    return arms[1][0] if len(arms) == 2 and len(arms[1]) == 2 else None


@cache
def lexical_layer(ast: IrAst) -> Runs:
    """The run terminals lexic derives for ``ast``, keyed by authored item.

    lexic does not parse a grammar as written: it normalises it, then DERIVES a
    lexical layer over the result, collapsing proved-safe character repetitions
    into single maximal-munch run terminals. That is why it reads csv as ~1,400
    units. A translation that dissolves the layer hands every lexer-based
    competitor 12,539 single-character tokens, and the row then measures the
    missing lexer rather than the engines.

    The proof is lexic's own (:func:`~lexic.parsing.earley.lexruns.run_candidates`):
    fixed charset, unique derivation, and a FOLLOW set disjoint from the charset
    so maximal munch is COMPLETE. A run whose follow set overlaps is declined
    there and must be declined here — collapsing it anyway hands a competitor a
    munch lexic itself refused, which is a different language.

    Results map BACK onto the authored items. A run whose unit is not an authored
    atom (a hoisted group) is dropped: emitting lexic's normalised grammar
    instead would replace every `x*` with a right-recursive rule pair, which
    costs lark-earley 3.5x on `arithmetic` — our shape, not Lark's fault.
    """
    grammar = normalize(ast)
    bodies = {str(rule.name): rule.body for rule in grammar.rules}
    runs: Runs = {}
    for name, (chars, empty, _u) in run_candidates(compile_tables(grammar)).items():
        unit = _unit_of(bodies[name])
        if unit is not None:
            runs[IrItem(unit.atom, _STAR if empty else _PLUS)] = RunTerminal(
                of_points(chars), empty
            )
    return runs


def _refs(node: IrSelf, runs: Runs) -> Iterator[str]:
    """Every rule name ``node`` still references once ``runs`` are collapsed."""
    if isinstance(node, IrRuleRef):
        yield str(node)
    elif isinstance(node, tuple) and node not in runs:
        for child in node:
            yield from _refs(child, runs)


def _live(ast: IrAst, runs: Runs) -> tuple[dict[str, IrSelf], str]:
    """``ast``'s rules less every one only a collapsed run still reaches.

    A run's unit rule (`digit` under `digit+`) has no reference left once the run
    becomes one terminal, and emitting it anyway declares a second lexer rule
    over the same code points for the lexer to trip on.
    """
    rules, start = _rule_map(ast)
    seen = {start}
    stack = [start]
    while stack:
        for ref in _refs(rules[stack.pop()], runs):
            if ref not in seen:
                seen.add(ref)
                stack.append(ref)
    return {n: b for n, b in rules.items() if n in seen}, start


# ── character-class spelling, per notation ─────────────────────────────────


_CONTROL = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}
"""Characters no text notation may carry literally."""


def _escaped(char: str) -> str | None:
    """A code point's escape when it must not appear literally, else ``None``.

    A grammar over the whole Unicode range starts its classes at U+0000, and a
    raw NUL in an emitted regex is not a refusal by the tool — it is a broken
    string. Emitting it produced "Lark cannot express this grammar".
    """
    point = ord(char)
    if char in _CONTROL:
        return _CONTROL[char]
    if point < 0x20 or point == 0x7F:
        return f"\\x{point:02x}"
    if point > 0x7E:
        return f"\\u{point:04x}" if point <= 0xFFFF else f"\\U{point:08x}"
    return None


def _antlr_escaped(char: str) -> str | None:
    """ANTLR's own escapes — `\\uXXXX` only; it rejects `\\xNN` outright.

    Escaping has proved notation-specific three times over: Lark eats `/`, PEG
    breaks on a raw newline, ANTLR refuses the hex form the other two accept. A
    shared escaper is a bug waiting for the next notation.
    """
    point = ord(char)
    if char in _CONTROL:
        return _CONTROL[char]
    if point < 0x20 or point == 0x7F or point > 0x7E:
        return f"\\u{point:04X}" if point <= 0xFFFF else f"\\u{{{point:X}}}"
    return None


_LARK_SPECIALS = "\\][^-/"
"""What a Lark regex needs backslashed inside a class. `[` is in there because
an unescaped one makes Python's `re` warn about a possible nested set."""

_ANTLR_SPECIALS = "\\]-"
"""What ANTLR backslashes INSIDE brackets. `^` is not special there and it
rejects the file for a `\\^` the regex notations both accept."""


def _members(node: IrCharClass, extra: str = "") -> str:
    """A char class's body for a regex notation, ranges kept as ranges.

    ``extra`` is what the ENCLOSING syntax would otherwise eat: Lark writes its
    regex between slashes, so `/` must be escaped there and must NOT be in PEG,
    where the class sits inside `~r"..."`. Sharing one escape set across
    notations is what produced `/[*/]/` — a regex terminated by its own member.
    """

    def one(char: str) -> str:
        if char in "\\]^-" or char in extra:
            return "\\" + char
        return _escaped(char) or char

    out: list[str] = []
    for member in node:
        if isinstance(member, IrRange):
            out.append(f"{one(str(member.lo))}-{one(str(member.hi))}")
        else:
            out.extend(one(c) for c in str(member))
    return "".join(out)


def _ranges(charset: CharSet, escape, specials: str) -> str:
    """An interval set as a bracketed class body in one notation's spelling."""

    def one(point: int) -> str:
        char = chr(point)
        return "\\" + char if char in specials else escape(char) or char

    return "".join(
        one(lo) if lo == hi else f"{one(lo)}-{one(hi)}" for lo, hi in charset
    )


def _text_literal(value: str) -> str:
    """A literal for a notation that quotes with `"`, control chars escaped.

    A raw newline inside `"..."` ends the line, not the string — which is how
    `nl = "<newline>"` reached parsimonious as an unterminated literal.
    """
    body = value.replace("\\", "\\\\").replace('"', '\\"')
    for raw, esc in _CONTROL.items():
        body = body.replace(raw, esc)
    return f'"{body}"'


class Lex(NamedTuple):
    """One emission's lexical state: what to collapse, and what got minted.

    :ivar runs: The authored items that become run terminals.
    :ivar terms: Terminal BODY → its minted name, in mint order. Keying by body
        deduplicates: one character class must not become two tokens the lexer
        then has to choose between.
    """

    runs: Runs
    terms: dict[str, str]
    blocks: Blocks | None = None


def _term_for(body: str, lex: Lex, prefix: str) -> str:
    """The terminal name for ``body``, minting one on first sight."""
    if body not in lex.terms:
        lex.terms[body] = f"{prefix}{len(lex.terms)}_"
    return lex.terms[body]


# ── Lark ───────────────────────────────────────────────────────────────────


def lark_grammar(ast: IrAst, refine: bool = False) -> str:
    """``ast`` as Lark source, start rule first, over the derived lexical layer.

    Lark HAS a lexer, so it gets the run terminals lexic derived — the `+` goes
    inside the terminal, where a person writing this grammar would put it.
    Everything else stays as authored: Lark's own `*` builds a flat inlined
    repetition, and substituting the right-recursive rule pair lexic normalises
    to costs it 3.5x on `arithmetic`.

    :param refine: Refine the character classes into disjoint blocks first,
        as :func:`antlr_grammar` always does. Lark's Earley backend uses a
        `dynamic` lexer that offers every matching terminal to the parser, so it
        settles an overlap itself and is better off with the run terminals. Its
        LALR backend uses a `contextual` lexer, which narrows by parser state
        but still has to pick ONE terminal per position — and in a merged state
        that admits both `ws` and `chars`, a single space goes to whichever
        terminal wins, not to the slot the parse needs. That is a token-set
        problem, not an LALR one, and the partition is its fix.
    """
    runs = lexical_layer(ast)
    if refine:
        runs = _safe_runs(_live(ast, runs)[0], runs)
    rules, start = _live(ast, runs)
    lex = Lex(runs, {}, _blocks(rules, runs) if refine else None)
    names = _names(rules)
    bodies = [(names[n], _lark(b, names, lex)) for n, b in rules.items()]
    lines = [f"start: {names[start]}"]
    lines += [f"{rule}: {body}" for rule, body in bodies]
    lines += [f"{name}: {body}" for body, name in lex.terms.items()]
    if lex.blocks is not None:
        lines += [
            f"B{i}: /[{_ranges(s, _escaped, _LARK_SPECIALS)}]/"
            for i, s in enumerate(lex.blocks.sets)
        ]
    return "\n".join(lines) + "\n"


def _lark_alternation(node: IrAlternation, names: dict[str, str], lex: Lex) -> str:
    return " | ".join(_lark(arm, names, lex) for arm in node)


def _lark_sequence(node: IrSequence, names: dict[str, str], lex: Lex) -> str:
    """Juxtaposition. An EMPTY arm emits nothing, not `""`.

    Lark refuses an empty terminal, and `a: | b` is how it spells the empty
    alternative — so emitting `""` reported "Lark cannot express this grammar"
    for a grammar whose only sin was having a nullable arm.
    """
    return " ".join(_lark(item, names, lex) for item in node)


def _lark_item(node: IrItem, names: dict[str, str], lex: Lex) -> str:
    run = lex.runs.get(node)
    if run is not None:
        term = _term_for(f"/[{_ranges(run.chars, _escaped, '\\]^-/')}]+/", lex, "RUN")
        return f"{term}?" if run.optional else term
    atom = _lark(node.atom, names, lex)
    if not isinstance(node.atom, (IrLiteral, IrCharClass, IrRuleRef, IrChr)):
        atom = f"({atom})"
    lo, hi = _bounds(node.quantifier)
    if node.quantifier == _UNIT:
        return atom
    if (lo, hi) == (0, 1):
        return f"{atom}?"
    if (lo, hi) == (0, -1):
        return f"{atom}*"
    if (lo, hi) == (1, -1):
        return f"{atom}+"
    return f"{atom}~{lo}..{hi}" if hi >= 0 else f"({atom}~{lo}..) {atom}*"


def _lark_literal(node: IrLiteral | IrChr, _names: dict[str, str], lex: Lex) -> str:
    """A quoted string, or the SEQUENCE of blocks holding its characters.

    Under a partition the string form is wrong for the same reason it is wrong
    in ANTLR: Lark gives a string literal higher priority than a regex terminal
    of equal length, so `true` would be lexed as the keyword even where the
    grammar wanted three characters of `chars`.
    """
    if lex.blocks is None:
        return _text_literal(str(node))
    parts = [f"B{lex.blocks.of_char[c]}" for c in str(node)]
    return parts[0] if len(parts) == 1 else "(" + " ".join(parts) + ")"


def _lark_charclass(node: IrCharClass, _names: dict[str, str], lex: Lex) -> str:
    if lex.blocks is None:
        return f"/[{_members(node, extra='/')}]/"
    return _named(lex.blocks.of_class[charset_of(node)])


def _lark_ruleref(node: IrRuleRef, names: dict[str, str], _lex: Lex) -> str:
    key = str(node)
    if key not in names:
        raise UnsupportedConstructError(f"benchmark: reference to unknown {key!r}")
    return names[key]


def _lark_not(node: IrNot, _names: dict[str, str], _lex: Lex) -> str:
    inner = node[0]
    if not isinstance(inner, IrCharClass):
        raise UnsupportedConstructError(
            f"benchmark: Lark cannot express IrNot over {type(inner).__name__}"
        )
    return f"/[^{_members(inner, extra='/')}]/"


_LARK: dict[type, Callable[..., str]] = {
    IrAlternation: _lark_alternation,
    IrSequence: _lark_sequence,
    IrItem: _lark_item,
    IrLiteral: _lark_literal,
    IrChr: _lark_literal,
    IrCharClass: _lark_charclass,
    IrRuleRef: _lark_ruleref,
    IrNot: _lark_not,
}
"""Node type → its Lark spelling. A new atom adds a row, not a branch."""


def _lark(node: IrSelf, names: dict[str, str], lex: Lex) -> str:
    emit = _LARK.get(type(node))
    if emit is None:
        raise UnsupportedConstructError(
            f"benchmark: no Lark spelling for {type(node).__name__}"
        )
    return emit(node, names, lex)


# ── parsimonious (PEG) ─────────────────────────────────────────────────────


def peg_grammar(ast: IrAst) -> str:
    """``ast`` as a parsimonious PEG, start rule first.

    PEG's choice is ORDERED and its repetition POSSESSIVE, so this is faithful
    only for a grammar that never needs to back out of a committed arm. The
    differential proves that per grammar rather than per assumption.
    Scannerless, so there is no lexical layer to hand it.
    """
    rules, start = _rule_map(ast)
    names = _names(rules)
    ordered = [(start, rules[start])] + [(n, b) for n, b in rules.items() if n != start]
    return "\n".join(f"{names[n]} = {_peg(b, names)}" for n, b in ordered) + "\n"


def _peg_alternation(node: IrAlternation, names: dict[str, str]) -> str:
    return " / ".join(_peg(arm, names) for arm in node)


def _peg_sequence(node: IrSequence, names: dict[str, str]) -> str:
    parts = [_peg(item, names) for item in node]
    return " ".join(parts) if parts else '""'


def _peg_item(node: IrItem, names: dict[str, str]) -> str:
    atom = _peg(node.atom, names)
    if isinstance(node.atom, (IrAlternation, IrSequence)):
        atom = f"({atom})"
    lo, hi = _bounds(node.quantifier)
    if node.quantifier == _UNIT:
        return atom
    if (lo, hi) == (0, 1):
        return f"{atom}?"
    if (lo, hi) == (0, -1):
        return f"{atom}*"
    if (lo, hi) == (1, -1):
        return f"{atom}+"
    return f"{atom}{{{lo},{hi}}}" if hi >= 0 else f"{atom}{{{lo},}}"


def _peg_literal(node: IrLiteral | IrChr, _names: dict[str, str]) -> str:
    return _text_literal(str(node))


def _peg_charclass(node: IrCharClass, _names: dict[str, str]) -> str:
    return f'~r"[{_members(node)}]"'


def _peg_ruleref(node: IrRuleRef, names: dict[str, str]) -> str:
    key = str(node)
    if key not in names:
        raise UnsupportedConstructError(f"benchmark: reference to unknown {key!r}")
    return names[key]


def _peg_not(node: IrNot, _names: dict[str, str]) -> str:
    inner = node[0]
    if not isinstance(inner, IrCharClass):
        raise UnsupportedConstructError(
            f"benchmark: PEG cannot express IrNot over {type(inner).__name__}"
        )
    return f'~r"[^{_members(inner)}]"'


_PEG: dict[type, Callable[..., str]] = {
    IrAlternation: _peg_alternation,
    IrSequence: _peg_sequence,
    IrItem: _peg_item,
    IrLiteral: _peg_literal,
    IrChr: _peg_literal,
    IrCharClass: _peg_charclass,
    IrRuleRef: _peg_ruleref,
    IrNot: _peg_not,
}
"""Node type → its PEG spelling."""


def _peg(node: IrSelf, names: dict[str, str]) -> str:
    emit = _PEG.get(type(node))
    if emit is None:
        raise UnsupportedConstructError(
            f"benchmark: no PEG spelling for {type(node).__name__}"
        )
    return emit(node, names)


# ── pyparsing (combinators, not text) ──────────────────────────────────────


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
    """Whichever alternation `pyparsing_parser` was asked for — see it for why."""
    return choice([_pp(arm, fwd, choice) for arm in node])


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


def _safe_runs(rules: dict[str, IrSelf], runs: Runs) -> Runs:
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


def _blocks(rules: dict[str, IrSelf], runs: Runs) -> Blocks:
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


def antlr_grammar(ast: IrAst, name: str) -> str:
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
    candidates = lexical_layer(ast)
    runs = _safe_runs(_live(ast, candidates)[0], candidates)
    rules, start = _live(ast, runs)
    names = {n: _antlr_safe(v) for n, v in _names(rules).items()}
    lex = Lex(runs, {})
    blocks = _blocks(rules, runs)
    bodies = [(names[n], _antlr(b, names, lex, blocks)) for n, b in rules.items()]
    lines = [f"grammar {name};"]
    lines += [f"{rule} : {body} ;" for rule, body in bodies]
    lines.append(f"entry_ : {names[start]} EOF ;")
    lines += [f"{term} : {body} ;" for body, term in lex.terms.items()]
    lines += [
        f"B{i} : [{_ranges(s, _antlr_escaped, _ANTLR_SPECIALS)}] ;"
        for i, s in enumerate(blocks.sets)
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
    lo, hi = _bounds(node.quantifier)
    if node.quantifier == _UNIT:
        return atom
    if (lo, hi) == (0, 1):
        return f"{atom}?"
    if (lo, hi) == (0, -1):
        return f"{atom}*"
    if (lo, hi) == (1, -1):
        return f"{atom}+"
    return _antlr_counted(atom, lo, hi)


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
    key = str(node)
    if key not in names:
        raise UnsupportedConstructError(f"benchmark: reference to unknown {key!r}")
    return names[key]


def _antlr_not(node, _names, _lex, blocks):
    inner = node[0]
    if not isinstance(inner, IrCharClass):
        raise UnsupportedConstructError(
            f"benchmark: ANTLR cannot express IrNot over {type(inner).__name__}"
        )
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
