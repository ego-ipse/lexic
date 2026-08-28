"""Reducer-free selection compiled as occurrence demand — one parse, no re-parse."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial
from pathlib import Path
from typing import NamedTuple

from lexic.compile import (
    KEEP,
    CompiledGrammar,
    Keep,
    MapShape,
    compile_ast,
    compile_text,
)
from lexic.compile.foldkit import ALT_BODY, model_fold, seq
from lexic.compile.pipeline.binding import compute_binding
from lexic.compile.pipeline.passes import retargeter, skip_rules
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrItem,
    IrLiteral,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
    IrSpan,
    refs_in_order,
)
from lexic.model import GrammarModel
from lexic.parsing import FieldFold, ModelBody, ModelFold, parse_model
from lexic.parsing.earley.kernel.forest.forest import ParseTree

type RawSpec = Mapping[str, "Keep | RawSpec"]
"""The caller's nested keep declaration over RAW key spellings."""

SELECTED, POISON = "--sel", "--poi"
"""Arm-rule name suffixes the deterministic route preference reads."""

TOY_GRAMMAR = r"""
start ::= ws sect ws
sect ::= "(" ws entries ws ")"
entries ::= entry e-more*
e-more ::= ws "," ws entry
entry ::= key ws "=" ws val
key ::= [a-z0-9]+
val ::= num | sect
num ::= [0-9]+
ws ::= [ \t\n]*
# @non-semantic ws
"""
"""The self-contained ``(k=v, ...)`` witness — no reducer exists for it."""

TOY_DOC = "(a=1, b=(c=22, d=(e=3)), f=4)"

BULK_ENTRIES = 1_000
"""Entries in the demand-locality witness document."""


class SpecRow(NamedTuple):
    """One validated selection row — a kept leaf or a nested level."""

    key: str
    keep: bool
    nested: tuple[SpecRow, ...]


class KeptHit(NamedTuple):
    """A kept value built DURING the one parse, with its certified span."""

    key: str
    value: GrammarModel
    value_at: IrSpan


class ExtentHit(NamedTuple):
    """A kept extent — the certified span alone, no value materialized."""

    key: str
    value_at: IrSpan


class NestedHit(NamedTuple):
    """A selected nested mapping — its level folded in place."""

    key: str
    level: "Level"


class PoisonHit(NamedTuple):
    """A selected-nested key whose value is not a mapping — a deferred verdict."""

    key: str


class KeyOnly(NamedTuple):
    """An unselected entry at a selected level — key text only, for duplicates."""

    key: str


type Hit = KeptHit | ExtentHit | NestedHit | PoisonHit | KeyOnly

type Folded = Hit | Level | IrSelf | tuple[Folded, ...] | list[Folded]


class Level(NamedTuple):
    """One selected mapping level's hits, in document order."""

    hits: tuple[Hit, ...]


class Shape(NamedTuple):
    """The grammar-derived map declaration and its item indices."""

    section: str
    entry: str
    key_item: int
    value_item: int
    value_rule: str


class Build(NamedTuple):
    """Shared state of one demand-grammar construction."""

    grammar: IrAst
    shape: Shape
    reaching: frozenset[str]
    extents_only: bool
    rules: list[IrRule]
    bodies: dict[str, ModelBody]
    counters: dict[str, int]


class BoundSelection(NamedTuple):
    """One morphism bound to one compiled grammar — a single demand grammar."""

    grammar: IrAst
    fold: ModelFold[Level]
    rows: tuple[SpecRow, ...]
    counters: dict[str, int]


def _declare_rows(spec: RawSpec) -> tuple[SpecRow, ...]:
    """Validate one declaration level into ordered immutable rows."""
    if not spec:
        raise UnsupportedConstructError(
            "demand selection: an empty selection declares no demand"
        )
    rows: list[SpecRow] = []
    for key, want in spec.items():
        if isinstance(want, Keep):
            rows.append(SpecRow(key, True, ()))
        elif isinstance(want, Mapping):
            rows.append(SpecRow(key, False, _declare_rows(want)))
        else:
            raise UnsupportedConstructError(
                f"demand selection: spec value at {key!r} must be KEEP or a mapping"
            )
    return tuple(rows)


