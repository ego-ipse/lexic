"""A text rule's arm read by its language: the PDA never answers differently
from whole-document Earley where matching the arm item by item would.

Two grammar shapes, each a rule whose arm's quantified item can take the one
character its successor needs — a run before an overlapping class, and an
optional literal before one. Matched item by item, the arm "did not derive" a
string in its language, the loop around it closed, and the PDA committed a
model Earley does not build.

Sabotage: with the entries matched item by item again (no forced end), every
test here fails.
"""

from __future__ import annotations

import itertools

import pytest

from lexic.compile import compile_text
from lexic.exceptions import LexicError
from lexic.parsing.pda.compiler.program.flatten import FlatClone, clone_arms
from lexic.parsing.pda.compiler.program.language import STATE_CAP, ForcedEnd
from lexic.parsing.pda.core.errors import PdaFail, ProbeFork
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import earley_model
from tests.unit.lexic.parsing.parsing_helpers import prod

RUN_BEFORE_CLASS = 'doc ::= part+ tail\npart ::= ";" ";"? | [a]* [a;]\ntail ::= [a]*\n'
"""``[a]*`` can take the ``a`` that ``[a;]`` needs."""

OPTIONAL_BEFORE_CLASS = (
    'doc ::= sec+\nsec ::= stmt+ end\nstmt ::= "!" | ";"? [a;]\n'
    'end ::= [a;] | [a]* "a"\n'
)
"""``";"?`` can take the ``;`` that ``[a;]`` needs."""

SHAPES = {
    "run before class": (RUN_BEFORE_CLASS, "a;"),
    "optional before class": (OPTIONAL_BEFORE_CLASS, "a;!"),
}


def _marked(source: str, key: str) -> int:
    """How many attempt entries in the compiled program match by a language."""
    root = prod(compile_text(source, cache_key=f"lang-mark-{key}")).pda.program.start
    seen: set[int] = set()
    work, marked = [root], 0
    while work:
        clone = work.pop()
        if id(clone) in seen or not isinstance(clone, FlatClone):
            continue
        seen.add(id(clone))
        work += [p for arm in clone_arms(clone) for p in arm.payloads]
        if clone.attempt is not None:
            subs = [entry[-1] for entry in clone.attempt[1]]
            marked += sum(_forced(sub) for sub in subs)
            work += subs
    return marked


def _forced(sub: FlatClone) -> bool:
    """Whether an entry's whole extent is its language's forced end."""
    runarm = sub.runarm
    return runarm is not None and isinstance(runarm.payloads[0], ForcedEnd)


MARKED = {"run before class": 1, "optional before class": 2}
"""The arms whose item can steal: ``[a]* [a;]``; and ``";"? [a;]`` with
``end``'s ``[a]* "a"``, a run before the literal it can take."""


@pytest.mark.parametrize("label", sorted(SHAPES))
def test_exactly_the_overlapping_arms_are_marked(label: str) -> None:
    """Each arm whose item can steal carries a language, and no other does."""
    source, _alphabet = SHAPES[label]
    assert _marked(source, label) == MARKED[label]


@pytest.mark.parametrize("label", sorted(SHAPES))
def test_the_pda_never_answers_differently_from_earley(label: str) -> None:
    """Every string up to length 6: where the PDA answers, it answers what
    Earley does; where it cannot certify the arm's end, it bails."""
    source, alphabet = SHAPES[label]
    compiled = compile_text(source, cache_key=f"lang-diff-{label}")
    product = prod(compiled)
    different = []
    for length in range(1, 7):
        for chars in itertools.product(alphabet, repeat=length):
            text = "".join(chars)
            try:
                earley = earley_model(
                    product.instance_grammar, text, compiled.product, product.tables
                )
            except LexicError:
                continue
            try:
                pda = pda_model(product.pda, text, compiled.executor)
            except PdaFail:
                continue
            if pda != earley:
                different.append(text)
    assert not different, different[:10]


def test_a_run_gives_back_the_character_its_class_needs() -> None:
    """``a;a``: the last ``a`` is a whole ``part`` — the decider's carving —
    not the tail's."""
    compiled = compile_text(RUN_BEFORE_CLASS, cache_key="lang-run")
    got = compiled.parse("a;a")
    assert [part.to_text() for part in got[0]] == ["a;", "a"]
    assert got[1].to_text() == ""


def test_an_optional_gives_back_the_character_its_class_needs() -> None:
    """``a;!;``: ``;`` is a whole ``stmt``, so the section is one, not two."""
    compiled = compile_text(OPTIONAL_BEFORE_CLASS, cache_key="lang-opt")
    got = compiled.parse("a;!;")
    assert len(got[0]) == 1
    assert [stmt.to_text() for stmt in got[0][0][0]] == ["a", ";", "!"]


PADDED = (
    'doc ::= part+ tail\npart ::= ";" | "' + "x" * STATE_CAP + '" [a]* [a;]\n'
    "tail ::= [ax]*\n"
)
"""The run-before-class shape behind a literal too long for an automaton."""


def test_an_arm_too_large_for_an_automaton_bails_on_the_public_path() -> None:
    """Marked but unbuildable: the PDA bails instead of matching item by item,
    which here would close ``part+`` and hand the whole arm's text to
    ``tail``. The public parse is Earley's: the second ``part``."""
    compiled = compile_text(PADDED, cache_key="lang-padded")
    product = prod(compiled)
    text = ";" + "x" * STATE_CAP + "a"
    with pytest.raises(ProbeFork):
        pda_model(product.pda, text, compiled.executor)
    got = compiled.parse(text)
    assert [part.to_text() for part in got[0]] == [";", text[1:]]
    assert got[1].to_text() == ""
