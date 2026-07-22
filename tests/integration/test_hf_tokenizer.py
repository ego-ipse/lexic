"""A *proper* HF ``tokenizer.json`` → lexic ``IrTokenizer``, end to end.

The strongest form of the D1 caller-owns-format seam: a genuine Hugging Face
``tokenizer.json`` (the full BPE schema — ``version``/``added_tokens``/
``normalizer``/``pre_tokenizer``/``model`` with ``vocab`` + ``merges``) is parsed
**by lexic itself** (the shared ``json.gbnf`` grammar, dogfooded — no stdlib
json anywhere), a semantic walker lifts the parsed model to Python values (the
"slight difference in the reduction" — same grammar, a value-yielding read), and
``model.vocab`` / ``model.merges`` drive ``IrTokenizer.from_merges``. HF is a
*template on top of json*: the format lives entirely here in the caller/test,
``src`` carries no HF/json knowledge, and the resulting tokenizer reproduces the
reference BPE segmentation exactly.
"""

from __future__ import annotations

from pathlib import Path

from lexic.compile import compile_from_path
from lexic.ir.base import IrStr, IrTuple
from lexic.ir.encoding import IrTokenizer
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import IrChr
from lexic.model import GrammarModel
from tests.paths import GROUND_TRUTH

_FIXTURE = Path(__file__).parent / "fixtures" / "hf_bpe.tokenizer.json"


# The synthesized json models carry per-grammar fields not on the ``GrammarModel``
# base, so navigation goes through ``getattr`` (the repo idiom — see
# ``test_model_surface_freeze``), dispatched on the runtime class name.


def _string_text(string_model: GrammarModel) -> str:
    """The content of a json ``String`` model — its char leaves (ASCII fixture)."""
    return "".join(getattr(c, "value") for c in getattr(string_model, "char"))


_CONSTANTS: dict[str, object] = {
    "True_": True,
    "False": False,
    "False_": False,
    "Null": None,
}


def _json_value(node: GrammarModel) -> object:
    """Lift a parsed lexic json value model to its Python value — the semantic
    read over ``json.gbnf`` (dogfood; no stdlib json).

    :param node: A ``value``-arm model (``Object``/``Array``/``String``/…).
    :returns: The dict / list / str / int / bool / None it denotes.
    """
    kind = type(node).__name__
    if kind == "Object":
        return _object(node)
    if kind == "Array":
        return _array(node)
    if kind == "String":
        return _string_text(node)
    if kind == "Number":
        return int(node.to_text())
    if kind in _CONSTANTS:
        return _CONSTANTS[kind]
    raise AssertionError(f"unexpected json node {kind}")


def _member(member: GrammarModel) -> tuple[str, object]:
    """A json object ``member`` model → its ``(key, value)`` pair."""
    return _string_text(getattr(member, "string")), _json_value(
        getattr(member, "value")
    )


def _object(node: GrammarModel) -> dict[str, object]:
    """A json ``Object`` model → ``{key: value}`` (empty when it matched ``{}``)."""
    items = getattr(node, "object_item2")
    if items is None:
        return {}
    out = dict([_member(getattr(items, "member"))])
    for tail in getattr(items, "object_item"):
        out.update([_member(getattr(tail, "member"))])
    return out


def _array(node: GrammarModel) -> list[object]:
    """A json ``Array`` model → ``[value, …]`` (empty when it matched ``[]``)."""
    items = getattr(node, "array_item2")
    if items is None:
        return []
    head = _json_value(getattr(items, "value"))
    return [head] + [
        _json_value(getattr(t, "value")) for t in getattr(items, "array_item")
    ]


def _load_hf() -> dict[str, object]:
    """Parse the HF ``tokenizer.json`` fixture with lexic's own json grammar."""
    text = _FIXTURE.read_text(encoding="utf-8")
    cg = compile_from_path(GROUND_TRUTH / "json.gbnf")
    doc = _json_value(getattr(cg.parse(text), "value"))
    assert isinstance(doc, dict)
    return doc


def _added_specials(doc: dict[str, object]) -> IrTuple:
    """The HF ``added_tokens`` content strings → the atomic-match ``specials``."""
    added = doc["added_tokens"]
    assert isinstance(added, list)
    return IrTuple(*(IrStr(str(_content(a))) for a in added))


def _content(added: object) -> object:
    """One ``added_tokens`` entry's ``content`` field."""
    assert isinstance(added, dict)
    return added["content"]


def _tokenizer_from_hf(doc: dict[str, object]) -> IrTokenizer:
    """The HF template: vocab + merges + added_tokens → ``IrTokenizer.from_merges``."""
    model = doc["model"]
    assert isinstance(model, dict)
    vocab = model["vocab"]
    merges = model["merges"]
    assert isinstance(vocab, dict) and isinstance(merges, list)
    encode = IrMap(*(IrTuple(IrStr(t), IrChr(i)) for t, i in vocab.items()))
    dyads = IrTuple(
        *(IrTuple(IrStr(a), IrStr(b)) for a, b in (str(m).split(" ") for m in merges))
    )
    return IrTokenizer.from_merges("hf-bpe", encode, dyads, _added_specials(doc))


def test_hf_tokenizer_json_parses_via_lexic() -> None:
    """The full HF schema parses through lexic's json grammar (no stdlib json)."""
    doc = _load_hf()
    assert doc["version"] == "1.0"
    assert _added_specials(doc) == IrTuple(IrStr("<think>"), IrStr("</think>"))
    model = doc["model"]
    assert isinstance(model, dict)
    assert model["type"] == "BPE"
    assert model["vocab"]["abc"] == 4 and model["vocab"]["<think>"] == 5
    assert model["merges"] == ["a b", "ab c"]


def test_hf_tokenizer_builds_from_merges() -> None:
    """The HF (vocab, merges) build a merge-carrying ``IrTokenizer``."""
    tok = _tokenizer_from_hf(_load_hf())
    assert tok.merges == IrTuple(
        IrTuple(IrStr("a"), IrStr("b")),
        IrTuple(IrStr("ab"), IrStr("c")),
    )
    assert tok.resolve("abc") == IrChr(4)


def test_hf_tokenizer_reproduces_reference_bpe() -> None:
    """The tokenizer reproduces the reference ranked-merge (BPE) segmentation."""
    tok = _tokenizer_from_hf(_load_hf())
    # a+b→ab (merge 0), ab+c→abc (merge 1): the whole word collapses to one token.
    assert tok.tokenize("abc") == [4]
    # 'abcab' → 'abc' then 'ab': ids 4, 3.
    assert tok.tokenize("abcab") == [4, 3]
    # single unmerged symbols stay separate.
    assert tok.tokenize("acb") == [0, 2, 1]


def test_hf_special_tokens_match_atomically() -> None:
    """HF ``added_tokens`` (``<think>``/``</think>``) are one token each, even
    though BPE runs on the ``abc`` content between them."""
    tok = _tokenizer_from_hf(_load_hf())
    assert tok.tokenize("<think>abc</think>") == [5, 4, 6]


def test_hf_tokenizer_round_trips_text() -> None:
    """Spelling the segmented ids back reconstructs the original text."""
    tok = _tokenizer_from_hf(_load_hf())
    text = "abcab"
    assert "".join(str(tok.spell(i)) for i in tok.tokenize(text)) == text
