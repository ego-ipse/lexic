"""The caller-owns-format seam — a format → Mapping → tokenizer.

A tokenizer is built from a *Mapping*. *How* that Mapping was produced — parsed
from any external format (CSV/JSON/GPT-2 merges/…) via a lexic ``(grammar,
fold)``, or handed in pre-parsed — is the **caller's** concern; ``src`` carries no
format knowledge. This test IS a caller: it authors two tiny format grammars +
folds (a ``token<TAB>id`` vocab file and a ``left right`` merges file, the shapes
real exports lower to), parses fixtures straight into ``IrMap``/``IrTuple`` via the
engine's own ``parse_model`` product, and feeds them to
``IrTokenizer.from_vocab`` / ``from_merges``. It mirrors ``compile/notation`` —
which parses IR-constructor text into real IR the same way.

Scope note: this proves the MODEL carries no format knowledge. `lexic.api`
does ship readers for third-party formats, deliberately — a reader takes the
grammar+reducer that parse its document as parameters, so it privileges no
formulation. What must stay format-free is `lexic.ir`, and that is what this
test pins.
"""

from __future__ import annotations

from typing import Callable

from lexic.compile.foldkit import AuthoredRule, model_fold, product_rules, seq
from lexic.compile.product import bind_symbols, rules_by_name
from lexic.ir import (
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrMap,
    IrNone,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSeq,
    IrSequence,
    IrStr,
    IrTokenizer,
    IrTuple,
)
from lexic.parsing import FieldFold, ModelBinding, ModelBody, parse_model
from lexic.parsing.product import CaptureMode, CaptureSpec, ConstructionTables

_STAR = IrQuantifier(0, IrNone)
_PLUS = IrQuantifier(1, IrNone)


def _lit(text: str) -> IrItem:
    return IrItem(IrLiteral(text))


def _ref(name: str) -> IrItem:
    return IrItem(IrRuleRef(name))


def _rule(name: str, *arms: IrSequence) -> IrRule:
    return IrRule(name, IrAlternation(*arms))


def _make_head_tail(first: object, rest: list | None = None) -> tuple:
    """A start ctor: the head + repeated tail as one flat tuple of dyads."""
    return (first, *(rest or ()))


def _head_tail_fields() -> tuple[FieldFold, FieldFold]:
    """The (head model, tail models) field pair shared by both start rules."""
    return (FieldFold(0, "model", "first", 1), FieldFold(1, "models", "rest", 0))


_ONE = int(CaptureMode.ONE)
_MANY = int(CaptureMode.MANY)
_TEXT = int(CaptureMode.TEXT)

_HEAD_TAIL_CAPTURES = (CaptureSpec(_ONE, 0), CaptureSpec(_MANY, 1))
"""The same head/tail pair as :func:`_head_tail_fields`, said as captures."""


def _binding(
    bodies: dict[str, ModelBody],
    rules: dict[str, AuthoredRule],
    registry: dict[str, Callable[..., object]],
) -> ModelBinding:
    """One fixture format's binding — both halves, from its own registry."""
    product = product_rules(rules)
    return ModelBinding(
        model_fold(bodies),
        rules_by_name(product.rules, product.codes),
        ConstructionTables(symbols=bind_symbols(product.symbols, registry)),
    )


# ── the vocab format: "token<TAB>id" lines → IrMap ───────────────────────

_NOT_TAB_NL = IrCharClass(
    IrRange(IrChr(0), IrChr(8)), IrRange(IrChr(11), IrChr(0x10FFFF))
)
_DIGITS = IrCharClass(IrRange(IrChr("0"), IrChr("9")))

VOCAB_GRAMMAR = IrAst(
    IrSeq(
        _rule("start", IrSequence(_ref("entry"), IrItem(IrRuleRef("entry"), _STAR))),
        _rule(
            "entry",
            IrSequence(
                IrItem(_NOT_TAB_NL, _PLUS),
                _lit("\t"),
                IrItem(_DIGITS, _PLUS),
                _lit("\n"),
            ),
        ),
    ),
    "start",
)


def _make_vocab(first: IrTuple, rest: list | None = None) -> IrMap:
    """start ctor: the collected spelling→id dyads as the vocab IrMap."""
    return IrMap(*_make_head_tail(first, rest))


def _make_entry(token: str, num: str) -> IrTuple:
    """entry ctor: one spelling→id dyad, IR-native."""
    return IrTuple(IrStr(token), IrChr(int(num)))


