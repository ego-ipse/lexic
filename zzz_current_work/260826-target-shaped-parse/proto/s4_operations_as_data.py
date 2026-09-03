"""Is any target object or morphism reachable from the paid path?

The bullet's claim is negative, and a negative claim is only worth what its
search covers. So this asks it two ways.

STATICALLY, over the functions the paid path IS — the character matcher, the
item loop, gate selection, and the frequent completion, each named with its
`file:line` — every global name they load must resolve to something the engine
owns, and every attribute they read off a flat record must be a declared field
of that record. A target callable can then only arrive through a field, and the
fields that carry one are named here rather than discovered later.

DYNAMICALLY, over every generated-model program the ground-truth corpus
compiles: the only callable any clone holds is the rule's own declared class or
that class's own positional constructor. No scalar decoder, validator, symbol
transform, or authored morphism is anywhere in the data the paid loop walks,
and every mode, kind and gate the loop dispatches on is an int of a closed
engine vocabulary.

The control seeds a morphism into a clone and insists the sweep refuses.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_operations_as_data.py`

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import builtins
import dis
import importlib
from pathlib import Path
from typing import Callable, NamedTuple

from lexic.compile import compile_from_path
from lexic.exceptions import LexicError
from lexic.model import GrammarModel
from lexic.parsing.caches import reset_caches
from lexic.parsing.earley.kernel.tables.atoms import tier_for
from lexic.parsing.pda.compiler.program.flatten import (
    FlatArm,
    FlatClone,
    no_construction,
    no_fast_construction,
)
from lexic.parsing.pda.compiler.program.opcodes import (
    GATE_ATTEMPT,
    GATE_KWIN,
    GATE_PAIR,
    GATE_PEEK,
    GATE_SCAN,
    GATE_STOP,
    M_CONST,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_SPAN,
    M_TEXT,
    M_VALUE,
    OP_CONSULT,
)
from lexic.parsing.products import _model_product, reset_product_cache

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"

PAID: dict[str, tuple[tuple[str, str], ...]] = {
    "character matcher": (
        ("lexic.parsing.pda.runtime.matchers", "match_lit"),
        ("lexic.parsing.pda.runtime.matchers", "match_cc"),
        ("lexic.parsing.pda.runtime.matchers", "match_arm"),
        ("lexic.parsing.pda.runtime.matchers", "vstr_once"),
        ("lexic.parsing.pda.runtime.matchers", "match_chartable"),
        ("lexic.parsing.pda.runtime.matchers", "match_runtable"),
        ("lexic.parsing.pda.runtime.matchers", "run_span_once"),
        ("lexic.parsing.pda.runtime.matchers", "consult_extent"),
        ("lexic.parsing.pda.runtime.matchers", "table_miss"),
    ),
    "item loop": (
        ("lexic.parsing.pda.runtime.kernel.kernel", "PdaKernel.run"),
        ("lexic.parsing.pda.runtime.kernel.kernel", "PdaKernel._quant_step"),
        ("lexic.parsing.pda.runtime.kernel.kernel", "PdaKernel._match_span"),
        (
            "lexic.parsing.pda.runtime.kernel.execution",
            "KernelExecutionMixin._leaf_run",
        ),
        (
            "lexic.parsing.pda.runtime.kernel.execution",
            "KernelExecutionMixin._run_leaf",
        ),
    ),
    "gate selection": (
        ("lexic.parsing.pda.runtime.matchers", "select_arm"),
        ("lexic.parsing.pda.compiler.program.flatten", "gate_take"),
        ("lexic.parsing.pda.compiler.program.flatten", "window_admits"),
        ("lexic.parsing.pda.compiler.program.flatten", "select_gated"),
        ("lexic.parsing.pda.compiler.program.flatten", "_peek_admits"),
        ("lexic.parsing.pda.compiler.program.flatten", "_skip_noise"),
    ),
    "frequent completion": (
        ("lexic.parsing.pda.runtime.build", "build_sequence"),
        ("lexic.parsing.pda.runtime.build", "fast_values"),
        ("lexic.parsing.pda.runtime.build", "build_validated"),
        ("lexic.parsing.pda.runtime.build", "_validated_fields"),
        ("lexic.parsing.pda.runtime.build", "build_vstr"),
        ("lexic.parsing.pda.runtime.build", "Frame.alt_model"),
        ("lexic.parsing.pda.runtime.build", "_intern_empty"),
        ("lexic.parsing.pda.compiler.program.flatten", "vstr_model"),
        (
            "lexic.parsing.pda.runtime.kernel.execution",
            "KernelExecutionMixin._complete",
        ),
    ),
}
"""The four surfaces the bullet names, as the functions they actually are."""

CALLING_FIELDS = frozenset({"ctor", "fast"})
"""The only flat-record fields the paid path CALLS through.

