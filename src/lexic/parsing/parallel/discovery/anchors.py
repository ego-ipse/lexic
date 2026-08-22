"""Anchor analysis — the characters no opaque interior can emit.

Every occurrence of such a character in valid input is structural — an
emission of an enumerable, discrete grammar site — so a local scan over a
window of text cannot be fooled by string or comment interiors. That is
the property a parallel splitter needs to cut input without left context.
Which SITE an occurrence belongs to may still be ambiguous; the site map
is the hypothesis set the orchestrator disambiguates over.

Site membership is counted over polarity-aware
:class:`~lexic.parsing.pda.core.charsets.CharSet` values, so a co-finite
class (an ``IrNot`` loop) de-certifies exactly the characters it covers
instead of being approximated away. Characters inside a derived
maximal-munch run charset
(:func:`~lexic.parsing.earley.lexruns.run_candidates`) are excluded too: a
boundary mid-run lands inside a terminal whose extent depends on text not
yet seen, which the resumable recognizer refuses.
"""

from __future__ import annotations

from lexic.ir import (
    IrAction,
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLambda,
    IrLeaf,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSelf,
    IrTypeMap,
)
from lexic.parsing.caches import adopt, memo
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.lexruns import run_candidates
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.pda.core.charsets import CharSet


class _Sites(IrLeaf[IrSelf, IrSelf]):
    """The collector one grammar's site walk fills — ``(rule, CharSet)`` rows.

    :ivar rule: The defining rule the walk currently stands in.
    :ivar sites: One row per emitting atom occurrence.
    """

    __slots__ = ("rule", "sites")

    rule: str
    sites: list[tuple[str, CharSet]]

    def __init__(self) -> None:
        self.rule = ""
        self.sites = []


def _site_literal(d: _Sites, n: IrSelf, _nc: object) -> None:
    """A literal occurrence emits exactly its own characters."""
    text = str(n)
    if text:
        d.sites.append((d.rule, CharSet.from_chars(*text)))


def _site_charclass(d: _Sites, n: IrSelf, _nc: object) -> None:
    """A char class emits its member set — exact even when co-finite."""
    assert isinstance(n, IrCharClass)
    d.sites.append((d.rule, CharSet.from_charclass(n)))


def _site_not(d: _Sites, n: IrSelf, _nc: object) -> None:
    """A negated class emits its complement (non-class inner: conservatively ANY)."""
    assert isinstance(n, IrNot)
    inner = n[0]
    emits = CharSet.from_not(inner) if isinstance(inner, IrCharClass) else CharSet.ANY
    d.sites.append((d.rule, emits))


def _site_alphabet(d: _Sites, _n: IrSelf, _nc: object) -> None:
    """A token terminal matches ids, not chars — ANY kills char anchors soundly."""
    d.sites.append((d.rule, CharSet.ANY))


def _site_ruleref(_d: _Sites, _n: IrSelf, _nc: object) -> None:
    """A rule reference emits no characters at its own site."""


def _site_alternation(d: _Sites, n: IrSelf, _nc: object) -> None:
    """A group contributes every atom site under every arm."""
    assert isinstance(n, IrAlternation)
    for arm in n:
        for item in arm:
            assert isinstance(item, IrItem)
            atom = item.atom
            SITE_EMITS.resolve(atom).eval(d, atom, ())


SITE_EMITS: IrTypeMap = IrTypeMap(
    IrAction(IrLiteral, IrLambda(_site_literal)),
    IrAction(IrCharClass, IrLambda(_site_charclass)),
    IrAction(IrNot, IrLambda(_site_not)),
    IrAction(IrAlphabet, IrLambda(_site_alphabet)),
    IrAction(IrRuleRef, IrLambda(_site_ruleref)),
    IrAction(IrAlternation, IrLambda(_site_alternation)),
)
"""What one atom occurrence can emit — a new atom type joins by adding a row."""


def _site_rows(grammar: IrAst) -> list[tuple[str, CharSet]]:
    """Every emitting site as a ``(defining rule, CharSet)`` row, in walk order."""
    d = _Sites()
    for rule in grammar.rules:
        d.rule = str(rule.name)
        body = rule.body
        SITE_EMITS.resolve(body).eval(d, body, ())
    return d.sites


def _sites_by_char(rows: list[tuple[str, CharSet]]) -> dict[str, tuple[str, ...]]:
    """Certified char → defining rules of its finite sites, definition order.

    A character qualifies iff NO co-finite (negated / ANY) site can emit it:
    such a site is an opaque interior — a string body, a comment, a token
    terminal — and an occurrence inside one is not structural. Candidates are
    enumerable only from the finite positive sets, which is not a loss: a
    character emitted solely by co-finite sites is disqualified by definition.
    """
    candidates: set[str] = set()
    for _rule, emits in rows:
        if not emits.negated:
            candidates |= emits.chars
    opaque = [emits for _rule, emits in rows if emits.negated]
    out: dict[str, tuple[str, ...]] = {}
    for ch in sorted(candidates):
        if any(emits.has(ch) for emits in opaque):
            continue
        rules = [rule for rule, emits in rows if emits.has(ch)]
        out[ch] = tuple(dict.fromkeys(rules))
    return out


def _run_chars(grammar: IrAst) -> set[str]:
    """The union of the grammar's derived maximal-munch run charsets."""
    normalized = normalize(grammar)
    adopt(id(grammar), normalized)  # transient shape, but the table memo keys on it
    tables = compile_tables(normalized)
    out: set[str] = set()
    for charset, _has_empty, _unit_rid in run_candidates(tables).values():
        out |= charset
    return out


_Entry = tuple[IrAst, frozenset[str], dict[str, tuple[str, ...]]]
_ANCHORS: dict[int, _Entry] = memo({})
"""Analysis memo — id(grammar) → (grammar, anchors, site map). The strong
reference pins the id, so a recycled id can never alias a live entry."""


def _analysis(grammar: IrAst) -> _Entry:
    """The memoised analysis entry for ``grammar``."""
    entry = _ANCHORS.get(id(grammar))
    if entry is None:
        by_char = _sites_by_char(_site_rows(grammar))
        if by_char:
            for ch in _run_chars(grammar):
                by_char.pop(ch, None)
        entry = (grammar, frozenset(by_char), by_char)
        _ANCHORS[id(grammar)] = entry
    return entry


def anchors(grammar: IrAst) -> frozenset[str]:
    """The grammar's structural anchor characters, memoised per grammar identity.

    A character is an anchor iff at least one site emits it, no co-finite
    site can, and no derived run charset contains it. Multi-site anchors are
    legitimate — the site set is the orchestrator's hypothesis set; a char
    that also PINS a single site is ``len(anchor_sites(g)[ch]) == 1``. An
    anchorless grammar returns the empty set — an answer (sequential
    processing), not a failure.

    :param grammar: The grammar to analyse — for a compiled artefact, the
        codegen grammar, the form the engine actually parses.
    :returns: The anchor characters.
    """
    return _analysis(grammar)[1]


def anchor_sites(grammar: IrAst) -> dict[str, tuple[str, ...]]:
    """Each anchor character's emitting sites, as defining-rule names.

    Definition order, deduplicated. This is the hypothesis set the
    orchestrator's local disambiguation chooses among when an anchor is
    emitted at more than one site.

    :param grammar: The grammar to analyse (same memo as :func:`anchors`).
    :returns: anchor char → the defining rules of its sites.
    """
    return _analysis(grammar)[2]
