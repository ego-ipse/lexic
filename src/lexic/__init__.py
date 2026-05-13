"""Lexic — Grammar engine."""

from lexic.compile import compile_from_path, compile_text
from lexic.generate import generate
from lexic.parse import parse

__all__ = ["compile_from_path", "compile_text", "generate", "parse"]
