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

from lexic.exceptions import SemanticVerdict
from lexic.parsing.earley.kernel.forest.support.ambiguity import same_value
from lexic.parsing.product import (
    ConstructionTables,
    LoweringOwned,
    MeaningOp,
    OperandTables,
    ProductExecutor,
    ProductProgram,
    RootOp,
    RuleProduct,
    lower_product,
    verify_program,
)

__all__ = ["ModelBinding"]


def _identity_root[M](carry: M, _verdicts: tuple[SemanticVerdict, ...]) -> M:
    """The default root finalizer — the start rule's value, unchanged."""
    return carry


class ModelBinding[M]:
    """One grammar's model product — what a parse entry is handed.

    The product IS the binding: the rules each contextual name completes
    through, the verified program they lower to, the construction tables a
    completion indexes, and the one executor that runs them over a derivation.
    One object rather than four parameters, so a caller cannot pair a
    grammar's rules with another grammar's constructors and the per-identity
    memo has a single key to hold.

    Everything but :attr:`rules` is DERIVED here, once. The construction
    tables are read back off the verified program's own operand lanes rather
    than resolved a second time, so what a completion indexes is exactly what
    the verifier bounded. The executor is derived here too because it scans
    every rule for span demand once, and an island splice reaches for it per
    island reference.

    :ivar rules: Rule name → its authored product, in contextual-code order.
    :ivar owned: The authored tables this binding lowered from, retained so a
        worker replica can rebuild an EQUAL binding with physically distinct
        tables rather than sharing this one's.
    :ivar program: The lowered, verified program. Every rule in it names one
        tagged, non-empty, in-bounds completion range.
    :ivar codes: Rule name → its index in :attr:`program`.
    :ivar construction: The constructor and symbol operand tables a completion
        indexes — the program's own lanes.
    :ivar executor: The one completion over :attr:`rules` and
        :attr:`construction`.
    """

    __slots__ = ("rules", "owned", "program", "codes", "construction", "executor")

    rules: Mapping[str, RuleProduct]
    owned: LoweringOwned
    program: ProductProgram[M, M]
    codes: Mapping[str, int]
    construction: ConstructionTables
    executor: ProductExecutor[M]

    def __init__(
        self,
        rules: Mapping[str, RuleProduct] | None = None,
        owned: LoweringOwned = LoweringOwned(),
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
        self.rules = {} if rules is None else rules
        self.owned = owned
        self.codes = {name: at for at, name in enumerate(self.rules)}
        # The meaning row is the engine's own value law, not `==`: every
        # ambiguity gate compares with `same_value`, so a program declaring
        # anything else would name a law it does not live under.
        operands: OperandTables[M, M] = OperandTables(
            (), (), (), (), (same_value,), (_identity_root,), (), ()
        )
        self.program = lower_product(
            list(self.rules.values()),
            operands,
            owned=owned,
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
        verify_program(self.program)
        self.construction = ConstructionTables(
            self.program.operands.constructors, self.program.operands.symbols
        )
        self.executor = ProductExecutor(self.rules, self.construction)
