"""Generic templating over raw spans of any compiled grammar.

``spanify`` derives re-rooted span/value products from normal binding data;
``Template`` retains them and drives a nested keep-spec. The mechanism is
grammar-formulation neutral and uses the standard model parse path throughout.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Callable, ClassVar, Self, cast

from lexic.compile.artifact import CompiledGrammar
from lexic.compile.foldkit import AuthoredRule, product_rules
from lexic.compile.pipeline.binding import RuleBinding, compute_binding
from lexic.compile.pipeline.passes import retargeter, skip_rules
from lexic.compile.product import rules_by_name
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrBind,
    IrBottomUp,
    IrMap,
    IrNamedTuple,
    IrNoneType,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
    IrSingleton,
    IrSpan,
    IrStr,
    IrTuple,
    refs_in_order,
)
from lexic.model import GrammarModel
from lexic.parsing import ModelBinding, parse_model
from lexic.parsing.product import CAPTURE_FOR_BIND, CaptureSpec, LoweringOwned

__all__ = [
    "KEEP",
    "Keep",
    "MapShape",
    "Spec",
    "SpanEntry",
    "SpanLevel",
    "SpanPair",
    "Template",
    "skip_rules",
    "spanify",
    "template",
]

_SKIP = "-sk"
_SPAN = "-tm"


class Keep(IrSelf, metaclass=IrSingleton):
    """The keep-this-path spec leaf — a singleton, interned like ``IrNone``."""

    def __repr__(self) -> str:
        """Codegen repr — the singleton's constructor."""
        return "Keep()"


KEEP = Keep()
"""The one :class:`Keep` instance — marks a spec path for extraction."""


class Spec(IrMap[IrStr, "Keep | Spec"]):
    """One lifted keep-spec level — raw-span key → :data:`KEEP` or a nested level.

    A named map rather than an alias: the self-reference makes it the IR type
    a keep-spec IS, so a level reads without narrowing and its repr is
    reconstructing codegen.
    """

    __slots__ = ()


class MapShape(IrNamedTuple[str, str, str, str]):
    """The per-grammar map declaration templating is guided by — pure names.

    :ivar section: The codegen rule producing one mapping level.
    :ivar entry: The codegen rule producing one key/value pair (sequence-kind,
        single arm).
    :ivar key_field: The entry binding's key field (captured as a raw span).
    :ivar value_field: The entry binding's value field (captured as a raw
        span; its bound ref is the rule kept spans re-parse under).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    section: str
    entry: str
    key_field: str
    value_field: str

    @classmethod
    def for_entry(cls, compiled: CompiledGrammar, entry: str) -> Self:
        """Derive the whole shape from the ENTRY rule alone.

        Three of the four names are a function of the grammar, so asking for
        them is asking the caller to restate what the grammar already says —
        and a restatement can disagree.

        The **fields** are the entry's own binding: a key/value pair is a
        sequence with exactly two semantic fields, in document order. The
        **section** is the rule the value field reaches that in turn reaches the
        entry — the nesting cycle a mapping level closes, which is what makes it
        the level rather than merely a rule above it.

        :param compiled: The compiled grammar (any formulation of the language).
        :param entry: The rule producing one key/value pair.
        :returns: The resolved shape.
        :raises UnsupportedConstructError: When the entry is not a rule, does
            not bind exactly two semantic fields, or closes no nesting cycle.
        """
        grammar = compiled.codegen_grammar
        if entry not in {str(r.name) for r in grammar.rules}:
            raise UnsupportedConstructError(
                f"templating: entry {entry!r} is not a rule of the grammar"
            )
        bound = {b.rule_name: b for b in compute_binding(grammar)}[entry]
        fields = [name for name, b in bound.fields.items() if b.semantic]
        if len(fields) < 2:
            raise UnsupportedConstructError(
                f"templating: entry {entry!r} binds {fields!r}, and a key/value "
                "pair binds at least a key and a value"
            )
        # First and last, not "the only two": a separator between them is a
        # bound field of its own wherever the grammar names it — json's
        # `member ::= string name-separator value` binds all three.
        key_field, value_field = fields[0], fields[-1]
        return cls(
            _section_for(grammar, entry, bound, value_field),
            entry,
            key_field,
            value_field,
        )


class SpanEntry(IrNamedTuple[str, str, IrSpan, IrSpan]):
    """One extracted ``key → value`` pair — the raw text, and where it was.

    The offsets are the parse's own: the PDA route reads them off the
    kernel's frame, and the tree route accumulates them over the leaves
    `_subtree_text` already walks. Neither re-finds a span by searching the
    document for its text, which is ambiguous the moment a document repeats
    itself — the first ``"name"`` and the fifth are the same string.

    :ivar key: The key's raw span text.
    :ivar value: The value's raw span text.
    :ivar key_at: Where ``key`` sits in the document, in code units.
    :ivar value_at: Where ``value`` sits in the document, in code units.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("key_at", "value_at")
    key: str
    value: str
    key_at: IrSpan = IrSpan(0, 0)
    value_at: IrSpan = IrSpan(0, 0)


