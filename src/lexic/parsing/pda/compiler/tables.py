"""``PdaTables`` — what a compiled grammar's predictive half IS.

The artifact `compile_pda` returns and the runtime executes: the flat program
and the island tables the cold path falls back to. The authored clone specs it
was lowered from are a compile-time intermediate and do not survive here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lexic.ir import (
    IrAst,
    IrLeaf,
    IrSelf,
)
from lexic.parsing.caches import once
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ORIGIN_BITS, ParserTables
from lexic.parsing.executable import private_copy
from lexic.parsing.pda.compiler.program.flatten import (
    FlatClone,
    PdaProgram,
)
from lexic.parsing.pda.compiler.program.lower import flatten_program
from lexic.parsing.pda.compiler.specs import (
    CloneKey,
    IslandRef,
)

if TYPE_CHECKING:  # `clones` imports this module — the reference is mutual
    from lexic.parsing.pda.compiler.clones import PdaCompiler


class PdaTables(IrLeaf[IrSelf, IrSelf]):
    """The compiled predictive-parser artifact — the sibling of :class:`ParserTables`.

    Complete and immutable after :func:`compile_pda`; only the island cache
    fills lazily (in place, the :class:`ParserTables` scanning-cache precedent).

    The authored :class:`CloneSpec` layer is **not** part of it. Those specs
    are what the clone compiler produces on the way here; once
    :func:`~lexic.parsing.pda.compiler.program.lower.flatten_program` has
    lowered them the artifact is the program, and holding them on as well kept
    a large share of its GC-tracked population alive for the life of the
    process with nothing reading it. A caller that wants to
    READ the specs compiles them itself
    (:func:`~lexic.parsing.pda.compiler.clones.compile_clones`), where their
    lifetime is its own.

    :ivar start_key: The start clone's key, or an :class:`IslandRef` when the
        start rule is an island (the whole-grammar opt-out signal for Task 6).
    :ivar islands: The island rule names. The seam's continuation evidence
        used to live here as a per-island FOLLOW map; it does not, because the
        set a two-ends check needs is what the island's REFERENCES are
        followed by, not what the island rule's own FOLLOW contains, and that
        set rides on the reference
        (:attr:`~lexic.parsing.pda.compiler.specs.IslandRef.cont`).
    :ivar instance_grammar: The Earley-normalised instance grammar island
        tables are built over.
    :ivar program: The flat int-coded runtime program (:class:`PdaProgram`)
        :class:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel` walks.
    :ivar origin: For a worker's private copy, the tables it was copied from:
        an island it has not met yet is compiled there and copied here. ``None``
        on the tables a compile built.
    """

    __slots__ = (
        "start_key",
        "islands",
        "instance_grammar",
        "program",
        "_island_tables",
        "origin",
    )

    start_key: CloneKey | IslandRef
    islands: frozenset[str]
    instance_grammar: IrAst
    program: PdaProgram
    _island_tables: dict[tuple[str, int], ParserTables]
    origin: PdaTables | None

    def __init__(
        self,
        compiler: PdaCompiler,
        start_key: CloneKey | IslandRef,
        instance_grammar: IrAst,
    ) -> None:
        """Freeze the clone table, lower it to the flat program, seed the caches.

        The clones and island set come off ``compiler``, which the caller
        then drops: nothing below is a view onto it.
        The island-interior delegate source is attached to :attr:`program` by
        the compile entry points (:func:`_attach_delegates`), so the artifact's
        own attribute set stays put.
        """
        self.start_key = start_key
        self.islands = compiler.islands
        self.instance_grammar = instance_grammar
        self.program = flatten_program(compiler.clones, start_key, compiler.folds)
        self._island_tables = {}
        self.origin = None

    def island_tables(self, name: str, bits: int = ORIGIN_BITS) -> ParserTables:
        """The :class:`ParserTables` for island rule ``name``, built once per
        ``(name, bits)`` and cached — compiled over :attr:`instance_grammar`
        with ``name`` as the start rule (the Earley sub-parser for a
        conflicted rule), at the run's packing tier ``bits`` (an island window
        can span the whole remaining input)."""
        cached = self._island_tables.get((name, bits))
        return self._island_miss(name, bits) if cached is None else cached

    def _island_miss(self, name: str, bits: int) -> ParserTables:
        """Island ``name``'s tables where none is held: a replica copies its
        origin's, which compiles them once whichever replica asked first."""
        if self.origin is not None:
            held = self.origin.island_tables(name, bits)
            made = private_copy(held)
            self._island_tables[(name, bits)] = made
            return made
        with once((id(self), name, bits)):
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
        return self.program.delegates.for_island(name)

    def reset_delegate_cache(self) -> None:
        """Drop the per-island delegate cache — a test seam for the A/B parity
        gate, which swaps in a no-delegates :class:`DelegateSource` and
        recomputes each side."""
        self.program.delegates.reset()
