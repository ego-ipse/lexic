"""What the LIVE bake writes IS what the rule's product declares.

The bake is no longer two implementations to diff: `bake_product_build` writes
a clone's whole build state from its product, and the fold is gone from the
runtime entirely. The question the witness has to answer changed with it, from
"do two bakes agree" to "does the one bake say what the ABI declares".

So this asserts PROPERTIES of the live bake over every rule and every clone of
the ground-truth corpus, and asserts most of them BEHAVIOURALLY — by driving
the real `fast_values` / `vstr_model` over synthesized frame captures and
reading the constructed model's fields back by name. A property phrased that
way cannot be satisfied by a bake that merely agrees with itself:

* **Class-field order.** The plan has one entry per class field, and the field
  each entry fills is the field the record says fills it. Read back off the
  built model, so a permuted plan is a wrong model rather than a wrong tuple.
* **Absence, coded per `optional`.** A capture the record admits being absent
  takes the class's DEFAULT when its span is empty; one it does not takes the
  empty string. This is the gtext absence-vs-empty-string row, on the real
  corpus, through the real build.
* **`matched_field`.** A `value_str` rule's own matched extent fills the field
  the record names — checked through `vstr_model`, which is the only builder
  that ever sees an `M_VALUE` plan entry.
* **Cleared state.** A transparent clone and a pass-through leave the four
  fused-build fields saying nothing, and name no constructor.
* **The build mode, and the arm width.** Read off the completion record and
  the rule, so a transparent clone, a pass-through, a record build and a
  value_str are four answers to one question rather than a second vocabulary.
* **Item ends kept for TEXT or EXTENT.** Both read an item's end position back
  off the frame, so a clone with either keeps them.
* **No symbol reaches the model product.** Not one symbol opcode and not one
  resolved callable, over every grammar's lowered model program.

The three `lo` zero-test predicates keep their exhaustiveness pin, tokenized
rather than grepped, because the `0 if optional else 1` normalization is only
sound while that list is the whole of them.

Every property is proved live by a seeded defect: `the_checks_are_live` mutates
a real constructor five ways and insists each one is caught.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

import io
import tokenize
from pathlib import Path
from typing import Any, Callable

from lexic.compile import compile_from_path
from lexic.compile.pipeline.synthesis import ModelPlan, model_plan
from lexic.compile.product import LoweringOwned, lower_product
from lexic.compile.product.binding import _check_covered, rules_by_name
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import IrSpan
from lexic.parsing.pda.compiler.program.flatten import FlatClone, vstr_model
from lexic.parsing.pda.compiler.program.opcodes import (
    BUILD_ALT,
    BUILD_SEQ,
    BUILD_TRANSPARENT,
    BUILD_VALUE_STR,
    M_CONST,
    M_GTEXT,
    M_MODEL,
    M_MODELS,
    M_SPAN,
    M_TEXT,
    M_VALUE,
)
from lexic.parsing.pda.compiler.program.product import bake_product_build
from lexic.parsing.pda.runtime.build import fast_values
from lexic.parsing.product import (
    CaptureMode,
    ConstructionTables,
    ExprCode,
    MeaningOp,
    OperandTables,
    PassOp,
    RecordConstructor,
    RecordOp,
    RootOp,
    RuleProduct,
)

EMPTY_OPERANDS: OperandTables = OperandTables(
    constants=(),
    constructors=(),
    sequences=(),
    mappings=(),
    meanings=(),
    roots=(),
    routes=(),
    continuations=(),
)
"""The model product builds records and nothing else, so every operand table
but the constructors lowering fills is empty."""

ROOT = Path(__file__).resolve().parents[3]
GROUND_TRUTH = ROOT / "resources" / "ground_truth"
BUILD_SOURCE = ROOT / "src" / "lexic" / "parsing" / "pda" / "runtime" / "build.py"

TEXT_MODES = frozenset({M_TEXT, M_GTEXT})
ITEM_MODES = frozenset({M_TEXT, M_GTEXT, M_SPAN, M_MODEL, M_MODELS})
"""Plan modes that read one item's captured span or sink."""

FILLED = "abcdefghijklmnopqrstuvwxyz" * 8
"""Enough distinct characters that every item's synthesized span is unique."""


class Defect(Exception):
    """A seeded defect the property checks were supposed to catch, and did."""


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s4 bake identity: {claim}")


# ── the live bake ─────────────────────────────────────────────────────


def _shell() -> FlatClone:
    """An empty clone shell — only the build state is written into it."""
    return FlatClone.__new__(FlatClone)


