"""Generic conversion entry points — delegate to SequenceConverter protocol."""

from __future__ import annotations

from typing import TypeVar

from lexic.ir.atoms import Atom
from lexic.ir.helpers import HelperRuleRegistry
from lexic.ir.protocols import SequenceConverter

Node = TypeVar("Node")


def convert_value_str(
    body: Node,
    converter: SequenceConverter[Node],
) -> list[Atom]:
    """Convert a value_str rule body to atoms by asking the converter."""
    return converter.value_str_atoms(body)


def convert_sequence(
    body: Node,
    parent_class_name: str,
    helpers: HelperRuleRegistry,
    converter: SequenceConverter[Node],
) -> list[Atom]:
    """Convert a sequence rule body to atoms by asking the converter."""
    return converter.sequence_atoms(body, parent_class_name, helpers)
