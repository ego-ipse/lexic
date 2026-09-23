"""Every clone a compiled grammar holds is a clone a field walk can reach.

This test exists because an instrument got it wrong. A census of
:class:`FlatClone` slots walked the program through ``selectors`` alone — but a
clone selecting its arms by a wide selection leaves ``selectors`` empty and
holds them elsewhere, so that clone was never visited and neither was anything
below it. The census reported a third fewer clones than exist, and on that
undercount two record overlays were proposed that would have built wrong
models.

The lesson was not "walk more edges". It was **count the population by a second
route before trusting the first**, and the second route has to be one that
cannot share the first's blind spot:

* the **walk** reads named fields, the way every consumer does;
* the **oracle** is :func:`gc.get_referents` from the compiled tables, which is
  field-name blind — it follows a reference without knowing what holds it, so
  it structurally cannot forget an edge. An oracle that knew the field names
  would be a second copy of the walk, and two wrong instruments agreeing look
  exactly like two right ones.

:func:`test_a_crippled_walk_is_caught` is what keeps that honest: a walk with a
known hole must fail, or this module proves nothing.

The two routes also start from different places, and their agreeing says
something no other test does. The oracle roots at the whole ``PdaTables``; the
walk roots at ``tables.program.start``. Equal sets therefore mean **every clone
the artefact holds anywhere is reachable from the program's entry** — no
delegate or orphan clone sits outside that graph.
"""

from __future__ import annotations

import gc
from types import BuiltinFunctionType, FunctionType, ModuleType

import pytest

from lexic.parsing.pda.compiler.program.flatten import FlatClone, PdaProgram
from lexic.parsing.products import _model_product
from tools.benchmark.cases.grammars import BENCHES, Bench

EDGES = (
    "selectors",
    "wide_selectors",
    "default",
    "attempt",
    "runarm",
    "chartable",
)
"""Slots that hold, or nest, an arm or a clone.

``struct_arm`` is deliberately absent: a ``ScanGate`` reaches no clone. The
oracle does not consult this list, which is the point of having it.
"""

_OPAQUE = (type, ModuleType, FunctionType, BuiltinFunctionType)
"""Never descended into.

An instance reaches its type, a type its methods, a method its module globals,
and from there the whole interpreter is three steps away. The fence is what
keeps the oracle's closure the artefact's and not the process's.
"""


def _spread(value: object, stack: list[object]) -> None:
    """Push every object nested anywhere inside a slot's value.

    Shape-agnostic deliberately. A clone sits in ``arm.payloads[i]`` under any
    of several op-codes, an attempt entry carries its sub-clone in the last of
    five fields, and a dispatch clone holds clones in ``selectors`` where every
    other clone holds arms. Unpacking by arity or by op-code would encode all
    three and go stale when the next one changes; pushing everything and
    keeping whatever turns out to be a clone cannot.
    """
    if isinstance(value, (tuple, list)):
        for item in value:
            _spread(item, stack)
    elif isinstance(value, dict):
        for item in value.values():
            _spread(item, stack)
    elif value is not None:
        stack.append(value)


def walked(program: PdaProgram, edges: tuple[str, ...] = EDGES) -> set[int]:
    """Clone ids reachable from ``program`` through the named fields.

    An island reference's payload names its rule (a string, once the payload
    is spread), and the program's delegate source holds the interior clones
    compiled for that island so far: that is the edge from the reference to
    them. Any other name holds none. They are compiled on first use, so
    which are held depends on what the process has parsed.
    """
    seen: set[int] = set()
    delegates = program.delegates
    stack: list[object] = [program.start]
    while stack:
        node = stack.pop()
        _spread(getattr(node, "payloads", None), stack)
        if delegates is not None and isinstance(node, str):
            _spread(delegates.held(node), stack)
        if not isinstance(node, FlatClone) or id(node) in seen:
            continue
        seen.add(id(node))
        for slot in edges:
            _spread(getattr(node, slot), stack)
    return seen


def _closure(root: object) -> tuple[list[object], list[FunctionType]]:
    """Objects reachable from ``root``, and the functions the fence dropped.

    The second list is not a by-product: it is the one place the two routes
    could share a blind spot, so it is handed back to be checked rather than
    discarded. See :func:`test_no_clone_hides_in_a_closure_cell`.
    """
    seen: set[int] = {id(root)}
    out: list[object] = [root]
    dropped: list[FunctionType] = []
    stack: list[object] = [root]
    while stack:
        for child in gc.get_referents(stack.pop()):
            if id(child) in seen:
                continue
            seen.add(id(child))
            if isinstance(child, _OPAQUE):
                if isinstance(child, FunctionType):
                    dropped.append(child)
                continue
            out.append(child)
            stack.append(child)
    return out, dropped


