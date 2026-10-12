"""The bound model product — what a parse entry is handed.

Binding is the one moment an AUTHORED product becomes an executable one. A
surface hands in its rules and the tables lowering owns — constructors to
check, routes to specialize, symbol keys and the registry that resolves them —
and gets back a verified program plus the readers both engines use. Doing that
here rather than at each surface is what makes "lowered once, verified cold at
bind" literally true: no caller can hand an engine a program the verifier has
not seen.

Its own module because both halves of the engine reach it: the product entry
hands it down, the clone compiler bakes from it, and a record either of them
owned would make the other import it back.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from copy import deepcopy
from types import CellType, FunctionType, MappingProxyType, MethodType
from typing import Any, TypeVar

from lexic.exceptions import SemanticVerdict, UnsupportedConstructError
from lexic.ir import IrAst, IrSelf, Singleton
from lexic.parsing.earley.kernel.forest.support.ambiguity import ParseConfig, same_value
from lexic.parsing.product import (
    LoweringOwned,
    MeaningOp,
    OperandTables,
    ProductExecutor,
    ProductProgram,
    RootOp,
    RuleProduct,
    RuleRoutine,
    lower_product,
    rule_routines,
    verify_program,
)

__all__ = ["ModelExecutable", "ModelParse", "private_copy", "process_constants"]


type ModelParse[M] = Callable[[IrAst, str, ModelExecutable[M], ParseConfig], M]
"""A model parse entry, as the callers that INJECT one see it.

One product parses every grammar, and it is the ``binding`` handed in that says
which model comes back — so the alias is generic in that model. Declaring it
here is what lets a caller pass the product down through a layer that must not
import it (the split orchestrator) without the model type being erased on the
way through.
"""


def _identity_root[M](carry: M, _verdicts: tuple[SemanticVerdict, ...]) -> M:
    """The default root finalizer — the start rule's value, unchanged."""
    return carry


