"""GrammarModel: base class for all generated Pydantic models."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from lexic.grammars import get_flavour
from lexic.ir.bind import IrBind
from lexic.ir.nodes import IrLiteral, IrRule, IrSequence


class GrammarModel(BaseModel):
    """Abstract base for all generated grammar model classes.

    Each subclass carries ``__grammar__: ClassVar[IrRule]`` — its rule from
    the codegen grammar — and every bound field an :class:`IrBind` in its
    ``Annotated`` metadata tying it to an item slot of that rule's sequence
    arm.

    ``to_text()`` walks the arm's items in order: a bound slot emits its
    field's value, an unbound ``IrLiteral`` emits itself, anything else is
    structural and silent. A ``value_str`` class (the implicit ``value``
    field, no binds) emits its value; an abstract alternation class (no
    fields at all) has no ``to_text`` of its own.
    """

    __grammar__: ClassVar[IrRule]

    @classmethod
    def _bound_fields(cls) -> dict[int, tuple[str, IrBind]]:
        """Item slot → ``(field name, bind)`` from the fields' metadata."""
        bound: dict[int, tuple[str, IrBind]] = {}
        for name, info in cls.model_fields.items():
            for meta in info.metadata:
                if isinstance(meta, IrBind):
                    bound[meta.item] = (name, meta)
        return bound

    def to_text(self) -> str:
        """Emit source text for this model instance."""
        binds = self._bound_fields()
        if not binds:
            if any(name == "value" for name in type(self).model_fields.keys()):
                return str(getattr(self, "value", ""))
            raise NotImplementedError(
                f"to_text() is undefined on abstract alternation class "
                f"{type(self).__name__}; call it on a concrete arm instance."
            )
        body = self.__grammar__.body
        values = {slot: getattr(self, name, None) for slot, (name, _b) in binds.items()}
        if any(not arm for arm in body) and all(v is None for v in values.values()):
            return ""  # the rule's empty alternate arm matched — no field set
        arm = next((a for a in body if a), IrSequence())
        parts: list[str] = []
        for slot, item in enumerate(arm):
            if slot in binds:
                value = values[slot]
                if value is not None:
                    parts.append(_field_text(value))
            elif isinstance(item.atom, IrLiteral):
                parts.append(str(item.atom))
        return "".join(parts)

    def to_grammar(self, flavour: str = "gbnf") -> str:
        """Emit this model's rule as grammar text in the given flavour."""
        return str(get_flavour(flavour).apply(self.__grammar__))

    def semantic_dump(self) -> dict[str, Any]:
        """Dump only semantic fields (binds with ``semantic=False`` excluded)."""
        exclude = {
            name for name, bind in self._bound_fields().values() if not bind.semantic
        }
        return self.model_dump(exclude=exclude)


def _field_text(value: object) -> str:
    """One field value's text: recurse into models, join lists, else str."""
    if isinstance(value, list):
        return "".join(_field_text(v) for v in value)
    if isinstance(value, GrammarModel):
        return value.to_text()
    return str(value)
