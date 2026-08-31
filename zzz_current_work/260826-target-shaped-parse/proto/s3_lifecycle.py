"""Exercise the bound-product lifetime seam against the real caches protocol.

The four §3 exercises, plus the retention property that makes them safe:

1. **Explicit release** drops the entry, and the next bind is cold again.
2. **Collection** of the source artefact drops it too, with no explicit call —
   the weakref finalizer the `track` protocol installs does it.
3. **Concurrent first bind** compiles exactly once: N threads reaching an
   unbound declaration together get one object and one cold build.
4. **A pool-retained bound product still runs** after both release and
   collection, because it holds nothing of the source.

The retention property under all four: the registry's reference to the source
is weak, so a bound product never keeps its artefact alive.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import gc
import weakref
from threading import Barrier, Thread

from lexic.compile.product import BindingRegistry, ProgramProduct, lower_product
from lexic.parsing.product import (
    MeaningOp,
    OperandTables,
    PassOp,
    ProductProgram,
    RootOp,
    RuleProduct,
)
from lexic.parsing.caches import cached_entries, release


class _Source:
    """A stand-in compiled artefact — weak-referenceable, and disposable."""

    __slots__ = ("__weakref__", "name")

    def __init__(self, name: str) -> None:
        self.name = name


class _Declaration:
    """An inert declaration: no cache, no lock, no factory, no executor."""

    __slots__ = ("paths",)

    def __init__(self, *paths: str) -> None:
        self.paths = paths


REGISTRY: BindingRegistry[_Declaration, str] = BindingRegistry()
"""One registry for this witness's one declaration kind — a module-level
singleton, as the class requires."""


_EMPTY: OperandTables[str, str] = OperandTables((), (), (), (), (), (), (), ())


def _program() -> ProductProgram[str, str]:
    """One real lowered program — the thing a binding actually holds."""
    return lower_product(
        (RuleProduct((), PassOp(0)),), _EMPTY, root=RootOp(0), meaning=MeaningOp(0)
    )


def _build(declaration: _Declaration, source: _Source) -> ProgramProduct[str, str]:
    """Compile one bound product, retaining ONLY what compilation derived.

    The source's name is COPIED into the executor's own state rather than kept
    by reference: a bound product that held its artefact would make every
    artefact immortal, which is the retention this seam exists to bound.
    """
    derived = "-".join((source.name, *declaration.paths))

    def execute(program: ProductProgram[str, str], text: str, cores: int) -> str:
        del program, cores
        return f"{derived}:{text}"

    return ProgramProduct(_program(), execute)


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s3 lifecycle: {claim}")


def warm_lookup_is_the_same_object() -> None:
    """A second bind of the same pair returns the identical runner."""
    declaration, source = _Declaration("a"), _Source("g1")
    before = REGISTRY.binds
    first = REGISTRY.bind(declaration, source, _build)
    second = REGISTRY.bind(declaration, source, _build)
    _check("a warm bind rebuilt", first is second)
    _check("a warm bind compiled twice", REGISTRY.binds == before + 1)
    _check("the bound product does not run", first.run("x") == "g1-a:x")
    print(f"warm\tone object, one build\t{first.run('x')}")


def explicit_release_drops_the_entry() -> None:
    """`release` evicts, and the next bind is cold — same answer, new object."""
    declaration, source = _Declaration("b"), _Source("g2")
    first = REGISTRY.bind(declaration, source, _build)
    before = REGISTRY.binds

    release((id(source),))
    second = REGISTRY.bind(declaration, source, _build)
    _check("release did not evict", REGISTRY.binds == before + 1)
    _check("recompilation changed the binding's meaning", first.run("x") == second.run("x"))
    print("release\tevicted; rebind identical in meaning, fresh in identity")


def collection_drops_the_entry() -> None:
    """The source dying evicts its entries with no explicit call."""
    declaration = _Declaration("c")
    source = _Source("g3")
    watch = weakref.ref(source)
    REGISTRY.bind(declaration, source, _build)
    filled = cached_entries()

    del source
    gc.collect()
    _check("the source survived collection", watch() is None)
    _check("collection did not drop the entry", cached_entries() < filled)
    print(f"collection\tentries {filled} -> {cached_entries()}\tno explicit release")


def the_source_is_not_kept_alive() -> None:
    """Binding does not make an artefact immortal — the reference is weak."""
    declaration = _Declaration("d")
    source = _Source("g4")
    watch = weakref.ref(source)
    bound = REGISTRY.bind(declaration, source, _build)

    del source
    gc.collect()
    _check("the registry pinned its source artefact", watch() is None)
    _check("the retained runner stopped working", bound.run("x") == "g4-d:x")
    print("retention\tweak source; the bound product outlives it")


def concurrent_first_bind_compiles_once() -> None:
    """Eight threads reaching one unbound declaration compile it once."""
    declaration, source = _Declaration("e"), _Source("g5")
    workers = 8
    gate = Barrier(workers)
    seen: list[object] = []
    before = REGISTRY.binds

    def contend() -> None:
        gate.wait()
        seen.append(REGISTRY.bind(declaration, source, _build))

    threads = [Thread(target=contend) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    _check("a racing bind lost a result", len(seen) == workers)
    _check("racing binds got different objects", len({id(one) for one in seen}) == 1)
    _check(
        f"the cold miss compiled {REGISTRY.binds - before} times, not once",
        REGISTRY.binds == before + 1,
    )
    print(f"concurrency\t{workers} threads\tone object, one build")


def a_pool_keeps_running_after_release() -> None:
    """The pool-retention case: an explicit owner survives eviction AND death."""
    declaration = _Declaration("f")
    source = _Source("g6")
    pool = [REGISTRY.bind(declaration, source, _build)]

    release((id(source),))
    _check("the pooled runner broke on release", pool[0].run("x") == "g6-f:x")

    watch = weakref.ref(source)
    del source
    gc.collect()
    _check("the pool pinned the source", watch() is None)
    _check("the pooled runner broke on collection", pool[0].run("y") == "g6-f:y")
    print("pool\truns after release AND after the source is collected")


def main() -> None:
    """Run every exercise; any failure raises."""
    warm_lookup_is_the_same_object()
    explicit_release_drops_the_entry()
    collection_drops_the_entry()
    the_source_is_not_kept_alive()
    concurrent_first_bind_compiles_once()
    a_pool_keeps_running_after_release()
    print("s3 lifecycle\tPASS\trelease, collection, concurrent bind, pool retention")


if __name__ == "__main__":
    main()
