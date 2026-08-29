"""Arbitrary custom result classes through an immutable constructor symbol.

The impossibility boundary first: an *arbitrary runtime* class is reachable
only through (a) an object reference to the class itself, (b) a name looked up
by reflection, or (c) a mutable registry. (b) and (c) are forbidden by the
design; therefore the declaration must carry the class object. A class object
is callable, so a literal "no public callable field" is unsatisfiable for this
feature — the smallest contract change is: the declaration may carry exactly
one CLASS OBJECT as an immutable constructor symbol (never a bound callable,
lambda, factory, or executor), and that symbol is invoked only at root
finalization, never in a frequent completion.

The typing resolution: the private registry caches a result-free ``RecordPlan``
(the derived lowering — plain data), one homogeneous registry for the whole
declaration kind. The result-typed ``BoundRecord[Result]`` view is rebuilt per
bind from the immutable declaration plus the cached plan, so no heterogeneous
``dict`` ever erases ``Result`` and no cast exists anywhere.

Real boundary: value extraction runs the real ``compile_ast(JSON_GRAMMAR)
.reduce`` route as a stand-in for the direct product; what this file proves is
declaration shape, binding lifecycle, typing, and refusal — not throughput.
"""

from __future__ import annotations

import gc
import weakref
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import partial
from collections.abc import Hashable
from threading import Barrier, Lock
from typing import NamedTuple, assert_type

from lexic.compile import compile_ast
from lexic.compile.artifact import CompiledGrammar
from lexic.exceptions import FieldValidationError, UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrInt, IrMap, IrSelf, IrStr


class RecordSpec[Result](NamedTuple):
    """Public declaration: one constructor symbol plus named semantic paths.

    ``constructor`` is the one sanctioned class-object field. The record
    itself is immutable; no cache, lock, factory closure, or executor is
    reachable from it.
    """

    constructor: type[Result]
    fields: tuple[tuple[str, tuple[str, ...]], ...]

    def _bind(self, grammar: CompiledGrammar) -> BoundRecord[Result]:
        """Enter the one homogeneous plan registry for this declaration kind."""
        plan = _RECORD_PLANS.plan(self, grammar)
        return BoundRecord(self, plan)


class RecordPlan(NamedTuple):
    """The cached result-free lowering — plain data, no class, no callable."""

    parameter_order: tuple[str, ...]
    paths: tuple[tuple[str, ...], ...]
    constructor_name: str


class PlanKey(NamedTuple):
    """Value key: the hashable declaration itself beside one source identity.

    Keying by declaration VALUE (a ``RecordSpec`` is a hashable record) rather
    than ``id()`` removes the id-reuse hazard outright and makes equal
    declarations share one binding — the stronger reading of "stable
    declaration identity". ``Hashable`` is the honest bound a dict key needs;
    it is not an erasure because nothing ever reads the key back as a value.
    """

    declaration: Hashable
    grammar: int


class PlanEntry(NamedTuple):
    """One registry row: weak source artefact plus the derived plan."""

    grammar: weakref.ReferenceType[CompiledGrammar]
    plan: RecordPlan


def _release_plan(
    entries: dict[PlanKey, PlanEntry],
    lock: Lock,
    key: PlanKey,
    _grammar: weakref.ReferenceType[CompiledGrammar],
) -> None:
    """Drop one plan entry when its source artefact dies."""
    with lock:
        entries.pop(key, None)


def _derive_plan[Result](
    declaration: RecordSpec[Result], grammar: CompiledGrammar
) -> RecordPlan:
    """Cold lowering: validate the declaration's own data and freeze the plan.

    Deliberately does NOT inspect ``declaration.constructor``: Lexic never
    infers class shape or reads consumer code, so a class/field mismatch is a
    cold root-finalization failure on the first parse, not a binding check.
    """
    if not declaration.fields:
        raise UnsupportedConstructError(
            "record target: a constructor with no declared fields builds nothing"
        )
    names = tuple(name for name, _path in declaration.fields)
    if len(set(names)) != len(names):
        raise UnsupportedConstructError(
            f"record target: duplicate constructor field in {sorted(names)!r}"
        )
    for name, path in declaration.fields:
        if not path:
            raise UnsupportedConstructError(
                f"record target: field {name!r} declares an empty semantic path"
            )
    del grammar
    return RecordPlan(
        names,
        tuple(path for _name, path in declaration.fields),
        declaration.constructor.__qualname__,
    )