VOCAB_BINDING = _binding(
    {
        "start": seq(_make_vocab, 2, _head_tail_fields()),
        "entry": seq(
            _make_entry,
            4,
            (FieldFold(0, "text", "token", 1), FieldFold(2, "text", "num", 1)),
        ),
    },
    {
        "start": AuthoredRule("make_vocab", _HEAD_TAIL_CAPTURES, ("first", "rest"), 2),
        "entry": AuthoredRule(
            "make_entry",
            (CaptureSpec(_TEXT, 0), CaptureSpec(_TEXT, 2)),
            ("token", "num"),
            4,
        ),
    },
    {"make_vocab": _make_vocab, "make_entry": _make_entry},
)


# ── the merges format: "left right" lines → IrTuple (rank = position) ─────

_NOT_SP_NL = IrCharClass(
    IrRange(IrChr(0), IrChr(8)),
    IrRange(IrChr(11), IrChr(31)),
    IrRange(IrChr(33), IrChr(0x10FFFF)),
)

MERGES_GRAMMAR = IrAst(
    IrSeq(
        _rule("start", IrSequence(_ref("mline"), IrItem(IrRuleRef("mline"), _STAR))),
        _rule(
            "mline",
            IrSequence(
                IrItem(_NOT_SP_NL, _PLUS),
                _lit(" "),
                IrItem(_NOT_SP_NL, _PLUS),
                _lit("\n"),
            ),
        ),
    ),
    "start",
)


def _make_merges(first: IrTuple, rest: list | None = None) -> IrTuple:
    """start ctor: the ordered merge dyads as one IrTuple (rank = position)."""
    return IrTuple(*_make_head_tail(first, rest))


def _make_dyad(left: str, right: str) -> IrTuple:
    """mline ctor: one (left, right) merge dyad, IR-native."""
    return IrTuple(IrStr(left), IrStr(right))


MERGES_BINDING = _binding(
    {
        "start": seq(_make_merges, 2, _head_tail_fields()),
        "mline": seq(
            _make_dyad,
            4,
            (FieldFold(0, "text", "left", 1), FieldFold(2, "text", "right", 1)),
        ),
    },
    {
        "start": AuthoredRule("make_merges", _HEAD_TAIL_CAPTURES, ("first", "rest"), 2),
        "mline": AuthoredRule(
            "make_dyad",
            (CaptureSpec(_TEXT, 0), CaptureSpec(_TEXT, 2)),
            ("left", "right"),
            4,
        ),
    },
    {"make_merges": _make_merges, "make_dyad": _make_dyad},
)


# ── the vocab seam ───────────────────────────────────────────────────────

_VOCAB_FIXTURE = "<think>\t0\n</think>\t1\n hi \t2\n"


def test_vocab_format_parses_to_irmap() -> None:
    """The vocab format text parses straight into a real ``IrMap``."""
    vocab = parse_model(VOCAB_GRAMMAR, _VOCAB_FIXTURE, VOCAB_BINDING)
    assert isinstance(vocab, IrMap)
    assert vocab.get(IrStr("<think>")) == IrChr(0)
    assert vocab.get(IrStr(" hi ")) == IrChr(2)


def test_vocab_format_builds_a_working_tokenizer() -> None:
    """The parsed vocab drives a longest-match tokenizer that round-trips."""
    vocab = parse_model(VOCAB_GRAMMAR, _VOCAB_FIXTURE, VOCAB_BINDING)
    tok = IrTokenizer.from_vocab("fixture", vocab)
    text = "<think> hi </think>"
    assert tok.tokenize(text) == [0, 2, 1]
    assert "".join(str(tok.spell(i)) for i in tok.tokenize(text)) == text


# ── the merges seam ──────────────────────────────────────────────────────

_MERGES_FIXTURE = "a b\nab c\n"


def _bpe_vocab() -> IrMap:
    return IrMap(
        *(
            IrTuple(IrStr(s), IrChr(i))
            for i, s in enumerate(["a", "b", "c", "ab", "abc"])
        )
    )


def test_merges_format_parses_to_ordered_irtuple() -> None:
    """The merges format text parses into an ordered ``IrTuple`` of dyads."""
    merges = parse_model(MERGES_GRAMMAR, _MERGES_FIXTURE, MERGES_BINDING)
    assert merges == IrTuple(
        IrTuple(IrStr("a"), IrStr("b")),
        IrTuple(IrStr("ab"), IrStr("c")),
    )


def test_merges_format_builds_a_bpe_tokenizer() -> None:
    """The parsed merges drive the ranked-merge (BPE) segmentation."""
    merges = parse_model(MERGES_GRAMMAR, _MERGES_FIXTURE, MERGES_BINDING)
    tok = IrTokenizer.from_merges("bpe", _bpe_vocab(), merges)
    assert tok.tokenize("abc") == [4]  # a+b→ab, ab+c→abc (id 4)