class ModelExecutable[M]:
    """One grammar's model product — what a parse entry is handed.

    The product IS the binding: the verified program its rules lowered to, the
    routine each contextual name completes through, and the one executor that
    runs them over a derivation. One object rather than several parameters, so
    a caller cannot pair a grammar's captures with another grammar's
    constructors and the per-identity memo has a single key to hold.

    The authored rules are LOWERING INPUT and nothing else: they are consumed
    in the constructor and not retained. Everything downstream — completion,
    the clone bake, stitch layout — reads :attr:`routines`, which is the
    verified program read back. That is what makes "the program the verifier
    passed is the program that runs" a property of the object rather than a
    claim about it; holding the authored records too would leave a second
    representation for an engine to reach for.

    Verification is a claim about an OBJECT, so the object cannot change after
    it is made. Every attribute here is bound once and the projections are
    read-only views over containers no caller holds; the executor keeps its own
    plain dict as a private physical copy, so the hot reader pays a dict lookup
    and the public surface still cannot be edited into disagreeing with the
    program the verifier passed.

    :ivar program: The lowered, verified program. Every rule in it names one
        tagged, non-empty, in-bounds completion range.
    :ivar codes: Rule name → its index in :attr:`program`, read-only.
    :ivar routines: Rule name → its verified completion routine, read-only.
    :ivar executor: The one completion over :attr:`routines`.
    """

    __slots__ = ("program", "codes", "routines", "executor")

    program: ProductProgram[M, M]
    codes: Mapping[str, int]
    routines: Mapping[str, RuleRoutine[M]]
    executor: ProductExecutor[M]

    def __init__(
        self,
        rules: Mapping[str, RuleProduct] | None = None,
        owned: LoweringOwned[M] = LoweringOwned(),
    ) -> None:
        """Lower one surface's authored rules, and verify them before any use.

        :param rules: Rule name → its authored product. An authored
            compile-time surface fills this from its own table; a generated
            model from the binding view.
        :param owned: The tables lowering writes — constructors to validate,
            routes to specialize, and symbol keys with the registry they
            resolve through.
        :raises UnsupportedConstructError: When the rules do not lower, or the
            program they lower to does not verify.
        """
        authored = {} if rules is None else rules
        codes = {name: at for at, name in enumerate(authored)}
        object.__setattr__(self, "codes", MappingProxyType(codes))
        # The meaning row is the engine's own value law, not `==`: every
        # ambiguity gate compares with `same_value`, so a program declaring
        # anything else would name a law it does not live under.
        operands: OperandTables[M, M] = OperandTables(
            (), (), (), (), (same_value,), (_identity_root,), (), ()
        )
        program = lower_product(
            list(authored.values()),
            operands,
            owned=owned,
            root=RootOp(0),
            meaning=MeaningOp(0),
        )
        verify_program(program)
        resolved = rule_routines(program)
        routines = {name: resolved[code] for name, code in codes.items()}
        object.__setattr__(self, "program", program)
        object.__setattr__(self, "routines", MappingProxyType(routines))
        object.__setattr__(self, "executor", ProductExecutor(routines))

    def __setattr__(self, name: str, value: object) -> None:
        """Refuse every rebinding — a verified executable is bound once.

        :raises UnsupportedConstructError: Always. Rebinding one of these is
            an attempt to produce the defective compiled artefact that class
            names, not a field failing its own check.
        """
        del value
        raise UnsupportedConstructError(
            f"parsing: {type(self).__name__}.{name} cannot be reassigned; a "
            "verified executable is what the verifier passed"
        )

    def __delattr__(self, name: str) -> None:
        """Refuse every deletion, for the same reason as :meth:`__setattr__`.

        :raises UnsupportedConstructError: Always.
        """
        raise UnsupportedConstructError(
            f"parsing: {type(self).__name__}.{name} cannot be deleted; a "
            "verified executable is what the verifier passed"
        )

    def replica(self) -> ModelExecutable[M]:
        """An equal binding whose routine map is a worker's own.

        The memo keys on the BINDING's identity, so a worker that wants its own
        compiled tables needs its own binding; the routine map is rebuilt —
        inside the executor, which copies what it is handed — because it is the
        container every completion reads, and therefore the one whose sharing
        costs the reference-count traffic that held eight threads below the
        throughput of one. The read-only projections are shared by identity
        instead: nothing can write through them, so nothing has to be copied.

        Nothing is lowered or verified again. The program is immutable and
        already passed the cold gate, so re-deriving it per worker would pay a
        whole lowering pass to reach the artefact this one is holding — and a
        worker rebuilding the constructors would change what a model is built
        from, when model equality across workers is the contract the split
        rests on.
        """
        copy = object.__new__(type(self))
        object.__setattr__(copy, "program", self.program)
        object.__setattr__(copy, "codes", self.codes)
        object.__setattr__(copy, "routines", self.routines)
        object.__setattr__(copy, "executor", ProductExecutor(self.routines))
        return copy

    def copied[T](self, compiled: T, replica: ModelExecutable[M]) -> T:
        """``compiled``, built against this binding, as ``replica``'s own copy.

        What a compile minted is made anew, so nothing the copy reads while it
        parses is an object another thread reads too; this binding and its
        executor become ``replica``'s, and the read-only projections stay shared
        exactly as :meth:`replica` shares them.

        :param compiled: An artefact compiled with this binding.
        :param replica: A :meth:`replica` of this binding.
        :returns: The private copy.
        """
        remap: dict[int, object] = {
            id(self): replica,
            id(self.executor): replica.executor,
            id(self.program): self.program,
            id(self.codes): self.codes,
            id(self.routines): self.routines,
        }
        remap.update((id(routine), routine) for routine in self.routines.values())
        return private_copy(compiled, remap)


def private_copy[T](compiled: T, remap: Mapping[int, object] | None = None) -> T:
    """``compiled`` as a private structural copy — the one entry to the copy.

    What a compile minted is made anew; what a lexic module or class names is
    kept; ``remap`` names what else is kept or replaced, by identity. A binding's
    artefacts pass the binding's own remap (:meth:`ModelExecutable.copied`);
    an artefact that never reaches a binding — an island's Earley tables —
    passes none.

    :param compiled: The artefact to copy.
    :param remap: Original ``id`` → the object the copy uses in its place.
    :returns: The copy.
    """
    kept = process_constants()
    kept.update(remap or {})
    return PrivateCopy(kept).of(compiled)


_NOT_MADE = object()
"""A memo miss — distinct from every value a copy can make, ``None`` included."""

_SELF_COPYING = frozenset({("re", "Pattern")})
"""The C types copied by their own deep-copy protocol, named rather than
imported: a compiled pattern answers with itself (immutable, and re's own cache
shares it between compiles anyway). A C type not named here is refused —
defining ``__deepcopy__`` says nothing about what it shares."""

_CLASS_STATEMENT = "__firstlineno__"
"""What a ``class`` statement records on the class it makes: its instances are
plain slot/dict objects the structural copy can rebuild. A C type has none,
and on 3.14 many of those are heap types too, so the heap flag cannot tell."""


