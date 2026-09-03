"""Does the regular proof ask each rule the question that is really there?

Two defects, one module. The first: `build_recognizer` lowers an inline group
to the same ordered, committed alternation a same-bodied rule gets, and the
proof asked the arm obligations of rule arms only. The second: every rule of
the closure was proved against the REGION's follow, when a rule reached through
a reference is followed by the remainder of the referencing arm — so a rule in
the middle of a region was asked about text that cannot be there, and the group
shortcut inherited that wrong question and granted a commitment on it.

`build_recognizer` lowers an inline group to the same ordered, committed
alternation a same-bodied rule gets — its own docstring says a group is a rule
the grammar did not name and nothing there can tell them apart. The proof did
not: `_rule_is_deterministic` asked the arm obligations of rule arms only, so
`("a" | "ab")+` earned a proof it must not, and a consult taken on that proof
would answer a rule's extent with the wrong number.

This witness holds the proof to both. Four unsound group shapes and two
wrong-continuation shapes must decline, two sound ones must keep proving, and
each decline is shown to prevent a CONCRETE wrong answer: the pattern the old
shape licensed is matched against a real document and compared with what the
engine itself says that document means. Two controls neutralise the two
obligations in turn and insist every shape they guard comes back — without them
"the proof declines these" is a claim about a check nobody has shown is
load-bearing.

Run: `uv run python zzz_current_work/260826-target-shaped-parse/proto/s4_consult_soundness.py`

Uncommitted evidence, not a test. Luna owns the committed suite.
"""

from __future__ import annotations

from typing import NamedTuple

import lexic.parsing.product.regular as regular
from lexic.compile import canonical_grammar, compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from lexic.ir import IrAlternation, IrItem, IrRule, IrRuleRef
from lexic.parsing.lift import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.compiler.eligibility import extent_consult
from lexic.parsing.pda.core.charsets import CharSet
from lexic.parsing.pda.core.scanner import build_recognizer
from lexic.parsing.product import prove_regular

NULLABLE_FOLLOWER = 'root ::= word gap "z"\nword ::= "x" [a-b]+ "q"?\ngap ::= "q"*\n'
"""A clone whose hard continuation hides the follower it can steal from.

``word``'s next MANDATORY item is the ``"z"``, so the clone is compiled with
``tail = {z}`` and obligation 3 is never asked whether the trailing ``"q"?``
can take ``gap``'s ``q``. Both engines resolve that split the same greedy way
today, so this is a proof defect rather than a wrong model — but the proof is
what licenses a consult to decide the extent on its own."""

RELATION = (
    "root ::= expr op expr\n"
    "expr ::= [a-z]+\n"
    'op ::= ("<=" | "<" | "==" | "!=" | ">=" | ">")\n'
)
"""The shape the ruling names as sound: ordered literal arms one character
cannot separate, where nothing but the longest munch can be meant."""


class Case(NamedTuple):
    """One grammar, one region, one continuation — and what the proof owes it.

    :ivar label: How the row is reported.
    :ivar source: The GBNF source the region lives in.
    :ivar root: The rule the proof is taken on.
    :ivar tail: The continuation's characters, spelled as one string.
    """

    label: str
    source: str
    root: str
    tail: str


UNSOUND = (
    Case(
        "(a|ab)+ repeated", 'root ::= pair "c"\npair ::= ("a" | "ab")+\n', "pair", "c"
    ),
    Case("(a|ab) before c", 'root ::= word "c"\nword ::= ("a" | "ab")\n', "word", "c"),
    Case(
        "(ab|a) before bc", 'root ::= word "bc"\nword ::= ("ab" | "a")\n', "word", "b"
    ),
    Case("relation group, = may follow", RELATION, "op", "="),
)
"""Every shape whose ordered commitment can differ from the grammar's own
answer. The last is the residual obligation: ``("<=" | "<")`` is only forced
while the character the longer arm holds past the shorter one cannot begin
what follows — let ``=`` follow and taking ``<=`` strands it."""

SOUND = (
    Case("relation group", RELATION, "op", "abz"),
    Case(
        "(ab|a)+ longest first",
        'root ::= pair "c"\npair ::= ("ab" | "a")+\n',
        "pair",
        "c",
    ),
)
"""The same literals, ordered so the munch is forced. Kept as a pair with
``UNSOUND`` deliberately: the obligation is about ORDER and continuation, not
about literal arms being suspicious."""


REFERENCED = (
    Case(
        "referenced group, own continuation",
        'root ::= word "z"\nword ::= a b\na ::= ("px" | "p")\nb ::= "x"\n',
        "word",
        "z",
    ),
    Case(
        "referenced optional, own continuation",
        'root ::= word "z"\nword ::= a b\na ::= "p" "x"?\nb ::= "x"\n',
        "word",
        "z",
    ),
)
"""Two regions whose interior rule is followed by `b`, never by the region's
own `z`. Proved against `z` both earn a commitment: the group takes ``px``
because ``x`` cannot follow the region, and the optional takes ``x`` for the
same reason. Both then strand `b`, and the possessive pattern — which cannot
give the character back — fails on a document the grammar derives."""


