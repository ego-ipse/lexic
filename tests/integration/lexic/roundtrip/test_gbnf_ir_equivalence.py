"""Golden gate — the IR-native GBNF self-grammar over the ground-truth corpus.

Formerly pinned :data:`~lexic.grammars.gbnf.GBNF_GRAMMAR` /
:data:`~lexic.grammars.gbnf.GBNF_REDUCER` against the (now-deleted) Lark
meta-parser. With the Lark path gone this asserts stable invariants instead:
every ground-truth grammar reduces to an :class:`IrAst` with the expected
start rule and rule set, unambiguously, and re-emitting through
``GBNF_FLAVOUR`` and re-parsing preserves that rule fingerprint.

(Full-AST round-trip equality does not hold for the json variants — the GBNF
emitter canonicalises some bodies so ``parse(emit(ast))`` differs from ``ast``
in body detail while keeping the same rule set. The fingerprint invariant
captures the stable part.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lexic.grammars.gbnf import GBNF_FLAVOUR, GBNF_GRAMMAR, GBNF_REDUCER
from lexic.ir import IrAst
from lexic.parsing import is_ambiguous
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.products import earley_reduce
from tests.paths import GROUND_TRUTH
from tests.unit.lexic.parsing.ir_fixtures import JSON_RULE_NAMES

# Golden per-file fingerprint: start rule + rule names in source order.
GOLDEN: dict[str, tuple[str, tuple[str, ...]]] = {
    "arithmetic": ("root", ("root", "expr", "term", "ident", "num", "ws")),
    "markdown": (
        "document",
        (
            "document",
            "block",
            "heading",
            "bullet",
            "paragraph",
            "blank",
            "level",
            "start",
            "opener",
            "line",
            "styled",
            "code",
            "emphasis",
            "plain",
        ),
    ),
    "c": (
        "root",
        (
            "root",
            "declaration",
            "dataType",
            "identifier",
            "parameter",
            "paramList",
            "statement",
            "forInit",
            "forUpdate",
            "condition",
            "relationOperator",
            "expression",
            "term",
            "factor",
            "unaryTerm",
            "funcCall",
            "parenExpression",
            "argList",
            "number",
            "singleLineComment",
            "multiLineComment",
            "ws",
        ),
    ),
    "chess": ("root", ("root", "move", "nonpawn", "pawn", "castle")),
    "japanese": (
        "root",
        ("root", "jp-char", "hiragana", "katakana", "punctuation", "cjk"),
    ),
    "json": ("JSON-text", JSON_RULE_NAMES),
    "json_arr": (
        "root",
        ("root", "value", "arr", "object", "array", "string", "number", "ws"),
    ),
    "json_ws": (
        "root",
        ("root", "value", "object", "array", "string", "number", "ws"),
    ),
    "list": ("root", ("root", "item")),
    "think": ("root", ("root", "thinking")),
    "vyx": (
        "packet",
        (
            "packet",
            "definition",
            "body",
            "envelope",
            "performative",
            "std-perf",
            "custom-perf",
            "inline-body",
            "inline-content",
            "block-body",
            "body-line",
            "nl-escape",
            "nl-force",
            "nl-text",
            "nl-head",
            "nl-word",
            "nl-first",
            "nl-inner",
            "nl-tail",
            "value",
            "bare-val",
            "null-val",
            "unquoted",
            "uq-first",
            "uq-tail",
            "quoted",
            "quoted-char",
            "escaped",
            "kv-pair",
            "kv-pairs",
            "kv-line",
            "key",
            "kv-like-item",
            "pipe-list",
            "pipe-item",
            "pipe-bare",
            "pipe-unquoted",
            "pipe-esc",
            "pipe-first",
            "pipe-tail",
            "scope-line",
            "scope-item",
            "scope-scalar",
            "scope-word",
            "sw-first",
            "sw-tail",
            "scope-name",
            "scope-path",
            "indent",
            "seq-item",
            "item-head",
            "ref",
            "spread",
            "ref-id",
            "labeled-val",
            "table-header",
            "table-row",
            "tag",
            "count",
            "field-list",
            "field-name",
            "cell",
            "row-copy",
            "col-copy",
            "subtable-ref",
            "row-annotation",
            "ann-indent",
            "row-key",
            "schema-def",
            "schema-name",
            "dict-def",
            "col-name",
            "dict-entries",
            "dict-entry",
            "dict-code",
            "budget",
            "env-field",
            "o-field",
            "s-field",
            "r-field",
            "v-field",
            "c-field",
            "pref-field",
            "n-field",
            "label-field",
            "ref-field",
            "agent-id",
            "template-def",
            "template-use",
            "tpl-name",
            "vyx-file",
            "file-line",
        ),
    ),
}

GRAMMARS = sorted(GROUND_TRUTH.glob("*.gbnf"))


def fingerprint(ast: IrAst) -> tuple[str, tuple[str, ...]]:
    """(start rule, rule names in order) — the golden-comparable shape."""
    return str(ast.start), tuple(str(r.name) for r in ast.rules)


@pytest.fixture(name="norm_grammar", scope="module")
def norm_grammar_fixture() -> IrAst:
    """The Earley-normalised GBNF self-grammar, shared across the module."""
    return normalize(GBNF_GRAMMAR)


def test_corpus_is_complete() -> None:
    """Every golden entry has a ground-truth file and vice versa."""
    assert {p.stem for p in GRAMMARS} == set(GOLDEN)


@pytest.mark.parametrize("path", GRAMMARS, ids=lambda p: p.stem)
def test_reduces_to_golden_fingerprint(path: Path, norm_grammar: IrAst) -> None:
    """earley_reduce yields the golden start rule and rule set."""
    text = path.read_text(encoding="utf-8")
    ast = earley_reduce(norm_grammar, text, GBNF_REDUCER)
    assert isinstance(ast, IrAst)
    assert fingerprint(ast) == GOLDEN[path.stem]


@pytest.mark.parametrize("path", GRAMMARS, ids=lambda p: p.stem)
def test_ground_truth_unambiguous(path: Path, norm_grammar: IrAst) -> None:
    """Every ground-truth grammar has exactly one derivation."""
    text = path.read_text(encoding="utf-8")
    assert not is_ambiguous(norm_grammar, text)


@pytest.mark.parametrize("path", GRAMMARS, ids=lambda p: p.stem)
def test_emit_reparse_preserves_fingerprint(path: Path, norm_grammar: IrAst) -> None:
    """Emitting the reduced AST as GBNF and re-parsing keeps the rule fingerprint."""
    text = path.read_text(encoding="utf-8")
    ast = earley_reduce(norm_grammar, text, GBNF_REDUCER)
    assert isinstance(ast, IrAst)
    reparsed = earley_reduce(norm_grammar, str(GBNF_FLAVOUR.apply(ast)), GBNF_REDUCER)
    assert isinstance(reparsed, IrAst)
    assert fingerprint(reparsed) == fingerprint(ast)
