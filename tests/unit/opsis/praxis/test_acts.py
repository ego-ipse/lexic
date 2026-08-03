"""Acts contract — what deeds are offered, and what performing them does."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest

from lexic.exceptions import UnsupportedConstructError
from lexic.grammars import GBNF_FLAVOUR
from opsis.praxis.acts import deeds, perform
from opsis.praxis.ingress import vocabulary_reader
from opsis.praxis.reading import Reading, Source, _flavour_reader
from opsis.praxis.session import Session
from tests.paths import GROUND_TRUTH

BindVocab = Callable[[Session, Reading, str], Reading]

_TOY = 'root ::= "x"+\n'


def test_deeds_offers_generate_and_twin_only_for_a_compiled_reading(
    tmp_path: Path,
) -> None:
    """A reading with no compiled grammar offers neither generate nor twin."""
    session = Session(tmp_path)
    gname = session.surface(_flavour_reader(GBNF_FLAVOUR))
    grammar = session.add("toy", "grammar", gname, Source(_TOY))
    names = {deed.name for deed in deeds(grammar)}
    assert {"generate", "twin"} <= names

    loose = session.add("loose")
    assert not deeds(loose)


def test_deeds_offers_constrain_only_when_a_tokenizer_is_bound(
    tmp_path: Path, bind_vocab: BindVocab
) -> None:
    """Constrain shows up only once a vocabulary is bound to the grammar."""
    session = Session(tmp_path)
    gname = session.surface(_flavour_reader(GBNF_FLAVOUR))
    vname = session.surface(vocabulary_reader())
    grammar = session.add("toy", "grammar", gname, Source(_TOY))
    assert "constrain" not in {deed.name for deed in deeds(grammar)}

    bind_vocab(session, grammar, vname)
    assert "constrain" in {deed.name for deed in deeds(grammar)}


def test_perform_with_an_unoffered_name_raises_naming_the_offer(
    tmp_path: Path,
) -> None:
    """Asking for a deed a reading does not have names what it DOES offer."""
    session = Session(tmp_path)
    loose = session.add("loose")
    with pytest.raises(UnsupportedConstructError, match="offers"):
        perform(session, loose, "generate")


def test_generate_on_a_compiled_json_grammar_makes_readings_that_all_parse(
    tmp_path: Path,
) -> None:
    """Every generated string opens as a text that the same grammar reads."""
    session = Session(tmp_path)
    gname = session.surface(_flavour_reader(GBNF_FLAVOUR))
    text = (GROUND_TRUTH / "json.gbnf").read_text(encoding="utf-8")
    grammar = session.add("json", "grammar", gname, Source(text))
    assert grammar.compiled is not None

    before = set(session.readings)
    perform(session, grammar, "generate")
    made = [session.readings[i] for i in set(session.readings) - before]

    assert made
    for reading in made:
        assert reading.error == ""
        assert reading.product is not None
