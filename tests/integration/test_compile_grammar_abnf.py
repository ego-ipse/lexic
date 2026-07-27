"""ABNF end-to-end: canonical grammar → binding view / codegen shape."""

from __future__ import annotations

from lexic.compile import canonical_grammar
from lexic.compile.pipeline.binding import compute_binding
from lexic.compile.pipeline.passes import build_codegen_grammar
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.ir import IrCharClass, IrItem
from tests.integration.abnf_fixtures import NON_SEMANTIC_DIRECTIVE_ABNF
from tests.paths import GROUND_TRUTH


def binding(text: str):
    """(canonical ast, {rule_name: RuleBinding}) for an ABNF grammar string."""
    ast = canonical_grammar(text, ABNF_FLAVOUR)
    bound = compute_binding(build_codegen_grammar(ast))
    return ast, {b.rule_name: b for b in bound}


def test_compile_arithmetic_abnf_succeeds():
    """All expected rule names are present and structural kinds are correct.

    Rule names fold to canonical form (lowercase, ``_``→``-``) as of
    canonicalize's rewrite 7 — ``DIGIT``/``WSP`` become ``digit``/``wsp``.
    """
    text = (GROUND_TRUTH / "arithmetic.abnf").read_text(encoding="utf-8")
    _ast, by = binding(text)
    assert {"root", "expr", "term", "op", "num", "digit", "wsp"} <= set(by)
    assert by["op"].kind == "value_str"
    assert by["expr"].kind == "sequence"
    assert by["digit"].kind == "value_str"


def test_compile_abnf_non_semantic_directive_propagates_to_referencing_rule():
    """@non-semantic WSP propagates onto any field that references it — the ref
    folds to canonical ``wsp``, same as the rule name."""
    _ast, by = binding(NON_SEMANTIC_DIRECTIVE_ABNF)
    assert any(not ibind.semantic for ibind in by["root"].fields.values())
    assert "wsp" in by["root"].fields
    assert by["root"].fields["wsp"].semantic is False


def test_compile_abnf_case_insensitive_literal_expanded():
    """`root = "Hi"` in ABNF → two direct char-class items, ``[Hh][Ii]``.

    Canonicalize's rewrite 5 inlines the single-arm group each case-folded
    letter used to sit in, so the case-insensitive expansion is now two
    ``IrItem``s carrying an ``IrCharClass`` atom directly — not a group.
    """
    text = 'root = "Hi"\n'
    ast, by = binding(text)
    assert by["root"].kind == "value_str"
    rule = next(r for r in ast.rules if r.name == "root")
    arm = next(a for a in rule.body if a)
    items = [item for item in arm if isinstance(item, IrItem)]
    assert len(items) == 2
    atoms = [item.atom for item in items]
    assert all(isinstance(atom, IrCharClass) for atom in atoms)
    charclasses = [atom for atom in atoms if isinstance(atom, IrCharClass)]
    assert [sorted(cc.members()) for cc in charclasses] == [
        sorted(map(ord, "Hh")),
        sorted(map(ord, "Ii")),
    ]
