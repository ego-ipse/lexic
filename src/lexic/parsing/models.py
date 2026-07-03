"""Instance-parsing bridge — RuleSpecs + generated classes → engine-ready parser.

Replaces the Lark ``build_lark``/``build_transformer`` pair: an instance
grammar is reconstituted from the derived :class:`~lexic.ir.spec.RuleSpec`
list and parsed by :mod:`lexic.parsing`; :class:`ModelFold` folds the
resulting :class:`~lexic.parsing.forest.ParseTree` into generated model
instances.

Design:

- :func:`specs_to_grammar` wraps every field-bearing item of a sequence rule
  in a dedicated wrapper rule (``<rule>--f<idx>``), so each field's extent is
  a structural subtree — no positional char-boundary guessing. Unquantified
  literals stay inline (no field). Optional refs to nullable rules are lifted
  ``R? → R`` (language-preserving; removes empty-span ambiguity and matches
  the Lark path's "empty match is present" output).
- :class:`ModelFold` walks the tree bottom-up on an explicit stack
  (depth-safe): user rules build models per ``spec.kind``; wrapper rules
  yield joined text (terminal fields, ``""`` when empty), optional-group
  text (``None`` when absent), or collected sub-models; synthetic
  (normalize) layers are transparent. The runtime mirror of
  :class:`~lexic.parsing.reduce.Reducer` — its outputs are model
  instances, so it lives outside the IrSelf dispatch algebra.
- Instance parsing runs :func:`~lexic.parsing.parse_first` (deterministic
  first derivation — Lark ``ambiguity="resolve"`` parity; e.g. json_ws's
  ``int`` is genuinely ambiguous).
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
from lexic.parsing.forest import ParseTree
from lexic.parsing.normalize import normalize

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


def _specs_to_rules(
    specs: list[RuleSpec], wrappers: dict[str, tuple[str, int]]
) -> list[IrRule]:
    """Instance-grammar rules from derived specs; fills ``wrappers``.

    Sequence rules get one wrapper rule per field-bearing item; value_str
    rules reconstitute via ``RuleSpec.to_ir_rule``; alternation rules get a
    real multi-arm body (``to_ir_rule`` folds arms into one sequence — the
    wrong shape for this kind).

    :raises UnsupportedConstructError: a user rule name collides with a
        wrapper name.
    """
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
            wrappers[wname] = (mode, int(item.quantifier.lo))
            rules.append(IrRule(wname, IrAlternation(IrSequence(item))))
            body.append(IrItem(IrRuleRef(wname)))
        rules.append(IrRule(spec.rule_name, IrAlternation(IrSequence(*body))))
    return _lift_optional_nullables(rules)


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
    """Bottom-up ParseTree → model-instance fold over per-grammar tables.

    The runtime mirror of :class:`~lexic.parsing.reduce.Reducer`: same
    explicit-stack discipline, but the outputs are generated model instances
    rather than IR nodes, so it lives outside the IrSelf dispatch algebra.

    :ivar specs: rule name → its RuleSpec.
    :ivar classes: class name → generated model class.
    :ivar wrappers: wrapper rule name → (mode, lo) — fold behavior.
    """

    __slots__ = ("specs", "classes", "wrappers")

    def __init__(self, specs: list[RuleSpec], classes: dict[str, type]) -> None:
        self.specs = {s.rule_name: s for s in specs}
        self.classes = classes
        self.wrappers: dict[str, tuple[str, int]] = {}

    @classmethod
    def for_specs(
        cls, specs: list[RuleSpec], classes: dict[str, type], start: str
    ) -> tuple[IrAst, "ModelFold"]:
        """Build the normalized instance grammar and its configured fold."""
        fold = cls(specs, classes)
        rules = _specs_to_rules(specs, fold.wrappers)
        return normalize(IrAst(rules=IrSeq(*rules), start=start)), fold

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
        wrapper = self.wrappers.get(name)
        if wrapper is not None:
            results[id(node)] = self._fold_wrapper(node, wrapper, results)
            return
        spec = self.specs.get(name)
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
        cls = self.classes.get(spec.class_name)
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
    return ModelFold.for_specs(specs, classes, start)
