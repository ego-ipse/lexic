"""Reduce as derived directives — a reducer becomes an ``@lexical`` variant.

A reducer declares what a parse is FOR: ``DROP`` names subtrees the caller
never wants, ``YIELD`` names rules whose value is their own text. This module
turns those declarations into the directive vocabulary the compile pipeline
already has — a derived ``@lexical`` mark set (plus run hoists) whose variant
compilation PRUNES the model the parse builds — and folds the pruned model to
the reducer's value with a thin bridge over the binding view.

Four derived tiers, all read off reducer bodies (never a grammar's name):

- **DROP refful rules** — the value is unused, so the whole subtree may
  collapse to one text node.
- **join-transparent rules** (``IrJoin(IrArgs())`` over text-equivalent
  children) — join is concatenation, so the value IS the span and the body
  evaluates from a one-argument ``[text]`` channel unchanged.
- **channel-free bodies** (constants, ``IrRaise``) — evaluation reads no
  channel; a refusing body refuses at fold time with the same exception.
- **conditional runs** (``r*`` where some arms prove value == text and every
  failing arm has a derivable lead character) — hoisted to a marked
  ``<r>-run`` rule. A poison-free interior contributes its raw text; a
  poisoned one sub-parses under a group-named sub-grammar
  (:func:`sub_grammar`) and contributes the per-element values.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, NamedTuple, cast

from lexic.compile.pipeline.moments import CompileMoments
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrArgs,
    IrAst,
    IrCharClass,
    IrInt,
    IrItem,
    IrJoin,
    IrLiteral,
    IrNone,
    IrNoneType,
    IrQuantifier,
    IrRaise,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
    IrStr,
    IrTuple,
    inline_refs,
)
from lexic.model import GrammarModel
from lexic.parsing.earley.reduce.policy import DROP, KEEP_RAW, YIELD
from lexic.parsing.earley.reduce.reducer import Reducer

_JOIN_ARGS = IrJoin(IrArgs())


class RunSpec(NamedTuple):
    """One hoisted text run — its poison characters and its element rule.

    :ivar poison: Characters whose presence in a run's raw text voids the
        value == text shortcut (each is a failing arm's lead character).
    :ivar element: The repeated rule the run rule wraps.
    """

    poison: frozenset[str]
    element: str


class ReduceDerivation(NamedTuple):
    """What a reducer derives for a grammar — the variant and its marks.

    :ivar variant: The grammar with run hoists applied (pre-inline; apply
        ``inline_refs(canonicalize(variant), marks)`` to obtain the compile
        input, exactly as the ``@lexical`` directive would).
    :ivar marks: The derived ``@lexical`` mark set, run rules included.
    :ivar runs: Run rule name → its :class:`RunSpec`.
    """

    variant: IrAst
    marks: frozenset[str]
    runs: Mapping[str, RunSpec]


class SubRun(NamedTuple):
    """A run's escape hatch — parse the interior, fold its elements.

    :ivar parse: Parses a poisoned interior under the run's sub-grammar.
    :ivar fold: The sub-grammar's own :class:`ReduceFold`.
    """

    parse: Callable[[str], GrammarModel]
    fold: "ReduceFold"


class FoldPlan(NamedTuple):
    """What a derivation hands the fold — marks, runs and their escapes.

    :ivar runs: Marked run rules, by name.
    :ivar subs: Each run's :class:`SubRun` escape hatch.
    :ivar synthetic: Group rules :func:`sub_grammar` named — spliced like
        the hoists they are, never given a body.
    :ivar marks: The ``@lexical`` mark set — rules whose channel is
        licensed to be their span.
    """

    runs: Mapping[str, RunSpec] = {}
    subs: Mapping[str, "SubRun"] = {}
    synthetic: frozenset[str] = frozenset()
    marks: frozenset[str] = frozenset()


# ── the derivation: reducer → mark set + run hoists ───────────────────────


def _dropped(reducer: Reducer, rule: str) -> bool:
    """Whether the reducer's noise policy drops the rule's contribution."""
    return reducer.noise.resolve(IrRuleRef(rule)) is DROP


def _collect_refs(node: Any, out: set[str]) -> None:
    """Accumulate every rule name referenced under ``node``."""
    if isinstance(node, IrRuleRef):
        out.add(str(node))
        return
    for child in node.children():
        _collect_refs(child, out)


def _reach_map(grammar: IrAst) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Per rule: its direct references, and its full reachable closure."""
    refs: dict[str, set[str]] = {}
    for rule in grammar.rules:
        refs[str(rule.name)] = set()
        _collect_refs(rule.body, refs[str(rule.name)])
    reach: dict[str, set[str]] = {}
    for name in refs:
        _reachable(refs, reach, name, frozenset())
    return refs, reach


def _reachable(
    refs: dict[str, set[str]], reach: dict[str, set[str]], name: str, seen: frozenset
) -> set[str]:
    """The transitive reference closure of one rule, memoised into ``reach``."""
    if name in reach:
        return reach[name]
    out = set(refs.get(name, ()))
    for ref in list(out):
        if ref not in seen:
            out |= _reachable(refs, reach, ref, seen | {name})
    reach[name] = out
    return out


def _unbounded(quantifier: IrQuantifier) -> bool:
    """Whether the quantifier has no upper bound (``hi`` is ``IrNone``)."""
    return isinstance(quantifier.hi, IrNoneType)


def _exactly_once(quantifier: IrQuantifier) -> bool:
    """Whether the quantifier is the plain single occurrence."""
    hi = quantifier.hi
    if isinstance(hi, IrNoneType):
        return False
    return int(quantifier.lo) == 1 and int(hi) == 1


def _single_literal(rule: IrRule) -> str | None:
    """The rule's whole language when it is one plain literal, else ``None``."""
    arms = [tuple(arm) for arm in rule.body]
    if len(arms) != 1 or len(arms[0]) != 1:
        return None
    item = arms[0][0]
    if not isinstance(item.atom, IrLiteral) or not _exactly_once(item.quantifier):
        return None
    return str(item.atom)


def _channel_free(body: Any) -> bool:
    """Bodies that evaluate without reading the channel: constants + raises.

    Constants are EXACT value leaves. A node is its payload, so an action
    like ``IrArg(0)`` is itself an ``int`` — an isinstance test would call
    every pass-through a constant and collapse its subtree to text.
    """
    if isinstance(body, IrRaise):
        return True
    return body.__class__ in (IrStr, IrInt) or isinstance(body, IrNoneType)


class _Analysis(NamedTuple):
    """The derivation's working state over one grammar + reducer."""

    rules: dict[str, IrRule]
    refs: dict[str, set[str]]
    reach: dict[str, set[str]]
    equiv: dict[str, bool]


def _analyze(grammar: IrAst, reducer: Reducer) -> _Analysis:
    """Build the analysis: rule tables and the text-equivalence verdicts."""
    rules = {str(rule.name): rule for rule in grammar.rules}
    refs, reach = _reach_map(grammar)
    analysis = _Analysis(rules, refs, reach, {})
    for name in rules:
        _text_equiv(analysis, reducer, name)
    return analysis


def _text_equiv(analysis: _Analysis, reducer: Reducer, name: str) -> bool:
    """Whether the rule's reduced VALUE is provably its matched text."""
    if name in analysis.equiv:
        return analysis.equiv[name]
    analysis.equiv[name] = False  # cycles refuse
    body = reducer.body(IrRuleRef(name))
    if _dropped(reducer, name):
        got = False
    elif body is YIELD:
        got = not any(_dropped(reducer, r) for r in analysis.reach[name])
    elif body.__class__ is IrStr:
        got = _single_literal(analysis.rules[name]) == str(body)
    elif body == _JOIN_ARGS:
        got = _join_transparent(analysis, reducer, name)
    else:
        got = False
    analysis.equiv[name] = got
    return got


def _join_transparent(analysis: _Analysis, reducer: Reducer, name: str) -> bool:
    """``join(args) == text``: every consumed atom is a text-equivalent ref."""
    for arm in analysis.rules[name].body:
        for item in arm:
            if not isinstance(item.atom, IrRuleRef):
                return False
            if not _text_equiv(analysis, reducer, str(item.atom)):
                return False
    return True


def _as_node(node: object) -> IrSelf:
    """The eval protocol's node slot — bodies here only ever ``str()`` it."""
    return cast(IrSelf, node)


class _ProbeNode(NamedTuple):
    """Sample node for body evaluation — ``YIELD`` falls through to ``str()``."""

    text: str

    def __str__(self) -> str:
        return self.text


def _class_sample(rule: IrRule, cap: int = 96) -> list[str]:
    """Sample characters of a single-charclass rule's language."""
    arms = [tuple(arm) for arm in rule.body]
    if len(arms) != 1 or len(arms[0]) != 1:
        return []
    atom = arms[0][0].atom
    if not isinstance(atom, IrCharClass):
        return []
    out: list[str] = []
    for part in atom:
        if isinstance(part, IrRange):
            lo, hi = int(part.lo), int(part.hi)
            out.extend(chr(c) for c in range(lo, min(lo + 48, hi + 1)))
        else:
            out.append(chr(int(part)))
        if len(out) >= cap:
            break
    return out[:cap]


def _arm_ref(arm: IrSequence) -> str | None:
    """The arm's single plain rule ref, when that is all it consists of."""
    items = tuple(arm)
    if len(items) != 1 or not isinstance(items[0].atom, IrRuleRef):
        return None
    if not _exactly_once(items[0].quantifier):
        return None
    return str(items[0].atom)


def _first_char(arm: IrSequence, analysis: _Analysis) -> str | None:
    """The arm's single leading character — the poison a failing arm emits."""
    items = tuple(arm)
    if not items:
        return None
    atom = items[0].atom
    if isinstance(atom, IrLiteral):
        return str(atom)[0]
    if not isinstance(atom, IrRuleRef):
        return None
    rule = analysis.rules.get(str(atom))
    literal = _single_literal(rule) if rule is not None else None
    return literal[0] if literal else None


def _proven_arm(analysis: _Analysis, reducer: Reducer, body: Any, arm) -> bool:
    """Whether the arm's value provably equals its text, by evaluation.

    A single ref to a text-equivalent rule, with the body confirmed over
    sampled one-character channels — the poison probe in miniature.
    """
    ref = _arm_ref(arm)
    if ref is None or not _text_equiv(analysis, reducer, ref):
        return False
    sample = _class_sample(analysis.rules[ref])
    if not sample:
        return False
    return all(
        str(body.eval(reducer, _as_node(_ProbeNode(c)), IrTuple(IrStr(c)))) == c
        for c in sample
    )


def _conditional(
    analysis: _Analysis, reducer: Reducer, name: str
) -> frozenset[str] | None:
    """Poison chars licensing a conditional text run of ``name``, or ``None``.

    Every arm must either prove value == text (:func:`_proven_arm`) or
    contribute a derivable leading poison character.
    """
    body = reducer.body(IrRuleRef(name))
    poison: set[str] = set()
    proven = False
    for arm in analysis.rules[name].body:
        if _proven_arm(analysis, reducer, body, arm):
            proven = True
            continue
        lead = _first_char(arm, analysis)
        if lead is None:
            return None
        poison.add(lead)
    return frozenset(poison) if proven and poison else None


def _run_replacement(
    analysis: _Analysis,
    reducer: Reducer,
    item: IrItem,
    runs: dict[str, RunSpec],
    allowed: frozenset[str] | None,
) -> IrItem | None:
    """A run item's replacement ref (registering its :class:`RunSpec`), or ``None``."""
    if not isinstance(item.atom, IrRuleRef) or not _unbounded(item.quantifier):
        return None
    element = str(item.atom)
    if int(item.quantifier.lo) != 0 or _dropped(reducer, element):
        return None
    run_name = f"{element}-run"
    if allowed is not None and run_name not in allowed:
        return None
    if analysis.equiv[element]:
        poison: frozenset[str] = frozenset()
    else:
        conditional = _conditional(analysis, reducer, element)
        if conditional is None:
            return None
        poison = conditional
    runs[run_name] = RunSpec(poison, element)
    return IrItem(IrRuleRef(run_name))


def _hoist_runs(
    analysis: _Analysis,
    reducer: Reducer,
    rule: IrRule,
    runs: dict[str, RunSpec],
    allowed: frozenset[str] | None,
) -> IrRule:
    """The rule with unbounded text-equivalent/conditional ref runs hoisted."""
    arms = []
    changed = False
    for arm in rule.body:
        items = []
        for item in arm:
            replacement = _run_replacement(analysis, reducer, item, runs, allowed)
            items.append(replacement if replacement is not None else item)
            changed = changed or replacement is not None
        arms.append(IrSequence(*items))
    if not changed:
        return rule
    return IrRule(rule.name, IrAlternation(*arms), rule.semantic)


def _run_rule(run_name: str, element: str) -> IrRule:
    """The hoisted run rule — ``<run_name> ::= <element>*``."""
    body = IrAlternation(
        IrSequence(IrItem(IrRuleRef(element), IrQuantifier(0, IrNone)))
    )
    return IrRule(run_name, body)


def _markable(variant: IrAst, name: str) -> bool:
    """Whether ``inline_refs`` accepts the mark (the ``@lexical`` licence)."""
    try:
        inline_refs(variant, frozenset({name}))
    except UnsupportedConstructError:
        return False
    return True


def derive_reduction(grammar: IrAst, reducer: Reducer) -> ReduceDerivation:
    """Derive the reducer's ``@lexical`` variant of the grammar.

    :param grammar: The canonical source grammar.
    :param reducer: The reducer whose declarations drive the derivation.
    :returns: The variant grammar, its mark set and its run specs. A grammar
        the tiers cannot touch derives an empty mark set — the variant then
        compiles identically and the fold walks the full model.
    """
    analysis = _analyze(grammar, reducer)
    base: set[str] = set()
    for name in analysis.rules:
        if not analysis.refs[name]:
            continue  # ref-free — already value_str, a mark changes nothing
        body = reducer.body(IrRuleRef(name))
        if _dropped(reducer, name) or analysis.equiv[name] or _channel_free(body):
            base.add(name)
    candidates: dict[str, RunSpec] = {}
    trial = IrAst(
        IrSeq(*_variant_rules(analysis, reducer, base, candidates, None)),
        grammar.start,
    )
    runs = {n: s for n, s in candidates.items() if _markable(trial, n)}
    variant = trial
    if len(runs) != len(candidates):  # an unmarkable run keeps its repetition
        runs = {}
        rules = _variant_rules(analysis, reducer, base, runs, frozenset(candidates))
        variant = IrAst(IrSeq(*rules), grammar.start)
    marks = set(runs)
    marks.update(name for name in base if _markable(variant, name))
    return ReduceDerivation(variant, frozenset(marks), runs)


def _variant_rules(
    analysis: _Analysis,
    reducer: Reducer,
    base: set[str],
    runs: dict[str, RunSpec],
    allowed: frozenset[str] | None,
) -> list[IrRule]:
    """The variant's rules, hoisting (and registering) the allowed runs."""
    rules: list[IrRule] = []
    for name, rule in analysis.rules.items():
        if name in base or _dropped(reducer, name):
            rules.append(rule)
            continue
        rules.append(_hoist_runs(analysis, reducer, rule, runs, allowed))
    rules.extend(_run_rule(n, s.element) for n, s in runs.items())
    return rules


def sub_grammar(
    grammar: IrAst, run_name: str, element: str
) -> tuple[IrAst, frozenset[str]]:
    """The run's sub-grammar — the element closure, with groups named.

    The model pipeline may collapse an inner group to a gtext field (raw text
    is all the MODEL product needs), but the reduce channel needs the group's
    interior rule values — so every group becomes a named rule the fold
    splices like the hoist it is.

    :param grammar: The source grammar.
    :param run_name: The run rule's name (becomes the sub-grammar's start).
    :param element: The repeated rule.
    :returns: The sub-grammar AST and its synthetic group-rule names.
    """
    rules = {str(rule.name): rule for rule in grammar.rules}
    _refs, reach = _reach_map(grammar)
    closure = sorted({element} | reach[element])
    named, synthetic = _name_groups(
        [_run_rule(run_name, element), *(rules[n] for n in closure)]
    )
    return IrAst(IrSeq(*named), run_name), synthetic


def _name_groups(rules: list[IrRule]) -> tuple[list[IrRule], frozenset[str]]:
    """Hoist inner alternation groups into named rules."""
    fresh: list[IrRule] = []
    named: list[str] = []
    out = [_name_rule_groups(rule, fresh, named) for rule in rules]
    return out + fresh, frozenset(named)


def _name_rule_groups(rule: IrRule, fresh: list[IrRule], named: list[str]) -> IrRule:
    """One rule with every group item replaced by a fresh named rule's ref."""
    counter = [0]
    arms = [
        IrSequence(*(_name_item(i, str(rule.name), counter, fresh, named) for i in arm))
        for arm in rule.body
    ]
    return IrRule(rule.name, IrAlternation(*arms), rule.semantic)


def _name_item(
    item: IrItem, base: str, counter: list[int], fresh: list[IrRule], named: list[str]
) -> IrItem:
    """The item itself, or its group hoisted under ``<base>-g<n>``."""
    if not isinstance(item.atom, IrAlternation):
        return item
    counter[0] += 1
    name = f"{base}-g{counter[0]}"
    arms = [
        IrSequence(*(_name_item(i, name, counter, fresh, named) for i in arm))
        for arm in item.atom
    ]
    fresh.append(IrRule(name, IrAlternation(*arms)))
    named.append(name)
    return IrItem(IrRuleRef(name), item.quantifier)


# ── the thin fold over the pruned model ───────────────────────────────────


class _YieldNode(NamedTuple):
    """Stand-in node: ``YIELD`` falls through to ``str()``, computed on demand."""

    fold: "ReduceFold"
    model: Any

    def __str__(self) -> str:
        return self.fold.yield_text(self.model)


def _single_arm(rule: IrRule) -> tuple[IrItem, ...] | None:
    """The rule's items when its body is exactly one arm, else ``None``."""
    arms = [tuple(arm) for arm in rule.body]
    return arms[0] if len(arms) == 1 else None


def _slot_map(rule: IrRule) -> dict[int, tuple[str, bool]]:
    """A single-arm rule's item slot → (referenced rule, required)."""
    items = _single_arm(rule) or ()
    return {
        k: (str(item.atom), int(item.quantifier.lo) >= 1)
        for k, item in enumerate(items)
        if isinstance(item.atom, IrRuleRef)
    }


def _opaque_span(rule: IrRule, reducer: Reducer, raw: bool) -> bool:
    """Whether a span-collapsed rule's fused channel cannot be rebuilt from it."""
    refs: set[str] = set()
    _collect_refs(rule.body, refs)
    if raw:
        return bool(refs)
    return any(not _dropped(reducer, ref) for ref in refs)


def _absent(value: Any) -> bool:
    """Whether a field value records no match at all."""
    if value is None or isinstance(value, IrNoneType):
        return True
    return isinstance(value, tuple) and not hasattr(value, "to_text") and not value


def _alt_refs(rule: IrRule) -> tuple[str, ...] | None:
    """The rule's arm refs when EVERY non-empty arm is a single plain ref."""
    arms = [tuple(arm) for arm in rule.body]
    refs = [
        str(arm[0].atom)
        for arm in arms
        if len(arm) == 1 and isinstance(arm[0].atom, IrRuleRef)
    ]
    if refs and len(refs) == len([arm for arm in arms if arm]):
        return tuple(refs)
    return None


class _FoldTables(NamedTuple):
    """The fold's derived views over one variant compilation — one value.

    :ivar rule_of: Model class → the rule it was synthesized for.
    :ivar hoisted: Pipeline-hoisted rules (synthetic group rules included).
    :ivar fields_of: Rule → its bound fields, in source (item) order.
    :ivar text_rules: Rules whose binding kind is ``value_str``.
    :ivar slots: Rule → item slot → (referenced rule, required).
    :ivar arm_items: Rule → its single arm's items (KEEP_RAW item walk).
    :ivar empty_arms: Rules whose body carries an empty alternate arm.
    :ivar alt_arms: Rule → its arm refs when every non-empty arm is one ref.
    :ivar arm_owner: Hoisted arm rule → its owning authored alternation.
    :ivar bodies: Rule → its reduction body.
    :ivar drops: Rules the reducer's noise policy drops.
    :ivar span_opaque: Span-collapsed rules whose channel cannot be rebuilt.
    """

    rule_of: dict[type, str]
    hoisted: frozenset[str]
    fields_of: dict[str, tuple]
    text_rules: frozenset[str]
    slots: dict[str, dict[int, tuple[str, bool]]]
    arm_items: dict[str, tuple[IrItem, ...]]
    empty_arms: frozenset[str]
    alt_arms: dict[str, tuple[str, ...]]
    arm_owner: dict[str, str]
    bodies: dict[str, IrSelf]
    drops: frozenset[str]
    span_opaque: frozenset[str]


def _binding_views(
    moments: CompileMoments,
) -> tuple[dict[type, str], dict[str, tuple], frozenset[str]]:
    """The binding-derived views: class → rule, fields per rule, text rules."""
    names = {b.class_name: b.rule_name for b in moments.binding}
    rule_of = {cls: names[cn] for cn, cls in moments.classes.items() if cn in names}
    fields_of = {
        b.rule_name: tuple(sorted(b.fields.items(), key=lambda p: p[1].item))
        for b in moments.binding
    }
    text_rules = frozenset(
        b.rule_name for b in moments.binding if str(b.kind) == "value_str"
    )
    return rule_of, fields_of, text_rules


def _fold_tables(
    moments: CompileMoments, reducer: Reducer, plan: FoldPlan
) -> _FoldTables:
    """Build every derived view the fold reads — flat, once, up front."""
    rule_of, fields_of, text_rules = _binding_views(moments)
    authored = {str(r.name) for r in moments.grammar.canonical.rules} - plan.synthetic
    codegen = moments.grammar.relaxed
    hoisted = ({str(r.name) for r in codegen.rules} - authored) | plan.synthetic
    alt_arms = {
        str(r.name): refs for r in codegen.rules if (refs := _alt_refs(r)) is not None
    }
    arm_owner = {
        arm: owner
        for owner, arms in alt_arms.items()
        if owner in authored
        for arm in arms
        if arm in hoisted
    }
    every = authored | hoisted
    raw = reducer.literal is KEEP_RAW
    return _FoldTables(
        rule_of=rule_of,
        hoisted=frozenset(hoisted),
        fields_of=fields_of,
        text_rules=text_rules,
        slots={str(r.name): _slot_map(r) for r in codegen.rules},
        arm_items={
            str(r.name): items
            for r in codegen.rules
            if (items := _single_arm(r)) is not None
        },
        empty_arms=frozenset(
            str(r.name) for r in codegen.rules if any(not tuple(a) for a in r.body)
        ),
        alt_arms=alt_arms,
        arm_owner=arm_owner,
        bodies={r: reducer.body(IrRuleRef(r)) for r in every},
        drops=frozenset(r for r in every if _dropped(reducer, r)),
        span_opaque=frozenset(
            str(r.name)
            for r in codegen.rules
            if str(r.name) in text_rules - plan.marks and _opaque_span(r, reducer, raw)
        ),
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
        self.tables = _fold_tables(moments, reducer, plan)
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
        return body.eval(
            self.reducer, _as_node(_YieldNode(self, model)), IrTuple(*parts)
        )

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
        if rule in self.tables.empty_arms and all(_absent(v) for v in values):
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
            if not _exactly_once(item.quantifier):
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
                self.reducer, _as_node(_YieldNode(self, value)), IrTuple(*parts)
            )
            rest = bodies[1:]
        for body in rest:
            reduced = body.eval(
                self.reducer, _as_node(_YieldNode(self, value)), IrTuple(reduced)
            )
        return reduced
