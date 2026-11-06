"""The table builder — a normalised grammar into the compiled tables.

The codegen moment: rules become int-coded productions, terminals become
acceptance tests, and the FIRST gates that let the kernel skip a prediction
are computed once here rather than per parse.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlphabet,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLeaf,
    IrLiteral,
    IrNot,
    IrRuleRef,
    IrSelf,
    IrSequence,
)
from lexic.parsing.caches import adopt, memo
from lexic.parsing.earley.kernel.tables.atoms import (
    RunTerm,
    expand_atom,
)
from lexic.parsing.earley.kernel.tables.records import (
    ORIGIN_BITS,
    RUN_DROP,
    Charset,
    ParserTables,
)

_EMPTY_RUN = RunTerm(frozenset(), 1, RUN_DROP)
"""Placeholder for :attr:`ParserTables.term_runs`' non-run slots — never
matches, never read (the kernel only indexes it where ``term_lens`` is 0)."""

_CACHE: dict[tuple[int, int], tuple[IrAst, ParserTables]] = memo({}, 0)
"""Compile memo — (id(grammar), bits) → (the grammar, its tables). The strong
grammar reference pins the id, so a recycled id can never alias a live
entry."""


class TableBuilder:
    """One-shot builder walking a normalised grammar into :class:`ParserTables`.

    Attributes are deliberately public: the table constructors read them to
    freeze the result. ``arms`` collects ``(seq, rule_id, base_code)`` triples
    and ``codes`` collects ``(arm_id, next_sym)`` pairs, so each position is
    laid out exactly once.
    """

    def __init__(
        self, grammar: IrAst, runs: dict[str, tuple[RunTerm, bool]] | None = None
    ) -> None:
        """Prepare a build of ``grammar``, optionally collapsing run rules.

        :param grammar: The Earley-normalised grammar to compile.
        :param runs: rule name → ``(run_term, has_empty_arm)`` — synthetic
            rules whose body compiles to a maximal-munch run terminal.
        """
        self.grammar = grammar
        self.runs = runs or {}
        self.rule_ids: dict[str, int] = {}
        self.terms: dict[
            "IrLiteral | IrCharClass | IrNot | IrAlphabet | RunTerm", int
        ] = {}
        self.arms: list[tuple[IrSequence, int, int]] = []
        self.codes: list[tuple[int, int]] = []
        self.rule_dot0: list[list[int]] = []

    def build(self, bits: int = ORIGIN_BITS) -> ParserTables:
        """Compile the grammar at packing tier ``bits``.

        :param bits: The origin-bits tier the tables pack with.
        :returns: The finished tables.
        :raises UnsupportedConstructError: On a non-normalised construct
            (a quantifier other than ``(1, 1)``, or a group/negation atom).
        """
        for rule in self.grammar.rules:
            self._rule_id(str(rule.name))
        for rule in self.grammar.rules:
            name = str(rule.name)
            spec = self.runs.get(name)
            if spec is None:
                self._compile_rule(self.rule_ids[name], rule.body)
            else:
                self._compile_run_rule(self.rule_ids[name], spec)
        return ParserTables(self, bits)

    def start_id(self) -> int:
        """The start rule's id, or ``-1`` when the grammar never defines it."""
        return self.rule_ids.get(str(self.grammar.start), -1)

    def term_atoms(
        self,
    ) -> tuple["IrLiteral | IrCharClass | IrNot | IrAlphabet | RunTerm", ...]:
        """The terminal atoms in term_id order."""
        return tuple(self.terms)

    def term_lens(self) -> tuple[int, ...]:
        """Per term, the scan kind: literal length / 1 (char class) / 0 (run)."""
        out = []
        for atom in self.terms:
            if isinstance(atom, RunTerm):
                out.append(0)
            elif isinstance(atom, IrLiteral):
                out.append(len(atom))
            else:
                out.append(1)
        return tuple(out)

    def term_literals(self) -> tuple[str, ...]:
        """Per term, the literal text when ``term_lens`` is > 1, else ``""``."""
        return tuple(
            str(atom) if isinstance(atom, IrLiteral) and len(atom) > 1 else ""
            for atom in self.terms
        )

    def term_runs(self) -> tuple[RunTerm, ...]:
        """Per term, the :class:`RunTerm` when ``term_lens`` is 0, else the
        shared :data:`_EMPTY_RUN` placeholder."""
        return tuple(
            atom if isinstance(atom, RunTerm) else _EMPTY_RUN for atom in self.terms
        )

    def accept_codes(self) -> frozenset[int]:
        """Completed codes of the start rule's arms (the accepting items)."""
        start = self.start_id()
        return frozenset(
            base + len(seq) for seq, rid, base in self.arms if rid == start
        )

    def _rule_id(self, name: str) -> int:
        """The rule_id for ``name``, minting one on first sight."""
        rid = self.rule_ids.get(name)
        if rid is None:
            rid = len(self.rule_ids)
            self.rule_ids[name] = rid
            self.rule_dot0.append([])
        return rid

    def _compile_run_rule(self, rid: int, spec: tuple[RunTerm, bool]) -> None:
        """Lay out a collapsed run rule: an optional empty arm + one run item."""
        term, has_empty = spec
        if has_empty:
            arm_id = len(self.arms)
            base = len(self.codes)
            self.arms.append((IrSequence(), rid, base))
            self.rule_dot0[rid].append(base)
            self.codes.append((arm_id, 0))
        arm_id = len(self.arms)
        base = len(self.codes)
        self.arms.append((IrSequence(IrItem(term)), rid, base))
        self.rule_dot0[rid].append(base)
        self.codes.append((arm_id, -(self._term_id(term) + 1)))
        self.codes.append((arm_id, 0))

    def _term_id(
        self, atom: IrLiteral | IrCharClass | IrNot | IrAlphabet | RunTerm
    ) -> int:
        """The term_id for ``atom``, minting one on first sight."""
        tid = self.terms.get(atom)
        if tid is None:
            tid = len(self.terms)
            self.terms[atom] = tid
        return tid

    def _compile_rule(self, rid: int, body: IrAlternation) -> None:
        """Lay out one rule's arms as dot-dense code runs.

        Value-equal arms of one rule intern to a single arm — the IR node IS
        its value, so two equal arms are the same arm (matching
        :class:`~lexic.parsing.earley.kernel.forest.chart.EarleyItem`'s arm field, which
        dedupes by value).
        """
        seen_arms: set[IrSequence] = set()
        for arm in body:
            if arm in seen_arms:
                continue
            seen_arms.add(arm)
            arm_id = len(self.arms)
            base = len(self.codes)
            self.arms.append((arm, rid, base))
            self.rule_dot0[rid].append(base)
            for item in arm:
                self.codes.append((arm_id, self._symbol_of(item)))
            self.codes.append((arm_id, 0))  # the completed position

    def _symbol_of(self, item: IrItem) -> int:
        """The ``next_sym`` discriminator for one arm item.

        :raises UnsupportedConstructError: If the item is not normalised.
        """
        if not item.quantifier.once():
            raise UnsupportedConstructError(
                f"parsing: unnormalised quantifier {item.quantifier!r} — "
                "run normalize() before compiling"
            )
        atom = item.atom
        if isinstance(atom, IrRuleRef):
            return self._rule_id(str(atom)) + 1
        if isinstance(atom, (IrLiteral, IrCharClass, IrNot, IrAlphabet)):
            return -(self._term_id(atom) + 1)
        raise UnsupportedConstructError(
            f"parsing: unnormalised atom {type(atom).__name__} — "
            "run normalize() before compiling"
        )

    def nullable_rules(self) -> frozenset[int]:
        """Rule ids deriving the empty string — the grammar's own set."""
        ids = self.rule_ids
        return frozenset([ids[name] for name in self.grammar.nullable()])

    def nullable(self, nullable: frozenset[int]) -> list[tuple[int, ...]]:
        """Per-rule completed codes of empty-deriving arms, given the rule ids
        that derive the empty string (:meth:`nullable_rules`)."""
        out: list[tuple[int, ...]] = [() for _ in self.rule_ids]
        for arm_id, (seq, rid, base) in enumerate(self.arms):
            if rid in nullable and self.arm_nullable(arm_id, nullable):
                out[rid] = out[rid] + (base + len(seq),)
        return out

    def arm_nullable(self, arm_id: int, nullable: frozenset[int]) -> bool:
        """Whether every position of ``arm_id`` predicts a nullable rule."""
        seq, _, base = self.arms[arm_id]
        for code in range(base, base + len(seq)):
            sym = self.codes[code][1]
            if sym <= 0 or (sym - 1) not in nullable:
                return False
        return True

    def seed_gates(
        self, next_sym: Sequence[int], nullable: frozenset[int]
    ) -> list[tuple[Charset, ...]]:
        """Per rule, per dot-0 arm, the FIRST seed gate (``None`` = always).

        :param next_sym: code → symbol, the column the finished tables carry.
        :param nullable: The ids of the rules deriving the empty string.
        """
        return _FirstGates(self, next_sym, nullable).gates()


