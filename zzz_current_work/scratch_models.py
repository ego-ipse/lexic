"""SCRATCH — Phase 4 instance-parsing bridge (destined: src/lexic/parsing_2/models.py).

Replaces build_lark + build_transformer: RuleSpecs + generated classes →
(normalized instance IrAst, ModelFold). CompiledGrammar.parse becomes
``fold.apply(parse(grammar, text))``.

Design (see plan Phase 4 + execution log):
- ``specs_to_grammar`` wraps every field-bearing item of a sequence rule in a
  dedicated wrapper rule (``<rule>--f<idx>``), so each field's extent is a
  structural subtree — no positional char-boundary guessing. The quantifier
  moves onto the wrapped item inside the wrapper; the parent references the
  wrapper exactly once. Unquantified literals stay inline (no field).
- ``ModelFold`` walks the ParseTree bottom-up with an explicit stack
  (depth-safe): user rules build model instances per spec.kind; wrapper rules
  yield either joined subtree text (terminal fields) or collected sub-models
  (ref/group fields); synthetic (normalize) nodes are transparent.
- Optional-ref presence is structural (empty wrapper ⇒ absent) — replaces
  build_transformer's isinstance disambiguation.

Smoke: parses every ground-truth grammar's sample corpus and round-trips
text — mirrors tests/integration/test_parse.py + test_full_round_trip.py.
"""

from __future__ import annotations

from typing import Iterator

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNoneType, IrSeq
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.operators import IrNot
from lexic.ir.spec import RuleSpec
from lexic.parsing_2.forest import ParseTree

_WRAP_SEP = "--f"
"""Wrapper-rule name infix: ``<rule>--f<item-index>``."""


def _is_plain_literal(item: IrItem) -> bool:
    """A structural literal — quantifier (1,1), never a field."""
    return isinstance(item.atom, IrLiteral) and item.quantifier == IrQuantifier(1, 1)


def _group_has_ruleref(group: IrAlternation) -> bool:
    """Whether any arm of a group alternation references a rule."""
    return any(
        isinstance(sub.atom, IrRuleRef)
        for arm in group
        for sub in arm
        if isinstance(sub, IrItem)
    )


def _wrapper_mode(item: IrItem) -> str:
    """How a wrapper's content folds: 'text', 'gtext', 'model', or 'models'.

    'text' (terminal atoms) always yields the joined chars — an empty match
    is ``""``, mirroring build_transformer's _consume_terminal. 'gtext'
    (literal-only groups) yields ``None`` when an optional group is absent,
    mirroring _consume_group.
    """
    atom = item.atom
    if isinstance(atom, (IrCharClass, IrNot, IrLiteral)):
        return "text"
    hi = item.quantifier.hi
    many = isinstance(hi, IrNoneType) or int(hi) > 1
    if isinstance(atom, IrRuleRef):
        return "models" if many else "model"
    if isinstance(atom, IrAlternation):
        if _group_has_ruleref(atom):
            return "models" if many else "model"
        return "gtext"
    raise UnsupportedConstructError(
        f"models: no wrapper mode for atom type {type(atom).__name__!r}"
    )


class FoldPlan:
    """Per-grammar fold tables: what each rule name means to the fold.

    :ivar specs: rule name → its RuleSpec.
    :ivar classes: class name → generated model class.
    :ivar wrappers: wrapper rule name → (mode, lo) — fold behavior + emptiness.
    """

    __slots__ = ("specs", "classes", "wrappers")

    def __init__(self, specs: list[RuleSpec], classes: dict[str, type]) -> None:
        self.specs = {s.rule_name: s for s in specs}
        self.classes = classes
        self.wrappers: dict[str, tuple[str, int]] = {}


def _nullable_names(rules: list[IrRule]) -> set[str]:
    """Rule names that can derive the empty string (fixpoint)."""

    def item_nullable(item: IrItem, known: set[str]) -> bool:
        if int(item.quantifier.lo) == 0:
            return True
        atom = item.atom
        if isinstance(atom, IrRuleRef):
            return str(atom) in known
        if isinstance(atom, IrLiteral):
            return not str(atom)
        if isinstance(atom, IrAlternation):
            return any(
                all(item_nullable(i, known) for i in arm if isinstance(i, IrItem))
                for arm in atom
            )
        return False

    known: set[str] = set()
    changed = True
    while changed:
        changed = False
        for rule in rules:
            if str(rule.name) in known:
                continue
            if any(
                all(item_nullable(i, known) for i in arm if isinstance(i, IrItem))
                for arm in rule.body
            ):
                known.add(str(rule.name))
                changed = True
    return known


