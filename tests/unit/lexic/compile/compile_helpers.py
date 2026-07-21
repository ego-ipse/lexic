"""Shared compile-package test helpers (round-trip assertions, hermetic imports)."""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

from lexic.compile import compile_from_path
from lexic.model import GrammarModel
from tests.paths import GROUND_TRUTH as GRAMMAR_DIR


def roundtrip(text: str, grammar: str) -> GrammarModel:
    """Assert a full parse round-trip for ``text`` against a ground-truth grammar.

    :param text: The instance text to parse.
    :param grammar: The ground-truth grammar's stem (e.g. ``"json_ws"``).
    :returns: The parsed model instance.
    :raises AssertionError: If ``to_text()`` does not reproduce ``text``, or a
        second parse of the round-tripped text does not ``dump()``-match.
    """
    gpath = GRAMMAR_DIR / f"{grammar}.gbnf"
    inst = compile_from_path(gpath).parse(text)
    assert inst is not None
    assert isinstance(inst, GrammarModel)

    roundtrip_str = inst.to_text()
    assert text == roundtrip_str, (
        f"to_text() mismatch for {grammar!r}:\n"
        f"  original:  {text!r}\n"
        f"  roundtrip: {roundtrip_str!r}"
    )

    rt = compile_from_path(gpath).parse(roundtrip_str)
    assert inst.dump() == rt.dump(), (
        f"dump() mismatch after round-trip for {grammar!r}:\n"
        f"  original:  {inst.dump()}\n"
        f"  roundtrip: {rt.dump()}"
    )
    return inst


def import_hermetic_module(path: Path, name: str) -> types.ModuleType:
    """Import a written module from disk, hermetically (its own namespace).

    :param path: The ``.py`` file to import.
    :param name: The module name to register it under.
    :returns: The imported, fully-executed module.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