def _reaching(grammar: IrAst, entry: str) -> frozenset[str]:
    """The rules from which ``entry`` is reachable — ``entry`` included."""
    referrers: dict[str, set[str]] = {}
    for rule in grammar.rules:
        refs: list[str] = []
        refs_in_order(rule.body, refs)
        for target in refs:
            referrers.setdefault(target, set()).add(str(rule.name))
    out = {entry}
    queue = [entry]
    while queue:
        for source in referrers.get(queue.pop(), ()):
            if source not in out:
                out.add(source)
                queue.append(source)
    return frozenset(out)


def _shape_of(compiled: CompiledGrammar, entry: str) -> Shape:
    """Resolve the map shape and its entry-arm item indices from binding data."""
    declared = MapShape.for_entry(compiled, entry)
    grammar = compiled.codegen_grammar
    bound = {b.rule_name: b for b in compute_binding(grammar)}[entry]
    arm = next(r.body for r in grammar.rules if str(r.name) == entry)[0]
    key_item = bound.fields[declared.key_field].item
    value_item = bound.fields[declared.value_field].item
    return Shape(
        declared.section,
        entry,
        key_item,
        value_item,
        str(arm[value_item].atom),
    )


def _count(counters: dict[str, int], name: str) -> None:
    """One construction event."""
    counters[name] = counters.get(name, 0) + 1


def _kept_hit(
    key: str, counters: dict[str, int], value: GrammarModel, value_at: IrSpan
) -> KeptHit:
    """The kept arm's ctor — the model was built by the same parse."""
    _count(counters, "kept")
    return KeptHit(key, value, value_at)


def _extent_hit(key: str, counters: dict[str, int], value_at: IrSpan) -> ExtentHit:
    """The extent arm's ctor — span only."""
    _count(counters, "extent")
    return ExtentHit(key, value_at)


def _nested_hit(key: str, counters: dict[str, int], level: Level) -> NestedHit:
    """The nested arm's ctor."""
    _count(counters, "nested")
    return NestedHit(key, level)


def _poison_hit(key: str, counters: dict[str, int]) -> PoisonHit:
    """The poison arm's ctor — shape mismatch retained as a value."""
    _count(counters, "poison")
    return PoisonHit(key)


def _key_only(counters: dict[str, int], key: str) -> KeyOnly:
    """The fallback arm's ctor — key text, demanded by duplicate refusal."""
    _count(counters, "fallback")
    return KeyOnly(key)


def _flatten(out: list[Hit], value: Folded) -> None:
    """Collect hits from one folded field, looking through collections."""
    if isinstance(value, (KeptHit, ExtentHit, NestedHit, PoisonHit, KeyOnly)):
        out.append(value)
        return
    if isinstance(value, Level):
        out.extend(value.hits)
        return
    if isinstance(value, (list, tuple)):
        for element in value:
            _flatten(out, element)


def _gather(**fields: Folded) -> tuple[Hit, ...]:
    """An intermediate context clone's ctor — hits in document order."""
    out: list[Hit] = []
    for value in fields.values():
        _flatten(out, value)
    return tuple(out)


def _level(**fields: Folded) -> Level:
    """The section clone's ctor — one selected level's hits."""
    return Level(_gather(**fields))


def _entry_items(
    build: Build, raw_key: str, value_atom: IrRuleRef | None
) -> tuple[IrItem, ...]:
    """One dispatch arm's items: literal key, chosen value child, ``-sk`` rest."""
    shape = build.shape
    skip = retargeter({str(r.name): str(r.name) + "-sk" for r in build.grammar.rules})
    arm = next(r.body for r in build.grammar.rules if str(r.name) == shape.entry)[0]
    items: list[IrItem] = []
    for index, item in enumerate(arm):
        if index == shape.key_item:
            items.append(IrItem(IrLiteral(raw_key)))
        elif index == shape.value_item and value_atom is not None:
            items.append(IrItem(value_atom))
        else:
            items.append(skip.apply(item))
    return tuple(items)


def _arm_rule(
    build: Build, name: str, items: tuple[IrItem, ...], body: ModelBody
) -> IrRuleRef:
    """Register one dispatch arm rule and its fold body."""
    build.rules.append(IrRule(name, IrAlternation(IrSequence(*items))))
    build.bodies[name] = body
    return IrRuleRef(name)


