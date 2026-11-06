"""Run-terminal detection — where a grammar's lexical layer is *derived*.

Lark closes its step-count gap with a hand-declared token layer matched by C
regexes. This module derives the same layer from the IR instead: a synthetic
star/plus rule (minted by :mod:`~lexic.parsing.earley.normalize`) collapses into a
single maximal-munch :class:`~lexic.parsing.earley.kernel.tables.RunTerm` when three
facts are **proved** about it, so the collapse is exact — never Lark's
silent maximal-munch approximation:

1. **Fixed charset.** The repetition unit resolves to a set of single chars:
   a single-char terminal, or a rule whose every arm is one such atom (or a
   ref to another charset rule), transitively. The set is an exact
   :class:`~lexic.ir.IrCharClass` of any width and either polarity. The
   scanner lists whichever side is small (``[^"]*`` scans until a quote) and
   tests a unit too large on both sides by its ranges.
2. **Derivation uniqueness.** Iterating single-char units splits a run one
   way only, and the charset-rule alternatives are pairwise disjoint — so
   the collapse cannot hide ambiguity from the SPPF.
3. **Follow disjointness.** ``FOLLOW(rule) ∩ charset = ∅`` (classic
   FIRST/FOLLOW over the compiled tables), so a shorter-than-maximal match
   can never be required by any continuation — maximal munch is *complete*.

FOLLOW is built over TERM IDS, from
:func:`~lexic.parsing.earley.kernel.tables.builder.first_ids` (the one FIRST
the seed gates read too), so no terminal can make it unknown. The character
question is asked once per FOLLOW terminal and unit, on interval covers, by
:func:`~lexic.parsing.earley.kernel.tables.atoms.may_begin_within` — a token
answers yes, so a run beside one stays per-char. A grammar with no candidate
shape asks nothing. Product folds add their own licence for
whether hidden per-character structure is reconstructible, fed by
:func:`unit_leaves`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Callable

from lexic.ir import IrAst, IrCharClass, IrLeaf, IrNone, IrNoneType, IrSelf
from lexic.parsing.caches import adopt, memo
from lexic.parsing.earley.kernel.tables.atoms import (
    RunTerm,
    atom_unit,
    may_begin_within,
)
from lexic.parsing.earley.kernel.tables.builder import (
    build_tables,
    compile_tables,
    first_ids,
)
from lexic.parsing.earley.kernel.tables.records import (
    ORIGIN_BITS,
    RUN_DROP,
    ParserTables,
)
from lexic.parsing.earley.normalize import SYNTHETIC_PREFIX

RunShape = tuple[IrCharClass, bool, int]
"""One detected run rule: ``(unit, has_empty_arm, unit_rid)`` — ``unit`` is the
exact class one iteration matches; ``unit_rid`` is ``-1`` when the unit is a
bare terminal atom."""


class _Analysis(IrLeaf[IrSelf, IrSelf]):
    """One grammar's run analysis — arm symbols, shapes, FOLLOW over term ids.

    :ivar tables: The compiled grammar under analysis.
    :ivar arm_syms: rule_id → its arms as symbol lists (``next_sym`` values).
    :ivar nullable: The ids of the rules deriving the empty string.
    """

    __slots__ = ("tables", "arm_syms", "nullable")

    tables: ParserTables
    arm_syms: list[list[list[int]]]
    nullable: frozenset[int]

    def __init__(self, tables: ParserTables) -> None:
        """Read the arms and nullability; FOLLOW waits for a candidate."""
        self.tables = tables
        codes = tables.codes
        dot0 = codes.rule_dot0  # derived property — bind the rebuild once
        self.arm_syms = [[self._syms_from(base) for base in bases] for bases in dot0]
        self.nullable = frozenset(
            rid for rid, done in enumerate(codes.nullable_completes) if done
        )

    def _syms_from(self, base: int) -> list[int]:
        """The symbol run of the arm starting at code ``base``."""
        nxt = self.tables.codes.next_sym
        syms: list[int] = []
        code = base
        while nxt[code] != 0:
            syms.append(nxt[code])
            code += 1
        return syms

    def _follow_sets(self) -> list[set[int]]:
        """Per-rule FOLLOW term ids: direct tail-FIRST + owner-edge fixpoint."""
        codes = self.tables.codes
        first = first_ids(codes.next_sym, codes.rule_dot0, self.nullable)
        follow: list[set[int]] = [set() for _ in self.arm_syms]
        edges: set[tuple[int, int]] = set()  # (owner, target): follow ⊇ follow
        for rid, arms in enumerate(self.arm_syms):
            for syms in arms:
                for k, sym in enumerate(syms):
                    if sym > 0 and self._follow_direct(syms, k, first, follow):
                        edges.add((rid, sym - 1))
        changed = True
        while changed:
            changed = False
            for owner, target in edges:
                before = len(follow[target])
                follow[target] |= follow[owner]
                changed = changed or len(follow[target]) != before
        return follow

    def _follow_direct(
        self,
        syms: list[int],
        k: int,
        first: list[frozenset[int]],
        follow: list[set[int]],
    ) -> bool:
        """Add the tail-FIRST after position ``k`` to the FOLLOW of the rule
        ``syms[k]`` references; ``True`` when the whole tail is nullable, so
        that rule also inherits its owner's FOLLOW."""
        target = follow[syms[k] - 1]
        for sym in syms[k + 1 :]:
            if sym < 0:
                target.add(-sym - 1)
                return False
            target |= first[sym - 1]
            if sym - 1 not in self.nullable:
                return False
        return True

    def _rule_unit(
        self, rid: int, visiting: frozenset[int]
    ) -> IrCharClass | IrNoneType:
        """The exact class rule ``rid`` matches as a single-char unit.

        Requires every arm to be one single-char atom (or a ref to another
        unit rule) with **pairwise-disjoint** alternatives — the
        derivation-uniqueness half of the collapse proof. ``IrNone`` otherwise.
        """
        arms = self.arm_syms[rid]
        if rid in visiting or not arms:
            return IrNone
        union = IrCharClass()
        for syms in arms:
            if len(syms) != 1:
                return IrNone
            unit = self._sym_unit(syms[0], visiting | {rid})
            if isinstance(unit, IrNoneType) or union.meets(unit):
                return IrNone  # unresolvable, or ambiguous alternatives
            union = IrCharClass.from_intervals(union.intervals() + unit.intervals())
        return union

    def _sym_unit(self, sym: int, visiting: frozenset[int]) -> IrCharClass | IrNoneType:
        """The unit of one arm symbol: a terminal's own, or a unit rule's."""
        if sym < 0:
            return atom_unit(self.tables.terms.atoms[-sym - 1])
        return self._rule_unit(sym - 1, visiting)

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
        unit_rid = unit - 1 if unit > 0 else -1
        chars = self._sym_unit(unit, frozenset())
        if isinstance(chars, IrNoneType) or chars.is_empty:
            return None
        return (chars, has_empty, unit_rid)

    def candidates(self) -> dict[str, RunShape]:
        """Every synthetic run rule whose collapse is proved safe.

        :returns: rule name → ``(unit, has_empty, unit_rid)``.
        """
        names = self.tables.decode.rule_names
        shapes: dict[int, RunShape] = {}
        for rid, name in enumerate(names):
            if name.startswith(SYNTHETIC_PREFIX):
                shape = self._run_shape(rid)
                if shape is not None:
                    shapes[rid] = shape
        if not shapes:
            return {}
        follow = self._follow_sets()
        atoms = self.tables.terms.atoms
        meets: dict[tuple[int, IrCharClass], bool] = {}
        out: dict[str, RunShape] = {}
        for rid, shape in shapes.items():
            if any(_meets(atoms, tid, shape[0], meets) for tid in follow[rid]):
                continue  # a continuation can begin inside the run — per-char
            out[names[rid]] = shape
        return out


