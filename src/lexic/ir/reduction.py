"""Declarative reduction data — contribution policies, signatures, schemas.

A :class:`Reducer` says what a grammar parse is FOR: rule refs map to IR
actions, while child and literal policies say which values reach an action's
argument channel. The compile layer derives a pruned model artefact from them
and supplies the drop-aware text view used by :data:`YIELD`.

A :class:`SemanticSignature` says what those actions MEAN. It is a boundary of
named events over :class:`SemanticSort` values and names no rule at all, so
every formulation of a language — native, GBNF, ABNF, EBNF — presents one
boundary; each formulation's reducer states its own symbol→event bindings in
:attr:`Reducer.events`, which is the only place a rule name appears.

A :class:`TargetSchema` is the layer above: a finite state machine over one
signature's events, saying which event shapes form a supported product, where
a decoded discriminator routes, what is checked, and what a refusal records.

Everything here is grammar-side IR data, independent of any parser. Nothing
here executes a parse, lowers a program, or declares a specific format.
"""

from __future__ import annotations

from collections.abc import Sequence

from lexic.exceptions import UnsupportedConstructError
from lexic.ir.action.mapping import IR_DEFAULT, IrMap
from lexic.ir.action.walk import IrDispatch
from lexic.ir.grammar.nodes import IrRuleRef
from lexic.ir.spine.meta import IrSingleton
from lexic.ir.spine.records import IrNamedTuple, IrSeq, IrTuple
from lexic.ir.spine.scalars import IrStr
from lexic.ir.spine.spine import IrLeaf, IrNone, IrSelf

# ── Contribution policies ─────────────────────────────────────────────


