"""The IR-constructor notation — text → real ``lexic.ir`` objects.

``load_ir(text)`` parses IR-constructor notation and returns the ``IrSelf`` it
evaluates to — so ``load_ir(repr(node))`` reconstructs ``node``. It is the
flagship *supplied* binding: one **generic-apply** grammar (left-factored,
FIRST-disjoint, PDA-speed) plus a curated **symbol table** drive the engine's
own :func:`~lexic.parsing.parse_model` product. A rule of the grammar names no
IR class; every constructor name resolves through :data:`SYMBOLS` at fold time
(``SYMBOLS[name](*args)`` — positional apply onto the raw IR classes, whose own
``__new__`` coercion does the rest). Adding an IR node type is therefore *one
symbol-table entry, zero grammar change*.

The notation is a strict **superset** of :func:`repr` output: it accepts
per-tail default elision (``IrItem(x)`` == ``IrItem(x, IrQuantifier(1, 1))``),
generous whitespace, ``#`` line comments, and both Python quote styles, and
converges every spelling onto the same node. The round-trip fixpoint
``repr(load_ir(repr(x))) == repr(x)`` holds for canonical spellings.

Design notes:

- **The symbol table is the no-exec boundary** (:data:`SYMBOLS`): only
  ``IrSelf``-subclass constructors plus a fixed set of named singletons /
  bools / the boundary exception are reachable. There is no ``exec``/``eval``.
- **Engine sentinels are singleton classes**: the engine identity-checks them
  (``node is YIELD``, ``body is DROP``), so ``Yield()`` in the notation must be
  THE singleton rather than a repr-equal twin. That holds by construction —
  each is an :class:`~lexic.ir.meta.IrSingleton` — rather than by a table of
  which classes to intern, which is one entry away from a silent wrong answer.
- **Structural string decode** (:func:`_decode_escapes`): the grammar carries
  one rule per escape kind (short / ``\\xNN`` / ``\\uNNNN`` / ``\\UNNNNNNNN``,
  the ``grammars/gbnf.py`` precedent); the reassembled raw body is decoded by a
  named def (permitted compile-side).
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import cast

import lexic.ir.action as _action
import lexic.ir.bind as _bind
import lexic.ir.encoding as _encoding
import lexic.ir.flavour as _flavour
import lexic.ir.layout as _layout
import lexic.ir.mapping as _mapping
import lexic.ir.nodes as _nodes
import lexic.ir.operators as _operators
import lexic.ir.records as _records
import lexic.ir.scalars as _scalars
import lexic.ir.spine as _spine
from lexic.compile.foldkit import (
    ABSENT,
    ALT_BODY,
    DECODE_INT,
    absent_tail,
    first_rest,
    model_fold,
    passthrough,
    seq,
)
from lexic.exceptions import UnsupportedConstructError
from lexic.ir import (
    IR_DEFAULT,
    IrAlternation,
    IrAst,
    IrCharClass,
    IrChr,
    IrItem,
    IrLiteral,
    IrNone,
    IrQuantifier,
    IrRange,
    IrRule,
    IrRuleRef,
    IrSelf,
    IrSeq,
    IrSequence,
)
from lexic.parsing import FieldFold, ModelBody, parse_model
from lexic.parsing.earley.reduce import (
    YIELD,
    Drop,
    KeepRaw,
    KeepReduced,
    Reducer,
    Yield,
)

# ── the symbol table: THE binding + the no-exec boundary ─────────────────

_IR_MODULES = (
    _spine,
    _scalars,
    _records,
    _bind,
    _nodes,
    _operators,
    _action,
    _mapping,
    _flavour,
    _layout,
    _encoding,
)


def _ir_node_symbols() -> dict[str, object]:
    """Every public ``IrSelf``-subclass constructor across the IR modules.

    The filter — a class that is an :class:`~lexic.ir.base.IrSelf` subclass —
    is the curation: helper functions, imported names and module data never
    enter the table, only IR node constructors. A new IR node joins the
    vocabulary automatically; the drift-pin test guards the boundary.

    :returns: Public name → its IR node class.
    """
    out: dict[str, object] = {}
    for mod in _IR_MODULES:
        for name, val in vars(mod).items():
            if (
                not name.startswith("_")
                and isinstance(val, type)
                and issubclass(val, IrSelf)
            ):
                out[name] = val
    return out


def _build_symbols() -> dict[str, object]:
    """The notation vocabulary: every IR node constructor plus the fixed extras."""
    out = _ir_node_symbols()
    out.update(
        {
            # Named singletons resolve by bare name to THE instance (their repr
            # is the bare name, not a constructor call).
            "IrNone": IrNone,
            "IR_DEFAULT": IR_DEFAULT,
            "YIELD": YIELD,
            # The reduce sentinels' classes — each spelled ``Name()`` by repr,
            # and a singleton, so a spelled one IS the engine's own.
            "Yield": Yield,
            "Reducer": Reducer,
            "Drop": Drop,
            "KeepRaw": KeepRaw,
            "KeepReduced": KeepReduced,
            # The parser/boundary exception a reduction body may reference.
            "UnsupportedConstructError": UnsupportedConstructError,
            # Booleans — ``IrRule``'s ``semantic`` flag and friends.
            "True": True,
            "False": False,
        }
    )
    return out


SYMBOLS: dict[str, object] = _build_symbols()
"""The IR-constructor notation's vocabulary — the whitelist that IS the no-exec
boundary. Every reachable name is either an ``IrSelf``-subclass constructor or
one of the fixed extras above. Drift-pinned by ``test_notation``.