class Defect(AssertionError):
    """A claim this witness makes that the proof does not support."""


class Vacuous(Exception):
    """The new obligation was neutralised and nothing noticed."""


def _check(claim: str, held: bool) -> None:
    """Refuse the witness the moment one claim stops holding."""
    if not held:
        raise Defect(f"s4 consult soundness: {claim}")


def _rules(source: str) -> dict[str, IrRule]:
    """The canonical rule table of one GBNF grammar."""
    ast = canonical_grammar(source, GBNF_FLAVOUR)
    return {str(rule.name): rule for rule in ast.rules}


def _proves(case: Case) -> bool:
    """Whether the region proves regular against its stated continuation."""
    tail = CharSet.from_chars(*case.tail)
    return prove_regular(_rules(case.source), case.root, tail) is not None


def _possessive_extent(case: Case, document: str) -> int:
    """What the pattern the proof WOULD license consumes at position 0.

    The recognizer is built directly, without the proof: this is the answer a
    consult would have returned had the region been proved, which is what makes
    a decline's value measurable rather than asserted.

    :returns: The extent, or ``-1`` when the pattern does not match at all.
    """
    recognizer = build_recognizer(_rules(case.source), frozenset({case.root}))
    _check(f"{case.label}: no recognizer to measure", recognizer is not None)
    assert recognizer is not None
    matched = recognizer.pats[recognizer.index[case.root]].match(document, 0)
    return -1 if matched is None else matched.end()


def the_unsound_groups_decline() -> None:
    """Every shape whose commitment can be wrong is refused a proof."""
    for case in UNSOUND:
        _check(f"{case.label} was proved regular", not _proves(case))
        print(f"declines\t{case.label}")


def the_sound_groups_keep_proving() -> None:
    """The forced-munch shapes still prove — the fix is not a blanket refusal."""
    for case in SOUND:
        _check(f"{case.label} lost its proof", _proves(case))
        print(f"proves  \t{case.label}")


def the_referenced_rules_get_their_own_continuation() -> None:
    """A rule in the middle of a region is proved against what follows IT.

    Each row is measured as well as asserted: the pattern the region-follow
    proof licensed is run over a document the grammar derives, and it returns
    no match at all — a consult on that proof would refuse a valid document.
    """
    for case in REFERENCED:
        _check(f"{case.label} was proved regular", not _proves(case))
        model = compile_text(case.source).parse("pxz", cores=1)
        meant = getattr(model, case.root).to_text()
        _check(f"{case.label}: the engine reads {meant!r}, not 'px'", meant == "px")
        licensed = _possessive_extent(case, "pxz")
        _check(
            f"{case.label}: the licensed pattern agreed ({licensed}) — no wrong "
            "answer to prevent",
            licensed != len(meant),
        )
        print(
            f"declines\t{case.label}\tpattern={licensed}, "
            f"grammar={len(meant)} ({meant!r})"
        )


def _the_old_question(
    first: object, rules: dict[str, IrRule], items: list[IrItem], tail: set, proved: set
) -> bool:
    """The walk as it WAS: every referenced rule asked the region's question.

    A control has to restore the defect rather than remove the check. Deleting
    the walk would leave the closure half-visited and the coverage guard would
    decline for a different reason, which proves nothing about the threading.
    So this keeps the walk, the coverage and the memo, and changes only the
    continuation each reference is handed.
    """
    for item in items:
        atom = item.atom
        if isinstance(atom, IrRuleRef):
            if not regular._closure_holds(first, rules, str(atom), tail, proved):
                return False
        elif isinstance(atom, IrAlternation) and not all(
            _the_old_question(first, rules, regular._items(arm), tail, proved)
            for arm in atom
        ):
            return False
    return True


def the_reference_walk_is_what_declines() -> None:
    """Restore the region-follow question; both shapes must prove again."""
    kept = regular._references_hold
    regular._references_hold = _the_old_question
    try:
        revived = [case.label for case in REFERENCED if _proves(case)]
        sound = [case.label for case in SOUND if _proves(case)]
    finally:
        regular._references_hold = kept
    if len(revived) != len(REFERENCED):
        raise Vacuous(
            "s4 consult soundness: with the reference walk off, "
            f"{len(revived)} of {len(REFERENCED)} wrong-continuation shapes "
            "still declined — something else is doing the declining"
        )
    _check("a sound shape needed the reference walk to prove", len(sound) == len(SOUND))
    _check("the neutralised walk outlived the control", regular._references_hold is kept)
    print(f"control \tthreading off ⇒ all {len(revived)} referenced shapes prove again")


