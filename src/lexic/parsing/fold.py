"""ParseTree → object fold — the instance-parsing bridge.

The one authored instance-fold is :class:`ModelFold`: a per-rule IR body-table
(:attr:`ModelFold.bodies`, an :class:`~lexic.ir.action.mapping.IrMap` from each rule's
:class:`~lexic.ir.grammar.nodes.IrRuleRef` to its :class:`ModelBody`) — the same shape
the grammar-text :class:`~lexic.parsing.earley.reduce.Reducer` carries its
reductions in. A :class:`ModelBody` carries the model constructor as an
:class:`~lexic.ir.base.IrLambda` plus structural metadata (kind / n_items /
fields / fast); :meth:`ModelBody.bake` lowers it losslessly to a
:class:`RuleFold`, the flat-runtime record the predictive PDA's clone compiler
and this fold's own :meth:`~ModelFold.apply` consume unchanged.

Instance parsing runs over the *real* codegen grammar and field extraction is
positional. ``normalize()`` replaces items in place, so an original item is
always exactly one symbol slot in the normalized arm — for a rule's
:class:`ParseTree` node, ``kids[i] ↔ items[i]``. No ``--f<idx>`` wrapper rules,
no name protocol.

The baked config is plain data: per rule a :class:`RuleFold` — ``(kind, ctor,
n_items, fields)`` with each field a ``(item, mode, name, lo)``
:class:`FieldFold`. Constructors are opaque callables; modes are the
:data:`~lexic.ir.spine.bind.BIND_MODES` vocabulary. This module sees only IR and its
own baked config — no binding view, no model synthesis.

Fold behavior per kind:

- ``value_str`` → ``ctor(value=<subtree text>)``;
- ``alternation`` → pass-through to the single sub-model under the node
  (the matched arm's model identifies itself);
- ``sequence`` → per field, ``kids[item]``: ``text``/``gtext`` take the slot's
  consumed text, ``model``/``models`` collect folded sub-models through
  synthetic (normalize) layers; ``None`` values are omitted from kwargs.
  A zero-kid node when ``n_items > 0`` is the rule's empty alternate arm —
  ``ctor()`` with no kwargs (an all-nullable full arm would make the empty
  match ambiguous; :func:`~lexic.parsing.parse_first` resolves it to the
  first derivation, deterministically).

Instance parsing runs :func:`~lexic.parsing.parse_first` (deterministic first
derivation; e.g. json_ws's ``int`` is genuinely ambiguous).
"""

from __future__ import annotations

from typing import Callable, ClassVar, Mapping, NamedTuple, Sequence, cast

from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    BIND_MODES,
    IrAlternation,
    IrAst,
    IrItem,
    IrLambda,
    IrLiteral,
    IrMap,
    IrNamedTuple,
    IrNone,
    IrNoneType,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
    IrSpan,
    IrTuple,
)
from lexic.parsing.earley.kernel.forest.forest import ParseTree, PayloadLeaf
from lexic.parsing.earley.kernel.tables.records import (
    ORIGIN_BITS,
    RUN_STR,
    ParserTables,
)
from lexic.parsing.earley.lexruns import collapse_runs, unit_leaves
from lexic.parsing.pda.analysis.analysis import nullable_names

FOLD_KINDS: tuple[str, ...] = ("value_str", "sequence", "alternation")
"""The rule-kind vocabulary a :class:`RuleFold` may carry."""


class FieldFold(NamedTuple):
    """One bound field: which kid slot it reads and how it folds.

    :ivar item: Positional index into the rule's sequence arm (= kid slot).
    :ivar mode: One of :data:`~lexic.ir.spine.bind.BIND_MODES`.
    :ivar name: The constructor kwarg the folded value binds to.
    :ivar lo: The item's original quantifier ``lo`` — consumed only by
        ``gtext`` (empty text with ``lo == 0`` means absent, not ``""``).
    """

    item: int
    mode: str
    name: str
    lo: int


