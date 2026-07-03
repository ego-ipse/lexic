"""Run-terminal detection — where a grammar's lexical layer is *derived*.

Lark closes its step-count gap with a hand-declared token layer matched by C
regexes. This module derives the same layer from the IR instead: a synthetic
star/plus rule (minted by :mod:`~lexic.parsing.normalize`) collapses into a
single maximal-munch :class:`~lexic.parsing.tables.RunTerm` when three
facts are **proved** about it, so the collapse is exact — never Lark's
silent maximal-munch approximation:

1. **Fixed charset.** The repetition unit resolves to a set of single chars:
   a single-char terminal, or a rule whose every arm is one such atom (or a
   ref to another charset rule), transitively.
2. **Derivation uniqueness.** Iterating single-char units splits a run one
   way only, and the charset-rule alternatives are pairwise disjoint — so
   the collapse cannot hide ambiguity from the SPPF.
3. **Follow disjointness.** ``FOLLOW(rule) ∩ charset = ∅`` (classic
   FIRST/FOLLOW over the compiled tables), so a shorter-than-maximal match
   can never be required by any continuation — maximal munch is *complete*.

A char class too large to expand poisons every set it touches
(conservative: the affected rules simply stay per-char). The reducer-side
half of the decision — whether the collapsed run's per-char contributions
can be reconstructed — lives in :mod:`~lexic.parsing.reduce`, fed by
:func:`unit_leaves`.
"""

from __future__ import annotations

from lexic.ir.base import IrLeaf, IrSelf
from lexic.ir.nodes import IrAst, IrLiteral
from lexic.parsing.normalize import SYNTHETIC_PREFIX
from lexic.parsing.tables import (
    RUN_DROP,
    Charset,
    ParserTables,
    RunTerm,
    _expand_atom,
    build_tables,
    compile_tables,
)

RunShape = tuple[frozenset[str], bool, int]
"""One detected run rule: ``(charset, has_empty_arm, unit_rid)`` —
``unit_rid`` is ``-1`` when the unit is a bare terminal atom."""


