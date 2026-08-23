"""Every test in this lane carries the ``concurrency`` marker, automatically.

Marking the directory rather than each file is what keeps the phased runner
honest: a test added here is deselected from the parallel bulk phase the
moment it exists, with nobody having to remember a decorator. A lane test that
leaked into the xdist phase would not fail — it would pass, slowly and
serialised, having proven far less than it claims.
"""

from __future__ import annotations

from pathlib import Path

import pytest

LANE = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply ``concurrency`` to items collected under THIS directory.

    The hook is global — a directory ``conftest`` still sees every item in the
    session — so the path test is what keeps the mark from landing on the
    whole suite. Without it both lane markers match everything, and the
    phased runner silently partitions nothing.
    """
    for item in items:
        if LANE in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.concurrency)