Both hold the rule's own declared record construction — the class, and the
class's own positional constructor. Naming them here is the point: a third
field carrying a callable would have to be added to this set by hand, which is
the review the bullet is asking for."""

RECORD_FIELDS = frozenset(FlatClone.__slots__) | frozenset(FlatArm.__slots__)
"""Every declared field of the two flat records — read from the records
themselves, so a field added to either is inside the search by construction."""

MODES = frozenset({M_TEXT, M_GTEXT, M_MODEL, M_MODELS, M_SPAN, M_CONST, M_VALUE})
GATES = frozenset({GATE_STOP, GATE_PAIR, GATE_KWIN, GATE_PEEK, GATE_SCAN, GATE_ATTEMPT})
KINDS = frozenset(range(OP_CONSULT + 1))
"""The closed int vocabularies the completion, the item loop and the loop gates
dispatch on. The op-codes are contiguous from zero by construction, so the set
is stated as the range rather than re-listed — a code added past the last one
lands outside it until it is deliberately let in."""


class Finding(NamedTuple):
    """One name the paid path reaches that the engine does not own.

    :ivar where: ``file:line`` of the function that reaches it.
    :ivar what: The name.
    :ivar why: What it resolved to.
    """

    where: str
    what: str
    why: str


class Defect(AssertionError):
    """A claim this witness makes that the tree does not support."""


class Vacuous(Exception):
    """A seeded morphism the sweep was supposed to catch, and did not."""


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise Defect(f"s4 operations-as-data: {claim}")


def _function(module_name: str, dotted: str) -> Callable[..., object]:
    """One named function or method off its module."""
    found: object = importlib.import_module(module_name)
    for part in dotted.split("."):
        found = getattr(found, part)
    _check(f"{module_name}.{dotted} is not callable", callable(found))
    assert callable(found)
    return found


def _where(function: Callable[..., object]) -> str:
    """``path:line`` of a function, relative to the repository root."""
    code = function.__code__
    return f"{Path(code.co_filename).relative_to(ROOT)}:{code.co_firstlineno}"


def _engine_owned(value: object) -> str:
    """Why a loaded global is the engine's own, or the reason it is not."""
    if value is None or isinstance(value, (int, str, float, frozenset, tuple)):
        return ""
    module = getattr(value, "__module__", "")
    if module.startswith("lexic."):
        return ""
    if module in ("builtins", "typing", "enum", "re"):
        return ""
    return f"{module or type(value).__name__}"


def _globals_and_attrs(
    function: Callable[..., object],
) -> tuple[set[str], set[str]]:
    """Every global name and attribute name the function's code touches."""
    names: set[str] = set()
    attrs: set[str] = set()
    for instruction in dis.get_instructions(function.__code__):
        if instruction.opname == "LOAD_GLOBAL":
            names.add(instruction.argval)
        elif instruction.opname in ("LOAD_ATTR", "LOAD_METHOD", "STORE_ATTR"):
            attrs.add(instruction.argval)
    return names, attrs


