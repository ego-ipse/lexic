"""Tests for lexic.parsing.earley.kernel.loop.leo — Leo right-recursion.

The deterministic-chain fast path, exercised where it is observable: through
``Kernel`` on right-recursive grammars. ``leo_sole`` / ``leo_resolve`` decide
*whether* a completion jumps and *where to*; what a test can see is that the
language and the derivations are unchanged, and that a long right recursion
neither overflows the stack nor loses a family.

Ported from ``test_kernel.py`` when ``leo.py`` was split out — assertions
unchanged.
"""

from __future__ import annotations

import pytest

from lexic.compile import compile_text
from lexic.exceptions import EngineInvariantError, UnsupportedConstructError
from lexic.ir import (
    IrAlternation,
    IrItem,
    IrLiteral,
    IrNone,
    IrQuantifier,
    IrRule,
    IrRuleRef,
    IrSequence,
)
from lexic.parsing import parse, recognize
from lexic.parsing.earley.kernel.forest.forest import ParseTree
from lexic.parsing.earley.kernel.forest.support.readout import accept_item
from lexic.parsing.earley.kernel.loop import kernel as kernel_module
from lexic.parsing.earley.kernel.loop import leo as leo_module
from lexic.parsing.earley.kernel.loop.kernel import Kernel
from lexic.parsing.earley.kernel.loop.leo import expand_leo, leo_resolve, leo_sole
from lexic.parsing.earley.kernel.tables.builder import compile_tables
from lexic.parsing.earley.normalize import normalize
from lexic.parsing.products import earley_model, model_product
from tests.unit.lexic.parsing.ir_fixtures import (
    norm,
    plus_of,
    star,
)

# ── Leo correctness: right-recursive grammars accept/reject properly ──
# (ported from the deleted test_ops.py)


def test_leo_star_accepts_empty():
    """S = 'a'* accepts the empty string."""
    g = star("a")
    assert recognize(g, "") == 1


def test_leo_star_accepts_single():
    """S = 'a'* accepts a single 'a'."""
    g = star("a")
    assert recognize(g, "a") == 1


def test_leo_star_accepts_many():
    """S = 'a'* accepts a run of four 'a's."""
    g = star("a")
    assert recognize(g, "aaaa") == 1


def test_leo_star_rejects_wrong_char():
    """S = 'a'* rejects input containing a 'b'."""
    g = star("a")
    assert recognize(g, "aab") == 0


def test_leo_plus_rejects_empty():
    """S = 'a'+ rejects the empty string."""
    g = plus_of("a")
    assert recognize(g, "") == 0


def test_leo_plus_accepts_one():
    """S = 'a'+ accepts a single 'a'."""
    g = plus_of("a")
    assert recognize(g, "a") == 1


def test_leo_plus_accepts_many():
    """S = 'a'+ accepts a run of five 'a's."""
    g = plus_of("a")
    assert recognize(g, "aaaaa") == 1


def test_leo_star_star_sequence():
    """S = 'a'* 'b'* accepts '', 'aaa', 'bbb', 'aabb', rejects 'ba'."""
    g = norm(
        IrRule(
            "S",
            IrAlternation(
                IrSequence(
                    IrItem(IrLiteral("a"), IrQuantifier(0, IrNone)),
                    IrItem(IrLiteral("b"), IrQuantifier(0, IrNone)),
                )
            ),
        ),
        start="S",
    )
    assert recognize(g, "") == 1
    assert recognize(g, "aaa") == 1
    assert recognize(g, "bbb") == 1
    assert recognize(g, "aabb") == 1
    assert recognize(g, "ba") == 0


def test_leo_indirect_ruleref_star():
    """S = X*  where  X = 'a' | 'b'  (right-recursive via an indirect ref)."""
    x_rule = IrRule(
        "X",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a"))),
            IrSequence(IrItem(IrLiteral("b"))),
        ),
    )
    s_rule = IrRule(
        "S",
        IrAlternation(IrSequence(IrItem(IrRuleRef("X"), IrQuantifier(0, IrNone)))),
    )
    g = norm(s_rule, x_rule, start="S")
    assert recognize(g, "") == 1
    assert recognize(g, "abba") == 1
    assert recognize(g, "c") == 0