class PrivateCopy:
    """One structural copy of a compiled artefact.

    Every object the compile minted — engine records, containers, the closures
    it baked and their cells — is made anew; what the copy must not duplicate
    is :attr:`made` from the start: values a module or class names (constants
    compared by identity), and whatever the caller keeps or remaps. Atoms are
    shared, as they are between two compiles of one grammar; an IR value node
    is rebuilt, because the tables a parse reads hold them.

    :ivar made: Original ``id`` → its copy (or itself, where it is kept).
    """

    __slots__ = ("made",)

    def __init__(self, kept: dict[int, Any]) -> None:
        """Start from the objects that are kept or remapped, not copied."""
        self.made = kept

    def of[T](self, part: T) -> T:
        """``part``'s copy, made once however often it is reached."""
        made = self.made.get(id(part), _NOT_MADE)
        if made is not _NOT_MADE:
            return made
        return _copier(type(part))(self, part)

    def keep[T](self, part: T, made: T) -> T:
        """Record ``made`` as ``part``'s copy and hand it back."""
        self.made[id(part)] = made
        return made


def process_constants() -> dict[int, Any]:
    """Every object a lexic module or class names, keyed by its ``id``.

    Such an object is the process's — a sentinel, a ``CharSet.EMPTY``, a
    module-level function — and may be compared by identity, so a copy keeps
    it rather than making a second one.
    """
    kept: dict[int, Any] = {}
    for module in list(sys.modules.values()):
        if module is None or not module.__name__.startswith("lexic"):
            continue
        for value in list(vars(module).values()):
            kept[id(value)] = value
            if isinstance(value, type):
                kept.update((id(attr), attr) for attr in vars(value).values())
    return kept


def _shared[T](_copy: PrivateCopy, part: T) -> T:
    """An immutable atom: one object serves every copy."""
    return part


def _ir_value(copy: PrivateCopy, part: IrSelf) -> IrSelf:
    """An IR value node rebuilt over copies of its children.

    Immutable, but counted: the tables a parse reads hold them (a decoded
    rule's reference, a terminal's spelling), and a worker reading the
    original's would pay an atomic count on every one. A scalar leaf rebuilds
    as itself.
    """
    made = part.rebuild([copy.of(kid) for kid in part.children()])
    if made is part:  # a scalar leaf: its payload IS the value, so make it anew
        made = _leaf(part)
    return copy.keep(part, made)


def _own_copy[T](copy: PrivateCopy, part: T) -> T:
    """A C-level object :data:`_SELF_COPYING` names, copied by its own
    deep-copy protocol."""
    return copy.keep(part, deepcopy(part, copy.made))


def _leaf(part: IrSelf) -> IrSelf:
    """A scalar IR leaf made anew over its payload; anything else as it is."""
    if isinstance(part, str):
        return _text_leaf(part)
    if isinstance(part, int):
        return _number_leaf(part)
    return part


def _text_leaf[T: str](part: T) -> T:
    """A string-payload IR leaf, new: its class rebuilt over its own text."""
    return _fields_from(part, type(part)(part))


def _number_leaf[T: int](part: T) -> T:
    """An int-payload IR leaf, new: its class rebuilt over its own value."""
    return _fields_from(part, type(part)(part))


def _fields_from[T](part: T, made: T) -> T:
    """``made`` with ``part``'s slots and ``__dict__`` carried over."""
    for name in _slot_names(type(part)):
        value = getattr(part, name, _NOT_MADE)
        if value is not _NOT_MADE:
            object.__setattr__(made, name, value)
    if hasattr(part, "__dict__"):
        vars(made).update(vars(part))
    return made


def _tuple(copy: PrivateCopy, part: tuple[Any, ...]) -> tuple[Any, ...]:
    """A tuple of copies — after its members, since a member may reach it."""
    members = [copy.of(one) for one in part]
    made = copy.made.get(id(part), _NOT_MADE)
    return made if made is not _NOT_MADE else copy.keep(part, tuple(members))


def _named[T: tuple[Any, ...]](copy: PrivateCopy, part: T) -> T:
    """A named tuple rebuilt over copies of its fields, by the ``_make`` every
    named tuple class carries."""
    members = [copy.of(one) for one in part]
    made = copy.made.get(id(part), _NOT_MADE)
    return (
        made
        if made is not _NOT_MADE
        else copy.keep(part, getattr(type(part), "_make")(members))
    )


def _frozenset(copy: PrivateCopy, part: frozenset[Any]) -> frozenset[Any]:
    """A frozenset of copies."""
    return copy.keep(part, frozenset([copy.of(one) for one in part]))