class FastCtor(NamedTuple):
    """A validation-skip construction licence — plain data, builder opaque.

    Granted per rule by the compile seam when the model class provably needs
    no per-field validation; the PDA runtime then builds instances through
    :attr:`make` instead of the validated constructor. The engine-side fold
    ignores it — the engine path stays the validated reference.

    :ivar make: ``(values) -> model`` — the class's positional constructor,
        taking one value per field in :attr:`fields` order.
    :ivar defaults: Field name → default for every optional field; the PDA
        bakes each into its per-clone build plan.
    :ivar fields: The class's field names, in construction order — what makes
        the plan positional without reaching into the class from the compiler.
    """

    make: Callable[[list[object]], object]
    defaults: Mapping[str, object]
    fields: tuple[str, ...] = ()


class RuleFold(NamedTuple):
    """One rule's fold config — plain data, constructor opaque.

    :ivar kind: One of :data:`FOLD_KINDS`.
    :ivar ctor: The rule's model constructor (unused for ``alternation``).
    :ivar n_items: Kid-slot count of the single non-empty sequence arm
        (``0`` for the other kinds; a zero-kid mismatch = empty-arm match).
    :ivar fields: The bound fields, in item order.
    :ivar fast: The rule's :class:`FastCtor` licence, or ``None`` (the
        validated constructor is used everywhere).
    """

    kind: str
    ctor: Callable[..., object]
    n_items: int
    fields: tuple[FieldFold, ...]
    fast: FastCtor | None = None


def _alt_ctor(*_args: object, **_kwargs: object) -> None:
    """Stand-in constructor for an ``alternation`` fold — never invoked.

    An alternation rule passes its matched arm's sub-model through
    (:meth:`ModelFold._first_model_under`, the PDA's ``BUILD_ALT``), so its
    baked :class:`RuleFold` never calls a constructor; this keeps the ``ctor``
    slot a plain callable while :class:`ModelBody` records the absence as
    :data:`~lexic.ir.base.IrNone`.
    """
    return None