# ── Parse correctness: Leo-on-parse returns correct trees ────────────


def test_leo_parse_star_single():
    """S = 'a'* — parse 'a' returns correct tree."""
    g = star("a")
    tree = parse(g, "a")
    assert tree is not None


def test_leo_parse_star_many():
    """S = 'a'* — parse 'aaaa' returns correct tree."""
    g = star("a")
    tree = parse(g, "aaaa")
    assert tree is not None


def test_leo_parse_plus_many():
    """S = 'a'+ — parse 'aaaaaa' returns correct tree (deep right-recursion)."""
    g = plus_of("a")
    tree = parse(g, "aaaaaa")
    assert tree is not None


def test_leo_parse_deep_right_recursion():
    """Leo-on-parse: parse 200 'a's — would crash at ~300 without depth safety."""
    g = star("a")
    tree = parse(g, "a" * 200)
    assert tree is not None


def test_leo_parse_indirect_ruleref():
    """Leo-on-parse: indirect right-recursion via ruleref."""
    x_rule = IrRule(
        "X",
        IrAlternation(
            IrSequence(IrItem(IrLiteral("a"))),
            IrSequence(IrItem(IrLiteral("b"))),
        ),
    )
    s_rule = IrRule(
        "S",
        IrAlternation(IrSequence(IrItem(IrRuleRef("X"), IrQuantifier(0, IrNone)))),
    )
    g = norm(s_rule, x_rule, start="S")
    tree = parse(g, "abba")
    assert tree is not None


# ── Leo engaging on a long right-recursive input: no stack overflow ───


def test_leo_engages_on_long_input_no_recursion_error():
    """S = 'a'* over 200+ chars does not stack overflow and produces a tree."""
    g = star("a")
    text = "a" * 250
    tree = parse(g, text)
    assert isinstance(tree, ParseTree)


def test_leo_engages_on_long_input_via_kernel_run():
    """Kernel.run() over 200+ chars resolves accept without crashing."""
    g = star("a")
    tables = compile_tables(g)
    kernel = Kernel(tables, "a" * 250).run()
    assert accept_item(kernel) >= 0


# ── a right recursion through a unit arm ────────────────────────────────────

SPELLINGS = {
    "recursive-first": 'root ::= x root | x\nx ::= "a" [b-z]+ ";"\n',
    "recursive-last": 'root ::= x | x root\nx ::= "a" [b-z]+ ";"\n',
}
"""The arm hoist gives ``root`` a unit arm over the recursive one, so each
level's climb meets ``root → • root-arm1`` in the column the level began in."""

TWO_UNITS = 'root ::= u | x\nu ::= w\nw ::= x root\nx ::= "a" [b-z]+ ";"\n'
"""Two unit arms stacked in one column: ``root → • u`` over ``u → • w``."""


def _climbing(monkeypatch, source: str, text: str, passing: bool = True):
    """``(model, top-level Leo climbs, Leo jumps)`` of one whole-document
    Earley parse, with the unit pass on or with no code marked a unit arm."""
    compiled = compile_text(source, cache_key=f"leo-unit-{hash(source)}")
    product = model_product(compiled.codegen_grammar, compiled.product)
    codes = product.tables.codes
    if not passing:
        monkeypatch.setattr(codes, "unit_start", tuple(False for _ in codes.unit_start))
    counts = [0, 0]
    climb, jump = vars(leo_module)["leo_resolve"], vars(Kernel)["_try_leo"]

    def climbed(*args):
        counts[0] += 1
        return climb(*args)

    def jumped(self, *args):
        took = jump(self, *args)
        counts[1] += took
        return took

    monkeypatch.setattr(kernel_module, "leo_resolve", climbed)
    monkeypatch.setattr(Kernel, "_try_leo", jumped)
    model = earley_model(
        product.instance_grammar, text, compiled.product, product.tables
    )
    monkeypatch.undo()
    return model, counts[0], counts[1]