class SpanLevel(IrSeq[SpanEntry]):
    """One parsed section level — the span fold's product, in document order."""


class SpanPair(
    IrNamedTuple[
        IrAst, IrAst, ModelBinding[SpanLevel], IrAst, ModelBinding[GrammarModel]
    ]
):
    """The retained span-mode artifacts one :func:`spanify` call produces.

    :ivar spans: The span grammar, rooted at the start rule's ``-tm`` clone.
    :ivar sections: The same rules rooted at the section clone (recursion).
    :ivar span_binding: The derived span product (clones only).
    :ivar values: The codegen grammar re-rooted at the derived value rule.
    :ivar value_binding: The compiled grammar's own product (rule-keyed, so
        re-rooting shares it).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    spans: IrAst
    sections: IrAst
    span_binding: ModelBinding[SpanLevel]
    values: IrAst
    value_binding: ModelBinding[GrammarModel]


def _reaching(grammar: IrAst, entry: str) -> frozenset[str]:
    """The rules from which ``entry`` is reachable — ``entry`` included."""
    referrers: dict[str, set[str]] = {}
    for named in grammar.rules:
        refs: list[str] = []
        refs_in_order(named.body, refs)
        for target in refs:
            referrers.setdefault(target, set()).add(named.name)
    out = {entry}
    queue = [entry]
    while queue:
        for source in referrers.get(queue.pop(), ()):
            if source not in out:
                out.add(source)
                queue.append(source)
    return frozenset(out)


def _span_entry(
    key: str = "",
    value: str = "",
    key_at: IrSpan = IrSpan(0, 0),
    value_at: IrSpan = IrSpan(0, 0),
) -> SpanEntry:
    """The entry clone's ctor — both captured raw spans, and where they were."""
    return SpanEntry(key, value, key_at, value_at)


def _collect(**fields: object) -> SpanLevel:
    """A sequence clone's ctor — flatten the reaching fields' span entries.

    Takes ``**fields`` because that IS the fold's constructor protocol
    (``rule_fold.ctor(**kwargs)``); the product is on-spine so every
    downstream read is typed.
    """
    out: list[SpanEntry] = []
    for value in fields.values():
        _flatten_into(out, value)
    return SpanLevel(*out)


def _flatten_into(out: list[SpanEntry], value: object) -> None:
    """Append ``value``'s span entries to ``out`` (absence contributes none).

    :raises UnsupportedConstructError: On a value the span fold cannot have
        produced (a wiring defect, never data).
    """
    if isinstance(value, SpanEntry):
        out.append(value)
        return
    if isinstance(value, (list, tuple)):
        for element in value:
            _flatten_into(out, element)
        return
    if value is None or isinstance(value, IrNoneType):
        return
    raise UnsupportedConstructError(
        f"templating: span fold produced {type(value).__name__!r}"
    )


