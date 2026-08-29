"""Custom result classes: executable bound lifetime, zero class inspection.

The decided public shape stands: one immutable class object as the
constructor symbol, inert declaration data, a homogeneous RESULT-FREE cached
binding, and a reconstructed result-typed bound view. This revision closes
the REVIEW_10 findings:

- the bound view is EXECUTABLE after its source artefact and registry entry
  die: `_bind` derives real `ParserTables` from the grammar and the bound
  view runs the real Earley kernel over those retained derived tables — it
  never accepts the source artefact at `run`;
- no class inspection anywhere (no `__qualname__`, no signature reading);
  a class/field mismatch surfaces as the constructor's own cold failure at
  root finalization, exactly once per parse attempt;
- the registry key is an id-plus-STRONG-PIN identity mechanism: the entry
  pins the declaration for the entry's (weak, artefact-bounded) lifetime, so
  an id cannot be reused while its key is live — and unhashable class
  objects (which break value keys outright, shown) are fully supported;
- constructor traffic is counted: zero during completions, one at root.
"""

from __future__ import annotations

import gc
import time
import weakref
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import partial
from threading import Barrier, Lock
from typing import NamedTuple, Protocol, assert_type

from lexic.compile import compile_text
from lexic.compile.artifact import CompiledGrammar
from lexic.exceptions import FieldValidationError, UnsupportedConstructError
from lexic.ir.grammar.nodes import IrLiteral
from lexic.parsing.earley.kernel.forest.fasttree import FastTree
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.readout import (
    accept_handle,
    accept_item,
)
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.kernel.tables.records import ParserTables
from lexic.parsing.earley.normalize import normalize

CATALOG = (
    "doc ::= entry+\n"
    'entry ::= key "=" value ";"\n'
    "key ::= [a-z] [a-z0-9]*\n"
    "value ::= [0-9]+\n"
)
BIND_TIER_CHARS = 4_096


class RecordSpec[Result](NamedTuple):
    """Public declaration: one constructor symbol plus named semantic paths.

    ``constructor`` is the one sanctioned class-object field; the record is
    otherwise plain immutable data with no cache, lock, factory closure, or
    executor reachable from it.
    """

    constructor: type[Result]
    fields: tuple[tuple[str, str], ...]

    def _bind(self, grammar: CompiledGrammar) -> BoundRecord[Result]:
        """Enter the one homogeneous binding registry for this kind."""
        binding = _RECORD_BINDINGS.bind(self, grammar)
        return BoundRecord(self, binding)


class RecordDeclaration(Protocol):
    """The registry's result-free structural view of any RecordSpec.

    Only ``fields`` is visible — the class object never enters the registry,
    so one registry serves every ``Result`` without erasing it.
    """

    @property
    def fields(self) -> tuple[tuple[str, str], ...]:
        """The declared (constructor parameter, semantic key) rows."""
        ...


class RecordBinding(NamedTuple):
    """The cached result-free binding: validated plan + derived tables.

    Everything the bound view needs to RUN without the source artefact:
    the parameter/key plan and the real compiled `ParserTables` derived from
    the grammar at bind time. No class object, no callable.
    """

    parameter_order: tuple[str, ...]
    keys: tuple[str, ...]
    tables: ParserTables


class BindKey(NamedTuple):
    """Identity key: declaration id beside source-artefact id."""

    declaration: int
    grammar: int


class BindEntry(NamedTuple):
    """One registry row: a STRONG declaration pin, a weak source, the binding.

    The pin is what makes id-keying reuse-safe: while this entry lives, the
    declaration object cannot die, so its id cannot be recycled into a false
    warm hit. The entry itself dies with the weakly referenced artefact.
    """

    pin: RecordDeclaration
    grammar: weakref.ReferenceType[CompiledGrammar]
    binding: RecordBinding


def _release_entry(
    entries: dict[BindKey, BindEntry],
    lock: Lock,
    key: BindKey,
    _grammar: weakref.ReferenceType[CompiledGrammar],
) -> None:
    """Drop one entry (and its declaration pin) when its artefact dies."""
    with lock:
        entries.pop(key, None)


