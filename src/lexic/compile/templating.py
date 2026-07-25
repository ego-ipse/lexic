"""Generic templating — extract selected paths of any COMPILED grammar via spans.

Templating consumes a :class:`~lexic.compile.artifact.CompiledGrammar` — the
standard pipeline artifact — guided by a per-grammar :class:`MapShape`
declaration, so it applies identically to every formulation of a language
(``json.gbnf``, ``json.abnf``, a pure-IR grammar): no privileged formulation,
no hand-authored fold convention anywhere.

:func:`spanify` builds the span pair once over the codegen grammar: every rule
that can reach ``shape.entry`` is cloned under ``-tm`` names; the entry clone
captures its key/value items as raw spans over the ``-sk`` skip twins
(:func:`skip_rules` — matched structure, nothing built). The span fold is
DERIVED from the compiled grammar's binding — an alternation-kind clone is the
shared pass-through, a sequence-kind clone flatten-collects its entry-reaching
fields, the entry clone builds a :class:`SpanEntry` — so a section level
parses to a flat :class:`SpanLevel`, the driver's own co-designed product.

:class:`Template` is the retained compile product. :meth:`Template.run` parses
the document once, then drives the spec as a post-pass: keys match as RAW
SPANS (the spec is written in the grammar's own surface syntax); a
:data:`KEEP` leaf re-parses its value span with the compiled pair re-rooted at
the derived value rule and yields a :class:`~lexic.model.GrammarModel`; a
nested spec re-parses with the section clone and recurses, so a run's product
is an ``IrMap`` whose values are models or nested levels — both ``IrSelf``,
so the level needs no union type. Every artifact is a
spine record; the re-rooted grammars are retained on the :class:`SpanPair` so
the engine's identity memoisation stays hot across runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Callable, ClassVar, Self, Sequence, cast

from lexic.compile.artifact import CompiledGrammar
from lexic.compile.foldkit import ALT_BODY, model_fold
from lexic.compile.pipeline.binding import RuleBinding, compute_binding
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.ir.action import IrAction
from lexic.ir.base import (
    IrLambda,
    IrNamedTuple,
    IrNode,
    IrNoneType,
    IrSelf,
    IrSeq,
    IrStr,
    IrTuple,
)
from lexic.ir.bind import IrBind
from lexic.ir.mapping import IrMap, IrTypeMap
from lexic.ir.meta import IrSingleton
from lexic.ir.nodes import (
    IrAlternation,
    IrAst,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.ir.order import refs_in_order
from lexic.ir.walk import IrBottomUp
from lexic.model import GrammarModel
from lexic.parsing import FieldFold, ModelBody, ModelFold, parse_model

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


class SpanEntry(IrNamedTuple[str, str]):
    """One extracted ``key → value`` pair, both as raw document spans."""

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    key: str
    value: str


class SpanLevel(IrSeq[SpanEntry]):
    """One parsed section level — the span fold's product, in document order."""


class SpanPair(
    IrNamedTuple[IrAst, IrAst, ModelFold[SpanLevel], IrAst, ModelFold[GrammarModel]]
):
    """The retained span-mode artifacts one :func:`spanify` call produces.

    :ivar spans: The span grammar, rooted at the start rule's ``-tm`` clone.
    :ivar sections: The same rules rooted at the section clone (recursion).
    :ivar span_fold: The binding-derived span fold (clones only).
    :ivar values: The codegen grammar re-rooted at the derived value rule.
    :ivar value_fold: The compiled grammar's own fold (rule-keyed, so
        re-rooting shares it).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    spans: IrAst
    sections: IrAst
    span_fold: ModelFold[SpanLevel]
    values: IrAst
    value_fold: ModelFold[GrammarModel]


class _Retarget(IrNode[IrSelf, IrSelf]):
    """Transformer body — retarget every ``IrRuleRef`` through a name mapping."""

    __slots__ = ("mapping",)
    _bound: ClassVar[type] = IrSelf
    mapping: Mapping[str, str]

    def __new__(cls, mapping: Mapping[str, str], /) -> Self:
        """Wrap the rename mapping as an immutable leaf."""
        obj = object.__new__(cls)
        object.__setattr__(obj, "mapping", mapping)
        return obj

    def __repr__(self) -> str:
        """Codegen repr over the mapping literal."""
        return f"_Retarget({dict(self.mapping)!r})"

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """The dispatched ref, renamed when the mapping covers it."""
        target = self.mapping.get(str(n))
        return n if target is None else IrRuleRef(target)


def _retargeter(mapping: Mapping[str, str]) -> IrBottomUp:
    """The ref-retarget transformer over ``mapping`` (the ``_RENAME`` idiom)."""
    return IrBottomUp(actions=IrTypeMap(IrAction(IrRuleRef, _Retarget(mapping))))


def skip_rules(
    grammar: IrAst, shared: frozenset[str] = frozenset()
) -> tuple[IrRule, ...]:
    """Twin every non-shared rule as ``<name>-sk`` with refs remapped.

    A skip twin has no fold body — a transparent frame: a skipped subtree
    matches the same structure and builds nothing.

    :param grammar: The base grammar.
    :param shared: Rule names left un-twinned (refs to them stay).
    :returns: The skip twins, in rule order.
    """
    twins = {r.name: r.name + _SKIP for r in grammar.rules if r.name not in shared}
    retag = _retargeter(twins)
    return tuple(
        IrRule(twins[r.name], retag.apply(r.body), r.semantic)
        for r in grammar.rules
        if r.name in twins
    )


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


def _span_entry(key: str = "", value: str = "") -> SpanEntry:
    """The entry clone's ctor — both captured raw spans as one record."""
    return SpanEntry(key, value)


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