def first_ids(
    next_sym: Sequence[int],
    rule_dot0: Sequence[Sequence[int]],
    nullable: Collection[int],
) -> list[frozenset[int]]:
    """Per rule, the ids of the terminals it can begin with — a least fixpoint.

    An arm contributes its symbols left to right until one cannot vanish; a
    terminal contributes its own id. Exact, since an id never needs listing,
    and built from what a builder and a finished table both carry, so each
    caller computes it when it needs it and nothing stores it.

    :param next_sym: code → symbol (``< 0`` terminal, ``> 0`` rule + 1, ``0`` end).
    :param rule_dot0: rule_id → the dot-0 codes of its arms.
    :param nullable: The ids of the rules deriving the empty string.
    :returns: rule_id → the term ids it can begin with.
    """
    first: list[set[int]] = [set() for _ in rule_dot0]
    changed = True
    while changed:
        changed = False
        for rid, dot0 in enumerate(rule_dot0):
            mine = first[rid]
            before = len(mine)
            for base in dot0:
                _grow_arm_first(next_sym, base, nullable, mine, first)
            changed = changed or len(mine) != before
    return [frozenset(ids) for ids in first]


def _grow_arm_first(
    next_sym: Sequence[int],
    base: int,
    nullable: Collection[int],
    mine: set[int],
    first: list[set[int]],
) -> None:
    """Grow ``mine`` by the term ids the arm at ``base`` can begin with."""
    code = base
    while (sym := next_sym[code]) != 0:
        if sym < 0:
            mine.add(-sym - 1)
            return
        mine |= first[sym - 1]
        if sym - 1 not in nullable:
            return
        code += 1


