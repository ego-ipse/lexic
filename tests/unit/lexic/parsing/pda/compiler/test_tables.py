"""Tests for lexic.parsing.pda.compiler.tables — PdaTables, the compiled
predictive-parser artifact.

The clone table's own shape (islands, cloning residue) is pinned in depth in
``tests/unit/lexic/parsing/pda/compiler/test_clones.py``; this file targets
``PdaTables``'s own accessor surface: ``islands``, the Earley tables it holds
(``island_tables``, ``product_tables``, a replica's copies), ``island_delegates``,
and ``reset_delegate_cache``.
"""

from __future__ import annotations

import threading
from collections.abc import Collection

import pytest

from lexic.compile import compile_text
from lexic.ir import IrAst
from lexic.parsing import executable
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.records import ORIGIN_BITS, ParserTables
from lexic.parsing.pda.compiler import tables as tables_module
from lexic.parsing.pda.compiler.program.flatten import PdaProgram
from lexic.parsing.pda.compiler.tables import PdaTables
from lexic.parsing.products import declare_replica, earley_model, model_product
from tests.split_helpers import FiledDuringRead
from tests.unit.lexic.parsing.pda.compiler.test_clones import (
    pda_from_text,
    specs_from_text,
)

LEFT_RECURSIVE = 'root ::= x\nx ::= y "a" | "b"\ny ::= x\n'
"""INDIRECT left recursion — `x` reaches itself through `y`.

Direct left recursion no longer islands: the fold rewrites `A ::= A β | γ` to
`(γ)(β)*` and builds the model back
(:mod:`lexic.parsing.pda.compiler.leftrec.rewrite`). What still islands is the
recursion the fold refuses, and this is the smallest such shape — a fixture for
island behaviour has to be one the fold does not take, or it pins nothing."""


def test_program_and_clones_are_populated_after_compilation():
    """A trivial grammar still yields a real program, and real clones behind it."""
    pda = pda_from_text('root ::= "x"\n')
    assert isinstance(pda.program, PdaProgram)
    assert specs_from_text('root ::= "x"\n').clones  # at least the root clone


def test_the_artefact_does_not_carry_the_authored_clone_specs():
    """The specs are a compile-time intermediate and do not survive lowering.

    Holding them beside the program kept a fifth to two fifths of the
    artefact's GC-tracked population alive with nothing reading it, so the
    absence is the point and belongs in a test rather than only in a docstring.
    """
    pda = pda_from_text('root ::= "x"\n')
    assert not hasattr(pda, "clones")
    assert "clones" not in type(pda).__slots__


def test_islands_is_the_compilers_island_set():
    """``islands`` is the compiler's residue, carried as a plain set.

    It used to be the key set of a per-island FOLLOW map. The values of that
    map were the seam's two-ends evidence and are now wrong for the job — the
    set a two-ends check needs is what the island's REFERENCES are followed
    by — so the evidence moved onto the reference and the map became a dict
    nothing read the values of.
    """
    pda = pda_from_text(LEFT_RECURSIVE)
    assert not hasattr(pda, "island_follow")
    assert isinstance(pda.islands, frozenset)
    assert "x" in pda.islands


def test_island_tables_returns_a_parser_tables_instance():
    """The Earley sub-parser tables for an island rule."""
    pda = pda_from_text(LEFT_RECURSIVE)
    tables = pda.island_tables("x")
    assert isinstance(tables, ParserTables)


def test_island_tables_is_memoised_by_identity_per_name():
    """Repeat calls for the same name return the identical object."""
    pda = pda_from_text(LEFT_RECURSIVE)
    first = pda.island_tables("x")
    second = pda.island_tables("x")
    assert first is second


def test_island_tables_differs_by_packing_tier():
    """Different packing tiers compile distinct tables, even for the same rule."""
    pda = pda_from_text(LEFT_RECURSIVE)
    small = pda.island_tables("x", bits=8)
    default = pda.island_tables("x")
    assert small is not default


def test_island_delegates_is_empty_when_nothing_delegates():
    """An island with no delegable interior clones returns an empty dict."""
    pda = pda_from_text('root ::= "x"\n')
    assert pda.island_delegates("nonexistent") == {}


def test_reset_delegate_cache_does_not_raise():
    """The cache-reset seam is safe to call even after populating the cache."""
    pda = pda_from_text(LEFT_RECURSIVE)
    pda.island_delegates("x")
    pda.reset_delegate_cache()  # must not raise, whether or not anything delegated