class _ShapeView(IrNamedTuple[IrAst, MapShape, "dict[str, RuleBinding]", frozenset]):
    """The resolved shape over one compiled grammar — validation's product.

    :ivar grammar: The codegen grammar.
    :ivar shape: The user's declaration.
    :ivar binding: Rule name → its :class:`RuleBinding`.
    :ivar reaching: The entry-reaching rule names (entry included).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    grammar: IrAst
    shape: MapShape
    binding: dict[str, RuleBinding]
    reaching: frozenset

    def entry_arm(self) -> IrSequence:
        """The entry rule's single sequence arm."""
        body = next(r.body for r in self.grammar.rules if r.name == self.shape.entry)
        return body[0]

    def entry_bind(self, field: str) -> IrBind:
        """The entry binding's ``IrBind`` for ``field``."""
        return self.binding[self.shape.entry].fields[field]

    def value_rule(self) -> str:
        """The rule kept value spans re-parse under — the value field's ref."""
        atom = self.entry_arm()[self.entry_bind(self.shape.value_field).item].atom
        return str(atom)

    def reaching_fields(self, name: str) -> dict[str, IrBind]:
        """``name``'s binding fields whose bound ref targets a reaching rule."""
        arm = next(r.body for r in self.grammar.rules if r.name == name)[0]
        out: dict[str, IrBind] = {}
        for field, bind in self.binding[name].fields.items():
            atom = arm[bind.item].atom
            if isinstance(atom, IrRuleRef) and str(atom) in self.reaching:
                out[field] = bind
        return out


def _section_for(
    grammar: IrAst, entry: str, bound: RuleBinding, value_field: str
) -> str:
    """The rule a mapping level is — derived, not declared.

    A level is the rule the VALUE can reach that reaches the entry back: that
    cycle is what makes nesting possible, and closing it is what distinguishes
    the level from every other rule sitting above the entry. The nearest such
    rule is taken, so an outer wrapper that merely contains a level is not
    mistaken for one.

    :param grammar: The codegen grammar.
    :param entry: The entry rule.
    :param bound: The entry's binding.
    :param value_field: The entry's value field.
    :returns: The section rule's name.
    :raises UnsupportedConstructError: When the value closes no cycle back to
        the entry — the grammar has no nesting level to template.
    """
    # What the VALUE OFFERS, not what sits nearest the entry. A level is one of
    # the things a value can BE — `val ::= num | sect`, `value ::= object | …` —
    # and asking the entry's neighbourhood instead finds the repetition helper
    # (`e-more`, `object-item`), which is a continuation, not a level.
    value_rule = _value_ref(grammar, entry, bound, value_field)
    offered: list[str] = []
    refs_in_order(
        next(r.body for r in grammar.rules if str(r.name) == value_rule), offered
    )
    reaches = _reaching(grammar, entry)
    cycle = {name for name in offered if name in reaches} - {entry}
    if not cycle:
        raise UnsupportedConstructError(
            f"templating: the value of entry {entry!r} offers no rule that "
            "reaches it back, so the grammar has no mapping level to template"
        )
    # Among what it offers, the NEAREST: json's `value` offers both `object` and
    # `array`, and an array reaches `member` too — through `value` and back into
    # an object. Only the hop count says which one IS the mapping level.
    hops = _hops_to(grammar, entry)
    return min(sorted(cycle), key=lambda name: (hops.get(name, len(hops)), name))


def _hops_to(grammar: IrAst, target: str) -> dict[str, int]:
    """Shortest reference distance from each rule to ``target``."""
    back: dict[str, list[str]] = {}
    for rule in grammar.rules:
        out: list[str] = []
        refs_in_order(rule.body, out)
        for ref in out:
            back.setdefault(ref, []).append(str(rule.name))
    seen = {target: 0}
    edge = [target]
    while edge:
        nxt: list[str] = []
        for name in edge:
            for prev in back.get(name, ()):
                if prev not in seen:
                    seen[prev] = seen[name] + 1
                    nxt.append(prev)
        edge = nxt
    return seen


def _value_ref(grammar: IrAst, entry: str, bound: RuleBinding, value_field: str) -> str:
    """The rule name the entry's value field is bound to."""
    body = next(r.body for r in grammar.rules if str(r.name) == entry)
    refs: list[str] = []
    refs_in_order(body, refs)
    del bound, value_field
    return refs[-1] if refs else entry


