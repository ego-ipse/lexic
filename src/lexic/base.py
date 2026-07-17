"""GrammarModel: the record spine every generated model class lives on.

A generated model IS an IR record (ruling 9 / D2 of
``zzz_current_work/260716-ir-native/PLAN_v4.md``): :class:`GrammarModel`
subclasses :class:`~lexic.ir.base.IrNamedTuple`, so instances are immutable
named tuples that join the IR algebra — walkable (:meth:`children` yields the
bound-field values in item order), dispatchable (an ``IrTypeMap``'s
``IrTuple`` entry admits models via the MRO), hashable, and type-aware in
equality (two distinct classes with equal payloads never compare equal).

Each class carries ``__grammar__: ClassVar[IrRule]`` — its rule from the
codegen grammar — and a binds table ``__binds__`` mapping each bound item
slot to ``(field name, IrBind)``. Synthesis writes the table directly; for
classes authored with ``Annotated[..., IrBind(...)]`` field metadata (the
codegen-emitted modules, whose ``from __future__ import annotations`` makes
every annotation a string), :meth:`GrammarModel.bound_fields` resolves the
annotations once and caches the result. That resolution branch and the no-op
:meth:`GrammarModel.model_rebuild` are the emitter shim keeping the old
codegen path green; both die when the runtime-synthesis flip lands.

Construction is trusted (checked construction is a later, separate wiring):
the record builds whatever it is handed, coercing ``models``-mode lists to
tuples (the fold and PDA hand live sink lists; stored raw they would alias
and kill hashability). :meth:`GrammarModel.model_dump` re-emits those tuples
as lists and serializes by RUNTIME type (ruling 12 — never by declared
schema), walking an explicit stack so depth never overflows.
"""

from __future__ import annotations

from typing import Any, Callable, ClassVar, Self, Sequence, cast, get_type_hints

from lexic.grammars import get_flavour
from lexic.ir.base import IrNamedTuple, IrSelf
from lexic.ir.bind import IrBind
from lexic.ir.nodes import IrLiteral, IrRule, IrSequence


def _binds_from_annotations(cls: type[GrammarModel]) -> dict[int, tuple[str, IrBind]]:
    """Resolve a class's ``Annotated`` field metadata into its binds table.

    The emitter-shim half of the binds channel: codegen-emitted modules
    stringize annotations (``from __future__ import annotations``), so the
    ``IrBind`` metadata only exists after annotation resolution. Every name
    an emitted module references is a module-level import, so resolution
    always succeeds there; a hand-authored class using unresolvable local
    names must declare ``__binds__`` directly instead.

    :param cls: The model class whose annotations carry the binds.
    :returns: Item slot → ``(field name, bind)``, one entry per bound field.
    """
    hints = get_type_hints(cls, include_extras=True)
    binds: dict[int, tuple[str, IrBind]] = {}
    for name in cls._fields:
        for meta in getattr(hints.get(name), "__metadata__", ()):
            if isinstance(meta, IrBind):
                binds[meta.item] = (name, meta)
    return binds


def _child_attrs_of(binds: dict[int, tuple[str, IrBind]]) -> tuple[str, ...]:
    """The bound field names in item order — the ``_child_attrs`` payload."""
    return tuple(name for _slot, (name, _bind) in sorted(binds.items()))


def _dump_value(
    value: object, stack: list[tuple[GrammarModel, dict[str, Any]]]
) -> object:
    """One dump slot: models defer to the stack, tuples re-emit as lists.

    A nested model contributes an (initially empty) dict placeholder and a
    stack entry that fills it later — model nesting rides the explicit stack,
    so depth is unbounded. Tuple nesting recurses (it is structurally
    bounded: a ``models`` field is one tuple layer of sub-models).

    :param value: The field value to serialize.
    :param stack: The dump work stack nested models are deferred onto.
    :returns: The serialized slot value.
    """
    if isinstance(value, GrammarModel):
        sub: dict[str, Any] = {}
        stack.append((value, sub))
        return sub
    if isinstance(value, tuple):
        return [_dump_value(element, stack) for element in value]
    return value


