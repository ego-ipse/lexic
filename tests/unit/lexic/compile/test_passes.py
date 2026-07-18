"""Tests for compile/passes.py — hoist groups, hoist arms, relax noise.

The actual test bodies live in :mod:`tests.unit.lexic.compile.passes_cases`, bound here to
:mod:`lexic.compile.passes`.
"""

from __future__ import annotations

from lexic.compile import passes
from tests.unit.lexic.compile.passes_cases import make_passes_tests

globals().update(make_passes_tests(passes))
