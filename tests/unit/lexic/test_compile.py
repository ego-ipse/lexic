import time
from pathlib import Path

import pytest

from lexic.compile import (
    CompiledGrammar,
    compile,
    compile_from_path,
    reset_cache_for_tests,
)

GROUND_TRUTH = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"


@pytest.fixture(autouse=True)
def clear_cache():
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def test_compile_from_path_returns_compiled_grammar():
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    assert isinstance(cg, CompiledGrammar)
    assert cg.classes
    assert isinstance(cg.specs, dict)
    assert cg.specs


def test_compile_from_path_memoises_by_path_mtime_size():
    src = GROUND_TRUTH / "arithmetic.gbnf"
    cg1 = compile_from_path(src)
    cg2 = compile_from_path(src)
    assert cg1 is cg2


def test_compile_from_path_invalidates_on_mtime_change(tmp_path):
    src = tmp_path / "g.gbnf"
    src.write_text('root ::= "a"\n')
    cg1 = compile_from_path(src)
    time.sleep(0.01)
    src.write_text('root ::= "b"\n')
    cg2 = compile_from_path(src)
    assert cg1 is not cg2


def test_compile_from_path_invalidates_on_size_change_same_mtime(tmp_path, monkeypatch):
    """Same mtime but different size should invalidate."""
    src = tmp_path / "g.gbnf"
    src.write_text('root ::= "aa"\n')
    cg1 = compile_from_path(src)
    original_mtime = src.stat().st_mtime
    src.write_text('root ::= "bbb"\n')
    import os

    os.utime(src, (original_mtime, original_mtime))
    cg2 = compile_from_path(src)
    assert cg1 is not cg2


def test_compile_no_cache_by_default():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg1 = compile(text)
    cg2 = compile(text)
    assert cg1 is not cg2  # no cache_key → no memoization


def test_compile_with_cache_key():
    text = (GROUND_TRUTH / "arithmetic.gbnf").read_text()
    cg1 = compile(text, cache_key="fixture-a")
    cg2 = compile(text, cache_key="fixture-a")
    assert cg1 is cg2


def test_compile_and_compile_from_path_share_cache():
    """compile_from_path(path) should cache-hit after compile(text, cache_key=key)."""
    path = GROUND_TRUTH / "arithmetic.gbnf"
    resolved = str(path.resolve())
    stat = path.stat()
    key = (resolved, stat.st_mtime, stat.st_size, "gbnf")
    cg1 = compile(path.read_text(), cache_key=key)
    cg2 = compile_from_path(path)
    assert cg1 is cg2


def test_compiled_grammar_parse_roundtrips():
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    inst = cg.parse("x=1\n")
    assert inst.to_text() == "x=1\n"


def test_repeated_parse_is_fast():
    cg = compile_from_path(GROUND_TRUTH / "arithmetic.gbnf")
    cg.parse("x=1\n")  # warm
    start = time.perf_counter()
    for _ in range(100):
        cg.parse("x=1\n")
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"100 cached parses took {elapsed:.3f}s"
