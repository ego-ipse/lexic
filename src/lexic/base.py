"""GrammarModel: base class for all generated Pydantic models."""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any, Callable, ClassVar

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

    @classmethod
    def fast_construct(
        cls,
    ) -> (
        tuple[Callable[[dict[str, Any], set[str]], "GrammarModel"], dict[str, Any]]
        | None
    ):
        """The validation-skip construction licence, or ``None``.

        Granted only when constructing an instance from already-validated
        parts is provably equivalent to the validated constructor: no
        ``model_post_init``, no decorators (validators/serializers/computed
        fields), no ``model_config`` overrides, no private attributes, and
        every optional field defaulting to a plain ``None`` (no factories, no
        mutable defaults).

        :returns: ``(parts constructor, per-class defaults)`` when safe,
            else ``None``.
        """
        if cls.__pydantic_post_init__ is not None or cls.model_config:
            return None
        decorators = cls.__pydantic_decorators__
        if any(getattr(decorators, f.name) for f in dataclass_fields(decorators)):
            return None
        if cls.__private_attributes__:
            return None
        defaults: dict[str, Any] = {}
        for name, info in cls.model_fields.items():
            if info.is_required():
                continue
            if info.default_factory is not None or info.default is not None:
                return None
            defaults[name] = None
        return cls._from_parts, defaults

    @classmethod
    def _from_parts(cls, parts: dict[str, Any], keys: set[str]) -> "GrammarModel":
        """Build an instance directly from validated parts — no field validation.

        The :meth:`fast_construct` licence guarantees equivalence with the
        validated constructor; ``parts`` becomes the instance ``__dict__`` and
        ``keys`` its ``__pydantic_fields_set__`` (both owned by the instance —
        callers must pass fresh objects).

        :param parts: Every field's value, defaults already filled.
        :param keys: The explicitly-set field names (defaults excluded).
        :returns: The constructed instance.
        """
        model = object.__new__(cls)
        object.__setattr__(model, "__dict__", parts)
        object.__setattr__(model, "__pydantic_fields_set__", keys)
        object.__setattr__(model, "__pydantic_extra__", None)
        object.__setattr__(model, "__pydantic_private__", None)
        return model

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