@pytest.mark.parametrize("spelling", sorted(SPELLINGS))
def test_a_right_recursion_through_a_unit_arm_climbs_once_per_level(
    monkeypatch, spelling: str
) -> None:
    """The climb passes the hoist's unit step, so a level jumps to the top of
    the chain instead of stopping one step up and leaving the next level to
    climb again: one climb and one jump per level, against n² climbs without
    the pass."""
    for units in (100, 200):
        text = "abc;" * units
        model, climbs, jumps = _climbing(monkeypatch, SPELLINGS[spelling], text)
        assert model.to_text() == text
        assert climbs == jumps == units - 1
        _model, refused, _jumps = _climbing(
            monkeypatch, SPELLINGS[spelling], text, False
        )
        assert refused == (units - 1) ** 2, "the pass was never needed here"


@pytest.mark.parametrize("spelling", sorted(SPELLINGS))
def test_a_passed_unit_step_reads_back_the_same_families(
    monkeypatch, spelling: str
) -> None:
    """A jump defers the families its chain skipped, and expansion files them
    back: the decoded chart holds the same family set at every key as when
    the climb stops at the unit step."""
    text = "abc;" * 40
    grammar = normalize(compile_text(SPELLINGS[spelling]).codegen_grammar)
    tables = compile_tables(grammar)
    passing = _families(Kernel(tables, text, True).run())
    codes = tables.codes
    monkeypatch.setattr(codes, "unit_start", tuple(False for _ in codes.unit_start))
    assert passing == _families(Kernel(tables, text, True).run())
    assert passing


def _families(kern: Kernel) -> dict[int, frozenset]:
    """Every key's family set, every deferred chain expanded."""
    for key in list(kern.st.leo_links):
        expand_leo(kern.st, kern.tables, key)
    return {key: frozenset(fams) for key, fams in kern.family_reader().items()}


def test_two_unit_arms_in_one_column_still_climb_per_level(monkeypatch) -> None:
    """The measured limit: one unit step is passed per column, so a second one
    stacked on it is refused and the climb stops there, quadratic as before,
    and the model is still right. A pass whose climb then stops jumps nowhere:
    Leo engages exactly where it does without the pass."""
    climbs = {}
    for units in (100, 200):
        text = "abc;" * units
        model, climbs[units], jumps = _climbing(monkeypatch, TWO_UNITS, text)
        assert model.to_text() == text
        assert jumps == _climbing(monkeypatch, TWO_UNITS, text, False)[2]
    assert climbs[200] > 3.5 * climbs[100]


LEADING_TOKEN = 's ::= "y" a\na ::= b\nb ::= "z" b | "z"\n'
"""The outermost ``b``'s waiter is the unit arm ``a → • b``, and past it the
climb takes one step, to ``s → "y" • a``, which nothing waits on."""


def test_a_jump_counts_its_steps_past_the_unit_arm(monkeypatch) -> None:
    """A climb of one real step costs the jump more than the completer, and a
    unit step passed on the way is free, so it does not make two: the
    outermost ``b`` completes as it would without the pass, and every inner
    level jumps once."""
    text = "y" + "z" * 50
    model, _climbs, jumps = _climbing(monkeypatch, LEADING_TOKEN, text)
    assert model.to_text() == text
    assert jumps == len(text) - 2


def test_a_unit_cycle_terminates() -> None:
    """``a ::= b``, ``b ::= a``: the pass never takes a second same-column
    step, so the climb ends, and the document is refused as ambiguous."""
    compiled = compile_text('a ::= b | "x" a | "x"\nb ::= a\n', cache_key="leo-cycle")
    product = model_product(compiled.codegen_grammar, compiled.product)
    with pytest.raises(UnsupportedConstructError):
        earley_model(
            product.instance_grammar, "x" * 50, compiled.product, product.tables
        )


def test_a_unit_step_passed_in_an_open_column_is_an_invariant_breach() -> None:
    """A climb starts below the current column and descends, so the column a
    unit step is passed in is closed and its waiters final; one that is not
    would let the pass skip a completion a later waiter needs."""
    grammar = normalize(compile_text(SPELLINGS["recursive-first"]).codegen_grammar)
    tables = compile_tables(grammar)
    kern = Kernel(tables, "abc;abc;", True).run()
    arm = tables.decode.rule_ids["root-arm1"]
    assert tables.codes.unit_start[
        leo_sole(kern.st, tables, 4, arm) >> tables.packing.bits
    ], "column 4's waiter is no unit arm — the test proves nothing"
    with pytest.raises(EngineInvariantError):
        leo_resolve(kern.st, tables, 4, 4, arm)