def referenced(root: object) -> dict[int, FlatClone]:
    """The clones in ``root``'s reference closure, by id — field names unread.

    The oracle. :func:`gc.get_referents` answers "what does this object point
    at" without being told where it keeps it, so a slot this test has never
    heard of is followed anyway.
    """
    reached, _dropped = _closure(root)
    return {id(one): one for one in reached if isinstance(one, FlatClone)}


def _names(found: dict[int, FlatClone], ids: set[int]) -> list[str]:
    """The rule names behind a set of clone ids, for a failure message."""
    return sorted(found[one].name or "<inline group>" for one in ids if one in found)


@pytest.mark.parametrize("bench", BENCHES, ids=lambda one: one.name)
def test_the_walk_reaches_every_clone_the_artefact_holds(bench: Bench) -> None:
    """Per grammar, the field walk and the reference closure are one set."""
    tables = _model_product(bench.compiled.codegen_grammar, bench.compiled.product).pda
    oracle = referenced(tables)
    found = walked(tables.program)

    missed = set(oracle) - found
    extra = found - set(oracle)
    assert not missed, (
        f"{bench.name}: the walk missed {len(missed)} of {len(oracle)} clones — "
        f"an edge is absent from {EDGES}: {_names(oracle, missed)}"
    )
    assert not extra, (
        f"{bench.name}: the walk reached {len(extra)} clones the artefact does "
        "not hold — it escaped its own root"
    )


def test_a_crippled_walk_is_caught() -> None:
    """A walk with a known hole must DISAGREE with the oracle.

    Without this the module's own agreement means nothing: two instruments
    that share a blind spot agree exactly as loudly as two that are right.
    The hole chosen is the original one — follow ``selectors`` and no other
    field, which is what reported a third of the roster missing.
    """
    bench = next(one for one in BENCHES if one.name == "gbnf-meta")
    tables = _model_product(bench.compiled.codegen_grammar, bench.compiled.product).pda

    blind = walked(tables.program, edges=("selectors",))

    assert blind < set(referenced(tables)), "a one-edge walk must not see it all"


@pytest.mark.parametrize("bench", BENCHES, ids=lambda one: one.name)
def test_no_clone_hides_in_a_closure_cell(bench: Bench) -> None:
    """The one blind spot the two routes SHARE, asserted empty per grammar.

    The fence stops the oracle at a function, and the walk reads named slots,
    so neither opens a closure: a clone captured in a cell is invisible to
    both, and they would agree about a number that is wrong. That is not
    hypothetical — ``clone.build`` and a fold's ``step`` are composed closures
    already. True today, so it is asserted rather than assumed.
    """
    tables = _model_product(bench.compiled.codegen_grammar, bench.compiled.product).pda
    _reached, dropped = _closure(tables)

    captured: list[object] = []
    for function in dropped:
        for cell in function.__closure__ or ():
            try:
                _spread(cell.cell_contents, captured)
            except ValueError:
                continue  # an empty cell — a recursive closure not yet bound

    hidden = [
        one.name or "<inline group>" for one in captured if isinstance(one, FlatClone)
    ]
    assert not hidden, (
        f"{bench.name}: {len(hidden)} clone(s) reachable ONLY through a closure "
        f"cell, which neither route follows: {sorted(hidden)}"
    )


def test_the_closure_check_can_see_a_captured_clone() -> None:
    """The cell check must FIRE, or its sixteen green rows say nothing.

    A first attempt at this control captured a module global, which compiles
    to no cell at all and reported a clean miss — the detector looked broken
    and was not. Both shapes are pinned: a clone held bare in a cell, and one
    held inside a container in a cell.
    """
    clone = FlatClone.__new__(FlatClone)
    clone.name = "planted"

    def hold(value: object) -> FunctionType:
        def captured() -> object:
            return value

        return captured

    for held in (clone, (clone,)):
        found: list[object] = []
        for cell in hold(held).__closure__ or ():
            _spread(cell.cell_contents, found)
        assert any(isinstance(one, FlatClone) for one in found)


def test_a_clone_carries_no_completion_index() -> None:
    """The slot is gone, not merely unread.

    It was written once at bake and read nowhere, so it recorded provenance no
    consumer asked for — and it was never assigned at all on the attempt
    sub-clones, which do not pass through that bake. A reader that one day
    needs it brings the slot back with itself, populated on every path.
    """
    assert "completion" not in FlatClone.__slots__
