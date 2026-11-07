"""Fuzz census — generated grammars, every short word, both engines' answers.

Each grammar is four GBNF rules, ``root x y z``, over the alphabet ``a b ;``;
every word up to a length is asked of the predictive engine and of Earley, and
the pair is classified (:func:`kind`). A census is a JSON map from
``{variant}-fuzz{seed}:{index}|{word}`` to ``[kind, gated, predictive]``, the
answers as short hashes, so two censuses of the same generator compare entry by
entry. The variants are the shapes that reach wrong models; one with mostly
unquantified items and refs only downward finds none.

    uv run python -m tools.fuzz_census run OUT.json [--variants B,D,E] [--seeds 1,2,3]
    uv run python -m tools.fuzz_census compare BASE.json HEAD.json

To census another tree, put its ``src`` first on ``PYTHONPATH``.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import NamedTuple

from lexic.compile import CompiledGrammar, compile_text
from lexic.exceptions import LexicError, UnsupportedConstructError
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.products import ModelProduct, earley_model, model_product, pda_model

ALPHABET = "ab;"
ATOMS = ('"a"', '"b"', '";"', '"ab"', "[ab]", "[a;]")
DOWNWARD = {"root": ("x", "y", "z"), "x": ("y", "z"), "y": ("z",), "z": ()}
CYCLIC = {"root": ("x", "y", "z"), "x": ("y", "z"), "y": ("z", "x"), "z": ("x", "y")}
CRASHES = (
    AssertionError,
    AttributeError,
    IndexError,
    KeyError,
    RecursionError,
    TypeError,
    ValueError,
)
"""What a predictive parse raises when it breaks rather than declines or refuses."""
DECLINED = "declined"
REFUSED = "refused"


class Variant(NamedTuple):
    """One generator shape.

    :ivar quants: The quantifier suffixes an item draws from, uniformly.
    :ivar max_arms: A rule's arms, drawn from ``1..max_arms``.
    :ivar max_items: An arm's items, drawn from ``1..max_items``.
    :ivar ref_weight: How many times each allowed reference joins the atoms drawn.
    :ivar refs: The rules each rule may reference, in definition order.
    """

    quants: tuple[str, ...]
    max_arms: int
    max_items: int
    ref_weight: int
    refs: Mapping[str, tuple[str, ...]]


UNIFORM = ("", "?", "*", "+")
VARIANTS = {
    "B": Variant(UNIFORM, 3, 3, 2, DOWNWARD),
    "D": Variant(UNIFORM, 3, 4, 3, DOWNWARD),
    "E": Variant(UNIFORM, 3, 3, 2, CYCLIC),
}


class Answer(NamedTuple):
    """One word's census entry: its :func:`kind` and both answers' hashes."""

    kind: str
    gated: str
    predictive: str


def grammar(variant: Variant, rng: random.Random) -> str:
    """One generated grammar's GBNF source, drawn from ``rng``."""
    lines = []
    for rule, refs in variant.refs.items():
        pool = ATOMS + refs * variant.ref_weight
        arms = (
            " ".join(
                rng.choice(pool) + rng.choice(variant.quants)
                for _ in range(rng.randint(1, variant.max_items))
            )
            for _ in range(rng.randint(1, variant.max_arms))
        )
        lines.append(f"{rule} ::= {' | '.join(arms)}\n")
    return "".join(lines)


def words(length: int) -> list[str]:
    """Every word over :data:`ALPHABET` of length ``1..length``, shortest first."""
    return [
        "".join(w)
        for n in range(1, length + 1)
        for w in itertools.product(ALPHABET, repeat=n)
    ]


def kind(predictive: str, gated: str) -> str:
    """Classify one word from both engines' rendered answers.

    :param predictive: The predictive model's ``repr``, :data:`DECLINED` or
        :data:`REFUSED`.
    :param gated: Earley's model ``repr`` or :data:`REFUSED`.
    :returns: ``EQUAL``, ``BOTH_REFUSE``, ``DECLINED`` (Earley answers),
        ``DECLINED_REFUSED`` (Earley refuses) or ``WRONG`` — a predictive
        model Earley does not build, a refused text included.
    """
    if predictive == DECLINED:
        return "DECLINED_REFUSED" if gated == REFUSED else "DECLINED"
    if predictive == gated:
        return "BOTH_REFUSE" if gated == REFUSED else "EQUAL"
    return "WRONG"


def _short(text: str) -> str:
    """A 12-hex-digit digest of one rendered answer."""
    return hashlib.blake2b(text.encode(), digest_size=6).hexdigest()


