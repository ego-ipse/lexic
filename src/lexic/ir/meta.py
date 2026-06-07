"""Borg and Singleton metaclasses for IR classes."""

from threading import RLock
from typing import Any, ClassVar
from weakref import WeakKeyDictionary


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

