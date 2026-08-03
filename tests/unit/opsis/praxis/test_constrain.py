"""Constrain contract — the token-mask cursor over a bound grammar."""

from __future__ import annotations

from pathlib import Path

import pytest

from ext.API import cache
from lexic.api.json_tokenizer import tokenizer_of
from lexic.compile import compile_from_path
from lexic.exceptions import UnsupportedConstructError
from lexic.grammars.json import JSON_GRAMMAR, JSON_REDUCER
from lexic.ir import IrMap, IrTokenizer
from lexic.parsing import parse_reduced
from opsis.praxis.constrain import Cursors, Prefix, sample
from opsis.praxis.reading import Outcome, Reading
from opsis.praxis.session import Session
from tests.paths import GROUND_TRUTH

_FIXTURE = cache.cached("gpt2")

pytestmark = pytest.mark.skipif(
    _FIXTURE is None,
    reason="real tokenizer fixture absent — run 'uv run python -m ext.API.hf'",
)


@pytest.fixture(scope="module", name="tokenizer")
def _tokenizer() -> IrTokenizer:
    """The real gpt2 vocabulary, reduced once for the whole module."""
    assert _FIXTURE is not None
    text = _FIXTURE.read_text(encoding="utf-8")
    doc = parse_reduced(JSON_GRAMMAR, text, JSON_REDUCER)
    assert isinstance(doc, IrMap)
    return tokenizer_of(doc, "gpt2")


def _reading(tokenizer: IrTokenizer) -> Reading:
    """A reading whose product is the shipped json grammar, bound to ``tokenizer``."""
    compiled = compile_from_path(str(GROUND_TRUTH / "json.gbnf")).bind(tokenizer)
    reading = Reading("r1", "json")
    reading.outcome = Outcome(product=compiled)
    return reading


def test_push_an_id_not_in_the_mask_raises(tokenizer: IrTokenizer) -> None:
    """Pushing an inadmissible token id is refused, not silently accepted."""
    prefix = Prefix(_reading(tokenizer))
    bad = max(prefix.mask()) + 1_000_000
    with pytest.raises(UnsupportedConstructError, match="not admitted"):
        prefix.push(bad)


def test_push_text_with_an_unadmitted_spelling_names_admitted_ones(
    tokenizer: IrTokenizer,
) -> None:
    """A spelling nothing admits is refused, and the message names real ones."""
    prefix = Prefix(_reading(tokenizer))
    preview = sample(prefix.mask(), prefix.vocabulary)
    with pytest.raises(UnsupportedConstructError) as excinfo:
        prefix.push_text("###nothing-admits-this###")
    message = str(excinfo.value)
    assert "###nothing-admits-this###" in message
    assert preview in message


def test_back_on_an_empty_prefix_raises(tokenizer: IrTokenizer) -> None:
    """Undoing before anything was pushed has nothing to undo."""
    prefix = Prefix(_reading(tokenizer))
    with pytest.raises(UnsupportedConstructError, match="nothing pushed"):
        prefix.back()


def test_back_undoes_exactly_one_push(tokenizer: IrTokenizer) -> None:
    """After two pushes, one ``back()`` returns the prefix to the first."""
    prefix = Prefix(_reading(tokenizer))
    prefix.push_text("{")
    after_first = list(prefix.pushed)
    prefix.push_text('"')
    prefix.back()
    assert prefix.pushed == after_first


def test_cursors_of_returns_a_fresh_prefix_after_the_product_changes(
    tmp_path: Path, tokenizer: IrTokenizer
) -> None:
    """A reading's cursor is thrown away once its product is a new object."""
    session = Session(tmp_path)
    reading = _reading(tokenizer)
    session.readings[reading.ident] = reading

    cursors = Cursors()
    first = cursors.of(session, reading.ident)
    first.push_text("{")

    reading.outcome = Outcome(product=_reading(tokenizer).product)
    second = cursors.of(session, reading.ident)
    assert second is not first
    assert second.pushed == []
