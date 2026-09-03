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

from nullable_quantifier_ambiguity import complete_ambiguity_points

from lexic.compile import compile_text
from lexic.compile.artifact import CompiledGrammar
from lexic.exceptions import FieldValidationError, UnsupportedConstructError
from lexic.ir import IrAst
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
from lexic.parsing.parallel.pool import ParsePool

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


class ProductRegistry:
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


_RECORD_BINDINGS = ProductRegistry()


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

    # `__weakref__` exists only so the pool-retention proof can watch this
    # object's lifetime from outside; it adds no field and no behaviour.
    __slots__ = ("__weakref__", "binding", "declaration", "last_report")

    def __init__(self, declaration: RecordSpec[Result], binding: RecordBinding) -> None:
        self.declaration = declaration
        self.binding = binding
        self.last_report = RunReport(0, 0)

    def walk(self, text: str) -> tuple[dict[str, int], int]:
        """Recognize and complete — the FREQUENT path, constructor-free.

        Nothing on this path holds a reference to the consumer class: the
        walk is a module-level function of the derivation alone, and the
        binding it reads carries no class object. A document beyond the base
        tier recompiles tables COLD from the retained derived AST; the source
        artefact is never consulted.
        """
        tables = self.binding.tables
        if len(text) > BIND_TIER_CHARS:
            tables = compile_tables(self.binding.ast, tier_for(len(text)))
        kernel = Kernel(tables, text, True).run()
        if accept_item(kernel) < 0:
            raise UnsupportedConstructError("record target: document did not parse")
        root = accept_handle(kernel)
        if complete_ambiguity_points(kernel, root):
            # The refusal happens BEFORE any result exists, so an ambiguous
            # document can never reach the consumer constructor.
            raise UnsupportedConstructError(
                "record target: the document has more than one derivation"
            )
        tree = FastTree(kernel, {}).build(root)
        if not isinstance(tree, ParseTree):
            raise UnsupportedConstructError("record target: derivation missing")
        return _extract(tree)

    def arguments(self, values: dict[str, int]) -> dict[str, int]:
        """The declared constructor arguments, by name — still class-free."""
        found: dict[str, int] = {}
        for name, key in zip(self.binding.parameter_order, self.binding.keys):
            if key not in values:
                raise UnsupportedConstructError(
                    f"record target: document has no key {key!r}"
                )
            found[name] = values[key]
        return found

    def run(self, text: str) -> Result:
        """Parse over the RETAINED derived tables; construct ONCE at root."""
        values, completions = self.walk(text)
        result = self.declaration.constructor(**self.arguments(values))
        self.last_report = RunReport(completions, 1)
        return result


def _extract(tree: ParseTree) -> tuple[dict[str, int], int]:
    """Walk the real derivation once, decoding entry key/value pairs.

    Engine-shaped closed decode (text and int). It takes the derivation and
    nothing else, so no consumer constructor is reachable from this path — a
    property `prove_traffic` checks by running it under a constructor that
    raises on any call.
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


CONSTRUCTOR_CALLS: dict[str, int] = {}
"""External allocation counter, incremented by the consumer classes below.

