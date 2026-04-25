"""Generic IR-construction protocols + HelperRuleRegistry + IRBuilder.

IRBuilder[Node] is parameterised by a RuleClassifier and SequenceConverter
so it contains zero flavour-specific knowledge.
"""

from __future__ import annotations

from typing import Generic, Literal, Protocol, TypeVar

from lexic.ir.atoms import Atom
from lexic.ir.spec import RuleSpec

Node = TypeVar("Node")
Node_contra = TypeVar("Node_contra", contravariant=True)


class RuleClassifier(Protocol[Node]):
    """Determines the IR kind and structure of a single grammar rule node."""

    def rule_name(self, rule: Node) -> str: ...

    def kind(self, rule: Node) -> Literal["sequence", "alternation", "value_str"]: ...

    def alternation_arm_nodes(self, rule: Node) -> list[Node]:
        """For alternation rules: return the stripped arm nodes."""
        ...

    def sequence_body(self, rule: Node) -> Node:
        """For sequence rules: return the body node to convert."""
        ...

    def single_ruleref(self, arm: Node) -> str | None:
        """If arm is a single unquantified rule reference, return its name; else None."""
        ...


class SequenceConverter(Protocol[Node_contra]):
    """Converts flavour AST nodes to IR Atoms + field_map."""

    def value_str_atoms(self, rule: Node_contra) -> list[Atom]:
        """Atoms for a value_str rule (literals/chars/groups only, no rule refs)."""
        ...

    def sequence_atoms(
        self,
        body: Node_contra,
        cls_name: str,
        helpers: "HelperRuleRegistry",
        name_map: dict[str, str],
        parent_of: dict[str, str],
    ) -> tuple[list[Atom], dict[str, int]]:
        """Atoms + field_map for a sequence or alternation-arm body."""
        ...


class HelperRuleRegistry:
    """Accumulates synthesised helper RuleSpecs during IR construction."""

    def __init__(self) -> None:
        self._specs: list[RuleSpec] = []
        self._names: set[str] = set()

    def reserve(self, base_name: str) -> str:
        """Return a unique rule_name without marking it as taken."""
        if base_name not in self._names:
            return base_name
        suffix = 2
        while f"{base_name}{suffix}" in self._names:
            suffix += 1
        return f"{base_name}{suffix}"

    def register(self, spec: RuleSpec) -> None:
        if spec.rule_name in self._names:
            raise ValueError(f"Helper rule {spec.rule_name!r} already registered")
        self._names.add(spec.rule_name)
        self._specs.append(spec)

    def all_specs(self) -> list[RuleSpec]:
        return list(self._specs)


class IRBuilder(Generic[Node]):
    """Generic orchestrator: list[Node] → list[RuleSpec].

    Callers wire: IRBuilder(GbnfClassifier(), GbnfConverter()).build(ast_rules).
    """

    def __init__(
        self,
        classifier: RuleClassifier[Node],
        converter: SequenceConverter[Node],
    ) -> None:
        self._classifier = classifier
        self._converter = converter

    def build(self, rules: list[Node]) -> list[RuleSpec]:
        raise NotImplementedError("Implemented in Task 3")