class ModelBody(
    IrNamedTuple[str, "IrSelf", int, "tuple[FieldFold, ...]", "FastCtor | None"]
):
    """One rule's model-fold body — the IR-native authored form.

    The only IR-carried field is the model constructor, wrapped in
    :class:`~lexic.ir.base.IrLambda` (:data:`~lexic.ir.base.IrNone` for an
    ``alternation``, which has no constructor); ``kind`` / ``n_items`` /
    ``fields`` / ``fast`` are structural metadata mapping 1:1 onto the baked
    :class:`RuleFold`'s flat-clone build plan. :meth:`bake` lowers this
    losslessly to a :class:`RuleFold` — the flat clone and the engine fold are
    byte-for-byte unchanged. Scalar payload only, so ``_child_attrs`` is empty
    (the ``IrLambda`` is never walked as a grammar child).

    :ivar kind: One of :data:`FOLD_KINDS`.
    :ivar ctor: ``IrLambda(model_class)``, or :data:`~lexic.ir.base.IrNone` for
        an ``alternation``.
    :ivar n_items: Kid-slot count of the single non-empty sequence arm.
    :ivar fields: The bound fields, in item order.
    :ivar fast: The rule's :class:`FastCtor` licence, or ``None``.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    kind: str
    ctor: IrSelf
    n_items: int
    fields: tuple[FieldFold, ...]
    fast: FastCtor | None = None

    def bake(self) -> RuleFold:
        """Lower to the flat-runtime :class:`RuleFold`, adapting the ctor body.

        Three ctor shapes lower to the one ``ctor(**kwargs)`` the fold calls:

        - :data:`~lexic.ir.base.IrNone` (an ``alternation``) → :func:`_alt_ctor`,
          the never-called stand-in;
        - an :class:`~lexic.ir.base.IrLambda` → its wrapped callable (``.eval``
          IS the callable — identity), which takes the field-name kwargs itself;
        - any other IR body (a shared idiom in the ``foldkit`` vocabulary) →
          :meth:`_channel_ctor`, which maps the kwargs onto the body's positional
          argument channel.

        The structural metadata passes through untouched — it already IS the
        closed vocabulary the flatten pass int-codes.

        :returns: The runtime :class:`RuleFold`.
        """
        return RuleFold(
            self.kind, self._baked_ctor(), self.n_items, self.fields, self.fast
        )

    def _baked_ctor(self) -> Callable[..., object]:
        """Resolve the ctor body to the ``ctor(**kwargs)`` callable the fold calls."""
        if self.ctor is IrNone:
            return _alt_ctor
        if isinstance(self.ctor, IrLambda):
            return self.ctor.eval
        return self._channel_ctor()

    def _channel_ctor(self) -> Callable[..., object]:
        """Adapt a pure IR body to a kwargs-taking ctor over its argument channel.

        The fold calls a ctor with field-name kwargs; an IR body reads a
        positional argument channel (``IrArg(i)``). The closure bridges them: it
        lays the kwargs out in ``fields`` order, fills an omitted optional with
        :data:`~lexic.ir.base.IrNone` (a body branches on absence by
        ``IrNoneType`` type, never falsiness — ``IrNone`` is truthy), and
        evaluates the body with ``d = n = IrNone`` (the algebra subset never
        dereferences them). A ``value_str`` body reads the sole ``value`` kwarg;
        an empty arm (no ``fields``) evaluates over an empty channel.

        :returns: The ``ctor(**kwargs)`` callable.
        """
        body = self.ctor
        kind = self.kind
        names = tuple(field.name for field in self.fields)

        def ctor(**kwargs: object) -> object:
            if kind == "value_str":
                channel: tuple[object, ...] = (kwargs["value"],)
            else:
                channel = tuple(kwargs.get(name, IrNone) for name in names)
            return body.eval(IrNone, IrNone, cast(Sequence[IrSelf], channel))

        return ctor

    @classmethod
    def of(cls, rule_fold: RuleFold) -> "ModelBody":
        """Lift a baked :class:`RuleFold` back into the IR body form.

        The inverse of :meth:`bake`: the constructor is re-wrapped in
        :class:`~lexic.ir.base.IrLambda` (:data:`~lexic.ir.base.IrNone` for an
        ``alternation``), the structural metadata carried over verbatim.
        ``ModelBody.of(rf).bake()`` is runtime-identical to ``rf``.

        :param rule_fold: The baked record to lift.
        :returns: The equivalent :class:`ModelBody`.
        """
        ctor = IrNone if rule_fold.kind == "alternation" else IrLambda(rule_fold.ctor)
        return cls(
            rule_fold.kind,
            ctor,
            rule_fold.n_items,
            rule_fold.fields,
            rule_fold.fast,
        )


def _subtree_text(node: ParseTree | IrLiteral | PayloadLeaf) -> str:
    """All consumed chars under ``node``, in source order (iterative).

    A delegated :class:`~lexic.parsing.earley.kernel.forest.forest.PayloadLeaf` contributes its
    recorded span text (its interior was folded by the sub-run, not walked).
    """
    parts: list[str] = []
    stack: list[ParseTree | IrLiteral | PayloadLeaf] = [node]
    while stack:
        k = stack.pop()
        if isinstance(k, ParseTree):
            stack.extend(reversed(k.kids))
        elif isinstance(k, PayloadLeaf):
            parts.append(k.text)
        else:
            parts.append(str(k))
    return "".join(parts)


type Offsets = "tuple[dict[int, int], dict[int, int]]"
"""``(start by node id, consumed length by node id)`` for one parse tree."""

_NO_OFFSETS: Offsets = ({}, {})
"""What a fold with no ``span`` field carries instead of paying for offsets."""


def _leaf_len(kid: object) -> int:
    """Characters a non-``ParseTree`` kid consumed."""
    return len(kid.text) if isinstance(kid, PayloadLeaf) else len(str(kid))


def _kid_size(kid: object, sizes: dict[int, int]) -> int:
    """Characters a kid consumed, from the pre-pass for a subtree."""
    return sizes[id(kid)] if kid.__class__ is ParseTree else _leaf_len(kid)


def _tree_offsets(root: ParseTree) -> Offsets:
    """Every node's start offset and size, in one pre-order pass with a cursor.

    Document positions the tree route does not otherwise carry: `ParseTree` is
    ``(symbol, kids)`` and `_subtree_text` REBUILDS a slot's text from its
    leaves, so leaf order plus leaf lengths already ARE the positions — this
    accumulates them once instead of re-finding a span by searching the
    document for its text (which is ambiguous the moment a document repeats
    itself).

    Sharing: the forest interns nodes, and a shared node's first occurrence
    wins here. That is exact for every NON-EMPTY node, because a non-empty
    derivation is keyed by its span and so cannot be shared across positions;
    only zero-width nodes can, and a zero-width span at another position is
    the one case this pass cannot separate. The PDA route, which carries the
    kernel's own offsets, has no such case — the parity gate pins the two
    routes to each other over the corpus.

    :param root: The start-rule match.
    :returns: ``(starts, sizes)`` keyed by node id.
    """
    starts: dict[int, int] = {}
    sizes: dict[int, int] = {}
    at = 0
    stack: list[object] = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, list):  # the close marker: [node]
            inner = node[0]
            sizes.setdefault(id(inner), at - starts[id(inner)])
            continue
        if isinstance(node, ParseTree):
            starts.setdefault(id(node), at)
            stack.append([node])
            stack.extend(reversed(node.kids))
            continue
        at += _leaf_len(node)
    return starts, sizes


def _slot_span(
    node: ParseTree, kids: Sequence[object], item: int, offsets: Offsets
) -> IrSpan:
    """Where the kid at ``item`` was consumed, from the PARENT's frame.

    Computed in the parent's frame rather than read off the kid, so a shared
    kid still reports the position it occupies HERE.

    :param node: The rule node being folded.
    :param kids: Its kids, in source order.
    :param item: The bound slot.
    :param offsets: The pre-pass's ``(starts, sizes)``.
    :returns: The slot's half-open span, in document code units.
    """
    starts, sizes = offsets
    at = starts[id(node)]
    for kid in kids[:item]:
        at += _kid_size(kid, sizes)
    return IrSpan(at, at + _kid_size(kids[item], sizes))


class ModelFold[M]:
    """The one authored instance-fold — an IR body-table plus its runtime.

    Generic in ``M``, the model type the start rule folds to: a fold built for
    a codegen grammar produces ``ModelFold[GrammarModel]`` and
    :meth:`apply` returns a ``GrammarModel`` — the engine stays a leaf w.r.t.
    :mod:`lexic.model`, so the concrete model type rides the type parameter the
    caller (``compile.py``) binds rather than an import.

    The authored form is :attr:`bodies`, a per-rule
    :class:`~lexic.ir.action.mapping.IrMap` from each rule's
    :class:`~lexic.ir.grammar.nodes.IrRuleRef` to its :class:`ModelBody` (an
    :class:`~lexic.ir.base.IrSelf`) — the same shape the grammar-text
    :class:`~lexic.parsing.earley.reduce.Reducer` carries its reductions in. On
    construction every body is :meth:`~ModelBody.bake`\\ d to the flat-runtime
    :class:`RuleFold` table :attr:`config`, which drives both this fold's
    :meth:`apply` (the engine-fallback path) and — via :attr:`baked` — the
    predictive PDA's clone compiler; both consumers are byte-for-byte unchanged
    from the retired plain-data config.

    Bottom-up ParseTree → model-instance fold: the runtime mirror of the
    :class:`~lexic.parsing.earley.reduce.Reducer`, same explicit-stack
    discipline, but the outputs are opaque constructor results rather than IR
    nodes, so it lives outside the IrSelf dispatch algebra.

    :ivar bodies: Rule ref → its :class:`ModelBody` (the authored IR body-table).
    :ivar config: Rule name → baked :class:`RuleFold`. Synthetic (``__rep``/
        ``__opt``/``__grp``) nodes are absent from it and looked through.
    """

    __slots__ = ("bodies", "config", "wants_spans")

    def __init__(self, bodies: IrMap) -> None:
        """Bake the IR body-table to its flat-runtime config, then validate.

        :param bodies: Rule ref → :class:`ModelBody`.
        :raises UnsupportedConstructError: On a kind outside
            :data:`FOLD_KINDS` or a field mode outside
            :data:`~lexic.ir.spine.bind.BIND_MODES`.
        """
        config: dict[str, RuleFold] = {
            str(ref): body.bake() for ref, body in bodies.items()
        }
        for rule_name, rule_fold in config.items():
            if rule_fold.kind not in FOLD_KINDS:
                raise UnsupportedConstructError(
                    f"fold: rule {rule_name!r} has unknown kind "
                    f"{rule_fold.kind!r} (expected one of {FOLD_KINDS})"
                )
            for field in rule_fold.fields:
                if field.mode not in BIND_MODES:
                    raise UnsupportedConstructError(
                        f"fold: field {rule_name}.{field.name} has unknown "
                        f"mode {field.mode!r} (expected one of {BIND_MODES})"
                    )
        self.bodies = bodies
        self.config = config
        # Offsets are derived only for a fold that asked: a `span` field
        # is templating's raw-span capture, and every other fold — every
        # ordinary grammar's — must not pay a pass for it.
        self.wants_spans = any(
            field.mode == "span"
            for rule_fold in config.values()
            for field in rule_fold.fields
        )

    @classmethod
    def from_config(cls, config: Mapping[str, RuleFold]) -> "ModelFold[object]":
        """Build a fold from a baked ``dict[str, RuleFold]`` (the lowered form).

        Lifts each :class:`RuleFold` to a :class:`ModelBody` (via
        :meth:`ModelBody.of`) and constructs the IR body-table — the inverse of
        :attr:`baked`. The authored path (:mod:`lexic.compile`) builds the body
        table directly; this is the direct-from-baked seam for callers holding
        the lowered config.

        :param config: Rule name → :class:`RuleFold`.
        :returns: The equivalent fold.
        """
        return cls(
            IrMap(
                *(
                    IrTuple(IrRuleRef(name), ModelBody.of(rule_fold))
                    for name, rule_fold in config.items()
                )
            )
        )

    @property
    def baked(self) -> dict[str, RuleFold]:
        """The baked rule name → :class:`RuleFold` table (the PDA clone input)."""
        return self.config

    def run_ok(self, tables: ParserTables, unit_rid: int) -> bool:
        """The run-collapse licence: may this lexical run collapse to one leaf?

        A run may collapse iff none of its unit leaves is a constructor-bearing
        rule (a config key) — those subtrees fold to models a single run leaf
        would erase. A bare terminal (``unit_rid < 0``) and any looked-through
        synthetic layer are safe: the fold reconstructs their text from the
        run's leaf.

        :param tables: The plain (uncollapsed) tables under analysis.
        :param unit_rid: The run's repetition-unit rule id (``-1`` = bare
            terminal).
        :returns: ``True`` when collapsing the run preserves the fold's output.
        """
        if unit_rid < 0:  # bare terminal unit — anonymous, no model structure
            return True
        resolved = unit_leaves(tables, unit_rid)
        if resolved is None:
            return False
        leaf_rids, _has_bare = resolved
        names = tables.decode.rule_names
        return not any(names[rid] in self.config for rid in leaf_rids)

    def apply(self, root: ParseTree) -> M:
        """Fold the parse tree of a start-rule match into its model.

        :returns: The start rule's model — of the type ``M`` this fold's
            constructors were built to produce (the ``results`` table holds the
            mixed intermediate outputs; only the start node's is the model).
        """
        results: dict[int, object] = {}
        offsets = _tree_offsets(root) if self.wants_spans else _NO_OFFSETS
        stack: list[tuple[ParseTree, bool]] = [(root, False)]
        push = stack.append
        while stack:
            node, expanded = stack.pop()
            if not expanded:
                push((node, True))
                for k in node.kids:
                    if k.__class__ is ParseTree and id(k) not in results:
                        push((k, False))
                continue
            self._fold_node(node, results, offsets)
        return cast(M, results[id(root)])

    # ── per-node folding ────────────────────────────────────────────

    def _fold_node(
        self, node: ParseTree, results: dict[int, object], offsets: Offsets
    ) -> None:
        rule_fold = self.config.get(str(node.symbol))
        if rule_fold is None:
            return  # synthetic (__rep/__opt/__grp) — parents look through it
        if rule_fold.kind == "value_str":
            results[id(node)] = rule_fold.ctor(value=_subtree_text(node))
        elif rule_fold.kind == "alternation":
            results[id(node)] = self._first_model_under(node, results)
        else:
            results[id(node)] = self._fold_sequence(node, rule_fold, results, offsets)

    def _fold_sequence(
        self,
        node: ParseTree,
        rule_fold: RuleFold,
        results: dict[int, object],
        offsets: Offsets,
    ) -> object:
        kids = node.kids
        if len(kids) != rule_fold.n_items:
            if kids:
                raise UnsupportedConstructError(
                    f"fold: {node.symbol}: {len(kids)} kids do not match "
                    f"{rule_fold.n_items} items (nor the empty arm)"
                )
            return rule_fold.ctor()  # empty alternate arm matched
        kwargs: dict[str, object] = {}
        for item, mode, name, lo in rule_fold.fields:
            if mode == "span":
                kwargs[name] = _slot_span(node, kids, item, offsets)
                continue
            value = self._fold_field(kids[item], mode, lo, results)
            # A model field whose sub-rule matched an EMPTY arm folds to None,
            # and None IS the value the record carries — the PDA's trusted
            # build reads exactly that out of `parts.get`. Dropping it would
            # turn "matched empty" into "missing field" and the checked
            # constructor refuses a required one.
            if value is not None or mode == "model":
                kwargs[name] = value
        return rule_fold.ctor(**kwargs)

    def _fold_field(
        self,
        kid: ParseTree | IrLiteral,
        mode: str,
        lo: int,
        results: dict[int, object],
    ) -> object:
        if mode == "text":
            return _subtree_text(kid)
        if mode == "gtext":
            text = _subtree_text(kid)
            return None if (not text and lo == 0) else text
        models = self._models_at(kid, results)
        if mode == "models":
            return models
        return models[0] if models else None

    def _models_at(
        self, kid: ParseTree | IrLiteral | PayloadLeaf, results: dict[int, object]
    ) -> list[object]:
        """Folded models at/under a kid slot, looking through synthetic layers.

        A delegated :class:`~lexic.parsing.earley.kernel.forest.forest.PayloadLeaf` contributes
        its pre-built sub-model directly (the PDA sub-run already folded it) —
        the same already-folded-child pass-through the PDA-side island splice
        performs.
        """
        kid_id = id(kid)
        if kid_id in results:  # directly folded — the common case, no walk
            model = results[kid_id]
            return [] if model is None else [model]
        out: list[object] = []
        stack: list[ParseTree | IrLiteral | PayloadLeaf] = [kid]
        while stack:
            k = stack.pop()
            if isinstance(k, PayloadLeaf):  # delegated pre-folded sub-model
                if k.payload is not None:
                    out.append(k.payload)
            elif isinstance(k, ParseTree):
                if id(k) in results:
                    model = results[id(k)]
                    if model is not None:
                        out.append(model)
                else:  # synthetic / non-model layer — descend
                    stack.extend(reversed(k.kids))
        return out

    def _first_model_under(self, node: ParseTree, results: dict[int, object]) -> object:
        """The first folded model under ``node``'s kids, or ``None``."""
        for kid in node.kids:
            models = self._models_at(kid, results)
            if models:
                return models[0]
        return None


# ── optional-nullable lift (engine-ambiguity policy) ──────────────────


def lift_optional_nullables(grammar: IrAst) -> IrAst:
    """Rewrite ``R?`` to ``R`` where ``R`` is nullable.

    An optional occurrence of a rule that itself derives empty is genuinely
    ambiguous on the empty span (absent vs empty match) — the engine raises on
    it. The lift is language-preserving (``R? == R`` for nullable ``R``) and
    keeps the empty match present as a zero-width kid, so item positions are
    untouched. Applied to the codegen grammar before :func:`normalize`.

    :param grammar: The instance grammar to lift.
    :returns: The lifted grammar (same rule order, same item positions).
    """
    rules = tuple(grammar.rules)
    nullable = nullable_names(rules)

    def lift_item(item: IrItem) -> IrItem:
        atom = item.atom
        quantifier = item.quantifier
        if (
            isinstance(atom, IrRuleRef)
            and str(atom) in nullable
            and int(quantifier.lo) == 0
            and not isinstance(quantifier.hi, IrNoneType)
            and int(quantifier.hi) == 1
        ):
            return IrItem(atom, IrQuantifier(1, 1))
        return item

    lifted = tuple(
        IrRule(
            rule.name,
            IrAlternation(
                *(
                    IrSequence(*(lift_item(i) for i in arm if isinstance(i, IrItem)))
                    for arm in rule.body
                )
            ),
            rule.semantic,
        )
        for rule in rules
    )
    return IrAst(rules=IrSeq(*lifted), start=grammar.start)


# ── instance-path run collapse (the fold-config licence) ──────────────


_COLLAPSED: dict[tuple[int, int, int], tuple[ModelFold, IrAst, ParserTables]] = {}
"""Collapsed instance-tables memo — (id(fold), id(grammar), bits) → (fold,
grammar, tables). Strong references pin both ids against reuse."""


def collapsed_fold_tables(
    grammar: IrAst, fold: ModelFold, bits: int = ORIGIN_BITS
) -> ParserTables:
    """Instance tables with every fold-safe lexical run collapsed.

    The grammar-side proof (charset, uniqueness, follow disjointness) comes
    from :func:`~lexic.parsing.earley.lexruns.run_candidates`; the fold-side licence
    (:meth:`ModelFold.run_ok`) keeps only runs whose collapsed multi-char
    leaf hides structure the fold looks through anyway. Every kept run is
    :data:`~lexic.parsing.earley.kernel.tables.RUN_STR` (text-preserving): the run text
    stays a leaf in the tree so ``to_text()`` round-trips exactly — never
    ``RUN_DROP``. Memoised per ``(fold, grammar, bits)``.

    :param grammar: The Earley-normalised instance grammar.
    :param fold: The configured :class:`ModelFold` for that grammar.
    :param bits: The packing tier the tables compile at.
    :returns: The collapsed tables (the plain tables when nothing collapses).
    """
    key = (id(fold), id(grammar), bits)
    entry = _COLLAPSED.get(key)
    if entry is not None:
        return entry[2]
    tables = collapse_runs(
        grammar,
        lambda plain, unit_rid: RUN_STR if fold.run_ok(plain, unit_rid) else None,
        bits,
    )
    _COLLAPSED[key] = (fold, grammar, tables)
    return tables
