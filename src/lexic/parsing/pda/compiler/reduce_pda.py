"""Reduce (grammar-text) completion — the b1 twin of the model fold.

The reduce-path counterpart of :class:`~lexic.parsing.fold.RuleFold`: where the
model path bakes a fold onto each clone, the grammar-text path bakes a
:class:`ReduceComp` read straight off the reducer's compiled
:class:`~lexic.parsing.earley.reduce.ReducePlan` (H5 — the single home the
Earley fused path also reads, no re-derivation). A leaf w.r.t. the clone
compiler: it imports the flatten runtime constants and the earley reduce
plan, never :mod:`lexic.parsing.pda.compiler.clones` (which imports *these* back).
"""

from __future__ import annotations

from typing import Mapping, NamedTuple, TypeVar

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrLeaf, IrSelf
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.reduce.fused import DROP_KIND, KEEP_KIND, ReducePlan
from lexic.parsing.earley.reduce.policy import YIELD
from lexic.parsing.earley.reduce.reducer import Reducer
from lexic.parsing.pda.compiler.flatten import FlatClone
from lexic.parsing.pda.compiler.opcodes import (
    BUILD_REDUCE,
    R_DROP,
    R_KEEP,
    R_SPLICE,
    TERMINAL_OPS,
)
from lexic.parsing.pda.compiler.specialize import (
    all_clones,
    clone_arms,
    specialize_terminals,
)

__all__ = ["ReduceComp", "ReduceRun"]

_K = TypeVar("_K")


class ReduceComp(NamedTuple):
    """One reduce clone's completion plan — the grammar-text twin of a
    :class:`~lexic.parsing.fold.RuleFold`.

    Read straight off the compiled :class:`~lexic.parsing.earley.reduce.ReducePlan`
    (the single home the Earley fused path also reads — H5, no re-derivation);
    baked onto the flat clone by :func:`_bake_reduce`.

    :ivar kind: :data:`~lexic.parsing.pda.compiler.flatten.R_KEEP` /
        :data:`~lexic.parsing.pda.compiler.flatten.R_DROP` /
        :data:`~lexic.parsing.pda.compiler.flatten.R_SPLICE`.
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


class ReduceCompile(IrLeaf[IrSelf, IrSelf]):
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
        if kind == DROP_KIND:
            return ReduceComp(R_DROP, None, False, False, False)
        if kind != KEEP_KIND:
            raise UnsupportedConstructError(
                f"reduce: rule {name!r} has a custom noise policy"
            )
        body = self.plan.body(self.reducer, rid)
        return ReduceComp(
            R_KEEP,
            body,
            body is YIELD,
            self.plan.mentions[rid],
            self.plan.can_drop[rid],
        )


class ReduceRun(IrLeaf[IrSelf, IrSelf]):
    """The runtime context a reduce PDA carries — reducer, plan, instance tables.

    Bundled on :attr:`~lexic.parsing.pda.compiler.clones.PdaTables.reduce` so
    :func:`~lexic.parsing.pda.runtime.kernel.reduce_runtime.pda_reduce` can drive the b1 reduce
    completion (:data:`~lexic.parsing.pda.compiler.flatten.BUILD_REDUCE`): the reducer's
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
        self.literal_keep = plan.literal_kind == KEEP_KIND


def _span_only(clone: FlatClone, comp: ReduceComp) -> bool:
    """Whether this clone's reduction reads nothing but its own matched span.

    Two completions qualify. A ``DROP`` clone contributes nothing to its
    caller — ``_complete`` pops the frame and returns — and a ``YIELD`` body's
    value IS ``IrStr(span)``. Neither reads a child, so neither needs a frame
    to hold one: the clone runs frame-lessly in
    :meth:`~lexic.parsing.pda.runtime.kernel.kernel.PdaKernel._enter`, which is
    the same leaf run an ``OP_VSTR`` target gets on the model path.

    Terminal-only arms are what make the span matchable inline, and they are
    also what makes a ``YIELD``'s value a contiguous slice: ``_reduce_span``
    stitches raw terminal slices with the kept string values of reference
    children, and an all-terminal arm has none. The gated and attempt clones
    are refused for the reason ``_vstr_inlinable`` refuses them — the inline
    matcher selects on FIRST, which is the decision those clones exist to make
    some other way.

    :param clone: The flat clone, already carrying its specialised arms.
    :param comp: Its completion plan.
    :returns: Whether the clone can run without a frame.
    """
    if comp.kind == R_SPLICE or (comp.kind == R_KEEP and not comp.is_yield):
        return False
    arms = clone_arms(clone)
    return (
        bool(arms)
        and clone.attempt is None
        and clone.kwin_selectors is None
        and clone.pn_selectors is None
        and clone.struct_arm is None
        and all(all(kind in TERMINAL_OPS for kind in arm.kinds) for arm in arms)
    )


def _bake_reduce(clone: FlatClone, comp: ReduceComp) -> None:
    """Bake a reduce clone's completion plan in place (the b1 twin of
    :func:`~lexic.parsing.pda.compiler.clones._bake_build`).

    :param clone: The clone (or inline group) being retargeted for the reducer.
    :param comp: Its :class:`ReduceComp`.
    """
    clone.mode = BUILD_REDUCE
    clone.fold = None
    clone.fields = ()
    clone.plan = ()
    clone.fast = None
    clone.defaults = None
    clone.leaf = _span_only(clone, comp)  # runs frame-lessly when it qualifies
    clone.needs_ends = True  # reduce reconstructs cleaned children from item ends
    clone.reduce_kind = comp.kind
    clone.reduce_body = comp.body
    clone.reduce_is_yield = comp.is_yield
    clone.reduce_span = comp.span_needed
    clone.reduce_can_drop = comp.can_drop


def reduce_rewrite(
    shells: Mapping[_K, FlatClone], completions: Mapping[_K, ReduceComp]
) -> None:
    """Retarget every clone for the reducer completion (replaces model optimize).

    A named clone bakes its rule's :class:`ReduceComp`; an inline group (reached
    only through a ``OP_GRP`` payload, never a clone key) splices — its ordered
    children flatten into the caller.

    Terminal specialisation runs. It is the one pass that removes a quantifier
    loop without removing a frame, an item or an item end, and the reduce
    completion reconstructs its children from exactly those — so the
    specialised arm reads the same and the driver stops stepping a loop per
    character of every exactly-once literal and char class.

    The specialisations that RESHAPE the op-stream stay skipped: ``OP_VSTR``
    inlining and leaf marking run a referenced clone frame-lessly, and dispatch
    conversion drops a pass-through frame. Each removes a completion, which on
    this path is where a rule's reduction body runs — the child would never
    build its value.
    """
    comp_by_id = {id(shells[key]): comp for key, comp in completions.items()}
    splice = ReduceComp(R_SPLICE, None, False, False, False)
    for clone in all_clones(list(shells.values())):
        for arm in clone_arms(clone):
            specialize_terminals(arm)
        _bake_reduce(clone, comp_by_id.get(id(clone), splice))