def _entry_body(view: _ShapeView) -> ModelBody:
    """The entry clone's fold body: two raw-span fields + the pair ctor."""
    arm, shape = view.entry_arm(), view.shape
    fields = tuple(
        FieldFold(bind.item, "text", name, int(arm[bind.item].quantifier.lo))
        for name, bind in (
            ("key", view.entry_bind(shape.key_field)),
            ("value", view.entry_bind(shape.value_field)),
        )
    )
    return ModelBody("sequence", IrLambda(_span_entry), len(arm), fields)


def _clone_body(view: _ShapeView, name: str) -> ModelBody | None:
    """The binding-derived span-fold body for a reaching rule's ``-tm`` clone.

    :returns: The body, or ``None`` for a kind with nothing to build
        (``value_str`` cannot reach; a body-less clone stays transparent).
    """
    kind = view.binding[name].kind
    if kind == "alternation":
        return ALT_BODY
    if kind != "sequence":
        return None
    arm = next(r.body for r in view.grammar.rules if r.name == name)[0]
    fields = tuple(
        FieldFold(bind.item, bind.mode, field, int(arm[bind.item].quantifier.lo))
        for field, bind in view.reaching_fields(name).items()
    )
    return ModelBody("sequence", IrLambda(_collect), len(arm), fields)


def _span_fold(view: _ShapeView) -> ModelFold[SpanLevel]:
    """The derived span fold — bodies for the ``-tm`` clones only."""
    bodies: dict[str, ModelBody] = {view.shape.entry + _SPAN: _entry_body(view)}
    for name in view.reaching - {view.shape.entry}:
        body = _clone_body(view, name)
        if body is not None:
            bodies[name + _SPAN] = body
    return model_fold(bodies)


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
    tm = _retargeter({name: name + _SPAN for name in view.reaching})
    sk = _retargeter({r.name: r.name + _SKIP for r in grammar.rules})
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
    return SpanPair(spans, sections, _span_fold(view), values, compiled.fold)


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
        """Extract the spec'd paths of ``text`` — one parse, then the post-pass.

        The result is FLAT and keyed by PATH: a nested spec does not produce
        nested maps, because that would make a value ``GrammarModel | IrMap``
        and force every read to narrow. Every value here is a kept model, so a
        read is typed with nothing to unwrap. Paths key natively —
        ``out["a", "b"]`` is ``out[("a", "b")]``, and ``IrTuple``/``IrStr``
        hash-match plain tuples and strings.

        :param text: The document to extract from.
        :returns: Spec path → the kept :class:`~lexic.model.GrammarModel`.
            Paths absent from the document are absent from the result.
        :raises UnsupportedConstructError: On a parse failure (wrapped with the
            document path) or a shape/spec level mismatch.
        """
        entries = _parse_step(self.span.spans, self.span.span_fold, text, "<document>")
        kept: list[IrTuple] = []
        _collect_kept(self.span, self.spec, entries, (), kept)
        return IrMap(*kept)


def _parse_step[M](grammar: IrAst, fold: ModelFold[M], text: str, path: str) -> M:
    """One engine call, wrapped with the document path on failure."""
    try:
        return parse_model(grammar, text, fold)
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
            model = _parse_step(pair.values, pair.value_fold, span, where)
            out.append(IrTuple(IrTuple(*path), model))
            continue
        sub = _parse_step(pair.sections, pair.span_fold, span, where)
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