def _dict(copy: PrivateCopy, part: dict[Any, Any]) -> dict[Any, Any]:
    """A dict of copies, read from a snapshot a concurrent writer cannot tear."""
    made = copy.keep(part, {})
    for key, value in dict(part).items():
        made[copy.of(key)] = copy.of(value)
    return made


def _list(copy: PrivateCopy, part: list[Any]) -> list[Any]:
    """A list of copies."""
    made = copy.keep(part, [])
    made.extend(copy.of(one) for one in list(part))
    return made


def _set(copy: PrivateCopy, part: set[Any]) -> set[Any]:
    """A set of copies."""
    made = copy.keep(part, set())
    made.update(copy.of(one) for one in set(part))
    return made


def _function(copy: PrivateCopy, part: FunctionType) -> FunctionType:
    """A baked closure with cells of its own.

    The function is recorded before its cells are filled, so a closure that
    reaches itself through them closes over its copy.
    """
    cells = tuple(CellType() for _ in part.__closure__ or ())
    made = copy.keep(
        part,
        FunctionType(
            part.__code__, part.__globals__, part.__name__, None, cells or None
        ),
    )
    made.__qualname__ = part.__qualname__
    made.__defaults__ = copy.of(part.__defaults__)
    made.__kwdefaults__ = copy.of(part.__kwdefaults__)
    made.__dict__.update(copy.of(part.__dict__))
    for old, new in zip(part.__closure__ or (), cells, strict=True):
        new.cell_contents = copy.of(old.cell_contents)
    return made


def _method(copy: PrivateCopy, part: MethodType) -> MethodType:
    """A bound method on the copy of its receiver."""
    return copy.keep(part, MethodType(copy.of(part.__func__), copy.of(part.__self__)))


def _object[T](copy: PrivateCopy, part: T) -> T:
    """An instance of a Python class, its slots and ``__dict__`` copied.

    Recorded before its fields are copied, so the cycles a compiled program
    holds — a clone reaching itself through its arms — close over the copy.
    """
    made = copy.keep(part, object.__new__(type(part)))
    for name in _slot_names(type(part)):
        value = getattr(part, name, _NOT_MADE)
        if value is not _NOT_MADE:
            object.__setattr__(made, name, copy.of(value))
    if hasattr(part, "__dict__"):
        vars(made).update(copy.of(vars(part)))
    return made


def _slot_names(cls: type) -> tuple[str, ...]:
    """Every instance slot ``cls`` and its bases declare, by its stored name."""
    names: list[str] = []
    for base in cls.__mro__:
        declared = vars(base).get("__slots__", ())
        for name in (declared,) if isinstance(declared, str) else declared:
            private = name.startswith("__") and not name.endswith("__")
            names.append(f"_{base.__name__.lstrip('_')}{name}" if private else name)
    return tuple(name for name in names if name not in ("__dict__", "__weakref__"))


type Copier = Callable[[PrivateCopy, Any], Any]
"""How one type is copied."""

_COPIERS: dict[type, Copier] = {
    **dict.fromkeys(
        (str, int, float, bool, bytes, type(None), type, TypeVar),
        _shared,
    ),
    tuple: _tuple,
    frozenset: _frozenset,
    dict: _dict,
    list: _list,
    set: _set,
    FunctionType: _function,
    MethodType: _method,
}
"""The copier per exact type; a type first met is classified by
:func:`_classify` and filed here."""


def _copier(cls: type) -> Copier:
    """The copier for ``cls``, classified once."""
    known = _COPIERS.get(cls)
    if known is not None:
        return known
    found = _classify(cls)
    _COPIERS[cls] = found
    return found


def _classify(cls: type) -> Copier:
    """How a type no row names is copied.

    :raises UnsupportedConstructError: For a C-level type no row names — a
        copy that cannot say what such an object holds must not guess.
    """
    if issubclass(cls, type):
        return _shared  # a class, whatever its metaclass, is the process's
    if isinstance(cls, Singleton):
        return _shared  # one instance per class, compared by identity
    if issubclass(cls, IrSelf) and issubclass(cls, (tuple, str, int)):
        return _ir_value
    if issubclass(cls, tuple) and hasattr(cls, "_make"):
        return _named
    if _CLASS_STATEMENT in vars(cls):
        return _object
    if (cls.__module__, cls.__qualname__) in _SELF_COPYING:
        return _own_copy
    raise UnsupportedConstructError(
        f"parsing: no private copy for a {cls.__module__}.{cls.__qualname__}"
    )
