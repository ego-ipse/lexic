"""``PdaTables`` — what a compiled grammar's predictive half IS.

The artifact `compile_pda` returns and the runtime executes: the flat program,
its clone index, and the island tables the cold path falls back to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from lexic.ir import (
    IrAst,
    IrLeaf,
    IrSelf,
)
from lexic.parsing.earley.kernel.tables import ORIGIN_BITS, ParserTables, compile_tables
from lexic.parsing.pda.compiler.flatten import (
    FlatClone,
    PdaProgram,
)
from lexic.parsing.pda.compiler.lower import flatten_program
from lexic.parsing.pda.compiler.reduce_pda import (
    ReduceRun,
)
from lexic.parsing.pda.compiler.specs import (
    CloneKey,
    CloneSpec,
    IslandRef,
)

if TYPE_CHECKING:  # `clones` imports this module — the reference is mutual
    from lexic.parsing.pda.compiler.clones import PdaCompiler


class PdaTables(IrLeaf[IrSelf, IrSelf]):
    """The compiled predictive-parser artifact — the sibling of :class:`ParserTables`.

    Complete and immutable after :func:`compile_pda`; only the island cache
    fills lazily (in place, the :class:`ParserTables` scanning-cache precedent).

    :ivar clones: Clone key → its :class:`CloneSpec`.
    :ivar start_key: The start clone's key, or an :class:`IslandRef` when the
        start rule is an island (the whole-grammar opt-out signal for Task 6).
    :ivar islands: The island rule names (from
        :attr:`~lexic.parsing.pda.analysis.analysis.GrammarAnalysis.islands`).
    :ivar instance_grammar: The Earley-normalised instance grammar island
        tables are built over.
    :ivar program: The flat int-coded runtime program (:class:`PdaProgram`)
        :class:`~lexic.parsing.pda.runtime.runtime.PdaKernel` walks.
    :ivar reduce: The reduce runtime context (:class:`ReduceRun`) on a
        grammar-text (reducer) PDA, else ``None`` — the model path.
    """

    __slots__ = (
        "clones",
        "start_key",
        "islands",
        "instance_grammar",
        "program",
        "reduce",
        "_island_tables",
    )

    clones: dict[CloneKey, CloneSpec]
    start_key: CloneKey | IslandRef
    islands: frozenset[str]
    instance_grammar: IrAst
    program: PdaProgram
    reduce: ReduceRun | None
    _island_tables: dict[tuple[str, int], ParserTables]

    def __init__(
        self,
        compiler: PdaCompiler,
        start_key: CloneKey | IslandRef,
        instance_grammar: IrAst,
        reduce: ReduceRun | None = None,
    ) -> None:
        """Freeze the clone table, lower it to the flat program, seed the caches.

        The clones, island set and reduce completions come off ``compiler``.
        The island-interior delegate source is attached to :attr:`program` by
        the compile entry points (:func:`_attach_delegates`), so the artifact's
        own attribute set stays put.
        """
        completions = compiler.completions if compiler.reduce is not None else None
        self.clones = compiler.clones
        self.start_key = start_key
        self.islands = compiler.islands
        self.instance_grammar = instance_grammar
        self.program = flatten_program(compiler.clones, start_key, completions)
        self.reduce = reduce
        self._island_tables = {}

    def island_tables(self, name: str, bits: int = ORIGIN_BITS) -> ParserTables:
        """The :class:`ParserTables` for island rule ``name``, built once per
        ``(name, bits)`` and cached — compiled over :attr:`instance_grammar`
        with ``name`` as the start rule (the Earley sub-parser for a
        conflicted rule), at the run's packing tier ``bits`` (an island window
        can span the whole remaining input)."""
        cached = self._island_tables.get((name, bits))
        if cached is None:
            cached = compile_tables(IrAst(self.instance_grammar.rules, name), bits)
            self._island_tables[(name, bits)] = cached
        return cached

    def island_delegates(self, name: str) -> "dict[int, FlatClone]":
        """The island-interior delegate clones for island ``name`` (rule_id →
        clone), computed once by the program's
        :class:`~lexic.parsing.pda.compiler.delegate_compile.DelegateSource` — empty when
        nothing delegates. The runtime wraps each into a fail-soft callable and
        threads it through the island Earley sub-parse (the keys are island
        tables rule ids, the predictor's ``rid``)."""
        return cast("dict[int, FlatClone]", self.program.delegates.for_island(name))

    def reset_delegate_cache(self) -> None:
        """Drop the per-island delegate cache — a test seam for the A/B parity
        gate, which swaps in a no-delegates :class:`DelegateSource` and
        recomputes each side."""
        self.program.delegates.reset()