def _reaching_from(grammar: IrAst, start: str) -> set[str]:
    """Every rule reachable FROM ``start`` (the mirror of :func:`_reaching`)."""
    edges: dict[str, list[str]] = {}
    for rule in grammar.rules:
        out: list[str] = []
        refs_in_order(rule.body, out)
        edges[str(rule.name)] = out
    seen: set[str] = set()
    stack = [start]
    while stack:
        name = stack.pop()
        if name in seen or name not in edges:
            continue
        seen.add(name)
        stack.extend(edges[name])
    return seen


def _resolve_shape(compiled: CompiledGrammar, shape: MapShape) -> _ShapeView:
    """Validate ``shape`` against ``compiled`` and resolve the working view.

    :raises UnsupportedConstructError: On an unknown rule, a non-sequence or
        multi-arm entry, an unknown/`models`-mode key or value field, a value
        field not bound to a rule ref, a clone-suffix collision, or a start /
        section that cannot reach the entry.
    """
    grammar = compiled.codegen_grammar
    names = {str(r.name) for r in grammar.rules}
    for role, name in (("section", shape.section), ("entry", shape.entry)):
        if name not in names:
            raise UnsupportedConstructError(
                f"templating: shape.{role} {name!r} is not a rule of the grammar"
            )
    collisions = sorted(n for n in names if n + _SPAN in names or n + _SKIP in names)
    if collisions:
        raise UnsupportedConstructError(
            f"templating: clone-suffix collision on rules {collisions!r}"
        )
    binding = {b.rule_name: b for b in compute_binding(grammar)}
    view = _ShapeView(grammar, shape, binding, _reaching(grammar, shape.entry))
    _check_entry(view)
    for role, name in (("start", grammar.start), ("section", shape.section)):
        if name not in view.reaching:
            raise UnsupportedConstructError(
                f"templating: {role} {name!r} cannot reach shape.entry {shape.entry!r}"
            )
    return view


def _check_entry(view: _ShapeView) -> None:
    """Refuse an entry rule / key/value fields the span clone cannot serve."""
    shape = view.shape
    bound = view.binding[shape.entry]
    if bound.kind != "sequence":
        raise UnsupportedConstructError(
            f"templating: shape.entry {shape.entry!r} must be sequence-kind, "
            f"is {bound.kind!r}"
        )
    body = next(r.body for r in view.grammar.rules if r.name == shape.entry)
    if len(body) != 1:
        raise UnsupportedConstructError(
            f"templating: shape.entry {shape.entry!r} must have one sequence arm"
        )
    for role, field in (("key", shape.key_field), ("value", shape.value_field)):
        bind = bound.fields.get(field)
        if bind is None:
            raise UnsupportedConstructError(
                f"templating: {role} field {field!r} is not a binding field of "
                f"{shape.entry!r} (has {sorted(bound.fields)!r})"
            )
        if bind.mode == "models":
            raise UnsupportedConstructError(
                f"templating: {role} field {field!r} is a list field — a span "
                "captures one item"
            )
    value_atom = view.entry_arm()[bound.fields[shape.value_field].item].atom
    if not isinstance(value_atom, IrRuleRef):
        raise UnsupportedConstructError(
            f"templating: value field {shape.value_field!r} must be bound to a "
            "rule ref (kept spans re-parse under it)"
        )


def _entry_clone(view: _ShapeView, tm: IrBottomUp, sk: IrBottomUp) -> IrRule:
    """The entry ``-tm`` clone: span items over ``-sk``, the rest over ``-tm``."""
    shape = view.shape
    span_slots = (
        view.entry_bind(shape.key_field).item,
        view.entry_bind(shape.value_field).item,
    )
    items = [
        (sk if i in span_slots else tm).apply(item)
        for i, item in enumerate(view.entry_arm())
    ]
    entry = next(r for r in view.grammar.rules if r.name == shape.entry)
    return IrRule(
        shape.entry + _SPAN, IrAlternation(IrSequence(*items)), entry.semantic
    )


