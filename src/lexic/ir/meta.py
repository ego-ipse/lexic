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
    """Distinct instances sharing one live state per class; the newest construction wins.

    Every call runs ``__init__`` and overwrites the shared state, so all live
    instances (``__dict__`` or ``__slots__``) reflect the most recent values.
    """

    _states: ClassVar[WeakKeyDictionary[type, dict[str, Any]]] = WeakKeyDictionary()
    _lock: ClassVar[RLock] = RLock()

    def __call__(cls, *args: P.args, **kwargs: P.kwargs) -> T:
        """Return a new instance whose state overwrites and is shared with the rest."""
        if cls not in cls._states:
            with cls._lock:
                if cls not in cls._states:
                    return cls._register(*args, **kwargs)
        return cls._overwrite(*args, **kwargs)

    def _register(cls, *args: P.args, **kwargs: P.kwargs) -> T:
        obj: T = super().__call__(*args, **kwargs)
        if cls.__dictoffset__:
            cls._states[cls] = obj.__dict__
            return obj
        names = cls._slot_names(cls)
        state = {n: getattr(obj, n) for n in names if hasattr(obj, n)}
        for name in names:
            setattr(cls, name, cls._proxy(state, name))
        cls._states[cls] = state
        return obj

    def _overwrite(cls, *args: P.args, **kwargs: P.kwargs) -> T:
        obj: T = super().__call__(*args, **kwargs)
        if cls.__dictoffset__:
            shared = cls._states[cls]
            shared.update(obj.__dict__)
            obj.__dict__ = shared
        return obj

    @staticmethod
    def _slot_names(klass: type) -> list[str]:
        names: list[str] = []
        for base in klass.__mro__:
            for name in getattr(base, "__slots__", ()):
                if name not in ("__dict__", "__weakref__") and name not in names:
                    names.append(name)
        return names

    @staticmethod
    def _proxy(state: dict[str, T], name: str) -> property:
        def getter(_obj: type) -> T:
            try:
                return state[name]
            except KeyError:
                raise AttributeError(name) from None

        def setter(_obj: type, value: T) -> None:
            state[name] = value

        return property(getter, setter)


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
