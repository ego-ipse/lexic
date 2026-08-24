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
from importlib import import_module
from typing import TYPE_CHECKING, NamedTuple


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
    inline_refs,
)
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.lexruns import run_candidates
from lexic.parsing.earley.normalize import normalize
from tools.benchmark.emitters.charsets import (
    CharSet,
    normalized,
    of_points,
)
from tools.benchmark.emitters.directives import NO_MARKS, Marks, inlined_marks

if TYPE_CHECKING:
    from tools.benchmark.emitters.structured import Blocks

_UNIT = IrQuantifier(1, 1)
_STAR = IrQuantifier(0, IrNone)
_PLUS = IrQuantifier(1, IrNone)


def _bounds(quant: IrQuantifier) -> tuple[int, int]:
    """``(lo, hi)`` with ``-1`` for unbounded — absence is ``IrNone``, not None."""
    return int(quant.lo), int(quant.hi) if isinstance(quant.hi, int) else -1


def _quantified(
    atom: str, quantifier: IrQuantifier, counted: Callable[[str, int, int], str]
) -> str:
    """Apply shared optional/star/plus syntax or delegate a counted repeat."""
    lo, hi = _bounds(quantifier)
    if quantifier == _UNIT:
        return atom
    if (lo, hi) == (0, 1):
        return f"{atom}?"
    if (lo, hi) == (0, -1):
        return f"{atom}*"
    if (lo, hi) == (1, -1):
        return f"{atom}+"
    return counted(atom, lo, hi)


def _known_ref(node: IrRuleRef, names: dict[str, str]) -> str:
    """Resolve a rule reference or reject a dangling emitted grammar."""
    key = str(node)
    if key not in names:
        raise UnsupportedConstructError(f"benchmark: reference to unknown {key!r}")
    return names[key]


def _negated_class(node: IrNot, engine: str) -> IrCharClass:
    """Return the class under a supported character-class negation."""
    inner = node[0]
    if not isinstance(inner, IrCharClass):
        raise UnsupportedConstructError(
            f"benchmark: {engine} cannot express IrNot over {type(inner).__name__}"
        )
    return inner


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


def _folded(
    names: dict[str, str],
    marks: Marks,
    rules: dict[str, IrSelf],
    start: str,
) -> dict[str, str]:
    """The emitted names ``marks`` changes, as Lark spells the two directives.

    A directive lexic honours for ITSELF and the translation withholds is not a
    grammar difference, it is a handicap, and it is the whole gap on `json`.
    Both have an exact Lark spelling, so both are spelled:

    ``@lexical`` — lexic inlines the rule's refs until its body is ref-free and
    keeps the matched TEXT instead of a subtree of interior models. Lark's
    equivalent is a TERMINAL: same body, moved from the parser to the lexer,
    which is where a person writing this grammar puts a string or a number.

    ``@non-semantic`` — lexic drops structural rules from the model. Lark's
    ``_``-prefixed rule is filtered out of the tree, which drops the same nodes
    and, unlike ``%ignore``, does NOT let the noise appear where the grammar
    forbids it. The language is untouched; only the tree the row is timed
    building gets smaller, exactly as the model does.
    """
    lexical, noise = marks
    out = {
        name: f"{names[name].upper()}_"
        for name in lexical
        if name in rules and name != start
    }
    out.update(
        {
            name: f"_{names[name]}"
            for name in noise
            if name in rules and name not in out and name != start
        }
    )
    return out


def lark_grammar(ast: IrAst, refine: bool = False, marks: Marks = NO_MARKS) -> str:
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
    :param marks: The ``(lexical, non_semantic)`` directive sets to translate,
        as :func:`_folded` spells them. Default is neither, which is the
        grammar exactly as authored.
    """
    if marks[0]:
        ast = inline_refs(ast, marks[0])
    runs = lexical_layer(ast)
    blocks = None
    if refine:
        structured = import_module("tools.benchmark.emitters.structured")
        runs = structured.safe_runs(_live(ast, runs)[0], runs)
        blocks = structured.partition_blocks(_live(ast, runs)[0], runs)
    rules, start = _live(ast, runs)
    lex = Lex(runs, {}, blocks)
    names = _names(rules)
    names.update(_folded(names, marks, rules, start))
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
    return _quantified(atom, node.quantifier, _lark_counted)


def _lark_counted(atom: str, lo: int, hi: int) -> str:
    """Lark's bounded and lower-bounded repetition syntax."""
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
    indices = lex.blocks.of_class[charset_of(node)]
    if len(indices) == 1:
        return f"B{indices[0]}"
    return "(" + " | ".join(f"B{i}" for i in indices) + ")"


