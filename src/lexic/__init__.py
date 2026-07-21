"""Lexic — Grammar engine."""

from lexic.compile import (
    compile_from_path,
    compile_text,
    parse_grammar,
    parse_instance,
    parse_instance_from_path,
)
from lexic.generate import generate

__all__ = [
    "compile_from_path",
    "compile_text",
    "generate",
    "parse_instance",
    "parse_instance_from_path",
    "parse_grammar",
]