class GrammarModel(IrNamedTuple):
    """Abstract base for all generated grammar model classes.

    Each subclass carries ``__grammar__: ClassVar[IrRule]`` — its rule from
    the codegen grammar — and a binds table tying every bound field to a
    positional item slot of that rule's sequence arm (``__binds__`` directly,
    or resolved once from ``Annotated`` ``IrBind`` metadata).

    ``to_text()`` walks the arm's items in order: a bound slot emits its
    field's value, an unbound ``IrLiteral`` emits itself, anything else is
    structural and silent. A ``value_str`` class (the implicit ``value``
    field, no binds) emits its value; an abstract alternation class (no
    fields at all) has no ``to_text`` of its own.
    """

    __grammar__: ClassVar[IrRule]
    __binds__: ClassVar[dict[int, tuple[str, IrBind]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Derive ``_child_attrs`` from an explicitly declared binds table.

        A class that ships its own ``__binds__`` (runtime synthesis, or a
        hand-authored model) gets ``_child_attrs`` = bound fields in item
        order immediately; the ``Annotated`` shim path sets both lazily in
        :meth:`bound_fields` instead.

        :param kwargs: Forwarded to ``super().__init_subclass__``.
        """
        super().__init_subclass__(**kwargs)
        binds = cls.__dict__.get("__binds__")
        if binds is not None and "_child_attrs" not in cls.__dict__:
            cls._child_attrs = _child_attrs_of(binds)

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        """Build the record, coercing ``models``-mode lists to tuples.

        The fold and the PDA hand live sink lists; stored raw they would
        alias per-parse state and make the record unhashable.

        :param args: Leading field values, positionally.
        :param kwargs: Remaining field values, by name.
        :returns: A new immutable record instance.
        """
        if any(isinstance(value, list) for value in args):
            args = tuple(
                tuple(value) if isinstance(value, list) else value for value in args
            )
        kwargs |= {
            name: tuple(value)
            for name, value in kwargs.items()
            if isinstance(value, list)
        }
        return super().__new__(cls, *args, **kwargs)

    def __eq__(self, other: object) -> bool:
        """Type-aware equality: same concrete class AND equal payload.

        Plain tuple equality is cross-class (``A('x') == B('x')``), which
        would collide distinct rules' models in dicts/sets and weaken
        round-trip determinism assertions — the ``IrBounds`` precedent.

        :param other: The value to compare against.
        :returns: ``True`` when ``other`` is the same class with equal fields.
        """
        if type(self) is not type(other):
            return False
        return tuple.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        """Negation of :meth:`__eq__`, kept consistent with it.

        :param other: The value to compare against.
        :returns: ``True`` when not equal under :meth:`__eq__`.
        """
        return not self == other

    def __hash__(self) -> int:
        """Hash by tuple payload — consistent with :meth:`__eq__`.

        Distinct classes with equal payloads may collide (harmless); equal
        models always share a hash.

        :returns: The native tuple hash.
        """
        return tuple.__hash__(self)

    @classmethod
    def bound_fields(cls) -> dict[int, tuple[str, IrBind]]:
        """Item slot → ``(field name, bind)`` — the class's binds table.

        The neutral accessor onto a class's field bindings — shared by
        :meth:`to_text`/:meth:`semantic_dump` and by external consumers
        (e.g. viz) that need the same slot → field mapping. An explicitly
        declared ``__binds__`` wins; otherwise the table is resolved once
        from ``Annotated`` ``IrBind`` metadata and cached (the emitter shim,
        see the module docstring).

        :returns: Item slot to ``(field name, bind)``, one entry per bound field.
        """
        if "__binds__" not in cls.__dict__:
            binds = _binds_from_annotations(cls)
            cls.__binds__ = binds
            cls._child_attrs = _child_attrs_of(binds)
        return cls.__dict__["__binds__"]

    def children(self) -> Sequence[IrSelf]:
        """Bound-field values in item order — the model's walk/viz payload.

        Follows the binds table's item order (not field declaration order);
        an unset optional field contributes its ``None`` as-is.

        :returns: The bound values, item order.
        """
        bound = type(self).bound_fields()
        return cast(
            Sequence[IrSelf],
            tuple(
                getattr(self, name) for _slot, (name, _bind) in sorted(bound.items())
            ),
        )

    def rebuild(self, new_children: Sequence[IrSelf]) -> Self:
        """Splice replacements into the bound fields; keep everything else.

        The inverse of :meth:`children`: ``new_children`` supplies one value
        per bound field, in the same item order.

        :param new_children: Replacement values for the bound fields.
        :returns: A new instance with the bound fields replaced.
        """
        bound = type(self).bound_fields()
        names = [name for _slot, (name, _bind) in sorted(bound.items())]
        replacements = dict(zip(names, new_children, strict=True))
        values = [
            replacements.get(name, self[index])
            for index, name in enumerate(self._fields)
        ]
        return type(self)(*values)

    def model_dump(self) -> dict[str, Any]:
        """The native dict dump — runtime-complete, stack-safe (ruling 12).

        Serializes every nested value by ITS OWN runtime type (never by a
        declared schema, so no subtree ever erases), keys in field order,
        tuples re-emitted as lists. Model nesting rides an explicit work
        stack, so arbitrarily deep chains dump with constant Python stack.

        :returns: The runtime-complete dump.
        """
        out: dict[str, Any] = {}
        stack: list[tuple[GrammarModel, dict[str, Any]]] = [(self, out)]
        while stack:
            model, sink = stack.pop()
            for name in model._fields:
                sink[name] = _dump_value(getattr(model, name), stack)
        return out

    def semantic_dump(self) -> dict[str, Any]:
        """Dump only semantic fields (binds with ``semantic=False`` excluded).

        The exclusion is top-level-only — a nested model's own non-semantic
        fields remain in the dump (the measured R2-5 depth).

        :returns: :meth:`model_dump` with this model's own noise fields removed.
        """
        exclude = {
            name
            for name, bind in type(self).bound_fields().values()
            if not bind.semantic
        }
        return {k: v for k, v in self.model_dump().items() if k not in exclude}

    def to_text(self) -> str:
        """Emit source text for this model instance.

        Walks an explicit work-stack rather than recursing into nested
        models, so emission is stack-safe at any nesting depth. Each stack
        entry is either resolved text or an unexpanded field value; a model
        is expanded via :meth:`_emit_parts`, preserving pre-order output.
        The model check precedes the tuple check — records ARE tuples.
        """
        out: list[str] = []
        stack: list[object] = [self]
        while stack:
            node = stack.pop()
            if isinstance(node, str):
                out.append(node)
            elif isinstance(node, GrammarModel):
                stack.extend(reversed(GrammarModel._emit_parts(node)))
            elif isinstance(node, (list, tuple)):
                stack.extend(reversed(node))
            else:
                out.append(str(node))
        return "".join(out)

    def _emit_parts(self) -> list[object]:
        """This model's own emission items, deferring nested values.

        Returns the ordered items :meth:`to_text` would emit for this model
        alone — literal strings for unbound literals, and each bound field's
        value (str, model, or tuple) left unexpanded for the walker to
        resolve. Mirrors ``to_text``'s per-item logic without recursing.

        :returns: The ordered emission items for this model.
        :raises NotImplementedError: On an abstract alternation class (no
            fields at all); call ``to_text`` on the concrete arm instead.
        """
        binds = type(self).bound_fields()
        if not binds:
            if "value" in self._fields:
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
    ) -> tuple[Callable[[dict[str, Any], set[str]], GrammarModel], dict[str, Any]]:
        """The construction licence — trivially granted on the record spine.

        A record build is one C-level tuple construction from already-folded
        parts; there is no per-field validation to skip, so every class
        qualifies (the pydantic-era refusal conditions — validators,
        post-init, config, private attributes — cannot exist on a record).

        :returns: ``(parts constructor, per-class field defaults)``.
        """
        return cls._from_parts, dict(cls._field_defaults)

    @classmethod
    def _from_parts(cls, parts: dict[str, Any], _keys: set[str]) -> Self:
        """Trusted build from complete parts — one C-level tuple construction.

        ``parts`` arrives pre-seeded with the class defaults (the licence
        contract), so the build is a single ordered read; ``models``-mode
        live lists coerce to tuples here exactly as in :meth:`__new__`.

        :param parts: Every field's value, defaults already filled.
        :param _keys: The explicitly-set field names (unused on the spine;
            kept for the frozen ``FastCtor.make`` call shape).
        :returns: The constructed instance.
        """
        return tuple.__new__(
            cls,
            [
                tuple(value) if isinstance(value, list) else value
                for value in map(parts.get, cls._fields)
            ],
        )

    @classmethod
    def model_rebuild(cls) -> None:
        """No-op emitter shim — the codegen loader rebuilds every class.

        The record spine has no deferred schema to resolve; this exists only
        so the (read-only) old codegen path stays green and dies with the
        runtime-synthesis flip.
        """
