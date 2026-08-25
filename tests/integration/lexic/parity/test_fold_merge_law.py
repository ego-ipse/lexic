"""The FOLD-MERGE LAW: a node's fold value depends only on its own record and
its model children's folded values — never on wall-clock completion order.

That law is the entire basis for ever partitioning ``ReduceFold`` across
workers, so it is decided here, against the CURRENT sequential fold, before
any concurrency exists. Each check targets a different way the law could be
false; a design that partitions the fold reads these as its refutation
criteria (see the design notes this suite pins down):

- **V1** (:func:`test_partition_oracle_matches_a_standalone_re_fold`) — a
  fold worker's exact case: fold the whole model once, then re-invoke a
  sample of its ``fold_subtree`` calls STANDALONE (a fresh top-level fold that
  starts mid-tree with an empty cache) and assert the value is IR-equal AND
  same-type to what the whole-document fold produced there.
- **V2** (:func:`test_shuffled_linear_extension_folds_bit_identical`) — fill
  the channel pass in a random valid topological order instead of the fixed
  post-order, and assert a bit-identical reduction. Parallelism IS
  non-deterministic completion order, so an order-sensitive reducer body
  fails this deterministically.
- **V4** (:func:`test_shared_nodes_are_leaf_only_value_models`) — whether any
  ``(id(node), rule)`` is folded from more than one parent. Real models ARE
  DAGs (not trees), so a future partitioner must duplicate a shared node's
  fold rather than assume tree structure; this pins that the sharing stays
  confined to leaves so the duplicated work is cheap.

Four small witnesses — one per reducer family (GBNF, ABNF, EBNF self-grammars
reducing a real ground-truth file) plus JSON — because "the law holds for any
reducer" cannot be shown on one. Kept corpus-SIZED-DOWN relative to the
16-witness sweep that first decided this: this suite runs in seconds.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, NamedTuple, Self

from lexic.compile import compile_ast
from lexic.compile.artifact import _reduce_entry
from lexic.compile.reduce.fold import ReduceFold
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrAst, IrSelf, Reducer
from tests.integration.lexic.parity.fold_recorder_helpers import CarriesFoldState
from tests.paths import GROUND_TRUTH

_SEED = 20260825
"""Fixed seed — V2's bit-identical assertion must be reproducible."""


class Witness(NamedTuple):
    """One ``(grammar, reducer, document)`` the law must hold for.

    :ivar name: A short label for failure messages.
    :ivar grammar: The authored grammar.
    :ivar reducer: Its reducer.
    :ivar text: A document it reduces.
    """

    name: str
    grammar: IrAst
    reducer: Reducer
    text: str


class Call(NamedTuple):
    """One recorded ``fold_subtree`` invocation and the value it produced.

    :ivar model: The child value ``fold_subtree`` was called on.
    :ivar rule: The child's own rule.
    :ivar body_rule: The body actually applied (post pass-through chain).
    :ivar slot: The declaring field's ``(rule, required)``, or ``None``.
    :ivar value: What the sequential fold's ``fold_subtree`` returned.
    """

    model: Any
    rule: str
    body_rule: str
    slot: tuple[str, bool] | None
    value: IrSelf


@dataclass
class _Observed:
    """What a :class:`Recorder` run has seen — split out from ``Recorder``
    itself so the fold subclass stays a thin wrapper around the source
    fold's own state rather than a second attribute-heavy class.
    """

    calls: list[Call] = field(default_factory=list)
    edges: dict[tuple[int, str], set[tuple[int, str] | None]] = field(
        default_factory=dict
    )
    assembling: tuple[int, str] | None = None
    on_demand: int = 0
    recording: bool = True