class _Analysis(IrLeaf[IrSelf, IrSelf]):
    """One grammar's run analysis — arm symbols, FIRST/FOLLOW, shapes.

    :ivar tables: The compiled grammar under analysis.
    :ivar arm_syms: rule_id → its arms as symbol lists (``next_sym`` values).
    :ivar nullable: rule_id → derives the empty string.
    :ivar first: rule_id → FIRST char set (``None`` = poisoned).
    :ivar follow: rule_id → FOLLOW char set (``None`` = poisoned).
    """

    __slots__ = ("tables", "arm_syms", "nullable", "first", "follow")

    tables: ParserTables
    arm_syms: list[list[list[int]]]
    nullable: list[bool]
    first: list[set[str] | None]
    follow: list[set[str] | None]

    def __init__(self, tables: ParserTables) -> None:
        """Run the full analysis over ``tables``."""
        self.tables = tables
        codes = tables.codes
        dot0 = codes.rule_dot0  # derived property — bind the rebuild once
        self.arm_syms = [[self._syms_from(base) for base in bases] for bases in dot0]
        self.nullable = [bool(n) for n in codes.nullable_completes]
        self.first = self._first_sets()
        self.follow = self._follow_sets()

    def _syms_from(self, base: int) -> list[int]:
        """The symbol run of the arm starting at code ``base``."""
        nxt = self.tables.codes.next_sym
        syms: list[int] = []
        code = base
        while nxt[code] != 0:
            syms.append(nxt[code])
            code += 1
        return syms

    def _term_first(self, sym: int) -> Charset:
        """Begin-chars of terminal symbol ``sym`` (< 0), or poisoned."""
        atom = self.tables.terms.atoms[-sym - 1]
        if isinstance(atom, IrLiteral):
            return frozenset(atom[0]) if atom else frozenset()
        return _expand_atom(atom)

    def _first_sets(self) -> list[set[str] | None]:
        """Per-rule FIRST char sets by least fixpoint (poison propagates)."""
        first: list[set[str] | None] = [set() for _ in self.arm_syms]
        changed = True
        while changed:
            changed = False
            for rid, arms in enumerate(self.arm_syms):
                if first[rid] is None:
                    continue
                grown = self._first_of_rule(rid, arms, first)
                if grown:
                    changed = True
        return first

    def _first_of_rule(
        self, rid: int, arms: list[list[int]], first: list[set[str] | None]
    ) -> bool:
        """Grow ``first[rid]`` from its arms; ``True`` when it changed."""
        mine = first[rid]
        assert mine is not None
        before = len(mine)
        for syms in arms:
            for sym in syms:
                if sym < 0:
                    add = self._term_first(sym)
                    if add is None:
                        first[rid] = None
                        return True
                    mine |= add
                    break
                target = first[sym - 1]
                if target is None:
                    first[rid] = None
                    return True
                mine |= target
                if not self.nullable[sym - 1]:
                    break
        return len(mine) != before

    def _follow_sets(self) -> list[set[str] | None]:
        """Per-rule FOLLOW char sets: direct tail-FIRST + owner-edge fixpoint."""
        self.follow = [set() for _ in self.arm_syms]
        edges: set[tuple[int, int]] = set()  # (owner, target): follow ⊇ follow
        for rid, arms in enumerate(self.arm_syms):
            for syms in arms:
                for k, sym in enumerate(syms):
                    if sym > 0:
                        self._follow_direct(rid, syms, k, edges)
        follow = self.follow
        changed = True
        while changed:
            changed = False
            for owner, target in edges:
                target_set = follow[target]
                if target_set is None:
                    continue
                owner_set = follow[owner]
                if owner_set is None:
                    follow[target] = None
                    changed = True
                    continue
                before = len(target_set)
                target_set |= owner_set
                if len(target_set) != before:
                    changed = True
        return follow

    def _follow_direct(
        self, owner: int, syms: list[int], k: int, edges: set[tuple[int, int]]
    ) -> None:
        """Add the tail-FIRST after position ``k`` to the target's FOLLOW.

        The target is the rule ``syms[k]`` references. When the whole tail
        is nullable, the target also inherits ``FOLLOW(owner)`` (recorded as
        an edge for the fixpoint).
        """
        follow = self.follow
        target = syms[k] - 1
        for sym in syms[k + 1 :]:
            add = self._term_first(sym) if sym < 0 else self.first[sym - 1]
            if add is None:
                follow[target] = None
                return
            target_set = follow[target]
            if target_set is not None:
                target_set |= add
            if sym < 0 or not self.nullable[sym - 1]:
                return
        edges.add((owner, target))

    def _rule_charset(self, rid: int, visiting: frozenset[int]) -> Charset:
        """The exact char set rule ``rid`` matches as a single-char unit.

        Requires every arm to be one single-char atom (or a ref to another
        charset rule) with **pairwise-disjoint** alternatives — the
        derivation-uniqueness half of the collapse proof. ``None`` otherwise.
        """
        if rid in visiting:
            return None
        arms = self.arm_syms[rid]
        if not arms:
            return None
        union: set[str] = set()
        for syms in arms:
            if len(syms) != 1:
                return None
            sym = syms[0]
            if sym < 0:
                charset = _expand_atom(self.tables.terms.atoms[-sym - 1])
            else:
                charset = self._rule_charset(sym - 1, visiting | {rid})
            if charset is None or union & charset:
                return None  # unresolvable, or ambiguous alternatives
            union |= charset
        return frozenset(union)

    def _run_shape(self, rid: int) -> RunShape | None:
        """Detect the star/plus desugar shape for synthetic rule ``rid``."""
        arms = sorted(self.arm_syms[rid], key=len)
        if len(arms) != 2 or len(arms[1]) != 2 or arms[1][1] != rid + 1:
            return None
        unit = arms[1][0]
        if len(arms[0]) == 0:
            has_empty = True
        elif len(arms[0]) == 1 and arms[0][0] == unit:
            has_empty = False
        else:
            return None
        if unit < 0:
            atom = self.tables.terms.atoms[-unit - 1]
            charset = _expand_atom(atom)
            unit_rid = -1
        else:
            unit_rid = unit - 1
            charset = self._rule_charset(unit_rid, frozenset())
        if charset is None or not charset:
            return None
        return (charset, has_empty, unit_rid)

    def candidates(self) -> dict[str, RunShape]:
        """Every synthetic run rule whose collapse is proved safe.

        :returns: rule name → ``(charset, has_empty, unit_rid)``.
        """
        out: dict[str, RunShape] = {}
        for rid, name in enumerate(self.tables.decode.rule_names):
            if not name.startswith(SYNTHETIC_PREFIX):
                continue
            shape = self._run_shape(rid)
            if shape is None:
                continue
            fol = self.follow[rid]
            if fol is None or fol & shape[0]:
                continue  # poisoned or overlapping follow — stay per-char
            out[name] = shape
        return out


