"""IRBuilder — generic orchestrator parameterised by classifier + converter.

Subclass to override per-step behaviour; the default implementation works
for any flavour whose classifier and converter satisfy the protocols.
"""

from __future__ import annotations

from typing import Generator, Generic, TypeVar

from lexic.ir.atoms import (
    AlternationAtom,
    Atom,
    RuleRefAtom,
)
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.naming import assign_field_names
from lexic.ir.protocols import RuleClassifier, SequenceConverter
from lexic.ir.spec import RuleSpec
from lexic.ir.topo import topo_sort
from lexic.utils.names import to_pascal

Node = TypeVar("Node")


class IRBuilder(Generic[Node]):
    """list[Node] → list[RuleSpec]. Wired by a flavour adapter."""

    def __init__(
        self,
        classifier: RuleClassifier[Node],
        converter: SequenceConverter[Node],
        *,
        helpers: HelperRuleRegistry | None = None,
        trivia_rules: frozenset[str] = frozenset({"ws"}),
    ) -> None:
        """Initialise with given classifier and converter, and optional helpers / trivia rules."""
        self._classifier = classifier
        self._converter = converter
        self._helpers = helpers if helpers is not None else HelperRuleRegistry()
        self._trivia_rules = trivia_rules
        self._start_rule_names: frozenset[str] = frozenset()  # populated at build time
        self._name_map: dict[str, str] = {}  # populated at build time

    def _nmap_values(self, rules: list[Node]) -> Generator[str, None, None]:
        """Populate the name map from rule names to class names."""
        for rule in rules:
            yield self._classifier.rule_name(rule)

    @property
    def trivia_rules(self) -> frozenset[str]:
        """The set of rule names the builder treats as trivia (e.g. whitespace)."""
        return self._trivia_rules

    def build(self, rules: list[Node]) -> list[RuleSpec]:
        """Build a list of RuleSpecs from the given list of nodes."""
        self._name_map = {name: to_pascal(name) for name in self._nmap_values(rules)}
        self._start_rule_names = frozenset(
            self._classifier.rule_name(r)
            for r in rules
            if self._classifier.is_start_rule(r)
        )
        parent_of = self._compute_parents(rules)
        primary: list[RuleSpec] = []
        for rule in rules:
            primary.extend(self._build_rule(rule, parent_of))
        all_specs = primary + self._helpers.all_specs()
        all_specs = [self._mark_trivia(s) for s in all_specs]
        return topo_sort(all_specs, is_start_rule=self._is_start_spec)

    # ── overridable steps ────────────────────────────────────────────────

    def _compute_parents(self, rules: list[Node]) -> dict[str, str]:
        """Compute mapping from rule names to parent class names, based on alternation arms."""
        parent_of: dict[str, str] = {}
        for rule in rules:
            if self._classifier.kind(rule) != "alternation":
                continue
            parent_cls = self._name_map[self._classifier.rule_name(rule)]
            for arm in self._classifier.alternation_arm_nodes(rule):
                ref = self._classifier.single_ruleref(arm)
                if ref is not None:
                    parent_of[ref] = parent_cls
        return parent_of

    def _build_rule(self, rule: Node, parents: dict[str, str]) -> list[RuleSpec]:
        """Build RuleSpecs for the given rule, to determine parent classes."""
        name = self._classifier.rule_name(rule)
        cls_name = self._name_map[name]
        parent_cls = parents.get(name, "GrammarModel")
        kind = self._classifier.kind(rule)
        if kind == "value_str":
            return self._build_value_str(rule, cls_name, parent_cls)
        if kind == "alternation":
            return self._build_named_alt(rule, cls_name, parent_cls)
        return self._build_sequence(rule, cls_name, parent_cls)

    def _build_value_str(
        self, rule: Node, cls_name: str, parent_cls: str
    ) -> list[RuleSpec]:
        """Build a value_str RuleSpec for the given rule."""
        body = self._classifier.value_str_body(rule)
        atoms = self._converter.value_str_atoms(body)
        return [
            RuleSpec(
                rule_name=self._classifier.rule_name(rule),
                class_name=cls_name,
                parent_class_name=parent_cls,
                kind="value_str",
                items=atoms,
                field_map={},
            )
        ]

    def _build_named_alt(
        self, rule: Node, cls_name: str, parent_cls: str
    ) -> list[RuleSpec]:
        """Build an alternation RuleSpec (with arms) for the given rule."""
        rule_name = self._classifier.rule_name(rule)
        arms = self._classifier.alternation_arm_nodes(rule)
        arm_rule_names: list[str] = []
        arm_specs: list[RuleSpec] = []
        for idx, arm in enumerate(arms, start=1):
            ref = self._classifier.single_ruleref(arm)
            if ref is not None:
                arm_rule_names.append(ref)
                continue
            arm_rule_name = f"{rule_name}-arm{idx}"
            arm_cls_name = f"{cls_name}Arm{idx}"
            arm_rule_names.append(arm_rule_name)
            atoms = self._converter.sequence_atoms(arm, arm_cls_name, self._helpers)
            arm_specs.append(
                RuleSpec(
                    rule_name=arm_rule_name,
                    class_name=arm_cls_name,
                    parent_class_name=cls_name,
                    kind="sequence",
                    items=atoms,
                    field_map=assign_field_names(atoms),
                )
            )
        abstract = RuleSpec(
            rule_name=rule_name,
            class_name=cls_name,
            parent_class_name=parent_cls,
            kind="alternation",
            items=[AlternationAtom(arm_rule_names=arm_rule_names)],
            field_map={},
        )
        return [abstract] + arm_specs

    def _build_sequence(
        self, rule: Node, cls_name: str, parent_cls: str
    ) -> list[RuleSpec]:
        """Build a sequence RuleSpec for the given rule."""
        body = self._classifier.sequence_body(rule)
        atoms = self._converter.sequence_atoms(body, cls_name, self._helpers)
        return [
            RuleSpec(
                rule_name=self._classifier.rule_name(rule),
                class_name=cls_name,
                parent_class_name=parent_cls,
                kind="sequence",
                items=atoms,
                field_map=assign_field_names(atoms),
            )
        ]

    # ── trivia handling (D2) ────────────────────────────────────────────

    def _mark_trivia(self, spec: RuleSpec) -> RuleSpec:
        """Set min=0 on every trivia-RuleRef and populate non_semantic_fields."""
        new_items: list[Atom] = []
        for atom in spec.items:
            if (
                isinstance(atom, RuleRefAtom)
                and atom.rule_name in self._trivia_rules
                and atom.min > 0
            ):
                new_items.append(RuleRefAtom(atom.rule_name, 0, atom.max))
            else:
                new_items.append(atom)
        non_sem = frozenset(
            name
            for name, idx in spec.field_map.items()
            if isinstance(atom := new_items[idx], RuleRefAtom)
            and atom.rule_name in self._trivia_rules
        )
        if new_items == spec.items and non_sem == spec.non_semantic_fields:
            return spec
        return RuleSpec(
            rule_name=spec.rule_name,
            class_name=spec.class_name,
            parent_class_name=spec.parent_class_name,
            kind=spec.kind,
            items=new_items,
            field_map=spec.field_map,
            non_semantic_fields=non_sem,
        )

    def _is_start_spec(self, spec: RuleSpec) -> bool:
        """Determine if the given RuleSpec is a start rule, for topo sorting.

        Default: a spec is the start if its rule_name matches the first input rule.
        Subclasses may override; flavour classifiers may also expose is_start_rule
        at the AST level — but by build-time we operate on RuleSpecs.
        """
        return spec.rule_name in self._start_rule_names
