"""IRBuilder: converts GBNF AST (list[Rule]) into list[RuleSpec].

Single responsibility: understanding GBNF semantics.
Knows nothing about Lark, Python source, or Pydantic.
"""

from __future__ import annotations

from typing import assert_never

from lexic.codegen.ast_utils import single_ruleref_of
from lexic.codegen.classify import (
    Classifier,
    NamedAlt,
    PureLiteralAlt,
    SequenceKind,
    ValueStr,
)
from lexic.codegen.seq_to_atoms import seq_to_atoms, value_str_to_atoms
from lexic.grammars.gbnf.ast import Alternation, Rule, Sequence
from lexic.ir import AlternationAtom, RuleSpec
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.naming import assign_field_names
from lexic.utils.names import to_pascal

# ── Main builder ─────────────────────────────────────────────────────────────


class IRBuilder:
    """Converts a list of GBNF Rule objects into a list of RuleSpec IR objects.

    Knows nothing about Lark, Python source, or Pydantic.
    """

    def __init__(self, rules: list[Rule]):
        self._rules = rules
        self._rules_dict = {r.name: r for r in rules}
        self._name_map = {r.name: to_pascal(r.name) for r in rules}
        self._helpers = HelperRuleRegistry()
        self._classifier = Classifier()

    def build(self) -> list[RuleSpec]:
        """Build and return specs in grammar order (root first)."""
        parent_of = self._compute_parents()
        primary_specs: list[RuleSpec] = []
        for rule in self._rules:
            primary_specs.extend(self._build_rule(rule, parent_of))
        all_specs = primary_specs + self._helpers.all_specs()
        return self._topo_sort(all_specs)

    def _compute_parents(self) -> dict[str, str]:
        """For each rule that is a named arm of an alternation, record its parent class."""
        parent_of: dict[str, str] = {}
        for rule in self._rules:
            classification = self._classifier.classify(rule)
            if not isinstance(classification, NamedAlt):
                continue
            parent_cls = self._name_map[rule.name]
            for seq in classification.arms:
                ref = single_ruleref_of(seq)
                if ref is not None:
                    parent_of[ref] = parent_cls
        return parent_of

    def _build_value_str(
        self,
        rule: Rule,
        alt: Alternation,
        cls_name: str,
        parent_cls: str,
    ) -> list[RuleSpec]:
        """Build a value_str rule from a ValueStr or PureLiteralAlt classification."""
        return [
            RuleSpec(
                rule_name=rule.name,
                class_name=cls_name,
                parent_class_name=parent_cls,
                kind="value_str",
                items=value_str_to_atoms(alt),
                field_map={},
            )
        ]

    def _build_named_alt(
        self,
        rule: Rule,
        arms: list[Sequence],
        cls_name: str,
        parent_cls: str,
        parent_of: dict[str, str],
    ) -> list[RuleSpec]:
        """Build an alternation rule with named arm variants."""
        arm_rule_names: list[str] = []
        arm_specs: list[RuleSpec] = []

        for arm_idx, stripped in enumerate(arms, start=1):
            ref = single_ruleref_of(stripped)
            if ref is not None:
                arm_rule_names.append(ref)
            else:
                arm_rule_name = f"{rule.name}-arm{arm_idx}"
                arm_cls_name = f"{cls_name}Arm{arm_idx}"
                arm_rule_names.append(arm_rule_name)
                atoms = seq_to_atoms(
                    stripped, arm_cls_name, self._helpers, self._name_map, parent_of
                )
                fm = assign_field_names(atoms)
                arm_specs.append(
                    RuleSpec(
                        rule_name=arm_rule_name,
                        class_name=arm_cls_name,
                        parent_class_name=cls_name,
                        kind="sequence",
                        items=atoms,
                        field_map=fm,
                    )
                )

        abstract_spec = RuleSpec(
            rule_name=rule.name,
            class_name=cls_name,
            parent_class_name=parent_cls,
            kind="alternation",
            items=[AlternationAtom(arm_rule_names=arm_rule_names)],
            field_map={},
        )
        return [abstract_spec] + arm_specs

    def _build_sequence(
        self,
        rule: Rule,
        body: Sequence,
        cls_name: str,
        parent_cls: str,
        parent_of: dict[str, str],
    ) -> list[RuleSpec]:
        """Build a sequence rule from a SequenceKind classification."""
        atoms_seq = seq_to_atoms(
            body, cls_name, self._helpers, self._name_map, parent_of
        )
        fm_seq = assign_field_names(atoms_seq)
        seq_spec = RuleSpec(
            rule_name=rule.name,
            class_name=cls_name,
            parent_class_name=parent_cls,
            kind="sequence",
            items=atoms_seq,
            field_map=fm_seq,
        )
        return [seq_spec]

    def _build_rule(
        self,
        rule: Rule,
        parent_of: dict[str, str],
    ) -> list[RuleSpec]:
        """Build RuleSpec(s) for a GBNF Rule via match-dispatch on classification."""
        cls_name = self._name_map[rule.name]
        parent_cls = parent_of.get(rule.name, "GrammarModel")
        classification = self._classifier.classify(rule)

        match classification:
            case ValueStr(alt=alt) | PureLiteralAlt(alt=alt):
                return self._build_value_str(rule, alt, cls_name, parent_cls)
            case NamedAlt(arms=arms):
                return self._build_named_alt(
                    rule, arms, cls_name, parent_cls, parent_of
                )
            case SequenceKind(body=body):
                return self._build_sequence(rule, body, cls_name, parent_cls, parent_of)
            case _:
                assert_never(classification)

    def _topo_sort(self, specs: list[RuleSpec]) -> list[RuleSpec]:
        """Order specs so parent classes appear before subclasses, with root first."""
        by_cls = {s.class_name: s for s in specs}
        ordered: list[RuleSpec] = []
        visited: set[str] = set()

        def visit(cls_name: str) -> None:
            if cls_name in visited:
                return
            visited.add(cls_name)
            spec = by_cls.get(cls_name)
            if spec and spec.parent_class_name not in ("GrammarModel", "BaseModel"):
                visit(spec.parent_class_name)
            if spec:
                ordered.append(spec)

        # Seed with root first so it always appears at index 0
        root_spec = next((s for s in specs if s.rule_name == "root"), None)
        if root_spec:
            visit(root_spec.class_name)
        for s in specs:
            visit(s.class_name)

        return ordered
