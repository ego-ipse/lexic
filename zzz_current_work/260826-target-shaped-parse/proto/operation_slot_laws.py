"""Lower the REAL operation declarations to the cyclic slot algebra.

`cyclic_meaning.py` decides a zero-width strongly connected component from four
per-slot classes — ``const`` / ``ident`` / declared-``finite`` /
proper-subvalue-``grow``. It reads them from a toy policy table. This module
supplies them for the operations that actually exist in ``src``: every action
declared by the shipped GBNF, ABNF, EBNF and JSON reducers, plus the emit-side
action tables, plus the contribution policies in ``lexic.ir.reduction``.

**The classification is structural, never nominal.** Nothing here reads an
operation's name, samples its values to guess, keys on a Python callable, or
runs an ``isinstance`` cascade. One open table maps an *operation type* to the
law it declares, resolved through `IrTypeMap`'s own concrete-first ``__mro__``
walk — the dispatcher lexic uses everywhere — and a type with no row reaches a
raising default that names the operation and the slot. An expression's law is
then the COMPOSITION of its sub-expressions' laws under those rows, so the real
reducer bodies are classified by being read, not by being recognised.

The proof obligation each authored operation must supply is one row in
:data:`OPERATION_LAWS` (or, for a construction target, :data:`CONSTRUCTOR_LAWS`)
stating, for an argument whose value varies:

- ``const``  — the result does not depend on that argument at all;
- ``ident``  — the result IS that argument;
- ``finite`` — the result ranges over a declared, explicitly bounded image;
- ``grow``   — the result retains that argument as a proper sub-value, so the
  operation is injective in it and strictly increases value size.

Anything else has no law and must refuse at binding, with words. Two lanes are
deliberately separated: what the present source can be held to, and the product
operations that do not exist until the product compiler lands (see
:data:`FUTURE_OPERATIONS`) — those are named as declaration obligations, not
audited.

Run directly for the census over the real reducers, the finite-domain
differential, the misdeclaration catches, and the bounds.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Mapping, Sequence
from typing import NamedTuple

import cyclic_meaning as cyclic

from lexic.compile import canonical_grammar
from lexic.compile.foldkit import IrNamed
from lexic.exceptions import IrKeyError, UnsupportedConstructError
from lexic.grammars.abnf import ABNF_FLAVOUR, ABNF_REDUCER
from lexic.grammars.ebnf import EBNF_FLAVOUR, EBNF_REDUCER
from lexic.grammars.gbnf import GBNF_FLAVOUR, GBNF_REDUCER
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import (
    IrAction,
    IrApply,
    IrArg,
    IrArgs,
    IrAst,
    IrAt,
    IrBuild,
    IrChild,
    IrChildren,
    IrChr,
    IrCompare,
    IrConcat,
    IrCond,
    IrEach,
    IrEmit,
    IrField,
    IrGlyph,
    IrIndex,
    IrInt,
    IrIsA,
    IrJoin,
    IrLen,
    IrMap,
    IrMapping,
    IrMerge,
    IrNode,
    IrNone,
    IrNoneType,
    IrOp,
    IrOrd,
    IrPass,
    IrPipe,
    IrRadix,
    IrRaise,
    IrRebuild,
    IrRuleRef,
    IrScalar,
    IrSelf,
    IrStr,
    IrThis,
    IrTuple,
    IrTypeMap,
    IrUnradix,
    IrUtf,
    IrWalk,
    Reducer,
    canonicalize,
)
from lexic.ir.grammar.nodes import IrAlternation, IrItem, IrLiteral, IrRule, IrSequence
from lexic.ir.reduction import Drop, KeepRaw, KeepReduced, Yield
from lexic.parsing.earley.normalize import normalize

CONST = cyclic.CONST
IDENT = cyclic.IDENT
FINITE = cyclic.FINITE
GROW = cyclic.GROW

CARRYING = frozenset({IDENT, GROW})
"""The classes that let a value reach a parent unchanged or embedded."""

UNICODE_POINTS = 0x110000
"""The declared image bound of every code-point-valued operation."""

TRUTH_VALUES = 2
"""The declared image bound of a truth-valued operation — ``IrInt`` in {0, 1}."""


class SlotRefusal(UnsupportedConstructError):
    """An operation and slot for which no law is declared or derivable."""


class SlotLaw(NamedTuple):
    """One operation's declared dependence on the value in one child slot."""

    kind: str
    bound: int = 0


UNKNOWN = "unknown"
"""A position whose own law refused — never a verdict, only an argument state."""

CONST_LAW = SlotLaw(CONST, 1)
IDENT_LAW = SlotLaw(IDENT)
GROW_LAW = SlotLaw(GROW)
UNKNOWN_LAW = SlotLaw(UNKNOWN)


def finite(bound: int) -> SlotLaw:
    """A declared finite image of exactly ``bound`` values."""
    return SlotLaw(FINITE, bound)


class Env(NamedTuple):
    """The slot under study, the channel width, the focus law, and whether the
    focus's TEXT VIEW is already a function of its span alone."""

    slot: int
    width: int
    focus: SlotLaw
    span_fixed: bool = False


class LawRule(IrStr):
    """A named slot-law declaration — the leaf IS its :data:`LAW_RULES` key.

    The `foldkit.IrNamed` precedent: a registry-resolved symbol rather than an
    embedded closure, so a declaration table stays repr-able and a reader can
    see WHICH law an operation claims without executing anything.
    """

    A scalar declaration needs no custom allocation, equality, hashing, or
    executable action surface. Keeping it on the existing scalar spine also
    prevents a law declaration from being mistaken for an operation body.
    """


# ── the class algebra ─────────────────────────────────────────────────────


def _retain(law: SlotLaw) -> SlotLaw:
    """A retaining constructor's law: the argument becomes a proper subvalue."""
    if law.kind == CONST:
        return CONST_LAW
    if law.kind == FINITE:
        return finite(law.bound)
    return GROW_LAW


def _project(law: SlotLaw, what: str) -> SlotLaw:
    """A projection's law — reading INTO a value is not injective."""
    if law.kind == CONST:
        return CONST_LAW
    if law.kind == FINITE:
        return finite(law.bound)
    raise SlotRefusal(
        f"{what}: projects out of a slot-carrying value; a projection is not"
        " injective, so no const/ident/finite/grow law holds"
    )


def _decode(law: SlotLaw, what: str) -> SlotLaw:
    """A scalar decode's law — it neither retains nor bounds its input."""
    if law.kind == CONST:
        return CONST_LAW
    if law.kind == FINITE:
        return finite(law.bound)
    raise SlotRefusal(
        f"{what}: decodes a slot-carrying value into a scalar; the result"
        " neither retains it nor has a declared finite image"
    )


def _bounded(law: SlotLaw, bound: int) -> SlotLaw:
    """An operation with a declared finite codomain, whatever its input."""
    return CONST_LAW if law.kind == CONST else finite(bound)


def _combine(laws: Sequence[SlotLaw], what: str) -> SlotLaw:
    """How a slot reaches an operation through several of its positions.

    A single carrying position DOMINATES, even beside a position whose own law
    refused: if the receiving operation retains its arguments, then equal
    results force equal components, so injectivity follows from that one
    position alone and the others cannot take it away. Whether retention holds
    is the constructor law's question, asked next — this only says how the slot
    arrives. Without a carrying position an unclassified one is fatal, because
    nothing else pins the result.
    """
    kinds = {law.kind for law in laws}
    if GROW in kinds:
        return GROW_LAW
    if IDENT in kinds:
        return IDENT_LAW
    if UNKNOWN in kinds:
        raise SlotRefusal(
            f"{what}: an argument position has no law and no other position"
            " carries the slot, so the result is unclassified"
        )
    if FINITE in kinds:
        return finite(sum(law.bound for law in laws if law.kind == FINITE))
    return CONST_LAW


