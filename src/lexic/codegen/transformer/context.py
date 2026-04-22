"""Protocol types for FieldBuilder dispatch.

Per design spec §Q1: BuildContext is frozen; orchestrator owns cursor.
Builders return FieldResult | SkipField (tagged union, no sentinels).

FieldBuilder (the Protocol) lives here — next to the types it quantifies
over (BuildContext, BuildResult) — so that builders.py implements it and
registry.py consumes it without creating a registry→builders→registry
import cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from lexic.ir import Atom, RuleSpec


@dataclass(frozen=True)
class BuildContext:
    spec: RuleSpec
    children: tuple[Any, ...]
    hints: Mapping[str, type]
    cursor: int = 0

    def peek(self) -> Any | None:
        return self.children[self.cursor] if self.cursor < len(self.children) else None

    def exhausted(self) -> bool:
        return self.cursor >= len(self.children)


@dataclass(frozen=True)
class SkipField:
    """Signal: do not include this field in kwargs."""


SKIP_FIELD = SkipField()


@dataclass(frozen=True)
class FieldResult:
    value: Any
    consumed: int


BuildResult = FieldResult | SkipField


class FieldBuilder(Protocol):
    def build(self, atom: Atom, field_name: str, ctx: BuildContext) -> BuildResult: ...