class _FirstGates(IrLeaf[IrSelf, IrSelf]):
    """Per-arm FIRST seed gates — the compile-time half of gated prediction.

    Runs over a finished builder's layout (so it covers every table variant,
    run-collapsed or not). A gate is ``None`` — *always seed* — for an
    empty-deriving arm (its empty completion's advance links must exist in
    the chart) or a poisoned FIRST (an ``IrNot`` atom, a char class wider
    than :data:`MAX_CHARSET`, or anything transitively reaching one);
    otherwise it is the arm's FIRST char set with nullable-prefix
    continuation, and the predictor seeds the arm only when the column's
    char is in it. A rule's FIRST is :func:`first_ids` read as characters:
    the union of its terminals' first chars, poisoned when one is not
    listable.

    :ivar builder: The builder whose layout to analyse.
    :ivar atoms: term_id → the terminal atom (for terminal FIRST chars).
    :ivar nullable_rules: Rule ids deriving the empty string.
    :ivar first: rule_id → the term ids it can begin with.
    :ivar chars: rule_id → its FIRST as characters, read on first use.
    :ivar term_chars: term_id → its begin-chars, read on first use.
    """

    __slots__ = ("builder", "atoms", "nullable_rules", "first", "chars", "term_chars")

    builder: TableBuilder
    atoms: tuple["IrLiteral | IrCharClass | IrNot | IrAlphabet | RunTerm", ...]
    nullable_rules: frozenset[int]
    first: list[frozenset[int]]
    chars: dict[int, Charset]
    term_chars: dict[int, Charset]

    def __init__(
        self, builder: TableBuilder, next_sym: Sequence[int], nullable: frozenset[int]
    ) -> None:
        """Run the FIRST analysis over ``builder``'s finished layout."""
        self.builder = builder
        self.atoms = builder.term_atoms()
        self.nullable_rules = nullable
        self.first = first_ids(next_sym, builder.rule_dot0, self.nullable_rules)
        self.chars = {}
        self.term_chars = {}

    def gates(self) -> list[tuple[Charset, ...]]:
        """Per rule, per dot-0 arm, the seed gate (``None`` = always seed)."""
        return [
            tuple(self._gate_of(base) for base in dot0)
            for dot0 in self.builder.rule_dot0
        ]

    def _gate_of(self, base: int) -> Charset:
        """The gate of the arm whose dot-0 code is ``base``."""
        arm_id = self.builder.codes[base][0]
        if self.builder.arm_nullable(arm_id, self.nullable_rules):
            return None  # empty-deriving — must always seed
        return self._arm_first(base)

    def _term_first(self, tid: int) -> Charset:
        """Begin-chars of terminal ``tid``, or poisoned — read once per terminal.

        A multi-char literal is begun by its first char; a :class:`RunTerm`
        by any char of its set (too many to list when it is negated or
        ranged); the rest is :func:`expand_atom`.
        """
        if tid not in self.term_chars:
            atom = self.atoms[tid]
            if isinstance(atom, IrLiteral):
                got = frozenset(atom[0]) if atom else frozenset()
            elif isinstance(atom, RunTerm):
                got = atom.first_chars
            else:
                got = expand_atom(atom)
            self.term_chars[tid] = got
        return self.term_chars[tid]

    def _rule_chars(self, rid: int) -> Charset:
        """Rule ``rid``'s FIRST as characters — poisoned when a terminal is."""
        if rid not in self.chars:
            out: set[str] = set()
            for tid in self.first[rid]:
                got = self._term_first(tid)
                if got is None:
                    self.chars[rid] = None
                    return None
                out |= got
            self.chars[rid] = frozenset(out)
        return self.chars[rid]

    def _arm_first(self, base: int) -> Charset:
        """The FIRST of the arm at ``base``, with nullable-prefix continuation.

        Walks the arm's symbols left to right, unioning each symbol's
        first-chars, stopping at the first non-nullable symbol; poison
        anywhere on the walked prefix poisons the arm.
        """
        codes = self.builder.codes
        out: set[str] = set()
        code = base
        while (sym := codes[code][1]) != 0:
            add = self._term_first(-sym - 1) if sym < 0 else self._rule_chars(sym - 1)
            if add is None:
                return None
            out |= add
            if sym < 0 or sym - 1 not in self.nullable_rules:
                return frozenset(out)
            code += 1
        return frozenset(out)