def _leaf_arm(build: Build, context: int, index: int, raw_key: str) -> IrRuleRef:
    """A kept leaf: the value builds through the ORIGINAL rules — or, in the
    extents-only variant, stays recognition-only and yields its span alone."""
    shape = build.shape
    name = f"{shape.entry}--c{context}--a{index}{SELECTED}"
    if build.extents_only:
        items = _entry_items(build, raw_key, IrRuleRef(shape.value_rule + "-sk"))
        fields = (FieldFold(shape.value_item, "span", "value_at", 1),)
        ctor = partial(_extent_hit, raw_key, build.counters)
    else:
        items = _entry_items(build, raw_key, IrRuleRef(shape.value_rule))
        fields = (
            FieldFold(shape.value_item, "model", "value", 1),
            FieldFold(shape.value_item, "span", "value_at", 1),
        )
        ctor = partial(_kept_hit, raw_key, build.counters)
    body = seq(ctor, len(items), fields)
    return _arm_rule(build, name, items, body)


def _nested_arm(
    build: Build, context: int, index: int, raw_key: str, child: int
) -> tuple[IrRuleRef, IrRuleRef]:
    """A selected nested key: the specialized section child, plus its poison
    twin consuming a non-mapping value through recognition-only recovery."""
    shape = build.shape
    name = f"{shape.entry}--c{context}--a{index}{SELECTED}"
    items = _entry_items(build, raw_key, IrRuleRef(f"{shape.section}--c{child}"))
    body = seq(
        partial(_nested_hit, raw_key, build.counters),
        len(items),
        (FieldFold(shape.value_item, "model", "level", 1),),
    )
    poison_name = f"{shape.entry}--c{context}--a{index}{POISON}"
    poison_items = _entry_items(build, raw_key, IrRuleRef(shape.value_rule + "-sk"))
    poison_body = seq(
        partial(_poison_hit, raw_key, build.counters), len(poison_items), ()
    )
    return (
        _arm_rule(build, name, items, body),
        _arm_rule(build, poison_name, poison_items, poison_body),
    )


def _fallback_arm(build: Build, context: int) -> IrRuleRef:
    """The unselected-entry arm — key text only, everything else ``-sk``."""
    shape = build.shape
    name = f"{shape.entry}--c{context}--fal"
    items = _entry_items(build, "", None)
    items = (
        items[: shape.key_item]
        + (IrItem(IrRuleRef(str(shape.entry) + "-key-sk")),)
        + items[shape.key_item + 1 :]
    )
    body = seq(
        partial(_key_only, build.counters),
        len(items),
        (FieldFold(shape.key_item, "text", "key", 1),),
    )
    return _arm_rule(build, name, items, body)


def _context_clones(build: Build, context: int, rows: tuple[SpecRow, ...]) -> int:
    """Clone the section-to-entry rules for one spec level; return next id."""
    shape = build.shape
    arms: list[IrRuleRef] = []
    next_context = context + 1
    for index, row in enumerate(rows):
        if row.keep:
            arms.append(_leaf_arm(build, context, index, row.key))
            continue
        child = next_context
        next_context = _context_clones(build, child, row.nested)
        selected, poison = _nested_arm(build, context, index, row.key, child)
        arms.extend((selected, poison))
    arms.append(_fallback_arm(build, context))
    entry_name = f"{shape.entry}--c{context}"
    build.rules.append(
        IrRule(entry_name, IrAlternation(*(IrSequence(a) for a in arms)))
    )
    build.bodies[entry_name] = ALT_BODY
    _reaching_clones(build, context)
    return next_context


def _reaching_clones(build: Build, context: int) -> None:
    """Context clones for every rule between the section and the entry."""
    shape = build.shape
    names = {
        name: f"{name}--c{context}" for name in build.reaching if name != shape.entry
    }
    names[shape.entry] = f"{shape.entry}--c{context}"
    retag_reaching = retargeter(names)
    skip = retargeter(
        {
            str(r.name): str(r.name) + "-sk"
            for r in build.grammar.rules
            if str(r.name) not in build.reaching
        }
    )
    binding = {b.rule_name: b for b in compute_binding(build.grammar)}
    for name in sorted(build.reaching - {shape.entry}):
        rule = next(r for r in build.grammar.rules if str(r.name) == name)
        body = retag_reaching.apply(skip.apply(rule.body))
        build.rules.append(IrRule(names[name], body, rule.semantic))
        build.bodies[names[name]] = _collector_body(build, binding, name)


