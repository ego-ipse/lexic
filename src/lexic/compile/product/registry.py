"""Bound products and their lifetime — one registry per declaration kind.

A declaration is inert data; running it needs a compiled program, and
compiling one per parse would be absurd. So bindings are memoised — and a
memo keyed by object identity has to say who owns its entries, or it is a
leak with a fast path.

Ownership here is the repo's existing protocol, not a second one. The entries
dict registers with :func:`~lexic.parsing.caches.memo`, naming which key
position holds the source identity; :func:`~lexic.parsing.caches.track` binds
those entries to the source artefact's lifetime; and everything the binding
derives is :func:`~lexic.parsing.caches.adopt`\\ ed under the same identity, so
one death releases the chain.

Three properties this file exists to keep:

**A bound product never retains its source.** It holds a verified program and
an executor, both derived. That is what lets a pool keep running one after the
source artefact is gone and its registry entry evicted — the pool is then the
explicit owner, which is the whole point of eviction being safe.

**Eviction changes residency, never meaning.** Every entry is a pure memo:
dropping it costs a recompilation and changes no answer.

**A cold miss binds once.** The warm read is a plain dict lookup with no lock;
only a miss takes one, and re-checks under it, so two threads reaching an
unbound declaration together compile it once and share the result.
"""

from __future__ import annotations

import weakref
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from threading import Lock
from typing import NamedTuple

from lexic.compile.pipeline.rulemap import RuleMap
from lexic.compile.pipeline.synthesis import model_plan
from lexic.ir import IrAst
from lexic.model import GrammarModel
from lexic.parsing import ModelExecutable
from lexic.parsing.caches import adopt, memo, track
from lexic.parsing.product import LoweringOwned, ProductProgram, RuleProduct

__all__ = ["ProductRegistry", "RegisteredProduct", "ProgramProduct"]


class RegisteredProduct[Result](ABC):
    """A result-typed runner whose carrier type stays hidden.

    The public seam is exact in ``Result`` while ``Carry`` — the internal
    value type a program's rules produce — is not erased, only concealed: the
    concrete runner below stays generic in both and this base names the half a
    caller cares about.

    Two things a holder needs and neither of which requires knowing ``Carry``:
    run it, and know whether running it needs parse-local state. The second is
    what lets a pool honour "the generated-model product allocates none"
    without reaching into the program to find out.
    """

    __slots__ = ()

    @property
    @abstractmethod
    def stateful(self) -> bool:
        """Whether one run needs a parse-local ``ParseState``."""

    @abstractmethod
    def run(self, text: str, cores: int = 0) -> Result:
        """Run the already-bound product over ``text``."""


type ProductExecutor[Carry, Result] = Callable[
    [ProductProgram[Carry, Result], str, int], Result
]
"""How a bound program is executed. Supplied at binding, never by a caller."""


class ProgramProduct[Carry, Result](RegisteredProduct[Result]):
    """One verified program plus the executor that runs it.

    Deliberately holds no source artefact, no grammar and no reducer — only
    what compilation derived. A pool that keeps one of these keeps exactly
    what it needs and nothing that would make an artefact immortal.
    """

    __slots__ = ("_execute", "_program")

    def __init__(
        self,
        program: ProductProgram[Carry, Result],
        execute: ProductExecutor[Carry, Result],
    ) -> None:
        """Bind the compiled program to its executor."""
        self._program = program
        self._execute = execute

    @property
    def program(self) -> ProductProgram[Carry, Result]:
        """The compiled program this runner executes."""
        return self._program

    @property
    def stateful(self) -> bool:
        """Whether one run needs a parse-local ``ParseState``.

        Read off the program, which DERIVED it from its own instructions —
        so this cannot disagree with what the product actually does.
        """
        return self._program.stateful

    def run(self, text: str, cores: int = 0) -> Result:
        """Execute without exposing or erasing the carrier."""
        return self._execute(self._program, text, cores)


class _Entry[Declaration, Result](NamedTuple):
    """One registry row, bounded by the source artefact it was built for.

    :ivar declaration: Pinned live, so an entry keyed by a recycled address
        can never be served to a different declaration.
    :ivar source: A WEAK reference. Pinning the artefact here would make every
        bound product immortal — the exact retention the lifetime protocol
        exists to bound.
    :ivar bound: The result-typed runner.
    """

    declaration: Declaration
    source: weakref.ReferenceType[object]
    bound: RegisteredProduct[Result]


