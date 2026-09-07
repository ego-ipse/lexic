"""The language differential — probes derived from the grammar, judged by lexic.

A handful of authored sentences cannot prove two parsers describe the same
language. They prove the parser handles the sentences someone thought of, and
the failures worth catching are exactly the ones nobody thought of: a
`pyparsing` seat whose end-of-input anchor skipped whitespace accepted every
row's corpus with a newline glued on, and passed an authored gate that held no
such string for nine of ten benches.

So the probe set is DERIVED. :func:`lexic.generate.generate` walks the same
canonical grammar every seat was translated from, at fixed seeds; each sample
is then edited one character at a time into strings that are mostly NOT in the
language; and the document each row is timed on gets its boundaries poked. The
reference verdict is lexic's own, taken through the compiled artefact the row
is measured against, so the comparison is two-directional by construction — a
seat that accepts a probe lexic refuses fails exactly as loudly as one that
refuses a probe lexic accepts.

The probes are computed ONCE per bench per process and are deterministic, so a
disagreement is replayable by name and seed rather than by rerunning a search.

:func:`unfaithful` is the judgement those probes exist to answer, and it lives
here for that reason: a seat earns a number only by describing the row's
language, and there is one place that decides it.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from lexic.generate import generate
from lexic.ir import IrAst
from tools.benchmark.cases.grammars import Bench
from tools.benchmark.engines.refusals import LEXIC_REFUSALS, accepts, refusal
from tools.benchmark.measurement.sampling import Parse

PROBE_SEEDS: tuple[int, ...] = tuple(range(16))
"""Generation seeds — fixed, so a failing probe is named rather than hunted."""

PROBE_DEPTH = 4
"""Ref-expansion budget per sample; deep enough to reach every arm's shape."""

PROBE_LIMIT = 400
"""Longest generated sample kept — a probe set is a language test, not a load."""

EDIT_CHARS: tuple[str, ...] = (" ", "\t", "\n", "\r", "a", "0", '"', ",")
"""Characters inserted into a sample.

The four whitespace spellings are here because whitespace is what a translation
handles implicitly and therefore wrongly: every engine in this harness offers a
skip-whitespace default, and the grammars have none. The other four are the
ordinary content characters a class either holds or does not.
"""

BOUNDARY_SUFFIXES: tuple[str, ...] = ("\n", " ", "\t", "\r", "  \n")
"""Suffixes glued onto the timed document — where an anchor's slack shows."""

_PROBES: dict[str, tuple[tuple[str, bool], ...]] = {}
"""Bench name → its probes and lexic's verdict on each, built once per process."""


def _samples(ast: IrAst) -> list[str]:
    """One generated string per seed, short enough to edit and re-parse."""
    rules = {str(rule.name): rule for rule in ast.rules}
    start = str(ast.start)
    texts = [
        generate(start, rules, rng=random.Random(seed), max_depth=PROBE_DEPTH)
        for seed in PROBE_SEEDS
    ]
    return [text for text in texts if len(text) <= PROBE_LIMIT]


def _edits(text: str, rng: random.Random) -> list[str]:
    """One sample's single-character neighbours — delete, double, cut, insert."""
    out: list[str] = []
    if text:
        at = rng.randrange(len(text))
        out.append(text[:at] + text[at + 1 :])
        out.append(text[:at] + text[at] * 2 + text[at + 1 :])
        out.append(text[:at])
    for char in EDIT_CHARS:
        at = rng.randrange(len(text) + 1)
        out.append(text[:at] + char + text[at:])
    return out


def _candidates(ast: IrAst, corpus: str) -> list[str]:
    """Every probe string for one bench, deduplicated in generation order."""
    rng = random.Random(0xC0FFEE)
    texts: list[str] = []
    for sample in _samples(ast):
        texts.append(sample)
        texts.extend(_edits(sample, rng))
    texts.extend(corpus + suffix for suffix in BOUNDARY_SUFFIXES)
    texts.extend(suffix + corpus for suffix in BOUNDARY_SUFFIXES)
    texts.append(corpus[:-1])
    return list(dict.fromkeys(texts))


