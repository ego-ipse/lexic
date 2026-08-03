"""What a node offers — as data, and grouped so it can be worn.

The fan is not a list somebody typed into a function. It is a table:
each entry says what it is called, what it opens, and what has to be
true of a reading for it to be there at all. Being a table is what lets
it be inspected in the registry window beside every other table lexic
dispatches on — and, in time, edited the way the scene is.

Grouping is the second half. A reading with twenty readings of its own
is not a fan, it is a wall; so entries fall into a handful of groups,
and a group rides as ONE moon whose own orbit opens in place.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from lexic.compile import CompiledGrammar
from lexic.model import GrammarModel
from opsis.praxis.reading import Reading

__all__ = ["GROUPS", "OFFERS", "Group", "Offer", "offered"]

Test = Callable[["Fan"], bool]
"""What has to be true of a reading for an entry to be offered."""


class Fan(NamedTuple):
    """What the fan gets to look at — a reading, and what read it.

    A record rather than two arguments, because every test asks about
    the same pair and threading them separately invites one of them to
    go missing.
    """

    reading: Reading
    read_by: CompiledGrammar | None = None
    grammar: CompiledGrammar | None = None


class Offer(NamedTuple):
    """One thing a node can open, and when it can."""

    kind: str
    label: str
    group: str
    when: Test


class Group(NamedTuple):
    """A handful of offers, worn as one moon."""

    name: str
    label: str


GROUPS: tuple[Group, ...] = (
    Group("its text", "text"),
    Group("shape", "shape"),
    Group("product", "product ▲"),
    Group("engine", "engine"),
    Group("tokens", "tokens"),
    Group("do", "do"),
    Group("meta", "meta"),
)
"""The orbits a node wears, in the order they ride.

Seven, because a fan you cannot take in at a glance is a wall. Every
offer belongs to exactly one, and a group with nothing in it is not
drawn — an empty orbit is not a category, it is a gap.
"""


def _has_grammar(fan: Fan) -> bool:
    """Whether this reading IS a grammar, however it came to be one."""
    return fan.grammar is not None


def _read(fan: Fan) -> bool:
    """Whether something above actually read this one."""
    return fan.read_by is not None


def _is_model(fan: Fan) -> bool:
    """Whether what came back is a parsed model."""
    return isinstance(fan.reading.product, GrammarModel)


def _has_product(fan: Fan) -> bool:
    """Whether something came back that is not itself a grammar."""
    return fan.reading.product is not None and fan.reading.compiled is None


def _bound(fan: Fan) -> bool:
    """Whether a vocabulary is docked to this grammar."""
    return fan.grammar is not None and fan.grammar.tokens.tokenizer is not None


def _segments(fan: Fan) -> bool:
    """Whether the grammar above reads this text as tokens."""
    return fan.read_by is not None and fan.read_by.tokens.segmented


def _flavour(fan: Fan) -> bool:
    """Whether this reading produced a reader."""
    return fan.reading.flavour is not None


def _loose(fan: Fan) -> bool:
    """Whether nothing reads this one yet."""
    return not fan.reading.reader


def _always(_fan: Fan) -> bool:
    """Offered wherever the group is."""
    return True


OFFERS: tuple[Offer, ...] = (
    Offer("text", "the text", "its text", _always),
    Offer("rules", "rules", "shape", _has_grammar),
    Offer("railroad", "railroad", "shape", _has_grammar),
    Offer("doc", "document", "shape", _has_grammar),
    Offer("binding", "binding", "shape", _has_grammar),
    Offer("fold", "fold", "shape", _has_grammar),
    Offer("runs", "runs", "shape", _has_grammar),
    Offer("pipeline", "pipeline", "shape", _has_grammar),
    Offer("module", "module", "shape", _has_grammar),
    Offer("instance", "instance", "product", lambda f: f.reading.instance is not None),
    Offer("product", "what it built", "product", _has_product),
    Offer("semantic", "semantic", "product", _is_model),
    Offer("regrammar", "its grammar", "product", _is_model),
    Offer("reader", "read by", "product", _read),
    Offer("floor", "the floor", "engine", _read),
    Offer("forest", "forest", "engine", _read),
    Offer("derivations", "derivations", "engine", _read),
    Offer("chart", "chart", "engine", _read),
    Offer("execution", "what ran", "engine", _read),
    Offer("analysis", "verdicts", "engine", _has_grammar),
    Offer("tables", "tables", "engine", _has_grammar),
    Offer("resume", "resume", "engine", _has_grammar),
    Offer(
        "vocabulary", "vocabulary", "tokens", lambda f: f.reading.tokenizer is not None
    ),
    Offer("tokens", "binding", "tokens", _has_grammar),
    Offer("bound", "bound to", "tokens", _bound),
    Offer("plug", "plug ⊕", "tokens", lambda f: bool(_wanted(f))),
    Offer("segmentation", "its tokens", "tokens", _segments),
    Offer("carve", "template", "do", _has_grammar),
    Offer("flavour", "what it IS", "meta", _flavour),
    Offer("dispatch", "its tables", "meta", _flavour),
    Offer("lanes", "lanes ≅", "meta", _has_grammar),
    Offer("registry", "the registry", "meta", _loose),
)
"""Kind → what it is called, which orbit it rides, and when it is there.

Open and declarative: an offer that has no business on a reading is
absent because its own test says so, never because a branch forgot it.
"""


def _wanted(fan: Fan) -> list[str]:
    """The encoding names this reading asks to be read under."""
    from opsis.praxis.session import alphabets

    return alphabets(fan.reading.instance)


def offered(fan: Fan, deeds: tuple[tuple[str, str], ...] = ()) -> list[Offer]:
    """Every offer this reading actually has, deeds folded in.

    :param fan: The reading and what read it.
    :param deeds: ``(name, label)`` per deed, which are offers too —
        they just come from what a reading can DO rather than from what
        it has.
    """
    out = [offer for offer in OFFERS if offer.when(fan)]
    out += [Offer(f"do:{name}", label, "do", _always) for name, label in deeds]
    return out
