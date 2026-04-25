"""HelperRuleRegistry: one-per-build registry for synthesised helper rules."""

from __future__ import annotations

from lexic.ir.spec import RuleSpec


class HelperRuleRegistry:
    """Accumulates synthesised helper RuleSpecs during a single IR build pass.

    Created once per IRBuilder.build() call; not shared across builds.
    """

    def __init__(self) -> None:
        self._specs: list[RuleSpec] = []
        self._names: set[str] = set()

    def reserve(self, base_name: str) -> str:
        """Return a unique rule name derived from base_name without registering it."""
        if base_name not in self._names:
            return base_name
        suffix = 2
        while f"{base_name}{suffix}" in self._names:
            suffix += 1
        return f"{base_name}{suffix}"

    def register(self, spec: RuleSpec) -> None:
        """Add spec to the registry; raise ValueError if the name is already taken."""
        if spec.rule_name in self._names:
            raise ValueError(f"Helper rule {spec.rule_name!r} already registered")
        self._names.add(spec.rule_name)
        self._specs.append(spec)

    def all_specs(self) -> list[RuleSpec]:
        """Return all registered specs in registration order."""
        return list(self._specs)
