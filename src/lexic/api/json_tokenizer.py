"""The ``tokenizer.json`` serialization format → an :class:`IrTokenizer`.

Three responsibilities, three homes, and this is the middle one:

- **getting** a document is ``ext/API/hf.py``'s — the hub merely hosts files
  written in this format, so fetching is not the format's business and this
  module never reaches the network;
- **reading** one is here;
- **the model** is ``lexic.ir``'s, and it knows nothing of this format. The
  direction is one-way, document → model.

The json formulation is a **parameter**, never an assumption — pass
whichever grammar+reducer pair should read the document, including one
compiled from a ground-truth ``.gbnf``.

Reading is thin because lexic does the parsing: the document arrives as
typed IR values and this only names which field means what. ``Sequence``
nesting in the ``normalizer`` / ``pre_tokenizer`` slots is flattened; a
``Regex`` pattern refuses, because no split spec matches a general regex and
reading one as a literal would lie.
"""

from __future__ import annotations

from pathlib import Path

from lexic.api.pretokens import (
    BYTE_FALLBACK,
    BYTE_LEVEL_REMAP,
    QWEN_PATTERN,
    IrByteLevel,
    IrDigits,
    IrQwenSplit,
    IrSplitMerged,
)
from lexic.compile import Reducer, parse_reduced
from lexic.exceptions import UnsupportedConstructError
from lexic.ir.base import IrNone, IrSelf, IrStr, IrTuple
from lexic.ir.encoding import (
    IrNormalizer,
    IrPretoken,
    IrReplace,
    IrTokenizer,
    IrTokenPipeline,
    IrUnicodeForm,
    IrUnknown,
)
from lexic.ir.mapping import IrMap
from lexic.ir.nodes import IrAst

__all__ = ["PRETOKENS", "read", "read_from_path", "tokenizer_of"]

PRETOKENS: dict[str, type[IrPretoken]] = {
    "Digits": IrDigits,
    "ByteLevel": IrByteLevel,
    "Split": IrSplitMerged,
}
"""Document ``"type"`` → the split spec it names, from
:mod:`lexic.api.pretokens` — this format's own vocabulary, declared beside
it rather than in the spine."""


def read(text: str, grammar: IrAst, reducer: Reducer, *, name: str) -> IrTokenizer:
    """Read a ``tokenizer.json`` document into a tokenizer.

    **Start here.** Of the three entries this is the one that parses AND
    builds: use :func:`read_from_path` when the document is a file, and
    :func:`tokenizer_of` when you already hold the reduction.

    :param text: The document source.
    :param grammar: The json formulation to read it with.
    :param reducer: That formulation's reducer.
    :param name: The tokenizer's name.
    :returns: The tokenizer the document describes.
    :raises UnsupportedConstructError: If the document does not reduce to a
        map, or describes a model this cannot build.
    """
    return tokenizer_of(
        IrMap.ensure(parse_reduced(grammar, text, reducer), "the document"), name
    )


def read_from_path(
    path: str | Path, grammar: IrAst, reducer: Reducer, *, name: str = ""
) -> IrTokenizer:
    """Read a ``tokenizer.json`` file into a tokenizer.

    The path-taking wrapper around :func:`read`, per the repo convention that
    the string-taker gets the unqualified name. It also defaults ``name``
    from the filename, which the string form cannot.

    :param path: The document's path (see :func:`ext.API.hf.cached`).
    :param grammar: The json formulation to read it with.
    :param reducer: That formulation's reducer.
    :param name: The tokenizer's name; defaults to the file's stem up to the
        first dot (``smollm2.tokenizer.json`` → ``smollm2``).
    :returns: The tokenizer the document describes.
    """
    file = Path(path)
    return read(
        file.read_text(encoding="utf-8"),
        grammar,
        reducer,
        name=name or file.name.split(".", 1)[0],
    )


def tokenizer_of(doc: IrMap, name: str) -> IrTokenizer:
    """Build the tokenizer a reduced ``tokenizer.json`` document describes.

    **Pick this when you already have the document.** The other two parse it
    for you; this one does not, and takes no grammar or reducer at all — so
    it is also the entry for a caller who obtained the reduction by some
    other route. Re-parsing instead is not free: a whole-file reduce is ~8 s
    for a 2 MB document and ~30 s for an 11 MB one, which is why the
    real-file suites reduce once and enter here.

    :param doc: The reduced document.
    :param name: The tokenizer's name.
    :returns: The tokenizer the document describes.
    :raises UnsupportedConstructError: On a model this cannot build.
    """
    model = IrMap.ensure(doc[IrStr("model")], "'model'")
    # `type` is the discriminator, but older files (GPT-2's) omit it entirely.
    # Absent means UNSPECIFIED, not "not BPE" — refuse only a declared other.
    kind = model.get(IrStr("type"))
    if kind is not None and kind != "BPE":
        raise UnsupportedConstructError(
            f"tokenizer.json: {kind} model — only BPE is supported"
        )
    _refuse_unsupported_model(model)
    added = [
        IrMap.ensure(t, "an added_tokens entry")
        for t in IrTuple.ensure(doc.get(IrStr("added_tokens"), IrTuple()))
    ]
    _refuse_unsupported_specials(
        added, bool(_normalizers(doc.get(IrStr("normalizer"))))
    )
    return IrTokenizer.from_merges(
        name,
        _vocab(model, added),
        [_dyad(m) for m in IrTuple.ensure(model[IrStr("merges")], "'merges'")],
        pipeline=_pipeline(doc, model, added),
    )


