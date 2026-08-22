"""Ordered attempt on inline group arms — the I11b end-to-end pins.

``@lexical`` inlining moves an alternation out of a rule body and into an
inline group; before I11b, the arm-conflict licence was rule-body-only, so a
group overlap a fixed-k window cannot separate stayed a hard note and
islanded its enclosing rule — routing the WHOLE parse through Earley (measured
16-28x slower than the unmarked grammar on the witness below). Group-scoped
ordered attempt closes it: the group's arms try in order with rollback, and
the runtime's second-success audit refuses only what genuinely cannot be
decided.

This module is the cross-cutting proof — one compiled grammar, both engines,
the real runtime — beside the narrower per-module pins in ``analysis/`` and
``core/``.
"""

from __future__ import annotations

import time

import pytest

from lexic.compile import compile_text
from lexic.exceptions import UnsupportedConstructError
from lexic.parsing.fold import lift_optional_nullables
from lexic.parsing.pda.analysis.analysis import GrammarAnalysis
from lexic.parsing.pda.core.errors import PdaFail
from lexic.parsing.pda.runtime.kernel.kernel import pda_model
from lexic.parsing.products import earley_model
from tests.unit.lexic.parsing.parsing_helpers import prod

# ── item 1: the B1 six-line witness ─────────────────────────────────────────

_WITNESS_BODY = (
    "root ::= stmt+\n"
    "stmt ::= block | bind\n"
    'block ::= "def " name "() { " word " }\\n"\n'
    'bind ::= "def " name "() = " word ";\\n"\n'
    "name ::= [a-z] [a-z0-9]*\n"
    "word ::= [a-z0-9]+\n"
)
_WITNESS_UNIT = "def alpha() { one }\ndef beta() = two;\n"
_WITNESS_DOC = _WITNESS_UNIT * 300


def _routes_pda(cg, text: str) -> bool:
    """Whether ``text`` parses through the PDA, or islands to Earley."""
    try:
        pda_model(prod(cg).pda, text, cg.fold)
        return True
    except PdaFail:
        return False


def _process_time(cg, text: str) -> float:
    start = time.process_time()
    cg.parse(text, cores=1)
    return time.process_time() - start


def test_lexical_root_witness_routes_pda_and_round_trips():
    """`# @lexical root` moves ``stmt``'s alternation into an inline group;
    the group's arms share an unbounded prefix (``"def " name``) no fixed-k
    window can separate — before I11b this islanded ``root`` and every parse
    fell back to Earley (``pos -1``). It must now route PDA and round-trip."""
    marked = compile_text(
        "# @lexical root\n" + _WITNESS_BODY, cache_key="i11b-witness-route"
    )
    assert _routes_pda(marked, _WITNESS_DOC)
    model = marked.parse(_WITNESS_DOC, cores=1)
    assert model.to_text() == _WITNESS_DOC


def test_lexical_root_witness_lands_within_a_small_factor_of_unmarked():
    """The group attempt licence, not an island, decides this route — so the
    marked parse must land near its unmarked cousin, not the 16-28x an
    islanded start rule cost before this increment."""
    unmarked = compile_text(_WITNESS_BODY, cache_key="i11b-witness-unmarked")
    marked = compile_text(
        "# @lexical root\n" + _WITNESS_BODY, cache_key="i11b-witness-timed"
    )
    for cg in (unmarked, marked):
        cg.parse(_WITNESS_DOC, cores=1)  # warm the compiled product

    base = min(_process_time(unmarked, _WITNESS_DOC) for _ in range(5))
    lexical = min(_process_time(marked, _WITNESS_DOC) for _ in range(5))

    assert lexical <= base * 3, (
        f"@lexical root took {lexical * 1000:.2f} ms against "
        f"{base * 1000:.2f} ms unmarked ({lexical / base:.1f}x) — "
        "this is the island regression's own shape"
    )


def test_lexical_root_witness_group_carries_an_ordered_attempt_licence():
    """The analysis pins the licence directly: the group's overlap is not
    window- or peek-demoted, it is settled by ordered attempt, authored
    order — ``block`` before ``bind``, neither nullable."""
    marked = compile_text(
        "# @lexical root\n" + _WITNESS_BODY, cache_key="i11b-witness-analysis"
    )
    lifted = lift_optional_nullables(marked.codegen_grammar)
    taxonomy = GrammarAnalysis(lifted).taxonomy
    attempted = [
        gate for gate in taxonomy.grp_arm_gates.values() if gate[2] is not None
    ]

    assert len(attempted) == 1
    windows, peek, attempt = attempted[0]
    assert (windows, peek) == (None, None)
    assert attempt is not None
    order, _follow = attempt
    assert order.order == (0, 1)


# ── item 2: the six B3 ambiguity-parity adversarials ────────────────────────
#
# Ported from the increment's own ``proto/proto_b_amb.py`` (measured "zero
# divergences"). The right differential is PDA vs Earley on ONE compiled
# grammar — comparing a marked grammar against an unmarked one compares two
# different model shapes and proves nothing.

