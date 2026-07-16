"""GrammarModel: base class for all generated Pydantic models."""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any, Callable, ClassVar, Optional, cast

from pydantic import BaseModel, GetCoreSchemaHandler
from pydantic.main import IncEx
from pydantic_core import CoreSchema, core_schema
from pydantic_core.core_schema import SerializationInfo

from lexic.grammars import get_flavour
from lexic.ir.bind import IrBind
from lexic.ir.nodes import IrLiteral, IrRule, IrSequence


def _joint_dump(model: BaseModel, info: SerializationInfo) -> Any:
    """Serialize a joint-nested model by delegating to its own ``model_dump``.

    A schema joint is opaque to pydantic-core, so serialization crosses into
    Python once per joint (once per stride levels, never per level) and
    re-enters the nested model's own — again Rust-driven — dump with the
    caller's options threaded through.

    :param model: The nested model behind the joint.
    :param info: The outer serializer's options.
    :returns: The nested model's dump under those options.
    """
    # ``SerializationInfo`` types include/exclude with the callable-admitting
    # form, but everything reaching a joint came through a ``model_dump``
    # entry, which only accepts ``IncEx`` — the cast narrows to that reality.
    return model.model_dump(
        mode=info.mode,
        include=cast(Optional[IncEx], info.include),
        exclude=cast(Optional[IncEx], info.exclude),
        by_alias=info.by_alias,
        exclude_unset=info.exclude_unset,
        exclude_defaults=info.exclude_defaults,
        exclude_none=info.exclude_none,
        round_trip=info.round_trip,
    )


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
    __schema_joint__: ClassVar[bool] = False

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler, /
    ) -> CoreSchema:
        """The core schema — shallow at expansion joints, default elsewhere.

        pydantic inlines a completed sub-model's whole core schema into its
        referrer (definition-refs are kept only for recursive models), so a
        long acyclic ref chain of generated classes builds a chain-deep
        schema and pydantic's own recursive schema walks overflow near ~450
        rules. Codegen flags every stride-th class along a chain with
        ``__schema_joint__`` (see ``lexic.codegen.binding._schema_joints``);
        a *completed* joint presents a shallow validate-through-the-class
        schema instead, bounding every inlined schema — and each dump's
        Python crossings — by the stride. The class's own schema build (not
        yet complete) and every non-joint class take the default path, so
        grammars shallower than one stride are untouched.
        """
        if cls.__dict__.get("__schema_joint__", False) and cls.__dict__.get(
            "__pydantic_complete__", False
        ):
            return core_schema.no_info_plain_validator_function(
                cls.model_validate,
                serialization=core_schema.plain_serializer_function_ser_schema(
                    _joint_dump,
                    info_arg=True,
                    return_schema=core_schema.any_schema(),
                ),
            )
        return handler(source_type)

    @classmethod
    def bound_fields(cls) -> dict[int, tuple[str, IrBind]]:
        """Item slot → ``(field name, bind)`` from the fields' metadata.

        The neutral accessor onto a class's field bindings — shared by
        :meth:`to_text`/:meth:`semantic_dump` and by external consumers (e.g.
        viz) that need the same slot → field mapping without reading pydantic
        internals directly.

        :returns: Item slot to ``(field name, bind)``, one entry per bound field.
        """
        bound: dict[int, tuple[str, IrBind]] = {}
        for name, info in cls.model_fields.items():
            for meta in info.metadata:
                if isinstance(meta, IrBind):
                    bound[meta.item] = (name, meta)
        return bound

    def to_text(self) -> str:
        """Emit source text for this model instance.

        Walks an explicit work-stack rather than recursing into nested
        models, so emission is stack-safe at any nesting depth. Each stack
        entry is either resolved text or an unexpanded field value; a model
        is expanded via :meth:`_emit_parts`, preserving pre-order output.
        """
        out: list[str] = []
        stack: list[object] = [self]
        while stack:
            node = stack.pop()
            if isinstance(node, str):
                out.append(node)
            elif isinstance(node, GrammarModel):
                stack.extend(reversed(GrammarModel._emit_parts(node)))
            elif isinstance(node, list):
                stack.extend(reversed(node))
            else:
                out.append(str(node))
        return "".join(out)

    def _emit_parts(self) -> list[object]:
        """This model's own emission items, deferring nested values.

        Returns the ordered items :meth:`to_text` would emit for this model
        alone — literal strings for unbound literals, and each bound field's
        value (str, model, or list) left unexpanded for the walker to
        resolve. Mirrors ``to_text``'s per-item logic without recursing.

        :returns: The ordered emission items for this model.
        :raises NotImplementedError: On an abstract alternation class (no
            fields at all); call ``to_text`` on the concrete arm instead.
        """
        binds = self.bound_fields()
        if not binds:
            if any(name == "value" for name in type(self).model_fields.keys()):
                return [str(getattr(self, "value", ""))]
            raise NotImplementedError(
                f"to_text() is undefined on abstract alternation class "
                f"{type(self).__name__}; call it on a concrete arm instance."
            )
        body = self.__grammar__.body
        values = {slot: getattr(self, name, None) for slot, (name, _b) in binds.items()}
        if any(not arm for arm in body) and all(v is None for v in values.values()):
            return []  # the rule's empty alternate arm matched — no field set
        arm = next((a for a in body if a), IrSequence())
        parts: list[object] = []
        for slot, item in enumerate(arm):
            if slot in binds:
                value = values[slot]
                if value is not None:
                    parts.append(value)
            elif isinstance(item.atom, IrLiteral):
                parts.append(str(item.atom))
        return parts

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
            name for name, bind in self.bound_fields().values() if not bind.semantic
        }
        return self.model_dump(exclude=exclude)
