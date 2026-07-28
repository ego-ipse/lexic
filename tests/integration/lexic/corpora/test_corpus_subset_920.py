"""Fixture-level lock on the disputed benchmark corpus.

``resources/corpora/corpus_subset_920.abnf`` is the fixed 920-char old-subset-
grammar self-emit that ``zzz_current_work/Disputed.md`` measured its perf
regression claims against, and the benchmark's
"subset-920" workload times. It is old-subset ABNF syntax, but also valid
syntax under the current full RFC 5234+7405 ABNF grammar (a strict syntactic
superset) — pinning that here means a future ABNF grammar change that stops
accepting this corpus fails a test, not just silently skews a benchmark run.
"""

from __future__ import annotations

from lexic.compile import parse_grammar
from lexic.grammars.abnf import ABNF_FLAVOUR
from lexic.ir import IrAst
from tests.paths import CORPORA

CORPUS_TEXT = (CORPORA / "corpus_subset_920.abnf").read_text()


def test_corpus_subset_920_parses_to_ir_ast():
    """The disputed corpus parses against the current ABNF flavour into an IrAst."""
    ast = parse_grammar(CORPUS_TEXT, ABNF_FLAVOUR)
    assert isinstance(ast, IrAst)


def test_corpus_subset_920_defines_its_full_rule_set():
    """The corpus defines its old-subset rule set (34 rules), start = rulelist."""
    ast = parse_grammar(CORPUS_TEXT, ABNF_FLAVOUR)
    assert len(ast.rules) == 34
    assert ast.start == "rulelist"
