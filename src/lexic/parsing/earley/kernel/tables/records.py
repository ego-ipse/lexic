"""Compiled grammar tables — the parser's "codegen moment".

A normalised :class:`~lexic.ir.grammar.nodes.IrAst` compiles **once** into
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

An **Earley item** is the single int ``code << bits | origin`` (``bits`` being
the tables' :class:`Packing` tier, default :data:`ORIGIN_BITS`) — dedup is
``set[int]`` membership, advance is ``item + packing.advance``, and no tuple is
ever allocated on the hot path. An **SPPF handle** ``(item, end)`` packs the
same way again: ``item << bits | end``.

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

from typing import TYPE_CHECKING

from lexic.ir import (
    IrAlphabet,
    IrCharClass,
    IrLeaf,
    IrLiteral,
    IrNot,
    IrQuantifier,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
)
from lexic.parsing.earley.kernel.forest import ParseTree
from lexic.parsing.earley.kernel.tables.atoms import (
    Charset,
    Packing,
    RunTerm,
    atom_accepts,
)

if TYPE_CHECKING:  # a record is CONSTRUCTED from a builder; the builder
    # imports these records, so naming it at runtime would close the loop
    from lexic.parsing.earley.kernel.tables.builder import TableBuilder

ORIGIN_BITS = 28
"""Bits reserved for an origin / end column in a packed item or handle."""

ORIGIN_MASK = (1 << ORIGIN_BITS) - 1
"""Mask extracting the origin from a packed item (or the end from a handle)."""

ADVANCE = 1 << ORIGIN_BITS
"""Adding this to a packed item advances its dot by one (codes are dot-dense)."""


_ONE = IrQuantifier(1, 1)


RUN_DROP, RUN_STR, RUN_LEAF = 0, 1, 2
"""A :class:`RunTerm`'s per-char reduction contribution: nothing (the unit is
DROP noise), one ``IrStr`` per char (the unit rule YIELDs its text), or one
interned ``IrLiteral`` leaf per char (a bare terminal unit under KEEP_RAW)."""


_EMPTY_RUN = RunTerm(frozenset(), 1, RUN_DROP)
"""Placeholder for :attr:`ParserTables.term_runs`' non-run slots — never
matches, never read (the kernel only indexes it where ``term_lens`` is 0)."""


class CodeTables(IrLeaf[IrSelf, IrSelf]):
    """The code-space tables — everything the kernel loop indexes per item.

    :ivar next_sym: code → the symbol discriminator (see the module scheme).
    :ivar code_arm: code → its arm_id.
    :ivar arm_rule: arm_id → owning rule_id.
    :ivar arm_base: arm_id → the arm's dot-0 code.
    :ivar rule_seed_gates: rule_id → the ``(dot-0 code << bits,
        next_sym, gate)`` triples the predictor files per arm (empty when the
        rule is referenced but never defined — prediction seeds nothing).
        This is the stored primitive: the dot-0 codes pre-shifted, pre-paired
        with their symbol, and pre-joined with the arm's FIRST gate, so
        :meth:`~lexic.parsing.earley.kernel.kernel.Kernel._seed` neither re-shifts,
        re-indexes ``next_sym``, nor looks up a parallel column per seed.
        ``gate`` is ``None`` — *always seed* (the arm is empty-deriving or
        its FIRST is poisoned) — or the arm's nullable-prefix-closed FIRST
        char set (see :class:`_FirstGates`): the arm seeds only when the
        column's char is in it. The plain ``rule_seeds`` pair view and the
        ``rule_dot0`` code view are derived from it.
    :ivar nullable_completes: rule_id → completed codes of its empty-deriving
        arms (empty tuple ⇔ not nullable) — the Aycock-Horspool advance set.
    :ivar accept_codes: completed codes of the start rule's arms.
    """

    __slots__ = (
        "next_sym",
        "code_arm",
        "arm_rule",
        "arm_base",
        "rule_seed_gates",
        "nullable_completes",
        "accept_codes",
    )

    next_sym: tuple[int, ...]
    code_arm: tuple[int, ...]
    arm_rule: tuple[int, ...]
    arm_base: tuple[int, ...]
    rule_seed_gates: tuple[tuple[tuple[int, int, Charset], ...], ...]
    nullable_completes: tuple[tuple[int, ...], ...]
    accept_codes: frozenset[int]

    def __init__(self, builder: TableBuilder, bits: int) -> None:
        """Freeze the code-space half of a finished builder.

        :param builder: The builder whose numbering to adopt.
        :param bits: The packing tier the seeds pre-shift by.
        """
        self.next_sym = tuple(sym for _, sym in builder.codes)
        self.code_arm = tuple(aid for aid, _ in builder.codes)
        self.arm_rule = tuple(rid for _, rid, _ in builder.arms)
        self.arm_base = tuple(base for _, _, base in builder.arms)
        self.rule_seed_gates = tuple(
            tuple(
                (code << bits, self.next_sym[code], gate)
                for code, gate in zip(dot0, gates)
            )
            for dot0, gates in zip(builder.rule_dot0, builder.seed_gates())
        )
        self.nullable_completes = tuple(builder.nullable())
        self.accept_codes = builder.accept_codes()

    @property
    def rule_seeds(self) -> tuple[tuple[tuple[int, int], ...], ...]:
        """rule_id → the ``(dot-0 code << bits, next_sym)`` seed pairs.

        The gate-free pair view of ``rule_seed_gates``, rebuilt per access —
        compile-time / test surface only; the hot per-parse path reads
        ``rule_seed_gates`` directly.
        """
        return tuple(
            tuple((shifted, sym) for shifted, sym, _ in seeds)
            for seeds in self.rule_seed_gates
        )

    @property
    def rule_dot0(self) -> tuple[tuple[int, ...], ...]:
        """rule_id → the dot-0 codes of its arms, recovered from the arm tables.

        The compile-time (FIRST/FOLLOW analysis) view of the seed column,
        rebuilt per access — never on a hot or per-rule-loop path. Arms are
        laid out rule by rule in arm order, so grouping ``arm_base`` by
        ``arm_rule`` recovers each rule's dot-0 codes in source order (an
        undefined rule keeps its empty entry).
        """
        out: list[list[int]] = [[] for _ in self.rule_seed_gates]
        for rid, base in zip(self.arm_rule, self.arm_base):
            out[rid].append(base)
        return tuple(tuple(bases) for bases in out)


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

    def __init__(self, builder: TableBuilder) -> None:
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
    needs. The scan loop (:mod:`~lexic.parsing.earley.kernel.kernel`) reads ``lens`` to
    discriminate the scan kind, then ``literals`` or ``runs`` for the matching
    branch — never ``atoms``, which exists for the IR-space consumers
    (:mod:`~lexic.parsing.earley.lexruns`'s FIRST/FOLLOW analysis) that need the
    atom node itself. Also hosts the two lazily-filled per-char caches
    (``char → accepting term ids``, ``char → interned IrLiteral leaf``) —
    per-grammar and monotone, so sharing across parses is safe and amortises
    the fills.

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

    __slots__ = ("atoms", "lens", "literals", "runs", "_char_terms", "_char_leaves")

    atoms: tuple[IrLiteral | IrCharClass | IrNot | IrAlphabet | RunTerm, ...]
    lens: tuple[int, ...]
    literals: tuple[str, ...]
    runs: tuple[RunTerm, ...]
    _char_terms: dict[str, tuple[int, ...]]
    _char_leaves: dict[str, IrLiteral]

    def __init__(self, builder: TableBuilder) -> None:
        """Freeze the terminal-atom tables of a finished builder.

        :param builder: The builder whose numbering to adopt.
        """
        self.atoms = builder.term_atoms()
        self.lens = builder.term_lens()
        self.literals = builder.term_literals()
        self.runs = builder.term_runs()
        self._char_terms = {}
        self._char_leaves = {}

    @property
    def cache_sizes(self) -> tuple[int, int]:
        """Entry counts of the two scanning caches (terms, leaves).

        :returns: ``(distinct chars with resolved term ids, interned leaves)``.
        """
        return (len(self._char_terms), len(self._char_leaves))

    def terms_for(self, char: str) -> tuple[int, ...]:
        """The term_ids whose atom accepts ``char`` (cached per distinct char).

        :param char: The character being scanned.
        :returns: Accepting term_ids, resolved once then replayed.
        """
        cached = self._char_terms.get(char)
        if cached is None:
            cached = tuple(
                tid for tid, atom in enumerate(self.atoms) if atom_accepts(atom, char)
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


class ParserTables(IrLeaf[IrSelf, IrSelf]):
    """The compiled, immutable form of one normalised grammar.

    Composes the code-space and IR-space halves with the terminal tables
    (which carry the per-char scanning caches) and the packing tier the
    parse's items pack with. The lazy caches are per-grammar and monotone,
    so sharing one ``ParserTables`` across parses is safe.

    :ivar codes: The :class:`CodeTables` the kernel loop indexes.
    :ivar decode: The :class:`DecodeTables` for IR decoding.
    :ivar terms: The :class:`TermTables` for terminal atoms, scan kinds and
        the per-char caches.
    :ivar start_id: the start rule's rule_id (``-1`` when never defined).
    :ivar packing: The :class:`Packing` tier — every seed pre-shifts by its
        ``bits``; ``advance - 1`` is the input-length capacity ceiling.
    """

    __slots__ = (
        "codes",
        "decode",
        "terms",
        "start_id",
        "packing",
        "_empty_trees",
    )

    codes: CodeTables
    decode: DecodeTables
    terms: TermTables
    start_id: int
    packing: Packing
    _empty_trees: dict[int, ParseTree | None]

    def __init__(self, builder: TableBuilder, bits: int = ORIGIN_BITS) -> None:
        """Freeze a finished builder's accumulated state.

        :param builder: The builder whose numbering to adopt.
        :param bits: The packing tier for this table set.
        """
        self.codes = CodeTables(builder, bits)
        self.decode = DecodeTables(builder)
        self.terms = TermTables(builder)
        self.start_id = builder.start_id()
        self.packing = Packing(bits)
        self._empty_trees = {}

    def empty_tree(self, rid: int) -> ParseTree | None:
        """Rule ``rid``'s unique empty-match :class:`ParseTree`, or ``None``.

        A zero-width completion consumes no text, so its derivation is fixed
        by the grammar alone — one shared tree serves every column of every
        parse over these tables. ``None`` means no such unique tree exists:
        the rule is not nullable, its empty derivation is ambiguous (more
        than one empty-deriving arm anywhere below), or a nullable cycle is
        involved — the decoder then falls back to the per-column links walk.

        :param rid: The rule id.
        :returns: The shared empty derivation, or ``None``.
        """
        if rid in self._empty_trees:
            return self._empty_trees[rid]
        self._empty_trees[rid] = None  # cycle guard — re-entry reads None
        completes = self.codes.nullable_completes[rid]
        if len(completes) != 1:
            return None
        done = completes[0]
        base = self.codes.arm_base[self.codes.code_arm[done]]
        kids: list[ParseTree] = []
        for code in range(base, done):
            sym = self.codes.next_sym[code]
            kid = self.empty_tree(sym - 1) if sym > 0 else None
            if kid is None:
                return None
            kids.append(kid)
        tree = ParseTree(self.decode.rule_refs[rid], IrSeq(*kids))
        self._empty_trees[rid] = tree
        return tree