Covers every node type in ``lexic.ir``. A node declared OUTSIDE the spine —
a format's own families, which is where they belong — is not in here and is
supplied per call instead; see :func:`load_ir`."""

_EXTRA_SYMBOLS: ContextVar[Mapping[str, type]] = ContextVar(
    "_EXTRA_SYMBOLS", default={}
)
"""The caller-supplied vocabulary for the load in flight.

Per call rather than registered globally: the whitelist is a boundary, and a
boundary that any import can widen is not one. A context variable rather than
a parameter because the fold reaches :func:`_resolve` as data, not as an
argument."""

# ── grammar builders ─────────────────────────────────────────────────────


def _lit(text: str) -> IrItem:
    return IrItem(IrLiteral(text))


def _ref(name: str) -> IrItem:
    return IrItem(IrRuleRef(name))


def _rule(name: str, *arms: IrSequence, semantic: bool = True) -> IrRule:
    return IrRule(name, IrAlternation(*arms), semantic)


def _rng(lo: int | str, hi: int | str) -> IrRange:
    return IrRange(IrChr(lo), IrChr(hi))


_STAR = IrQuantifier(0, IrNone)
_PLUS = IrQuantifier(1, IrNone)
_OPT = IrQuantifier(0, 1)

_NAME_FIRST = IrCharClass(_rng("A", "Z"), _rng("a", "z"), IrChr("_"))
_NAME_REST = IrCharClass(_rng("0", "9"), _rng("A", "Z"), _rng("a", "z"), IrChr("_"))
# Printable + non-ASCII, minus the closing quote and the backslash. Python repr
# leaves a raw double quote inside single-quoted strings (and vice versa), so
# only the matching quote is excluded from each plain class.
_SQ_PLAIN = IrCharClass(
    _rng(0x20, 0x26), _rng(0x28, 0x5B), _rng(0x5D, 0x7E), _rng(0xA0, 0x10FFFF)
)
_DQ_PLAIN = IrCharClass(
    _rng(0x20, 0x21), _rng(0x23, 0x5B), _rng(0x5D, 0x7E), _rng(0xA0, 0x10FFFF)
)
# The short-escape chars Python repr emits: \n \r \t \\ \' \" (one class covers
# both quote contexts — a lenient superset).
_SHORT = IrCharClass(
    IrChr("n"), IrChr("r"), IrChr("t"), IrChr("\\"), IrChr("'"), IrChr('"')
)
_HEX = IrCharClass(_rng("0", "9"), _rng("A", "F"), _rng("a", "f"))
_DIGITS = IrCharClass(_rng("0", "9"))
_WS = IrCharClass(IrChr(9), IrChr(10), IrChr(13), IrChr(32))
# Anything except a newline — the body of a ``#`` line comment.
_NOT_NL = IrCharClass(_rng(0x00, 0x09), _rng(0x0B, 0x10FFFF))


def _hexn(count: int) -> IrSequence:
    """A ``\\<tag>`` fixed-width hex escape arm (``tag`` + ``count`` hex digits)."""
    return IrSequence(*([IrItem(_HEX)] * count))


NOTATION_GRAMMAR = IrAst(
    IrSeq(
        _rule("start", IrSequence(_ref("ws"), _ref("value"))),
        _rule(
            "value",
            IrSequence(_ref("nv")),
            IrSequence(_ref("strval")),
            IrSequence(_ref("intval")),
            IrSequence(_ref("tuple")),
        ),
        _rule("nv", IrSequence(_ref("name"), _ref("ct-opt"))),
        _rule(
            "name",
            IrSequence(IrItem(_NAME_FIRST), IrItem(_NAME_REST, _STAR), _ref("ws")),
        ),
        _rule("ct-opt", IrSequence(_ref("call-tail")), IrSequence()),
        _rule(
            "call-tail", IrSequence(_ref("lparen"), _ref("args-opt"), _ref("rparen"))
        ),
        _rule("lparen", IrSequence(_lit("("), _ref("ws"))),
        _rule("rparen", IrSequence(_lit(")"), _ref("ws"))),
        _rule("args-opt", IrSequence(_ref("arglist")), IrSequence()),
        # Trailing commas (``F(a,)``) parse via the GATEABLE deferred-decision
        # shape: an ``arg-tail`` consumes the comma FIRST, then decides
        # value-vs-nothing — so the loop take/skip stays FIRST-disjoint
        # (',' vs ')') and nothing islands. The naive shape
        # ``value arg-rest* comma?`` is ungateable (loop and optional share
        # FIRST=','). The grammar is deliberately LENIENT (a bare comma is an
        # empty tail anywhere); ``_arglist`` enforces "empty tail only in
        # final position" at fold time — the unknown-symbol precedent — so
        # ``F(a,,b)`` still refuses.
        _rule(
            "arglist",
            IrSequence(_ref("value"), IrItem(IrRuleRef("arg-tail"), _STAR)),
        ),
        _rule(
            "arg-tail",
            IrSequence(_ref("comma"), IrItem(IrRuleRef("arg-val"), _OPT)),
        ),
        _rule("arg-val", IrSequence(_ref("value"))),
        # A plain Python tuple — the one composite value that is not a call. A
        # variadic model field holds one, so ``repr`` emits it and the parse
        # half has to read it back.
        #
        # ``tuplist ::= value tup-tail tup-tail*`` makes at least one comma
        # MANDATORY, so ``(1)`` has no derivation. That refusal is structural on
        # purpose — two loaders read a notation artefact, CPython and this half,
        # and in Python ``(1)`` is ``1`` while ``(1,)`` is a one-tuple. A lenient
        # arm would make the two disagree about one file with nothing to report
        # it.
        #
        # One mandatory tail plus a STAR, not ``tup-tail+``: normalising a ``+``
        # over a rule ref yields ``X | X __rep``, whose two arms share a FIRST,
        # so the analysis islands the loop and every tuple sub-parse escapes to
        # Earley. The star shape (``ε | X __rep``) gates on FIRST(X) against
        # FOLLOW and stays a clone. Measured both ways — see
        # ``proto/rv2_b1_islands.py``. Past the first comma the shape is
        # ``arglist``'s: the tail consumes the comma FIRST and then decides
        # value-vs-nothing, keeping the loop gate FIRST-disjoint (',' vs ')'),
        # with the stray-comma refusal at fold time.
        _rule("tuple", IrSequence(_ref("lparen"), _ref("tup-opt"), _ref("rparen"))),
        _rule("tup-opt", IrSequence(_ref("tuplist")), IrSequence()),
        _rule(
            "tuplist",
            IrSequence(
                _ref("value"),
                _ref("tup-tail"),
                IrItem(IrRuleRef("tup-tail"), _STAR),
            ),
        ),
        _rule(
            "tup-tail",
            IrSequence(_ref("comma"), IrItem(IrRuleRef("tup-val"), _OPT)),
        ),
        _rule("tup-val", IrSequence(_ref("value"))),
        _rule("comma", IrSequence(_lit(","), _ref("ws"))),
        _rule("strval", IrSequence(_ref("sq-str")), IrSequence(_ref("dq-str"))),
        _rule(
            "sq-str",
            IrSequence(
                _lit("'"), IrItem(IrRuleRef("squnit"), _STAR), _lit("'"), _ref("ws")
            ),
        ),
        _rule(
            "dq-str",
            IrSequence(
                _lit('"'), IrItem(IrRuleRef("dqunit"), _STAR), _lit('"'), _ref("ws")
            ),
        ),
        _rule("squnit", IrSequence(IrItem(_SQ_PLAIN)), IrSequence(_ref("esc"))),
        _rule("dqunit", IrSequence(IrItem(_DQ_PLAIN)), IrSequence(_ref("esc"))),
        # One rule per escape kind (the gbnf.py precedent): a short escape, or a
        # fixed-width hex escape. The whole string body is reassembled as raw
        # text and decoded structurally by _decode_escapes.
        _rule("esc", IrSequence(_ref("esc-short")), IrSequence(_ref("esc-hex"))),
        _rule("esc-short", IrSequence(_lit("\\"), IrItem(_SHORT))),
        _rule(
            "esc-hex",
            IrSequence(_ref("esc-x")),
            IrSequence(_ref("esc-u")),
            IrSequence(_ref("esc-U")),
        ),
        _rule("esc-x", IrSequence(_lit("\\x"), *_hexn(2))),
        _rule("esc-u", IrSequence(_lit("\\u"), *_hexn(4))),
        _rule("esc-U", IrSequence(_lit("\\U"), *_hexn(8))),
        _rule("intval", IrSequence(_ref("pos-int")), IrSequence(_ref("neg-int"))),
        _rule("pos-int", IrSequence(IrItem(_DIGITS, _PLUS), _ref("ws"))),
        _rule("neg-int", IrSequence(_lit("-"), IrItem(_DIGITS, _PLUS), _ref("ws"))),
        # Whitespace (and ``#`` line comments) — structural noise, looked through
        # by the fold. The trailing newline of a comment is itself whitespace,
        # consumed by the next ws-piece.
        _rule("ws", IrSequence(IrItem(IrRuleRef("ws-piece"), _STAR)), semantic=False),
        _rule("ws-piece", IrSequence(IrItem(_WS)), IrSequence(_ref("comment"))),
        # A line comment consumes its terminating newline (mandatory) so the
        # ``[^\n]*`` body loop gate is disjoint from what follows — the newline
        # belongs to the comment, never to the surrounding whitespace run.
        _rule(
            "comment",
            IrSequence(_lit("#"), IrItem(_NOT_NL, _STAR), _lit("\n")),
            semantic=False,
        ),
    ),
    "start",
)
"""The generic-apply notation grammar (authored IR, PDA-shaped)."""


# ── string decode: structural, over the reassembled raw body ─────────────

_SHORT_MAP = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "'": "'", '"': '"'}
_HEX_WIDTH = {"x": 2, "u": 4, "U": 8}


def _decode_escapes(raw: str = "") -> str:
    """Decode a Python-repr string body — the structural escape reader.

    Replaces the prototypes' ``ast.literal_eval`` shortcut: walks the raw body
    escape-by-escape, mapping each ``grammars/gbnf.py``-style escape kind (short
    or fixed-width hex) to its character. The grammar guarantees only valid
    escapes reach here; an unrecognised ``\\<c>`` is kept verbatim (the
    superset property — repr never emits one).

    :param raw: The raw string body (between the quotes), escapes intact.
    :returns: The decoded string value.
    """
    out: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        tag = raw[i + 1]
        if tag in _SHORT_MAP:
            out.append(_SHORT_MAP[tag])
            i += 2
        elif tag in _HEX_WIDTH:
            width = _HEX_WIDTH[tag]
            out.append(chr(int(raw[i + 2 : i + 2 + width], 16)))
            i += 2 + width
        else:  # not emitted by repr — kept verbatim (superset leniency)
            out.append(c + tag)
            i += 2
    return "".join(out)


# ── the fold: one generic positional apply + coercions ───────────────────


class _Call(tuple):
    """Marks that a call happened — distinguishes a bare name from ``Name()``."""


def _resolve(name: str) -> object:
    """Resolve a bare name through the symbol table (the no-exec boundary).

    :param name: The constructor / singleton name.
    :returns: The bound symbol.
    :raises UnsupportedConstructError: When ``name`` is not whitelisted.
    """
    if name in SYMBOLS:
        return SYMBOLS[name]
    extra = _EXTRA_SYMBOLS.get()
    if name in extra:
        return extra[name]
    raise UnsupportedConstructError(f"notation: unknown symbol {name!r}")


def _name(head: str, tail: str = "") -> object:
    return _resolve(head + tail)


def _nv(sym: object, call: _Call | None = None) -> object:
    if call is None:
        return sym  # bare name: a class, singleton, or bool
    if not callable(sym):  # a bool/singleton spelled with a call — a misuse
        raise UnsupportedConstructError(f"notation: {sym!r} is not callable")
    return sym(*call)  # positional apply — the raw IR class IS the ctor


def _call_tail(a: list[object] | None = None) -> _Call:
    return _Call(a if a is not None else ())


def _comma_list(first: object, rest: list[object] | None, what: str) -> tuple:
    """A comma-separated run; refuse a bare comma anywhere but last.

    The grammar leniently parses every bare comma as an empty tail (folded to
    the shared :data:`~lexic.compile.foldkit.ABSENT` marker); the fold is where
    strictness lives (the unknown-symbol precedent): an
    :data:`~lexic.compile.foldkit.ABSENT` in a non-final position is a stray
    ``,,`` and refuses, a final one is the trailing comma and drops. The
    surviving values ride the shared
    :func:`~lexic.compile.foldkit.first_rest` collector.

    :param first: The head value.
    :param rest: The repeated tails.
    :param what: The construct named in the refusal.
    :returns: The surviving values.
    :raises UnsupportedConstructError: On a stray comma.
    """
    tails = rest or []
    if ABSENT in tails[:-1]:
        raise UnsupportedConstructError(f"notation: stray ',' in {what}")
    return first_rest(first, [x for x in tails if x is not ABSENT])


def _arglist(first: object, rest: list[object] | None = None) -> list[object]:
    """The argument list of a call — positionally applied by :func:`_nv`."""
    return list(_comma_list(first, rest, "argument list"))


def _tuplist(first: object, one: object, rest: list[object] | None = None) -> tuple:
    """A plain tuple's elements: the head, the mandatory tail, then the rest.

    ``one`` is what makes the value a tuple — the grammar cannot derive a
    parenthesised single value without it, so a one-element result really is
    ``(x,)`` and never ``(x)``.
    """
    return _comma_list(first, [one, *(rest or [])], "tuple")


def _tuple(items: tuple | None = None) -> tuple:
    """``()`` when the parens were empty, else the collected elements."""
    return items if items is not None else ()


def _neg_int(raw: str) -> int:
    return -int(raw)


_BODIES: dict[str, ModelBody] = {
    "start": seq(passthrough, 2, (FieldFold(1, "model", "v", 1),)),
    "value": ALT_BODY,
    "nv": seq(
        _nv, 2, (FieldFold(0, "model", "sym", 1), FieldFold(1, "model", "call", 0))
    ),
    "name": seq(
        _name, 3, (FieldFold(0, "text", "head", 1), FieldFold(1, "text", "tail", 0))
    ),
    "ct-opt": ALT_BODY,
    "call-tail": seq(_call_tail, 3, (FieldFold(1, "model", "a", 0),)),
    "args-opt": ALT_BODY,
    "arglist": seq(
        _arglist,
        2,
        (FieldFold(0, "model", "first", 1), FieldFold(1, "models", "rest", 0)),
    ),
    "arg-tail": seq(absent_tail, 2, (FieldFold(1, "model", "v", 0),)),
    "arg-val": seq(passthrough, 1, (FieldFold(0, "model", "v", 1),)),
    "tuple": seq(_tuple, 3, (FieldFold(1, "model", "items", 0),)),
    "tup-opt": ALT_BODY,
    "tuplist": seq(
        _tuplist,
        3,
        (
            FieldFold(0, "model", "first", 1),
            FieldFold(1, "model", "one", 1),
            FieldFold(2, "models", "rest", 0),
        ),
    ),
    "tup-tail": seq(absent_tail, 2, (FieldFold(1, "model", "v", 0),)),
    "tup-val": seq(passthrough, 1, (FieldFold(0, "model", "v", 1),)),
    "strval": ALT_BODY,
    "sq-str": seq(_decode_escapes, 4, (FieldFold(1, "text", "raw", 0),)),
    "dq-str": seq(_decode_escapes, 4, (FieldFold(1, "text", "raw", 0),)),
    "intval": ALT_BODY,
    "pos-int": seq(DECODE_INT, 2, (FieldFold(0, "text", "raw", 1),)),
    "neg-int": seq(_neg_int, 3, (FieldFold(1, "text", "raw", 1),)),
}

NOTATION_FOLD = model_fold(_BODIES)


# ── the entry ─────────────────────────────────────────────────────────────


def load_ir(text: str, symbols: Mapping[str, type] | None = None) -> IrSelf:
    """Parse IR-constructor notation into the ``IrSelf`` it evaluates to.

    The inverse of :func:`repr`: ``load_ir(repr(node))`` reconstructs ``node``.
    Drives the engine's :func:`~lexic.parsing.parse_model` product over
    :data:`NOTATION_GRAMMAR` with the notation fold. Saving is just
    ``repr(node)``; this is the other half, so **anything lexic parses can be
    written to a file and read back** — a grammar, a flavour manifest, a
    tokenizer.

    ``symbols`` extends the vocabulary for THIS call, for a value naming node
    types declared outside ``lexic.ir`` — a format's own families live beside
    their reader, so the spine's whitelist cannot know them. Each must be an
    ``IrSelf`` subclass: the whitelist IS the no-exec boundary, and admitting
    a plain callable would reopen it.

    :param text: IR-constructor notation (the root is an IR node — an
        ``IrAst`` for ``.ir`` data files, an ``IrMap`` for flavour manifests).
    :param symbols: Extra ``name → IrSelf subclass`` entries for this load.
    :returns: The reconstructed IR node.
    :raises UnsupportedConstructError: On a parse failure, an unknown symbol,
        or a supplied symbol that is not an ``IrSelf`` subclass.
    """
    if not symbols:
        return cast(IrSelf, parse_model(NOTATION_GRAMMAR, text, NOTATION_FOLD))
    for name, symbol in symbols.items():
        if not (isinstance(symbol, type) and issubclass(symbol, IrSelf)):
            raise UnsupportedConstructError(
                f"notation: {name!r} is not an IrSelf subclass — the symbol "
                "table is the no-exec boundary and only IR nodes may enter it"
            )
    token = _EXTRA_SYMBOLS.set(symbols)
    try:
        return cast(IrSelf, parse_model(NOTATION_GRAMMAR, text, NOTATION_FOLD))
    finally:
        _EXTRA_SYMBOLS.reset(token)


def load_ir_from_path(
    path: str | Path, symbols: Mapping[str, type] | None = None
) -> IrSelf:
    """Load IR-constructor notation from a UTF-8 file.

    :param path: Path to a ``.ir`` notation file.
    :param symbols: Extra vocabulary for this load (see :func:`load_ir`).
    :returns: The reconstructed IR node.
    """
    return load_ir(Path(path).read_text(encoding="utf-8"), symbols)