class Recorder(CarriesFoldState):
    """A fold that records every ``fold_subtree`` call and its parent edge.

    Subclassed rather than monkeypatched so ``ReduceFold`` itself is
    untouched — this suite verifies the law, it does not implement it.
    Also supports filling the channel pass in a random linear extension
    (:meth:`_fill_permuted`), which is V2's whole mechanism.

    Built through :meth:`wrapping` rather than ``__init__``: it reuses an
    existing fold's already-compiled ``tables``/``plan`` rather than
    recompiling them, so there is no ``ReduceFold.__init__`` call this
    class could sensibly make.
    """

    permute: random.Random | None
    observed: _Observed

    @classmethod
    def wrapping(cls, source: ReduceFold, permute: random.Random | None = None) -> Self:
        """Wrap an existing fold's tables and plan without recompiling them.

        :param source: The fold whose ``tables``/``plan``/``reducer`` to reuse.
        :param permute: When given, :meth:`_fill_channels` fills in a random
            valid topological order instead of the fixed post-order.
        """
        self = cls.carrying(source)
        self.permute = permute
        self.observed = _Observed()
        return self

    def fold_subtree(
        self, value: Any, rule: str, body_rule: str, slot: tuple[str, bool] | None
    ) -> IrSelf:
        """Record the call, its result, and which parent asked for it."""
        out = super().fold_subtree(value, rule, body_rule, slot)
        if self.observed.recording:
            self.observed.calls.append(Call(value, rule, body_rule, slot, out))
            key = (id(value), rule)
            self.observed.edges.setdefault(key, set()).add(self.observed.assembling)
        return out

    def _channel_once(self, model: Any, rule: str) -> list[IrSelf]:
        """Note whose channel is under assembly, so ``fold_subtree`` can name it."""
        previous = self.observed.assembling
        self.observed.assembling = (id(model), rule)
        try:
            return super()._channel_once(model, rule)
        finally:
            self.observed.assembling = previous

    def channel(self, model: Any, rule: str) -> list[IrSelf]:
        """Count the ON-DEMAND fill branch and delegate."""
        cache = self._channel_cache
        if cache is not None and (id(model), rule) not in cache:
            self.observed.on_demand += 1
        return super().channel(model, rule)

    def _fill_channels(self, model: Any, rule: str) -> None:
        """Fill in a random linear extension when permuting, else the base."""
        if self.permute is None:
            super()._fill_channels(model, rule)
            return
        self._fill_permuted(model, rule)

    def _fill_permuted(self, model: Any, rule: str) -> None:
        """Fill every discoverable node in a RANDOM valid topological order.

        Kahn's algorithm with a randomly-drawn ready node: every run is a
        different linear extension of the same dependency order (children
        always before parents; everything else free to move).
        """
        assert self._channel_cache is not None
        assert self.permute is not None
        deps = self.dependency_graph(model, rule)
        parents, pending = _kahn_indegree(deps)
        ready = [key for key, count in pending.items() if count == 0]
        while ready:
            at = self.permute.randrange(len(ready))
            ready[at], ready[-1] = ready[-1], ready[at]
            key = ready.pop()
            _kids, node = deps[key]
            if key not in self._channel_cache:
                self._channel_cache[key] = self._channel_once(node, key[1])
            for parent in parents.get(key, ()):
                pending[parent] -= 1
                if pending[parent] == 0:
                    ready.append(parent)

    def dependency_graph(
        self, model: Any, rule: str
    ) -> dict[tuple[int, str], tuple[list[tuple[int, str]], Any]]:
        """``key -> (child keys, node)`` over everything the base pass reaches."""
        out: dict[tuple[int, str], tuple[list[tuple[int, str]], Any]] = {}
        stack = [(model, rule)]
        while stack:
            node, node_rule = stack.pop()
            key = (id(node), node_rule)
            if key in out or key in (self._channel_cache or {}):
                continue
            kids: list[tuple[int, str]] = []
            for name, _bind in self.tables.fields_of.get(node_rule, ()):
                for kid, kid_rule in self._model_values(getattr(node, name)):
                    kids.append((id(kid), kid_rule))
                    stack.append((kid, kid_rule))
            out[key] = (kids, node)
        return out


def _kahn_indegree(
    deps: dict[tuple[int, str], tuple[list[tuple[int, str]], Any]],
) -> tuple[dict[tuple[int, str], list[tuple[int, str]]], dict[tuple[int, str], int]]:
    """``(parents, pending)`` — the reverse edges and in-degree Kahn's
    algorithm needs, both derived from :meth:`Recorder.dependency_graph`."""
    parents: dict[tuple[int, str], list[tuple[int, str]]] = {}
    pending: dict[tuple[int, str], int] = {}
    for key, (kids, _node) in deps.items():
        inner = {k for k in kids if k in deps}
        pending[key] = len(inner)
        for kid in inner:
            parents.setdefault(kid, []).append(key)
    return parents, pending


def _synthetic_json() -> str:
    """A small document with enough nesting for interesting fold structure."""
    return (
        '{"model": {"vocab": {"a": 0, "b": 1, "ab": 2}, "type": "BPE"}, '
        '"nested": {"x": [1, 2, [3, {"y": "z"}]], "w": {"e": [true, null]}}, '
        '"strings": ["plain", "with \\"escape\\"", "caf\\u00e9"]}'
    )