def _entry_rule(view: _ShapeView) -> AuthoredRule:
    """The entry clone — the two raw spans, text AND position.

    Four fields over TWO slots: what the entry says and where it said it, from
    one occurrence. A capture is a (mode, slot) pair and nothing makes a slot
    exclusive. None is absence-bearing — a text capture that matched nothing
    IS the empty string, and an extent always has one.
    """
    arm, shape = view.entry_arm(), view.shape
    bound = (
        ("key", view.entry_bind(shape.key_field)),
        ("value", view.entry_bind(shape.value_field)),
    )
    pairs = tuple(
        (name + suffix, mode, bind)
        for mode, suffix in (("text", ""), ("span", "_at"))
        for name, bind in bound
    )
    captures = tuple(
        CaptureSpec(int(CAPTURE_FOR_BIND[mode]), bind.item) for _n, mode, bind in pairs
    )
    names = tuple(name for name, _m, _b in pairs)
    return AuthoredRule("span_entry", captures, names, len(arm))


def _clone_rule(view: _ShapeView, name: str) -> AuthoredRule | None:
    """A reaching rule's ``-tm`` clone.

    :returns: The rule, or ``None`` for a kind with nothing to build
        (``value_str`` cannot reach; a body-less clone stays transparent).
    """
    kind = view.binding[name].kind
    if kind == "alternation":
        return AuthoredRule("")
    if kind != "sequence":
        return None
    arm = next(r.body for r in view.grammar.rules if r.name == name)[0]
    reaching = view.reaching_fields(name)
    los = {field: int(arm[bind.item].quantifier.lo) for field, bind in reaching.items()}
    captures = tuple(
        CaptureSpec(int(CAPTURE_FOR_BIND[bind.mode]), bind.item)
        for bind in reaching.values()
    )
    optional = tuple(
        at
        for at, (field, bind) in enumerate(reaching.items())
        if bind.mode == "gtext" and los[field] == 0
    )
    return AuthoredRule("collect", captures, tuple(reaching), len(arm), optional)


SPAN_SYMBOLS: dict[str, Callable[..., object]] = {
    "span_entry": _span_entry,
    "collect": _collect,
}


def _span_binding(view: _ShapeView) -> ModelBinding[SpanLevel]:
    """The span surface's product, from one walk over the reaching set."""
    entry = view.shape.entry + _SPAN
    rules: dict[str, AuthoredRule] = {entry: _entry_rule(view)}
    for name in view.reaching - {view.shape.entry}:
        rule = _clone_rule(view, name)
        if rule is None:  # a kind with nothing to build stays transparent
            continue
        rules[name + _SPAN] = rule
    product = product_rules(rules)
    return ModelBinding(
        rules_by_name(product.rules, product.codes),
        LoweringOwned(symbols=product.symbols, registry=SPAN_SYMBOLS),
    )


def spanify(compiled: CompiledGrammar, shape: MapShape) -> SpanPair:
    """Build the retained span pair for ``compiled`` under ``shape``.

    :param compiled: The compiled grammar (any formulation of the language).
    :param shape: The grammar's map declaration.
    :returns: The span pair every keep-spec over this grammar drives.
    :raises UnsupportedConstructError: On a shape/grammar mismatch (see
        :func:`_resolve_shape`).
    """
    view = _resolve_shape(compiled, shape)
    grammar = view.grammar
    tm = retargeter({name: name + _SPAN for name in view.reaching})
    sk = retargeter({r.name: r.name + _SKIP for r in grammar.rules})
    rules = list(grammar.rules)
    rules.extend(skip_rules(grammar))
    rules.extend(
        IrRule(r.name + _SPAN, tm.apply(r.body), r.semantic)
        for r in grammar.rules
        if r.name in view.reaching and r.name != shape.entry
    )
    rules.append(_entry_clone(view, tm, sk))
    spans = IrAst(IrSeq(*rules), grammar.start + _SPAN)
    sections = IrAst(IrSeq(*rules), shape.section + _SPAN)
    values = IrAst(grammar.rules, view.value_rule())
    return SpanPair(spans, sections, _span_binding(view), values, compiled.product)


