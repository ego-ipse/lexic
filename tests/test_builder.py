# tests/test_builder.py
"""Tests that builder.py runs and produces importable output."""
import subprocess
import sys
from pathlib import Path


def test_builder_runs():
    """builder.py must exit 0."""
    result = subprocess.run(
        [sys.executable, "builder.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, f"builder.py failed:\n{result.stderr}"


def test_generated_models_importable():
    """Generated models.py must be importable."""
    result = subprocess.run(
        [sys.executable, "-c", "from vyx.models import Packet, Body, BodyLine"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
        env={**__import__("os").environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
    )
    assert result.returncode == 0, f"Import failed:\n{result.stderr}"


def test_generated_parser_importable():
    """Generated parser.py must be importable."""
    result = subprocess.run(
        [sys.executable, "-c", "from vyx.parser import parse"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
        env={**__import__("os").environ, "PYTHONPATH": str(Path(__file__).parent.parent / "src")},
    )
    assert result.returncode == 0, f"Import failed:\n{result.stderr}"