class Drop(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute nothing: a non-semantic child or inline terminal."""

    def eval(self, _d: IrSelf, _n: IrSelf, _nc: Sequence[IrSelf], /) -> IrTuple:
        """Return the empty argument channel."""
        return IrTuple()


class KeepRaw(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute the input node unchanged."""

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrTuple:
        """Return ``n`` as a one-element argument channel."""
        return IrTuple(n)


class KeepReduced(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute the dispatcher's interpretation of the input node."""

    def eval(self, d: IrSelf, n: IrSelf, nc: Sequence[IrSelf], /) -> IrTuple:
        """Dispatch ``n`` and return its value as a one-element channel."""
        return IrTuple(d.eval(d, n, nc))


class Yield(IrLeaf[IrSelf, IrSelf], metaclass=IrSingleton):
    """Contribute the source-text view supplied by the caller.

    ``ReduceFold`` wraps model nodes in a view whose ``str`` is the emission
    stream minus dropped subtrees. Probe and notation callers likewise supply
    their own text-bearing IR node, so the policy remains parser-independent.
    """

    def eval(self, _d: IrSelf, n: IrSelf, _nc: Sequence[IrSelf], /) -> IrStr:
        """Return the caller-provided text view of ``n``."""
        return IrStr(str(n))


DROP = Drop()
"""Contribute nothing."""
KEEP_RAW = KeepRaw()
"""Contribute the node unchanged."""
KEEP_REDUCED = KeepReduced()
"""Contribute the node's interpreted value."""
YIELD = Yield()
"""Contribute the node's source-text view."""


# ── Semantic sorts ────────────────────────────────────────────────────


class SemanticSort(IrStr):
    """What kind of value an event produces — the node IS the sort's name.

    No enum: the sort is its own string, keyed directly into whatever table a
    consumer builds over it. That table is open — a signature may name a sort
    this module does not, and the consumer's own miss is what refuses it — so
    a new sort costs a constant here and an entry there, never a cascade.
    """


SORT_ABSENCE = SemanticSort("absence")
"""A decoded nothing — the sort of a literal absent value."""
SORT_TRUTH = SemanticSort("truth")
"""A decoded truth value."""
SORT_INTEGER = SemanticSort("integer")
"""A decoded exact integer."""
SORT_FRACTION = SemanticSort("fraction")
"""A decoded number that is not an integer."""
SORT_TEXT = SemanticSort("text")
"""Decoded text — escapes resolved, delimiters gone."""
SORT_ITEM = SemanticSort("item")
"""One value contributed to the ordered collection enclosing it."""
SORT_SEQUENCE = SemanticSort("sequence")
"""A finished ordered collection."""
SORT_ENTRY = SemanticSort("entry")
"""One decoded key and value contributed to the mapping enclosing them."""
SORT_MAPPING = SemanticSort("mapping")
"""A finished keyed collection."""
SORT_COMPLETION = SemanticSort("completion")
"""The whole document's value — the event a root finalizer waits for."""


class SemanticSignature(IrNamedTuple[IrStr, IrMap]):
    """A reducer's semantic boundary: its events, by name, with their sorts.

    Deliberately free of rule names, generated classes and target vocabulary.
    That is what lets one signature object stand for every formulation of a
    language: what differs between formulations is which SYMBOL raises each
    event, and that belongs to the formulation's reducer
    (:attr:`Reducer.events`), not to the boundary they share.

    :ivar name: What this boundary is called. A schema names the same string
        to say which boundary it was authored over.
    :ivar events: Event name → the :class:`SemanticSort` it produces.
    """

    name: IrStr
    events: IrMap[IrStr, SemanticSort]

    def sort(self, event: IrStr) -> SemanticSort:
        """The sort of one declared event.

        :param event: The event name.
        :returns: The sort that event produces.
        :raises UnsupportedConstructError: On an event this signature does
            not declare — never a silent absence, which would let a target
            bind against a boundary that cannot supply it.
        """
        found = self.events.get(event)
        if found is None:
            raise UnsupportedConstructError(
                f"semantic signature {str(self.name)!r} declares no event "
                f"{str(event)!r}"
            )
        return found


# ── The reducer ───────────────────────────────────────────────────────


class Reducer(IrDispatch):
    """Rule-action declarations, contribution policies, and semantic bindings.

    :ivar noise: Per-rule child-contribution policy.
    :ivar literal: The contribution policy inline terminals take.
    :ivar signature: The :class:`SemanticSignature` this reducer implements,
        or :data:`~lexic.ir.spine.spine.IrNone` when it declares none — a
        reducer without one still produces its own codomain, but no target
        schema can claim to understand it.
    :ivar events: Rule ref → the name of the signature event that symbol
        raises. This is the one place a semantic role meets a grammar
        spelling, and it is authored beside the actions it describes; a role
        is never inferred from what a rule happens to be called.
    """

    noise: IrMap = IrMap(IrTuple(IR_DEFAULT, KEEP_REDUCED))
    literal: IrSelf = KEEP_RAW
    signature: IrSelf = IrNone
    events: IrMap[IrRuleRef, IrStr] = IrMap()

    def body(self, symbol: IrSelf) -> IrSelf:
        """Return the explicit action for ``symbol``, or the default action."""
        found = self.actions.get(symbol)
        return self.default if found is None else found


# ── Schema routes ─────────────────────────────────────────────────────


class SchemaRoute(IrNamedTuple[IrStr]):
    """Where a decoded discriminator sends the schema — the route family's base.

    :ivar state: The schema state the routed value is read in.
    """

    state: IrStr

    def accepts(self, key: IrStr) -> bool:
        """Whether this route claims ``key``.

        :param key: The decoded discriminator.
        :returns: ``True`` when the route claims it.
        :raises UnsupportedConstructError: Always, on the base — a route
            family member that does not say which keys it claims cannot be
            reached by a silent fallback.
        """
        del key
        raise UnsupportedConstructError(
            f"{type(self).__name__} does not say which decoded keys it accepts"
        )


class KnownRoute(SchemaRoute):
    """One exact decoded spelling the schema consumes.

    :ivar key: The decoded key, escapes already resolved — so every spelling
        that decodes to it reaches this one route.
    :ivar state: The schema state its value is read in.
    """

    key: IrStr
    state: IrStr

    def accepts(self, key: IrStr) -> bool:
        """Whether ``key`` decodes to exactly this route's key."""
        return self.key == key


class ExtensionRoute(SchemaRoute):
    """Every key the schema does not consume, taken together.

    Which state it names is the whole contract for an unknown key: a
    recognition-only state reads it and keeps nothing, a poisoned state
    refuses it. Last among a state's routes, since it claims what is left.

    :ivar state: The schema state an unconsumed key's value is read in.
    """

    state: IrStr

    def accepts(self, key: IrStr) -> bool:
        """Claim every key — the routes ahead of this one had first refusal."""
        del key
        return True


class EntryRoute(SchemaRoute):
    """A mapping whose keys are DATA — every key routes to one value state.

    The open case beside :class:`KnownRoute`'s closed one: a vocabulary has no
    key the schema could enumerate, and the decoded key is retained as part of
    the entry rather than spent choosing a route.

    :ivar state: The schema state every entry's value is read in.
    """

    state: IrStr

    def accepts(self, key: IrStr) -> bool:
        """Claim every key — a dynamic mapping classifies none of them."""
        del key
        return True


class SchemaRoutes(IrSeq[SchemaRoute]):
    """One state's routes, in declaration order — the catch-all comes last."""


# ── Validation declarations ───────────────────────────────────────────


class SchemaCheck(IrNamedTuple[IrStr, IrStr, IrStr]):
    """One declared semantic check and the verdict its failure records.

    The check itself is named, not supplied: a target declares WHICH check
    runs and what a failure says, and the compiled product owns the operation
    that runs it. A check that arrived as a callable would be a target
    callback in a completion path, which the product ABI does not admit.

    :ivar check: Which declared check runs here.
    :ivar verdict: The :class:`~lexic.exceptions.SemanticVerdict` sort a
        failure records.
    :ivar words: What that failure says.
    """

    check: IrStr
    verdict: IrStr
    words: IrStr


class SchemaChecks(IrSeq[SchemaCheck]):
    """One state's checks, in the order their verdicts are ordered."""


class DuplicatePolicy(IrStr):
    """What a repeated decoded key means at one mapping level.

    Declared per level rather than inherited from whatever container the
    values happen to land in: refusing a duplicate is a target's semantic
    contract, and a builder that silently kept the last one would make that
    contract an accident of construction order.
    """


REFUSE_DUPLICATE = DuplicatePolicy("refuse")
"""A repeated decoded key records a verdict."""
FIRST_DUPLICATE = DuplicatePolicy("first")
"""A repeated decoded key is recognized and discarded; the first value wins."""
LAST_DUPLICATE = DuplicatePolicy("last")
"""A repeated decoded key replaces the value already read."""


# ── Schema states ─────────────────────────────────────────────────────


class SchemaState(IrNamedTuple[IrStr]):
    """One node of a target's upper grammar — the state family's base.

    A state answers three questions and no others: where an event continues,
    where a decoded key routes, and which events it names. Each is answered by
    the state itself, so nothing downstream has to ask what KIND of state it
    is holding.

    :ivar name: What the schema calls this state.
    """

    name: IrStr

    def after(self, event: IrStr) -> IrStr:
        """The state this one continues in once ``event`` fires.

        :param event: The signature event that fired.
        :returns: The name of the state to continue in.
        :raises UnsupportedConstructError: Always, on the base.
        """
        del event
        raise UnsupportedConstructError(
            f"{type(self).__name__} does not say where an event continues"
        )

    def route(self, key: IrStr) -> IrStr:
        """The state a decoded key's value is read in.

        :param key: The decoded discriminator.
        :returns: The name of the state to read its value in.
        :raises UnsupportedConstructError: Always, on the base.
        """
        del key
        raise UnsupportedConstructError(
            f"{type(self).__name__} does not say where a decoded key routes"
        )

    def consumed(self) -> tuple[IrStr, ...]:
        """Every event name this state names a transition for.

        :returns: The event names, so a schema can be checked against a
            signature before anything is compiled.
        :raises UnsupportedConstructError: Always, on the base.
        """
        raise UnsupportedConstructError(
            f"{type(self).__name__} does not say which events it consumes"
        )


class AcceptingState(SchemaState):
    """A valid state: the target's product is still being built here.

    :ivar name: What the schema calls this state.
    :ivar events: Signature event name → the state to continue in.
    :ivar routes: Where each decoded key's value is read.
    :ivar checks: What is checked while this state holds.
    :ivar duplicates: What a repeated decoded key means here.
    """

    name: IrStr
    events: IrMap[IrStr, IrStr]
    routes: SchemaRoutes = SchemaRoutes()
    checks: SchemaChecks = SchemaChecks()
    duplicates: DuplicatePolicy = REFUSE_DUPLICATE

    def after(self, event: IrStr) -> IrStr:
        """The declared continuation for ``event``.

        :param event: The signature event that fired.
        :returns: The name of the state to continue in.
        :raises UnsupportedConstructError: On an event this state does not
            admit — the composed language does not contain it.
        """
        found = self.events.get(event)
        if found is None:
            raise UnsupportedConstructError(
                f"schema state {str(self.name)!r} admits no event {str(event)!r}"
            )
        return found

    def route(self, key: IrStr) -> IrStr:
        """The first route claiming ``key``.

        :param key: The decoded discriminator.
        :returns: The name of the state to read its value in.
        :raises UnsupportedConstructError: When no route claims it — a state
            with no catch-all route consumes exactly what it enumerates.
        """
        for candidate in self.routes:
            if candidate.accepts(key):
                return candidate.state
        raise UnsupportedConstructError(
            f"schema state {str(self.name)!r} has no route for decoded key {str(key)!r}"
        )

    def consumed(self) -> tuple[IrStr, ...]:
        """The event names this state admits."""
        return tuple(self.events.keys())


class PoisonedState(SchemaState):
    """A refused state: the product is lost, the document is not yet read.

    The verdict is recorded rather than raised, and every event from here
    continues in :attr:`recovery` — because a semantic failure over text that
    turns out not to parse is not the failure worth reporting.

    :ivar name: What the schema calls this state.
    :ivar verdict: The :class:`~lexic.exceptions.SemanticVerdict` sort
        entering this state records.
    :ivar words: What that verdict says.
    :ivar recovery: The recognition-only state the rest of the value is read
        in.
    """

    name: IrStr
    verdict: IrStr
    words: IrStr
    recovery: IrStr

    def after(self, event: IrStr) -> IrStr:
        """Continue in the recovery state, whatever fired."""
        del event
        return self.recovery

    def route(self, key: IrStr) -> IrStr:
        """Route every key into the recovery state."""
        del key
        return self.recovery

    def consumed(self) -> tuple[IrStr, ...]:
        """No events — a poisoned state admits everything and names nothing."""
        return ()


class RecoveryState(SchemaState):
    """A recognition-only state: the lower syntax is read, nothing is built.

    Absorbing by construction. It exists so a target that defers its failure
    to the end of the document can still prove the document was well formed,
    without constructing values it has already decided to discard.

    :ivar name: What the schema calls this state.
    """

    name: IrStr

    def after(self, event: IrStr) -> IrStr:
        """Stay here — recovery reads the remaining syntax and ends."""
        del event
        return self.name

    def route(self, key: IrStr) -> IrStr:
        """Stay here — a key inside a discarded value routes nowhere else."""
        del key
        return self.name

    def consumed(self) -> tuple[IrStr, ...]:
        """No events — recovery recognizes rather than consumes."""
        return ()


# ── Meaning and failure declarations ──────────────────────────────────


class MeaningLaw(IrStr):
    """How two derivations of one span are compared when a target must choose.

    A target declares this because equality belongs to the codomain: two
    values that a map calls equal an ordered accumulator may not. No law here
    stands a hash or a digest in for equality.
    """


EXACT_MEANING = MeaningLaw("exact")
"""Compare two complete values outright."""
SHARED_MEANING = MeaningLaw("shared")
"""Compare persistent values, skipping the branches they share by identity."""


class FailureOrder(IrStr):
    """When a target's semantic refusal is raised, relative to lower syntax."""


DEFERRED_FAILURE = FailureOrder("deferred")
"""Recognize the complete lower syntax first; then raise the earliest verdict."""
IMMEDIATE_FAILURE = FailureOrder("immediate")
"""Raise at the refusing occurrence, leaving the rest of the document unread."""


# ── The target schema ─────────────────────────────────────────────────


class TargetSchema(IrNamedTuple[IrStr, IrStr, IrStr, IrMap, MeaningLaw, FailureOrder]):
    """A finite state machine over one signature's events — a target's grammar.

    The lower grammar says how characters form events; this says which event
    shapes form a supported product. Their composition is the real grammar of
    what the caller asked for, and it is stated without either layer naming
    the other's vocabulary: states transition on event NAMES, and the reducer
    alone knows which symbol raises each.

    States refer to one another by name rather than by reference, so a schema
    whose product is recursive stays a finite value.

    :ivar name: What this schema is called.
    :ivar signature: The name of the :class:`SemanticSignature` it is authored
        over.
    :ivar start: The state a document enters.
    :ivar states: State name → the :class:`SchemaState` it names.
    :ivar meaning: How this target compares two meanings of one span.
    :ivar failure: When a semantic refusal is raised.
    """

    name: IrStr
    signature: IrStr
    start: IrStr
    states: IrMap[IrStr, SchemaState]
    meaning: MeaningLaw = EXACT_MEANING
    failure: FailureOrder = DEFERRED_FAILURE

    def state(self, name: IrStr) -> SchemaState:
        """One named state.

        :param name: The state name.
        :returns: The state it names.
        :raises UnsupportedConstructError: On a name this schema does not
            declare.
        """
        found = self.states.get(name)
        if found is None:
            raise UnsupportedConstructError(
                f"target schema {str(self.name)!r} declares no state {str(name)!r}"
            )
        return found

    def consumed(self) -> tuple[IrStr, ...]:
        """Every event name this schema's states transition on."""
        return tuple(
            event for state in self.states.values() for event in state.consumed()
        )

    def verify(self, signature: SemanticSignature) -> None:
        """Refuse a signature this schema cannot be composed with.

        The diagnosis a caller gets before anything is parsed: either the
        boundary is a different one, or it is the right one and does not
        declare an event some state transitions on.

        :param signature: The boundary the reducer declares.
        :raises UnsupportedConstructError: On either mismatch.
        """
        if signature.name != self.signature:
            raise UnsupportedConstructError(
                f"target schema {str(self.name)!r} is authored over semantic "
                f"signature {str(self.signature)!r}, not {str(signature.name)!r}"
            )
        missing = sorted({str(e) for e in self.consumed() if e not in signature.events})
        if missing:
            raise UnsupportedConstructError(
                f"target schema {str(self.name)!r} transitions on events "
                f"{missing}, which semantic signature "
                f"{str(signature.name)!r} does not declare"
            )


__all__ = [
    # Contribution policies
    "Drop",
    "DROP",
    "KeepRaw",
    "KEEP_RAW",
    "KeepReduced",
    "KEEP_REDUCED",
    "Yield",
    "YIELD",
    # Semantic sorts, and the boundary they describe
    "SemanticSort",
    "SORT_ABSENCE",
    "SORT_TRUTH",
    "SORT_INTEGER",
    "SORT_FRACTION",
    "SORT_TEXT",
    "SORT_ITEM",
    "SORT_SEQUENCE",
    "SORT_ENTRY",
    "SORT_MAPPING",
    "SORT_COMPLETION",
    "SemanticSignature",
    # The reducer
    "Reducer",
    # Schema routes
    "SchemaRoute",
    "KnownRoute",
    "ExtensionRoute",
    "EntryRoute",
    "SchemaRoutes",
    # Validation declarations
    "SchemaCheck",
    "SchemaChecks",
    "DuplicatePolicy",
    "REFUSE_DUPLICATE",
    "FIRST_DUPLICATE",
    "LAST_DUPLICATE",
    # Schema states
    "SchemaState",
    "AcceptingState",
    "PoisonedState",
    "RecoveryState",
    # Meaning and failure declarations
    "MeaningLaw",
    "EXACT_MEANING",
    "SHARED_MEANING",
    "FailureOrder",
    "DEFERRED_FAILURE",
    "IMMEDIATE_FAILURE",
    # The target schema
    "TargetSchema",
]
