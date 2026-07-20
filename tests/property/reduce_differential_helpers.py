"""Shared harness for the per-flavour ε-channel reduce differentials.

Factored out of the GBNF/ABNF/EBNF differentials (``test_reduce_differential.py``
/ ``test_reduce_differential_abnf.py`` / ``test_reduce_differential_ebnf.py``) —
their ``pda()``/``earley()`` wrappers and top-level assertion were identical
apart from the flavour, tripping pylint's whole-tree ``R0801``. All three now
construct one ``ReduceDifferential(<FLAVOUR>)`` and call ``.assert_agree(text)``;
Task 4's completion-grammar flip is therefore a single edit to this class's
``earley_grammar`` line, applying to all three at once.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.flavour import IrFlavour
from lexic.ir.nodes import IrAst
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce import Reducer
from lexic.parsing.pda.runtime.reduce_runtime import parse_pda
from lexic.parsing.pda.runtime.runtime import PdaFail
from lexic.parsing.products import _as_ast, _reduce_product, earley_reduce


class ReduceDifferential:
    """The raw reduce PDA vs. the forced Earley completion, for one flavour.

    ``earley_grammar`` stays ``normalize(grammar)`` (unlifted) while the PDA
    compiles over ``lift_optional_nullables(grammar)`` — see each differential
    module's docstring for why the two routes running different normalised
    shapes is BY DESIGN, and the module-level ``# Task 4 flip point`` comment
    each caller carries next to its own construction of this class.
    """

    def __init__(self, flavour: IrFlavour) -> None:
        """
        :param flavour: The flavour whose self-grammar/reducer both routes run.
        """
        # ``IrFlavour.reducer`` is declared ``ClassVar[IrDispatch]`` on the base
        # (a concrete flavour narrows it to ``Reducer``); narrow it back here so
        # the base-typed ``flavour`` param still satisfies the two products.
        reducer = flavour.reducer
        assert isinstance(reducer, Reducer)
        self.flavour = flavour
        self.reducer = reducer
        self.product = _reduce_product(flavour.grammar, reducer)
        self.earley_grammar = normalize(flavour.grammar)

    def pda(self, text: str) -> IrAst | None:
        """The raw reduce PDA in isolation — ``None`` on any :class:`PdaFail`."""
        try:
            return _as_ast(parse_pda(self.product.pda, text, None))
        except PdaFail:
            return None

    def earley(self, text: str) -> IrAst | None:
        """The forced Earley completion — ``None`` on any unparseable text."""
        try:
            return _as_ast(earley_reduce(self.earley_grammar, text, self.reducer))
        except UnsupportedConstructError:
            return None

    def assert_agree(self, text: str) -> None:
        """PDA-recognised text ⊆ Earley-recognised text, equal where both do.

        Only asserts when the PDA recognises the text — the property is
        one-directional (see the module docstring): the PDA runs the lifted
        self-grammar, Earley the unlifted one, and this is the guard that the
        authored reduce bodies keep the two routes' IR equivalent despite that.

        :param text: The candidate meta-syntax text.
        """
        pda_ir = self.pda(text)
        if pda_ir is None:
            return
        earley_ir = self.earley(text)
        assert earley_ir is not None, f"PDA recognised text Earley rejected:\n{text!r}"
        assert pda_ir == earley_ir, (
            f"PDA/Earley reduce diverged on:\n{text!r}\n"
            f"  pda:    {pda_ir!r}\n"
            f"  earley: {earley_ir!r}"
        )