class PlanRegistry:
    """The one homogeneous private registry for the record declaration kind.

    Entries are result-free ``RecordPlan`` rows, so one registry serves every
    ``Result`` without a heterogeneous result-erasing value type. Warm lookup
    is lock-free; a cold miss is double-checked under the lock; entries die
    with their weakly-referenced source artefact.
    """

    __slots__ = ("_build_count", "_entries", "_lock")

    def __init__(self) -> None:
        self._build_count = 0
        self._entries: dict[PlanKey, PlanEntry] = {}
        self._lock = Lock()

    @property
    def build_count(self) -> int:
        """Expose cold-build evidence without exposing the mutable entries."""
        return self._build_count

    @property
    def entry_count(self) -> int:
        """Expose residency evidence."""
        return len(self._entries)

    def plan[Result](
        self, declaration: RecordSpec[Result], grammar: CompiledGrammar
    ) -> RecordPlan:
        """Bind once; eviction only ever causes equivalent recomputation."""
        key = PlanKey(declaration, id(grammar))
        cached = self._entries.get(key)
        if cached is not None and cached.grammar() is grammar:
            return cached.plan
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and cached.grammar() is grammar:
                return cached.plan
            plan = _derive_plan(declaration, grammar)
            self._build_count += 1
            source = weakref.ref(
                grammar, partial(_release_plan, self._entries, self._lock, key)
            )
            self._entries[key] = PlanEntry(source, plan)
            return plan

    def release(self, grammar: CompiledGrammar) -> None:
        """Explicitly drop every entry bound against ``grammar``."""
        with self._lock:
            stale = [key for key in self._entries if key.grammar == id(grammar)]
            for key in stale:
                del self._entries[key]


_RECORD_PLANS = PlanRegistry()


class BoundRecord[Result]:
    """Result-typed bound view: immutable declaration + cached plan, no cache.

    Rebuilt per ``_bind`` from write-once parts and — like the design's bound
    program — forbidden to retain the source artefact: the stand-in executor
    takes it per call where production embeds derived tables instead. It stays
    valid after the registry evicts its plan (a pool retaining this object
    retains everything it needs) and never enters a heterogeneous container.
    """

    __slots__ = ("declaration", "plan")

    def __init__(self, declaration: RecordSpec[Result], plan: RecordPlan) -> None:
        self.declaration = declaration
        self.plan = plan

    def run(self, grammar: CompiledGrammar, text: str) -> Result:
        """Parse once, then construct the class ONCE at root finalization.

        The extraction below rides the current reduce route as the direct
        product's stand-in; the class constructor runs exactly once, at the
        cold root boundary — never per entry, character, or completion.
        """
        document = grammar.reduce(text, JSON_REDUCER, cores=1)
        if not isinstance(document, IrMap):
            raise UnsupportedConstructError(
                "record target: the witness document is not a mapping"
            )
        arguments: dict[str, str | int] = {}
        for name, path in zip(self.plan.parameter_order, self.plan.paths):
            arguments[name] = _decode(_walk(document, path))
        return self.declaration.constructor(**arguments)


def _walk(document: IrMap, path: tuple[str, ...]) -> IrSelf:
    """Follow one decoded-key path into the reduced document."""
    value: IrSelf = document
    for key in path:
        if not isinstance(value, IrMap):
            raise UnsupportedConstructError(
                f"record target: path {path!r} crosses a non-mapping value"
            )
        value = value[IrStr(key)]
    return value


def _decode(value: IrSelf) -> str | int:
    """Engine-owned scalar decode for the two witness scalar sorts."""
    if isinstance(value, IrInt):
        return int(value)
    if isinstance(value, IrStr):
        return str(value)
    raise UnsupportedConstructError(
        f"record target: undeclared scalar sort {type(value).__name__}"
    )


@dataclass(frozen=True)
class TokenizerInfo:
    """A frozen record-like consumer class."""

    version: str
    vocab_size: int


class CheckedRange:
    """A consumer class whose constructor validates its inputs."""

    __slots__ = ("high", "low")

    def __init__(self, low: int, high: int) -> None:
        if low > high:
            raise FieldValidationError(f"range: {low} > {high}")
        self.low = low
        self.high = high


class Box[Item]:
    """A generic consumer result type."""

    __slots__ = ("item",)

    def __init__(self, item: Item) -> None:
        self.item = item


DOCUMENT = '{"version": "v1", "model": {"size": 7}, "low": 2, "high": 5}'
CONFLICT = '{"version": "v1"}'


def _spec_info() -> RecordSpec[TokenizerInfo]:
    """The beginner-shaped declaration for the frozen record witness."""
    return RecordSpec(
        TokenizerInfo,
        (("version", ("version",)), ("vocab_size", ("model", "size"))),
    )


def prove_declarations_inert() -> None:
    """Declarations are immutable data with no reachable binding state."""
    spec = _spec_info()
    assert spec.constructor is TokenizerInfo
    for name in ("cache", "entries", "factory", "lock", "run", "__dict__"):
        assert not hasattr(spec, name)
    assert isinstance(hash((spec.fields,)), int)