def _gated(compiled: CompiledGrammar, product: ModelProduct, text: str) -> str:
    """Earley's answer, rendered."""
    try:
        return repr(
            earley_model(
                product.instance_grammar, text, compiled.product, product.tables
            )
        )
    except UnsupportedConstructError:
        return REFUSED


def classify(compiled: CompiledGrammar, product: ModelProduct, text: str) -> Answer:
    """Ask both engines about ``text``; a predictive :data:`CRASHES` exception is
    the census's ``CRASH:<type>``."""
    gated = _gated(compiled, product, text)
    try:
        predictive = repr(pda_model(product.pda, text, compiled.product.executor))
    except PdaFail:
        predictive = DECLINED
    except UnsupportedConstructError:
        predictive = REFUSED
    except CRASHES as exc:
        return Answer(f"CRASH:{type(exc).__name__}", _short(gated), "")
    return Answer(kind(predictive, gated), _short(gated), _short(predictive))


def census(
    variants: Iterable[str], seeds: Iterable[int], count: int, length: int
) -> dict[str, Answer]:
    """Every word of ``count`` grammars per variant and seed, classified."""
    found: dict[str, Answer] = {}
    texts = words(length)
    for name, seed in itertools.product(variants, seeds):
        rng = random.Random(seed)
        for index in range(count):
            found.update(
                _one_grammar(f"{name}-fuzz{seed}:{index}", VARIANTS[name], rng, texts)
            )
    return found


def _one_grammar(
    key: str, variant: Variant, rng: random.Random, texts: Sequence[str]
) -> dict[str, Answer]:
    """One generated grammar's entries; one that does not compile is one entry."""
    source = grammar(variant, rng)
    try:
        compiled = compile_text(source, cache_key=f"fuzz-census-{key}-{source}")
        product = model_product(compiled.codegen_grammar, compiled.product)
    except LexicError as exc:
        return {key: Answer(f"COMPILE:{type(exc).__name__}", "", "")}
    return {f"{key}|{text}": classify(compiled, product, text) for text in texts}


def moves(
    base: Mapping[str, Sequence[str]], head: Mapping[str, Sequence[str]]
) -> Counter[tuple[str, str]]:
    """``(base kind, head kind)`` counts over every entry whose answer changed;
    a kind kept with a different answer reads ``"<kind> (answer differs)"``."""
    found: Counter[tuple[str, str]] = Counter()
    for key in base.keys() | head.keys():
        was, now = tuple(base.get(key, ("ABSENT",))), tuple(head.get(key, ("ABSENT",)))
        if was != now:
            found[
                (was[0], now[0] if now[0] != was[0] else f"{now[0]} (answer differs)")
            ] += 1
    return found


def new_wrong(
    base: Mapping[str, Sequence[str]], head: Mapping[str, Sequence[str]]
) -> list[str]:
    """The entries head classifies WRONG or a crash that base did not, sorted."""
    bad = ("WRONG", "CRASH:")
    return sorted(
        key
        for key, now in head.items()
        if now[0].startswith(bad) and tuple(base.get(key, ("",))) != tuple(now)
    )


def _run(args: argparse.Namespace) -> None:
    """The ``run`` subcommand."""
    found = census(
        args.variants.split(","),
        [int(s) for s in args.seeds.split(",")],
        args.grammars,
        args.length,
    )
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(found, fh)
    print(dict(sorted(Counter(a.kind for a in found.values()).items())))


def _compare(args: argparse.Namespace) -> None:
    """The ``compare`` subcommand."""
    with open(args.base, encoding="utf-8") as fh:
        base = json.load(fh)
    with open(args.head, encoding="utf-8") as fh:
        head = json.load(fh)
    for (was, now), n in sorted(moves(base, head).items()):
        print(f"{was:20s} -> {now:32s} {n:7d}")
    fresh = new_wrong(base, head)
    print(f"new WRONG or crash: {len(fresh)}", *fresh[:20], sep="\n  ")


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line and run one subcommand."""
    parser = argparse.ArgumentParser(prog="tools.fuzz_census", description=__doc__)
    sub = parser.add_subparsers(required=True)
    run = sub.add_parser("run", help="census the lexic on sys.path")
    run.add_argument("out")
    run.add_argument("--variants", default="B,D,E")
    run.add_argument("--seeds", default="1,2,3")
    run.add_argument("--grammars", type=int, default=300)
    run.add_argument("--length", type=int, default=5)
    run.set_defaults(handler=_run)
    cmp = sub.add_parser("compare", help="base vs head: moves and new WRONG")
    cmp.add_argument("base")
    cmp.add_argument("head")
    cmp.set_defaults(handler=_compare)
    args = parser.parse_args(argv)
    args.handler(args)


if __name__ == "__main__":
    main()