def _join(laws: Sequence[SlotLaw], varying: bool, what: str) -> SlotLaw:
    """The law of a value that is ONE of several branch results.

    :param laws: The branches' laws.
    :param varying: Whether the branch selection itself depends on the slot.
    :returns: The combined law.
    :raises SlotRefusal: When the branches disagree in a way no class covers.
    """
    if not laws:
        return CONST_LAW
    kinds = {law.kind for law in laws}
    if kinds == {IDENT}:
        return IDENT_LAW
    if kinds == {GROW} and not varying:
        return GROW_LAW
    if kinds <= {CONST, FINITE}:
        total = sum(law.bound if law.kind == FINITE else 1 for law in laws)
        return CONST_LAW if not varying and kinds == {CONST} else finite(total)
    raise SlotRefusal(
        f"{what}: branches classify as {sorted(kinds)}"
        f"{' under a slot-dependent test' if varying else ''}; the selected"
        " branch is not determined, so no single law holds"
    )


# ── the classifier ────────────────────────────────────────────────────────


class Counts:
    """What one classification pass visited."""

    __slots__ = ("expressions", "resolutions")

    def __init__(self) -> None:
        self.expressions = 0
        self.resolutions = 0


class Classifier:
    """Abstract interpretation of one operation body over the slot algebra."""

    __slots__ = ("constructors", "counts", "laws")

    def __init__(
        self,
        laws: IrTypeMap,
        constructors: IrMap,
        counts: Counts | None = None,
    ) -> None:
        self.laws = laws
        self.constructors = constructors
        self.counts = Counts() if counts is None else counts

    def law(self, node: IrSelf, env: Env) -> SlotLaw:
        """The law of one expression with respect to ``env.slot``.

        :param node: The authored operation.
        :param env: The slot under study, the channel width, and the focus law.
        :returns: The derived :class:`SlotLaw`.
        :raises SlotRefusal: When the operation declares no law.
        """
        self.counts.expressions += 1
        return LAW_RULES[str(self.rule(node, env))](self, node, env)

    def attempt(self, node: IrSelf, env: Env) -> SlotLaw:
        """One position's law, or :data:`UNKNOWN_LAW` when it has none."""
        try:
            return self.law(node, env)
        except SlotRefusal:
            return UNKNOWN_LAW

    def rule(self, node: IrSelf, env: Env) -> LawRule:
        """Resolve the declared rule for ``type(node)`` or refuse with words."""
        self.counts.resolutions += 1
        if not isinstance(node, IrSelf):
            raise SlotRefusal(
                f"payload {type(node).__name__!r} (slot {env.slot}) is not an"
                " IR operation; only an IrSelf node can declare a slot law"
            )
        try:
            found = self.laws.resolve(node)
        except IrKeyError as error:
            raise SlotRefusal(
                f"operation {type(node).__name__!r} declares no slot law"
                f" (slot {env.slot}); an authored operation must supply one"
            ) from error
        if not isinstance(found, LawRule):
            raise SlotRefusal(
                f"operation {type(node).__name__!r} (slot {env.slot}) resolved"
                f" to {type(found).__name__!r}, which is not a law declaration"
            )
        return found

    def constructor(self, target: type, env: Env) -> LawRule:
        """Resolve a construction target's declared law through its ``__mro__``."""
        self.counts.resolutions += 1
        for base in target.__mro__:
            found = self.constructors.get(base)
            if isinstance(found, LawRule):
                return found
        raise SlotRefusal(
            f"construction target {target.__name__!r} declares no law"
            f" (slot {env.slot}); a target must state whether it retains its"
            " arguments, bounds them, or decodes them"
        )

    def positions(self, args: IrSelf, env: Env, what: str) -> tuple[SlotLaw, ...]:
        """The laws of an operation's positional arguments.

        ``IrNone`` and :class:`IrArgs` both splat the raw channel, so the slot
        occupies exactly one position unchanged; an :class:`IrTuple` literal is
        read element-wise; anything else hides its positions and refuses.
        """
        if args is IrNone or isinstance(args, IrArgs):
            return (IDENT_LAW,)
        if type(args) is IrTuple:
            return tuple(self.attempt(part, env) for part in args)
        raise SlotRefusal(
            f"{what}: argument expression {type(args).__name__!r} does not"
            " expose its positions, so no per-slot law is derivable"
        )


# ── the declared rules ────────────────────────────────────────────────────


def _as[Node: IrSelf](node: IrSelf, kind: type[Node], what: str) -> Node:
    """Narrow a dispatched node to the type its declared rule is written for.

    The one genuine boundary narrowing here: a row in :data:`OPERATION_LAWS`
    binds a rule to a type, so a rule that receives another one has been
    mis-wired, and saying so is better than reading fields off it.
    """
    if not isinstance(node, kind):
        raise SlotRefusal(
            f"{what}: rule bound to {kind.__name__!r} received {type(node).__name__!r}"
        )
    return node


def _rule_const(_c: Classifier, _node: IrSelf, _env: Env) -> SlotLaw:
    """Ignores the argument channel entirely."""
    return CONST_LAW


def _rule_this(_c: Classifier, _node: IrSelf, env: Env) -> SlotLaw:
    """Evaluates to the current focus."""
    return env.focus