def witnesses() -> tuple[Witness, ...]:
    """One small witness per reducer family — GBNF/ABNF/EBNF self-grammars
    reducing a real ground-truth file, plus JSON on a synthetic document."""
    return (
        Witness(
            "gbnf:think.gbnf",
            GBNF_FLAVOUR.grammar,
            GBNF_FLAVOUR.reducer,
            (GROUND_TRUTH / "think.gbnf").read_text(encoding="utf-8"),
        ),
        Witness(
            "abnf:arithmetic.abnf",
            ABNF_FLAVOUR.grammar,
            ABNF_FLAVOUR.reducer,
            (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8"),
        ),
        Witness(
            "ebnf:arithmetic.ebnf",
            EBNF_FLAVOUR.grammar,
            EBNF_FLAVOUR.reducer,
            (GROUND_TRUTH / "arithmetic.ebnf").read_text(encoding="utf-8"),
        ),
        Witness("json:synthetic", JSON_GRAMMAR, JSON_REDUCER, _synthetic_json()),
    )


def _build(w: Witness) -> tuple[ReduceFold, Any]:
    """The witness's fold and its parsed variant model."""
    entry = _reduce_entry(
        compile_ast(w.grammar, cache_key=f"i22-law-{w.name}"), w.reducer
    )
    return entry.fold, entry.variant.parse(w.text, cores=1)


# ── V1 — the partition oracle ───────────────────────────────────────────────


def test_partition_oracle_matches_a_standalone_re_fold() -> None:
    """Every ``fold_subtree`` call the sequential fold makes, re-invoked standalone
    (a fresh top-level fold, empty cache — a worker's exact starting point),
    reproduces the SAME value: IR-equal AND same leaf kind.

    This IS the fold-merge law stated as a test: a worker folding one
    maximal subtree independently must build the value the parent's channel
    wanted, at every node the sequential fold visited — this re-invokes ALL
    of them (the witnesses are small enough that "all" stays test-fast),
    not a sample.
    """
    for w in witnesses():
        fold, model = _build(w)
        base = Recorder.wrapping(fold)
        base.reduce(model)
        calls = base.observed.calls
        assert calls, f"{w.name}: nothing to check — the witness is vacuous"
        for call in calls:
            standalone = Recorder.wrapping(fold)
            standalone.observed.recording = False
            got = standalone.fold_subtree(
                call.model, call.rule, call.body_rule, call.slot
            )
            assert got == call.value, (
                f"{w.name}: standalone re-fold of {call.rule!r} differs from "
                "the sequential fold's value"
            )
            assert type(got) is type(call.value), (
                f"{w.name}: standalone re-fold of {call.rule!r} produced "
                f"{type(got).__name__}, sequential produced "
                f"{type(call.value).__name__} — same VALUE, wrong leaf kind"
            )


# ── V2 — shuffled linear-extension fold ─────────────────────────────────────


def test_shuffled_linear_extension_folds_bit_identical() -> None:
    """Filling the channel pass in a RANDOM valid topological order — five
    fixed-seed permutations per witness — reproduces the sequential fold's
    value bit-for-bit. Parallelism is exactly non-deterministic completion
    order, so an order-sensitive reducer body would fail this
    deterministically and reproducibly (the fixed seed makes a failure
    replayable).

    **Blind spot, and why V1 covers it instead:** starting from the root,
    ``ReduceFold``'s own discovery is already complete before the fill
    begins, so PERMUTING that fill never drives ``channel``'s ON-DEMAND path
    (the branch that fills a node reached with no bound edge from the
    parent currently being assembled — alternation/pass-through chains can
    expose one). Zero permuted runs below ever take it; V1's standalone
    re-folds do (they start mid-tree with an empty cache, which is exactly
    what exposes it), so the two checks are complementary rather than
    redundant — V2 alone would have this exact gap.
    """
    for w in witnesses():
        fold, model = _build(w)
        truth = Recorder.wrapping(fold).reduce(model)
        rng = random.Random(_SEED)
        on_demand = 0
        for _ in range(5):
            shuffled = Recorder.wrapping(fold, permute=rng)
            shuffled.observed.recording = False
            got = shuffled.reduce(model)
            on_demand += shuffled.observed.on_demand
            assert got == truth, f"{w.name}: a permuted fold differs from sequential"
            assert type(got) is type(truth), (
                f"{w.name}: a permuted fold changed the reduction's leaf kind"
            )
        assert on_demand == 0, (
            f"{w.name}: permutation fired the on-demand path {on_demand} "
            "times — this test's blind-spot claim above is now false"
        )


# ── V4 — leaf-only sharing (T3 / the partitioner's cost assumption) ────────


def test_shared_nodes_are_leaf_only_value_models() -> None:
    """Real models are DAGs, not trees: some ``(id, rule)`` keys are folded
    from more than one distinct parent (grammar self-reference — the SAME
    parsed node standing in for two positions). A future partitioner must
    duplicate such a node's fold when its parents land in different
    partitions, so the partitioner's COST assumption depends on how big a
    shared subtree can be.

    This pins that every multi-parent key found on the ``think.gbnf``
    witness is an ATOMIC VALUE MODEL — it has no model children of its own —
    so a duplication is never more than one cheap leaf-level ``_channel_once``
    call. If a future grammar/codegen change ever introduces a shared
    INTERIOR node (with model children), this fails loudly instead of the
    duplication silently becoming a mystery slowdown later.
    """
    w = witnesses()[0]  # gbnf:think.gbnf — measured to have real sharing
    fold, model = _build(w)
    recorder = Recorder.wrapping(fold)
    recorder.reduce(model)
    edges = recorder.observed.edges
    shared = {key: owners for key, owners in edges.items() if len(owners) > 1}
    assert shared, f"{w.name}: no shared node found — pick a witness that has one"
    deps = recorder.dependency_graph(model, fold.rule(model))
    for key in shared:
        kids, _node = deps.get(key, ([], None))
        real_kids = [k for k in kids if k in deps]
        assert not real_kids, (
            f"{w.name}: shared node {key} has {len(real_kids)} model children — "
            "sharing is no longer leaf-only, the partitioner's cost bound is stale"
        )
