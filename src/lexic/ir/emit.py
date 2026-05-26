"""render_specs — render a list of RuleSpec back to grammar text via a flavour."""

from __future__ import annotations

from collections.abc import Callable

from lexic.ir.nodes import IrNode


def render_specs(specs: list, flavour: Callable[[IrNode], str]) -> str:
    """Render a list of RuleSpecs to a grammar text string.

    :param specs: Topologically sorted list of RuleSpec instances.
    :param flavour: An IrFlavour singleton (callable from IrEmitter); takes
        an IrNode and returns its rendered string.
    :returns: Newline-joined rule strings, with a trailing newline.
    """
    rules = [spec.to_ir_rule() for spec in specs]
    return "\n".join(flavour(rule) for rule in rules) + "\n"