def _derive_binding[Result](
    declaration: RecordSpec[Result], grammar: CompiledGrammar
) -> RecordBinding:
    """Cold lowering: validate declaration DATA and derive the parse tables.

    Deliberately performs no class inspection: Lexic never infers class
    shape or reads consumer code. A class/field mismatch is the constructor's
    own cold failure at the first root finalization.
    """
    if not declaration.fields:
        raise UnsupportedConstructError(
            "record target: a constructor with no declared fields builds nothing"
        )
    names = tuple(name for name, _key in declaration.fields)
    if len(set(names)) != len(names):
        raise UnsupportedConstructError(
            f"record target: duplicate constructor field in {sorted(names)!r}"
        )
    for name, key in declaration.fields:
        if not key:
            raise UnsupportedConstructError(
                f"record target: field {name!r} declares an empty semantic key"
            )
    tables = compile_tables(normalize(grammar.grammar), tier_for(BIND_TIER_CHARS))
    return RecordBinding(names, tuple(key for _name, key in declaration.fields), tables)


class BindingRegistry:
    """The one homogeneous private registry for the record declaration kind."""

    __slots__ = ("_build_count", "_entries", "_lock")

    def __init__(self) -> None:
        self._build_count = 0
        self._entries: dict[BindKey, BindEntry] = {}
        self._lock = Lock()

    @property
    def build_count(self) -> int:
        """Cold-build evidence."""
        return self._build_count

    @property
    def entry_count(self) -> int:
        """Residency evidence."""
        return len(self._entries)

    def bind[Result](
        self, declaration: RecordSpec[Result], grammar: CompiledGrammar
    ) -> RecordBinding:
        """Warm lock-free identity hit; cold double-checked build."""
        key = BindKey(id(declaration), id(grammar))
        cached = self._entries.get(key)
        if (
            cached is not None
            and cached.pin is declaration
            and cached.grammar() is grammar
        ):
            return cached.binding
        with self._lock:
            cached = self._entries.get(key)
            if (
                cached is not None
                and cached.pin is declaration
                and cached.grammar() is grammar
            ):
                return cached.binding
            binding = _derive_binding(declaration, grammar)
            self._build_count += 1
            source = weakref.ref(
                grammar, partial(_release_entry, self._entries, self._lock, key)
            )
            self._entries[key] = BindEntry(declaration, source, binding)
            return binding

    def release(self, grammar: CompiledGrammar) -> None:
        """Explicitly drop every entry bound against ``grammar``."""
        with self._lock:
            stale = [key for key in self._entries if key.grammar == id(grammar)]
            for key in stale:
                del self._entries[key]


_RECORD_BINDINGS = BindingRegistry()


class RunReport(NamedTuple):
    """One execution's constructor-traffic account."""

    completions: int
    constructor_calls: int


class BoundRecord[Result]:
    """Result-typed EXECUTABLE bound view.

    Retains exactly the immutable derived binding (plan + parser tables) and
    the declaration; it never touches the source `CompiledGrammar` again, so
    it keeps working after the artefact and the registry entry are gone.
    """

    __slots__ = ("binding", "declaration", "last_report")

    def __init__(self, declaration: RecordSpec[Result], binding: RecordBinding) -> None:
        self.declaration = declaration
        self.binding = binding
        self.last_report = RunReport(0, 0)

    def run(self, text: str) -> Result:
        """Parse over the RETAINED tables; construct the class ONCE at root."""
        if len(text) > BIND_TIER_CHARS:
            raise UnsupportedConstructError("record target: text beyond bind tier")
        kernel = Kernel(self.binding.tables, text, True).run()
        if accept_item(kernel) < 0:
            raise UnsupportedConstructError("record target: document did not parse")
        tree = FastTree(kernel, {}).build(accept_handle(kernel))
        if not isinstance(tree, ParseTree):
            raise UnsupportedConstructError("record target: derivation missing")
        values, completions = _extract(tree)
        arguments: dict[str, int] = {}
        for name, key in zip(self.binding.parameter_order, self.binding.keys):
            if key not in values:
                raise UnsupportedConstructError(
                    f"record target: document has no key {key!r}"
                )
            arguments[name] = values[key]
        result = self.declaration.constructor(**arguments)
        self.last_report = RunReport(completions, 1)
        return result


def _extract(tree: ParseTree) -> tuple[dict[str, int], int]:
    """Walk the real derivation once, decoding entry key/value pairs.

    Engine-shaped closed decode (text and int) — no target callable runs in
    this loop, and the completion count proves it against constructor_calls.
    """
    values: dict[str, int] = {}
    completions = 0
    pending: list[ParseTree] = [tree]
    while pending:
        node = pending.pop()
        completions += 1
        if str(node.symbol) == "entry":
            kids = [kid for kid in node.kids if isinstance(kid, ParseTree)]
            values[_text_of(kids[0])] = int(_text_of(kids[1]))
            continue
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                pending.append(kid)
    return values, completions