def build_tables(
    grammar: IrAst,
    runs: dict[str, tuple[RunTerm, bool]] | None = None,
    bits: int = ORIGIN_BITS,
) -> ParserTables:
    """Build tables for ``grammar``, optionally collapsing run rules (uncached).

    :param grammar: An Earley-normalised grammar.
    :param runs: rule name → ``(run_term, has_empty_arm)`` collapse spec.
    :param bits: The origin-bits packing tier.
    :returns: Fresh tables (callers memoise their own variants).
    :raises UnsupportedConstructError: On a non-normalised construct.
    """
    return TableBuilder(grammar, runs).build(bits)


def compile_tables(grammar: IrAst, bits: int = ORIGIN_BITS) -> ParserTables:
    """The :class:`ParserTables` for ``grammar``, compiled once and memoised.

    :param grammar: An Earley-normalised grammar (see
        :func:`lexic.parsing.earley.normalize.normalize`).
    :param bits: The origin-bits packing tier (input capacity ``2**bits - 1``).
    :returns: The compiled tables (shared across parses of the same grammar).
    :raises UnsupportedConstructError: On a non-normalised construct.
    """
    entry = _CACHE.get((id(grammar), bits))
    if entry is not None:
        return entry[1]
    tables = TableBuilder(grammar).build(bits)
    _CACHE[(id(grammar), bits)] = (grammar, tables)
    adopt(id(grammar), tables)  # the run analysis keys on the tables' identity
    return tables