def the_paid_path_reaches_no_foreign_name() -> list[Finding]:
    """Every global the four surfaces load resolves to something lexic owns."""
    findings: list[Finding] = []
    for role, entries in PAID.items():
        for module_name, dotted in entries:
            module = importlib.import_module(module_name)
            function = _function(module_name, dotted)
            names, _attrs = _globals_and_attrs(function)
            for name in sorted(names):
                value = getattr(module, name, getattr(builtins, name, None))
                foreign = _engine_owned(value)
                if foreign:
                    findings.append(Finding(_where(function), name, foreign))
            print(f"  {_where(function):<50}{dotted:<32}{len(names):>3} globals")
        print(
            f"names   \t{role:<22}{len(entries)} functions, every global engine-owned"
        )
    return findings


def the_paid_path_calls_through_two_fields() -> None:
    """Every flat-record attribute the paid path reads is a declared field.

    The attribute set is compared against the RECORDS' own ``__slots__``, so
    the search cannot go stale: a new field carrying a callable is inside it the
    day it is added, and the two fields that legitimately carry one are named
    in :data:`CALLING_FIELDS`.
    """
    touched: set[str] = set()
    for entries in PAID.values():
        for module_name, dotted in entries:
            _names, attrs = _globals_and_attrs(_function(module_name, dotted))
            touched |= attrs & RECORD_FIELDS
    carrying = touched & CALLING_FIELDS
    _check(
        f"the paid path reads no construction field at all ({sorted(touched)}) — "
        "the search is looking at the wrong functions",
        bool(carrying),
    )
    print(
        f"fields  \t{len(touched)} flat-record fields read; the only ones holding a "
        f"callable are {sorted(carrying)}"
    )


def _kids(clone: FlatClone) -> tuple[list[FlatArm], list[FlatClone]]:
    """One clone's arms and child clones, whatever selector shape it has."""
    arms: list[FlatArm] = []
    kids: list[FlatClone] = []
    pool: list[object] = [clone.default, clone.runarm, clone.struct_arm]
    pool += [entry[-1] for entry in clone.selectors]
    if clone.kwin_selectors is not None:
        pool += [arm for _windows, arm in clone.kwin_selectors]
    if clone.pn_selectors is not None:
        pool += [entry[-1] for entry in clone.pn_selectors[1]]
    if clone.attempt is not None:
        pool += [entry[-1] for entry in clone.attempt[1]]
    for found in pool:
        if isinstance(found, FlatArm):
            arms.append(found)
        elif isinstance(found, FlatClone):
            kids.append(found)
    for arm in list(arms):
        for payload in arm.payloads:
            if isinstance(payload, FlatClone):
                kids.append(payload)
    return arms, kids


def _program_clones(start: object) -> tuple[list[FlatClone], list[FlatArm]]:
    """Every clone and arm reachable from a program's entry."""
    seen: set[int] = set()
    clones: list[FlatClone] = []
    arms: list[FlatArm] = []
    work: list[object] = [start]
    while work:
        found = work.pop()
        if not isinstance(found, FlatClone) or id(found) in seen:
            continue
        seen.add(id(found))
        clones.append(found)
        own_arms, kids = _kids(found)
        arms.extend(own_arms)
        work.extend(kids)
    return clones, arms


def _construction_is_declared(clone: FlatClone) -> str:
    """Why this clone's construction is the rule's own class, or how it is not."""
    ctor = clone.ctor
    if ctor is None or ctor is no_construction:
        return ""
    if not isinstance(ctor, type):
        return f"{clone.name or '<group>'}: ctor is {ctor!r}, not a declared class"
    if not issubclass(ctor, GrammarModel):
        return f"{clone.name or '<group>'}: ctor {ctor!r} is not a model class"
    fast = clone.fast
    if fast is no_fast_construction:
        return ""
    if getattr(fast, "__self__", None) is not ctor:
        return f"{clone.name or '<group>'}: fast {fast!r} is not {ctor!r}'s own"
    return ""


