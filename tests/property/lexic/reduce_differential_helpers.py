"""Shared one-path reduction harness for generated flavour syntax."""

from __future__ import annotations

from lexic.compile import compile_ast
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrFlavour, Reducer


class ReduceDifferential:
    """Assert that a flavour's artefact reduction is deterministic.

    The historical name stays so the three property modules keep one shared
    harness. The retired PDA/Earley twin comparison is replaced by a stronger
    production contract: any generated source accepted by the sole route must
    reduce to the identical raw AST on a second invocation.
    """

    def __init__(self, flavour: IrFlavour) -> None:
        """:param flavour: The generated syntax's self-grammar and reducer."""
        reducer = flavour.reducer
        assert isinstance(reducer, Reducer)
        self.flavour = flavour
        self.reducer = reducer
        self.artifact = compile_ast(flavour.grammar)

    def reduce(self, text: str) -> IrAst | None:
        """Reduce ``text`` to an AST, or ``None`` when it is not accepted."""
        try:
            value = self.artifact.reduce(text, self.reducer, cores=1)
        except UnsupportedConstructError:
            return None
        assert isinstance(value, IrAst), type(value).__name__
        return value

    def assert_agree(self, text: str) -> None:
        """Every accepted generated source reduces deterministically."""
        first = self.reduce(text)
        if first is None:
            return
        second = self.reduce(text)
        assert second is not None
        assert second == first, (
            f"one-path reduction was not deterministic:\n{text!r}\n"
            f"  first:  {first!r}\n"
            f"  second: {second!r}"
        )