def _meets(
    atoms: Sequence[IrSelf],
    tid: int,
    unit: IrCharClass,
    meets: dict[tuple[int, IrCharClass], bool],
) -> bool:
    """Whether terminal ``tid`` may begin inside ``unit``, memoised per pair."""
    key = (tid, unit)
    if key not in meets:
        meets[key] = may_begin_within(atoms[tid], unit)
    return meets[key]


_CANDIDATES: dict[int, tuple[ParserTables, dict[str, RunShape]]] = memo({})
"""Analysis memo — id(tables) → (tables, candidates). The strong reference
pins the id, so a recycled id can never alias a live entry."""


def run_candidates(tables: ParserTables) -> dict[str, RunShape]:
    """The proved-safe run collapses for ``tables``, memoised per grammar.

    :param tables: Plain (uncollapsed) compiled tables.
    :returns: rule name → ``(unit, has_empty_arm, unit_rid)``.
    """
    entry = _CANDIDATES.get(id(tables))
    if entry is None:
        entry = (tables, _Analysis(tables).candidates())
        _CANDIDATES[id(tables)] = entry
    return entry[1]


def collapse_runs(
    grammar: IrAst,
    run_mode: Callable[[ParserTables, int], int | None],
    bits: int = ORIGIN_BITS,
) -> ParserTables:
    """Tables for ``grammar`` with every licensed candidate run collapsed.

    The grammar-side proof (charset, uniqueness, follow disjointness) comes
    from :func:`run_candidates`; ``run_mode`` is the caller's policy half —
    it maps a candidate's ``(plain_tables, unit_rid)`` to the run's per-char
    contribution mode, or ``None`` to keep the run per-char.

    :param grammar: An Earley-normalised grammar.
    :param run_mode: The collapse licence, ``(tables, unit_rid) → mode | None``.
    :param bits: The packing tier the tables compile at.
    :returns: The collapsed tables (the plain tables when nothing collapses).
    """
    plain = compile_tables(grammar, bits)
    runs: dict[str, tuple[RunTerm, bool]] = {}
    for name, (unit, has_empty, unit_rid) in run_candidates(plain).items():
        mode = run_mode(plain, unit_rid)
        if mode is not None:
            runs[name] = (RunTerm.over(unit, mode), has_empty)
    if not runs:
        return plain
    tables = build_tables(grammar, runs, bits)
    adopt(id(grammar), tables)  # collapsed tables are keyed on by run analysis
    return tables


_RECOGNITION: dict[tuple[int, int], tuple[IrAst, ParserTables]] = memo({}, 0)
"""Recognition-tables memo — (id(grammar), bits) → (grammar, tables). The
strong grammar reference pins the id against reuse."""


def recognition_tables(grammar: IrAst, bits: int = ORIGIN_BITS) -> ParserTables:
    """Tables with **every** grammar-proved run collapsed — recognition only.

    Recognition builds no tree and no SPPF, so a fold-side reconstruction
    constraint does not apply: any candidate that passes the
    three grammar proofs collapses (the contribution mode is never read).
    The recognised language is identical by the follow-disjointness proof.

    :param grammar: An Earley-normalised grammar.
    :param bits: The packing tier the tables compile at.
    :returns: The maximally collapsed tables (plain when nothing collapses).
    """
    entry = _RECOGNITION.get((id(grammar), bits))
    if entry is not None:
        return entry[1]
    tables = collapse_runs(grammar, lambda _tables, _rid: RUN_DROP, bits)
    _RECOGNITION[(id(grammar), bits)] = (grammar, tables)
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
