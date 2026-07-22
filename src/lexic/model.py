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
slot to ``(field name, IrBind)``. Runtime synthesis writes the table directly;
a hand-authored model declares its own; a class with no bound fields inherits
the empty default.

Hand construction (``cls(**kwargs)`` via :meth:`GrammarModel.__new__`) is
checked: missing required fields and per-field IR-intrinsic violations raise
:exc:`~lexic.exceptions.FieldValidationError`. The trusted parse paths
(:meth:`GrammarModel._from_parts` / :meth:`GrammarModel.fast_construct`)
bypass ``__new__`` and stay unchecked, so the PDA hot path pays nothing.
Construction coerces ``models``-mode lists to tuples (the fold and PDA hand
live sink lists; stored raw they would alias and kill hashability).
:meth:`GrammarModel.dump` re-emits those tuples
as lists and serializes by RUNTIME type (ruling 12 — never by declared
schema), walking an explicit stack so depth never overflows.
"""

from __future__ import annotations

from typing import Any, Callable, ClassVar, Self, Sequence, cast

from lexic.exceptions import FieldValidationError
from lexic.grammars import get_flavour
from lexic.ir.action import IrAction
from lexic.ir.base import IrLambda, IrNamedTuple, IrNone, IrSelf
from lexic.ir.bind import IrBind
from lexic.ir.mapping import IrTypeMap
from lexic.ir.nodes import (
    IrAlphabet,
    IrAlternation,
    IrCharClass,
    IrItem,
    IrLiteral,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.walk import IrDispatch


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


# ── checked construction ──────────────────────────────────────────────
#
# Hand construction (``cls(**kwargs)`` — tests, and the Earley completion
# path) runs IR-intrinsic per-field checks; the trusted parse paths
# (``_from_parts``/``fast_construct``) bypass ``__new__`` entirely, so the PDA
# hot path pays nothing. Every check reads the field's own grammar item — char
# class membership + length bounds, ``Literal``-arm membership, sub-model
# isinstance — with no engine call and no regex compilation.
#
# R7 holes (typed plain ``str`` and never validated, left
# unchecked deliberately): a bound (always quantified) literal field, and a
# ref-bearing ``gtext`` group. A value_str whose value is a single char class
# or a lone literal is likewise not checked — the char-class check is
# bind-driven (it reads ``IrBind.item.quantifier``) and a value_str field
# carries no bind; only the multi-arm ``Literal[...]`` value_str is checked.

_UNIT = IrQuantifier(1, 1)


class _FieldCheck(IrNamedTuple[str, object, str]):
    """State carrier for the per-field check dispatch (the ``d`` slot).

    Passed as the dispatcher to :data:`_FIELD_CHECK` so each open body reads
    the field name, its runtime value and its fold mode without a closure (the
    ``_FieldTyper`` idiom). ``_child_attrs`` is empty — none of the three is an
    IR-node child.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    field: str
    value: object
    mode: str


def _uncovered_char(cc: IrCharClass, value: str) -> str | None:
    """The first char of ``value`` not covered by ``cc``, or ``None``.

    Tests membership against the class's interval cover, so a ``[^...]``
    complement is never materialised point-by-point.

    :param cc: The char class the field's characters must fall within.
    :param value: The field's string value.
    :returns: The first out-of-class character, or ``None`` if all are covered.
    """
    spans = cc.intervals()
    for ch in value:
        point = ord(ch)
        if not any(lo <= point <= hi for lo, hi in spans):
            return ch
    return None


def _check_charclass(d: _FieldCheck, n: IrSelf, nc: Sequence[IrSelf]) -> IrSelf:
    """Text-mode char class: every char covered, length within the quantifier."""
    assert isinstance(n, IrCharClass)
    value = d.value
    if not isinstance(value, str):
        raise FieldValidationError(
            f"field {d.field!r}: expected a str for char-class field, got "
            f"{type(value).__name__}"
        )
    bad = _uncovered_char(n, value)
    if bad is not None:
        raise FieldValidationError(
            f"field {d.field!r}: character {bad!r} is not in [{n.pattern()}]"
        )
    quantifier = cast(IrItem, nc[0]).quantifier
    if len(value) not in quantifier:
        raise FieldValidationError(
            f"field {d.field!r}: length {len(value)} out of bounds {quantifier!r}"
        )
    return IrNone