def probes(
    name: str, ast: IrAst, corpus: str, reference: Callable[[str], object]
) -> tuple[tuple[str, bool], ...]:
    """This bench's probe set, each paired with lexic's verdict on it.

    :param name: The bench name, which keys the per-process memo.
    :param ast: The canonical grammar every seat was translated from.
    :param corpus: The document whose boundaries are poked.
    :param reference: lexic's own parse entry — the verdict everything is read
        against.
    :returns: ``(text, lexic accepted it)`` pairs, in a deterministic order.
    """
    held = _PROBES.get(name)
    if held is not None:
        return held
    built = tuple(
        (text, accepts(reference, text, LEXIC_REFUSALS))
        for text in _candidates(ast, corpus)
    )
    _PROBES[name] = built
    return built


def disagreement(
    parse: Callable[[str], object],
    seats: tuple[tuple[str, bool], ...],
    exceptions: tuple[type[BaseException], ...] | None = None,
) -> str | None:
    """The first probe ``parse`` and lexic answer differently on, or None.

    :param parse: The seat's parse entry point.
    :param seats: Probes and lexic's verdict, from :func:`probes`.
    :param exceptions: The refusal vocabulary to read, or None for every one.
    :returns: What disagreed, in the seat's own words where it refused.
    """
    for text, taken in seats:
        why = refusal(parse, text, exceptions)
        if (why is None) == taken:
            continue
        if taken:
            return f"refuses the derived probe {text[:24]!r} — {why}"
        return f"accepts the derived probe {text[:24]!r}, which lexic refuses"
    return None


def unfaithful(
    parse: Parse,
    bench: Bench,
    document: str | None = None,
    exceptions: tuple[type[BaseException], ...] | None = None,
    fixed_language: bool = False,
) -> str | None:
    """The first way ``parse`` disagrees with lexic about the language, or None.

    The single place a translation is judged, in BOTH directions. An
    over-permissive one describes a larger language and passes any accept-only
    check; an over-restrictive one passes the corpus and then refuses a sentence
    nobody sampled — which is what a context-free lexer does to a grammar whose
    character classes overlap. Either way the engine gets no number, because a
    number for a different language is not a faster answer to the question, it
    is an answer to a different one.

    The authored `accepts`/`rejects` are the adversarial sentences a person
    chose; they run first because their names are the most readable failure.
    What decides the question is the DERIVED differential behind them —
    :func:`probes` and :func:`disagreement` — because a sample nobody thought
    of is the only thing that can separate two languages an author believed
    were one.

    :param document: The text this engine will be timed on — the acceptance
        half is checked against exactly that (default: the small corpus).
    :param fixed_language: This seat takes NO grammar. Only the accepting
        direction is then a claim about it, so the refusing one is not asked
        rather than quietly passed.
    """
    why = refusal(
        parse,
        document if document is not None else bench.corpus,
        exceptions,
    )
    if why is not None:
        return f"refuses the corpus — {why}"
    for text in bench.accepts:
        why = refusal(parse, text, exceptions)
        if why is not None:
            return f"refuses {text!r} — {why}"
    if not fixed_language:
        for text in bench.rejects:
            if accepts(parse, text, exceptions):
                return f"accepts {text[:18]!r}, which lexic refuses"
    return disagreement(parse, _case_probes(bench, fixed_language), exceptions)


def _case_probes(
    bench: Bench, accepted_only: bool = False
) -> tuple[tuple[str, bool], ...]:
    """This bench's derived probe set, judged by its own compiled artefact."""
    built = probes(
        bench.name,
        bench.ast,
        bench.corpus,
        lambda text: bench.compiled.parse(text, cores=1),
    )
    return tuple(pair for pair in built if pair[1]) if accepted_only else built
