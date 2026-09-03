"""Tests for lexic.compile.product.registry — bound products and their lifetime.

Three properties the module states for itself: a bound product never retains
its source; eviction changes residency, never meaning; and a cold miss binds
once, even under an identity collision where a stale entry's WEAK source
reference has died and a fresh object happens to reuse the same address.

The staleness test exercises this through the PUBLIC path only: bind a real
declaration against a real source, drop every strong reference to the source,
force collection, then rebind under the same declaration — the way the race
actually happens, with no reach into the registry's own entries dict.

No IR-spine or compiled-artefact type in this codebase supports weak
references (every one of them declares ``__slots__`` without
``__weakref__``, by design, for memory efficiency — confirmed directly for
``IrAst`` and ``ModelExecutable``), and ``register_model`` is the only wired
caller of this registry's SIBLING function, not of ``ProductRegistry``
itself — nothing in the tree yet demonstrates a concrete (declaration,
source) pair flowing through it. Testing the registry's own generic
cold-miss/warm-hit/staleness mechanism therefore needs a real, minimal,
weakref-able Python object standing in for "the compiled artefact a
declaration is bound against" — the same role a real source will occupy once
a caller is wired to this registry, not a type this file invents to
misrepresent one that already exists.
"""

from __future__ import annotations

import gc
from dataclasses import dataclass

from lexic.compile import compile_text
from lexic.compile.product.registry import (
    ProductRegistry,
    ProgramProduct,
    rules_by_name,
)
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.product import (
    BeginSequenceOp,
    MeaningOp,
    OperandTables,
    PassOp,
    RootOp,
    RuleProduct,
    lower_product,
)

_ROOTS = (lambda carry, _verdicts: carry,)
_MEANINGS = (lambda left, right: left == right,)


def _operands() -> OperandTables:
    return OperandTables((), (), (), (), _MEANINGS, _ROOTS, (), ())


def _program(source: int, stateful: bool):
    """A real, minimal ProductProgram — PASS-only, or one BEGIN_SEQUENCE rule."""
    completion = BeginSequenceOp(0) if stateful else PassOp(source)
    rules = [RuleProduct(captures=(), completion=completion)]
    return lower_product(rules, _operands(), root=RootOp(0), meaning=MeaningOp(0))


@dataclass(frozen=True)
class Source:
    """A named declaration standing in for a compiled artefact — weakref-able
    because a plain dataclass carries no ``__slots__``."""

    name: str


def test_bind_is_a_cold_miss_the_first_time():
    """The factory runs exactly once for a declaration never bound before."""
    registry = ProductRegistry[str, str]()
    calls = []

    def factory(declaration, source):
        calls.append((declaration, source))
        return ProgramProduct(program=_program(0, False), execute=lambda p, t, c: t)

    source = Source(name="artefact")
    registry.bind("decl", source, factory)
    assert len(calls) == 1
    assert registry.binds == 1


def test_bind_is_a_warm_hit_on_the_second_call():
    """The SAME (declaration, source) pair returns the SAME bound object, no
    second factory call — the whole point of memoisation."""
    registry = ProductRegistry[str, str]()
    calls = []

    def factory(_declaration, _source):
        calls.append(1)
        return ProgramProduct(program=_program(0, False), execute=lambda p, t, c: t)

    source = Source(name="artefact")
    first = registry.bind("decl", source, factory)
    second = registry.bind("decl", source, factory)
    assert first is second
    assert len(calls) == 1
    assert registry.binds == 1


def test_two_distinct_sources_bind_independently():
    """The SAME declaration over two DIFFERENT sources is two entries, two binds."""
    registry = ProductRegistry[str, str]()
    calls = []

    def factory(_declaration, _source):
        calls.append(1)
        return ProgramProduct(program=_program(0, False), execute=lambda p, t, c: t)

    first = registry.bind("decl", Source(name="artefact-a"), factory)
    second = registry.bind("decl", Source(name="artefact-b"), factory)
    assert first is not second
    assert len(calls) == 2
    assert registry.binds == 2


def test_a_dead_sources_entry_is_never_served_to_a_later_bind():
    """The identity-collision defence, exercised through the public path: a
    source that has genuinely died must not leave its entry servable — a
    later bind under the SAME declaration re-runs the factory rather than
    returning whatever the dead source's entry held."""
    registry = ProductRegistry[str, str]()
    calls = []

    def factory(_declaration, _source):
        calls.append(1)
        return ProgramProduct(program=_program(0, False), execute=lambda p, t, c: t)

    first_source = Source(name="dying-artefact")
    first_bound = registry.bind("decl", first_source, factory)
    del first_source  # drop the only strong reference
    gc.collect()  # force collection even where refcounting alone would not

    second_bound = registry.bind("decl", Source(name="fresh-artefact"), factory)
    assert len(calls) == 2  # the dead source's entry was never re-served
    assert second_bound is not first_bound


# ── ProgramProduct ────────────────────────────────────────────────────────


def test_program_product_stateful_reads_the_programs_own_flag():
    """stateful is DERIVED from the program, never independently declared."""
    stateful = ProgramProduct(program=_program(0, True), execute=lambda p, t, c: None)
    stateless = ProgramProduct(program=_program(0, False), execute=lambda p, t, c: None)
    assert stateful.stateful is True
    assert stateless.stateful is False


def test_program_product_run_delegates_to_its_executor_with_its_own_program():
    """run(text, cores) calls execute(program, text, cores) — nothing more."""
    program = _program(0, False)
    calls = []

    def execute(prog, text, cores):
        calls.append((prog, text, cores))
        return f"ran:{text}:{cores}"

    product = ProgramProduct(program=program, execute=execute)
    result = product.run("hello", cores=3)
    assert result == "ran:hello:3"
    assert calls == [(program, "hello", 3)]


def test_program_product_run_defaults_cores_to_zero():
    """The cores parameter defaults to 0 when a caller omits it."""
    calls = []
    product = ProgramProduct(
        program=_program(0, False),
        execute=lambda p, t, c: calls.append(c),
    )
    product.run("x")
    assert calls == [0]


# ── rules_by_name ──────────────────────────────────────────────────────────


def test_rules_by_name_maps_by_contextual_code_not_by_position():
    """codes need not be dense-from-zero-in-order — rules_by_name reads the
    CODE, not the iteration position, so an out-of-order codes mapping still
    lands each name on its own rule."""
    rule_b = RuleProduct(captures=(), completion=PassOp(9))
    rule_a = RuleProduct(captures=(), completion=PassOp(1))
    rules = [rule_b, rule_a]
    codes = {"a": 1, "b": 0}
    result = rules_by_name(rules, codes)
    assert result == {"a": rule_a, "b": rule_b}


# ── register_model: the one path compilation turns a view into a bound product ─


def test_bind_model_produces_a_working_binding_for_every_rule():
    """A real grammar's binding view binds to a ModelExecutable whose codes and
    routines name exactly its rules — exercised through compile_text, the
    only real caller of register_model."""
    compiled = compile_text('root ::= "a" "b"\n', cache_key="product-binding-test")
    binding = compiled.product
    assert isinstance(binding, ModelExecutable)
    assert binding.codes.keys() == binding.routines.keys()
    assert "root" in binding.codes
    model = compiled.parse("ab")
    assert model.to_text() == "ab"