def _vocab(model: IrMap, added: list[IrMap]) -> dict[str, int]:
    """``model.vocab``, extended by any added token it does not already cover.

    Some families list their specials only under ``added_tokens``; the ids
    there are authoritative for exactly those spellings.
    """
    table = IrMap.ensure(model[IrStr("vocab")], "'vocab'")
    vocab = {str(k): int(v) for k, v in table.items()}
    for token in added:
        spelling = str(token[IrStr("content")])
        if spelling not in vocab:
            vocab[spelling] = int(token[IrStr("id")])
    return vocab


def _dyad(merge: IrSelf) -> tuple[str, str]:
    """One merge as ``(left, right)``.

    Both encodings occur in the wild — an ``[l, r]`` array and an ``"l r"``
    string. The array form is the unambiguous one; the string form splits at
    the first space, so a part containing a space needs the array form.
    """
    if not isinstance(merge, IrTuple):
        left, _, right = str(merge).partition(" ")
        return left, right
    if len(merge) != 2:  # else the extra parts would be dropped in silence
        raise UnsupportedConstructError(
            f"tokenizer.json: merge of {len(merge)} parts — expected 2"
        )
    return str(merge[0]), str(merge[1])


def _pipeline(doc: IrMap, model: IrMap, added: list[IrMap]) -> IrTokenPipeline:
    """The text→pieces pipeline, derived from the document's own sections."""
    steps = _steps(doc.get(IrStr("pre_tokenizer")), "pretokenizers")
    byte_level = any(str(s[IrStr("type")]) == "ByteLevel" for s in steps)
    pretokens = [_spec(s) for s in steps if _splits(s)]
    return IrTokenPipeline(
        IrTuple(*(t[IrStr("content")] for t in added)),
        BYTE_LEVEL_REMAP if byte_level else IrMap(),
        IrTuple(*_normalizers(doc.get(IrStr("normalizer")))),
        IrTuple(*pretokens),
        # A json true reduces to IrInt(1); the SPELLING table is this format's.
        BYTE_FALLBACK if model.get(IrStr("byte_fallback")) == 1 else IrMap(),
        _unknown(model),
    )


MODEL_KNOBS = (
    "end_of_word_suffix",
    "continuing_subword_prefix",
    "ignore_merges",
    "dropout",
)
"""Model fields that change segmentation and have no spec here.

Every shipped fixture leaves all four at a default, which is why ignoring
them stayed green — and why ignoring them is still a wrong answer for the
files that do not.
"""


def _is_unset(value: IrSelf | None) -> bool:
    """Whether a document says "not set" — in any of the four spellings.

    Absent, ``null``, ``""`` and ``false`` all occur across the shipped
    fixtures for these same fields: ``ignore_merges`` is absent on one and
    ``false`` on the rest; the two affix knobs are ``""`` on two and ``null``
    on the others. A check written as ``is not None`` refuses three of the
    four real files.
    """
    return value is None or value is IrNone or value == "" or value == 0


def _refuse_unsupported_model(model: IrMap) -> None:
    """Refuse a model knob set to something this reader does not implement.

    The same shape ``_normalizers`` uses: a field that changes what gets
    segmented is refused, not skipped. ``dropout`` is a PERMANENT refusal
    rather than a future feature — it makes tokenization non-deterministic,
    which cannot coexist with round-trip fidelity.

    :raises UnsupportedConstructError: On a non-default knob.
    """
    for knob in MODEL_KNOBS:
        value = model.get(IrStr(knob))
        if not _is_unset(value):
            raise UnsupportedConstructError(
                f"tokenizer.json: {knob!r} is set to {value!r}, which this "
                "reader does not implement — refusing rather than segmenting "
                "as though it were unset"
            )


def _refuse_unsupported_specials(added: list[IrMap], normalized: bool) -> None:
    """Refuse added-token flags that move a token boundary.

    ``lstrip``/``rstrip`` pull adjacent whitespace into the special's span,
    which IS a boundary change. ``normalized`` decides whether the special is
    matched before or after normalization — inert when the document declares
    no normalizer, which is exactly how one shipped fixture sets it, so
    refusing it unconditionally would reject a file that tokenizes fine.

    :param added: The added-token entries.
    :param normalized: Whether the document carries any normalizer.
    :raises UnsupportedConstructError: On a flag that would move a boundary.
    """
    for entry in added:
        for flag in ("lstrip", "rstrip"):
            if entry.get(IrStr(flag)) == 1:
                raise UnsupportedConstructError(
                    f"tokenizer.json: added token "
                    f"{str(entry[IrStr('content')])!r} sets {flag!r}, which "
                    "moves a token boundary"
                )
        if normalized and entry.get(IrStr("normalized")) == 1:
            raise UnsupportedConstructError(
                f"tokenizer.json: added token "
                f"{str(entry[IrStr('content')])!r} is 'normalized' and the "
                "document declares a normalizer — specials are matched before "
                "normalization here, so the two disagree"
            )