def _lark_ruleref(node: IrRuleRef, names: dict[str, str], _lex: Lex) -> str:
    return _known_ref(node, names)


def _lark_not(node: IrNot, _names: dict[str, str], _lex: Lex) -> str:
    inner = _negated_class(node, "Lark")
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


# ── ordered choice (PEG / MatchFirst) — the arm order an author would use ──


def _choice_arms(node: IrAlternation) -> list[IrSequence]:
    """``node``'s arms in the order an ordered-choice author would write them.

    A context-free ``|`` is unordered; PEG's ``/`` (and pyparsing's
    ``MatchFirst``) commits to the first arm that matches. An EMPTY arm first
    makes every later arm dead code — ``x-tail = "" / x-range / x-seq`` can
    never match a range, and the row then reports the tool refusing a grammar
    when it was only handed a losing order no PEG author would write. Empty
    arms go last; everything else stays as authored, and the faithfulness
    differential still judges the result per grammar.
    """
    arms = list(node)
    return [arm for arm in arms if arm] + [arm for arm in arms if not arm]


# ── parsimonious (PEG) ─────────────────────────────────────────────────────


def peg_grammar(ast: IrAst, marks: Marks = NO_MARKS) -> str:
    """``ast`` as a parsimonious PEG, start rule first.

    PEG's choice is ORDERED and its repetition POSSESSIVE, so this is faithful
    only for a grammar that never needs to back out of a committed arm. The
    differential proves that per grammar rather than per assumption.
    Scannerless, so there is no lexical layer to hand it. Directive-matched
    rows inline refs to lexical and non-semantic rules, the available spelling
    that avoids building their otherwise-mandatory ``Node`` wrappers.
    """
    ast = inlined_marks(ast, marks)
    rules, start = _rule_map(ast)
    names = _names(rules)
    ordered = [(start, rules[start])] + [(n, b) for n, b in rules.items() if n != start]
    return "\n".join(f"{names[n]} = {_peg(b, names)}" for n, b in ordered) + "\n"


def _peg_alternation(node: IrAlternation, names: dict[str, str]) -> str:
    return " / ".join(_peg(arm, names) for arm in _choice_arms(node))


def _peg_sequence(node: IrSequence, names: dict[str, str]) -> str:
    parts = [_peg(item, names) for item in node]
    return " ".join(parts) if parts else '""'


def _peg_item(node: IrItem, names: dict[str, str]) -> str:
    atom = _peg(node.atom, names)
    if isinstance(node.atom, (IrAlternation, IrSequence)):
        atom = f"({atom})"
    return _quantified(atom, node.quantifier, _peg_counted)


def _peg_counted(atom: str, lo: int, hi: int) -> str:
    """PEG bounded and lower-bounded repetition syntax."""
    return f"{atom}{{{lo},{hi}}}" if hi >= 0 else f"{atom}{{{lo},}}"


def _peg_literal(node: IrLiteral | IrChr, _names: dict[str, str]) -> str:
    return _text_literal(str(node))


def _peg_charclass(node: IrCharClass, _names: dict[str, str]) -> str:
    """The class inside parsimonious's ``~r"[...]"`` — so ``"`` must be escaped.

    A class holding the double-quote (vyx's ``!-"`` range) would otherwise
    terminate the regex literal mid-class, and parsimonious's own grammar
    reader refuses the file — read as "PEG cannot express this grammar" when
    the only problem was the quoting. ``\\"`` inside a Python regex is ``"``.
    """
    return f'~r"[{_members(node, extra=chr(34))}]"'


def _peg_ruleref(node: IrRuleRef, names: dict[str, str]) -> str:
    return _known_ref(node, names)


def _peg_not(node: IrNot, _names: dict[str, str]) -> str:
    inner = _negated_class(node, "PEG")
    return f'~r"[^{_members(inner, extra=chr(34))}]"'


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
