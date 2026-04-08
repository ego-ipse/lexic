"""GBNFModelBuilder — derives Pydantic BaseModel subclasses from GBNF grammar.

No target-language knowledge lives here. Sigils, dispatch tables, and Vyx-
specific base classes are all absent. One plain BaseModel subclass per rule.

Charclass repetitions ([a-z]+) produce str fields for ergonomics.
Non-charclass repetitions produce list[...] fields.
"""

from __future__ import annotations

from typing import Any, Literal

from ogbnf import (
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
)
from pydantic import BaseModel, Field, create_model


class GBNFModelBuilder:
    """Compiles a GBNF grammar into a registry of BaseModel subclasses.

    Usage::

        grammar = Path("grammar.gbnf").read_text()
        rules   = GBNFParser().parse(grammar)
        models  = GBNFModelBuilder(rules).build()
        schema  = models["packet"].model_json_schema()
    """

    def __init__(self, rules: dict[str, GBNFNode]) -> None:
        self._rules = rules
        self._registry: dict[str, type[BaseModel]] = {}

    @classmethod
    def from_grammar(cls, grammar: str) -> GBNFModelBuilder:
        return cls(GBNFParser().parse(grammar))

    def build(self) -> dict[str, type[BaseModel]]:
        for name in self._rules:
            if name not in self._registry:
                self._build(name)
        return self._registry

    # ------------------------------------------------------------------
    # GBNFNode → Python type annotation
    # ------------------------------------------------------------------

    def _python_type(self, node: GBNFNode) -> Any:
        match node:
            case GBNFLiteral(values=values) if values:
                if len(values) == 1:
                    return Literal[values[0]]  # type: ignore[misc]
                return Literal[values]  # type: ignore[misc]

            case GBNFAlternation(arms=arms):
                if all(isinstance(a, GBNFLiteral) for a in arms):
                    vals: tuple[str, ...] = tuple(
                        v for a in arms for v in a.values  # type: ignore[union-attr]
                    )
                    return Literal[vals]  # type: ignore[misc]
                types = [self._python_type(a) for a in arms]
                result = types[0]
                for t in types[1:]:
                    result = result | t
                return result

            case GBNFRepetition(element=el):
                # Charclass repetitions → str (joining chars is always intended)
                if isinstance(el, GBNFCharClass):
                    return str
                return list[self._python_type(el)]  # type: ignore[misc]

            case GBNFOptional(element=el):
                return self._python_type(el) | None

            case GBNFReference(rule=r):
                return self._ref(r)

            case GBNFCharClass():
                return str

            case GBNFSequence():
                fields = self._fields_for(node)
                return create_model("_inline", **fields)

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
                        if isinstance(el.node.element, GBNFCharClass):
                            fields[fname] = (str, Field(..., min_length=el.node.min))
                        else:
                            fields[fname] = (py_type, Field(..., min_length=el.node.min))
                    elif el.required:
                        fields[fname] = (py_type, ...)
                    else:
                        fields[fname] = (py_type, None)
                return fields

            case GBNFRepetition(element=el, min=min_):
                fname = _element_name(el, 0)
                if isinstance(el, GBNFCharClass):
                    f = Field(..., min_length=min_) if min_ > 0 else Field(default="")
                    return {fname: (str, f)}
                inner = self._python_type(el)
                f = (
                    Field(..., min_length=min_)
                    if min_ > 0
                    else Field(default_factory=list)
                )
                return {fname: (list[inner], f)}  # type: ignore[misc]

            case GBNFOptional(element=el):
                return {_element_name(el, 0): (self._python_type(el) | None, None)}

            case GBNFAlternation() | GBNFLiteral() | GBNFCharClass():
                return {"value": (self._python_type(node), ...)}

            case GBNFReference(rule=r):
                return {r.replace("-", "_"): (self._ref(r), ...)}

            case _:
                return {"value": (Any, None)}

    # ------------------------------------------------------------------
    # Rule → model (placeholder handles mutual recursion)
    # ------------------------------------------------------------------

    def _build(self, name: str) -> type[BaseModel]:
        if name in self._registry:
            return self._registry[name]

        self._registry[name] = BaseModel  # placeholder for recursion

        node = self._rules[name]
        fields = self._fields_for(node)
        model = create_model(name, **fields)
        self._registry[name] = model
        return model

    def _ref(self, rule: str) -> type[BaseModel]:
        if rule in self._registry:
            t = self._registry[rule]
            return t if t is not BaseModel else BaseModel
        if rule in self._rules:
            return self._build(rule)
        return BaseModel  # unknown rule — permissive fallback
