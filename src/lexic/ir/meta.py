"""Metaclasses for IR classes — the slots-injecting spine metaclass
(:class:`IrMeta`) plus shared-state (:class:`Borg`) and single-instance
(:class:`Singleton` / :class:`IrSingleton`) variants."""

from abc import ABCMeta
from threading import RLock
from typing import Any, ClassVar
from weakref import WeakKeyDictionary


class IrMeta(ABCMeta):
    """Metaclass that gives every IR class an empty ``__slots__`` by default.

    IR nodes keep their payload in the primitive they subclass (``str``/``int``/
    ``tuple``) or in their tuple elements — never in a per-instance ``__dict__``,
    and a ``tuple``/``str`` subclass *must* have empty ``__slots__`` to stay
    dict-free. ``__slots__`` has to be in the class namespace before the class
    object is built, which only a metaclass can guarantee (``__init_subclass__``
    runs too late). Derives from :class:`abc.ABCMeta` so it composes with
    ``IrNode``'s ``ABC`` base. A class that needs its own slots (e.g.
    :class:`Field`) just declares ``__slots__`` — ``setdefault`` leaves it alone.
    """

    def __new__(
        mcs, name: str, bases: tuple[type, ...], namespace: dict[str, Any], /, **kw: Any
    ) -> type:
        """Inject ``__slots__ = ()`` unless the class declared its own.

        :param name: New class name.
        :param bases: Base classes.
        :param namespace: Class body namespace (mutated in place).
        :param kw: Remaining class keyword arguments.
        :returns: The constructed class.
        """
        namespace.setdefault("__slots__", ())
        return super().__new__(mcs, name, bases, namespace, **kw)