def _collector_body(build: Build, binding: dict, name: str) -> ModelBody:
    """The fold body funneling one context clone's hits upward."""
    bound = binding[name]
    if bound.kind == "alternation":
        return ALT_BODY
    arm = next(r.body for r in build.grammar.rules if str(r.name) == name)[0]
    fields = tuple(
        FieldFold(bind.item, bind.mode, field, int(arm[bind.item].quantifier.lo))
        for field, bind in bound.fields.items()
        if isinstance(arm[bind.item].atom, IrRuleRef)
        and str(arm[bind.item].atom) in build.reaching
    )
    ctor = _level if name == build.shape.section else _gather
    return seq(ctor, len(arm), fields)


def _key_skip_rule(build: Build) -> None:
    """A dedicated ``-sk`` twin of the key rule for the fallback's text capture."""
    shape = build.shape
    arm = next(r.body for r in build.grammar.rules if str(r.name) == shape.entry)[0]
    key_atom = arm[shape.key_item].atom
    if not isinstance(key_atom, IrRuleRef):
        raise UnsupportedConstructError(
            "demand selection: the entry's key item must be a rule reference"
        )
    build.rules.append(
        IrRule(
            str(shape.entry) + "-key-sk",
            IrAlternation(IrSequence(IrItem(IrRuleRef(str(key_atom) + "-sk")))),
        )
    )


def bind_selection(
    compiled: CompiledGrammar,
    entry: str,
    spec: RawSpec,
    extents_only: bool = False,
) -> BoundSelection:
    """Compile the selection's demand into ONE contextual clone grammar.

    Binding consumes the compiled grammar and its binding view only — no
    ``Reducer``, no ``SemanticSignature``. The rule-keyed fold becomes
    occurrence-keyed through cloning: undemanded subtrees are ``-sk``
    recognition-only twins with no fold body, demanded values are the
    original model-building rules, and selected keys are literal-routed
    dispatch arms.
    """
    rows = _declare_rows(spec)
    grammar = compiled.codegen_grammar
    if any("--" in str(r.name) for r in grammar.rules):
        raise UnsupportedConstructError(
            "demand selection: clone-suffix collision with a grammar rule"
        )
    shape = _shape_of(compiled, entry)
    counters: dict[str, int] = {}
    build = Build(
        grammar,
        shape,
        _reaching(grammar, entry),
        extents_only,
        list(grammar.rules) + list(skip_rules(grammar)),
        {},
        counters,
    )
    _key_skip_rule(build)
    _context_clones(build, 0, rows)
    start = next(
        name
        for name in (f"{str(grammar.start)}--c0", f"{shape.section}--c0")
        if any(str(r.name) == name for r in build.rules)
    )
    merged = {
        str(ref): body for ref, body in compiled.fold.bodies.items() if not extents_only
    }
    merged.update(build.bodies)
    return BoundSelection(
        IrAst(IrSeq(*build.rules), start),
        model_fold(merged),
        rows,
        counters,
    )


def _score(tree: ParseTree) -> int:
    """The deterministic route preference: specialized > poison > fallback."""
    total = 0
    stack: list[ParseTree] = [tree]
    while stack:
        node = stack.pop()
        name = str(node.symbol)
        if name.endswith(SELECTED):
            total += 2
        elif name.endswith(POISON):
            total += 1
        stack.extend(kid for kid in node.kids if isinstance(kid, ParseTree))
    return total


def _prefer(first: ParseTree, other: ParseTree) -> ParseTree:
    """The RouteOp stand-in: settle key-dispatch overlap deterministically.

    Production compiles this decision into the recognition-time route
    continuation (`proto/route_continuation.py`); here the public ambiguity
    resolver carries the identical policy, so no grammar-level negation is
    needed and both engines answer alike.
    """
    return other if _score(other) > _score(first) else first


def run_selection(bound: BoundSelection, text: str) -> Level:
    """THE one engine parse — kept models/extents are built during it."""
    product = parse_model(bound.grammar, text, bound.fold, _prefer)
    out: list[Hit] = []
    _flatten(out, product)
    for hit in out:
        if isinstance(hit, Level):
            raise AssertionError("demand selection nested a loose level")
    if not out and not isinstance(product, Level):
        raise UnsupportedConstructError(
            "demand selection: the document root is not a mapping"
        )
    if isinstance(product, Level):
        return product
    return Level(tuple(out))


