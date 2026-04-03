"""GBNFModelBuilder — derives everything from the grammar.

No Vyx-specific knowledge lives here. Sigils, field types, and the
dispatch table all come from reading the grammar IR.

Three exported capabilities:

1. build() → dict[str, type[VyxBase]]
   One Pydantic model per grammar rule. Field types mirror the rule
   structure. SIGIL is set from the rule's first fixed literal.

2. dispatch_table(rule) → dict[str, str]
   For alternation rules (like body-line), returns the mapping
   {first_literal → rule_name}. Used by the parser to dispatch
   without any hardcoded Vyx knowledge.

3. rebuild(grammar) → fresh registry
   For !H L4 grammar mutations. Old registry untouched.

The resulting models:
    • are the only representation of Vyx node types
    • expose model_json_schema() for constrained generation
    • are validated by pydantic-ai on provider output
    • are navigated via VyxBase.__getitem__ using registered sigils
"""

from __future__ import annotations

from typing import Any, Literal

from base import VyxBase
from gbnf import (
    GBNFAlternation,
    GBNFCharClass,
    GBNFLiteral,
    GBNFNode,
    GBNFOptional,
    GBNFParser,
    GBNFReference,
    GBNFRepetition,
    GBNFSequence,
    _element_name,
    first_terminal,
)
from gbnf import (
    dispatch_table as _gbnf_dispatch_table,
)
from pydantic import Field, create_model

# ------------------------------------------------------------------
# GBNFModelBuilder
# ------------------------------------------------------------------


class GBNFModelBuilder:
    """Compiles a GBNF grammar into a registry of VyxBase subclasses.

    Usage::

        grammar   = Path("grammar.gbnf").read_text()
        registry  = GBNFModelBuilder.from_grammar(grammar).build()

        # JSON Schema for llama.cpp / pydantic-ai
        schema = registry["packet"].model_json_schema()

        # Dispatch table for the parser
        table = GBNFModelBuilder(rules).dispatch_table("body-line")
        # → {"\\\\": "nl-escape", "# ": "nl-force", "$": "table-block", ...}

        # Rebuild after !H L4 grammar mutation
        new_registry = builder.rebuild(new_grammar)
    """

    def __init__(self, rules: dict[str, GBNFNode]) -> None:
        self._rules = rules
        self._registry: dict[str, type[VyxBase]] = {}

    @classmethod
    def from_grammar(cls, grammar: str) -> GBNFModelBuilder:
        return cls(GBNFParser().parse(grammar))

    def build(self) -> dict[str, type[VyxBase]]:
        """Build all models and return the registry."""
        for name in self._rules:
            if name not in self._registry:
                self._build(name)
        return self._registry

    def rebuild(self, grammar: str) -> dict[str, type[VyxBase]]:
        """Return a fresh registry from an updated grammar.

        The existing registry is untouched. Caller swaps it in at the
        next !W boundary after !H L4 resolution.
        """
        return GBNFModelBuilder.from_grammar(grammar).build()

    # ------------------------------------------------------------------
    # Dispatch table — grammar-derived, no hardcoded Vyx knowledge
    # ------------------------------------------------------------------

    def dispatch_table(self, rule: str) -> dict[str, str]:
        """Return {first_literal: rule_name} for an alternation rule.

        Delegates to gbnf.dispatch_table — pure Python, no pydantic.
        """
        return _gbnf_dispatch_table(self._rules, rule)

    # ------------------------------------------------------------------
    # Core: GBNFNode → Python type
    # ------------------------------------------------------------------

    def _python_type(self, node: GBNFNode) -> Any:
        match node:
            case GBNFLiteral(values=values) if values:
                if len(values) == 1:
                    return Literal[values[0]]  # type: ignore[misc]
                return Literal[values]  # type: ignore[misc]

            case GBNFAlternation(arms=arms):
                # All-terminal alternation → single Literal type
                if all(isinstance(a, GBNFLiteral) for a in arms):
                    vals: tuple[str, ...] = tuple(
                        v
                        for a in arms
                        for v in a.values  # type: ignore[union-attr]
                    )
                    return Literal[vals]  # type: ignore[misc]
                # Mixed arms → Union
                types = [self._python_type(a) for a in arms]
                result = types[0]
                for t in types[1:]:
                    result = result | t
                return result

            case GBNFRepetition(element=el):
                return list[self._python_type(el)]

            case GBNFOptional(element=el):
                return self._python_type(el) | None

            case GBNFReference(rule=r):
                return self._ref(r)

            case GBNFCharClass():
                return str

            case GBNFSequence():
                # Inline anonymous model for nested sequences
                fields = self._fields_for(node)
                return create_model("_inline", __base__=VyxBase, **fields)

            case _:
                return Any

    # ------------------------------------------------------------------
    # GBNFNode → Pydantic field definitions
    # ------------------------------------------------------------------

    def _fields_for(self, node: GBNFNode) -> dict[str, tuple[type, Any]]:
        match node:
            case GBNFSequence(elements=elements):
                fields: dict[str, tuple[type, Any]] = {}
                seen: dict[str, int] = {}
                for el in elements:
                    base = el.name
                    count = seen.get(base, 0)
                    fname = base if count == 0 else f"{base}_{count}"
                    seen[base] = count + 1
                    py_type = self._python_type(el.node)
                    if isinstance(el.node, GBNFRepetition) and el.node.min > 0:
                        fields[fname] = (py_type, Field(..., min_length=el.node.min))
                    elif el.required:
                        fields[fname] = (py_type, ...)
                    else:
                        fields[fname] = (py_type, None)
                return fields

            case GBNFRepetition(element=el, min=min_):
                inner = self._python_type(el)
                fname = _element_name(el, 0)
                f = (
                    Field(..., min_length=min_)
                    if min_ > 0
                    else Field(default_factory=list)
                )
                return {fname: (list[inner], f)}

            case GBNFOptional(element=el):
                return {
                    _element_name(el, 0): (
                        self._python_type(el) | None,
                        None,
                    )
                }

            case GBNFAlternation() | GBNFLiteral() | GBNFCharClass():
                return {"value": (self._python_type(node), ...)}

            case GBNFReference(rule=r):
                return {r.replace("-", "_"): (self._ref(r), ...)}

            case _:
                return {"value": (Any, None)}

    # ------------------------------------------------------------------
    # Rule → model, placeholder handles mutual recursion
    # ------------------------------------------------------------------

    def _build(self, name: str) -> type[VyxBase]:
        if name in self._registry:
            return self._registry[name]

        # Placeholder breaks recursive / mutually recursive rules
        self._registry[name] = VyxBase

        node = self._rules[name]
        fields = self._fields_for(node)

        # Sigil derived from grammar — never from a hardcoded map
        sigil = first_terminal(self._rules, node)

        model = create_model(name, __base__=VyxBase, **fields)
        model.SIGIL = sigil
        if sigil:
            VyxBase._sigil_registry[sigil] = model

        self._registry[name] = model
        return model

    def _ref(self, rule: str) -> type[VyxBase]:
        if rule in self._registry:
            t = self._registry[rule]
            return t if t is not VyxBase else VyxBase
        if rule in self._rules:
            return self._build(rule)
        return VyxBase  # unknown rule — permissive fallback