def _baked(product: RuleProduct | None, tables: ConstructionTables) -> FlatClone:
    """One clone's build state, from the shipped bake."""
    clone = _shell()
    bake_product_build(clone, product, tables)
    return clone


def _constructor_of(
    product: RuleProduct | None, tables: ConstructionTables
) -> RecordConstructor | None:
    """The constructor record a rule's completion names, if it names one."""
    if product is None or not isinstance(product.completion, RecordOp):
        return None
    return tables.constructors[product.completion.constructor]


# ── synthesized frame captures ────────────────────────────────────────


def _item_count(clone: FlatClone) -> int:
    """How many items the clone's plan and capture layout reach into."""
    items = [row[1] for row in clone.plan if row[0] in ITEM_MODES]
    items += [row[0] for row in clone.fields]
    return max(items, default=-1) + 1


def _captures(clone: FlatClone, filled: bool) -> tuple[str, int, list[int], list[Any]]:
    """A frame's ``(text, start, ends, sinks)`` for one clone.

    ``filled`` gives item ``i`` the one-character span ``FILLED[i]``; its
    negation gives every item the EMPTY span, which is the only input that can
    separate an absence-bearing capture from a required one.
    """
    n = _item_count(clone)
    ends = [i + 1 for i in range(n)] if filled else [0] * n
    sinks: list[Any] = [[f"<model {i}>", f"<extra {i}>"] for i in range(n)]
    return FILLED, 0, ends, sinks


def _span_of(text: str, start: int, ends: list[int], item: int) -> str:
    """Item ``item``'s captured text — the frame's own span convention."""
    return text[(start if item == 0 else ends[item - 1]) : ends[item]]


def _declared_value(
    name: str,
    at: int | None,
    product: RuleProduct,
    constructor: RecordConstructor,
    frame: tuple[str, int, list[int], list[Any]],
) -> object:
    """What the RECORD says one class field is built from.

    Written from :class:`RecordConstructor`'s declared meaning rather than from
    the bake's plan, so agreement is evidence instead of a tautology.
    """
    text, start, ends, sinks = frame
    if at is None:
        return constructor.defaults.get(name)
    spec = product.captures[at]
    if spec.mode == CaptureMode.ONE:
        return sinks[spec.slot][0]
    if spec.mode == CaptureMode.MANY:
        return tuple(sinks[spec.slot])
    if spec.mode == CaptureMode.EXTENT:
        return IrSpan(start if spec.slot == 0 else ends[spec.slot - 1], ends[spec.slot])
    span = _span_of(text, start, ends, spec.slot)
    if not span and at in constructor.optional:
        return constructor.defaults.get(name)  # ABSENT — never the empty string
    return span


# ── the properties ────────────────────────────────────────────────────


def _check_cleared(label: str, clone: FlatClone) -> None:
    """A clone that builds nothing says nothing, not something empty-looking."""
    _check(f"{label}: cleared clone kept fields {clone.fields}", clone.fields == ())
    _check(f"{label}: cleared clone kept plan {clone.plan}", clone.plan == ())
    _check(f"{label}: cleared clone kept fast {clone.fast!r}", clone.fast is None)
    _check(
        f"{label}: cleared clone kept defaults {clone.defaults!r}",
        clone.defaults is None,
    )


def _check_fields(
    label: str, clone: FlatClone, product: RuleProduct, constructor: RecordConstructor
) -> None:
    """The capture layout: one row per capture, absence coded in mode and lo."""
    _check(
        f"{label}: {len(clone.fields)} field rows for {len(product.captures)} captures",
        len(clone.fields) == len(product.captures),
    )
    for at, (item, mode, name, lo) in enumerate(clone.fields):
        spec = product.captures[at]
        absent = at in constructor.optional
        where = f"{label}.fields[{at}]"
        _check(f"{where}: item {item} for capture slot {spec.slot}", item == spec.slot)
        _check(
            f"{where}: name {name!r} for declared field {constructor.names[at]!r}",
            name == constructor.names[at],
        )
        _check(f"{where}: lo {lo} for optional={absent}", lo == (0 if absent else 1))
        _check(
            f"{where}: mode {mode} codes absence {mode == M_GTEXT} for {absent}",
            (mode == M_GTEXT) == (absent and spec.mode == CaptureMode.TEXT),
        )
        _check(
            f"{where}: mode {mode} is not a text mode for a TEXT capture",
            (mode in TEXT_MODES) == (spec.mode == CaptureMode.TEXT),
        )