_CANDIDATES: dict[int, tuple[ParserTables, dict[str, RunShape]]] = {}
"""Analysis memo — id(tables) → (tables, candidates). The strong reference
pins the id, so a recycled id can never alias a live entry."""


def run_candidates(tables: ParserTables) -> dict[str, RunShape]:
    """The proved-safe run collapses for ``tables``, memoised per grammar.

    :param tables: Plain (uncollapsed) compiled tables.
    :returns: rule name → ``(charset, has_empty_arm, unit_rid)``.
    """
    entry = _CANDIDATES.get(id(tables))
    if entry is None:
        entry = (tables, _Analysis(tables).candidates())
        _CANDIDATES[id(tables)] = entry
    return entry[1]


_RECOGNITION: dict[int, tuple[IrAst, ParserTables]] = {}
"""Recognition-tables memo — id(grammar) → (grammar, tables). The strong
grammar reference pins the id against reuse."""


def recognition_tables(grammar: IrAst) -> ParserTables:
    """Tables with **every** grammar-proved run collapsed — recognition only.

    Recognition builds no tree and no SPPF, so the reducer-side
    reconstruction constraint does not apply: any candidate that passes the
    three grammar proofs collapses (the contribution mode is never read).
    The recognised language is identical by the follow-disjointness proof.

    :param grammar: An Earley-normalised grammar.
    :returns: The maximally collapsed tables (plain when nothing collapses).
    """
    entry = _RECOGNITION.get(id(grammar))
    if entry is not None:
        return entry[1]
    plain = compile_tables(grammar)
    candidates = run_candidates(plain)
    tables = plain
    if candidates:
        runs = {
            name: (RunTerm(charset, 1, RUN_DROP), has_empty)
            for name, (charset, has_empty, _) in candidates.items()
        }
        tables = build_tables(grammar, runs)
    _RECOGNITION[id(grammar)] = (grammar, tables)
    return tables


def unit_leaves(tables: ParserTables, rid: int) -> tuple[set[int], bool] | None:
    """The reduction-visible leaves under charset-unit rule ``rid``.

    Walks synthetic charset rules transitively; a non-synthetic rule is a
    leaf (its own reduction applies per char), a bare terminal sets the
    ``has_bare`` flag (the literal policy applies per char).

    :returns: ``(leaf_rule_ids, has_bare_terminal)``, or ``None`` when the
        structure is not the expected charset-rule shape.
    """
    names = tables.decode.rule_names
    if not names[rid].startswith(SYNTHETIC_PREFIX):
        return ({rid}, False)
    leaves: set[int] = set()
    has_bare = False
    stack = [rid]
    seen = {rid}
    codes = tables.codes
    nxt = codes.next_sym
    dot0 = codes.rule_dot0  # derived property — bind the rebuild once
    while stack:
        current = stack.pop()
        for base in dot0[current]:
            sym = nxt[base]
            if sym == 0 or nxt[base + 1] != 0:
                return None  # not a single-item arm — unexpected shape
            if sym < 0:
                has_bare = True
            else:
                target = sym - 1
                if not names[target].startswith(SYNTHETIC_PREFIX):
                    leaves.add(target)
                elif target not in seen:
                    seen.add(target)
                    stack.append(target)
    return (leaves, has_bare)
