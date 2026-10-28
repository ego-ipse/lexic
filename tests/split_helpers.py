"""Shared split-path helpers for tests that must not assume engagement.

Faithfulness and concurrency both need the same question answered — *did the
split entry actually take this document?* — and both are worthless if it is
guessed. A suite whose split silently declines still passes every equality it
asserts, having compared a sequential parse against a sequential parse.

One copy, because two would drift: the call reaches into ``split_model``'s
exact signature, and a change there should break one place rather than leave
a stale second answer behind.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from threading import Barrier, Event, Thread

from lexic.compile import CompiledGrammar
from lexic.ir import IrAst
from lexic.parsing.executable import ModelExecutable
from lexic.parsing.parallel import split_model
from lexic.parsing.parallel.orchestrate import Request
from lexic.parsing.parallel.pool import WorkPool
from lexic.parsing.parallel.replicas import replica_count
from lexic.parsing.products import parse_model

WORKERS = 8
"""Worker count engagement is asked at — enough that most shapes can use it."""


def engages(compiled: CompiledGrammar, text: str, cores: int = WORKERS) -> bool:
    """Whether the split entry itself takes ``text``, asked through the real entry.

    Note what this is NOT: a retained pool in ``lexic.parsing.parallel.pool``
    is no evidence of engagement, because the lease is taken before the plan
    settles. A declining grammar leaves a warm pool behind, and discovery may
    already have submitted work to it. Only ``split_model``'s result answers
    whether the split itself produced a model.

    :param compiled: The artefact whose split path is in question.
    :param text: The document to offer it.
    :param cores: The worker count to ask at.
    :returns: Whether the split produced a model rather than declining.
    """
    found = split_model(
        parse_model,
        compiled.codegen_grammar,
        Request(text, compiled.product),
        cores,
        analysis=compiled.split_analysis or compiled.grammar,
    )
    return found is not None


def assert_parallel_matches_sequential(
    compiled: CompiledGrammar, text: str, workers: int
):
    """The parallel answer IS the sequential one — class, model and text.

    One copy for the same reason as :func:`engages`: every suite that divides
    a document owes exactly these three, and a second spelling would drift
    into asserting less while still reading like this one. Equality alone is
    not enough — two models of different classes can compare equal field for
    field — and the round-trip is what catches a stitch that reassembled the
    right values in the wrong order.

    :param compiled: The artefact to parse with.
    :param text: The document, long enough that the split takes it.
    :param workers: The worker count to parse at.
    :returns: The sequential model, for a caller with more to ask of it.
    """
    sequential = compiled.parse(text, cores=1)
    parallel = compiled.parse(text, cores=workers)
    assert type(parallel) is type(sequential)
    assert parallel == sequential
    assert parallel.to_text() == text
    return sequential


LEAD_RULE = (
    "root ::= pair tail*\n"
    "tail ::= comma pair\n"
    'comma ::= "," ws\n'
    'pair ::= [a-z]+ ":" [0-9]+\n'
    'ws ::= " "*\n'
)
"""A SEPARATED repetition: the split re-parses every cut's lead on the driver.

One copy for the same reason as :func:`engages`. Two suites need the shape
whose split does work on the submitting thread — the orchestrator's own tests
and the artefact's document-view regression — and a second spelling of it would
drift into a different shape while both still claimed to be testing this one.
"""


def lead_rule_document(pairs: int) -> str:
    """A ``LEAD_RULE`` document of ``pairs`` items, long enough to divide."""
    return ", ".join(f"key{'x' * (index % 7)}:{index}" for index in range(pairs))


CLOSER_SEPARATOR_UNREAD = {
    "unreachable": (
        'root ::= "<" item ("." item)* ","\nunused ::= item ("," item)*\n'
        "item ::= [a-z]+\n"
    ),
    "inside-a-skipped-string": (
        'root ::= "<" part ("." part)* ","\npart ::= item | quoted\n'
        'quoted ::= "\\"" item ("," item)* "\\""\nitem ::= [a-z]+\n'
    ),
}
"""A pair closing on ``,`` whose grammar ALSO spells ``,`` as a separator,
only where the scan never reads it: in a rule nothing reaches, or inside the
string the walk skips whole. One copy: the region scan's vocabulary pins and
the split's faithfulness pins read the same two shapes."""


def closer_separator_document(shape: str, parts: int) -> str:
    """A ``CLOSER_SEPARATOR_UNREAD[shape]`` document of ``parts`` dotted parts;
    every third is a string holding a ``,`` where the shape has strings."""
    quoted = shape != "unreachable"
    return (
        "<"
        + ".".join(
            '"a,b"' if quoted and index % 3 == 0 else "ab" for index in range(parts)
        )
        + ","
    )


TWO_ROLE_PAIRS = (
    'root ::= part ("," part)*\n'
    "part ::= angle | bar | word\n"
    'angle ::= "<" word "|"\n'
    'bar ::= "|" word ("," word)* ">"\n'
    "word ::= [a-z0-9]+\n"
)
"""``|`` closes ``angle`` and opens ``bar``: one character in two pair roles.
A depth count would net it to zero and read a ``bar``'s own commas as top-level
marks, and a walk can read it only one way, so neither pair stands
(:func:`~lexic.parsing.parallel.roles.standing_pairs`). One copy: the scan, the
region walk and the split read the same shape."""