_AMBIGUITY_CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "two equal arms in one group — same span, two readings",
        'root ::= ("d" w "!" | "d" w "!")\nw ::= [a-z]+\n',
        ("dab!", "d!"),
    ),
    (
        "equal prefixes, tails decide past any window",
        'root ::= ("d" w "!" | "d" w "?")\nw ::= [a-z]+\n',
        ("dab!", "dab?"),
    ),
    (
        "group arms build DIFFERENT models over one text",
        'root ::= (x | y)\nx ::= "d" w "!"\ny ::= "d" w "!"\nw ::= [a-z]+\n',
        ("dab!",),
    ),
    (
        "nested group inside an attempted group",
        'root ::= (("p" w "!" | "p" w "!") | "q")+ "."\nw ::= [a-z]+\n',
        ("pab!.", "q.", "pab!q."),
    ),
    (
        "group + a tail the shorter reading could compose with",
        'root ::= ("a" w | "a" w) "z"\nw ::= [a-z]+\n',
        ("abz", "az"),
    ),
    (
        "decidable — neither engine may refuse",
        'root ::= item+\nitem ::= a | b\na ::= "ax" "1"\nb ::= "ax" "2"\n',
        ("ax1", "ax2", "ax1ax2"),
    ),
)


def _pda_verdict(cg, text: str) -> tuple[str, str]:
    try:
        return ("ok", pda_model(prod(cg).pda, text, cg.fold).to_text())
    except PdaFail:
        return ("declined", "")
    except UnsupportedConstructError as exc:
        return ("refused", str(exc))


def _earley_verdict(cg, text: str) -> tuple[str, str]:
    try:
        product = prod(cg)
        model = earley_model(product.instance_grammar, text, cg.fold, product.tables)
        return ("ok", model.to_text())
    except UnsupportedConstructError as exc:
        return ("refused", str(exc))


@pytest.mark.parametrize(
    ("label", "source", "inputs"),
    _AMBIGUITY_CASES,
    ids=[case[0] for case in _AMBIGUITY_CASES],
)
def test_pda_and_earley_agree_on_one_compiled_grammar(
    label: str, source: str, inputs: tuple[str, ...]
) -> None:
    """A PDA decline is the designed escape, not a divergence: the audit
    could not settle it, so the gated engine's verdict — ok or refused — is
    the answer, and the PDA must never have committed something different."""
    cg = compile_text(source, cache_key=f"i11b-amb-{label}")
    for text in inputs:
        pda_outcome, earley_outcome = _pda_verdict(cg, text), _earley_verdict(cg, text)
        if pda_outcome[0] == "declined":
            # Decline is always SAFE — but on the decidable case it would be
            # a silent capability regression, and skipping would hide it.
            assert not label.startswith("decidable"), (label, text)
            continue
        assert pda_outcome[0] == earley_outcome[0], (
            label,
            text,
            pda_outcome,
            earley_outcome,
        )
        if pda_outcome[0] == "ok":
            assert pda_outcome[1] == earley_outcome[1] == text


# ── item 5: the soft-continuation gate, behaviourally ───────────────────────

_LOOPBACK_SOURCE = (
    "# @lexical root\n"
    "root ::= entry+\n"
    "entry ::= alt\n"
    'alt ::= "d" run "!" "\\n" | "d" run "?" "\\n"\n'
    "run ::= [a-c]*\n"
)
"""``@lexical root`` inlines ``entry``/``alt`` into ONE repeated group whose
two arms share an unbounded prefix (``"d" run``) — an ordered-attempt shape —
and whose own FIRST character (``'d'``) is exactly what a winning arm's next
iteration begins with. A hard tail gate (the compiler's own per-clone
continuation, which deliberately excludes repeat loopback) would see the
following ``'d'`` as outside the arm's continuation and discard the live
reading as dead; the analysis' SOFT continuation includes the group's own
FIRST when it repeats, so the parse must succeed."""


def test_repeated_group_attempt_stores_its_own_first_in_the_follow_set():
    """Analysis-level proof of the loopback term: the stored continuation at
    the group's attempt entry contains 'd', the group's own FIRST — not just
    the EOF sentinel the enclosing (non-repeating) tail alone would carry."""
    cg = compile_text(_LOOPBACK_SOURCE, cache_key="i11b-loopback-analysis")
    lifted = lift_optional_nullables(cg.codegen_grammar)
    taxonomy = GrammarAnalysis(lifted).taxonomy
    attempted = [
        gate for gate in taxonomy.grp_arm_gates.values() if gate[2] is not None
    ]

    assert len(attempted) == 1
    _windows, _peek, attempt = attempted[0]
    assert attempt is not None
    _order, follow = attempt
    assert "d" in follow.chars


def test_repeated_group_attempt_succeeds_across_an_iteration_boundary():
    """Two consecutive iterations, back to back with no separator between
    them, so the second iteration's leading 'd' immediately follows the
    first's committed arm — exactly the boundary a hard tail gate would
    discard. The parse must succeed and round-trip byte for byte."""
    cg = compile_text(_LOOPBACK_SOURCE, cache_key="i11b-loopback-parse")
    text = "dab!\ndc?\n"
    assert _routes_pda(cg, text)
    model = cg.parse(text, cores=1)
    assert model.to_text() == text