def test_a_replica_copies_every_island_its_origin_holds_at_once() -> None:
    """``copy_held_tables`` gives a worker's replica its own copy of each island
    table and delegate set its origin has met — made now, not on each island's
    first meeting in a later parse — and does nothing on tables a compile built.

    The replica is made the way a pool worker's is (a view declared on the
    original pair, its product copied through the binding), so the copy keeps
    by identity exactly what production keeps.
    """
    compiled = compile_text(LEFT_RECURSIVE, cache_key="copy-held-islands")
    grammar, binding = compiled.codegen_grammar, compiled.product
    view = (IrAst(grammar.rules, grammar.start), binding.replica())
    declare_replica(grammar, binding, *view)
    origin = model_product(grammar, binding, ORIGIN_BITS).pda
    replica = model_product(*view, ORIGIN_BITS).pda
    island = sorted(origin.islands)[0]
    held = origin.island_tables(island)
    origin.island_delegates(island)

    replica.copy_held_tables()

    assert (island, ORIGIN_BITS, False) in replica.held_tables()
    copied = replica.island_tables(island, ORIGIN_BITS)
    assert copied is not held, "a copy, not the origin's own tables"
    assert isinstance(copied, ParserTables)
    delegates = replica.program.delegates
    if origin.program.delegates is not None:
        assert delegates is not None and island in delegates.held_islands()
    origin.copy_held_tables()  # no origin: nothing to do, nothing raised


def test_copying_held_islands_reads_what_the_origin_is_still_filing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A worker copies the islands its origin holds while another thread,
    parsing on that origin, compiles one more: the copy reads snapshots of the
    origin's island tables and delegate sets, so it neither raises nor misses
    what was held."""
    compiled = compile_text(LEFT_RECURSIVE, cache_key="copy-held-islands-filing")
    grammar, binding = compiled.codegen_grammar, compiled.product
    view = (IrAst(grammar.rules, grammar.start), binding.replica())
    declare_replica(grammar, binding, *view)
    origin = model_product(grammar, binding, ORIGIN_BITS).pda
    replica = model_product(*view, ORIGIN_BITS).pda
    island = sorted(origin.islands)[0]
    origin.island_tables(island)
    origin.island_delegates(island)
    held = origin.held_tables()
    monkeypatch.setattr(origin, "_earley", FiledDuringRead(held))
    sources = origin.program.delegates
    assert sources is not None, "every compiled program carries its delegate source"
    cache = {name: sources.held(name) for name in sources.held_islands()}
    assert island in cache
    monkeypatch.setattr(sources, "_cache", FiledDuringRead(cache))

    replica.copy_held_tables()

    assert (island, ORIGIN_BITS, False) in replica.held_tables()
    copies = replica.program.delegates
    assert copies is not None and island in copies.held_islands()


# ── the product's collapsed tables: held beside the islands, built on first use


def _compiled(cache_key: str):
    """``LEFT_RECURSIVE`` compiled under its own key: a fresh product."""
    compiled = compile_text(LEFT_RECURSIVE, cache_key=cache_key)
    return compiled.codegen_grammar, compiled.product


def _origin_and_replica(cache_key: str):
    """An original product and a pool-worker view's, made as production makes them."""
    grammar, binding = _compiled(cache_key)
    view = (IrAst(grammar.rules, grammar.start), binding.replica())
    declare_replica(grammar, binding, *view)
    origin = model_product(grammar, binding, ORIGIN_BITS)
    return origin, model_product(*view, ORIGIN_BITS)


def _arm_ids(grammar: IrAst) -> set[int]:
    return {id(arm) for rule in grammar.rules for arm in rule.body}


def test_a_product_without_a_replica_builds_no_tables_on_a_pda_parse() -> None:
    """The collapsed tables wait for an Earley use: a parse the PDA finishes
    alone leaves none held."""
    compiled = compile_text('root ::= "x" "y"*\n', cache_key="pda-only-no-tables")
    compiled.parse("xyy")
    product = model_product(compiled.codegen_grammar, compiled.product, tier_for(3))
    assert [key for key in product.pda.held_tables() if key[2]] == []