The count lives OUTSIDE the target machinery: nothing in `BoundRecord` or the
prototype derivation walk can decrement or bypass it, so a zero here after a
walk is evidence about the prototype rather than a list documenting a known
call site.
"""


@dataclass(frozen=True)
class CountedInfo:
    """A consumer class that counts every construction, wherever it happens."""

    version: int
    size: int

    def __post_init__(self) -> None:
        """Record one construction."""
        CONSTRUCTOR_CALLS["CountedInfo"] = CONSTRUCTOR_CALLS.get("CountedInfo", 0) + 1


class Forbidden:
    """A consumer class that must never be constructed."""

    __slots__ = ()

    def __init__(self, **fields: int) -> None:
        """:raises AssertionError: Always — the frequent path called it."""
        raise AssertionError(f"the derivation walk constructed a result: {fields!r}")


def prove_traffic(grammar: CompiledGrammar) -> None:
    """Zero constructor calls on the frequent path; exactly one at the root.

    Two independent checks: an external counter on a real consumer class, and
    the same prototype walk driven through a declaration whose constructor
    raises on any call — so a walk that touched it could not finish.
    """
    CONSTRUCTOR_CALLS.clear()
    counted = RecordSpec(CountedInfo, (("version", "version"), ("size", "size")))
    bound = counted._bind(grammar)
    values, completions = bound.walk(DOCUMENT)
    walk_calls = CONSTRUCTOR_CALLS.get("CountedInfo", 0)
    result = bound.run(DOCUMENT)
    assert result == CountedInfo(3, 71)
    # The equality above constructs one more CountedInfo; the run itself is
    # the difference between the two reads.
    run_calls = CONSTRUCTOR_CALLS.get("CountedInfo", 0) - walk_calls - 1
    assert walk_calls == 0 and run_calls == 1, CONSTRUCTOR_CALLS

    refusing = RecordSpec(Forbidden, (("version", "version"), ("size", "size")))
    refusing_bound = refusing._bind(grammar)
    refused_values, refused_completions = refusing_bound.walk(DOCUMENT)
    assert refused_values == values and refused_completions == completions
    assert refusing_bound.arguments(refused_values) == {"version": 3, "size": 71}

    walk_names = set(_extract.__code__.co_names) | set(
        BoundRecord.walk.__code__.co_names
    )
    assert "constructor" not in walk_names and "declaration" not in walk_names
    print(
        "traffic",
        f"completions={completions}",
        f"walk_constructor_calls={walk_calls}",
        f"root_constructor_calls={run_calls}",
        "the same walk finishes under a constructor that raises on any call,"
        " and neither the walk nor the extraction names `constructor` or"
        " `declaration` in its code object",
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


def prove_no_traffic_on_refusal(grammar: CompiledGrammar) -> None:
    """Syntax failure and ambiguity refusal both construct nothing.

    Both are checked with the counting consumer class, so a construction
    anywhere — including one this file does not know about — would show up.
    """
    CONSTRUCTOR_CALLS.clear()
    bound = RecordSpec(CountedInfo, (("version", "version"), ("size", "size")))._bind(
        grammar
    )
    for text in ("version=3;size", "!!!", ""):
        try:
            bound.run(text)
        except UnsupportedConstructError:
            continue
        raise AssertionError(f"malformed document {text!r} produced a result")

    ambiguous = replace(
        compile_text(
            # Two explicit entries rather than `entry+`: `ambiguity_points`
            # does not surface an arm choice under a quantifier chain, and the
            # completeness of production's refusal PREDICATE is §8's question,
            # not this gate's — the gate needs a chart that really refuses.
            "doc ::= entry entry\n"
            'entry ::= key "=" value ";"\n'
            "value ::= num1 | num2\n"
            "num1 ::= [0-9]\n"
            "num2 ::= [0-9]\n"
            "key ::= [a-z] [a-z0-9]*\n"
        ),
        stem="ambiguous-record-witness",
    )
    ambiguous_bound = RecordSpec(
        CountedInfo, (("version", "version"), ("size", "size"))
    )._bind(ambiguous)
    try:
        ambiguous_bound.run("version=3;size=7;")
    except UnsupportedConstructError as error:
        assert "more than one derivation" in str(error), str(error)
    else:
        raise AssertionError("an ambiguous document produced a result")
    assert CONSTRUCTOR_CALLS.get("CountedInfo", 0) == 0, CONSTRUCTOR_CALLS
    print(
        "no-traffic-on-refusal",
        "three malformed documents and one genuinely ambiguous document all"
        f" refuse with constructor_calls={CONSTRUCTOR_CALLS.get('CountedInfo', 0)};"
        " the ambiguity refusal happens before any result exists, so no"
        " unchosen result is ever constructed",
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


POOL_DOCUMENTS = tuple(
    f"version={index};size={index * 7};low=1;high=9;" for index in range(1, 33)
)
"""Distinct documents mapped through one retained pool."""


def _long_document(version: int) -> str:
    """A document past the bind tier — the pool's tier-escape witness."""
    filler = "".join(f"pad{index}={index};" for index in range(600))
    return f"{filler}version={version};size=8;"