def _check_needs_ends(label: str, clone: FlatClone, product: RuleProduct) -> None:
    """Item ends are kept exactly when some capture reads one."""
    wanted = any(
        spec.mode in (CaptureMode.TEXT, CaptureMode.EXTENT) for spec in product.captures
    )
    _check(
        f"{label}: needs_ends {clone.needs_ends} for text captures {wanted}",
        clone.needs_ends == wanted,
    )


def _check_plan_shape(
    label: str, clone: FlatClone, constructor: RecordConstructor
) -> None:
    """One plan entry per class field, and the licence is the class's own."""
    make, _defaults, order = constructor.cls.fast_construct()
    _check(
        f"{label}: plan of {len(clone.plan)} for a class of {len(order)} fields",
        len(clone.plan) == len(order),
    )
    _check(f"{label}: fast {clone.fast!r} is not the class's", clone.fast == make)
    _check(
        f"{label}: defaults {clone.defaults!r} vs declared {dict(constructor.defaults)}",
        clone.defaults == dict(constructor.defaults),
    )


def _check_built_model(
    label: str,
    clone: FlatClone,
    product: RuleProduct,
    constructor: RecordConstructor,
    filled: bool,
) -> None:
    """Build through the real `fast_values` and read every field back by name."""
    frame = _captures(clone, filled)
    text, start, ends, sinks = frame
    model = clone.fast(fast_values(text, clone, (start, ends, sinks)))
    filling = {name: at for at, name in enumerate(constructor.names)}
    for name in constructor.cls.fast_construct()[2]:
        want = _declared_value(name, filling.get(name), product, constructor, frame)
        got = getattr(model, name)
        _check(
            f"{label}[{'filled' if filled else 'empty'}].{name}: built {got!r}, "
            f"the record declares {want!r}",
            got == want,
        )


def _check_matched_field(
    label: str, clone: FlatClone, constructor: RecordConstructor
) -> None:
    """A value_str rule's own extent fills the field the record names."""
    codes = {row[0] for row in clone.plan}
    _check(
        f"{label}: plan carries M_VALUE {M_VALUE in codes} for matched_field "
        f"{constructor.matched_field!r}",
        (M_VALUE in codes) == bool(constructor.matched_field),
    )
    if not constructor.matched_field:
        return
    model = vstr_model(clone, "matched")
    for name in constructor.cls.fast_construct()[2]:
        want = "matched" if name == constructor.matched_field else None
        got = getattr(model, name)
        _check(
            f"{label}.{name}: value_str built {got!r}, the record declares {want!r}",
            got == (want if want is not None else constructor.defaults.get(name)),
        )


def _check_unfilled(
    label: str, clone: FlatClone, constructor: RecordConstructor
) -> None:
    """A field no capture fills is a constant, and its constant is the default."""
    filling = set(constructor.names)
    order = constructor.cls.fast_construct()[2]
    for at, name in enumerate(order):
        mode, _item, _lo, default = clone.plan[at]
        if name in filling or name == constructor.matched_field:
            continue
        _check(
            f"{label}.{name}: unfilled field bakes mode {mode}, not a constant",
            mode == M_CONST,
        )
        _check(
            f"{label}.{name}: unfilled constant {default!r} vs default "
            f"{constructor.defaults.get(name)!r}",
            default == constructor.defaults.get(name),
        )