def _check_literal(_d: _FieldCheck, _n: IrSelf, _nc: Sequence[IrSelf]) -> IrSelf:
    """R7 hole: a bound (quantified) literal field is plain ``str`` — unchecked."""
    return IrNone


def _check_model(field: str, value: object) -> None:
    """A model-mode field holds a sub-model — any :class:`GrammarModel`."""
    if not isinstance(value, GrammarModel):
        raise FieldValidationError(
            f"field {field!r}: expected a sub-model, got {type(value).__name__}"
        )


def _check_ref(d: _FieldCheck, _n: IrSelf, _nc: Sequence[IrSelf]) -> IrSelf:
    """Model/models mode: the value is a sub-model, or a tuple of sub-models.

    The isinstance target is the :class:`GrammarModel` spine, not the exact arm
    class: a model carries only its own ``__grammar__``, no rule→class registry
    (a class→grammar backlink is out of scope, R1), so exact-arm membership is
    not per-field intrinsic.
    """
    value = d.value
    if d.mode == "models":
        if not isinstance(value, (tuple, list)):
            raise FieldValidationError(
                f"field {d.field!r}: expected a list of sub-models, got "
                f"{type(value).__name__}"
            )
        for element in value:
            _check_model(d.field, element)
    else:
        _check_model(d.field, value)
    return IrNone


def _check_group(d: _FieldCheck, n: IrSelf, nc: Sequence[IrSelf]) -> IrSelf:
    """Inline group: model/models like a ref; gtext is an R7 hole (plain str)."""
    if d.mode in ("model", "models"):
        return _check_ref(d, n, nc)
    return IrNone


def _check_token(d: _FieldCheck, _n: IrSelf, _nc: Sequence[IrSelf]) -> IrSelf:
    """Text-mode token: the field holds the token's text.

    A plain ``str`` (an R7 hole like a bound literal) — the vocab-membership
    check needs a tokenizer, which is not a per-field intrinsic. The atom is
    always an ``IrAlphabet`` (negation lives inside it; char negation is
    canonicalised away).
    """
    if not isinstance(d.value, str):
        raise FieldValidationError(
            f"field {d.field!r}: expected a str for token field, got "
            f"{type(d.value).__name__}"
        )
    return IrNone


# Dispatched on the field's atom; the owning IrItem rides the argument channel
# and the value/mode/name ride the ``d`` carrier. The raising default refuses
# an atom type outside this table — no silent unchecked field.
_FIELD_CHECK: IrDispatch = IrDispatch(
    actions=IrTypeMap(
        IrAction(IrCharClass, IrLambda(_check_charclass)),
        IrAction(IrLiteral, IrLambda(_check_literal)),
        IrAction(IrAlphabet, IrLambda(_check_token)),
        IrAction(IrRuleRef, IrLambda(_check_ref)),
        IrAction(IrAlternation, IrLambda(_check_group)),
    ),
)