def _pool_owner() -> tuple[
    ParsePool[str, TokenizerInfo], weakref.ReferenceType[BoundRecord[TokenizerInfo]]
]:
    """Bind a target, hand the bound product to a real pool, kill the source.

    The pool's ordinary work binding is the ONLY thing holding the bound view
    afterwards: the local reference and the registry entry are both gone.
    """
    grammar = _grammar()
    spec = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))
    bound = spec._bind(grammar)
    watch = weakref.ref(bound)
    pool: ParsePool[str, TokenizerInfo] = ParsePool(bound.run, cores=4)
    source = weakref.ref(grammar)
    entries_before = _RECORD_BINDINGS.entry_count
    del grammar, bound, spec
    gc.collect()
    assert source() is None, "the source artefact survived"
    assert _RECORD_BINDINGS.entry_count == entries_before - 1
    assert watch() is not None, "the pool did not retain the bound product"
    return pool, watch


def prove_pool_lifecycle() -> None:
    """A real `ParsePool` owns the bound product past source and entry death."""
    pool, watch = _pool_owner()
    results = pool.map(POOL_DOCUMENTS)
    assert len(results) == len(POOL_DOCUMENTS)
    assert results[0] == TokenizerInfo(1, 7)
    assert results[-1] == TokenizerInfo(32, 224)
    long_result = pool.map([_long_document(4)])[0]
    assert long_result == TokenizerInfo(4, 8)
    workers = pool.workers
    pool.close()
    del pool
    gc.collect()
    assert watch() is None, "the bound product outlived the pool that owned it"
    print(
        "pool-lifecycle",
        f"workers={workers}",
        f"documents={len(POOL_DOCUMENTS)}",
        f"beyond_tier_chars={len(_long_document(4))}",
        "source artefact collected and registry entry released BEFORE the"
        " first map; the pool's own work binding was the sole owner, and"
        " closing the pool dropped the bound product",
        sep="\t",
    )


def _map_slice(pool: ParsePool[str, TokenizerInfo], start: int) -> list[TokenizerInfo]:
    """One concurrent map over half the documents."""
    return pool.map(POOL_DOCUMENTS[start::2])


def prove_pool_concurrency() -> None:
    """Concurrent maps through one retained pool return the same results."""
    pool, _watch = _pool_owner()
    with ThreadPoolExecutor(max_workers=2) as outer:
        futures = tuple(outer.submit(_map_slice, pool, start) for start in (0, 1))
        halves = tuple(future.result() for future in futures)
    interleaved: list[TokenizerInfo] = []
    for even, odd in zip(halves[0], halves[1]):
        interleaved.extend((even, odd))
    assert interleaved == pool.map(POOL_DOCUMENTS)
    pool.close()
    print(
        "pool-concurrency",
        "2 concurrent maps x 16 documents through one retained pool agree with"
        " the sequential map over the same documents",
        sep="\t",
    )