def _unknown(model: IrMap) -> IrUnknown:
    """``model.unk_token`` + ``fuse_unk`` as the uncovered-symbol fallback.

    Read rather than refused, because a document may declare an unknown
    token it can never reach: gemma4 does, and its byte fallback covers all
    256 bytes, so nothing uncovered ever gets that far. Refusing the
    declaration would reject a file that tokenizes perfectly.
    """
    unk = model.get(IrStr("unk_token"))
    if unk is None or not isinstance(unk, IrStr):
        return IrUnknown()
    return IrUnknown(str(unk), model.get(IrStr("fuse_unk")) == 1)


def _spec(step: IrMap) -> IrPretoken:
    """One pre-tokenizer step as its split spec.

    :raises UnsupportedConstructError: On a family with no split spec.
    """
    kind = str(step[IrStr("type")])
    if kind not in PRETOKENS:
        raise UnsupportedConstructError(f"tokenizer.json: unsupported {kind!r}")
    if kind == "Digits":
        return IrDigits(step.get(IrStr("individual_digits")) == 1)
    if kind == "Split":
        return _split(step)
    return PRETOKENS[kind]()


def _split(step: IrMap) -> IrPretoken:
    """A ``Split`` step as its spec — a literal separator, or a known pattern.

    A regex is never approximated: only patterns lexic implements by name are
    accepted, and anything else refuses rather than silently mis-segmenting.

    :raises UnsupportedConstructError: On an unimplemented pattern or an
        unsupported behaviour.
    """
    pattern = IrMap.ensure(step[IrStr("pattern")], "'pattern'")
    behaviour = str(step[IrStr("behavior")])
    regex = pattern.get(IrStr("Regex"))
    if regex is not None:
        if str(regex) == QWEN_PATTERN and behaviour == "Isolated":
            return IrQwenSplit()
        raise UnsupportedConstructError(
            f"tokenizer.json: unimplemented Split regex ({behaviour})"
        )
    if behaviour != "MergedWithPrevious":
        raise UnsupportedConstructError(f"tokenizer.json: Split behavior {behaviour}")
    return IrSplitMerged(_pattern(step[IrStr("pattern")]))


def _splits(step: IrMap) -> bool:
    """Whether ``step`` contributes a split at all.

    A byte-level step with ``use_regex: false`` contributes only the byte
    MAPPING — families that pre-split with their own pattern set it that way,
    and adding this pattern on top would corrupt their segmentation. Absent
    means true. The mapping itself follows the step's PRESENCE, so it is
    decided separately.
    """
    if str(step[IrStr("type")]) != "ByteLevel":
        return True
    return step.get(IrStr("use_regex")) != 0


UNICODE_FORMS: dict[str, IrUnicodeForm] = {
    "NFC": IrUnicodeForm("NFC"),
    "NFD": IrUnicodeForm("NFD"),
    "NFKC": IrUnicodeForm("NFKC"),
    "NFKD": IrUnicodeForm("NFKD"),
}
"""Document ``"type"`` → the normalization form it names."""


def _normalizers(node: IrSelf | None) -> list[IrNormalizer]:
    """A normalizer section as ordered spec steps.

    A step with no spec is REFUSED, never skipped: a normalizer changes what
    gets segmented, so ignoring one is not a partial read but a wrong answer
    (dropping ``NFC`` mis-tokenizes every decomposed character).

    :raises UnsupportedConstructError: On a normalizer with no spec.
    """
    steps: list[IrNormalizer] = []
    for step in _steps(node, "normalizers"):
        kind = str(step[IrStr("type")])
        form = UNICODE_FORMS.get(kind)
        if form is not None:
            steps.append(form)
        elif kind == "Replace":
            src = _pattern(step[IrStr("pattern")])
            steps.append(IrReplace(src, str(step[IrStr("content")])))
        else:
            raise UnsupportedConstructError(
                f"tokenizer.json: unimplemented normalizer {kind!r}"
            )
    return steps


def _pattern(pattern: IrSelf) -> str:
    """A step's ``pattern`` as its literal string.

    :raises UnsupportedConstructError: On a non-literal (``Regex``) pattern.
    """
    literal = IrMap.ensure(pattern, "'pattern'").get(IrStr("String"))
    if literal is None:
        raise UnsupportedConstructError(
            f"tokenizer.json: non-literal pattern {pattern}"
        )
    return str(literal)


def _steps(node: IrSelf | None, inner: str) -> list[IrMap]:
    """A section's steps — absent, a single step, or a ``Sequence`` of them."""
    if not isinstance(node, IrMap):
        return []
    if node[IrStr("type")] != "Sequence":
        return [node]
    return [
        IrMap.ensure(s, f"a {inner} step") for s in IrTuple.ensure(node[IrStr(inner)])
    ]