def _value_str_literals(rule: IrRule) -> frozenset[str] | None:
    """The allowed set of a ``Literal[...]`` value_str rule, else ``None``.

    Mirrors the emitter's ``value_str_type`` ``Literal`` branch: a body whose
    every arm is a single unit-quantified literal (and which is not the
    single-item shortcut) is typed ``Literal[...]`` and membership-checked. A
    single-item value (str / char class) and any ref-bearing body are typed
    plain ``str`` / a pattern and are not checked here.

    :param rule: The value_str class's own ``__grammar__`` rule.
    :returns: The permitted literal strings, or ``None`` when not a
        ``Literal[...]`` value_str.
    """
    arms = [arm for arm in rule.body if arm]
    if len(arms) == 1 and len(arms[0]) == 1:
        return None
    if all(
        len(arm) == 1
        and isinstance(arm[0].atom, IrLiteral)
        and arm[0].quantifier == _UNIT
        for arm in rule.body
    ):
        return frozenset(str(arm[0].atom) for arm in arms)
    return None


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

    def __new__(cls, *args: Any, **kwargs: Any) -> Self:
        """Build the record with checked construction (hand-construction path).

        Coerces ``models``-mode lists to tuples (the fold and PDA hand live
        sink lists; stored raw they would alias per-parse state and make the
        record unhashable), rewires a missing required field to
        :exc:`FieldValidationError`, and runs the IR-intrinsic per-field checks
        on the built record. The trusted parse paths bypass this method.

        :param args: Leading field values, positionally.
        :param kwargs: Remaining field values, by name.
        :returns: A new immutable record instance.
        :raises FieldValidationError: On a missing required field or a field
            value that violates its grammar-intrinsic contract.
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
        cls._check_required(args, kwargs)
        instance = super().__new__(cls, *args, **kwargs)
        instance._check_fields()
        return instance

    @classmethod
    def _check_required(cls, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        """Raise :exc:`FieldValidationError` for a missing required field.

        Rewires the record metaclass's ``TypeError`` on the hand-construction
        path (a genuine ``unexpected fields`` misuse still surfaces as a
        ``TypeError`` from the record build). Positional args fill the leading
        fields; keywords fill by name.

        :param args: The positional construction args.
        :param kwargs: The keyword construction args.
        :raises FieldValidationError: On a field with no value and no default.
        """
        provided = set(cls._fields[: len(args)]) | set(kwargs)
        for name in cls._fields:
            if name not in provided and name not in cls._field_defaults:
                raise FieldValidationError(
                    f"{cls.__name__} missing required field {name!r}"
                )

    def _check_fields(self) -> None:
        """Run every bound field's check; a value_str routes to its own path.

        A None value is an absent optional field (presence is enforced before
        the build), skipped here. Each bound field dispatches on its atom via
        :data:`_FIELD_CHECK`, the owning item and the value/mode/name supplied.

        :raises FieldValidationError: On any field-value violation.
        """
        cls = type(self)
        binds = cls.bound_fields()
        if not binds:
            self._check_value_str()
            return
        arm = next((a for a in cls.__grammar__.body if a), IrSequence())
        for _slot, (name, bind) in binds.items():
            value = getattr(self, name)
            if value is None:
                continue
            item = arm[bind.item]
            _FIELD_CHECK.eval(_FieldCheck(name, value, bind.mode), item.atom, (item,))

    def _check_value_str(self) -> None:
        """Membership-check a ``Literal[...]`` value_str; nothing else here.

        An abstract alternation class (no ``value`` field) and a plain-``str`` /
        char-class value_str carry nothing checkable through this path.

        :raises FieldValidationError: When the value is outside the arm set.
        """
        if "value" not in self._fields:
            return
        allowed = _value_str_literals(type(self).__grammar__)
        if allowed is None:
            return
        value = getattr(self, "value")
        if value not in allowed:
            raise FieldValidationError(
                f"field 'value': {value!r} is not one of {sorted(allowed)}"
            )

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
        (e.g. viz) that need the same slot → field mapping. Every class carries
        an explicit ``__binds__`` (runtime synthesis writes it; a hand-authored
        model declares it); a class with none inherits the empty default.

        :returns: Item slot to ``(field name, bind)``, one entry per bound field.
        """
        return cls.__binds__

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

    def dump(self) -> dict[str, Any]:
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

        :returns: :meth:`dump` with this model's own noise fields removed.
        """
        exclude = {
            name
            for name, bind in type(self).bound_fields().values()
            if not bind.semantic
        }
        return {k: v for k, v in self.dump().items() if k not in exclude}

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

    def to_grammar(self, flavour: str = "gbnf", width: int | None = 88) -> str:
        """Emit this model's rule as grammar text in the given flavour.

        :param flavour: The target flavour name.
        :param width: Target maximum line width; ``None`` emits flat.
        """
        return str(get_flavour(flavour).apply(self.__grammar__, width))

    @classmethod
    def fast_construct(
        cls,
    ) -> tuple[Callable[[dict[str, Any], set[str]], GrammarModel], dict[str, Any]]:
        """The construction licence — trivially granted on the record spine.

        A record build is one C-level tuple construction from already-folded
        parts; there is no per-field validation to skip, so every class
        qualifies (a record has no validators, post-init, config, or private
        attributes that could refuse the licence).

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