def check_clone(
    label: str,
    product: RuleProduct | None,
    tables: ConstructionTables,
    totals: dict[str, int],
    baked_with: ConstructionTables | None = None,
) -> None:
    """Every property of one clone's live build state.

    ``baked_with`` is what the bake is HANDED and ``tables`` is what the
    record DECLARES; they are the same table in the sweep and differ only when
    a control seeds a defect into one side, which is the only way a check over
    a declaration can be shown to be watching the bake rather than itself.
    """
    clone = _baked(product, tables if baked_with is None else baked_with)
    constructor = _constructor_of(product, tables)
    totals["clones"] = totals.get("clones", 0) + 1
    _check_mode(label, clone, product, constructor)
    _check_arm_width(label, clone, product)
    if product is not None:
        _check_needs_ends(label, clone, product)
    if product is None or constructor is None:
        totals["no record"] = totals.get("no record", 0) + 1
        return
    _check(
        f"{label}: ctor {clone.ctor!r} is not the declared class",
        clone.ctor is constructor.cls,
    )
    _check(
        f"{label}: matched {clone.matched!r} vs declared {constructor.matched_field!r}",
        clone.matched == constructor.matched_field,
    )
    _check_fields(label, clone, product, constructor)
    if not constructor.licensed:
        totals["unlicensed"] = totals.get("unlicensed", 0) + 1
        _check(f"{label}: unlicensed clone kept a plan {clone.plan}", clone.plan == ())
        _check(
            f"{label}: unlicensed clone kept fast {clone.fast!r}", clone.fast is None
        )
        return
    totals["licensed"] = totals.get("licensed", 0) + 1
    _check_plan_shape(label, clone, constructor)
    _check_unfilled(label, clone, constructor)
    _check_matched_field(label, clone, constructor)
    if constructor.matched_field:
        return  # a value_str builds through vstr_model, never through the plan
    _check_built_model(label, clone, product, constructor, filled=True)
    _check_built_model(label, clone, product, constructor, filled=False)
    absent_text = [
        at
        for at in constructor.optional
        if product.captures[at].mode == CaptureMode.TEXT
    ]
    totals["absence_rows"] = totals.get("absence_rows", 0) + len(absent_text)


def _check_mode(
    label: str,
    clone: FlatClone,
    product: RuleProduct | None,
    constructor: RecordConstructor | None,
) -> None:
    """The build mode is what the completion record says it is."""
    if product is None:
        wanted = BUILD_TRANSPARENT
    elif constructor is None:
        wanted = BUILD_ALT if isinstance(product.completion, PassOp) else BUILD_SEQ
    else:
        wanted = BUILD_VALUE_STR if constructor.matched_field else BUILD_SEQ
    _check(
        f"{label}: mode {clone.mode} for a completion that wants {wanted}",
        clone.mode == wanted,
    )


def _check_arm_width(label: str, clone: FlatClone, product: RuleProduct | None) -> None:
    """The arm width is the rule's own, and nothing invents one."""
    wanted = 0 if product is None else product.n_items
    _check(
        f"{label}: n_items {clone.n_items} for a rule declaring {wanted}",
        clone.n_items == wanted,
    )


# ── the corpus sweep ──────────────────────────────────────────────────


def _model_program(label: str, plan: ModelPlan) -> None:
    """Lower the model product and insist no symbol reaches it."""
    program = lower_product(
        plan.rules,
        EMPTY_OPERANDS,
        owned=LoweringOwned(constructors=plan.constructors),
        root=RootOp(0),
        meaning=MeaningOp(0),
    )
    _check(
        f"{label}: the model product lowered "
        f"{program.expression_opcodes.count(int(ExprCode.SYMBOL))} symbol operations",
        int(ExprCode.SYMBOL) not in program.expression_opcodes,
    )
    _check(
        f"{label}: the model product carries {len(program.operands.symbols)} "
        f"resolved symbol callables",
        not program.operands.symbols,
    )


def _rule_level(label: str, compiled: Any, totals: dict[str, int]) -> None:
    """Every RULE of one grammar, through the live bake.

    Rule level rather than clone level so a grammar whose terminals name an
    encoding — and which therefore cannot compile predictive tables without a
    vocabulary — is still covered.
    """
    plan = model_plan(
        compiled.codegen_grammar, compiled.moments.binding, compiled.classes
    )
    _check(
        f"{label}: the plan covers {len(plan.codes)} rules, the fold "
        f"{len(compiled.fold.baked)}",
        set(plan.codes) == set(compiled.fold.baked),
    )
    _model_program(label, plan)
    totals["audited"] = totals.get("audited", 0) + len(plan.constructors)
    for name, code in plan.codes.items():
        check_clone(f"{label}/{name}", plan.rules[code], _tables(plan), totals)


def _clone_level(label: str, compiled: Any, totals: dict[str, int]) -> bool:
    """Every CLONE of one grammar — contextual copies and inline groups included.

    :returns: Whether the grammar's predictive tables could be compiled.
    """
    try:
        tables = compiled.pda_tables()
    except UnsupportedConstructError:
        return False
    construction = compiled.product.construction
    for key, spec in tables.clones.items():
        where = f"{label}/clone {spec.name or '<group>'} {key}"
        check_clone(where, spec.product, construction, totals)
        _check_no_fold(where)
    return True


def _check_no_fold(label: str) -> None:
    """The clone carries no fold at all — the runtime reads its own slots."""
    _check(
        f"{label}: FlatClone declares a `fold` slot again",
        "fold" not in FlatClone.__slots__,
    )


