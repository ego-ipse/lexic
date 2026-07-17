"""Tests for compile/binding.py — the per-rule binding view.

The actual test bodies live in :mod:`tests._binding_cases` (shared with the
``lexic.codegen.binding`` mirror — see that module's docstring for why),
bound here to :mod:`lexic.compile.binding`.
"""

from __future__ import annotations

from lexic.compile import binding
from tests._binding_cases import make_binding_tests

globals().update(make_binding_tests(binding))