def _lift_spec(spec: Mapping[str, object] | IrMap) -> Spec:
    """Lift a nested pythonic spec to ``IrMap[IrStr, Keep | Spec]``."""
    dyads = (
        IrTuple(IrStr(key), _lift_value(key, value)) for key, value in spec.items()
    )
    return Spec(*dyads)


def _lift_value(key: object, value: object) -> Keep | Spec:
    """One spec value: :data:`KEEP`, or a nested mapping lifted recursively."""
    if isinstance(value, Keep):
        return value
    if isinstance(value, (Mapping, IrMap)):
        return _lift_spec(value)
    raise UnsupportedConstructError(
        f"templating: spec value at {str(key)!r} must be KEEP or a nested mapping"
    )


class Template(IrNamedTuple[SpanPair, Spec], init=False):
    """The retained templating product — a span pair driving a keep-spec.

    :ivar span: The compiled span pair (:func:`spanify` output).
    :ivar spec: The keep-spec — a :data:`Spec` whose keys are RAW SPANS in
        the grammar's own surface syntax.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    span: SpanPair
    spec: Spec

    def __new__(cls, span: SpanPair, spec: Mapping[str, object] | IrMap) -> Self:
        """Construct the template, lifting + validating the spec at the seam.

        :param span: The span pair to drive.
        :param spec: The keep-spec — nested ``Mapping``s with :data:`KEEP`
            leaves (or an already-lifted ``IrMap``).
        :returns: The template.
        :raises UnsupportedConstructError: On a spec value that is neither
            :data:`KEEP` nor a mapping.
        """
        lifted = _lift_spec(spec)
        return cast(Callable[..., Self], super().__new__)(cls, span, lifted)

    def run(self, text: str) -> IrMap[IrTuple, GrammarModel]:
        """Extract kept paths as a flat path-to-model map."""
        entries = _parse_step(
            self.span.spans, self.span.span_binding, text, "<document>"
        )
        kept: list[IrTuple] = []
        _collect_kept(self.span, self.spec, entries, (), kept)
        return IrMap(*kept)


def _parse_step[M](grammar: IrAst, binding: ModelBinding[M], text: str, path: str) -> M:
    """One engine call, wrapped with the document path on failure."""
    try:
        return parse_model(grammar, text, binding)
    except LexicError as err:
        raise UnsupportedConstructError(f"template at {path}: {err}") from err


def _collect_kept(
    pair: SpanPair,
    spec: Spec,
    entries: SpanLevel,
    prefix: tuple[IrStr, ...],
    out: list[IrTuple],
) -> None:
    """Walk one spec level, appending ``(path, model)`` dyads for KEEP leaves.

    A nested spec recurses with the path prefix extended, so the product stays
    flat and single-typed however deep the spec goes.
    """
    spans: dict[str, str] = {}
    for each in entries:
        spans.setdefault(str(each.key), str(each.value))
    for key, want in spec.items():
        span = spans.get(str(key))
        if span is None:
            continue
        path = prefix + (IrStr(key),)
        where = ".".join(str(part) for part in path)
        if isinstance(want, Keep):
            model = _parse_step(pair.values, pair.value_binding, span, where)
            out.append(IrTuple(IrTuple(*path), model))
            continue
        sub = _parse_step(pair.sections, pair.span_binding, span, where)
        _collect_kept(pair, want, sub, path, out)


def template(
    compiled: CompiledGrammar, shape: MapShape, spec: Mapping[str, object] | IrMap
) -> Template:
    """Compile a retained :class:`Template` for ``compiled`` under ``shape``.

    :param compiled: The compiled grammar (any formulation of the language).
    :param shape: The grammar's map declaration.
    :param spec: The keep-spec (pure driver data, raw-span keys).
    :returns: The template — compile once, :meth:`Template.run` many.
    """
    return Template(spanify(compiled, shape), spec)
