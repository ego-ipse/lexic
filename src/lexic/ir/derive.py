"""derive_specs — IR AST → list[RuleSpec] (the codegen view)."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from functools import cache
from typing import Callable, Literal, TypeAlias, TypeVar

from lexic.ir.action import IrAction, IrReturn
from lexic.ir.naming import CHARCLASS_NAMES, LITERAL_NAMES
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrAtom,
    IrCharClass,
    IrGroup,
    IrItem,
    IrLiteral,
    IrNode,
    IrNone,
    IrNot,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.spec import RuleSpec
from lexic.ir.topo import topo_sort
from lexic.ir.walk import IrTransformer
from lexic.ir.walk_2 import IrVisitor
from lexic.utils.names import to_pascal

# ── classification ────────────────────────────────────────────────────

_HAS_RULEREF: IrVisitor = IrVisitor(
    actions=(IrAction(IrRuleRef, IrReturn(True)),),
)


@cache
def has_ruleref(node: IrNode) -> bool:
    """True if any :class:`IrRuleRef` exists in the node subtree.

    Short-circuits on first hit: the singleton :class:`IrVisitor` carries
    an :class:`IrReturn` body for :class:`IrRuleRef`, which raises a
    control-flow exception caught by :meth:`IrDispatch.apply`. Cached on
    node identity for repeat queries.

    :param node: Root of the subtree to scan.
    :returns: ``True`` if an :class:`IrRuleRef` was found, else ``False``.
    """
    return _HAS_RULEREF.apply(node) is not IrNone


def _non_empty_arms(body: IrAlternation) -> list[IrSequence]:
    """Return the non-empty arms of an alternation."""
    return [a for a in body.arms if a.items]


def classify_kind(rule: IrRule) -> Literal["sequence", "alternation", "value_str"]:
    """Classify a rule's body into one of the three IR kinds.

    - value_str: no IrRuleRef anywhere in the body.
    - alternation: multiple non-empty arms with rulerefs.
    - sequence: single non-empty arm with rulerefs.
    """
    if not has_ruleref(rule.body):
        return "value_str"
    if len(_non_empty_arms(rule.body)) > 1:
        return "alternation"
    return "sequence"


# ── parent inference ──────────────────────────────────────────────────


def _single_unquantified_ruleref(arm: IrSequence) -> str | None:
    """If arm is a single IrItem(IrRuleRef, IrQuantifier(1,1)), return the ref name."""
    if len(arm.items) != 1:
        return None
    item = arm.items[0]
    if not isinstance(item.atom, IrRuleRef):
        return None
    if item.quantifier != IrQuantifier(1, 1):
        return None
    return item.atom.value


def compute_parents(rules: list[IrRule]) -> dict[str, str]:
    """Map rules appearing as single-unquantified-ref alternation arms to
    their alternation's class name.
    """
    parent_of: dict[str, str] = {}
    for rule in rules:
        if classify_kind(rule) != "alternation":
            continue
        parent_cls = to_pascal(rule.name)
        for arm in _non_empty_arms(rule.body):
            ref = _single_unquantified_ruleref(arm)
            if ref is not None:
                parent_of[ref] = parent_cls
    return parent_of


# ── group hoisting ────────────────────────────────────────────────────


def _reserve_helper_name(parent_name: str, taken: set[str]) -> str:
    """Return '<parent_name>-item[N]', the lowest N not already taken."""
    base = f"{parent_name}-item"
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


class _HoistTransformer(IrTransformer):
    """Quantified IrGroup with rulerefs → synthetic helper rule + IrRuleRef.

    Pure-literal groups (no IrRuleRef anywhere) are left intact regardless
    of their quantifier so codegen can treat them as regex patterns.
    """

    def __init__(self, parent_name: str, name_set: set[str]) -> None:
        """Keep your existing visitor logic, but cache the result per node instance"""
        self._parent_name = parent_name
        self._name_set = name_set
        self.helpers: list[IrRule] = []

    def visit_IrItem(self, node: IrItem) -> IrItem:  # pylint: disable=invalid-name
        """Recurse into the atom first so nested groups are processed bottom-up."""
        new_atom = self.visit(node.atom)
        if not isinstance(new_atom, IrGroup):
            if new_atom is node.atom:
                return node
            return IrItem(atom=new_atom, quantifier=node.quantifier)
        is_quantified = node.quantifier != IrQuantifier(1, 1)
        if is_quantified and has_ruleref(new_atom.body):
            helper_name = _reserve_helper_name(self._parent_name, self._name_set)
            self._name_set.add(helper_name)
            self.helpers.append(IrRule(name=helper_name, body=new_atom.body))
            return IrItem(atom=IrRuleRef(helper_name), quantifier=node.quantifier)
        return IrItem(atom=new_atom, quantifier=node.quantifier)


def hoist_helpers(ast: IrAst) -> tuple[IrAst, list[IrRule]]:
    """Rewrite quantified groups containing rulerefs into synthetic rules."""
    name_set: set[str] = {r.name for r in ast.rules}
    helpers: list[IrRule] = []
    new_rules: list[IrRule] = []
    for rule in ast.rules:
        t = _HoistTransformer(parent_name=rule.name, name_set=name_set)
        new_body = t.visit(rule.body)
        helpers.extend(t.helpers)
        new_rules.append(IrRule(rule.name, new_body))
    return IrAst(rules=tuple(new_rules), start=ast.start), helpers


# ── field naming ──────────────────────────────────────────────────────

_A = TypeVar("_A", bound=IrAtom)
_FieldHint: TypeAlias = Callable[[_A], str]


def _bracketed(atom: IrAtom) -> str:
    """Return the bracket-form of a charclass or negated-charclass atom."""
    if isinstance(atom, IrNot) and isinstance(atom.body, IrCharClass):
        return f"[^{atom.body.value}]"
    if isinstance(atom, IrCharClass):
        return f"[{atom.value}]"
    return ""


def _ascii_token(value: str) -> str:
    """Name a literal from its value."""
    return re.sub(r"[^a-zA-Z0-9]", "_", value).strip("_").lower()[:12]


def _sanitize_pattern(pattern: str) -> str:
    inner = re.sub(r"[\[\]\^]", "", pattern)
    inner = inner.replace("-", "_").lower()
    inner = re.sub(r"[^a-z0-9_]", "", inner)
    inner = inner.strip("_")
    inner = re.sub(r"_+", "_", inner)
    if not inner:
        return ""
    if inner[0].isdigit():
        inner = "cc_" + inner
    return inner[:12].strip("_")


# Always returns str (sanitize/fallback literals ensure no None).
# Used only inside _group_hint to name the first child of a literal-only group.
# _group_hint is forward-referenced safely: lambdas evaluate at call time.
_ATOM_HINT: dict[type, _FieldHint] = {
    IrLiteral: lambda a: LITERAL_NAMES.get(a.value) or _ascii_token(a.value) or "lit",
    IrCharClass: lambda a: (
        CHARCLASS_NAMES.get(_bracketed(a)) or _sanitize_pattern(_bracketed(a)) or "cc"
    ),
    IrNot: lambda a: (
        CHARCLASS_NAMES.get(_bracketed(a)) or _sanitize_pattern(_bracketed(a)) or "cc"
    ),
    IrRuleRef: lambda a: a.value.replace("-", "_"),
    # ruleref group → "kind" (structural slot); literal-only group → name from content
    IrGroup: lambda a: "kind" if has_ruleref(a) else _group_hint(a),
}


def _group_hint(group: IrGroup) -> str:
    """Name a literal-only group from the first atom of its first arm."""
    if not (group.body.arms and group.body.arms[0].items):
        return "inline"
    first = group.body.arms[0].items[0].atom
    hint = _ATOM_HINT.get(type(first))
    return hint(first) if hint else "inline"


def _group_field_base(a: IrGroup) -> str | None:
    """Tier-2 name for a group atom, or None → Tier-3 positional fallback."""
    if has_ruleref(a):
        return "kind"
    h = _group_hint(a)
    return h if h not in {"inline", "lit", "cc"} else None


# Returns str | None. None signals no Tier-2 match; _field_map falls through to
# Tier-3 positional naming ("head" / "part_N"). Contrast with _ATOM_HINT which
# always returns str and is used only for naming, never for fallback routing.
FieldBase: TypeAlias = dict[type[_A], Callable[[_A], str | None]]
_FIELD_BASE: FieldBase = {
    IrLiteral: lambda a: LITERAL_NAMES.get(a.value) or _ascii_token(a.value) or "lit",
    IrRuleRef: lambda a: a.value.replace("-", "_"),
    IrCharClass: lambda a: CHARCLASS_NAMES.get(_bracketed(a)),
    IrNot: lambda a: CHARCLASS_NAMES.get(_bracketed(a)),
    IrGroup: _group_field_base,
}


def _field_map(items: Sequence[IrItem]) -> dict[str, int]:
    """Map atoms to Pydantic field names.

    Tier 2 (pattern library): CHARCLASS_NAMES / LITERAL_NAMES lookup.
    Tier 3 (positional): first unmatched pattern field → 'head', rest → 'part_N'.
    Rule-refs keep the rule name. Unquantified IrLiterals produce no field and
    never reach Tier-3; quantified IrLiterals do produce a field via Tier-2.
    """
    result: dict[str, int] = {}
    counts: defaultdict[str, int] = defaultdict(int)
    pattern_pos = 0
    for i, item in enumerate(items):
        atom = item.atom
        if isinstance(atom, IrLiteral) and item.quantifier == IrQuantifier(1, 1):
            continue
        handler = _FIELD_BASE.get(type(atom))
        if handler is None:
            continue
        base = handler(atom)
        if base is None:
            pattern_pos += 1
            base = "head" if pattern_pos == 1 else f"part_{pattern_pos}"
        counts[base] += 1
        result[base if counts[base] == 1 else f"{base}{counts[base]}"] = i
    return result


# ── spec construction ─────────────────────────────────────────────────

# rule → list of NewRuleSpecs for that rule's kind. Each builder consumes the
# rule plus its assigned class name and parent class name.
_KindBuilder: TypeAlias = Callable[[IrRule, str, str], list[RuleSpec]]


def _build_value_str(rule: IrRule, cls_name: str, parent: str) -> list[RuleSpec]:
    """Build a RuleSpec for a value_str rule."""
    arms = _non_empty_arms(rule.body)
    # Multi-arm: place IrAlternation directly; emitters dispatch on
    # isinstance(items[0], IrAlternation). (Decision C.)
    items: list[IrItem | IrAlternation] = (
        [rule.body] if len(arms) > 1 else list(arms[0].items)
    )
    return [RuleSpec(rule.name, cls_name, parent, "value_str", items, {})]


def _build_sequence(rule: IrRule, cls_name: str, parent: str) -> list[RuleSpec]:
    """Build a RuleSpec for a sequence rule."""
    arms = _non_empty_arms(rule.body)
    arm_items = arms[0].items if arms else ()
    items: list[IrItem | IrAlternation] = list(arm_items)
    return [
        RuleSpec(rule.name, cls_name, parent, "sequence", items, _field_map(arm_items))
    ]


def _build_alternation(rule: IrRule, cls_name: str, parent: str) -> list[RuleSpec]:
    """Build a RuleSpec for an alternation rule."""
    arm_names: list[str] = []
    arm_specs: list[RuleSpec] = []
    for idx, arm in enumerate(_non_empty_arms(rule.body), start=1):
        ref = _single_unquantified_ruleref(arm)
        if ref is not None:
            arm_names.append(ref)
            continue
        arm_name = f"{rule.name}-arm{idx}"
        arm_names.append(arm_name)
        arm_items: list[IrItem | IrAlternation] = list(arm.items)
        arm_specs.append(
            RuleSpec(
                arm_name,
                f"{cls_name}Arm{idx}",
                cls_name,
                "sequence",
                arm_items,
                _field_map(arm.items),
            )
        )
    abstract_items: list[IrItem | IrAlternation] = [
        IrItem(atom=IrRuleRef(n)) for n in arm_names
    ]
    abstract = RuleSpec(rule.name, cls_name, parent, "alternation", abstract_items, {})
    return [abstract] + arm_specs


_BUILDERS: dict[str, _KindBuilder] = {
    "value_str": _build_value_str,
    "sequence": _build_sequence,
    "alternation": _build_alternation,
}


# ── non-semantic relaxation ───────────────────────────────────────────


def _is_non_sem_ref(item: IrItem, rules: frozenset[str]) -> bool:
    """Return True if `item` is an IrItem with an IrRuleRef that references a non-semantic rule."""
    return isinstance(item.atom, IrRuleRef) and item.atom.value in rules


def _relax_item(
    item: IrItem | IrAlternation, rules: frozenset[str]
) -> IrItem | IrAlternation:
    """Set min=0 if `item` references a non-semantic rule with min > 0."""
    if (
        isinstance(item, IrItem)
        and _is_non_sem_ref(item, rules)
        and item.quantifier.min > 0
    ):
        return IrItem(item.atom, IrQuantifier(0, item.quantifier.max))
    return item


def _apply_non_semantic(spec: RuleSpec, rules: frozenset[str]) -> RuleSpec:
    """Relax non-semantic ruleref quantifiers and record their field names."""
    if not rules:
        return spec
    new_items = [_relax_item(it, rules) for it in spec.items]
    non_sem = frozenset(
        name
        for name, idx in spec.field_map.items()
        if isinstance((it := new_items[idx]), IrItem) and _is_non_sem_ref(it, rules)
    )
    if new_items == spec.items and non_sem == spec.non_semantic_fields:
        return spec
    return RuleSpec(
        spec.rule_name,
        spec.class_name,
        spec.parent_class_name,
        spec.kind,
        new_items,
        spec.field_map,
        non_sem,
    )


# ── orchestration ─────────────────────────────────────────────────────


def derive_specs(
    ast: IrAst,
    *,
    non_semantic_rules: frozenset[str] = frozenset(),
) -> list[RuleSpec]:
    """Walk the IR AST; produce the codegen RuleSpec view.

    Pure function. No flavour reference.

    Helper rules synthesised by hoist_helpers always receive
    parent_class_name='GrammarModel'; they never participate in
    alternation-arm-driven inheritance (Decision OV #11).
    """
    hoisted, helpers = hoist_helpers(ast)
    rules = list(hoisted.rules) + helpers
    parents = compute_parents(rules)
    names = {r.name: to_pascal(r.name) for r in rules}

    specs: list[RuleSpec] = []
    for rule in rules:
        cls_name = names[rule.name]
        parent = parents.get(rule.name, "GrammarModel")
        specs.extend(_BUILDERS[classify_kind(rule)](rule, cls_name, parent))

    specs = [_apply_non_semantic(s, non_semantic_rules) for s in specs]
    return topo_sort(specs, is_start_rule=lambda s: s.rule_name == ast.start)