def _lift_optional_nullables(rules: list[IrRule]) -> list[IrRule]:
    """Rewrite ``R?`` to ``R`` where ``R`` is nullable.

    An optional occurrence of a rule that itself derives empty is genuinely
    ambiguous on the empty span (absent vs empty match) — Lark's
    ``ambiguity="resolve"`` silently collapsed this; the engine raises. The
    lift is language-preserving (``R? == R`` for nullable ``R``) and keeps
    the empty match present, matching the Lark path's observable output.
    """
    nullable = _nullable_names(rules)

    def lift_item(item: IrItem) -> IrItem:
        atom = item.atom
        q = item.quantifier
        if (
            isinstance(atom, IrRuleRef)
            and str(atom) in nullable
            and int(q.lo) == 0
            and not isinstance(q.hi, IrNoneType)
            and int(q.hi) == 1
        ):
            return IrItem(atom, IrQuantifier(1, 1))
        return item

    lifted: list[IrRule] = []
    for rule in rules:
        arms = tuple(
            IrSequence(*(lift_item(i) for i in arm if isinstance(i, IrItem)))
            for arm in rule.body
        )
        lifted.append(IrRule(rule.name, IrAlternation(*arms)))
    return lifted


def specs_to_grammar(
    specs: list[RuleSpec], classes: dict[str, type], start: str
) -> tuple[IrAst, FoldPlan]:
    """Instance grammar + fold plan from derived specs.

    Sequence rules get one wrapper rule per field-bearing item; alternation
    and value_str rules reconstitute via ``RuleSpec.to_ir_rule`` unchanged.

    :raises UnsupportedConstructError: a user rule name collides with a
        wrapper name.
    """
    plan = FoldPlan(specs, classes)
    rules: list[IrRule] = []
    names = {s.rule_name for s in specs}
    for spec in specs:
        if spec.kind == "alternation":
            # to_ir_rule folds arm refs into ONE sequence — wrong shape for
            # alternation kind; build the real multi-arm body here.
            arms = tuple(IrSequence(it) for it in spec.items if isinstance(it, IrItem))
            rules.append(IrRule(spec.rule_name, IrAlternation(*arms)))
            continue
        if spec.kind != "sequence":
            rules.append(spec.to_ir_rule())
            continue
        body: list[IrItem] = []
        for idx, item in enumerate(spec.items):
            if not isinstance(item, IrItem) or _is_plain_literal(item):
                if isinstance(item, IrItem):
                    body.append(item)
                continue
            wname = f"{spec.rule_name}{_WRAP_SEP}{idx}"
            if wname in names:
                raise UnsupportedConstructError(
                    f"models: user rule {wname!r} collides with a wrapper name"
                )
            mode = _wrapper_mode(item)
            plan.wrappers[wname] = (mode, int(item.quantifier.lo))
            rules.append(IrRule(wname, IrAlternation(IrSequence(item))))
            body.append(IrItem(IrRuleRef(wname)))
        rules.append(IrRule(spec.rule_name, IrAlternation(IrSequence(*body))))
    return IrAst(rules=IrSeq(*_lift_optional_nullables(rules)), start=start), plan


def _subtree_text(node: ParseTree | IrLiteral) -> str:
    """All consumed chars under ``node``, in source order (iterative)."""
    parts: list[str] = []
    stack: list = [node]
    while stack:
        k = stack.pop()
        if isinstance(k, ParseTree):
            stack.extend(reversed(k.kids))
        else:
            parts.append(str(k))
    return "".join(parts)


def _direct_models(node: ParseTree, results: dict[int, object]) -> Iterator[object]:
    """Sub-models directly under ``node``, looking through synthetic layers."""
    stack: list = list(reversed(node.kids))
    while stack:
        k = stack.pop()
        if not isinstance(k, ParseTree):
            continue
        if id(k) in results:
            yield results[id(k)]
        else:  # synthetic / non-model layer — descend
            stack.extend(reversed(k.kids))


