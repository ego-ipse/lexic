"""Compiled grammar tables — the parser's "codegen moment".

A normalised :class:`~lexic.ir.nodes.IrAst` compiles **once** into
:class:`ParserTables`: flat, int-coded tables the kernel loop indexes instead of
interpreting IR nodes per item. Grammar stays ground truth; the tables are a
compiled *representation* of it, exactly as ``generated/*.py`` is codegen's
compiled representation of a ``RuleSpec``.

**The coding scheme.** Every dotted position of every arm gets one int ``code``,
laid out so consecutive dots are consecutive ints — advancing an item's dot is
``+ 1`` on the code. ``next_sym[code]`` discriminates the classic Earley
trichotomy with a single list index (no ``isinstance``, no dispatch table):

======================  ==========================================
``next_sym[code]``      meaning
======================  ==========================================
``rule_id + 1``  (> 0)  dot faces that non-terminal — predict
``-(term_id + 1)`` (<0) dot faces that terminal atom — scan
``0``                   dot past the arm's end — complete
======================  ==========================================

An **Earley item** is the single int ``code << ORIGIN_BITS | origin`` — dedup
is ``set[int]`` membership, advance is ``item + ADVANCE``, and no tuple is ever
allocated on the hot path. An **SPPF handle** ``(item, end)`` packs the same
way again: ``item << ORIGIN_BITS | end``.

The tables split along their consumers: :class:`CodeTables` is the code-space
half the kernel loop indexes per item; :class:`DecodeTables` is the IR-space
half used only when a packed result is decoded back into IR nodes;
:class:`ParserTables` composes the two with the terminal atoms and the
per-char scanning caches.

:func:`compile_tables` memoises per grammar object (keeping a strong reference,
so a recycled ``id`` can never alias a live entry) — the compile cost is paid
once per grammar, like building a ``lark.Lark`` instance.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrAtom, IrLeaf, IrSelf
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRange,
    IrRuleRef,
    IrSequence,
)

ORIGIN_BITS = 20
"""Bits reserved for an origin / end column in a packed item or handle."""

ORIGIN_MASK = (1 << ORIGIN_BITS) - 1
"""Mask extracting the origin from a packed item (or the end from a handle)."""

ADVANCE = 1 << ORIGIN_BITS
"""Adding this to a packed item advances its dot by one (codes are dot-dense)."""

KLink = tuple[int, int, "int | str"]
"""One packed SPPF family: ``(predecessor_item, predecessor_end, child)`` —
``child`` is a packed handle (completed sub-derivation) or the scanned char."""


def predecessor_chain(
    links: dict[int, list[KLink]], item: int, end: int, base: int
) -> list[KLink] | None:
    """Walk a packed handle's single-link predecessor chain down to ``base``.

    Shared by :class:`~lexic.parsing_2.kernel.FastTree` and
    :class:`~lexic.parsing_2.reduce.FusedReduce`, whose kid-collection walks
    are otherwise identical.

    :param links: The parse's SPPF family table.
    :param item: The handle's packed item (dot strictly past ``base``).
    :param end: The handle's column.
    :param base: The arm's dot-0 code — the chain stops here.
    :returns: The chain's ``(predecessor_item, predecessor_end, child)``
        triples in source order, or ``None`` when a key is missing or packs
        more than one family — the caller's cue to bail (no build, or fall
        back to the ambiguity-aware path).
    """
    chain: list[KLink] = []
    while (item >> ORIGIN_BITS) != base:
        bucket = links.get((item << ORIGIN_BITS) | end)
        if bucket is None or len(bucket) > 1:
            return None
        item, end, child = bucket[0]
        chain.append((item, end, child))
    chain.reverse()
    return chain


_ONE = IrQuantifier(1, 1)


def atom_accepts(atom: "IrLiteral | IrCharClass | RunTerm", char: str) -> bool:
    """Whether a terminal atom can **begin** with ``char`` — the scan filter.

    A multi-char literal is begun by its first character (the full match is
    the scanner's ``startswith``); a :class:`RunTerm` by any char of its set.

    :param atom: A terminal atom (``IrLiteral``, ``IrCharClass``, ``RunTerm``).
    :param char: A single character.
    :returns: ``True`` when a match at ``char`` is possible.
    """
    if isinstance(atom, IrLiteral):
        return atom.startswith(char)  # IrLiteral IS-A str
    if isinstance(atom, IrCharClass):
        for element in atom:
            if isinstance(element, IrRange):
                if str(element.lo) <= char <= str(element.hi):
                    return True
            elif char in str(element):
                return True
    if isinstance(atom, RunTerm):
        return char in atom.charset
    return False


RUN_DROP, RUN_STR, RUN_LEAF = 0, 1, 2
"""A :class:`RunTerm`'s per-char reduction contribution: nothing (the unit is
DROP noise), one ``IrStr`` per char (the unit rule YIELDs its text), or one
interned ``IrLiteral`` leaf per char (a bare terminal unit under KEEP_RAW)."""


class RunTerm(IrLeaf[IrSelf, IrSelf], IrAtom):
    """A compiled maximal-munch run terminal — one scan step per whole run.

    Replaces the body of a *synthetic* star/plus rule whose unit resolves to
    a fixed charset, whose iteration is derivation-unique, and whose FOLLOW
    set is disjoint from the charset (so maximal munch is complete, not a
    heuristic — see :mod:`lexic.parsing_2.lexruns`). The scanner consumes the
    maximal run in one loop and lands the advance at its end.

    IS-A :class:`~lexic.ir.base.IrAtom`: in the compiled-tables world a run
    terminal fills exactly the atom slot a literal or char class would in an
    uncollapsed grammar (:meth:`_TableBuilder._compile_run_rule` wraps one in
    an ``IrItem`` alongside them).

    :ivar charset: The characters the run ranges over.
    :ivar lo: The minimum run length (≥ 1 — an empty star match stays on the
        synthetic rule's empty arm).
    :ivar mode: The per-char reduction contribution (:data:`RUN_DROP` /
        :data:`RUN_STR` / :data:`RUN_LEAF`).
    """

    __slots__ = ("charset", "lo", "mode")

    charset: frozenset[str]
    lo: int
    mode: int

    def __init__(self, charset: frozenset[str], lo: int, mode: int) -> None:
        """Freeze one run terminal's matching and reduction metadata."""
        self.charset = charset
        self.lo = lo
        self.mode = mode


_EMPTY_RUN = RunTerm(frozenset(), 1, RUN_DROP)
"""Placeholder for :attr:`ParserTables.term_runs`' non-run slots — never
matches, never read (the kernel only indexes it where ``term_lens`` is 0)."""


class CodeTables(IrLeaf[IrSelf, IrSelf]):
    """The code-space tables — everything the kernel loop indexes per item.

    :ivar next_sym: code → the symbol discriminator (see the module scheme).
    :ivar code_arm: code → its arm_id.
    :ivar arm_rule: arm_id → owning rule_id.
    :ivar arm_base: arm_id → the arm's dot-0 code.
    :ivar rule_dot0: rule_id → the dot-0 codes of its arms (empty when the
        rule is referenced but never defined — prediction seeds nothing).
    :ivar nullable_completes: rule_id → completed codes of its empty-deriving
        arms (empty tuple ⇔ not nullable) — the Aycock-Horspool advance set.
    :ivar accept_codes: completed codes of the start rule's arms.
    """

    __slots__ = (
        "next_sym",
        "code_arm",
        "arm_rule",
        "arm_base",
        "rule_dot0",
        "nullable_completes",
        "accept_codes",
    )

    next_sym: tuple[int, ...]
    code_arm: tuple[int, ...]
    arm_rule: tuple[int, ...]
    arm_base: tuple[int, ...]
    rule_dot0: tuple[tuple[int, ...], ...]
    nullable_completes: tuple[tuple[int, ...], ...]
    accept_codes: frozenset[int]

    def __init__(self, builder: _TableBuilder) -> None:
        """Freeze the code-space half of a finished builder.

        :param builder: The builder whose numbering to adopt.
        """
        self.next_sym = tuple(sym for _, sym in builder.codes)
        self.code_arm = tuple(aid for aid, _ in builder.codes)
        self.arm_rule = tuple(rid for _, rid, _ in builder.arms)
        self.arm_base = tuple(base for _, _, base in builder.arms)
        self.rule_dot0 = tuple(tuple(d) for d in builder.rule_dot0)
        self.nullable_completes = tuple(builder.nullable())
        self.accept_codes = builder.accept_codes()


class DecodeTables(IrLeaf[IrSelf, IrSelf]):
    """The IR-space tables — used only when packed results decode back to IR.

    :ivar rule_names: rule_id → rule name.
    :ivar rule_ids: rule name → rule_id.
    :ivar rule_refs: rule_id → interned :class:`IrRuleRef` (for tree symbols).
    :ivar arm_seqs: arm_id → the arm's :class:`IrSequence`.
    """

    __slots__ = ("rule_names", "rule_ids", "rule_refs", "arm_seqs")

    rule_names: tuple[str, ...]
    rule_ids: dict[str, int]
    rule_refs: tuple[IrRuleRef, ...]
    arm_seqs: tuple[IrSequence, ...]

    def __init__(self, builder: _TableBuilder) -> None:
        """Freeze the IR-space half of a finished builder.

        :param builder: The builder whose numbering to adopt.
        """
        self.rule_names = tuple(builder.rule_ids)
        self.rule_ids = dict(builder.rule_ids)
        self.rule_refs = tuple(IrRuleRef(n) for n in self.rule_names)
        self.arm_seqs = tuple(seq for seq, _, _ in builder.arms)


class TermTables(IrLeaf[IrSelf, IrSelf]):
    """The terminal-atom tables — one row per distinct terminal.

    Split out of :class:`ParserTables` for the same reason :class:`CodeTables`
    and :class:`DecodeTables` are: each consumer indexes only the columns it
    needs. The scan loop (:mod:`~lexic.parsing_2.kernel`) reads ``lens`` to
    discriminate the scan kind, then ``literals`` or ``runs`` for the matching
    branch — never ``atoms``, which exists for the IR-space consumers
    (:mod:`~lexic.parsing_2.lexruns`'s FIRST/FOLLOW analysis) that need the
    atom node itself.

    :ivar atoms: term_id → the terminal atom node.
    :ivar lens: term_id → scan kind: the literal's length, ``1`` for a char
        class, ``0`` for a :class:`RunTerm` (variable-length run).
    :ivar literals: term_id → the literal text when ``lens`` is > 1, else
        ``""``. A compile-time-precise parallel to ``atoms`` so the scan
        loop's multi-char-literal branch indexes a plain ``str`` with no
        per-step narrowing.
    :ivar runs: term_id → the :class:`RunTerm` when ``lens`` is ``0``, else
        :data:`_EMPTY_RUN`. Same rationale as ``literals``, for the
        run-terminal branch.
    """

    __slots__ = ("atoms", "lens", "literals", "runs")

    atoms: tuple["IrLiteral | IrCharClass | RunTerm", ...]
    lens: tuple[int, ...]
    literals: tuple[str, ...]
    runs: tuple[RunTerm, ...]

    def __init__(self, builder: _TableBuilder) -> None:
        """Freeze the terminal-atom tables of a finished builder.

        :param builder: The builder whose numbering to adopt.
        """
        self.atoms = builder.term_atoms()
        self.lens = builder.term_lens()
        self.literals = builder.term_literals()
        self.runs = builder.term_runs()


class ParserTables(IrLeaf[IrSelf, IrSelf]):
    """The compiled, immutable form of one normalised grammar.

    Composes the code-space and IR-space halves with the terminal tables and
    the two lazily-filled scanning caches (``char → accepting term ids``,
    ``char → interned IrLiteral leaf``). The caches are per-grammar and
    monotone, so sharing one ``ParserTables`` across parses is safe and
    amortises the fills.

    :ivar codes: The :class:`CodeTables` the kernel loop indexes.
    :ivar decode: The :class:`DecodeTables` for IR decoding.
    :ivar terms: The :class:`TermTables` for terminal atoms and scan kinds.
    :ivar start_id: the start rule's rule_id (``-1`` when never defined).
    """

    __slots__ = (
        "codes",
        "decode",
        "terms",
        "start_id",
        "_char_terms",
        "_char_leaves",
    )

    codes: CodeTables
    decode: DecodeTables
    terms: TermTables
    start_id: int
    _char_terms: dict[str, tuple[int, ...]]
    _char_leaves: dict[str, IrLiteral]

    def __init__(self, builder: _TableBuilder) -> None:
        """Freeze a finished builder's accumulated state.

        :param builder: The builder whose numbering to adopt.
        """
        self.codes = CodeTables(builder)
        self.decode = DecodeTables(builder)
        self.terms = TermTables(builder)
        self.start_id = builder.start_id()
        self._char_terms = {}
        self._char_leaves = {}

    def terms_for(self, char: str) -> tuple[int, ...]:
        """The term_ids whose atom accepts ``char`` (cached per distinct char).

        :param char: The character being scanned.
        :returns: Accepting term_ids, resolved once then replayed.
        """
        cached = self._char_terms.get(char)
        if cached is None:
            cached = tuple(
                tid
                for tid, atom in enumerate(self.terms.atoms)
                if atom_accepts(atom, char)
            )
            self._char_terms[char] = cached
        return cached

    def char_leaf(self, char: str) -> IrLiteral:
        """The interned :class:`IrLiteral` leaf for a scanned ``char``.

        :param char: The consumed character.
        :returns: One shared leaf per distinct character.
        """
        leaf = self._char_leaves.get(char)
        if leaf is None:
            leaf = IrLiteral(char)
            self._char_leaves[char] = leaf
        return leaf


class _TableBuilder:
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
        self.terms: dict["IrLiteral | IrCharClass | RunTerm", int] = {}
        self.arms: list[tuple[IrSequence, int, int]] = []
        self.codes: list[tuple[int, int]] = []
        self.rule_dot0: list[list[int]] = []

    def build(self) -> ParserTables:
        """Compile the grammar.

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
        return ParserTables(self)

    def start_id(self) -> int:
        """The start rule's id, or ``-1`` when the grammar never defines it."""
        return self.rule_ids.get(str(self.grammar.start), -1)

    def term_atoms(self) -> tuple["IrLiteral | IrCharClass | RunTerm", ...]:
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

    def _term_id(self, atom: "IrLiteral | IrCharClass | RunTerm") -> int:
        """The term_id for ``atom``, minting one on first sight."""
        tid = self.terms.get(atom)
        if tid is None:
            tid = len(self.terms)
            self.terms[atom] = tid
        return tid

    def _compile_rule(self, rid: int, body: IrAlternation) -> None:
        """Lay out one rule's arms as dot-dense code runs.

        Value-equal arms of one rule intern to a single arm — the IR node IS
        its value, so two equal arms are the same arm (matching the legacy
        item tuples, whose arm field deduped by value).
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
        if item.quantifier != _ONE:
            raise UnsupportedConstructError(
                f"parsing_2: unnormalised quantifier {item.quantifier!r} — "
                "run normalize() before compiling"
            )
        atom = item.atom
        if isinstance(atom, IrRuleRef):
            return self._rule_id(str(atom)) + 1
        if isinstance(atom, (IrLiteral, IrCharClass)):
            return -(self._term_id(atom) + 1)
        raise UnsupportedConstructError(
            f"parsing_2: unnormalised atom {type(atom).__name__} — "
            "run normalize() before compiling"
        )

    def nullable(self) -> list[tuple[int, ...]]:
        """Per-rule completed codes of empty-deriving arms, by least fixpoint.

        A rule is nullable if any arm is nullable; an arm is nullable if every
        position predicts a nullable rule (an empty arm vacuously).
        """
        nullable: set[int] = set()
        changed = True
        while changed:
            changed = False
            for arm_id, (_, rid, _) in enumerate(self.arms):
                if rid not in nullable and self._arm_nullable(arm_id, nullable):
                    nullable.add(rid)
                    changed = True
        out: list[tuple[int, ...]] = [() for _ in self.rule_ids]
        for arm_id, (seq, rid, base) in enumerate(self.arms):
            if rid in nullable and self._arm_nullable(arm_id, nullable):
                out[rid] = out[rid] + (base + len(seq),)
        return out

    def _arm_nullable(self, arm_id: int, nullable: set[int]) -> bool:
        """Whether every position of ``arm_id`` predicts a nullable rule."""
        seq, _, base = self.arms[arm_id]
        for code in range(base, base + len(seq)):
            sym = self.codes[code][1]
            if sym <= 0 or (sym - 1) not in nullable:
                return False
        return True


def build_tables(
    grammar: IrAst, runs: dict[str, tuple[RunTerm, bool]] | None = None
) -> ParserTables:
    """Build tables for ``grammar``, optionally collapsing run rules (uncached).

    :param grammar: An Earley-normalised grammar.
    :param runs: rule name → ``(run_term, has_empty_arm)`` collapse spec.
    :returns: Fresh tables (callers memoise their own variants).
    :raises UnsupportedConstructError: On a non-normalised construct.
    """
    return _TableBuilder(grammar, runs).build()


_CACHE: dict[int, tuple[IrAst, ParserTables]] = {}
"""Compile memo — id(grammar) → (the grammar, its tables). The strong grammar
reference pins the id, so a recycled id can never alias a live entry."""


def compile_tables(grammar: IrAst) -> ParserTables:
    """The :class:`ParserTables` for ``grammar``, compiled once and memoised.

    :param grammar: An Earley-normalised grammar (see
        :func:`lexic.parsing_2.normalize.normalize`).
    :returns: The compiled tables (shared across parses of the same grammar).
    :raises UnsupportedConstructError: On a non-normalised construct.
    """
    entry = _CACHE.get(id(grammar))
    if entry is not None:
        return entry[1]
    tables = _TableBuilder(grammar).build()
    _CACHE[id(grammar)] = (grammar, tables)
    return tables