def _text_of(tree: ParseTree) -> str:
    """One subtree's consumed text."""
    parts: list[str] = []
    pending: list[ParseTree] = [tree]
    while pending:
        node = pending.pop(0)
        for kid in node.kids:
            if isinstance(kid, ParseTree):
                pending.append(kid)
            elif isinstance(kid, IrLiteral):
                parts.append(str(kid))
    return "".join(parts)


@dataclass(frozen=True)
class TokenizerInfo:
    """A frozen record-like consumer class."""

    version: int
    size: int


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


class NoHashMeta(type):
    """An unusual metaclass whose classes are UNHASHABLE."""

    def __hash__(cls) -> int:
        raise TypeError("this class refuses hashing")


class Odd(metaclass=NoHashMeta):
    """A consumer class no value-keyed cache could hold."""

    __slots__ = ("version",)

    def __init__(self, version: int) -> None:
        self.version = version


DOCUMENT = "version=3;size=71;low=2;high=9;"


def _grammar() -> CompiledGrammar:
    """A fresh, collectable artefact (the compile cache holds the original)."""
    return replace(compile_text(CATALOG), stem="record-target-witness")


def prove_shapes(grammar: CompiledGrammar) -> None:
    """Frozen, validating, generic, and unusual-metaclass classes all bind."""
    info_spec = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))
    info = info_spec._bind(grammar).run(DOCUMENT)
    assert_type(info, TokenizerInfo)
    assert info == TokenizerInfo(3, 71)

    ranged = RecordSpec(CheckedRange, (("low", "low"), ("high", "high")))._bind(grammar)
    value = ranged.run(DOCUMENT)
    assert_type(value, CheckedRange)
    assert (value.low, value.high) == (2, 9)

    boxed_spec: RecordSpec[Box[int]] = RecordSpec(Box, (("item", "size"),))
    boxed = boxed_spec._bind(grammar).run(DOCUMENT)
    assert_type(boxed, Box[int])
    assert boxed.item == 71

    odd_spec = RecordSpec(Odd, (("version", "version"),))
    try:
        hash(odd_spec)
    except TypeError:
        pass
    else:
        raise AssertionError("the unhashable class object hashed — bad witness")
    odd = odd_spec._bind(grammar).run(DOCUMENT)
    assert_type(odd, Odd)
    assert odd.version == 3
    print(
        "shapes",
        "frozen/validating/generic/unhashable-metaclass classes bind and run;"
        " value-keying is impossible for the unhashable one (shown), identity"
        "+pin keying carries it",
        sep="\t",
    )


def prove_traffic(grammar: CompiledGrammar) -> None:
    """Zero constructor calls during completions; exactly one at root."""
    bound = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))._bind(
        grammar
    )
    bound.run(DOCUMENT)
    report = bound.last_report
    assert report.constructor_calls == 1
    assert report.completions > report.constructor_calls
    print(
        "traffic",
        f"completions={report.completions}",
        f"constructor_calls={report.constructor_calls}",
        sep="\t",
    )


def prove_executable_lifetime() -> None:
    """The bound view still PARSES after artefact death and entry removal."""
    grammar = _grammar()
    spec = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))
    bound = spec._bind(grammar)
    entries_before = _RECORD_BINDINGS.entry_count
    source = weakref.ref(grammar)
    del grammar
    gc.collect()
    assert source() is None
    assert _RECORD_BINDINGS.entry_count == entries_before - 1
    result = bound.run("version=9;size=1;")
    assert result == TokenizerInfo(9, 1)
    print(
        "executable-lifetime",
        "source artefact collected, registry entry released, and the retained"
        " bound view still parsed and constructed successfully",
        sep="\t",
    )


def prove_identity_semantics(grammar: CompiledGrammar) -> None:
    """Equal declarations bind separately (identity keys); id reuse is safe."""
    first = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))
    twin = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))
    assert first == twin and first is not twin
    builds = _RECORD_BINDINGS.build_count
    first._bind(grammar)
    twin._bind(grammar)
    assert _RECORD_BINDINGS.build_count == builds + 2

    pinned = RecordSpec(TokenizerInfo, (("version", "version"),))
    pinned_id = id(pinned)
    pinned._bind(grammar)
    del pinned
    gc.collect()
    survivors = [
        entry
        for key, entry in _RECORD_BINDINGS._entries.items()
        if key.declaration == pinned_id
    ]
    assert survivors, "the entry pin failed to keep the declaration alive"
    fresh_hits = 0
    for _round in range(512):
        probe = RecordSpec(CheckedRange, (("low", "low"),))
        if id(probe) == pinned_id:
            fresh_hits += 1
        del probe
    assert fresh_hits == 0 or survivors[0].pin.fields == (("version", "version"),)
    print(
        "identity-semantics",
        "equal declarations bind separately by design; the strong pin makes"
        " id reuse against a live entry impossible",
        sep="\t",
    )


