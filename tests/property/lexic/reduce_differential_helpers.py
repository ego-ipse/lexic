"""Shared harness for the per-flavour ε-channel reduce differentials.

Factored out of the GBNF/ABNF/EBNF differentials (``test_reduce_differential.py``
/ ``test_reduce_differential_abnf.py`` / ``test_reduce_differential_ebnf.py``) —
their ``pda()``/``earley()`` wrappers and top-level assertion were identical
apart from the flavour, tripping pylint's whole-tree ``R0801``. All three now
construct one ``ReduceDifferential(<FLAVOUR>)`` and call ``.assert_agree(text)``.
"""

from __future__ import annotations

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrAst, IrFlavour
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.earley.reduce.reducer import Reducer
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.runtime.reduce_runtime import pda_reduce
from lexic.parsing.pda.runtime.runtime import PdaFail
from lexic.parsing.products import _reduce_product, earley_reduce


def _narrow(value: object) -> IrAst:
    """The flavour differential compares grammar reductions — assert the shape."""
    assert isinstance(value, IrAst), type(value).__name__
    return value


class ReduceDifferential:
    """The raw reduce PDA vs. the forced Earley completion, for one flavour.

    ``earley_grammar`` is ``normalize(lift_optional_nullables(grammar))`` —
    the same lifted, normalised grammar the PDA compiles over (the product's
    own ``_reduce_product.earley_grammar``), so this guards the REAL pair
    ``parse_reduced`` actually runs.
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
        self.earley_grammar = normalize(lift_optional_nullables(flavour.grammar))

    def pda(self, text: str) -> IrAst | None:
        """The raw reduce PDA in isolation — ``None`` on any :class:`PdaFail`."""
        try:
            return _narrow(pda_reduce(self.product.pda, text))
        except PdaFail:
            return None

    def earley(self, text: str) -> IrAst | None:
        """The forced Earley completion — ``None`` on any unparseable text."""
        try:
            return _narrow(earley_reduce(self.earley_grammar, text, self.reducer))
        except UnsupportedConstructError:
            return None

    def assert_agree(self, text: str) -> None:
        """PDA-recognised text ⊆ Earley-recognised text, equal where both do.

        Only asserts when the PDA recognises the text — the property stays
        one-directional even on the shared lifted grammar (the PDA's
        predictive descent can fail-soft to :class:`PdaFail` where the fused
        Earley completion still recognises), and this is the guard that both
        routes' IR agree on the one grammar ``parse_reduced`` actually runs.

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