def _grammars() -> list[Path]:
    """The ground-truth corpus, in a fixed order."""
    paths = sorted(GROUND_TRUTH.glob("*.gbnf"))
    return (
        paths
        + sorted(GROUND_TRUTH.glob("*.abnf"))
        + sorted(GROUND_TRUTH.glob("*.ebnf"))
    )


def the_live_bake_says_what_the_product_declares() -> dict[str, int]:
    """The sweep: every rule and every clone of the whole corpus."""
    rules: dict[str, int] = {}
    clones: dict[str, int] = {}
    tabled = 0
    grammars = _grammars()
    for path in grammars:
        compiled = compile_from_path(path)
        _rule_level(path.name, compiled, rules)
        tabled += int(_clone_level(path.name, compiled, clones))
    print(
        f"rules\t{len(grammars)} grammars\trules={rules['clones']}\t"
        f"licensed={rules['licensed']}\tunlicensed={rules.get('unlicensed', 0)}\t"
        f"pass-through={rules.get('no record', 0)}\t"
        f"constructors audited={rules['audited']}"
    )
    print(
        f"clones\t{tabled} grammars\tclones={clones['clones']}\t"
        f"licensed={clones['licensed']}\tunlicensed={clones.get('unlicensed', 0)}\t"
        f"builds nothing={clones.get('no record', 0)}"
    )
    print(
        f"absence\t{clones['absence_rows']} optional TEXT captures built empty "
        f"and non-empty through the real fast_values"
    )
    _check(
        "no optional TEXT capture in the whole corpus — the absence row is vacuous",
        clones.get("absence_rows", 0) > 0,
    )
    return clones


# ── the seeded defects ────────────────────────────────────────────────


def _has_absent_text(product: RuleProduct, constructor: RecordConstructor) -> bool:
    """Whether the rule carries a TEXT capture the record admits being absent."""
    return any(
        product.captures[at].mode == CaptureMode.TEXT for at in constructor.optional
    )


def _is_value_str(_product: RuleProduct, constructor: RecordConstructor) -> bool:
    """Whether the rule's own matched extent fills a class field."""
    return bool(constructor.matched_field)


def _tables(plan: ModelPlan) -> ConstructionTables:
    """The model plan's construction tables — it names no symbol."""
    return ConstructionTables(plan.constructors)


def _corpus_row(
    wanted: Callable[[RuleProduct, RecordConstructor], bool], described: str
) -> tuple[str, RuleProduct, ConstructionTables]:
    """The first licensed corpus rule matching ``wanted`` — a control's subject."""
    for path in _grammars():
        compiled = compile_from_path(path)
        plan = model_plan(
            compiled.codegen_grammar, compiled.moments.binding, compiled.classes
        )
        for name, code in plan.codes.items():
            product = plan.rules[code]
            constructor = _constructor_of(product, _tables(plan))
            if constructor is None or not constructor.licensed:
                continue
            if wanted(product, constructor):
                return f"{path.name}/{name}", product, _tables(plan)
    raise AssertionError(f"s4 bake identity: the corpus has no {described}")


def _seeded(
    label: str,
    product: RuleProduct,
    tables: ConstructionTables,
    at: int,
    edit: Callable[[RecordConstructor], RecordConstructor],
) -> None:
    """Bake from a mutated constructor, declare from the real one, insist it refuses."""
    mutated = ConstructionTables(
        tuple(
            edit(entry) if index == at else entry
            for index, entry in enumerate(tables.constructors)
        ),
        tables.symbols,
    )
    try:
        check_clone(label, product, tables, {}, baked_with=mutated)
    except AssertionError, IndexError, KeyError, TypeError:
        return
    raise Defect(f"s4 bake identity: the seeded defect {label} went uncaught")


def the_checks_are_live() -> None:
    """Five seeded defects, each caught by the property it was aimed at."""
    label, product, tables = _corpus_row(
        _has_absent_text, "TEXT capture the record admits being absent"
    )
    at = product.completion.constructor
    print(f"control\tseeding defects into {label}")
    _seeded("absence dropped", product, tables, at, lambda c: c._replace(optional=()))
    _seeded(
        "names permuted",
        product,
        tables,
        at,
        lambda c: c._replace(names=c.names[::-1]),
    )
    _seeded("defaults dropped", product, tables, at, lambda c: c._replace(defaults={}))
    _seeded(
        "licence withdrawn",
        product,
        tables,
        at,
        lambda c: c._replace(licensed=False),
    )
    matched, vstr, vstr_tables = _corpus_row(_is_value_str, "value_str rule")
    print(f"control\tseeding the matched-field defect into {matched}")
    _seeded(
        "matched_field dropped",
        vstr,
        vstr_tables,
        vstr.completion.constructor,
        lambda c: c._replace(matched_field=""),
    )
    print("control\tfive seeded defects, five refusals")


