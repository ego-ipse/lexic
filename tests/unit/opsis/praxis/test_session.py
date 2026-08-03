"""Session contract — idents, naming, the re-read cascade, alphabets."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from lexic.compile import parse_grammar
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from opsis.praxis.ingress.ingress import vocabulary_reader
from opsis.praxis.reading import Reading, Source, _flavour_reader
from opsis.praxis.session import Session, alphabets
from tests.paths import GROUND_TRUTH

BindVocab = Callable[[Session, Reading, str], Reading]

_TOY = 'root ::= "x"+\n'


def _seeded(tmp_path: Path) -> tuple[Session, str]:
    """A session carrying the GBNF flavour as a surface reader."""
    session = Session(tmp_path)
    name = session.surface(_flavour_reader(GBNF_FLAVOUR))
    return session, name


def test_add_assigns_increasing_idents(tmp_path: Path) -> None:
    """Each new reading takes the next ``r<n>`` name in sequence."""
    session, _ = _seeded(tmp_path)
    first = session.add("a")
    second = session.add("b")
    assert first.ident == "r1"
    assert second.ident == "r2"


def test_claim_moves_the_counter_past_a_restored_ident(tmp_path: Path) -> None:
    """Claiming a restored ident stops a new reading from reusing its name."""
    session, _ = _seeded(tmp_path)
    session.add("a")
    session.claim("r7")
    third = session.add("c")
    assert third.ident == "r8"


def test_name_reader_refuses_self_reading(tmp_path: Path) -> None:
    """A reading cannot be named as its own reader."""
    session, _ = _seeded(tmp_path)
    a = session.add("a")
    with pytest.raises(UnsupportedConstructError, match="cannot read itself"):
        session.name_reader(a.ident, a.ident)


def test_name_reader_refuses_a_cycle(tmp_path: Path) -> None:
    """Naming a reader that is already downstream of this reading closes a loop."""
    session, _ = _seeded(tmp_path)
    a = session.add("a")
    b = session.add("b")
    session.name_reader(b.ident, a.ident)
    with pytest.raises(UnsupportedConstructError, match="circle"):
        session.name_reader(a.ident, b.ident)


def test_read_records_a_refusal_instead_of_raising(tmp_path: Path) -> None:
    """A text that does not parse leaves the session in a legal, drawn state."""
    session, name = _seeded(tmp_path)
    bad = session.add(
        "bad grammar", "grammar", name, Source("root ::= ((( unterminated")
    )
    assert bad.error != ""
    assert bad.product is None


def test_edit_cascades_through_a_bound_reading(
    tmp_path: Path, bind_vocab: BindVocab
) -> None:
    """Editing a vocabulary re-reads the grammar bound to it, and its readers."""
    session, gname = _seeded(tmp_path)
    vname = session.surface(vocabulary_reader())
    grammar = session.add("toy", "grammar", gname, Source(_TOY))
    vocab = bind_vocab(session, grammar, vname)
    assert grammar.params.bound == vocab.ident
    assert grammar.compiled is not None
    assert grammar.compiled.tokens.tokenizer is vocab.tokenizer

    text = session.add("text", "text", grammar.ident, Source("xx"))
    before = id(text.product)

    session.edit(vocab.ident, '{"model": {"vocab": {"a": 0, "b": 1}, "merges": []}}')
    assert grammar.compiled is not None
    assert grammar.compiled.tokens.tokenizer is vocab.tokenizer
    assert id(text.product) != before


def test_drop_removes_a_reading_and_the_child_survives(tmp_path: Path) -> None:
    """Dropping a reading clears anyone naming it, but does not remove them."""
    session, name = _seeded(tmp_path)
    parent = session.add("parent", "grammar", name, Source(_TOY))
    child = session.add("child", "text", parent.ident, Source("x"))
    assert child.reader == parent.ident

    gone = session.drop(parent.ident)
    assert gone is not None
    assert gone.title == "parent"
    assert parent.ident not in session.readings
    assert child.ident in session.readings
    assert session.readings[child.ident].reader == ""


def test_drop_of_an_unknown_ident_returns_none(tmp_path: Path) -> None:
    """Dropping a reading that is not there is a no-op, not a refusal."""
    session, _ = _seeded(tmp_path)
    assert session.drop("nope") is None


def test_bind_refuses_binding_a_reading_to_itself(tmp_path: Path) -> None:
    """A grammar cannot serve as its own vocabulary."""
    session, name = _seeded(tmp_path)
    grammar = session.add("toy", "grammar", name, Source(_TOY))
    with pytest.raises(UnsupportedConstructError, match="own vocabulary"):
        session.bind(grammar.ident, grammar.ident)


def test_alphabets_of_a_non_ir_node_is_empty() -> None:
    """A node with no alphabets — including a non-``IrSelf`` value — asks for none."""
    assert not alphabets(object())


def test_alphabets_of_think_gbnf_asks_for_tokens() -> None:
    """think.gbnf's token terminals ask to be read under the ``tokens`` encoding."""
    text = (GROUND_TRUTH / "think.gbnf").read_text(encoding="utf-8")
    ast = parse_grammar(text, GBNF_FLAVOUR)
    assert alphabets(ast) == ["tokens"]


def test_alphabets_of_json_gbnf_asks_for_none() -> None:
    """A plain char grammar asks for no vocabulary at all."""
    text = (GROUND_TRUTH / "json.gbnf").read_text(encoding="utf-8")
    ast = parse_grammar(text, GBNF_FLAVOUR)
    assert not alphabets(ast)
