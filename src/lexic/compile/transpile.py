"""Transpile — a document under grammar A re-expressed under grammar B.

The mechanism is the model plane: A's parse is the lossless account of the
source, B's ``to_text()`` is the emitter, and the TRANSFORM between the two
model spaces is the one authored piece — a table of per-RULE bodies, spelled
in the grammars' own vocabulary:

- rows are keyed by A's **rule names**, never by class objects;
- a body builds a target by **name** through :class:`Make`, carries a
  scalar's exact source spelling through :class:`Spelled`, flattens a
  hoisted channel through :class:`Flat` or a built chain through
  :class:`Split`, and branches on what a child became through :class:`Is`
  — beside the ordinary ir/ algebra (``IrArg`` picks a transformed child,
  ``IrPipe``/``IrEach``/``IrCond``/``IrRaise`` compose).

:func:`transpile` BAKES that table against the two artifacts: rule names
resolve to the synthesized classes, and a :class:`Make` aimed at a hoisted
list rule (``x ::= y (sep y)*``) grows the ``y``/``x-item`` chain from a
flat tuple — the inverse of lexic's own hoist passes, supplied by the tier
that ran them. An authored table therefore contains no class objects at
all: it is pure data, and travels through the notation like a grammar or a
reducer does.

:class:`~lexic.ir.action.walk.IrBottomUp` drives the walk — every body
receives its already-transformed children on ``nc``, and every intermediate
rebuild threads through checked construction, so a body that hands a parent
something outside its grammar refuses with
:exc:`~lexic.exceptions.FieldValidationError` instead of shipping.

What the artifact adds over a bare walk is the transpile CONTRACT, gated
always-on in the export-gate tradition:

- **completeness** — the product must land wholly in the target's class
  space. An untargeted source class surviving into the output means the
  table has a hole, and the hole is refused with the class named rather
  than emitted as text that may or may not mean something.
- **membership and fidelity** (:meth:`Transpiler.run`) — the emitted text
  must parse under the target, and parse back EQUAL to the models the
  transform built: what is returned is in B's language and means what T
  built.

What a table cannot express is the caller's stated domain: a body refuses
with its own words, and the refusal carries through — never a silent drop.
"""

from __future__ import annotations

from typing import Callable, ClassVar, Self, Sequence, cast

from lexic.compile.artifact import CompiledGrammar
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IrAction,
    IrBottomUp,
    IrInt,
    IrLambda,
    IrLeaf,
    IrMap,
    IrNamedTuple,
    IrNone,
    IrRuleRef,
    IrSelf,
    IrSingleton,
    IrStr,
    IrTuple,
    IrTypeMap,
    fold_name,
)
from lexic.model import GrammarModel
from lexic.parsing.earley.kernel.forest.ambiguity import Resolver

__all__ = ["Flat", "Is", "Make", "Spelled", "Transpiler", "transpile"]


class Spelled(IrLeaf[IrSelf, IrStr], metaclass=IrSingleton):
    """The focus, as the source text it spells — ``to_text()`` as algebra.

    ``Make("number", Spelled())`` carries a scalar whole: the source node's
    exact spelling becomes the target's payload, so a float needs no float
    type and an escape survives untouched. Lives at this tier rather than
    ``ir/`` because the spelling protocol is the model layer's (the foldkit
    precedent: a tier's authored vocabulary lives with its tier).
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Return the focus's source spelling as an :class:`IrStr`.

        :param _d: Dispatcher (unused — the spelling is the node's own).
        :param n: The focus; must be a model (the layer that spells).
        :param _nc: Pre-walked children (unused).
        :returns: ``n.to_text()``, lifted onto the spine.
        :raises UnsupportedConstructError: When the focus is not a model.
        """
        return IrStr(GrammarModel.ensure(n, "Spelled: the focus").to_text())


class Flat(IrLeaf[IrSelf, IrTuple], metaclass=IrSingleton):
    """A hoisted list's argument channel, flattened — ``(first, *rest)``.

    The reading half of the list story: a source rule ``x ::= y (sep y)*``
    hands its body ``nc = (first, (item, item, …))``, and ``Flat()`` turns
    that into one flat tuple. :class:`Make` aimed at a list-shaped target
    rule is the writing half.
    """

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrTuple:
        """Flatten ``(first, rest-tuple)`` into one tuple.

        :param _d: Dispatcher (unused).
        :param _n: The focus (unused — the channel is the subject).
        :param nc: The argument channel: the first element, then a tuple.
        :returns: ``(nc[0], *nc[1])``.
        """
        rest = nc[1] if len(nc) > 1 and isinstance(nc[1], tuple) else ()
        return IrTuple(nc[0], *rest)