def the_nullable_follower_is_in_the_question() -> None:
    """A skipped nullable follower is part of what the clone must not steal."""
    compiled = compile_text(NULLABLE_FOLLOWER)
    tables = compiled.pda_tables()
    specs = [spec for spec in tables.clones.values() if spec.name == "word"]
    _check(f"no 'word' clone to read ({len(tables.clones)} clones)", len(specs) == 1)
    spec = specs[0]
    _check("the clone is not match-only, so nothing was ever asked", spec.match_only)
    _check("the clone kept a consult its tail could not justify", spec.consult is None)
    key = next(key for key in tables.clones if tables.clones[key] is spec)
    analysis = GrammarAnalysis(lift_optional_nullables(compiled.codegen_grammar))
    rules, follow = analysis.rules, analysis.follow["word"]
    _check(
        f"the clone's tail {sorted(key.tail.chars)} already holds the follower",
        "q" not in key.tail.chars,
    )
    _check(
        f"the rule's soft FOLLOW {sorted(follow.chars)} does not hold it either",
        "q" in follow.chars,
    )
    old = extent_consult(rules, "word", True, key.tail, CharSet.EMPTY)
    _check("the old question also declined — nothing changed here", old is not None)
    print(
        "follower\tword: tail=%s, soft FOLLOW=%s — proves on the tail alone, "
        "declines on the real continuation"
        % (sorted(key.tail.chars), sorted(follow.chars))
    )


def the_decline_prevents_a_wrong_extent() -> None:
    """Two documents where the licensed pattern and the engine disagree."""
    short = Case(
        "(a|ab) before c", 'root ::= word "c"\nword ::= ("a" | "ab")\n', "word", "c"
    )
    long = Case(
        "(ab|a) before bc", 'root ::= word "bc"\nword ::= ("ab" | "a")\n', "word", "b"
    )
    for case, expected in ((short, "ab"), (long, "a")):
        model = compile_text(case.source).parse("abc", cores=1)
        meant = getattr(model, case.root).to_text()
        licensed = _possessive_extent(case, "abc")
        _check(
            f"{case.label}: the engine reads {meant!r}, not {expected!r}",
            meant == expected,
        )
        _check(
            f"{case.label}: the licensed pattern agreed ({licensed}) — no wrong "
            "answer to prevent",
            licensed != len(meant),
        )
        print(
            f"wrong   \t{case.label}\tpattern={licensed} chars, "
            f"grammar={len(meant)} ({meant!r})"
        )


def the_decline_prevents_a_silent_choice() -> None:
    """A document the grammar REFUSES, that the licensed pattern would answer.

    The shorter possessive extent still lets the enclosing parse succeed here,
    so nothing downstream fails and nothing is caught: the consult would have
    returned one of two meanings where the engine's whole contract is to refuse
    a span that means two things.
    """
    source = 'root ::= word tail\nword ::= ("a" | "ab")\ntail ::= "bc" | "c"\n'
    case = Case("(a|ab) before bc|c", source, "word", "bc")
    _check("the ambiguous shape was proved regular", not _proves(case))
    refused = ""
    try:
        compile_text(source).parse("abc", cores=1)
    except UnsupportedConstructError as refusal:
        refused = str(refusal)
    _check("the grammar did not refuse the ambiguous document", "ambiguous" in refused)
    licensed = _possessive_extent(case, "abc")
    _check("the licensed pattern declined too", licensed > 0)
    print(
        f"silent  \t(a|ab) before bc|c\tpattern={licensed} chars, "
        "grammar=refuses as ambiguous"
    )


def the_group_obligation_is_what_declines() -> None:
    """Neutralise the group walk; every unsound shape must earn a proof again."""
    kept = regular._group_holds
    regular._group_holds = lambda *_args: True
    try:
        revived = [case.label for case in UNSOUND if _proves(case)]
        sound = [case.label for case in SOUND if _proves(case)]
    finally:
        regular._group_holds = kept
    if len(revived) != len(UNSOUND):
        raise Vacuous(
            "s4 consult soundness: with the group obligation off, "
            f"{len(revived)} of {len(UNSOUND)} unsound shapes still declined — "
            "something else is doing the declining"
        )
    _check("a sound shape needed the group walk to prove", len(sound) == len(SOUND))
    _check("the neutralised walk outlived the control", regular._group_holds is kept)
    print(f"control \tobligation off ⇒ all {len(revived)} unsound shapes prove again")


def main() -> None:
    """Run every claim; any failure raises."""
    the_unsound_groups_decline()
    the_sound_groups_keep_proving()
    the_referenced_rules_get_their_own_continuation()
    the_nullable_follower_is_in_the_question()
    the_decline_prevents_a_wrong_extent()
    the_decline_prevents_a_silent_choice()
    the_group_obligation_is_what_declines()
    the_reference_walk_is_what_declines()
    print(
        "s4 consult soundness\tPASS\ta group owes what a rule owes, and each "
        "rule is asked its own continuation"
    )


if __name__ == "__main__":
    main()