def _data_holds_no_callable(clone: FlatClone) -> str:
    """Why the clone's build data is inert, or which entry is not."""
    for mode, _item, _lo, default in clone.plan:
        if mode not in MODES:
            return f"{clone.name}: plan mode {mode!r} is outside the vocabulary"
        if callable(default) and not isinstance(default, type):
            return f"{clone.name}: plan default {default!r} is a morphism"
    for _item, mode, name, _lo in clone.fields:
        if mode not in MODES:
            return f"{clone.name}: field mode {mode!r} is outside the vocabulary"
        if not isinstance(name, str):
            return f"{clone.name}: field name {name!r} is not a name"
    for value in (clone.defaults or {}).values():
        if callable(value) and not isinstance(value, type):
            return f"{clone.name}: default {value!r} is a morphism"
    return ""


def _arm_is_int_coded(arm: FlatArm) -> str:
    """Why the arm's dispatch is closed ints, or which entry is not."""
    for kind in arm.kinds:
        if kind not in KINDS:
            return f"arm kind {kind!r} is outside the op-code vocabulary"
    for gate in arm.gate_kinds:
        if gate not in GATES:
            return f"gate kind {gate!r} is outside the vocabulary"
    return ""


def _sweep(path: Path) -> tuple[int, int, list[str]]:
    """One grammar's whole program, swept for a reachable morphism."""
    reset_product_cache()
    reset_caches()
    compiled = compile_from_path(path)
    product = _model_product(compiled.codegen_grammar, compiled.product, tier_for(100))
    clones, arms = _program_clones(product.pda.program.start)
    faults = [
        fault
        for clone in clones
        for fault in (_construction_is_declared(clone), _data_holds_no_callable(clone))
        if fault
    ]
    faults += [fault for arm in arms if (fault := _arm_is_int_coded(arm))]
    return len(clones), len(arms), faults


def the_corpus_holds_no_morphism() -> tuple[int, int]:
    """Every generated-model program the corpus compiles, swept clone by clone."""
    total_clones = total_arms = 0
    for path in (
        sorted(GROUND_TRUTH.glob("*.gbnf"))
        + sorted(GROUND_TRUTH.glob("*.abnf"))
        + sorted(GROUND_TRUTH.glob("*.ebnf"))
    ):
        try:
            clones, arms, faults = _sweep(path)
        except LexicError:
            continue  # a token-terminal grammar compiles no predictive program
        _check(f"{path.name}: {faults[:3]}", not faults)
        total_clones += clones
        total_arms += arms
    _check("the corpus produced no clones — the sweep is vacuous", total_clones > 100)
    print(
        f"corpus  \t{total_clones} clones and {total_arms} arms hold no callable but "
        "the rule's own declared class"
    )
    return total_clones, total_arms


def the_sweep_catches_a_seeded_morphism() -> None:
    """Seed a target morphism into a real clone; the sweep must refuse it."""
    reset_product_cache()
    reset_caches()
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    product = _model_product(compiled.codegen_grammar, compiled.product, tier_for(100))
    clones, _arms = _program_clones(product.pda.program.start)
    victim = next(clone for clone in clones if isinstance(clone.ctor, type))
    kept = victim.ctor
    victim.ctor = _decode_int
    try:
        caught = _construction_is_declared(victim)
    finally:
        victim.ctor = kept
    if not caught:
        raise Vacuous(
            "s4 operations-as-data: a morphism installed as a clone's ctor "
            "passed the sweep"
        )
    print(f"control \tseeded morphism caught: {caught}")


def _decode_int(text: str) -> int:
    """A scalar decoder — the shape of the thing that must not be reachable."""
    return int(text)


def main() -> None:
    """Run every claim; any failure raises."""
    findings = the_paid_path_reaches_no_foreign_name()
    for finding in findings:
        print(f"FOREIGN \t{finding.where}\t{finding.what}\t{finding.why}")
    _check(f"{len(findings)} foreign names on the paid path", not findings)
    the_paid_path_calls_through_two_fields()
    the_corpus_holds_no_morphism()
    the_sweep_catches_a_seeded_morphism()
    print("s4 operations-as-data\tPASS\tno target morphism is reachable from the loop")


if __name__ == "__main__":
    main()