def two_role_document(words: int) -> str:
    """``words`` words, a ``bar`` of ``words`` words, and ``words`` words again."""
    run = ",".join(f"w{index}" for index in range(words))
    return run + ",|" + ",".join(f"x{index}" for index in range(words)) + ">," + run


TWO_ROLE_SHAPES = {
    "list": (
        'root ::= "[" part ("," part)* "]"',
        'angle ::= "<" word ("." word)* "|"',
        'bar ::= "|" word (";" word)* ">"',
        "part ::= angle | bar | word",
    ),
    "top": (
        'root ::= part ("," part)*',
        'angle ::= "<" word ("." word)* "|"',
        'bar ::= "|" word (";" word)* ">"',
        "part ::= angle | bar | word",
    ),
    "nest": (
        'root ::= part ("," part)*',
        'angle ::= "<" part ("." part)* "|"',
        'bar ::= "|" part (";" part)* ">"',
        "part ::= angle | bar | word",
    ),
    "tail": (
        'root ::= part ("," part)*',
        'angle ::= "<" word ("." word)* "|"',
        'bar ::= "|" part (";" part)* ">"',
        "part ::= angle word | bar | word",
    ),
    "tail-list": (
        'root ::= "[" part ("," part)* "]"',
        'angle ::= "<" word ("." word)* "|"',
        'bar ::= "|" part (";" part)* ">"',
        "part ::= angle word | bar | word",
    ),
    "lines": (
        'root ::= line+\nline ::= part ("," part)* "\\n"',
        'angle ::= "<" word "|"',
        'bar ::= "|" word ("," word)* ">"',
        "part ::= angle | bar | word",
    ),
    "lines-nl-in-bar": (
        'root ::= line+\nline ::= part (" " part)* "\\n"',
        'angle ::= "<" word "|"',
        'bar ::= "|" word ("\\n" word)* ">"',
        "part ::= angle | bar | word",
    ),
    "semis": (
        'root ::= part (";" part)*',
        'angle ::= "<" word "|"',
        'bar ::= "|" part (";" part)* ">"',
        "part ::= word | angle | bar",
    ),
}
"""Shapes around ``|`` closing ``angle`` and opening ``bar``: the two pairs in a
list, at the top level, nested, juxtaposed with a word, line-terminated, and
sharing the top level's separator."""


def two_role_source(shape: str) -> str:
    """The grammar text of one ``TWO_ROLE_SHAPES`` entry."""
    return "\n".join(TWO_ROLE_SHAPES[shape]) + "\nword ::= [a-z0-9]+\n"


SHARED_CLOSER = {
    "top": 'root ::= part ("," part)*',
    "wrapped": 'root ::= "{" part ("," part)* "}"',
}
"""Two standing pairs closing on one character: ``a`` opens on ``(`` and ``b``
on ``[``, and both close on ``)``. One copy: the region walk, the windowed find
and the split read the same shapes."""


def shared_closer_source(shape: str) -> str:
    """The grammar text of one ``SHARED_CLOSER`` shape."""
    return (
        SHARED_CLOSER[shape]
        + '\npart ::= a | b\na ::= "(" w (";" w)* ")"\n'
        + 'b ::= "[" w (";" w)* ")"\nw ::= [a-z0-9]+\n'
    )


def shared_closer_document(shape: str, runs: Sequence[tuple[str, int]]) -> str:
    """One part per ``(opener, words)`` in ``runs``, comma-separated."""
    body = ",".join(
        opener + ";".join(f"w{index}" for index in range(words)) + ")"
        for opener, words in runs
    )
    return "{" + body + "}" if shape == "wrapped" else body


SETTLE = 5.0
"""Seconds a thread's exit signal is given before a case fails."""


def settled_replica_count(
    grammar: IrAst, binding: ModelExecutable, want: int, deadline: float = SETTLE
) -> int:
    """Poll ``replica_count`` until it reaches ``want``, or the deadline fails.

    One copy, because two files assert on the same release and two polls would
    drift. Finalization is not synchronous with `Thread.join` returning: the
    exit signal fires when the thread's own state is freed, which CPython does
    on its way out and not before releasing the join. Reading the count
    straight after a join relies on an ordering nothing promises.

    The deadline is a FAILURE, not a pass — a release that needs the whole of
    it has not been demonstrated.
    """
    end = time.monotonic() + deadline
    count = replica_count(grammar, binding)
    while time.monotonic() < end and count != want:
        time.sleep(0.01)
        count = replica_count(grammar, binding)
    return count


def hold_workers(pool: WorkPool, count: int, release: Event) -> Thread:
    """Occupy ``count`` of ``pool``'s workers until ``release`` is set.

    The holding phase runs on a thread of its own, so the caller's next phase
    finds only the rest of the pool free; returned once every held worker is
    running, for the caller to join after setting ``release``.
    """
    running = Barrier(count + 1)

    def hold(_slot: int) -> None:
        running.wait(timeout=30)
        release.wait(timeout=30)

    holder = Thread(target=pool.map, args=(hold, list(range(count))))
    holder.start()
    running.wait(timeout=30)
    return holder


class FiledDuringRead(dict):
    """A dict another thread inserts into while it is read: a reader that walks
    it live meets an insert mid-walk and raises, as a free-threaded dict does
    under a concurrent writer; a reader that takes a snapshot does not."""

    def __iter__(self):
        for key in super().__iter__():
            self[("~filed meanwhile", len(self))] = None
            yield key
