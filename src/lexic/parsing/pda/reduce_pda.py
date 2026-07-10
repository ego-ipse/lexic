"""Reduce (grammar-text) completion — the b1 twin of the model fold.

The reduce-path counterpart of :class:`~lexic.parsing.fold.RuleFold`: where the
model path bakes a fold onto each clone, the grammar-text path bakes a
:class:`ReduceComp` read straight off the reducer's compiled
:class:`~lexic.parsing.earley.reduce.ReducePlan` (H5 — the single home the
Earley fused path also reads, no re-derivation). A leaf w.r.t. the clone
compiler: it imports the flatten runtime constants and the earley reduce
plan, never :mod:`lexic.parsing.pda.clones` (which imports *these* back).
"""

from __future__ import annotations

from typing import NamedTuple

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrLeaf, IrSelf
from lexic.parsing.earley.reduce import (
    _DROP_KIND,
    _KEEP_KIND,
    YIELD,
    ReducePlan,
    Reducer,
)
from lexic.parsing.earley.tables import ParserTables
from lexic.parsing.pda.flatten import _R_DROP, _R_KEEP

__all__ = ["ReduceComp", "ReduceRun"]


class ReduceComp(NamedTuple):
    """One reduce clone's completion plan — the grammar-text twin of a
    :class:`~lexic.parsing.fold.RuleFold`.

    Read straight off the compiled :class:`~lexic.parsing.earley.reduce.ReducePlan`
    (the single home the Earley fused path also reads — H5, no re-derivation);
    baked onto the flat clone by :func:`~lexic.parsing.pda.clones._bake_reduce`.

    :ivar kind: :data:`~lexic.parsing.pda.flatten._R_KEEP` /
        :data:`~lexic.parsing.pda.flatten._R_DROP` /
        :data:`~lexic.parsing.pda.flatten._R_SPLICE`.
    :ivar body: The reduction body (``KEEP`` only), else ``None``.
    :ivar is_yield: The body IS ``YIELD`` (span-as-value).
    :ivar span_needed: The body mentions ``YIELD`` (span passed as ``n``).
    :ivar can_drop: ``plan.can_drop`` — a DROP span is reachable beneath the rule.
    """

    kind: int
    body: object
    is_yield: bool
    span_needed: bool
    can_drop: bool


class _ReduceCompile(IrLeaf[IrSelf, IrSelf]):
    """Per-rule reduce-completion source — the reduce target of the compiler.

    Wraps the compiled :class:`~lexic.parsing.earley.reduce.ReducePlan` and the
    rule-name → rule-id map; :meth:`comp_for` produces the :class:`ReduceComp` a
    clone bakes, reading policy exclusively from the plan.

    :ivar reducer: The flavour's reducer.
    :ivar plan: The compiled reduce plan over the instance tables.
    :ivar name_to_rid: Rule name → its id in the instance tables.
    """

    __slots__ = ("reducer", "plan", "name_to_rid")

    reducer: Reducer
    plan: ReducePlan
    name_to_rid: dict[str, int]

    def __init__(
        self, reducer: Reducer, plan: ReducePlan, name_to_rid: dict[str, int]
    ) -> None:
        """:param reducer: the reducer; :param plan: its plan; :param name_to_rid: name→id."""
        self.reducer = reducer
        self.plan = plan
        self.name_to_rid = name_to_rid

    def comp_for(self, name: str) -> ReduceComp:
        """The :class:`ReduceComp` for rule ``name``.

        :raises UnsupportedConstructError: When the rule is unknown to the
            instance tables or carries a custom (non-DROP/KEEP) noise policy the
            reduce runtime cannot reconstruct (a whole-grammar opt-out).
        """
        rid = self.name_to_rid.get(name)
        if rid is None:
            raise UnsupportedConstructError(
                f"reduce: rule {name!r} not in instance tables"
            )
        kind = self.plan.noise_kind[rid]
        if kind == _DROP_KIND:
            return ReduceComp(_R_DROP, None, False, False, False)
        if kind != _KEEP_KIND:
            raise UnsupportedConstructError(
                f"reduce: rule {name!r} has a custom noise policy"
            )
        body = self.plan.body(self.reducer, rid)
        return ReduceComp(
            _R_KEEP,
            body,
            body is YIELD,
            self.plan.mentions[rid],
            self.plan.can_drop[rid],
        )


class ReduceRun(IrLeaf[IrSelf, IrSelf]):
    """The runtime context a reduce PDA carries — reducer, plan, instance tables.

    Bundled on :attr:`~lexic.parsing.pda.clones.PdaTables.reduce` so
    :func:`~lexic.parsing.pda.runtime.parse_pda` can drive the b1 reduce
    completion (:data:`~lexic.parsing.pda.flatten._BUILD_REDUCE`): the reducer's
    reduction bodies evaluate over cleaned children, ``char_leaf`` supplies the
    KEEP_RAW terminal leaves, ``name_to_rid`` resolves an island rule's noise
    policy, ``literal_keep`` is the compiled terminal-leaf policy.

    :ivar reducer: The flavour's reducer.
    :ivar plan: The compiled reduce plan.
    :ivar tables: The instance tables (island sub-parses reduce against them).
    :ivar name_to_rid: Rule name → its instance-table id.
    :ivar literal_keep: ``True`` when the terminal-leaf policy is KEEP_RAW.
    """

    __slots__ = ("reducer", "plan", "tables", "name_to_rid", "literal_keep")

    reducer: Reducer
    plan: ReducePlan
    tables: ParserTables
    name_to_rid: dict[str, int]
    literal_keep: bool

    def __init__(
        self,
        reducer: Reducer,
        plan: ReducePlan,
        tables: ParserTables,
        name_to_rid: dict[str, int],
    ) -> None:
        """Bundle the reduce runtime context (``literal_keep`` derived from the plan)."""
        self.reducer = reducer
        self.plan = plan
        self.tables = tables
        self.name_to_rid = name_to_rid
        self.literal_keep = plan.literal_kind == _KEEP_KIND