class Is(IrNamedTuple[str]):
    """Test whether the FOCUS is the named target rule's model — by name.

    The focus-variant of :class:`~lexic.ir.IrIsA` (which tests a named
    attribute), spelled in the transform's own vocabulary: ``IrPipe(IrArg(1),
    IrCond(test=Is("flowmap"), …))`` branches on what a transformed child
    became. Baked to the class like :class:`Make`; evals to a truth value
    (``IrInt`` in ``{0, 1}``).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    rule: str

    def __new__(cls, rule: str) -> Self:
        """Spell the test: the target grammar's rule name."""
        make = cast(Callable[..., Self], super().__new__)
        return make(cls, IrStr(fold_name(str(rule))))

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Refuse — an unbaked table reached evaluation.

        :raises UnsupportedConstructError: Always; hand the table to
            :func:`transpile` first.
        """
        raise UnsupportedConstructError(
            f"Is({str(self.rule)!r}): an unbaked transform table cannot run "
            "— hand it to transpile()"
        )


class Split(IrLeaf[IrSelf, IrTuple], metaclass=IrSingleton):
    """A hoisted chain, read back flat — the inverse of the list ``Make``.

    The focus is a list rule's model (``x ::= y (sep y)*`` → ``X(y,
    x_item[…])``); the result is the flat tuple of its ``y``s. Absence
    (``None`` — the optional list was empty) splits to the empty tuple, so
    a downstream :class:`~lexic.ir.IrEach` maps over nothing.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrTuple:
        """Flatten the chain model into its elements.

        :param _d: Dispatcher (unused).
        :param n: The chain's head model, or ``None``/``IrNone`` for absence.
        :param _nc: Pre-walked children (unused).
        :returns: ``(head-element, *item-elements)`` — or empty for absence.
        :raises UnsupportedConstructError: When the focus is not chain-shaped.
        """
        if n is None or n is IrNone:
            return IrTuple()
        head = GrammarModel.ensure(n, "Split: the focus")
        kids = head.children()
        if len(kids) != 2 or not isinstance(kids[1], tuple):
            raise UnsupportedConstructError(
                f"Split: {type(head).__name__} is not a hoisted chain — "
                "expected (element, items) as its two bound fields"
            )
        return IrTuple(
            kids[0],
            *(
                GrammarModel.ensure(item, "Split: a chain item").children()[0]
                for item in kids[1]
            ),
        )


