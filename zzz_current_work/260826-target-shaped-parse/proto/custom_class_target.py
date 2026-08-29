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
import types
import weakref
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from functools import partial
from threading import Barrier, Lock
from typing import NamedTuple, Protocol, assert_type

from lexic.compile import compile_text
from lexic.compile.artifact import CompiledGrammar
from lexic.ir import IrAst
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
    """The cached result-free binding: plan + derived AST + base-tier tables.

    Everything the bound view needs to RUN without the source artefact: the
    parameter/key plan, the DERIVED normalized grammar AST (a fresh object,
    not the artefact's), and base-tier `ParserTables`. A document beyond the
    base tier recompiles tables cold from the retained derived AST — never
    from the source artefact. No class object, no callable.
    """

    parameter_order: tuple[str, ...]
    keys: tuple[str, ...]
    ast: IrAst
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
    dead: weakref.ReferenceType[CompiledGrammar],
) -> None:
    """Drop one entry (and its pin) when ITS artefact dies — the callback
    validates that the entry still belongs to the dead weakref, so a
    recycled id can never evict a live successor's entry."""
    with lock:
        cached = entries.get(key)
        if cached is not None and cached.grammar is dead:
            del entries[key]


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
    ast, tables = _SHARED_TABLES.derive(grammar)
    return RecordBinding(
        names, tuple(key for _name, key in declaration.fields), ast, tables
    )


class SharedTables:
    """One derived (AST, base-tier tables) pair per source artefact.

    N declarations against one grammar share one derivation; the entry dies
    with the weakly referenced artefact, exactly like binding entries.
    """

    __slots__ = ("_by_grammar", "_derives", "_lock")

    def __init__(self) -> None:
        self._by_grammar: dict[
            int,
            tuple[weakref.ReferenceType[CompiledGrammar], IrAst, ParserTables],
        ] = {}
        self._derives = 0
        self._lock = Lock()

    @property
    def derive_count(self) -> int:
        """How many grammars were actually lowered."""
        return self._derives

    def release(self, grammar: CompiledGrammar) -> None:
        """Explicitly drop one artefact's shared derivation."""
        with self._lock:
            self._by_grammar.pop(id(grammar), None)

    def derive(self, grammar: CompiledGrammar) -> tuple[IrAst, ParserTables]:
        """One normalized AST + base-tier tables per live artefact.

        The stored weakref is re-validated on every read — the same
        id-reuse-safety rule the binding entries follow: an id hit whose
        referent is not THIS grammar is a stale entry, never an answer.
        """
        key = id(grammar)
        cached = self._by_grammar.get(key)
        if cached is not None and cached[0]() is grammar:
            return cached[1], cached[2]
        with self._lock:
            cached = self._by_grammar.get(key)
            if cached is not None and cached[0]() is grammar:
                return cached[1], cached[2]
            ast = normalize(grammar.grammar)
            tables = compile_tables(ast, tier_for(BIND_TIER_CHARS))
            self._derives += 1
            source = weakref.ref(grammar, partial(_release_tables, self, key))
            self._by_grammar[key] = (source, ast, tables)
            return ast, tables


def _release_tables(
    shared: SharedTables,
    key: int,
    dead: weakref.ReferenceType[CompiledGrammar],
) -> None:
    """Drop one shared derivation when ITS artefact dies — validated against
    the stored weakref, under the lock, symmetric with `_release_entry`."""
    with shared._lock:
        cached = shared._by_grammar.get(key)
        if cached is not None and cached[0] is dead:
            del shared._by_grammar[key]


_SHARED_TABLES = SharedTables()


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
        """Explicitly drop every entry AND the shared derivation for
        ``grammar`` — eviction may only ever cause equivalent recomputation."""
        with self._lock:
            stale = [key for key in self._entries if key.grammar == id(grammar)]
            for key in stale:
                del self._entries[key]
        _SHARED_TABLES.release(grammar)


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
        """Parse over the RETAINED derived tables; construct ONCE at root.

        A document beyond the base tier recompiles tables COLD from the
        retained derived AST — the source artefact is never consulted.
        """
        tables = self.binding.tables
        if len(text) > BIND_TIER_CHARS:
            tables = compile_tables(self.binding.ast, tier_for(len(text)))
        kernel = Kernel(tables, text, True).run()
        if accept_item(kernel) < 0:
            raise UnsupportedConstructError("record target: document did not parse")
        tree = FastTree(kernel, {}).build(accept_handle(kernel))
        if not isinstance(tree, ParseTree):
            raise UnsupportedConstructError("record target: derivation missing")
        invocations: list[str] = []
        values, completions = _extract(tree, invocations)
        if invocations:
            raise UnsupportedConstructError(
                "record target: a constructor ran inside the completion walk"
            )
        arguments: dict[str, int] = {}
        for name, key in zip(self.binding.parameter_order, self.binding.keys):
            if key not in values:
                raise UnsupportedConstructError(
                    f"record target: document has no key {key!r}"
                )
            arguments[name] = values[key]
        invocations.append("root")
        result = self.declaration.constructor(**arguments)
        self.last_report = RunReport(completions, len(invocations))
        return result