# ── the exhaustiveness pin ────────────────────────────────────────────

EXPECTED_LO_READS = ("values.append(span if (span or lo) else default)",)
"""The ONE predicate that still consults a capture's `lo` at run time.

It was three. The keyword build lost the other two when it started reading
int-coded modes: under the product's coding `M_GTEXT` means exactly "this
capture may be absent", so `lo != 0` is false wherever that branch runs and the
test said nothing. The remaining reader is the positional plan's, where
`span or lo` is the same predicate written on a column the plan still carries."""

EXPECTED_LO_BINDS = ("for mode, item, lo, default in clone.plan:",)
"""The one place `lo` enters a runtime scope at all."""


def the_lo_readers_are_exactly_three() -> None:
    """Pin every `lo` occurrence in the runtime build, the bind included.

    Read off the source with the tokenizer rather than a grep, so a `lo`
    inside a string or a comment cannot pad the count and a fourth genuine
    reader cannot hide behind one.
    """
    source = BUILD_SOURCE.read_text(encoding="utf-8")
    lines = source.splitlines()
    sites = [
        token.start[0]
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.NAME and token.string == "lo"
    ]
    texts = [lines[number - 1].strip() for number in sites]
    binds = [text for text in texts if text.startswith("for ")]
    reads = [text for text in texts if not text.startswith("for ")]
    _check(
        f"build.py mentions `lo` at {len(sites)} places: {texts}",
        len(sites) == len(EXPECTED_LO_BINDS) + len(EXPECTED_LO_READS),
    )
    _check(f"the binds moved: {binds}", tuple(binds) == EXPECTED_LO_BINDS)
    _check(f"the readers moved: {reads}", tuple(reads) == EXPECTED_LO_READS)
    print(
        f"lo trace\t{len(EXPECTED_LO_BINDS)} bind + {len(EXPECTED_LO_READS)} "
        f"reader, a zero-test in a text branch"
    )


def the_plan_lo_has_one_other_consumer_and_it_discards_it() -> None:
    """`vstr_model` unpacks the plan and throws `lo` away — pin that it still does."""
    flatten = (
        ROOT
        / "src"
        / "lexic"
        / "parsing"
        / "pda"
        / "compiler"
        / "program"
        / "flatten.py"
    )
    source = flatten.read_text(encoding="utf-8")
    _check(
        "vstr_model no longer discards the plan's lo",
        "for mode, _i, _lo, default in plan" in source,
    )
    print("lo trace\tvstr_model unpacks the plan and discards lo")


def the_binding_guard_refuses_an_uncovered_fold() -> None:
    """A binding whose product names fewer rules than its fold is refused.

    The historical shape, exactly: a bare fold wrapped into a `ModelBinding`
    left the rules map EMPTY, every clone baked no build state, and nothing
    said so. `bind_model` cannot produce that from one binding view — which is
    why the guard needs a row of its own to show it is not decoration.
    """
    compiled = compile_from_path(GROUND_TRUTH / "json.gbnf")
    plan = model_plan(
        compiled.codegen_grammar, compiled.moments.binding, compiled.classes
    )
    covered = rules_by_name(plan.rules, plan.codes)
    _check_covered(covered, compiled.fold)  # the real pairing passes
    for label, rules in (
        ("an empty rules map", {}),
        ("one rule short", dict(list(covered.items())[1:])),
    ):
        try:
            _check_covered(rules, compiled.fold)
        except UnsupportedConstructError:
            continue
        raise Defect(f"s4 bake identity: bind_model's guard admitted {label}")
    print("guard\tan empty and a short rules map are both refused, with words")


def main() -> None:
    """Run the sweep, the controls and the pins; any disagreement raises."""
    counts = the_live_bake_says_what_the_product_declares()
    the_checks_are_live()
    the_binding_guard_refuses_an_uncovered_fold()
    the_lo_readers_are_exactly_three()
    the_plan_lo_has_one_other_consumer_and_it_discards_it()
    print(
        f"s4 bake identity\tPASS\t{counts['clones']} clones bake exactly what "
        f"their product declares"
    )


if __name__ == "__main__":
    main()