class Make(IrNamedTuple[str, IrSelf]):
    """Build a target model, by RULE NAME — resolved when the table bakes.

    :class:`~lexic.ir.IrBuild`'s exact contract, with the class replaced by
    a name: ``args=IrNone`` (default) splats the raw argument channel —
    the transformed children, positionally in bound-field order — and an
    ``args`` body reshapes it first (``Make("line", IrTuple(IrArg(0),
    IrArg(1)))``). Aimed at a hoisted list rule (``x ::= y (sep y)*``) the
    evaluated arguments are read as the FLAT element tuple and the chain is
    grown — first element in the head slot, the rest wrapped in the item
    rule's class. An argument that evaluates to ``None`` propagates:
    absence flows, so an optional slot stays optional.

    A ``Make`` never evaluates directly — :func:`transpile` bakes it against
    the target artifact. That is what keeps the authored table free of class
    objects: it is data, and travels through the notation.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("args",)
    rule: str
    args: IrSelf = IrNone

    def __new__(cls, rule: str, args: IrSelf = IrNone) -> Self:
        """Spell the row: the target rule's name and the argument body.

        :param rule: The target grammar's rule name (folded like the
            grammar's own).
        :param args: One body whose result is splatted into the
            constructor; ``IrNone`` splats the raw channel.
        """
        make = cast(Callable[..., Self], super().__new__)
        return make(cls, IrStr(fold_name(str(rule))), args)

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """Refuse — an unbaked table reached evaluation.

        :raises UnsupportedConstructError: Always; hand the table to
            :func:`transpile` first.
        """
        raise UnsupportedConstructError(
            f"Make({str(self.rule)!r}): an unbaked transform table cannot "
            "run — hand it to transpile(), which resolves rule names "
            "against the target grammar"
        )


class _Grown(IrNamedTuple[type, type, IrSelf]):
    """A baked list-``Make``: grow the target's hoisted chain from a flat tuple.

    Internal to the bake — never authored, never emitted. ``head`` is the
    list rule's class, ``item`` the chain rule's, ``source`` the baked body
    yielding the flat element tuple (``IrNone`` splats the raw channel).
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("source",)
    head: type
    item: type
    source: IrSelf = IrNone

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Build ``head(first, [item(x), …])`` from the flat tuple.

        :returns: The grown chain; ``IrNone``-as-absence when the source
            yields ``None`` or an empty tuple (the optional slot stays
            empty).
        """
        flat = tuple(nc) if self.source is IrNone else self.source.eval(d, n, nc)
        if flat is None or flat is IrNone or not tuple(flat):
            return IrNone
        items = tuple(flat)
        names = _slot_names(self.head)
        rest = [self.item(x) for x in items[1:]]
        return self.head(**dict(zip(names, (items[0], rest))))


class Transpiler(IrNamedTuple[CompiledGrammar, CompiledGrammar, IrBottomUp]):
    """The retained transpilation product — two grammars and the baked walk.

    :ivar source: The grammar the document is read under.
    :ivar target: The grammar the product is spelled under.
    :ivar walk: The baked transform — a bottom-up walk whose table maps
        source model classes to bodies building target models.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    source: CompiledGrammar
    target: CompiledGrammar
    walk: IrBottomUp

    def apply(self, model: GrammarModel) -> GrammarModel:
        """Transform a parsed source model into the target's model space.

        :param model: A model parsed under :attr:`source`.
        :returns: The target-space model, completeness-gated.
        :raises UnsupportedConstructError: When the product is not a model,
            or a source class survived into it (a hole in the table).
        """
        product = GrammarModel.ensure(
            self.walk.apply(model), "transpile: the transform's product"
        )
        self._complete(product)
        return product

    def run(self, text: str, resolve: Resolver | None = None) -> str:
        """Parse under the source, transform, emit — the whole path, gated.

        :param text: A document in the source grammar's language.
        :param resolve: The source parse's ambiguity resolver, if any.
        :returns: The document re-expressed in the target's language.
        :raises UnsupportedConstructError: When the text refuses under the
            source, the product fails the completeness gate, the emitted
            text refuses under the target (not in its language), or it
            parses back as a DIFFERENT value than the transform built.
        """
        product = self.apply(self.source.parse(text, resolve))
        out = product.to_text()
        again = self.target.parse(out)
        if again != product:
            raise UnsupportedConstructError(
                "transpile: the emitted text parses back as a different value "
                "than the transform built — the target grammar reads "
                f"{type(again).__name__} differently than it was written"
            )
        return out

    def _complete(self, product: GrammarModel) -> None:
        """Refuse any model in the product that is not the target's.

        :param product: The transform's product.
        :raises UnsupportedConstructError: Naming the first foreign class.
        """
        allowed = set(self.target.classes.values())
        stack: list[object] = [product]
        while stack:
            node = stack.pop()
            if isinstance(node, GrammarModel):
                if type(node) not in allowed:
                    raise UnsupportedConstructError(
                        f"transpile: {type(node).__name__} is not a class of "
                        "the target grammar — the transform's table has no "
                        "row for it (or a body passed it through)"
                    )
                stack.extend(node.children())
            elif isinstance(node, tuple):
                stack.extend(node)


# ── the bake: rule names → classes, list Makes → grown chains ───────────


def _slot_names(cls: type) -> list[str]:
    """A model class's field names in ITEM SLOT order — the channel's order.

    Empty for a class with no binds (a ``value_str``'s implicit ``value``
    constructs positionally).

    :param cls: The target model class.
    :returns: Field names ordered by their bound item slots.
    """
    binds = getattr(cls, "__binds__", {})
    return [name for _slot, (name, _bind) in sorted(binds.items())]


def _by_rule(compiled: CompiledGrammar) -> dict[str, type]:
    """Each synthesized class under its own rule's name.

    :param compiled: The artifact whose classes to index.
    :returns: Folded rule name → class; every class carries its rule.
    """
    return {
        fold_name(str(cls.__grammar__.name)): cls for cls in compiled.classes.values()
    }


def _list_shape(cls: type, targets: dict[str, type]) -> type | None:
    """The item class of a hoisted list rule, or ``None`` for a plain one.

    A list rule is codegen's own artifact — ``x ::= y (sep y)*`` hoists to
    ``x ::= y x-item*`` with ``x-item ::= sep y`` — so its shape is exactly:
    two bound fields, the second a ``models`` list of a single-model-field
    item rule. Recognized structurally from the class's own rule and binds,
    never by name.

    :param cls: A candidate target class.
    :param targets: The target's rule-name index, for the item class.
    :returns: The item class to grow with, or ``None``.
    """
    binds = sorted(cls.__binds__.items())
    if len(binds) != 2 or binds[1][1][1].mode != "models":
        return None
    arm = next((a for a in cls.__grammar__.body if a), None)
    if arm is None:
        return None
    atom = arm[binds[1][0]].atom
    if not isinstance(atom, IrRuleRef):
        return None
    item = targets.get(fold_name(str(atom)))
    if item is None or len(item.__binds__) != 1:
        return None
    return item


