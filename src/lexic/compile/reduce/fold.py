"""Thin-fold execution for a reducer-derived model variant."""

from __future__ import annotations

from typing import Any

from lexic.compile.reduction import (
    DROP,
    KEEP_RAW,
    YIELD,
    CompileMoments,
    FoldPlan,
    GrammarModel,
    IrLiteral,
    IrNoneType,
    IrSelf,
    IrStr,
    IrTuple,
    Reducer,
    UnsupportedConstructError,
    YieldNode,
    absent,
    as_node,
    exactly_once,
    fold_tables,
)


class ReduceFold:
    """The bridge from a directive-pruned model to the reducer's value.

    Channels are rebuilt from the binding view exactly as the reducer defines
    them: source-order fields (``IrBind.item``), group hoists spliced,
    arm hoists folded through their owning alternation, ε-matches of required
    refs occupying their channel positions, pass-through chains re-applying
    bodies by descent, and ``YIELD`` as the emission stream minus DROP
    subtrees. Marked rules contribute their span as a one-argument channel;
    marked runs contribute raw text when poison-free and sub-parse otherwise.
    """

    def __init__(
        self,
        moments: CompileMoments,
        reducer: Reducer,
        plan: FoldPlan = FoldPlan(),
    ) -> None:
        """Bind the fold to one variant compilation.

        :param moments: The variant's compile moments (binding + grammars).
        :param reducer: The reducer whose bodies the fold applies.
        :param plan: The derivation's marks, runs and escapes.
        """
        self.reducer = reducer
        self.plan = plan
        self.raw_literals = reducer.literal is KEEP_RAW
        self.tables = fold_tables(moments, reducer, plan)
        self._channel_cache: dict[tuple[int, str], list[IrSelf]] | None = None

    def reduce(self, model: GrammarModel) -> IrSelf:
        """Fold a parsed variant model to the reducer's value.

        :param model: The variant artefact's parse result.
        :returns: The reduction — whatever the start rule's body builds.
        """
        return self.apply(model, self.rule(model))

    def rule(self, model: Any) -> str:
        """The rule a model node was synthesized for."""
        got = self.tables.rule_of.get(type(model))
        if got is None:
            raise UnsupportedConstructError(
                f"reduce: no rule for model {type(model).__name__!r}"
            )
        return got

    def chain(self, slot_rule: str, child: str) -> list[str]:
        """The pass-through rules between a slot's rule and the child, by descent."""
        if slot_rule == child or slot_rule in self.tables.hoisted:
            return []
        paths: list[tuple[str, ...]] = []
        stack: list[tuple[str, tuple[str, ...], frozenset[str]]] = [
            (slot_rule, (), frozenset())
        ]
        while stack:
            at, trail, seen = stack.pop()
            for arm in self.tables.alt_arms.get(at, ()):
                if arm == child:
                    paths.append(trail)
                elif arm not in seen:
                    stack.append((arm, trail + (arm,), seen | {at}))
        if len(paths) != 1:
            raise UnsupportedConstructError(
                f"reduce: pass-through chain {slot_rule!r} → {child!r} "
                f"resolved {len(paths)} ways"
            )
        return list(reversed(paths[0])) + [slot_rule]

    def apply(self, model: Any, rule: str) -> IrSelf:
        """Evaluate the rule's body over the model's rebuilt channel."""
        body = self.tables.bodies.get(rule, YIELD)
        if body is YIELD:
            return IrStr(self.yield_text(model))
        parts = self.channel(model, rule)
        return body.eval(self.reducer, as_node(YieldNode(self, model)), IrTuple(*parts))

    def yield_text(self, model: Any) -> str:
        """The emission stream minus DROP-rule subtrees."""
        out: list[str] = []
        stack: list[Any] = [model]
        while stack:
            node = stack.pop()
            if isinstance(node, str):
                out.append(node)
            elif hasattr(node, "emit_parts"):
                rule = self.tables.rule_of.get(type(node))
                if rule is None or rule not in self.tables.drops:
                    stack.extend(part for _f, part in reversed(node.emit_parts()))
            elif isinstance(node, (list, tuple)):
                stack.extend(reversed(node))
            elif node is not None:
                out.append(str(node))
        return "".join(out)

    def channel(self, model: Any, rule: str) -> list[IrSelf]:
        """The rule's reduce channel, rebuilt without recursive model descent.

        A surface group expands to several model rules, so a legal grammar
        hundreds of groups deep can exceed Python's recursion limit even when
        every individual compiler pass is iterative. Collect the model nodes
        first and assemble their channels in post-order; nested calls made by
        :meth:`wrapped` then read an already-built child channel.
        """
        key = (id(model), rule)
        if self._channel_cache is not None:
            cached = self._channel_cache.get(key)
            if cached is None:
                # Alternation/pass-through chains can reach a model without a
                # bound edge from the parent currently being assembled. Fill
                # that newly exposed subtree on demand, still post-order.
                self._fill_channels(model, rule)
                cached = self._channel_cache[key]
            return cached

        cache: dict[tuple[int, str], list[IrSelf]] = {}
        self._channel_cache = cache
        try:
            self._fill_channels(model, rule)
            return cache[key]
        finally:
            self._channel_cache = None

    def _fill_channels(self, model: Any, rule: str) -> None:
        """Fill ``model`` and its discoverable descendants into the active cache."""
        assert self._channel_cache is not None
        order: list[tuple[Any, str]] = []
        stack: list[tuple[Any, str]] = [(model, rule)]
        seen: set[tuple[int, str]] = set()
        while stack:
            node, node_rule = stack.pop()
            key = (id(node), node_rule)
            if key in seen or key in self._channel_cache:
                continue
            seen.add(key)
            order.append((node, node_rule))
            fields = self.tables.fields_of.get(node_rule, ())
            for name, _bind in fields:
                stack.extend(self._model_values(getattr(node, name)))
        for node, node_rule in reversed(order):
            key = (id(node), node_rule)
            if key not in self._channel_cache:
                self._channel_cache[key] = self._channel_once(node, node_rule)

    def _model_values(self, value: Any) -> list[tuple[Any, str]]:
        """Model nodes nested in one bound field value, without recursion."""
        out: list[tuple[Any, str]] = []
        pending = [value]
        while pending:
            current = pending.pop()
            if hasattr(current, "to_text"):
                out.append((current, self.rule(current)))
            elif isinstance(current, (list, tuple)):
                pending.extend(reversed(current))
        return out

    def _channel_once(self, model: Any, rule: str) -> list[IrSelf]:
        """Assemble one channel; every model child's channel is already cached."""
        if rule in self.plan.marks:
            return [IrStr(model.value)]  # span-licensed — one text argument
        if rule in self.tables.text_rules:
            return self._terminal_channel(model, rule)
        fields = self.tables.fields_of.get(rule, ())
        values = [getattr(model, name) for name, _bind in fields]
        if rule in self.tables.empty_arms and all(absent(v) for v in values):
            return []  # the empty arm matched — the derivation has no children
        parts: list[IrSelf] = []
        slots = self.tables.slots.get(rule, {})
        if self.raw_literals:
            by_item = {b.item: v for v, (_n, b) in zip(values, fields)}
            self._raw_channel(rule, by_item, slots, parts)
            return parts
        for value, (_name, bind) in zip(values, fields):
            self.contribute(value, slots.get(bind.item), parts)
        return parts

    def _raw_channel(
        self,
        rule: str,
        by_item: dict[int, Any],
        slots: dict[int, tuple[str, bool]],
        parts: list[IrSelf],
    ) -> None:
        """The KEEP_RAW channel — item order, inline literals included."""
        for k, item in enumerate(self.tables.arm_items.get(rule, ())):
            if k in by_item:
                self.contribute(by_item[k], slots.get(k), parts)
                continue
            if not isinstance(item.atom, IrLiteral):
                continue
            if not exactly_once(item.quantifier):
                raise UnsupportedConstructError(
                    f"reduce: rule {rule!r} has an unbound inline literal "
                    "under literal=KEEP_RAW — its occurrence count is not "
                    "recorded by the model"
                )
            parts.extend(IrLiteral(c) for c in str(item.atom))

    def contribute(
        self, value: Any, slot: tuple[str, bool] | None, parts: list[IrSelf]
    ) -> None:
        """One field value's contribution(s) to the channel under assembly."""
        if value is None or isinstance(value, IrNoneType):
            self._contribute_epsilon(slot, parts)
            return
        if isinstance(value, tuple) and not hasattr(value, "to_text"):
            for element in value:
                self.contribute(element, slot, parts)
            return
        if not hasattr(value, "to_text"):
            if self.raw_literals:
                parts.extend(IrLiteral(c) for c in str(value))
            return  # terminal text field — DROP contributes nothing
        rule = self.rule(value)
        if rule in self.plan.runs:
            self._splice_run(value, parts, rule)
            return
        if rule in self.tables.hoisted:
            self._contribute_hoisted(value, rule, slot, parts)
            return
        if rule in self.tables.drops:
            return
        parts.append(self.wrapped(value, rule, rule, slot))

    def _terminal_channel(self, model: Any, rule: str) -> list[IrSelf]:
        """An UNMARKED value_str rule's channel — what its terminals drop or keep.

        Such a rule's consumed atoms are literals, classes and relaxed noise
        refs; the model kept only the span. Under ``literal=DROP`` (and DROP
        noise) the fused channel is empty; under ``KEEP_RAW`` it is one
        ``IrLiteral`` per consumed character — reconstructible only when no
        ref shares the span, so anything else refuses.
        """
        if rule in self.tables.span_opaque:
            raise UnsupportedConstructError(
                f"reduce: rule {rule!r} collapsed to a span but its channel "
                "keeps ref contributions — not reconstructible from text"
            )
        if self.reducer.literal is DROP:
            return []
        return [IrLiteral(c) for c in str(model.value)]

    def _contribute_epsilon(
        self, slot: tuple[str, bool] | None, parts: list[IrSelf]
    ) -> None:
        """An ε-match of a REQUIRED nullable ref still occupies its position."""
        if slot is None or not slot[1] or slot[0] in self.tables.hoisted:
            return
        rule = slot[0]
        if rule in self.tables.drops:
            return
        body = self.tables.bodies[rule]
        if body is YIELD:
            parts.append(IrStr(""))
            return
        parts.append(body.eval(self.reducer, IrStr(""), IrTuple()))

    def _contribute_hoisted(
        self, value: Any, rule: str, slot: tuple[str, bool] | None, parts: list[IrSelf]
    ) -> None:
        """A hoisted rule: groups splice; arms fold through their owner."""
        owner = self.tables.arm_owner.get(rule)
        if owner is None:
            parts.extend(self.channel(value, rule))
            return
        if owner in self.tables.drops:
            return
        parts.append(self.wrapped(value, rule, owner, slot))

    def _splice_run(self, value: Any, parts: list[IrSelf], rule: str) -> None:
        """A marked run: raw text when poison-free, else sub-parse + fold."""
        poison = self.plan.runs[rule].poison
        text = str(value.value)
        if not text:
            return
        if not any(c in text for c in poison):
            parts.append(IrStr(text))
            return
        sub = self.plan.subs[rule]
        parts.extend(sub.fold.channel(sub.parse(text), rule))

    def wrapped(
        self, value: Any, rule: str, body_rule: str, slot: tuple[str, bool] | None
    ) -> IrSelf:
        """The value under every body its chain applies — last ``YIELD`` wins."""
        names = [body_rule] + (self.chain(slot[0], body_rule) if slot else [])
        bodies = [self.tables.bodies[n] for n in names]
        last = max((k for k, b in enumerate(bodies) if b is YIELD), default=-1)
        if last >= 0:
            reduced: IrSelf = IrStr(self.yield_text(value))
            rest = bodies[last + 1 :]
        else:
            parts = self.channel(value, rule)
            reduced = bodies[0].eval(
                self.reducer, as_node(YieldNode(self, value)), IrTuple(*parts)
            )
            rest = bodies[1:]
        for body in rest:
            reduced = body.eval(
                self.reducer, as_node(YieldNode(self, value)), IrTuple(reduced)
            )
        return reduced
