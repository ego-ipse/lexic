"""Root conftest: shared pytest fixtures for the full test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.paths import GROUND_TRUTH


@pytest.fixture(scope="session")
def ground_truth() -> Path:
    return GROUND_TRUTH