def prove_pool_failure_and_eviction() -> None:
    """Constructor failure and registry eviction, both through the pool."""
    grammar = _grammar()
    ranged = RecordSpec(CheckedRange, (("low", "high"), ("high", "low")))
    bad: ParsePool[str, CheckedRange] = ParsePool(ranged._bind(grammar).run, cores=2)
    try:
        bad.map([DOCUMENT, DOCUMENT])
    except FieldValidationError as error:
        assert "9 > 2" in str(error)
    else:
        raise AssertionError("a backwards range survived the pool")
    finally:
        bad.close()

    spec = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))
    first: ParsePool[str, TokenizerInfo] = ParsePool(spec._bind(grammar).run, cores=2)
    before = first.map(POOL_DOCUMENTS[:4])
    first.close()
    _RECORD_BINDINGS.release(grammar)
    second: ParsePool[str, TokenizerInfo] = ParsePool(spec._bind(grammar).run, cores=2)
    after = second.map(POOL_DOCUMENTS[:4])
    second.close()
    assert before == after
    closed = False
    try:
        second.map(POOL_DOCUMENTS[:1])
    except RuntimeError:
        closed = True
    assert closed, "a closed pool still accepted work"
    print(
        "pool-failure-and-eviction",
        "a failing constructor surfaces as its own exception through"
        " ParsePool.map; release + rebind recomputes an equivalent binding"
        " whose pooled results are identical; a closed pool refuses work",
        sep="\t",
    )


class DefaultProduct:
    """The control target: the same walk, finalized by the engine itself.

    It is the prototype-walk comparison partner — identical recognition,
    identical derivation walk, and a root finalizer that is engine-owned rather
    than a consumer class.
    """

    __slots__ = ("bound",)

    def __init__(self, bound: BoundRecord[TokenizerInfo]) -> None:
        self.bound = bound

    def run(self, text: str) -> dict[str, int]:
        """Walk, then finalize into the engine's own default codomain."""
        values, _completions = self.bound.walk(text)
        return self.bound.arguments(values)


def prove_paid_loop_neutrality(grammar: CompiledGrammar) -> None:
    """Default control vs custom target through the same prototype shape.

    Alternating, in one process, minimum of the rounds: the two arms differ
    only in the root finalizer. This isolates finalization cost inside the
    prototype; it does not measure the production paid loop.
    """
    spec = RecordSpec(TokenizerInfo, (("version", "version"), ("size", "size")))
    bound = spec._bind(grammar)
    control = DefaultProduct(bound)
    document = _long_document(9)
    control_cpu: list[float] = []
    control_wall: list[float] = []
    custom_cpu: list[float] = []
    custom_wall: list[float] = []
    for round_index in range(8):
        arms = (
            (control_cpu, control_wall, control.run),
            (custom_cpu, custom_wall, bound.run),
        )
        for cpu_lane, wall_lane, work in arms if round_index % 2 == 0 else arms[::-1]:
            cpu = time.process_time()
            wall = time.perf_counter()
            for _repeat in range(4):
                work(document)
            cpu_lane.append(time.process_time() - cpu)
            wall_lane.append(time.perf_counter() - wall)
    print(
        "prototype-finalizer-neutrality",
        f"document_chars={len(document)}",
        "rounds=8 x 4 parses",
        f"control_min_cpu={min(control_cpu):.6f}",
        f"custom_min_cpu={min(custom_cpu):.6f}",
        f"cpu_ratio={min(custom_cpu) / min(control_cpu):.6f}",
        f"control_min_wall={min(control_wall):.6f}",
        f"custom_min_wall={min(custom_wall):.6f}",
        "same tables, same kernel, same derivation walk; the arms differ only"
        " in the root finalizer, and the order alternates every round; this is"
        " not production completion traffic",
        sep="\t",
    )


def main() -> None:
    """Run the full executable-lifecycle proof."""
    grammar = _grammar()
    prove_shapes(grammar)
    prove_traffic(grammar)
    prove_executable_lifetime()
    prove_no_traffic_on_refusal(grammar)
    prove_identity_semantics(grammar)
    prove_shared_tables_and_retention()
    prove_long_document_after_death()
    prove_eviction(grammar)
    prove_concurrent_cold_bind(grammar)
    prove_cold_root_failure(grammar)
    prove_pool_lifecycle()
    prove_pool_concurrency()
    prove_pool_failure_and_eviction()
    prove_paid_loop_neutrality(grammar)
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