def test_concurrent_first_uses_build_the_product_tables_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Eight threads asking at once share one build: the rest wait on the miss
    lock, so the build never meets a second caller."""
    grammar, binding = _compiled("product-tables-once")
    product = model_product(grammar, binding, ORIGIN_BITS)
    calls: list[int] = []
    inside = threading.Barrier(2)
    build = tables_module.collapsed_product_tables

    def counted(grammar: IrAst, rules: Collection[str], bits: int) -> ParserTables:
        calls.append(1)
        try:
            inside.wait(timeout=0.5)  # a second concurrent builder would meet here
        except threading.BrokenBarrierError:
            pass
        return build(grammar, rules, bits)

    monkeypatch.setattr(tables_module, "collapsed_product_tables", counted)
    start = threading.Barrier(8)
    got: list[ParserTables] = []

    def ask() -> None:
        start.wait()
        got.append(product.pda.product_tables(ORIGIN_BITS, binding.routines))

    threads = [threading.Thread(target=ask) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(calls) == 1
    assert len(got) == 8 and all(tables is got[0] for tables in got)


def test_a_product_holds_its_tables_once() -> None:
    """Every read is the one held object, bound on the product after the
    first, so later reads are an attribute lookup."""
    grammar, binding = _compiled("product-tables-held")
    product = model_product(grammar, binding, ORIGIN_BITS)
    assert "tables" not in vars(product), "nothing is bound before the first read"
    assert product.tables is product.tables
    assert product.tables is product.pda.product_tables(product.bits, binding.routines)
    assert vars(product)["tables"] is product.tables, "bound as a plain attribute"
    assert product.instance_grammar is product.pda.instance_grammar
    assert len(vars(product)) == 5, "four fields and the bound tables, no more"


def test_a_replica_holds_the_product_tables_from_its_creation() -> None:
    """Made before any fallback, a replica already holds its own copy — over
    its own arms, with its own caches — so its first fallback finds it there,
    as when the product compiled the tables eagerly; and it parses alike."""
    origin, replica = _origin_and_replica("product-tables-replica")
    key = (str(origin.instance_grammar.start), ORIGIN_BITS, True)
    mine, theirs = replica.pda.held_tables()[key], origin.pda.held_tables()[key]
    assert mine is replica.tables and mine is not theirs
    assert mine.terms is not theirs.terms and mine.decode is not theirs.decode
    held = {id(arm) for arm in mine.decode.arm_seqs}
    assert held & _arm_ids(replica.instance_grammar)
    assert not held & _arm_ids(origin.instance_grammar)
    expected = earley_model(origin.instance_grammar, "ba", origin.binding, theirs)
    got = earley_model(replica.instance_grammar, "ba", replica.binding, mine)
    assert got == expected


def test_a_warm_copies_every_missing_table_in_one_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two islands and a product table at a new tier, built after the replica:
    one warm copies all three with one constants sweep, over the replica's arms."""
    origin, replica = _origin_and_replica("product-tables-one-copy")
    island = sorted(origin.pda.islands)[0]
    origin.pda.island_tables(island, ORIGIN_BITS)
    origin.pda.island_tables(island, 8)
    origin.pda.product_tables(8, origin.binding.routines)
    late = {(island, ORIGIN_BITS, False), (island, 8, False)}
    late.add((str(origin.instance_grammar.start), 8, True))
    assert not late & set(replica.pda.held_tables())
    sweeps: list[int] = []
    sweep = executable.process_constants

    def counted() -> dict[int, object]:
        sweeps.append(1)
        return sweep()

    monkeypatch.setattr(executable, "process_constants", counted)
    replica.pda.copy_held_tables()
    assert len(sweeps) == 1
    held = replica.pda.held_tables()
    assert late <= set(held)
    copied = {id(arm) for key in late for arm in held[key].decode.arm_seqs}
    assert copied & _arm_ids(replica.instance_grammar)
    assert not copied & _arm_ids(origin.instance_grammar)


def test_a_table_built_after_the_last_warm_is_copied_on_first_use() -> None:
    """The lazy miss: a replica asked for a tier its origin built after the
    replica's creation copies it then, over its own arms."""
    origin, replica = _origin_and_replica("product-tables-lazy")
    theirs = origin.pda.product_tables(8, origin.binding.routines)
    mine = replica.pda.product_tables(8, replica.binding.routines)
    assert mine is not theirs
    assert mine is replica.pda.product_tables(8, replica.binding.routines)
    held = {id(arm) for arm in mine.decode.arm_seqs}
    assert held & _arm_ids(replica.instance_grammar)
    assert not held & _arm_ids(origin.instance_grammar)


def test_the_tables_slots_are_the_holder_and_the_start_alone() -> None:
    """A replica copies nothing per worker beyond what the islands' holder
    always cost: one holder for every table, and a start name strings share."""
    slots = set(PdaTables.__slots__)
    assert len(slots) == 7
    assert {"_start", "_earley"} <= slots
    assert not slots & {"product_rules", "_island_tables"}
