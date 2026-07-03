"""Shared path constants for the test suite."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GROUND_TRUTH = PROJECT_ROOT / "resources" / "ground_truth"
GENERATED = PROJECT_ROOT / "generated"
BENCHMARK = PROJECT_ROOT / "tools" / "benchmark"