class KeptRow(NamedTuple):
    """One result row — path plus its model or certified extent."""

    path: tuple[str, ...]
    value: GrammarModel | None
    start: int
    end: int


def _walk_level(
    rows: tuple[SpecRow, ...],
    level: Level,
    prefix: tuple[str, ...],
    out: list[KeptRow],
) -> None:
    """Duplicate refusal, declaration order, absence, and poison verdicts."""
    seen: dict[str, Hit] = {}
    for hit in level.hits:
        if hit.key in seen:
            where = ".".join(prefix) or "<root>"
            raise UnsupportedConstructError(
                f"demand selection: repeated raw key {hit.key!r} at {where}"
            )
        seen[hit.key] = hit
    for row in rows:
        hit = seen.get(row.key)
        path = prefix + (row.key,)
        if hit is None:
            continue
        if isinstance(hit, PoisonHit):
            raise UnsupportedConstructError(
                f"demand selection: value at {'.'.join(path)} is not a mapping"
            )
        if isinstance(hit, KeptHit):
            out.append(
                KeptRow(path, hit.value, int(hit.value_at.start), int(hit.value_at.end))
            )
        elif isinstance(hit, ExtentHit):
            out.append(
                KeptRow(path, None, int(hit.value_at.start), int(hit.value_at.end))
            )
        elif isinstance(hit, NestedHit):
            _walk_level(row.nested, hit.level, path, out)


def select_values(bound: BoundSelection, text: str) -> tuple[KeptRow, ...]:
    """One parse of ``text``; kept paths in declaration order."""
    out: list[KeptRow] = []
    _walk_level(bound.rows, run_selection(bound, text), (), out)
    return tuple(out)


def _model_free(bound: BoundSelection) -> bool:
    """Static proof: no model-building rule is reachable from the start."""
    edges: dict[str, list[str]] = {}
    for rule in bound.grammar.rules:
        refs: list[str] = []
        refs_in_order(rule.body, refs)
        edges[str(rule.name)] = refs
    seen: set[str] = set()
    stack = [str(bound.grammar.start)]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack.extend(edges.get(name, ()))
    clones = {name for name in seen if "--" in name or name.endswith("-sk")}
    return not seen - clones


def _texts(rows: tuple[KeptRow, ...]) -> dict[tuple[str, ...], str]:
    """Path → round-tripped model text."""
    out: dict[tuple[str, ...], str] = {}
    for row in rows:
        if row.value is None:
            raise AssertionError("a value selection returned no model")
        out[row.path] = row.value.to_text()
    return out


def _expect_refusal(label: str, bound: BoundSelection | None, text: str) -> None:
    """Require one declared refusal edge."""
    try:
        if bound is None:
            _declare_rows({} if label == "empty" else {"a": {}})
        else:
            select_values(bound, text)
    except UnsupportedConstructError:
        return
    raise AssertionError(f"demand selection accepted the {label} case")


def _toy_witness() -> None:
    """Values, extents, order, absence, verdicts, and refusals — one parse each."""
    compiled = compile_text(TOY_GRAMMAR)
    spec: RawSpec = {"f": KEEP, "b": {"c": KEEP}, "zz": KEEP}
    bound = bind_selection(compiled, "entry", spec)
    rows = select_values(bound, TOY_DOC)
    if _texts(rows) != {("f",): "4", ("b", "c"): "22"}:
        raise AssertionError("toy selection changed its kept values")
    if [row.path for row in rows] != [("f",), ("b", "c")]:
        raise AssertionError("toy selection lost declaration order")
    for row in rows:
        if TOY_DOC[row.start : row.end] != _texts(rows)[row.path]:
            raise AssertionError(f"span at {row.path} is not certified")
    extent_bound = bind_selection(compiled, "entry", spec, extents_only=True)
    if not _model_free(extent_bound):
        raise AssertionError("the extent grammar can still reach a model rule")
    extents = select_values(extent_bound, TOY_DOC)
    for row in extents:
        if row.value is not None:
            raise AssertionError("the extent variant materialized a value")
    if {r.path: TOY_DOC[r.start : r.end] for r in extents} != {
        ("f",): "4",
        ("b", "c"): "22",
    }:
        raise AssertionError("extent selection changed its certified slices")
    print("toy", f"kept={len(rows)}", "extents=model-free", sep="\t")
    _expect_refusal("empty", None, "")
    _expect_refusal("nested-empty", None, "")
    _expect_refusal(
        "duplicate", bind_selection(compiled, "entry", {"a": KEEP}), "(a=1, a=2)"
    )
    _expect_refusal(
        "poison", bind_selection(compiled, "entry", {"a": {"x": KEEP}}), "(a=1)"
    )
    unchecked = bind_selection(compiled, "entry", {"a": KEEP})
    if _texts(select_values(unchecked, "(x=(d=1, d=2), a=7)")) != {("a",): "7"}:
        raise AssertionError("an unselected level's duplicates leaked a refusal")