def _rule_arg(_c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Reads one channel position — the identity exactly on that slot.

    A NEGATIVE position refuses. Resolving it needs the exact channel width,
    and this analysis only has an upper bound: a quantified item makes a rule's
    channel width input-dependent (``abnf:cvbody`` reads ``IrArg(-1)`` behind a
    ``cvany*``), so no single static width can say where it lands. Resolving it
    against an over-approximation would name a HIGHER slot than the real one
    and classify the truly carrying slot ``const`` — the unsafe direction.
    """
    index = int(_as(node, IrArg, "IrArg"))
    if index < 0:
        raise SlotRefusal(
            f"IrArg({index}): a negative position needs the exact channel"
            " width, which a quantified item makes input-dependent"
        )
    return IDENT_LAW if index == env.slot else CONST_LAW


def _rule_args(_c: Classifier, _node: IrSelf, _env: Env) -> SlotLaw:
    """Reads the whole channel as a tuple, retaining every argument."""
    return GROW_LAW


def _rule_pipe(c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Rebinds the focus to a computed value, then evaluates the body."""
    pipe = _as(node, IrPipe, "IrPipe")
    source = c.law(pipe.source, env)
    return c.law(pipe.body, Env(env.slot, env.width, source))


def _static_truth(test: IrSelf, env: Env) -> bool | None:
    """Whether one test's TRUTH is already settled by the channel's shape.

    A collection-valued test is truthy exactly when it has elements, and a
    slot's VALUE cannot change how many elements the channel or a literal
    tuple has. Every slot this analysis classifies exists, so a channel-wide
    test is settled true; a literal tuple is settled by its own length.
    """
    if isinstance(test, IrArgs):
        return env.width > 0
    if type(test) is IrTuple:
        return len(test) > 0
    return None


def _rule_cond(c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Selects one of two branches; the test decides whether it varies."""
    cond = _as(node, IrCond, "IrCond")
    settled = _static_truth(cond.test, env)
    if settled is not None:
        return c.law(cond.then_op if settled else cond.else_op, env)
    test = c.law(cond.test, env)
    branches = (c.law(cond.then_op, env), c.law(cond.else_op, env))
    return _join(branches, test.kind != CONST, "IrCond")


def _rule_build(c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Constructs a target from positional arguments."""
    build = _as(node, IrBuild, "IrBuild")
    target = build.target
    rule = c.constructor(target, env)
    combined = _combine(c.positions(build.args, env, "IrBuild"), "IrBuild")
    return CONSTRUCTOR_RULES[str(rule)](combined, f"IrBuild({target.__name__})")


def _rule_collection(c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """A tuple-shaped literal evaluates its elements and retains them."""
    collection = _as(node, IrTuple, "IrTuple")
    laws = tuple(c.attempt(part, env) for part in collection)
    return _retain(_combine(laws, type(node).__name__))


def _rule_text_join(c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Joins evaluated parts as TEXT — ``str`` is not injective on IR values."""
    what = type(node).__name__
    laws: list[SlotLaw] = []
    for child in _as(node, IrNode, what).children():
        if type(child) is IrTuple:
            laws.extend(c.law(part, env) for part in child)
        else:
            laws.append(c.law(child, env))
    return _decode(_combine(laws, what), what)


def _rule_lookup(c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Keys a table on the focus and evaluates the entry it selects."""
    if not isinstance(node, IrMapping):
        raise SlotRefusal("lookup rule applied to a non-mapping operation")
    laws = tuple(c.law(value, env) for value in node.values())
    return _join(laws, env.focus.kind != CONST, type(node).__name__)


def _rule_projection(_c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Reads inside the focus."""
    return _project(env.focus, type(node).__name__)


def _rule_at(c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Rebinds the focus to a raw child, then evaluates the body."""
    inner = _project(env.focus, "IrAt")
    return c.law(_as(node, IrAt, "IrAt").body, Env(env.slot, env.width, inner))


def _rule_each(c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Maps a body over the focus's elements, collecting a tuple."""
    inner = _project(env.focus, "IrEach")
    body = _as(node, IrEach, "IrEach").body
    return _retain(c.law(body, Env(env.slot, env.width, inner)))


def _rule_children(_c: Classifier, _node: IrSelf, env: Env) -> SlotLaw:
    """Collects the focus's dispatched children."""
    return _retain(_project(env.focus, "IrChildren"))


def _rule_rebuild(_c: Classifier, _node: IrSelf, env: Env) -> SlotLaw:
    """Rebuilds the focus around its walked children."""
    return _retain(env.focus)


def _rule_decode(_c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Decodes the focus into a scalar with no declared image bound."""
    return _decode(env.focus, type(node).__name__)


def _rule_codepoint(_c: Classifier, _node: IrSelf, env: Env) -> SlotLaw:
    """Produces a Unicode code point — a declared finite image."""
    return _bounded(env.focus, UNICODE_POINTS)


def _rule_predicate(_c: Classifier, _node: IrSelf, _env: Env) -> SlotLaw:
    """Produces a truth value — a declared image of exactly two values."""
    return finite(TRUTH_VALUES)


def _rule_raise(_c: Classifier, _node: IrSelf, _env: Env) -> SlotLaw:
    """Never returns — the empty image, which carries nothing."""
    return finite(0)


def _rule_merge(_c: Classifier, _node: IrSelf, _env: Env) -> SlotLaw:
    """Folds the whole channel into one record, retaining every argument."""
    return _retain(_combine((IDENT_LAW,), "IrMerge"))


def _rule_yield(_c: Classifier, _node: IrSelf, env: Env) -> SlotLaw:
    """Contributes the focus's DROP-AWARE text view.

    ``const`` only where the analysis has proved that view is a function of the
    span alone — no rule reachable below the focus is dropped. Otherwise it
    refuses: within an equal-span component two families cover the SAME span
    but can drop different subtrees of it, so the text view is a function of
    the derivation, which is exactly what varies. It is NOT enough that the
    component shares a span.
    """
    if env.span_fixed:
        return CONST_LAW
    raise SlotRefusal(
        "YIELD: the drop-aware text view is a function of the derivation, not"
        " of the child's value, unless no rule below the focus is dropped"
    )


def _rule_apply(c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Re-dispatches the focus; the receiving action's law is not visible here."""
    laws = tuple(c.law(part, env) for part in _as(node, IrApply, "IrApply").args)
    combined = _combine(laws, "IrApply")
    if combined.kind == CONST and env.focus.kind == CONST:
        return CONST_LAW
    raise SlotRefusal(
        "IrApply: the dispatched action is chosen at runtime, so its slot law"
        " is not derivable from this expression"
    )


def _rule_action(c: Classifier, node: IrSelf, env: Env) -> SlotLaw:
    """Delegates to the bound body."""
    return c.law(_as(node, IrAction, "IrAction").body, env)


def _rule_ident(_c: Classifier, _node: IrSelf, _env: Env) -> SlotLaw:
    """Contributes the child value itself."""
    return IDENT_LAW


LAW_RULES: dict[str, Callable[[Classifier, IrSelf, Env], SlotLaw]] = {
    "action": _rule_action,
    "apply": _rule_apply,
    "arg": _rule_arg,
    "args": _rule_args,
    "at": _rule_at,
    "build": _rule_build,
    "children": _rule_children,
    "codepoint": _rule_codepoint,
    "collection": _rule_collection,
    "cond": _rule_cond,
    "const": _rule_const,
    "decode": _rule_decode,
    "each": _rule_each,
    "ident": _rule_ident,
    "lookup": _rule_lookup,
    "merge": _rule_merge,
    "pipe": _rule_pipe,
    "predicate": _rule_predicate,
    "projection": _rule_projection,
    "raise": _rule_raise,
    "rebuild": _rule_rebuild,
    "text-join": _rule_text_join,
    "this": _rule_this,
    "yield": _rule_yield,
}
"""The curated law registry a :class:`LawRule` resolves through."""


OPERATION_LAWS = IrTypeMap(
    IrAction(IrAction, LawRule("action")),
    IrAction(IrApply, LawRule("apply")),
    IrAction(IrArg, LawRule("arg")),
    IrAction(IrArgs, LawRule("args")),
    IrAction(IrAt, LawRule("at")),
    IrAction(IrBuild, LawRule("build")),
    IrAction(IrChild, LawRule("projection")),
    IrAction(IrChildren, LawRule("children")),
    IrAction(IrCompare, LawRule("predicate")),
    IrAction(IrConcat, LawRule("text-join")),
    IrAction(IrCond, LawRule("cond")),
    IrAction(IrEach, LawRule("each")),
    IrAction(IrEmit, LawRule("decode")),
    IrAction(IrField, LawRule("projection")),
    IrAction(IrGlyph, LawRule("codepoint")),
    IrAction(IrIndex, LawRule("projection")),
    IrAction(IrIsA, LawRule("predicate")),
    IrAction(IrJoin, LawRule("text-join")),
    IrAction(IrLen, LawRule("decode")),
    IrAction(IrMap, LawRule("lookup")),
    IrAction(IrMerge, LawRule("merge")),
    IrAction(IrNoneType, LawRule("const")),
    IrAction(IrOrd, LawRule("codepoint")),
    IrAction(IrPass, LawRule("const")),
    IrAction(IrPipe, LawRule("pipe")),
    IrAction(IrRadix, LawRule("decode")),
    IrAction(IrRaise, LawRule("raise")),
    IrAction(IrRebuild, LawRule("rebuild")),
    IrAction(IrScalar, LawRule("const")),
    IrAction(IrThis, LawRule("this")),
    IrAction(IrTuple, LawRule("collection")),
    IrAction(IrUnradix, LawRule("decode")),
    IrAction(IrUtf, LawRule("decode")),
    IrAction(IrWalk, LawRule("const")),
    IrAction(Drop, LawRule("const")),
    IrAction(KeepRaw, LawRule("ident")),
    IrAction(KeepReduced, LawRule("ident")),
    IrAction(Yield, LawRule("yield")),
)
"""Operation type → the slot law it declares.

Open by construction: resolution is `IrTypeMap`'s concrete-first ``__mro__``
walk, a new operation adds a row, and a type with no row reaches
:meth:`Classifier.rule`'s raising default. There is deliberately no
``IR_DEFAULT`` entry — a silent catch-all is exactly the failure this table
exists to prevent.

``Yield`` gets no blanket licence. It reads the focus's drop-aware text, which
two families of one equal-span component can spell differently by dropping
different subtrees, so it is ``const`` only where the caller has PROVED that
view is a function of the span alone (``Env.span_fixed`` — nothing reachable
below the focus is dropped) and refuses otherwise.

`LawRule` is itself a string-keyed registry of Python callables, which the
census refuses `foldkit.IrNamed` for being. The asymmetry is deliberate and
worth stating: a law is a DECLARATION about an operation, read by this module;
`IrNamed` is a COMPUTATION whose behaviour the algebra would have to derive.
Declarations may be named; classifications may not.
"""


CONSTRUCTOR_LAWS = IrMap.from_table(
    (
        (IrTuple, LawRule("retaining")),
        (IrMapping, LawRule("retaining")),
        (IrScalar, LawRule("scalar")),
        (IrNoneType, LawRule("constant")),
    )
)
"""Construction target → whether it retains, bounds, or decodes its arguments.

``IrTuple`` covers the whole record spine (``IrSeq``, ``IrNamedTuple`` and
every concrete grammar record derive from it) because a record IS its field
tuple — construction stores each argument at depth one, which is what makes
``grow`` a structural fact rather than a claim about a name. ``IrScalar``
covers the value leaves, whose constructors consume a payload instead of
retaining it.
"""

CONSTRUCTOR_RULES: dict[str, Callable[[SlotLaw, str], SlotLaw]] = {
    "constant": lambda _law, _what: CONST_LAW,
    "retaining": lambda law, _what: _retain(law),
    "scalar": _decode,
}
"""The curated constructor-law registry."""


FUTURE_OPERATIONS = (
    "collection finish (target-supplied)",
    "root finalization (target-supplied)",
    "meaning comparison (target-supplied)",
    "keyed accumulation finish (target-supplied)",
)
"""Product operations that do not exist in ``src`` yet.

They are listed as declaration obligations only. The product compiler must
give each a :data:`CONSTRUCTOR_LAWS`/:data:`OPERATION_LAWS` row and hold it
against :func:`differential_law`; until then they are unaudited by
construction, and :func:`prove_unknown_operation_refuses` shows what they meet
if they arrive undeclared.
"""


# ── real reducer surfaces ─────────────────────────────────────────────────


class BodySite(NamedTuple):
    """One authored operation body and where it was declared."""

    surface: str
    name: str
    body: IrSelf
    width: int


def contributing(arm: IrSequence, dropped: frozenset[str]) -> tuple[int, ...]:
    """The item positions of one arm that reach the argument channel.

    A reference to a rule the reducer DROPS never reaches the channel, so the
    channel index counts only the surviving references before it. The exact
    channel is the binding view's ``fields_of`` (``compile/reduce/fold.py``),
    which additionally splices hoisted groups and quantified repeats; this is
    the same rule minus that splicing, applied to the NORMALIZED grammar so
    both lanes of this module share one coordinate system.
    """
    items = [part for part in arm if isinstance(part, IrItem)]
    return tuple(
        position
        for position, item in enumerate(items)
        if isinstance(item[0], IrRuleRef) and str(item[0]) not in dropped
    )


def dropped_rules(reducer: Reducer) -> frozenset[str]:
    """The rule names this reducer's noise policy contributes nothing for."""
    return frozenset(
        str(key)
        for key, value in reducer.noise.items()
        if isinstance(value, Drop) and isinstance(key, IrRuleRef)
    )


def rule_arity(ast: IrAst, dropped: frozenset[str]) -> dict[str, int]:
    """Each rule's widest arm, in CONTRIBUTING items — the channel-width bound.

    Still an upper bound: hoisted groups and quantified repeats can make the
    real width differ per input. The over-approximation biases toward
    CARRYING, not toward ``const`` — :meth:`Classifier.positions` reports the
    splatted channel as one identity position whatever the slot index — so a
    phantom slot classifies like a real retained one and the census
    over-reports carrying slots rather than hiding them.
    """
    widths: dict[str, int] = {}
    for rule in cyclic._rules(ast):
        widest = max(
            (len(contributing(arm, dropped)) for arm in cyclic._arms(rule)), default=0
        )
        widths[str(rule.name)] = widest
    return widths


def reducer_sites(
    surface: str, reducer: Reducer, arity: dict[str, int]
) -> tuple[BodySite, ...]:
    """Every authored body of one shipped reducer, with its channel width."""
    sites = [
        BodySite(surface, str(key), value, max(_width(value), arity.get(str(key), 0)))
        for key, value in reducer.actions.items()
    ]
    sites.append(BodySite(surface, "<default>", reducer.default, 1))
    return tuple(sites)


def emitter_sites(surface: str, actions: IrTypeMap) -> tuple[BodySite, ...]:
    """Every authored emit action of one flavour."""
    return tuple(
        BodySite(surface, getattr(key, "__name__", str(key)), value, _width(value))
        for key, value in actions.items()
    )


def _width(body: IrSelf) -> int:
    """The channel width one body reads — one past its largest ``IrArg``."""
    largest = -1
    pending: list[IrSelf] = [body]
    while pending:
        node = pending.pop()
        if isinstance(node, IrArg):
            largest = max(largest, int(node) if int(node) >= 0 else -int(node) - 1)
        if isinstance(node, IrArgs):
            largest = max(largest, 0)
        if isinstance(node, IrNode):
            pending.extend(node.children())
        if isinstance(node, IrMapping):
            pending.extend(node.values())
    return largest + 1


class SlotVerdict(NamedTuple):
    """One (surface, rule, slot) classification outcome."""

    surface: str
    name: str
    slot: int
    kind: str
    bound: int
    refusal: str


def classify_site(site: BodySite, classifier: Classifier) -> tuple[SlotVerdict, ...]:
    """Classify every argument slot of one authored body.

    A site whose derived width is zero is still classified at slot 0 — an
    emit action reads no channel at all — and the Env carries width 1 there so
    ``_static_truth``'s premise ("every slot classified exists") holds instead
    of silently inverting.
    """
    out: list[SlotVerdict] = []
    width = max(site.width, 1)
    for slot in range(width):
        env = Env(slot, width, CONST_LAW)
        try:
            law = classifier.law(site.body, env)
        except SlotRefusal as error:
            out.append(SlotVerdict(site.surface, site.name, slot, "", 0, str(error)))
            continue
        out.append(SlotVerdict(site.surface, site.name, slot, law.kind, law.bound, ""))
    return tuple(out)


# ── which slots can sit in a zero-width component ─────────────────────────


class CarrierSlot(NamedTuple):
    """One grammar edge whose child can cover its parent's whole span."""

    parent: str
    child: str
    slot: int
    ref_slot: int
    contributes: bool
    empty_span: bool


def carrier_slots(ast: IrAst, dropped: frozenset[str]) -> tuple[CarrierSlot, ...]:
    """Grammar edges that can participate in an equal-span component.

    The same nullability test `cyclic_meaning.carrier_edges` runs — a child
    that can cover its parent's entire span — re-expressed in CHANNEL
    coordinates: a dropped child never reaches the argument channel, so the
    channel slot counts only the contributing references before it, and a
    dropped child has no slot at all. `carrier_edges`' own ``slot`` numbers
    references INCLUDING dropped ones, which is a different coordinate system;
    :func:`prove_slot_alignment` holds the two against each other.

    ``empty_span`` is true when the carrier child is ITSELF nullable, so the
    parent's whole arm can derive the empty string.
    """
    rules = cyclic._rules(ast)
    empty = cyclic._nullable(rules)
    out: list[CarrierSlot] = []
    for rule in rules:
        for arm in cyclic._arms(rule):
            out.extend(_arm_carriers(str(rule.name), arm, empty, dropped))
    return tuple(out)


def _arm_carriers(
    parent: str, arm: IrSequence, empty: set[str], dropped: frozenset[str]
) -> tuple[CarrierSlot, ...]:
    """One arm's carrier edges, in both coordinate systems."""
    items = [part for part in arm if isinstance(part, IrItem)]
    refs = [
        position
        for position, item in enumerate(items)
        if isinstance(item[0], IrRuleRef)
    ]
    kept = contributing(arm, dropped)
    out: list[CarrierSlot] = []
    for ref_slot, position in enumerate(refs):
        others = [item for index, item in enumerate(items) if index != position]
        if not all(cyclic._item_nullable(other, empty) for other in others):
            continue
        child = str(items[position][0])
        out.append(
            CarrierSlot(
                parent,
                child,
                kept.index(position) if position in kept else -1,
                ref_slot,
                position in kept,
                child in empty,
            )
        )
    return tuple(out)


def reachable_rules(ast: IrAst, start: str) -> frozenset[str]:
    """Every rule reachable from ``start`` through reference items."""
    edges: dict[str, list[str]] = {}
    for rule in cyclic._rules(ast):
        for arm in cyclic._arms(rule):
            for item in arm:
                if isinstance(item, IrItem) and isinstance(item[0], IrRuleRef):
                    edges.setdefault(str(rule.name), []).append(str(item[0]))
    seen = {start}
    pending = [start]
    while pending:
        name = pending.pop()
        for child in edges.get(name, ()):
            if child in seen:
                continue
            seen.add(child)
            pending.append(child)
    return frozenset(seen)


# ── the finite-domain differential ────────────────────────────────────────


PROBES: tuple[IrSelf, ...] = (
    IrStr("a"),
    IrStr("bb"),
    IrStr("7"),
    IrStr("12"),
    IrTuple(IrStr("a")),
    IrTuple(IrStr("a"), IrStr("b")),
    IrInt(3),
)
"""The small finite domain a declared law is held against."""

FILLER = IrStr("z")
"""The fixed value every non-studied channel position carries."""


def value_size(value: IrSelf) -> int:
    """Node count of one evaluated value — the well-founded size measure.

    Both retaining tiers count: a record IS its field tuple, and a mapping
    holds its dyads behind ``children()``. Counting only the tuple tier made
    ``IrBuild(IrMap)`` — a genuinely retaining constructor — read as size one
    and fail its own ``grow`` law.
    """
    total = 1
    pending: list[IrSelf] = [value]
    while pending:
        node = pending.pop()
        if isinstance(node, IrMap):
            total += len(node)
            pending.extend(node.children())
            continue
        if isinstance(node, tuple):
            total += len(node)
            pending.extend(node)
    return total


class DiffResult(NamedTuple):
    """One differential outcome: agreement, contradiction, or not executable."""

    checked: bool
    agrees: bool
    detail: str


def differential_law(
    body: IrSelf, dispatcher: IrSelf, slot: int, width: int, law: SlotLaw
) -> DiffResult:
    """Hold one derived law against direct evaluation on :data:`PROBES`.

    :param body: The authored operation.
    :param dispatcher: The dispatcher the body was declared under.
    :param slot: The channel position the probes occupy.
    :param width: The channel width to build.
    :param law: The law the classifier derived.
    :returns: Whether the law was executable, and whether it held.
    """
    observed: list[tuple[IrSelf, IrSelf]] = []
    refused = ""
    for probe in PROBES:
        channel = tuple(probe if i == slot else FILLER for i in range(max(width, 1)))
        try:
            observed.append((probe, body.eval(dispatcher, FILLER, channel)))
        except (TypeError, ValueError, AttributeError, LookupError) as error:
            refused = repr(error)
        except UnsupportedConstructError as error:
            refused = repr(error)
    if len(observed) < 2:
        return DiffResult(False, True, f"under two executable probes: {refused}")
    return _judge(law, observed)


def _judge(law: SlotLaw, observed: Sequence[tuple[IrSelf, IrSelf]]) -> DiffResult:
    """Compare observed behaviour on the probe domain against one law."""
    results = [value for _probe, value in observed]
    distinct = {repr(value) for value in results}
    if law.kind == CONST:
        return DiffResult(True, len(distinct) == 1, f"distinct={len(distinct)}")
    if law.kind == IDENT:
        same = all(value is probe for probe, value in observed)
        return DiffResult(True, same, f"returns its own argument: {same}")
    if law.kind == FINITE:
        return DiffResult(
            True, len(distinct) <= max(law.bound, 1), f"distinct={len(distinct)}"
        )
    grew = all(value_size(value) > value_size(probe) for probe, value in observed)
    injective = len(distinct) == len(results)
    return DiffResult(True, grew and injective, f"injective={injective} grew={grew}")


DISPATCHERS: dict[str, Reducer] = {
    "gbnf": GBNF_REDUCER,
    "abnf": ABNF_REDUCER,
    "ebnf": EBNF_REDUCER,
    "json": JSON_REDUCER,
}
"""The real dispatcher each reducer surface's bodies run under."""


SURFACE_GRAMMARS: dict[str, IrAst] = {
    "gbnf": GBNF_FLAVOUR.grammar,
    "abnf": ABNF_FLAVOUR.grammar,
    "ebnf": EBNF_FLAVOUR.grammar,
    "json": JSON_GRAMMAR,
}
"""Each reducer surface's own authored self-grammar."""

_CANONICAL: dict[str, IrAst] = {}
_NORMALIZED: dict[str, IrAst] = {}


def _canonical(surface: str) -> IrAst:
    """The surface's canonical grammar — authored rule names, built once."""
    found = _CANONICAL.get(surface)
    if found is None:
        found = canonicalize(SURFACE_GRAMMARS[surface])
        _CANONICAL[surface] = found
    return found


def _normalized(surface: str) -> IrAst:
    """The surface's normalized grammar — classical Earley shape, built once."""
    found = _NORMALIZED.get(surface)
    if found is None:
        found = normalize(_canonical(surface))
        _NORMALIZED[surface] = found
    return found


# ── the witnesses ─────────────────────────────────────────────────────────


_SITES: tuple[BodySite, ...] = ()


def all_sites() -> tuple[BodySite, ...]:
    """Every authored operation body in the shipped surfaces, built once."""
    global _SITES
    if _SITES:
        return _SITES
    sites: list[BodySite] = []
    for surface, reducer in DISPATCHERS.items():
        arity = rule_arity(_normalized(surface), dropped_rules(reducer))
        sites.extend(reducer_sites(surface, reducer, arity))
    for surface, flavour in (
        ("gbnf-emit", GBNF_FLAVOUR),
        ("abnf-emit", ABNF_FLAVOUR),
        ("ebnf-emit", EBNF_FLAVOUR),
    ):
        actions = getattr(flavour, "actions")
        if isinstance(actions, IrTypeMap):
            sites.extend(emitter_sites(surface, actions))
    _SITES = tuple(sites)
    return _SITES


def _census(verdicts: Sequence[SlotVerdict]) -> dict[str, int]:
    """Class counts over one lane's verdicts."""
    out: dict[str, int] = {}
    for verdict in verdicts:
        key = verdict.kind or "refused"
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def _refusal_families(verdicts: Sequence[SlotVerdict]) -> dict[str, int]:
    """Which operation each refusal names, and how often.

    Every refusal message either starts ``<operation>:`` or quotes the
    operation's type name, so both spellings are read rather than the first
    only — a message with no colon must not become a dictionary key.
    """
    out: dict[str, int] = {}
    for verdict in verdicts:
        if not verdict.refusal:
            continue
        head = _refusal_operation(verdict.refusal)
        out[head] = out.get(head, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def _refusal_operation(message: str) -> str:
    """The operation one refusal message names."""
    head, colon, _rest = message.partition(":")
    if colon and " " not in head:
        return head
    quoted = re.search(r"'([^']+)'", message)
    return quoted.group(1) if quoted else head


def prove_real_operation_census() -> tuple[SlotVerdict, ...]:
    """Classify every argument slot of every shipped operation declaration.

    The completion lane — the four shipped reducers — is what the product
    schedules and where a law is mandatory. The emit lane is reported beside
    it and deliberately NOT declared: those families build layout documents
    and flavour spellings, no completion runs through them, and declaring a
    law nothing differentials would be exactly the unproved claim this module
    exists to refuse.
    """
    counts = Counts()
    classifier = Classifier(OPERATION_LAWS, CONSTRUCTOR_LAWS, counts)
    verdicts: list[SlotVerdict] = []
    started = time.process_time()
    for site in all_sites():
        verdicts.extend(classify_site(site, classifier))
    elapsed = time.process_time() - started
    completion = [v for v in verdicts if v.surface in DISPATCHERS]
    emit = [v for v in verdicts if v.surface not in DISPATCHERS]
    print(
        "operation-census",
        "lane=completion",
        f"sites={sum(1 for s in all_sites() if s.surface in DISPATCHERS)}",
        f"slots={len(completion)}",
        f"expressions={counts.expressions}",
        f"resolutions={counts.resolutions}",
        f"classes={_census(completion)}",
        f"refusals_by_operation={_refusal_families(completion)}",
        f"cpu={elapsed:.6f}",
        sep="\t",
    )
    print(
        "operation-census",
        "lane=emit-unscheduled",
        f"slots={len(emit)}",
        f"classes={_census(emit)}",
        f"undeclared_families={_refusal_families(emit)}",
        "no completion runs through these; each needs a row and a"
        " differential before a target may emit through it",
        sep="\t",
    )
    return tuple(verdicts)


def prove_category_coverage(verdicts: tuple[SlotVerdict, ...]) -> None:
    """Every operation category the design schedules reaches a class."""
    index = {(v.surface, v.name, v.slot): v for v in verdicts}
    rows = (
        ("record construction", ("gbnf", "rule", 0), GROW),
        ("record construction", ("gbnf", "item", 1), GROW),
        ("sequence accumulation", ("json", "array", 0), GROW),
        ("keyed accumulation", ("json", "object", 0), GROW),
        ("joint retain/ignore", ("gbnf", "group", 0), IDENT),
        ("joint retain/ignore", ("gbnf", "group", 1), CONST),
        ("joint retain/ignore", ("abnf", "option", 0), GROW),
        ("joint retain/ignore", ("abnf", "option", 2), CONST),
        ("validation refusal", ("json", "frac", 0), FINITE),
        ("validation refusal", ("abnf", "prose", 0), FINITE),
    )
    refused = index.get(("json", "<default>", 0))
    assert refused is not None and refused.refusal, refused
    print(
        "category",
        "default action (YIELD)",
        "site=json:<default>",
        "slot=0",
        "class=refused-without-a-span-proof",
        f"refusal={refused.refusal}",
        sep="\t",
    )
    for label, key, expected in rows:
        found = index.get(key)
        assert found is not None, (label, key)
        assert found.kind == expected, (label, key, found)
        print(
            "category",
            label,
            f"site={key[0]}:{key[1]}",
            f"slot={key[2]}",
            f"class={found.kind}",
            f"bound={found.bound}",
            sep="\t",
        )
    _report_category_execution(rows)
    scalars = [v for v in verdicts if v.refusal and "decodes" in v.refusal]
    print(
        "category",
        "scalar decode",
        f"slots_with_no_law={len(scalars)}",
        "a scalar decode over a slot-carrying value has no const/ident/finite/"
        "grow law and refuses at binding",
        sep="\t",
    )


def _report_category_execution(
    rows: Sequence[tuple[str, tuple[str, str, int], str]],
) -> None:
    """Say, per showcased category, whether the differential could execute it."""
    classifier = Classifier(OPERATION_LAWS, CONSTRUCTOR_LAWS)
    index = {(site.surface, site.name): site for site in all_sites()}
    for label, key, _expected in rows:
        site = index[(key[0], key[1])]
        dispatcher = DISPATCHERS[key[0]]
        law = classifier.law(site.body, Env(key[2], max(site.width, 1), CONST_LAW))
        result = differential_law(site.body, dispatcher, key[2], site.width, law)
        print(
            "category-execution",
            label,
            f"site={key[0]}:{key[1]}[{key[2]}]",
            f"executed_on_probes={result.checked}",
            f"agrees={result.agrees}",
            f"detail={result.detail}",
            sep="\t",
        )


RETAINING_PROBES: tuple[
    tuple[str, IrSelf, int, tuple[tuple[IrSelf, ...], ...]], ...
] = (
    (
        "IrBuild(IrTuple)",
        IrBuild(IrTuple),
        0,
        tuple((probe,) for probe in PROBES),
    ),
    (
        "IrBuild(IrRule)",
        IrBuild(IrRule),
        0,
        tuple(
            (
                IrStr(name),
                IrAlternation(IrSequence(IrItem(IrLiteral("x")))),
            )
            for name in ("one", "two", "three")
        ),
    ),
    (
        "IrBuild(IrMap)",
        IrBuild(IrMap),
        1,
        tuple(
            (IrTuple(IrStr("k"), IrStr("v")), IrTuple(IrStr("j"), IrStr(value)))
            for value in ("a", "bb", "ccc")
        ),
    ),
    (
        "IrMerge()",
        IrMerge(),
        0,
        tuple(
            (
                IrRule(IrStr("r"), IrAlternation(IrSequence(IrItem(IrLiteral(text))))),
                IrRule(IrStr("s"), IrAlternation(IrSequence(IrItem(IrLiteral("z"))))),
            )
            for text in ("a", "bb", "ccc")
        ),
    ),
)
"""Per-operation probe channels for the retaining constructors.

The seven-value `PROBES` domain cannot execute these — a record constructor
raises on a channel of the wrong shape — so the operations the census calls
``grow`` on record construction, keyed accumulation and merge would otherwise
have a class and no measurement. Each row supplies a channel the operation
actually accepts and varies exactly one position.
"""


def prove_retaining_constructors() -> None:
    """Differential the retaining constructors on channels they accept."""
    classifier = Classifier(OPERATION_LAWS, CONSTRUCTOR_LAWS)
    for label, body, slot, channels in RETAINING_PROBES:
        law = classifier.law(body, Env(slot, len(channels[0]), CONST_LAW))
        observed = [
            (channel[slot], body.eval(GBNF_REDUCER, IrStr(""), channel))
            for channel in channels
        ]
        result = _judge(law, observed)
        assert law.kind == GROW, (label, law)
        assert result.checked and result.agrees, (label, result)
        print(
            "retaining-constructor",
            label,
            f"slot={slot}",
            f"class={law.kind}",
            f"channels={len(channels)}",
            f"agrees={result.agrees}",
            f"detail={result.detail}",
            sep="\t",
        )
    _prove_partial_operation()


def _prove_partial_operation() -> None:
    """A PARTIAL operation raises instead of returning a second meaning.

    ``IrBuild(IrMap)`` refuses a repeated key. The algebra has no ``partial``
    class and does not need one: where the operation raises it produces no
    value at all, which is the ``finite(0)`` bottom :func:`_rule_raise`
    already names, and an absent value cannot make a requested root mean two
    things. The law therefore holds on the operation's DOMAIN, which is where
    a meaning exists to compare.
    """
    duplicate = (IrTuple(IrStr("k"), IrStr("v")), IrTuple(IrStr("k"), IrStr("w")))
    try:
        IrBuild(IrMap).eval(GBNF_REDUCER, IrStr(""), duplicate)
    except UnsupportedConstructError as error:
        message = str(error)
    else:
        raise AssertionError("a duplicate map key was accepted")
    print(
        "partial-operation",
        "IrBuild(IrMap)",
        f"refuses={message}",
        f"empty_image_class={FINITE} bound=0",
        "a family whose operation raises contributes no value, so partiality"
        " cannot create a second requested-root meaning; the law is stated"
        " over the operation's domain",
        sep="\t",
    )


class YieldView(IrStr):
    """A drop-aware text view of one zero-width span — what `YIELD` reads."""


def prove_contribution_policies() -> None:
    """The four contribution policies decide WHETHER a slot exists, and what
    it carries — a lane the channel algebra sits on top of, checked directly.

    A policy is not a slot-indexed operation: it runs on the child, before the
    channel exists. The claims are executable, so they are executed rather than
    declared: ``DROP`` yields no slot at all, ``KEEP_RAW``/``KEEP_REDUCED``
    yield exactly one slot carrying that child's contribution (the algebra's
    ``ident``), and ``YIELD`` yields the drop-aware text of the focus.

    What the last row EXECUTES is span sensitivity: three different views give
    three different texts. What it does NOT execute is the sharper claim —
    that two families of ONE equal-span component can drop different subtrees
    and so spell that one span two ways — because building a real drop-aware
    view for two families needs the compile pipeline's fold. That claim is the
    REASON :func:`_rule_yield` refuses by default, and refusing is the
    conservative direction, so the unexecuted premise can only over-refuse.
    Section 4 of the report carries it as an obligation, not a result.
    """
    reducer = JSON_REDUCER
    node = IrStr("child")
    dropped = reducer.noise[IrRuleRef("ws")].eval(reducer, node, ())
    kept = KeepRaw().eval(reducer, node, ())
    reduced = reducer.noise.resolve(IrRuleRef("value")).eval(reducer, node, ())
    empty_span = Yield().eval(reducer, YieldView(""), ())
    wider = Yield().eval(reducer, YieldView("xy"), ())
    partial = Yield().eval(reducer, YieldView("x"), ())
    assert len(dropped) == 0, dropped
    assert len(kept) == 1 and kept[0] is node, kept
    assert len(reduced) == 1, reduced
    assert empty_span == IrStr(""), empty_span
    assert wider != empty_span and wider != partial, (wider, partial)
    print(
        "contribution-policies",
        f"DROP_slots={len(dropped)} class={CONST}",
        f"KEEP_RAW_slots={len(kept)} carries_child={kept[0] is node} class={IDENT}",
        f"KEEP_REDUCED_slots={len(reduced)} class={IDENT}",
        f"YIELD_on_empty_span={empty_span!r}",
        f"YIELD_on_one_char={partial!r}",
        f"YIELD_on_a_wider_span={wider!r}",
        f"YIELD_is_span_sensitive={len({empty_span, partial, wider}) == 3}",
        "so YIELD carries no blanket const licence: it is const in a child's"
        " VALUE only where the caller proved the drop-aware text is a function"
        " of the span alone, and refuses otherwise",
        sep="\t",
    )


def prove_zero_width_slots() -> None:
    """Which shipped rule slots can sit in an equal-span component at all.

    Each edge is classified against the parent's own body under the parent's
    real span situation: ``span_fixed`` is true only when no rule reachable
    below the parent is dropped, which is what licences ``YIELD`` — the
    reducer default for every rule with no explicit action.
    """
    for surface, reducer in DISPATCHERS.items():
        ast = _normalized(surface)
        dropped = dropped_rules(reducer)
        edges = carrier_slots(ast, dropped)
        classifier = Classifier(OPERATION_LAWS, CONSTRUCTOR_LAWS)
        classes: dict[str, int] = {}
        refusals: list[str] = []
        empty_capable = 0
        for edge in edges:
            if not edge.contributes:
                classes[CONST] = classes.get(CONST, 0) + 1
                continue
            empty_capable += 1 if edge.empty_span else 0
            law = _carrier_law(reducer, ast, dropped, edge, classifier, refusals)
            if law is None:
                continue
            classes[law.kind] = classes.get(law.kind, 0) + 1
        print(
            "zero-width-slots",
            surface,
            f"rules={len(cyclic._rules(ast))}",
            f"carrier_edges={len(edges)}",
            f"dropped_child_edges={sum(1 for e in edges if not e.contributes)}",
            f"empty_span_capable={empty_capable}",
            f"classes={dict(sorted(classes.items()))}",
            f"refused={len(refusals)}",
            f"refusals_by_operation={_message_families(refusals)}",
            f"first_refusal={refusals[0] if refusals else ''}",
            sep="\t",
        )


def _carrier_law(
    reducer: Reducer,
    ast: IrAst,
    dropped: frozenset[str],
    edge: CarrierSlot,
    classifier: Classifier,
    refusals: list[str],
) -> SlotLaw | None:
    """One carrier edge's class, or ``None`` when it refuses."""
    body = reducer.actions.get(IrRuleRef(edge.parent))
    if body is None:
        body = reducer.default
    fixed = not (reachable_rules(ast, edge.parent) & dropped)
    env = Env(edge.slot, max(_width(body), edge.slot + 1), CONST_LAW, fixed)
    try:
        return classifier.law(body, env)
    except SlotRefusal as error:
        refusals.append(f"{edge.parent}[{edge.slot}]: {error}")
        return None


def _message_families(refusals: Sequence[str]) -> dict[str, int]:
    """Which operation each carrier refusal names, and how often."""
    out: dict[str, int] = {}
    for message in refusals:
        _site, _colon, rest = message.partition(": ")
        head = _refusal_operation(rest)
        out[head] = out.get(head, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def prove_slot_alignment() -> None:
    """The channel and reference coordinate systems, held against each other.

    `cyclic_meaning.carrier_edges` numbers a slot among ALL reference items;
    the channel numbers only the contributing ones. Reporting one as the other
    is the failure this row exists to catch, so both are computed and the
    disagreements are named rather than assumed absent.
    """
    for surface, reducer in DISPATCHERS.items():
        ast = _normalized(surface)
        dropped = dropped_rules(reducer)
        mine = carrier_slots(ast, dropped)
        theirs = cyclic.carrier_edges(ast)
        pairs = sorted((e.parent, e.child, e.ref_slot) for e in mine)
        others = sorted((e.parent, e.child, e.slot) for e in theirs)
        misaligned = [
            f"{e.parent}->{e.child} ref_slot={e.ref_slot} channel_slot={e.slot}"
            for e in mine
            if e.contributes and e.slot != e.ref_slot
        ]
        assert pairs == others, (surface, len(pairs), len(others))
        print(
            "slot-alignment",
            surface,
            f"edges={len(mine)}",
            f"reference_coordinates_match_cyclic_meaning={pairs == others}",
            f"channel_differs_from_reference={len(misaligned)}",
            f"examples={misaligned[:2]}",
            sep="\t",
        )


def prove_differential() -> None:
    """Hold every derived law against direct evaluation on a finite domain."""
    classifier = Classifier(OPERATION_LAWS, CONSTRUCTOR_LAWS)
    checked = agreed = skipped = classified = 0
    for site in all_sites():
        dispatcher = DISPATCHERS.get(site.surface)
        if dispatcher is None:
            continue
        for verdict in classify_site(site, classifier):
            if verdict.refusal:
                continue
            classified += 1
            result = differential_law(
                site.body,
                dispatcher,
                verdict.slot,
                site.width,
                SlotLaw(verdict.kind, verdict.bound),
            )
            if not result.checked:
                skipped += 1
                continue
            checked += 1
            agreed += 1 if result.agrees else 0
            assert result.agrees, (site.surface, site.name, verdict, result)
    print(
        "differential",
        f"classified_slots={classified}",
        f"executable_on_probes={checked}",
        f"agreed={agreed}",
        f"not_executable={skipped}",
        "every executable row agrees with direct evaluation",
        sep="\t",
    )


MISDECLARATIONS = (
    ("IrJoin declared retaining", IrJoin, LawRule("collection")),
    ("IrArg declared constant", IrArg, LawRule("const")),
    ("IrArgs declared constant", IrArgs, LawRule("const")),
    ("IrPipe declared focus-preserving", IrPipe, LawRule("this")),
    ("IrUnradix declared identity", IrUnradix, LawRule("ident")),
)
"""Deliberately wrong rows the differential must catch."""


def _misdeclared(target: type, rule: LawRule) -> IrTypeMap:
    """The real table with exactly one row replaced by a wrong claim."""
    rows = [
        IrAction(key, rule if key is target else value)
        for key, value in OPERATION_LAWS.items()
    ]
    return IrTypeMap(*rows)


def prove_misdeclaration_caught() -> None:
    """A wrong law is caught by the checker or by a binding refusal."""
    for label, target, rule in MISDECLARATIONS:
        table = _misdeclared(target, rule)
        classifier = Classifier(table, CONSTRUCTOR_LAWS)
        caught = ""
        for site in all_sites():
            dispatcher = DISPATCHERS.get(site.surface)
            if dispatcher is None or caught:
                continue
            caught = _first_contradiction(site, dispatcher, classifier)
        assert caught, label
        print("misdeclaration", label, f"caught_at={caught}", sep="\t")
    _prove_misdeclared_constructor()


def _first_contradiction(
    site: BodySite, dispatcher: Reducer, classifier: Classifier
) -> str:
    """The first probe contradiction one body produces, or the empty string."""
    for verdict in classify_site(site, classifier):
        if verdict.refusal:
            continue
        result = differential_law(
            site.body,
            dispatcher,
            verdict.slot,
            site.width,
            SlotLaw(verdict.kind, verdict.bound),
        )
        if result.checked and not result.agrees:
            return f"{site.surface}:{site.name}[{verdict.slot}] {result.detail}"
    return ""


def _prove_misdeclared_constructor() -> None:
    """A scalar target wrongly declared retaining is caught on the probes."""
    table = IrMap.from_table(
        (
            (IrTuple, LawRule("retaining")),
            (IrMapping, LawRule("retaining")),
            (IrScalar, LawRule("retaining")),
            (IrNoneType, LawRule("constant")),
        )
    )
    classifier = Classifier(OPERATION_LAWS, table)
    body = IrBuild(IrChr, IrTuple(IrArg(0)))
    law = classifier.law(body, Env(0, 1, CONST_LAW))
    assert law.kind == GROW, law
    result = differential_law(body, GBNF_REDUCER, 0, 1, law)
    assert result.checked and not result.agrees, result
    print(
        "misdeclaration",
        "IrScalar target declared retaining",
        f"caught_at=IrBuild(IrChr)[0] {result.detail}",
        sep="\t",
    )


class FutureOperation(IrNode[IrSelf, IrSelf]):
    """A product operation the compiler has not declared a law for yet."""

    __slots__ = ()

    def eval(self, _d: IrSelf, _n: IrSelf, nc: Sequence[IrSelf], /) -> IrSelf:
        """Return the channel unchanged — the shape a collection finish has."""
        return IrTuple(*nc)


def prove_unknown_operation_refuses() -> None:
    """An operation with no declared law reaches the raising default."""
    classifier = Classifier(OPERATION_LAWS, CONSTRUCTOR_LAWS)
    try:
        classifier.law(FutureOperation(), Env(0, 1, CONST_LAW))
    except SlotRefusal as error:
        message = str(error)
    else:
        raise AssertionError("an undeclared operation was not refused")
    try:
        classifier.law(IrNamed("first_rest"), Env(0, 2, CONST_LAW))
    except SlotRefusal as named_error:
        named = str(named_error)
    else:
        raise AssertionError("the foldkit named ctor was not refused")
    try:
        classifier.law(
            IrBuild(FutureOperation, IrTuple(IrArg(0))), Env(0, 1, CONST_LAW)
        )
    except SlotRefusal as target_error:
        target = str(target_error)
    else:
        raise AssertionError("an undeclared construction target was not refused")
    print("unknown-operation", f"body={message}", sep="\t")
    print("unknown-operation", f"foldkit={named}", sep="\t")
    print("unknown-operation", f"target={target}", sep="\t")
    print(
        "future-operations",
        f"undeclared_by_construction={list(FUTURE_OPERATIONS)}",
        "these do not exist in src today; each must add a law row and pass"
        " differential_law before the product compiler may schedule it",
        sep="\t",
    )


def _edge_class(
    classifier: Classifier, bodies: Mapping[str, IrSelf], edge: cyclic.RuleEdge
) -> str:
    """The class one real operation gives one grammar edge's slot."""
    body = bodies.get(edge.parent, IrArg(0))
    width = max(_width(body), edge.slot + 1)
    return classifier.law(body, Env(edge.slot, width, CONST_LAW)).kind


def binding_verdict(
    grammar: str, bodies: Mapping[str, IrSelf]
) -> cyclic.GrammarVerdict:
    """`cyclic_meaning.grammar_verdict`, driven by REAL operation declarations.

    Same graph, same component decision, same reachability lanes — only the
    per-edge class comes from :func:`Classifier.law` over an authored IR body
    instead of the toy policy table.
    """
    ast = normalize(canonical_grammar(grammar, GBNF_FLAVOUR))
    start = "".join(str(part) for part in ast[1])
    names = tuple(str(rule.name) for rule in cyclic._rules(ast))
    edges = cyclic.carrier_edges(ast)
    flow = cyclic.child_edges(ast)
    classifier = Classifier(OPERATION_LAWS, CONSTRUCTOR_LAWS)
    classified = {edge: _edge_class(classifier, bodies, edge) for edge in edges + flow}
    adjacency: dict[str, tuple[str, ...]] = {name: () for name in names}
    for edge in edges:
        adjacency[edge.parent] = adjacency[edge.parent] + (edge.child,)
    visible = cyclic._rule_reach(names, flow, classified, start, frozenset({CONST}))
    injective = cyclic._rule_reach(
        names, flow, classified, start, frozenset({CONST, FINITE})
    )
    groups = cyclic.components(names, adjacency)
    kinds = tuple(
        cyclic._rule_component_kind(group, edges, classified, visible, injective)
        for group in groups
    )
    refused = [
        group[0]
        for group, kind in zip(groups, kinds)
        if kind == cyclic.CYCLIC_UNREPRESENTABLE
    ]
    return cyclic.GrammarVerdict(
        bool(refused),
        tuple(groups),
        kinds,
        "binding refuses: " + ", ".join(sorted(refused))
        if refused
        else "binding accepts",
    )


REAL_BODY_WITNESSES = (
    (
        "real-grow-injective-root",
        cyclic.UNIT,
        {"a": IrBuild(IrTuple)},
        {"root": "pass", "a": "", "b": "pass"},
    ),
    (
        "real-identity-cycle",
        cyclic.UNIT,
        {},
        {"root": "pass", "a": "pass", "b": "pass"},
    ),
    (
        "real-dropping-root",
        cyclic.UNIT,
        {"root": IrStr("fixed"), "a": IrBuild(IrTuple)},
        {"root": "drop", "a": "", "b": "pass"},
    ),
    (
        "real-bounded-consumer",
        cyclic.RING,
        {
            "root": IrCompare(IrArg(0), IrOp("=="), IrStr("x")),
            "s": IrBuild(IrTuple),
            "t": IrArg(0),
        },
        {"root": "atmost1", "s": "", "t": "pass"},
    ),
)
"""Witnesses where a REAL operation body stands in for each toy policy."""


def prove_cyclic_parity() -> None:
    """The real-operation classes decide the cyclic witnesses identically."""
    for name, grammar, bodies, policies in REAL_BODY_WITNESSES:
        real = binding_verdict(grammar, bodies)
        toy = cyclic.grammar_verdict(grammar, policies)
        assert real.kinds == toy.kinds, (name, real.kinds, toy.kinds)
        assert real.refused == toy.refused, (name, real, toy)
        print(
            "cyclic-parity",
            name,
            f"kinds={real.kinds}",
            f"refused={real.refused}",
            f"matches_toy_policy_verdict={real.kinds == toy.kinds}",
            sep="\t",
        )


def prove_algebra_agreement() -> None:
    """The four class names ARE the ones `cyclic_meaning` decides components on."""
    assert (CONST, IDENT, FINITE, GROW) == (
        cyclic.CONST,
        cyclic.IDENT,
        cyclic.FINITE,
        cyclic.GROW,
    )
    policies = {"root": "atmost2", "s": "ring", "t": "pass"}
    for policy, slot in (("drop", 0), ("pass", 0), ("pass", 1), ("ring", 0), ("", 0)):
        toy = cyclic.slot_class(policy, slot)
        assert toy in (CONST, IDENT, FINITE, GROW), (policy, slot)
    verdict = cyclic.grammar_verdict(cyclic.RING, policies)
    print(
        "algebra-agreement",
        f"classes={(CONST, IDENT, FINITE, GROW)}",
        f"cyclic_binding_kinds={verdict.kinds}",
        "the real-operation classifier emits exactly the classes the cyclic"
        " component decision consumes",
        sep="\t",
    )


def prove_bounds() -> None:
    """State the cost in operations, slots, expression nodes, and SCC size."""
    counts = Counts()
    classifier = Classifier(OPERATION_LAWS, CONSTRUCTOR_LAWS, counts)
    sites = all_sites()
    started = time.process_time()
    slots = 0
    for site in sites:
        slots += len(classify_site(site, classifier))
    elapsed = time.process_time() - started
    edges = carrier_slots(_normalized("gbnf"), dropped_rules(GBNF_REDUCER))
    print(
        "bounds",
        f"operations={len(sites)}",
        f"slots={slots}",
        f"expression_visits={counts.expressions}",
        f"table_resolutions={counts.resolutions}",
        "classification is one pass per (operation, slot) over the body tree:"
        " O(sum over operations of width x |body|) time and O(depth) stack;"
        " the component decision it feeds is O(V + E) over the chart's"
        " completed nodes and family edges",
        f"gbnf_carrier_edges={len(edges)}",
        f"cpu={elapsed:.6f}",
        sep="\t",
    )


def main() -> None:
    """Classify the real operations, differential them, and state the bounds."""
    verdicts = prove_real_operation_census()
    prove_category_coverage(verdicts)
    prove_contribution_policies()
    prove_slot_alignment()
    prove_zero_width_slots()
    prove_differential()
    prove_retaining_constructors()
    prove_misdeclaration_caught()
    prove_unknown_operation_refuses()
    prove_cyclic_parity()
    prove_algebra_agreement()
    prove_bounds()
    print(
        "invariant",
        "every shipped operation declaration reaches exactly one of const,"
        " ident, declared-finite, proper-subvalue-grow, or a binding refusal"
        " naming the operation and slot; the classification composes declared"
        " per-type rows through lexic's own MRO dispatch, so it never reads a"
        " name, samples a value, keys on a callable, or runs a closed"
        " isinstance cascade, and an undeclared operation cannot be silently"
        " admitted",
        sep="\t",
    )


if __name__ == "__main__":
    main()
