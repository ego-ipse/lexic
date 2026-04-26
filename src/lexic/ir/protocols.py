"""IR-construction Protocols, FlavourAdapter Protocol, and handler type aliases.

Type-only.  No runtime classes live here — HelperRuleRegistry is in
`lexic.ir.helpers`; IRBuilder is in `lexic.ir.builder`; FlavourEmitter ABC
is in `lexic.ir.emit`; EscapeCodec ABC is in `lexic.ir.escapes`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Literal, Protocol, TypeVar

from lexic.ir.atoms import Atom
from lexic.ir.emit import FlavourEmitter
from lexic.ir.escapes import EscapeCodec
from lexic.ir.spec import RuleSpec

if TYPE_CHECKING:
    from lexic.ir.helpers import HelperRuleRegistry

Node = TypeVar("Node")
Node_contra = TypeVar("Node_contra", contravariant=True)


class RuleClassifier(Protocol[Node]):
    """AST-shape queries on a single rule node.

    Implementations live next to their grammar's AST (e.g. grammars/gbnf/ast_to_ir.py).
    The generic IRBuilder receives one of these and calls the methods below to
    extract the information it needs without knowing the AST node type.
    """

    def rule_name(self, rule: Node) -> str:
        """Return the grammar rule name used as the dict key and class-name seed."""
        raise NotImplementedError("To be done")

    def is_start_rule(self, rule: Node) -> bool:
        """Return True if this rule is the grammar's start/root rule."""
        raise NotImplementedError("To be done")

    def kind(self, rule: Node) -> Literal["sequence", "alternation", "value_str"]:
        """Classify the rule into one of the three IR kinds."""
        raise NotImplementedError("To be done")

    def alternation_arm_nodes(self, rule: Node) -> list[Node]:
        """For alternation rules: return the list of arm nodes in definition order."""
        raise NotImplementedError("To be done")

    def sequence_body(self, rule: Node) -> Node:
        """For sequence rules: return the body node to pass to SequenceConverter."""
        raise NotImplementedError("To be done")

    def value_str_body(self, rule: Node) -> Node:
        """For value_str rules: return the body node to pass to SequenceConverter."""
        raise NotImplementedError("To be done")

    def single_ruleref(self, arm: Node) -> str | None:
        """If arm is a single unquantified rule reference, return its name; else None."""
        raise NotImplementedError("To be done")


class SequenceConverter(Protocol[Node_contra]):
    """AST → Atom conversion. Flavour supplies AST-shape logic; output is canonical Atoms."""

    def value_str_atoms(self, body: Node_contra) -> list[Atom]:
        """Return atoms for a value_str rule body (literals/chars/groups; no rule refs)."""
        raise NotImplementedError("To be done")

    def sequence_atoms(
        self,
        body: Node_contra,
        parent_class_name: str,
        helpers: HelperRuleRegistry,
    ) -> list[Atom]:
        """Return atoms for a sequence or alternation-arm body."""
        raise NotImplementedError("To be done")


class FlavourParser(Protocol):
    """text → list[RuleSpec]. The intermediate AST is package-internal."""

    def parse(self, text: str) -> list[RuleSpec]:
        """Parse grammar text and return a fully-built list of RuleSpecs."""
        raise NotImplementedError("To be done")

    def trivia_rules(self) -> frozenset[str]:
        """Return the set of rule names that are trivia (whitespace, comments, etc.)."""
        raise NotImplementedError("To be done")


# Per-consumer handler type aliases.
AtomEmitHandler = Callable[[Atom, FlavourEmitter], str]
FieldHandler = Callable[..., object]  # signature finalised in Task 9
LarkHandler = Callable[..., str]  # signature finalised in Task 8
TransformHandler = Callable[..., object]  # signature finalised in Task 8
ToTextHandler = Callable[..., str]  # signature finalised in Task 10


class FlavourAdapter(Protocol):
    """The full adapter surface a flavour package exposes to generic consumers."""

    name: str
    extensions: tuple[str, ...]
    parser: FlavourParser
    emitter: FlavourEmitter
    escapes: EscapeCodec
    supports: frozenset[str]

    field_handlers: dict[type, FieldHandler]
    lark_handlers: dict[type, LarkHandler]
    transform_handlers: dict[type, TransformHandler]
    to_text_handlers: dict[type, ToTextHandler]

    def emit(self, specs: list[RuleSpec]) -> str:
        """Emit a list of RuleSpecs as grammar text; delegates to self.emitter."""
        raise NotImplementedError("To be done")

    def emit_rule(self, spec: RuleSpec) -> str:
        """Emit a single RuleSpec as a grammar rule string; delegates to self.emitter."""
        raise NotImplementedError("To be done")
