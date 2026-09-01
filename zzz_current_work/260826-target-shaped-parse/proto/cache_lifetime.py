"""Typed bound-product cache whose entries die with the source artefact."""

from __future__ import annotations

import gc
import weakref
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from functools import partial
from threading import Barrier, Lock
from typing import NamedTuple

from lexic.compile import compile_ast
from lexic.compile.artifact import CompiledGrammar
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir.reduction import Reducer


class BoundProduct[Result]:
    """Result-only runner retained by one cache entry."""

    __slots__ = ("result",)

    def __init__(self, result: Result) -> None:
        self.result = result

    def run(self) -> Result:
        """Return the prototype result."""
        return self.result


class CacheKey(NamedTuple):
    """Identity key owned by one private compiler/artifact registry."""

    declaration: int
    grammar: int
    reducer: int


class MorphismDeclaration[Result](NamedTuple):
    """Public immutable signature/schema/algebra data and nothing mutable."""

    signature: frozenset[str]
    algebra: tuple[int, ...]


class BoundEntry[Result](NamedTuple):
    """Private entry with a weak source and stable declaration identity."""

    declaration: MorphismDeclaration[Result]
    grammar: weakref.ReferenceType[CompiledGrammar]
    reducer: Reducer
    bound: BoundProduct[Result]


class CallableFactory[Result]:
    """Typed cold builder protocol without an erased payload."""

    def __call__(
        self, grammar: CompiledGrammar, reducer: Reducer
    ) -> BoundProduct[Result]:
        """Build one bound product which does not retain ``grammar``."""
        raise NotImplementedError


def _release[Result](
    entries: dict[CacheKey, BoundEntry[Result]],
    lock: Lock,
    key: CacheKey,
    _grammar: weakref.ReferenceType[CompiledGrammar],
) -> None:
    """Drop one entry when its source artefact dies."""
    with lock:
        entries.pop(key, None)


class ArtifactBindings[Result]:
    """Private compiler/artifact owner of cache, lock, and cold factory."""

    __slots__ = ("_entries", "_factory", "_lock")

    def __init__(self, factory: CallableFactory[Result]) -> None:
        self._entries: dict[CacheKey, BoundEntry[Result]] = {}
        self._factory = factory
        self._lock = Lock()

    @property
    def entry_count(self) -> int:
        """Expose residency evidence without exposing the mutable registry."""
        return len(self._entries)

    def bind(
        self,
        declaration: MorphismDeclaration[Result],
        grammar: CompiledGrammar,
        reducer: Reducer,
    ) -> BoundProduct[Result]:
        """Read lock-free when warm; serialize and double-check cold binding."""
        key = CacheKey(id(declaration), id(grammar), id(reducer))
        cached = self._entries.get(key)
        if (
            cached is not None
            and cached.declaration is declaration
            and cached.grammar() is grammar
            and cached.reducer is reducer
        ):
            return cached.bound
        with self._lock:
            cached = self._entries.get(key)
            if (
                cached is not None
                and cached.declaration is declaration
                and cached.grammar() is grammar
                and cached.reducer is reducer
            ):
                return cached.bound
            bound = self._factory(grammar, reducer)
            source = weakref.ref(
                grammar,
                partial(_release, self._entries, self._lock, key),
            )
            self._entries[key] = BoundEntry(declaration, source, reducer, bound)
            return bound


class IntFactory(CallableFactory[int]):
    """Count cold builds without retaining their source grammar."""

    __slots__ = ("builds",)

    def __init__(self) -> None:
        self.builds = 0

    def __call__(self, grammar: CompiledGrammar, reducer: Reducer) -> BoundProduct[int]:
        """Build one source-independent result runner."""
        del reducer
        self.builds += 1
        return BoundProduct(len(grammar.grammar.rules))


def _concurrent_bind(
    barrier: Barrier,
    declaration: MorphismDeclaration[int],
    bindings: ArtifactBindings[int],
    grammar: CompiledGrammar,
) -> BoundProduct[int]:
    """Reach one cold cache key concurrently."""
    barrier.wait()
    return bindings.bind(declaration, grammar, JSON_REDUCER)


def prove_concurrent_first_bind() -> None:
    """One cold source/target pair compiles once under concurrent callers."""
    grammar = replace(
        compile_ast(JSON_GRAMMAR),
        stem="prototype-concurrent-cache",
    )
    factory = IntFactory()
    declaration = MorphismDeclaration[int](frozenset({"mapping"}), (1, 2))
    bindings = ArtifactBindings(factory)
    barrier = Barrier(8)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = tuple(
            pool.submit(
                _concurrent_bind,
                barrier,
                declaration,
                bindings,
                grammar,
            )
            for _ in range(8)
        )
        products = tuple(future.result() for future in futures)
    assert factory.builds == 1
    assert all(product is products[0] for product in products)


def prove_artefact_lifetime() -> None:
    """A private registry cannot retain a dead source artefact."""
    grammar = replace(
        compile_ast(JSON_GRAMMAR),
        stem="prototype-released-cache",
    )
    factory = IntFactory()
    declaration = MorphismDeclaration[int](frozenset({"mapping"}), (1, 2))
    bindings = ArtifactBindings(factory)
    pool_product = bindings.bind(declaration, grammar, JSON_REDUCER)
    source = weakref.ref(grammar)
    assert pool_product.run() == len(JSON_GRAMMAR.rules)
    assert bindings.entry_count == 1

    del grammar
    gc.collect()

    assert source() is None
    assert bindings.entry_count == 0
    assert pool_product.run() == len(JSON_GRAMMAR.rules)


def prove_declaration_is_data_only() -> None:
    """Public declaration exposes only recursively immutable values."""
    declaration = MorphismDeclaration[int](
        frozenset({"mapping", "scalar"}),
        (1, 2, 3),
    )
    assert declaration.signature == frozenset({"mapping", "scalar"})
    assert declaration.algebra == (1, 2, 3)
    assert not hasattr(declaration, "cache")
    assert not hasattr(declaration, "entries")
    assert not hasattr(declaration, "factory")
    assert not hasattr(declaration, "lock")
    assert not hasattr(declaration, "__dict__")
    assert isinstance(hash(declaration), int)


def main() -> None:
    """Run lifetime and concurrent-cold-bind proofs."""
    prove_declaration_is_data_only()
    prove_concurrent_first_bind()
    prove_artefact_lifetime()
    print("PASS: typed binding is single-build and artefact-bounded")


if __name__ == "__main__":
    main()