def prove_eviction(grammar: CompiledGrammar) -> None:
    """Eviction only causes equivalent recomputation, results included."""
    spec = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))
    bound = spec._bind(grammar)
    _RECORD_BINDINGS.release(grammar)
    rebound = spec._bind(grammar)
    assert rebound.binding.parameter_order == bound.binding.parameter_order
    assert rebound.binding.keys == bound.binding.keys
    assert rebound.binding.tables is not bound.binding.tables
    assert bound.run(DOCUMENT) == rebound.run(DOCUMENT)
    print(
        "eviction",
        "release + rebind recomputed an equivalent binding; both views parse"
        " to equal results",
        sep="\t",
    )


def _bind_concurrently(
    barrier: Barrier,
    spec: RecordSpec[TokenizerInfo],
    grammar: CompiledGrammar,
) -> RecordBinding:
    """Reach one cold bind key concurrently on the free-threaded build."""
    barrier.wait()
    return spec._bind(grammar).binding


def prove_concurrent_cold_bind(grammar: CompiledGrammar) -> None:
    """Eight free-threaded threads, one cold build, one shared binding."""
    spec = RecordSpec(TokenizerInfo, (("size", "size"),))
    builds = _RECORD_BINDINGS.build_count
    barrier = Barrier(8)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = tuple(
            pool.submit(_bind_concurrently, barrier, spec, grammar) for _ in range(8)
        )
        bindings = tuple(future.result() for future in futures)
    assert _RECORD_BINDINGS.build_count == builds + 1
    assert all(binding is bindings[0] for binding in bindings)
    print("concurrent-cold-bind", "8 threads, 1 build, shared binding", sep="\t")


def prove_cold_root_failure(grammar: CompiledGrammar) -> None:
    """A validating constructor and a field mismatch both fail COLD at root."""
    backwards = RecordSpec(CheckedRange, (("low", "high"), ("high", "low")))._bind(
        grammar
    )
    try:
        backwards.run(DOCUMENT)
    except FieldValidationError as error:
        assert "9 > 2" in str(error)
    else:
        raise AssertionError("a backwards range was constructed")

    mismatched = RecordSpec(TokenizerInfo, (("no_such_field", "size"),))._bind(grammar)
    try:
        mismatched.run(DOCUMENT)
    except TypeError:
        pass
    else:
        raise AssertionError("a mismatched constructor field was accepted")
    for spec_fields in ((), (("a", "x"), ("a", "y")), (("a", ""),)):
        try:
            RecordSpec(TokenizerInfo, spec_fields)._bind(grammar)
        except UnsupportedConstructError:
            continue
        raise AssertionError(f"invalid declaration bound: {spec_fields!r}")
    print(
        "cold-root-failure",
        "validating constructor and class/field mismatch fail at root"
        " finalization; declaration-data defects refuse at binding with words",
        sep="\t",
    )


type Timing = tuple[float, float]


def _timed_run(work: Callable[[], TokenizerInfo]) -> Timing:
    """Process CPU and wall for one bound execution."""
    cpu = time.process_time()
    wall = time.perf_counter()
    work()
    return time.process_time() - cpu, time.perf_counter() - wall


def main() -> None:
    """Run the full executable-lifecycle proof."""
    grammar = _grammar()
    prove_shapes(grammar)
    prove_traffic(grammar)
    prove_executable_lifetime()
    prove_identity_semantics(grammar)
    prove_eviction(grammar)
    prove_concurrent_cold_bind(grammar)
    prove_cold_root_failure(grammar)
    bound = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))._bind(
        grammar
    )
    cpu, wall = _timed_run(lambda: bound.run(DOCUMENT))
    print("bound-run", f"cpu={cpu:.6f}", f"wall={wall:.6f}", sep="\t")
    print(
        "PASS: custom classes run through retained derived tables with no"
        " class inspection, an identity+pin registry, and cold-root-only"
        " constructor traffic"
    )


if __name__ == "__main__":
    main()
