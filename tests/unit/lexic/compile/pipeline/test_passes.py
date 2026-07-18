"""Tests for compile/passes.py — hoist groups, hoist arms, relax noise.

The actual test bodies live in :mod:`tests.unit.lexic.compile.pipeline.passes_cases`, bound here to
:mod:`lexic.compile.pipeline.passes`.
"""

from __future__ import annotations

from lexic.compile.pipeline import passes
from tests.unit.lexic.compile.pipeline.passes_cases import make_passes_tests

globals().update(make_passes_tests(passes))