class Borg[**P, T](type):
    """Distinct instances sharing one live, lock-guarded state per class; newest construction wins.

    Every call runs ``__init__`` and overwrites the shared state, so all live
    instances (``__dict__`` or ``__slots__``) reflect the most recent values.

    Thread safety. Each class owns its own :class:`RLock`, stored next to its
    state and used for *both* construction and later attribute mutation — a
    construction-only lock would leave post-construction writes unguarded.
    Whatever the backing store, every attribute access through normal ``obj.x``
    syntax funnels through that lock via the ``__getattr__``/``__setattr__``/
    ``__delattr__`` that :meth:`_register` installs on the class before publishing
    its state; an instance's own ``__dict__``/slots stay empty, so its state lives
    in the shared store. (Low-level bypasses — ``object.__setattr__``,
    ``obj.__dict__[...] = ...`` — write the instance directly and escape the
    routing; don't.) A slotted class stays a *closed* attribute set (the routed
    setter rejects names outside its ``__slots__``, exactly as real slots would);
    a ``__dict__``-backed class accepts any name, so dynamically added attributes
    are shared too.

    Per-attribute access is atomic; a multi-attribute *transaction* still needs
    the caller to hold the lock across the whole sequence.
    """

    _lock: ClassVar[RLock] = RLock()
    _states: ClassVar[WeakKeyDictionary[type, tuple[dict[str, Any], RLock]]] = (
        WeakKeyDictionary()
    )

    def __call__(cls, *args: P.args, **kwargs: P.kwargs) -> T:
        """Return a new instance whose state overwrites and is shared with the rest."""
        if cls not in cls._states:
            with cls._lock:
                if cls not in cls._states:
                    return cls._register(*args, **kwargs)
        return cls._overwrite(*args, **kwargs)

    def _register(cls, *args: P.args, **kwargs: P.kwargs) -> T:
        """Install locked routing and publish the state, then build through it.

        Routing and the ``_states`` entry are both in place *before* the first
        ``__init__`` runs, so its assignments flow straight into the shared state
        and the instance keeps nothing of its own. Publishing first also means a
        re-entrant construction of the *same* class lands in :meth:`_overwrite`
        against this state (rather than racing a second registration), and a
        failing ``__init__`` leaves the class consistently registered rather than
        wedged with routing but no state.

        :param args: Positional constructor arguments.
        :param kwargs: Keyword constructor arguments.
        :returns: The first instance, already sharing the new state.
        """
        lock = RLock()
        state: dict[str, Any] = {}
        cls._install_routing(cls, state, lock)
        cls._states[cls] = (state, lock)
        with lock:
            return super().__call__(*args, **kwargs)

    def _overwrite(cls, *args: P.args, **kwargs: P.kwargs) -> T:
        """Construct a new instance under the lock, sharing the class's state.

        ``__init__``'s assignments land in the shared state via the routed
        ``__setattr__``, so the newest construction wins.

        :param args: Positional constructor arguments.
        :param kwargs: Keyword constructor arguments.
        :returns: The new instance, sharing the class's state.
        """
        _state, lock = cls._states[cls]
        with lock:
            return super().__call__(*args, **kwargs)

    @staticmethod
    def _slot_names(klass: type) -> list[str]:
        names: list[str] = []
        for base in klass.__mro__:
            slots = getattr(base, "__slots__", ())
            if isinstance(slots, str):  # a bare-string __slots__ is a single name
                slots = (slots,)
            for name in slots:
                if name not in ("__dict__", "__weakref__") and name not in names:
                    names.append(name)
        return names

    @staticmethod
    def _install_routing(klass: type, state: dict[str, Any], lock: RLock) -> None:
        """Install locked attribute routing onto a Borg-managed class.

        Every instance attribute read, write, and delete through normal syntax is
        redirected to the shared ``state`` under ``lock``; an instance's own
        storage stays empty (``object.__setattr__``-style bypasses excepted). A
        slotted class stays a *closed* attribute set — the setter rejects names
        outside its ``__slots__``, exactly as real slots would — while a
        ``__dict__``-backed class accepts any name, sharing dynamically added
        attributes too.

        :param klass: The Borg-managed class to route.
        :param state: The shared per-class state mapping.
        :param lock: The per-class lock guarding ``state``.
        """
        allowed = None if klass.__dictoffset__ else frozenset(Borg._slot_names(klass))

        def getter(_self: object, name: str) -> Any:
            with lock:
                try:
                    return state[name]
                except KeyError:
                    raise AttributeError(name) from None

        def setter(_self: object, name: str, value: Any) -> None:
            if allowed is not None and name not in allowed:
                raise AttributeError(name)
            with lock:
                state[name] = value

        def deleter(_self: object, name: str) -> None:
            with lock:
                try:
                    del state[name]
                except KeyError:
                    raise AttributeError(name) from None

        setattr(klass, "__getattr__", getter)
        setattr(klass, "__setattr__", setter)
        setattr(klass, "__delattr__", deleter)


class Singleton[**P, T](type):
    """One cached instance per class; works with ``__dict__`` or ``__slots__``."""

    _instances: ClassVar[dict[type, Any]] = {}
    _lock: ClassVar[RLock] = RLock()

    def __call__(cls, *args: P.args, **kwargs: P.kwargs) -> T:
        """Return the single cached instance, constructing it once under a lock."""
        if cls not in cls._instances:
            with cls._lock:
                if cls not in cls._instances:
                    cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class IrSingleton(Singleton, IrMeta):
    """Singleton metaclass for IR classes — :class:`Singleton` caching composed
    with :class:`IrMeta`'s ``__slots__`` injection and ``ABCMeta`` base.

    A bare :class:`Singleton` cannot be the metaclass of an
    :class:`~lexic.ir.base.IrSelf` subclass: ``IrSelf``'s metaclass is
    :class:`IrMeta`, and a class's metaclass must subclass every base's
    metaclass. ``IrSingleton`` IS-A ``IrMeta``, so it composes, while
    ``Singleton.__call__`` supplies the one-instance-per-class caching. This
    replaces the hand-rolled ``__new__`` on the IR sentinels
    (:data:`~lexic.ir.base.IrNone`, :data:`~lexic.ir.mapping.IR_DEFAULT`).
    """