type BindingFactory[Declaration, Result] = Callable[
    [Declaration, object], RegisteredProduct[Result]
]
"""Builds one bound product from a declaration and its source artefact."""


class ProductRegistry[Declaration, Result]:
    """The one homogeneous owner of one declaration kind's bindings.

    Homogeneous on purpose: a registry holding several declaration kinds would
    have to erase ``Result`` to store them together, and a result-erasing
    registry is what the typed seam exists to avoid. One kind, one registry,
    one ``Result``.

    **Construct these as module-level singletons, one per declaration kind.**
    :func:`~lexic.parsing.caches.memo` registers the entries dict globally, so
    a registry minted per call would grow the registry list without bound —
    and would also be a second cache of the same binding, which the design
    forbids outright.
    """

    __slots__ = ("_binds", "_entries", "_lock")

    def __init__(self) -> None:
        """Register this kind's entries with the shared lifetime protocol."""
        self._entries: dict[tuple[int, int], _Entry[Declaration, Result]] = memo({}, 1)
        self._lock = Lock()
        self._binds = 0

    @property
    def binds(self) -> int:
        """How many cold binds have run — evidence, without exposing entries."""
        return self._binds

    def bind(
        self,
        declaration: Declaration,
        source: object,
        factory: BindingFactory[Declaration, Result],
    ) -> RegisteredProduct[Result]:
        """The bound product for one declaration over one source artefact.

        :param declaration: The inert declaration being bound.
        :param source: The compiled artefact it binds against; its death
            releases this entry.
        :param factory: Builds the bound product on a cold miss.
        :returns: The bound runner — the same object on every warm call.
        """
        key = (id(declaration), id(source))
        warm = self._entries.get(key)
        if warm is not None and self._matches(warm, declaration, source):
            return warm.bound
        return self._bind_cold(key, declaration, source, factory)

    def _bind_cold(
        self,
        key: tuple[int, int],
        declaration: Declaration,
        source: object,
        factory: BindingFactory[Declaration, Result],
    ) -> RegisteredProduct[Result]:
        """Bind under the lock, re-checking so a race compiles once."""
        with self._lock:
            found = self._entries.get(key)
            if found is not None and self._matches(found, declaration, source):
                return found.bound
            bound = factory(declaration, source)
            self._binds += 1
            self._entries[key] = _Entry(declaration, weakref.ref(source), bound)
            # The source's death releases this entry, and everything the
            # binding derived rides the same identity so the whole chain —
            # program, tables, replicas — goes with it.
            track(source, source)
            adopt(id(source), bound)
            return bound

    @staticmethod
    def _matches(
        entry: _Entry[Declaration, Result], declaration: Declaration, source: object
    ) -> bool:
        """Whether a hit really is this declaration over this source.

        Identity keys can collide after an address is recycled, so a hit is
        confirmed against the objects themselves before it is served.
        """
        return entry.declaration is declaration and entry.source() is source


def register_model(
    codegen_grammar: IrAst,
    view: list[RuleMap],
    classes: dict[str, type],
    omit: frozenset[str] = frozenset(),
) -> ModelExecutable[GrammarModel]:
    """The generated-model product a parse entry is handed.

    The one place a compilation turns its binding view into a bound product,
    so the two artefact paths — a compile and a derived variant — cannot
    drift about how one is built.

    :param codegen_grammar: The post-pass grammar the view was computed on.
    :param view: The binding view, in emission order.
    :param classes: Generated classes by class name.
    :param omit: Rules kept recognition-only by leaving them out.
    :returns: The bound model product.
    """
    plan = model_plan(codegen_grammar, view, classes, omit=omit)
    return ModelExecutable(
        rules_by_name(plan.rules, plan.codes),
        LoweringOwned(constructors=plan.constructors),
    )


def rules_by_name(
    rules: Sequence[RuleProduct], codes: Mapping[str, int]
) -> dict[str, RuleProduct]:
    """One authored product's rules, keyed the way a clone compiler asks.

    A clone knows the rule it stands for by NAME; an authored product orders
    its rules by contextual code. This is the one place that turns one into
    the other, so the two authoring paths — the generated model's binding view
    and an authored surface's own table — hand the engine the same shape.

    :param rules: The authored rules, in contextual-code order.
    :param codes: Rule name → its contextual code.
    :returns: Rule name → its authored product.
    """
    return {name: rules[code] for name, code in codes.items()}
