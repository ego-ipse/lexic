"""Declarative reduction policy attached to a grammar flavour.

The reducer declares a rule-body table plus child and literal contribution
policies. Parsing no longer folds an Earley tree through this object: the
compile artefact derives a pruned model grammar from the declarations, then
``ReduceFold`` applies the bodies to that model.
"""

from __future__ import annotations

from lexic.ir import IR_DEFAULT, IrDispatch, IrMap, IrSelf, IrTuple
from lexic.parsing.earley.reduce.policy import KEEP_RAW, KEEP_REDUCED


class Reducer(IrDispatch):
    """Rule reduction declarations and their cleaning policy.

    ``actions`` is a value-keyed map from rule refs to reduction bodies;
    ``default`` is the body used on a miss. ``noise`` controls whether a
    referenced rule contributes to its parent's channel, while ``literal``
    controls terminal-leaf contributions.
    """

    noise: IrMap = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
    literal: IrSelf = KEEP_RAW

    def body(self, symbol: IrSelf) -> IrSelf:
        """The reduction body declared for ``symbol``.

        :param symbol: The value-keyed rule reference.
        :returns: Its explicit body, or :attr:`default` on a miss.
        """
        found = self.actions.get(symbol)
        return self.default if found is None else found
