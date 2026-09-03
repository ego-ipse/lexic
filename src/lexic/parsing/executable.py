"""The bound model product — what a parse entry is handed.

Binding is the one moment an AUTHORED product becomes an executable one. A
surface hands in its rules and the tables lowering owns — constructors to
check, routes to specialize, symbol keys and the registry that resolves them —
and gets back a verified program plus the readers both engines use. Doing that
here rather than at each surface is what makes "lowered once, verified cold at
bind" literally true: no caller can hand an engine a program the verifier has
not seen.

Its own module because both halves of the engine reach it: the product entry
hands it down, the clone compiler bakes from it, and a record either of them
owned would make the other import it back.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from lexic.exceptions import SemanticVerdict, UnsupportedConstructError
from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.product import (
    LoweringOwned,
    MeaningOp,
    OperandTables,
    ProductExecutor,
    ProductProgram,
    RootOp,
    RuleProduct,
    RuleRoutine,
    lower_product,
    rule_routines,
    verify_program,
)

__all__ = ["ModelExecutable"]


def _identity_root[M](carry: M, _verdicts: tuple[SemanticVerdict, ...]) -> M:
    """The default root finalizer — the start rule's value, unchanged."""
    return carry


class ModelExecutable[M]:
    """One grammar's model product — what a parse entry is handed.

    The product IS the binding: the verified program its rules lowered to, the
    routine each contextual name completes through, and the one executor that
    runs them over a derivation. One object rather than several parameters, so
    a caller cannot pair a grammar's captures with another grammar's
    constructors and the per-identity memo has a single key to hold.

    The authored rules are LOWERING INPUT and nothing else: they are consumed
    in the constructor and not retained. Everything downstream — completion,
    the clone bake, stitch layout — reads :attr:`routines`, which is the
    verified program read back. That is what makes "the program the verifier
    passed is the program that runs" a property of the object rather than a
    claim about it; holding the authored records too would leave a second
    representation for an engine to reach for.

    Verification is a claim about an OBJECT, so the object cannot change after
    it is made. Every attribute here is bound once and the projections are
    read-only views over containers no caller holds; the executor keeps its own
    plain dict as a private physical copy, so the hot reader pays a dict lookup
    and the public surface still cannot be edited into disagreeing with the
    program the verifier passed.

    :ivar program: The lowered, verified program. Every rule in it names one
        tagged, non-empty, in-bounds completion range.
    :ivar codes: Rule name → its index in :attr:`program`, read-only.
    :ivar routines: Rule name → its verified completion routine, read-only.
    :ivar executor: The one completion over :attr:`routines`.
    """

    __slots__ = ("program", "codes", "routines", "executor")

    program: ProductProgram[M, M]
    codes: Mapping[str, int]
    routines: Mapping[str, RuleRoutine[M]]
    executor: ProductExecutor[M]

    def __init__(
        self,
        rules: Mapping[str, RuleProduct] | None = None,
        owned: LoweringOwned[M] = LoweringOwned(),
    ) -> None:
        """Lower one surface's authored rules, and verify them before any use.

        :param rules: Rule name → its authored product. An authored
            compile-time surface fills this from its own table; a generated
            model from the binding view.
        :param owned: The tables lowering writes — constructors to validate,
            routes to specialize, and symbol keys with the registry they
            resolve through.
        :raises UnsupportedConstructError: When the rules do not lower, or the
            program they lower to does not verify.
        """
        authored = {} if rules is None else rules
        codes = {name: at for at, name in enumerate(authored)}
        object.__setattr__(self, "codes", MappingProxyType(codes))
        # The meaning row is the engine's own value law, not `==`: every
        # ambiguity gate compares with `same_value`, so a program declaring
        # anything else would name a law it does not live under.
        operands: OperandTables[M, M] = OperandTables(
            (), (), (), (), (same_value,), (_identity_root,), (), ()
        )
        program = lower_product(
            list(authored.values()),
            operands,
            owned=owned,
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
        verify_program(program)
        resolved = rule_routines(program)
        routines = {name: resolved[code] for name, code in codes.items()}
        object.__setattr__(self, "program", program)
        object.__setattr__(self, "routines", MappingProxyType(routines))
        object.__setattr__(self, "executor", ProductExecutor(routines))

    def __setattr__(self, name: str, value: object) -> None:
        """Refuse every rebinding — a verified executable is bound once.

        :raises UnsupportedConstructError: Always. Rebinding one of these is
            an attempt to produce the defective compiled artefact that class
            names, not a field failing its own check.
        """
        del value
        raise UnsupportedConstructError(
            f"parsing: {type(self).__name__}.{name} cannot be reassigned; a "
            "verified executable is what the verifier passed"
        )

    def __delattr__(self, name: str) -> None:
        """Refuse every deletion, for the same reason as :meth:`__setattr__`.

        :raises UnsupportedConstructError: Always.
        """
        raise UnsupportedConstructError(
            f"parsing: {type(self).__name__}.{name} cannot be deleted; a "
            "verified executable is what the verifier passed"
        )

    def replica(self) -> ModelExecutable[M]:
        """An equal binding whose routine map is a worker's own.

        The memo keys on the BINDING's identity, so a worker that wants its own
        compiled tables needs its own binding; the routine map is rebuilt —
        inside the executor, which copies what it is handed — because it is the
        container every completion reads, and therefore the one whose sharing
        costs the reference-count traffic that held eight threads below the
        throughput of one. The read-only projections are shared by identity
        instead: nothing can write through them, so nothing has to be copied.

        Nothing is lowered or verified again. The program is immutable and
        already passed the cold gate, so re-deriving it per worker would pay a
        whole lowering pass to reach the artefact this one is holding — and a
        worker rebuilding the constructors would change what a model is built
        from, when model equality across workers is the contract the split
        rests on.
        """
        copy = object.__new__(type(self))
        object.__setattr__(copy, "program", self.program)
        object.__setattr__(copy, "codes", self.codes)
        object.__setattr__(copy, "routines", self.routines)
        object.__setattr__(copy, "executor", ProductExecutor(self.routines))
        return copy