def _baked_make(targets: dict[str, type], _d: IrSelf, n: IrSelf, _nc) -> IrSelf:
    """One :class:`Make`, resolved — the bake walk's only body.

    Runs under the bake's own bottom-up walk, so ``n`` is the ``Make`` with
    its argument bodies already baked. A plain rule becomes a positional
    construction; a list-shaped rule becomes a :class:`_Grown`.

    :raises UnsupportedConstructError: When the rule is not the target's.
    """
    make = Make.ensure(n, "bake: the Make row")
    cls = targets.get(str(make.rule))
    if cls is None:
        raise UnsupportedConstructError(
            f"transpile: Make({str(make.rule)!r}) names no rule of the "
            f"target grammar — it defines {sorted(targets)}"
        )
    item = _list_shape(cls, targets)
    if item is not None:
        return _Grown(cls, item, make.args)
    return _Construct(cls, make.args)


class _Construct(IrNamedTuple[type, IrSelf]):
    """A baked plain ``Make``: :class:`~lexic.ir.IrBuild` with a resolved class.

    Internal to the bake. ``None`` results ride through to the checked
    constructor as absent optionals; ``IrNone`` args splat the raw channel.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ("args",)
    target: type
    args: IrSelf = IrNone

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Construct the target from the raw channel or the reshaped args.

        Arguments arrive in ITEM SLOT order — the order the grammar's arm
        spells and the walk's channel carries — and are bound to fields
        through the binds table, because a class DECLARES defaults-last and
        the two orders differ whenever an optional slot precedes a required
        one. Spine absence (``IrNone``) bridges to the model layer's own
        (``None``) per part, so an optional slot stays an absent optional.
        """
        parts = nc if self.args is IrNone else tuple(self.args.eval(d, n, nc))
        values = [None if p is IrNone else p for p in parts]
        names = _slot_names(self.target)
        if names:
            return self.target(**dict(zip(names, values)))
        return self.target(*values)


class _TypeTest(IrNamedTuple[type]):
    """A baked :class:`Is`: the focus against the resolved class.

    Internal to the bake — the truth value ``IrCond`` branches on.
    """

    _child_attrs: ClassVar[tuple[str, ...]] = ()
    target: type

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrSelf:
        """``isinstance``, as a truth value on the spine."""
        return IrInt(1 if isinstance(n, self.target) else 0)


def _baked_is(targets: dict[str, type], n: IrSelf) -> IrSelf:
    """One :class:`Is`, resolved against the target's rule-name index.

    :raises UnsupportedConstructError: When the rule is not the target's.
    """
    test = Is.ensure(n, "bake: the Is test")
    cls = targets.get(str(test.rule))
    if cls is None:
        raise UnsupportedConstructError(
            f"transpile: Is({str(test.rule)!r}) names no rule of the target "
            f"grammar — it defines {sorted(targets)}"
        )
    return _TypeTest(cls)


def transpile(
    source: CompiledGrammar, target: CompiledGrammar, rules: IrMap
) -> Transpiler:
    """Bake the rule-named table and build the retained :class:`Transpiler`.

    :param source: The grammar documents are read under.
    :param target: The grammar products are spelled under.
    :param rules: The transform — source RULE NAMES to bodies. A body is
        algebra (:class:`Make`/:class:`Spelled`/:class:`Flat` beside the
        ir/ nodes) or, where a genuine policy needs code, an
        :class:`~lexic.ir.IrLambda`. Unnamed rules pass through the walk
        untouched; a semantic one reaching the product without a row fails
        the completeness gate.
    :returns: The transpiler — bake once, :meth:`Transpiler.run` many.
    :raises UnsupportedConstructError: On a row naming no source rule, or a
        ``Make`` naming no target rule.
    """
    sources = _by_rule(source)
    targets = _by_rule(target)
    baker = IrBottomUp(
        actions=IrTypeMap(
            IrAction(
                Make,
                IrLambda(lambda d, n, nc, _t=targets: _baked_make(_t, d, n, nc)),
            ),
            IrAction(
                Is,
                IrLambda(lambda _d, n, _nc, _t=targets: _baked_is(_t, n)),
            ),
        )
    )
    rows: list[IrAction] = []
    for key, body in rules.items():
        name = fold_name(str(key))
        cls = sources.get(name)
        if cls is None:
            raise UnsupportedConstructError(
                f"transpile: row {name!r} names no rule of the source "
                f"grammar — it defines {sorted(sources)}"
            )
        rows.append(IrAction(cls, baker.apply(body)))
    return Transpiler(source, target, IrBottomUp(actions=IrTypeMap(*rows)))
