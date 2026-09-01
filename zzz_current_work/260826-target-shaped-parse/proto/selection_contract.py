"""Executable contract for the finite nested-mapping selection morphism.

This is a semantic-event prototype, not a parser.  It fixes what selection
retains once a compatible reducer has supplied decoded mapping events.  The
route and parser integration are proved separately by route_continuation.py.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import NamedTuple

from product_types import KEEP, Keep, Selection, SelectionSpec

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrInt, IrSelf, IrStr


class BeginMapping(NamedTuple):
    """Enter one mapping selected by a nested declaration."""


class DecodedKey(NamedTuple):
    """Publish one reducer-decoded key."""

    value: str


class KeptValue(NamedTuple):
    """Publish the reducer semantic value at one KEEP leaf."""

    value: IrSelf


class DiscardedValue(NamedTuple):
    """Confirm successful recognition of an unselected value."""


class EndMapping(NamedTuple):
    """Leave one selected mapping."""


type SelectionEvent = (
    BeginMapping | DecodedKey | KeptValue | DiscardedValue | EndMapping
)


class SelectionBranch:
    """Compiled declaration node; construction happens before parsing."""

    __slots__ = ("children",)

    def __init__(self, spec: SelectionSpec) -> None:
        children: dict[str, Keep | SelectionBranch] = {}
        for key, child in spec.items():
            if key in children:
                raise UnsupportedConstructError(
                    f"selection declaration repeats decoded key {key!r}"
                )
            if isinstance(child, Keep):
                children[key] = child
            else:
                children[key] = SelectionBranch(child)
        self.children = children


def declared_paths(
    branch: SelectionBranch, prefix: tuple[str, ...] = ()
) -> tuple[tuple[str, ...], ...]:
    """Return KEEP paths in declaration order."""
    paths: list[tuple[str, ...]] = []
    for key, child in branch.children.items():
        path = prefix + (key,)
        if isinstance(child, Keep):
            paths.append(path)
        else:
            paths.extend(declared_paths(child, path))
    return tuple(paths)


class SelectionFrame:
    """Parse-local state for one traversed mapping."""

    __slots__ = ("branch", "pending", "prefix", "repeated", "seen")

    def __init__(self, branch: SelectionBranch, prefix: tuple[str, ...]) -> None:
        self.branch = branch
        self.pending: str | None = None
        self.prefix = prefix
        self.repeated = False
        self.seen: set[str] = set()


class SelectionMachine:
    """Direct selection product over decoded semantic mapping events."""

    __slots__ = ("branch", "frames", "order", "retained", "verdicts")

    def __init__(self, spec: SelectionSpec) -> None:
        self.branch = SelectionBranch(spec)
        self.frames: list[SelectionFrame] = []
        self.order = declared_paths(self.branch)
        self.retained: dict[tuple[str, ...], IrSelf] = {}
        self.verdicts: list[str] = []

    def _frame(self) -> SelectionFrame:
        if not self.frames:
            raise UnsupportedConstructError(
                "selection event occurred outside its root mapping"
            )
        return self.frames[-1]

    def _begin(self) -> None:
        if not self.frames:
            self.frames.append(SelectionFrame(self.branch, ()))
            return
        parent = self._frame()
        if parent.pending is None:
            raise UnsupportedConstructError("nested mapping has no decoded-key route")
        child = parent.branch.children.get(parent.pending)
        if not isinstance(child, SelectionBranch):
            raise UnsupportedConstructError(
                "mapping event entered a non-nested selection route"
            )
        self.frames.append(SelectionFrame(child, parent.prefix + (parent.pending,)))

    def _key(self, key: str) -> None:
        frame = self._frame()
        if frame.pending is not None:
            raise UnsupportedConstructError(
                "decoded key arrived before its preceding value completed"
            )
        frame.repeated = key in frame.seen
        if frame.repeated:
            self.verdicts.append(f"selection input repeats decoded key {key!r}")
        else:
            frame.seen.add(key)
        frame.pending = key

    def _value(self, value: IrSelf) -> None:
        frame = self._frame()
        key = frame.pending
        if key is None:
            raise UnsupportedConstructError("value has no decoded-key route")
        child = frame.branch.children.get(key)
        if isinstance(child, SelectionBranch):
            self.verdicts.append(
                f"selection path {frame.prefix + (key,)!r} requires a mapping"
            )
        elif child is KEEP:
            if not frame.repeated:
                self.retained[frame.prefix + (key,)] = value
        else:
            raise UnsupportedConstructError(
                "unselected route constructed a semantic value"
            )
        frame.pending = None
        frame.repeated = False

    def _discard(self) -> None:
        frame = self._frame()
        key = frame.pending
        if key is None:
            raise UnsupportedConstructError("discarded value has no decoded-key route")
        child = frame.branch.children.get(key)
        if child is not None and not frame.repeated:
            raise UnsupportedConstructError(
                "selected route discarded its semantic value"
            )
        frame.pending = None
        frame.repeated = False

    def _end(self) -> None:
        frame = self._frame()
        if frame.pending is not None:
            raise UnsupportedConstructError(
                "mapping ended before its pending value completed"
            )
        self.frames.pop()
        if self.frames:
            parent = self._frame()
            parent.pending = None
            parent.repeated = False

    def consume(self, events: Iterable[SelectionEvent]) -> None:
        """Consume one syntax-valid semantic event stream."""
        for event in events:
            if isinstance(event, BeginMapping):
                self._begin()
            elif isinstance(event, DecodedKey):
                self._key(event.value)
            elif isinstance(event, KeptValue):
                self._value(event.value)
            elif isinstance(event, DiscardedValue):
                self._discard()
            elif isinstance(event, EndMapping):
                self._end()

    def finish(self, syntax_failure: str | None = None) -> Selection:
        """Prefer syntax failure, then semantic verdicts, then result."""
        if syntax_failure is not None:
            raise SyntaxError(syntax_failure)
        if self.frames:
            raise UnsupportedConstructError("selection mapping did not finish")
        if self.verdicts:
            raise UnsupportedConstructError(self.verdicts[0])
        return {
            path: self.retained[path] for path in self.order if path in self.retained
        }


def prove_selection_contract() -> None:
    """Pin ordering, absence, ownership, nesting, discard, and refusal."""
    model_type = IrStr("BPE")
    machine = SelectionMachine(
        {"version": KEEP, "model": {"type": KEEP}, "missing": KEEP}
    )
    machine.consume(
        (
            BeginMapping(),
            DecodedKey("extension"),
            DiscardedValue(),
            DecodedKey("model"),
            BeginMapping(),
            DecodedKey("unused"),
            DiscardedValue(),
            DecodedKey("type"),
            KeptValue(model_type),
            EndMapping(),
            DecodedKey("version"),
            KeptValue(IrInt(3)),
            EndMapping(),
        )
    )
    selected = machine.finish()
    assert tuple(selected) == (("version",), ("model", "type"))
    assert selected[("model", "type")] is model_type
    assert ("missing",) not in selected

    duplicate = SelectionMachine({"model": KEEP})
    duplicate.consume(
        (
            BeginMapping(),
            DecodedKey("model"),
            KeptValue(IrStr("first")),
            DecodedKey("model"),
            KeptValue(IrStr("second")),
            EndMapping(),
        )
    )
    try:
        duplicate.finish("unterminated string")
    except SyntaxError:
        pass
    else:
        raise AssertionError("semantic refusal outranked syntax")
    try:
        duplicate.finish()
    except UnsupportedConstructError as error:
        assert "repeats decoded key" in str(error)
    else:
        raise AssertionError("repeated decoded key was accepted")

    wrong_shape = SelectionMachine({"model": {"type": KEEP}})
    wrong_shape.consume(
        (
            BeginMapping(),
            DecodedKey("model"),
            KeptValue(IrStr("not a mapping")),
            EndMapping(),
        )
    )
    try:
        wrong_shape.finish()
    except UnsupportedConstructError as error:
        assert "requires a mapping" in str(error)
    else:
        raise AssertionError("nested selection accepted a scalar")


if __name__ == "__main__":
    prove_selection_contract()
    print("PASS: finite nested-mapping selection semantics")
