"""Generic conversion: takes a SequenceConverter, returns atoms + field_map."""

from __future__ import annotations

from dataclasses import dataclass

from lexic.ir import HelperRuleRegistry, LiteralAtom, RuleRefAtom
from lexic.ir.convert import convert_sequence, convert_value_str


@dataclass(frozen=True)
class FakeBody:
    """A fake body node with just the fields needed for testing."""

    expected_atoms: list


class FakeConverter:
    """A fake SequenceConverter that returns the expected_atoms field of the body."""

    def value_str_atoms(self, body):
        """Return the atoms for a value_str rule, which we just take from the body."""
        return list(body.expected_atoms)

    def sequence_atoms(self, body, parent_class_name, helpers):
        """Return the atoms for a sequence rule, which we just take from the body."""
        assert isinstance(parent_class_name, str)
        assert helpers.all_specs() is not None
        return list(body.expected_atoms)


def test_convert_value_str_returns_atoms_from_converter():
    """convert_value_str should return the atoms as determined by the converter."""
    body = FakeBody(expected_atoms=[LiteralAtom(value="hi")])
    assert convert_value_str(body, FakeConverter()) == [LiteralAtom(value="hi")]


def test_convert_sequence_returns_atoms_from_converter():
    """convert_sequence should return the atoms as determined by the converter."""
    body = FakeBody(expected_atoms=[RuleRefAtom("x", 1, 1)])
    helpers = HelperRuleRegistry()
    out = convert_sequence(body, "Cls", helpers, FakeConverter())
    assert out == [RuleRefAtom("x", 1, 1)]