class ModelFold:
    """Bottom-up ParseTree → model-instance fold, driven by a FoldPlan.

    The runtime mirror of :class:`~lexic.parsing_2.reduce.Reducer`: same
    explicit-stack discipline, but the outputs are generated model instances
    rather than IR nodes, so it lives outside the IrSelf dispatch algebra.
    """

    __slots__ = ("plan",)

    def __init__(self, plan: FoldPlan) -> None:
        self.plan = plan

    def apply(self, root: ParseTree) -> object:
        """Fold the parse tree of a start-rule match into its model."""
        results: dict[int, object] = {}
        stack: list[tuple[ParseTree, bool]] = [(root, False)]
        while stack:
            node, expanded = stack.pop()
            if not expanded:
                stack.append((node, True))
                stack.extend(
                    (k, False)
                    for k in node.kids
                    if isinstance(k, ParseTree) and id(k) not in results
                )
                continue
            self._fold_node(node, results)
        return results[id(root)]

    # ── per-node folding ────────────────────────────────────────────

    def _fold_node(self, node: ParseTree, results: dict[int, object]) -> None:
        name = str(node.symbol)
        wrapper = self.plan.wrappers.get(name)
        if wrapper is not None:
            results[id(node)] = self._fold_wrapper(node, wrapper, results)
            return
        spec = self.plan.specs.get(name)
        if spec is None:
            return  # synthetic — parents look through it
        results[id(node)] = self._fold_rule(node, spec, results)

    def _fold_wrapper(
        self, node: ParseTree, wrapper: tuple[str, int], results: dict[int, object]
    ) -> object:
        mode, lo = wrapper
        if mode == "text":
            return _subtree_text(node)
        if mode == "gtext":
            text = _subtree_text(node)
            return None if (not text and lo == 0) else text
        models = list(_direct_models(node, results))
        if mode == "models":
            return models
        return models[0] if models else None

    def _fold_rule(
        self, node: ParseTree, spec: RuleSpec, results: dict[int, object]
    ) -> object:
        cls = self.plan.classes.get(spec.class_name)
        if cls is None:
            raise UnsupportedConstructError(
                f"models: no class for rule {spec.rule_name!r}"
            )
        if spec.kind == "alternation":
            models = list(_direct_models(node, results))
            return models[0] if models else None
        if spec.kind == "value_str":
            return cls(value=_subtree_text(node))
        if spec.kind == "sequence":
            return self._fold_sequence(node, spec, cls, results)
        raise UnsupportedConstructError(f"models: unknown kind {spec.kind!r}")

    def _fold_sequence(
        self,
        node: ParseTree,
        spec: RuleSpec,
        cls: type,
        results: dict[int, object],
    ) -> object:
        inv = {v: k for k, v in spec.field_map.items()}
        by_index: dict[int, object] = {}
        for kid in node.kids:
            if not isinstance(kid, ParseTree):
                continue  # inline structural-literal chars
            name = str(kid.symbol)
            rule, sep, idx_s = name.rpartition(_WRAP_SEP)
            if sep and rule == spec.rule_name and idx_s.isdigit():
                by_index[int(idx_s)] = results[id(kid)]
        kwargs = {
            fname: by_index[idx]
            for idx, fname in inv.items()
            if idx in by_index and by_index[idx] is not None
        }
        return cls(**kwargs)


def build_instance_parser(
    specs: list[RuleSpec], classes: dict[str, type], start: str
) -> tuple[IrAst, ModelFold]:
    """One-call helper for compile.py: specs → (normalized grammar, fold)."""
    from lexic.parsing_2.normalize import normalize

    grammar, plan = specs_to_grammar(specs, classes, start)
    return normalize(grammar), ModelFold(plan)


def first_tree(grammar: IrAst, text: str) -> ParseTree:
    """The instance path's Lark-parity derivation: first one, deterministic."""
    from lexic.exceptions import UnsupportedConstructError as _U
    from lexic.parsing_2 import derivations, parse

    try:
        return parse(grammar, text)
    except _U as exc:
        if "ambiguous" not in str(exc):
            raise
        return derivations(grammar, text)[0]


if __name__ == "__main__":
    from pathlib import Path

    from lexic.codegen import codegen
    from lexic.compile import compile_grammar
    from lexic.grammars import get_flavour
    from lexic.parsing_2 import parse as e_parse

    SAMPLES = {
        "arithmetic": "1+2=3\n",
        "json_arr": '[\n"a"]',
        "list": "- a\n- b\n",
    }
    for stem, sample in SAMPLES.items():
        path = Path("resources/ground_truth") / f"{stem}.gbnf"
        text = path.read_text(encoding="utf-8")
        start_rule, specs_list = compile_grammar(text, get_flavour("gbnf"))
        classes = codegen(specs_list, stem)
        grammar, fold = build_instance_parser(specs_list, classes, start_rule)
        tree = e_parse(grammar, sample)
        model = fold.apply(tree)
        rt = model.to_text()
        print(
            f"{stem}: parsed={type(model).__name__} roundtrip={'OK' if rt == sample else 'DIFF ' + repr(rt)}"
        )