def _retained(level: Level) -> dict[str, int]:
    """Retained hit counts by kind, across nested selected levels."""
    counts: dict[str, int] = {}
    stack: list[Level] = [level]
    while stack:
        for hit in stack.pop().hits:
            _count(counts, type(hit).__name__)
            if isinstance(hit, NestedHit):
                stack.append(hit.level)
    return counts


def _bulk_witness() -> None:
    """Demand locality: RETAINED construction is spec-sized, never
    document-sized. Fold-body EXECUTIONS run higher because today's
    ambiguity/attempt machinery re-folds candidate derivations — the
    root-refold cost REVIEW_7 finding 8 prices and the §8 local-meaning
    mechanism removes; the counters report both."""
    compiled = compile_text(TOY_GRAMMAR)
    doc = "(" + ", ".join(f"k{i}={i}" for i in range(BULK_ENTRIES)) + ")"
    bound = bind_selection(compiled, "entry", {"k3": KEEP, "k997": KEEP})
    level = run_selection(bound, doc)
    retained = _retained(level)
    rows: list[KeptRow] = []
    _walk_level(bound.rows, level, (), rows)
    if _texts(tuple(rows)) != {("k3",): "3", ("k997",): "997"}:
        raise AssertionError("bulk selection changed its kept values")
    if retained.get("KeptHit", 0) != 2:
        raise AssertionError(f"bulk retained {retained} kept models, not 2")
    if retained.get("KeyOnly", 0) != BULK_ENTRIES - 2:
        raise AssertionError(f"bulk retained {retained} key records")
    print(
        "bulk",
        f"entries={BULK_ENTRIES}",
        f"retained_models={retained.get('KeptHit', 0)}",
        f"retained_keys={retained.get('KeyOnly', 0)}",
        f"fold_executions_kept={bound.counters.get('kept', 0)}",
        f"fold_executions_fallback={bound.counters.get('fallback', 0)}",
        sep="\t",
    )


def _json_witnesses() -> None:
    """The same mechanism over both JSON formulations — no reducer anywhere."""
    source = (
        Path(__file__).resolve().parents[3] / "resources" / "ground_truth" / "json.gbnf"
    )
    gbnf = compile_text(source.read_text(encoding="utf-8"))
    native = compile_ast(JSON_GRAMMAR)
    doc = '{"a": 1, "b": {"c": 22}, "s": "x"}'
    spec: RawSpec = {'"s"': KEEP, '"b"': {'"c"': KEEP}}
    results: list[dict[tuple[str, ...], str]] = []
    for compiled in (gbnf, native):
        bound = bind_selection(compiled, "member", spec)
        results.append(_texts(select_values(bound, doc)))
    if results[0] != results[1]:
        raise AssertionError("formulations disagreed on kept values")
    if results[0] != {('"s"',): '"x"', ('"b"', '"c"'): "22"}:
        raise AssertionError("json selection changed its kept values")
    twins = '{"a": 1, "\\u0061": 2}'
    bound = bind_selection(gbnf, "member", {'"a"': KEEP})
    if _texts(select_values(bound, twins)) != {('"a"',): "1"}:
        raise AssertionError("raw keys stopped being raw")
    print("json", "gbnf == native", "escape-twins distinct", sep="\t")


def main() -> None:
    """Run every witness for the demand-compiled reducer-free selection."""
    _toy_witness()
    _bulk_witness()
    _json_witnesses()
    print(
        "conclusion",
        "selection demand compiles into contextual clones over any compiled"
        " grammar: one engine parse per document, kept models/extents built"
        " during it, undemanded subtrees recognition-only, key routing"
        " deterministic, shape verdicts syntax-first — no reducer, no"
        " signature, no re-parse",
        sep="\t",
    )


if __name__ == "__main__":
    main()