def prove_shapes(grammar: CompiledGrammar) -> None:
    """Bind three materially different class shapes with exact result types."""
    info = _spec_info()._bind(grammar).run(grammar, DOCUMENT)
    assert_type(info, TokenizerInfo)
    assert info == TokenizerInfo("v1", 7)

    ranged = RecordSpec(CheckedRange, (("low", ("low",)), ("high", ("high",))))._bind(
        grammar
    )
    value = ranged.run(grammar, DOCUMENT)
    assert_type(value, CheckedRange)
    assert (value.low, value.high) == (2, 5)

    boxed_spec: RecordSpec[Box[str]] = RecordSpec(Box, (("item", ("version",)),))
    boxed = boxed_spec._bind(grammar).run(grammar, DOCUMENT)
    assert_type(boxed, Box[str])
    assert boxed.item == "v1"


def prove_validated_refusal(grammar: CompiledGrammar) -> None:
    """A validating constructor refuses at the cold root boundary, once."""
    backwards = RecordSpec(
        CheckedRange, (("low", ("high",)), ("high", ("low",)))
    )._bind(grammar)
    try:
        backwards.run(grammar, DOCUMENT)
    except FieldValidationError as error:
        assert "5 > 2" in str(error)
    else:
        raise AssertionError("a backwards range was constructed")


def prove_invalid_bindings(grammar: CompiledGrammar) -> None:
    """Declaration-data defects refuse with words at binding time."""
    for spec in (
        RecordSpec(TokenizerInfo, ()),
        RecordSpec(TokenizerInfo, (("version", ("a",)), ("version", ("b",)))),
        RecordSpec(TokenizerInfo, (("version", ()),)),
    ):
        try:
            spec._bind(grammar)
        except UnsupportedConstructError as error:
            assert "record target" in str(error)
        else:
            raise AssertionError(f"invalid declaration bound: {spec.fields!r}")
    mismatched = RecordSpec(
        TokenizerInfo, (("no_such_parameter", ("version",)),)
    )._bind(grammar)
    try:
        mismatched.run(grammar, CONFLICT)
    except TypeError:
        pass
    else:
        raise AssertionError("a mismatched constructor field was accepted")


def _bind_concurrently(
    barrier: Barrier, spec: RecordSpec[TokenizerInfo], grammar: CompiledGrammar
) -> RecordPlan:
    """Reach one cold plan key concurrently."""
    barrier.wait()
    return spec._bind(grammar).plan


def prove_concurrent_binding(grammar: CompiledGrammar) -> None:
    """Two declarations bind concurrently; each plan compiles exactly once."""
    first = RecordSpec(TokenizerInfo, (("version", ("version",)),))
    second = RecordSpec(TokenizerInfo, (("vocab_size", ("model", "size")),))
    builds = _RECORD_PLANS.build_count
    barrier = Barrier(8)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = tuple(
            pool.submit(_bind_concurrently, barrier, spec, grammar)
            for spec in (first, second) * 4
        )
        plans = tuple(future.result() for future in futures)
    assert _RECORD_PLANS.build_count == builds + 2
    assert plans[0] == plans[2] and plans[1] == plans[3]


def prove_eviction_and_pool(grammar: CompiledGrammar) -> None:
    """Eviction recomputes equivalently; a retained bound view stays valid."""
    spec = _spec_info()
    bound = spec._bind(grammar)
    first_plan = bound.plan
    _RECORD_PLANS.release(grammar)
    rebound = spec._bind(grammar)
    assert rebound.plan == first_plan
    assert rebound.plan is not first_plan
    assert bound.run(grammar, DOCUMENT) == rebound.run(grammar, DOCUMENT)


def prove_artefact_lifetime() -> None:
    """A plan entry dies with its weakly referenced source artefact."""
    grammar = replace(compile_ast(JSON_GRAMMAR), stem="record-target-lifetime")
    spec = _spec_info()
    bound = spec._bind(grammar)
    entries = _RECORD_PLANS.entry_count
    source = weakref.ref(grammar)
    del grammar
    gc.collect()
    assert source() is None
    assert _RECORD_PLANS.entry_count == entries - 1
    assert bound.plan.parameter_order == ("version", "vocab_size")


def main() -> None:
    """Run the full declaration/binding/lifecycle proof."""
    grammar = compile_ast(JSON_GRAMMAR)
    prove_declarations_inert()
    prove_shapes(grammar)
    prove_validated_refusal(grammar)
    prove_invalid_bindings(grammar)
    prove_concurrent_binding(grammar)
    prove_eviction_and_pool(grammar)
    prove_artefact_lifetime()
    print(
        "PASS: custom classes bind through one immutable constructor symbol,"
        " a result-free homogeneous plan registry, and cold root construction"
    )


if __name__ == "__main__":
    main()