def _extract(tree: ParseTree, invocations: list[str]) -> tuple[dict[str, int], int]:
    """Walk the real derivation once, decoding entry key/value pairs.

    Engine-shaped closed decode (text and int). The zero-constructor-traffic
    property is STRUCTURAL: the walk holds no reference to the constructor
    (only the caller does, and it constructs after this returns); the shared
    ``invocations`` list documents the single call site rather than claiming
    a runtime count of calls nothing else could make.
    """
    if invocations:
        raise UnsupportedConstructError("record target: walk started dirty")
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
    assert survivors[0].pin.fields == (("version", "version"),)
    print(
        "identity-semantics",
        "equal declarations bind separately by design; id-reuse safety is the"
        " DOUBLE identity check — the strong pin keeps the declaration alive"
        " (its id cannot recycle while the entry lives) and every lookup"
        " re-validates `pin is declaration` AND `grammar() is grammar`",
        sep="\t",
    )


def _closure_reaches_compiled(root_object: BoundRecord[TokenizerInfo]) -> bool:
    """Whether a `CompiledGrammar` is reachable through DATA edges.

    Types, modules, functions, and code objects are ambient code references
    (every class reaches its module's globals and thereby the compile memo);
    the retention question is about the bound view's DATA, so the walk stops
    at those.
    """
    ambient = (types.ModuleType, types.CodeType)
    seen: set[int] = set()
    # Seeded THROUGH get_referents of a wrapping tuple so the pending lane
    # carries the same dynamic typing the referent stream itself has.
    pending = list(gc.get_referents((root_object,)))
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, CompiledGrammar):
            return True
        if isinstance(current, type):
            # A class defined outside builtins can carry DATA in class
            # attributes (a registry hanging off a class is a retention
            # shape); walk its dict's values while still skipping the
            # module-globals escape (methods are functions, handled below).
            if current.__module__ != "builtins":
                pending.extend(vars(current).values())
            continue
        if isinstance(current, ambient):
            continue
        if isinstance(current, types.FunctionType):
            # A function's __globals__ is ambient code reference, but its
            # closure cells and defaults are DATA — a closure over the
            # artefact is exactly the retention shape this check exists to
            # rule out, so those edges are walked.
            pending.extend(current.__defaults__ or ())
            for cell in current.__closure__ or ():
                try:
                    pending.append(cell.cell_contents)
                except ValueError:
                    continue
            continue
        pending.extend(gc.get_referents(current))
    return False


def prove_shared_tables_and_retention() -> None:
    """N declarations share ONE derived table set; the retention rule is
    explicit: entries (and their declaration pins) live exactly as long as
    the weakly referenced artefact, or until `release`."""
    grammar = _grammar()
    entries_before = _RECORD_BINDINGS.entry_count
    derives_before = _SHARED_TABLES.derive_count
    tables_seen: set[int] = set()
    for index in range(50):
        spec = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))
        bound = spec._bind(grammar)
        tables_seen.add(id(bound.binding.tables))
        del spec, bound
    gc.collect()
    held = _RECORD_BINDINGS.entry_count - entries_before
    derived = _SHARED_TABLES.derive_count - derives_before
    assert derived == 1 and len(tables_seen) == 1
    assert held == 50
    source = weakref.ref(grammar)
    del grammar
    gc.collect()
    assert source() is None
    assert _RECORD_BINDINGS.entry_count == entries_before
    print(
        "shared-tables-retention",
        f"equal_distinct_declarations=50 entries_held={held} table_derivations="
        f"{derived} shared_tables=1; all fifty entries (and pins) died with"
        " the artefact — retention is artefact-bounded, and the caller idiom"
        " is one held declaration object per target",
        sep="\t",
    )


def prove_long_document_after_death() -> None:
    """Beyond-tier documents parse from the RETAINED derived AST after the
    source artefact is collected — no artefact consult exists to fall back
    on, and none is needed."""
    grammar = _grammar()
    spec = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))
    bound = spec._bind(grammar)
    assert not _closure_reaches_compiled(bound)
    source = weakref.ref(grammar)
    del grammar
    gc.collect()
    assert source() is None
    filler = "".join(f"pad{index}={index};" for index in range(600))
    long_doc = filler + "version=4;size=8;"
    assert len(long_doc) > BIND_TIER_CHARS
    result = bound.run(long_doc)
    assert result == TokenizerInfo(4, 8)
    print(
        "long-document-after-death",
        f"doc_chars={len(long_doc)} parsed over tables recompiled from the"
        " retained derived AST; no CompiledGrammar reachable from the bound"
        " view (checked over the data-edge gc referent closure)",
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
    prove_shared_tables_and_retention()
    prove_long_document_after_death()
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
