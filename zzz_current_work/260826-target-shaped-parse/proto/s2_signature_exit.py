"""Execute the §2 exit criterion against the real source tree.

Two claims, both run end to end:

1. Native json and every compiled formulation reduced by ``JSON_REDUCER``
   expose the SAME ``SemanticSignature`` object, and every symbol that reducer
   binds to an event names a rule each formulation actually has.
2. A mismatched target is diagnosed BEFORE a parse — a wrong boundary, an
   event the boundary does not declare, and a reducer with no boundary at all
   each refuse with words while the document is still just a string.

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from pathlib import Path

from lexic.compile import compile_ast, compile_from_path
from lexic.exceptions import (
    SemanticVerdict,
    TargetRefusalError,
    UnsupportedConstructError,
)
from lexic.grammars import ABNF_FLAVOUR, EBNF_FLAVOUR, GBNF_FLAVOUR
from lexic.grammars.json import (
    JSON_EVENTS,
    JSON_GRAMMAR,
    JSON_REDUCER,
    JSON_SIGNATURE,
)
from lexic.ir import (
    DEFERRED_FAILURE,
    EXACT_MEANING,
    REFUSE_DUPLICATE,
    SORT_ENTRY,
    SORT_MAPPING,
    SORT_TEXT,
    AcceptingState,
    EntryRoute,
    ExtensionRoute,
    IrMap,
    IrStr,
    IrTuple,
    KnownRoute,
    PoisonedState,
    RecoveryState,
    Reducer,
    SchemaCheck,
    SchemaChecks,
    SchemaRoute,
    SchemaRoutes,
    SchemaState,
    SemanticSignature,
    TargetSchema,
)

GROUND_TRUTH = Path(__file__).resolve().parents[3] / "resources" / "ground_truth"
DOCUMENT = '{"model": {"type": "bpe"}, "version": 1, "added": [true, null]}'

# A stand-in for the target §7 authors: it names json events only, never a
# rule, and its states form a finite machine over that boundary.
SAMPLE_SCHEMA = TargetSchema(
    IrStr("sample-target"),
    IrStr("json"),
    IrStr("root"),
    IrMap(
        IrTuple(
            IrStr("root"),
            AcceptingState(
                IrStr("root"),
                IrMap(
                    IrTuple(IrStr("document"), IrStr("root")),
                    IrTuple(IrStr("object"), IrStr("root")),
                    IrTuple(IrStr("object-entry"), IrStr("root")),
                ),
                SchemaRoutes(
                    KnownRoute(IrStr("model"), IrStr("model")),
                    ExtensionRoute(IrStr("ignored")),
                ),
                SchemaChecks(
                    SchemaCheck(
                        IrStr("required"),
                        IrStr("missing-field"),
                        IrStr("a sample target needs a model section"),
                    )
                ),
                REFUSE_DUPLICATE,
            ),
        ),
        IrTuple(
            IrStr("model"),
            AcceptingState(
                IrStr("model"),
                IrMap(IrTuple(IrStr("string"), IrStr("model"))),
                SchemaRoutes(EntryRoute(IrStr("model"))),
            ),
        ),
        IrTuple(
            IrStr("refused"),
            PoisonedState(
                IrStr("refused"),
                IrStr("unsupported-knob"),
                IrStr("a sample target does not support this knob"),
                IrStr("ignored"),
            ),
        ),
        IrTuple(IrStr("ignored"), RecoveryState(IrStr("ignored"))),
    ),
    EXACT_MEANING,
    DEFERRED_FAILURE,
)


def _check(claim: str, held: bool) -> None:
    """Refuse the whole witness the moment one claim stops holding."""
    if not held:
        raise AssertionError(f"s2 exit: {claim}")


def _refuses(claim: str, call: object) -> str:
    """Run a zero-argument call that must refuse, and return its words."""
    if not callable(call):
        raise AssertionError(f"s2 exit: {claim} is not callable")
    try:
        call()
    except UnsupportedConstructError as refusal:
        return str(refusal)
    raise AssertionError(f"s2 exit: {claim} did not refuse")


def one_signature_across_formulations() -> None:
    """Every formulation reduced by one reducer presents one boundary object."""
    sources = [("native", compile_ast(JSON_GRAMMAR))]
    for stem in ("json.gbnf", "json.abnf", "json.ebnf"):
        sources.append((stem, compile_from_path(GROUND_TRUTH / stem)))

    values = []
    for label, compiled in sources:
        _check(
            f"{label} does not expose THE signature object",
            JSON_REDUCER.signature is JSON_SIGNATURE,
        )
        rules = {str(rule.name) for rule in compiled.grammar.rules}
        unbound = sorted(str(sym) for sym in JSON_EVENTS.keys() if str(sym) not in rules)
        _check(f"{label} has no rule for bound symbols {unbound}", not unbound)
        declared = sorted(
            str(event)
            for event in JSON_EVENTS.values()
            if event not in JSON_SIGNATURE.events
        )
        _check(f"{label} binds undeclared events {declared}", not declared)
        values.append((label, compiled.reduce(DOCUMENT, JSON_REDUCER)))

    first_label, first = values[0]
    for label, value in values[1:]:
        _check(f"{label} reduced differently from {first_label}", value == first)
    print(
        f"one boundary\t{len(sources)} formulations\t"
        f"{len(JSON_SIGNATURE.events)} events, {len(JSON_EVENTS)} symbols bound, "
        "one reduced value"
    )


def mismatch_is_diagnosed_before_parse() -> None:
    """Each way a target can fail to compose refuses without reading text."""
    SAMPLE_SCHEMA.verify(JSON_SIGNATURE)

    other = SemanticSignature(
        IrStr("csv"), IrMap(IrTuple(IrStr("document"), SORT_MAPPING))
    )
    wrong_boundary = _refuses(
        "a schema over another boundary", lambda: SAMPLE_SCHEMA.verify(other)
    )

    thin = SemanticSignature(
        IrStr("json"),
        IrMap(
            IrTuple(IrStr("document"), SORT_MAPPING),
            IrTuple(IrStr("object"), SORT_MAPPING),
        ),
    )
    missing_event = _refuses(
        "a boundary missing a consumed event", lambda: SAMPLE_SCHEMA.verify(thin)
    )

    for flavour in (GBNF_FLAVOUR, ABNF_FLAVOUR, EBNF_FLAVOUR):
        _refuses(
            f"{type(flavour).__name__} declares no boundary",
            lambda f=flavour: SemanticSignature.ensure(
                f.reducer.signature, "the reducer's semantic signature"
            ),
        )

    _check(
        "the default reducer silently declares a boundary",
        Reducer().signature is not JSON_SIGNATURE and not Reducer().events,
    )
    print(f"before parse\twrong boundary\t{wrong_boundary}")
    print(f"before parse\tmissing event\t{missing_event}")
    print("before parse\tno boundary\tflavour reducers refuse the narrow")


def the_vocabulary_refuses_what_it_does_not_know() -> None:
    """Every family answers through itself; an unstated construct raises."""
    root = SchemaState.ensure(SAMPLE_SCHEMA.state(IrStr("root")))
    _check("root does not continue on document", root.after(IrStr("document")) == "root")
    _check("a known key does not route", root.route(IrStr("model")) == "model")
    _check("an unknown key does not reach the catch-all", root.route(IrStr("x")) == "ignored")
    _check("root consumes the wrong events", set(root.consumed()) == {
        IrStr("document"), IrStr("object"), IrStr("object-entry")
    })

    poisoned = SchemaState.ensure(SAMPLE_SCHEMA.state(IrStr("refused")))
    _check("a poisoned state does not recover", poisoned.after(IrStr("object")) == "ignored")
    _check("a poisoned state routes elsewhere", poisoned.route(IrStr("x")) == "ignored")
    _check("a poisoned state consumes events", poisoned.consumed() == ())

    recovery = SchemaState.ensure(SAMPLE_SCHEMA.state(IrStr("ignored")))
    _check("recovery is not absorbing", recovery.after(IrStr("object")) == "ignored")

    entry = SchemaState.ensure(SAMPLE_SCHEMA.state(IrStr("model")))
    _check("a dynamic mapping classified a key", entry.route(IrStr("anything")) == "model")

    unknown_event = _refuses(
        "a state admitting an unstated event", lambda: entry.after(IrStr("array"))
    )
    unknown_state = _refuses(
        "a schema naming an unstated state", lambda: SAMPLE_SCHEMA.state(IrStr("nope"))
    )
    unknown_sort = _refuses(
        "a signature declaring an unstated event",
        lambda: JSON_SIGNATURE.sort(IrStr("nope")),
    )
    _refuses(
        "the route family's base", lambda: SchemaRoute(IrStr("s")).accepts(IrStr("k"))
    )
    _refuses(
        "the state family's base", lambda: SchemaState(IrStr("s")).after(IrStr("e"))
    )
    _refuses(
        "the state family's base route", lambda: SchemaState(IrStr("s")).route(IrStr("k"))
    )
    _refuses(
        "the state family's base consumed", lambda: SchemaState(IrStr("s")).consumed()
    )
    _check(
        "sorts of different families compare equal",
        SORT_TEXT != IrStr("text") and SORT_ENTRY != SORT_TEXT and SORT_TEXT == "text",
    )
    print(f"open dispatch\tunknown event\t{unknown_event}")
    print(f"open dispatch\tunknown state\t{unknown_state}")
    print(f"open dispatch\tunknown sort\t{unknown_sort}")


def verdicts_order_and_carry() -> None:
    """The refusal value records order totally and reach the new exception."""
    late = SemanticVerdict("missing-field", "no model section", -1, 1)
    early = SemanticVerdict("duplicate-key", "repeated key 'type'", 12, 0)
    same_place = SemanticVerdict("unsupported-knob", "unknown knob", 12, 1)
    ordered = sorted((late, same_place, early), key=lambda v: (v.pos, v.order))
    _check(
        "verdicts do not order by (pos, order)",
        ordered == [late, early, same_place],
    )
    error = TargetRefusalError(ordered[0].words, ordered)
    _check("the refusal lost its verdicts", error.verdicts == tuple(ordered))
    _check("the refusal is not a LexicError", isinstance(error, Exception))
    print(f"verdicts\t{len(error.verdicts)} ordered\t{error}")


def main() -> None:
    """Run every claim; any failure raises."""
    one_signature_across_formulations()
    mismatch_is_diagnosed_before_parse()
    the_vocabulary_refuses_what_it_does_not_know()
    verdicts_order_and_carry()
    print("s2 exit\tPASS\tone signature, mismatch diagnosed before parse")


if __name__ == "__main__":
    main()
